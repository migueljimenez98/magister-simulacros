# Desplegar magister-simulacros en Render

Crea: Postgres 16 + **ms-api** (backend) + **ms-frontend** (dashboard). Ligero,
sin Redis ni MinIO.

## 0) Requisitos
- Cuenta Render conectada a GitHub.
- Este proyecto en un repo de GitHub (ver paso 1).
- `backend/.env` está en `.gitignore` → los secretos NO se suben.

## 1) Subir a git
```bash
cd magister-simulacros
git init
git add -A
git commit -m "magister-simulacros: proyecto inicial"
git branch -M main
git remote add origin https://github.com/<tu-usuario>/magister-simulacros.git
git push -u origin main
```

## 2) Blueprint en Render
Render → **New → Blueprint** → elige el repo → detecta `render.yaml` → **Apply**.
Crea la base de datos y los dos servicios web.

## 3) Secretos en **ms-api** (Environment)
- `DEFAULT_LLM_API_KEY` → tu API key de OpenAI (`sk-…`)
- `RETELL_API_KEY`, `RETELL_AGENT_ID`, `RETELL_FROM_NUMBER`
- `CRM_ANNOUNCE_TOKEN` → un token fuerte
- (`JWT_SECRET` y `DATABASE_URL` se rellenan solos)

## 4) URLs cruzadas (tras el 1er deploy)
1. URL del backend (p.ej. `https://ms-api-xxxx.onrender.com`):
   - En **ms-frontend** → env `NEXT_PUBLIC_API_URL` = esa URL → **Clear build cache & deploy**.
2. URL del frontend:
   - En **ms-api** → env `CORS_ORIGINS` = esa URL → redeploy.

## 5) Usuario admin (una vez)
**ms-api → Shell**:
```bash
python -m scripts.seed_admin admin@magister.com 'TuPassword'
```

## 6) Apuntar Retell a la URL real
- Webhook del agente → `https://ms-api-xxxx.onrender.com/api/retell/webhook`
- Inbound webhook del número → `https://ms-api-xxxx.onrender.com/api/retell/inbound-vars`

## 7) CRM
En `INTEGRACION_CRM_SIMULACROS.md` → `config-simulacros.php`:
`MQ_SIMULACRO_HOST` = la URL del backend, `MQ_SIMULACRO_TOKEN` = el `CRM_ANNOUNCE_TOKEN`.

## Notas
- Plan `free`: la api **duerme** tras inactividad (cold start). Para webhooks
  fiables, sube `ms-api` a **Starter**.
- Postgres `free` caduca a los ~30 días.
