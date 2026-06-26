# magister-simulacros — Guía del proyecto (para humanos y LLMs)

> Documento de contexto. Si eres un LLM y vas a trabajar en este repo, **lee esto
> primero**: explica qué es el producto, la arquitectura, el modelo de datos, los
> conceptos de dominio, los endpoints, el flujo de evaluación, el despliegue y las
> trampas conocidas (gotchas). Es un **monorepo** (back + front en el mismo repo).

---

## 1. Qué es

**Simulacros de formación comercial con IA de voz (Retell) + evaluación automática.**

Una **asesora/comercial** llama por teléfono a un número de Retell. Le contesta una
**"persona IA"** (un alumno simulado) que sigue un guión con una dificultad
(fácil/medio/difícil). Al terminar, la llamada se **transcribe y se puntúa
automáticamente** con una rúbrica (LLM auditor + coach + composer), y el resultado
se ve en un panel: nota, feedback a la asesora, evaluación por parámetro e informe.

Es un producto **independiente** (BD propia, sin nada de un CRM real). Se integra con
el CRM existente con **un POST** (no se toca la centralita).

---

## 2. Arquitectura / stack

- **Backend**: Python 3.12 · FastAPI · **LangGraph** (grafo de auditoría) ·
  Postgres 16 + **pgvector** · SQLAlchemy async (asyncpg) · Alembic.
  LLM vía **OpenAI Agents SDK** (`openai-agents`) contra OpenAI.
- **Frontend**: Next.js 14 (App Router, `output: "standalone"`) · React 18 ·
  TailwindCSS · @tanstack/react-query.
- **Infra**: Docker Compose (local) · **Render** (producción, Blueprint
  `render.yaml`). Sin Redis ni MinIO.

```
magister-simulacros/
├─ backend/         FastAPI + LangGraph + Alembic  (Render: servicio ms-api)
├─ frontend/        Next.js                         (Render: servicio ms-frontend)
├─ render.yaml      Blueprint (ms-db + ms-api + ms-frontend)
├─ docker-compose.yml
├─ INTEGRACION_CRM_SIMULACROS.md   (cómo enganchar el CRM)
├─ DEPLOY_RENDER.md
└─ SECURITY_REVIEW.md
```

---

## 3. Conceptos de dominio (¡importante!)

- **Departamento** (`SimulacroDepartamento`): agrupa todo. Tiene:
  - **niveles fijos**: siempre `facil / medio / dificil` (no editables).
  - **FAQs comunes estructuradas** (`faqs`): lista de `{pregunta, respuesta_esperada, nivel}`.
    Se inyectan en la llamada filtradas por el nivel.
  - **evaluador asignado** (`evaluador_id`) → cómo se puntúan sus llamadas.
  - (`faqs_por_nivel` es una columna **deprecada**, sustituida por `faqs`).
- **Personalidad** (= "persona IA"; en BD es `SimulacroScenario`): el alumno IA que
  recibe la llamada. Pertenece a un departamento, tiene `dificultad`, `persona`
  (perfil), `objeciones`, `faqs` propias, `guion` (situación), `producto`.
  **OJO terminología**: en la UI se llama **"Personalidad"**; en el código/tabla es
  `scenario`/`SimulacroScenario`.
- **Agente** (= comercial; en BD es `SimulacroComercial`): una **fila por membresía
  de departamento**. Un agente (identificado por `nombre`) puede estar en **varios
  departamentos**, cada uno con su `nivel`, pero **solo está ACTIVO en uno**
  (`activo=True`). El `nombre` es el alias que envía el CRM y por el que se atribuye
  la llamada. La atribución y el escalado usan siempre la **membresía activa**.
- **Evaluador** (`SimulacroEvaluador`): catálogo reutilizable de "cómo se puntúa" =
  `auditor_prompt` + `feedback_prompt` + `report_prompt` + `rules_table` (rúbrica).
  Se asigna uno por departamento. La rúbrica son parámetros con
  `{id, name, weight, dimension, criteria, description}`; la `dimension` siempre es
  `"informacion_telefonica"`.
- **Cola de turno** (`app/services/cola.py`): **un solo simulacro "armado" a la vez**.
  El panel `/simulacro` y el CRM comparten la cola. Se libera el turno cuando la
  llamada **CONECTA** (no cuando termina; Retell admite simultáneas), o a los **45 s**
  si no llama. El CRM toma el turno al instante (prioridad, fire-and-forget); el panel
  espera en cola.

---

## 4. Modelo de datos (`backend/app/core/models.py`)

- `User` — login (admin/viewer). Sin signup; se siembra con `scripts/seed_admin.py`.
- `QualityProject` — proyecto único de simulacros (`proj-simulacros`): rúbrica y
  prompts **por defecto** (fallback si un departamento no tiene evaluador), config, KB.
- `QualityAnalysis` — **un simulacro puntuado**. Campos: `agente_nombre`, `escenario`
  y `departamento` (denormalizados), `scores` (por parámetro), `total_score`,
  `percent_quality`, `feedback_message`, `detailed_report`, `crm_snapshot`
  (incluye la **transcripción** en `crm_snapshot.transcript` / `._simulacro`),
  `status` (`done`/`failed`/...), `error`.
- `KbDocument` / `KbChunk` (Vector 1536) — KB (docs/) para el grounding del coach.
- `SimulacroDepartamento`, `SimulacroScenario`, `SimulacroComercial`,
  `SimulacroEvaluador` — ver §3.

**Migraciones (Alembic, `backend/alembic/versions/`):**
`0001` inicial · `0002` `faqs_por_nivel` (deprecado) · `0003` `escenario`+`departamento`
en analyses · `0004` `faqs` estructuradas en dpto · `0005` evaluadores +
`departamento.evaluador_id` · `0006` `producto` String(120)→500.
El arranque corre `alembic upgrade head` (ver `backend/start.sh`).

---

## 5. Flujo de evaluación (grafo LangGraph)

`backend/app/graph/audit_graph.py`:
```
START → ingest_retell → load_rules_kb → score_param (fan-out por parámetro)
      → aggregate_totals → [compose_feedback ‖ compose_report] → persist
```
- `load_rules_kb` carga la rúbrica + prompts. Si el departamento tiene **evaluador
  asignado**, se inyecta como `evaluador_override` en el estado (rules_table +
  prompts) y se usa en vez del proyecto (con fallback al proyecto).
- `score_param` puntúa cada parámetro con el LLM auditor (cita evidencia).
- `persist` decide `status`: **"done"** si al menos un parámetro se evaluó (aunque sea
  0); **"failed"** si la llamada estaba bloqueada (sin transcripción), no hay rúbrica,
  o el auditor petó en TODOS los parámetros (`gap == "scoring_error"`, típico: falta
  la API key). Un 0 legítimo NO es "failed".

---

## 6. Endpoints (resumen)

Routers en `backend/app/api/`, montados con prefijo `/api` en `main.py`.

- **`/api/auth`** (`auth.py`) — `login` (rate-limit 5/min), `me`.
- **`/api/analyses`** (`analyses.py`, **requiere login**):
  - `GET /` lista (filtros agente/estado/búsqueda), `GET /facets`,
    `GET /{id}` detalle, `DELETE /{id}` (admin), `POST /{id}/redispatch`.
  - **`GET /stats`** — agregados del dashboard: KPIs, series, **temas más fallados**
    (peores parámetros), por dificultad, y **por agente** (última llamada `ultima_id`,
    nº, nota media, nivel activo, **membresías**, nivel recomendado).
- **`/api/retell`** (`retell.py`, **público**, lo llama Retell):
  - `POST /inbound-vars` — variables dinámicas para la llamada entrante (persona,
    guion, dificultad, FAQs del nivel). Resuelve el agente y consume la cola.
  - `POST /webhook` — eventos de llamada (`call_analyzed`/`call_ended`) → crea el
    análisis y lanza el grafo. ⚠️ **firma best-effort, no enforced** (ver SECURITY_REVIEW).
  - `POST /announce` — entrada del **CRM** (cabecera `X-CRM-Token`). Arma la cola.
- **`/api/simulacros/cola`** (`cola_router`, **público**, panel `/simulacro`):
  `POST /join`, `GET /status`, `GET /info` (devuelve `RETELL_FROM_NUMBER`).
- **`/api/simulacros`** (`simulacros_router`, **requiere login**; mutaciones = admin):
  - `scenarios` (= personalidades) CRUD + `POST /personalidades/generar` (IA).
  - `comerciales` (= agentes) CRUD + `DELETE /agentes/{nombre}` (borra fichas +
    sus simulacros).
  - `departamentos` CRUD + `POST /faqs/parse` (sube PDF/TXT → LLM estructura FAQs).
  - `evaluadores` (proyecto default, GET/PUT) + `evaluadores/catalogo` CRUD +
    `POST /evaluadores/generar` (IA).
  - `announce` (panel Dev), `start-call` (saliente de prueba), `test-ingest`
    (puntúa una transcripción pegada, sin teléfono), `evaluate-level`.

**Generación con IA** (misma API key que el evaluador, `DEFAULT_LLM_API_KEY`):
- Personas IA: `app/services/persona_gen.py`.
- Evaluadores: `app/services/evaluador_gen.py`.
- Import de FAQs desde PDF/TXT: `app/services/faq_import.py` (pypdf, texto plano).

---

## 7. Integración Retell + CRM

- **Un solo agente Retell** + **variables dinámicas**: el guión se inyecta por llamada
  (no hay un agente por guión). Ver `app/services/retell.py` →
  `build_dynamic_variables` (mezcla FAQs comunes del nivel + FAQs de la personalidad).
- **El CRM marca la llamada como siempre** (no usa la API de Retell). Justo antes,
  hace `POST /api/retell/announce {agente_nombre, from_number?}` con `X-CRM-Token`.
  Ver `INTEGRACION_CRM_SIMULACROS.md`. El `agente_nombre` debe coincidir con el
  `nombre` del agente dado de alta.
- Webhooks del agente/número de Retell apuntan a `…/api/retell/webhook` y
  `…/api/retell/inbound-vars`.

---

## 8. Frontend (Next.js, `frontend/src/app/`)

Nav (dentro de `/dashboard`, requiere login): **Agentes · Configuración · Dev · Logs**.
- **`/dashboard`** — pestaña **Agentes** (fusiona el antiguo dashboard): tabla a 100vw
  con todos los agentes (departamentos como chips con borde por nivel: fácil=verde,
  medio=amarillo, difícil=rojo; el activo con borde grueso), última llamada (clicable
  → detalle), nº, nota media, recomendado. Filtro por departamento + KPIs. Abajo:
  temas más fallados, nota por dificultad, progreso. **"Ver detalles"** → modal con
  membresías (gestión) + historial; cada llamada abre su detalle (transcripción +
  feedback + evaluación por parámetro + informe). Borrar agente / borrar simulacro.
- **`/dashboard/simulacros`** — **Configuración**: selector de departamento;
  por departamento, sus personalidades en **tabla** (ordenable por nombre/dificultad,
  default dificultad), FAQs, evaluador. Catálogo de **evaluadores** (CRUD + generar IA).
- **`/dashboard/dev`** — simulador del botón "Llamar" del CRM + llamada saliente de prueba.
- **`/dashboard/log`** — **Logs**: todas las llamadas; borrar por fila (confirmación escrita).
- **`/dashboard/detail?id=…`** — detalle completo de una llamada.
- **`/simulacro`** — **panel PÚBLICO sin login**: nombre de seguimiento + "Iniciar
  simulacro" → cola; muestra el número a llamar tras pulsar.
- **`/`** — login.

**Notas/escala:** las notas se muestran **sobre 10** con color gradiente rojo→amarillo→
verde (`frontend/src/lib/score.ts`: `nota10`, `notaHsl`). `NEXT_PUBLIC_API_URL` se
**hornea en build** (build-arg del Dockerfile).

---

## 9. Despliegue (Render) y dev local

**Render** (Blueprint `render.yaml`, mismo repo → 2 servicios + BD):
- `ms-db` (Postgres 16), `ms-api` (`rootDir: backend`), `ms-frontend` (`rootDir: frontend`).
- **Live**: api `https://ms-api-1bqi.onrender.com`, front
  `https://ms-frontend-sspg.onrender.com`.
- **Secretos a poner en ms-api** (`sync:false`): `DEFAULT_LLM_API_KEY`, `RETELL_API_KEY`,
  `RETELL_AGENT_ID`, `RETELL_FROM_NUMBER`, `CRM_ANNOUNCE_TOKEN`, `CORS_ORIGINS`
  (= URL del front). `JWT_SECRET` y `DATABASE_URL` se autogeneran.
- En **ms-frontend**: `NEXT_PUBLIC_API_URL` = URL de la api → **Clear build cache & deploy**.
- Admin (una vez, ms-api → Shell): `python -m scripts.seed_admin admin@magister.com 'Pass'`.
- Plan free: la api **duerme** (cold start ~30-60 s); para webhooks fiables → Starter.

**Local** (`docker compose up -d --build`, `COMPOSE_PROJECT_NAME=magister-simulacros`):
- Postgres **5434**, API **8002**, panel **http://localhost:3025**.
- Login `admin@magister.com / Magister2026!`. `backend/.env` trae valores de dev.

---

## 10. Gotchas / trampas conocidas (¡leer antes de tocar!)

- **`checkpoint_dsn` por defecto = `""`** en `config.py` a propósito: si no, se queda
  apuntando a `localhost` y el checkpointer de psycopg da PoolTimeout en Render.
- **`CORS_ORIGINS`** se lee como **string** separado por comas (`cors_origins_raw`,
  alias `CORS_ORIGINS`); `cors_origins` es una **property**. Un campo `list[str]`
  hacía que pydantic intentara JSON-decodificarlo y petaba el arranque.
- **`start.sh`** como CMD del backend (migra+seed+uvicorn). No usar `dockerCommand`
  en render.yaml con `sh -c "..."`: Render lo re-envuelve y rompe el quoting (status 127).
  `.gitattributes` fuerza LF en `*.sh`.
- **Campos FK** (`department_id`, `evaluador_id`, etc.): el esquema convierte `""`→`None`
  (un string vacío en una FK daba 500, que el navegador mostraba como error de CORS).
- **`producto`** es String(500) (la IA generaba textos >120 que daban 500 al guardar).
- **Niveles fijos**: `facil/medio/dificil` en todo el sistema.
- **Build de Docker local**: a veces deja contenedores "Dead"/renombrados que bloquean
  el recreate → `docker container prune -f` antes de `up --force-recreate`.
- **Agente sin membresía activa**: sus llamadas entran sin departamento/nivel; la UI lo
  marca ("sin activo").
