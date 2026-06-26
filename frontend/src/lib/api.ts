/**
 * Cliente API mínimo de magister-simulacros. Token en localStorage.
 */
const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8002";
const TOKEN_KEY = "mqsim_token";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}
export function setToken(t: string | null): void {
  if (typeof window === "undefined") return;
  if (t) window.localStorage.setItem(TOKEN_KEY, t);
  else window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API ${status}`);
  }
}

function redirectToLogin(): void {
  setToken(null);
  if (typeof window !== "undefined") window.location.replace("/");
}
function isLoginPath(path: string): boolean {
  return path === "/api/auth/login";
}

async function request<T>(path: string, init: RequestInit & { json?: unknown } = {}): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    ...((init.headers as Record<string, string>) || {}),
  };
  let body = init.body;
  if (init.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(init.json);
  }
  const tok = getToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;

  const r = await fetch(`${BASE}${path}`, { ...init, headers, body });
  const ct = r.headers.get("content-type") || "";
  const payload = ct.includes("application/json") ? await r.json() : await r.text();
  if (!r.ok) {
    if (r.status === 401 && !isLoginPath(path)) {
      redirectToLogin();
      return new Promise(() => {});
    }
    throw new ApiError(r.status, payload);
  }
  return payload as T;
}

// Multipart (subida de ficheros): no fijamos Content-Type para que el navegador
// ponga el boundary; sí adjuntamos el token de auth.
async function requestForm<T>(path: string, form: FormData): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const tok = getToken();
  if (tok) headers["Authorization"] = `Bearer ${tok}`;
  const r = await fetch(`${BASE}${path}`, { method: "POST", headers, body: form });
  const ct = r.headers.get("content-type") || "";
  const payload = ct.includes("application/json") ? await r.json() : await r.text();
  if (!r.ok) {
    if (r.status === 401 && !isLoginPath(path)) {
      redirectToLogin();
      return new Promise(() => {});
    }
    throw new ApiError(r.status, payload);
  }
  return payload as T;
}

// ── Tipos ────────────────────────────────────────────────────────────────────
export interface LoginResp {
  access_token: string;
  user_id: string;
  email: string;
  role: string;
}

export interface ParamScore {
  score: number | null;
  max: number | null;
  note?: string;
  etiqueta?: string | null;
  observacion?: string | null;
  evidencia?: string[];
  gap?: string | null;
  dimension?: string;
  applied?: boolean;
}

export interface DimensionScore {
  applied: boolean;
  n_rules?: number;
  total?: number;
  ideal?: number;
  percent?: number;
}

export interface Analysis {
  id: string;
  project_id: string;
  numero: string;
  agente_nombre: string;
  escenario?: string | null;
  departamento?: string | null;
  call_date: string | null;
  status: "pending" | "fetching" | "scoring" | "composing" | "persisting" | "done" | "failed";
  total_score: number | null;
  ideal_score: number | null;
  percent_quality: number | null;
  feedback_message: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
  scores: Record<string, ParamScore>;
  scores_by_dimension: Record<string, DimensionScore>;
  feedback_by_vertical?: Record<string, string>;
  feedback_selected_tier?: string | null;
}

export interface AnalysisDetail extends Analysis {
  detailed_report: string | null;
  instruction: string | null;
  crm_snapshot: Record<string, unknown>;
  coach_validation_notes?: Array<Record<string, unknown>>;
}

export interface AnalysisListPage {
  items: Analysis[];
  total: number;
  limit: number;
  offset: number;
}

export interface AnalysisListParams {
  project_id?: string;
  agente?: string;
  status_filter?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

// ── Endpoints base ────────────────────────────────────────────────────────────
export const api = {
  login: (email: string, password: string) =>
    request<LoginResp>("/api/auth/login", { method: "POST", json: { email, password } }),
  me: () => request<{ user_id: string; role: string }>("/api/auth/me"),

  analyses: {
    list: (params?: AnalysisListParams) => {
      const entries: [string, string][] = [];
      for (const [k, v] of Object.entries(params || {})) {
        if (v === undefined || v === null || v === "") continue;
        entries.push([k, String(v)]);
      }
      const q = new URLSearchParams(entries).toString();
      return request<AnalysisListPage>(`/api/analyses${q ? `?${q}` : ""}`);
    },
    facets: (project_id?: string) => {
      const q = project_id ? `?project_id=${encodeURIComponent(project_id)}` : "";
      return request<{ agentes: string[]; estados: string[] }>(`/api/analyses/facets${q}`);
    },
    get: (id: string) => request<AnalysisDetail>(`/api/analyses/${id}`),
    delete: (id: string) => request<void>(`/api/analyses/${id}`, { method: "DELETE" }),
    redispatch: (id: string) =>
      request<Analysis>(`/api/analyses/${id}/redispatch`, { method: "POST" }),
    stats: (params?: { departamento?: string; agente?: string; desde?: string; hasta?: string }) => {
      const entries: [string, string][] = [];
      for (const [k, v] of Object.entries(params || {})) {
        if (v) entries.push([k, String(v)]);
      }
      const q = new URLSearchParams(entries).toString();
      return request<Stats>(`/api/analyses/stats${q ? `?${q}` : ""}`);
    },
  },
};

export interface Stats {
  total: number;
  scored: number;
  avg_percent: number | null;
  by_status: Record<string, number>;
  timeseries: { date: string; avg_percent: number | null; count: number }[];
  por_parametro: { id: string; name: string; avg_percent: number | null; count: number }[];
  por_dificultad: { dificultad: string; avg_percent: number | null; count: number }[];
  por_agente: AgenteRow[];
  agentes: string[];
  departamentos: string[];
}

export interface AgenteMembership {
  id: string;
  departamento: string;
  department_id: string | null;
  nivel: string | null;
  activo: boolean;
}
export interface AgenteRow {
  agente: string;
  count: number;
  avg_percent: number | null;
  nivel_actual: string | null;
  departamento_activo: string | null;
  nivel_recomendado: string | null;
  ultima_id: string | null;
  ultima_fecha: string | null;
  ultima_nota: number | null;
  ultimo_departamento: string | null;
  memberships: AgenteMembership[];
}

// ── Simulacros ────────────────────────────────────────────────────────────────
export interface Scenario {
  id: string;
  nombre: string;
  dificultad: string;
  producto: string | null;
  persona: string;
  objeciones: string;
  faqs: string;
  guion: string;
  retell_agent_id: string | null;
  activo: boolean;
  department_id?: string | null;
}
export type ScenarioInput = Omit<Scenario, "id">;

export interface Comercial {
  id: string;
  extension?: string | null;
  nombre: string;
  activo: boolean;
  default_scenario_id: string | null;
  department_id?: string | null;
  nivel?: string | null;
}
export type ComercialInput = Omit<Comercial, "id">;

export interface FaqItem {
  pregunta: string;
  respuesta_esperada: string;
  nivel: string;
}
export interface Departamento {
  id: string;
  nombre: string;
  niveles: string[];          // fijos: facil/medio/dificil
  faqs: FaqItem[];            // FAQs comunes estructuradas, por nivel
  evaluador_id: string | null;
  reglas: Array<Record<string, unknown>>;
  auto_evaluar: boolean;
  project_id: string | null;
  activo: boolean;
}
export interface DepartamentoInput {
  nombre: string;
  faqs: FaqItem[];
  evaluador_id?: string | null;
  reglas?: Array<Record<string, unknown>>;
  auto_evaluar?: boolean;
  project_id?: string | null;
  activo?: boolean;
}

export interface Evaluador {
  id: string;
  nombre: string;
  auditor_prompt: string;
  feedback_prompt: string;
  report_prompt: string;
  rules_table: Array<Record<string, unknown>>;
}
export type EvaluadorInput = Omit<Evaluador, "id">;

export interface Evaluadores {
  project_id: string;
  auditor_prompt: string;
  feedback_prompt: string;
  report_prompt: string;
  rules_table: Array<Record<string, unknown>>;
}

export interface LevelResult {
  changed: boolean;
  nivel?: string | null;
  from?: string;
  reason?: string;
  rule_id?: string;
}

export interface AnnouncePending {
  agente: string;
  from_number: string;
  scenario_id: string;
  age_s: number;
}

export interface AnnounceResult {
  ok: boolean;
  status: string;
  mensaje: string;
  agente_nombre: string;
  nivel: string | null;
  escenario: string | null;
  dificultad: string | null;
}

export const simulacrosApi = {
  generarPersona: (data: { nombre: string; dificultad: string; descripcion?: string; department_id?: string | null }) =>
    request<ScenarioInput>("/api/simulacros/personalidades/generar", { method: "POST", json: data }),

  listScenarios: () => request<Scenario[]>("/api/simulacros/scenarios"),
  createScenario: (data: ScenarioInput) =>
    request<Scenario>("/api/simulacros/scenarios", { method: "POST", json: data }),
  updateScenario: (id: string, data: ScenarioInput) =>
    request<Scenario>(`/api/simulacros/scenarios/${encodeURIComponent(id)}`, { method: "PATCH", json: data }),
  deleteScenario: (id: string) =>
    request<void>(`/api/simulacros/scenarios/${encodeURIComponent(id)}`, { method: "DELETE" }),

  deleteAgente: (nombre: string) =>
    request<{ ok: boolean; fichas: number; simulacros: number }>(`/api/simulacros/agentes/${encodeURIComponent(nombre)}`, { method: "DELETE" }),
  listComerciales: () => request<Comercial[]>("/api/simulacros/comerciales"),
  createComercial: (data: ComercialInput) =>
    request<Comercial>("/api/simulacros/comerciales", { method: "POST", json: data }),
  updateComercial: (id: string, data: ComercialInput) =>
    request<Comercial>(`/api/simulacros/comerciales/${encodeURIComponent(id)}`, { method: "PATCH", json: data }),
  deleteComercial: (id: string) =>
    request<void>(`/api/simulacros/comerciales/${encodeURIComponent(id)}`, { method: "DELETE" }),

  listDepartamentos: () => request<Departamento[]>("/api/simulacros/departamentos"),
  createDepartamento: (data: DepartamentoInput) =>
    request<Departamento>("/api/simulacros/departamentos", { method: "POST", json: data }),
  updateDepartamento: (id: string, data: DepartamentoInput) =>
    request<Departamento>(`/api/simulacros/departamentos/${encodeURIComponent(id)}`, { method: "PATCH", json: data }),
  deleteDepartamento: (id: string) =>
    request<void>(`/api/simulacros/departamentos/${encodeURIComponent(id)}`, { method: "DELETE" }),
  importFaqs: (file: File, nivel?: string) => {
    const fd = new FormData();
    fd.append("file", file);
    if (nivel) fd.append("nivel", nivel);
    return requestForm<{ faqs: FaqItem[]; chars: number }>("/api/simulacros/faqs/parse", fd);
  },

  // Catálogo de evaluadores independientes
  generarEvaluador: (data: { nombre?: string; descripcion: string }) =>
    request<EvaluadorInput>("/api/simulacros/evaluadores/generar", { method: "POST", json: data }),
  listEvaluadores: () => request<Evaluador[]>("/api/simulacros/evaluadores/catalogo"),
  createEvaluador: (data: EvaluadorInput) =>
    request<Evaluador>("/api/simulacros/evaluadores/catalogo", { method: "POST", json: data }),
  updateEvaluador: (id: string, data: EvaluadorInput) =>
    request<Evaluador>(`/api/simulacros/evaluadores/catalogo/${encodeURIComponent(id)}`, { method: "PATCH", json: data }),
  deleteEvaluador: (id: string) =>
    request<void>(`/api/simulacros/evaluadores/catalogo/${encodeURIComponent(id)}`, { method: "DELETE" }),

  evaluateLevel: (comercialId: string) =>
    request<LevelResult>(`/api/simulacros/comerciales/${encodeURIComponent(comercialId)}/evaluate-level`, { method: "POST" }),

  getEvaluadores: () => request<Evaluadores>("/api/simulacros/evaluadores"),
  putEvaluadores: (data: Omit<Evaluadores, "project_id">) =>
    request<Evaluadores>("/api/simulacros/evaluadores", { method: "PUT", json: data }),

  testIngest: (data: { transcript: string; agente_nombre?: string; scenario_id?: string }) =>
    request<{ ok: boolean; analysis_id: string; status: string }>(
      "/api/simulacros/test-ingest", { method: "POST", json: data }),
  startCall: (data: { to_number: string; scenario_id?: string; agente_nombre?: string }) =>
    request<{ ok: boolean; call: unknown; scenario: string | null }>(
      "/api/simulacros/start-call", { method: "POST", json: data }),

  announce: (data: { agente_nombre: string; from_number?: string; scenario_id?: string }) =>
    request<AnnounceResult>("/api/simulacros/announce", { method: "POST", json: data }),
};

// ── Cola pública (panel /simulacro, sin login) ────────────────────────────────
export interface ColaStatus {
  status: "active" | "waiting" | "started" | "expired";
  numero: string;
  nombre?: string;
  seconds_left?: number;   // solo en "active"
  position?: number;       // solo en "waiting"
  ahead?: number;
}
export interface ColaJoinResult extends ColaStatus {
  ticket: string;
  escenario?: string | null;
  dificultad?: string | null;
}

export const colaApi = {
  info: () => request<{ numero: string }>("/api/simulacros/cola/info"),
  join: (nombre: string, from_number?: string) =>
    request<ColaJoinResult>("/api/simulacros/cola/join", {
      method: "POST",
      json: { nombre, from_number: from_number ?? "" },
    }),
  status: (ticket: string) =>
    request<ColaStatus>(`/api/simulacros/cola/status?ticket=${encodeURIComponent(ticket)}`),
};
