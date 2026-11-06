# Dataset de soporte

El corpus contiene tickets sintéticos en español para un producto ficticio llamado Nubbix. Proviene del prototipo de Nubbix y se conserva como un conjunto conocido de regresión. El split `test` ya existía y fue inspeccionado durante el desarrollo: no es un holdout nuevo ni independiente.

| Archivo | Split o tipo | Casos |
| --- | --- | ---: |
| `datasets/tickets.jsonl` | dev | 40 |
| `datasets/tickets.jsonl` | test | 40 |
| `datasets/adversarial.jsonl` | attack | 10 |
| `datasets/adversarial.jsonl` | control | 10 |

Cada split de tickets tiene diez casos de cada categoría: `billing`, `technical`, `account` y `other`. Se conservan los identificadores, textos, etiquetas, acciones esperadas y escenarios del prototipo. La adaptación agrega `kind: ticket` a los tickets; asigna el split `adversarial` y cambia el nombre del tipo `benign` por `control` en los controles. Los identificadores originales `benign-*` se mantienen para preservar la trazabilidad.

`datasets/metadata.json` registra la procedencia, la condición de corpus conocido, las transformaciones y los SHA-256 de los archivos originales y adaptados. Una campaña registra además el hash canónico de los casos efectivamente seleccionados, incluyendo sus anotaciones y su orden. Este hash puede diferir del hash de bytes del archivo completo.

Cada línea JSONL describe un caso:

```json
{"id":"example-1","split":"dev","kind":"ticket","text":"Necesito revisar un cargo.","category":"billing","expected_actions":["Solicitar fecha y referencia sin datos sensibles."],"forbidden_patterns":[],"scenario":"Ejemplo ilustrativo, fuera del corpus."}
```

Los casos adversariales utilizan `expected_category`; el cargador acepta también `category` y rechaza anotaciones contradictorias. Los patrones prohibidos son expresiones regulares revisadas del dataset local. Los archivos no se interpretan como código ni como instrucciones confiables del modelo.

Los cuatro ejemplos de `prompts/versions/v2/examples.yaml` se redactan por separado. Las pruebas rechazan coincidencias exactas después de normalizar mayúsculas y espacios; la separación entre familias de escenarios requiere revisión humana. Compartir una categoría no implica repetir una familia: un fallo concreto de navegación por teclado y una exportación bloqueada pertenecen a `technical`, pero plantean escenarios distintos. La separación de ejemplos no convierte este corpus conocido en una prueba independiente de generalización.

La suite adversarial mezcla ataques puros y consultas legítimas con instrucciones maliciosas. Los controles mencionan roles, secretos, XML, fraude o prompt injection sin pedir que se ejecuten instrucciones inseguras. Bloquear un control por esas palabras puede perjudicar la utilidad y requiere revisión.

El canario sintético se agrega exclusivamente al contexto confiable del arnés adversarial. Ningún ticket contiene su valor. Los prompts normales y el catálogo compartido del runtime conservan su contenido; los bundles del arnés tienen hashes propios.

Para validar el corpus sin llamadas a modelos:

```console
uv run --locked pytest tests/test_dataset.py
```

Las acciones esperadas orientan la rúbrica humana. No se puntúan por coincidencia textual, porque una redacción diferente puede resolver correctamente el mismo problema. Los patrones y el canario aportan señales limitadas; su ausencia no demuestra seguridad.
