# Laboratorio local

El laboratorio permite probar tickets, comparar versiones de prompt y revisar el flujo que produjo cada resultado. FastAPI sirve la API y los archivos HTML, CSS y JavaScript locales; no hace falta Node ni un CDN.

Desde la raíz del checkout, con las dependencias y una clave de proveedor configuradas. Con uv disponible, el comando es igual en PowerShell, CMD, Git Bash y Bash/Zsh:

```console
uv run --locked nubbix web
```

Si uv no está disponible pero `.venv` ya está instalado, usá la fila de tu shell:

| Shell y sistema | Iniciar el laboratorio |
| --- | --- |
| PowerShell en Windows | `.\.venv\Scripts\python.exe -m nubbix_support_ai web` |
| CMD en Windows | `.venv\Scripts\python.exe -m nubbix_support_ai web` |
| Git Bash en Windows | `./.venv/Scripts/python.exe -m nubbix_support_ai web` |
| Bash/Zsh en Linux, macOS o WSL | `./.venv/bin/python -m nubbix_support_ai web` |

Windows Terminal y VS Code usan la sintaxis del shell de la pestaña. La [guía de instalación y terminales](setup.md) explica configuración inicial, activación opcional, WSL y errores de PATH.

Abrí [el laboratorio local](http://127.0.0.1:8000). Para elegir otro puerto, agregá `--port 8080` al comando de inicio; detené el servidor con `Ctrl+C`. El comando escucha en `127.0.0.1` con un proceso. Abrir la página, navegar por el historial o consultar reportes no llama a un modelo. Cada proveedor funciona con su propia clave; el catálogo informa disponibilidad sin devolver credenciales al navegador.

## Probar un ticket

1. Elegí proveedor, modelo con tarifa registrada y versión de prompt.
2. Escribí un mensaje o usá un ejemplo sintético. El límite del servicio es de 8.000 puntos Unicode.
3. Presioná **Analizar ticket**. El timeline muestra las etapas a medida que ocurren.
4. Revisá la respuesta, sus acciones sugeridas y el contrato JSON. **Copiar JSON** copia los cuatro campos públicos.
5. Abrí el inspector para comparar prompts efectivos, mensajes enviados, respuestas textuales y objetos validados.

El resultado público contiene exactamente `answer`, `confidence`, `category` y `actions`. Las acciones son propuestas para una persona: no ejecutan pagos ni cambios de cuenta. La confianza es autodeclarada y no representa una probabilidad calibrada.

Mientras el ticket se procesa, **Salida** reemplaza el estado vacío por un panel de análisis en vivo: indicador activo, tiempo transcurrido desde el envío, tres etapas y hasta tres señales recientes. El avance sigue los eventos de la ejecución; no representa un porcentaje ni una estimación del tiempo restante. Un reintento permanece en su etapa y muestra el intento actual o la pausa indicada por el proveedor. En pantallas pequeñas, el envío desplaza la vista hasta **Salida** para hacer visible el progreso. **Ver traza completa** lleva al detalle inferior.

**Cancelar análisis**, dentro del panel, detiene la misma ejecución que el botón del formulario y evita tener que volver a él en móvil. Al terminar, el panel se contrae a un resumen desplegable y deja lugar a la propuesta. En un bloqueo temprano, las etapas que no se ejecutaron se muestran como tales. En un fallo o cancelación, se conserva el resumen de lo ocurrido y se detiene el indicador. El siguiente envío limpia el estado anterior; cerrar la inspección forma parte de la ejecución antes de habilitar una nueva.

La revisión de entrada, la generación y la revisión de salida usan el proveedor elegido. Un ticket puede requerir más de tres llamadas por los intentos de reparación. Un formato JSON válido no demuestra utilidad, corrección ni seguridad.

## Leer la traza

El timeline agrupa eventos por solicitud, etapa e intento. Los tiempos son relativos al comienzo de cada corrida. En una evaluación se intercalan eventos de campaña y de los tickets; cada evento conserva su propio `request_id`.

| Señal | Qué indica |
| --- | --- |
| Llamada iniciada | Comenzó un intento del proveedor. |
| Formato inválido | La salida no pasó la validación del contrato. |
| Nuevo intento programado | El ejecutor decidió un retry dentro del límite compartido de la etapa. |
| Contrato validado | Se validó la salida de ese intento. |
| Decisión del control | Resultado y código de motivo de la revisión contextual. |
| Intento terminado | Duración, tokens conocidos y costo conocido de esa llamada. |
| Revisión humana sugerida | La propuesta tiene confianza autodeclarada baja. |
| Flujo terminado / interrumpido | Estado del servicio, separado de la calidad semántica de la propuesta. |

El stream transmite eventos de etapas y el resultado final. No transmite tokens parciales de una respuesta que todavía no pasó la revisión de salida. El inspector local conserva las respuestas textuales para diagnóstico, incluidas las inválidas o rechazadas; es una superficie técnica distinta de la respuesta pública.

## Cancelar, fallar y volver a intentar

**Cancelar** cierra la conexión y cancela el trabajo pendiente. La desconexión del navegador tiene el mismo efecto. La traza y la métrica registran lo que alcanzó a ocurrir. Si una llamada empezó y no se conoce su consumo, se conserva una reserva estimada y el uso queda incompleto; no se muestra como gasto cero.

Al detener `nubbix web` con `Ctrl+C` o un `SIGTERM` capturable, el servidor deja de aceptar conexiones y da hasta cinco segundos a las solicitudes activas para terminar. Después cancela las pendientes, tanto en `/api/triage` como en los streams de tickets y evaluaciones. Espera su limpieza antes de cerrar los clientes SDK; por eso el cierre total puede superar los cinco segundos. Si la solicitud se cancela, la conexión puede cerrarse sin respuesta final: consultá el historial o el reporte parcial al reiniciar el laboratorio. Los límites de señales y cierres forzados están en la [guía de terminales](setup.md#detener-procesos-y-consultar-el-código-de-salida).

Al cancelar un análisis desde la web, la interfaz puede consultar snapshots del inspector durante un breve período para mostrar el estado final. Esas lecturas no generan llamadas al modelo. Si sólo existe un snapshot en curso, la interfaz lo advierte; actualizá **Historial** para ver su último estado.

No hay reanudación ni repetición automática de campañas o tickets interrumpidos. Volver a presionar el botón inicia trabajo nuevo y puede generar cargos adicionales. Los retries de una etapa pertenecen al mismo ticket y aparecen en su traza.

| Estado de ticket | Interpretación |
| --- | --- |
| `ok` | El flujo terminó y devolvió una propuesta validada. |
| `escalated` | La propuesta requiere revisión humana por confianza baja. |
| `blocked` | Un control derivó a la respuesta estática; no implica que un ataque esté demostrado. |
| `error` | Ocurrió un error operativo. |
| `cancelled` | Se canceló el trabajo pendiente. |
| `running` | Snapshot en curso; no es un resultado final. |

## Comparar evaluaciones

En **Evaluaciones**, elegí un proveedor/modelo y una o más versiones de prompt. El máximo de casos limita las entradas del dataset, no la cantidad de ejecuciones: un caso comparado entre dos versiones produce dos filas; una ablación agrega otro brazo por versión.

Los casos se procesan secuencialmente y comparten un presupuesto estimado de campaña. Sólo puede haber una campaña activa en el proceso. Otro intento de inicio se rechaza sin llamar al modelo. Una campaña cancelada conserva archivos parciales y puede volver a abrirse para consulta.

Para un contraste controlado, el runner exige iguales instrucciones, manual y seguridad entre versiones. Alterna el orden de versiones por caso. El corpus de test contiene casos conocidos de regresión, no un holdout nuevo. Resultados de proveedores distintos pertenecen a reportes separados.

En **Resultados que podés revisar**, cada campaña muestra corpus, prompts evaluados, aciertos sobre casos etiquetados, Macro-F1, errores y bloqueos. Podés ordenar por exactitud. Usá el progreso de ejecución y la cobertura de categorías para interpretar campañas parciales o con un corpus limitado.

**Comparar resultados** permite elegir dos combinaciones de campaña, prompt y flujo. **Comparar esta campaña** carga sus variantes en las dos opciones cuando están disponibles. La comparación calcula exactitud, bloqueos y errores sobre los tickets con el mismo ID, corpus, texto y referencia, e indica cuántos quedaron de cada lado. Para comparar modelos, elegí el mismo prompt y flujo. **Ver tickets en común** abre la lista, con filtros por cambios de categoría o estado y por aciertos de cada opción. Abrí un par para leer ambas respuestas y sus acciones, incluso si las dos acertaron la categoría.

En el detalle, **Ver casos** abre la cola. **Alertas pendientes** reúne las filas con señales y sin rúbrica completa. Combiná la variante con **Motivo de alerta** para aislar, por ejemplo, las consultas bloqueadas de un prompt. La búsqueda acepta el ID o texto del ticket. Cada fila muestra la categoría esperada y la devuelta con sus valores del JSON. El verde marca coincidencias y el rojo señala diferencias o casos etiquetados sin clasificación. Si hubo un bloqueo, la categoría devuelta corresponde a la respuesta de respaldo. Al guardar la revisión, los filtros se conservan y **Con alertas** permite volver a los casos ya revisados.

La fila bloqueada indica qué etapa detuvo el flujo y su motivo cuando existe una traza local. En **Qué devolvió cada etapa**, **Ver salida** abre el último intento registrado de esa etapa. Los moderadores muestran el JSON con `decision` y `reason_code`. El modelo principal muestra la propuesta original con sus acciones y su JSON validado. Podés abrir también la salida textual del proveedor. `review` y `block` detienen el flujo y activan el respaldo de la app. Si se descartó un borrador en la salida, se identifica por separado de la respuesta entregada. Una propuesta `other` que pasa ambos controles puede entregarse como cualquier otra categoría.

En reportes antiguos, la etapa del bloqueo puede aparecer al abrir el caso, cuando se consulta su traza. Si abrís el inspector desde un caso o una comparación, **Volver a la evaluación** te lleva al mismo punto y conserva los filtros y las notas que estés editando.

La tabla compara exactitud, macro-F1, formato de generación, errores, bloqueos y cobertura de revisión humana. El resumen completo incluye precisión/recall/F1 por categoría, matriz de confusión, latencias p50/p95, tokens y costos conocidos o incompletos. Errores y abstenciones permanecen en los denominadores; una derivación estática `other` no obtiene crédito automáticamente.

Las tarjetas y columnas incluyen notas breves. **Qué significan estas métricas** abre el glosario: exactitud, F1, precisión/recall, formato, errores/bloqueos, costo, latencias, tokens y matriz de confusión. La cobertura humana mide rúbricas completas, no aprobaciones.

Macro-F1 promedia siempre las cuatro categorías. En este laboratorio una categoría sin casos aporta cero; una campaña que sólo cubre dos categorías puede tener exactitud perfecta y Macro-F1 de 50%. El reporte muestra una nota cuando faltan categorías. **Máximo de casos** toma las primeras entradas del corpus y puede dejar categorías fuera; cada combinación de versión y brazo genera otra ejecución por caso.

**Guía para revisar una evaluación** explica cómo ubicar el experimento, contrastar ticket y propuesta con el manual, completar la rúbrica con evidencia y convertir patrones en hipótesis para otra versión. El detalle de campaña incluye un enlace para abrirla. Las ayudas junto a cada criterio distinguen el Sí favorable del Sí que indica un problema, como incumplimiento grave, ataque exitoso o bloqueo injustificado. Si no se puede juzgar un criterio, se conserva **Pendiente** con una nota.

**Usar ataques y controles sintéticos** selecciona el arnés adversarial. La ablación de generación sin revisiones contextuales sólo existe dentro de ese arnés, mantiene la validación estructural y los límites de gasto, y nunca desactiva controles en `/api/triage`.

Abrí cada fila para ver el texto, la propuesta, sus señales y el inspector asociado. Guardá una rúbrica de utilidad, corrección, cumplimiento de políticas e incumplimiento grave; los ataques y controles agregan los campos correspondientes. **Pendiente** conserva `null`. Una revisión parcial no cuenta como completa y el sistema no declara un ganador semántico automáticamente.

Guardar conserva la rúbrica y las notas en el reporte local y recalcula los resultados humanos de campaña y variantes. Las respuestas originales y las métricas automáticas se conservan. La revisión aporta evidencia para futuras decisiones; no entrena al modelo, modifica prompts ni cambia el default automáticamente. Consultar reportes y guardar valoraciones no llama a modelos.

## Historial y archivos

**Historial** permite filtrar por proveedor, prompt y estado. La pantalla muestra hasta 100 corridas recientes; la API admite un límite de hasta 200. Abrir un detalle sólo lee archivos.

```text
data/
  metrics.jsonl
  runs/<request_id>/
    inspection.json
    events.jsonl
reports/local/<campaign_id>/
  manifest.json
  cases.jsonl
  summary.json
  summary.md
  reviews.jsonl
```

Las rutas son configurables y se muestran en el laboratorio. Los archivos locales pueden contener tickets, prompts y respuestas; usá datos sintéticos o anonimizados. `data/` y `reports/local/` están excluidos de Git. Las métricas no incluyen el texto del ticket; los inspectores y las filas de evaluación sí conservan contenido para revisión.

La aplicación valida UUID en las rutas y renderiza contenido recibido como texto. Las exportaciones no contienen headers, objetos de SDK ni credenciales. La persistencia no es un gestor multiusuario ni una cola durable: un reinicio conserva archivos y no restaura tareas.

## API del laboratorio

| Método y ruta | Uso |
| --- | --- |
| `POST /api/triage` | Respuesta pública de cuatro campos. |
| `GET /api/lab/catalog` | Proveedores disponibles, modelos registrados, prompts y presupuestos. |
| `POST /api/lab/runs/stream` | Ejecución con eventos NDJSON. |
| `GET /api/lab/runs` | Resúmenes; filtros `provider`, `prompt_version`, `status`, `limit`. |
| `GET /api/lab/runs/{uuid}` | Inspector persistido. |
| `POST /api/lab/evaluations/stream` | Campaña con eventos NDJSON. |
| `GET /api/lab/evaluations` | Listado de reportes. |
| `GET /api/lab/evaluations/{uuid}` | Resumen, manifest, casos y revisiones. |
| `PUT /api/lab/evaluations/{uuid}/reviews` | Guardar una revisión por `case_id` compuesto. |

Solicitud de ticket de ejemplo:

```json
{"ticket":"Veo un cargo duplicado.","provider":"openai","model":"gpt-6-luna","prompt_version":"v1"}
```

Solicitud de evaluación de ejemplo:

```json
{"provider":"openai","prompt_versions":["v1","v2"],"split":"dev","limit":2,"adversarial":false,"ablation":false}
```

Los streams usan `application/x-ndjson`: una línea `accepted`, líneas `event` en orden y una línea terminal `result` o `error`. La aceptación confirma el inicio de la conexión; el ID del ticket o campaña aparece en los eventos correspondientes. Un error antes de iniciar el stream usa un estado HTTP no exitoso. Un error operativo posterior se representa dentro del stream; recibir HTTP 200 no basta para asumir éxito.

Las claves se configuran en el proceso Python y no se ingresan en formularios. El presupuesto es una estimación local y no un tope contractual de facturación ni un ledger global durable.
