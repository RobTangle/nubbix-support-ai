import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from nubbix_support_ai.observability.storage import RunStore

Stage = Literal["input_moderation", "generation", "output_moderation"]
Scalar = str | int | float | bool | None


class FlowEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: int = 1
    request_id: str
    sequence: int
    timestamp: str
    elapsed_ms: float
    event: str
    stage: Stage | None = None
    attempt: int | None = None
    details: dict[str, Scalar]


EventSink = Callable[[FlowEvent], Awaitable[None]]


class RunRecorder:
    def __init__(self, request_id: str, store: RunStore, inspection: dict[str, Any],
                 on_event: EventSink | None) -> None:
        self.request_id = request_id
        self.store = store
        self.inspection = inspection
        self.on_event = on_event
        self.started = time.monotonic()
        self.events: list[FlowEvent] = []
        self.calls: list[dict[str, Any]] = []
        self.input_tokens = 0
        self.output_tokens = 0
        self.cached_tokens = 0
        self.cache_write_tokens = 0
        self.reasoning_tokens = 0
        self.usage_complete = True

    async def emit(self, event: str, *, stage: Stage | None = None, attempt: int | None = None,
                   notify: bool = True, **details: Scalar) -> None:
        item = FlowEvent(request_id=self.request_id, sequence=len(self.events) + 1,
                         timestamp=datetime.now(UTC).isoformat(),
                         elapsed_ms=round((time.monotonic() - self.started) * 1000, 3),
                         event=event, stage=stage, attempt=attempt, details=details)
        self.events.append(item)
        self.store.append_event(self.request_id, item.model_dump())
        if notify and self.on_event is not None:
            await self.on_event(item)

    def checkpoint(self) -> None:
        self.inspection["calls"] = self.calls
        self.store.write_inspection(self.request_id, self.inspection)
