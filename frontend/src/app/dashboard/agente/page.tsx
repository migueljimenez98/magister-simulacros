"use client";

/**
 * Ficha del agente — su evolución completa en una pantalla.
 *
 * Responde a: cuántos simulacros lleva, en qué nivel los hizo, cómo ha ido
 * avanzando y en qué falla. Todo sale de /api/analyses/agente/{nombre}/evolucion
 * (una sola llamada) para que las cifras de las distintas secciones no puedan
 * contradecirse entre sí.
 */

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type AgenteEvolucion, type LlamadaAgente, type TramoNivel } from "@/lib/api";
import { nota10, notaHsl } from "@/lib/score";

const DIFF_COLOR: Record<string, string> = {
  facil: "text-emerald-300 border-emerald-700 bg-emerald-900/30",
  medio: "text-amber-300 border-amber-700 bg-amber-900/30",
  dificil: "text-rose-300 border-rose-700 bg-rose-900/30",
};
const ORIGEN_LABEL: Record<string, string> = {
  auto: "regla automática",
  manual: "cambio manual",
  alta: "alta",
};
const fdate = (s: string | null | undefined) =>
  s ? new Date(s).toLocaleDateString("es-ES", { day: "2-digit", month: "short", year: "numeric" }) : "—";

function Nota({ v }: { v: number | null | undefined }) {
  return <span className="tabular-nums font-semibold" style={{ color: notaHsl(v) }}>{nota10(v)}</span>;
}

function NivelBadge({ nivel }: { nivel: string | null }) {
  if (!nivel) return <span className="text-muted text-xs">sin registrar</span>;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[nivel] ?? "border-border text-muted"}`}>
      {nivel}
    </span>
  );
}

export default function AgentePage() {
  return (
    <Suspense fallback={<p className="text-muted">Cargando…</p>}>
      <Inner />
    </Suspense>
  );
}

function Inner() {
  const nombre = useSearchParams()?.get("nombre") || "";
  const { data, isLoading } = useQuery({
    queryKey: ["agente-evolucion", nombre],
    queryFn: () => api.analyses.evolucion(nombre),
    enabled: Boolean(nombre),
  });

  if (!nombre) return <p className="text-rose-400">Falta el parámetro ?nombre=</p>;
  if (isLoading || !data) return <p className="text-muted">Cargando…</p>;

  const { resumen, tramos, llamadas } = data;
  const enCurso = tramos.find((t) => t.en_curso);

  return (
    <div className="w-full space-y-5">
      <div className="flex items-center gap-3 flex-wrap">
        <Link href="/dashboard" className="text-sm text-muted hover:text-white">← Agentes</Link>
        <h2 className="text-xl font-semibold">{data.agente}</h2>
        {resumen.memberships.map((m) => (
          <span key={m.id} className={`text-xs px-2 py-0.5 rounded-full border ${m.activo ? "border-accent text-white" : "border-border text-muted opacity-70"}`}>
            {m.departamento} · {m.nivel ?? "—"}
          </span>
        ))}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Simulacros" value={String(resumen.total)} hint={`${resumen.evaluados} con nota`} />
        <Kpi label="Nota media" value={nota10(resumen.avg_percent)} hint="sobre 10" color={notaHsl(resumen.avg_percent)} />
        <Kpi label="Nivel actual" value={resumen.nivel_actual ?? "—"} hint={resumen.departamento_activo ?? "sin departamento"} />
        <Kpi
          label="En este nivel"
          value={enCurso ? String(enCurso.llamadas) : "0"}
          hint={enCurso?.desde ? `desde ${fdate(enCurso.desde)}` : "sin cambios registrados"}
        />
      </div>

      <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
        <div>
          <h3 className="font-semibold">Trayectoria por nivel</h3>
          <p className="text-xs text-muted">
            Cuántos simulacros hizo en cada nivel y cómo salió de él.
          </p>
        </div>
        <div className="space-y-2">
          {[...tramos].reverse().map((t, i) => <TramoRow key={i} t={t} />)}
        </div>
      </section>

      <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
        <div>
          <h3 className="font-semibold">Evolución</h3>
          <p className="text-xs text-muted">
            Nota de cada simulacro en orden cronológico. Las líneas verticales marcan los cambios de nivel.
          </p>
        </div>
        <Evolucion llamadas={llamadas} tramos={tramos} />
      </section>

      <div className="grid gap-5 lg:grid-cols-2">
        <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
          <div>
            <h3 className="font-semibold">Nota por dificultad del guión</h3>
            <p className="text-xs text-muted">Incluye todo su histórico, también el anterior al registro de niveles.</p>
          </div>
          {!data.por_dificultad.length ? <p className="text-sm text-muted">Sin datos.</p> : (
            <div className="space-y-2">
              {data.por_dificultad.map((d) => (
                <BarRow key={d.dificultad} label={d.dificultad} value={d.avg_percent} count={d.count} />
              ))}
            </div>
          )}
        </section>

        <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
          <div>
            <h3 className="font-semibold">En qué falla</h3>
            <p className="text-xs text-muted">Sus parámetros con peor nota media.</p>
          </div>
          {!data.por_parametro.length ? <p className="text-sm text-muted">Sin datos.</p> : (
            <div className="space-y-2">
              {data.por_parametro.slice(0, 8).map((p) => (
                <BarRow key={p.id} label={p.name} value={p.avg_percent} count={p.count} />
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="bg-card border border-border rounded-2xl overflow-hidden">
        <div className="px-4 py-3 border-b border-border">
          <h3 className="font-semibold">Todos sus simulacros</h3>
        </div>
        {!llamadas.length ? (
          <p className="text-sm text-muted px-4 py-3">Todavía no ha hecho ninguno.</p>
        ) : (
          <div className="overflow-x-auto max-h-[26rem] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg/50 text-muted text-left sticky top-0">
                <tr>
                  <th className="px-4 py-2 font-medium">Fecha</th>
                  <th className="px-4 py-2 font-medium">Personalidad</th>
                  <th className="px-4 py-2 font-medium">Dificultad</th>
                  <th className="px-4 py-2 font-medium">Departamento</th>
                  <th className="px-4 py-2 font-medium">Nota</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {[...llamadas].reverse().map((c) => (
                  <tr key={c.id} className="border-t border-border hover:bg-bg/40">
                    <td className="px-4 py-2 text-muted whitespace-nowrap">
                      {c.fecha ? new Date(c.fecha).toLocaleString("es-ES") : "—"}
                    </td>
                    <td className="px-4 py-2 text-muted truncate max-w-[220px]">{c.escenario || "—"}</td>
                    <td className="px-4 py-2"><NivelBadge nivel={c.dificultad} /></td>
                    <td className="px-4 py-2 text-muted whitespace-nowrap">{c.departamento || "—"}</td>
                    <td className="px-4 py-2">
                      {c.status === "done" ? <Nota v={c.percent} /> : <span className="text-muted text-xs">{c.status}</span>}
                    </td>
                    <td className="px-4 py-2 text-right">
                      <Link href={`/dashboard/detail?id=${c.id}`} className="text-accent hover:underline whitespace-nowrap">Ver</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Kpi({ label, value, hint, color }: { label: string; value: string; hint?: string; color?: string }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4">
      <p className="text-xs text-muted">{label}</p>
      <p className="text-2xl font-semibold tabular-nums" style={color ? { color } : undefined}>{value}</p>
      {hint && <p className="text-xs text-muted mt-0.5">{hint}</p>}
    </div>
  );
}

function TramoRow({ t }: { t: TramoNivel }) {
  const s = t.salida;
  const flecha = s?.direction === "demote" ? "bajó a" : "subió a";
  return (
    <div className="rounded-xl border border-border bg-bg/40 px-3 py-2 text-sm flex flex-wrap items-center gap-x-3 gap-y-1">
      <NivelBadge nivel={t.nivel} />
      {t.en_curso && <span className="text-xs text-accent">actual</span>}
      <span className="text-muted">
        <strong className="text-white tabular-nums">{t.llamadas}</strong> simulacro{t.llamadas === 1 ? "" : "s"}
      </span>
      <span className="text-muted">· media <Nota v={t.avg_percent} /></span>
      <span className="text-muted text-xs">
        · {fdate(t.desde) === "—" ? "desde el principio" : fdate(t.desde)} → {t.en_curso ? "hoy" : fdate(t.hasta)}
      </span>
      {t.estimado && (
        <span
          className="text-xs text-amber-300/80"
          title="Periodo anterior al registro de cambios de nivel: el recuento de simulacros es exacto, pero pudo haber estado en otro nivel durante parte de ese tiempo."
        >
          · anterior al registro
        </span>
      )}
      {s && (
        <span className="text-xs text-muted ml-auto">
          {flecha} <strong className="text-white">{s.to_nivel}</strong> ({ORIGEN_LABEL[s.origen] ?? s.origen})
        </span>
      )}
    </div>
  );
}

// Curva de notas por simulacro + marcas verticales en los cambios de nivel.
function Evolucion({ llamadas, tramos }: { llamadas: LlamadaAgente[]; tramos: TramoNivel[] }) {
  const pts = llamadas.filter((c) => c.status === "done" && c.percent != null) as (LlamadaAgente & { percent: number })[];
  if (pts.length < 1) return <p className="text-sm text-muted">Aún no hay simulacros evaluados.</p>;

  const W = 760, H = 200, padL = 28, padB = 22, padT = 10, padR = 10;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = pts.length;
  const x = (i: number) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => padT + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.percent).toFixed(1)}`).join(" ");

  // Cada cambio de nivel se coloca entre la última llamada anterior al cambio
  // y la primera posterior, para que la marca caiga donde de verdad ocurrió.
  const marcas = tramos
    .filter((t) => t.salida?.fecha)
    .map((t) => {
      const corte = new Date(t.salida!.fecha!).getTime();
      const anteriores = pts.filter((p) => p.fecha && new Date(p.fecha).getTime() <= corte).length;
      return { i: anteriores - 0.5, nivel: t.salida!.to_nivel };
    })
    .filter((m) => m.i > 0 && m.i < n - 0.5);

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 320 }}>
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke="currentColor" className="text-border" strokeWidth={1} />
            <text x={2} y={y(g) + 3} className="fill-current text-muted" fontSize={9}>{g / 10}</text>
          </g>
        ))}
        {marcas.map((m, k) => (
          <g key={`m${k}`}>
            <line
              x1={x(m.i)} x2={x(m.i)} y1={padT} y2={padT + innerH}
              stroke="currentColor" className="text-accent" strokeWidth={1} strokeDasharray="3 3" opacity={0.7}
            />
            <text x={x(m.i) + 3} y={padT + 9} className="fill-current text-accent" fontSize={9}>→ {m.nivel}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="currentColor" className="text-accent" strokeWidth={2} />
        {pts.map((p, i) => (
          <circle key={p.id} cx={x(i)} cy={y(p.percent)} r={3} style={{ fill: notaHsl(p.percent) }}>
            <title>{`${p.fecha ? new Date(p.fecha).toLocaleString("es-ES") : ""} · ${nota10(p.percent)}/10${p.escenario ? ` · ${p.escenario}` : ""}`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
}

function BarRow({ label, value, count }: { label: string; value: number | null; count: number }) {
  const w = value == null ? 0 : Math.max(2, Math.min(100, value));
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm w-40 shrink-0 truncate" title={label}>{label}</span>
      <div className="flex-1 h-3 rounded-full bg-bg overflow-hidden">
        <div className="h-full" style={{ width: `${w}%`, backgroundColor: notaHsl(value) }} />
      </div>
      <span className="text-sm tabular-nums w-9 text-right" style={{ color: notaHsl(value) }}>{nota10(value)}</span>
      <span className="text-xs text-muted w-9 text-right">n={count}</span>
    </div>
  );
}
