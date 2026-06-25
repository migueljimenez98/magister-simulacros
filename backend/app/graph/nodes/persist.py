"""persist — write the final QualityAnalysis row for a simulacro.

Sole writer to `quality_analyses`. Keyed by analysis_id, so a re-run lands in
the same row. Status is `done` when scoring produced any non-zero applied
score, else `failed`.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import update

from ...core.db import get_session
from ...core.models import QualityAnalysis, SimulacroDepartamento
from ..state import AuditState

log = structlog.get_logger()


def _decimal(v: Any) -> Decimal | None:
    if v is None:
        return None
    try:
        return Decimal(str(v))
    except Exception:
        return None


async def run(state: AuditState) -> dict:
    analysis_id = state.get("analysis_id")
    scores = state.get("scores") or {}
    errors = state.get("errors") or []

    # Status semantics: "failed" means the audit could NOT run, NOT that the
    # call scored badly. A call where every parameter was evaluated but scored
    # 0 is a legitimate (bad) simulacro → "done" with 0%. We only mark "failed"
    # when the call was blocked (no transcript), there was nothing to score, or
    # the auditor itself errored on EVERY parameter (gap == "scoring_error",
    # set by score_param's except branch — typically a missing/invalid LLM key).
    applied = [s for s in scores.values() if s.get("applied")]
    errored = [s for s in applied if s.get("gap") == "scoring_error"]
    scored_ok = len(applied) > len(errored)  # ≥1 parameter got a real verdict
    has_blocked = state.get("crm_snapshot", {}).get("status") == "blocked"
    final_status = "done" if scored_ok and not has_blocked else "failed"
    error_text = "\n".join(errors)[:4000] if errors else None

    # Denormalize guión + departamento for the results table.
    sim = (state.get("crm_snapshot") or {}).get("_simulacro") or {}
    scenario = sim.get("scenario") or {}
    escenario = (scenario.get("nombre") or "").strip() or None
    departamento = None
    dept_id = scenario.get("department_id")
    if dept_id:
        async with get_session() as s:
            dept = await s.get(SimulacroDepartamento, dept_id)
            if dept:
                departamento = dept.nombre

    update_values: dict[str, Any] = dict(
        scores=scores,
        scores_by_dimension=state.get("scores_by_dimension") or {},
        total_score=_decimal(state.get("total_score")),
        ideal_score=_decimal(state.get("ideal_score")),
        percent_quality=_decimal(state.get("percent_quality")),
        feedback_message=state.get("feedback_message") or None,
        feedback_by_vertical=state.get("feedback_by_vertical") or {},
        feedback_selected_tier=state.get("feedback_selected_tier") or None,
        coach_validation_notes=state.get("coach_validation_notes") or [],
        detailed_report=state.get("detailed_report") or None,
        crm_snapshot=state.get("crm_snapshot") or {},
        escenario=escenario,
        departamento=departamento,
        status=final_status,
        error=error_text,
        updated_at=datetime.now(timezone.utc),
    )
    agente = (state.get("agente") or "").strip()
    if agente and not agente.startswith("("):
        update_values["agente_nombre"] = agente

    async with get_session() as s:
        result = await s.execute(
            update(QualityAnalysis)
            .where(QualityAnalysis.id == analysis_id)
            .values(**update_values)
        )
        if result.rowcount == 0:
            log.warning("persist_no_row", analysis_id=analysis_id)
        await s.commit()

    log.info(
        "simulacro_persisted",
        analysis_id=analysis_id, status=final_status,
        params=len(scores), percent=state.get("percent_quality"),
    )
    return {"status": final_status}
