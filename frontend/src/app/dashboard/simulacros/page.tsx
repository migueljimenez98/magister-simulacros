"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  simulacrosApi,
  type Departamento,
  type DepartamentoInput,
  type Evaluador,
  type EvaluadorInput,
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

type ScenarioModalState = { scenario: Scenario | null; departmentId: string | null; draft?: ScenarioInput };

export default function SimulacrosPage() {
  const qc = useQueryClient();
  const { data: scenarios, isLoading } = useQuery({
    queryKey: ["sim-scenarios"],
    queryFn: simulacrosApi.listScenarios,
  });
  const { data: departamentos } = useQuery({
    queryKey: ["sim-departamentos"],
    queryFn: simulacrosApi.listDepartamentos,
  });
  const { data: evaluadores } = useQuery({
    queryKey: ["sim-evaluadores-cat"],
    queryFn: simulacrosApi.listEvaluadores,
  });

  const [scenarioModal, setScenarioModal] = useState<ScenarioModalState | null>(null);
  const [deptModal, setDeptModal] = useState<Departamento | "new" | null>(null);
  const [generarModal, setGenerarModal] = useState<{ departmentId: string | null } | null>(null);
  const [testing, setTesting] = useState<Scenario | null>(null);
  const [selectedDept, setSelectedDept] = useState("");

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["sim-scenarios"] });
    qc.invalidateQueries({ queryKey: ["sim-comerciales"] });
    qc.invalidateQueries({ queryKey: ["sim-departamentos"] });
    qc.invalidateQueries({ queryKey: ["sim-evaluadores-cat"] });
  };

  const deptList = departamentos ?? [];
  const knownDeptIds = new Set(deptList.map((d) => d.id));
  const huerfanos = (scenarios ?? []).filter(
    (s) => !s.department_id || !knownDeptIds.has(s.department_id),
  );

  const deptsToShow = deptList.filter((d) => !selectedDept || d.id === selectedDept);

  return (
    <div className="w-full space-y-8">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4 flex-wrap">
          <h2 className="text-xl font-semibold">Configuración</h2>
          <select
            value={selectedDept}
            onChange={(e) => setSelectedDept(e.target.value)}
            className="text-sm bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">Todos los departamentos</option>
            {deptList.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
          </select>
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
          {deptsToShow.map((dept) => (
            <DepartmentSection
              key={dept.id}
              dept={dept}
              scenarios={(scenarios ?? []).filter((s) => s.department_id === dept.id)}
              evaluadorNombre={evaluadores?.find((e) => e.id === dept.evaluador_id)?.nombre ?? null}
              onEditDept={() => setDeptModal(dept)}
              onNewScenario={() => setScenarioModal({ scenario: null, departmentId: dept.id })}
              onGenerar={() => setGenerarModal({ departmentId: dept.id })}
              onEditScenario={(s) => setScenarioModal({ scenario: s, departmentId: s.department_id ?? dept.id })}
              onTestScenario={(s) => setTesting(s)}
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
          <PersonalidadTable
            scenarios={huerfanos}
            onEdit={(s) => setScenarioModal({ scenario: s, departmentId: s.department_id ?? null })}
            onTest={(s) => setTesting(s)}
            onChanged={invalidate}
          />
        </section>
      )}

      <EvaluadoresCatalog />

      {scenarioModal && (
        <PersonalidadModal
          scenario={scenarioModal.scenario}
          departmentId={scenarioModal.departmentId}
          draft={scenarioModal.draft}
          departamentos={deptList}
          onClose={() => setScenarioModal(null)}
          onSaved={() => { setScenarioModal(null); invalidate(); }}
        />
      )}
      {generarModal && (
        <GenerarPersonaModal
          departmentId={generarModal.departmentId}
          departamentos={deptList}
          onClose={() => setGenerarModal(null)}
          onGenerated={(draft) => {
            setGenerarModal(null);
            setScenarioModal({ scenario: null, departmentId: draft.department_id ?? generarModal.departmentId, draft });
          }}
        />
      )}
      {deptModal && (
        <DepartmentModal
          dept={deptModal === "new" ? null : deptModal}
          evaluadores={evaluadores ?? []}
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
  dept, scenarios, evaluadorNombre,
  onEditDept, onNewScenario, onGenerar, onEditScenario, onTestScenario, onChanged,
}: {
  dept: Departamento;
  scenarios: Scenario[];
  evaluadorNombre: string | null;
  onEditDept: () => void;
  onNewScenario: () => void;
  onGenerar: () => void;
  onEditScenario: (s: Scenario) => void;
  onTestScenario: (s: Scenario) => void;
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
            <span className="text-xs px-2 py-0.5 rounded-full border border-border text-muted">
              Evaluador: {evaluadorNombre ?? "por defecto"}
            </span>
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
          <div className="flex gap-2">
            <button onClick={onGenerar} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">
              ✨ Generar con IA
            </button>
            <button onClick={onNewScenario} className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent">
              + Nueva personalidad
            </button>
          </div>
        </div>
        {!scenarios.length ? (
          <p className="text-sm text-muted">Sin personalidades todavía en este departamento.</p>
        ) : (
          <PersonalidadTable scenarios={scenarios} onEdit={onEditScenario} onTest={onTestScenario} onChanged={onChanged} />
        )}
      </div>

      <p className="text-xs text-muted">
        Los comerciales/agentes se gestionan en la pestaña <strong>Agentes</strong>.
      </p>
    </section>
  );
}

// ─── Personalidades: tabla ───────────────────────────────────────────────────

const NIVEL_ORDER: Record<string, number> = { facil: 0, medio: 1, dificil: 2 };

function PersonalidadTable({
  scenarios, onEdit, onTest, onChanged,
}: {
  scenarios: Scenario[];
  onEdit: (s: Scenario) => void;
  onTest: (s: Scenario) => void;
  onChanged: () => void;
}) {
  const [sort, setSort] = useState<{ field: "nombre" | "dificultad"; dir: 1 | -1 }>({ field: "dificultad", dir: 1 });
  const sorted = [...scenarios].sort((a, b) => {
    const cmp = sort.field === "nombre"
      ? a.nombre.localeCompare(b.nombre)
      : (NIVEL_ORDER[a.dificultad] ?? 9) - (NIVEL_ORDER[b.dificultad] ?? 9);
    return cmp * sort.dir;
  });
  const toggle = (field: "nombre" | "dificultad") =>
    setSort((s) => (s.field === field ? { field, dir: (s.dir === 1 ? -1 : 1) as 1 | -1 } : { field, dir: 1 }));
  const arrow = (field: string) => (sort.field === field ? (sort.dir === 1 ? " ▲" : " ▼") : "");

  return (
    <div className="bg-bg/40 border border-border rounded-xl overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-bg/50 text-muted text-left">
          <tr>
            <th onClick={() => toggle("nombre")} className="px-4 py-2 font-medium cursor-pointer select-none hover:text-white whitespace-nowrap">Nombre{arrow("nombre")}</th>
            <th onClick={() => toggle("dificultad")} className="px-4 py-2 font-medium cursor-pointer select-none hover:text-white whitespace-nowrap">Dificultad{arrow("dificultad")}</th>
            <th className="px-4 py-2 font-medium">Producto</th>
            <th className="px-4 py-2 font-medium">Persona</th>
            <th className="px-4 py-2 font-medium">Estado</th>
            <th className="px-4 py-2"></th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((s) => (
            <PersonalidadRow key={s.id} scenario={s} onEdit={() => onEdit(s)} onTest={() => onTest(s)} onChanged={onChanged} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PersonalidadRow({
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
    <>
      <tr className={`border-t border-border align-top ${s.activo ? "" : "opacity-60"}`}>
        <td className="px-4 py-2 font-medium">{s.nombre}</td>
        <td className="px-4 py-2">
          <span className={`text-xs px-2 py-0.5 rounded-full border ${DIFF_COLOR[s.dificultad] ?? "border-border text-muted"}`}>{s.dificultad}</span>
        </td>
        <td className="px-4 py-2 text-muted truncate max-w-[160px]">{s.producto || "—"}</td>
        <td className="px-4 py-2 text-muted truncate max-w-[320px]">{s.persona || "—"}</td>
        <td className="px-4 py-2 whitespace-nowrap">
          {s.activo ? <span className="text-emerald-300 text-xs">Activa</span> : <span className="text-muted text-xs">Inactiva</span>}
        </td>
        <td className="px-4 py-2 text-right whitespace-nowrap">
          <button onClick={() => setOpen((v) => !v)} className="text-accent hover:underline">{open ? "Ocultar" : "Ver"}</button>
          <span className="text-border mx-1.5">·</span>
          <button onClick={onEdit} className="text-muted hover:text-white">Editar</button>
          <span className="text-border mx-1.5">·</span>
          <button onClick={onTest} className="text-muted hover:text-white">Probar</button>
          <span className="text-border mx-1.5">·</span>
          <button onClick={() => toggle.mutate()} className="text-muted hover:text-white">{s.activo ? "Desactivar" : "Activar"}</button>
          <span className="text-border mx-1.5">·</span>
          <button onClick={() => { if (confirm(`¿Borrar la personalidad “${s.nombre}”?`)) remove.mutate(); }} className="text-rose-400 hover:text-rose-300">Borrar</button>
        </td>
      </tr>
      {open && (
        <tr className="border-t border-border bg-bg/20">
          <td colSpan={6} className="px-4 py-3">
            <div className="grid md:grid-cols-2 gap-3 text-sm">
              <Field label="Persona" value={s.persona} />
              <Field label="Objeciones" value={s.objeciones} />
              <Field label="FAQs propias" value={s.faqs} />
              <Field label="Situación (guion)" value={s.guion} />
              {s.retell_agent_id && <Field label="Agente Retell" value={s.retell_agent_id} />}
            </div>
          </td>
        </tr>
      )}
    </>
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
  scenario, departmentId, draft, departamentos, onClose, onSaved,
}: {
  scenario: Scenario | null;
  departmentId: string | null;
  draft?: ScenarioInput;
  departamentos: Departamento[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<ScenarioInput>(
    scenario
      ? stripId(scenario)
      : draft
        ? { ...EMPTY_SCENARIO, ...draft, department_id: draft.department_id ?? departmentId }
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
    <Modal title={scenario ? "Editar personalidad" : draft ? "Nueva personalidad (generada con IA — revísala)" : "Nueva personalidad"} onClose={onClose}>
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

// ─── Generar Persona IA (con IA) ─────────────────────────────────────────────

function GenerarPersonaModal({
  departmentId, departamentos, onClose, onGenerated,
}: {
  departmentId: string | null;
  departamentos: Departamento[];
  onClose: () => void;
  onGenerated: (draft: ScenarioInput) => void;
}) {
  const [deptId, setDeptId] = useState(departmentId ?? "");
  const [dificultad, setDificultad] = useState<string>("medio");
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const gen = useMutation({
    mutationFn: () =>
      simulacrosApi.generarPersona({
        nombre: nombre.trim(), dificultad, descripcion, department_id: deptId || null,
      }),
    onSuccess: (draft) => onGenerated(draft),
  });

  return (
    <Modal title="Generar persona IA" onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-muted">
          La IA crea una persona realista (perfil, objeciones, motivo de la llamada) usando las FAQs
          del departamento del nivel elegido. Luego la revisas y la guardas.
        </p>
        <div className="grid grid-cols-2 gap-3">
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Departamento</span>
            <select
              value={deptId}
              onChange={(e) => setDeptId(e.target.value)}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              <option value="">— sin departamento —</option>
              {departamentos.map((d) => <option key={d.id} value={d.id}>{d.nombre}</option>)}
            </select>
          </label>
          <label className="text-sm space-y-1 block">
            <span className="text-muted">Dificultad</span>
            <select
              value={dificultad}
              onChange={(e) => setDificultad(e.target.value)}
              className="w-full bg-bg border border-border rounded-lg px-3 py-2"
            >
              {NIVELES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
          </label>
        </div>
        <Input label="Nombre de la persona" value={nombre} onChange={setNombre} />
        <TextArea
          label="Descripción / cómo quieres que se comporte (perfil, motivo, carácter…)"
          value={descripcion}
          onChange={setDescripcion}
          rows={4}
        />
        {gen.isError && <p className="text-sm text-rose-400">No se pudo generar (¿falta la API key de OpenAI?).</p>}
      </div>
      <ModalActions
        onClose={onClose}
        onSave={() => gen.mutate()}
        saving={gen.isPending}
        disabled={!nombre.trim()}
        saveLabel={gen.isPending ? "Generando…" : "Generar"}
      />
    </Modal>
  );
}

// ─── Department modal (nombre + FAQs comunes estructuradas) ───────────────────

function DepartmentModal({
  dept, evaluadores, onClose, onSaved,
}: {
  dept: Departamento | null;
  evaluadores: Evaluador[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [nombre, setNombre] = useState(dept?.nombre ?? "");
  const [evaluadorId, setEvaluadorId] = useState(dept?.evaluador_id ?? "");
  const [faqs, setFaqs] = useState<FaqItem[]>(dept?.faqs ? [...dept.faqs] : []);
  const [err, setErr] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);
  const [importNivel, setImportNivel] = useState("");
  const importMut = useMutation({
    mutationFn: (file: File) => simulacrosApi.importFaqs(file, importNivel || undefined),
    onSuccess: (r) => {
      setFaqs((f) => [...f, ...r.faqs]);
      if (fileRef.current) fileRef.current.value = "";
    },
  });

  const save = useMutation({
    mutationFn: () => {
      const clean = faqs.filter((f) => f.pregunta.trim() || f.respuesta_esperada.trim());
      const body: DepartamentoInput = {
        nombre: nombre.trim(),
        faqs: clean,
        evaluador_id: evaluadorId || null,
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

        <label className="text-sm space-y-1 block">
          <span className="text-muted">Evaluador (cómo se puntúan sus llamadas)</span>
          <select
            value={evaluadorId}
            onChange={(e) => setEvaluadorId(e.target.value)}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2"
          >
            <option value="">— evaluador por defecto —</option>
            {evaluadores.map((e) => <option key={e.id} value={e.id}>{e.nombre}</option>)}
          </select>
        </label>

        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm text-muted">FAQs comunes (por nivel)</span>
            <button onClick={addFaq} className="text-sm text-accent hover:underline">+ Añadir FAQ</button>
          </div>
          <p className="text-xs text-muted -mt-1">
            Cada FAQ: pregunta + respuesta esperada + nivel. Se inyectan en la llamada según el nivel
            de la persona IA.
          </p>

          {/* Importar desde PDF/TXT (la IA estructura las FAQs) */}
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-dashed border-border p-3 bg-bg/30">
            <span className="text-xs text-muted">Importar PDF/TXT:</span>
            <select
              value={importNivel}
              onChange={(e) => setImportNivel(e.target.value)}
              className="text-xs bg-bg border border-border rounded-lg px-2 py-1"
              title="Nivel a asignar (o que decida la IA)"
            >
              <option value="">nivel: que decida la IA</option>
              {NIVELES.map((n) => <option key={n} value={n}>nivel: {n}</option>)}
            </select>
            <input
              ref={fileRef}
              type="file"
              accept=".pdf,.txt,.md,text/plain,application/pdf"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) importMut.mutate(f);
              }}
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={importMut.isPending}
              className="text-xs rounded-lg border border-border px-3 py-1 hover:border-accent disabled:opacity-50"
            >
              {importMut.isPending ? "Extrayendo…" : "Elegir archivo"}
            </button>
            {importMut.isSuccess && (
              <span className="text-xs text-emerald-300">+{importMut.data.faqs.length} FAQs añadidas (revísalas y guarda).</span>
            )}
            {importMut.isError && (
              <span className="text-xs text-rose-400">No se pudo extraer (¿PDF escaneado? solo texto plano).</span>
            )}
          </div>
          <p className="text-[11px] text-muted -mt-1">
            La IA (misma API key del evaluador) extrae las FAQs en texto plano; no se admiten PDFs escaneados.
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

// ─── Evaluadores (catálogo reutilizable, se asignan a departamentos) ──────────

function EvaluadoresCatalog() {
  const qc = useQueryClient();
  const { data: evaluadores } = useQuery({
    queryKey: ["sim-evaluadores-cat"],
    queryFn: simulacrosApi.listEvaluadores,
  });
  const [editing, setEditing] = useState<Evaluador | "new" | null>(null);
  const [draft, setDraft] = useState<EvaluadorInput | null>(null);
  const [generar, setGenerar] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["sim-evaluadores-cat"] });

  return (
    <section className="bg-card border border-border rounded-2xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold">Evaluadores</h3>
          <p className="text-sm text-muted">
            Cómo se puntúa la llamada (auditor + coach + composer + rúbrica). Se asigna uno a cada
            departamento.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setGenerar(true)}
            className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent"
          >
            ✨ Generar con IA
          </button>
          <button
            onClick={() => { setDraft(null); setEditing("new"); }}
            className="text-sm rounded-lg border border-border px-3 py-2 hover:border-accent"
          >
            + Nuevo evaluador
          </button>
        </div>
      </div>
      {!evaluadores?.length ? (
        <p className="text-sm text-muted">Sin evaluadores. Crea el primero con “+ Nuevo evaluador”.</p>
      ) : (
        <div className="grid gap-2">
          {evaluadores.map((e) => (
            <div key={e.id} className="flex items-center justify-between rounded-xl border border-border px-4 py-2 bg-bg/40">
              <div>
                <span className="font-medium">{e.nombre}</span>
                <span className="text-xs text-muted ml-2">{(e.rules_table?.length ?? 0)} parámetros</span>
              </div>
              <button onClick={() => setEditing(e)} className="text-sm text-accent hover:underline">Editar</button>
            </div>
          ))}
        </div>
      )}
      {editing && (
        <EvaluadorModal
          evaluador={editing === "new" ? null : editing}
          draft={editing === "new" ? draft ?? undefined : undefined}
          onClose={() => { setEditing(null); setDraft(null); }}
          onSaved={() => { setEditing(null); setDraft(null); invalidate(); }}
        />
      )}
      {generar && (
        <GenerarEvaluadorModal
          onClose={() => setGenerar(false)}
          onGenerated={(d) => { setGenerar(false); setDraft(d); setEditing("new"); }}
        />
      )}
    </section>
  );
}

function GenerarEvaluadorModal({
  onClose, onGenerated,
}: {
  onClose: () => void;
  onGenerated: (draft: EvaluadorInput) => void;
}) {
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const gen = useMutation({
    mutationFn: () => simulacrosApi.generarEvaluador({ nombre: nombre.trim() || undefined, descripcion }),
    onSuccess: (d) => onGenerated(d),
  });
  return (
    <Modal title="Generar evaluador con IA" onClose={onClose}>
      <div className="space-y-3">
        <p className="text-sm text-muted">
          Pega el <strong>guión</strong> o describe cómo debe ser la llamada. La IA crea la rúbrica
          (parámetros con pesos) y los prompts. Luego lo revisas y lo guardas.
        </p>
        <Input label="Nombre del evaluador (opcional)" value={nombre} onChange={setNombre} />
        <TextArea
          label="Guión / descripción de la llamada"
          value={descripcion}
          onChange={setDescripcion}
          rows={10}
        />
        {gen.isError && <p className="text-sm text-rose-400">No se pudo generar (¿falta la API key de OpenAI?).</p>}
      </div>
      <ModalActions
        onClose={onClose}
        onSave={() => gen.mutate()}
        saving={gen.isPending}
        disabled={!descripcion.trim()}
        saveLabel={gen.isPending ? "Generando…" : "Generar"}
      />
    </Modal>
  );
}

const EMPTY_EVALUADOR: EvaluadorInput = {
  nombre: "", auditor_prompt: "", feedback_prompt: "", report_prompt: "", rules_table: [],
};

function EvaluadorModal({
  evaluador, draft, onClose, onSaved,
}: {
  evaluador: Evaluador | null;
  draft?: EvaluadorInput;
  onClose: () => void;
  onSaved: () => void;
}) {
  const base = evaluador ?? draft ?? EMPTY_EVALUADOR;
  const [nombre, setNombre] = useState(base.nombre ?? "");
  const [auditor, setAuditor] = useState(base.auditor_prompt ?? "");
  const [feedback, setFeedback] = useState(base.feedback_prompt ?? "");
  const [report, setReport] = useState(base.report_prompt ?? "");
  const [rubric, setRubric] = useState(JSON.stringify(base.rules_table ?? [], null, 2));
  const [err, setErr] = useState("");

  const save = useMutation({
    mutationFn: () => {
      let r: Array<Record<string, unknown>>;
      try { r = JSON.parse(rubric); } catch { throw new Error("La rúbrica (JSON) no es válida."); }
      const body: EvaluadorInput = {
        nombre: nombre.trim(), auditor_prompt: auditor, feedback_prompt: feedback,
        report_prompt: report, rules_table: r,
      };
      return evaluador ? simulacrosApi.updateEvaluador(evaluador.id, body) : simulacrosApi.createEvaluador(body);
    },
    onSuccess: () => { setErr(""); onSaved(); },
    onError: (e: unknown) => setErr(e instanceof Error ? e.message : "Error al guardar"),
  });
  const remove = useMutation({
    mutationFn: () => evaluador ? simulacrosApi.deleteEvaluador(evaluador.id) : Promise.resolve(),
    onSuccess: onSaved,
  });

  return (
    <Modal title={evaluador ? `Editar evaluador — ${evaluador.nombre}` : draft ? "Nuevo evaluador (generado con IA — revísalo)" : "Nuevo evaluador"} onClose={onClose}>
      <div className="space-y-3">
        <Input label="Nombre del evaluador" value={nombre} onChange={setNombre} />
        <TextArea label="Auditor (puntúa cada parámetro de la rúbrica)" value={auditor} onChange={setAuditor} rows={5} />
        <TextArea label="Coach (redacta el feedback a la asesora)" value={feedback} onChange={setFeedback} rows={4} />
        <TextArea label="Composer (redacta el informe)" value={report} onChange={setReport} rows={4} />
        <label className="text-sm space-y-1 block">
          <span className="text-muted">Rúbrica (JSON: id, name, weight, dimension, criteria, description)</span>
          <textarea
            value={rubric}
            onChange={(e) => setRubric(e.target.value)}
            rows={10}
            className="w-full bg-bg border border-border rounded-lg px-3 py-2 font-mono text-xs resize-y"
          />
        </label>
        {err && <p className="text-sm text-rose-400">{err}</p>}
      </div>
      <div className="flex items-center justify-between pt-4">
        {evaluador ? (
          <button
            onClick={() => { if (confirm(`¿Borrar el evaluador “${evaluador.nombre}”?`)) remove.mutate(); }}
            className="text-sm text-rose-400 hover:text-rose-300"
          >
            Borrar
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
