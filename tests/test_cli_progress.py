import io
import json
import os
from pathlib import Path

from nubbix_support_ai import cli
from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.llm.contracts import ProviderError
from tests.helpers import ALLOW, PROPOSAL, ScriptedProvider, settings_at


class Terminal(io.StringIO):
    def isatty(self):
        return True


class ObservingProvider(ScriptedProvider):
    def __init__(self, terminal, replies):
        super().__init__(replies)
        self.terminal = terminal
        self.before_calls = []

    async def complete(self, request):
        self.before_calls.append(self.terminal.getvalue())
        return await super().complete(request)


def test_ticket_displays_stages_and_retry_before_provider_replies(tmp_path, monkeypatch, capsys):
    terminal = Terminal()
    provider = ObservingProvider(terminal, [ALLOW, "PRIVATE-DRAFT", PROPOSAL, ALLOW])
    settings = settings_at(tmp_path)
    monkeypatch.setattr("sys.stderr", terminal)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["respond", "--text", "PRIVATE-TICKET"]) == 0
    assert "Revisando entrada" in provider.before_calls[0]
    assert "Generando propuesta" in provider.before_calls[1]
    assert "Reintento" in provider.before_calls[2]
    assert "Revisando salida" in provider.before_calls[3]
    assert "Ticket procesado" in terminal.getvalue()
    assert "PRIVATE" not in terminal.getvalue()
    assert json.loads(capsys.readouterr().out) == PROPOSAL


def test_campaign_updates_one_line_and_reports_partial_result(tmp_path, monkeypatch, capsys):
    terminal = Terminal()
    provider = ObservingProvider(
        terminal, [ALLOW, PROPOSAL, ALLOW, ProviderError("quota_exhausted")],
    )
    settings = settings_at(tmp_path)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(terminal, "fileno", lambda: 2)
    monkeypatch.setattr("os.get_terminal_size", lambda *_: os.terminal_size((0, 0)))
    monkeypatch.setattr("sys.stderr", terminal)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": provider}))
    assert cli.main(["eval", "run", "--split", "test", "--prompt-version", "v5"]) == 1
    assert "40 ejecuciones" in provider.before_calls[0]
    assert "0/40" in provider.before_calls[0]
    assert "\r" in provider.before_calls[3]
    assert "1/40" in provider.before_calls[3]
    assert "test-billing-02" in provider.before_calls[3]
    output = terminal.getvalue()
    assert "Evaluación detenida" in output
    assert "cuota agotada" in output.lower()
    assert "2/40" in output
    report = json.loads(capsys.readouterr().out)
    summary = Path(report["directory"]) / "summary.md"
    assert report["summary"]["stopping_error"] == "quota_exhausted"
    assert summary.is_file() and f"{summary.parent.name}/summary.md" in output


def test_progress_can_be_forced_as_plain_lines_or_disabled_in_a_terminal(
    tmp_path, monkeypatch, capsys,
):
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, {"openai": ScriptedProvider()}))
    assert cli.main(["respond", "--text", "Consulta", "--progress"]) == 0
    output = capsys.readouterr()
    assert "Revisando entrada" in output.err and "\r" not in output.err
    assert json.loads(output.out) == PROPOSAL
    terminal = Terminal()
    monkeypatch.setattr("sys.stderr", terminal)
    assert cli.main(["respond", "--text", "Consulta", "--no-progress"]) == 0
    assert terminal.getvalue() == ""
    assert json.loads(capsys.readouterr().out) == PROPOSAL
