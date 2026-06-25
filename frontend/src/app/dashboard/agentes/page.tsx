"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { simulacrosApi, type Comercial, type Departamento } from "@/lib/api";

const NIVELES = ["facil", "medio", "dificil"] as const;
const DIFF_COLOR: Record<string, string> = {
  facil: "text-emerald-300 border-emerald-700 bg-emerald-900/30",
  medio: "text-amber-300 border-amber-700 bg-amber-900/30",
  dificil: "text-rose-300 border-rose-700 bg-rose-900/30",
};

export default function AgentesPage() {
  const qc = useQueryClient();
  const { data: comerciales, isLoading } = useQuery({
    queryKey: ["sim-comerciales"], queryFn: simulacrosApi.listComerciales,
  });
  const { data: departamentos } = useQuery({
    queryKey: ["sim-departamentos"], queryFn: simulacrosApi.listDepartamentos,
  });
  const [nuevo, setNuevo] = useState(false);
  const [addTo, setAddTo] = useState<string | null>(null); // nombre del agente
  const invalidate = () => qc.invalidateQueries({ queryKey: ["sim-comerciales"] });

  const deptName = (id: string | null | undefined) =>
    departamentos?.find((d) => d.id === id)?.nombre ?? "(sin departamento)";

  // Agrupar fichas (membresías) por nombre de agente.
  const byName = new Map<string, Comercial[]>();
  for (const c of comerciales ?? []) {
    const arr = byName.get(c.nombre) ?? [];
    arr.push(c);
    byName.set(c.nombre, arr);
  }
  const agentes = [...byName.entries()].sort((a, b) => a[0].localeCompare(b[0]));

  return (
    <div className="space-y-6 max-w-[1100px] mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold">Agentes</h2>
          <p className="text-sm text-muted">
            Un agente puede estar en varios departamentos, cada uno con su nivel, pero solo está
            <strong> activo en uno</strong> (el que se usa al llamar y puntuar).
          </p>
        </div>
        <button
          onClick={() => setNuevo(true)}
          className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90"
        >
          + Nuevo agente
        </button>
      </div>

      {isLoading ? (
        <p className="text-muted">Cargando…</p>
      ) : !agentes.length ? (
        <p className="text-muted">Aún no hay agentes. Crea el primero con “+ Nuevo agente”.</p>
      ) : (
        <div className="space-y-4">
          {agentes.map(([nombre, fichas]) => (
            <AgenteCard
              key={nombre}
              nombre={nombre}
              fichas={fichas}
              deptName={deptName}
              onChanged={invalidate}
              onAddTo={() => setAddTo(nombre)}
            />
          ))}
        </div>
      )}

      {nuevo && (
        <AgenteModal
          nombre={null}
          existentes={agentes.map(([n]) => n)}
          fichasActuales={[]}
          departamentos={departamentos ?? []}
          onClose={() => setNuevo(false)}
          onSaved={() => { setNuevo(false); invalidate(); }}
        />
      )}
      {addTo && (
        <AgenteModal
          nombre={addTo}
          existentes={[]}
          fichasActuales={byName.get(addTo) ?? []}
          departamentos={departamentos ?? []}
          onClose={() => setAddTo(null)}
          onSaved={() => { setAddTo(null); invalidate(); }}
        />
      )}
    </div>
  );
}

function AgenteCard({
  nombre, fichas, deptName, onChanged, onAddTo,
}: {
  nombre: string;
  fichas: Comercial[];
  deptName: (id: string | null | undefined) => string;
  onChanged: () => void;
  onAddTo: () => void;
}) {
  const activa = fichas.find((f) => f.activo);
  return (
    <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold">{nombre}</h3>
          <p className="text-xs text-muted">
            {activa ? <>Activo en <strong>{deptName(activa.department_id)}</strong> · nivel {activa.nivel ?? "—"}</> : "Sin departamento activo"}
          </p>
        </div>
        <button onClick={onAddTo} className="text-sm text-accent hover:underline">+ Añadir a departamento</button>
      </div>
      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full text-sm">
          <thead className="bg-bg/50 text-muted text-left">
            <tr>
              <th className="px-4 py-2 font-medium">Departamento</th>
              <th className="px-4 py-2 font-medium">Nivel</th>
              <th className="px-4 py-2 font-medium">Estado</th>
              <th className="px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {fichas.map((f) => (
              <MembershipRow key={f.id} ficha={f} deptName={deptName} onChanged={onChanged} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function MembershipRow({
  ficha, deptName, onChanged,
}: {
  ficha: Comercial;
  deptName: (id: string | null | undefined) => string;
  onChanged: () => void;
}) {
  const base = {
    extension: ficha.extension, nombre: ficha.nombre,
    default_scenario_id: ficha.default_scenario_id, department_id: ficha.department_id,
  };
  const setNivel = useMutation({
    mutationFn: (nivel: string) => simulacrosApi.updateComercial(ficha.id, { ...base, nivel, activo: ficha.activo }),
    onSuccess: onChanged,
  });
  const activar = useMutation({
    mutationFn: () => simulacrosApi.updateComercial(ficha.id, { ...base, nivel: ficha.nivel, activo: true }),
    onSuccess: onChanged,
  });
  const quitar = useMutation({
    mutationFn: () => simulacrosApi.deleteComercial(ficha.id),
    onSuccess: onChanged,
  });

  return (
    <tr className="border-t border-border">
      <td className="px-4 py-2">{deptName(ficha.department_id)}</td>
      <td className="px-4 py-2">
        <select
          value={ficha.nivel ?? "medio"}
          onChange={(e) => setNivel.mutate(e.target.value)}
          className={`text-xs px-2 py-1 rounded-lg border bg-bg ${DIFF_COLOR[ficha.nivel ?? ""] ?? "border-border"}`}
        >
          {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </td>
      <td className="px-4 py-2">
        {ficha.activo ? (
          <span className="text-xs px-2 py-0.5 rounded-full border border-emerald-700 bg-emerald-900/30 text-emerald-300">Activo</span>
        ) : (
          <span className="text-xs text-muted">inactivo</span>
        )}
      </td>
      <td className="px-4 py-2 text-right whitespace-nowrap">
        {!ficha.activo && (
          <>
            <button onClick={() => activar.mutate()} className="text-accent hover:underline">Activar</button>
            <span className="text-border mx-2">·</span>
          </>
        )}
        <button
          onClick={() => { if (confirm(`¿Quitar a ${ficha.nombre} de ${deptName(ficha.department_id)}?`)) quitar.mutate(); }}
          className="text-rose-400 hover:text-rose-300"
        >
          Quitar
        </button>
      </td>
    </tr>
  );
}

function AgenteModal({
  nombre, existentes, fichasActuales, departamentos, onClose, onSaved,
}: {
  nombre: string | null;            // null = nuevo agente; string = añadir a departamento
  existentes: string[];
  fichasActuales: Comercial[];
  departamentos: Departamento[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const esNuevo = nombre === null;
  const [name, setName] = useState(nombre ?? "");
  const usados = new Set(fichasActuales.map((f) => f.department_id));
  const disponibles = departamentos.filter((d) => !usados.has(d.id));
  const [deptId, setDeptId] = useState(disponibles[0]?.id ?? "");
  const [nivel, setNivel] = useState<string>("facil");
  const [err, setErr] = useState("");

  const save = useMutation({
    mutationFn: () => {
      const n = name.trim();
      if (!n) throw new Error("Falta el nombre");
      if (esNuevo && existentes.includes(n)) throw new Error("Ya existe un agente con ese nombre");
      if (!deptId) throw new Error("Elige un departamento");
      return simulacrosApi.createComercial({
        nombre: n, department_id: deptId, nivel, activo: esNuevo, // nuevo agente → activo; añadir → inactivo
        default_scenario_id: null, extension: "",
      });
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Error"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 overflow-auto" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl p-5 w-full max-w-md my-8" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4">
          {esNuevo ? "Nuevo agente" : `Añadir “${nombre}” a un departamento`}
        </h3>
        <div className="space-y-3">
          {esNuevo && (
            <label className="text-sm space-y-1 block">
              <span className="text-muted">Nombre (= alias que envía el CRM)</span>
              <input value={name} onChange={(e) => setName(e.target.value)}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2" autoFocus />
            </label>
          )}
          <div className="grid grid-cols-2 gap-3">
            <label className="text-sm space-y-1 block">
              <span className="text-muted">Departamento</span>
              <select value={deptId} onChange={(e) => setDeptId(e.target.value)}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2">
                {!disponibles.length && <option value="">— sin departamentos libres —</option>}
                {disponibles.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
              </select>
            </label>
            <label className="text-sm space-y-1 block">
              <span className="text-muted">Nivel</span>
              <select value={nivel} onChange={(e) => setNivel(e.target.value)}
                className="w-full bg-bg border border-border rounded-lg px-3 py-2">
                {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
          </div>
          {!esNuevo && <p className="text-xs text-muted">Se añade como inactivo; actívalo desde la ficha del agente.</p>}
          {err && <p className="text-sm text-rose-400">{err}</p>}
        </div>
        <div className="flex justify-end gap-2 pt-4">
          <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
          <button onClick={() => save.mutate()} disabled={save.isPending || !deptId || (esNuevo && !name.trim())}
            className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90 disabled:opacity-50">
            {save.isPending ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </div>
  );
}
