# Plantillas de WhatsApp — Magister

Plantillas canónicas referenciadas en `procedimientos-gestion-leads.md`.
Las variables `{{1}}`, `{{2}}`, `{{3}}`, `{{4}}` se rellenan en envío
(`{{1}}` = nombre del lead, `{{2}}` = nombre del agente, `{{3}}` = especialidad/CCAA, `{{4}}` = URL/contenido específico).

**Regla maestra:** si la asesora envió un mensaje **distinto** pero **más
personalizado** y mejor encajado al contexto del lead, **se da por bueno**
(la atención personalizada prevalece sobre el ajuste literal).

**Por qué existen plantillas (regla operativa Meta):** WhatsApp Business API
**obliga** a enviar una *Message Template* aprobada para iniciar una
conversación con un usuario que no ha escrito en las últimas 24 horas
(Customer Service Window). Fuera de esa ventana NO se puede enviar texto
libre — solo plantillas. Por tanto, una plantilla aprobada **NO es
"lenguaje robótico"** ni mala personalización: es la única forma técnica
disponible. El auditor debe reconocerla como tal y NO penalizarla por
"falta de personalización" o "uso de template genérico".

---

## `oposiciones_confirmar_email_post_llamada`

*Uso: post-llamada inmediato. La asesora llama, queda en mandar info por
email y usa esta plantilla por WhatsApp para confirmar recepción y
reabrir la ventana 24h de Meta. Plantilla aprobada Meta.*

> ¡Hola {{1}}!
>
> Soy {{2}} de Magister. Te he enviado toda la información por email sobre la preparación de oposiciones como hablamos.
>
> ¿Me puedes confirmar que la recibiste?

---

## `oposiciones_saber-decisión`

*Uso (procedimiento A, intento 1): post-llamada **antes** del FDP/cierre, para invitar a cerrar la matrícula.*

> ¡Hola {{1}}!
>
> Soy {{2}} de Magister. Estuvimos hablando hace poco sobre la preparación de oposiciones para {{3}}.
>
> ¿Te quedó alguna duda respecto a la información o quieres que hagamos la matrícula?

---

## `plantilla_oposiciones_fin_promo_proximo_curso`

*Uso (procedimiento A, intento 1): post-llamada el **día de fin de promo / cierre**, para presionar reserva anticipada con la matrícula de 31 €.*

> ¡Hola {{1}}!
>
> Soy {{2}} de Magister.
>
> Recuerda que hasta hoy tenemos las condiciones especiales por reserva anticipada.
>
> Ahora puedes pagar únicamente la matrícula de **31 €** y así asegurarte **25 € de descuento cada mes**.
>
> ¿Te quedó alguna duda o quieres aprovechar la reserva anticipada?
>
> Si es un ERROR nos ayudaría que respondas.

---

## *(plantilla sin nombre confirmado — variante FDP "mantener condiciones")*

*Uso probable (procedimiento A, intento 1): post-llamada el día de fin de promo, alternativa a la anterior cuando se quiere recalcar el acceso al material previo.*

> ¡Hola, {{1}}!
>
> Soy {{2}} de Magíster.
>
> Recuerda que hasta hoy te puedo mantener las condiciones especiales para iniciar la preparación en {{3}} con los mejores descuentos y con el acceso **SIN COSTE adicional** a todas las clases y material de los meses anteriores.
>
> ¿Te quedó alguna duda o te quieres asegurar las condiciones? Con cualquier duda o si quieres asegurarte las condiciones, escríbeme.
>
> Si es un error nos ayudaría si respondes.

> **Pendiente de confirmar:** nombre canónico exacto en el sistema (¿es otra variante de `plantilla_oposiciones_fin_promo_proximo_curso`? ¿una distinta?).

---

## `oposiciones_cierre_grupos`

*Uso (procedimiento A, intento 1): post-llamada el **día de cierre de grupos** del curso correspondiente.*

> **AVISO IMPORTANTE MAGISTER:**
>
> Cierre de grupos para el curso de la preparación de oposiciones {{1}}.
>
> Si estabas pendiente de completar una matrícula con una especialista puedes responder este WhatsApp para que intentemos ayudarte.

---

## `recu_prox_curso`

*Uso (procedimiento A intento 4 y procedimiento B intento 4): recuperación próximo curso, contacto a 15 días tras intento previo.*

> ¡Hola!
>
> Soy {{1}} de Magister.
>
> Estamos haciendo una campaña para orientar sobre las novedades, cambios y previsiones de las próximas oposiciones.
>
> ¿Tienes previsto opositar en 2026 o 2027?
>
> Si es un ERROR o ya no te interesa nos ayudaría que respondas.

---

## `oposiciones_url_info`

*Uso (procedimiento B intento 2): primer envío de información a un lead **con el que NO se ha hablado**, con el link específico según CCAA + cuerpo (Maestros / Secundaria, Madrid / no Madrid).*

> ¡Hola {{1}}!
>
> Soy {{2}} de Magister. Te dejo por aquí toda la información de la preparación de oposiciones de {{3}}.
>
> {{4}}
>
> Si te surge cualquier duda o lo que sea, coméntame y lo vemos.
>
> Si es un ERROR o ya no te interesa nos ayudaría que respondas.

**`{{4}}` (link a inyectar) según CCAA + cuerpo:**

- **MAESTROS Madrid:** <https://l.magister.com/opo-maestros-madrid-26>
- **MAESTROS no Madrid** (o solo prácticos / solo programación): <https://l.magister.com/opo-inf-maestros-26>
- **SECUNDARIA Madrid:** <https://l.magister.com/opo-sec-madrid-26>
- **SECUNDARIA no Madrid** (o solo prácticos / solo programación): <https://l.magister.com/opo-inf-sec-26>

---

## `plantilla_simple_seguimiento_de_contacto`

*Plantilla genérica usada en intentos 2, 3 y 5 de A y B. Lleva una única variable `{{1}}` con el cuerpo libre. Los textos canónicos por intento están en [`procedimientos-gestion-leads.md`](./procedimientos-gestion-leads.md) (mensaje "consulta a dirección", testimonio, ebooks).*

> {{1}}

---

## Pendientes de confirmar con producto

1. **Nombre canónico** de la "variante FDP — mantener condiciones" (sección sin nombre arriba). Es una plantilla activa o un caso de personalización libre?
2. **Bloque "instancia 64 según QQMLL"** del intento 1B (sin contacto previo): ¿es una sola plantilla por tipo de formulario o varias? Pasame los textos / variantes para añadirlas también.
