"""Single-slot turn queue for simulacros (public panel + CRM).

Only ONE simulacro is "armed" for Retell at a time. Acquiring a turn arms the
inbound match; the turn is RELEASED the instant the call CONNECTS (inbound-vars
fires) — NOT when it ends (Retell allows concurrent calls) — or after a 45s
margin if the person never calls. The next person in the FIFO queue is then
promoted automatically.

In-memory, single process (one Render instance) — resets on restart, which is
fine: turns are ephemeral.

Used by:
  - the public `/simulacros/cola/join` + `/status` endpoints (panel sin login),
  - the CRM/Dev announce path via `take_now()` (the call is imminent, so it
    claims the slot immediately, bumping any waiting panel turn to the front),
  - `inbound_dynamic_variables` via `match_and_consume()` (call connected →
    attribute + release the turn).
"""
from __future__ import annotations

import re
import threading
import time

from ..core.config import settings

HOLD_SECONDS = 45.0        # margin to start the call once it's your turn
WAITING_STALE = 12.0       # drop a waiting ticket whose panel stopped polling
STARTED_TTL = 90.0         # how long we remember "your call connected" for the panel

_lock = threading.Lock()
_active: dict | None = None
_waiting: list[dict] = []
_started: dict[str, float] = {}   # ticket -> ts when its call connected
_seq = 0


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _numero() -> str:
    return settings.retell_from_number or ""


def _new_ticket() -> str:
    global _seq
    _seq += 1
    return f"t{_seq}"


def _promote_locked(now: float) -> None:
    """Release the current active turn and promote the next waiting one."""
    global _active
    if _waiting:
        w = _waiting.pop(0)
        _active = {**w, "deadline": now + HOLD_SECONDS}
    else:
        _active = None


def _gc_locked(now: float) -> None:
    global _active
    # Forget old "your call connected" markers.
    for t in [t for t, ts in _started.items() if now - ts > STARTED_TTL]:
        _started.pop(t, None)
    # Drop waiting tickets whose panel stopped polling (closed tab).
    _waiting[:] = [w for w in _waiting if now - w["last_seen"] <= WAITING_STALE]
    # Expire the active turn if its margin elapsed without a call → promote next.
    if _active and now >= _active["deadline"]:
        _promote_locked(now)
    elif _active is None and _waiting:
        _promote_locked(now)


def _status_locked(ticket: str, now: float) -> dict:
    if _active and _active["ticket"] == ticket:
        return {
            "status": "active",
            "numero": _numero(),
            "seconds_left": max(0, int(round(_active["deadline"] - now))),
            "nombre": _active["nombre"],
        }
    for i, w in enumerate(_waiting):
        if w["ticket"] == ticket:
            return {"status": "waiting", "position": i + 1, "ahead": i, "numero": _numero(), "nombre": w["nombre"]}
    if ticket in _started:
        return {"status": "started", "numero": _numero()}
    return {"status": "expired", "numero": _numero()}


def join(nombre: str, from_number: str = "", scenario_id: str = "") -> dict:
    """Request a turn. Becomes active immediately if the slot is free, else
    enters the FIFO queue. Returns the ticket + current status."""
    now = time.monotonic()
    with _lock:
        _gc_locked(now)
        ticket = _new_ticket()
        entry = {
            "ticket": ticket, "nombre": nombre, "from_number": _digits(from_number),
            "scenario_id": scenario_id or "", "last_seen": now,
        }
        global _active
        if _active is None:
            _active = {**entry, "deadline": now + HOLD_SECONDS}
        else:
            _waiting.append(entry)
        return {"ticket": ticket, **_status_locked(ticket, now)}


def poll(ticket: str) -> dict:
    """Status of a ticket. Refreshes its liveness so an open panel keeps its
    place in the queue."""
    now = time.monotonic()
    with _lock:
        if _active and _active["ticket"] == ticket:
            _active["last_seen"] = now
        for w in _waiting:
            if w["ticket"] == ticket:
                w["last_seen"] = now
        _gc_locked(now)
        return _status_locked(ticket, now)


def take_now(nombre: str, from_number: str = "", scenario_id: str = "") -> None:
    """CRM / Dev simulator: claim the slot immediately (the call is imminent and
    won't wait). Any current panel turn is pushed to the FRONT of the queue so
    it isn't lost — it resumes once this call connects or its margin expires."""
    now = time.monotonic()
    with _lock:
        _gc_locked(now)
        global _active
        if _active is not None:
            bumped = {k: _active[k] for k in ("ticket", "nombre", "from_number", "scenario_id")}
            bumped["last_seen"] = now
            _waiting.insert(0, bumped)
        _active = {
            "ticket": _new_ticket(), "nombre": nombre, "from_number": _digits(from_number),
            "scenario_id": scenario_id or "", "last_seen": now, "deadline": now + HOLD_SECONDS,
        }


def match_and_consume(from_number: str = "") -> dict | None:
    """Inbound-vars calls this when a call connects: attribute it to the armed
    comercial and RELEASE the turn (promote the next). With a single armed slot
    we attribute to the active holder; from_number is only a sanity hint."""
    now = time.monotonic()
    with _lock:
        _gc_locked(now)
        global _active
        if _active is None:
            return None
        result = {"agente": _active["nombre"], "scenario_id": _active.get("scenario_id") or ""}
        _started[_active["ticket"]] = now   # so the panel can show "call detected"
        _promote_locked(now)
        return result


def snapshot() -> dict:
    """Debug view of the current turn + queue."""
    now = time.monotonic()
    with _lock:
        _gc_locked(now)
        return {
            "active": (
                {"nombre": _active["nombre"], "seconds_left": max(0, int(round(_active["deadline"] - now)))}
                if _active else None
            ),
            "waiting": [{"nombre": w["nombre"], "position": i + 1} for i, w in enumerate(_waiting)],
        }
