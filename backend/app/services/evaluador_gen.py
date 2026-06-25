"""Generate an evaluador (scoring rubric + prompts) with an LLM.

Given a free description / call script ("guión"), an LLM builds the rubric
(parameters with weights) and the auditor/coach/composer prompts in the format
the audit pipeline needs. Same LLM (DEFAULT_LLM_API_KEY) as the evaluator.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..agents.llm import bounded_run, load_config, make_agent

log = structlog.get_logger()

DIM = "informacion_telefonica"  # the audit pipeline's single dimension


class _Rule(BaseModel):
    id: str = ""
    name: str = ""
    weight: int = 10
    criteria: str = ""
    description: str = ""


class _EvaluadorDraft(BaseModel):
    auditor_prompt: str = ""
    feedback_prompt: str = ""
    report_prompt: str = ""
    rules: list[_Rule] = Field(default_factory=list)


_INSTRUCTIONS = """Eres un diseñador de EVALUADORES de calidad de llamadas comerciales/de formación.
A partir de un GUIÓN o descripción de cómo debe ser la llamada (qué debe hacer la asesora), genera un
evaluador completo:
- rules: la rúbrica. Una entrada por cada cosa importante a evaluar (normalmente las FASES del guión:
  apertura, descubrimiento/escucha, confirmación, propuesta, cierre, tono, etc.). Cada regla con:
  id (corto, en minúsculas, sin espacios), name (claro), weight (0-100, importancia relativa),
  criteria (qué se mira, en pocas palabras), description (qué tiene que cumplir la asesora para
  puntuar alto). Los weight deben sumar aprox. 100.
- auditor_prompt: instrucciones para el auditor que puntúa cada parámetro (incluye el contexto del
  guión y que sea exigente, que cite evidencia y no premie el discurso genérico ni la presión).
- feedback_prompt: instrucciones para el coach que da feedback breve y accionable a la asesora.
- report_prompt: instrucciones para redactar un informe claro de la llamada.
Escribe en español. Sé concreto y fiel al guión recibido."""


def _slug(s: str, fallback: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-zA-Z0-9]+", "_", s).strip("_").lower()
    return s or fallback


async def generate(nombre: str, descripcion: str) -> dict[str, Any]:
    cfg = await load_config("evaluador_gen")
    agent = make_agent(cfg, instructions=_INSTRUCTIONS, output_type=_EvaluadorDraft)
    prompt = (
        f"Nombre del evaluador: {nombre or '(libre)'}\n\n"
        f"GUIÓN / descripción de cómo debe ser la llamada:\n{descripcion.strip()}\n"
    )
    result = await bounded_run(agent, prompt[:20000])
    d: _EvaluadorDraft = result.final_output

    # Build the rules_table: force the pipeline dimension, unique ids, scale
    # weights to ~100.
    raw = [r for r in d.rules if (r.name or r.criteria or r.description)]
    total = sum(max(0, r.weight) for r in raw) or len(raw) or 1
    rules: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, r in enumerate(raw):
        rid = _slug(r.id or r.name, f"param_{i+1}")
        while rid in seen:
            rid = f"{rid}_{i+1}"
        seen.add(rid)
        w = max(1, round(max(0, r.weight) / total * 100))
        rules.append({
            "id": rid, "name": (r.name or rid).strip(), "weight": w, "dimension": DIM,
            "criteria": (r.criteria or "").strip(), "description": (r.description or "").strip(),
        })
    return {
        "auditor_prompt": (d.auditor_prompt or "").strip(),
        "feedback_prompt": (d.feedback_prompt or "").strip(),
        "report_prompt": (d.report_prompt or "").strip(),
        "rules_table": rules,
    }
