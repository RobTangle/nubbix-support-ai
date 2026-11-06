import asyncio
import json
import time
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from nubbix_support_ai.config import Settings
from nubbix_support_ai.llm.contracts import LLMProvider, LLMRequest, Message, ProviderError
from nubbix_support_ai.observability.costs import Budget, PriceCatalog
from nubbix_support_ai.observability.events import RunRecorder, Stage
from nubbix_support_ai.support.contracts import AppError

T = TypeVar("T", bound=BaseModel)


class StructuredExecutor:
    def __init__(self, provider: LLMProvider, settings: Settings, prices: PriceCatalog,
                 recorder: RunRecorder, ticket_budget: Budget, campaign_budget: Budget | None,
                 deadline: float, repair: str) -> None:
        self.provider = provider
        self.settings = settings
        self.prices = prices
        self.recorder = recorder
        self.budgets = [ticket_budget] + ([campaign_budget] if campaign_budget is not None else [])
        self.deadline = deadline
        self.repair = repair

    async def call(self, stage: Stage, system: str, messages: tuple[Message, ...],
                   response_model: type[T]) -> T | None:
        current = messages
        for attempt in range(1, self.settings.max_attempts + 1):
            remaining = self.deadline - time.monotonic()
            if remaining <= 0:
                raise AppError("deadline_exceeded")
            request = LLMRequest(system, current, response_model.model_json_schema(),
                                 self.settings.max_output_tokens,
                                 min(self.settings.timeout_seconds, remaining))
            payload = {"system": system, "messages": [
                {"role": message.role, "content": message.content} for message in current
            ], "schema": request.schema, "max_output_tokens": request.max_output_tokens}
            reservation = self.prices.reserve_cost(self.provider.name, self.provider.model,
                                                   json.dumps(payload), request.max_output_tokens)
            reserved: list[tuple[Budget, Any]] = []
            try:
                for budget in self.budgets:
                    reserved.append((budget, budget.reserve(reservation)))
            except AppError:
                for budget, amount in reserved:
                    budget.settle(amount, amount * 0)
                raise
            call: dict[str, Any] = {"stage": stage, "attempt": attempt, "request": payload,
                                    "status": "running", "response_text": None, "usage": None,
                                    "validated_response": None}
            self.recorder.calls.append(call)
            self.recorder.checkpoint()
            usage = None
            started = False
            call_started = time.monotonic()
            failure: AppError | None = None
            retryable = False
            retry_after = 0.0
            result: T | None = None
            try:
                await self.recorder.emit("llm.request.started", stage=stage, attempt=attempt,
                                         max_output_tokens=request.max_output_tokens)
                started = True
                async with asyncio.timeout(request.timeout_seconds):
                    reply = await self.provider.complete(request)
                usage = reply.usage
                call["response_text"] = reply.text
                call["reported_model"] = reply.model
                if reply.refused:
                    call["status"] = "refused"
                else:
                    if reply.finish_reason not in {"completed", "STOP"}:
                        raise ProviderError("max_tokens", usage=usage)
                    await self.recorder.emit("schema.validation.started", stage=stage, attempt=attempt)
                    try:
                        result = response_model.model_validate_json(reply.text)
                    except ValidationError:
                        call["status"] = "invalid_output"
                        await self.recorder.emit("schema.validation.failed", stage=stage,
                                                 attempt=attempt)
                        failure = AppError("invalid_model_output")
                        retryable = True
                        current = (*current, Message("assistant", reply.text),
                                   Message("user", self.repair))
                    else:
                        call["status"] = "ok"
                        call["validated_response"] = result.model_dump()
                        await self.recorder.emit("schema.validation.completed", stage=stage,
                                                 attempt=attempt)
            except asyncio.CancelledError:
                call["status"] = "cancelled"
                raise
            except (ProviderError, TimeoutError) as exc:
                error = (exc if isinstance(exc, ProviderError)
                         else ProviderError("timeout", retryable=True))
                usage = error.usage or usage
                failure = error
                retryable = error.retryable
                retry_after = error.retry_after
                call["status"] = "error"
                call["error_code"] = error.code
                await self.recorder.emit("llm.request.failed", stage=stage, attempt=attempt,
                                         error_code=error.code)
            finally:
                cost = (self.prices.cost(self.provider.name, self.provider.model, usage)
                        if usage is not None else (None if started else reservation * 0))
                for budget, amount in reserved:
                    budget.settle(amount, cost)
                if started and usage is None:
                    self.recorder.usage_complete = False
                if usage is not None:
                    self.recorder.input_tokens += usage.input_tokens
                    self.recorder.output_tokens += usage.output_tokens
                    self.recorder.cached_tokens += usage.cached_input_tokens
                    self.recorder.cache_write_tokens += usage.cache_write_input_tokens
                    self.recorder.reasoning_tokens += usage.reasoning_output_tokens
                    call["usage"] = usage.model_dump() | {"total_tokens": usage.total_tokens}
                call["known_cost_usd"] = str(cost) if cost is not None else None
                call["reserved_unknown_usd"] = str(reservation) if started and cost is None else "0"
                call["duration_ms"] = round((time.monotonic() - call_started) * 1000, 3)
                self.recorder.checkpoint()
            await self.recorder.emit("attempt.completed", stage=stage, attempt=attempt,
                                     status=call["status"], duration_ms=call["duration_ms"],
                                     total_tokens=usage.total_tokens if usage else None,
                                     known_cost_usd=str(cost) if cost is not None else None)
            if result is not None:
                return result
            if call["status"] == "refused":
                return None
            if failure is None:
                raise AppError("invalid_model_output")
            if not retryable or attempt == self.settings.max_attempts:
                raise failure
            delay = max(retry_after, 0.05 * attempt)
            if not delay < self.deadline - time.monotonic():
                raise AppError("deadline_exceeded")
            await self.recorder.emit("retry.scheduled", stage=stage, attempt=attempt,
                                     error_code=failure.code, delay_seconds=delay)
            await asyncio.sleep(delay)
        raise AppError("invalid_model_output")
