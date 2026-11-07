from typing import Any

STAGES = ("input_moderation", "generation", "output_moderation")


def summarize_flow(inspection: dict[str, Any], *, arm: str | None = None) -> dict[str, Any] | None:
    """Summarize recorded decisions without copying prompt or response text."""
    calls = inspection.get("calls")
    if not isinstance(calls, list):
        return None
    unguarded = (arm or inspection.get("evaluation_arm")) == "unguarded"
    stages: dict[str, dict[str, Any]] = {}
    blockers = []
    for stage in STAGES:
        attempts = [call for call in calls if isinstance(call, dict) and call.get("stage") == stage]
        if not attempts:
            status = "skipped" if unguarded and stage != "generation" else "not_run"
            stages[stage] = {"status": status, "attempts": 0}
            continue
        last = attempts[-1]
        status = last.get("status", "unknown")
        result = {"status": status, "attempts": len(attempts)}
        validated = last.get("validated_response") or last.get("validated")
        if status == "ok" and isinstance(validated, dict):
            keys = ("category", "confidence") if stage == "generation" else ("decision", "reason_code")
            result.update({key: validated[key] for key in keys if key in validated})
        if status == "refused":
            result["reason_code"] = "provider_refusal"
        if last.get("error_code"):
            result["error_code"] = last["error_code"]
        if status == "refused" or result.get("decision") in ("block", "review"):
            blockers.append(stage)
        stages[stage] = result
    blocked_at = blockers[0] if inspection.get("status") == "blocked" and len(blockers) == 1 else None
    return {"stages": stages, "blocked_at": blocked_at}
