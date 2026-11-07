# Nubbix Support AI

Asistente de soporte con IA para clasificar consultas de facturación, problemas técnicos, cuentas y otros asuntos, y preparar respuestas y acciones sugeridas para un equipo de atención al cliente. Las propuestas se revisan antes de mostrarse y las acciones quedan a cargo de una persona.

[Inicio rápido](#inicio-rápido) · [Cómo funciona](#cómo-funciona) · [Documentación](#documentación)

## Qué permite hacer

- **CLI y API:** acceso al mismo flujo de clasificación y generación.
- **Dos proveedores:** integración independiente con OpenAI y Google.
- **Laboratorio local:** pruebas de tickets y comparación de versiones de prompts.
- **Trazabilidad:** timeline e inspector de solicitudes, respuestas, reintentos, consumo y latencia.
- **Prompts versionados:** instrucciones, contexto y ejemplos en YAML, con changelog.
- **Evaluaciones:** métricas de clasificación, revisión de respuestas y casos adversariales con controles benignos.

## Inicio rápido

### 1. Comprobar los requisitos

- Python 3.12 o superior.
- [uv](https://docs.astral.sh/uv/getting-started/installation/) para instalar las dependencias y ejecutar los comandos.
- Una clave de OpenAI o Google Gemini para analizar tickets. Con una sola basta para usar ese proveedor.

Abrí la terminal en la raíz del checkout, donde está `pyproject.toml`. En Windows Terminal o VS Code, elegí las instrucciones según el shell de la pestaña: PowerShell, CMD, Git Bash o Bash/Zsh. La [guía de instalación y terminales](docs/setup.md) incluye instalación de uv, una alternativa inicial con pip y particularidades de WSL.

Si `.venv` ya está preparado y uv no está disponible, podés ir directamente a [Entorno existente sin uv](#entorno-existente-sin-uv).

### 2. Instalar las dependencias

Estos comandos sirven en PowerShell, CMD, Git Bash y Bash/Zsh:

```console
uv --version
uv sync --locked
```

### 3. Configurar las claves

Creá `.env` sólo si todavía no existe, usando la fila correspondiente a tu shell:

| Shell | Crear la configuración local sin sobrescribirla |
| --- | --- |
| PowerShell | `if (-not (Test-Path .env)) { Copy-Item .env.example .env }` |
| CMD | `if not exist .env copy .env.example .env` |
| Git Bash / Bash / Zsh | `if [ ! -e .env ]; then cp .env.example .env; fi` |

Abrí `.env` en tu editor y completá únicamente las claves de los proveedores que quieras utilizar: `OPENAI_API_KEY` y/o `GEMINI_API_KEY`. La aplicación no necesita ambas para funcionar con uno solo.

### 4. Iniciar el laboratorio web

Validá los prompts e iniciá el servidor. Estos comandos no llaman a las APIs de modelos:

```console
uv run --locked nubbix prompts check
uv run --locked nubbix web
```

Dejá la terminal abierta y visitá [http://127.0.0.1:8000](http://127.0.0.1:8000). Detené el servidor con `Ctrl+C`. Abrir el laboratorio, el historial o los reportes no consume API; analizar un ticket o ejecutar una evaluación sí puede generar cargos.

Al detener el servidor, las solicitudes activas tienen hasta cinco segundos para terminar. Después se cancelan las pendientes y se espera su limpieza antes de cerrar los clientes. La [guía del laboratorio](docs/lab-guide.md#cancelar-fallar-y-volver-a-intentar) detalla cómo se registra una interrupción.

### Entorno existente sin uv

Si `.venv` ya tiene instaladas las dependencias, podés iniciar el laboratorio directamente. No hace falta activar el entorno; para analizar tickets, configurá `.env` como se indica en el paso 3:

| Shell y sistema | Iniciar el laboratorio |
| --- | --- |
| PowerShell en Windows | `.\.venv\Scripts\python.exe -m nubbix_support_ai web` |
| CMD en Windows | `.venv\Scripts\python.exe -m nubbix_support_ai web` |
| Git Bash en Windows | `./.venv/Scripts/python.exe -m nubbix_support_ai web` |
| Bash/Zsh en Linux, macOS o WSL | `./.venv/bin/python -m nubbix_support_ai web` |

Después abrí la misma dirección del laboratorio. En Git Bash usá `/` en las rutas: `\` funciona como escape. Para WSL, creá un entorno Linux en un checkout separado del utilizado en Windows. La [guía completa](docs/setup.md) detalla la activación opcional del entorno y los errores de rutas o PATH.

## Primera prueba

Con el laboratorio abierto y una clave configurada:

1. Elegí el proveedor disponible y conservá el modelo y la versión de prompt seleccionados por la aplicación.
2. Usá el ejemplo **Cobro duplicado** o escribí: "Veo dos cargos iguales en mi tarjeta. ¿Me ayudan a revisarlo?".
3. Presioná **Analizar ticket**. Este paso inicia las llamadas al proveedor; el timeline muestra las etapas e intentos.
4. Al terminar, revisá la propuesta y abrí **Ver contrato JSON**: contiene `answer`, `confidence`, `category` y `actions`. La respuesta concreta depende del modelo y sus controles.
5. Abrí el inspector para ver los prompts, las respuestas, el consumo y las validaciones; después podés recuperar la corrida desde **Historial**.

Si el flujo queda bloqueado o falla, revisá su estado y los eventos en lugar de interpretarlo como una respuesta satisfactoria. La [guía del laboratorio](docs/lab-guide.md) explica cada señal y cómo cancelar una ejecución.

## Cómo funciona

CLI, API y laboratorio utilizan el mismo servicio. El recorrido habitual es:

**Consulta → revisión de entrada → generación → validación del JSON → revisión de salida → propuesta.**

El proveedor elegido ejecuta las tres etapas que requieren un modelo: entrada, generación y salida. Los controles pueden derivar a una respuesta estática de revisión humana. Los fallos operativos se informan como errores, y el historial conserva las etapas e intentos para inspección.

La aplicación utiliza Python, FastAPI, Pydantic y los SDK oficiales de ambos proveedores. FastAPI sirve también el laboratorio en HTML, CSS y JavaScript, sin una compilación frontend independiente. La [arquitectura y su diagrama de flujo](docs/architecture.md) explican las responsabilidades y las decisiones de diseño.

## Otros modos de uso

### CLI

En otra pestaña de terminal, ejecutá una variante según la clave que hayas configurado. Con uv, la sintaxis es igual en todos los shells mencionados.

OpenAI:

```console
uv run --locked nubbix respond --provider openai --text "Me cobraron dos veces este mes"
```

Google Gemini:

```console
uv run --locked nubbix respond --provider google --text "Me cobraron dos veces este mes"
```

`respond` escribe sólo los cuatro campos públicos en stdout: `answer`, `confidence`, `category` y `actions`. Los errores operativos usan stderr y un código de salida no exitoso. Estas consultas consumen API.

En `respond` y las campañas de evaluación, `Ctrl+C` cancela con código de salida `130`; una señal `SIGTERM` capturable usa `143`. Ambos esperan la limpieza y conservan los registros parciales. Consultá [cierre y señales según el sistema](docs/setup.md#detener-procesos-y-consultar-el-código-de-salida).

Sin uv, usá el ejecutable de la tabla de terminales seguido de `-m nubbix_support_ai respond ...`. Por ejemplo, en Git Bash: `./.venv/Scripts/python.exe -m nubbix_support_ai respond --provider google --text "Me cobraron dos veces este mes"`.

### API HTTP

Con el servidor iniciado, abrí [la documentación interactiva de la API](http://127.0.0.1:8000/docs). Permite probar `POST /api/triage` desde el navegador, sin diferencias de comillas o continuaciones de línea entre shells.

Solicitud de ejemplo; elegí `openai` o `google` según tu clave:

```json
{"ticket":"Me cobraron dos veces este mes","provider":"google"}
```

La respuesta de éxito tiene los mismos cuatro campos que la CLI. Ejecutar esta solicitud también consume API. La [guía del laboratorio](docs/lab-guide.md#api-del-laboratorio) documenta las rutas de streaming, historial y evaluaciones.

## Configuración, modelos y consumo

Estas variables se pueden definir en `.env`; los valores de la tabla son los predeterminados:

| Variable | Default |
|---|---|
| `NUBBIX_OPENAI_MODEL` | `gpt-6-luna` |
| `NUBBIX_REASONING_EFFORT` | `xhigh` |
| `NUBBIX_GOOGLE_MODEL` | `gemini-3.5-flash-lite`, thinking mínimo |
| `NUBBIX_TICKET_USD` | `0.05` |
| `NUBBIX_CAMPAIGN_USD` | `2` |

Una consulta permitida normalmente realiza tres llamadas: revisión de entrada, generación y revisión de salida. Cada etapa admite dos intentos totales, compartidos entre errores transitorios y formato inválido. El máximo por intento es 15 segundos y el plazo compartido por ticket es 60 segundos.

`xhigh` puede aumentar tokens de razonamiento y latencia; su utilidad debe contrastarse con las evaluaciones. Los costos se estiman con tarifas versionadas y tokens informados, incluyendo caché y razonamiento sin contarlos dos veces. Consumo desconocido conserva una reserva y nunca se informa como cero. El presupuesto es local al proceso/campaña y no garantiza el importe final de facturación del proveedor.

## Evaluaciones y resultados

```console
uv run --locked nubbix eval compare --provider openai --split dev --prompt-versions v1 v2
uv run --locked nubbix eval run --provider google --prompt-version v1 --split test
uv run --locked nubbix eval adversarial --provider openai --prompt-version v1 --ablation
```

Estos comandos consumen API. `--max-cost-usd` permite fijar el presupuesto de una campaña. `datasets/` contiene 80 tickets y 20 casos de seguridad; `evaluation/`, dentro del paquete, contiene el runner y las métricas. Los resultados se guardan en `reports/local/` y pueden revisarse desde el laboratorio.

Los errores y abstenciones permanecen en los denominadores. Utilidad, corrección y respeto de políticas tienen una rúbrica de revisión; valores pendientes no cuentan como aprobaciones. El corpus es sintético y conocido de regresión, no una muestra representativa de clientes ni un holdout nuevo.

Las [mediciones iniciales](docs/results.md) incluyen campañas reales, configuración y cobertura: OpenAI obtuvo 38/40 clasificaciones correctas en `test` con v2; Gemini se verificó con una muestra reducida tras límites de cuota. La revisión semántica permanece pendiente.

## Documentación

Para profundizar en cada área:

| Documento | Qué explica |
| --- | --- |
| [Arquitectura y diagrama de flujo](docs/architecture.md) | Recorrido de una consulta, responsabilidades de los módulos y decisiones de diseño. |
| [Laboratorio e inspector](docs/lab-guide.md) | Uso de la interfaz, lectura de trazas, cancelación, historial y API. |
| [Instalación y terminales](docs/setup.md) | Configuración y comandos para PowerShell, CMD, Git Bash y Bash/Zsh, incluido WSL. |
| [Prompts versionados](docs/prompting.md) | Instrucciones, contexto, ejemplos, hashes y cómo agregar una versión. |
| [Dataset y procedencia](docs/dataset.md) | Composición del corpus, etiquetas, ataques y controles benignos. |
| [Evaluaciones](docs/evaluation.md) | Campañas, comparación, métricas, presupuestos y revisión humana. |
| [Resultados y evidencia](docs/results.md) | Mediciones reales, cobertura y limitaciones de los resultados. |

## Verificar el software

```console
uv run --locked pytest
uv run --locked ruff check src tests
uv run --locked mypy
```

La suite no requiere claves y restringe conexiones a loopback para soportar el event loop de Windows. La CI está configurada para Python 3.12/3.13 en Windows y Linux. El entorno de desarrollo se fija con `uv.lock`; `requirements.txt` se exporta desde ese lock.

También podés iniciar la CI desde GitHub: **Actions → Python quality → Run workflow**.

Si Node 22 o superior está disponible, pytest ejecuta también las regresiones JavaScript del progreso del ticket y las ayudas de evaluación. Es opcional para estas pruebas; el laboratorio se ejecuta con Python y no requiere una compilación frontend.

## Datos y limitaciones

Nubbix es un SaaS ficticio utilizado como escenario de soporte. El manual y los casos son sintéticos. Las acciones se sugieren para una persona: el asistente no ejecuta reintegros ni modifica cuentas.

Las credenciales y el historial de ejecuciones permanecen fuera del repositorio. Los resultados reales se publican únicamente con su configuración, denominadores y limitaciones; una suite de software aprobada no demuestra calidad semántica ni resistencia completa a ataques.
