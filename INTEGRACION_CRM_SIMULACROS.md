# Integración CRM ↔ Simulacros (Magister)

Enlazar el botón "Llamar" del CRM con el sistema de simulacros, **sin tocar la
centralita** y con impacto **nulo** en el rendimiento. Solo actúa cuando el
número marcado está en la **lista de números de simulacro** (pueden ser varios).

## Idea

Cuando una comercial pulsa "Llamar" hacia un número de simulacro, el CRM —que ya
sabe quién es— hace **un POST** a nuestra API avisando ("el agente X va a
llamar"). Elegimos el guion según su nivel y armamos a Retell. Cuando la llamada
entra, ya sabemos de quién es. El POST es *fire-and-forget*: si fallara, la
llamada se cursa igual.

```
Comercial pulsa "Llamar" (nº de la lista de simulacro)
   → CRM: POST {HOST}/api/retell/announce { agente_nombre }   (X-CRM-Token)
   → respondemos OK/Cambiado
   → el CRM cursa la llamada por la centralita como siempre
   → la llamada llega a Retell ya atribuida al agente y con su guion
```

## Nuestro endpoint (ya desplegado)

- **URL:** `POST {HOST}/api/retell/announce`
- **Cabecera:** `X-CRM-Token: <token>`  ·  **Content-Type:** `application/json`
- **Body:** `{ "agente_nombre": "<nombre>", "from_number": "<opcional>", "scenario_id": "<opcional>" }`
- **Respuesta 200:** `{ "status": "OK", "mensaje": "Cambiado", "escenario": "...", "nivel": "..." }`
- Sin login (servidor-a-servidor). Token ausente/!inválido → 401.

> ⚠️ **`agente_nombre` debe coincidir con el `nombre`** del comercial dado de alta
> en el panel (Simulacros → Comerciales). Es la clave de atribución y de nivel.

---

# Cambios en el CRM (3 pasos)

## Paso 1 — Config (EDITA SOLO ESTO)

Crea el archivo **`seguimiento/includes/config-simulacros.php`** con la ruta, el
token y los números de simulacro. Es lo único que se toca al cambiar de
entorno o al añadir/quitar números:

```php
<?php
/**
 * Configuración de la integración con magister-simulacros (simulacros).
 * EDITA SOLO LOS TRES VALORES DE ARRIBA.
 */

// Host de magister-simulacros. PRODUCCIÓN (Render):
define('MQ_SIMULACRO_HOST',  'https://ms-api-1bqi.onrender.com');

// Token compartido (debe coincidir con CRM_ANNOUNCE_TOKEN del backend/.env)
define('MQ_SIMULACRO_TOKEN', 'crmtok_TU_TOKEN_AQUI');

// Números de simulacro. PUEDEN SER VARIOS, separados por coma. Se comparan por
// sus últimos dígitos, así que da igual el prefijo (+34 / 0034 / 34 / nada).
define('MQ_SIMULACRO_NUMEROS', '919932448');     // ej. varios: '919932448,910000001,910000002'

// ───────────────────────────── (no tocar de aquí para abajo) ─────────────────

/** ¿El número marcado es uno de simulacro? (compara por dígitos finales) */
function mq_es_numero_simulacro($telefono) {
    $d = preg_replace('/\D/', '', (string)$telefono);
    if ($d === '') return false;
    foreach (explode(',', MQ_SIMULACRO_NUMEROS) as $n) {
        $n = preg_replace('/\D/', '', $n);
        if ($n !== '' && substr($d, -strlen($n)) === $n) return true;
    }
    return false;
}

/** Avisa a magister-simulacros. Fire-and-forget: timeout corto, ignora respuesta. */
function mq_avisar_simulacro($agente_nombre, $from_number = '') {
    $body = ['agente_nombre' => $agente_nombre];
    if ($from_number !== '') $body['from_number'] = $from_number;
    $ch = curl_init(MQ_SIMULACRO_HOST . '/api/retell/announce');
    curl_setopt_array($ch, [
        CURLOPT_POST              => true,
        CURLOPT_POSTFIELDS        => json_encode($body),
        CURLOPT_HTTPHEADER        => ['Content-Type: application/json', 'X-CRM-Token: ' . MQ_SIMULACRO_TOKEN],
        CURLOPT_RETURNTRANSFER    => true,
        CURLOPT_CONNECTTIMEOUT_MS => 400,   // como mucho ~0,4s de conexión
        CURLOPT_TIMEOUT_MS        => 600,
        CURLOPT_NOSIGNAL          => true,
    ]);
    @curl_exec($ch);    // ignoramos el resultado a propósito (no bloquea el flujo)
    @curl_close($ch);
}
```

## Paso 2 — Incluir la config

Una sola vez, al principio de **`seguimiento/includes/funciones-hacer-llamada.php`**
(después de `<?php`):

```php
require_once __DIR__ . '/config-simulacros.php';
```

## Paso 3 — El enganche (3 líneas)

En `funciones-hacer-llamada.php`, dentro de `hacer_llamada_core()`, **justo antes
de la línea 333** (`$ejecucion = ejecutar_llamada(...)`):

```php
if (mq_es_numero_simulacro($telefono)) {
    mq_avisar_simulacro($row_agente['nombre']);
}
$ejecucion = ejecutar_llamada($row_agente, $urow, $telefono);   // <-- línea 333 original
```

Eso es todo. Para añadir/quitar números de simulacro o cambiar host/token, solo
se edita `config-simulacros.php`.

---

## Variante aún más rápida (opcional, red interna HTTP plano)

Si el CRM y magister-simulacros están en la misma red (HTTP, sin TLS), puedes
sustituir el cuerpo de `mq_avisar_simulacro()` por un envío 100% no bloqueante
con `fsockopen` (no espera respuesta):

```php
function mq_avisar_simulacro($agente_nombre, $from_number = '') {
    $url = parse_url(MQ_SIMULACRO_HOST);
    $host = $url['host']; $port = $url['port'] ?? 8001;
    $payload = json_encode(['agente_nombre' => $agente_nombre]);
    $fp = @fsockopen($host, $port, $e, $s, 0.3);
    if (!$fp) return;
    $req = "POST /api/retell/announce HTTP/1.1\r\nHost: $host\r\n"
         . "Content-Type: application/json\r\nX-CRM-Token: " . MQ_SIMULACRO_TOKEN . "\r\n"
         . "Content-Length: " . strlen($payload) . "\r\nConnection: close\r\n\r\n" . $payload;
    @fwrite($fp, $req);
    @fclose($fp);   // no leemos respuesta → vuelve al instante
}
```

## Por qué es seguro

- **Rendimiento:** solo se ejecuta para los números de simulacro; las demás
  llamadas no ejecutan nada. Fire-and-forget (no espera respuesta).
- **No rompe la llamada:** el aviso es independiente; si falla, `ejecutar_llamada()`
  se ejecuta igual.
- **Complejidad mínima:** 1 archivo de config + 1 include + 3 líneas. No toca
  `todos.js`, ni la BD, ni el flujo de la centralita.

## Probar sin tocar el CRM

```bash
curl -X POST {HOST}/api/retell/announce \
  -H 'Content-Type: application/json' \
  -H 'X-CRM-Token: crmtok_TU_TOKEN_AQUI' \
  -d '{"agente_nombre":"Miguel"}'
# -> {"status":"OK","mensaje":"Cambiado","escenario":"...","nivel":"facil"}
```

## Notas
- `MQ_SIMULACRO_NUMEROS` admite varios números separados por coma. Compara por
  dígitos finales, así que da igual el formato (+34 / 0034 / 34 / sin prefijo).
- Para desempatar llamadas simultáneas con el mismo caller ID, pásale el caller
  ID del agente como 2º argumento: `mq_avisar_simulacro($row_agente['nombre'], $telefono_origen)`.
- Token de desarrollo (cámbialo en producción): está en `backend/.env`
  (`CRM_ANNOUNCE_TOKEN`).
