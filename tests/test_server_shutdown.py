import asyncio
import json
import socket
from contextlib import asynccontextmanager, contextmanager
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
import uvicorn

from nubbix_support_ai import cli
from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.llm.contracts import LLMReply
from nubbix_support_ai.web import app as web_app
from tests.helpers import ALLOW, PROPOSAL, USAGE, ScriptedProvider, settings_at


class GatedProvider(ScriptedProvider):
    def __init__(self, data_directory: Path) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.data_directory = data_directory
        self.statuses_at_close: list[str] = []

    async def complete(self, request):
        self.calls.append(request)
        try:
            if len(self.calls) == 1:
                self.started.set()
                await self.release.wait()
            value = PROPOSAL if "answer" in request.schema["properties"] else ALLOW
            return LLMReply(json.dumps(value), USAGE, self.model)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def aclose(self):
        path = self.data_directory / "metrics.jsonl"
        if path.exists():
            self.statuses_at_close = [
                json.loads(line)["status"] for line in path.read_text("utf-8").splitlines()
            ]
        await super().aclose()


class TestServer(uvicorn.Server):
    __test__ = False

    @contextmanager
    def capture_signals(self):
        yield


class SlowCleanupProvider(GatedProvider):
    def __init__(self, data_directory):
        super().__init__(data_directory)
        self.cleanup_finished = False
        self.cleanup_finished_at_close = False

    async def complete(self, request):
        try:
            return await super().complete(request)
        finally:
            await asyncio.sleep(0.3)
            self.cleanup_finished = True

    async def aclose(self):
        self.cleanup_finished_at_close = self.cleanup_finished
        await super().aclose()


@asynccontextmanager
async def server_from_cli(tmp_path, monkeypatch, provider_type=GatedProvider):
    settings = settings_at(tmp_path, openai_api_key=None, gemini_api_key=None)
    provider = provider_type(settings.data_dir)
    runtime = Runtime(settings, providers={"openai": provider})
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(web_app, "Runtime", lambda _: runtime)
    captured = {}
    def capture_server(app, **options):
        captured.update(app=app, **options)
    monkeypatch.setattr(cli.uvicorn, "run", capture_server)
    assert cli.main(["web"]) == 0
    config = uvicorn.Config(**captured, lifespan="on", log_level="critical", log_config=None)
    server = TestServer(config)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    address = f"http://127.0.0.1:{listener.getsockname()[1]}"
    serving = asyncio.create_task(server.serve(sockets=[listener]))
    try:
        async with asyncio.timeout(3):
            while not server.started:
                if serving.done():
                    await serving
                await asyncio.sleep(0.01)
        yield server, serving, provider, runtime, address
    finally:
        provider.release.set()
        server.should_exit = True
        try:
            await asyncio.wait_for(asyncio.shield(serving), timeout=3)
        except TimeoutError:
            serving.cancel()
            await asyncio.wait_for(asyncio.gather(serving, return_exceptions=True), timeout=3)
        finally:
            listener.close()


async def test_server_shutdown_finishes_an_active_request_within_grace(tmp_path, monkeypatch):
    async with server_from_cli(tmp_path, monkeypatch) as (server, serving, provider, runtime, url):
        async with httpx.AsyncClient(base_url=url, timeout=10) as client:
            request = asyncio.create_task(client.post("/api/triage", json={"ticket": "Cargo duplicado"}))
            try:
                await asyncio.wait_for(provider.started.wait(), timeout=3)
                server.should_exit = True
                await asyncio.sleep(0.25)
                assert not serving.done()
                assert not provider.closed
                provider.release.set()
                response = await asyncio.wait_for(request, timeout=3)
                await asyncio.wait_for(serving, timeout=3)
            finally:
                provider.release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), timeout=3)
        assert response.status_code == 200
        assert response.json() == PROPOSAL
        assert len(provider.calls) == 3
        assert provider.cancelled is False
        assert provider.closed is True
        assert provider.statuses_at_close == ["ok"]
        assert runtime.store.list_runs()[0]["status"] == "ok"


@pytest.mark.parametrize("path", ["/api/triage", "/api/lab/runs/stream"])
async def test_server_shutdown_cancels_requests_after_five_seconds(tmp_path, monkeypatch, path):
    async with server_from_cli(tmp_path, monkeypatch) as (server, serving, provider, runtime, url):
        async with httpx.AsyncClient(base_url=url, timeout=10) as client:
            request = asyncio.create_task(client.post(path, json={"ticket": "Esperar para cancelar"}))
            try:
                await asyncio.wait_for(provider.started.wait(), timeout=3)
                started = asyncio.get_running_loop().time()
                server.should_exit = True
                await asyncio.wait_for(asyncio.shield(serving), timeout=7)
                elapsed = asyncio.get_running_loop().time() - started
                responses = await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), 2)
            finally:
                provider.release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), timeout=3)
        assert 4.5 <= elapsed < 7
        assert server.config.timeout_graceful_shutdown == 5
        assert provider.cancelled is True
        assert len(provider.calls) == 1
        assert provider.closed is True
        assert provider.statuses_at_close == ["cancelled"]
        runs = runtime.store.list_runs()
        assert len(runs) == 1 and runs[0]["status"] == "cancelled"
        inspection = runtime.store.get_run(runs[0]["request_id"])
        metrics = inspection["metrics"]
        assert metrics["usage_complete"] is False
        assert metrics["total_tokens"] is None
        assert Decimal(metrics["reserved_unknown_usd"]) > 0
        assert Decimal(metrics["estimated_cost_usd"]) > 0
        assert inspection["response"] is None
        assert not server.config.app.state.stream_tasks
        response = responses[0]
        if isinstance(response, httpx.Response):
            if path.endswith("/stream"):
                rows = [json.loads(line) for line in response.text.splitlines() if line]
                assert not any(row["type"] == "result" for row in rows)
            else:
                assert response.status_code >= 400
        else:
            assert isinstance(response, httpx.HTTPError)


@pytest.mark.parametrize("path,payload", [
    ("/api/lab/runs/stream", {"ticket": "Esperar para cancelar"}),
    ("/api/lab/evaluations/stream", {"prompt_versions": ["v1"], "limit": 2}),
])
async def test_server_shutdown_waits_for_stream_cleanup_before_closing_clients(
    tmp_path, monkeypatch, path, payload,
):
    async with server_from_cli(tmp_path, monkeypatch, SlowCleanupProvider) as context:
        server, serving, provider, runtime, url = context
        server.config.timeout_graceful_shutdown = 0.1
        async with httpx.AsyncClient(base_url=url, timeout=5) as client:
            request = asyncio.create_task(client.post(path, json=payload))
            try:
                await asyncio.wait_for(provider.started.wait(), timeout=3)
                server.should_exit = True
                await asyncio.wait_for(serving, timeout=3)
            finally:
                provider.release.set()
                await asyncio.wait_for(asyncio.gather(request, return_exceptions=True), timeout=3)
        assert provider.cleanup_finished is True
        assert provider.cleanup_finished_at_close is True
        assert provider.closed is True and len(provider.calls) == 1
        assert provider.statuses_at_close == ["cancelled"]
        assert not server.config.app.state.stream_tasks
        assert runtime.store.list_runs()[0]["status"] == "cancelled"
