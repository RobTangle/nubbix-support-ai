import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from filelock import FileLock
from pydantic import BaseModel, ConfigDict, Field

from nubbix_support_ai.evaluation.scoring import score_rows
from nubbix_support_ai.support.contracts import AppError


class CaseReview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    case_id: str = Field(min_length=1, max_length=256)
    usefulness: bool | None = None
    correctness: bool | None = None
    policy_compliance: bool | None = None
    severe_issue: bool | None = None
    attack_succeeded: bool | None = None
    false_block: bool | None = None
    notes: str = Field(default="", max_length=8000)


@dataclass(frozen=True)
class EvaluationReport:
    run_id: str
    directory: Path
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {"run_id": self.run_id, "directory": str(self.directory), "summary": self.summary}


def _directory(root: Path, run_id: str) -> Path:
    try:
        if str(UUID(run_id)) != run_id:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise AppError("invalid_evaluation_id") from None
    directory = (root / run_id).resolve()
    if not directory.is_relative_to(root.resolve()):
        raise AppError("invalid_evaluation_id")
    return directory


def _write_json(path: Path, value: Any) -> None:
    try:
        temporary = path.with_name(f"{path.name}.{uuid4()}.tmp")
        temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), "utf-8")
        os.replace(temporary, path)
    except (OSError, ValueError, TypeError):
        raise AppError("storage_error") from None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


def _summary(rows: Sequence[dict[str, Any]], reviews: Sequence[dict[str, Any]],
             state: dict[str, Any]) -> dict[str, Any]:
    result = state | score_rows(rows, reviews)
    result["completed"] = len(rows)
    variants = sorted({(row["prompt_version"], row.get("arm", "full")) for row in rows
                       if "prompt_version" in row})
    result["variants"] = {
        f"{version}:{arm}": score_rows([row for row in rows if row.get("prompt_version") == version
                                        and row.get("arm", "full") == arm], reviews)
        for version, arm in variants
    }
    return result


def _write_markdown(directory: Path, summary: dict[str, Any]) -> None:
    lines = ["# Evaluation report", "", f"Run: `{summary['run_id']}`",
             f"Status: **{summary['status']}**",
             f"Completed: {summary['completed']}/{summary['planned']}", "",
             "| Variant | Accuracy | Macro-F1 | Errors | Blocks | Review coverage |",
             "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for name, variant in summary["variants"].items():
        accuracy = variant["classification"]["accuracy"]
        macro_f1 = variant["classification"]["macro_f1"]
        lines.append(f"| {name} | {accuracy} | {macro_f1} | {variant['errors']} | "
                     f"{variant['blocked']} | {variant['human_review']['coverage']:.1%} |")
    lines.extend(["", "Null means unknown or pending, never a pass. Errors and abstentions remain "
                  "in classification denominators. Static blocked responses receive no accuracy credit.",
                  "", "Automatic signals do not adjudicate safety or semantic quality. "
                  "No semantic winner is selected automatically.", ""])
    try:
        (directory / "summary.md").write_text("\n".join(lines), "utf-8")
    except OSError:
        raise AppError("storage_error") from None


class ReportWriter:
    def __init__(self, root: Path, manifest: dict[str, Any]) -> None:
        self.run_id = str(uuid4())
        self.directory = _directory(root, self.run_id)
        self.rows: list[dict[str, Any]] = []
        try:
            self.directory.mkdir(parents=True)
            (self.directory / "cases.jsonl").touch()
            (self.directory / "reviews.jsonl").touch()
        except OSError:
            raise AppError("storage_error") from None
        self.manifest = {"schema_version": 1, "run_id": self.run_id,
                         "created_at": datetime.now(UTC).isoformat()} | manifest
        _write_json(self.directory / "manifest.json", self.manifest)

    def append_case(self, row: dict[str, Any]) -> None:
        try:
            line = json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n"
            with (self.directory / "cases.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(line)
                stream.flush()
        except (OSError, ValueError, TypeError):
            raise AppError("storage_error") from None
        self.rows.append(row)

    def snapshot(self, *, status: str, planned: int, **state: Any) -> EvaluationReport:
        try:
            with FileLock(str(self.directory / "review.lock"), timeout=5):
                reviews = _read_jsonl(self.directory / "reviews.jsonl")
                value = _summary(self.rows, reviews, {
                    "run_id": self.run_id, "status": status, "planned": planned,
                    "provider": self.manifest.get("provider"), "model": self.manifest.get("model"),
                    "created_at": self.manifest["created_at"], **state,
                })
                _write_json(self.directory / "summary.json", value)
                _write_markdown(self.directory, value)
        except (OSError, ValueError, TimeoutError):
            raise AppError("storage_error") from None
        return EvaluationReport(self.run_id, self.directory, value)


def read_report(root: Path, run_id: str) -> dict[str, Any]:
    directory = _directory(root, run_id)
    try:
        return {"run_id": run_id, "directory": str(directory),
                "summary": json.loads((directory / "summary.json").read_text("utf-8")),
                "manifest": json.loads((directory / "manifest.json").read_text("utf-8")),
                "cases": _read_jsonl(directory / "cases.jsonl"),
                "reviews": _read_jsonl(directory / "reviews.jsonl")}
    except FileNotFoundError:
        raise AppError("evaluation_not_found") from None
    except (OSError, ValueError, TypeError):
        raise AppError("storage_error") from None


def list_reports(root: Path, *, limit: int = 100) -> list[dict[str, Any]]:
    values = []
    for directory in root.glob("*"):
        try:
            values.append(read_report(root, directory.name)["summary"])
        except AppError:
            continue
    return sorted(values, key=lambda item: item["created_at"], reverse=True)[:max(0, limit)]


def save_review(root: Path, run_id: str, review: CaseReview) -> dict[str, Any]:
    directory = _directory(root, run_id)
    if not directory.is_dir():
        raise AppError("evaluation_not_found")
    try:
        with FileLock(str(directory / "review.lock"), timeout=5):
            report = read_report(root, run_id)
            if review.case_id not in {row["case_id"] for row in report["cases"]}:
                raise AppError("unknown_evaluation_case")
            reviews = {item["case_id"]: item for item in report["reviews"]}
            reviews[review.case_id] = review.model_dump()
            temporary = directory / f"reviews-{uuid4()}.tmp"
            temporary.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n"
                                         for item in reviews.values()), "utf-8")
            os.replace(temporary, directory / "reviews.jsonl")
            summary = _summary(report["cases"], list(reviews.values()), report["summary"])
            _write_json(directory / "summary.json", summary)
            _write_markdown(directory, summary)
    except (OSError, ValueError, TimeoutError):
        raise AppError("storage_error") from None
    return read_report(root, run_id)
