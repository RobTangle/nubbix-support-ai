import asyncio
import json
from pathlib import Path
from typing import Any

from nubbix_support_ai.config import Settings
from nubbix_support_ai.llm.contracts import LLMReply, LLMRequest, TokenUsage

ROOT = Path(__file__).resolve().parents[1]
PROPOSAL = {"answer": "Indicanos la fecha y referencia del cargo para revisarlo.",
            "confidence": 0.85, "category": "billing", "actions": ["Verificar el cargo."]}
ALLOW = {"decision": "allow", "reason_code": "allowed"}
USAGE = TokenUsage(input_tokens=100, output_tokens=20, cached_input_tokens=40,
                   reasoning_output_tokens=5)


class ScriptedProvider:
    name = "openai"
    model = "gpt-6-luna"
    parameters = {"reasoning_effort": "xhigh"}

    def __init__(self, replies: list[Any] | None = None, *, delay: float = 0) -> None:
        self.replies = list(replies or [])
        self.calls: list[LLMRequest] = []
        self.delay = delay
        self.closed = False

    async def complete(self, request: LLMRequest) -> LLMReply:
        self.calls.append(request)
        if self.delay:
            await asyncio.sleep(self.delay)
        value = self.replies.pop(0) if self.replies else (
            PROPOSAL if "answer" in request.schema["properties"] else ALLOW
        )
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, LLMReply):
            return value
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return LLMReply(text, USAGE, self.model)

    async def aclose(self) -> None:
        self.closed = True


def settings_at(directory: Path, **overrides: Any) -> Settings:
    return Settings(project_root=ROOT, data_dir=directory / "data",
                    reports_dir=directory / "reports", **overrides)
