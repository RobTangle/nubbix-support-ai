import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.config import Settings
from nubbix_support_ai.support.contracts import AppError
from nubbix_support_ai.web.evaluations import build_evaluation_router
from nubbix_support_ai.web.lifecycle import cancel_and_drain
from nubbix_support_ai.web.routes import STATIC, build_router


def create_app(settings: Settings, runtime: Runtime | None = None) -> FastAPI:
    owns_runtime = runtime is None
    active_runtime = runtime if runtime is not None else Runtime(settings)
    tasks: set[asyncio.Task[Any]] = set()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            pending = tuple(tasks)
            await cancel_and_drain(*pending)
            if owns_runtime:
                await active_runtime.aclose()

    app = FastAPI(title="Nubbix Support AI", version="0.1.0", lifespan=lifespan)
    app.state.runtime = active_runtime
    app.state.stream_tasks = tasks

    @app.exception_handler(AppError)
    async def application_error(request: Request, exc: AppError) -> JSONResponse:
        status = 422 if exc.code in {
            "unknown_prompt_version", "unpriced_model", "invalid_run_id", "invalid_evaluation_id",
            "unknown_evaluation_case", "invalid_evaluation", "invalid_dataset",
            "incomparable_prompt_bundles", "invalid_evaluation_selection",
        } else 404 if exc.code in {"run_not_found", "evaluation_not_found"} else (
            409 if exc.code == "evaluation_in_progress" else 503)
        return JSONResponse(status_code=status,
                            content={"error": {"code": exc.code, "request_id": exc.request_id}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content={"error": {"code": "invalid_request", "request_id": None}})

    app.include_router(build_router(active_runtime, tasks))
    app.include_router(build_evaluation_router(active_runtime, tasks))
    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
