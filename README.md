# Nubbix Support AI

Asistente de soporte con IA para clasificar consultas y preparar respuestas y acciones sugeridas para un equipo de atención al cliente.

CLI, API y laboratorio local implementados. Las pruebas de software usan transportes controlados; la calidad de los modelos se mide por separado con el runner de evaluaciones.

## Objetivo

Ayudar a un agente de soporte a responder consultas de facturación, problemas técnicos, gestión de cuentas y otros asuntos. Cada propuesta sigue un contrato JSON estable y pasa por controles de entrada y salida antes de presentarse para revisión humana.

## Funcionalidades

- **CLI y API:** acceso al mismo flujo de clasificación y generación.
- **Dos proveedores:** integración independiente con OpenAI y Google.
- **Laboratorio local:** pruebas de tickets y comparación de versiones de prompts.
- **Trazabilidad:** timeline e inspector de solicitudes, respuestas, reintentos, consumo y latencia.
- **Prompts versionados:** instrucciones, contexto y ejemplos en YAML, con changelog.
- **Evaluaciones:** métricas de clasificación, revisión de respuestas y casos adversariales con controles benignos.

## Empezar

Requiere Python 3.12 o superior. La [guía de instalación y terminales](docs/setup.md) cubre PowerShell, CMD, Git Bash y Bash/Zsh en Linux, macOS o WSL. En Windows Terminal o VS Code, elegí los comandos según el shell abierto en esa pestaña.

Con [uv instalado](https://docs.astral.sh/uv/getting-started/installation/), ejecutá desde la raíz del repositorio. Estos comandos sirven en todos los shells anteriores:

```console
uv --version
uv sync --locked
```

Creá `.env` sólo si todavía no existe, usando la fila correspondiente a tu shell:

| Shell | Crear la configuración local sin sobrescribirla |
| --- | --- |
| PowerShell | `if (-not (Test-Path .env)) { Copy-Item .env.example .env }` |
| CMD | `if not exist .env copy .env.example .env` |
| Git Bash / Bash / Zsh | `if [ ! -e .env ]; then cp .env.example .env; fi` |

Completá únicamente las claves de los proveedores que quieras utilizar: `OPENAI_API_KEY` y/o `GEMINI_API_KEY`. La aplicación no necesita ambas para funcionar con uno solo.

```console
uv run --locked nubbix prompts check
uv run --locked nubbix respond --provider openai --text "Me cobraron dos veces este mes"
uv run --locked nubbix web
```

El laboratorio queda en [localhost:8000](http://127.0.0.1:8000), con documentación HTTP en `/docs`. Permite probar tickets, ver etapas e intentos en vivo, inspeccionar prompts y respuestas, ejecutar campañas y revisar sus resultados.

El comando `respond` escribe sólo los cuatro campos públicos en stdout: `answer`, `confidence`, `category` y `actions`. Los errores operativos usan stderr y un código de salida no exitoso.

### Si `uv` no está disponible y el entorno ya existe

Si `.venv` ya tiene instaladas las dependencias, podés iniciar el laboratorio directamente. No hace falta activar el entorno:

| Shell y sistema | Iniciar el laboratorio |
| --- | --- |
| PowerShell en Windows | `.\.venv\Scripts\python.exe -m nubbix_support_ai web` |
| CMD en Windows | `.venv\Scripts\python.exe -m nubbix_support_ai web` |
| Git Bash en Windows | `./.venv/Scripts/python.exe -m nubbix_support_ai web` |
| Bash/Zsh en Linux, macOS o WSL | `./.venv/bin/python -m nubbix_support_ai web` |

Detené el servidor con `Ctrl+C`. En Git Bash usá `/` en las rutas: `\` funciona como escape. Para WSL, creá un entorno Linux en un checkout separado del utilizado en Windows. La [guía completa](docs/setup.md) explica cómo instalar uv, activar opcionalmente el entorno y hacer una instalación inicial con pip.

## Modelos y consumo

| Variable | Default |
|---|---|
| `NUBBIX_OPENAI_MODEL` | `gpt-6-luna` |
| `NUBBIX_REASONING_EFFORT` | `xhigh` |
| `NUBBIX_GOOGLE_MODEL` | `gemini-3.5-flash-lite`, thinking mínimo |
| `NUBBIX_TICKET_USD` | `0.05` |
| `NUBBIX_CAMPAIGN_USD` | `2` |

Una consulta permitida normalmente realiza tres llamadas: revisión de entrada, generación y revisión de salida. Cada etapa admite dos intentos totales, compartidos entre errores transitorios y formato inválido. El máximo por intento es 15 segundos y el plazo compartido por ticket es 60 segundos.

`xhigh` puede aumentar tokens de razonamiento y latencia; su utilidad debe contrastarse con las evaluaciones. Los costos se estiman con tarifas versionadas y tokens informados, incluyendo caché y razonamiento sin contarlos dos veces. Consumo desconocido conserva una reserva y nunca se informa como cero. El presupuesto es local al proceso/campaña y no garantiza el importe final de facturación del proveedor.

## Evaluaciones

```console
uv run --locked nubbix eval compare --provider openai --split dev --prompt-versions v1 v2
uv run --locked nubbix eval run --provider google --prompt-version v1 --split test
uv run --locked nubbix eval adversarial --provider openai --prompt-version v1 --ablation
```

Estos comandos consumen API. `--max-cost-usd` permite fijar el presupuesto de una campaña. `datasets/` contiene 80 tickets y 20 casos de seguridad; `evaluation/`, dentro del paquete, contiene el runner y las métricas. Los resultados se guardan en `reports/local/` y pueden revisarse desde el laboratorio.

Los errores y abstenciones permanecen en los denominadores. Utilidad, corrección y respeto de políticas tienen una rúbrica de revisión; valores pendientes no cuentan como aprobaciones. El corpus es sintético y conocido de regresión, no una muestra representativa de clientes ni un holdout nuevo.

Las [mediciones iniciales](docs/results.md) incluyen campañas reales, configuración y cobertura: OpenAI obtuvo 38/40 clasificaciones correctas en `test` con v2; Gemini se verificó con una muestra reducida tras límites de cuota. La revisión semántica permanece pendiente.

## Arquitectura y documentación

La aplicación utiliza Python, FastAPI, Pydantic y los SDK oficiales de ambos proveedores. El laboratorio se sirve desde la misma aplicación con HTML, CSS y JavaScript, sin una compilación frontend independiente.

Para entender cómo funciona la aplicación, empezá por la arquitectura y su diagrama general del flujo de soporte. Las guías complementarias explican cada área:

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

## Datos y alcance

Nubbix es un SaaS ficticio utilizado como escenario de soporte. El manual y los casos son sintéticos. Las acciones se sugieren para una persona: el asistente no ejecuta reintegros ni modifica cuentas.

Las credenciales y el historial de ejecuciones permanecen fuera del repositorio. Los resultados reales se publican únicamente con su configuración, denominadores y limitaciones; una suite de software aprobada no demuestra calidad semántica ni resistencia completa a ataques.
