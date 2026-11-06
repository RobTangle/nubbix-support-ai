import asyncio
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from nubbix_support_ai.config import Settings
from nubbix_support_ai.llm.contracts import LLMProvider, Message
from nubbix_support_ai.llm.execution import StructuredExecutor
from nubbix_support_ai.observability.costs import Budget, PriceCatalog
from nubbix_support_ai.observability.events import EventSink, FlowEvent, RunRecorder
from nubbix_support_ai.observability.storage import RunStore
from nubbix_support_ai.prompting.catalog import PromptCatalog
from nubbix_support_ai.support.contracts import (
    AppError,
    SafetyAssessment,
    SupportResponse,
    Ticket,
)
from nubbix_support_ai.support.policies import safe_response, suggest_review


@dataclass(frozen=True)
class SupportRun:
    request_id: str
    response: SupportResponse
    status: str
    events: tuple[FlowEvent, ...]
    metrics: dict[str, Any]


class SupportService:
    def __init__(self, provider: LLMProvider, settings: Settings, catalog: PromptCatalog,
                 prices: PriceCatalog, store: RunStore) -> None:
        self.provider = provider
        self.settings = settings
        self.catalog = catalog
        self.prices = prices
        self.store = store

    async def run(self, ticket: Ticket, *, prompt_version: str | None = None,
                  on_event: EventSink | None = None,
                  campaign_budget: Budget | None = None) -> SupportRun:
        ticket = Ticket.model_validate(ticket.model_dump())
        bundle = self.catalog.get(prompt_version or self.settings.prompt)
        self.prices.tariff(self.provider.name, self.provider.model)
        request_id = str(uuid4())
        timestamp = datetime.now(UTC).isoformat()
        inspection: dict[str, Any] = {
            "request_id": request_id, "timestamp": timestamp, "ticket": ticket.text,
            "provider": self.provider.name, "model": self.provider.model,
            "parameters": self.provider.parameters, "prompt_version": bundle.version,
            "prompt_hash": bundle.content_hash, "comparison_hash": bundle.comparison_hash,
            "status": "running", "response": None,
        }
        record = RunRecorder(request_id, self.store, inspection, on_event)
        record.checkpoint()
        budget = Budget(self.settings.ticket_usd, scope="ticket")
        executor = StructuredExecutor(self.provider, self.settings, self.prices, record, budget,
                                      campaign_budget, record.started + self.settings.deadline_seconds,
                                      bundle.repair)
        status, error_code = "error", None
        budget_scope = None
        response = None
        try:
            await record.emit("request.received", input_length=len(ticket.text))
            input_value = json.dumps({"ticket": ticket.text}, ensure_ascii=False)
            assessment = await executor.call("input_moderation", bundle.input_moderation,
                                             (Message("user", input_value),), SafetyAssessment)
            await record.emit("moderation.completed", stage="input_moderation",
                              decision=assessment.decision if assessment else "block",
                              reason_code=assessment.reason_code if assessment else "provider_refusal")
            if assessment is None or assessment.decision != "allow":
                response, status = safe_response(), "blocked"
            else:
                examples = tuple(message for text, answer in bundle.examples for message in (
                    Message("user", json.dumps({"ticket": text}, ensure_ascii=False)),
                    Message("assistant", answer),
                ))
                proposal = await executor.call("generation", bundle.system,
                                               (*examples, Message("user", input_value)),
                                               SupportResponse)
                if proposal is None:
                    response, status = safe_response(), "blocked"
                else:
                    proposal = suggest_review(proposal)
                    if proposal.confidence < 0.70:
                        await record.emit("human_review.suggested", confidence=proposal.confidence)
                    output_value = json.dumps({"ticket": ticket.text,
                                               "proposal": proposal.model_dump()}, ensure_ascii=False)
                    assessment = await executor.call("output_moderation", bundle.output_moderation,
                                                     (Message("user", output_value),), SafetyAssessment)
                    await record.emit("moderation.completed", stage="output_moderation",
                                      decision=assessment.decision if assessment else "block",
                                      reason_code=assessment.reason_code if assessment else
                                      "provider_refusal")
                    if assessment is None or assessment.decision != "allow":
                        response, status = safe_response(), "blocked"
                    else:
                        response = proposal
                        status = "escalated" if proposal.confidence < 0.70 else "ok"
            await record.emit("run.completed", status=status)
        except asyncio.CancelledError:
            status, error_code = "cancelled", "cancelled"
            raise
        except AppError as exc:
            error_code = exc.code
            budget_scope = getattr(exc, "scope", None)
            exc.request_id = request_id
            raise
        except Exception:
            error_code = "internal_error"
            raise AppError(error_code, request_id=request_id) from None
        finally:
            if status in {"error", "cancelled"}:
                await record.emit("run.failed", notify=False, status=status, error_code=error_code)
            metrics = {
                "request_id": request_id, "timestamp": timestamp, "provider": self.provider.name,
                "model": self.provider.model, "prompt_version": bundle.version,
                "prompt_hash": bundle.content_hash, "status": status,
                "abstained": status == "blocked", "error_code": error_code,
                "budget_scope": budget_scope,
                "input_tokens": record.input_tokens if record.usage_complete else None,
                "output_tokens": record.output_tokens if record.usage_complete else None,
                "total_tokens": (record.input_tokens + record.output_tokens
                                 if record.usage_complete else None),
                "known_input_tokens": record.input_tokens, "known_output_tokens": record.output_tokens,
                "cached_input_tokens": record.cached_tokens if record.usage_complete else None,
                "cache_write_input_tokens": (record.cache_write_tokens
                                             if record.usage_complete else None),
                "reasoning_output_tokens": record.reasoning_tokens if record.usage_complete else None,
                "usage_complete": record.usage_complete, "known_cost_usd": str(budget.known),
                "reserved_unknown_usd": str(budget.unknown),
                "estimated_cost_usd": str(budget.committed),
                "latency_seconds": round(time.monotonic() - record.started, 6),
                "calls": len(record.calls), "tariff_checked_on": self.prices.checked_on,
            }
            inspection.update(status=status, metrics=metrics,
                              response=response.model_dump() if response is not None else None)
            record.checkpoint()
            self.store.append_metric(metrics)
        if response is None:
            raise AppError("internal_error", request_id=request_id)
        return SupportRun(request_id, response, status, tuple(record.events), metrics)
