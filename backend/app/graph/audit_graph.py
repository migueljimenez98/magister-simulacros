"""Audit graph for simulacros — scores one role-play call end to end.

Topology (single dimension, no CRM, no lead management):

    ingest_retell        transcript (from Retell) → one `simulacro` slice
        │
        ▼
    load_rules_kb        project rules + prompts + KB context (guión)
        │
        ▼
    [score_param × N]    one Send per rule (parallel); LLM grades each
        │
        ▼
    aggregate_totals     per-dimension subtotal + global percent
        │
        ▼
    [compose_feedback ‖ compose_report]
        │
        ▼
    persist ─► END

The simulacro is scored under the `informacion_telefonica` dimension so the
coach (info_call tier) and composer work as-is. If a node marks the row
`failed`, the fan-outs short-circuit to persist.
"""
from __future__ import annotations

from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..services.project_prompts import (
    feedback_prompt,
    report_prompt,
    system_prompt_for,
)
from .nodes import (
    aggregate_totals,
    compose_feedback,
    compose_report,
    ingest_retell,
    load_rules_kb,
    persist,
    score_param,
)
from .state import AuditState

DEFAULT_DIMENSION = "informacion_telefonica"


def _dimension_of(rule: dict[str, Any]) -> str:
    return (rule.get("dimension") or DEFAULT_DIMENSION).strip() or DEFAULT_DIMENSION


def _route_after_slice(state: AuditState):
    """Fan out one Send per rule, or jump to persist if upstream failed."""
    if state.get("status") == "failed":
        return "persist"

    rules = state.get("rules_table", []) or []
    kb_context = state.get("kb_context", []) or []
    prompts = state.get("prompts") or {}
    slices = state.get("slices") or {}
    standing = state.get("standing_instruction", "") or ""
    project_config = state.get("project_config") or {}

    sends: list[Send] = []
    for rule in rules:
        dim = _dimension_of(rule)
        slice_ = slices.get(dim) or {"empty": True}
        sends.append(
            Send(
                "score_param",
                {
                    "rule": rule,
                    "dimension": dim,
                    "slice": slice_,
                    "kb_context": kb_context,
                    "agente": state.get("agente", ""),
                    "numero": state.get("numero", ""),
                    "call_date": state.get("call_date"),
                    "analysis_mode": state.get("analysis_mode", "statistical"),
                    "system_block": system_prompt_for(prompts, dim),
                    "standing_instruction": standing,
                    "project_config": project_config,
                },
            )
        )
    return sends


def _route_after_aggregate(state: AuditState):
    """Fan out feedback + report in parallel (or short-circuit to persist)."""
    if state.get("status") == "failed":
        return "persist"
    prompts = state.get("prompts") or {}
    base = {
        "scores": state.get("scores", {}),
        "scores_by_dimension": state.get("scores_by_dimension", {}),
        "rules_table": state.get("rules_table", []),
        "slices": state.get("slices", {}),
        "agente": state.get("agente", ""),
        "analysis_mode": state.get("analysis_mode", "statistical"),
        "total_score": state.get("total_score"),
        "ideal_score": state.get("ideal_score"),
        "percent_quality": state.get("percent_quality"),
        "standing_instruction": state.get("standing_instruction", ""),
        "kb_collection_id": state.get("kb_collection_id") or "",
    }
    return [
        Send("compose_feedback", {**base, "system_block": feedback_prompt(prompts)}),
        Send("compose_report",   {**base, "system_block": report_prompt(prompts)}),
    ]


def build_audit_graph() -> StateGraph:
    g = StateGraph(AuditState)

    g.add_node("ingest_retell", ingest_retell.run)
    g.add_node("load_rules_kb", load_rules_kb.run)
    g.add_node("score_param", score_param.run)
    g.add_node("aggregate_totals", aggregate_totals.run)
    g.add_node("compose_feedback", compose_feedback.run)
    g.add_node("compose_report", compose_report.run)
    g.add_node("persist", persist.run)

    g.add_edge(START, "ingest_retell")
    g.add_edge("ingest_retell", "load_rules_kb")
    g.add_conditional_edges(
        "load_rules_kb", _route_after_slice, ["score_param", "persist"]
    )
    g.add_edge("score_param", "aggregate_totals")
    g.add_conditional_edges(
        "aggregate_totals",
        _route_after_aggregate,
        ["compose_feedback", "compose_report", "persist"],
    )
    g.add_edge("compose_feedback", "persist")
    g.add_edge("compose_report", "persist")
    g.add_edge("persist", END)

    return g
