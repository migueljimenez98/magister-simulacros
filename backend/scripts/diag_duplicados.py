"""Diagnóstico (y limpieza opcional) de simulacros DUPLICADOS.

Contexto: el webhook de Retell es idempotente — el id de la evaluación se deriva
del `call_id` (`qa-<sha256(call_id)[:12]>`), así que un reenvío del mismo evento
cae en la MISMA fila. Pero una recuperación manual que inserte por otra vía crea
una fila nueva cada vez, aunque esa llamada ya estuviera en la base de datos. El
resultado son varias evaluaciones de una única llamada real, que inflan el número
de simulacros del agente y pueden disparar el motor de escalado (una bajada de
nivel "porque sí").

Cómo detecta un duplicado, en dos pasadas:
  1. Mismo `call_id` de Retell en más de una fila. Es prueba definitiva: es
     literalmente la misma llamada.
  2. Para filas sin `call_id` (p. ej. cargadas por test-ingest): mismo agente y
     misma transcripción (normalizada). Es la misma conversación dos veces.

Cuál se queda de cada grupo, en este orden:
  status=done > con nota > id canónico del call_id > la más antigua.
El id canónico se prefiere para que un futuro reenvío del webhook siga cayendo
en esa fila en vez de crear otra.

Uso:
    # Solo informe, NO toca nada (empieza siempre por aquí):
    python -m scripts.diag_duplicados

    # Borra las filas sobrantes de cada grupo:
    python -m scripts.diag_duplicados --apply

    # Además, deshace los cambios de nivel registrados desde esa fecha
    # (los que provocó la avalancha de duplicados) y devuelve al agente
    # al nivel que tenía antes:
    python -m scripts.diag_duplicados --apply --eventos-desde 2026-08-03

    # Informe de fechas de un día concreto: contrasta cuándo se INSERTÓ cada
    # fila con cuándo ocurrió la llamada. Sirve cuando no hay duplicados pero
    # sí una avalancha sospechosa en un solo día (típico tras recuperar
    # llamadas antiguas: se insertan hoy y parecen todas de hoy):
    python -m scripts.diag_duplicados --fechas 2026-08-03
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select

from app.core.db import async_session
from app.core.models import QualityAnalysis, SimulacroComercial, SimulacroNivelEvento

_FUTURO = datetime.max.replace(tzinfo=timezone.utc)


def _sim(a: QualityAnalysis) -> dict:
    snap = a.crm_snapshot if isinstance(a.crm_snapshot, dict) else {}
    sim = snap.get("_simulacro")
    return sim if isinstance(sim, dict) else {}


def _call_id(a: QualityAnalysis) -> str:
    return str(_sim(a).get("call_id") or "").strip()


def _canonical_id(call_id: str) -> str:
    return "qa-" + hashlib.sha256(call_id.encode()).hexdigest()[:12] if call_id else ""


def _transcript_key(a: QualityAnalysis) -> str:
    """Huella de la conversación: sirve para cazar duplicados sin call_id.
    Solo se usa con transcripciones con cuerpo real, para no agrupar restos."""
    snap = a.crm_snapshot if isinstance(a.crm_snapshot, dict) else {}
    t = snap.get("transcript") or _sim(a).get("transcript") or ""
    norm = re.sub(r"\s+", " ", str(t)).strip().lower()
    if len(norm) < 80:
        return ""
    return hashlib.sha256(norm.encode()).hexdigest()[:16]


def _created(a: QualityAnalysis) -> datetime:
    return a.created_at or _FUTURO


def _rank(a: QualityAnalysis, canonical: str):
    """Menor = mejor candidata a QUEDARSE."""
    return (
        0 if a.status == "done" else 1,
        0 if a.percent_quality is not None else 1,
        0 if (canonical and a.id == canonical) else 1,
        _created(a),
    )


def _fecha(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "—"


def _grupos(rows: list[QualityAnalysis]) -> list[tuple[str, str, list[QualityAnalysis]]]:
    """[(tipo, clave, filas)] solo con los grupos que tienen más de una fila."""
    por_call: dict[str, list[QualityAnalysis]] = defaultdict(list)
    sin_call: list[QualityAnalysis] = []
    for a in rows:
        cid = _call_id(a)
        if cid:
            por_call[cid].append(a)
        else:
            sin_call.append(a)

    grupos: list[tuple[str, str, list[QualityAnalysis]]] = [
        ("call_id", cid, filas) for cid, filas in por_call.items() if len(filas) > 1
    ]

    por_texto: dict[tuple[str, str], list[QualityAnalysis]] = defaultdict(list)
    for a in sin_call:
        key = _transcript_key(a)
        if key:
            por_texto[(a.agente_nombre or "", key)].append(a)
    grupos += [
        ("transcripcion", f"{ag} · {k}", filas)
        for (ag, k), filas in por_texto.items() if len(filas) > 1
    ]
    return grupos


async def _informe_distribucion(rows: list[QualityAnalysis]) -> None:
    """Simulacros por agente y día, contados de las DOS formas.

    - Por fecha de llamada (`call_date`): la realidad, y lo que usan el panel,
      las estadísticas y el motor de escalado.
    - Por fecha de inserción (`created_at`): cuándo entró la fila. Un pico aquí
      que no existe en la columna de la izquierda es una recuperación de
      llamadas antiguas — normal, no un problema.

    Si las dos columnas coinciden en todo, es que cada llamada se evaluó el día
    que ocurrió y nunca hubo recuperaciones."""
    por_llamada: dict[tuple[str, str], int] = defaultdict(int)
    por_insercion: dict[tuple[str, str], int] = defaultdict(int)
    for a in rows:
        ag = a.agente_nombre or "(sin agente)"
        f_real = a.call_date or a.created_at
        por_llamada[(ag, f_real.date().isoformat() if f_real else "—")] += 1
        por_insercion[(ag, a.created_at.date().isoformat() if a.created_at else "—")] += 1

    claves = sorted(set(por_llamada) | set(por_insercion), key=lambda k: (k[1], k[0]))
    print("\n[SIMULACROS POR AGENTE Y DÍA]")
    print(f"  {'día':<12} {'agente':<26} {'por llamada':>12} {'por inserción':>14}")
    for ag, dia in claves:
        n_real, n_ins = por_llamada.get((ag, dia), 0), por_insercion.get((ag, dia), 0)
        if n_real < 5 and n_ins < 5:
            continue
        marca = "   <-- recuperadas" if n_ins - n_real >= 5 else ""
        print(f"  {dia:<12} {ag:<26} {n_real:>12} {n_ins:>14}{marca}")
    desfase = sum(
        1 for a in rows
        if a.call_date and a.created_at
        and a.call_date.date() != a.created_at.date()
    )
    print(f"\n  Evaluadas en un día distinto al de la llamada: {desfase}/{len(rows)}")
    if desfase:
        print("  -> Son las recuperadas. El panel y el escalado las cuentan en su día real;")
        print("     la columna 'por inserción' seguirá mostrándolas juntas, y es correcto.")


async def _informe_fechas(rows: list[QualityAnalysis], dia: str) -> None:
    """Contrasta CUÁNDO se insertó la fila con cuándo ocurrió la llamada.

    `created_at` es la hora de inserción. Si una recuperación mete hoy llamadas
    de días pasados, todas quedan fechadas hoy: parecen una avalancha y el motor
    de escalado (que mira los últimos N tests por esa fecha) se dispara con
    datos que no son de hoy. Aquí se ve si es eso lo que pasó y, sobre todo, qué
    campos del snapshot permitirían recuperar la fecha real."""
    sel = [a for a in rows if a.created_at and a.created_at.date().isoformat() == dia]
    print(f"\n[FECHAS · insertadas el {dia}] {len(sel)} evaluaciones")
    if not sel:
        return
    claves: set[str] = set()
    for a in sel:
        claves |= set(_sim(a).keys())
    print(f"  campos disponibles en el snapshot: {sorted(claves)}")
    marcas = [k for k in sorted(claves) if "time" in k.lower() or "date" in k.lower()]
    print(f"  campos con pinta de fecha: {marcas or 'NINGUNO — la hora real no está guardada'}")
    print(f"\n  {'insertada':<17} {'call_date':<17} {'nota':>5}  {'call_id':<24} agente")
    for a in sorted(sel, key=_created)[:40]:
        print(f"  {_fecha(a.created_at):<17} {_fecha(a.call_date):<17} "
              f"{str(a.percent_quality or '—'):>5}  {(_call_id(a) or '—')[:24]:<24} {a.agente_nombre}")
    if len(sel) > 40:
        print(f"  … y {len(sel) - 40} más")
    iguales = sum(
        1 for a in sel
        if a.call_date and a.created_at and abs((a.call_date - a.created_at).total_seconds()) < 120
    )
    print(f"\n  call_date coincide con la inserción en {iguales}/{len(sel)} filas.")
    if iguales == len(sel):
        print("  -> La hora real de la llamada NO se guardó: se selló la de inserción.")
        print("     Para recolocarlas hace falta el volcado de Retell (start_timestamp por call_id).")


async def main(apply: bool, eventos_desde: str | None, dia_fechas: str | None) -> None:
    print(f"\n=== Duplicados de simulacros — modo: {'APLICAR CAMBIOS' if apply else 'solo informe'} ===")

    async with async_session() as s:
        rows = (await s.execute(
            select(QualityAnalysis).order_by(QualityAnalysis.created_at)
        )).scalars().all()
        print(f"\n[TOTAL] evaluaciones en la base de datos: {len(rows)}")

        grupos = _grupos(list(rows))
        sobrantes: list[QualityAnalysis] = []
        por_agente: dict[str, int] = defaultdict(int)

        print(f"\n[GRUPOS DUPLICADOS] {len(grupos)}")
        for tipo, clave, filas in sorted(grupos, key=lambda g: len(g[2]), reverse=True):
            canonical = _canonical_id(clave) if tipo == "call_id" else ""
            filas = sorted(filas, key=lambda a: _rank(a, canonical))
            queda, fuera = filas[0], filas[1:]
            sobrantes.extend(fuera)
            for a in fuera:
                por_agente[a.agente_nombre or "(sin agente)"] += 1
            print(f"\n  [{tipo}] {clave}  ({len(filas)} filas)")
            print(f"    QUEDA  {queda.id}  {_fecha(queda.created_at)}  {queda.status:<8} "
                  f"nota={queda.percent_quality}  agente={queda.agente_nombre!r}")
            for a in fuera:
                print(f"    borrar {a.id}  {_fecha(a.created_at)}  {a.status:<8} "
                      f"nota={a.percent_quality}  agente={a.agente_nombre!r}")

        print(f"\n[RESUMEN] filas sobrantes a borrar: {len(sobrantes)} "
              f"→ quedarían {len(rows) - len(sobrantes)} evaluaciones")
        for ag, n in sorted(por_agente.items(), key=lambda kv: -kv[1]):
            print(f"    {ag:<28} -{n}")

        await _informe_distribucion(list(rows))
        if dia_fechas:
            await _informe_fechas(list(rows), dia_fechas)

        # Cambios de nivel recientes: aquí se ve si la avalancha disparó el motor.
        evs = (await s.execute(
            select(SimulacroNivelEvento).order_by(SimulacroNivelEvento.created_at.desc()).limit(20)
        )).scalars().all()
        print(f"\n[ÚLTIMOS CAMBIOS DE NIVEL] {len(evs)}")
        for e in evs:
            print(f"  {_fecha(e.created_at)}  {e.agente_nombre:<24} "
                  f"{e.from_nivel or '—'} → {e.to_nivel:<8} {e.origen:<7} "
                  f"llamadas_en_nivel={e.llamadas_en_nivel}  {(e.motivo or '')[:60]}")
        if not evs:
            print("  (ninguno registrado)")

        if not apply:
            print("\n(Solo informe: NO se ha modificado nada.")
            print(" Revisa los grupos de arriba y, si cuadran, repite con --apply.)")
            return

        for a in sobrantes:
            await s.delete(a)
        print(f"\n*** BORRADAS {len(sobrantes)} evaluaciones duplicadas ***")

        if eventos_desde:
            corte = datetime.fromisoformat(eventos_desde).replace(tzinfo=timezone.utc)
            malos = (await s.execute(
                select(SimulacroNivelEvento)
                .where(SimulacroNivelEvento.created_at >= corte)
                .order_by(SimulacroNivelEvento.created_at)
            )).scalars().all()
            # Deshacer = devolver a cada ficha el nivel que tenía ANTES del
            # primer cambio anulado. Basta con el `from_nivel` del más antiguo.
            primero: dict[str, SimulacroNivelEvento] = {}
            for e in malos:
                if e.comercial_id and e.comercial_id not in primero:
                    primero[e.comercial_id] = e
            for cid, e in primero.items():
                c = await s.get(SimulacroComercial, cid)
                if c and e.from_nivel:
                    print(f"    {c.nombre}: nivel {c.nivel} → {e.from_nivel} (deshecho)")
                    c.nivel = e.from_nivel
            for e in malos:
                await s.delete(e)
            print(f"*** BORRADOS {len(malos)} cambios de nivel desde {eventos_desde} ***")

        await s.commit()
        print("\n*** Cambios GUARDADOS. ***")
        print("Repasa el panel: Agentes → Ver evolución del agente afectado.")


def _valor(args: list[str], flag: str) -> str | None:
    if flag not in args:
        return None
    i = args.index(flag)
    return args[i + 1] if i + 1 < len(args) and not args[i + 1].startswith("--") else None


if __name__ == "__main__":
    args = sys.argv[1:]
    asyncio.run(main(
        "--apply" in args,
        _valor(args, "--eventos-desde"),
        _valor(args, "--fechas"),
    ))
