"""Comercial leveling engine for simulacros.

A comercial has a `nivel` within their department's ordered `niveles`. The
department defines `reglas` that promote/demote based on recent simulacro
results. This module evaluates those rules and (optionally) applies the move.

Rule shape (all configurable, stored on simulacro_departamentos.reglas):
    {
      "id": "r1",
      "from_nivel": "facil",        # only applies when comercial is here
      "to_nivel": "medio",
      "direction": "promote",        # promote | demote
      "scenario_dificultad": "facil" | null,   # filter tests by scenario level
      "metric": "count_above" | "avg_last_n" | "consecutive_above",
      "n": 3,                        # how many tests
      "min_score": 80               # percent threshold (0-100)
    }

Examples the coordinator asked for:
  - "3 tests fáciles con >80 → medio":
      {from:facil,to:medio,direction:promote,scenario_dificultad:facil,
       metric:count_above,n:3,min_score:80}
  - "media de los últimos 4 tests > 80 → siguiente nivel":
      {from:medio,to:dificil,direction:promote,metric:avg_last_n,n:4,min_score:80}
"""
from __future__ import annotations

from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.models import QualityAnalysis, SimulacroComercial, SimulacroDepartamento

log = structlog.get_logger()

_DEFAULT_NIVELES = ["facil", "medio", "dificil"]


def _scenario_dificultad(row: QualityAnalysis) -> str | None:
    snap = row.crm_snapshot or {}
    if not isinstance(snap, dict):
        return None
    sim = snap.get("_simulacro") or {}
    sc = sim.get("scenario") or {}
    d = sc.get("dificultad")
    return str(d) if d else None


def _percent(row: QualityAnalysis) -> float | None:
    if row.percent_quality is None:
        return None
    try:
        return float(row.percent_quality)
    except (TypeError, ValueError):
        return None


async def _recent_tests(
    session: AsyncSession, comercial: SimulacroComercial, project_id: str, limit: int = 30
) -> list[QualityAnalysis]:
    rows = (await session.execute(
        select(QualityAnalysis)
        .where(
            QualityAnalysis.project_id == project_id,
            QualityAnalysis.agente_nombre == comercial.nombre,
            QualityAnalysis.status == "done",
        )
        .order_by(QualityAnalysis.created_at.desc())
        .limit(limit)
    )).scalars().all()
    return list(rows)


def _rule_matches(rule: dict[str, Any], tests: list[tuple[float, str | None]]) -> bool:
    """tests: list of (percent, scenario_dificultad), most-recent first."""
    diff = rule.get("scenario_dificultad")
    pool = [(p, d) for (p, d) in tests if not diff or d == diff]
    n = int(rule.get("n") or 0)
    min_score = float(rule.get("min_score") or 0)
    metric = rule.get("metric") or "count_above"
    direction = rule.get("direction") or "promote"

    if metric == "count_above":
        cnt = sum(1 for (p, _) in pool if p >= min_score)
        return cnt >= n
    if metric == "avg_last_n":
        last = pool[:n]
        if len(last) < n:
            return False
        avg = sum(p for (p, _) in last) / len(last)
        return avg >= min_score if direction == "promote" else avg <= min_score
    if metric == "consecutive_above":
        last = pool[:n]
        if len(last) < n:
            return False
        if direction == "promote":
            return all(p >= min_score for (p, _) in last)
        return all(p <= min_score for (p, _) in last)
    return False


async def evaluate_and_apply(
    session: AsyncSession,
    comercial: SimulacroComercial,
    *,
    persist: bool = True,
    auto_trigger: bool = False,
) -> dict[str, Any]:
    """Evaluate the department's rules for this comercial and (optionally)
    apply the first matching move. Returns a trace dict.

    `auto_trigger=True` is used by the post-call hook: it respects the
    department's `auto_evaluar` switch (a coordinator can turn off automatic
    leveling and only move people manually)."""
    dept: SimulacroDepartamento | None = None
    if comercial.department_id:
        dept = await session.get(SimulacroDepartamento, comercial.department_id)

    if auto_trigger and dept is not None and not dept.auto_evaluar:
        return {"changed": False, "nivel": comercial.nivel, "reason": "auto-evaluación desactivada en el departamento"}

    niveles = (dept.niveles if dept and dept.niveles else _DEFAULT_NIVELES)
    reglas = (dept.reglas if dept and dept.reglas else [])
    project_id = (dept.project_id if dept and dept.project_id else settings.simulacros_project_id)
    current = comercial.nivel or (niveles[0] if niveles else "facil")

    if not reglas:
        return {"changed": False, "nivel": current, "reason": "sin reglas configuradas"}

    rows = await _recent_tests(session, comercial, project_id)
    tests = [(p, _scenario_dificultad(r)) for r in rows if (p := _percent(r)) is not None]
    if not tests:
        return {"changed": False, "nivel": current, "reason": "sin tests completados todavía"}

    for rule in reglas:
        if (rule.get("from_nivel") or "") != current:
            continue
        to = rule.get("to_nivel")
        if not to or to not in niveles:
            continue
        if _rule_matches(rule, tests):
            if persist:
                comercial.nivel = to
                session.add(comercial)
                await session.commit()
            log.info(
                "leveling_move",
                comercial=comercial.nombre, from_nivel=current, to_nivel=to,
                rule=rule.get("id"), direction=rule.get("direction"),
            )
            return {
                "changed": True, "from": current, "nivel": to,
                "rule_id": rule.get("id"), "direction": rule.get("direction"),
                "reason": f"regla '{rule.get('id')}' cumplida ({rule.get('metric')} n={rule.get('n')} ≥{rule.get('min_score')})",
                "tests_considerados": len(tests),
            }

    return {"changed": False, "nivel": current, "reason": "ninguna regla cumplida", "tests_considerados": len(tests)}


async def evaluate_by_name(
    session: AsyncSession, nombre: str, *, auto_trigger: bool = False
) -> dict[str, Any] | None:
    """Find a comercial by name and run the engine. Used by the post-call hook
    (simulacros are attributed by name). Returns None if no comercial matches."""
    comercial = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.nombre == nombre)
    )).scalar_one_or_none()
    if comercial is None:
        return None
    return await evaluate_and_apply(session, comercial, persist=True, auto_trigger=auto_trigger)
