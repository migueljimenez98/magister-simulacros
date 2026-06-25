"""Simulacros API — Retell webhooks + management.

Two routers:
  - `retell_router`  (/api/retell)     : Retell-facing callbacks. NO JWT —
    Retell calls these. The webhook is signature-verified (best-effort).
      · POST /retell/inbound-vars  → dynamic variables for an inbound call
                                      (caller ID → comercial + scenario).
      · POST /retell/webhook       → call events; on call_analyzed we create
                                      a QualityAnalysis and run the audit
                                      graph with data_source="retell".
  - `simulacros_router` (/api/simulacros) : authed management.
      · scenarios + comerciales CRUD
      · POST /simulacros/test-ingest  → run a simulacro from a pasted
                                        transcript (no telephony needed).
      · POST /simulacros/start-call   → place an outbound Retell test call.
"""
from __future__ import annotations

import hashlib
import hmac
import random
import re
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..core.config import settings
from ..core.models import (
    QualityAnalysis,
    QualityProject,
    SimulacroComercial,
    SimulacroDepartamento,
    SimulacroScenario,
)
from ..services import announce as announce_svc  # noqa: F401  (legacy, superseded by cola)
from ..services import cola
from ..services import leveling
from ..services import retell as retell_svc
from .deps import SessionDep, current_user, get_audit_graph, require_role

log = structlog.get_logger()

retell_router = APIRouter(prefix="/retell", tags=["simulacros-retell"])
simulacros_router = APIRouter(
    prefix="/simulacros",
    tags=["simulacros"],
    dependencies=[Depends(current_user)],
)
# Public (no login): the self-service "Iniciar simulacro" panel + its turn queue.
cola_router = APIRouter(prefix="/simulacros/cola", tags=["simulacros-cola"])

# Niveles de dificultad fijos en todo el sistema.
NIVELES = ["facil", "medio", "dificil"]


# ── helpers ──────────────────────────────────────────────────────────────────


def _digits(s: str | None) -> str:
    return re.sub(r"\D", "", s or "")


def _scenario_to_dict(s: SimulacroScenario) -> dict[str, Any]:
    return {
        "id": s.id,
        "nombre": s.nombre,
        "dificultad": s.dificultad,
        "producto": s.producto,
        "persona": s.persona,
        "objeciones": s.objeciones,
        "faqs": s.faqs,
        "guion": s.guion,
        "retell_agent_id": s.retell_agent_id,
        "activo": s.activo,
        "department_id": s.department_id,
    }


_COMERCIAL_HINT_KEYS = ("comercial", "usuario", "user", "agent", "asesora", "extension", "ext", "agente")


def _collect_signals(*sources: Any) -> dict[str, str]:
    """Gather candidate identity values from SIP headers + dynamic variables.

    Retell, on inbound SIP calls, extracts custom `X-` SIP headers into
    `custom_sip_headers` AND into the dynamic variables. We merge all of those
    so a comercial identity injected by Asterisk (e.g. `X-Comercial: miguel`)
    is found wherever Retell puts it."""
    out: dict[str, str] = {}
    for src in sources:
        if not isinstance(src, dict):
            continue
        for bag_key in ("custom_sip_headers", "retell_llm_dynamic_variables", "dynamic_variables"):
            bag = src.get(bag_key)
            if isinstance(bag, dict):
                for k, v in bag.items():
                    if v is not None:
                        out[str(k)] = str(v)
    return out


async def _comercial_from_signals(
    session: SessionDep, signals: dict[str, str]
) -> SimulacroComercial | None:
    """Resolve a comercial from a SIP-header/dynamic-variable identity value.
    Matches by extension (exact or digits) or by name. None if no hint."""
    candidates = [v for k, v in signals.items()
                  if any(t in k.lower() for t in _COMERCIAL_HINT_KEYS) and v.strip()]
    for val in candidates:
        val = val.strip()
        hit = (await session.execute(
            select(SimulacroComercial).where(SimulacroComercial.extension == val)
        )).scalar_one_or_none()
        if hit:
            return hit
        hit = (await session.execute(
            select(SimulacroComercial).where(SimulacroComercial.nombre == val)
        )).scalar_one_or_none()
        if hit:
            return hit
        digits = _digits(val)
        if digits:
            for c in (await session.execute(select(SimulacroComercial))).scalars().all():
                cd = _digits(c.extension)
                if cd and (cd == digits or digits.endswith(cd) or cd.endswith(digits)):
                    return c
    return None


async def _comercial_for_caller(session: SessionDep, from_number: str) -> SimulacroComercial | None:
    """Resolve the comercial from the caller ID. Matches on exact extension
    first, then on a digits-suffix (handles +34 / 0034 prefixes)."""
    raw = (from_number or "").strip()
    if not raw:
        return None
    hit = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.extension == raw)
    )).scalar_one_or_none()
    if hit:
        return hit
    digits = _digits(raw)
    if not digits:
        return None
    rows = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.activo.is_(True))
    )).scalars().all()
    for c in rows:
        cd = _digits(c.extension)
        if cd and (cd == digits or digits.endswith(cd) or cd.endswith(digits)):
            return c
    return None


async def _pick_scenario(
    session: SessionDep,
    comercial: SimulacroComercial | None,
    explicit_id: str | None = None,
) -> SimulacroScenario | None:
    """Choose which scenario to run: explicit > comercial default > a RANDOM
    active scenario of the simulacros project.

    The random pick is what makes the guión vary call to call: every inbound
    call (with no pinned scenario) gets a different active scenario, so the
    asesora trains against varied leads instead of always the same one."""
    if explicit_id:
        s = await session.get(SimulacroScenario, explicit_id)
        if s:
            return s
    if comercial and comercial.default_scenario_id:
        s = await session.get(SimulacroScenario, comercial.default_scenario_id)
        if s:
            return s
    rows = (await session.execute(
        select(SimulacroScenario)
        .where(
            SimulacroScenario.project_id == settings.simulacros_project_id,
            SimulacroScenario.activo.is_(True),
        )
    )).scalars().all()
    if not rows:
        return None
    # Department-aware: a comercial trains against the guiones of THEIR
    # department. Restrict to that department's scenarios when possible, but
    # fall back to all active scenarios if the department has none yet.
    if comercial and comercial.department_id:
        dept_rows = [s for s in rows if s.department_id == comercial.department_id]
        if dept_rows:
            rows = dept_rows
    # Level-aware: inject a scenario whose difficulty matches the comercial's
    # current level ("el guion correspondiente al agente"). Fall back to any
    # active scenario (within the department) if there's none at that level.
    if comercial and comercial.nivel:
        matching = [s for s in rows if (s.dificultad or "") == comercial.nivel]
        if matching:
            return random.choice(matching)
    return random.choice(rows)


def _faqs_to_text(faqs: list[dict[str, Any]], nivel: str | None) -> str:
    """Render the department's structured FAQs (filtered by nivel) as a text
    block the agent prompt can consume: 'P: … / R esperada: …' per FAQ."""
    out: list[str] = []
    for f in faqs or []:
        if nivel and (f.get("nivel") or "") != nivel:
            continue
        preg = str(f.get("pregunta") or "").strip()
        resp = str(f.get("respuesta_esperada") or "").strip()
        if not preg and not resp:
            continue
        out.append(f"P: {preg}\nR esperada: {resp}".strip())
    return "\n\n".join(out)


async def _common_faqs_for(
    session: SessionDep,
    comercial: SimulacroComercial | None,
    scenario: SimulacroScenario | None,
) -> str:
    """Department-level common FAQ block for the relevant difficulty level.

    Looks up the department (from the comercial, else the scenario) and renders
    its structured `faqs` filtered by `nivel` (the comercial's level, falling
    back to the scenario's difficulty). Empty string if none applies."""
    dept_id = (comercial.department_id if comercial else None) or (
        scenario.department_id if scenario else None
    )
    if not dept_id:
        return ""
    dept = await session.get(SimulacroDepartamento, dept_id)
    if not dept or not dept.faqs:
        return ""
    nivel = (comercial.nivel if comercial and comercial.nivel else None) or (
        scenario.dificultad if scenario else None
    )
    return _faqs_to_text(dept.faqs, nivel)


async def _run_simulacro_audit(
    graph,
    analysis_id: str,
    agente: str,
    call_date: datetime | None,
    transcript: str,
    snapshot: dict[str, Any],
) -> None:
    """Invoke the audit graph for a simulacro. The persist node writes the
    result back into the row keyed by analysis_id."""
    try:
        await graph.ainvoke(
            {
                "analysis_id": analysis_id,
                "project_id": settings.simulacros_project_id,
                "numero": (snapshot.get("_simulacro") or {}).get("from_number") or analysis_id,
                "agente": agente,
                "call_date": call_date,
                "transcript": transcript,
                "crm_snapshot": snapshot,
            },
            config={"configurable": {"thread_id": analysis_id}},
        )
    except Exception as exc:  # noqa: BLE001
        log.error("simulacro_audit_failed", analysis_id=analysis_id, error=str(exc)[:300])
        return

    # Post-call leveling: if this simulacro is attributed to a known comercial
    # and their department has auto-evaluación on, move their level per the rules.
    try:
        from ..core.db import async_session
        from ..services import leveling
        async with async_session() as s:
            res = await leveling.evaluate_by_name(s, agente, auto_trigger=True)
            if res and res.get("changed"):
                log.info("simulacro_level_changed", comercial=agente, to=res.get("nivel"))
    except Exception as exc:  # noqa: BLE001
        log.warning("simulacro_leveling_failed", comercial=agente, error=str(exc)[:200])


async def _create_and_dispatch(
    session: SessionDep,
    graph,
    background: BackgroundTasks,
    *,
    analysis_id: str | None,
    agente: str,
    transcript: str,
    snapshot: dict[str, Any],
    numero: str,
) -> QualityAnalysis:
    """Insert a pending simulacro analysis and schedule the audit graph.
    Idempotent when `analysis_id` is provided (re-delivered webhook → skip)."""
    project = await session.get(QualityProject, settings.simulacros_project_id)
    if not project:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            f"Proyecto de simulacros '{settings.simulacros_project_id}' no existe. "
            "Ejecuta scripts.seed_simulacros.",
        )

    if analysis_id:
        existing = await session.get(QualityAnalysis, analysis_id)
        if existing is not None:
            log.info("simulacro_webhook_duplicate_skip", analysis_id=analysis_id)
            return existing

    row = QualityAnalysis(
        project_id=settings.simulacros_project_id,
        numero=numero or "simulacro",
        agente_nombre=agente or "(simulacro)",
        call_date=datetime.now(timezone.utc),
        status="pending",
        crm_snapshot=snapshot,
    )
    if analysis_id:
        row.id = analysis_id
    session.add(row)
    await session.commit()
    await session.refresh(row)

    background.add_task(
        _run_simulacro_audit, graph, row.id, agente, row.call_date, transcript, snapshot,
    )
    return row


# ── Retell-facing callbacks (no JWT) ─────────────────────────────────────────


@retell_router.post("/inbound-vars")
async def inbound_dynamic_variables(request: Request, session: SessionDep) -> dict[str, Any]:
    """Return the dynamic variables for an inbound simulacro call.

    Retell calls this when a comercial dials in (before the agent speaks).
    We map the caller ID → comercial, pick a scenario, and hand back the
    guión/persona/difficulty. We answer in BOTH the legacy top-level shape
    and the newer `call_inbound` wrapper so either Retell config works.
    """
    payload = await request.json()
    inbound = payload.get("call_inbound") or payload.get("call") or payload
    from_number = inbound.get("from_number") or payload.get("from_number") or ""

    # Log the raw inbound payload so we can SEE exactly what Retell delivers
    # (incl. any custom SIP headers Asterisk injects) when wiring the trunk.
    log.info("retell_inbound_payload", payload=payload)

    # Resolve who's calling, in priority order:
    #   1. SIP header / dynamic variable (future Asterisk trunk).
    #   2. Announcement ("Miguel va a llamar ahora" from the CRM) — the path
    #      that works when the CRM dials the number like a normal call.
    #   3. Caller ID → registered comercial (local tests / per-agent number).
    signals = _collect_signals(payload, inbound)
    comercial = await _comercial_from_signals(session, signals)
    via = "sip_header" if comercial else ""
    announced_name: str | None = None
    announced_scenario: str = ""
    if comercial is None:
        # Call connected → take the armed turn and RELEASE the queue slot
        # (promotes the next person). One armed slot at a time.
        announced = cola.match_and_consume(from_number)
        if announced:
            via = "announce"
            announced_name = announced["agente"]
            announced_scenario = announced.get("scenario_id") or ""
            comercial = (await session.execute(
                select(SimulacroComercial).where(SimulacroComercial.nombre == announced_name)
            )).scalar_one_or_none()
    if comercial is None and not announced_name:
        comercial = await _comercial_for_caller(session, from_number)
        via = "caller_id" if comercial else "none"
    scenario = await _pick_scenario(session, comercial, explicit_id=announced_scenario or None)
    comercial_nombre = (comercial.nombre if comercial else (announced_name or ""))
    common_faqs = await _common_faqs_for(session, comercial, scenario)

    dyn = retell_svc.build_dynamic_variables(
        _scenario_to_dict(scenario) if scenario else None,
        comercial_nombre,
        scenario_id=scenario.id if scenario else "",
        comercial_id=comercial.id if comercial else "",
        common_faqs=common_faqs,
    )
    log.info(
        "retell_inbound_vars",
        from_number=from_number,
        comercial=comercial_nombre or "(desconocido)",
        via=via,
        signals=list(signals.keys()),
        scenario=(scenario.nombre if scenario else "(ninguno)"),
    )
    call_inbound: dict[str, Any] = {"dynamic_variables": dyn}
    if scenario and scenario.retell_agent_id:
        call_inbound["override_agent_id"] = scenario.retell_agent_id
    return {"dynamic_variables": dyn, "call_inbound": call_inbound}


class CrmAnnounceIn(BaseModel):
    agente_nombre: str
    from_number: str = ""
    scenario_id: str = ""


@retell_router.post("/announce", status_code=202)
async def crm_announce(data: CrmAnnounceIn, request: Request, session: SessionDep) -> dict[str, Any]:
    """Server-to-server entry point for the CRM (no user login). The CRM calls
    this the instant a comercial requests a simulacro, sending the shared token
    in the `X-CRM-Token` header. We arm Retell with the agent's level-scenario
    and return OK/Cambiado so the CRM can place the call."""
    token = (settings.crm_announce_token or "").strip()
    if not token:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "CRM_ANNOUNCE_TOKEN no configurado en el servidor",
        )
    provided = (request.headers.get("x-crm-token") or "").strip()
    if not provided or not hmac.compare_digest(provided, token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "X-CRM-Token inválido")
    return await _process_announce(session, data.agente_nombre, data.from_number, data.scenario_id)


@retell_router.post("/webhook")
async def retell_webhook(
    request: Request,
    session: SessionDep,
    background: BackgroundTasks,
    graph=Depends(get_audit_graph),
) -> dict[str, Any]:
    """Receive Retell call events. On `call_analyzed` we create a simulacro
    analysis from the transcript and run the audit graph.

    Signature is verified best-effort: a mismatch is logged but not rejected
    (local / pre-production tolerance). Tighten to a hard 401 once the live
    Asterisk→Retell path is confirmed.
    """
    raw = await request.body()
    signature = request.headers.get("x-retell-signature") or request.headers.get("X-Retell-Signature")
    if not retell_svc.verify_signature(raw, signature):
        log.warning("retell_webhook_signature_unverified", has_sig=bool(signature))

    payload = await request.json()
    parsed = retell_svc.parse_webhook(payload)
    event = parsed["event"]

    # Act on the call's terminal events. Prefer call_analyzed (richest), but
    # also handle call_ended so we still get a result when post-call analysis
    # is disabled on the agent. Dedupe by call_id (deterministic analysis_id)
    # means whichever arrives first wins and the later one is skipped.
    if event not in ("call_analyzed", "call_ended"):
        return {"ok": True, "ignored_event": event}

    transcript = parsed["transcript"]
    if not transcript:
        log.warning("retell_webhook_no_transcript", call_id=parsed["call_id"])
        return {"ok": True, "skipped": "no_transcript"}

    dyn = parsed["dynamic_variables"]
    # Recover scenario + comercial. Priority: SIP header / dynamic-variable
    # identity (the shared-number production path) → caller-ID (tests).
    scenario_id = dyn.get("scenario_id") or ""
    signals = _collect_signals(
        {"custom_sip_headers": parsed.get("custom_sip_headers"), "dynamic_variables": dyn}
    )
    comercial = await _comercial_from_signals(session, signals)
    if comercial is None:
        comercial = await _comercial_for_caller(session, parsed["from_number"])
    scenario = await _pick_scenario(session, comercial, explicit_id=scenario_id or None)
    agente = dyn.get("nombre_comercial") or (comercial.nombre if comercial else "") or parsed["from_number"]

    snapshot: dict[str, Any] = {
        "source": "retell",
        "transcript": transcript,
        "recording_url": parsed["recording_url"],
        "_simulacro": {
            "call_id": parsed["call_id"],
            "agent_id": parsed["agent_id"],
            "from_number": parsed["from_number"],
            "to_number": parsed["to_number"],
            "recording_url": parsed["recording_url"],
            "duration_ms": parsed["duration_ms"],
            "scenario": _scenario_to_dict(scenario) if scenario else {},
            "dynamic_variables": dyn,
            "call_analysis": parsed["call_analysis"],
        },
    }

    analysis_id = "qa-" + hashlib.sha256(parsed["call_id"].encode()).hexdigest()[:12] if parsed["call_id"] else None
    row = await _create_and_dispatch(
        session, graph, background,
        analysis_id=analysis_id,
        agente=agente,
        transcript=transcript,
        snapshot=snapshot,
        numero=parsed["from_number"] or parsed["call_id"],
    )
    log.info("retell_webhook_dispatched", analysis_id=row.id, call_id=parsed["call_id"])
    return {"ok": True, "analysis_id": row.id}


# ── Management: test-ingest + outbound test call ─────────────────────────────


class TestIngestIn(BaseModel):
    transcript: str = Field(..., min_length=1)
    agente_nombre: str = "Asesora de prueba"
    scenario_id: str | None = None


@simulacros_router.post(
    "/test-ingest", status_code=202,
    dependencies=[Depends(require_role("admin"))],
)
async def test_ingest(
    data: TestIngestIn,
    session: SessionDep,
    background: BackgroundTasks,
    graph=Depends(get_audit_graph),
) -> dict[str, Any]:
    """Run a simulacro from a pasted transcript — no Retell/telephony needed.
    The end-to-end demo path: see the audit, score and feedback in the panel."""
    scenario = await _pick_scenario(session, None, explicit_id=data.scenario_id)
    snapshot: dict[str, Any] = {
        "source": "retell_test",
        "transcript": data.transcript,
        "recording_url": "",
        "_simulacro": {
            "call_id": "",
            "scenario": _scenario_to_dict(scenario) if scenario else {},
            "dynamic_variables": {"nombre_comercial": data.agente_nombre},
        },
    }
    row = await _create_and_dispatch(
        session, graph, background,
        analysis_id=None,
        agente=data.agente_nombre,
        transcript=data.transcript,
        snapshot=snapshot,
        numero="simulacro-test",
    )
    return {"ok": True, "analysis_id": row.id, "status": row.status}


class StartCallIn(BaseModel):
    to_number: str = Field(..., description="Número destino en formato E.164 (+34...)")
    scenario_id: str | None = None
    # Name to attribute the simulacro to. Emulates the CRM "call" button: the
    # comercial's name comes from the CRM; here you type it for testing. It is
    # echoed back by Retell in the webhook, so the analysis lands under it.
    agente_nombre: str = ""


@simulacros_router.post(
    "/start-call", status_code=202,
    dependencies=[Depends(require_role("admin"))],
)
async def start_call(data: StartCallIn, session: SessionDep) -> dict[str, Any]:
    """Place an outbound Retell call to `to_number` so a comercial can test
    the role-play on their own phone without the Asterisk path. `agente_nombre`
    simulates the CRM identity so the resulting simulacro is attributed to it.
    If no scenario is pinned, a random active one is used (varies each call)."""
    scenario = await _pick_scenario(session, None, explicit_id=data.scenario_id)
    if not settings.retell_api_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "RETELL_API_KEY no configurada")
    common_faqs = await _common_faqs_for(session, None, scenario)
    dyn = retell_svc.build_dynamic_variables(
        _scenario_to_dict(scenario) if scenario else None,
        data.agente_nombre,
        scenario_id=scenario.id if scenario else "",
        common_faqs=common_faqs,
    )
    try:
        result = await retell_svc.create_phone_call(
            data.to_number, dyn,
            metadata={
                "scenario_id": scenario.id if scenario else "",
                "agente_nombre": data.agente_nombre,
            },
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Retell rechazó la llamada: {exc}") from exc
    return {"ok": True, "call": result, "scenario": scenario.nombre if scenario else None}


# ── Management: scenarios CRUD ───────────────────────────────────────────────


class ScenarioIn(BaseModel):
    nombre: str
    dificultad: str = "medio"
    producto: str | None = None
    persona: str = ""
    objeciones: str = ""
    faqs: str = ""
    guion: str = ""
    retell_agent_id: str | None = None
    activo: bool = True
    department_id: str | None = None


@simulacros_router.get("/scenarios")
async def list_scenarios(session: SessionDep) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(SimulacroScenario)
        .where(SimulacroScenario.project_id == settings.simulacros_project_id)
        .order_by(SimulacroScenario.created_at.desc())
    )).scalars().all()
    return [_scenario_to_dict(s) for s in rows]


@simulacros_router.post(
    "/scenarios", status_code=201,
    dependencies=[Depends(require_role("admin"))],
)
async def create_scenario(data: ScenarioIn, session: SessionDep) -> dict[str, Any]:
    s = SimulacroScenario(project_id=settings.simulacros_project_id, **data.model_dump())
    session.add(s)
    await session.commit()
    await session.refresh(s)
    return _scenario_to_dict(s)


@simulacros_router.patch(
    "/scenarios/{scenario_id}",
    dependencies=[Depends(require_role("admin"))],
)
async def update_scenario(scenario_id: str, data: ScenarioIn, session: SessionDep) -> dict[str, Any]:
    s = await session.get(SimulacroScenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escenario no encontrado")
    for k, v in data.model_dump().items():
        setattr(s, k, v)
    await session.commit()
    await session.refresh(s)
    return _scenario_to_dict(s)


@simulacros_router.delete(
    "/scenarios/{scenario_id}", status_code=204,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_scenario(scenario_id: str, session: SessionDep) -> None:
    s = await session.get(SimulacroScenario, scenario_id)
    if not s:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Escenario no encontrado")
    await session.delete(s)
    await session.commit()


# ── Management: comerciales CRUD ─────────────────────────────────────────────


class ComercialIn(BaseModel):
    nombre: str
    # Optional — no longer used for attribution (kept as a fallback only).
    extension: str | None = None
    activo: bool = True
    default_scenario_id: str | None = None
    department_id: str | None = None
    nivel: str | None = None


def _comercial_to_dict(c: SimulacroComercial) -> dict[str, Any]:
    return {
        "id": c.id,
        "extension": c.extension,
        "nombre": c.nombre,
        "activo": c.activo,
        "default_scenario_id": c.default_scenario_id,
        "department_id": c.department_id,
        "nivel": c.nivel,
    }


@simulacros_router.get("/comerciales")
async def list_comerciales(session: SessionDep) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(SimulacroComercial).order_by(SimulacroComercial.nombre)
    )).scalars().all()
    return [_comercial_to_dict(c) for c in rows]


@simulacros_router.post(
    "/comerciales", status_code=201,
    dependencies=[Depends(require_role("admin"))],
)
async def create_comercial(data: ComercialIn, session: SessionDep) -> dict[str, Any]:
    c = SimulacroComercial(**data.model_dump())
    session.add(c)
    await session.commit()
    await session.refresh(c)
    return _comercial_to_dict(c)


@simulacros_router.patch(
    "/comerciales/{comercial_id}",
    dependencies=[Depends(require_role("admin"))],
)
async def update_comercial(comercial_id: str, data: ComercialIn, session: SessionDep) -> dict[str, Any]:
    c = await session.get(SimulacroComercial, comercial_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comercial no encontrado")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    await session.commit()
    await session.refresh(c)
    return _comercial_to_dict(c)


@simulacros_router.delete(
    "/comerciales/{comercial_id}", status_code=204,
    dependencies=[Depends(require_role("admin"))],
)
async def delete_comercial(comercial_id: str, session: SessionDep) -> None:
    c = await session.get(SimulacroComercial, comercial_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comercial no encontrado")
    await session.delete(c)
    await session.commit()


class AnnounceIn(BaseModel):
    agente_nombre: str
    # Optional caller number — if provided, it pins the match precisely (avoids
    # ambiguity when several comerciales call within the same few seconds).
    from_number: str = ""
    # Optional scenario to force; empty → pick by the comercial's level / random.
    scenario_id: str = ""


async def _process_announce(
    session: SessionDep, agente_nombre: str, from_number: str = "", scenario_id: str = "",
) -> dict[str, Any]:
    """Core of the announce: take the alias, look up the comercial's level,
    PICK the scenario (sealed now, not at call time), arm Retell for the next
    inbound call, and return the "OK / Cambiado" summary. Shared by the authed
    panel endpoint and the token-protected CRM endpoint."""
    comercial = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.nombre == agente_nombre)
    )).scalar_one_or_none()
    scenario = await _pick_scenario(session, comercial, explicit_id=scenario_id or None)

    # CRM / Dev simulator: the call is imminent → claim the turn now.
    cola.take_now(agente_nombre, from_number, scenario.id if scenario else "")
    log.info(
        "simulacro_announce",
        agente=agente_nombre,
        nivel=(comercial.nivel if comercial else None),
        escenario=(scenario.nombre if scenario else None),
        from_number=from_number or "(none)",
    )
    return {
        "ok": True,
        "status": "OK",
        "mensaje": "Cambiado",
        "agente_nombre": agente_nombre,
        "nivel": comercial.nivel if comercial else None,
        "escenario": scenario.nombre if scenario else None,
        "dificultad": scenario.dificultad if scenario else None,
    }


@simulacros_router.post("/announce", status_code=202)
async def announce_call(data: AnnounceIn, session: SessionDep) -> dict[str, Any]:
    """Panel (authed) entry point — used by the Dev simulator."""
    return await _process_announce(session, data.agente_nombre, data.from_number, data.scenario_id)


@simulacros_router.get("/announce/pending")
async def announce_pending() -> dict[str, Any]:
    """Debug: the active turn + the waiting queue."""
    return cola.snapshot()


# ── Public: self-service "Iniciar simulacro" panel + turn queue ──────────────


class ColaJoinIn(BaseModel):
    nombre: str
    from_number: str = ""


@cola_router.post("/join")
async def cola_join(data: ColaJoinIn, session: SessionDep) -> dict[str, Any]:
    """Public (no login): request a turn for a self-service simulacro. Seals the
    guión by the tracking name's level (random if unknown) and either arms it now
    (slot free) or queues it. The panel polls /status with the returned ticket."""
    nombre = (data.nombre or "").strip()
    if not nombre:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Falta el nombre de seguimiento")
    comercial = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.nombre == nombre)
    )).scalar_one_or_none()
    scenario = await _pick_scenario(session, comercial, explicit_id=None)
    res = cola.join(nombre, data.from_number, scenario.id if scenario else "")
    res["escenario"] = scenario.nombre if scenario else None
    res["dificultad"] = scenario.dificultad if scenario else None
    return res


@cola_router.get("/status")
async def cola_status(ticket: str) -> dict[str, Any]:
    """Public: poll a ticket's turn status (keeps the panel's place alive)."""
    return cola.poll(ticket)


@cola_router.get("/info")
async def cola_info() -> dict[str, Any]:
    """Public: the phone number to call for the self-service panel."""
    return {"numero": settings.retell_from_number or ""}


@simulacros_router.post("/comerciales/{comercial_id}/evaluate-level")
async def evaluate_comercial_level(comercial_id: str, session: SessionDep) -> dict[str, Any]:
    """Run the leveling engine for one comercial on demand (manual trigger by
    the coordinator). Applies the move if a rule matches."""
    c = await session.get(SimulacroComercial, comercial_id)
    if not c:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Comercial no encontrado")
    return await leveling.evaluate_and_apply(session, c, persist=True)


# ── Management: departamentos (niveles + reglas de escalado) ─────────────────


def _dept_to_dict(d: SimulacroDepartamento) -> dict[str, Any]:
    return {
        "id": d.id,
        "nombre": d.nombre,
        "niveles": NIVELES,                    # fijos: facil/medio/dificil
        "faqs": d.faqs or [],                  # [{pregunta, respuesta_esperada, nivel}]
        "reglas": d.reglas or [],
        "auto_evaluar": d.auto_evaluar,
        "project_id": d.project_id,
        "activo": d.activo,
    }


class FaqItem(BaseModel):
    pregunta: str = ""
    respuesta_esperada: str = ""
    nivel: str = "medio"


class DepartamentoIn(BaseModel):
    nombre: str
    faqs: list[FaqItem] = Field(default_factory=list)
    # Escalado: se conserva en BD pero ya no se edita desde el alta del dpto.
    reglas: list[dict[str, Any]] = Field(default_factory=list)
    auto_evaluar: bool = True
    project_id: str | None = None
    activo: bool = True


@simulacros_router.get("/departamentos")
async def list_departamentos(session: SessionDep) -> list[dict[str, Any]]:
    rows = (await session.execute(
        select(SimulacroDepartamento).order_by(SimulacroDepartamento.nombre)
    )).scalars().all()
    return [_dept_to_dict(d) for d in rows]


@simulacros_router.post(
    "/departamentos", status_code=201, dependencies=[Depends(require_role("admin"))],
)
async def create_departamento(data: DepartamentoIn, session: SessionDep) -> dict[str, Any]:
    d = SimulacroDepartamento(**data.model_dump())
    session.add(d)
    await session.commit()
    await session.refresh(d)
    return _dept_to_dict(d)


@simulacros_router.patch(
    "/departamentos/{dept_id}", dependencies=[Depends(require_role("admin"))],
)
async def update_departamento(dept_id: str, data: DepartamentoIn, session: SessionDep) -> dict[str, Any]:
    d = await session.get(SimulacroDepartamento, dept_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Departamento no encontrado")
    for k, v in data.model_dump().items():
        setattr(d, k, v)
    await session.commit()
    await session.refresh(d)
    return _dept_to_dict(d)


@simulacros_router.delete(
    "/departamentos/{dept_id}", status_code=204, dependencies=[Depends(require_role("admin"))],
)
async def delete_departamento(dept_id: str, session: SessionDep) -> None:
    d = await session.get(SimulacroDepartamento, dept_id)
    if not d:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Departamento no encontrado")
    await session.delete(d)
    await session.commit()


# ── Management: evaluadores (prompts + rúbrica de cómo se puntúa) ─────────────

# The "moderators" that score the call ARE the project's evaluator prompts +
# rubric. We expose them under a friendly shape so a coordinator can edit how
# the simulacro is judged without touching the projects internals.
_AUDITOR_DIM = "informacion_telefonica"


class EvaluadoresIn(BaseModel):
    auditor_prompt: str
    feedback_prompt: str
    report_prompt: str
    rules_table: list[dict[str, Any]]


def _evaluadores_from_project(p: QualityProject) -> dict[str, Any]:
    prompts = p.prompts or {}
    dims = prompts.get("dimensions") or {}
    return {
        "project_id": p.id,
        "auditor_prompt": ((dims.get(_AUDITOR_DIM) or {}).get("system_prompt") or ""),
        "feedback_prompt": ((prompts.get("feedback") or {}).get("system_prompt") or ""),
        "report_prompt": ((prompts.get("report") or {}).get("system_prompt") or ""),
        "rules_table": p.rules_table or [],
    }


@simulacros_router.get("/evaluadores")
async def get_evaluadores(session: SessionDep) -> dict[str, Any]:
    p = await session.get(QualityProject, settings.simulacros_project_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto de simulacros no encontrado")
    return _evaluadores_from_project(p)


@simulacros_router.put(
    "/evaluadores", dependencies=[Depends(require_role("admin"))],
)
async def update_evaluadores(data: EvaluadoresIn, session: SessionDep) -> dict[str, Any]:
    p = await session.get(QualityProject, settings.simulacros_project_id)
    if not p:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proyecto de simulacros no encontrado")
    prompts = dict(p.prompts or {})
    dims = dict(prompts.get("dimensions") or {})
    dims[_AUDITOR_DIM] = {
        "label": (dims.get(_AUDITOR_DIM) or {}).get("label", "Simulacro (llamada)"),
        "system_prompt": data.auditor_prompt,
    }
    prompts["dimensions"] = dims
    prompts["feedback"] = {"system_prompt": data.feedback_prompt}
    prompts["report"] = {"system_prompt": data.report_prompt}
    p.prompts = prompts
    p.rules_table = data.rules_table
    await session.commit()
    return _evaluadores_from_project(p)
