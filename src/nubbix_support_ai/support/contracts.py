from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["billing", "technical", "account", "other"]
ProviderName = Literal["openai", "google"]
Action = Annotated[str, Field(min_length=1, max_length=500)]


class AppError(Exception):
    """An operational code safe to expose; never a raw SDK diagnostic."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class Ticket(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    text: str = Field(min_length=1, max_length=8000)


class SupportResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1, allow_inf_nan=False)
    category: Category
    actions: list[Action] = Field(max_length=5)


class SafetyAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Literal["allow", "review", "block"]
    reason_code: Literal[
        "allowed", "injection", "unsafe_content", "sensitive_data",
        "policy_violation", "ambiguous", "unsupported",
    ]
