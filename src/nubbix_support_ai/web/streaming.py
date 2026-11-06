import asyncio
import json
from collections.abc import AsyncGenerator, Awaitable, Callable
from typing import Any

from fastapi.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from nubbix_support_ai.support.contracts import AppError
from nubbix_support_ai.web.lifecycle import cancel_and_drain

StreamWork = Callable[[Callable[[dict[str, Any]], Awaitable[None]]], Awaitable[dict[str, Any]]]


class LabStream(StreamingResponse):
    """Close owned work on receive disconnects and ASGI 2.4 send failures."""

    def __init__(self, content: AsyncGenerator[str, None]) -> None:
        self._stream = content
        super().__init__(content, media_type="application/x-ndjson",
                         headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._stream.aclose()


async def stream_operation(work: StreamWork, *, operation: str, queue_size: int = 32,
                           tasks: set[asyncio.Task[Any]] | None = None) -> AsyncGenerator[str, None]:
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=queue_size)
    async def emit(event: dict[str, Any]) -> None:
        await queue.put({"type": "event", "event": event})
    async def produce() -> None:
        try:
            result = await work(emit)
        except asyncio.CancelledError:
            raise
        except AppError as exc:
            await queue.put({"type": "error", "error": {
                "code": exc.code, "request_id": exc.request_id,
            }})
        except Exception:
            await queue.put({"type": "error", "error": {
                "code": "internal_error", "request_id": None,
            }})
        else:
            await queue.put({"type": "result", **result})
    task = asyncio.create_task(produce(), name=f"lab-{operation}")
    if tasks is not None:
        tasks.add(task)
        task.add_done_callback(tasks.discard)
    try:
        yield json.dumps({"type": "accepted", "operation": operation}) + "\n"
        while True:
            item = await queue.get()
            yield json.dumps(item, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n"
            if item["type"] in {"result", "error"}:
                break
    finally:
        await cancel_and_drain(task)
