"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  simulacrosApi,
  type Comercial,
  type ComercialInput,
  type Departamento,
  type DepartamentoInput,
  type Evaluadores,
  type FaqItem,
  type Scenario,
  type ScenarioInput,
} from "@/lib/api";

// Niveles de dificultad fijos en todo el sistema.
const NIVELES = ["facil", "medio", "dificil"] as const;

const DIFF_COLOR: Record<string, string> = {
  facil: "bg-emerald-900/40 text-emerald-300 border-emerald-700",
  medio: "bg-amber-900/40 text-amber-300 border-amber-700",
  dificil: "bg-rose-900/40 text-rose-300 border-rose-700",
};

const EMPTY_SCENARIO: ScenarioInput = {
  nombre: "",
  dificultad: "medio",
  producto: "",
  persona: "",
  objeciones: "",
  faqs: "",
  guion: "",
  retell_agent_id: "",
  activo: true,
  department_id: null,
};

type ScenarioModalState = { scenario: Scenario | null; departmentId: string | null };
type ComercialModalState = { comercial: Comercial | null; departmentId: string | null };

export default function SimulacrosPage() {
  const qc = useQueryClient();
  const { data: scenarios, isLoading } = useQuery({
    queryKey: ["sim-scenarios"],
    queryFn: simulacrosApi.listScenarios,
  });
  const { data: comerciales } = useQuery({
    queryKey: ["sim-comerciales"],
    queryFn: simulacrosApi.listComerciales,
  });
  const { data: departamentos } = useQuery({
    queryKey: ["sim-departamentos"],
    queryFn: simulacrosApi.listDepartamentos,
  });

  const [scenarioModal, setScenarioModal] = useState<ScenarioModalState | null>(null);
  const [comercialModal, setComercialModal] = useState<ComercialModalState | null>(null);
  const [deptModal, setDeptModal] = useState<Departamento | "new" | null>(null);
  const [testing, setTesting] = useState<Scenario | null>(null);

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sim-scenarios"] });
    qc.invalidateQueries({ queryKey: ["sim-comerciales"] });
    qc.invalidateQueries({ queryKey: ["sim-departamentos"] });
  };

  const deptList = departamentos ?? [];
  const knownDeptIds = new Set(deptList.map((d) => d.id));
  const huerfanos = (scenarios ?? []).filter(
    (s) => !s.department_id || !knownDeptIds.has(s.department_id),
  );

  return (
    <div className="space-y-8 max-w-[1400px] mx-auto">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-semibold">Simulacros</h2>
          <p className="text-sm text-muted">
            Cada <strong>departamento</strong> agrupa sus <strong>personalidades</strong> (personas IA
            por dificultad), sus comerciales (con su nivel) y sus FAQs comunes por nivel.
          </p>
        </div>
        <button
          onClick={() => setDeptModal("new")}
          className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90"
        >
          + Nuevo departamento
        </button>
      </div>

      {isLoading ? (
        <p className="text-muted">Cargando…</p>
      ) : !deptList.length ? (
        <p className="text-muted">
          Aún no hay departamentos. Crea el primero con “+ Nuevo departamento”.
        </p>
      ) : (
        <div className="space-y-6">
          {deptList.map((dept) => (
            <DepartmentSection
              key={dept.id}
              dept={dept}
              scenarios={(scenarios ?? []).filter((s) => s.department_id === dept.id)}
              comerciales={(comerciales ?? []).filter((c) => c.department_id === dept.id)}
              allScenarios={scenarios ?? []}
              onEditDept={() => setDeptModal(dept)}
              onNewScenario={() => setScenarioModal({ scenario: null, departmentId: dept.id })}
              onEditScenario={(s) => setScenarioModal({ scenario: s, departmentId: s.department_id ?? dept.id })}
              onTestScenario={(s) => setTesting(s)}
              onNewComercial={() => setComercialModal({ comercial: null, departmentId: dept.id })}
              onEditComercial={(c) => setComercialModal({ comercial: c, departmentId: c.department_id ?? dept.id })}
              onChanged={invalidate}
            />
          ))}
        </div>
      )}

      {huerfanos.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-lg font-semibold text-amber-300">Personalidades sin departamento</h3>
          <p className="text-sm text-muted">
            Estas personalidades no están asignadas a ningún departamento. Edítalas para asignarlas.
          </p>
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {huerfanos.map((s) => (
              <PersonalidadCard
                key={s.id}
                scenario={s}
                onEdit={() => setScenarioModal({ scenario: s, departmentId: s.department_id ?? null })}
                onTest={() => setTesting(s)}
                onChanged={invalidate}
              />
            ))}
          </div>
        </section>
      )}

      <EvaluadoresPanel />

      {scenarioModal && (
        <PersonalidadModal
          scenario={scenarioModal.scenario}
          departmentId={scenarioModal.departmentId}
          departamentos={deptList}
          onClose={() => setScenarioModal(null)}
          onSaved={() => { setScenarioModal(null); invalidate(); }}
        />
      )}
      {comercialModal && (
        <ComercialModal
          comercial={comercialModal.comercial}
          departmentId={comercialModal.departmentId}
          scenarios={scenarios ?? []}
          departamentos={deptList}
          onClose={() => setComercialModal(null)}
          onSaved={() => { setComercialModal(null); invalidate(); }}
        />
      )}
      {deptModal && (
        <DepartmentModal
          dept={deptModal === "new" ? null : deptModal}
          onClose={() => setDeptModal(null)}
          onSaved={() => { setDeptModal(null); invalidate(); }}
        />
      )}
      {testing && <TestModal scenario={testing} onClose={() => setTesting(null)} />}
    </div>
  );
}

// ─── Department section ──────────────────────────────────────────────────────

function DepartmentSection({
  dept, scenarios, comerciales, allScenarios,
  onEditDept, onNewScenario, onEditScenario, onTestScenario,
  onNewComercial, onEditComercial, onChanged,
}: {
  dept: Departamento;
  scenarios: Scenario[];
  comerciales: Comercial[];
  allScenarios: Scenario[];
  onEditDept: () => void;
  onNewScenario: () => void;
  onEditScenario: (s: Scenario) => void;
  onTestScenario: (s: Scenario) => void;
  onNewComercial: () => void;
  onEditComercial: (c: Comercial) => void;
  onChanged: () => void;
}) {
  const faqsPorNivel = (n: string) => (dept.faqs ?? []).filter((f) => f.nivel === n).length;

  return (
    <section className="bg-card border border-border rounded-2xl p-5 space-y-5">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div className="space-y-1">
          <h3 className="text-lg font-semibold">{dept.nombre}</h3>
          <div className="flex flex-wrap items-center gap-1.5">
            {NIVELES.map((n) => (
              <span
                key={n}
                className={`text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[n]}`}
              >
                {n}
                {faqsPorNivel(n) > 0 ? ` · ${faqsPorNivel(n)} FAQ` : ""}
              </span>
            ))}
          </div>
        </div>
        <button
          onClick={onEditDept}
          className="text-sm rounded-lg border border-border px-3 py-1.5 hover:border-accent"
        >
          Configurar departamento
        </button>
      </div>

      {/* Personalidades */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="font-medium">Personalidades ({scenarios.length})</h4>
          <button onClick={onNewScenario} className="text-sm text-accent hover:underline">
            + Nueva personalidad
          </button>
        </div>
        {!scenarios.length ? (
          <p className="text-sm text-muted">Sin personalidades todavía en este departamento.</p>
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {scenarios.map((s) => (
              <PersonalidadCard
                key={s.id}
                scenario={s}
                onEdit={() => onEditScenario(s)}
                onTest={() => onTestScenario(s)}
                onChanged={onChanged}
              />
            ))}
          </div>
        )}
      </div>

      {/* Comerciales */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h4 className="font-medium">Comerciales ({comerciales.length})</h4>
          <button onClick={onNewComercial} className="text-sm text-accent hover:underline">
            + Comercial
          </button>
        </div>
        <p className="text-xs text-muted">
          El <strong>nombre</strong> debe coincidir con el alias que envía el CRM; por él se atribuye
          cada llamada y se aplica su nivel.
        </p>
        <div className="bg-bg/40 border border-border rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-bg/50 text-muted text-left">
              <tr>
                <th className="px-4 py-2 font-medium">Nombre</th>
                <th className="px-4 py-2 font-medium">Nivel</th>
                <th className="px-4 py-2 font-medium">Personalidad por defecto</th>
                <th className="px-4 py-2 font-medium">Activo</th>
                <th className="px-4 py-2"></th>
              </tr>
            </thead>
            <tbody>
              {!comerciales.length ? (
                <tr><td colSpan={5} className="px-4 py-3 text-muted">Sin comerciales todavía.</td></tr>
              ) : (
                comerciales.map((c) => (
                  <tr key={c.id} className="border-t border-border">
                    <td className="px-4 py-2">{c.nombre}</td>
                    <td className="px-4 py-2">
                      <span className={`text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[c.nivel ?? ""] ?? "border-border text-muted"}`}>
                        {c.nivel ?? "—"}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-muted">
                      {allScenarios.find((s) => s.id === c.default_scenario_id)?.nombre ?? "—"}
                    </td>
                    <td className="px-4 py-2">{c.activo ? "Sí" : "No"}</td>
                    <td className="px-4 py-2 text-right whitespace-nowrap">
                      <EvaluarNivelButton comercial={c} onChanged={onChanged} />
                      <span className="text-border mx-2">·</span>
                      <button onClick={() => onEditComercial(c)} className="text-accent hover:underline">Editar</button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}

// ─── Personalidad card ───────────────────────────────────────────────────────

function PersonalidadCard({
  scenario: s, onEdit, onTest, onChanged,
}: {
  scenario: Scenario;
  onEdit: () => void;
  onTest: () => void;
  onChanged: () => void;
}) {
  const [open, setOpen] = useState(false);
  const toggle = useMutation({
    mutationFn: () => simulacrosApi.updateScenario(s.id, { ...stripId(s), activo: !s.activo }),
    onSuccess: onChanged,
  });
  const remove = useMutation({
    mutationFn: () => simulacrosApi.deleteScenario(s.id),
    onSuccess: onChanged,
  });

  return (
    <div className={`bg-card border rounded-2xl p-4 space-y-3 ${s.activo ? "border-border" : "border-border opacity-60"}`}>
      <div className="flex items-start justify-between gap-2">
        <h4 className="font-medium leading-snug">{s.nombre}</h4>
        <span className={`shrink-0 text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[s.dificultad] ?? "border-border text-muted"}`}>
          {s.dificultad}
        </span>
      </div>
      {s.producto && <p className="text-xs text-muted">{s.producto}</p>}
      <p className="text-sm text-zinc-300 line-clamp-3">{s.persona}</p>

      {open && (
        <div className="space-y-2 text-sm border-t border-border pt-3">
          <Field label="Objeciones" value={s.objeciones} />
          <Field label="FAQs propias" value={s.faqs} />
          <Field label="Situación (guion)" value={s.guion} />
          {s.retell_agent_id && <Field label="Agente Retell" value={s.retell_agent_id} />}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 pt-1 text-sm">
        <button onClick={() => setOpen((v) => !v)} className="text-accent hover:underline">
          {open ? "Ocultar" : "Ver detalle"}
        </button>
        <span className="text-border">·</span>
        <button onClick={onEdit} className="text-muted hover:text-white">Editar</button>
        <span className="text-border">·</span>
        <button onClick={onTest} className="text-muted hover:text-white">Probar</button>
        <span className="text-border">·</span>
        <button onClick={() => toggle.mutate()} className="text-muted hover:text-white">
          {s.activo ? "Desactivar" : "Activar"}
        </button>
        <span className="text-border">·</span>
        <button
          onClick={() => { if (confirm(`¿Borrar la personalidad “${s.nombre}”?`)) remove.mutate(); }}
          className="text-rose-400 hover:text-rose-300"
        >
          Borrar
        </button>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-xs uppercase tracking-wide text-muted">{label}</span>
      <p className="text-zinc-200 whitespace-pre-wrap">{value}</p>
    </div>
  );
}

// ─── Personalidad create/edit modal ──────────────────────────────────────────

function stripId(s: Scenario): ScenarioInput {
  const { id: _id, ...rest } = s;
  return rest;
}

function PersonalidadModal({
  scenario, departmentId, departamentos, onClose, onSaved,
}: {
  scenario: Scenario | null;
  departmentId: string | null;
  departamentos: Departamento[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ScenarioInput>(
    scenario
      ? stripId(scenario)
      : { ...EMPTY_SCENARIO, department_id: departmentId },
  );
  const save = useMutation({
    mutationFn: () =>
      scenario
        ? simulacrosApi.updateScenario(scenario.id, form)
        : simulacrosApi.createScenario(form),
    onSuccess: onSaved,
  });
  const set = (k: keyof ScenarioInput, v: string | boolean | null) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <Modal title={scenario ? "Editar personalidad" : "Nueva personalidad"} onClose={onClose}>
      <div className="space-y-3">
        <Input label="Nombre de la persona IA" value={form.nombre} onChange={(v) => set("nombre", v)} />
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Departamento</span>
            <select
              value={form.department_id ?? ""}
              onChange={(e) => set("department_id", e.target.value || null)}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              <option value="">— sin departamento —</option>
              {departamentos.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
            </select>
          </label>
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Dificultad (nivel)</span>
            <select
              value={form.dificultad}
              onChange={(e) => set("dificultad", e.target.value)}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              {NIVELES.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
        </div>
        <Input label="Producto" value={form.producto ?? ""} onChange={(v) => set("producto", v)} />
        <TextArea label="Persona (perfil del alumno IA)" value={form.persona} onChange={(v) => set("persona", v)} />
        <TextArea label="Objeciones" value={form.objeciones} onChange={(v) => set("objeciones", v)} />
        <TextArea label="FAQs propias de la personalidad" value={form.faqs} onChange={(v) => set("faqs", v)} />
        <p className="text-xs text-muted -mt-1">
          Se suman a las FAQs comunes del nivel del departamento.
        </p>
        <TextArea label="Situación (guion)" value={form.guion} onChange={(v) => set("guion", v)} rows={4} />
        <Input label="Agente Retell (opcional, para voz distinta)" value={form.retell_agent_id ?? ""} onChange={(v) => set("retell_agent_id", v)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.activo} onChange={(e) => set("activo", e.target.checked)} />
          Activa
        </label>
        {save.isError && <p className="text-sm text-rose-400">No se pudo guardar.</p>}
      </div>
      <ModalActions onClose={onClose} onSave={() => save.mutate()} saving={save.isPending} disabled={!form.nombre.trim()} />
    </Modal>
  );
}

// ─── Comercial modal ─────────────────────────────────────────────────────────

function ComercialModal({
  comercial, departmentId, scenarios, departamentos, onClose, onSaved,
}: {
  comercial: Comercial | null;
  departmentId: string | null;
  scenarios: Scenario[];
  departamentos: Departamento[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const initialDept = comercial?.department_id ?? departmentId ?? (departamentos[0]?.id ?? null);
  const [form, setForm] = useState<ComercialInput>(
    comercial
      ? {
          extension: comercial.extension, nombre: comercial.nombre, activo: comercial.activo,
          default_scenario_id: comercial.default_scenario_id,
          department_id: comercial.department_id ?? initialDept,
          nivel: comercial.nivel ?? NIVELES[0],
        }
      : {
          extension: "", nombre: "", activo: true, default_scenario_id: null,
          department_id: initialDept, nivel: NIVELES[0],
        },
  );
  const deptScenarios = scenarios.filter((s) => !form.department_id || s.department_id === form.department_id);
  const save = useMutation({
    mutationFn: () =>
      comercial
        ? simulacrosApi.updateComercial(comercial.id, form)
        : simulacrosApi.createComercial(form),
    onSuccess: onSaved,
  });
  const remove = useMutation({
    mutationFn: () => comercial ? simulacrosApi.deleteComercial(comercial.id) : Promise.resolve(),
    onSuccess: onSaved,
  });
  const set = (k: keyof ComercialInput, v: string | boolean | null) => setForm((f) => ({ ...f, [k]: v }));

  return (
    <Modal title={comercial ? "Editar comercial" : "Nuevo comercial"} onClose={onClose}>
      <div className="space-y-3">
        <Input label="Nombre (= alias que envía el CRM)" value={form.nombre} onChange={(v) => set("nombre", v)} />
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Departamento</span>
            <select
              value={form.department_id ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, department_id: e.target.value || null, default_scenario_id: null }))}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              <option value="">—</option>
              {departamentos.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
            </select>
          </label>
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Nivel de dificultad</span>
            <select
              value={form.nivel ?? ""}
              onChange={(e) => set("nivel", e.target.value || null)}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Personalidad por defecto (opcional)</span>
          <select
            value={form.default_scenario_id ?? ""}
            onChange={(e) => set("default_scenario_id", e.target.value || null)}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">— (el sistema elige por nivel) —</option>
            {deptScenarios.map((s) => <option key={s.id} value={s.id}>{s.nombre} ({s.dificultad})</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={form.activo} onChange={(e) => set("activo", e.target.checked)} />
          Activo
        </label>
      </div>
      <div className="flex items-center justify-between pt-4">
        {comercial ? (
          <button
            onClick={() => { if (confirm("¿Borrar comercial?")) remove.mutate(); }}
            className="text-sm text-rose-400 hover:text-rose-300"
          >
            Borrar
          </button>
        ) : <span />}
        <div className="flex gap-2">
          <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending || !form.nombre.trim()}
            className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90 disabled:opacity-50"
          >
            {save.isPending ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Department modal (nombre + FAQs comunes estructuradas) ───────────────────

function DepartmentModal({
  dept, onClose, onSaved,
}: {
  dept: Departamento | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [nombre, setNombre] = useState(dept?.nombre ?? "");
  const [faqs, setFaqs] = useState<FaqItem[]>(dept?.faqs ? [...dept.faqs] : []);
  const [err, setErr] = useState("");

  const save = useMutation({
    mutationFn: () => {
      const clean = faqs.filter((f) => f.pregunta.trim() || f.respuesta_esperada.trim());
      const body: DepartamentoInput = {
        nombre: nombre.trim(),
        faqs: clean,
        reglas: (dept?.reglas as Array<Record<string, unknown>>) ?? [],
        auto_evaluar: dept?.auto_evaluar ?? true,
        project_id: dept?.project_id ?? null,
        activo: dept?.activo ?? true,
      };
      return dept ? simulacrosApi.updateDepartamento(dept.id, body) : simulacrosApi.createDepartamento(body);
    },
    onSuccess: () => { setErr(""); onSaved(); },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Error al guardar"),
  });
  const remove = useMutation({
    mutationFn: () => dept ? simulacrosApi.deleteDepartamento(dept.id) : Promise.resolve(),
    onSuccess: onSaved,
  });

  const addFaq = () => setFaqs((f) => [...f, { pregunta: "", respuesta_esperada: "", nivel: "medio" }]);
  const setFaq = (i: number, k: keyof FaqItem, v: string) =>
    setFaqs((f) => f.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
  const delFaq = (i: number) => setFaqs((f) => f.filter((_, j) => j !== i));

  return (
    <Modal title={dept ? `Configurar — ${dept.nombre}` : "Nuevo departamento"} onClose={onClose}>
      <div className="space-y-4">
        <Input label="Nombre del departamento" value={nombre} onChange={setNombre} />

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted">FAQs comunes (por nivel)</span>
            <button onClick={addFaq} className="text-sm text-accent hover:underline">+ Añadir FAQ</button>
          </div>
          <p className="text-xs text-muted -mt-1">
            Cada FAQ: pregunta + respuesta esperada + nivel. Se inyectan en la llamada según el nivel
            de la persona IA.
          </p>
          {!faqs.length ? (
            <p className="text-xs text-muted">Sin FAQs todavía. Añade la primera con “+ Añadir FAQ”.</p>
          ) : (
            <div className="space-y-3">
              {faqs.map((f, i) => (
                <div key={i} className="rounded-xl border border-border p-3 space-y-2 bg-bg/40">
                  <div className="flex items-center justify-between gap-2">
                    <select
                      value={f.nivel}
                      onChange={(e) => setFaq(i, "nivel", e.target.value)}
                      className={`text-xs px-2 py-1 rounded-lg border bg-bg ${DIFF_COLOR[f.nivel] ?? "border-border"}`}
                    >
                      {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
                    </select>
                    <button onClick={() => delFaq(i)} className="text-xs text-rose-400 hover:text-rose-300">Quitar</button>
                  </div>
                  <input
                    value={f.pregunta}
                    onChange={(e) => setFaq(i, "pregunta", e.target.value)}
                    placeholder="Pregunta"
                    className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm"
                  />
                  <textarea
                    value={f.respuesta_esperada}
                    onChange={(e) => setFaq(i, "respuesta_esperada", e.target.value)}
                    placeholder="Respuesta esperada"
                    rows={2}
                    className="w-full bg-bg border border-border rounded-lg px-3 py-2 text-sm resize-y"
                  />
                </div>
              ))}
            </div>
          )}
        </div>
        {err && <p className="text-sm text-rose-400">{err}</p>}
      </div>

      <div className="flex items-center justify-between pt-4">
        {dept ? (
          <button
            onClick={() => { if (confirm(`¿Borrar el departamento “${dept.nombre}”? Sus personalidades y comerciales quedarán sin departamento.`)) remove.mutate(); }}
            className="text-sm text-rose-400 hover:text-rose-300"
          >
            Borrar departamento
          </button>
        ) : <span />}
        <div className="flex gap-2">
          <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
          <button
            onClick={() => save.mutate()}
            disabled={save.isPending || !nombre.trim()}
            className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90 disabled:opacity-50"
          >
            {save.isPending ? "Guardando…" : "Guardar"}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ─── Test (test-ingest) modal ────────────────────────────────────────────────

function TestModal({ scenario, onClose }: { scenario: Scenario; onClose: () => void }) {
  const [transcript, setTranscript] = useState("");
  const [agente, setAgente] = useState("Asesora de prueba");
  const run = useMutation({
    mutationFn: () =>
      simulacrosApi.testIngest({ transcript, agente_nombre: agente, scenario_id: scenario.id }),
  });

  return (
    <Modal title={`Probar personalidad — ${scenario.nombre}`} onClose={onClose}>
      <p className="text-sm text-muted mb-3">
        Pega una transcripción de ejemplo (sin teléfono). Se evaluará con la rúbrica y aparecerá en Resultados.
      </p>
      <div className="space-y-3">
        <Input label="Nombre de la asesora" value={agente} onChange={setAgente} />
        <TextArea label="Transcripción" value={transcript} onChange={setTranscript} rows={8} />
        {run.isError && <p className="text-sm text-rose-400">No se pudo lanzar (¿falta la API key de OpenAI?).</p>}
        {run.data && (
          <div className="text-sm rounded-lg border border-emerald-800 bg-emerald-950/30 p-3 space-y-1">
            <p className="text-emerald-300">Simulacro creado: {run.data.analysis_id}</p>
            <Link href={`/dashboard/detail?id=${run.data.analysis_id}`} className="text-accent hover:underline">
              Ver resultado →
            </Link>
          </div>
        )}
      </div>
      <ModalActions
        onClose={onClose}
        onSave={() => run.mutate()}
        saving={run.isPending}
        disabled={!transcript.trim()}
        saveLabel="Lanzar"
      />
    </Modal>
  );
}

// ─── Nivel: evaluar ahora ───────────────────────────────────────────────────

function EvaluarNivelButton({ comercial, onChanged }: { comercial: Comercial; onChanged: () => void }) {
  const m = useMutation({
    mutationFn: () => simulacrosApi.evaluateLevel(comercial.id),
    onSuccess: (r) => {
      if (r.changed) onChanged();
      alert(
        r.changed
          ? `${comercial.nombre}: ${r.from} → ${r.nivel}\n(${r.reason})`
          : `${comercial.nombre}: sin cambio de nivel.\n(${r.reason})`,
      );
    },
  });
  return (
    <button onClick={() => m.mutate()} disabled={m.isPending} className="text-muted hover:text-white">
      {m.isPending ? "…" : "Evaluar nivel"}
    </button>
  );
}

// ─── Evaluadores (cómo se puntúa la llamada) ─────────────────────────────────

function EvaluadoresPanel() {
  const { data } = useQuery({ queryKey: ["sim-evaluadores"], queryFn: simulacrosApi.getEvaluadores });
  if (!data) return <p className="text-muted">Cargando evaluadores…</p>;
  return <EvaluadoresForm initial={data} />;
}

function EvaluadoresForm({ initial }: { initial: Evaluadores }) {
  const qc = useQueryClient();
  const [auditor, setAuditor] = useState(initial.auditor_prompt);
  const [feedback, setFeedback] = useState(initial.feedback_prompt);
  const [report, setReport] = useState(initial.report_prompt);
  const [rubric, setRubric] = useState(JSON.stringify(initial.rules_table, null, 2));
  const [err, setErr] = useState("");
  const save = useMutation({
    mutationFn: () => {
      let r: Array<Record<string, unknown>>;
      try { r = JSON.parse(rubric); } catch { throw new Error("La rúbrica (JSON) no es válida."); }
      return simulacrosApi.putEvaluadores({
        auditor_prompt: auditor, feedback_prompt: feedback, report_prompt: report, rules_table: r,
      });
    },
    onSuccess: () => { setErr(""); qc.invalidateQueries({ queryKey: ["sim-evaluadores"] }); },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Error al guardar"),
  });

  return (
    <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div>
        <h3 className="text-lg font-semibold">Evaluadores — cómo se puntúa la llamada</h3>
        <p className="text-sm text-muted">
          Los “moderadores” que evalúan la transcripción. Edita sus instrucciones y la rúbrica.
        </p>
      </div>
      <TextArea label="Auditor (puntúa cada parámetro de la rúbrica)" value={auditor} onChange={setAuditor} rows={6} />
      <TextArea label="Coach (redacta el feedback a la asesora)" value={feedback} onChange={setFeedback} rows={4} />
      <TextArea label="Composer (redacta el informe)" value={report} onChange={setReport} rows={4} />
      <label className="text-sm space-y-1 block">
        <span className="text-muted">Rúbrica (JSON: id, name, weight, dimension, criteria, description)</span>
        <textarea
          value={rubric}
          onChange={(e) => setRubric(e.target.value)}
          rows={12}
          className="w-full bg-bg border border-border rounded-lg px-3 py-2 font-mono text-xs resize-y"
        />
      </label>
      <div className="flex items-center gap-3">
        <button
          onClick={() => save.mutate()}
          disabled={save.isPending}
          className="text-sm rounded-lg bg-accent text-black font-medium px-4 py-2 hover:opacity-90 disabled:opacity-50"
        >
          {save.isPending ? "Guardando…" : "Guardar evaluadores"}
        </button>
        {err && <span className="text-sm text-rose-400">{err}</span>}
        {save.isSuccess && !err && <span className="text-sm text-emerald-300">Guardado.</span>}
      </div>
    </section>
  );
}

// ─── Generic modal primitives ────────────────────────────────────────────────

function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 overflow-auto" onClick={onClose}>
      <div className="bg-card border border-border rounded-2xl p-5 w-full max-w-2xl my-8" onClick={(e) => e.stopPropagation()}>
        <h3 className="text-lg font-semibold mb-4">{title}</h3>
        {children}
      </div>
    </div>
  );
}

function ModalActions({
  onClose, onSave, saving, disabled, saveLabel = "Guardar",
}: {
  onClose: () => void;
  onSave: () => void;
  saving: boolean;
  disabled?: boolean;
  saveLabel?: string;
}) {
  return (
    <div className="flex justify-end gap-2 pt-4">
      <button onClick={onClose} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">Cancelar</button>
      <button
        onClick={onSave}
        disabled={saving || disabled}
        className="text-sm rounded-lg bg-accent text-black font-medium px-3 py-2 hover:opacity-90 disabled:opacity-50"
      >
        {saving ? "…" : saveLabel}
      </button>
    </div>
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

function TextArea({ label, value, onChange, rows = 3 }: { label: string; value: string; onChange: (v: string) => void; rows?: number }) {
  return (
    <label className="text-sm space-y-1 block">
      <span className="text-muted">{label}</span>
      <textarea
        value={value}
        rows={rows}
        onChange={(e) => onChange(e.target.value)}
        className="w-full bg-bg border border-border rounded-lg px-3 py-2 resize-y"
      />
    </label>
  );
}
