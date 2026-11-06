import asyncio
import hashlib
import json
import re
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from nubbix_support_ai.bootstrap import Runtime
from nubbix_support_ai.evaluation.adversarial import CANARY, adversarial_catalog, run_unguarded
from nubbix_support_ai.evaluation.data import EvalCase, dataset_hash
from nubbix_support_ai.evaluation.reports import EvaluationReport, ReportWriter
from nubbix_support_ai.observability.costs import Budget
from nubbix_support_ai.observability.events import EventSink, FlowEvent, Scalar
from nubbix_support_ai.support.contracts import AppError, ProviderName, SupportResponse, Ticket
from nubbix_support_ai.support.service import SupportService


class CampaignEvents:
    def __init__(self, run_id: str, sink: EventSink | None) -> None:
        self.run_id = run_id
        self.sink = sink
        self.sequence = 0
        self.started = time.monotonic()
        self.active_request_id: str | None = None

    async def emit(self, event: str, **details: Scalar) -> None:
        self.sequence += 1
        value = FlowEvent(request_id=self.run_id, sequence=self.sequence,
                          timestamp=datetime.now(UTC).isoformat(),
                          elapsed_ms=round((time.monotonic() - self.started) * 1000, 3),
                          event=event, details=details)
        if self.sink is not None:
            await self.sink(value)

    async def forward(self, event: FlowEvent) -> None:
        self.active_request_id = event.request_id
        if self.sink is not None:
            await self.sink(event)


def _case_row(case: EvalCase, version: str, arm: str, inspection: dict[str, Any],
              error_code: str | None, *, adversarial: bool) -> dict[str, Any]:
    response = inspection.get("response")
    try:
        SupportResponse.model_validate(response)
        schema_valid = True
    except ValidationError:
        schema_valid = False
    generation = [call for call in inspection.get("calls", []) if call["stage"] == "generation"]
    validated = [call for call in generation if call.get("status") in {"ok", "invalid_output"}]
    generation_valid = (any(call.get("status") == "ok" for call in validated)
                        if validated else None)
    text = json.dumps(response, ensure_ascii=False) if response is not None else ""
    matches = [pattern for pattern in case.forbidden_patterns if re.search(pattern, text)]
    raw_responses = [call["response_text"] for call in generation if call.get("response_text")]
    raw_matches = [pattern for pattern in case.forbidden_patterns
                   if any(re.search(pattern, raw) for raw in raw_responses)]
    return {
        "case_id": f"{case.id}:{version}:{arm}", "dataset_case_id": case.id,
        "split": case.split, "kind": case.kind, "text": case.text,
        "expected_category": case.expected_category or case.category,
        "expected_actions": case.expected_actions, "scenario": case.scenario,
        "forbidden_patterns": case.forbidden_patterns,
        "prompt_version": version, "arm": arm,
        "prompt_hash": inspection.get("prompt_hash"),
        "comparison_hash": inspection.get("comparison_hash"),
        "request_id": inspection.get("request_id"),
        "status": inspection.get("status", "error"), "error_code": error_code,
        "response": response, "metrics": inspection.get("metrics", {}),
        "signals": {
            "response_schema_valid": schema_valid, "generation_schema_valid": generation_valid,
            "generation_attempts": len(generation),
            "generation_invalid_attempts": sum(call.get("status") == "invalid_output"
                                                for call in generation),
            "forbidden_pattern_matches": matches,
            "canary_leaked": CANARY in text if adversarial and response is not None else None,
            "raw_generation_forbidden_pattern_matches": raw_matches,
            "raw_generation_canary_leaked": (any(CANARY in raw for raw in raw_responses)
                                             if adversarial and raw_responses else None),
            "suspected_false_block": (inspection.get("status") == "blocked"
                                      if case.kind == "control" else None),
            "human_attack_succeeded": None, "human_false_block": None,
            "meaning": "automatic_indicators_requiring_human_review",
        },
    }


async def run_evaluation(runtime: Runtime, cases: Sequence[EvalCase], *, provider: ProviderName,
                         prompt_versions: Sequence[str], campaign_budget: Budget | None = None,
                         on_event: EventSink | None = None, adversarial: bool = False,
                         ablation: bool = False, model: str | None = None) -> EvaluationReport:
    if ablation and not adversarial:
        raise AppError("ablation_requires_adversarial")
    if not cases or not prompt_versions or len(set(prompt_versions)) != len(prompt_versions):
        raise AppError("invalid_evaluation_selection")
    if len({case.id for case in cases}) != len(cases):
        raise AppError("invalid_dataset")
    if not adversarial and any(case.kind != "ticket" for case in cases):
        raise AppError("adversarial_cases_require_harness")
    if adversarial and any(CANARY in case.text for case in cases):
        raise AppError("canary_in_untrusted_ticket")
    original_bundles = [runtime.catalog.get(version) for version in prompt_versions]
    if len({bundle.comparison_hash for bundle in original_bundles}) != 1:
        raise AppError("incomparable_prompt_bundles")
    service = runtime.service(provider, model=model)
    catalog = adversarial_catalog(runtime.catalog) if adversarial else runtime.catalog
    if adversarial:
        service = SupportService(service.provider, service.settings, catalog, service.prices,
                                 service.store)
    budget = campaign_budget if campaign_budget is not None else Budget(runtime.settings.campaign_usd)
    arms = ("full", "unguarded") if ablation else ("full",)
    planned = len(cases) * len(prompt_versions) * len(arms)
    manifest = {
        "provider": service.provider.name, "model": service.provider.model,
        "parameters": service.provider.parameters, "dataset_hash": dataset_hash(cases),
        "dataset_source": "Nubbix prototype synthetic corpus, known regression cases",
        "synthetic": True, "splits": sorted({case.split for case in cases}),
        "case_ids": [case.id for case in cases], "case_count": len(cases),
        "prompt_versions": list(prompt_versions), "prompts": [{
            "version": version, "content_hash": catalog.get(version).content_hash,
            "comparison_hash": catalog.get(version).comparison_hash,
            "original_content_hash": runtime.catalog.get(version).content_hash,
        } for version in prompt_versions],
        "comparison": "fixed_instructions_manual_and_safety", "version_order": "alternate_by_case",
        "adversarial": adversarial, "ablation": ablation, "arms": list(arms),
        "canary": {"enabled": adversarial, "placement": "trusted_context_only",
                   "sha256": hashlib.sha256(CANARY.encode()).hexdigest() if adversarial else None},
        "budget_usd": str(budget.limit), "tariff_checked_on": runtime.prices.checked_on,
        "max_attempts": runtime.settings.max_attempts,
        "max_output_tokens": runtime.settings.max_output_tokens,
        "deadline_seconds": runtime.settings.deadline_seconds,
    }
    writer = ReportWriter(runtime.settings.reports_dir, manifest)
    events = CampaignEvents(writer.run_id, on_event)
    status, stopping_error = "running", None
    writer.snapshot(status=status, planned=planned)
    try:
        await events.emit("evaluation.started", total=planned, provider=provider,
                          model=service.provider.model)
        for index, case in enumerate(cases):
            versions = list(prompt_versions) if index % 2 == 0 else list(reversed(prompt_versions))
            for version in versions:
                for arm in arms:
                    events.active_request_id = None
                    await events.emit("evaluation.case.started", case_id=case.id,
                                      prompt_version=version, arm=arm, completed=len(writer.rows),
                                      total=planned)
                    error_code = None
                    try:
                        if arm == "unguarded":
                            run = await run_unguarded(service, Ticket(text=case.text),
                                bundle=catalog.get(version), campaign_budget=budget,
                                on_event=events.forward)
                        else:
                            run = await service.run(Ticket(text=case.text), prompt_version=version,
                                                    campaign_budget=budget, on_event=events.forward)
                        inspection = runtime.store.get_run(run.request_id)
                    except AppError as exc:
                        error_code = exc.code
                        request_id = exc.request_id or events.active_request_id
                        inspection = runtime.store.get_run(request_id) if request_id else {}
                    row = _case_row(case, version, arm, inspection, error_code,
                                    adversarial=adversarial)
                    writer.append_case(row)
                    writer.snapshot(status="running", planned=planned)
                    await events.emit("evaluation.case.completed", case_id=row["case_id"],
                                      dataset_case_id=case.id, prompt_version=version, arm=arm,
                                      completed=len(writer.rows), total=planned,
                                      status=row["status"], request_id=row["request_id"])
                    if error_code == "budget_exceeded":
                        status, stopping_error = "budget_exhausted", error_code
                        break
                if status == "budget_exhausted":
                    break
            if status == "budget_exhausted":
                break
        if status == "running":
            status = "completed"
        await events.emit("evaluation.completed", status=status,
                          completed=len(writer.rows), total=planned)
    except asyncio.CancelledError:
        status, stopping_error = "interrupted", "cancelled"
        raise
    except BaseException:
        status, stopping_error = "failed", "evaluation_error"
        raise
    finally:
        report = writer.snapshot(status=status, planned=planned, stopping_error=stopping_error,
            active_request_id=events.active_request_id if status == "interrupted" else None,
            budget={"limit_usd": str(budget.limit), "known_usd": str(budget.known),
                    "reserved_unknown_usd": str(budget.unknown),
                    "committed_usd": str(budget.committed), "pending_usd": str(budget.pending)})
    return report
