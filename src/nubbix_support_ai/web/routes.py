import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from starlette.requests import ClientDisconnect

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.observability.events import FlowEvent
from nubbix_support_ai.observability.stages import summarize_flow
from nubbix_support_ai.support.contracts import ProviderName, SupportResponse, Ticket
from nubbix_support_ai.web.lifecycle import cancel_and_drain
from nubbix_support_ai.web.streaming import LabStream, stream_operation

STATIC = Path(__file__).parent / "static"
RunStatus = Literal["running", "ok", "escalated", "blocked", "error", "cancelled"]
PROVIDERS: tuple[tuple[ProviderName, str], ...] = (("openai", "OpenAI"), ("google", "Google Gemini"))


class TriageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)
    ticket: str = Field(min_length=1, max_length=8000)
    provider: ProviderName | None = None
    model: str | None = Field(default=None, min_length=1, max_length=160)
    prompt_version: str | None = Field(default=None, min_length=1, max_length=64)


def build_router(runtime: Runtime, tasks: set[asyncio.Task[Any]]) -> APIRouter:
    router = APIRouter()

    @router.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-cache"})

    @router.get("/api/lab/catalog")
    async def catalog() -> dict[str, Any]:
        return {
            "providers": [{"id": provider, "label": label,
                           "available": runtime.available(provider),
                           "default_model": runtime.settings.model_for(provider),
                           "models": [key.split(":", 1)[1] for key in runtime.prices.models
                                      if key.startswith(f"{provider}:")]} for provider, label in
                          PROVIDERS],
            "prompts": [item.model_dump() for item in runtime.catalog.versions],
            "default_prompt": runtime.settings.prompt or runtime.catalog.default,
            "baseline_prompt": runtime.catalog.baseline,
            "default_provider": runtime.settings.provider,
            "ticket_budget_usd": str(runtime.settings.ticket_usd),
            "campaign_budget_usd": str(runtime.settings.campaign_usd),
            "data_directory": str(runtime.settings.data_dir),
            "reports_directory": str(runtime.settings.reports_dir),
            "tariff_checked_on": runtime.prices.checked_on,
        }

    @router.post("/api/triage", response_model=SupportResponse)
    async def triage(payload: TriageRequest, request: Request) -> SupportResponse:
        runtime.catalog.get(payload.prompt_version or runtime.settings.prompt)
        service = runtime.service(payload.provider, payload.model)
        async def disconnected() -> None:
            while True:
                if (await request.receive())["type"] == "http.disconnect":
                    return
        work = asyncio.create_task(service.run(Ticket(text=payload.ticket),
                                               prompt_version=payload.prompt_version))
        monitor = asyncio.create_task(disconnected())
        tasks.add(work)
        try:
            done, _ = await asyncio.wait({work, monitor}, return_when=asyncio.FIRST_COMPLETED)
            if work in done:
                return (await work).response
            raise ClientDisconnect()
        finally:
            await cancel_and_drain(work, monitor)
            tasks.discard(work)

    @router.post("/api/lab/runs/stream")
    async def stream_run(payload: TriageRequest) -> LabStream:
        runtime.catalog.get(payload.prompt_version or runtime.settings.prompt)
        service = runtime.service(payload.provider, payload.model)
        async def work(emit: Callable[[dict[str, Any]], Awaitable[None]]) -> dict[str, Any]:
            async def on_event(event: FlowEvent) -> None:
                await emit(event.model_dump())
            result = await service.run(Ticket(text=payload.ticket),
                                       prompt_version=payload.prompt_version, on_event=on_event)
            return {"run_id": result.request_id, "status": result.status,
                    "response": result.response.model_dump(), "metrics": result.metrics}
        return LabStream(stream_operation(work, operation="triage", tasks=tasks))

    @router.get("/api/lab/runs")
    async def history(provider: ProviderName | None = None, prompt_version: str | None = None,
                      status: RunStatus | None = None,
                      limit: Annotated[int, Query(ge=1, le=200)] = 100) -> dict[str, Any]:
        if prompt_version is not None:
            runtime.catalog.get(prompt_version)
        return {"runs": runtime.store.list_runs(provider=provider, prompt_version=prompt_version,
                                                status=status, limit=limit)}

    @router.get("/api/lab/runs/{run_id}")
    async def inspection(run_id: UUID) -> dict[str, Any]:
        run = runtime.store.get_run(str(run_id))
        return run | {"flow": summarize_flow(run)}

    return router
