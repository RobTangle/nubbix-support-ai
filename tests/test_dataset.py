import hashlib
import json
from collections import Counter

import pytest

from nubbix_support_ai.evaluation.data import EvalCase, load_cases
from nubbix_support_ai.prompting.catalog import load_catalog
from nubbix_support_ai.support.contracts import AppError
from tests.helpers import ROOT


def test_regression_corpus_is_balanced_and_separate_from_few_shots():
    cases = load_cases(ROOT / "datasets/tickets.jsonl")
    assert len(cases) == 80
    assert len({case.id for case in cases}) == 80
    assert Counter((case.split, case.category) for case in cases) == {
        (split, category): 10 for split in ("dev", "test")
        for category in ("billing", "technical", "account", "other")
    }
    examples = {" ".join(text.lower().split())
                for text, _ in load_catalog(ROOT).get("v2").examples}
    assert not examples.intersection(" ".join(case.text.lower().split()) for case in cases)
    assert len(load_cases(ROOT / "datasets/tickets.jsonl", split="test")) == 40


def test_adversarial_corpus_contains_attacks_and_benign_controls_without_ticket_canary():
    cases = load_cases(ROOT / "datasets/adversarial.jsonl")
    assert Counter(case.kind for case in cases) == {"attack": 10, "control": 10}
    assert all(case.split == "adversarial" for case in cases)
    assert all("NUBBIX_CANARY_7F2A" not in case.text for case in cases)
    assert all(case.scenario and case.expected_category for case in cases)


@pytest.mark.parametrize("rows", [
    [{"id": "x", "text": "a", "category": "billing"}] * 2,
    [{"id": "x", "text": "a", "category": "billing", "expected_category": "other"}],
    [{"id": "x", "text": "a", "category": "billing", "forbidden_patterns": ["["]}],
    [{"id": "../x", "text": "a", "category": "billing"}],
])
def test_loader_rejects_ambiguous_or_invalid_cases(tmp_path, rows):
    path = tmp_path / "cases.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(AppError, match="invalid_dataset"):
        load_cases(path)


def test_case_does_not_require_optional_human_rubric_fields():
    case = EvalCase(id="case-1", split="dev", text="Consulta", category="other")
    assert case.kind == "ticket"
    assert case.expected_actions == []


def test_provenance_records_known_regression_corpus_and_unique_normalized_text():
    metadata = json.loads((ROOT / "datasets/metadata.json").read_text("utf-8"))
    assert metadata["source"] == "Nubbix prototype synthetic corpus"
    assert metadata["independent_holdout"] is False
    for filename, count in (("tickets.jsonl", 80), ("adversarial.jsonl", 20)):
        cases = load_cases(ROOT / "datasets" / filename)
        assert metadata["files"][filename]["cases"] == count
        assert len({" ".join(case.text.casefold().split()) for case in cases}) == count


def test_provenance_hashes_match_canonical_utf8_content_across_platforms():
    metadata = json.loads((ROOT / "datasets/metadata.json").read_text("utf-8"))
    for filename in ("tickets.jsonl", "adversarial.jsonl"):
        canonical = (ROOT / "datasets" / filename).read_text("utf-8").encode("utf-8")
        assert hashlib.sha256(canonical).hexdigest() == metadata["files"][filename]["adapted_sha256"]
