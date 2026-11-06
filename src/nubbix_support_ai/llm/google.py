from math import ceil
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from nubbix_support_ai.llm.contracts import LLMReply, LLMRequest, ProviderError, TokenUsage
from nubbix_support_ai.llm.errors import configure_sdk_logging, google_error


def _usage(counts: types.GenerateContentResponseUsageMetadata | None) -> TokenUsage | None:
    if counts is None or counts.prompt_token_count is None:
        return None
    try:
        candidates = counts.candidates_token_count
        reasoning = counts.thoughts_token_count or 0
        if candidates is None and counts.total_token_count is None:
            return None
        if candidates is not None and candidates < 0:
            return None
        output = (candidates or 0) + reasoning
        if counts.total_token_count is not None:
            total_output = counts.total_token_count - counts.prompt_token_count
            if total_output < output:
                return None
            output = total_output
        return TokenUsage(input_tokens=counts.prompt_token_count, output_tokens=output,
                          cached_input_tokens=counts.cached_content_token_count or 0,
                          reasoning_output_tokens=reasoning)
    except (ValueError, TypeError):
        return None


class GeminiProvider:
    name = "google"

    def __init__(self, api_key: str, model: str,
                 *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self.parameters: dict[str, Any] = {"thinking_level": "MINIMAL", "service_tier": "standard"}
        configure_sdk_logging()
        self._http = httpx.AsyncClient(transport=transport, timeout=15)
        self._client = genai.Client(api_key=api_key, vertexai=False,
                                    http_options=types.HttpOptions(
                                        base_url="https://generativelanguage.googleapis.com",
                                        httpx_async_client=self._http, timeout=15000,
                                        retry_options=types.HttpRetryOptions(attempts=1),
                                    ))

    async def complete(self, request: LLMRequest) -> LLMReply:
        try:
            response = await self._client.aio.models.generate_content(
                model=self.model, contents=[types.Content(
                    role="model" if message.role == "assistant" else "user",
                    parts=[types.Part.from_text(text=message.content)],
                ) for message in request.messages],
                config=types.GenerateContentConfig(
                    system_instruction=request.system, response_mime_type="application/json",
                    response_json_schema=request.schema, max_output_tokens=request.max_output_tokens,
                    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
                    service_tier=types.ServiceTier.STANDARD,
                    # Gemini's server deadline has a 10s minimum; the local timeout stays shorter.
                    http_options=types.HttpOptions(
                        timeout=max(1, int(request.timeout_seconds * 1000)),
                        headers={"X-Server-Timeout": str(max(10, ceil(request.timeout_seconds)))},
                    ),
                ),
            )
            usage = _usage(response.usage_metadata)
            model = response.model_version or self.model
            block = response.prompt_feedback.block_reason if response.prompt_feedback else None
            if block and block != types.BlockedReason.BLOCKED_REASON_UNSPECIFIED:
                return LLMReply("", usage, model, refused=True)
            if not response.candidates or len(response.candidates) != 1:
                raise ProviderError("invalid_provider_response", usage=usage)
            candidate = response.candidates[0]
            if candidate.finish_reason in {types.FinishReason.SAFETY, types.FinishReason.RECITATION,
                                            types.FinishReason.BLOCKLIST,
                                            types.FinishReason.PROHIBITED_CONTENT,
                                            types.FinishReason.SPII}:
                return LLMReply("", usage, model, refused=True)
            if candidate.finish_reason == types.FinishReason.MAX_TOKENS:
                raise ProviderError("max_tokens", usage=usage)
            if candidate.finish_reason != types.FinishReason.STOP or not candidate.content:
                raise ProviderError("invalid_provider_response", usage=usage)
            text = "".join(part.text for part in candidate.content.parts or []
                           if part.text and not part.thought)
            if not text:
                raise ProviderError("invalid_provider_response", usage=usage)
            return LLMReply(text, usage, model)
        except ProviderError:
            raise
        except errors.APIError as exc:
            headers = getattr(exc.response, "headers", {})
            raise google_error(exc.code, exc.details, headers.get("retry-after")) from None
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderError("timeout", retryable=True) from None
        except (httpx.NetworkError, httpx.RemoteProtocolError):
            raise ProviderError("connection_error", retryable=True) from None
        except Exception:
            raise ProviderError("invalid_provider_response") from None

    async def aclose(self) -> None:
        await self._client.aio.aclose()
        self._client.close()
        await self._http.aclose()
