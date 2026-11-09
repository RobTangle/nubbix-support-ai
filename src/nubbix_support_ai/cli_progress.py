import asyncio
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, TextIO, cast

from nubbix_support_ai.observability.events import FlowEvent, Scalar

_PROVIDERS = {"openai": "OpenAI", "google": "Gemini"}
_STAGES = {
    "input_moderation": "Revisando entrada",
    "generation": "Generando propuesta",
    "output_moderation": "Revisando salida",
}
_ERRORS = {
    "authentication_error": "la clave del proveedor fue rechazada",
    "budget_exceeded": "se alcanzó el presupuesto",
    "connection_error": "se interrumpió la conexión con el proveedor",
    "deadline_exceeded": "se agotó el tiempo del ticket",
    "incomparable_prompt_bundles": "esas versiones requieren campañas separadas",
    "invalid_dataset": "no se pudo leer un dataset válido",
    "invalid_input_or_configuration": "revisá la consulta y la configuración",
    "invalid_model_output": "la respuesta no cumple el formato esperado",
    "io_error": "no se pudo leer o escribir la salida",
    "missing_google_key": "configurá GEMINI_API_KEY",
    "missing_openai_key": "configurá OPENAI_API_KEY",
    "model_not_found": "el proveedor no encontró el modelo",
    "permission_denied": "el proveedor rechazó el acceso",
    "provider_unavailable": "el proveedor no está disponible",
    "quota_exhausted": "cuota agotada en el proveedor",
    "rate_limited": "el proveedor limitó el ritmo de llamadas",
    "storage_error": "no se pudo guardar o leer el registro local",
    "timeout": "la llamada superó su tiempo máximo",
}
_CASE_OUTCOMES = {"blocked": "bloqueado", "escalated": "revisión humana sugerida"}
_TICKET_OUTCOMES = {
    "blocked": "Ticket bloqueado por seguridad",
    "escalated": "Ticket procesado · revisión humana sugerida",
}


def _error_text(code: Scalar) -> str:
    return _ERRORS.get(str(code), f"error de ejecución ({code})" if code else "error de ejecución")


class CliProgress:
    def __init__(self, stream: TextIO, requested: bool | None, reports_dir: Path) -> None:
        terminal = stream.isatty()
        self.enabled = terminal if requested is None else requested
        self._compact = terminal and os.environ.get("TERM") != "dumb"
        self._stream = stream
        self._reports_dir = reports_dir
        self._started = time.monotonic()
        self._last_output = self._started
        self._status_width = 0
        self._activity = ""
        self._case = ""
        self._campaign_id: str | None = None
        self._completed = 0
        self._total = 0
        self._ticket_status = ""

    @asynccontextmanager
    async def live(self) -> AsyncIterator[None]:
        if not self.enabled:
            yield
            return
        heartbeat = asyncio.create_task(self._heartbeat())
        try:
            yield
        finally:
            heartbeat.cancel()
            self._clear_status()
            await asyncio.gather(heartbeat, return_exceptions=True)

    def start_ticket(self, provider: str, model: str) -> None:
        self._activity = "Preparando ticket"
        self._note(f"Analizando ticket · {_PROVIDERS.get(provider, provider)} · {model}")

    async def on_event(self, event: FlowEvent) -> None:
        if not self.enabled:
            return
        details = event.details
        match event.event:
            case "evaluation.started":
                self._campaign_id = event.request_id
                self._total = cast(int, details["total"])
                provider = str(details["provider"])
                self._note(
                    f"Evaluando {details['split']} · {details['versions']} · "
                    f"{_PROVIDERS.get(provider, provider)} · {details['model']} · "
                    f"{self._total} ejecuciones"
                )
            case "evaluation.case.started":
                self._case = f"{details['case_id']} · {details['prompt_version']}"
                if details["arm"] == "unguarded":
                    self._case += " · sin revisiones"
                self._activity = "Preparando caso"
                if self._compact or not self._completed:
                    self._show_activity()
            case "evaluation.case.completed":
                self._completed = cast(int, details["completed"])
                self._activity = ""
                status = str(details["status"])
                if status == "error":
                    self._note(f"{self._count()} · {self._case} · Error · "
                               f"{_error_text(details.get('error_code'))}")
                elif not self._compact:
                    self._note(f"{self._count()} · {self._case} · "
                               f"{_CASE_OUTCOMES.get(status, 'completado')}")
            case "llm.request.started" if event.stage is not None:
                self._activity = _STAGES[event.stage]
                if event.attempt is not None and event.attempt > 1:
                    self._activity += f" (intento {event.attempt})"
                if self._campaign_id is None or self._compact:
                    self._show_activity()
            case "retry.scheduled" if event.stage is not None:
                delay = cast(float, details["delay_seconds"])
                subject = f"{self._case} · " if self._campaign_id else ""
                self._note(f"{subject}Reintento en {delay:.2f} s · {_STAGES[event.stage]} · "
                           f"{_error_text(details.get('error_code'))}")
                self._activity = f"Esperando reintento · {_STAGES[event.stage].lower()}"
                if self._campaign_id and self._compact:
                    self._show_activity()
            case "run.completed" if self._campaign_id is None:
                self._ticket_status = str(details["status"])
                self._activity = "Guardando resultado"
            case "evaluation.completed":
                self._case = ""
                self._activity = "Guardando reporte"
                if self._compact:
                    self._show_activity()

    def finish_ticket(self) -> None:
        self._note(_TICKET_OUTCOMES.get(self._ticket_status, "Ticket procesado"))

    def finish_campaign(self, summary: dict[str, Any]) -> None:
        if not self.enabled:
            return
        partial = summary["status"] != "completed"
        label = (f"Evaluación detenida · {_error_text(summary['stopping_error'])}"
                 if partial else "Evaluación completa")
        self._note(f"{label} · {self._count()} · bloqueos {summary['blocked']} · "
                   f"errores {summary['errors']}")
        self._show_report("Reporte parcial" if partial else "Reporte")

    def fail(self, code: str | None) -> None:
        if not self.enabled:
            return
        incomplete = self._completed < self._total
        if code == "cancelled":
            label = "Evaluación cancelada" if incomplete else "Operación cancelada"
        else:
            label = f"Error · {_error_text(code)}"
        self._note(f"{label} · {self._count()}" if self._campaign_id else label)
        self._show_report("Reporte parcial" if incomplete else "Reporte guardado")

    async def _heartbeat(self) -> None:
        while self.enabled:
            await asyncio.sleep(1)
            if not self._activity:
                continue
            if ((self._compact and self._campaign_id)
                    or time.monotonic() - self._last_output >= 5):
                self._show_activity()

    def _count(self) -> str:
        return f"{self._completed}/{self._total} procesadas"

    def _show_activity(self) -> None:
        message = self._activity
        if self._campaign_id:
            message = f"{self._count()} · {message}"
            if self._case:
                message += f" · {self._case}"
        if not (self._compact and self._campaign_id):
            self._note(message)
            return
        width = self._terminal_width()
        line = self._format(message)
        if len(line) > width:
            line = line[:width - 1] + "…"
        self._write("\r" + line.ljust(min(width, self._status_width)))
        self._status_width = len(line)

    def _show_report(self, label: str) -> None:
        if self._campaign_id is None:
            return
        path = self._reports_dir / self._campaign_id / "summary.md"
        with suppress(OSError):
            if path.is_file():
                with suppress(ValueError):
                    path = path.relative_to(Path.cwd())
                self._note(f"{label} · {path.as_posix()}")

    def _terminal_width(self) -> int:
        try:
            columns = os.get_terminal_size(self._stream.fileno()).columns
        except (OSError, ValueError):
            columns = 0
        return max(1, (columns or 80) - 1)

    def _clear_status(self) -> None:
        if self._status_width:
            self._write("\r" + " " * min(self._status_width, self._terminal_width()) + "\r")
            self._status_width = 0

    def _format(self, message: str) -> str:
        minutes, seconds = divmod(int(time.monotonic() - self._started), 60)
        text = "".join(character if character.isprintable() else " " for character in message)
        return f"{minutes:02}:{seconds:02}  {text}"

    def _note(self, message: str) -> None:
        if self.enabled:
            self._clear_status()
            self._write(self._format(message) + "\n")

    def _write(self, text: str) -> None:
        if not self.enabled:
            return
        try:
            self._stream.write(text)
            self._stream.flush()
        except (OSError, ValueError):
            self.enabled = False
        else:
            self._last_output = time.monotonic()
