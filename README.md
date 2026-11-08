# Nubbix Support AI

Asistente de soporte con IA para clasificar consultas de facturación, problemas técnicos, cuentas y otros asuntos, y preparar respuestas y acciones sugeridas para un equipo de atención al cliente. Las propuestas se revisan antes de mostrarse y las acciones quedan a cargo de una persona.

[Inicio rápido](#inicio-rápido) · [Cómo funciona](#cómo-funciona) · [Documentación](#documentación)

## Inicio rápido

Necesitás Python 3.12 o superior con `venv` y `pip`. uv es opcional. Si Debian o Ubuntu muestra `ensurepip is not available`, la guía indica qué paquete instalar. [Problemas frecuentes](docs/setup.md#problemas-frecuentes)

Abrí la terminal en la raíz del clon, donde está `pyproject.toml`. En Windows Terminal o VS Code, elegí el bloque según el shell de la pestaña. [Perfiles de terminal y WSL](docs/setup.md#elegir-el-shell)

### 1. Instalar y abrir el laboratorio

En un clon nuevo, comprobá que la primera línea del bloque muestre Python 3.12 o superior y ejecutá el resto. Los comandos crean `.venv`, usan su `pip` para instalar las dependencias fijadas en `requirements.txt` e instalan el paquete en modo editable para que encuentre los prompts y datasets del clon. Si ya instalaste el proyecto, podés saltar a los comandos de arranque. [Usar un entorno existente](docs/setup.md#usar-un-entorno-existente)

#### PowerShell en Windows

```powershell
python --version
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
.\.venv\Scripts\python.exe -m nubbix_support_ai prompts check
.\.venv\Scripts\python.exe -m nubbix_support_ai web
```

#### CMD en Windows

```bat
python --version
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m pip install --no-deps -e .
.venv\Scripts\python.exe -m nubbix_support_ai prompts check
.venv\Scripts\python.exe -m nubbix_support_ai web
```

#### Git Bash en Windows

```bash
python --version
python -m venv .venv
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pip install --no-deps -e .
./.venv/Scripts/python.exe -m nubbix_support_ai prompts check
./.venv/Scripts/python.exe -m nubbix_support_ai web
```

#### Bash/Zsh en Linux, macOS o WSL

```bash
python3 --version
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip install --no-deps -e .
./.venv/bin/python -m nubbix_support_ai prompts check
./.venv/bin/python -m nubbix_support_ai web
```

Con el servidor en ejecución, podés abrir el laboratorio y consultar el historial y los reportes sin claves. [Abrir el laboratorio en el puerto 8000](http://127.0.0.1:8000)

Detené el servidor con `Ctrl+C`. La aplicación da hasta cinco segundos a las solicitudes activas antes de cancelar las pendientes y esperar su limpieza. [Cancelación y cierre](docs/lab-guide.md#cancelar-fallar-y-volver-a-intentar)

### 2. Configurar un proveedor para analizar tickets

Creá `.env` a partir de `.env.example` si todavía no existe y completá `OPENAI_API_KEY` o `GEMINI_API_KEY` según el proveedor que vayas a usar. Si sólo vas a usar uno, dejá vacía la variable del otro. [Crear `.env` en tu shell](docs/setup.md#configurar-las-claves-locales)

Si el servidor ya está abierto, detenelo con `Ctrl+C` y repetí el comando `web` para cargar las claves.

Analizar un ticket o ejecutar una evaluación puede generar cargos del proveedor. La versión predeterminada del prompt es `v5`. [Historial de prompts](prompts/CHANGELOG.md)

## Primera prueba

Con el laboratorio abierto y una clave configurada:

1. Elegí el proveedor disponible y conservá el modelo y la versión de prompt seleccionados por la aplicación.
2. Usá el ejemplo **Cobro duplicado** o escribí: "Veo dos cargos iguales en mi tarjeta. ¿Me ayudan a revisarlo?".
3. Presioná **Analizar ticket**. Este paso inicia las llamadas al proveedor; el timeline muestra las etapas e intentos.
4. Al terminar, revisá la propuesta y abrí **Ver contrato JSON**: contiene `answer`, `confidence`, `category` y `actions`. La respuesta concreta depende del modelo y sus controles.
5. Abrí el inspector para ver los prompts, las respuestas, el consumo y las validaciones; después podés recuperar la corrida desde **Historial**.

Si el flujo queda bloqueado o falla, revisá su estado y los eventos en lugar de interpretarlo como una respuesta satisfactoria. La [guía del laboratorio](docs/lab-guide.md) explica cada señal y cómo cancelar una ejecución.

## Qué permite hacer

- Usar el mismo flujo de clasificación y generación desde la CLI y la API.
- Ejecutar el flujo con OpenAI o Google, cada uno con su propia clave.
- Probar tickets y comparar versiones de prompts en el laboratorio local.
- Inspeccionar solicitudes, respuestas, reintentos, consumo y latencia.
- Consultar instrucciones, contexto y ejemplos versionados en YAML con su changelog.
- Medir la clasificación, revisar respuestas y evaluar ataques con controles benignos.

## Cómo funciona

CLI, API y laboratorio utilizan el mismo servicio. El recorrido habitual es:

**Consulta → revisión de entrada → generación → validación del JSON → revisión de salida → propuesta.**

El proveedor elegido ejecuta las tres etapas que requieren un modelo: entrada, generación y salida. Los controles pueden derivar a una respuesta estática de revisión humana. Los fallos operativos se informan como errores, y el historial conserva las etapas e intentos para inspección.

La aplicación utiliza Python, FastAPI, Pydantic y los SDK oficiales de ambos proveedores. FastAPI sirve también el laboratorio en HTML, CSS y JavaScript, sin una compilación frontend independiente. La [arquitectura y su diagrama de flujo](docs/architecture.md) explican las responsabilidades y las decisiones de diseño.

## Otros modos de uso

### CLI

En otra pestaña, activá `.venv` para usar `python` como en los ejemplos o reemplazalo por la ruta al ejecutable del entorno. Elegí el comando según la clave que hayas configurado. [Activación](docs/setup.md#activar-el-entorno) · [Rutas por shell](docs/setup.md#elegir-el-shell)

**OpenAI**

```console
python -m nubbix_support_ai respond --provider openai --text "Me cobraron dos veces este mes"
```

**Google Gemini**

```console
python -m nubbix_support_ai respond --provider google --text "Me cobraron dos veces este mes"
```

`respond` escribe sólo los cuatro campos públicos en stdout: `answer`, `confidence`, `category` y `actions`. Los errores operativos usan stderr y un código de salida no exitoso. Estas consultas consumen API.

En `respond` y las campañas de evaluación, `Ctrl+C` cancela con código de salida `130`; una señal `SIGTERM` capturable usa `143`. Ambos esperan la limpieza y conservan los registros parciales. Consultá [cierre y señales según el sistema](docs/setup.md#detener-procesos-y-consultar-el-código-de-salida).

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

Elegí un comando para un proveedor con clave configurada. Usá `python` con `.venv` activo o indicá la ruta del intérprete del entorno. [Rutas por shell](docs/setup.md#elegir-el-shell)

```console
python -m nubbix_support_ai eval compare --provider openai --split dev --prompt-versions v1 v2
python -m nubbix_support_ai eval run --provider google --prompt-version v1 --split test
python -m nubbix_support_ai eval adversarial --provider openai --prompt-version v1 --ablation
```

Estos comandos consumen API. `--max-cost-usd` permite fijar el presupuesto de una campaña. `datasets/` contiene 80 tickets y 20 casos de seguridad; `evaluation/`, dentro del paquete, contiene el runner y las métricas. Los resultados se guardan en `reports/local/` y pueden revisarse desde el laboratorio.

Los errores y abstenciones de tickets y controles benignos permanecen en el denominador de clasificación. Los ataques se miden por separado. La rúbrica permite revisar la utilidad, corrección y respeto de políticas. El corpus sintético sirve como conjunto conocido de regresión.

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

Estos comandos usan uv con las dependencias de desarrollo. [Configurar uv](docs/setup.md#usar-uv-para-desarrollo)

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
