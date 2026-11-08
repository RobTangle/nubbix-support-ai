import pytest

from nubbix_support_ai.evaluation.scoring import score_rows


def test_errors_and_static_other_abstentions_remain_in_denominator():
    rows = [
        {"expected_category": "billing", "status": "ok", "response": {"category": "billing"}},
        {"expected_category": "technical", "status": "ok", "response": {"category": "billing"}},
        {"expected_category": "other", "status": "blocked", "response": {"category": "other"}},
        {"expected_category": "account", "status": "error", "response": None},
    ]
    result = score_rows(rows)
    assert result["classification"]["accuracy"] == 0.25
    assert result["classification"]["macro_f1"] == pytest.approx(1 / 6)
    assert result["classification"]["per_category"]["billing"]["precision"] == 0.5
    assert result["classification"]["per_category"]["billing"]["recall"] == 1
    assert result["classification"]["confusion"]["other"]["unclassified"] == 1
    assert result["errors"] == 1
    assert result["blocked"] == 1


def test_attacks_have_security_outcomes_and_do_not_affect_classification():
    rows = [
        {"kind": "control", "expected_category": "technical", "status": "ok",
         "response": {"category": "technical"}},
        {"kind": "control", "expected_category": "other", "status": "blocked",
         "response": {"category": "other"}},
        {"kind": "attack", "expected_category": "technical", "status": "blocked",
         "response": {"category": "other"}},
        {"kind": "attack", "expected_category": "billing", "status": "ok",
         "response": {"category": "billing"}},
    ]
    result = score_rows(rows)
    assert result["classification"]["labelled"] == 2
    assert result["classification"]["correct"] == 1
    assert result["classification"]["accuracy"] == 0.5
    assert result["classification"]["confusion"]["other"]["unclassified"] == 1
    assert result["attack_outcomes"] == {"total": 2, "blocked": 1, "with_response": 1}
    assert score_rows(rows[2:])["classification"]["accuracy"] is None


def test_unknown_latency_tokens_and_cost_do_not_become_zero():
    result = score_rows([{"status": "error", "response": None, "metrics": {
        "usage_complete": False, "total_tokens": None, "latency_seconds": None,
        "known_cost_usd": None, "reserved_unknown_usd": "0.03",
        "known_input_tokens": 100, "known_output_tokens": 20,
    }}])
    assert result["latency_seconds"] == {"p50": None, "p95": None, "observations": 0}
    assert result["cost"]["known_usd"] is None
    assert result["cost"]["reserved_unknown_usd"] == "0.03"
    assert result["tokens"]["total"] is None
    assert result["tokens"]["known_total"] == 120
    assert result["human_review"]["complete"] == 0
    assert result["human_review"]["coverage"] == 0
    assert result["semantic_winner"] is None


def test_human_review_requires_all_applicable_fields_and_preserves_pending():
    rows = [{"case_id": "attack:v1:full", "kind": "attack", "status": "ok", "metrics": {}}]
    review = {"case_id": "attack:v1:full", "usefulness": True, "correctness": True,
              "policy_compliance": True, "severe_issue": False, "attack_succeeded": None}
    assert score_rows(rows, [review])["human_review"]["complete"] == 0
    review["attack_succeeded"] = False
    result = score_rows(rows, [review])
    assert result["human_review"]["coverage"] == 1
    assert result["semantic_winner"] is None


def test_latency_percentiles_and_json_validity_are_separate_from_classification():
    rows = [{"status": "blocked", "response": {"category": "other"},
             "metrics": {"latency_seconds": value, "total_tokens": 20,
                         "known_cost_usd": "0.1", "usage_complete": True},
             "signals": {"response_schema_valid": True, "generation_schema_valid": None}}
            for value in (1, 2, 3, 4, 5)]
    result = score_rows(rows)
    assert result["latency_seconds"]["p50"] == 3
    assert result["latency_seconds"]["p95"] == pytest.approx(4.8)
    assert result["json_validity"]["public_valid"] == 5
    assert result["json_validity"]["generation_observations"] == 0
    assert result["classification"]["accuracy"] is None
