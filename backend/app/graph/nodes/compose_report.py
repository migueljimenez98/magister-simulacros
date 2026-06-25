"""compose_report — long-form executive markdown report."""
from __future__ import annotations

from typing import Any

import structlog

from ...agents.composer import compose

log = structlog.get_logger()


async def run(payload: dict[str, Any]) -> dict:
    try:
        text = await compose(payload)
        return {"detailed_report": text}
    except Exception as exc:
        log.warning("compose_report_failed", error=str(exc)[:200])
        return {
            "detailed_report": "",
            "errors": [f"compose_report_failed: {exc}"[:500]],
        }
