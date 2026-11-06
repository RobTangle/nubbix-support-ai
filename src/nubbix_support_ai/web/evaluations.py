import asyncio
from collections.abc import Awaitable, Callable
from threading import Lock
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.types import Receive, Scope, Send

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.evaluation.data import load_cases
from nubbix_support_ai.evaluation.reports import CaseReview, list_reports, read_report, save_review
from nubbix_support_ai.evaluation.runner import run_evaluation
from nubbix_support_ai.observability.costs import Budget
from nubbix_support_ai.observability.events import FlowEvent
from nubbix_support_ai.support.contracts import AppError, ProviderName
from nubbix_support_ai.web.streaming import LabStream, stream_operation

_campaign_lock = Lock()


class EvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    provider: ProviderName | None = None
    model: str | None = Field(default=None, min_length=1, max_length=160)
    prompt_versions: list[str] = Field(min_length=1, max_length=16)
    split: Literal["dev", "test"] = "dev"
    adversarial: bool = False
    ablation: bool = False
    limit: int | None = Field(default=None, ge=1, le=200)

    @model_validator(mode="after")
    def validate_selection(self) -> Self:
        if self.ablation and not self.adversarial:
            raise ValueError("ablation requires adversarial dataset")
        if len(set(self.prompt_versions)) != len(self.prompt_versions):
            raise ValueError("duplicate prompt versions")
        return self


class CampaignStream(LabStream):
    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            _campaign_lock.release()


def build_evaluation_router(runtime: Runtime, tasks: set[asyncio.Task[Any]]) -> APIRouter:
    router = APIRouter()

    @router.post("/api/lab/evaluations/stream")
    async def stream_evaluation(payload: EvaluationRequest) -> CampaignStream:
        bundles = [runtime.catalog.get(version) for version in payload.prompt_versions]
        if len({bundle.comparison_hash for bundle in bundles}) != 1:
            raise AppError("incomparable_prompt_bundles")
        provider = payload.provider or runtime.settings.provider
        runtime.prices.tariff(provider, payload.model or runtime.settings.model_for(provider))
        path = runtime.settings.project_root / "datasets" / (
            "adversarial.jsonl" if payload.adversarial else "tickets.jsonl")
        cases = load_cases(path, split="adversarial" if payload.adversarial else payload.split)
        if payload.limit is not None:
            cases = cases[:payload.limit]
        if not cases:
            raise AppError("invalid_evaluation_selection")
        if not _campaign_lock.acquire(blocking=False):
            raise AppError("evaluation_in_progress")
        try:
            runtime.service(provider, payload.model)
        except BaseException:
            _campaign_lock.release()
            raise
        async def work(emit: Callable[[dict[str, Any]], Awaitable[None]]) -> dict[str, Any]:
            async def on_event(event: FlowEvent) -> None:
                await emit(event.model_dump())
            report = await run_evaluation(
                runtime, cases, provider=provider, model=payload.model,
                prompt_versions=payload.prompt_versions,
                campaign_budget=Budget(runtime.settings.campaign_usd), on_event=on_event,
                adversarial=payload.adversarial, ablation=payload.ablation)
            return report.to_dict()
        return CampaignStream(stream_operation(work, operation="evaluation", tasks=tasks))

    @router.get("/api/lab/evaluations")
    async def evaluations(limit: Annotated[int, Query(ge=1, le=200)] = 100) -> dict[str, Any]:
        return {"evaluations": list_reports(runtime.settings.reports_dir, limit=limit)}

    @router.get("/api/lab/evaluations/{run_id}")
    async def evaluation_detail(run_id: UUID) -> dict[str, Any]:
        return read_report(runtime.settings.reports_dir, str(run_id))

    @router.put("/api/lab/evaluations/{run_id}/reviews")
    async def review(run_id: UUID, payload: CaseReview) -> dict[str, Any]:
        return save_review(runtime.settings.reports_dir, str(run_id), payload)

    return router
