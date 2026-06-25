"""Import FAQs from an uploaded PDF/TXT and structure them with an LLM.

Plain-text extraction only (no OCR) — a scanned PDF yields no text. Uses the
same LLM (DEFAULT_LLM_API_KEY) as the evaluator to turn the raw document into
the structured {pregunta, respuesta_esperada, nivel} format the system needs.
"""
from __future__ import annotations

import io
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..agents.llm import bounded_run, load_config, make_agent

log = structlog.get_logger()

NIVELES = ["facil", "medio", "dificil"]
_MAX_CHARS = 20000   # cap LLM input


class _FaqOut(BaseModel):
    pregunta: str = ""
    respuesta_esperada: str = ""
    nivel: str = "medio"


class _FaqList(BaseModel):
    faqs: list[_FaqOut] = Field(default_factory=list)


_INSTRUCTIONS = """Eres un extractor de FAQs para simulacros de formación comercial.
Recibes el TEXTO PLANO de un documento (PDF/TXT) con preguntas frecuentes y sus respuestas.
Devuelve una lista de FAQs; cada una con:
- pregunta: la pregunta (reformúlala con claridad si está implícita).
- respuesta_esperada: la respuesta correcta/esperada, concisa.
- nivel: dificultad de manejarla en una llamada → "facil", "medio" o "dificil".
  (precio/garantías/comparativas con la competencia = dificil; dudas simples de
  horario/temario/modalidad = facil; el resto = medio).
No inventes nada que no esté en el texto. Si no hay FAQs claras, devuelve lista vacía."""


def extract_text(filename: str, data: bytes) -> str:
    """Plain-text from a PDF (pypdf) or a TXT/MD file. No OCR."""
    name = (filename or "").lower()
    if name.endswith(".pdf"):
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(data))
            parts: list[str] = []
            for page in reader.pages:
                try:
                    parts.append(page.extract_text() or "")
                except Exception:  # noqa: BLE001
                    continue
            return "\n".join(parts).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("faq_pdf_extract_failed", error=str(exc)[:200])
            return ""
    # txt / md / csv / anything else → decode best-effort
    return data.decode("utf-8", errors="ignore").strip()


async def parse_faqs(raw_text: str, forced_nivel: str | None = None) -> list[dict[str, Any]]:
    """LLM → structured FAQs. `forced_nivel` overrides the model's level guess."""
    text = (raw_text or "").strip()
    if not text:
        return []
    cfg = await load_config("faq_importer")
    agent = make_agent(cfg, instructions=_INSTRUCTIONS, output_type=_FaqList)
    result = await bounded_run(agent, text[:_MAX_CHARS])
    out: _FaqList = result.final_output
    faqs: list[dict[str, Any]] = []
    for f in out.faqs:
        preg = (f.pregunta or "").strip()
        resp = (f.respuesta_esperada or "").strip()
        if not preg and not resp:
            continue
        if forced_nivel in NIVELES:
            nivel = forced_nivel
        else:
            nivel = f.nivel if f.nivel in NIVELES else "medio"
        faqs.append({"pregunta": preg, "respuesta_esperada": resp, "nivel": nivel})
    return faqs
