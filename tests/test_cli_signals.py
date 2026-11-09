import asyncio
import json
import signal
from decimal import Decimal

import pytest

from nubbix_support_ai import cli
from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.evaluation.reports import list_reports, read_report
from nubbix_support_ai.llm.contracts import ProviderError
from tests.helpers import ScriptedProvider, settings_at


class SignallingProvider(ScriptedProvider):
    def __init__(self, *, signum=signal.SIGTERM, trigger_at=1, signal_on_close=False):
        super().__init__()
        self.signum = signum
        self.trigger_at = trigger_at
        self.signal_on_close = signal_on_close

    async def complete(self, request):
        reply = await super().complete(request)
        if len(self.calls) == self.trigger_at:
            asyncio.get_running_loop().call_soon(signal.raise_signal, self.signum)
            await asyncio.sleep(0.05)
        return reply

    async def aclose(self):
        if self.signal_on_close:
            asyncio.get_running_loop().call_soon(signal.raise_signal, self.signum)
            await asyncio.sleep(0.05)
        await super().aclose()


@pytest.fixture
def previous_sigterm_handler():
    observed = []
    def previous(signum, frame):
        observed.append(signum)
    original = signal.signal(signal.SIGTERM, previous)
    try:
        yield previous, observed
    finally:
        signal.signal(signal.SIGTERM, original)


def test_sigterm_respond_cancels_without_retry_and_restores_previous_handler(
    tmp_path, monkeypatch, capsys, previous_sigterm_handler,
):
    previous, observed = previous_sigterm_handler
    provider = SignallingProvider()
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["respond", "--text", "PRIVATE-TICKET"]) == 143
    output = capsys.readouterr()
    metric = json.loads((settings.data_dir / "metrics.jsonl").read_text("utf-8"))
    assert output.out == ""
    assert json.loads(output.err)["error"]["code"] == "cancelled"
    assert "PRIVATE-TICKET" not in output.err
    assert metric["status"] == "cancelled" and metric["usage_complete"] is False
    assert Decimal(metric["reserved_unknown_usd"]) > 0
    assert len(provider.calls) == 1 and provider.closed
    assert signal.getsignal(signal.SIGTERM) is previous and observed == []


@pytest.mark.parametrize(("action", "progress"), [
    ("run", []), ("compare", []), ("adversarial", []), ("run", ["--progress"]),
])
def test_sigterm_evaluation_keeps_completed_case_and_interrupts_the_next(
    tmp_path, monkeypatch, capsys, previous_sigterm_handler, action, progress,
):
    previous, observed = previous_sigterm_handler
    provider = SignallingProvider(trigger_at=4)
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["eval", action, *progress]) == 143
    output = capsys.readouterr()
    reports = list_reports(settings.reports_dir)
    assert len(reports) == 1
    report = read_report(settings.reports_dir, reports[0]["run_id"])
    summary = report["summary"]
    assert summary["status"] == "interrupted" and summary["stopping_error"] == "cancelled"
    assert summary["completed"] == len(report["cases"]) == 1
    assert Decimal(summary["budget"]["pending_usd"]) == 0
    assert Decimal(summary["budget"]["reserved_unknown_usd"]) > 0
    if progress:
        assert "Evaluación cancelada" in output.err and "1/40" in output.err
        assert f"{reports[0]['run_id']}/summary.md" in output.err
    assert output.out == "" and json.loads(output.err.splitlines()[-1])["error"]["code"] == "cancelled"
    assert len(provider.calls) == 4 and provider.closed
    assert signal.getsignal(signal.SIGTERM) is previous and observed == []


def test_sigint_keeps_exit_130_and_closes_the_runtime(
    tmp_path, monkeypatch, capsys, previous_sigterm_handler,
):
    previous, observed = previous_sigterm_handler
    original = signal.signal(signal.SIGINT, signal.default_int_handler)
    provider = SignallingProvider(signum=signal.SIGINT)
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    try:
        assert cli.main(["respond", "--text", "Cancelar"]) == 130
    finally:
        signal.signal(signal.SIGINT, original)
    output = capsys.readouterr()
    assert output.out == "" and json.loads(output.err)["error"]["code"] == "cancelled"
    assert len(provider.calls) == 1 and provider.closed
    assert signal.getsignal(signal.SIGTERM) is previous and observed == []


def test_sigterm_during_close_points_to_the_complete_campaign(
    tmp_path, monkeypatch, capsys, previous_sigterm_handler,
):
    provider = SignallingProvider(trigger_at=999, signal_on_close=True)
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["eval", "run", "--split", "test", "--progress"]) == 143
    output = capsys.readouterr()
    report = list_reports(settings.reports_dir)[0]
    assert report["status"] == "completed" and report["completed"] == 40
    assert output.out == "" and json.loads(output.err.splitlines()[-1])["error"]["code"] == "cancelled"
    assert "Reporte guardado" in output.err and f"{report['run_id']}/summary.md" in output.err


@pytest.mark.parametrize("failure", [False, True])
def test_signal_handler_is_restored_after_normal_completion_or_provider_failure(
    tmp_path, monkeypatch, capsys, previous_sigterm_handler, failure,
):
    previous, observed = previous_sigterm_handler
    provider = ScriptedProvider([ProviderError("authentication_error")] if failure else None)
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["respond", "--text", "Consulta"]) == (1 if failure else 0)
    capsys.readouterr()
    assert provider.closed
    assert signal.getsignal(signal.SIGTERM) is previous and observed == []


@pytest.mark.parametrize("trigger_at", [1, 99])
def test_sigterm_during_client_cleanup_waits_for_close_to_finish(
    tmp_path, monkeypatch, capsys, previous_sigterm_handler, trigger_at,
):
    previous, observed = previous_sigterm_handler
    provider = SignallingProvider(trigger_at=trigger_at, signal_on_close=True)
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["respond", "--text", "Consulta"]) == 143
    output = capsys.readouterr()
    assert provider.closed
    assert output.out == "" and json.loads(output.err)["error"]["code"] == "cancelled"
    assert len(provider.calls) == (1 if trigger_at == 1 else 3)
    metric = json.loads((settings.data_dir / "metrics.jsonl").read_text("utf-8"))
    assert metric["status"] == ("cancelled" if trigger_at == 1 else "ok")
    assert signal.getsignal(signal.SIGTERM) is previous and observed == []
