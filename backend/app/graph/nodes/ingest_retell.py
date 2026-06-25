"""ingest_retell — entry node for the simulacros (Retell) flow.

The CRM-backed flow (`fetch_crm`) pulls a transcript from the CRM. For a
simulacro the transcript is already known: a comercial called the Retell
voice agent, which role-played a prospective student, and Retell handed us
the full transcript + recording in the webhook. This node turns that into
the same shape the rest of the graph expects, so scoring/feedback/report
all run unchanged.

Key decision: the simulacro is scored under the **`informacion_telefonica`**
dimension (a simulacro IS an information call). That makes the coach's
`info_call` tier and the composer light up for free, and the auditor
validates against the real `guion-comercial-magister.md`. The call-specific
hard rules in `score_param` (speaker mismatch, short call, incoherent
transcript, Madrid-only…) are all guarded by context flags that we simply
do NOT set here, so none of them fire on a role-play transcript.

Inputs read from the initial graph state (set by the Retell webhook):
  - `transcript`        : the full conversation, already formatted.
  - `agente`            : the comercial being trained (resolved from caller ID).
  - `call_date`         : when the simulacro happened.
  - `crm_snapshot._simulacro` : {scenario, recording_url, call_id, ...}.
"""
from __future__ import annotations

import structlog

from ..state import AuditState

log = structlog.get_logger()

# The simulacro is audited as a phone information call.
SIMULACRO_DIMENSION = "informacion_telefonica"


def _scenario_header(scenario: dict, comercial: str) -> str:
    """One transparent header so the auditor knows this is a TRAINING
    role-play and what the 'student' was briefed to do — without leaking
    it as an instruction (it lands inside the untrusted block downstream)."""
    nombre = scenario.get("nombre") or "(escenario sin nombre)"
    dificultad = scenario.get("dificultad") or "(sin nivel)"
    persona = (scenario.get("persona") or "").strip()
    objeciones = (scenario.get("objeciones") or "").strip()
    producto = (scenario.get("producto") or "").strip()
    lines = [
        "[SIMULACRO DE FORMACIÓN — esto NO es una llamada real con un alumno. "
        "La asesora practica contra un 'alumno' interpretado por una IA de voz. "
        "Audita su desempeño con la MISMA rúbrica de una llamada de información real.]",
        f"[ESCENARIO: {nombre} · dificultad={dificultad}"
        + (f" · producto={producto}" if producto else "")
        + "]",
    ]
    if persona:
        lines.append(f"[PERFIL DEL ALUMNO SIMULADO: {persona[:600]}]")
    if objeciones:
        lines.append(f"[OBJECIONES QUE EL ALUMNO DEBÍA PLANTEAR: {objeciones[:600]}]")
    lines.append(f"[ASESORA EVALUADA: {comercial or '(desconocida)'}]")
    return "\n".join(lines)


async def run(state: AuditState) -> dict:
    transcript = (state.get("transcript") or "").strip()
    snapshot = dict(state.get("crm_snapshot") or {})
    sim = snapshot.get("_simulacro") or {}
    scenario = sim.get("scenario") or {}
    comercial = (state.get("agente") or "").strip()

    if not transcript:
        log.warning("ingest_retell_no_transcript", analysis_id=state.get("analysis_id"))
        return {
            "status": "failed",
            "errors": ["simulacro_sin_transcripcion: Retell no entregó transcript"],
            "crm_snapshot": snapshot or {"status": "blocked", "error": "no_transcript"},
            "transcript": "",
            "channel": "",
            "source_field": "",
        }

    primary = f"{_scenario_header(scenario, comercial)}\n\n{transcript}"

    # Build the slice the score_param fan-out will consume directly. We do
    # NOT set any of the call hard-rule trap flags (transcript_incoherent,
    # speaker_matches_agente, transcript_speaker, short_call) so the auditor
    # always runs on the role-play transcript.
    slice_: dict = {
        "empty": False,
        "channel": "simulacro",
        "primary": primary,
        "context": {
            "es_simulacro": True,
            "escenario": scenario.get("nombre"),
            "dificultad": scenario.get("dificultad"),
            "producto": scenario.get("producto"),
            "asesora_evaluada": comercial,
        },
        "registros": [],
    }

    log.info(
        "ingest_retell_ok",
        analysis_id=state.get("analysis_id"),
        comercial=comercial,
        escenario=scenario.get("nombre"),
        transcript_chars=len(transcript),
    )
    return {
        "status": "fetching",
        "crm_snapshot": snapshot,
        "transcript": transcript,
        "channel": "simulacro",
        "source_field": "retell",
        "slices": {SIMULACRO_DIMENSION: slice_},
    }
