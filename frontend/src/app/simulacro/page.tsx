"use client";

import { useEffect, useRef, useState } from "react";

import { colaApi, type ColaStatus } from "@/lib/api";

export default function SimulacroPage() {
  const [numero, setNumero] = useState("");
  const [nombre, setNombre] = useState("");
  const [ticket, setTicket] = useState<string | null>(null);
  const [state, setState] = useState<ColaStatus | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const ticketRef = useRef<string | null>(null);

  // Número de teléfono a marcar (público).
  useEffect(() => {
    colaApi.info().then((r) => setNumero(r.numero)).catch(() => {});
  }, []);

  // Polling del turno mientras tengamos ticket y no haya terminado.
  useEffect(() => {
    if (!ticket) return;
    ticketRef.current = ticket;
    let alive = true;
    const tick = async () => {
      try {
        const s = await colaApi.status(ticket);
        if (alive && ticketRef.current === ticket) setState(s);
      } catch {
        /* error transitorio: reintenta en el siguiente tick */
      }
    };
    tick();
    const id = setInterval(tick, 2000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [ticket]);

  const start = async () => {
    const n = nombre.trim();
    if (!n) return;
    setLoading(true);
    setError("");
    try {
      const r = await colaApi.join(n);
      if (r.numero) setNumero(r.numero);
      setState(r);
      setTicket(r.ticket);
    } catch {
      setError("No se pudo iniciar. Inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  };

  const reset = () => {
    ticketRef.current = null;
    setTicket(null);
    setState(null);
    setError("");
  };

  const numFmt = numero || "el número de simulacro";
  const st = state?.status;

  return (
    <main className="min-h-screen flex items-center justify-center bg-bg p-6">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center space-y-1">
          <h1 className="text-2xl font-semibold">Simulacro de llamada</h1>
          <p className="text-sm text-muted">Practica una llamada con el alumno IA.</p>
        </div>

        {/* Formulario (cuando no hay turno en curso) */}
        {!ticket || st === "expired" ? (
          <div className="bg-card border border-border rounded-2xl p-5 space-y-3">
            {st === "expired" && (
              <div className="text-sm rounded-lg border border-amber-800 bg-amber-950/30 p-3 text-amber-200">
                Se acabó el margen sin detectar la llamada. Vuelve a iniciar cuando estés listo.
              </div>
            )}
            <label className="text-sm space-y-1 block">
              <span className="text-muted">Nombre de seguimiento</span>
              <input
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && start()}
                placeholder="Tu nombre / alias"
                className="w-full bg-bg border border-border rounded-lg px-3 py-2"
                autoFocus
              />
            </label>
            <button
              onClick={start}
              disabled={loading || !nombre.trim()}
              className="w-full rounded-lg bg-accent text-black font-medium px-4 py-3 hover:opacity-90 disabled:opacity-50"
            >
              {loading ? "Iniciando…" : "Iniciar simulacro"}
            </button>
            <p className="text-xs text-muted text-center">
              Pulsa “Iniciar simulacro” y <strong>después</strong> te diremos a qué número llamar.
            </p>
            {error && <p className="text-sm text-rose-400">{error}</p>}
          </div>
        ) : st === "active" ? (
          <div className="bg-card border border-emerald-700 rounded-2xl p-5 space-y-4 text-center">
            <p className="text-lg font-semibold text-emerald-300">¡Es tu turno! Llama ahora</p>
            <div className="rounded-xl border border-emerald-700 bg-emerald-950/20 py-3">
              <p className="text-xs uppercase tracking-wide text-muted">Llama a este número</p>
              <p className="text-3xl font-bold tabular-nums mt-1 select-all text-emerald-200">{numFmt}</p>
            </div>
            <DatosSimulacro escenario={state?.escenario} datos={state?.datos} />
            {typeof state?.seconds_left === "number" && (
              <p className="text-sm text-muted">
                Tienes <span className="tabular-nums font-semibold">{state.seconds_left}s</span> para empezar la llamada.
              </p>
            )}
            <button onClick={reset} className="text-sm text-muted hover:text-white underline">
              Cancelar
            </button>
          </div>
        ) : st === "started" ? (
          <div className="bg-card border border-emerald-700 rounded-2xl p-5 space-y-3 text-center">
            <p className="text-lg font-semibold text-emerald-300">✅ Llamada detectada</p>
            <p className="text-sm text-muted">Tu simulacro está en curso. ¡Mucha suerte!</p>
            <DatosSimulacro escenario={state?.escenario} datos={state?.datos} />
            <button
              onClick={reset}
              className="rounded-lg border border-border px-4 py-2 text-sm hover:border-accent"
            >
              Hacer otro simulacro
            </button>
          </div>
        ) : (
          // waiting
          <div className="bg-card border border-border rounded-2xl p-5 space-y-2 text-center">
            <p className="text-lg font-semibold">Hay un simulacro en curso</p>
            <p className="text-sm text-muted">
              Estás en cola
              {typeof state?.position === "number" && (
                <>
                  {" "}— posición <span className="font-semibold tabular-nums">{state.position}</span>
                </>
              )}
              . Te avisamos aquí cuando sea tu turno.
            </p>
            <div className="flex items-center justify-center gap-2 pt-1 text-muted text-sm">
              <span className="inline-block w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              Esperando turno…
            </div>
            <button onClick={reset} className="text-sm text-muted hover:text-white underline pt-1">
              Cancelar
            </button>
          </div>
        )}

        <p className="text-center text-xs text-muted">
          No cierres esta página mientras esperas tu turno.
        </p>
      </div>
    </main>
  );
}

function DatosSimulacro({ escenario, datos }: { escenario?: string | null; datos?: string }) {
  if (!escenario && !datos) return null;
  return (
    <div className="rounded-xl border border-border bg-bg/40 p-3 text-left">
      <p className="text-xs uppercase tracking-wide text-muted mb-1">Datos del simulacro</p>
      {escenario && <p className="text-sm font-medium">{escenario}</p>}
      {datos && <p className="text-sm text-zinc-300 whitespace-pre-wrap mt-1">{datos}</p>}
    </div>
  );
}
