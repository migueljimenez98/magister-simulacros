"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  api, simulacrosApi,
  type AgenteRow, type Departamento,
} from "@/lib/api";

const NIVELES = ["facil", "medio", "dificil"] as const;
const DIFF_COLOR: Record<string, string> = {
  facil: "text-emerald-300 border-emerald-700 bg-emerald-900/30",
  medio: "text-amber-300 border-amber-700 bg-amber-900/30",
  dificil: "text-rose-300 border-rose-700 bg-rose-900/30",
};
const scoreColor = (v: number | null | undefined) =>
  v == null ? "text-muted" : v >= 80 ? "text-emerald-300" : v >= 50 ? "text-amber-300" : "text-rose-300";
const barColor = (v: number | null | undefined) =>
  v == null ? "bg-zinc-600" : v >= 80 ? "bg-emerald-500" : v >= 50 ? "bg-amber-500" : "bg-rose-500";
const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v)}%`);
const fdate = (s: string | null) => (s ? new Date(s).toLocaleString("es-ES", { dateStyle: "short", timeStyle: "short" }) : "—");
const nivelIdx = (n: string | null) => (n ? NIVELES.indexOf(n as (typeof NIVELES)[number]) : -1);

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
              <span className="text-muted">Nota media: <strong className={scoreColor(data.avg_percent)}>{pct(data.avg_percent)}</strong></span>
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
                  <th className="px-4 py-2 font-medium">Departamento activo</th>
                  <th className="px-4 py-2 font-medium">Nivel</th>
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
                      <td className="px-4 py-2 text-muted">{a.departamento_activo ?? <span className="text-rose-400">sin activo</span>}</td>
                      <td className="px-4 py-2"><NivelBadge nivel={a.nivel_actual} /></td>
                      <td className="px-4 py-2 text-muted whitespace-nowrap">{fdate(a.ultima_fecha)}{a.ultimo_departamento ? <span className="text-xs"> · {a.ultimo_departamento}</span> : ""}</td>
                      <td className={`px-4 py-2 font-semibold tabular-nums ${scoreColor(a.ultima_nota)}`}>{pct(a.ultima_nota)}</td>
                      <td className="px-4 py-2 text-muted tabular-nums">{a.count}</td>
                      <td className={`px-4 py-2 font-semibold tabular-nums ${scoreColor(a.avg_percent)}`}>{pct(a.avg_percent)}</td>
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

          {data.por_parametro.length > 0 && (
            <section className="bg-card border border-border rounded-2xl p-4 space-y-3 max-w-3xl">
              <div>
                <h3 className="font-semibold">Temas más fallados</h3>
                <p className="text-xs text-muted">Parámetros de la rúbrica con peor nota media.</p>
              </div>
              <div className="space-y-2">
                {data.por_parametro.slice(0, 8).map((p) => <BarRow key={p.id} label={p.name} value={p.avg_percent} count={p.count} />)}
              </div>
            </section>
          )}
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

function BarRow({ label, value, count }: { label: string; value: number | null; count: number }) {
  const w = value == null ? 0 : Math.max(2, Math.min(100, value));
  return (
    <div className="flex items-center gap-3">
      <span className="text-sm w-48 shrink-0 truncate" title={label}>{label}</span>
      <div className="flex-1 h-3 rounded-full bg-bg overflow-hidden">
        <div className={`h-full ${barColor(value)}`} style={{ width: `${w}%` }} />
      </div>
      <span className={`text-sm tabular-nums w-12 text-right ${scoreColor(value)}`}>{pct(value)}</span>
      <span className="text-xs text-muted w-10 text-right">n={count}</span>
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
              : "—"} (según su nota media {pct(agente.avg_percent)}).
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
                    <td className={`px-3 py-1.5 font-semibold tabular-nums ${scoreColor(r.percent_quality)}`}>{pct(r.percent_quality)}</td>
                    <td className="px-3 py-1.5 text-right">
                      <Link href={`/dashboard/detail?id=${r.id}`} className="text-accent hover:underline">Ver</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
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
