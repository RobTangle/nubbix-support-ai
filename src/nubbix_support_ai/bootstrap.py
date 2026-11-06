from types import TracebackType
from typing import Self

from nubbix_support_ai.config import Settings
from nubbix_support_ai.llm.contracts import LLMProvider
from nubbix_support_ai.observability.costs import load_prices
from nubbix_support_ai.observability.storage import RunStore
from nubbix_support_ai.prompting.catalog import load_catalog
from nubbix_support_ai.support.contracts import AppError, ProviderName
from nubbix_support_ai.support.service import SupportService


class Runtime:
    def __init__(self, settings: Settings,
                 providers: dict[ProviderName, LLMProvider] | None = None) -> None:
        self.settings = settings
        self.catalog = load_catalog(settings.project_root)
        self.prices = load_prices(settings.project_root)
        self.store = RunStore(settings.data_dir)
        self._providers: dict[tuple[ProviderName, str], LLMProvider] = {
            (name, provider.model): provider for name, provider in (providers or {}).items()
        }

    def service(self, provider: ProviderName | None = None,
                model: str | None = None) -> SupportService:
        selected = provider or self.settings.provider
        selected_model = model or self.settings.model_for(selected)
        self.prices.tariff(selected, selected_model)
        key = (selected, selected_model)
        if key not in self._providers:
            api_key = self.settings.key_for(selected)
            if selected == "openai":
                from nubbix_support_ai.llm.openai import OpenAIProvider
                client: LLMProvider = OpenAIProvider(api_key, selected_model,
                                                    effort=self.settings.reasoning_effort)
            elif selected == "google":
                from nubbix_support_ai.llm.google import GeminiProvider
                client = GeminiProvider(api_key, selected_model)
            else:
                raise AppError("unknown_provider")
            self._providers[key] = client
        return SupportService(self._providers[key], self.settings, self.catalog, self.prices, self.store)

    def available(self, provider: ProviderName) -> bool:
        if any(name == provider for name, _ in self._providers):
            return True
        try:
            self.settings.key_for(provider)
        except AppError:
            return False
        return True

    async def aclose(self) -> None:
        for provider in self._providers.values():
            await provider.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, exc_type: type[BaseException] | None,
                        exc: BaseException | None, traceback: TracebackType | None) -> None:
        await self.aclose()
