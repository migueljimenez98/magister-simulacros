# magister-simulacros

Simulacros de formación comercial con **Retell**: una comercial llama, un
"alumno" IA la atiende siguiendo un guión, y la llamada se **evalúa
automáticamente** (nota + feedback + informe) y se ve en un panel sencillo.

Producto **independiente** (BD propia, sin nada del CRM ni de auditoría real).

## Qué incluye
- **Motor de evaluación** (auditor LLM + rúbrica + coach + composer).
- **Integración Retell**: `inbound-vars`, `webhook`, `announce` (token CRM),
  `start-call`, `test-ingest`.
- **Guiones** (escenarios con dificultad), **comerciales** con **nivel** y
  **escalado automático** por reglas (departamentos), **evaluadores** editables.
- Panel: Resultados · Guiones y config · Dev (simulador).

## Stack
Python 3.12 · FastAPI · LangGraph · Postgres 16 + pgvector · Next.js 14.
Sin Redis ni MinIO.

## Dev local
```bash
docker compose up -d --build
docker compose run --rm api python -m scripts.seed_admin admin@magister.com 'Magister2026!'
```
- Panel: http://localhost:3025  (login admin@magister.com / Magister2026!)
- API:   http://localhost:8002
- Postgres: localhost:5434

Rellena `backend/.env` (OpenAI + Retell + token CRM) — ya viene con valores de dev.

## Despliegue en Render
Ver `DEPLOY_RENDER.md` y `render.yaml`.

## Integración con el CRM
Ver `INTEGRACION_CRM_SIMULACROS.md` (un POST a `/api/retell/announce`).
