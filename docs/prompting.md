# Prompts versionados

`prompts/registry.yaml` define versiones, etiquetas, default y baseline. `default` selecciona el prompt usado cuando no se especifica otro; `baseline` identifica la referencia experimental. No significan que exista una configuración ganadora.

Cada directorio `prompts/versions/<id>/` contiene:

| Archivo | Responsabilidad |
|---|---|
| `system.yaml` | Rol, instrucciones y formato de generación. |
| `context.yaml` | Manual de políticas del escenario ficticio. |
| `safety.yaml` | Revisión de entrada/salida y reparación de formato. |
| `examples.yaml` | Demostraciones ticket/respuesta opcionales. |

Las instrucciones incorporan `{{manual}}`; el cargador sustituye ese placeholder y rechaza cualquiera que quede sin resolver. También valida IDs, ubicación de recursos, registro y respuestas few-shot antes de consumir API.

## Comparación inicial

v1 usa instrucciones y contexto. v2 añade cuatro ejemplos: solicitud de prórroga de factura, fallo de foco con teclado, bloqueo por intentos de acceso y consulta de prensa. Esos escenarios no reutilizan tickets del dataset.

Las demás instrucciones, el manual y los controles son idénticos. `comparison_hash` identifica ese contexto fijo; `content_hash` incluye también los ejemplos y la versión efectiva. El runner rechaza una comparación automática de prompts si los contextos no coinciden.

Una modificación simultánea de manual y seguridad es una comparación de pipelines completos, no una medida aislada del aporte de few-shot. Los reportes individuales conservan hashes para describir ese contraste sin atribuciones incorrectas.

## Agregar una versión

1. Copiar una carpeta a un ID nuevo, por ejemplo `v3`.
2. Modificar los YAML, conservando los recursos dentro de esa carpeta.
3. Registrar el ID y su etiqueta en `registry.yaml`.
4. Explicar motivo, cambio e hipótesis en `prompts/CHANGELOG.md`.
5. Ejecutar `nubbix prompts check` y evaluar primero en `dev`.

No es necesario modificar Python, enums de CLI ni métricas. El laboratorio descubre las versiones del registro al iniciar; reiniciarlo recarga los recursos. No editar silenciosamente una versión utilizada por un reporte: una corrida antigua debe seguir siendo identificable por su contenido.

El inspector muestra los prompts efectivos enviados a cada llamada y sus respuestas. No pretende revelar el razonamiento interno del modelo. El canario de extracción se añade sólo desde el arnés adversarial mediante copias; no modifica los YAML normales.
