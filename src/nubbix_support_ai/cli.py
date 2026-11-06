import argparse
import asyncio
import json
import signal
import sys
from collections.abc import Callable, Coroutine, Sequence
from decimal import Decimal
from pathlib import Path
from types import FrameType
from typing import Any

import uvicorn
from pydantic import ValidationError

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.config import Settings
from nubbix_support_ai.observability.costs import Budget
from nubbix_support_ai.prompting.catalog import load_catalog
from nubbix_support_ai.support.contracts import AppError, Ticket


class _TerminationRequested(Exception):
    pass


async def _with_sigterm(
    operation: Callable[[], Coroutine[Any, Any, dict[str, Any]]],
) -> dict[str, Any]:
    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    assert task is not None
    received = False
    def terminate(signum: int, frame: FrameType | None) -> None:
        nonlocal received
        if not received:
            received = True
            loop.call_soon_threadsafe(task.cancel)
    previous = signal.signal(signal.SIGTERM, terminate)
    try:
        result = await operation()
        if received:
            raise _TerminationRequested()
        return result
    except asyncio.CancelledError:
        if received:
            raise _TerminationRequested() from None
        raise
    finally:
        signal.signal(signal.SIGTERM, previous)


def _selection(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", choices=["openai", "google"])
    parser.add_argument("--model", help="Model registered in the price catalog")
    parser.add_argument("--prompt-version", help="Prompt version from the YAML registry")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nubbix", description="Support proposals and local lab")
    commands = parser.add_subparsers(dest="command", required=True)
    respond = commands.add_parser("respond", help="Return a validated support proposal")
    source = respond.add_mutually_exclusive_group(required=True)
    source.add_argument("--text")
    source.add_argument("--stdin", action="store_true")
    _selection(respond)
    prompts = commands.add_parser("prompts", help="Inspect and validate prompt versions")
    prompt_actions = prompts.add_subparsers(dest="action", required=True)
    prompt_actions.add_parser("list")
    prompt_actions.add_parser("check")
    web = commands.add_parser("web", help="Start the local laboratory")
    web.add_argument("--port", type=int, default=8000)
    evaluate = commands.add_parser("eval", help="Run and inspect model evaluations")
    actions = evaluate.add_subparsers(dest="action", required=True)
    for name in ("run", "compare", "adversarial"):
        command = actions.add_parser(name)
        _selection(command)
        command.add_argument("--split", choices=["dev", "test"], default="dev")
        command.add_argument("--max-cost-usd", type=Decimal)
        if name == "compare":
            command.add_argument("--prompt-versions", nargs="+")
        if name == "adversarial":
            command.add_argument("--ablation", action="store_true")
    summarize = actions.add_parser("summarize")
    summarize.add_argument("report", type=Path, help="Path to a campaign directory")
    return parser


async def _respond(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    text = sys.stdin.read() if args.stdin else args.text
    ticket = Ticket(text=text)
    async with Runtime(settings) as runtime:
        result = await runtime.service(args.provider, args.model).run(
            ticket, prompt_version=args.prompt_version,
        )
        return result.response.model_dump()


async def _evaluate(settings: Settings, args: argparse.Namespace) -> dict[str, Any]:
    from nubbix_support_ai.evaluation.data import load_cases
    from nubbix_support_ai.evaluation.runner import run_evaluation
    async with Runtime(settings) as runtime:
        adversarial = args.action == "adversarial"
        path = settings.project_root / "datasets" / (
            "adversarial.jsonl" if adversarial else "tickets.jsonl"
        )
        cases = load_cases(path, None if adversarial else args.split)
        if args.action == "compare":
            versions = args.prompt_versions or [item.id for item in runtime.catalog.versions]
        else:
            versions = [args.prompt_version or settings.prompt or runtime.catalog.default]
        budget = Budget(args.max_cost_usd if args.max_cost_usd is not None else settings.campaign_usd)
        result = await run_evaluation(
            runtime, cases, provider=args.provider or settings.provider,
            prompt_versions=versions, model=args.model, campaign_budget=budget,
            adversarial=adversarial, ablation=getattr(args, "ablation", False),
        )
        return result.to_dict()


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    exit_code = 0
    try:
        settings = Settings.load()
        if args.command == "respond":
            value = asyncio.run(_with_sigterm(lambda: _respond(settings, args)))
        elif args.command == "prompts":
            catalog = load_catalog(settings.project_root)
            value = {"default": catalog.default, "baseline": catalog.baseline,
                     "versions": [item.model_dump() for item in catalog.versions]}
        elif args.command == "web":
            from nubbix_support_ai.web.app import create_app
            if not 1 <= args.port <= 65535:
                raise AppError("invalid_port")
            uvicorn.run(create_app(settings), host="127.0.0.1", port=args.port, workers=1,
                        timeout_graceful_shutdown=5)
            return 0
        elif args.action == "summarize":
            from nubbix_support_ai.evaluation.reports import read_report
            directory = args.report.resolve()
            value = read_report(directory.parent, directory.name)
        else:
            value = asyncio.run(_with_sigterm(lambda: _evaluate(settings, args)))
            exit_code = 0 if value["summary"]["status"] == "completed" else 1
        print(json.dumps(value, ensure_ascii=False, allow_nan=False))
        return exit_code
    except AppError as exc:
        print(json.dumps({"error": {"code": exc.code, "request_id": exc.request_id}}), file=sys.stderr)
    except (ValidationError, ValueError):
        print(json.dumps({"error": {"code": "invalid_input_or_configuration"}}), file=sys.stderr)
    except (_TerminationRequested, KeyboardInterrupt) as exc:
        print(json.dumps({"error": {"code": "cancelled"}}), file=sys.stderr)
        return 143 if isinstance(exc, _TerminationRequested) else 130
    except OSError:
        print(json.dumps({"error": {"code": "io_error"}}), file=sys.stderr)
    return 1
