"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
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
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["analyses"] }); qc.invalidateQueries({ queryKey: ["stats"] }); setDel(null); },
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
                <th className="px-4 py-2 font-medium">Fecha</th>
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
                  <td className="px-4 py-2 text-right">
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
    </div>
  );
}
