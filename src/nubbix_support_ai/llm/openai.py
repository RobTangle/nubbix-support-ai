from typing import Any, Literal

import httpx
import openai
from openai.types.responses import Response

from nubbix_support_ai.llm.contracts import LLMReply, LLMRequest, ProviderError, TokenUsage
from nubbix_support_ai.llm.errors import configure_sdk_logging, http_error

Effort = Literal["none", "low", "medium", "high", "xhigh", "max"]


def _usage(response: Response) -> TokenUsage | None:
    counts = response.usage
    if counts is None:
        return None
    try:
        usage = TokenUsage(
            input_tokens=counts.input_tokens, output_tokens=counts.output_tokens,
            cached_input_tokens=getattr(counts.input_tokens_details, "cached_tokens", 0),
            cache_write_input_tokens=getattr(counts.input_tokens_details, "cache_write_tokens", 0),
            reasoning_output_tokens=getattr(counts.output_tokens_details, "reasoning_tokens", 0),
        )
        return usage if usage.total_tokens == counts.total_tokens else None
    except (ValueError, TypeError, AttributeError):
        return None


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, model: str, *, effort: Effort = "xhigh",
                 transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.model = model
        self.effort = effort
        self.parameters: dict[str, Any] = {"reasoning_effort": effort,
                                           "reasoning_mode": "standard", "service_tier": "default"}
        configure_sdk_logging()
        self._client = openai.AsyncOpenAI(
            api_key=api_key, max_retries=0, base_url="https://api.openai.com/v1",
            http_client=httpx.AsyncClient(transport=transport, timeout=15),
        )

    async def complete(self, request: LLMRequest) -> LLMReply:
        try:
            response = await self._client.responses.create(
                model=self.model, instructions=request.system,
                input=[{"role": message.role, "content": message.content}
                       for message in request.messages],
                reasoning={"effort": self.effort, "mode": "standard"},
                max_output_tokens=request.max_output_tokens, store=False, service_tier="default",
                timeout=request.timeout_seconds,
                text={"format": {"type": "json_schema", "name": "structured_result",
                                  "strict": True, "schema": request.schema}},
            )
            usage = _usage(response)
            if response.status == "incomplete":
                reason = getattr(response.incomplete_details, "reason", None)
                if reason == "content_filter":
                    return LLMReply("", usage, response.model, refused=True)
                raise ProviderError("max_tokens", usage=usage)
            if response.status != "completed":
                code = getattr(response.error, "code", "invalid_provider_response")
                raise ProviderError("provider_unavailable" if code == "server_error" else
                                    "invalid_provider_response", retryable=code == "server_error",
                                    usage=usage)
            for item in response.output:
                if item.type == "message" and any(part.type == "refusal" for part in item.content):
                    return LLMReply("", usage, response.model, refused=True)
            if not response.output_text:
                raise ProviderError("invalid_provider_response", usage=usage)
            return LLMReply(response.output_text, usage, response.model)
        except ProviderError:
            raise
        except openai.APIStatusError as exc:
            if exc.status_code == 429 and exc.code in {"insufficient_quota", "billing_hard_limit_reached"}:
                raise ProviderError("quota_exhausted") from None
            raise http_error(exc.status_code, exc.response.headers.get("retry-after")) from None
        except (openai.APITimeoutError, httpx.TimeoutException):
            raise ProviderError("timeout", retryable=True) from None
        except (openai.APIConnectionError, httpx.NetworkError):
            raise ProviderError("connection_error", retryable=True) from None
        except Exception:
            raise ProviderError("invalid_provider_response") from None

    async def aclose(self) -> None:
        await self._client.close()
