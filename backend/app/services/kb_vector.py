"""Vector search over kb_chunks. Uses pgvector cosine distance.

Embeddings come from the same OpenAI-compatible endpoint configured for the
default LLM. Dimension is fixed at 1536 (text-embedding-3-small / equivalent)
to match the schema. If you swap to a different embedder, write a migration
that ALTERs the vector column dimension and reindexes — don't try to mix.
"""
from __future__ import annotations

from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings


_embed_client: AsyncOpenAI | None = None


def _embed_client_singleton() -> AsyncOpenAI:
    """OpenAI client pointed at the embedding provider. Falls back to the
    chat provider if no separate embedding endpoint is configured — useful
    when you're running against OpenAI's API (chat + embeddings same host)."""
    global _embed_client
    if _embed_client is None:
        base_url = settings.embedding_base_url or settings.default_llm_base_url
        api_key = settings.embedding_api_key or settings.default_llm_api_key or "not-used"
        _embed_client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return _embed_client


async def embed(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    """Embed a batch of texts. Returns one vector per input.

    `model` defaults to settings.embedding_model — anything the configured
    endpoint serves on /v1/embeddings.

    Tested with:
      - OpenAI text-embedding-3-small  (1536)
      - Ollama bge-m3                  (1024)
      - Ollama qwen3-embedding:8b      (4096 native, truncated to 2000)

    Matryoshka truncation: when the model emits more dimensions than
    `settings.embedding_dimensions`, we keep the first N. Qwen3-embedding
    is trained for this — the first 2000 dims are themselves a valid
    embedding (~95% of the full-rank quality at half the storage and
    inside pgvector's HNSW ceiling). Truncating a non-matryoshka model
    would degrade retrieval; only do it for models that advertise it.
    """
    if not texts:
        return []
    cli = _embed_client_singleton()
    resp = await cli.embeddings.create(
        model=model or settings.embedding_model,
        input=texts,
    )
    target = settings.embedding_dimensions
    out: list[list[float]] = []
    for d in resp.data:
        v = d.embedding
        if len(v) > target:
            v = v[:target]
        elif len(v) < target:
            raise RuntimeError(
                f"embedding model returned {len(v)} dims, schema expects "
                f"{target}. Either change embedding_dimensions in settings "
                f"and write a migration, or pick a model that produces "
                f"≥{target} dims."
            )
        out.append(v)
    return out


async def query_chunks(
    session: AsyncSession,
    *,
    collection_id: str,
    vector: list[float],
    top_k: int = 8,
) -> list[dict[str, Any]]:
    """Run the pgvector query against a pre-computed embedding vector.

    Kept separate from the embedding call so callers can compute the
    embedding outside their DB session (the embedding call can be slow
    and we don't want to hold a Postgres connection while it runs).
    """
    # pgvector + asyncpg need the vector as a literal string '[v1,v2,...]'
    # for the CAST to succeed. Sending a Python list crashes with
    # "expected str, got list" because asyncpg doesn't know the vector type
    # (we'd have to register it on every connection — fragile through the
    # SQLAlchemy pool). String literal is portable and small.
    vec_literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"

    rows = await session.execute(
        text(
            """
            SELECT id, document_id, content, extra_metadata,
                   1 - (embedding <=> CAST(:vec AS vector)) AS score
            FROM kb_chunks
            WHERE collection_id = :cid
              AND embedding IS NOT NULL
            ORDER BY embedding <=> CAST(:vec AS vector)
            LIMIT :k
            """
        ),
        {"vec": vec_literal, "cid": collection_id, "k": top_k},
    )
    return [
        {
            "chunk_id": r.id,
            "document_id": r.document_id,
            "content": r.content,
            "score": float(r.score),
            "metadata": r.extra_metadata or {},
        }
        for r in rows
    ]


async def search(
    session: AsyncSession,
    *,
    collection_id: str,
    query: str,
    top_k: int = 8,
    embedder_model: str | None = None,
) -> list[dict[str, Any]]:
    """Convenience wrapper that embeds + queries in one call.

    WARNING for high-concurrency callers: this holds the session for the
    duration of the embedding network call (potentially seconds). For
    bulk dispatches use `embed()` + `query_chunks()` separately so the
    session is only held for the quick SQL.
    """
    if not query or not query.strip():
        return []
    [vec] = await embed([query], model=embedder_model)
    return await query_chunks(session, collection_id=collection_id, vector=vec, top_k=top_k)
