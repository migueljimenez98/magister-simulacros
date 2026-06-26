# Revisión de seguridad — magister-simulacros

_Revisión de la superficie de seguridad del backend (routers, auth, endpoints
públicos, rate-limit, CORS). Fecha: 2026-06._

La base es sólida. Hay **un problema importante** (el webhook) y algunos menores.

---

## 🔴 Crítico — el webhook de Retell está, en la práctica, sin autenticar

**Endpoint:** `POST /api/retell/webhook` (público, sin login).

El handler verifica la firma pero **NO rechaza** si es inválida: solo hace
`log.warning(...)` y continúa (el código lo dice: _"Tighten to a hard 401 once
confirmed"_). Ver `app/api/retell.py` → `retell_webhook` y
`app/services/retell.py` → `verify_signature`.

**Impacto:** cualquiera puede enviar un `call_analyzed`/`call_ended` falso con una
transcripción y un `nombre_comercial` arbitrarios, lo que:
- crea filas en `quality_analyses` (ensucia datos),
- **dispara el motor de evaluación → llamadas al LLM (coste OpenAI)** → vector de
  gasto / DoS,
- atribuye el simulacro a cualquier agente y puede **cambiarle el nivel** (motor
  de escalado / leveling).

**Fix recomendado:** enforcing real de la firma — responder **401** cuando hay
secreto configurado y la firma no valida. En Render `RETELL_API_KEY` está puesta y
Retell firma el body con HMAC-SHA256, así que se puede activar.
⚠️ **Probar con una llamada real antes de forzarlo** por si el esquema de firma de
Retell difiere (si no, se caerían los webhooks legítimos).
**Implementación sugerida:** un flag `RETELL_ENFORCE_SIGNATURE` (default on en
producción) para activarlo sin riesgo.

---

## 🟠 Medios

1. **`/api/retell/inbound-vars` (público)** — devuelve la `persona`/`guion`/
   `objeciones` (contenido de entrenamiento) a quien haga el POST → divulgación de
   contenido interno. Es público a propósito (lo llama Retell antes de la llamada),
   pero conviene saberlo. Mitigación posible: validar firma/origen si Retell lo
   permite en el inbound webhook.

2. **Cola pública (`POST /api/simulacros/cola/join`, `GET /status`, `GET /info`)** —
   sin login (es el panel `/simulacro`, público a propósito). Cualquiera puede:
   - **ocupar el turno único** (DoS de simulacros legítimos),
   - **armar una llamada atribuida a un nombre elegido**.
   Mitigado en parte por el rate-limit (60/min) y el TTL del turno (45 s). Si el
   panel se expone fuera de la red interna, considerar protegerlo (enlace con
   secreto / IP allowlist).

3. **Rate-limit detrás del proxy de Render** — el limiter (`slowapi`) usa
   `get_remote_address` (IP del peer). Detrás de Render esa IP puede ser la del
   **proxy**, así que el límite de 60/min podría agruparse mal (todos comparten
   cubo, o no limita por cliente real). **Fix:** hacer que lea `X-Forwarded-For`
   (configurar `key_func` para tomar la IP real del cliente).

4. **CORS `allow_credentials=True`** con autenticación por **Bearer** (no cookies):
   no hace falta `credentials` y amplía un poco la exposición. Menor. Asegurar que
   `CORS_ORIGINS` en Render sea exactamente la URL del front (sin comodines).

---

## 🟢 Correcto (ya bien)

- **Sin SQL injection**: todo SQLAlchemy ORM parametrizado, sin SQL crudo con input
  de usuario.
- **Login** (`/api/auth/login`): rate-limit `5/minute`, verificación de contraseña
  en tiempo constante (`verify_password`), error genérico (sin enumeración de
  usuarios), sin endpoint de registro (los usuarios los siembra un admin).
- **JWT**: `JWT_SECRET` validado al arranque (≥32 chars, rechaza el valor de
  ejemplo). `current_user` recarga el usuario en cada request → una cuenta
  deshabilitada se rechaza al instante aunque el token siga vigente.
- **`require_role("admin")`** en todos los endpoints que mutan: personalidades,
  comerciales/agentes, departamentos, evaluadores, borrados, generación con IA,
  import de FAQs, test-ingest, start-call.
- **Token del CRM** (`X-CRM-Token`) comparado con `hmac.compare_digest`
  (tiempo constante).
- **Cabeceras de seguridad** (HSTS, `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, CSP `default-src 'none'`) vía middleware.
- **Import de FAQs** limitado a 5 MB; solo texto plano (sin OCR).
- Secretos en `.env` (gitignored). El repo se escaneó al subir (sin claves reales).

---

## Notas menores

- El webhook genera IDs deterministas a partir del `call_id`
  (`qa-<sha256(call_id)[:12]>`). Un atacante que reutilice un `call_id` podría
  provocar dedupe/colisión. Impacto bajo.
- Los borrados (análisis, agentes) son admin-only e irreversibles; la confirmación
  escrita ("confirmar") es solo de UI (el servidor no la exige). Aceptable.
- Sin riesgo CSRF (auth por Bearer, no cookies).

---

## Plan de arreglos sugerido (por prioridad)

1. **Webhook**: flag `RETELL_ENFORCE_SIGNATURE` → 401 si la firma no valida.
2. **Rate-limit**: respetar `X-Forwarded-For` (IP real del cliente en Render).
3. **CORS**: quitar `allow_credentials` (no se usa).
