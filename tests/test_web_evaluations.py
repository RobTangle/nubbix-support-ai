import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.evaluation.reports import ReportWriter
from nubbix_support_ai.support.contracts import Ticket
from tests.helpers import ALLOW, PROPOSAL, ScriptedProvider, settings_at


@pytest.mark.asyncio
async def test_evaluation_stream_writes_report_and_preserves_pending_reviews(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    runtime = Runtime(settings, {"openai": ScriptedProvider()})
    app = create_app(settings, runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/lab/evaluations/stream", json={
            "provider": "openai", "prompt_versions": ["v1", "v2"], "split": "dev", "limit": 1,
        })
        assert response.status_code == 200
        rows = [json.loads(line) for line in response.text.splitlines()]
        assert rows[0]["type"] == "accepted"
        assert rows[-1]["type"] == "result"
        report_id = rows[-1]["run_id"]
        reports = (await client.get("/api/lab/evaluations")).json()["evaluations"]
        detail = (await client.get(f"/api/lab/evaluations/{report_id}")).json()
        case_id = detail["cases"][0]["case_id"]
        review = await client.put(f"/api/lab/evaluations/{report_id}/reviews", json={
            "case_id": case_id, "usefulness": True, "correctness": None,
            "policy_compliance": True, "notes": "<script>sin ejecutar</script>",
        })
        unknown = await client.put(f"/api/lab/evaluations/{report_id}/reviews", json={
            "case_id": "unknown-case", "correctness": True,
        })
    assert reports[0]["run_id"] == report_id
    assert len(detail["cases"]) == 2
    assert review.status_code == 200
    saved = review.json()["reviews"][0]
    assert saved["case_id"] == case_id
    assert saved["usefulness"] is True
    assert saved["correctness"] is None
    assert saved["severe_issue"] is None
    assert saved["notes"] == "<script>sin ejecutar</script>"
    assert unknown.status_code == 422
    assert unknown.json()["error"]["code"] == "unknown_evaluation_case"


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{"prompt_versions": ["missing"]},
                                    {"prompt_versions": ["v1"], "ablation": True},
                                    {"prompt_versions": ["v1"], "limit": 0}])
async def test_invalid_evaluation_never_calls_provider(tmp_path: Path,
                                                      payload: dict[str, Any]) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider()
    app = create_app(settings, Runtime(settings, {"openai": provider}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        response = await client.post("/api/lab/evaluations/stream", json=payload)
    assert response.status_code == 422
    assert provider.calls == []


@pytest.mark.asyncio
async def test_only_one_campaign_starts_and_disconnect_releases_the_lease(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider(delay=30)
    app = create_app(settings, Runtime(settings, {"openai": provider}))
    payload = {"provider": "openai", "prompt_versions": ["v1"], "limit": 1}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        first = asyncio.create_task(client.post("/api/lab/evaluations/stream", json=payload))
        try:
            for _ in range(100):
                if provider.calls:
                    break
                await asyncio.sleep(0.01)
            assert provider.calls
            second = await client.post("/api/lab/evaluations/stream", json=payload)
            assert second.status_code == 409
            assert second.json()["error"]["code"] == "evaluation_in_progress"
            assert len(provider.calls) == 1
        finally:
            first.cancel()
            await asyncio.gather(first, return_exceptions=True)
        provider.delay = 0
        restarted = await client.post("/api/lab/evaluations/stream", json=payload)
    assert restarted.status_code == 200
    rows = [json.loads(line) for line in restarted.text.splitlines()]
    assert rows[-1]["type"] == "result"


@pytest.mark.asyncio
async def test_evaluation_identifiers_are_rejected(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    app = create_app(settings, Runtime(settings, {"openai": ScriptedProvider()}))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        invalid = await client.get("/api/lab/evaluations/invalid")
        missing = await client.get("/api/lab/evaluations/00000000-0000-0000-0000-000000000000")
    assert invalid.status_code == 422
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_old_blocked_cases_resolve_stage_from_local_inspector(tmp_path: Path) -> None:
    from nubbix_support_ai.web.app import create_app
    settings = settings_at(tmp_path)
    provider = ScriptedProvider([ALLOW, PROPOSAL, {"decision": "block", "reason_code": "unsupported"}])
    runtime = Runtime(settings, {"openai": provider})
    run = await runtime.service().run(Ticket(text="Cargo duplicado"))
    writer = ReportWriter(settings.reports_dir, {"provider": "openai", "model": provider.model})
    row = {"case_id": "legacy:v1:full", "status": "blocked", "request_id": run.request_id,
           "response": run.response.model_dump(), "prompt_version": "v1", "arm": "full"}
    writer.append_case(row)
    writer.append_case(row | {"case_id": "missing:v1:full", "request_id": "00000000-0000-0000-0000-000000000000"})
    report = writer.snapshot(status="completed", planned=2)
    cases_path = writer.directory / "cases.jsonl"
    before = cases_path.read_bytes()
    app = create_app(settings, runtime)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as client:
        detail = await client.get(f"/api/lab/evaluations/{report.run_id}")
        inspection = await client.get(f"/api/lab/runs/{run.request_id}")
    assert detail.status_code == 200
    with_trace, missing = detail.json()["cases"]
    assert with_trace["flow"]["blocked_at"] == "output_moderation"
    assert with_trace["flow"]["stages"]["output_moderation"]["reason_code"] == "unsupported"
    assert inspection.json()["flow"] == with_trace["flow"]
    assert missing.get("flow") is None
    assert cases_path.read_bytes() == before
