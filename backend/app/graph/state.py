"""Audit graph state for simulacros.

Single TypedDict shared by every node. Reducer-annotated fields merge across
parallel branches (Send fan-out); the rest are last-write-wins.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, TypedDict


def _merge_dicts(left: dict, right: dict) -> dict:
    return {**left, **right}


def _extend_list(left: list, right: list) -> list:
    return [*left, *right]


class ParamScore(TypedDict, total=False):
    score: float | None
    max: float | None
    note: str
    etiqueta: str | None
    observacion: str | None
    evidencia: list[str]
    gap: str | None
    dimension: str
    applied: bool
    na_reason: str


AuditStatus = Literal[
    "pending", "fetching", "scoring", "composing", "persisting", "done", "failed",
]


class AuditState(TypedDict, total=False):
    # Inputs (set by the Retell webhook when triggering the audit)
    analysis_id: str
    project_id: str
    numero: str
    agente: str
    call_date: datetime | None
    instruction: str | None
    analysis_mode: Literal["statistical", "qualitative"]
    # Per-department evaluador override: {rules_table, prompts}. Empty → project default.
    evaluador_override: dict[str, Any]

    # Filled by ingest_retell
    crm_snapshot: dict[str, Any]
    transcript: str
    channel: str
    source_field: str
    slices: dict[str, dict[str, Any]]

    # Filled by load_rules_kb
    rules_table: list[dict[str, Any]]
    kb_context: list[dict[str, Any]]
    kb_collection_id: str
    prompts: dict[str, Any]
    standing_instruction: str
    project_config: dict[str, Any]

    # Filled by score_param (parallel) → merged
    scores: Annotated[dict[str, ParamScore], _merge_dicts]

    # Filled by aggregate_totals
    total_score: float
    ideal_score: float
    percent_quality: float
    scores_by_dimension: dict[str, dict[str, Any]]

    # Filled by compose_feedback / compose_report
    feedback_message: str
    feedback_by_vertical: dict[str, str]
    feedback_selected_tier: str
    coach_validation_notes: list[dict[str, Any]]
    detailed_report: str

    # Bookkeeping
    status: AuditStatus
    errors: Annotated[list[str], _extend_list]
