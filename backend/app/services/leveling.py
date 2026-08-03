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

from datetime import datetime, timezone
from typing import Any

import structlog
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.models import (
    QualityAnalysis,
    SimulacroComercial,
    SimulacroDepartamento,
    SimulacroNivelEvento,
)

log = structlog.get_logger()

_DEFAULT_NIVELES = ["facil", "medio", "dificil"]

# CUÁNDO OCURRIÓ la llamada, no cuándo se insertó la fila. La diferencia importa
# al recuperar llamadas perdidas: se insertan hoy (created_at) pero son de días
# pasados (call_date). Ordenando por inserción, una recuperación de 34 llamadas
# antiguas se cuela como "los últimos 34 tests" y mueve de nivel a quien no toca
# (pasó el 2026-08-03 con micheller: bajó a fácil por llamadas del 30-31 jul).
_FECHA_LLAMADA = func.coalesce(QualityAnalysis.call_date, QualityAnalysis.created_at)


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
        .order_by(_FECHA_LLAMADA.desc())
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


# ── Historial de niveles (progreso real del agente) ─────────────────────────


def _direction(niveles: list[str], from_nivel: str | None, to_nivel: str) -> str:
    """promote / demote / lateral / alta, según la posición en la escala."""
    if from_nivel is None:
        return "alta"
    try:
        return "promote" if niveles.index(to_nivel) > niveles.index(from_nivel) else "demote"
    except ValueError:
        return "lateral"


async def _llamadas_desde(
    session: AsyncSession, agente_nombre: str, desde: datetime | None
) -> tuple[int, int, float | None]:
    """(llamadas_en_nivel, llamadas_totales, media_en_nivel) para este agente.

    "En nivel" = simulacros completados DESDE `desde` (el último cambio de
    nivel, o el alta). Es la respuesta a "cuántas llamadas hicieron falta".
    Solo cuentan los evaluados (status done con nota)."""
    stmt = select(QualityAnalysis.percent_quality, _FECHA_LLAMADA).where(
        QualityAnalysis.agente_nombre == agente_nombre,
        QualityAnalysis.status == "done",
        QualityAnalysis.percent_quality.isnot(None),
    )
    rows = (await session.execute(stmt)).all()
    total = len(rows)
    en_nivel = [
        float(p) for (p, fecha) in rows
        if desde is None or (fecha is not None and fecha > desde)
    ]
    media = round(sum(en_nivel) / len(en_nivel), 2) if en_nivel else None
    return len(en_nivel), total, media


async def record_nivel_change(
    session: AsyncSession,
    comercial: SimulacroComercial,
    *,
    from_nivel: str | None,
    to_nivel: str,
    origen: str = "auto",
    rule_id: str | None = None,
    motivo: str = "",
    actor: str | None = None,
    niveles: list[str] | None = None,
    departamento: str | None = None,
) -> SimulacroNivelEvento:
    """Deja constancia de un cambio de nivel y de cuánto trabajo costó.

    Añade la fila a la sesión (NO hace commit: lo hace quien llama, junto al
    cambio de nivel, para que ambas cosas viajen en la misma transacción)."""
    if departamento is None and comercial.department_id:
        dept = await session.get(SimulacroDepartamento, comercial.department_id)
        departamento = dept.nombre if dept else None
    if niveles is None:
        niveles = _DEFAULT_NIVELES

    # Punto de partida: el último evento de este agente EN ESTE departamento.
    # Sin eventos previos contamos desde el principio de su historial.
    # `== None` en SQL nunca casa: las fichas sin departamento necesitan IS NULL.
    dept_cond = (
        SimulacroNivelEvento.department_id.is_(None)
        if comercial.department_id is None
        else SimulacroNivelEvento.department_id == comercial.department_id
    )
    prev = (await session.execute(
        select(SimulacroNivelEvento)
        .where(SimulacroNivelEvento.agente_nombre == comercial.nombre, dept_cond)
        .order_by(desc(SimulacroNivelEvento.created_at))
        .limit(1)
    )).scalars().first()
    en_nivel, totales, media = await _llamadas_desde(
        session, comercial.nombre, prev.created_at if prev else None
    )

    ev = SimulacroNivelEvento(
        # Fijamos created_at en Python: con server_default el valor solo existe
        # en la BD y leerlo tras el commit dispararía un refresh perezoso que
        # en sesión async revienta (MissingGreenlet).
        created_at=datetime.now(timezone.utc),
        comercial_id=comercial.id,
        agente_nombre=comercial.nombre,
        department_id=comercial.department_id,
        departamento=departamento,
        from_nivel=from_nivel,
        to_nivel=to_nivel,
        direction=_direction(niveles, from_nivel, to_nivel),
        origen=origen,
        rule_id=rule_id,
        motivo=motivo or None,
        llamadas_en_nivel=en_nivel,
        llamadas_totales=totales,
        avg_percent_en_nivel=media,
        actor=actor,
    )
    session.add(ev)
    log.info(
        "nivel_evento",
        agente=comercial.nombre, from_nivel=from_nivel, to_nivel=to_nivel,
        origen=origen, llamadas_en_nivel=en_nivel,
    )
    return ev


def evento_to_dict(ev: SimulacroNivelEvento) -> dict[str, Any]:
    return {
        "id": ev.id,
        "fecha": ev.created_at.isoformat() if ev.created_at else None,
        "agente_nombre": ev.agente_nombre,
        "comercial_id": ev.comercial_id,
        "department_id": ev.department_id,
        "departamento": ev.departamento,
        "from_nivel": ev.from_nivel,
        "to_nivel": ev.to_nivel,
        "direction": ev.direction,
        "origen": ev.origen,
        "rule_id": ev.rule_id,
        "motivo": ev.motivo or "",
        "llamadas_en_nivel": ev.llamadas_en_nivel,
        "llamadas_totales": ev.llamadas_totales,
        "avg_percent_en_nivel": (
            float(ev.avg_percent_en_nivel) if ev.avg_percent_en_nivel is not None else None
        ),
        "actor": ev.actor or "",
    }


async def progreso_en_nivel(
    session: AsyncSession, agente_nombre: str, desde: datetime | None
) -> dict[str, Any]:
    """Progreso acumulado en el nivel ACTUAL (aún sin cambio registrado):
    llamadas hechas desde `desde`, total histórico y nota media del tramo."""
    en_nivel, totales, media = await _llamadas_desde(session, agente_nombre, desde)
    return {
        "llamadas_en_nivel": en_nivel,
        "llamadas_totales": totales,
        "avg_percent_en_nivel": media,
    }


async def historial(
    session: AsyncSession, agente_nombre: str, *, limit: int = 100
) -> list[dict[str, Any]]:
    """Historial de niveles de un agente (todas sus fichas), más reciente primero."""
    rows = (await session.execute(
        select(SimulacroNivelEvento)
        .where(SimulacroNivelEvento.agente_nombre == agente_nombre)
        .order_by(desc(SimulacroNivelEvento.created_at))
        .limit(max(1, min(limit, 500)))
    )).scalars().all()
    return [evento_to_dict(e) for e in rows]


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
            motivo = (
                f"regla '{rule.get('id')}' cumplida ({rule.get('metric')} "
                f"n={rule.get('n')} ≥{rule.get('min_score')})"
            )
            evento = None
            if persist:
                comercial.nivel = to
                session.add(comercial)
                # Constancia del movimiento + cuántos simulacros costó, en la
                # MISMA transacción que el cambio de nivel.
                evento = await record_nivel_change(
                    session, comercial,
                    from_nivel=current, to_nivel=to,
                    origen="auto", rule_id=rule.get("id"), motivo=motivo,
                    niveles=list(niveles),
                    departamento=(dept.nombre if dept else None),
                )
                await session.commit()
            log.info(
                "leveling_move",
                comercial=comercial.nombre, from_nivel=current, to_nivel=to,
                rule=rule.get("id"), direction=rule.get("direction"),
            )
            return {
                "changed": True, "from": current, "nivel": to,
                "rule_id": rule.get("id"), "direction": rule.get("direction"),
                "reason": motivo,
                "tests_considerados": len(tests),
                "llamadas_en_nivel": evento.llamadas_en_nivel if evento else None,
                "evento": evento_to_dict(evento) if evento else None,
            }

    return {"changed": False, "nivel": current, "reason": "ninguna regla cumplida", "tests_considerados": len(tests)}


async def evaluate_by_name(
    session: AsyncSession, nombre: str, *, auto_trigger: bool = False
) -> dict[str, Any] | None:
    """Find a comercial by name and run the engine. Used by the post-call hook
    (simulacros are attributed by name). Returns None if no comercial matches."""
    # An agent can have a membership per department; level the ACTIVE one.
    rows = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.nombre == nombre)
    )).scalars().all()
    comercial = next((c for c in rows if c.activo), rows[0] if rows else None)
    if comercial is None:
        return None
    return await evaluate_and_apply(session, comercial, persist=True, auto_trigger=auto_trigger)
