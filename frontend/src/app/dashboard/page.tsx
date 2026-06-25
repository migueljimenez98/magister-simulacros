"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { api, type Stats } from "@/lib/api";

const DIFF_COLOR: Record<string, string> = {
  facil: "text-emerald-300 border-emerald-700 bg-emerald-900/30",
  medio: "text-amber-300 border-amber-700 bg-amber-900/30",
  dificil: "text-rose-300 border-rose-700 bg-rose-900/30",
};

function scoreColor(v: number | null | undefined): string {
  if (v == null) return "text-muted";
  if (v >= 80) return "text-emerald-300";
  if (v >= 50) return "text-amber-300";
  return "text-rose-300";
}
function barColor(v: number | null | undefined): string {
  if (v == null) return "bg-zinc-600";
  if (v >= 80) return "bg-emerald-500";
  if (v >= 50) return "bg-amber-500";
  return "bg-rose-500";
}
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);

export default function DashboardPage() {
  const [departamento, setDepartamento] = useState("");
  const [agente, setAgente] = useState("");

  // Opciones de filtro (sin filtrar) — para que los desplegables no se vacíen.
  const { data: opts } = useQuery({ queryKey: ["stats-opts"], queryFn: () => api.analyses.stats() });
  // Datos del panel (con filtros).
  const { data, isLoading } = useQuery({
    queryKey: ["stats", departamento, agente],
    queryFn: () => api.analyses.stats({ departamento: departamento || undefined, agente: agente || undefined }),
  });

  return (
    <div className="space-y-6 max-w-[1300px] mx-auto">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold">Dashboard</h2>
          <p className="text-sm text-muted">Progreso de los comerciales en los simulacros.</p>
        </div>
        <div className="flex gap-2">
          <select
            value={departamento}
            onChange={(e) => { setDepartamento(e.target.value); setAgente(""); }}
            className="text-sm bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">Todos los departamentos</option>
            {(opts?.departamentos ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          <select
            value={agente}
            onChange={(e) => setAgente(e.target.value)}
            className="text-sm bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">Todos los comerciales</option>
            {(opts?.agentes ?? []).map((a) => <option key={a} value={a}>{a}</option>)}
          </select>
        </div>
      </div>

      {isLoading || !data ? (
        <p className="text-muted">Cargando…</p>
      ) : data.scored === 0 ? (
        <p className="text-muted">
          Aún no hay simulacros puntuados con estos filtros. Cuando se evalúen llamadas, verás aquí el progreso.
        </p>
      ) : (
        <Content data={data} />
      )}
    </div>
  );
}

function Content({ data }: { data: Stats }) {
  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi label="Nota media" value={pct(data.avg_percent)} valueClass={scoreColor(data.avg_percent)} />
        <Kpi label="Llamadas evaluadas" value={String(data.scored)} sub={`${data.total} en total`} />
        <Kpi label="Comerciales" value={String(data.por_agente.length)} />
        <Kpi
          label="Mejor comercial"
          value={data.por_agente[0]?.agente ?? "—"}
          sub={data.por_agente[0] ? pct(data.por_agente[0].avg_percent) : ""}
          small
        />
      </div>

      {/* Progreso temporal */}
      <Card title="Progreso (nota media por día)">
        <LineChart points={data.timeseries.map((t) => ({ x: t.date, y: t.avg_percent }))} />
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* Parámetros más fallados */}
        <Card title="Temas más fallados" subtitle="Parámetros de la rúbrica con peor nota media">
          {data.por_parametro.length === 0 ? (
            <p className="text-sm text-muted">Sin datos.</p>
          ) : (
            <div className="space-y-2">
              {data.por_parametro.slice(0, 8).map((p) => (
                <BarRow key={p.id} label={p.name} value={p.avg_percent} count={p.count} />
              ))}
            </div>
          )}
        </Card>

        {/* Nota por dificultad */}
        <Card title="Nota por dificultad">
          {data.por_dificultad.length === 0 ? (
            <p className="text-sm text-muted">Sin datos.</p>
          ) : (
            <div className="space-y-2">
              {data.por_dificultad.map((d) => (
                <BarRow key={d.dificultad} label={d.dificultad} value={d.avg_percent} count={d.count} />
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Por comercial: nivel actual + recomendado */}
      <Card title="Por comercial" subtitle="Nota media, nivel actual y nivel recomendado">
        <div className="overflow-hidden rounded-xl border border-border">
          <table className="w-full text-sm">
            <thead className="bg-bg/50 text-muted text-left">
              <tr>
                <th className="px-4 py-2 font-medium">Comercial</th>
                <th className="px-4 py-2 font-medium">Llamadas</th>
                <th className="px-4 py-2 font-medium">Nota media</th>
                <th className="px-4 py-2 font-medium">Nivel actual</th>
                <th className="px-4 py-2 font-medium">Recomendado</th>
              </tr>
            </thead>
            <tbody>
              {data.por_agente.map((a) => {
                const subir = a.nivel_actual && a.nivel_recomendado && a.nivel_actual !== a.nivel_recomendado;
                return (
                  <tr key={a.agente} className="border-t border-border">
                    <td className="px-4 py-2">{a.agente}</td>
                    <td className="px-4 py-2 text-muted tabular-nums">{a.count}</td>
                    <td className={`px-4 py-2 font-semibold tabular-nums ${scoreColor(a.avg_percent)}`}>{pct(a.avg_percent)}</td>
                    <td className="px-4 py-2"><NivelBadge nivel={a.nivel_actual} /></td>
                    <td className="px-4 py-2">
                      <NivelBadge nivel={a.nivel_recomendado} />
                      {subir && (
                        <span className="ml-2 text-xs text-muted">
                          {nivelIdx(a.nivel_recomendado) > nivelIdx(a.nivel_actual) ? "↑ subir" : "↓ bajar"}
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

const NIVELES = ["facil", "medio", "dificil"];
const nivelIdx = (n: string | null) => (n ? NIVELES.indexOf(n) : -1);

function NivelBadge({ nivel }: { nivel: string | null }) {
  if (!nivel) return <span className="text-muted">—</span>;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[nivel] ?? "border-border text-muted"}`}>
      {nivel}
    </span>
  );
}

function Kpi({ label, value, sub, valueClass, small }: { label: string; value: string; sub?: string; valueClass?: string; small?: boolean }) {
  return (
    <div className="bg-card border border-border rounded-2xl p-4">
      <p className="text-xs uppercase tracking-wide text-muted">{label}</p>
      <p className={`${small ? "text-lg" : "text-3xl"} font-bold mt-1 ${valueClass ?? ""} truncate`}>{value}</p>
      {sub && <p className="text-xs text-muted mt-0.5">{sub}</p>}
    </div>
  );
}

function Card({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div>
        <h3 className="font-semibold">{title}</h3>
        {subtitle && <p className="text-xs text-muted">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function BarRow({ label, value, count }: { label: string; value: number | null; count: number }) {
  const w = value == null ? 0 : Math.max(2, Math.min(100, value));
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm w-44 shrink-0 truncate" title={label}>{label}</span>
      <div className="flex-1 h-3 rounded-full bg-bg overflow-hidden">
        <div className={`h-full ${barColor(value)}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`text-sm tabular-nums w-12 text-right ${scoreColor(value)}`}>{pct(value)}</span>
      <span className="text-xs text-muted w-10 text-right">n={count}</span>
    </div>
  );
}

// Línea SVG simple (0-100) con la nota media por día.
function LineChart({ points }: { points: { x: string; y: number | null }[] }) {
  const pts = points.filter((p) => p.y != null) as { x: string; y: number }[];
  if (pts.length === 0) return <p className="text-sm text-muted">Sin datos.</p>;
  const W = 720, H = 180, padL = 32, padB = 20, padT = 10, padR = 10;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = pts.length;
  const x = (i: number) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => padT + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 480 }}>
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke="currentColor" className="text-border" strokeWidth={1} />
            <text x={4} y={y(g) + 3} className="fill-current text-muted" fontSize={10}>{g}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="currentColor" className="text-accent" strokeWidth={2} />
        {pts.map((p, i) => (
          <circle key={i} cx={x(i)} cy={y(p.y)} r={3} className="fill-current text-accent" />
        ))}
        {pts.map((p, i) => (
          (i === 0 || i === n - 1 || n <= 6) && (
            <text key={`t${i}`} x={x(i)} y={H - 6} textAnchor="middle" className="fill-current text-muted" fontSize={9}>
              {p.x.slice(5)}
            </text>
          )
        ))}
      </svg>
    </div>
  );
}
