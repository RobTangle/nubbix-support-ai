# Instalación y terminales

Abrí la terminal en la raíz del clon, donde están `pyproject.toml` y `.env.example`. Si acabás de clonar el repositorio, instalá y arrancá la aplicación con Python 3.12 o superior. [Inicio rápido](../README.md#inicio-rápido)

## Elegir el shell

Windows Terminal y la terminal integrada de VS Code ejecutan el shell del perfil que elegiste. Abrí el menú desplegable junto a `+` para ver los perfiles. Usá los comandos de la fila que corresponda. [Documentación de Windows Terminal](https://learn.microsoft.com/en-us/windows/terminal/)

| Shell | Cómo reconocerlo | Python del entorno virtual |
| --- | --- | --- |
| PowerShell en Windows | El prompt suele comenzar con `PS`. | `.\.venv\Scripts\python.exe` |
| CMD en Windows | Prompt similar a `C:\proyectos\nubbix-support-ai>`. | `.venv\Scripts\python.exe` |
| Git Bash en Windows | El prompt suele incluir `MINGW64` y terminar en `$`. | `./.venv/Scripts/python.exe` |
| Bash/Zsh en Linux o macOS con Apple Silicon | El prompt suele terminar en `$` o `%`. | `./.venv/bin/python` |
| Bash/Zsh en Mac Intel | `uname -m` muestra `x86_64` en una Mac con procesador Intel. | `python` con el entorno de Miniforge activo. |
| Bash/Zsh en WSL | Perfil de una distribución Linux, como Ubuntu. | `./.venv/bin/python` |

Git Bash ejecuta el Python de Windows con sintaxis Bash. En Git Bash y Bash/Zsh, usá `/` en las rutas. Una `\` sin comillas escapa el carácter siguiente. Copiá los comandos sin el indicador de tu terminal, como `$`, `PS>` o `C:\>`.

WSL ejecuta el Python de Linux. Cloná el repositorio dentro del sistema de archivos de tu distribución y creá ahí un `.venv` con el bloque de Bash/Zsh. Cada sistema usa sus propios ejecutables y dependencias.

## Usar un entorno existente

Si `.venv` ya tiene instalados el paquete y sus dependencias, podés verificar los prompts con `prompts check` y pasar a la primera prueba. Los comandos apuntan al Python del entorno. [Instalación](../README.md#1-instalar-la-aplicación) · [Uso con CLI](../README.md#uso-con-cli) · [Abrir el laboratorio](../README.md#primera-prueba-en-el-laboratorio)

Un `.venv` creado por uv puede prescindir de `pip` y ejecutar la aplicación si está instalada. Usá los comandos de instalación con `pip` para un entorno nuevo creado con `venv`.

## Instalar en Mac Intel

PyPI ofrece `cryptography==50.0.2` para macOS con Apple Silicon. En Intel, `pip` intenta compilarla y necesita herramientas de compilación y OpenSSL. El binario de conda-forge permite usar la misma versión en macOS 11 o posterior. [Binarios de conda-forge](https://anaconda.org/conda-forge/cryptography/files?version=50.0.2)

Si todavía no tenés `conda`, instalá `Miniforge3-MacOSX-x86_64.pkg` y elegí la opción de inicializar Conda para tu shell. Reabrí la terminal y comprobá `conda --version`. [Instaladores oficiales de Miniforge](https://github.com/conda-forge/miniforge#requirements-and-installers)

Desde la raíz del clon, creá un entorno con Python 3.12. El comando lee de `requirements.txt` la versión exacta de `cryptography`. `pip` reutiliza ese paquete y descarga las demás dependencias como wheels.

```bash
conda create --name nubbix-support-ai --override-channels --channel conda-forge \
  python=3.12 pip "$(sed -n '/^cryptography==/p' requirements.txt)"
conda activate nubbix-support-ai
python -m pip install --only-binary=:all: -r requirements.txt
python -m pip install --no-deps -e .
python -m pip check
python -m nubbix_support_ai prompts check
```

Activá `nubbix-support-ai` en cada terminal donde vayas a usar la app. Configurá una clave para analizar tickets o abrí el laboratorio para consultar el historial y los reportes. [Configurar las claves](#configurar-las-claves-locales) · [Uso con CLI](../README.md#uso-con-cli) · [Abrir el laboratorio](../README.md#primera-prueba-en-el-laboratorio)

## Configurar las claves locales

Podés abrir el laboratorio, revisar el historial y consultar reportes sin configurar una clave. Para analizar un ticket o ejecutar una evaluación, necesitás una clave del proveedor elegido. Ejecutá el bloque de tu shell para crear `.env` si todavía no existe.

### PowerShell

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

### CMD

```bat
if not exist .env copy .env.example .env
```

### Git Bash, Bash o Zsh

```bash
if [ ! -e .env ]; then cp .env.example .env; fi
```

Abrí `.env` en tu editor y reemplazá `yourOpenaiSecretKey` o `yourGoogleAiSecretKey` con la clave que corresponda. Dejá vacía la variable de cualquier proveedor que no uses. `.env` está ignorado por Git. Si el servidor está abierto, detenelo con `Ctrl+C` y ejecutá `web` de nuevo para cargar la configuración.

## Activar el entorno

Al activar el entorno, `python` apunta al intérprete de ese entorno en la pestaña actual. Si creaste `.venv`, también podés usar su ejecutable directamente.

| Shell y sistema | Activar |
| --- | --- |
| PowerShell en Windows | `.\.venv\Scripts\Activate.ps1` |
| CMD en Windows | `.venv\Scripts\activate.bat` |
| Git Bash en Windows | `source .venv/Scripts/activate` |
| Bash/Zsh en Linux, macOS con Apple Silicon o WSL | `source .venv/bin/activate` |
| Mac Intel con Miniforge | `conda activate nubbix-support-ai` |

Con el entorno activo, `web` inicia el servidor. Agregá `--port` para elegir un puerto distinto del 8000.

```console
python -m nubbix_support_ai web --port 8080
```

Usá otra pestaña si querés ejecutar la CLI mientras `web` sigue abierto. Activá el entorno en esa pestaña o usá el ejecutable de `.venv` si seguiste esa instalación. Estos dos comandos requieren una clave de OpenAI y llaman al modelo. [Guía de evaluación](evaluation.md)

```console
python -m nubbix_support_ai respond --provider openai --text "Me cobraron dos veces este mes"
python -m nubbix_support_ai eval run --provider openai --prompt-version v1 --split dev
```

Si PowerShell bloquea `Activate.ps1`, usá `.\.venv\Scripts\python.exe` directamente. Para salir de `.venv`, ejecutá `deactivate`. En Miniforge, usá `conda deactivate`.

## Usar uv para desarrollo

uv sincroniza el entorno con `uv.lock` e instala las herramientas de desarrollo. `requirements.txt`, usado en el inicio rápido con `pip`, contiene las dependencias de ejecución exportadas del mismo lock. Podés instalar uv siguiendo su [guía oficial](https://docs.astral.sh/uv/getting-started/installation/).

En Mac Intel, usá Miniforge para preparar el entorno de ejecución. [Instalar en Mac Intel](#instalar-en-mac-intel)

Cerrá y volvé a abrir la terminal para recargar el PATH. Si usás la terminal integrada, puede hacer falta reiniciar VS Code. Estos comandos sirven en Windows, Linux y macOS con Apple Silicon.

```console
uv --version
uv sync --locked
uv run --locked nubbix prompts check
uv run --locked nubbix web
```

`.python-version` indica a uv que use Python 3.12. Con `uv run --locked` podés ejecutar los comandos de verificación con el entorno inactivo. [Pruebas, lint y tipos](../README.md#verificar-el-software)

## Detener procesos y consultar el código de salida

Usá `Ctrl+C` en la terminal donde está ejecutándose la aplicación. En `web`, Uvicorn deja de aceptar conexiones y permite hasta cinco segundos para completar solicitudes activas. Al vencer ese plazo cancela las pendientes; la aplicación espera su limpieza y cierra los clientes. El cierre total puede llevar más de cinco segundos porque incluye esa limpieza.

En `respond` y `eval run/compare/adversarial`, las señales cancelan el trabajo async pendiente y esperan el cierre de recursos. `Ctrl+C` (`SIGINT`) devuelve `130`; `SIGTERM` devuelve `143` cuando llega al handler de Python. La CLI escribe `{"error": {"code": "cancelled"}}` en stderr, sin respuesta normal en stdout. Las evaluaciones conservan el reporte parcial en disco y no se reanudan automáticamente. Señales `SIGTERM` repetidas durante la limpieza no vuelven a cancelarla.

Para consultar el código de salida, ejecutá inmediatamente después del comando:

| Shell | Consultar el código |
| --- | --- |
| PowerShell | `$LASTEXITCODE` |
| CMD | `echo %ERRORLEVEL%` |
| Git Bash / Bash / Zsh | `echo $?` |

En Linux, macOS y WSL, `SIGTERM` permite solicitar este cierre desde otro proceso. En Windows, preferí `Ctrl+C` en la consola: `os.kill(pid, SIGTERM)` termina el proceso mediante `TerminateProcess`, según la [documentación de Python](https://docs.python.org/3.12/library/os.html#os.kill). Git Bash sigue usando el Python de Windows y comparte esa limitación.

La cancelación es cooperativa: se procesa en los puntos de espera async, y una operación síncrona como la lectura de `--stdin` puede demorarla. Un cierre forzado del sistema operativo, como `SIGKILL` o `taskkill /F`, no permite garantizar limpieza ni persistencia. Interrumpir una llamada tampoco garantiza que el proveedor no la haya cobrado; el consumo desconocido conserva su reserva estimada.

## Problemas frecuentes

| Mensaje o situación | Qué comprobar |
| --- | --- |
| `uv: command not found` o "uv no se reconoce" | Para instalar y ejecutar la app, seguí el [inicio rápido con Python](../README.md#inicio-rápido). Si ya instalaste uv para desarrollo, reabrí la terminal para actualizar el PATH. |
| `python` o `python3` falta o muestra una versión anterior a 3.12 | Seleccioná un intérprete instalado de Python 3.12 o superior. En Windows, si el lanzador `py` encuentra tu instalación 3.12, usá `py -3.12 --version` y `py -3.12 -m venv .venv` para las primeras dos líneas. Ajustá la versión si instalaste otra. |
| `ensurepip is not available` al crear `.venv` en Debian o Ubuntu | Para el Python predeterminado, ejecutá `sudo apt install python3-venv` y volvé a crear el entorno. Si elegiste otro intérprete, instalá su paquete `venv`, por ejemplo `python3.12-venv`. |
| `cryptography` no encuentra OpenSSL al instalar en Mac Intel | Usá el binario de conda-forge en un entorno de [Miniforge](#instalar-en-mac-intel) y repetí la instalación en ese entorno. |
| `No module named pip` en un `.venv` creado por uv | Si la app ya está instalada, usá el Python de ese entorno para ejecutarla. Para instalar con `pip`, prepará un entorno nuevo con `venv`. |
| Bash muestra `.venvScriptspython.exe` | Se copiaron barras `\` de un comando de Windows. Usá `./.venv/Scripts/python.exe` en Git Bash. |
| No aparece `.venv` al ejecutar `ls` | En Git Bash y Bash/Zsh, `ls -a` incluye los nombres que comienzan con punto. |
| No existe el ejecutable de `.venv` | Revisá que estés en la raíz del checkout y que hayas instalado el entorno para ese sistema operativo. |
| `No module named nubbix_support_ai` | Confirmá que ejecutás el Python del entorno en el que instalaste la app. Si usás `pip`, repetí la instalación en ese entorno. Si usás uv, ejecutá `uv sync --locked`. |
