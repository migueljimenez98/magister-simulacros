"""Pending-call announcements for simulacros.

The CRM dials the Retell number like a normal phone call, so the call reaches
us as a plain inbound PSTN call — Retell can't tell us who the comercial is.
But the CRM KNOWS who pressed "call". So just before dialing, the CRM pings
`POST /api/simulacros/announce {agente_nombre, from_number?}` ("Miguel va a
llamar ahora"). When the inbound call arrives we match it to the most recent
announcement and attribute the simulacro to that comercial.

Matching:
  1. If the announcement carried the caller number and it matches the call's
     from_number → use it (robust, survives concurrency).
  2. Otherwise the oldest still-pending announcement within the TTL (FIFO).

Storage is in-memory + TTL: announcements live seconds, and inbound-vars and
the webhook run in the same single api process. Lost on restart (fine — they
are ephemeral). NOTE: with several comerciales dialing in the same few seconds
AND a shared caller ID, FIFO can mis-assign; pass `from_number` to avoid that.
"""
from __future__ import annotations

import re
import threading
import time

_TTL_SECONDS = 180.0
_lock = threading.Lock()
_pending: list[dict] = []


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _gc_locked() -> None:
    global _pending
    now = time.monotonic()
    _pending = [p for p in _pending if not p["consumed"] and (now - p["ts"]) <= _TTL_SECONDS]


def announce(agente: str, from_number: str = "", scenario_id: str = "") -> None:
    with _lock:
        _gc_locked()
        _pending.append({
            "agente": agente,
            "from_number": _digits(from_number),
            "scenario_id": scenario_id or "",
            "ts": time.monotonic(),
            "consumed": False,
        })


def match_and_consume(from_number: str = "") -> dict | None:
    """Return the announced {agente, scenario_id} for an incoming call,
    consuming it. None if no pending announcement matches."""
    d = _digits(from_number)
    now = time.monotonic()
    with _lock:
        _gc_locked()
        cand = [p for p in _pending if not p["consumed"] and (now - p["ts"]) <= _TTL_SECONDS]
        if not cand:
            return None
        chosen = None
        if d:
            for p in cand:
                pd = p["from_number"]
                if pd and (pd == d or d.endswith(pd) or pd.endswith(d)):
                    chosen = p
                    break
        if chosen is None:
            chosen = min(cand, key=lambda p: p["ts"])  # FIFO
        chosen["consumed"] = True
        return {"agente": chosen["agente"], "scenario_id": chosen.get("scenario_id") or ""}


def pending() -> list[dict]:
    """Debug view of currently-pending announcements (non-consumed, in TTL)."""
    now = time.monotonic()
    with _lock:
        _gc_locked()
        return [
            {"agente": p["agente"], "from_number": p["from_number"],
             "scenario_id": p.get("scenario_id") or "", "age_s": round(now - p["ts"], 1)}
            for p in _pending if not p["consumed"]
        ]
