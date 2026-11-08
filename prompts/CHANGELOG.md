# Historial de prompts

## v5 — Clasificación por intención al derivar

Aclara que la categoría sigue la intención principal del ticket cuando la propuesta consiste en pedir datos, derivar o confirmar una capacidad. Conserva las reglas de generación de v4 y los controles de seguridad de v3.

Con `gpt-6-luna` en `xhigh`, entregó 40 de 40 clasificaciones correctas en Test sin retener propuestas. En la misma tanda, v2 entregó 35 de 40. Su corrida anterior había dado 38 de 40. En Adversarial, v5 permitió los 10 controles benignos y clasificó correctamente 9. La consulta sobre un CSV quedó como `other` en vez de `technical`. El moderador de entrada bloqueó los 10 ataques.

Es la candidata con mejor resultado observado en Test. La evaluación usa un corpus conocido de regresión y la revisión semántica de las propuestas sigue pendiente.

## v4 — Generación con derivaciones sujetas a revisión

El generador describe qué queda por verificar y presenta como requisito sólo lo que exige el manual. Conserva los ejemplos y controles de v3 para medir el cambio de redacción.

Con `gpt-6-luna` en `xhigh`, entregó 38 de 40 clasificaciones correctas en Test. Recuperó los cuatro casos bloqueados por v3 y retuvo otros dos. En Adversarial, aprobó los 10 controles benignos y clasificó correctamente 9. Los 10 ataques quedaron bloqueados en la entrada. El cambio recupera derivaciones, pero la clasificación de algunos tickets que requieren revisión sigue abierta.

## v3 — Moderación de salida para derivaciones

Aclara cuándo permitir una derivación para confirmar información y cuándo bloquear afirmaciones, compromisos o pedidos de credenciales en `answer` y `actions`. Usa el mismo generador, ejemplos, manual y moderador de entrada que v2.

Con `gpt-6-luna` en `xhigh`, recuperó el control benigno que v2 había bloqueado en Adversarial. Ambas versiones frenaron los 10 ataques en la moderación de entrada. En Test, v3 entregó 36 de 40 clasificaciones correctas frente a 38 de 40 de v2. Sigue como candidata.

## v2 — Ejemplos por categoría

Agrega cuatro demostraciones nuevas a la generación, una por categoría. Conserva instrucciones, contexto y revisiones de v1 para aislar el aporte de few-shot.

En Dev, `gpt-6-luna` en `xhigh` entregó 38 de 40 clasificaciones correctas con v2 y 37 de 40 con v1. La utilidad de las propuestas se evalúa por separado con la rúbrica. [Reporte de Dev](../reports/evidence/2026-11-06/7a973e48-b9a6-4be0-8006-6751d1503ed4/summary.json)

## v1 — Instrucciones y contexto

Define el rol de soporte, las cuatro categorías, el contrato estructurado y un manual ficticio de políticas. Incluye revisiones de entrada/salida y reparación de formato.

Es el default y baseline inicial. Las corridas registran los hashes efectivos de cada versión.
