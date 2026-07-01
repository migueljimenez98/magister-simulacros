"""Diagnóstico (y purga opcional) de parámetros de rúbrica.

Muestra DÓNDE vive cada id de parámetro: en la rúbrica por defecto del proyecto,
en cada evaluador del catálogo, y qué evaluador tiene asignado cada departamento.
Sirve para entender por qué un parámetro "quitado" sigue puntuándose (típico:
evaluador duplicado, o vive en la rúbrica por defecto del proyecto).

Uso:
    # Solo diagnóstico (no toca nada):
    python -m scripts.diag_rubricas cambios_novedades tema_practico_lomloe

    # Diagnóstico + eliminar esos ids de TODAS las rúbricas (proyecto + catálogo):
    python -m scripts.diag_rubricas --purge cambios_novedades tema_practico_lomloe

    # Limpiar esos ids de las EVALUACIONES ya guardadas (analysis.scores) y
    # recalcular la nota. Esto es lo que quita el parámetro del detalle y de
    # "temas más fallados" sin depender de reevaluar:
    python -m scripts.diag_rubricas --clean-analyses cambios_novedades tema_practico_lomloe

    # Ambas cosas a la vez:
    python -m scripts.diag_rubricas --purge --clean-analyses

Si no se pasan ids, usa por defecto: cambios_novedades, tema_practico_lomloe.
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.db import async_session
from app.core.models import (
    QualityAnalysis,
    QualityProject,
    SimulacroDepartamento,
    SimulacroEvaluador,
)

DEFAULT_IDS = ["cambios_novedades", "tema_practico_lomloe"]


def _rule_ids(rules: list[dict] | None) -> list[str]:
    return [str(r.get("id") or "") for r in (rules or [])]


def _hits(rules: list[dict] | None, targets: set[str]) -> list[str]:
    return [rid for rid in _rule_ids(rules) if rid in targets]


async def _clean_analyses(s, targets: set[str]) -> None:
    """Elimina claves huérfanas de `scores` en TODAS las evaluaciones y recalcula
    total/ideal/percent con los parámetros restantes. Necesario porque
    `analysis.scores` conserva parámetros de rúbricas antiguas hasta que se
    reevalúa con éxito; mientras, siguen saliendo en el detalle y en
    'temas más fallados'."""
    rows = (await s.execute(select(QualityAnalysis))).scalars().all()
    changed = 0
    for a in rows:
        scores = a.scores or {}
        hit_keys = [k for k in scores if k in targets]
        if not hit_keys:
            continue
        for k in hit_keys:
            del scores[k]
        # Recalcula la nota global con los parámetros aplicados que quedan.
        applied = [v for v in scores.values() if isinstance(v, dict) and v.get("applied")]
        total = sum(float(v.get("score") or 0) for v in applied)
        ideal = sum(float(v.get("max") or 0) for v in applied)
        a.scores = dict(scores)  # reasigna para marcar el JSONB como modificado
        a.total_score = total if applied else None
        a.ideal_score = ideal if applied else None
        a.percent_quality = round(100.0 * total / ideal, 2) if ideal > 0 else None
        changed += 1
        print(f"    limpiada evaluación {a.id} (quitados {hit_keys}) -> nota {a.percent_quality}")
    print(f"  [ANALYSES] filas con claves huérfanas limpiadas: {changed}/{len(rows)}")


async def main(target_ids: list[str], purge: bool, clean_analyses: bool) -> None:
    targets = set(target_ids)
    modo = "solo diagnóstico"
    if purge or clean_analyses:
        parts = []
        if purge:
            parts.append("PURGA rúbricas")
        if clean_analyses:
            parts.append("LIMPIA evaluaciones")
        modo = " + ".join(parts)
    print(f"\n=== Buscando parámetros: {sorted(targets)} ===")
    print(f"=== Modo: {modo} ===\n")

    async with async_session() as s:
        # 1) Rúbrica por defecto del proyecto
        project = (await s.execute(
            select(QualityProject).where(QualityProject.id == settings.simulacros_project_id)
        )).scalar_one_or_none()
        if project:
            hits = _hits(project.rules_table, targets)
            print(f"[PROYECTO default '{project.id}'] rules ids: {_rule_ids(project.rules_table)}")
            print(f"    -> contiene target: {hits or 'NO'}")
            if purge and hits:
                project.rules_table = [
                    r for r in (project.rules_table or []) if str(r.get('id')) not in targets
                ]
                print(f"    -> PURGADO. Nuevos ids: {_rule_ids(project.rules_table)}")
        else:
            print(f"[PROYECTO default '{settings.simulacros_project_id}'] NO EXISTE")

        # 2) Catálogo de evaluadores
        evals = (await s.execute(
            select(SimulacroEvaluador).order_by(SimulacroEvaluador.nombre)
        )).scalars().all()
        print(f"\n[CATÁLOGO EVALUADORES] total: {len(evals)}")
        for e in evals:
            hits = _hits(e.rules_table, targets)
            flag = f"  <<< CONTIENE {hits}" if hits else ""
            print(f"  - id={e.id!r} nombre={e.nombre!r} ids={_rule_ids(e.rules_table)}{flag}")
            if purge and hits:
                e.rules_table = [
                    r for r in (e.rules_table or []) if str(r.get('id')) not in targets
                ]
                print(f"      -> PURGADO. Nuevos ids: {_rule_ids(e.rules_table)}")

        # 3) Departamentos y su evaluador asignado
        depts = (await s.execute(
            select(SimulacroDepartamento).order_by(SimulacroDepartamento.nombre)
        )).scalars().all()
        eval_by_id = {e.id: e for e in evals}
        print(f"\n[DEPARTAMENTOS] total: {len(depts)}")
        for d in depts:
            ev = eval_by_id.get(d.evaluador_id) if d.evaluador_id else None
            rub = f"evaluador='{ev.nombre}' (id={ev.id})" if ev else "PROYECTO POR DEFECTO"
            print(f"  - {d.nombre!r} (id={d.id}) -> {rub}")

        # 4) Limpieza de scores huérfanos en las evaluaciones ya guardadas.
        if clean_analyses:
            print("\n[LIMPIEZA DE EVALUACIONES]")
            await _clean_analyses(s, targets)

        if purge or clean_analyses:
            await s.commit()
            print("\n*** Cambios GUARDADOS. ***")
        else:
            print(
                "\n(Solo diagnóstico: no se ha modificado nada. "
                "Añade --purge para limpiar rúbricas y/o --clean-analyses para "
                "limpiar los scores huérfanos de las evaluaciones guardadas.)"
            )


if __name__ == "__main__":
    args = [a for a in sys.argv[1:]]
    purge = "--purge" in args
    clean_analyses = "--clean-analyses" in args
    ids = [a for a in args if not a.startswith("--")] or DEFAULT_IDS
    asyncio.run(main(ids, purge, clean_analyses))
