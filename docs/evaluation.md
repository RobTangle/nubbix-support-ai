# Evaluaciones reproducibles

El runner ejecuta el mismo `SupportService.run` utilizado por CLI y HTTP. Procesa los casos secuencialmente y conserva una carpeta nueva por campaña. Abrir un reporte existente no ejecuta llamadas y una campaña interrumpida no se reanuda automáticamente.

Desde la raíz del repositorio, con uv instalado, los comandos son iguales en PowerShell, CMD, Git Bash y Bash/Zsh:

```console
uv run --locked nubbix eval run --provider openai --prompt-version v1 --split dev
uv run --locked nubbix eval compare --provider google --split test
uv run --locked nubbix eval adversarial --provider openai --prompt-version v1 --ablation
```

Sin uv, usá el Python del entorno según la [guía de terminales](setup.md), seguido de `-m nubbix_support_ai eval ...`. Por ejemplo, en Git Bash: `./.venv/Scripts/python.exe -m nubbix_support_ai eval compare --provider openai --split dev`. Estos comandos llaman a las APIs; para inspeccionar sus opciones sin consumirlas, agregá `--help`.

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

La exactitud usa todos los casos intentados con etiqueta. Los errores, bloqueos y abstenciones permanecen en el denominador. Una respuesta estática de derivación con categoría `other` no recibe crédito de clasificación. La matriz de confusión usa cuatro categorías esperadas y una columna adicional `unclassified` para esos resultados. La precisión, recall y F1 se calculan por categoría; macro-F1 promedia las cuatro F1. Una categoría sin predicciones recibe precisión y F1 cero; si no hay casos etiquetados, exactitud y macro-F1 permanecen `null`.

La validez de la respuesta pública y la validez del JSON generado se informan por separado. Una respuesta estática bloqueada puede respetar el esquema sin que haya generación. Un fallo de transporte sin respuesta no prueba que el modelo haya producido JSON inválido. Los intentos de generación que fallaron validación se cuentan incluso cuando una reparación posterior fue válida.

La latencia usa percentiles interpolados p50 y p95 de las observaciones disponibles. Tokens y costo distinguen valores conocidos, consumo incompleto y reservas cuyo consumo no pudo determinarse. Un valor desconocido permanece `null`. `known_total` conserva tokens informados en las llamadas completadas de un caso que después falló; el total completo del caso sigue siendo desconocido.

En una campaña parcial, las métricas clasifican los intentos terminados guardados. `completed/planned` muestra la cobertura de ejecución. Los casos todavía no ejecutados no se presentan como medidos. El presupuesto de `summary.budget` incluye también el consumo conocido o reservado de una llamada cancelada que no alcanzó a producir una fila de caso.

## Revisión humana

La rúbrica contiene `usefulness`, `correctness`, `policy_compliance` y `severe_issue`. Los ataques requieren además `attack_succeeded`; los controles requieren `false_block`. Cada campo admite `true`, `false` o `null`, donde `null` significa pendiente. Se pueden agregar notas. Una fila sólo cuenta como completamente revisada cuando todos sus campos aplicables tienen respuesta booleana.

La cobertura muestra cuántas filas están revisadas, y los campos pendientes se conservan explícitamente. Guardar una revisión vuelve a calcular los resúmenes por versión y brazo. La aplicación no elige automáticamente un ganador semántico: requiere adjudicación humana, incluyendo utilidad y políticas, incluso cuando todas las respuestas cumplen el esquema.

Las señales automáticas incluyen patrones prohibidos en la respuesta pública, canario visible, posible bloqueo de controles y patrones o canario en la generación cruda antes de la moderación de salida. Un canario en una generación que fue bloqueada y un canario efectivamente mostrado al usuario son señales distintas. Ninguna señal sustituye el juicio humano sobre el resultado de un ataque.

## Presupuesto, cancelación y ablación

Todos los casos, versiones, reparaciones y brazos de una campaña comparten el mismo `Budget`. El ejecutor reserva una estimación antes de cada llamada y concilia el uso conocido después. Si se agota el presupuesto de un ticket, guarda ese fallo y continúa con el caso siguiente. Si se agota el presupuesto compartido, termina con `budget_exhausted` y conserva sus resultados parciales. El presupuesto es una estimación local del proceso; no es un tope de facturación durable entre procesos.

Autenticación inválida, permisos, modelo inexistente y cuota diaria agotada detienen la campaña con `provider_error`. Los límites transitorios respetan `Retry-After` y la indicación estructurada de Google dentro del límite de intentos y tiempo. `eval run`, `compare` y `adversarial` conservan el reporte en stdout y devuelven código de salida 1 si la campaña queda incompleta; `eval summarize` devuelve 0 cuando puede leer el reporte, aunque describa una campaña parcial.

La cancelación detiene la llamada pendiente, guarda los casos ya terminados y marca el resumen `interrupted`. El inspector de la solicitud interrumpida conserva su estado y consumo incompleto. No se repite la llamada ni se reanuda la campaña automáticamente, porque una llamada interrumpida pudo ser cobrada.

`--ablation` sólo funciona en el arnés adversarial sintético. Compara el brazo `full` con `unguarded`, que hace generación estructurada sin las dos revisiones contextuales. Ambos mantienen contrato, reparación, límites de intentos, deadline y presupuesto. El arnés reutiliza `StructuredExecutor`, `RunRecorder` y `Budget`; el servicio de soporte y HTTP no ofrecen un parámetro para desactivar guardas. Los bundles con canario son copias locales cuyos hashes efectivos quedan registrados en el manifiesto.

Para verificar el software sin red ni claves:

```console
uv run --locked pytest tests/test_dataset.py tests/test_evaluation_scoring.py tests/test_evaluation_reports.py tests/test_evaluation_runner.py
```

El corpus `test` es conocido y mide regresión. Una mejora en estas métricas necesita revisión y validación adicional antes de extrapolarse a tickets reales.
