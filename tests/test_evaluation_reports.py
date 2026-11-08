import json
from uuid import uuid4

import pytest

from nubbix_support_ai.evaluation.reports import (
    CaseReview,
    ReportWriter,
    list_reports,
    read_report,
    save_review,
)
from nubbix_support_ai.support.contracts import AppError


def test_reports_validate_uuid_and_review_case_ids(tmp_path):
    writer = ReportWriter(tmp_path, {"provider": "openai", "model": "test"})
    writer.append_case({"case_id": "x:v1:full", "kind": "ticket", "status": "ok"})
    writer.snapshot(status="completed", planned=1)
    assert len(list_reports(tmp_path)) == 1
    report = read_report(tmp_path, writer.run_id)
    assert report["summary"]["completed"] == 1
    assert report["reviews"] == []
    saved = save_review(tmp_path, writer.run_id, CaseReview(case_id="x:v1:full", notes="Pendiente"))
    assert saved["reviews"][0]["correctness"] is None
    assert saved["summary"]["human_review"]["coverage"] == 0
    with pytest.raises(AppError, match="unknown_evaluation_case"):
        save_review(tmp_path, writer.run_id, CaseReview(case_id="unknown"))
    with pytest.raises(AppError, match="invalid_evaluation_id"):
        read_report(tmp_path, "../outside")
    with pytest.raises(AppError, match="evaluation_not_found"):
        read_report(tmp_path, str(uuid4()))


def test_updating_review_replaces_case_and_recalculates_coverage(tmp_path):
    writer = ReportWriter(tmp_path, {})
    writer.append_case({"case_id": "x:v1:full", "kind": "ticket", "status": "ok"})
    writer.snapshot(status="completed", planned=1)
    save_review(tmp_path, writer.run_id, CaseReview(case_id="x:v1:full"))
    result = save_review(tmp_path, writer.run_id, CaseReview(
        case_id="x:v1:full", usefulness=True, correctness=True,
        policy_compliance=True, severe_issue=False,
    ))
    assert len(result["reviews"]) == 1
    assert result["summary"]["human_review"]["coverage"] == 1
    assert result["summary"]["semantic_winner"] is None


def test_listing_preserves_metadata_for_an_older_partial_campaign(tmp_path):
    writer = ReportWriter(tmp_path, {"prompt_versions": ["v1", "v2"], "splits": ["dev"]})
    writer.append_case({"case_id": "x:v1:full", "kind": "ticket", "status": "ok",
                        "prompt_version": "v1", "arm": "full"})
    writer.snapshot(status="budget_exhausted", planned=2)
    [listed] = list_reports(tmp_path)
    assert listed["prompt_versions"] == ["v1", "v2"]
    assert listed["splits"] == ["dev"]
    assert list(listed["variants"]) == ["v1:full"]


def test_reading_an_older_adversarial_report_recalculates_without_rewriting_it(tmp_path):
    writer = ReportWriter(tmp_path, {"adversarial": True, "splits": ["adversarial"]})
    writer.append_case({"case_id": "control:v1:full", "kind": "control", "status": "ok",
                        "prompt_version": "v1", "expected_category": "technical",
                        "response": {"category": "technical"}})
    writer.append_case({"case_id": "attack:v1:full", "kind": "attack", "status": "blocked",
                        "prompt_version": "v1", "expected_category": "technical",
                        "response": {"category": "other"}})
    stored = writer.snapshot(status="completed", planned=2).summary
    for group in (stored, stored["variants"]["v1:full"]):
        group.pop("attack_outcomes", None)
        group["classification"].update(labelled=2, correct=1, accuracy=0.5)
    raw = json.dumps(stored)
    summary_path = writer.directory / "summary.json"
    summary_path.write_text(raw, encoding="utf-8")
    report = read_report(tmp_path, writer.run_id)
    [listed] = list_reports(tmp_path)
    assert report["summary"]["classification"]["accuracy"] == 1
    assert listed["variants"]["v1:full"]["classification"]["accuracy"] == 1
    assert listed["attack_outcomes"] == {"total": 1, "blocked": 1, "with_response": 0}
    assert summary_path.read_text(encoding="utf-8") == raw
