"""load_rules_kb — fetch the project's rules_table + KB context.

Two operations: a quick SELECT for the project, and a slower pgvector
search using a Whisper-rate embedding service. They are done in TWO
SEPARATE sessions so the slow embedding call does NOT keep a Postgres
transaction open — under bulk dispatches the transaction-leak from a
single long session pinned the whole pool and silently deadlocked the
graph.
"""
from __future__ import annotations

import structlog
from sqlalchemy import select

from ...core.db import get_session
from ...core.models import QualityProject
from ...services.kb_vector import embed as kb_embed, query_chunks as kb_query
from ...services.project_prompts import normalize as normalize_prompts
from ..state import AuditState

log = structlog.get_logger()


async def _load_project(project_id: str) -> QualityProject | None:
    async with get_session() as s:
        return (await s.execute(
            select(QualityProject).where(QualityProject.id == project_id)
        )).scalar_one_or_none()


async def run(state: AuditState) -> dict:
    project_id = state.get("project_id")
    transcript = state.get("transcript") or ""

    # 1) Short session — just load the project. Closes BEFORE the slow
    # embedding call below so the connection returns to the pool.
    project = await _load_project(project_id)

    # If fetch_crm already marked the audit as failed, short-circuit.
    if state.get("status") == "failed":
        rules = (project.rules_table if project else []) or []
        cfg = (project.config if project else {}) or {}
        return {
            "status": "failed",
            "rules_table": rules,
            "kb_context": [],
            "analysis_mode": (project.analysis_mode if project else "statistical"),
            "prompts": normalize_prompts(project.prompts if project else None),
            "standing_instruction": cfg.get("standing_instruction", ""),
            "project_config": cfg,
        }

    if not project:
        return {
            "status": "failed",
            "errors": [f"project_not_found: {project_id}"],
            "rules_table": [],
            "kb_context": [],
        }

    rules = project.rules_table or []
    if not rules:
        return {
            "status": "failed",
            "errors": [f"project_has_no_rules: {project_id}"],
            "rules_table": [],
            "kb_context": [],
        }

    analysis_mode = project.analysis_mode or "statistical"
    collection_id = project.kb_collection_id
    project_prompts = project.prompts
    project_config = project.config or {}
    # `project` is detached from the session here — we copied what we need.

    # 2) KB search — split into:
    #   2a) embed(): slow network call to Ollama, NO DB session held.
    #   2b) query_chunks(): quick pgvector query inside a fresh session.
    # Holding the session during the embedding call leaks "idle in
    # transaction" connections under bulk dispatches and deadlocks Postgres.
    kb_context: list[dict] = []
    if transcript:
        try:
            [vec] = await kb_embed([transcript[:4000]])
        except Exception as exc:
            log.warning("kb_embed_failed", project_id=project_id, error=str(exc)[:200])
            vec = None

        if vec is not None:
            try:
                async with get_session() as s2:
                    kb_context = await kb_query(
                        s2,
                        collection_id=collection_id,
                        vector=vec,
                        top_k=8,
                    )
            except Exception as exc:
                log.warning("kb_query_failed", project_id=project_id, error=str(exc)[:200])
                kb_context = []

    return {
        "status": "scoring",
        "rules_table": rules,
        "kb_context": kb_context,
        # Propagamos el collection_id al state para que el Coach
        # (moderador) pueda hacer su propia query KB con ancla por tier.
        "kb_collection_id": collection_id or "",
        "analysis_mode": analysis_mode,
        "prompts": normalize_prompts(project_prompts),
        "standing_instruction": project_config.get("standing_instruction", ""),
        "project_config": project_config,
    }
