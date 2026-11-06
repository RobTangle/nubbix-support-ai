from decimal import Decimal
from pathlib import Path
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from nubbix_support_ai.support.contracts import AppError, ProviderName


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NUBBIX_", extra="ignore", env_ignore_empty=True)
    project_root: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[2])
    openai_api_key: SecretStr | None = Field(default=None, validation_alias="OPENAI_API_KEY",
                                            repr=False, exclude=True)
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY",
                                            repr=False, exclude=True)
    provider: ProviderName = "openai"
    prompt: str | None = None
    openai_model: str = "gpt-6-luna"
    google_model: str = "gemini-3.5-flash-lite"
    reasoning_effort: Literal["none", "low", "medium", "high", "xhigh", "max"] = "xhigh"
    data_dir: Path = Path("data")
    reports_dir: Path = Path("reports/local")
    ticket_usd: Decimal = Field(default=Decimal("0.05"), gt=0, allow_inf_nan=False)
    campaign_usd: Decimal = Field(default=Decimal("2"), gt=0, allow_inf_nan=False)
    timeout_seconds: float = Field(default=15, gt=0, le=15)
    deadline_seconds: float = Field(default=60, gt=0, le=60)
    max_output_tokens: int = Field(default=8192, ge=256, le=16384)
    max_attempts: Literal[2] = 2

    @model_validator(mode="after")
    def resolve_paths(self) -> Self:
        self.project_root = self.project_root.resolve()
        self.data_dir = (self.project_root / self.data_dir).resolve()
        self.reports_dir = (self.project_root / self.reports_dir).resolve()
        return self

    @classmethod
    def load(cls, project_root: Path | None = None) -> Self:
        root = (project_root or Path(__file__).resolve().parents[2]).resolve()
        return cls(project_root=root, _env_file=root / ".env", _env_file_encoding="utf-8")

    def model_for(self, provider: ProviderName) -> str:
        return self.openai_model if provider == "openai" else self.google_model

    def key_for(self, provider: ProviderName) -> str:
        key = self.openai_api_key if provider == "openai" else self.gemini_api_key
        if key is None or not key.get_secret_value().strip():
            raise AppError(f"missing_{provider}_key")
        return key.get_secret_value().strip()
