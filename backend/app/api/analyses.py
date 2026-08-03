"""Analyses (simulacros) API — list, detail, delete, re-run."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select

from ..core.config import settings
from ..core.models import (
    QualityAnalysis,
    QualityProject,
    SimulacroComercial,
    SimulacroDepartamento,
    SimulacroNivelEvento,
)
from ..services import leveling
from .deps import CurrentUser, SessionDep, actor_label, current_user, get_audit_graph, require_role

_NIVEL_ORDER = ["facil", "medio", "dificil"]


def _recommend_nivel(actual: str | None, avg: float | None) -> str | None:
    """Heuristic: high average → suggest moving up a level, low → down."""
    if actual not in _NIVEL_ORDER or avg is None:
        return actual
    i = _NIVEL_ORDER.index(actual)
    if avg >= 80 and i < len(_NIVEL_ORDER) - 1:
        return _NIVEL_ORDER[i + 1]
    if avg < 50 and i > 0:
        return _NIVEL_ORDER[i - 1]
    return actual

log = structlog.get_logger()
router = APIRouter(prefix="/analyses", tags=["analyses"], dependencies=[Depends(current_user)])

# CUÁNDO OCURRIÓ la llamada, no cuándo se insertó la fila. Al recuperar llamadas
# perdidas se insertan hoy pero son de días pasados; agrupar por `created_at`
# las amontona todas en el día de la recuperación y falsea el progreso.
_FECHA_LLAMADA = func.coalesce(QualityAnalysis.call_date, QualityAnalysis.created_at)


class AnalysisOut(BaseModel):
    id: str
    project_id: str
    numero: str
    agente_nombre: str
    escenario: str | None = None
    departamento: str | None = None
    call_date: datetime | None
    status: str
    total_score: float | None
    ideal_score: float | None
    percent_quality: float | None
    feedback_message: str | None
    error: str | None
    admin_feedback: str | None = None
    created_at: datetime
    updated_at: datetime
    scores: dict[str, Any] = Field(default_factory=dict)
    scores_by_dimension: dict[str, Any] = Field(default_factory=dict)
    feedback_by_vertical: dict[str, Any] = Field(default_factory=dict)
    feedback_selected_tier: str | None = None

    class Config:
        from_attributes = True


class AnalysisDetail(AnalysisOut):
    detailed_report: str | None = None
    instruction: str | None = None
    crm_snapshot: dict[str, Any] = Field(default_factory=dict)
    coach_validation_notes: list[dict[str, Any]] = Field(default_factory=list)


class AnalysisListOut(BaseModel):
    items: list[AnalysisOut]
    total: int
    limit: int
    offset: int


_LIST_COLUMNS = (
    QualityAnalysis.id, QualityAnalysis.project_id, QualityAnalysis.numero,
    QualityAnalysis.agente_nombre, QualityAnalysis.escenario, QualityAnalysis.departamento,
    QualityAnalysis.call_date, QualityAnalysis.status,
    QualityAnalysis.total_score, QualityAnalysis.ideal_score, QualityAnalysis.percent_quality,
    QualityAnalysis.feedback_message, QualityAnalysis.error, QualityAnalysis.created_at,
    QualityAnalysis.updated_at, QualityAnalysis.scores, QualityAnalysis.scores_by_dimension,
    QualityAnalysis.feedback_by_vertical, QualityAnalysis.feedback_selected_tier,
)


@router.get("", response_model=AnalysisListOut)
async def list_analyses(
    session: SessionDep,
    project_id: str | None = None,
    agente: str | None = None,
    status_filter: str | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> AnalysisListOut:
    limit = max(1, min(limit, 500))
    conds = []
    if project_id:
        conds.append(QualityAnalysis.project_id == project_id)
    if agente:
        conds.append(QualityAnalysis.agente_nombre == agente)
    if status_filter:
        conds.append(QualityAnalysis.status == status_filter)
    if search:
        conds.append(QualityAnalysis.agente_nombre.ilike(f"%{search}%"))

    total_stmt = select(func.count()).select_from(QualityAnalysis)
    # Orden por fecha de LLAMADA: una recuperación de llamadas antiguas no debe
    # colarse al principio del log como si acabara de ocurrir.
    rows_stmt = select(*_LIST_COLUMNS).order_by(desc(_FECHA_LLAMADA)).limit(limit).offset(offset)
    for c in conds:
        total_stmt = total_stmt.where(c)
        rows_stmt = rows_stmt.where(c)

    total = (await session.execute(total_stmt)).scalar_one()
    rows = (await session.execute(rows_stmt)).mappings().all()
    items = [AnalysisOut(**dict(r)) for r in rows]
    return AnalysisListOut(items=items, total=total, limit=limit, offset=offset)


@router.get("/facets")
async def facets(session: SessionDep, project_id: str | None = None) -> dict[str, list[str]]:
    ag = select(QualityAnalysis.agente_nombre).distinct()
    st = select(QualityAnalysis.status).distinct()
    if project_id:
        ag = ag.where(QualityAnalysis.project_id == project_id)
        st = st.where(QualityAnalysis.project_id == project_id)
    agentes = [r for (r,) in (await session.execute(ag)).all() if r]
    estados = [r for (r,) in (await session.execute(st)).all() if r]
    return {"agentes": sorted(agentes), "estados": sorted(estados)}


@router.get("/stats")
async def stats(
    session: SessionDep,
    departamento: str | None = None,
    agente: str | None = None,
    desde: str | None = None,
    hasta: str | None = None,
) -> dict[str, Any]:
    """Aggregated analytics for the dashboard: KPIs, progress over time,
    worst-scoring parameters, by-difficulty, and per-agent level + recommendation.
    Filters by departamento / agente / date range (all optional)."""
    conds = []
    if departamento:
        conds.append(QualityAnalysis.departamento == departamento)
    if agente:
        conds.append(QualityAnalysis.agente_nombre == agente)
    if desde:
        try:
            conds.append(_FECHA_LLAMADA >= datetime.fromisoformat(desde))
        except ValueError:
            pass
    if hasta:
        try:
            conds.append(_FECHA_LLAMADA <= datetime.fromisoformat(hasta))
        except ValueError:
            pass

    stmt = select(
        QualityAnalysis.id, QualityAnalysis.agente_nombre, QualityAnalysis.departamento,
        QualityAnalysis.status, QualityAnalysis.percent_quality, QualityAnalysis.scores,
        QualityAnalysis.crm_snapshot, _FECHA_LLAMADA,
    )
    for c in conds:
        stmt = stmt.where(c)
    rows = (await session.execute(stmt.order_by(_FECHA_LLAMADA))).all()

    # Rule id → friendly name (from the project's rubric).
    project = await session.get(QualityProject, settings.simulacros_project_id)
    rule_names = {r.get("id"): (r.get("name") or r.get("id")) for r in (project.rules_table or [])} if project else {}

    # Memberships per agent + department names.
    comerciales = (await session.execute(select(SimulacroComercial))).scalars().all()
    deptos = (await session.execute(select(SimulacroDepartamento))).scalars().all()
    dept_name = {d.id: d.nombre for d in deptos}
    memb_by_name: dict[str, list[SimulacroComercial]] = {}
    for c in comerciales:
        memb_by_name.setdefault(c.nombre, []).append(c)

    total = len(rows)
    by_status: dict[str, int] = {}
    percents: list[float] = []
    ts: dict[str, list[float]] = {}              # date -> percents
    por_param: dict[str, list[float]] = {}       # rule_id -> score% list
    por_dif: dict[str, list[float]] = {}         # dificultad -> percents
    por_ag: dict[str, list[float]] = {}          # agente -> scored percents
    ag_count: dict[str, int] = {}                # agente -> total calls
    ag_last: dict[str, dict[str, Any]] = {}      # agente -> last call info

    for aid, agente_nombre, depto, st, pq, scores, snap, fecha in rows:
        by_status[st] = by_status.get(st, 0) + 1
        if agente_nombre:
            ag_count[agente_nombre] = ag_count.get(agente_nombre, 0) + 1
            # rows ascendentes por fecha de llamada → sobrescribir deja la última.
            ag_last[agente_nombre] = {
                "id": aid,
                "fecha": fecha.isoformat() if fecha else None,
                "nota": float(pq) if pq is not None else None,
                "departamento": depto,
                "status": st,
            }
        if st != "done" or pq is None:
            continue
        p = float(pq)
        percents.append(p)
        day = fecha.date().isoformat() if fecha else "—"
        ts.setdefault(day, []).append(p)
        if agente_nombre:
            por_ag.setdefault(agente_nombre, []).append(p)
        dif = (((snap or {}).get("_simulacro") or {}).get("scenario") or {}).get("dificultad")
        if dif:
            por_dif.setdefault(dif, []).append(p)
        for rid, sc in (scores or {}).items():
            if not isinstance(sc, dict) or not sc.get("applied"):
                continue
            mx = sc.get("max") or 0
            scv = sc.get("score")
            if not mx or scv is None:
                continue
            por_param.setdefault(rid, []).append(float(scv) / float(mx) * 100.0)

    def _avg(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 1) if xs else None

    def _memberships(nombre: str) -> list[dict[str, Any]]:
        return [
            {
                "id": m.id,
                "departamento": dept_name.get(m.department_id) or "(sin departamento)",
                "department_id": m.department_id, "nivel": m.nivel, "activo": m.activo,
            }
            for m in memb_by_name.get(nombre, [])
        ]

    # Which agents to show: filtered by the selected department (active there) +
    # any agent with calls in the filtered set; all of them when no filter.
    if departamento:
        # agentes que PERTENECEN a ese departamento (activos o no) + con llamadas allí
        names = {n for n, ms in memb_by_name.items()
                 if any(dept_name.get(m.department_id) == departamento for m in ms)}
        names |= set(ag_count.keys())
    else:
        names = set(memb_by_name.keys()) | set(ag_count.keys())

    por_agente = []
    for n in names:
        membs = _memberships(n)
        activa = next((m for m in membs if m["activo"]), None)
        avg = _avg(por_ag.get(n, []))
        por_agente.append({
            "agente": n,
            "count": ag_count.get(n, 0),
            "avg_percent": avg,
            "nivel_actual": activa["nivel"] if activa else None,
            "departamento_activo": activa["departamento"] if activa else None,
            "nivel_recomendado": _recommend_nivel(activa["nivel"] if activa else None, avg),
            "ultima_id": (ag_last.get(n) or {}).get("id"),
            "ultima_fecha": (ag_last.get(n) or {}).get("fecha"),
            "ultima_nota": (ag_last.get(n) or {}).get("nota"),
            "ultimo_departamento": (ag_last.get(n) or {}).get("departamento"),
            "memberships": membs,
        })
    por_agente.sort(key=lambda x: (x["ultima_fecha"] or ""), reverse=True)

    timeseries = [{"date": d, "avg_percent": _avg(v), "count": len(v)} for d, v in sorted(ts.items())]
    por_parametro = sorted(
        ({"id": rid, "name": rule_names.get(rid, rid), "avg_percent": _avg(v), "count": len(v)}
         for rid, v in por_param.items()),
        key=lambda x: (x["avg_percent"] if x["avg_percent"] is not None else 999),
    )
    por_dificultad = [
        {"dificultad": d, "avg_percent": _avg(v), "count": len(v)}
        for d, v in sorted(por_dif.items(), key=lambda kv: _NIVEL_ORDER.index(kv[0]) if kv[0] in _NIVEL_ORDER else 9)
    ]

    return {
        "total": total,
        "scored": len(percents),
        "avg_percent": _avg(percents),
        "by_status": by_status,
        "timeseries": timeseries,
        "por_parametro": por_parametro,
        "por_dificultad": por_dificultad,
        "por_agente": por_agente,
        "agentes": sorted(memb_by_name.keys() | set(ag_count.keys())),
        "departamentos": sorted({d.nombre for d in deptos}),
    }


def _avg1(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


@router.get("/agente/{nombre}/evolucion")
async def evolucion_agente(nombre: str, session: SessionDep) -> dict[str, Any]:
    """Ficha de evolución de UN agente: todo lo necesario para responder
    "cuántos simulacros ha hecho, en qué nivel, y cómo ha avanzado".

    El bloque clave es `tramos`: los periodos entre cambios de nivel, cada uno
    con las llamadas que hizo mientras estuvo ahí y su nota media. Se calculan
    cruzando las fechas de los simulacros con las de los eventos de nivel.

    Honestidad sobre el histórico: los cambios de nivel solo se registran desde
    que existe `simulacro_nivel_eventos`. Las llamadas anteriores al primer
    evento caen en un tramo marcado `estimado=True` — sabemos cuántas fueron,
    pero no en qué nivel estaba entonces. La vista `por_dificultad` sí es
    retroactiva (la dificultad del guión va en el snapshot de cada llamada).
    """
    # La dificultad vive en el snapshot; la extraemos con un path JSONB para no
    # traernos la transcripción entera de cada llamada.
    dificultad_col = QualityAnalysis.crm_snapshot["_simulacro"]["scenario"]["dificultad"].astext
    rows = (await session.execute(
        select(
            QualityAnalysis.id,
            QualityAnalysis.created_at,
            QualityAnalysis.percent_quality,
            QualityAnalysis.status,
            QualityAnalysis.escenario,
            QualityAnalysis.departamento,
            QualityAnalysis.scores,
            dificultad_col.label("dificultad"),
            _FECHA_LLAMADA.label("fecha_llamada"),
        )
        .where(QualityAnalysis.agente_nombre == nombre)
        .order_by(_FECHA_LLAMADA)
    )).mappings().all()

    llamadas: list[dict[str, Any]] = []
    fechas: list[datetime | None] = []
    por_dif: dict[str, list[float]] = {}
    por_param: dict[str, list[float]] = {}
    notas: list[float] = []
    for r in rows:
        pq = float(r["percent_quality"]) if r["percent_quality"] is not None else None
        # `fecha` es cuándo se hizo la llamada: es lo que ordena la trayectoria
        # y la curva. Usar la de inserción amontonaría las recuperadas en un día.
        f_llamada = r["fecha_llamada"]
        llamadas.append({
            "id": r["id"],
            "fecha": f_llamada.isoformat() if f_llamada else None,
            "escenario": r["escenario"],
            "departamento": r["departamento"],
            "dificultad": r["dificultad"],
            "percent": pq,
            "status": r["status"],
        })
        fechas.append(f_llamada)
        if r["status"] != "done" or pq is None:
            continue
        notas.append(pq)
        if r["dificultad"]:
            por_dif.setdefault(r["dificultad"], []).append(pq)
        for rid, sc in (r["scores"] or {}).items():
            if not isinstance(sc, dict) or not sc.get("applied"):
                continue
            mx, scv = sc.get("max") or 0, sc.get("score")
            if mx and scv is not None:
                por_param.setdefault(rid, []).append(float(scv) / float(mx) * 100.0)

    # ── Tramos: un periodo por cada nivel por el que ha pasado ────────────────
    eventos = (await session.execute(
        select(SimulacroNivelEvento)
        .where(SimulacroNivelEvento.agente_nombre == nombre)
        .order_by(SimulacroNivelEvento.created_at)
    )).scalars().all()

    def _idx_entre(desde: datetime | None, hasta: datetime | None) -> list[int]:
        return [
            i for i, f in enumerate(fechas)
            if f is not None
            and (desde is None or f > desde)
            and (hasta is None or f <= hasta)
        ]

    def _stats(idx: list[int]) -> tuple[int, int, float | None]:
        vals = [llamadas[i]["percent"] for i in idx if llamadas[i]["percent"] is not None]
        return len(idx), len(vals), _avg1(vals)

    def _tramo(
        nivel: str | None, desde: datetime | None, hasta: datetime | None,
        estimado: bool, salida: dict[str, Any] | None,
    ) -> dict[str, Any]:
        n, evaluadas, avg = _stats(_idx_entre(desde, hasta))
        return {
            "nivel": nivel,
            "desde": desde.isoformat() if desde else None,
            "hasta": hasta.isoformat() if hasta else None,
            "llamadas": n,
            "evaluadas": evaluadas,
            "avg_percent": avg,
            "estimado": estimado,
            "inferido": False,
            "salida": salida,
            "en_curso": hasta is None,
        }

    tramos: list[dict[str, Any]] = []
    prev: datetime | None = None
    for i, ev in enumerate(eventos):
        salida = {
            "fecha": ev.created_at.isoformat() if ev.created_at else None,
            "to_nivel": ev.to_nivel,
            "direction": ev.direction,
            "origen": ev.origen,
            "motivo": ev.motivo or "",
            "actor": ev.actor or "",
        }
        # El alta no cierra ningún tramo previo real: abre el historial.
        if i == 0 and ev.from_nivel is None:
            t = _tramo(None, None, ev.created_at, False, salida)
            if t["llamadas"]:
                tramos.append(t)
            prev = ev.created_at
            continue
        tramos.append(_tramo(ev.from_nivel, prev, ev.created_at, prev is None, salida))
        prev = ev.created_at

    comerciales = (await session.execute(
        select(SimulacroComercial).where(SimulacroComercial.nombre == nombre)
    )).scalars().all()
    activa = next((c for c in comerciales if c.activo), comerciales[0] if comerciales else None)
    nivel_actual = eventos[-1].to_nivel if eventos else (activa.nivel if activa else None)
    # Tramo abierto: el nivel de hoy. Si nunca hubo eventos, TODO el historial
    # cae aquí y se marca estimado (no sabemos si antes estuvo en otro nivel).
    tramos.append(_tramo(nivel_actual, prev, None, not eventos, None))

    # Reconstrucción del pasado: antes de la migración 0008 nadie guardaba los
    # cambios de nivel, así que TODO el histórico caería en un único tramo
    # inútil. Pero el sistema asigna a cada agente guiones de SU nivel
    # (_pick_scenario), así que la dificultad del guión de cada llamada es una
    # huella de en qué nivel estaba entonces: cuando la dificultad cambia y se
    # mantiene, ahí hubo un cambio de nivel. Lo derivamos y lo marcamos como
    # inferido — es una reconstrucción, no un registro.
    def _inferir_por_dificultad(tramo: dict[str, Any]) -> list[dict[str, Any]]:
        desde = datetime.fromisoformat(tramo["desde"]) if tramo["desde"] else None
        hasta = datetime.fromisoformat(tramo["hasta"]) if tramo["hasta"] else None
        idx = _idx_entre(desde, hasta)
        # Rachas de llamadas consecutivas con la misma dificultad.
        rachas: list[list[Any]] = []
        huerfanas: list[int] = []  # sin dificultad y aún sin racha a la que pegarse
        for i in idx:
            d = llamadas[i]["dificultad"]
            if not d:  # sin dato → se pega a la racha en curso
                (rachas[-1][1] if rachas else huerfanas).append(i)
                continue
            if rachas and rachas[-1][0] == d:
                rachas[-1][1].append(i)
            else:
                rachas.append([d, [i]])
        if rachas and huerfanas:  # las de cabecera van con la primera racha
            rachas[0][1] = sorted(huerfanas + rachas[0][1])

        # Una racha suelta suele ser ruido (el guión de ese nivel no existía y
        # _pick_scenario cayó en uno aleatorio), no un cambio de nivel real.
        fusionadas: list[list[Any]] = []
        for d, ids in rachas:
            if fusionadas and len(ids) < 2:
                fusionadas[-1][1].extend(ids)
            else:
                fusionadas.append([d, list(ids)])
        # Tras absorber el ruido pueden quedar dos rachas seguidas del MISMO
        # nivel; unirlas o la ficha mostraría un "difícil → difícil" inexistente.
        colapsadas: list[list[Any]] = []
        for d, ids in fusionadas:
            if colapsadas and colapsadas[-1][0] == d:
                colapsadas[-1][1].extend(ids)
            else:
                colapsadas.append([d, list(ids)])
        fusionadas = [[d, sorted(ids)] for d, ids in colapsadas]
        if len(fusionadas) < 2:
            return [tramo]  # un solo nivel detectado: no aporta nada partirlo

        out: list[dict[str, Any]] = []
        for k, (d, ids) in enumerate(fusionadas):
            ultima = k == len(fusionadas) - 1
            siguiente = fusionadas[k + 1] if not ultima else None
            f_ini, f_fin = fechas[ids[0]], fechas[ids[-1]]
            n, evaluadas, avg = _stats(ids)
            salida = None
            if siguiente:
                f_cambio = fechas[siguiente[1][0]]
                orden = _NIVEL_ORDER
                sube = (
                    d in orden and siguiente[0] in orden
                    and orden.index(siguiente[0]) > orden.index(d)
                )
                salida = {
                    "fecha": f_cambio.isoformat() if f_cambio else None,
                    "to_nivel": siguiente[0],
                    "direction": "promote" if sube else "demote",
                    "origen": "inferido",
                    "motivo": "deducido del cambio de dificultad de los guiones",
                    "actor": "",
                }
            out.append({
                "nivel": d,
                "desde": f_ini.isoformat() if f_ini else None,
                "hasta": (None if (ultima and tramo["en_curso"]) else (f_fin.isoformat() if f_fin else None)),
                "llamadas": n,
                "evaluadas": evaluadas,
                "avg_percent": avg,
                "estimado": True,
                "inferido": True,
                "salida": salida if salida else tramo["salida"],
                "en_curso": ultima and tramo["en_curso"],
            })
        return out

    expandidos: list[dict[str, Any]] = []
    for t in tramos:
        expandidos.extend(_inferir_por_dificultad(t) if t["estimado"] and t["llamadas"] else [t])
    tramos = expandidos

    deptos = {d.id: d.nombre for d in (await session.execute(
        select(SimulacroDepartamento)
    )).scalars().all()}
    project = await session.get(QualityProject, settings.simulacros_project_id)
    rule_names = {
        r.get("id"): (r.get("name") or r.get("id")) for r in (project.rules_table or [])
    } if project else {}

    return {
        "agente": nombre,
        "resumen": {
            "total": len(llamadas),
            "evaluados": len(notas),
            "avg_percent": _avg1(notas),
            "nivel_actual": nivel_actual,
            "departamento_activo": (deptos.get(activa.department_id) if activa else None),
            "memberships": [
                {
                    "id": c.id, "department_id": c.department_id,
                    "departamento": deptos.get(c.department_id) or "(sin departamento)",
                    "nivel": c.nivel, "activo": c.activo,
                }
                for c in comerciales
            ],
        },
        "tramos": tramos,
        "eventos": [leveling.evento_to_dict(e) for e in reversed(eventos)],
        "llamadas": llamadas,
        "por_dificultad": [
            {"dificultad": d, "avg_percent": _avg1(v), "count": len(v)}
            for d, v in sorted(
                por_dif.items(),
                key=lambda kv: _NIVEL_ORDER.index(kv[0]) if kv[0] in _NIVEL_ORDER else 9,
            )
        ],
        "por_parametro": sorted(
            ({"id": rid, "name": rule_names.get(rid, rid), "avg_percent": _avg1(v), "count": len(v)}
             for rid, v in por_param.items()),
            key=lambda x: (x["avg_percent"] if x["avg_percent"] is not None else 999),
        ),
    }


@router.get("/{analysis_id}", response_model=AnalysisDetail)
async def get_analysis(analysis_id: str, session: SessionDep) -> QualityAnalysis:
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    return row


class FeedbackIn(BaseModel):
    value: str | None = None  # "up" | "down" | null


@router.post("/{analysis_id}/feedback", dependencies=[Depends(require_role("admin"))])
async def set_feedback(analysis_id: str, data: FeedbackIn, session: SessionDep) -> dict[str, Any]:
    """El admin marca si la EVALUACIÓN fue buena (👍) o mala (👎). Toggle: el mismo
    valor lo quita. Sirve para medir el evaluador y, a futuro, afinar sus prompts."""
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    v = (data.value or "").lower()
    row.admin_feedback = v if v in ("up", "down") else None
    await session.commit()
    return {"ok": True, "admin_feedback": row.admin_feedback}


class ReasignarIn(BaseModel):
    agente_nombre: str = Field(..., min_length=1, max_length=200)


@router.post("/{analysis_id}/reasignar", dependencies=[Depends(require_role("admin"))])
async def reasignar_agente(
    analysis_id: str, data: ReasignarIn, session: SessionDep, user: CurrentUser
) -> dict[str, Any]:
    """Reasigna un simulacro a otro agente.

    La atribución automática (caller ID / anuncio del CRM) falla a veces y la
    llamada aterriza en la persona equivocada. Esto la mueve, deja constancia
    de quién y cuándo en `crm_snapshot._reasignaciones`, y vuelve a evaluar el
    nivel de los DOS agentes implicados (la nota deja de contar para uno y
    empieza a contar para el otro)."""
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    nuevo = (data.agente_nombre or "").strip()
    if not nuevo:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Falta el nombre del agente")
    anterior = row.agente_nombre or ""
    if nuevo == anterior:
        return {"ok": True, "changed": False, "agente_nombre": anterior}

    # Traza en el snapshot (JSONB): hay que reasignar el dict entero para que
    # SQLAlchemy detecte el cambio — mutarlo in-place no se persiste.
    snapshot = dict(row.crm_snapshot or {})
    historial = list(snapshot.get("_reasignaciones") or [])
    historial.append({
        "de": anterior,
        "a": nuevo,
        "fecha": datetime.now(timezone.utc).isoformat(),
        "actor": await actor_label(session, user),
    })
    snapshot["_reasignaciones"] = historial
    row.crm_snapshot = snapshot
    row.agente_nombre = nuevo
    await session.commit()

    # Re-nivelar a ambos: el motor respeta el switch `auto_evaluar` del
    # departamento, así que no fuerza nada que el coordinador haya apagado.
    niveles: dict[str, Any] = {}
    for nombre in filter(None, {anterior, nuevo}):
        try:
            niveles[nombre] = await leveling.evaluate_by_name(session, nombre, auto_trigger=True)
        except Exception as exc:  # noqa: BLE001
            log.warning("reasignar_leveling_failed", agente=nombre, error=str(exc)[:200])
            niveles[nombre] = None

    log.info("simulacro_reasignado", analysis_id=analysis_id, de=anterior, a=nuevo)
    return {
        "ok": True,
        "changed": True,
        "analysis_id": analysis_id,
        "de": anterior,
        "agente_nombre": nuevo,
        "niveles": niveles,
    }


@router.delete("/{analysis_id}", status_code=204, dependencies=[Depends(require_role("admin"))])
async def delete_analysis(analysis_id: str, session: SessionDep) -> None:
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    await session.delete(row)
    await session.commit()


@router.post("/{analysis_id}/redispatch", status_code=202, response_model=AnalysisOut,
             dependencies=[Depends(require_role("admin"))])
async def redispatch_analysis(
    analysis_id: str, session: SessionDep, background: BackgroundTasks, graph=Depends(get_audit_graph),
) -> QualityAnalysis:
    """Re-run the simulacro audit from the stored transcript."""
    row = await session.get(QualityAnalysis, analysis_id)
    if not row:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Analysis not found")
    row.status = "pending"
    row.scores = {}
    row.scores_by_dimension = {}
    row.total_score = None
    row.ideal_score = None
    row.percent_quality = None
    row.feedback_message = None
    row.detailed_report = None
    row.error = None
    snap = row.crm_snapshot or {}
    await session.commit()
    await session.refresh(row)

    from .retell import _evaluador_override_for, _run_simulacro_audit  # local import avoids cycle
    # Resolve the SAME evaluador the webhook would use (department's assigned
    # evaluador, else project default). Without this, redispatch scored with the
    # project rubric and re-introduced params removed from the department evaluador.
    evaluador_override = await _evaluador_override_for(session, snap, row.departamento)
    transcript = snap.get("transcript") or (snap.get("_simulacro") or {}).get("transcript") or ""
    background.add_task(
        _run_simulacro_audit, graph, row.id, row.agente_nombre, row.call_date, transcript, snap,
        evaluador_override,
    )
    return row
