import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from starlette.requests import ClientDisconnect

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.support.contracts import AppError
from tests.helpers import ScriptedProvider, settings_at


@pytest.mark.asyncio
async def test_stream_orders_events_before_result_and_persists_the_same_run(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    runtime = Runtime(settings, {"openai": ScriptedProvider()})
    app = create_app(settings, runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/lab/runs/stream", json={"ticket": "Cargo duplicado"})
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert rows[0]["type"] == "accepted"
    assert rows[-1]["type"] == "result"
    events = [row["event"] for row in rows if row["type"] == "event"]
    assert events[0]["event"] == "request.received"
    assert events[-1]["event"] == "run.completed"
    assert [event["sequence"] for event in events] == list(range(1, len(events) + 1))
    run_id = rows[-1]["run_id"]
    assert all(event["request_id"] == run_id for event in events)
    assert runtime.store.get_run(run_id)["response"] == rows[-1]["response"]


@pytest.mark.asyncio
async def test_operational_errors_are_terminal_sanitized_stream_records(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider([AppError("provider_unavailable"), AppError("provider_unavailable")])
    app = create_app(settings, Runtime(settings, {"openai": provider}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/lab/runs/stream", json={"ticket": "Un error"})
    rows = [json.loads(line) for line in response.text.splitlines()]
    assert response.status_code == 200
    assert rows[-1]["type"] == "error"
    assert rows[-1]["error"]["code"] == "provider_unavailable"
    assert rows[-1]["error"]["request_id"] is not None
    assert not any(row["type"] == "result" for row in rows)


@pytest.mark.asyncio
async def test_stream_disconnect_cancels_provider_and_preserves_cancelled_history(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider(delay=30)
    runtime = Runtime(settings, {"openai": provider})
    app = create_app(settings, runtime)
    disconnected = asyncio.Event()
    sent: list[dict[str, Any]] = []
    body = json.dumps({"ticket": "Cancelar"}).encode()
    received = False
    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}
    async def send(message: dict[str, Any]) -> None:
        sent.append(message)
        if message["type"] == "http.response.body" and b'"event"' in message.get("body", b""):
            disconnected.set()
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.3"},
             "method": "POST", "path": "/api/lab/runs/stream", "raw_path": b"/api/lab/runs/stream",
             "query_string": b"", "headers": [(b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1000), "server": ("test", 80), "scheme": "http"}
    await asyncio.wait_for(app(scope, receive, send), timeout=3)
    runs = runtime.store.list_runs()
    assert len(runs) == 1
    assert runs[0]["status"] == "cancelled"
    assert len(provider.calls) <= 1
    assert not any(b'"type":"result"' in item.get("body", b"") for item in sent)


@pytest.mark.asyncio
async def test_stream_backpressure_is_bounded_and_closes_its_task() -> None:
    from nubbix_support_ai.web.streaming import stream_operation
    produced = 0
    cancelled = asyncio.Event()
    async def work(emit: Any) -> dict[str, Any]:
        nonlocal produced
        try:
            for index in range(1000):
                await emit({"index": index})
                produced += 1
        finally:
            cancelled.set()
        return {"done": True}
    stream: AsyncIterator[str] = stream_operation(work, operation="test", queue_size=2)
    assert json.loads(await anext(stream))["type"] == "accepted"
    await asyncio.sleep(0.02)
    assert produced <= 2
    await stream.aclose()  # type: ignore[attr-defined]
    assert cancelled.is_set()


@pytest.mark.asyncio
async def test_send_failure_closes_stream_even_when_asgi_uses_disconnect_exceptions(
    tmp_path: Path,
) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider(delay=30)
    runtime = Runtime(settings, {"openai": provider})
    app = create_app(settings, runtime)
    received = False
    body = json.dumps({"ticket": "Conexión interrumpida"}).encode()
    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()
        return {"type": "http.disconnect"}
    async def send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.body" and b'"event"' in message.get("body", b""):
            raise OSError("connection closed")
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"},
             "method": "POST", "path": "/api/lab/runs/stream", "raw_path": b"/api/lab/runs/stream",
             "query_string": b"", "headers": [(b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1000), "server": ("test", 80), "scheme": "http"}
    with pytest.raises(ClientDisconnect):
        await asyncio.wait_for(app(scope, receive, send), timeout=3)
    assert runtime.store.list_runs()[0]["status"] == "cancelled"
    assert not app.state.stream_tasks
