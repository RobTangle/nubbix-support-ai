import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from logging import CRITICAL, Logger, getLogger
from math import isfinite
from typing import Any

from nubbix_support_ai.llm.contracts import ProviderError


def configure_sdk_logging() -> None:
    prefixes = ("openai", "google_genai", "httpx", "httpcore")
    for prefix in prefixes:
        getLogger(prefix).setLevel(CRITICAL + 1)
    for name, logger in list(Logger.manager.loggerDict.items()):
        if isinstance(logger, Logger) and any(name.startswith(prefix + ".") for prefix in prefixes):
            logger.setLevel(CRITICAL + 1)


def http_error(status: int, retry_after: str | None = None) -> ProviderError:
    codes = {400: "invalid_request", 401: "authentication_error", 403: "permission_denied",
             404: "model_not_found", 408: "timeout", 409: "conflict", 422: "invalid_request",
             429: "rate_limited"}
    retryable = status in {408, 409, 429} or 500 <= status < 600
    delay = 0.0
    if retry_after and retryable:
        try:
            delay = float(retry_after)
        except ValueError:
            try:
                delay = (parsedate_to_datetime(retry_after) - datetime.now(UTC)).total_seconds()
            except (ValueError, OverflowError, TypeError):
                pass
    return ProviderError(codes.get(status, "provider_unavailable" if status >= 500 else
                                    "provider_error"), retryable=retryable,
                         retry_after=max(0, delay) if isfinite(delay) else 0)


def google_error(status: int, details: Any, retry_after: str | None = None) -> ProviderError:
    result = http_error(status, retry_after)
    if status != 429 or not isinstance(details, dict):
        return result
    payload = details.get("error", details)
    records = payload.get("details", []) if isinstance(payload, dict) else []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
            continue
        duration = record.get("retryDelay", "")
        if isinstance(duration, str) and re.fullmatch(r"\d+(?:\.\d+)?s", duration):
            seconds = float(duration[:-1])
            if isfinite(seconds):
                result.retry_after = max(result.retry_after, seconds)
        for violation in record.get("violations", []):
            if not isinstance(violation, dict):
                continue
            quota_id = violation.get("quotaId", violation.get("quota_id", ""))
            if isinstance(quota_id, str) and "perday" in quota_id.lower().replace("_", ""):
                return ProviderError("quota_exhausted")
    return result
