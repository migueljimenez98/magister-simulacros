"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api, simulacrosApi,
  type AgenteRow, type Departamento, type ParamScore,
} from "@/lib/api";
import { nota10, notaHsl } from "@/lib/score";

const NIVELES = ["facil", "medio", "dificil"] as const;
const DIFF_COLOR: Record<string, string> = {
  facil: "text-emerald-300 border-emerald-700 bg-emerald-900/30",
  medio: "text-amber-300 border-amber-700 bg-amber-900/30",
  dificil: "text-rose-300 border-rose-700 bg-rose-900/30",
};
// Borde por nivel: facil verde · medio amarillo · dificil rojo.
const NIVEL_BORDER: Record<string, string> = {
  facil: "border-emerald-500",
  medio: "border-amber-500",
  dificil: "border-rose-500",
};
const fdate = (s: string | null) => (s ? new Date(s).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" }) : "—");
const nivelIdx = (n: string | null) => (n ? NIVELES.indexOf(n as (typeof NIVELES)[number]) : -1);

// Celda de nota sobre 10 con color gradiente.
function Nota({ v, className = "" }: { v: number | null | undefined; className?: string }) {
  return <span className={`tabular-nums font-semibold ${className}`} style={{ color: notaHsl(v) }}>{nota10(v)}</span>;
}

export default function AgentesDashboard() {
  const qc = useQueryClient();
  const [departamento, setDepartamento] = useState("");
  const [detalle, setDetalle] = useState<AgenteRow | null>(null);
  const [nuevo, setNuevo] = useState(false);

  const { data: opts } = useQuery({ queryKey: ["stats-opts"], queryFn: () => api.analyses.stats() });
  const { data, isLoading } = useQuery({
    queryKey: ["stats", departamento],
    queryFn: () => api.analyses.stats({ departamento: departamento || undefined }),
  });
  const { data: departamentos } = useQuery({ queryKey: ["sim-departamentos"], queryFn: simulacrosApi.listDepartamentos });
  const invalidate = () => qc.invalidateQueries({ queryKey: ["stats"] });

  return (
    <div className="w-full space-y-5">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4 flex-wrap">
          <h2 className="text-xl font-semibold">Agentes</h2>
          <select
            value={departamento}
            onChange={(e) => setDepartamento(e.target.value)}
            className="text-sm bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">Todos los departamentos</option>
            {(opts?.departamentos ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
          {data && (
            <div className="flex items-center gap-4 text-sm">
              <span className="text-muted">Nota media: <strong style={{ color: notaHsl(data.avg_percent) }}>{nota10(data.avg_percent)}</strong> <span className="text-xs">/10</span></span>
              <span className="text-muted">Llamadas: <strong className="text-white">{data.total}</strong></span>
            </div>
          )}
        </div>
        <button
          onClick={() => setNuevo(true)}
          className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90"
        >
          + Nuevo agente
        </button>
      </div>

      {isLoading || !data ? (
        <p className="text-muted">Cargando…</p>
      ) : data.por_agente.length === 0 ? (
        <PrimerosPasos hayDatos={data.total > 0} />
      ) : (
        <>
          <div className="bg-card border border-border rounded-2xl overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg/50 text-muted text-left">
                <tr>
                  <th className="px-4 py-2 font-medium">Agente</th>
                  <th className="px-4 py-2 font-medium">Departamentos (nivel)</th>
                  <th className="px-4 py-2 font-medium">Último simulacro</th>
                  <th className="px-4 py-2 font-medium">Nota última</th>
                  <th className="px-4 py-2 font-medium">Nº</th>
                  <th className="px-4 py-2 font-medium">Nota media</th>
                  <th className="px-4 py-2 font-medium">Recomendado</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {data.por_agente.map((a) => {
                  const cambia = a.nivel_actual && a.nivel_recomendado && a.nivel_actual !== a.nivel_recomendado;
                  return (
                    <tr key={a.agente} className="border-t border-border hover:bg-bg/40">
                      <td className="px-4 py-2 font-medium">{a.agente}</td>
                      <td className="px-4 py-2"><DeptChips memberships={a.memberships} /></td>
                      <td className="px-4 py-2 text-muted whitespace-nowrap">{fdate(a.ultima_fecha)}{a.ultimo_departamento ? <span className="text-xs"> · {a.ultimo_departamento}</span> : ""}</td>
                      <td className="px-4 py-2"><Nota v={a.ultima_nota} /></td>
                      <td className="px-4 py-2 text-muted tabular-nums">{a.count}</td>
                      <td className="px-4 py-2"><Nota v={a.avg_percent} /></td>
                      <td className="px-4 py-2">
                        <NivelBadge nivel={a.nivel_recomendado} />
                        {cambia && <span className="ml-1 text-xs text-muted">{nivelIdx(a.nivel_recomendado) > nivelIdx(a.nivel_actual) ? "↑" : "↓"}</span>}
                      </td>
                      <td className="px-4 py-2 text-right">
                        <button onClick={() => setDetalle(a)} className="text-accent hover:underline whitespace-nowrap">Ver detalles</button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          <div className="grid gap-5 lg:grid-cols-3">
            <StatCard title="Temas más fallados" subtitle="Parámetros con peor nota media">
              {data.por_parametro.length === 0 ? <p className="text-sm text-muted">Sin datos.</p> : (
                <div className="space-y-2">
                  {data.por_parametro.slice(0, 8).map((p) => <BarRow key={p.id} label={p.name} value={p.avg_percent} count={p.count} />)}
                </div>
              )}
            </StatCard>
            <StatCard title="Nota por dificultad">
              {data.por_dificultad.length === 0 ? <p className="text-sm text-muted">Sin datos.</p> : (
                <div className="space-y-2">
                  {data.por_dificultad.map((d) => <BarRow key={d.dificultad} label={d.dificultad} value={d.avg_percent} count={d.count} />)}
                </div>
              )}
            </StatCard>
            <StatCard title="Progreso" subtitle="Nota media por día">
              <LineChart points={data.timeseries.map((t) => ({ x: t.date, y: t.avg_percent }))} />
            </StatCard>
          </div>
        </>
      )}

      {detalle && (
        <AgenteDetailModal
          agente={detalle}
          departamentos={departamentos ?? []}
          onClose={() => setDetalle(null)}
          onChanged={() => { invalidate(); }}
        />
      )}
      {nuevo && (
        <NuevoAgenteModal
          departamentos={departamentos ?? []}
          existentes={(data?.agentes ?? [])}
          onClose={() => setNuevo(false)}
          onSaved={() => { setNuevo(false); invalidate(); }}
        />
      )}
    </div>
  );
}

function NivelBadge({ nivel }: { nivel: string | null }) {
  if (!nivel) return <span className="text-muted">—</span>;
  return <span className={`text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[nivel] ?? "border-border text-muted"}`}>{nivel}</span>;
}

function DeptChips({ memberships }: { memberships: AgenteRow["memberships"] }) {
  if (!memberships.length) return <span className="text-rose-400 text-xs">sin departamento</span>;
  return (
    <div className="flex flex-wrap gap-1">
      {memberships.map((m) => {
        const ring = NIVEL_BORDER[m.nivel ?? ""] ?? "border-border";
        return (
          <span
            key={m.id}
            title={`${m.nivel ?? "—"} · ${m.activo ? "activo" : "inactivo"}`}
            className={`text-xs px-2 py-0.5 rounded-full whitespace-nowrap ${ring} ${m.activo ? "border-2 text-white font-medium" : "border text-muted opacity-70"}`}
          >
            {m.departamento} · {m.nivel ?? "—"}
          </span>
        );
      })}
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

function StatCard({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
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

// Línea SVG (0-10) con la nota media por día.
function LineChart({ points }: { points: { x: string; y: number | null }[] }) {
  const pts = points.filter((p) => p.y != null) as { x: string; y: number }[];
  if (pts.length === 0) return <p className="text-sm text-muted">Sin datos.</p>;
  const W = 380, H = 150, padL = 24, padB = 18, padT = 8, padR = 8;
  const innerW = W - padL - padR, innerH = H - padT - padB;
  const n = pts.length;
  const x = (i: number) => padL + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW);
  const y = (v: number) => padT + innerH - (Math.max(0, Math.min(100, v)) / 100) * innerH;
  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(p.y).toFixed(1)}`).join(" ");
  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 280 }}>
        {[0, 50, 100].map((g) => (
          <g key={g}>
            <line x1={padL} x2={W - padR} y1={y(g)} y2={y(g)} stroke="currentColor" className="text-border" strokeWidth={1} />
            <text x={2} y={y(g) + 3} className="fill-current text-muted" fontSize={9}>{g / 10}</text>
          </g>
        ))}
        <path d={path} fill="none" stroke="currentColor" className="text-accent" strokeWidth={2} />
        {pts.map((p, i) => <circle key={i} cx={x(i)} cy={y(p.y)} r={3} style={{ fill: notaHsl(p.y) }} />)}
        {pts.map((p, i) => (i === 0 || i === n - 1 || n <= 6) && (
          <text key={`t${i}`} x={x(i)} y={H - 5} textAnchor="middle" className="fill-current text-muted" fontSize={8}>{p.x.slice(5)}</text>
        ))}
      </svg>
    </div>
  );
}

// ─── Detalle del agente (modal): membresías + historial ──────────────────────

function AgenteDetailModal({
  agente, departamentos, onClose, onChanged,
}: {
  agente: AgenteRow;
  departamentos: Departamento[];
  onClose: () => void;
  onChanged: () => void;
}) {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [verCall, setVerCall] = useState<string | null>(null);
  const { data: historial } = useQuery({
    queryKey: ["agente-historial", agente.agente],
    queryFn: () => api.analyses.list({ agente: agente.agente, limit: 50 }),
  });
  const refetchMemb = () => qc.invalidateQueries({ queryKey: ["sim-comerciales"] });
  const after = () => { onChanged(); refetchMemb(); };

  const usados = new Set(agente.memberships.map((m) => m.department_id));
  const disponibles = departamentos.filter((d) => !usados.has(d.id));

  return (
    <Modal title={`Agente — ${agente.agente}`} onClose={onClose} wide>
      <div className="grid md:grid-cols-2 gap-6">
        {/* Departamentos / membresías */}
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="font-medium">Departamentos</h4>
            {disponibles.length > 0 && (
              <button onClick={() => setAdding(true)} className="text-sm text-accent hover:underline">+ Añadir</button>
            )}
          </div>
          <div className="space-y-2">
            {agente.memberships.map((m) => (
              <MembershipRow key={m.id} nombre={agente.agente} m={m} onChanged={after} />
            ))}
            {agente.memberships.length === 0 && <p className="text-sm text-muted">Sin departamentos.</p>}
          </div>
          <p className="text-xs text-muted">
            Nivel recomendado:{" "}
            {agente.nivel_recomendado
              ? <span className={agente.nivel_recomendado !== agente.nivel_actual ? "text-amber-300" : ""}>{agente.nivel_recomendado}</span>
              : "—"} (según su nota media {nota10(agente.avg_percent)}/10).
          </p>
          {adding && (
            <AddDeptModal
              nombre={agente.agente}
              disponibles={disponibles}
              onClose={() => setAdding(false)}
              onSaved={() => { setAdding(false); after(); }}
            />
          )}
        </div>

        {/* Historial */}
        <div className="space-y-3">
          <h4 className="font-medium">Historial de simulacros</h4>
          <div className="rounded-xl border border-border overflow-hidden max-h-80 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-bg/50 text-muted text-left sticky top-0">
                <tr>
                  <th className="px-3 py-1.5 font-medium">Fecha</th>
                  <th className="px-3 py-1.5 font-medium">Personalidad</th>
                  <th className="px-3 py-1.5 font-medium">Nota</th>
                  <th className="px-3 py-1.5"></th>
                </tr>
              </thead>
              <tbody>
                {!historial?.items.length ? (
                  <tr><td colSpan={4} className="px-3 py-2 text-muted">Sin simulacros.</td></tr>
                ) : historial.items.map((r) => (
                  <tr key={r.id} className="border-t border-border">
                    <td className="px-3 py-1.5 text-muted whitespace-nowrap">{fdate(r.created_at)}</td>
                    <td className="px-3 py-1.5 text-muted truncate max-w-[160px]">{r.escenario || "—"}</td>
                    <td className="px-3 py-1.5"><Nota v={r.percent_quality} /></td>
                    <td className="px-3 py-1.5 text-right">
                      <button onClick={() => setVerCall(r.id)} className="text-accent hover:underline">Ver</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      {verCall && <CallDetailModal id={verCall} onClose={() => setVerCall(null)} />}
    </Modal>
  );
}

function CallDetailModal({ id, onClose }: { id: string; onClose: () => void }) {
  const { data: a, isLoading } = useQuery({ queryKey: ["analysis-detail", id], queryFn: () => api.analyses.get(id) });
  const snap = (a?.crm_snapshot || {}) as Record<string, unknown>;
  const sim = (snap._simulacro || {}) as Record<string, unknown>;
  const transcript =
    (typeof snap.transcript === "string" && snap.transcript) ||
    (typeof sim.transcript === "string" && sim.transcript) || "";
  const scores = a ? (Object.entries(a.scores || {}) as [string, ParamScore][]) : [];
  return (
    <Modal title={a ? `Simulacro — ${a.agente_nombre}` : "Simulacro"} onClose={onClose} wide>
      {isLoading || !a ? <p className="text-muted">Cargando…</p> : (
        <div className="space-y-4">
          <div className="flex items-center gap-3 text-sm">
            <span className="font-semibold"><Nota v={a.percent_quality} /> <span className="text-muted text-xs">/10</span></span>
            {a.escenario && <span className="text-muted">· {a.escenario}</span>}
            {a.departamento && <span className="text-muted">· {a.departamento}</span>}
            <span className="text-muted text-xs">{fdate(a.created_at)}</span>
          </div>
          {a.error && (
            <div className="text-sm rounded-lg border border-rose-800 bg-rose-950/30 p-3 text-rose-200"><strong>Error:</strong> {a.error}</div>
          )}
          {a.feedback_message && (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1">Feedback a la asesora (coach)</h4>
              <p className="text-zinc-200 whitespace-pre-wrap text-sm">{a.feedback_message}</p>
            </section>
          )}
          {scores.length > 0 && (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1">Evaluación por parámetro (moderador)</h4>
              <div className="rounded-xl border border-border overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-bg/50 text-muted text-left">
                    <tr>
                      <th className="px-3 py-1.5 font-medium">Parámetro</th>
                      <th className="px-3 py-1.5 font-medium">Nota</th>
                      <th className="px-3 py-1.5 font-medium">Qué dijo el moderador</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.map(([rid, s]) => (
                      <tr key={rid} className="border-t border-border align-top">
                        <td className="px-3 py-1.5 font-medium">{rid}</td>
                        <td className="px-3 py-1.5 tabular-nums whitespace-nowrap">{s.applied === false ? "n/a" : `${s.score ?? 0}/${s.max ?? 0}`}</td>
                        <td className="px-3 py-1.5 text-muted">
                          {s.observacion || s.gap || s.note || "—"}
                          {s.evidencia?.[0] && <div className="text-xs text-zinc-500 mt-1 italic">“{s.evidencia[0]}”</div>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          {a.detailed_report && (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1">Informe (composer)</h4>
              <p className="text-zinc-200 whitespace-pre-wrap text-sm">{a.detailed_report}</p>
            </section>
          )}
          {transcript ? (
            <section>
              <h4 className="text-xs font-semibold uppercase tracking-wide text-muted mb-1">Transcripción</h4>
              <pre className="overflow-auto bg-bg border border-border rounded-lg p-3 text-sm text-zinc-200 whitespace-pre-wrap font-mono leading-relaxed" style={{ maxHeight: 360 }}>{transcript}</pre>
            </section>
          ) : (
            <p className="text-xs text-muted">Sin transcripción guardada para esta llamada.</p>
          )}
          <div className="flex justify-end">
            <Link href={`/dashboard/detail?id=${id}`} className="text-sm text-accent hover:underline">Abrir en página completa →</Link>
          </div>
        </div>
      )}
    </Modal>
  );
}

function MembershipRow({ nombre, m, onChanged }: { nombre: string; m: AgenteRow["memberships"][number]; onChanged: () => void }) {
  const base = { extension: "", nombre, default_scenario_id: null, department_id: m.department_id };
  const setNivel = useMutation({ mutationFn: (nivel: string) => simulacrosApi.updateComercial(m.id, { ...base, nivel, activo: m.activo }), onSuccess: onChanged });
  const activar = useMutation({ mutationFn: () => simulacrosApi.updateComercial(m.id, { ...base, nivel: m.nivel, activo: true }), onSuccess: onChanged });
  const quitar = useMutation({ mutationFn: () => simulacrosApi.deleteComercial(m.id), onSuccess: onChanged });
  return (
    <div className="flex items-center gap-2 rounded-xl border border-border px-3 py-2 bg-bg/40">
      <span className="flex-1 truncate">{m.departamento}</span>
      <select
        value={m.nivel ?? "medio"}
        onChange={(e) => setNivel.mutate(e.target.value)}
        className={`text-xs px-2 py-1 rounded-lg border bg-bg ${DIFF_COLOR[m.nivel ?? ""] ?? "border-border"}`}
      >
        {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
      </select>
      {m.activo ? (
        <span className="text-xs px-2 py-0.5 rounded-full border border-emerald-700 bg-emerald-900/30 text-emerald-300">Activo</span>
      ) : (
        <button onClick={() => activar.mutate()} className="text-xs text-accent hover:underline">Activar</button>
      )}
      <button onClick={() => { if (confirm(`¿Quitar a ${nombre} de ${m.departamento}?`)) quitar.mutate(); }} className="text-xs text-rose-400 hover:text-rose-300">Quitar</button>
    </div>
  );
}

function AddDeptModal({
  nombre, disponibles, onClose, onSaved,
}: {
  nombre: string;
  disponibles: Departamento[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [deptId, setDeptId] = useState(disponibles[0]?.id ?? "");
  const [nivel, setNivel] = useState<string>("facil");
  const save = useMutation({
    mutationFn: () => simulacrosApi.createComercial({ nombre, department_id: deptId, nivel, activo: false, default_scenario_id: null, extension: "" }),
    onSuccess: onSaved,
  });
  return (
    <Modal title={`Añadir “${nombre}” a un departamento`} onClose={onClose}>
      <div className="grid grid-cols-2 gap-3">
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Departamento</span>
          <select value={deptId} onChange={(e) => setDeptId(e.target.value)} className="w-full bg-bg border border-border rounded-lg px-3 py-2">
            {disponibles.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
          </select>
        </label>
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Nivel</span>
          <select value={nivel} onChange={(e) => setNivel(e.target.value)} className="w-full bg-bg border border-border rounded-lg px-3 py-2">
            {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
      </div>
      <p className="text-xs text-muted pt-2">Se añade como inactivo; actívalo desde la lista.</p>
      <ModalActions onClose={onClose} onSave={() => save.mutate()} saving={save.isPending} disabled={!deptId} />
    </Modal>
  );
}

function NuevoAgenteModal({
  departamentos, existentes, onClose, onSaved,
}: {
  departamentos: Departamento[];
  existentes: string[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [nombre, setNombre] = useState("");
  const [deptId, setDeptId] = useState(departamentos[0]?.id ?? "");
  const [nivel, setNivel] = useState<string>("facil");
  const [err, setErr] = useState("");
  const save = useMutation({
    mutationFn: () => {
      const n = nombre.trim();
      if (!n) throw new Error("Falta el nombre");
      if (existentes.includes(n)) throw new Error("Ya existe un agente con ese nombre");
      if (!deptId) throw new Error("Elige un departamento");
      return simulacrosApi.createComercial({ nombre: n, department_id: deptId, nivel, activo: true, default_scenario_id: null, extension: "" });
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Error"),
  });
  return (
    <Modal title="Nuevo agente" onClose={onClose}>
      <div className="space-y-3">
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Nombre (= alias que envía el CRM)</span>
          <input value={nombre} onChange={(e) => setNombre(e.target.value)} className="w-full bg-bg border border-border rounded-lg px-3 py-2" autoFocus />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Departamento</span>
            <select value={deptId} onChange={(e) => setDeptId(e.target.value)} className="w-full bg-bg border border-border rounded-lg px-3 py-2">
              {!departamentos.length && <option value="">— crea un departamento antes —</option>}
              {departamentos.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
            </select>
          </label>
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Nivel</span>
            <select value={nivel} onChange={(e) => setNivel(e.target.value)} className="w-full bg-bg border border-border rounded-lg px-3 py-2">
              {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
        {err && <p className="text-sm text-rose-400">{err}</p>}
      </div>
      <ModalActions onClose={onClose} onSave={() => save.mutate()} saving={save.isPending} disabled={!nombre.trim() || !deptId} />
    </Modal>
  );
}

function PrimerosPasos({ hayDatos }: { hayDatos: boolean }) {
  if (hayDatos) return <p className="text-muted">No hay agentes con estos filtros.</p>;
  const pasos = [
    { n: 1, t: "Crea un departamento", d: "Con sus FAQs por nivel y su evaluador.", href: "/dashboard/simulacros" },
    { n: 2, t: "Crea personalidades", d: "Las personas IA que reciben la llamada.", href: "/dashboard/simulacros" },
    { n: 3, t: "Da de alta agentes", d: "Con “+ Nuevo agente” aquí mismo.", href: "/dashboard" },
    { n: 4, t: "Lanza un simulacro", d: "Desde “Dev” o llamando al número de /simulacro.", href: "/dashboard/dev" },
  ];
  return (
    <div className="bg-card border border-border rounded-2xl p-6 space-y-4 max-w-2xl">
      <div>
        <h3 className="font-semibold">Primeros pasos</h3>
        <p className="text-sm text-muted">Aún no hay agentes ni simulacros. Configúralo en 4 pasos:</p>
      </div>
      <ol className="space-y-3">
        {pasos.map((p) => (
          <li key={p.n}>
            <a href={p.href} className="flex items-start gap-3 group">
              <span className="shrink-0 w-6 h-6 rounded-full bg-accent text-black text-sm font-bold flex items-center justify-center">{p.n}</span>
              <span><span className="font-medium group-hover:underline">{p.t}</span><span className="block text-sm text-muted">{p.d}</span></span>
            </a>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ─── Modal primitives ────────────────────────────────────────────────────────

function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: React.ReactNode; wide?: boolean }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 overflow-auto" onClick={onClose}>
      <div className={`bg-card border border-border rounded-2xl p-5 w-full ${wide ? "max-w-4xl" : "max-w-md"} my-8`} onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function ModalActions({ onClose, onSave, saving, disabled }: { onClose: () => void; onSave: () => void; saving: boolean; disabled?: boolean }) {
  return (
    <div className="flex justify-end gap-2 pt-4">
      <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
      <button onClick={onSave} disabled={saving || disabled} className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90 disabled:opacity-50">
        {saving ? "Guardando…" : "Guardar"}
      </button>
    </div>
  );
}
