"""KB ingestion — chunk a markdown file, embed, upsert to kb_chunks.

Strategy:
  - Split by paragraph blocks separated by blank lines, then merge until a
    target chunk size of ~1200 chars (≈300 tokens) is reached. Cheap,
    deterministic, no external chunker dependency.
  - Embed in batches of 64 to amortize the OpenAI roundtrip.
  - Idempotent at the document level: if a doc with the same title +
    collection_id exists, replace its chunks. Title is the natural key for
    "this file already imported".

Used by `scripts.ingest_md` for bulk imports and (Phase 3) by the API
upload endpoint.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.models import KbChunk, KbDocument
from . import kb_vector


_TARGET = 1200
_MIN = 200
_MAX = 1800


def chunk_markdown(text: str) -> list[str]:
    """Split a markdown blob into ~1200-char chunks at paragraph boundaries.

    Never breaks mid-paragraph. If a single paragraph exceeds _MAX, it gets
    sliced on sentence boundaries (`.`, `?`, `!`) as a fallback.
    """
    text = text.replace("\r\n", "\n").strip()
    if not text:
        return []

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    chunks: list[str] = []
    buf = ""
    for p in paragraphs:
        if len(p) > _MAX:
            # Hard-split a giant paragraph on sentence boundaries.
            sentences = re.split(r"(?<=[.!?])\s+", p)
            for s in sentences:
                if len(buf) + len(s) + 2 > _MAX and len(buf) >= _MIN:
                    chunks.append(buf.strip())
                    buf = s
                else:
                    buf = f"{buf}\n\n{s}".strip() if buf else s
            continue
        if len(buf) + len(p) + 2 > _TARGET and len(buf) >= _MIN:
            chunks.append(buf.strip())
            buf = p
        else:
            buf = f"{buf}\n\n{p}".strip() if buf else p
    if buf.strip():
        chunks.append(buf.strip())
    return chunks


async def ingest_text(
    session: AsyncSession,
    *,
    collection_id: str,
    title: str,
    content: str,
    source: str = "upload",
    extra_metadata: dict[str, Any] | None = None,
    embedder_model: str | None = None,
) -> tuple[KbDocument, int]:
    """Ingest one markdown blob. Replaces chunks if title + collection_id
    already exist. Returns (doc, chunk_count)."""
    pieces = chunk_markdown(content)
    if not pieces:
        raise ValueError(f"empty content for {title!r}")

    # Replace existing doc with same title in this collection.
    existing = (
        await session.execute(
            select(KbDocument).where(
                KbDocument.collection_id == collection_id, KbDocument.title == title
            )
        )
    ).scalar_one_or_none()
    if existing:
        await session.execute(delete(KbChunk).where(KbChunk.document_id == existing.id))
        doc = existing
        doc.source = source
        doc.file_size = sum(len(p) for p in pieces)
        if extra_metadata is not None:
            doc.extra_metadata = {**(doc.extra_metadata or {}), **extra_metadata}
    else:
        doc = KbDocument(
            collection_id=collection_id,
            title=title,
            source=source,
            file_size=sum(len(p) for p in pieces),
            mime_type="text/markdown",
            extra_metadata=extra_metadata or {},
        )
        session.add(doc)
        await session.flush()  # need doc.id for chunks

    # Embed in batches of 64. Resolve model name now so we record what was
    # actually used in extra_metadata — useful when debugging cross-embedder
    # confusion later.
    actual_model = embedder_model or settings.embedding_model
    vectors: list[list[float]] = []
    for i in range(0, len(pieces), 64):
        batch = pieces[i:i + 64]
        vectors.extend(await kb_vector.embed(batch, model=actual_model))

    for idx, (text, vec) in enumerate(zip(pieces, vectors)):
        session.add(
            KbChunk(
                document_id=doc.id,
                collection_id=collection_id,
                chunk_index=idx,
                content=text,
                embedding=vec,
                extra_metadata={"embedder": actual_model, "title": title},
            )
        )

    await session.commit()
    await session.refresh(doc)
    return doc, len(pieces)


async def ingest_directory(
    session: AsyncSession,
    *,
    folder: Path,
    collection_id: str,
    pattern: str = "*.md",
) -> list[tuple[str, int]]:
    """Walk a folder and ingest every matching file. Returns
    `[(filename, chunk_count), ...]`."""
    out: list[tuple[str, int]] = []
    for p in sorted(folder.glob(pattern)):
        text = p.read_text(encoding="utf-8", errors="ignore")
        try:
            _, n = await ingest_text(
                session,
                collection_id=collection_id,
                title=p.name,
                content=text,
                source="bulk_import",
                extra_metadata={"original_path": str(p)},
            )
            out.append((p.name, n))
        except Exception as exc:
            out.append((p.name, -1))
            print(f"  ✗ {p.name}: {exc}")
    return out
