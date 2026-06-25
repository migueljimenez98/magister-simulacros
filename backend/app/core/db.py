"""Database engine + LangGraph checkpointer wiring.

Two clients live here:
  - `engine` / `async_session`: SQLAlchemy async, used by FastAPI routes and
    services. Connection pool sized for the API's request workload.
  - `checkpointer`: LangGraph AsyncPostgresSaver. Persists graph state per
    audit so a crashed run can be resumed from the last completed node
    instead of replayed from scratch.

Three traps with AsyncPostgresSaver (verified painfully in agents-autonomy):
  1. The underlying psycopg pool MUST run with autocommit=True. Without it,
     LangGraph's setup() opens a transaction that the migration DDL implicitly
     commits, and you end up with idle-in-transaction connections that
     CONCURRENTLY index creation cannot bypass.
  2. CONCURRENTLY index creation in setup() conflicts with idle transactions
     on the same DB. Run setup() once at startup against a *clean* connection.
  3. Pre-interrupt code in graph nodes runs twice on resume — design nodes
     to be idempotent or guard with a "already done" check.
"""
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .config import settings


# Pool tuned for bulk audits. Each audit holds 1 session for fetch_crm,
# 1 for load_rules_kb, then up to N short-lived sessions for score_param
# (one per rule, mostly read-only and quick). With ~20 rules and bulk
# dispatches of 15-60 audits, the worst case briefly needs ~80-100 conns.
# Postgres max_connections defaults to 100; we sit comfortably under.
# Pool budget (vs Postgres max_connections=100):
#   - engine SQLAlchemy: 15 base + 30 overflow = 45 max
#   - checkpointer psycopg pool: 30 max
#   - reserved for psql / other tools: ~25
# Total under load: ~75 — safely under the 100 cap.
engine = create_async_engine(
    settings.database_url,
    pool_size=15,
    max_overflow=30,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=False,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_session() -> AsyncIterator[AsyncSession]:
    """Async session that always closes its transaction.

    Without an explicit commit/rollback, a session that runs even a single
    SELECT returns its connection to the pool in `idle in transaction`
    state — which silently exhausts Postgres and deadlocks bulk dispatches.
    """
    async with async_session() as s:
        try:
            yield s
            await s.commit()
        except Exception:
            await s.rollback()
            raise


# Singleton pool + checkpointer. Initialized once at app startup.
_pool: AsyncConnectionPool | None = None
_checkpointer: AsyncPostgresSaver | None = None


async def init_checkpointer() -> AsyncPostgresSaver:
    """Open the psycopg pool and run AsyncPostgresSaver.setup() once.

    Call from FastAPI lifespan startup. Subsequent calls return the cached
    instance.
    """
    global _pool, _checkpointer
    if _checkpointer is not None:
        return _checkpointer

    _pool = AsyncConnectionPool(
        conninfo=settings.checkpoint_dsn,
        # Each audit writes ~7 checkpoints; with 14 in parallel that's a
        # bursty 100+ ops competing for the pool. 30 covers it without
        # starving SQLAlchemy.
        max_size=30,
        min_size=5,
        kwargs={"autocommit": True},   # trap #1
        open=False,
    )
    await _pool.open()
    _checkpointer = AsyncPostgresSaver(_pool)
    await _checkpointer.setup()  # creates langgraph_checkpoints + indexes
    return _checkpointer


def get_checkpointer() -> AsyncPostgresSaver:
    if _checkpointer is None:
        raise RuntimeError("Checkpointer not initialized — call init_checkpointer()")
    return _checkpointer


async def close_checkpointer() -> None:
    global _pool, _checkpointer
    if _pool is not None:
        await _pool.close()
    _pool = None
    _checkpointer = None
