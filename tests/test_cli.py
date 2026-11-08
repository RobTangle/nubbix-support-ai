import io
import json

import pytest

from nubbix_support_ai import cli
from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.llm.contracts import ProviderError
from tests.helpers import PROPOSAL, ScriptedProvider, settings_at


def test_prompt_validation_and_help_need_no_credentials(capsys):
    assert cli.main(["prompts", "check"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert {item["id"] for item in output["versions"]} >= {"v1", "v2", "v3"}
    with pytest.raises(SystemExit) as result:
        cli.main(["--help"])
    assert result.value.code == 0


def test_respond_prints_only_public_json_and_accepts_stdin(tmp_path, monkeypatch, capsys):
    provider = ScriptedProvider()
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, providers={"openai": provider}))
    monkeypatch.setattr("sys.stdin", io.StringIO("Cargo duplicado"))
    assert cli.main(["respond", "--stdin"]) == 0
    output = capsys.readouterr()
    assert json.loads(output.out) == PROPOSAL
    assert output.err == ""


def test_respond_reports_operational_errors_as_nonzero_sanitized_json(tmp_path, monkeypatch, capsys):
    provider = ScriptedProvider([ProviderError("authentication_error")])
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, providers={"openai": provider}))
    assert cli.main(["respond", "--text", "PRIVATE-TICKET"]) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert json.loads(output.err)["error"]["code"] == "authentication_error"
    assert "PRIVATE" not in output.err


def test_respond_rejects_conflicting_inputs_before_calling_provider():
    with pytest.raises(SystemExit) as result:
        cli.main(["respond", "--text", "Consulta", "--stdin"])
    assert result.value.code == 2


@pytest.mark.parametrize("action", ["run", "compare", "adversarial"])
def test_incomplete_evaluation_returns_nonzero_and_keeps_a_readable_partial_report(
    tmp_path, monkeypatch, capsys, action,
):
    provider = ScriptedProvider([ProviderError("quota_exhausted")])
    settings = settings_at(tmp_path)
    monkeypatch.setattr(cli.Settings, "load", lambda: settings)
    monkeypatch.setattr(cli, "Runtime", lambda _: Runtime(settings, providers={"openai": provider}))
    assert cli.main(["eval", action, "--provider", "openai"]) == 1
    output = capsys.readouterr()
    report = json.loads(output.out)
    assert report["summary"]["status"] == "provider_error"
    assert report["summary"]["stopping_error"] == "quota_exhausted"
    assert len(provider.calls) == 1
    assert cli.main(["eval", "summarize", report["directory"]]) == 0
    saved = json.loads(capsys.readouterr().out)
    assert saved["summary"]["status"] == "provider_error"
    if action == "compare":
        assert saved["manifest"]["prompt_versions"] == ["v1", "v2"]
