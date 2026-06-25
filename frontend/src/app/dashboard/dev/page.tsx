"use client";

import { useState } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";

import { simulacrosApi, type Comercial, type Scenario } from "@/lib/api";

const SIM_NUMBER = "+34 919 932 448";

export default function DevPage() {
  const { data: comerciales } = useQuery({
    queryKey: ["sim-comerciales"],
    queryFn: simulacrosApi.listComerciales,
  });
  const { data: scenarios } = useQuery({
    queryKey: ["sim-scenarios"],
    queryFn: simulacrosApi.listScenarios,
  });

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto">
      <div>
        <h2 className="text-xl font-semibold">Dev — simuladores</h2>
        <p className="text-sm text-muted">
          Herramientas de prueba para el equipo de desarrollo. No forman parte del flujo real.
        </p>
      </div>
      <CrmButtonSimulator comerciales={comerciales ?? []} scenarios={scenarios ?? []} />
      <CrmCallTester scenarios={scenarios ?? []} />
    </div>
  );
}

// ─── Simular el botón "Llamar" del CRM (announce → llamas tú) ────────────────

function CrmButtonSimulator({ comerciales, scenarios }: { comerciales: Comercial[]; scenarios: Scenario[] }) {
  const activos = scenarios.filter((s) => s.activo);
  const [comId, setComId] = useState(comerciales[0]?.id ?? "");
  const [nombre, setNombre] = useState(comerciales[0]?.nombre ?? "");
  const [fromNumber, setFromNumber] = useState(comerciales[0]?.extension ?? "");
  const [scenarioId, setScenarioId] = useState("");

  const pickComercial = (id: string) => {
    setComId(id);
    const c = comerciales.find((x) => x.id === id);
    if (c) { setNombre(c.nombre); setFromNumber(c.extension ?? ""); }
    else { setNombre(""); setFromNumber(""); }
  };

  const announce = useMutation({
    mutationFn: () =>
      simulacrosApi.announce({
        agente_nombre: nombre.trim(),
        from_number: fromNumber.trim() || undefined,
        scenario_id: scenarioId || undefined,
      }),
  });

  return (
    <section className="bg-card border border-emerald-800 rounded-2xl p-4 space-y-3">
      <div>
        <h3 className="text-lg font-semibold">🟢 Simular la petición del CRM</h3>
        <p className="text-sm text-zinc-300">
          Simula lo que hará el CRM: “el agente X solicita un simulacro”. Cogemos su alias,
          miramos su nivel, <strong>elegimos el guion</strong> y armamos a Retell. Te devolvemos{" "}
          <span className="font-mono text-emerald-300">OK</span> (como al CRM). Luego marca al{" "}
          <span className="font-mono text-emerald-300">{SIM_NUMBER}</span> y entrará con ese guion.
        </p>
      </div>

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
        {comerciales.length > 0 && (
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Comercial</span>
            <select
              value={comId}
              onChange={(e) => pickComercial(e.target.value)}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              <option value="">— escribir a mano —</option>
              {comerciales.map((c) => (
                <option key={c.id} value={c.id}>{c.nombre}{c.nivel ? ` (${c.nivel})` : ""}</option>
              ))}
            </select>
          </label>
        )}
        <Input label="Nombre de la agente" value={nombre} onChange={(v) => { setNombre(v); setComId(""); }} />
        <Input label="Su nº (caller ID, opcional)" value={fromNumber} onChange={setFromNumber} />
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Guion</span>
          <select
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">🎯 Auto (según su nivel)</option>
            {activos.map((s) => <option key={s.id} value={s.id}>{s.nombre}</option>)}
          </select>
        </label>
      </div>

      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={() => announce.mutate()}
          disabled={!nombre.trim() || announce.isPending}
          className="text-sm rounded-lg bg-accent text-black font-medium px-4 py-2 hover:opacity-90 disabled:opacity-50"
        >
          {announce.isPending ? "Procesando…" : "▶ Simular petición del CRM"}
        </button>
        {announce.isError && (
          <span className="text-sm text-rose-400">Error: no se pudo procesar la petición.</span>
        )}
        {announce.data && (
          <span className="text-sm inline-flex items-center gap-2">
            <span className="font-mono font-semibold text-emerald-300 bg-emerald-950/40 border border-emerald-800 rounded px-2 py-0.5">
              {announce.data.status} · {announce.data.mensaje}
            </span>
            <span className="text-muted">
              → {announce.data.agente_nombre}
              {announce.data.nivel ? ` (${announce.data.nivel})` : ""} · guion:{" "}
              <strong className="text-zinc-200">{announce.data.escenario ?? "—"}</strong>
            </span>
          </span>
        )}
      </div>
    </section>
  );
}

// ─── Simular llamada tipo CRM (outbound de prueba) ──────────────────────────

function CrmCallTester({ scenarios }: { scenarios: Scenario[] }) {
  const [nombre, setNombre] = useState("");
  const [numero, setNumero] = useState("");
  const [scenarioId, setScenarioId] = useState(""); // "" = aleatorio
  const activos = scenarios.filter((s) => s.activo);
  const call = useMutation({
    mutationFn: () =>
      simulacrosApi.startCall({
        to_number: numero.trim(),
        agente_nombre: nombre.trim() || undefined,
        scenario_id: scenarioId || undefined,
      }),
  });

  return (
    <section className="bg-card border border-border rounded-2xl p-4 space-y-4">
      <div>
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted">
          Prueba rápida (inversa): que Retell te llame
        </h3>
        <p className="text-sm text-muted">
          Alternativa sin marcar tú: Retell llamará al número que pongas y el simulacro se
          atribuye al nombre que escribas. El guion se elige al azar (o fija uno).
        </p>
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <Input label="Nombre (comercial)" value={nombre} onChange={setNombre} />
        <Input label="Número a llamar (+34…)" value={numero} onChange={setNumero} />
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Guion</span>
          <select
            value={scenarioId}
            onChange={(e) => setScenarioId(e.target.value)}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">🎲 Aleatorio (entre activos)</option>
            {activos.map((s) => (
              <option key={s.id} value={s.id}>{s.nombre}</option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={() => call.mutate()}
          disabled={!numero.trim() || call.isPending}
          className="text-sm rounded-lg border border-border px-4 py-2 hover:border-accent disabled:opacity-50"
        >
          {call.isPending ? "Llamando…" : "📞 Que Retell me llame"}
        </button>
        {call.isError && (
          <span className="text-sm text-rose-400">
            {(() => {
              const e = call.error as { body?: { detail?: string } } | undefined;
              const d = e?.body?.detail;
              return d ? String(d) : "No se pudo lanzar (revisa el número en formato +34… y la API key).";
            })()}
          </span>
        )}
        {call.data && (
          <span className="text-sm text-emerald-300">
            Llamando a {numero} · guion: {call.data.scenario ?? "aleatorio"}. Descuelga y haz
            de asesora; al colgar verás el análisis en “Análisis”.
          </span>
        )}
      </div>
    </section>
  );
}

function Input({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="text-sm space-y-1 block">
      <span className="text-muted">{label}</span>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-bg border border-border rounded-lg px-3 py-2"
      />
    </label>
  );
}
