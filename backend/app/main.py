"""FastAPI entrypoint — magister-simulacros.

Lifespan: open the LangGraph checkpointer pool, compile the audit graph,
auto-ingest the KB docs (guión) for the coach grounding.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from .core.config import settings
from .core.db import close_checkpointer, init_checkpointer
from .core.limiter import limiter
from .graph.audit_graph import build_audit_graph

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = structlog.get_logger("magister-simulacros")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup: initializing checkpointer + compiling audit graph")
    checkpointer = await init_checkpointer()
    app.state.audit_graph = build_audit_graph().compile(checkpointer=checkpointer)

    # Auto-ingest /app/docs (guión, plantillas) for the coach grounding.
    # Soft-fails so a missing/embedding issue never blocks startup.
    from .services.kb_bootstrap import bootstrap_kb
    try:
        await bootstrap_kb()
    except Exception as exc:
        log.warning("startup: kb bootstrap failed", error=str(exc)[:200])

    yield
    log.info("shutdown: closing checkpointer pool")
    await close_checkpointer()


app = FastAPI(
    title="Magister Simulacros",
    description="Simulacros de formación comercial (Retell) — evaluación automática.",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


from .api import analyses, auth  # noqa: E402
from .api.retell import retell_router, simulacros_router  # noqa: E402

app.include_router(auth.router, prefix="/api")
app.include_router(analyses.router, prefix="/api")
app.include_router(retell_router, prefix="/api")
app.include_router(simulacros_router, prefix="/api")
