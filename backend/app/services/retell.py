"""Retell AI integration for the simulacros product.

Three responsibilities:
  1. Build the dynamic variables that turn the single shared Retell agent
     into a specific role-play (persona, difficulty, objections, guión).
  2. Verify inbound webhook signatures (best-effort HMAC-SHA256).
  3. Optionally place an outbound test call via the Retell REST API.

We deliberately avoid a hard dependency on the `retell` SDK so the image
doesn't need it; the REST surface we use is tiny and stable.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx
import structlog

from ..core.config import settings

log = structlog.get_logger()

_TIMEOUT = httpx.Timeout(15.0, connect=5.0)


# ── Dynamic variables ───────────────────────────────────────────────────────


def build_dynamic_variables(
    scenario: dict[str, Any] | None,
    comercial_nombre: str,
    *,
    scenario_id: str = "",
    comercial_id: str = "",
    common_faqs: str = "",
) -> dict[str, str]:
    """Return the {{variable}} values Retell injects into the agent prompt.

    Retell requires string values. We also echo scenario_id / comercial so
    the post-call webhook can recover which scenario ran and who was trained
    (Retell returns these back in `call.retell_llm_dynamic_variables`).

    `common_faqs` is the department's common FAQ block for the relevant level;
    it's merged with the scenario's own FAQs into the single `faqs` variable."""
    s = scenario or {}
    scenario_faqs = str(s.get("faqs") or "").strip()
    common = str(common_faqs or "").strip()
    faqs = "\n\n".join(part for part in (common, scenario_faqs) if part)
    return {
        "persona": str(s.get("persona") or ""),
        "dificultad": str(s.get("dificultad") or "medio"),
        "objeciones": str(s.get("objeciones") or ""),
        "faqs": faqs,
        "guion": str(s.get("guion") or ""),
        # Intención del alumno: el prompt del agente Retell la usa ({{intencion}})
        # para comportarse (p.ej. poco interesado, sin tiempo) e incluso colgar.
        "intencion": str(s.get("intencion") or ""),
        "producto": str(s.get("producto") or ""),
        "escenario_nombre": str(s.get("nombre") or ""),
        "nombre_comercial": str(comercial_nombre or ""),
        # Bookkeeping echoed back by the webhook.
        "scenario_id": str(scenario_id or s.get("id") or ""),
        "comercial_id": str(comercial_id or ""),
    }


# ── Webhook signature verification ──────────────────────────────────────────


def _webhook_secret() -> str:
    return (settings.retell_webhook_secret or settings.retell_api_key or "").strip()


def verify_signature(raw_body: bytes, signature: str | None) -> bool:
    """Best-effort verification of a Retell webhook signature.

    Retell signs the raw request body with the API key (HMAC-SHA256). The
    header may arrive as the bare hex digest or prefixed (e.g. "v=<hex>").
    Returns True when the computed digest matches, False otherwise. The
    caller decides whether to ENFORCE (reject) or just warn — for local /
    pre-production we warn so a scheme mismatch doesn't drop real events.
    """
    secret = _webhook_secret()
    if not secret or not signature:
        return False
    provided = signature.strip()
    if "=" in provided:  # tolerate "v=<hex>" / "t=...,v=<hex>" style prefixes
        provided = provided.split("=")[-1].strip()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


# ── Webhook parsing ─────────────────────────────────────────────────────────


def parse_webhook(payload: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Retell webhook into the fields the ingest flow needs.

    Returns: {event, call_id, agent_id, from_number, to_number, transcript,
              recording_url, dynamic_variables, metadata}.
    """
    call = payload.get("call") or {}
    dyn = (
        call.get("retell_llm_dynamic_variables")
        or call.get("dynamic_variables")
        or {}
    )
    sip = call.get("custom_sip_headers")
    return {
        "event": payload.get("event") or "",
        "call_id": call.get("call_id") or "",
        "agent_id": call.get("agent_id") or "",
        "from_number": call.get("from_number") or "",
        "to_number": call.get("to_number") or "",
        "transcript": _coerce_transcript(call),
        "recording_url": call.get("recording_url") or "",
        "duration_ms": call.get("duration_ms") or call.get("call_duration_ms"),
        "dynamic_variables": dyn if isinstance(dyn, dict) else {},
        "custom_sip_headers": sip if isinstance(sip, dict) else {},
        "metadata": call.get("metadata") if isinstance(call.get("metadata"), dict) else {},
        "call_analysis": call.get("call_analysis") if isinstance(call.get("call_analysis"), dict) else {},
    }


def _coerce_transcript(call: dict[str, Any]) -> str:
    """Retell usually sends a ready-made `transcript` string. Fall back to
    building one from `transcript_object` (list of {role, content})."""
    t = call.get("transcript")
    if isinstance(t, str) and t.strip():
        return t.strip()
    obj = call.get("transcript_object") or call.get("transcript_with_tool_calls")
    if isinstance(obj, list):
        lines = []
        for turn in obj:
            if not isinstance(turn, dict):
                continue
            role = turn.get("role") or turn.get("speaker") or "?"
            content = turn.get("content") or turn.get("text") or ""
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines).strip()
    return ""


# ── Outbound test call (optional) ───────────────────────────────────────────


async def create_phone_call(
    to_number: str,
    dynamic_variables: dict[str, str],
    *,
    agent_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Place an outbound call via the Retell REST API. Used for testing the
    full loop without Asterisk (Retell dials `to_number` and the agent
    role-plays the scenario). Raises httpx.HTTPStatusError on non-2xx."""
    if not settings.retell_api_key:
        raise RuntimeError("RETELL_API_KEY no configurada")
    body: dict[str, Any] = {
        "from_number": settings.retell_from_number,
        "to_number": to_number,
        "retell_llm_dynamic_variables": dynamic_variables,
    }
    aid = agent_id or settings.retell_agent_id
    if aid:
        body["override_agent_id"] = aid
    if metadata:
        body["metadata"] = metadata
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.retell_base_url.rstrip('/')}/v2/create-phone-call",
            json=body,
            headers={"Authorization": f"Bearer {settings.retell_api_key}"},
        )
        resp.raise_for_status()
        return resp.json()
