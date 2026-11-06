import json
import logging

import httpx
import pytest

from nubbix_support_ai.llm.contracts import LLMRequest, Message, ProviderError
from nubbix_support_ai.llm.google import GeminiProvider
from nubbix_support_ai.llm.openai import OpenAIProvider
from nubbix_support_ai.support.contracts import SupportResponse
from tests.helpers import PROPOSAL

REQUEST = LLMRequest("System instructions", (Message("user", '{"ticket":"Test"}'),),
                     SupportResponse.model_json_schema(), 8192, 1)


def openai_response(status="completed", *, refusal=False):
    part = ({"type": "refusal", "refusal": "Cannot comply"} if refusal else
            {"type": "output_text", "text": json.dumps(PROPOSAL), "annotations": []})
    return {"id": "resp_test", "object": "response", "created_at": 1, "status": status,
            "model": "gpt-6-luna", "output": [{"id": "msg_test", "type": "message",
            "role": "assistant", "status": "completed", "content": [part]}],
            "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120,
                      "input_tokens_details": {"cached_tokens": 30, "cache_write_tokens": 10},
                      "output_tokens_details": {"reasoning_tokens": 5}}}


async def test_openai_uses_schema_xhigh_and_normalizes_billed_usage():
    bodies = []
    def handle(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json=openai_response())
    provider = OpenAIProvider("test-key", "gpt-6-luna", effort="xhigh",
                              transport=httpx.MockTransport(handle))
    try:
        reply = await provider.complete(REQUEST)
    finally:
        await provider.aclose()
    assert bodies[0]["reasoning"] == {"effort": "xhigh", "mode": "standard"}
    assert bodies[0]["text"]["format"]["strict"] is True
    assert bodies[0]["store"] is False
    assert "temperature" not in bodies[0]
    assert reply.usage.total_tokens == 120
    assert reply.usage.cache_write_input_tokens == 10
    assert reply.usage.reasoning_output_tokens == 5


@pytest.mark.parametrize("status,code,retryable", [
    (401, "authentication_error", False), (429, "rate_limited", True),
    (503, "provider_unavailable", True),
])
async def test_openai_performs_one_sdk_attempt_and_sanitizes_errors(status, code, retryable):
    attempts = []
    def handle(request):
        attempts.append(request)
        return httpx.Response(status, json={"error": {"message": "PRIVATE-TICKET",
                              "type": "test_error", "code": "test_error"}},
                              headers={"retry-after": "1"})
    provider = OpenAIProvider("test-key", "gpt-6-luna", effort="xhigh",
                              transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ProviderError) as error:
            await provider.complete(REQUEST)
    finally:
        await provider.aclose()
    assert error.value.code == code
    assert error.value.retryable is retryable
    assert "PRIVATE" not in str(error.value)
    assert len(attempts) == 1


async def test_openai_refusal_and_truncation_keep_usage():
    data = openai_response(refusal=True)
    provider = OpenAIProvider("test-key", "gpt-6-luna", effort="max",
                              transport=httpx.MockTransport(lambda _: httpx.Response(200, json=data)))
    try:
        reply = await provider.complete(REQUEST)
        assert reply.refused and reply.usage.total_tokens == 120
        data["status"] = "incomplete"
        data["incomplete_details"] = {"reason": "max_output_tokens"}
        with pytest.raises(ProviderError) as error:
            await provider.complete(REQUEST)
        assert error.value.code == "max_tokens"
        assert error.value.usage.total_tokens == 120
    finally:
        await provider.aclose()


async def test_gemini_normalizes_reasoning_and_standard_tier_without_openai():
    bodies = []
    def handle(request):
        bodies.append(json.loads(request.content))
        return httpx.Response(200, json={
            "candidates": [{"content": {"role": "model", "parts": [
                {"text": "hidden reasoning", "thought": True},
                {"text": json.dumps(PROPOSAL)}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 100, "candidatesTokenCount": 20,
                              "thoughtsTokenCount": 5, "totalTokenCount": 125,
                              "cachedContentTokenCount": 40},
            "modelVersion": "gemini-3.5-flash-lite",
        })
    provider = GeminiProvider("test-key", "gemini-3.5-flash-lite",
                              transport=httpx.MockTransport(handle))
    try:
        reply = await provider.complete(REQUEST)
    finally:
        await provider.aclose()
    assert reply.text == json.dumps(PROPOSAL)
    assert reply.usage.output_tokens == 25
    assert reply.usage.reasoning_output_tokens == 5
    assert reply.usage.total_tokens == 125
    assert bodies[0]["generationConfig"]["responseJsonSchema"]["additionalProperties"] is False
    thinking = bodies[0]["generationConfig"]["thinkingConfig"]
    assert thinking.get("thinking_level", thinking.get("thinkingLevel")) == "MINIMAL"
    assert bodies[0]["serviceTier"] == "standard"


async def test_gemini_rate_limit_has_no_hidden_sdk_retries():
    attempts = []
    def handle(request):
        attempts.append(request)
        return httpx.Response(429, json={"error": {"code": 429, "message": "PRIVATE-TICKET",
                                                  "status": "RESOURCE_EXHAUSTED"}})
    provider = GeminiProvider("test-key", "gemini-3.5-flash-lite",
                              transport=httpx.MockTransport(handle))
    try:
        with pytest.raises(ProviderError, match="rate_limited"):
            await provider.complete(REQUEST)
    finally:
        await provider.aclose()
    assert len(attempts) == 1


@pytest.mark.parametrize("provider_name", ["openai", "google"])
async def test_sdk_debug_logging_does_not_publish_request_content(provider_name, caplog):
    caplog.set_level(logging.DEBUG)
    if provider_name == "openai":
        provider = OpenAIProvider("test-key", "gpt-6-luna", transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=openai_response())))
    else:
        provider = GeminiProvider("test-key", "gemini-3.5-flash-lite", transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"promptFeedback": {"blockReason": "SAFETY"}})))
    try:
        await provider.complete(REQUEST)
    finally:
        await provider.aclose()
    assert "System instructions" not in caplog.text
    assert '"ticket":"Test"' not in caplog.text
