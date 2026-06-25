"""aggregate_totals — per-dimension subtotals + global percent_quality.

Pure arithmetic. No LLM call. Deterministic.

Per dimension and per rule, score_param marks each result with one of:
  - applied=True                                  → counts toward both
                                                    subtotal AND global.
  - applied=False, na_reason="rule_inapplicable" → excluded from both.
                                                    The rule literally doesn't
                                                    apply to this case (madrid
                                                    rule with unknown CCAA,
                                                    speaker mismatch, etc.).
  - applied=False, na_reason="channel_empty"     → "the lead had no data in
                                                    this channel" (no calls,
                                                    no emails, etc.). The
                                                    project decides via
                                                    `config.empty_channels_drag_down`:
                                                       false (default) → excluded
                                                                         (legacy
                                                                         behavior).
                                                       true (unified)   → counted
                                                                         as 0/max
                                                                         (drags
                                                                         down the
                                                                         global).

The unified dashboard sets `empty_channels_drag_down=true` so a lead with
only WhatsApps (no call, no email) shows the gap loud and clear in the
global percent. Old projects don't set the flag and keep their pre-existing
"exclude n/a" semantics.
"""
from __future__ import annotations

from collections import defaultdict

from ..state import AuditState


async def run(state: AuditState) -> dict:
    scores = state.get("scores", {}) or {}
    project_config = state.get("project_config") or {}
    drag_down_empty = bool(project_config.get("empty_channels_drag_down"))

    # Per-dimension accumulators
    dim_total: dict[str, float] = defaultdict(float)
    dim_ideal: dict[str, float] = defaultdict(float)
    dim_applied: dict[str, bool] = defaultdict(bool)
    dim_count_applied: dict[str, int] = defaultdict(int)
    dim_count_total: dict[str, int] = defaultdict(int)
    # Track empty-channel rules that we MIGHT count as 0 (drag-down mode).
    dim_empty_total: dict[str, float] = defaultdict(float)   # always 0, kept for symmetry
    dim_empty_ideal: dict[str, float] = defaultdict(float)
    dim_empty_count: dict[str, int] = defaultdict(int)

    for s in scores.values():
        dim = s.get("dimension") or "llamada"
        dim_count_total[dim] += 1
        if s.get("applied"):
            dim_applied[dim] = True
            dim_count_applied[dim] += 1
            dim_total[dim] += float(s.get("score") or 0.0)
            dim_ideal[dim] += float(s.get("max") or 0.0)
        elif s.get("na_reason") == "channel_empty":
            dim_empty_ideal[dim] += float(s.get("max") or 0.0)
            dim_empty_count[dim] += 1
        # rule_inapplicable / "" → excluded from both, as before.

    scores_by_dimension: dict[str, dict] = {}
    seen_dims = set(dim_count_total.keys())
    for dim in seen_dims:
        # Combine applied + (drag-down) empty buckets if the project opts in.
        if drag_down_empty:
            dim_total[dim] += dim_empty_total[dim]      # always 0, but explicit
            dim_ideal[dim] += dim_empty_ideal[dim]
            if dim_empty_count[dim] > 0 and not dim_applied[dim]:
                dim_applied[dim] = True
                dim_count_applied[dim] += dim_empty_count[dim]

        if dim_applied[dim] and dim_ideal[dim] > 0:
            scores_by_dimension[dim] = {
                "applied": True,
                "n_rules": dim_count_applied[dim],
                "total": round(dim_total[dim], 2),
                "ideal": round(dim_ideal[dim], 2),
                "percent": round(100.0 * dim_total[dim] / dim_ideal[dim], 2),
                # Useful for the dashboard to flag "vertical drag-down" when
                # a dim is at 0% purely because the channel was empty.
                "empty_channel_rules": dim_empty_count[dim] if drag_down_empty else 0,
            }
        else:
            scores_by_dimension[dim] = {
                "applied": False,
                "n_rules": dim_count_total[dim],
            }

    total = round(sum(d["total"] for d in scores_by_dimension.values() if d.get("applied")), 2)
    ideal = round(sum(d["ideal"] for d in scores_by_dimension.values() if d.get("applied")), 2)
    pct = round(100.0 * total / ideal, 2) if ideal > 0 else 0.0

    return {
        "status": "composing",
        "total_score": total,
        "ideal_score": ideal,
        "percent_quality": pct,
        "scores_by_dimension": scores_by_dimension,
    }
