"""Analyses (simulacros) API — list, detail, delete, re-run."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from ..core.models import QualityAnalysis
from .deps import SessionDep, current_user, get_audit_graph, require_role

log = structlog.get_logger()
router = APIRouter(prefix="/analyses", tags=["analyses"], dependencies=[Depends(current_user)])


class AnalysisOut(BaseModel):
    id: str
    project_id: str
    numero: str
    agente_nombre: str
    call_date: datetime | None
    status: str
    total_score: float | None
    ideal_score: float | None
    percent_quality: float | None
    feedback_message: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime
    scores: dict[str, Any] = Field(default_factory=dict)
    scores_by_dimension: dict[str, Any] = Field(default_factory=dict)
    feedback_by_vertical: dict[str, Any] = Field(default_factory=dict)
    feedback_selected_tier: str | None = None

    class Config:
        from_attributes = True


class AnalysisDetail(AnalysisOut):
    detailed_report: str | None = None
    instruction: str | None = None
    crm_snapshot: dict[str, Any] = Field(default_factory=dict)
    coach_validation_notes: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisListOut(BaseModel):
    items: list[AnalysisOut]
    total: int
    limit: int
    offset: int


_LIST_COLUMNS = (
    QualityAnalysis.id, QualityAnalysis.project_id, QualityAnalysis.numero,
    QualityAnalysis.agente_nombre, QualityAnalysis.call_date, QualityAnalysis.status,
    QualityAnalysis.total_score, QualityAnalysis.ideal_score, QualityAnalysis.percent_quality,
    QualityAnalysis.feedback_message, QualityAnalysis.error, QualityAnalysis.created_at,
    QualityAnalysis.updated_at, QualityAnalysis.scores, QualityAnalysis.scores_by_dimension,
    QualityAnalysis.feedback_by_vertical, QualityAnalysis.feedback_selected_tier,
)


@router.get("", response_model=AnalysisListOut)
async def list_analyses(
    session: SessionDep,
    project_id: str | None = None,
    agente: str | None = None,
    status_filter: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AnalysisListOut:
    limit = max(1, min(limit, 500))
    conds = []
    if project_id:
        conds.append(QualityAnalysis.project_id == project_id)
    if agente:
        conds.append(QualityAnalysis.agente_nombre == agente)
    if status_filter:
        conds.append(QualityAnalysis.status == status_filter)
    if search:
        conds.append(QualityAnalysis.agente_nombre.ilike(f"%{search}%"))

    total_stmt = select(func.count()).select_from(QualityAnalysis)
    rows_stmt = select(*_LIST_COLUMNS).order_by(desc(QualityAnalysis.created_at)).limit(limit).offset(offset)
    for c in conds:
        total_stmt = total_stmt.where(c)
        rows_stmt = rows_stmt.where(c)

    total = (await session.execute(total_stmt)).scalar_one()
    rows = (await session.execute(rows_stmt)).mappings().all()
    items = [AnalysisOut(**dict(r)) for r in rows]
    return AnalysisListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/facets")
async def facets(session: SessionDep, project_id: str | None = None) -> dict[str, list[str]]:
    ag = select(QualityAnalysis.agente_nombre).distinct()
    st = select(QualityAnalysis.status).distinct()
    if project_id:
        ag = ag.where(QualityAnalysis.project_id == project_id)
        st = st.where(QualityAnalysis.project_id == project_id)
    agentes = [r for (r,) in (await session.execute(ag)).all() if r]
    estados = [r for (r,) in (await session.execute(st)).all() if r]
    return {"agentes": sorted(agentes), "estados": sorted(estados)}


@router.get("/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(analysis_id: str, session: SessionDep) -> QualityAnalysis:
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    return row


@router.delete("/{analysis_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def delete_analysis(analysis_id: str, session: SessionDep) -> None:
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    await session.delete(row)
    await session.commit()


@router.post("/{analysis_id}/redispatch", status_code=202, response_model=AnalysisOut,
             dependencies=[Depends(require_role("admin"))])
async def redispatch_analysis(
    analysis_id: str, session: SessionDep, background: BackgroundTasks, graph=Depends(get_audit_graph),
) -> QualityAnalysis:
    """Re-run the simulacro audit from the stored transcript."""
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    row.status = "pending"
    row.scores = {}
    row.scores_by_dimension = {}
    row.total_score = None
    row.ideal_score = None
    row.percent_quality = None
    row.feedback_message = None
    row.detailed_report = None
    row.error = None
    snap = row.crm_snapshot or {}
    await session.commit()
    await session.refresh(row)

    from .retell import _run_simulacro_audit  # local import avoids cycle
    transcript = snap.get("transcript") or (snap.get("_simulacro") or {}).get("transcript") or ""
    background.add_task(
        _run_simulacro_audit, graph, row.id, row.agente_nombre, row.call_date, transcript, snap,
    )
    return row
