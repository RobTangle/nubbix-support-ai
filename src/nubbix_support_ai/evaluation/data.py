import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from nubbix_support_ai.support.contracts import AppError, Category


class EvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True)
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    split: Literal["dev", "test", "adversarial"] = "dev"
    text: str = Field(min_length=1, max_length=8000)
    category: Category | None = None
    expected_category: Category | None = None
    kind: Literal["ticket", "attack", "control"] = "ticket"
    expected_actions: list[str] = Field(default_factory=list)
    forbidden_patterns: list[str] = Field(default_factory=list)
    scenario: str | None = None

    @model_validator(mode="after")
    def validate_annotations(self) -> Self:
        if self.category and self.expected_category and self.category != self.expected_category:
            raise ValueError("conflicting category annotations")
        for pattern in self.forbidden_patterns:
            try:
                re.compile(pattern)
            except re.error:
                raise ValueError("invalid forbidden pattern") from None
        return self


def load_cases(path: Path, split: str | None = None) -> list[EvalCase]:
    try:
        rows = [EvalCase.model_validate_json(line) for line in path.read_text("utf-8").splitlines()
                if line.strip()]
        if not rows or len({row.id for row in rows}) != len(rows):
            raise ValueError("empty dataset or duplicate id")
        if split is not None and split not in {"dev", "test", "adversarial"}:
            raise ValueError("unknown split")
        return [row for row in rows if split is None or row.split == split]
    except (OSError, ValueError, ValidationError):
        raise AppError("invalid_dataset") from None


def dataset_hash(cases: Sequence[EvalCase]) -> str:
    canonical = json.dumps([case.model_dump() for case in cases], ensure_ascii=False,
                           sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
