# Catálogo de modalidades por Comunidad Autónoma — Magister

Matriz de qué modalidades se pueden ofrecer al alumno en cada CCAA. Es la
referencia para auditar la sección "ofreció soluciones" del rubric: si la
asesora propuso una modalidad fuera del catálogo permitido para la CCAA del
alumno, es bandera roja (score 0 en el parámetro correspondiente + gap).

## Modalidades disponibles

| Modalidad | Descripción | Dónde se ofrece |
|---|---|---|
| **Presencial** | Aulas físicas de Magister, asistencia obligatoria. | **Solo Madrid** |
| **Semipresencial** | Combinación de aulas físicas + sesiones online. | **Solo Madrid** |
| **Videoconferencia en directo** | Clases en vivo por video, todas las CCAA. | Todas las CCAA |
| **Online grabado** | Clases pregrabadas, acceso 24/7. | Todas las CCAA |

## Matriz por CCAA

| CCAA | Presencial | Semipresencial | Videoconferencia | Online grabado |
|---|:-:|:-:|:-:|:-:|
| Madrid | ✅ | ✅ | ✅ | ✅ |
| Andalucía | ❌ | ❌ | ✅ | ✅ |
| Aragón | ❌ | ❌ | ✅ | ✅ |
| Asturias | ❌ | ❌ | ✅ | ✅ |
| Baleares | ❌ | ❌ | ✅ | ✅ |
| Canarias | ❌ | ❌ | ✅ | ✅ |
| Cantabria | ❌ | ❌ | ✅ | ✅ |
| Castilla-La Mancha (CLM) | ❌ | ❌ | ✅ | ✅ |
| Castilla y León | ❌ | ❌ | ✅ | ✅ |
| Cataluña | ❌ | ❌ | ✅ | ✅ |
| Ceuta | ❌ | ❌ | ✅ | ✅ |
| Melilla | ❌ | ❌ | ✅ | ✅ |
| Comunidad Valenciana | ❌ | ❌ | ✅ | ✅ |
| Extremadura | ❌ | ❌ | ✅ | ✅ |
| Galicia | ❌ | ❌ | ✅ | ✅ |
| La Rioja | ❌ | ❌ | ✅ | ✅ |
| Murcia | ❌ | ❌ | ✅ | ✅ |
| Navarra | ❌ | ❌ | ✅ | ✅ |
| País Vasco | ❌ | ❌ | ✅ | ✅ |

## Reglas duras de auditoría

1. **Presencial / Semipresencial fuera de Madrid = infracción CRÍTICA.** Si
   el alumno está en cualquier CCAA distinta a Madrid y la asesora ofrece
   presencial o semipresencial, score 0 en `ofrece_soluciones` + gap
   "fuera_de_catalogo".

2. **Máximo 2 modalidades por mensaje.** Listar las 4 modalidades juntas
   confunde y dispersa la decisión. Penalización en `ofrece_soluciones` y
   `inicio` (mensajes con muros de info).

3. **Recomendación por defecto fuera de Madrid:** la pareja
   `videoconferencia en directo` (preferente) + `online grabado`
   (alternativa). El comercial debería justificar cuándo proponer cada una.

4. **Madrid:** la asesora debe preguntar si el alumno prefiere asistencia
   física (presencial/semi) o flexibilidad (video/online) ANTES de
   proponer. No asumir presencial por defecto.

## Casos límite frecuentes

- **Estudia en Madrid pero está empadronado en otra CCAA:** la modalidad la
  decide el lugar donde se prepara, no el padrón. Si el alumno dice "vivo
  en Madrid temporalmente para preparar la oposición", presencial/semi
  están sobre la mesa. Si se examina en otra CCAA pero prepara en Madrid,
  el cuerpo y la convocatoria son los del examen, no los del lugar de
  preparación.

- **Lead que ya estudió presencial el año anterior:** no asumir que
  repetirá modalidad. Volver a preguntar — la situación familiar/laboral
  pudo haber cambiado.

- **Lead pregunta por una modalidad inexistente en su CCAA:** explicar la
  oferta real de su CCAA sin crear falsas expectativas. Nunca decir
  "podemos abrir un grupo presencial si hay demanda" en una CCAA donde no
  hay aulas — eso es comprometer algo que no existe.
