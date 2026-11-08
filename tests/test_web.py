import asyncio
import importlib.util
import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from starlette.requests import ClientDisconnect

from nubbix_support_ai.bootstrap import Runtime
from tests.helpers import PROPOSAL, ScriptedProvider, settings_at


def test_web_factory_is_available() -> None:
    try:
        spec = importlib.util.find_spec("nubbix_support_ai.web.app")
    except ModuleNotFoundError:
        spec = None
    assert spec is not None


@pytest.mark.asyncio
async def test_triage_returns_only_the_public_contract(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider()
    runtime = Runtime(settings, {"openai": provider})
    app = create_app(settings, runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/triage", json={"ticket": "Me cobraron dos veces."})
    assert response.status_code == 200
    assert response.json() == PROPOSAL
    assert len(provider.calls) == 3


@pytest.mark.parametrize("spec_version", ["2.3", "2.4"])
async def test_json_triage_disconnect_cancels_work_and_preserves_history(tmp_path, spec_version):
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider(delay=30)
    runtime = Runtime(settings, {"openai": provider})
    app = create_app(settings, runtime)
    received = False
    sent: list[dict[str, Any]] = []
    body = json.dumps({"ticket": "Cancelar consulta"}).encode()
    async def receive() -> dict[str, Any]:
        nonlocal received
        if not received:
            received = True
            return {"type": "http.request", "body": body, "more_body": False}
        while not provider.calls:
            await asyncio.sleep(0)
        return {"type": "http.disconnect"}
    async def send(message: dict[str, Any]) -> None:
        sent.append(message)
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": spec_version},
             "method": "POST", "path": "/api/triage", "raw_path": b"/api/triage",
             "query_string": b"", "headers": [(b"content-type", b"application/json")],
             "client": ("127.0.0.1", 1000), "server": ("test", 80), "scheme": "http"}
    with pytest.raises(ClientDisconnect):
        await asyncio.wait_for(app(scope, receive, send), timeout=1)
    runs = runtime.store.list_runs()
    assert len(runs) == 1 and runs[0]["status"] == "cancelled"
    assert len(provider.calls) == 1
    assert not app.state.stream_tasks
    assert not any(item["type"] == "http.response.start" and item["status"] == 200 for item in sent)


async def test_shutdown_cancels_active_json_triage_before_closing_runtime(tmp_path):
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider(delay=30)
    runtime = Runtime(settings, {"openai": provider})
    app = create_app(settings, runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            request = asyncio.create_task(client.post("/api/triage", json={"ticket": "Cancelar"}))
            while not provider.calls:
                await asyncio.sleep(0)
            tracked = bool(app.state.stream_tasks)
        if not tracked:
            request.cancel()
        await asyncio.gather(request, return_exceptions=True)
    assert tracked is True
    assert runtime.store.list_runs()[0]["status"] == "cancelled"
    assert not app.state.stream_tasks


@pytest.mark.asyncio
async def test_catalog_does_not_initialize_clients_or_disclose_secrets(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path, openai_api_key=SecretStr("private-test-key"))
    runtime = Runtime(settings)
    app = create_app(settings, runtime)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                    base_url="http://test") as client:
            response = await client.get("/api/lab/catalog")
    catalog = response.json()
    assert response.status_code == 200
    assert "private-test-key" not in response.text
    assert runtime._providers == {}
    assert catalog["default_prompt"] == runtime.catalog.default
    assert catalog["prompts"] == [item.model_dump() for item in runtime.catalog.versions]
    assert catalog["providers"][0]["available"] is True
    assert catalog["providers"][1]["available"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"ticket": " "}, {"ticket": "x", "extra": "unsafe"},
                                    {"ticket": "x", "provider": "unknown"},
                                    {"ticket": "x", "prompt_version": "missing"},
                                    {"ticket": "x", "model": "unpriced"}])
async def test_invalid_input_does_not_call_a_provider(tmp_path: Path, payload: dict[str, str]) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider()
    app = create_app(settings, Runtime(settings, {"openai": provider}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/lab/runs/stream", json=payload)
    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/json")
    assert provider.calls == []


@pytest.mark.asyncio
async def test_lifespan_closes_only_owned_runtime(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider()
    runtime = Runtime(settings, {"openai": provider})
    app = create_app(settings, runtime)
    async with app.router.lifespan_context(app):
        assert app.state.runtime is runtime
    assert provider.closed is False
    owned = create_app(settings)
    async with owned.router.lifespan_context(owned):
        owned.state.runtime._providers[("openai", provider.model)] = provider
    assert provider.closed is True


@pytest.mark.asyncio
async def test_lab_is_local_and_serves_accessible_static_assets(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    app = create_app(settings, Runtime(settings, {"openai": ScriptedProvider()}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get("/")
        script = await client.get("/static/app.js")
        stylesheet = await client.get("/static/styles.css")
        progress = await client.get("/static/progress.js")
        evaluation_help = await client.get("/static/evaluation-help.js")
        unchanged = await client.get("/static/evaluation-help.js",
                                     headers={"If-None-Match": evaluation_help.headers["etag"]})
    assert response.status_code == script.status_code == stylesheet.status_code == 200
    assert progress.status_code == 200
    assert evaluation_help.status_code == 200
    assert unchanged.status_code == 304
    for asset in (response, script, stylesheet, progress, evaluation_help, unchanged):
        assert asset.headers.get("cache-control") == "no-cache"
    assert "javascript" in progress.headers["content-type"]
    assert '<html lang="es"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'name="viewport"' in response.text
    assert "https://" not in response.text
    assert "innerHTML" not in script.text
    assert "textContent" in script.text
