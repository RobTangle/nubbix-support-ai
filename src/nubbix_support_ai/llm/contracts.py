from dataclasses import dataclass
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nubbix_support_ai.support.contracts import AppError


class TokenUsage(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_input_tokens: int = Field(default=0, ge=0)
    cache_write_input_tokens: int = Field(default=0, ge=0)
    reasoning_output_tokens: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_subtotals(self) -> Self:
        if self.cached_input_tokens + self.cache_write_input_tokens > self.input_tokens:
            raise ValueError("cache subtotals exceed input")
        if self.reasoning_output_tokens > self.output_tokens:
            raise ValueError("reasoning subtotal exceeds output")
        return self

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class Message:
    role: Literal["user", "assistant"]
    content: str


@dataclass(frozen=True)
class LLMRequest:
    system: str
    messages: tuple[Message, ...]
    schema: dict[str, Any]
    max_output_tokens: int
    timeout_seconds: float


@dataclass(frozen=True)
class LLMReply:
    text: str
    usage: TokenUsage | None
    model: str
    refused: bool = False
    finish_reason: str = "completed"


class ProviderError(AppError):
    def __init__(self, code: str, *, retryable: bool = False, retry_after: float = 0,
                 usage: TokenUsage | None = None) -> None:
        super().__init__(code)
        self.retryable = retryable
        self.retry_after = retry_after
        self.usage = usage


class LLMProvider(Protocol):
    name: str
    model: str
    parameters: dict[str, Any]

    async def complete(self, request: LLMRequest) -> LLMReply: ...

    async def aclose(self) -> None: ...
