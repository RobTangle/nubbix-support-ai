import shutil
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
import yaml
from pydantic import ValidationError

from nubbix_support_ai.config import Settings
from nubbix_support_ai.llm.contracts import TokenUsage
from nubbix_support_ai.prompting.catalog import CatalogError, load_catalog
from nubbix_support_ai.support.contracts import SupportResponse, Ticket

ROOT = Path(__file__).resolve().parents[1]
RESPONSE = {"answer": "Revisaremos el cargo.", "confidence": 0.82,
            "category": "billing", "actions": ["Verificar el cargo."]}


@pytest.mark.parametrize("text", ["", "  \n", "x" * 8001, 123, None])
def test_ticket_rejects_empty_oversize_or_non_text(text):
    with pytest.raises(ValidationError):
        Ticket(text=text)


def test_ticket_preserves_unicode_and_response_has_only_public_fields():
    assert Ticket(text="  No puedo entrar 👩🏽‍💻  ").text == "No puedo entrar 👩🏽‍💻"
    assert SupportResponse(**RESPONSE).model_dump() == RESPONSE


@pytest.mark.parametrize("patch", [
    {"answer": ""}, {"answer": " "}, {"answer": "x" * 4001},
    {"confidence": float("nan")}, {"confidence": float("inf")},
    {"confidence": -0.1}, {"confidence": 1.1}, {"confidence": True},
    {"confidence": "0.8"}, {"category": "unknown"}, {"extra": "ignored?"},
    {"actions": ["x"] * 6}, {"actions": ["x" * 501]}, {"actions": [" "]},
])
def test_response_enforces_its_consumer_contract(patch):
    with pytest.raises(ValidationError):
        SupportResponse(**(RESPONSE | patch))


def test_usage_does_not_double_count_subtotals():
    usage = TokenUsage(input_tokens=100, output_tokens=20, cached_input_tokens=40,
                       reasoning_output_tokens=5)
    assert usage.total_tokens == 120
    with pytest.raises(ValidationError):
        TokenUsage(input_tokens=10, output_tokens=20, cached_input_tokens=11)


def test_settings_resolve_project_paths_and_environment_overrides_env_file(tmp_path, monkeypatch):
    (tmp_path / ".env").write_text("OPENAI_API_KEY=local-secret\nNUBBIX_TICKET_USD=0.01\n")
    monkeypatch.setenv("NUBBIX_TICKET_USD", "0.02")
    settings = Settings.load(tmp_path)
    assert settings.ticket_usd == Decimal("0.02")
    assert settings.data_dir == tmp_path / "data"
    assert settings.openai_api_key.get_secret_value() == "local-secret"
    assert settings.gemini_api_key is None
    assert "local-secret" not in repr(settings)


@pytest.mark.parametrize("value", ["-1", "0", "NaN", "Infinity"])
def test_settings_reject_invalid_money(tmp_path, monkeypatch, value):
    monkeypatch.setenv("NUBBIX_TICKET_USD", value)
    with pytest.raises(ValidationError):
        Settings.load(tmp_path)


def test_catalog_compares_effective_context_and_validates_examples():
    catalog = load_catalog(ROOT)
    first, second = catalog.get("v1"), catalog.get("v2")
    assert catalog.get().version == "v5"
    assert catalog.baseline == "v1"
    assert first.comparison_hash == second.comparison_hash
    assert first.content_hash != second.content_hash
    assert len(first.examples) == 0
    assert len(second.examples) == 4
    assert "{{" not in first.system
    assert "{{" not in first.input_moderation


def test_new_prompt_version_needs_no_python_change(tmp_path):
    version = f"test-{uuid4().hex}"
    shutil.copytree(ROOT / "prompts", tmp_path / "prompts")
    shutil.copytree(tmp_path / "prompts/versions/v1", tmp_path / "prompts/versions" / version)
    registry_path = tmp_path / "prompts/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["versions"].append({"id": version, "label": "Test version"})
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    assert load_catalog(tmp_path).get(version).version == version


def test_catalog_rejects_path_traversal_and_unresolved_templates(tmp_path):
    shutil.copytree(ROOT / "prompts", tmp_path / "prompts")
    registry_path = tmp_path / "prompts/registry.yaml"
    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    registry["versions"].append({"id": "../outside", "label": "Unsafe"})
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(tmp_path)
    registry["versions"].pop()
    registry_path.write_text(yaml.safe_dump(registry), encoding="utf-8")
    system_path = tmp_path / "prompts/versions/v1/system.yaml"
    system_path.write_text("instructions: '{{unknown}}'\n", encoding="utf-8")
    with pytest.raises(CatalogError):
        load_catalog(tmp_path)
