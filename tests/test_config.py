from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
    ProviderName,
    clear_settings_cache,
    get_settings,
)


def load_settings_without_dotenv() -> AppSettings:
    options: dict[str, Any] = {"_env_file": None}
    return AppSettings(**options)


def load_settings_from_dotenv(env_file: Path) -> AppSettings:
    options: dict[str, Any] = {"_env_file": env_file}
    return AppSettings(**options)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    for name in (
        "APP_ENVIRONMENT",
        "ANALYTICS_PROVIDER",
        "PSEUDONYMIZATION_KEY",
        "ANTHROPIC_ADMIN_API_KEY",
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "OTEL_EXPORTER_OTLP_HEADERS",
    ):
        monkeypatch.delenv(name, raising=False)
    clear_settings_cache()
    yield
    clear_settings_cache()


def test_defaults_select_local_mock_provider() -> None:
    settings = load_settings_without_dotenv()

    assert settings.app_environment is DeploymentEnvironment.DEVELOPMENT
    assert settings.analytics_provider is ProviderName.MOCK
    assert settings.pseudonymization_key is None
    assert settings.otel_exporter_otlp_endpoint is None


def test_settings_load_and_protect_environment_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "synthetic-pseudonymization-secret"
    monkeypatch.setenv("APP_ENVIRONMENT", "production")
    monkeypatch.setenv("PSEUDONYMIZATION_KEY", secret)
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "https://telemetry.example.test")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "x-demo=synthetic-value")

    settings = load_settings_without_dotenv()

    assert settings.app_environment is DeploymentEnvironment.PRODUCTION
    assert settings.pseudonymization_key is not None
    assert settings.pseudonymization_key.get_secret_value() == secret
    assert secret not in repr(settings)
    assert (
        str(settings.otel_exporter_otlp_endpoint) == "https://telemetry.example.test/"
    )


@pytest.mark.parametrize("environment", ["staging", "production"])
def test_nonlocal_environment_requires_pseudonymization_key(
    monkeypatch: pytest.MonkeyPatch, environment: str
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", environment)

    with pytest.raises(ValidationError, match="PSEUDONYMIZATION_KEY is required"):
        load_settings_without_dotenv()


def test_anthropic_provider_requires_admin_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANALYTICS_PROVIDER", "anthropic")

    with pytest.raises(ValidationError, match="ANTHROPIC_ADMIN_API_KEY is required"):
        load_settings_without_dotenv()


def test_anthropic_provider_accepts_admin_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ANALYTICS_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_ADMIN_API_KEY", "synthetic-admin-key")

    settings = load_settings_without_dotenv()

    assert settings.analytics_provider is ProviderName.ANTHROPIC
    assert settings.anthropic_admin_api_key is not None


def test_empty_optional_environment_values_are_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PSEUDONYMIZATION_KEY", "  ")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")

    settings = load_settings_without_dotenv()

    assert settings.pseudonymization_key is None
    assert settings.otel_exporter_otlp_endpoint is None


def test_invalid_endpoint_is_rejected_without_input_in_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_endpoint = "not-a-public-http-url"
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", invalid_endpoint)

    with pytest.raises(ValidationError) as error:
        load_settings_without_dotenv()

    assert invalid_endpoint not in str(error.value)


def test_unknown_dotenv_setting_is_rejected(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("UNRECOGNIZED_SETTING=value\n", encoding="utf-8")

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        load_settings_from_dotenv(env_file)


def test_get_settings_returns_cached_instance() -> None:
    first = get_settings()
    second = get_settings()

    assert first is second


def test_clear_settings_cache_loads_new_instance() -> None:
    first = get_settings()

    clear_settings_cache()

    assert get_settings() is not first


def test_settings_are_immutable() -> None:
    settings = load_settings_without_dotenv()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        settings.analytics_provider = ProviderName.ANTHROPIC
