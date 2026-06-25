"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { api, type ParamScore } from "@/lib/api";
import { nota10, notaHsl } from "@/lib/score";

const STATUS_LABEL: Record<string, string> = {
  pending: "En cola", fetching: "Procesando…", scoring: "Puntuando…",
  composing: "Redactando…", persisting: "Guardando…", done: "Listo", failed: "Error",
};

export default function DetailPage() {
  return (
    <Suspense fallback={<p className="text-muted">Cargando…</p>}>
      <Inner />
    </Suspense>
  );
}

function Inner() {
  const router = useRouter();
  const id = useSearchParams()?.get("id") || "";
  const qc = useQueryClient();

  const { data: a, isLoading } = useQuery({
    queryKey: ["analysis", id],
    queryFn: () => api.analyses.get(id),
    enabled: Boolean(id),
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s && !["done", "failed"].includes(s) ? 4000 : false;
    },
  });

  const redispatch = useMutation({
    mutationFn: () => api.analyses.redispatch(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["analysis", id] }),
  });
  const remove = useMutation({
    mutationFn: () => api.analyses.delete(id),
    onSuccess: () => router.replace("/dashboard"),
  });

  if (isLoading) return <p className="text-muted">Cargando…</p>;
  if (!a) return <p className="text-rose-400">No encontrado.</p>;

  const snap = (a.crm_snapshot || {}) as Record<string, unknown>;
  const sim = (snap._simulacro || {}) as Record<string, unknown>;
  const transcript =
    (typeof snap.transcript === "string" && snap.transcript) ||
    (typeof sim.transcript === "string" && sim.transcript) || "";
  const recording =
    (typeof snap.recording_url === "string" && snap.recording_url) ||
    (typeof sim.recording_url === "string" && sim.recording_url) || "";
  const escenario = (sim.scenario as Record<string, unknown> | undefined)?.nombre as string | undefined;

  const scores = Object.entries(a.scores || {}) as [string, ParamScore][];
  const ideal = a.ideal_score != null ? Number(a.ideal_score) : 0;
  const total = a.total_score != null ? Number(a.total_score) : 0;

  return (
    <div className="space-y-5 max-w-[1100px] mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <button onClick={() => router.back()} className="text-sm text-muted hover:text-white">← Volver</button>
          <h2 className="text-xl font-semibold">{a.agente_nombre}</h2>
          <span className="text-xs px-2 py-1 rounded-full border border-border text-muted">
            {STATUS_LABEL[a.status] ?? a.status}
          </span>
          {escenario && <span className="text-xs text-muted">· personalidad: {escenario}</span>}
        </div>
        <div className="flex items-center gap-2 text-sm">
          <span className="font-semibold">
            <span style={{ color: notaHsl(a.percent_quality) }}>{nota10(a.percent_quality)}</span>
            <span className="text-muted font-normal text-xs">/10</span>
            {ideal > 0 && <span className="text-muted font-normal"> · {total}/{ideal}</span>}
          </span>
          <button onClick={() => redispatch.mutate()} disabled={redispatch.isPending}
            className="rounded-lg border border-border px-3 py-1.5 hover:border-accent">
            {redispatch.isPending ? "…" : "Re-analizar"}
          </button>
          <button onClick={() => { if (confirm("¿Borrar este simulacro?")) remove.mutate(); }}
            className="rounded-lg border border-border px-3 py-1.5 text-rose-400 hover:border-rose-500">
            Borrar
          </button>
        </div>
      </div>

      {a.error && (
        <div className="bg-rose-950/30 border border-rose-900 rounded-2xl p-3 text-sm text-rose-200">
          <strong>Error:</strong> {a.error}
        </div>
      )}

      {a.feedback_message && (
        <section className="bg-card border border-border rounded-2xl p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2">Feedback para la asesora</h3>
          <p className="text-zinc-200 whitespace-pre-wrap">{a.feedback_message}</p>
        </section>
      )}

      {scores.length > 0 && (
        <section className="bg-card border border-border rounded-2xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg/50 text-muted text-left">
              <tr>
                <th className="px-4 py-2 font-medium">Parámetro</th>
                <th className="px-4 py-2 font-medium">Nota</th>
                <th className="px-4 py-2 font-medium">Qué mejorar</th>
              </tr>
            </thead>
            <tbody>
              {scores.map(([rid, s]) => (
                <tr key={rid} className="border-t border-border align-top">
                  <td className="px-4 py-2 font-medium">{rid}</td>
                  <td className="px-4 py-2 tabular-nums whitespace-nowrap">
                    {s.applied === false ? "n/a" : `${s.score ?? 0}/${s.max ?? 0}`}
                  </td>
                  <td className="px-4 py-2 text-muted">
                    {s.gap || s.note || "—"}
                    {s.evidencia?.[0] && (
                      <div className="text-xs text-zinc-500 mt-1 italic">“{s.evidencia[0]}”</div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {(transcript || recording) && (
        <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">Transcripción</h3>
          {recording && <audio controls src={recording} className="w-full" />}
          {transcript && (
            <pre style={{ maxHeight: 460 }}
              className="overflow-auto bg-bg border border-border rounded-lg p-4 text-sm text-zinc-200 whitespace-pre-wrap font-mono leading-relaxed">
              {transcript}
            </pre>
          )}
        </section>
      )}

      {a.detailed_report && (
        <section className="bg-card border border-border rounded-2xl p-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-muted mb-2">Informe</h3>
          <div className="prose prose-sm prose-invert max-w-none prose-headings:text-white prose-p:text-zinc-200 prose-li:text-zinc-200 prose-strong:text-white">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{a.detailed_report}</ReactMarkdown>
          </div>
        </section>
      )}
    </div>
  );
}
