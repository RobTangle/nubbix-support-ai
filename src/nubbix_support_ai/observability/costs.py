from decimal import Decimal
from pathlib import Path
from threading import Lock

import yaml
from pydantic import BaseModel, Field

from nubbix_support_ai.llm.contracts import TokenUsage
from nubbix_support_ai.support.contracts import AppError


class Tariff(BaseModel):
    input: Decimal = Field(ge=0, allow_inf_nan=False)
    cached: Decimal = Field(ge=0, allow_inf_nan=False)
    cache_write: Decimal = Field(ge=0, allow_inf_nan=False)
    output: Decimal = Field(ge=0, allow_inf_nan=False)
    source: str


class PriceCatalog(BaseModel):
    checked_on: str
    models: dict[str, Tariff]

    def tariff(self, provider: str, model: str) -> Tariff:
        try:
            return self.models[f"{provider}:{model}"]
        except KeyError:
            raise AppError("unpriced_model") from None

    def cost(self, provider: str, model: str, usage: TokenUsage) -> Decimal:
        tariff = self.tariff(provider, model)
        regular = usage.input_tokens - usage.cached_input_tokens - usage.cache_write_input_tokens
        return (regular * tariff.input + usage.cached_input_tokens * tariff.cached
                + usage.cache_write_input_tokens * tariff.cache_write
                + usage.output_tokens * tariff.output) / 1_000_000

    def reserve_cost(self, provider: str, model: str, payload: str, max_output: int) -> Decimal:
        tariff = self.tariff(provider, model)
        estimated_input = len(payload.encode("utf-8")) + 1024
        input_rate = max(tariff.input, tariff.cache_write)
        return (estimated_input * input_rate + max_output * tariff.output) / 1_000_000


def load_prices(project_root: Path) -> PriceCatalog:
    path = project_root / "src/nubbix_support_ai/observability/prices.yaml"
    try:
        return PriceCatalog.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    except (OSError, ValueError, yaml.YAMLError):
        raise AppError("invalid_price_catalog") from None


class Budget:
    """Conservative process-local accounting, shared by all cases in a campaign."""

    def __init__(self, limit: Decimal) -> None:
        if not limit.is_finite() or limit <= 0:
            raise AppError("invalid_budget")
        self.limit = limit
        self.known = Decimal(0)
        self.unknown = Decimal(0)
        self.pending = Decimal(0)
        self._lock = Lock()

    @property
    def committed(self) -> Decimal:
        return self.known + self.unknown + self.pending

    def reserve(self, amount: Decimal) -> Decimal:
        with self._lock:
            if not amount.is_finite() or amount < 0 or self.committed + amount > self.limit:
                raise AppError("budget_exceeded")
            self.pending += amount
        return amount

    def settle(self, reservation: Decimal, cost: Decimal | None) -> None:
        with self._lock:
            if reservation < 0 or reservation > self.pending or (cost is not None and cost < 0):
                raise AppError("budget_accounting_error")
            self.pending -= reservation
            if cost is None:
                self.unknown += reservation
            else:
                self.known += cost
