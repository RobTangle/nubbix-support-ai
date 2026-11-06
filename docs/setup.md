# Instalación y terminales

Todos los ejemplos parten de la raíz del repositorio, donde están `pyproject.toml` y `.env.example`. Copiá sólo los comandos de los bloques, sin agregar el indicador `$`, `PS>` o `C:\>` de tu terminal.

## Elegir los comandos correctos

[Windows Terminal](https://learn.microsoft.com/en-us/windows/terminal/) es una aplicación que aloja shells. La terminal integrada de VS Code también ejecuta el shell que hayas seleccionado. La sintaxis depende de ese perfil:

| Shell | Cómo reconocerlo | Python del entorno virtual |
| --- | --- | --- |
| PowerShell en Windows | El prompt suele comenzar con `PS`. | `.\.venv\Scripts\python.exe` |
| CMD en Windows | Prompt similar a `C:\proyectos\nubbix-support-ai>`. | `.venv\Scripts\python.exe` |
| Git Bash en Windows | El prompt suele incluir `MINGW64` y terminar en `$`. | `./.venv/Scripts/python.exe` |
| Bash/Zsh en Linux o macOS | Shell del sistema; suele terminar en `$` o `%`. | `./.venv/bin/python` |
| Bash/Zsh en WSL | Perfil de una distribución Linux, como Ubuntu. | `./.venv/bin/python` |

Git Bash ejecuta el Python de Windows usando sintaxis Bash. WSL ejecuta herramientas Linux: usá un checkout y un entorno virtual propios dentro de esa distribución. Los entornos virtuales de Windows y Linux tienen ejecutables y dependencias diferentes.

En Bash/Zsh usá `/` en las rutas; una barra `\` sin comillas escapa el carácter siguiente. Los ejemplos usan comandos de una sola línea para evitar también las diferencias entre continuaciones de línea de cada shell.

## Probar una instalación existente sin uv

Si el repo ya tiene `.venv` con las dependencias instaladas y `.env` configurado, podés usarlo directamente. La activación es opcional al indicar la ruta completa al Python del entorno.

### PowerShell en Windows

```powershell
.\.venv\Scripts\python.exe -m nubbix_support_ai prompts check
.\.venv\Scripts\python.exe -m nubbix_support_ai web
```

### CMD en Windows

```bat
.venv\Scripts\python.exe -m nubbix_support_ai prompts check
.venv\Scripts\python.exe -m nubbix_support_ai web
```

### Git Bash en Windows

```bash
./.venv/Scripts/python.exe -m nubbix_support_ai prompts check
./.venv/Scripts/python.exe -m nubbix_support_ai web
```

### Bash/Zsh en Linux, macOS o WSL

```bash
./.venv/bin/python -m nubbix_support_ai prompts check
./.venv/bin/python -m nubbix_support_ai web
```

`prompts check` valida los recursos sin llamar a un modelo. `web` mantiene el servidor abierto: visitá [http://127.0.0.1:8000](http://127.0.0.1:8000) y detenelo con `Ctrl+C`. Abrir el laboratorio no consume API; analizar tickets y ejecutar evaluaciones sí.

Para probar una consulta desde otra pestaña, conservá el ejecutable correspondiente a tu shell y reemplazá `web` por `respond`. Por ejemplo, en Git Bash:

```bash
./.venv/Scripts/python.exe -m nubbix_support_ai respond --provider openai --text "Me cobraron dos veces este mes"
```

## Instalar desde un checkout nuevo con uv

### Instalar uv y comprobar el PATH

En Windows, si tenés WinGet, el comando es el mismo desde PowerShell, CMD o Git Bash:

```console
winget install --id=astral-sh.uv -e
```

En Bash/Zsh de Linux, macOS o WSL:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Estos métodos están documentados en la [instalación oficial de uv](https://docs.astral.sh/uv/getting-started/installation/), que también ofrece alternativas si no tenés WinGet o curl. Cerrá y volvé a abrir la terminal para recargar el PATH; si usás la terminal integrada, puede hacer falta reiniciar VS Code. Después comprobá:

```console
uv --version
```

Si todavía aparece `command not found` o "no se reconoce", uv no está disponible en el PATH de ese shell. Podés usar la instalación existente como se explica arriba mientras resolvés su instalación.

### Instalar las dependencias

Con uv disponible, estos comandos sirven en todos los shells de la tabla:

```console
uv sync --locked
```

El archivo `.python-version` selecciona Python 3.12 para el entorno del proyecto. uv crea o sincroniza `.venv` usando `uv.lock` e incluye las dependencias de desarrollo. No necesitás activar el entorno para usar `uv run --locked`.

### Configurar las claves locales

Ejecutá sólo el bloque correspondiente a tu shell. Cada variante conserva un `.env` existente.

PowerShell:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

CMD:

```bat
if not exist .env copy .env.example .env
```

Git Bash, Bash o Zsh:

```bash
if [ ! -e .env ]; then cp .env.example .env; fi
```

Abrí `.env` en tu editor y completá `OPENAI_API_KEY` y/o `GEMINI_API_KEY`. Cada proveedor funciona con su propia clave. El archivo permanece fuera de Git.

### Ejecutar la aplicación

Estos comandos son iguales en PowerShell, CMD, Git Bash y Bash/Zsh:

```console
uv run --locked nubbix prompts check
uv run --locked nubbix web
```

Para otro puerto: `uv run --locked nubbix web --port 8080`. Para una consulta por CLI:

```console
uv run --locked nubbix respond --provider openai --text "Me cobraron dos veces este mes"
```

Los comandos de [evaluación](evaluation.md) y [verificación del software](../README.md#verificar-el-software) también usan `uv run --locked` con la misma sintaxis en todos estos shells.

## Activar el entorno, si preferís comandos cortos

La activación agrega temporalmente los ejecutables de `.venv` al PATH de esa terminal:

| Shell y sistema | Activar |
| --- | --- |
| PowerShell en Windows | `.\.venv\Scripts\Activate.ps1` |
| CMD en Windows | `.venv\Scripts\activate.bat` |
| Git Bash en Windows | `source .venv/Scripts/activate` |
| Bash/Zsh en Linux, macOS o WSL | `source .venv/bin/activate` |

Después podés usar el mismo comando en cualquiera de esos shells:

```console
python -m nubbix_support_ai web
```

Para salir del entorno, ejecutá `deactivate`. Si PowerShell bloquea `Activate.ps1`, podés ejecutar el Python por su ruta completa; no hace falta cambiar la política de ejecución para iniciar la aplicación.

## Instalación inicial con pip

Esta alternativa sirve para un checkout sin entorno virtual cuando preferís trabajar sin uv. Necesitás Python 3.12 o superior ya instalado. `requirements.txt` contiene las dependencias de ejecución exportadas del lock; el paquete se instala en modo editable para resolver los recursos desde el checkout.

En Windows, creá el entorno desde PowerShell, CMD o Git Bash:

```console
py -3.12 -m venv .venv
```

Si tu instalación es Python 3.13, usá `py -3.13` en ese comando. Si no tenés el launcher `py`, podés usar `python -m venv .venv` después de comprobar con `python --version` que corresponde a Python 3.12 o superior.

Luego instalá desde PowerShell o CMD:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

O desde Git Bash:

```bash
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m pip install --no-deps -e .
```

En Bash/Zsh de Linux, macOS o WSL, comprobá primero `python3 --version` y creá e instalá el entorno:

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m pip install --no-deps -e .
```

Después configurá `.env` e iniciá la aplicación con las instrucciones anteriores. Esta alternativa instala el runtime; las herramientas de desarrollo, como pytest, Ruff y mypy, se incluyen al usar `uv sync --locked`.

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
| `uv: command not found` / "uv no se reconoce" | Instalá uv y reabrí la terminal; si `.venv` ya está preparado, usá su Python directamente. |
| Bash muestra `.venvScriptspython.exe` | Se copiaron barras `\` de un comando de Windows. Usá `./.venv/Scripts/python.exe` en Git Bash. |
| No aparece `.venv` al ejecutar `ls` | En Git Bash y Bash/Zsh, `ls -a` incluye los nombres que comienzan con punto. |
| No existe el ejecutable de `.venv` | Revisá que estés en la raíz del checkout y que hayas instalado el entorno para ese sistema operativo. |
| `No module named nubbix_support_ai` | Usá el Python de `.venv`; completá `uv sync --locked` o la instalación editable de la alternativa con pip. |
| La terminal muestra un entorno activo, pero falla `uv` | La activación del entorno y la instalación de uv son independientes. |
