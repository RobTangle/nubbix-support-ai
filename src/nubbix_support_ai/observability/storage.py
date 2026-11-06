import json
import os
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from filelock import FileLock

from nubbix_support_ai.support.contracts import AppError


class RunStore:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def _directory(self, request_id: str) -> Path:
        try:
            if str(UUID(request_id)) != request_id:
                raise ValueError
        except ValueError:
            raise AppError("invalid_run_id") from None
        return self.data_dir / "runs" / request_id

    def write_inspection(self, request_id: str, value: dict[str, Any]) -> None:
        directory = self._directory(request_id)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / "inspection.json"
            temporary = directory / f"inspection-{uuid4()}.tmp"
            temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False),
                                 encoding="utf-8")
            os.replace(temporary, target)
        except (OSError, ValueError, TypeError):
            raise AppError("storage_error") from None

    def append_event(self, request_id: str, event: dict[str, Any]) -> None:
        self._append(self._directory(request_id) / "events.jsonl", event)

    def append_metric(self, metric: dict[str, Any]) -> None:
        self._append(self.data_dir / "metrics.jsonl", metric)

    def _append(self, path: Path, value: dict[str, Any]) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n"
            with FileLock(str(path) + ".lock", timeout=5):
                with path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(line)
        except (OSError, ValueError, TypeError, TimeoutError):
            raise AppError("storage_error") from None

    def get_run(self, request_id: str) -> dict[str, Any]:
        directory = self._directory(request_id)
        try:
            value: dict[str, Any] = json.loads((directory / "inspection.json").read_text("utf-8"))
            events = directory / "events.jsonl"
            value["events"] = [json.loads(line) for line in events.read_text("utf-8").splitlines()]
            return value
        except FileNotFoundError:
            raise AppError("run_not_found") from None
        except (OSError, ValueError):
            raise AppError("storage_error") from None

    def list_runs(self, *, provider: str | None = None, prompt_version: str | None = None,
                  status: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        summaries = []
        for path in (self.data_dir / "runs").glob("*/inspection.json"):
            try:
                data = json.loads(path.read_text("utf-8"))
                if provider and data["provider"] != provider:
                    continue
                if prompt_version and data["prompt_version"] != prompt_version:
                    continue
                if status and data["status"] != status:
                    continue
                summaries.append({key: data.get(key) for key in (
                    "request_id", "timestamp", "provider", "model", "prompt_version", "status",
                    "metrics", "response", "ticket",
                )})
            except (OSError, ValueError, KeyError):
                continue
        return sorted(summaries, key=lambda row: row["timestamp"], reverse=True)[:limit]
