from pathlib import Path

import httpx
import pytest

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.support.contracts import Ticket
from tests.helpers import ScriptedProvider, settings_at


@pytest.mark.asyncio
async def test_history_filters_and_inspector_correlate_with_stored_run(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    runtime = Runtime(settings, {"openai": ScriptedProvider()})
    run = await runtime.service().run(Ticket(text="<script>alert('ticket')</script>"),
                                      prompt_version="v2")
    app = create_app(settings, runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        listed = await client.get("/api/lab/runs?provider=openai&prompt_version=v2&status=ok")
        empty = await client.get("/api/lab/runs?prompt_version=v1")
        detail = await client.get(f"/api/lab/runs/{run.request_id}")
    assert len(listed.json()["runs"]) == 1
    assert listed.json()["runs"][0]["request_id"] == run.request_id
    assert empty.json()["runs"] == []
    inspection = detail.json()
    assert inspection["ticket"] == "<script>alert('ticket')</script>"
    assert inspection["response"] == run.response.model_dump()
    assert inspection["metrics"]["request_id"] == run.request_id
    assert all(event["request_id"] == run.request_id for event in inspection["events"])
    assert "authorization" not in detail.text.lower()
    assert "api_key" not in detail.text.lower()


@pytest.mark.asyncio
@pytest.mark.parametrize("path,expected", [("not-a-uuid", 422),
                                        ("00000000-0000-0000-0000-000000000000", 404),
                                        ("..%2F..%2Fconfig.py", 404)])
async def test_history_rejects_invalid_identifiers(tmp_path: Path, path: str, expected: int) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    app = create_app(settings, Runtime(settings, {"openai": ScriptedProvider()}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.get(f"/api/lab/runs/{path}")
    assert response.status_code == expected
