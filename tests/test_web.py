import importlib.util
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

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
    assert {item["id"] for item in catalog["prompts"]} == {"v1", "v2"}
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
    assert response.status_code == script.status_code == stylesheet.status_code == 200
    assert '<html lang="es"' in response.text
    assert 'aria-live="polite"' in response.text
    assert 'name="viewport"' in response.text
    assert "https://" not in response.text
    assert "innerHTML" not in script.text
    assert "textContent" in script.text
