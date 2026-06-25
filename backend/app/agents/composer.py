"""Composer agent — long-form executive markdown report (per-call detail).

Driven by `prompts.report.system_prompt`. The user_prompt ships
per-dimension subtotals + the gaps from each dim — the composer's job
is to turn that into a structured markdown report. We do NOT pass the
raw transcript here: the transcript was already cited inside the per-rule
verdicts, and re-shipping it would explode token usage for no benefit.
"""
from __future__ import annotations

from typing import Any

from .llm import LLMConfig, bounded_run, load_config, make_agent

_NOTE_BUDGET = 320


def _per_dim_block(scores_by_dim: dict[str, Any], scores: dict[str, Any]) -> str:
    if not scores_by_dim:
        return "(sin datos por dimensión)"

    rules_by_dim: dict[str, list[tuple[str, dict]]] = {}
    for rid, s in scores.items():
        rules_by_dim.setdefault(s.get("dimension") or "?", []).append((rid, s))

    blocks = []
    for dim, d in scores_by_dim.items():
        if not d.get("applied"):
            blocks.append(f"### {dim} — n/a (sin datos para este lead)")
            continue
        header = f"### {dim} — {d.get('total')}/{d.get('ideal')} ({d.get('percent')}%)"
        rule_lines = []
        for rid, s in rules_by_dim.get(dim, []):
            note = (s.get("note") or s.get("observacion") or "")[:_NOTE_BUDGET]
            ev = s.get("evidencia") or []
            ev_preview = (ev[0] if ev else "")[:240]
            rule_lines.append(
                f"- **{rid}** — {s.get('score')}/{s.get('max')} "
                f"({s.get('etiqueta') or '?'}) — {note}"
                + (f"\n  - cita: \"{ev_preview}\"" if ev_preview else "")
                + (f"\n  - gap: {s.get('gap')}" if s.get("gap") else "")
            )
        blocks.append(header + "\n" + "\n".join(rule_lines))
    return "\n\n".join(blocks)


async def compose(payload: dict[str, Any], cfg: LLMConfig | None = None) -> str:
    cfg = cfg or await load_config("composer")
    instructions = (payload.get("system_block") or "").strip()
    standing = (payload.get("standing_instruction") or "").strip()
    if standing:
        instructions = (
            f"{instructions}\n\n## Standing instruction (project-wide)\n{standing}"
        )
    if not instructions:
        instructions = (
            "Eres un composer. Devuelve un informe markdown agregando los "
            "scores por dimensión. Sin system_prompt configurado el informe "
            "será mínimo — usa los datos ya pre-procesados que recibes."
        )
    agent = make_agent(cfg, instructions=instructions)

    user_prompt = f"""\
ROL: COMPOSER (escribe el `detailed_report` markdown del análisis).

CONTEXTO
- Agente: {payload.get('agente') or 'la asesora'}
- Total global: {payload.get('total_score')}/{payload.get('ideal_score')} ({payload.get('percent_quality')}%)
- Modo: {payload.get('analysis_mode')}

DATOS POR DIMENSIÓN (resumen + reglas con sus citas y gaps):
{_per_dim_block(payload.get('scores_by_dimension') or {}, payload.get('scores') or {})}

Devuelve el informe markdown agregando todas las dimensiones aplicables.
Estructura sugerida (ajústala al system del proyecto):
1. Resumen ejecutivo (2-3 frases)
2. Una sección por dimensión aplicable, con:
   - Subtítulo + porcentaje
   - Bullets con los hallazgos clave (cita + por qué importa + corrección)
3. Acciones prioritarias (3 máx)

Solo markdown. Sin envoltorios JSON. Las dimensiones n/a no necesitan
sección — menciónalas brevemente al final si es relevante.
"""
    result = await bounded_run(agent, user_prompt)
    return str(result.final_output or "")
