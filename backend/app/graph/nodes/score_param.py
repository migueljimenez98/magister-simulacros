"""score_param — score one rubric parameter against its dimension's slice.

Runs in parallel via Send (one per rule). The state's `scores` field is
reducer-merged so all parallel branches collapse into a single dict.

Routing: each Send carries `dimension` + `slice` (the small per-dim view
of the CRM) + the dimension's `system_block`. If `slice.empty == true`
(this lead has no data for this dimension), the rule is recorded as
not-applicable WITHOUT calling the LLM — saving cost and ensuring the
global score isn't dragged down by a missing channel.
"""
from __future__ import annotations

import re
from typing import Any

import structlog

from ...agents.auditor import score_one
from ..state import ParamScore

log = structlog.get_logger()


_QUESTION_MARKERS_RE = re.compile(
    r"[¿?]"
    r"|\b(?:cu[áa]nto|cu[áa]ndo|c[óo]mo|d[óo]nde|por\s*qu[ée]|qu[ée]\s+|qui[ée]n"
    r"|cu[áa]l|me\s+puedes?|podr[íi]as?|puedo|tienes?|tienen|sabes|saben"
    r"|sirve|funciona|incluye|cubre|cuesta|vale|precio|temario|programaci[óo]n)\b",
    re.IGNORECASE,
)

# Mensajes cortos operativos que SOLO confirman recepción / agradecen /
# saludan. Si todos los inbounds del lead en ventana caen aquí, no hay
# duda concreta que resolver — la asesora no puede ser penalizada por no
# "resolver" una confirmación. Alternativas ordenadas de MÁS LARGAS a
# más cortas para que `s[íi]\s*[,.]?\s*lo\s+recib[íi]` matchee antes que
# el `s[íi]` aislado.
_BARE_CONFIRMATIONS_RE = re.compile(
    r"^\s*(?:"
    r"s[íi]\s*[,.]?\s*lo\s+recib[íi]"
    r"|ya\s+lo\s+recib[íi]"
    r"|lo\s+he\s+recib[íi]do"
    r"|recibid[oa]"
    r"|lo\s+recib[íi]"
    r"|de\s*acuerdo"
    r"|muchas\s+gracias"
    r"|graci[ñn]as"
    r"|buen[ao]s?\s+(?:d[íi]as|tardes|noches)"
    r"|s[íi]|ok|okay|vale|perfecto|genial|gracias"
    r"|hola|saludos|adi[óo]s|chao"
    r")"
    r"[\s\.,!¡¿?]*$",
    re.IGNORECASE,
)


def _inbound_carries_question(text: str) -> bool:
    """True if an inbound message from the lead carries a real question /
    request for info — i.e. something the asesora is supposed to resolve.

    Heuristic, deterministic, fail-OPEN (when in doubt → True, evaluate).
    The whole point is to filter out bare confirmations ("sí, lo recibí",
    "ok", "gracias") so the auditor doesn't fabricate a "duda" out of a
    receipt acknowledgment. Longer or interrogative inbounds always
    qualify — only short, single-token confirmations get filtered out.
    """
    body = (text or "").strip()
    if not body:
        return False
    # Bare confirmations / greetings → not a question.
    if len(body) <= 30 and _BARE_CONFIRMATIONS_RE.match(body):
        return False
    # Question markers or interrogative keywords → real question.
    if _QUESTION_MARKERS_RE.search(body):
        return True
    # Long messages (>120 chars) usually carry context the asesora should
    # engage with even without a literal question mark.
    if len(body) > 120:
        return True
    # Conservative default: short non-confirmation messages → also count
    # as engagement to avoid being too aggressive with skips.
    return True


async def run(payload: dict[str, Any]) -> dict:
    rule = payload.get("rule") or {}
    rule_id = rule.get("id") or "unknown"
    # Default to a real dimension that EXISTS in the SLICERS registry. The
    # legacy default `"llamada"` (singular) was removed when we unified to
    # plural names — picking it here would silently route every rule with
    # no `dimension` field to a non-existent slicer, returning empty. Loud
    # error is much better than silent zero-scores.
    dimension = payload.get("dimension") or "gestion"
    if not payload.get("dimension"):
        log.warning(
            "score_param_missing_dimension",
            rule_id=rule_id,
            fallback=dimension,
        )
    # Alias: "informacion_telefonica" es el nombre canónico de la vertical
    # antes llamada "llamadas". Las hard-rules de score_param se escribieron
    # comparando contra "llamadas"; en lugar de duplicar cada `if` lo
    # normalizamos aquí para que ambos ids accedan a las mismas reglas.
    is_call_dim = dimension in {"llamadas", "informacion_telefonica"}
    weight = float(rule.get("weight", 0.0))
    slice_ = payload.get("slice") or {"empty": True}

    # Product gating — rules tagged `product_specific: "X"` only apply when
    # the project's `config.product` matches X. Used by the unified project
    # to keep oposiciones-only rules (madrid_only_*) silent for master/CH/etc.
    # If the project doesn't set `product` at all, product_specific rules
    # are SILENT (we err on the side of "don't evaluate without context").
    rule_product = rule.get("product_specific")
    project_product = ((payload.get("project_config") or {}).get("product") or "").strip().lower()
    if rule_product and rule_product.strip().lower() != project_product:
        log.info(
            "score_param_skip_product_gate",
            rule_id=rule_id,
            rule_product=rule_product,
            project_product=project_product or "(unset)",
        )
        return {"scores": {rule_id: {
            "score": None, "max": weight,
            "note": (
                f"no_aplicable: regla específica de producto '{rule_product}'; "
                f"este proyecto audita producto '{project_product or '(no definido)'}'"
            ),
            "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
            "dimension": dimension, "applied": False,
            "na_reason": "rule_inapplicable",
        }}}

    # n/a path — no data for this dimension on this lead. Skip the LLM.
    # Tagged "channel_empty" so projects with empty_channels_drag_down=True
    # (the unified dashboard) count this as 0 toward the global score, not
    # as an exclusion. Old projects don't set the flag → behavior unchanged.
    if slice_.get("empty"):
        log.info("score_param_na", rule_id=rule_id, dimension=dimension)
        empty_context = slice_.get("context") or {}
        empty_reason = empty_context.get("empty_reason")
        na_reason = empty_context.get("empty_na_reason") or "channel_empty"
        score: ParamScore = {
            "score": None,
            "max": weight,
            "note": (
                f"no_aplicable: {empty_reason}"
                if empty_reason
                else f"no_aplicable: dimensión '{dimension}' sin datos para este lead"
            ),
            "etiqueta": None,
            "observacion": None,
            "evidencia": [],
            "gap": None,
            "dimension": dimension,
            "applied": False,
            "na_reason": na_reason,
        }
        return {"scores": {rule_id: score}}

    # Hard rules (out of band of the LLM) — enforced here so we never depend
    # on the LLM following a "magic prefix" instruction.
    context = slice_.get("context") or {}

    # Gestión (subgrupo protocolo): if the lead is already matriculated
    # (alumno_fecha_de_matricula is a real date, not "0000-00-00"), the cycle
    # "closed" successfully. Penalizing missed follow-up touchpoints AFTER
    # matriculation is unfair — the asesora can't be expected to keep chasing
    # somebody who already signed up. Only `secuencia_intentos` and
    # `no_abandono` are gated this way; the rest still apply (those measure
    # work BEFORE the close).
    if dimension == "gestion" and rule_id in {"secuencia_intentos", "no_abandono"}:
        timeline_meta = context.get("timeline") or {}
        fdm = (timeline_meta.get("alumno_fecha_de_matricula") or "").strip()
        if fdm and fdm != "0000-00-00":
            log.info("score_param_skip_matriculado", rule_id=rule_id, fecha_matricula=fdm)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": (
                    f"no_aplicable: alumno matriculado el {fdm}; el ciclo cerró "
                    "con éxito y los intentos posteriores no se evalúan."
                ),
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    # Gestión — sin conversación con el lead, varias reglas no aplican.
    # Si la asesora llamó (NC), mandó un WhatsApp y ahí se quedó sin
    # respuesta del lead, NO HAY material humano-conversacional para
    # juzgar entender_situacion, busca_soluciones o calidez_trato.
    # Lo único evaluable de verdad es esfuerzo_humano (sí, lo intentó)
    # y persistencia (¿siguió intentando? — eso se mide con la cadencia
    # posterior, que es procedimientos quien lo cubre cuantitativamente;
    # aquí persistencia lo mira a nivel humano).
    if dimension == "gestion" and not bool(context.get("lead_engaged", True)):
        if rule_id in ("entender_situacion", "busca_soluciones", "calidez_trato"):
            log.info("score_param_skip_gestion_no_conversation", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": (
                    "no_aplicable: la asesora intentó pero el lead NO contestó "
                    "y no respondió a los mensajes (NC + WhatsApp enviado sin "
                    "réplica). No hay material conversacional para evaluar "
                    f"'{rule_id}' — solo se puede medir el esfuerzo y la "
                    "persistencia."
                ),
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    # Gestión: if there is zero human activity from anyone in the management
    # window, no rule can be fairly evaluated against the asesora. Mark all
    # gestión rules `applied=False` so the dashboard surfaces "lead sin
    # actividad humana" cleanly instead of an arbitrary 0/5. The exception
    # is `lo_intenta` itself, which IS designed to capture this — that one
    # gets a hard 0 with a clear note (we want it to count as a failure).
    if dimension == "gestion":
        n_humanos_en_ventana = int(context.get("n_humanos_en_ventana") or 0)
        if n_humanos_en_ventana == 0:
            if rule_id == "lo_intenta":
                log.info("score_param_gestion_lo_intenta_zero", rule_id=rule_id)
                return {"scores": {rule_id: {
                    "score": 0.0, "max": weight,
                    "note": "no hay touchpoints humanos en la ventana de gestión: lead sin atender",
                    "etiqueta": "abandono", "observacion": None, "evidencia": [], "gap": "atender_lead",
                    "dimension": dimension, "applied": True,
                }}}
            log.info("score_param_skip_gestion_no_humanos", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": "no_aplicable: lead sin actividad humana en la ventana; solo evaluable 'lo_intenta'",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    # Speaker mismatch: the asesora assigned to this analysis is NOT the
    # person heard in the transcript. Most common cause: a call-center
    # captadora makes the cold call, qualifies the lead, and transfers to
    # the assigned specialist. Grading the specialist on the captadora's
    # words is unfair — every llamada rule short-circuits to n/a so the
    # dimension reports "another person did this call" instead of an
    # arbitrary 0/5.
    #
    # IMPORTANTE: solo skipear cuando hay un speaker DETECTADO y NO
    # coincide. Si `transcript_speaker is None` (la transcripción no se
    # auto-identifica con "Soy X de Magister"), `speaker_matches_agente`
    # también es False — pero eso NO significa mismatch real, solo que
    # no podemos verificarlo. Tratar None como mismatch descartaba
    # llamadas legítimas (follow-ups donde la asesora no se reintroduce).
    # Transcript incoherence: the slicer detected that the transcript has
    # no Magister/oposiciones markers (probable Whisper hallucination on
    # noise, kids in the background, or wrong audio file routed). Grading
    # the rúbrica on garbled audio is worse than no audit — the LLM happily
    # hands out 5/5 "Apertura clara" on snippets like "¡Regálame el
    # teléfono!". Short-circuit every llamadas rule to applied=False so the
    # dashboard surfaces "transcripción incoherente" cleanly instead of
    # mixing fake scores into the average.
    if is_call_dim and context.get("transcript_incoherent") is True:
        reason = context.get("transcript_incoherent_reason") or "transcripción incoherente"
        log.info(
            "score_param_skip_transcript_incoherent",
            rule_id=rule_id,
            reason=reason[:120],
        )
        return {"scores": {rule_id: {
            "score": None, "max": weight,
            "note": (
                f"no_aplicable: TRANSCRIPCIÓN_INCOHERENTE — {reason} "
                "El audio no permite auditar la llamada; revisar la "
                "grabación original antes de asumir un fallo de la asesora."
            ),
            "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
            "dimension": dimension, "applied": False,
            "na_reason": "transcript_incoherent",
        }}}

    if (
        is_call_dim
        and context.get("speaker_matches_agente") is False
        and context.get("transcript_speaker")
    ):
        speaker = context.get("transcript_speaker") or "(desconocido)"
        agente_asg = context.get("agente_asignado") or payload.get("agente", "(?)")
        log.info(
            "score_param_skip_speaker_mismatch",
            rule_id=rule_id,
            transcript_speaker=speaker,
            agente_asignado=agente_asg,
        )
        return {"scores": {rule_id: {
            "score": None, "max": weight,
            "note": (
                f"no_aplicable: la llamada la hizo {speaker}, no {agente_asg}. "
                "Probable handoff de captadora a especialista; no se puede "
                f"auditar a {agente_asg} sobre palabras de otra persona."
            ),
            "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
            "dimension": dimension, "applied": False,
            "na_reason": "rule_inapplicable",
        }}}

    # Short-call case: real conversation but it didn't develop (<60s /
    # <400 chars). Only opening/preparation rules can fairly be evaluated.
    # The rest (cierre, info, soluciones, objeciones, situación) have no
    # material to audit — penalizing them with 0 is unfair.
    if is_call_dim and context.get("short_call") is True:
        _ALLOWED_IN_SHORT_CALL = {"inicio", "madrid_only_modalidad_llamada"}
        if rule_id not in _ALLOWED_IN_SHORT_CALL:
            log.info("score_param_skip_short_call", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": "no_aplicable: llamada corta (no se desarrolló); la asesora abrió pero la conversación terminó pronto — no hay material para auditar este parámetro",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    # Madrid-only modalidad rules: only applicable when we KNOW the lead is
    # NOT in Madrid (so offering presencial/semi would be a critical error).
    # If CCAA is unknown OR the lead IS in Madrid → n/a. Hard-coded here so
    # the LLM can't accidentally score 0 with a "no_aplicable" note that
    # doesn't use the literal prefix our parser expects.
    if rule_id in {"madrid_only_modalidad_llamada", "madrid_only_modalidad_whatsapps"}:
        if rule_id == "madrid_only_modalidad_llamada":
            ccaa_raw = context.get("alumno_comunidad1")
        else:
            ccaa_raw = (context.get("alumno") or {}).get("comunidad1")
        ccaa = (str(ccaa_raw or "").strip().lower())
        if not ccaa:
            log.info("score_param_skip_madrid_unknown_ccaa", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": "no_aplicable: la ficha no informa la comunidad del alumno; no se puede verificar la regla Madrid-only",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}
        if "madrid" in ccaa:
            log.info("score_param_skip_madrid_in_madrid", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": f"no_aplicable: alumno en Madrid (comunidad1={ccaa_raw!r}); la regla solo aplica fuera de Madrid",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    # resuelve_dudas only applies when ALL of these hold:
    #   1) At least one inbound from the lead in the current window.
    #   2) That inbound contains a real question (not a bare confirmation
    #      like "ok"/"gracias"/"sí, lo recibí").
    #   3) The asesora had at least one window where she could send a free
    #      reply — i.e. an `[DENTRO_24h:libre]` slot. If she was always
    #      `[FUERA_24h:plantilla_obligatoria]`, the only option Meta allowed
    #      was a canonical template, and templates can't "resolve doubts"
    #      by design. Penalizing in that case contradicts the dimension
    #      prompt's own table ("FUERA 24h → NO aplica") and is unfair.
    if dimension == "whatsapps" and rule_id == "resuelve_dudas":
        n_recibidos_en_ventana = int(context.get("n_recibidos_en_ventana") or 0)
        if n_recibidos_en_ventana == 0:
            log.info("score_param_skip_resuelve_dudas_no_inbounds", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": "no_aplicable: no hay mensajes recibidos del lead en la ventana actual; no hay duda concreta que la asesora tuviera que responder",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

        n_dentro_24h = int(context.get("n_humano_dentro_24h") or 0)
        n_total_humano = int(context.get("n_enviados_humanos") or 0)
        if n_dentro_24h == 0 and n_total_humano > 0:
            log.info(
                "score_param_skip_resuelve_dudas_no_open_window",
                rule_id=rule_id,
                n_total_humano=n_total_humano,
            )
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": (
                    "no_aplicable: la asesora nunca tuvo la ventana de 24h "
                    "abierta (Meta forzó plantilla en todos sus envíos). "
                    "Las plantillas no resuelven dudas libres por diseño; "
                    "penalizar aquí contradice la regla del prompt de "
                    "whatsapps ('FUERA 24h → NO aplica')."
                ),
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

        # Heurística determinista para "el inbound no es una pregunta real".
        # Confirmaciones operativas cortas (≤30 chars sin '?') no abren
        # ningún deber de resolver duda. Si TODOS los inbounds en ventana
        # caen aquí → applied=False. Si alguno es una pregunta real, el
        # auditor evalúa normalmente.
        registros = slice_.get("registros") or []
        inbounds = [
            (m.get("mensaje") or "").strip()
            for m in registros
            if m.get("direccion") == "recibido"
            and m.get("in_current_window")
        ]
        if inbounds and not any(_inbound_carries_question(t) for t in inbounds):
            log.info(
                "score_param_skip_resuelve_dudas_no_real_question",
                rule_id=rule_id,
                inbounds_n=len(inbounds),
            )
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": (
                    "no_aplicable: los mensajes recibidos del lead en "
                    "ventana son confirmaciones operativas cortas (ej. "
                    "'sí, lo recibí', 'ok', 'gracias') sin pregunta "
                    "concreta. No hay duda explícita que la asesora "
                    "tuviera que responder."
                ),
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    # Meta WhatsApp 24h-window rules: if the asesora NEVER had an open
    # 24h window (no inbound → all outgoing msgs are platform-forced
    # templates), the rules below don't apply — she couldn't personalize,
    # couldn't pick her own tone, and can't reference what she knows
    # about the lead (the template is fixed). Keeping `no_te_llamabamos`,
    # `no_pedir_hora_a_frio` and `madrid_only_modalidad_whatsapps` live
    # because those can be wrong even inside a template (wrong template
    # chosen for the context).
    if dimension == "whatsapps" and rule_id in {"personalizacion", "tono", "no_repreguntar"}:
        n_dentro_24h = int(context.get("n_humano_dentro_24h") or 0)
        n_libre = int(context.get("n_humano_mensaje_libre") or 0)
        n_plantilla = int(context.get("n_humano_plantilla_canonica") or 0)
        n_total_humano = int(context.get("n_enviados_humanos") or 0)

        # Case A: no 24h window ever open → all outgoing forced to template
        if n_dentro_24h == 0 and n_total_humano > 0:
            log.info("score_param_skip_forced_template", rule_id=rule_id)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": "no_aplicable: todos los WhatsApps salientes en ventana fueron plantillas forzadas por Meta API (no hubo inbound en 24h); la asesora no pudo personalizar/tono/referenciar contexto",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

        # Case B: the asesora chose only CANONICAL templates from the KB.
        # Templates are approved by Magister — their wording is fixed,
        # their tone is corporate, they can't reference alumno context
        # freely. penalizing "lack of personalization" / "tone" / "no
        # repreguntar" on a canonical template is unfair: she had nothing
        # to personalize.
        if n_total_humano > 0 and n_libre == 0 and n_plantilla >= 1:
            log.info("score_param_skip_all_canonical_templates", rule_id=rule_id, n_plantilla=n_plantilla)
            return {"scores": {rule_id: {
                "score": None, "max": weight,
                "note": "no_aplicable: todos los WhatsApps salientes humanos son plantillas canónicas aprobadas por Magister (contenido fijo, no personalizable)",
                "etiqueta": None, "observacion": None, "evidencia": [], "gap": None,
                "dimension": dimension, "applied": False,
                "na_reason": "rule_inapplicable",
            }}}

    try:
        verdict = await score_one(
            rule=rule,
            dimension=dimension,
            slice_=slice_,
            agente=payload.get("agente", ""),
            numero=payload.get("numero", ""),
            kb_context=payload.get("kb_context", []),
            analysis_mode=payload.get("analysis_mode", "statistical"),
            system_block=payload.get("system_block", ""),
            standing_instruction=payload.get("standing_instruction", ""),
        )
        # All deterministic hard-rules above this point are the ONLY path to
        # applied=False. If execution reaches the LLM (score_one), the rule
        # is considered applicable — `applied` is always True here regardless
        # of the LLM's `note` text. A "no_aplicable" note from the LLM is
        # informational only and does NOT drop the rule from the total; this
        # prevents prompt-injected transcripts from manipulating scoring.
        note_text = (verdict.note or "").strip()
        score = {
            "score": verdict.score,
            "max": verdict.max,
            "note": note_text,
            "etiqueta": verdict.etiqueta,
            "observacion": verdict.observacion,
            "evidencia": verdict.evidencia,
            "gap": verdict.gap,
            "dimension": dimension,
            "applied": True,
            "na_reason": "",
        }
    except Exception as exc:
        log.warning("score_param_failed", rule_id=rule_id, dimension=dimension, error=str(exc)[:200])
        score = {
            "score": 0.0,
            "max": weight,
            "note": f"score_failed: {exc}"[:500],
            "etiqueta": None,
            "observacion": None,
            "evidencia": [],
            "gap": "scoring_error",
            "dimension": dimension,
            "applied": True,
        }

    return {"scores": {rule_id: score}}
