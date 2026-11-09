# Evaluaciones reproducibles

El runner ejecuta el mismo `SupportService.run` utilizado por CLI y HTTP. Procesa los casos secuencialmente y conserva una carpeta nueva por campaña. Abrir un reporte existente no ejecuta llamadas y una campaña interrumpida no se reanuda automáticamente.

Desde la raíz del repositorio, activá el entorno para usar `python` en estos ejemplos. Si creaste `.venv`, también podés usar la ruta a su intérprete. [Rutas y activación por shell](setup.md#elegir-el-shell)

```console
python -m nubbix_support_ai eval run --provider openai --prompt-version v1 --split dev
python -m nubbix_support_ai eval compare --provider google --split test
python -m nubbix_support_ai eval adversarial --provider openai --prompt-version v1 --ablation
```

Estos comandos llaman a las APIs. Para inspeccionar sus opciones, ejecutá el comando correspondiente con `--help`.

Las campañas muestran el avance en stderr cuando está conectado a una terminal. El total cuenta cada ejecución por caso, versión y brazo. `--progress` lo fuerza también al redirigir stderr, donde se escriben líneas completas. `--no-progress` desactiva los mensajes de avance. El reporte JSON se emite por stdout.

Para consultar una campaña ya guardada, pasá la ruta que devolvió `directory`. Este comando lee los archivos locales.

```console
python -m nubbix_support_ai eval summarize "reports/local/<id>"
```

La salida incluye `summary`, `manifest`, `cases` y `reviews`. Para leer una tabla desde la terminal o el editor, abrí `summary.md` en esa misma carpeta.

Cada campaña selecciona un proveedor, modelo y parámetros. Las comparaciones entre versiones utilizan esos mismos valores y alternan el orden de las versiones por caso: v1/v2 en el primero, v2/v1 en el segundo. El runner admite únicamente comparaciones cuyos bundles tienen el mismo `comparison_hash`, que representa instrucciones, manual, seguridad y reparación. Si esos componentes cambian, rechaza la comparación automática con `incomparable_prompt_bundles`; se pueden ejecutar campañas separadas e interpretar el contraste como una comparación de pipelines.

La implementación registra resultados de software con proveedores controlados en las pruebas. Eso valida el mecanismo de evaluación, no la calidad de OpenAI o Gemini. Las mediciones de modelos reales deben ejecutarse explícitamente y revisarse antes de afirmar mejoras.

## Artefactos

La carpeta configurada mediante `reports_dir`, por defecto `reports/local`, contiene un subdirectorio UUID por campaña:

| Archivo | Contenido |
| --- | --- |
| `manifest.json` | Proveedor, modelo, parámetros, selección y hash del dataset, versiones, hashes efectivos, procedencia sintética, brazos, límites y fecha de tarifas. |
| `cases.jsonl` | Una fila por intento de caso terminado, incluida una fila de error cuando falla el servicio. |
| `summary.json` | Estado, cobertura de ejecución, métricas globales y por versión/brazo, consumo y cobertura de revisión humana. |
| `summary.md` | Resumen legible de los resultados y sus límites. |
| `reviews.jsonl` | Rúbricas humanas editables, identificadas por la fila de evaluación. |

`case_id` combina el identificador original, versión y brazo, por ejemplo `dev-billing-01:v2:full`. `dataset_case_id` conserva el identificador del corpus. Cada fila incluye el `request_id` del inspector para consultar las etapas, solicitudes y respuestas originales en el historial local. Los reportes conservan texto y resultados sintéticos; los archivos de historial y reportes locales se excluyen de Git.

## Métricas

La exactitud usa los tickets y controles benignos intentados con etiqueta. Sus errores, bloqueos y abstenciones permanecen en el denominador como `unclassified`, incluso si la respuesta de respaldo lleva la categoría `other`. La precisión, el recall y el F1 se calculan por categoría. Macro-F1 promedia las cuatro categorías. Una categoría sin predicciones recibe precisión y F1 cero. Si no hay tickets o controles etiquetados, exactitud y macro-F1 permanecen `null`.

Los ataques conservan una intención de referencia en el corpus. El reporte separa su resultado de seguridad de la clasificación y registra el total de ataques, los bloqueados y los que recibieron una propuesta del modelo. Al abrir una campaña anterior, la app calcula estas métricas a partir de los casos guardados.

Una categoría sin casos también aporta F1 cero al promedio fijo. Si una selección limitada sólo incluye dos categorías, una clasificación perfecta puede producir exactitud de 100% y macro-F1 de 50%. Antes de interpretar diferencias, comprobá `support` por categoría y la cobertura del corpus. El laboratorio explica esta situación en el reporte y ofrece un glosario desplegable y una guía práctica de revisión.

La validez de la respuesta pública y la validez del JSON generado se informan por separado. Una respuesta estática bloqueada puede respetar el esquema sin que haya generación. Un fallo de transporte sin respuesta no prueba que el modelo haya producido JSON inválido. Los intentos de generación que fallaron validación se cuentan incluso cuando una reparación posterior fue válida.

La latencia usa percentiles interpolados p50 y p95 de las observaciones disponibles. Tokens y costo distinguen valores conocidos, consumo incompleto y reservas cuyo consumo no pudo determinarse. Un valor desconocido permanece `null`. `known_total` conserva tokens informados en las llamadas completadas de un caso que después falló; el total completo del caso sigue siendo desconocido.

En una campaña parcial, las métricas clasifican los intentos terminados guardados. `completed/planned` muestra la cobertura de ejecución. Los casos todavía no ejecutados no se presentan como medidos. El presupuesto de `summary.budget` incluye también el consumo conocido o reservado de una llamada cancelada que no alcanzó a producir una fila de caso.

## Revisión humana

La rúbrica contiene `usefulness`, `correctness`, `policy_compliance` y `severe_issue`. Los ataques requieren además `attack_succeeded`; los controles requieren `false_block`. Cada campo admite `true`, `false` o `null`, donde `null` significa pendiente. Se pueden agregar notas. Una fila sólo cuenta como completamente revisada cuando todos sus campos aplicables tienen respuesta booleana.

La cobertura muestra cuántas filas están revisadas, y los campos pendientes se conservan explícitamente. Guardar una revisión vuelve a calcular los resúmenes por versión y brazo. La aplicación no elige automáticamente un ganador semántico: requiere adjudicación humana, incluyendo utilidad y políticas, incluso cuando todas las respuestas cumplen el esquema.

Las señales automáticas incluyen patrones prohibidos en la respuesta pública, canario visible, posible bloqueo de controles y patrones o canario en la generación cruda antes de la moderación de salida. Un canario en una generación que fue bloqueada y un canario efectivamente mostrado al usuario son señales distintas. Ninguna señal sustituye el juicio humano sobre el resultado de un ataque.

## Presupuesto, cancelación y ablación

Todos los casos, versiones, reparaciones y brazos de una campaña comparten el mismo `Budget`. El ejecutor reserva una estimación antes de cada llamada y concilia el uso conocido después. Si se agota el presupuesto de un ticket, guarda ese fallo y continúa con el caso siguiente. Si se agota el presupuesto compartido, termina con `budget_exhausted` y conserva sus resultados parciales. El presupuesto es una estimación local del proceso; no es un tope de facturación durable entre procesos.

Autenticación inválida, permisos, modelo inexistente y cuota diaria agotada detienen la campaña con `provider_error`. Los límites transitorios respetan `Retry-After` y la indicación estructurada de Google dentro del límite de intentos y tiempo. Si el runner termina informando una campaña incompleta, `eval run`, `compare` y `adversarial` conservan el reporte en stdout y devuelven código de salida 1. Una interrupción por señal usa los códigos indicados abajo. `eval summarize` devuelve 0 cuando puede leer el reporte, aunque describa una campaña parcial.

La cancelación detiene la llamada pendiente, guarda los casos ya terminados y marca el resumen `interrupted`. El inspector de la solicitud interrumpida conserva su estado y consumo incompleto. No se repite la llamada ni se reanuda la campaña automáticamente, porque una llamada interrumpida pudo ser cobrada.

Desde la CLI, `Ctrl+C` (`SIGINT`) devuelve `130` y `SIGTERM` capturable devuelve `143`. Ambos esperan el cierre de los clientes y escriben `{"error": {"code": "cancelled"}}` en stderr, sin reporte en stdout. El reporte parcial queda en `reports/local/<campaign_id>/` y puede leerse con `eval summarize`. Desde la web, detener el servidor da cinco segundos de gracia antes de cancelar una campaña pendiente. Consultá [cierre y señales](setup.md#detener-procesos-y-consultar-el-código-de-salida) para las diferencias entre sistemas y los límites del cierre forzado.

`--ablation` sólo funciona en el arnés adversarial sintético. Compara el brazo `full` con `unguarded`, que hace generación estructurada sin las dos revisiones contextuales. Ambos mantienen contrato, reparación, límites de intentos, deadline y presupuesto. El arnés reutiliza `StructuredExecutor`, `RunRecorder` y `Budget`; el servicio de soporte y HTTP no ofrecen un parámetro para desactivar guardas. Los bundles con canario son copias locales cuyos hashes efectivos quedan registrados en el manifiesto.

Para verificar el software sin red ni claves:

```console
uv run --locked pytest tests/test_dataset.py tests/test_evaluation_scoring.py tests/test_evaluation_reports.py tests/test_evaluation_runner.py
```

El corpus `test` es conocido y mide regresión. Una mejora en estas métricas necesita revisión y validación adicional antes de extrapolarse a tickets reales.
