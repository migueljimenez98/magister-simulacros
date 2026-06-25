"""Seed the simulacros project + a starter set of scenarios.

Idempotent: upserts the project by id (settings.simulacros_project_id) and
inserts the 3 starter scenarios only if the project has none yet.

Usage:
    python -m scripts.seed_simulacros
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.config import settings
from app.core.db import async_session
from app.core.models import (
    QualityProject,
    SimulacroDepartamento,
    SimulacroEvaluador,
    SimulacroScenario,
)

EVALUADOR_ID = "eva-general"

DEPT_ID = "dep-oposiciones"
DEPT_NIVELES = ["facil", "medio", "dificil"]
# Reglas de escalado de ejemplo (editables desde el panel / API).
DEPT_REGLAS = [
    {"id": "asc_facil_medio", "from_nivel": "facil", "to_nivel": "medio",
     "direction": "promote", "scenario_dificultad": "facil",
     "metric": "count_above", "n": 3, "min_score": 80},
    {"id": "asc_medio_dificil", "from_nivel": "medio", "to_nivel": "dificil",
     "direction": "promote", "scenario_dificultad": None,
     "metric": "avg_last_n", "n": 4, "min_score": 80},
    {"id": "desc_medio_facil", "from_nivel": "medio", "to_nivel": "facil",
     "direction": "demote", "scenario_dificultad": None,
     "metric": "avg_last_n", "n": 4, "min_score": 40},
]

# The simulacro is audited under the phone-call dimension so the existing
# coach (info_call tier) and composer light up, and the auditor validates
# against the real guion-comercial-magister.md.
DIM = "informacion_telefonica"

RULES = [
    {"id": "inicio", "name": "Apertura e identificación", "weight": 10, "dimension": DIM,
     "criteria": "saludo, identificación Magister, tono cercano, motivo de la llamada",
     "description": "Abre con claridad, se identifica como asesora de Magister, tono cálido y profesional, deja claro el motivo."},
    {"id": "conoce_situacion", "name": "Conoce la situación del opositor", "weight": 15, "dimension": DIM,
     "criteria": "cuerpo/especialidad, CCAA, año de examen, situación actual",
     "description": "Pregunta o usa el contexto del opositor (qué oposición prepara, comunidad, convocatoria, punto de partida)."},
    {"id": "entiende_situacion", "name": "Entiende la situación (escucha activa)", "weight": 15, "dimension": DIM,
     "criteria": "escucha, reformulación, detecta necesidad real, empatía",
     "description": "Escucha de verdad, reformula lo que el opositor dice y detecta su necesidad antes de proponer."},
    {"id": "ofrece_soluciones", "name": "Ofrece soluciones adaptadas", "weight": 20, "dimension": DIM,
     "criteria": "modalidad adecuada, plan, becas, encaje con el perfil",
     "description": "Propone la modalidad/plan que encaja con el perfil y la comunidad del opositor; no suelta un discurso genérico."},
    {"id": "informacion", "name": "Información correcta y relevante", "weight": 15, "dimension": DIM,
     "criteria": "precio, plazos, temario, convocatoria, datos exactos",
     "description": "Los datos que da (precio, plazos, temario, convocatoria, baremo) son correctos y relevantes para este opositor."},
    {"id": "cierre", "name": "Cierre y próximo paso", "weight": 15, "dimension": DIM,
     "criteria": "avance claro, compromiso, próximo paso concreto",
     "description": "Cierra orientando: deja un próximo paso concreto (matrícula, envío de info, nueva llamada) sin presionar."},
    {"id": "objeciones", "name": "Manejo de objeciones", "weight": 10, "dimension": DIM,
     "criteria": "responde con datos, sin presión, rebate con calma",
     "description": "Maneja las objeciones (precio, dudas, comparativa) con datos y calma, sin tácticas de presión."},
]

AUDITOR_PROMPT = """\
Eres un AUDITOR de calidad de llamadas comerciales de Magister (centro de
preparación de oposiciones docentes). Estás evaluando un SIMULACRO DE
FORMACIÓN: la asesora practica contra un "alumno" interpretado por una IA de
voz. Audítala EXACTAMENTE igual que una llamada de información real — el hecho
de que sea un simulacro no cambia la rúbrica.

Filosofía de puntuación (orden de prioridad):
1. Adherencia al guión comercial de Magister y al rol de ORIENTADORA (no
   vendedora de presión): ayudar al opositor a decidir.
2. Comprensión real del opositor (escucha, reformulación) por encima de
   soltar datos sueltos.
3. Corrección de la información (precio, modalidad, plazos, convocatoria).

Para el parámetro que te toca:
- Puntúa en [0, weight]. Sé justo: si la asesora no tuvo material para ese
  punto (la conversación no llegó ahí), no la penalices con un 0 arbitrario;
  explícalo en la nota.
- Cita SIEMPRE de forma literal el fragmento de la transcripción que respalda
  tu valoración en `evidencia`.
- `gap`: una mejora concreta y accionable si la hay; vacío si cumplió bien.
- Usa una `etiqueta` del set de criterios de la regla cuando aplique.
No inventes datos del alumno ni de Magister que no estén en la transcripción
o en el contexto KB.
"""

FEEDBACK_PROMPT = """\
Eres un COACH de ventas de Magister que escribe un mensaje breve y
constructivo para una ASESORA tras un simulacro de llamada. Su rol es de
orientadora de opositores, no de closer. Escribe 2-4 frases, en español,
centradas en UNA mejora concreta y accionable, citando lo que dijo o no dijo
en la llamada. Tono cercano y profesional, sin coachismos vacíos. Si lo hizo
bien y no hay una mejora clara, dilo brevemente.
"""

REPORT_PROMPT = """\
Eres el COMPOSER que redacta el informe markdown de un simulacro de llamada de
Magister. Estructura:
1. **Resumen** (2-3 líneas: cómo fue el simulacro y la nota global).
2. **Por parámetro**: para cada parámetro evaluado, su puntuación, qué hizo
   bien y qué mejorar, con cita literal.
3. **Acciones prioritarias**: 1-3 mejoras concretas para la próxima llamada.
Español, claro, sin relleno. No inventes datos que no estén en las
evidencias.
"""

PROMPTS = {
    "dimensions": {
        DIM: {"label": "Simulacro (llamada)", "system_prompt": AUDITOR_PROMPT},
    },
    "feedback": {"system_prompt": FEEDBACK_PROMPT},
    "report": {"system_prompt": REPORT_PROMPT},
}

CONFIG = {
    "data_source": "retell",
    "product": "oposiciones",
    "empty_channels_drag_down": False,
    "standing_instruction": (
        "Esto es un simulacro de formación de asesoras de Magister. El 'alumno' "
        "es una IA. Evalúa el desempeño de la asesora como en una llamada real."
    ),
}

SCENARIOS = [
    {
        "nombre": "Opositora decidida — Primaria (Madrid)",
        "dificultad": "facil",
        "producto": "oposiciones presencial",
        "persona": (
            "Mujer, 28 años, maestra de Primaria que quiere preparar las oposiciones "
            "de Madrid para la próxima convocatoria. Está motivada y colaboradora, "
            "responde a lo que se le pregunta y tiene buena disposición a matricularse "
            "si le encaja."
        ),
        "objeciones": "Apenas pone pegas; solo quiere confirmar horarios y cómo es el grupo presencial.",
        "faqs": "¿Cuándo empieza el grupo? ¿Cuántas horas a la semana? ¿El temario está actualizado a la última convocatoria?",
        "guion": (
            "Llama interesada tras ver información de Magister. Quiere preparar Primaria "
            "en Madrid de forma presencial. Deja que la asesora lleve la conversación; "
            "si la asesora explica bien modalidad, precio y próximos pasos, se muestra "
            "dispuesta a reservar plaza."
        ),
    },
    {
        "nombre": "Indeciso comparando modalidades — Secundaria (Andalucía)",
        "dificultad": "medio",
        "producto": "oposiciones videoconferencia vs presencial",
        "persona": (
            "Hombre, 34 años, trabaja por las mañanas. Prepara Secundaria (Matemáticas) "
            "en Andalucía. Tiene interés real pero dudas: no sabe si online o presencial, "
            "le preocupan las fechas y quiere pensárselo."
        ),
        "objeciones": (
            "'No sé si me cuadra el presencial por el trabajo', 'tengo que mirar fechas de "
            "examen', 'me lo quiero pensar'. Pide tiempo antes de decidir."
        ),
        "faqs": (
            "¿Hay clases grabadas si no puedo asistir en directo? ¿Cuándo es la próxima "
            "convocatoria en Andalucía? ¿Qué incluye el precio? ¿Hay simulacros de examen?"
        ),
        "guion": (
            "Llama para informarse. Compara videoconferencia y presencial. La asesora debe "
            "entender su situación (trabaja de mañanas) y orientarle hacia la modalidad que "
            "encaja, resolviendo dudas de fechas y precio. Si la asesora no le entiende, se "
            "queda en 'me lo pienso'."
        ),
    },
    {
        "nombre": "Escéptico con objeción de precio — FP (Cataluña)",
        "dificultad": "dificil",
        "producto": "oposiciones videoconferencia",
        "persona": (
            "Mujer, 41 años, escéptica y directa. Prepara FP (Informática) en Cataluña. Ya "
            "ha mirado academias de la competencia y le parece caro. Interrumpe, presiona "
            "con el precio y desconfía de que 'todas las academias prometen lo mismo'."
        ),
        "objeciones": (
            "'Es más caro que otras', 'no me garantizáis la plaza', '¿por qué pagar esto si "
            "puedo prepararme por mi cuenta?', 'os llamo yo si me interesa'. Objeción de "
            "precio dura y comparación con competencia."
        ),
        "faqs": (
            "¿Por qué sois más caros? ¿Qué tasa de aprobados tenéis? ¿Qué pasa si no apruebo? "
            "¿Cuántos años de temario incluye? ¿Hay descuentos?"
        ),
        "guion": (
            "Llamada exigente. La opositora pone a prueba a la asesora con objeciones de "
            "precio y comparativa. La asesora debe mantener el guión, no entrar en presión, "
            "rebatir con datos (metodología, simulacros, seguimiento) y orientar con calma. "
            "Si la asesora se pone a la defensiva o presiona, la opositora corta la llamada."
        ),
    },
]


async def main() -> None:
    async with async_session() as s:
        proj = await s.get(QualityProject, settings.simulacros_project_id)
        if proj is None:
            proj = QualityProject(
                id=settings.simulacros_project_id,
                name="Simulacros Magister",
                description="Simulacros de llamadas de formación (Retell). Una asesora practica contra un alumno IA.",
                analysis_mode="statistical",
                rules_table=RULES,
                kb_collection_id="simulacros-kb",
                config=CONFIG,
                prompts=PROMPTS,
                enabled=True,
            )
            s.add(proj)
            print(f"Created project {proj.id}")
        else:
            proj.name = "Simulacros Magister"
            proj.rules_table = RULES
            proj.kb_collection_id = "simulacros-kb"
            proj.config = CONFIG
            proj.prompts = PROMPTS
            proj.enabled = True
            print(f"Updated project {proj.id}")
        await s.commit()

        # Default evaluador (reusable catalog entry) from the project prompts.
        ev = await s.get(SimulacroEvaluador, EVALUADOR_ID)
        if ev is None:
            ev = SimulacroEvaluador(
                id=EVALUADOR_ID, nombre="Evaluador general",
                auditor_prompt=AUDITOR_PROMPT, feedback_prompt=FEEDBACK_PROMPT,
                report_prompt=REPORT_PROMPT, rules_table=RULES,
            )
            s.add(ev)
            print(f"Created evaluador {EVALUADOR_ID}")
        await s.commit()

        # Department "Oposiciones".
        dept = await s.get(SimulacroDepartamento, DEPT_ID)
        if dept is None:
            dept = SimulacroDepartamento(
                id=DEPT_ID, nombre="Oposiciones", niveles=DEPT_NIVELES,
                reglas=DEPT_REGLAS, auto_evaluar=True, evaluador_id=EVALUADOR_ID,
                project_id=settings.simulacros_project_id, activo=True,
            )
            s.add(dept)
            print(f"Created department {DEPT_ID}")
        else:
            dept.project_id = settings.simulacros_project_id
            if not dept.reglas:
                dept.reglas = DEPT_REGLAS
            if not dept.evaluador_id:
                dept.evaluador_id = EVALUADOR_ID
            print(f"Department {DEPT_ID} already exists")
        await s.commit()

        existing = (await s.execute(
            select(SimulacroScenario).where(
                SimulacroScenario.project_id == settings.simulacros_project_id
            )
        )).scalars().all()
        # Backfill department on any scenario that doesn't have one yet.
        backfilled = 0
        for sc in existing:
            if not sc.department_id:
                sc.department_id = DEPT_ID
                backfilled += 1
        if backfilled:
            await s.commit()
            print(f"Backfilled department on {backfilled} scenarios")
        if existing:
            print(f"Scenarios already present ({len(existing)}) — leaving them untouched")
        else:
            for sc in SCENARIOS:
                s.add(SimulacroScenario(project_id=settings.simulacros_project_id, **sc))
            await s.commit()
            print(f"Seeded {len(SCENARIOS)} scenarios")


if __name__ == "__main__":
    asyncio.run(main())
