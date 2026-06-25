"""KB bootstrap — auto-ingest baked-in markdown docs at startup.

Replaces the manual `docker cp ... && python -m scripts.ingest_md` flow.
On every API start, for every project, for every .md mounted at
`/app/docs/`:
  1. Compare the .md filename + size against `kb_documents` in the
     project's collection.
  2. If the file is new OR its size changed → ingest (replaces chunks).
  3. If the file is identical to what's already in the DB → skip.

This is per-FILE, not per-collection. The previous version's blunt
"if collection has any rows → skip everything" was bad: it meant a doc
added to /docs after the first boot would NEVER get ingested.

The docs folder is bind-mounted from the host (`docker-compose.yml`
volumes), so editing a .md and restarting the api container is enough
to refresh the KB. Image rebuild not required.

Designed to fail SOFT: if anything goes wrong, log a warning and let
the API start anyway. The audit graph degrades gracefully — empty KB
means the auditor gets no `kb_context` chunks, which is unhelpful but
not crashy.
"""
from __future__ import annotations

from pathlib import Path

import structlog
from sqlalchemy import select

from ..core.db import get_session
from ..core.models import KbDocument, QualityProject
from .kb_ingest import ingest_text

log = structlog.get_logger()

DOCS_PATH = Path("/app/docs")


async def _existing_index(s, collection_id: str) -> dict[str, int]:
    """Return {title: file_size} for every doc already in the collection."""
    rows = (await s.execute(
        select(KbDocument.title, KbDocument.file_size)
        .where(KbDocument.collection_id == collection_id)
    )).all()
    return {title: int(size or 0) for title, size in rows}


async def bootstrap_kb() -> None:
    """Per-file diff: ingest /app/docs/*.md into every project's collection
    when the doc is new OR its filesize changed since last ingest."""
    if not DOCS_PATH.exists() or not DOCS_PATH.is_dir():
        log.info("kb_bootstrap_skip_no_docs_dir", path=str(DOCS_PATH))
        return

    md_files = sorted(DOCS_PATH.glob("*.md"))
    if not md_files:
        log.info("kb_bootstrap_skip_no_md_files", path=str(DOCS_PATH))
        return

    async with get_session() as s:
        projects = list((await s.execute(select(QualityProject))).scalars().all())

    if not projects:
        log.info("kb_bootstrap_skip_no_projects")
        return

    # Read each .md once (could be many projects; don't re-read per project).
    file_blobs: dict[str, tuple[str, int]] = {}
    for p in md_files:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
            file_blobs[p.name] = (text, len(text))
        except Exception as exc:
            log.warning("kb_bootstrap_read_failed", file=p.name, error=str(exc)[:200])

    seen_collections: set[str] = set()
    for proj in projects:
        cid = (proj.kb_collection_id or "").strip()
        if not cid or cid in seen_collections:
            continue
        seen_collections.add(cid)
        try:
            async with get_session() as s:
                existing = await _existing_index(s, cid)
                added = 0
                refreshed = 0
                skipped = 0
                for fname, (text, size) in file_blobs.items():
                    prev_size = existing.get(fname)
                    if prev_size == size:
                        skipped += 1
                        continue
                    # New OR changed — ingest. ingest_text replaces by title.
                    await ingest_text(
                        s,
                        collection_id=cid,
                        title=fname,
                        content=text,
                        source="bootstrap",
                        extra_metadata={"original_path": str(DOCS_PATH / fname)},
                    )
                    if prev_size is None:
                        added += 1
                    else:
                        refreshed += 1
                await s.commit()
            log.info(
                "kb_bootstrap_synced",
                collection=cid,
                added=added,
                refreshed=refreshed,
                skipped=skipped,
                files_total=len(file_blobs),
            )
        except Exception as exc:
            log.warning(
                "kb_bootstrap_failed",
                collection=cid,
                error=str(exc)[:200],
            )
