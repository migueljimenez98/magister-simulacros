"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api, simulacrosApi, type AnalysisListPage } from "@/lib/api";
import { nota10, notaHsl } from "@/lib/score";
import { ConfirmDelete } from "@/components/confirm-delete";

const STATUS_LABEL: Record<string, string> = {
  pending: "En cola", fetching: "Procesando…", scoring: "Puntuando…",
  composing: "Redactando…", persisting: "Guardando…", done: "Listo", failed: "Error",
};
const STATUS_COLOR: Record<string, string> = {
  done: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
  failed: "bg-rose-900/40 text-rose-300 border-rose-700",
  pending: "bg-zinc-800 text-zinc-300 border-zinc-700",
};

export default function LogLlamadasPage() {
  const qc = useQueryClient();
  const [del, setDel] = useState<{ id: string; nombre: string } | null>(null);
  const [reasignar, setReasignar] = useState<{ id: string; nombre: string } | null>(null);
  const { data, isLoading } = useQuery({
    queryKey: ["analyses"],
    queryFn: () => api.analyses.list({ limit: 200 }),
    refetchInterval: (q) => {
      const items = q.state.data?.items ?? [];
      return items.some((r) => !["done", "failed"].includes(r.status)) ? 4000 : 20000;
    },
  });
  const borrar = useMutation({
    mutationFn: (id: string) => api.analyses.delete(id),
    onSuccess: (_d, id) => {
      // Quita la fila al instante de la cache (no espera al refetch).
      qc.setQueryData<AnalysisListPage>(["analyses"], (old) =>
        old ? { ...old, items: old.items.filter((i) => i.id !== id), total: Math.max(0, old.total - 1) } : old);
      qc.invalidateQueries({ queryKey: ["analyses"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      setDel(null);
    },
  });
  const reevaluar = useMutation({
    mutationFn: (id: string) => api.analyses.redispatch(id),
    onSuccess: (_d, id) => {
      // Marca la fila como "en cola" al instante; el refetch (4s) traerá el resultado.
      qc.setQueryData<AnalysisListPage>(["analyses"], (old) =>
        old ? { ...old, items: old.items.map((i) => (i.id === id ? { ...i, status: "pending" } : i)) } : old);
      qc.invalidateQueries({ queryKey: ["analyses"] });
    },
  });

  const items = data?.items ?? [];

  return (
    <div className="w-full space-y-5">
      <div>
        <h2 className="text-xl font-semibold">Log de llamadas</h2>
        <p className="text-sm text-muted">
          Cada simulacro, con su nota. Pulsa una fila para ver la transcripción y el detalle.
        </p>
      </div>

      {isLoading ? (
        <p className="text-muted">Cargando…</p>
      ) : !items.length ? (
        <p className="text-muted">Aún no hay simulacros. Lanza uno desde la pestaña “Dev”.</p>
      ) : (
        <div className="bg-card border border-border rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg/50 text-muted text-left">
              <tr>
                <th className="px-4 py-2 font-medium">Agente</th>
                <th className="px-4 py-2 font-medium">Departamento</th>
                <th className="px-4 py-2 font-medium">Personalidad</th>
                <th className="px-4 py-2 font-medium">Nota</th>
                <th className="px-4 py-2 font-medium">Feedback</th>
                <th className="px-4 py-2 font-medium">Estado</th>
                <th className="px-4 py-2 font-medium">Fecha llamada</th>
                <th className="px-4 py-2 font-medium">Evaluado</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-t border-border hover:bg-bg/40">
                  <td className="px-4 py-2">
                    <Link href={`/dashboard/detail?id=${r.id}`} className="text-accent hover:underline">
                      {r.agente_nombre}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-muted whitespace-nowrap">{r.departamento || "—"}</td>
                  <td className="px-4 py-2 text-muted truncate max-w-[240px]">{r.escenario || "—"}</td>
                  <td className="px-4 py-2 font-semibold tabular-nums" style={{ color: notaHsl(r.percent_quality) }}>{nota10(r.percent_quality)}</td>
                  <td className="px-4 py-2 text-muted truncate max-w-[420px]">
                    {r.feedback_message || (r.status === "done" ? "(sin observaciones)" : "—")}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`text-xs px-2 py-0.5 rounded-full border ${STATUS_COLOR[r.status] ?? "border-border text-muted"}`}>
                      {STATUS_LABEL[r.status] ?? r.status}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-muted whitespace-nowrap">
                    {new Date(r.created_at).toLocaleString("es-ES")}
                  </td>
                  <td className="px-4 py-2 text-muted whitespace-nowrap">
                    {r.status === "done" ? new Date(r.updated_at).toLocaleString("es-ES") : "—"}
                  </td>
                  <td className="px-4 py-2 text-right whitespace-nowrap">
                    <button
                      onClick={() => reevaluar.mutate(r.id)}
                      disabled={reevaluar.isPending || !["done", "failed"].includes(r.status)}
                      title="Volver a evaluar desde la transcripción guardada"
                      className="text-accent hover:text-white disabled:opacity-40 disabled:cursor-not-allowed mr-3"
                    >
                      {reevaluar.isPending && reevaluar.variables === r.id ? "…" : "Reevaluar"}
                    </button>
                    <button
                      onClick={() => setReasignar({ id: r.id, nombre: r.agente_nombre })}
                      title="Asignar esta llamada a otro agente"
                      className="text-accent hover:text-white mr-3"
                    >
                      Reasignar
                    </button>
                    <button onClick={() => setDel({ id: r.id, nombre: r.agente_nombre })} className="text-rose-400 hover:text-rose-300">Borrar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {del && (
        <ConfirmDelete
          title="Eliminar simulacro"
          message={`Se borrará la llamada de ${del.nombre} y su evaluación de la base de datos.`}
          pending={borrar.isPending}
          onConfirm={() => borrar.mutate(del.id)}
          onClose={() => setDel(null)}
        />
      )}
      {reasignar && (
        <ReasignarModal
          id={reasignar.id}
          actual={reasignar.nombre}
          onClose={() => setReasignar(null)}
        />
      )}
    </div>
  );
}

// Mueve una llamada al agente correcto cuando la atribución automática
// (caller ID / anuncio del CRM) la dejó en la persona equivocada.
function ReasignarModal({ id, actual, onClose }: { id: string; actual: string; onClose: () => void }) {
  const qc = useQueryClient();
  const [nombre, setNombre] = useState("");
  const [err, setErr] = useState("");
  const { data: comerciales } = useQuery({
    queryKey: ["sim-comerciales"],
    queryFn: simulacrosApi.listComerciales,
  });
  // Un agente puede tener ficha en varios departamentos: la lista va por NOMBRE.
  const nombres = Array.from(new Set((comerciales ?? []).map((c) => c.nombre)))
    .filter((n) => n && n !== actual)
    .sort((a, b) => a.localeCompare(b, "es"));

  const guardar = useMutation({
    mutationFn: () => {
      const n = nombre.trim();
      if (!n) throw new Error("Elige un agente");
      return api.analyses.reasignar(id, n);
    },
    onSuccess: () => {
      // La nota cambia de dueño: refresca log, stats e historiales.
      qc.invalidateQueries({ queryKey: ["analyses"] });
      qc.invalidateQueries({ queryKey: ["stats"] });
      qc.invalidateQueries({ queryKey: ["agente-historial"] });
      qc.invalidateQueries({ queryKey: ["agente-niveles"] });
      onClose();
    },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "No se pudo reasignar"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 overflow-auto" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl p-5 w-full max-w-md my-16" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-1">Reasignar simulacro</h3>
        <p className="text-sm text-muted mb-4">
          Ahora está asignado a <strong className="text-white">{actual}</strong>. Al cambiarlo, la nota
          deja de contar para esa persona y pasa a contar para la nueva (se recalculan sus niveles).
        </p>
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Nuevo agente</span>
          <select
            value={nombre}
            onChange={(e) => { setNombre(e.target.value); setErr(""); }}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">— elige un agente —</option>
            {nombres.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        {!nombres.length && (
          <p className="text-xs text-muted pt-2">No hay otros agentes dados de alta.</p>
        )}
        {err && <p className="text-sm text-rose-400 pt-2">{err}</p>}
        <div className="flex justify-end gap-2 pt-4">
          <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
          <button
            onClick={() => guardar.mutate()}
            disabled={guardar.isPending || !nombre.trim()}
            className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90 disabled:opacity-50"
          >
            {guardar.isPending ? "Reasignando…" : "Reasignar"}
          </button>
        </div>
      </div>
    </div>
  );
}
