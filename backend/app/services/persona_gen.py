"""Generate an AI "persona" (personalidad) with an LLM.

Given a department, a difficulty level, a name and a free description of the
desired behaviour, an LLM enriches everything: the persona profile, the
objections, the reason for the call (situación/guion) and the product —
using the department's FAQs of that level as grounding. Same LLM
(DEFAULT_LLM_API_KEY) as the evaluator.
"""
from __future__ import annotations

from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..agents.llm import bounded_run, load_config, make_agent

log = structlog.get_logger()


class _PersonaDraft(BaseModel):
    persona: str = Field("", description="Perfil del alumno IA: quién es, contexto, tono, qué le mueve.")
    objeciones: str = Field("", description="Objeciones que pondrá durante la llamada.")
    faqs: str = Field("", description="Dudas/FAQs propias de esta persona (texto).")
    guion: str = Field("", description="Situación/guion: motivo de la llamada y cómo se comporta.")
    producto: str = Field("", description="Producto/servicio (etiqueta CORTA, máx ~8 palabras).")
    datos_agente: str = Field("", description="Ficha breve que ve la ASESORA antes de llamar (a quién llama, contexto, qué dejó anotado el CRM).")
    intencion: str = Field("", description="Intención del alumno en 2-5 palabras (ej: 'poco interesado, con prisa').")


_INSTRUCTIONS = """Eres un diseñador de simulacros de formación para asesoras comerciales.
Creas PERSONAS IA (un 'alumno' que RECIBE o HACE una llamada y la asesora practica con él).
A partir de: nombre, nivel de dificultad, una descripción del comportamiento deseado, el
departamento y sus FAQs comunes de ese nivel, GENERA y ENRIQUECE una persona realista y
coherente. Devuelve:
- persona: perfil completo (edad/contexto/situación, tono, qué le preocupa, su carácter).
- objeciones: las objeciones concretas que pondrá (acordes al nivel: más duras si es dificil).
- faqs: dudas propias de esta persona (puedes apoyarte en las FAQs del departamento).
- guion: la situación y el motivo de la llamada, y cómo evoluciona según la asesora.
- producto: el producto/servicio sobre el que va la llamada (ETIQUETA CORTA, máx ~8 palabras).
Sé concreto y verosímil. Respeta el nivel de dificultad pedido. Escribe en español."""


async def generate(
    *,
    nombre: str,
    dificultad: str,
    descripcion: str,
    dept_nombre: str = "",
    faqs_text: str = "",
) -> dict[str, Any]:
    prompt = (
        f"Nombre de la persona IA: {nombre}\n"
        f"Nivel de dificultad: {dificultad}\n"
        f"Departamento: {dept_nombre or '(sin departamento)'}\n"
        f"Descripción / comportamiento deseado:\n{descripcion or '(libre)'}\n\n"
        f"FAQs comunes del departamento para el nivel '{dificultad}':\n{faqs_text or '(ninguna)'}\n"
    )
    cfg = await load_config("persona_gen")
    agent = make_agent(cfg, instructions=_INSTRUCTIONS, output_type=_PersonaDraft)
    result = await bounded_run(agent, prompt)
    d: _PersonaDraft = result.final_output
    return {
        "persona": (d.persona or "").strip(),
        "objeciones": (d.objeciones or "").strip(),
        "faqs": (d.faqs or "").strip(),
        "guion": (d.guion or "").strip(),
        "producto": (d.producto or "").strip(),
        "datos_agente": (d.datos_agente or "").strip(),
        "intencion": (d.intencion or "").strip(),
    }
