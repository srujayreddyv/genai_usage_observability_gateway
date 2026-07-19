"""Application configuration loaded from environment variables."""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import (
    AnyHttpUrl,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict


class DeploymentEnvironment(StrEnum):
    """Supported deployment environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


class ProviderName(StrEnum):
    """Analytics providers supported by application configuration."""

    MOCK = "mock"
    ANTHROPIC = "anthropic"


DEFAULT_PREVIEW_OUTPUT_PATH = Path("telemetry-output/usage-preview.json")


class AppSettings(BaseSettings):
    """Validated, secret-safe application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_environment: DeploymentEnvironment = DeploymentEnvironment.DEVELOPMENT
    analytics_provider: ProviderName = ProviderName.MOCK
    pseudonymization_key: SecretStr | None = None
    anthropic_analytics_api_key: SecretStr | None = None
    anthropic_result_limit: int = Field(default=100, ge=1, le=1000)
    anthropic_request_timeout_seconds: float = Field(default=10.0, gt=0, le=120)
    otel_exporter_otlp_endpoint: AnyHttpUrl | None = None
    otel_exporter_otlp_headers: SecretStr | None = None
    preview_enabled: bool | None = None
    preview_output_path: Path = DEFAULT_PREVIEW_OUTPUT_PATH

    @field_validator(
        "pseudonymization_key",
        "anthropic_analytics_api_key",
        "otel_exporter_otlp_endpoint",
        "otel_exporter_otlp_headers",
        "preview_enabled",
        mode="before",
    )
    @classmethod
    def empty_string_is_unset(cls, value: Any) -> Any:
        """Treat empty environment variables as absent configuration."""

        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def validate_required_secrets(self) -> "AppSettings":
        """Require secrets only where the selected runtime needs them."""

        if (
            self.app_environment
            not in {DeploymentEnvironment.DEVELOPMENT, DeploymentEnvironment.TEST}
            and self.pseudonymization_key is None
        ):
            raise ValueError(
                "PSEUDONYMIZATION_KEY is required outside development and test"
            )

        if (
            self.analytics_provider is ProviderName.ANTHROPIC
            and self.anthropic_analytics_api_key is None
        ):
            raise ValueError(
                "ANTHROPIC_ANALYTICS_API_KEY is required for the Anthropic provider"
            )

        return self

    @property
    def preview_generation_enabled(self) -> bool:
        """Use environment-aware preview defaults unless explicitly configured."""

        if self.preview_enabled is not None:
            return self.preview_enabled
        return self.app_environment is DeploymentEnvironment.DEVELOPMENT


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    """Return one cached settings instance for the application process."""

    return AppSettings()


def clear_settings_cache() -> None:
    """Clear cached settings for tests and explicit runtime reconfiguration."""

    get_settings.cache_clear()
