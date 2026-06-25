"""compose_feedback — short message to the asesora.

The coach now generates feedback PER VERTICAL (info_call / info_whatsapp /
gestion) in parallel; we persist the priority winner in
`feedback_message` AND the full dict in `feedback_by_vertical` so the
dashboard can show all three with the cascade selection visible.
"""
from __future__ import annotations

from typing import Any

import structlog

from ...agents.coach import compose

log = structlog.get_logger()


async def run(payload: dict[str, Any]) -> dict:
    try:
        text = await compose(payload)
        # `compose()` stashes per-vertical results AND per-gap validation
        # notes inside the payload. Lift everything to state so persist
        # can write it to the row.
        by_vertical = payload.get("_feedback_by_vertical") or {}
        selected_tier = payload.get("_feedback_selected_tier") or ""
        validation_notes = payload.get("_coach_validation_notes") or []
        return {
            "feedback_message": text,
            "feedback_by_vertical": by_vertical,
            "feedback_selected_tier": selected_tier,
            "coach_validation_notes": validation_notes,
        }
    except Exception as exc:
        log.warning("compose_feedback_failed", error=str(exc)[:200])
        return {
            "feedback_message": "",
            "feedback_by_vertical": {},
            "feedback_selected_tier": "",
            "coach_validation_notes": [],
            "errors": [f"compose_feedback_failed: {exc}"[:500]],
        }
