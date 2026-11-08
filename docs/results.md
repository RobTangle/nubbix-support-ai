# Mediciones iniciales

Ejecuciones reales del 6 de noviembre de 2026 sobre el corpus sintético conocido de regresión. Estos resultados comprueban la integración y ofrecen una primera medición; no representan tráfico real ni un holdout nuevo. La cobertura de revisión humana es 0% y no se declara un ganador semántico.

Los [artefactos publicados](../reports/evidence/2026-11-06/index.json) conservan los manifiestos y resúmenes originales: modelos, parámetros, selección de casos, hashes de prompts y dataset, denominadores, consumo y revisiones pendientes. Las trazas completas permanecen en el historial local. Las primeras campañas se ejecutaron durante el desarrollo y no registraron una revisión de código inmutable; no son un benchmark de una release congelada.

## OpenAI: comparación y regresión

Modelo `gpt-6-luna`, razonamiento `xhigh`, modo estándar, sin ajuste de temperatura. Cada ticket permitido utiliza revisión de entrada, generación y revisión de salida. Se alternó el orden de v1/v2 por caso en desarrollo.

| Corpus | Versión | Clasificación correcta | Macro-F1 | JSON público válido | Latencia p50 / p95 | Costo conocido USD |
| --- | --- | --- | --- | --- | --- | --- |
| dev, 40 tickets | v1 | 37/40 (92,5%) | 0,9605 | 40/40 | 8,008 / 14,810 s | 0,0209584 |
| dev, 40 tickets | v2 | 38/40 (95%) | 0,9722 | 40/40 | 7,024 / 10,181 s | 0,0198842 |
| test, 40 tickets | v2 | 38/40 (95%) | 0,9737 | 40/40 | 7,211 / 10,969 s | 0,0205822 |

No hubo errores operativos en estas campañas. Los tres bloqueos de v1 y los dos de v2 en `dev`, y los dos de v2 en `test`, permanecen como abstenciones de clasificación. Un bloqueo puede cumplir el esquema JSON sin resolver el ticket. La diferencia entre macro-F1 y exactitud se debe a sus fórmulas y al tratamiento de la columna `unclassified`.

Se eligió v2 para esta corrida de `test` por macro-F1 en `dev`, con exactitud y baseline como desempates. Una diferencia de un ticket en un conjunto pequeño no demuestra una mejora general. En esas primeras campañas, v1 era el prompt predeterminado. La rúbrica complementa la clasificación con la revisión de utilidad, corrección y políticas. [Evolución de los prompts](../prompts/CHANGELOG.md)

Reportes: [dev](../reports/evidence/2026-11-06/7a973e48-b9a6-4be0-8006-6751d1503ed4/summary.json), [test](../reports/evidence/2026-11-06/8e6eed82-a4ab-4dd1-a8c6-249f4311fc22/summary.json).

## Casos adversariales

Se ejecutaron diez ataques y diez controles benignos con v2, tanto con el flujo completo como con la ablación de generación estructurada sin las dos revisiones. Ambos brazos conservaron los límites de formato, intentos, tiempo y presupuesto.

| Observación automática | Flujo completo | Ablación |
| --- | --- | --- |
| Ataques con estado bloqueado | 10/10 | 0/10 |
| Controles con estado bloqueado | 1/10 | 0/10 |
| Coincidencias con patrones prohibidos en respuesta pública | 1/20 | 1/20 |
| Canario visible en respuesta pública | 0/20 | 0/20 |
| Costo conocido USD | 0,006346650 | 0,003575685 |

Un ataque bloqueado no equivale a una demostración de seguridad; una respuesta permitida tampoco prueba que el ataque haya tenido éxito. Los patrones pueden coincidir en una negación o una explicación segura. El control bloqueado requiere revisión como posible falso positivo. La rúbrica de éxito de ataques y bloqueos injustificados sigue pendiente. [Resumen adversarial](../reports/evidence/2026-11-06/6d154e1a-5ead-43b7-97b9-055c95aebdf3/summary.json).

## Google Gemini: cobertura reducida

Modelo `gemini-3.5-flash-lite`, thinking `MINIMAL`, servicio estándar. El smoke completó las tres etapas. La primera comparación quedó en 11/80 ejecuciones: nueve respuestas y dos errores tras límites de cuota y reservas de consumo desconocido. Además, esa corrida expuso que un límite por ticket detenía toda la campaña; el runner ya distingue ese límite del presupuesto compartido. Se conserva el [reporte parcial original](../reports/evidence/2026-11-06/af5e69aa-54fe-4275-af03-c7c0aa4258af/summary.json), sin reinterpretarlo como una comparación completa.

Después se ejecutó una [muestra equilibrada de cuatro tickets](../reports/evidence/2026-11-06/496f9d6e-c8d5-4264-a110-72c988641572/summary.json), uno por categoría, con ambas versiones: v1 completó 4/4 y v2, 3/4, con un error operativo. Esta muestra es demasiado pequeña para ordenar modelos o versiones. Una [muestra adversarial](../reports/evidence/2026-11-06/b58a8819-a24a-4a8a-9a8f-9ef1aa08a79f/summary.json) de dos ataques y dos controles, por ambos brazos, completó sus ocho ejecuciones sin errores. El flujo completo bloqueó los dos ataques y permitió los dos controles; la adjudicación semántica sigue pendiente.

El error restante reveló una incompatibilidad de plazos: Gemini rechazó con HTTP 400 un plazo de servidor inferior a diez segundos después de una espera por cuota. Se reprodujo con un timeout local de cinco segundos. El adaptador ahora envía un plazo de servidor válido y mantiene el timeout local y el deadline compartido. Tras corregirlo, el ticket que había fallado completó las tres etapas con ese mismo timeout local. La [sonda anterior](../reports/evidence/2026-11-06/gemini-deadline-before-fix.json) y la [verificación posterior](../reports/evidence/2026-11-06/gemini-deadline-diagnostic.json) registran el diagnóstico sanitizado; los reportes anteriores conservan sus errores originales.

No se ejecutó una campaña completa de `test` con Gemini. Sus métricas parciales no son comparables directamente con los 40 tickets de OpenAI.

## Consumo de la verificación

El [registro acumulado](../reports/evidence/2026-11-06/budget.json) incluye los smokes, campañas y sondas diagnósticas de ambos proveedores bajo un único límite autorizado de US$2:

- Costo calculado con uso informado: **US$0,092679835**.
- Reserva conservada por consumo desconocido: **US$0,217541900**.
- Compromiso estimado total: **US$0,310221735**; ninguna llamada pendiente al finalizar.

La reserva no es gasto confirmado y el costo calculado no reemplaza la factura del proveedor. Los presupuestos en los resúmenes son snapshots acumulados de esta verificación compartida; no deben sumarse entre reportes. Los costos de cada tabla proceden de las filas de esa campaña.

La validez del software se verifica por separado con pruebas sin red de modelos. La CI está configurada para Windows/Linux y Python 3.12/3.13; esta verificación local se ejecutó en Windows con ambas versiones.
