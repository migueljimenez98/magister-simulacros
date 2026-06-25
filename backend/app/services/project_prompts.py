"""Normalize the per-project `prompts` JSONB into a stable shape.

Two formats coexist:

  Legacy (pre-migration 0005):
    { "system_block": "...", "auditor": "...", "coach": "...", "composer": "..." }

  New (post-migration 0005):
    {
      "dimensions": {
        "llamada":   {"label": "Llamada",   "system_prompt": "..."},
        "whatsapps": {"label": "WhatsApps", "system_prompt": "..."}
      },
      "feedback": {"system_prompt": "..."},
      "report":   {"system_prompt": "..."}
    }

This module returns the new shape no matter what the DB contains. Legacy
projects get their `system_block` (or `auditor` override) routed to the
"llamada" dimension and feedback/report are left empty (will fall back to
hardcoded baseline copy in coach.py / composer.py).
"""
from __future__ import annotations

from typing import Any

DIMENSIONS = (
    ("llamada", "Llamada"),
    ("whatsapps", "Gestión de WhatsApps"),
    # ("procedimientos", "Gestión de procedimientos") — archivada 2026-04-27.
    # Restauración: ver exports/procedimientos-archivado.md
)


def normalize(prompts_jsonb: dict[str, Any] | None) -> dict[str, Any]:
    """Return the new shape regardless of what the DB stores."""
    p = dict(prompts_jsonb or {})

    # Already new shape — top up missing dimensions/feedback/report with empties.
    if "dimensions" in p and isinstance(p["dimensions"], dict):
        dims = dict(p["dimensions"])
        for dim_id, label in DIMENSIONS:
            if dim_id not in dims or not isinstance(dims[dim_id], dict):
                dims[dim_id] = {"label": label, "system_prompt": ""}
            else:
                dims[dim_id].setdefault("label", label)
                dims[dim_id].setdefault("system_prompt", "")
        return {
            "dimensions": dims,
            "feedback": p.get("feedback") or {"system_prompt": ""},
            "report":   p.get("report")   or {"system_prompt": ""},
        }

    # Legacy — route system_block (or auditor) into "llamada"; leave others empty.
    legacy_block = (p.get("system_block") or p.get("auditor") or "").strip()
    legacy_coach = (p.get("coach") or "").strip()
    legacy_composer = (p.get("composer") or "").strip()
    return {
        "dimensions": {
            "llamada":   {"label": "Llamada",              "system_prompt": legacy_block},
            "whatsapps": {"label": "Gestión de WhatsApps", "system_prompt": ""},
            # procedimientos: archivada 2026-04-27 — exports/procedimientos-archivado.md
        },
        "feedback": {"system_prompt": legacy_coach},
        "report":   {"system_prompt": legacy_composer},
    }


def system_prompt_for(prompts_norm: dict[str, Any], dimension_id: str) -> str:
    return ((prompts_norm.get("dimensions") or {}).get(dimension_id) or {}).get("system_prompt", "")


def feedback_prompt(prompts_norm: dict[str, Any]) -> str:
    return (prompts_norm.get("feedback") or {}).get("system_prompt", "")


def report_prompt(prompts_norm: dict[str, Any]) -> str:
    return (prompts_norm.get("report") or {}).get("system_prompt", "")
