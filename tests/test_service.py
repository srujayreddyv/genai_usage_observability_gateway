"""Tests for provider selection, readiness, and safe preview loading."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, Generic, TypeVar

import pytest
from pydantic import SecretStr

from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
    ProviderName,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.providers.errors import ProviderTransportError
from genai_usage_observability_gateway.providers.mock import MockUserActivityRecord
from genai_usage_observability_gateway.service import (
    CollectionFailedError,
    GatewayService,
    PreviewNotFoundError,
    PreviewReadError,
    ServiceConfigurationError,
    _anthropic_client_from_settings,
    create_gateway_service,
)
from genai_usage_observability_gateway.telemetry import (
    TelemetryManager,
    TelemetryRuntime,
)
from tests.factories import anthropic_activity_payload, anthropic_record_from_payload

REPORTING_DATE = date(2026, 2, 3)
RecordT = TypeVar(
    "RecordT",
    AnthropicUserActivityRecord,
    MockUserActivityRecord,
)


def _settings(**values: object) -> AppSettings:
    options: dict[str, Any] = {
        "_env_file": None,
        "app_environment": DeploymentEnvironment.TEST,
        **values,
    }
    return AppSettings(**options)


@pytest.fixture
def telemetry_runtime() -> Iterator[TelemetryRuntime]:
    manager = TelemetryManager()
    runtime = manager.initialize(_settings())
    try:
        yield runtime
    finally:
        manager.shutdown()


class InMemoryClient(Generic[RecordT]):
    def __init__(
        self,
        provider: ProviderName,
        records: tuple[RecordT, ...] = (),
        *,
        exception: Exception | None = None,
    ) -> None:
        self._provider = provider
        self._records: tuple[RecordT, ...] = records
        self._exception = exception

    @property
    def provider(self) -> ProviderName:
        return self._provider

    async def get_usage_analytics(self, reporting_date: date) -> tuple[RecordT, ...]:
        if self._exception is not None:
            raise self._exception
        return self._records


def test_anthropic_client_factory_requires_and_uses_configuration() -> None:
    missing = _settings().model_copy(
        update={"analytics_provider": ProviderName.ANTHROPIC}
    )
    with pytest.raises(ServiceConfigurationError, match="credentials"):
        _anthropic_client_from_settings(missing)

    configured = _settings(
        analytics_provider=ProviderName.ANTHROPIC,
        anthropic_analytics_api_key=SecretStr("synthetic-anthropic-api-key"),
        pseudonymization_key=SecretStr("synthetic-pseudonym-key"),
    )
    client = _anthropic_client_from_settings(configured)
    assert client.provider is ProviderName.ANTHROPIC
    assert "synthetic-anthropic-api-key" not in repr(client)


def test_service_rejects_invalid_preview_destination(
    telemetry_runtime: TelemetryRuntime,
) -> None:
    settings = _settings(preview_enabled=True, preview_output_path=Path("/"))

    with pytest.raises(ServiceConfigurationError, match="preview output"):
        GatewayService(settings, telemetry_runtime)


def test_readiness_validates_each_selected_provider_requirement(
    telemetry_runtime: TelemetryRuntime,
) -> None:
    missing_anthropic_key = _settings().model_copy(
        update={"analytics_provider": ProviderName.ANTHROPIC}
    )
    with pytest.raises(ServiceConfigurationError, match="credentials"):
        GatewayService(missing_anthropic_key, telemetry_runtime).validate_readiness()

    missing_pseudonym_key = _settings(
        analytics_provider=ProviderName.ANTHROPIC,
        anthropic_analytics_api_key=SecretStr("synthetic-api-key"),
    )
    with pytest.raises(ServiceConfigurationError, match="pseudonymization"):
        GatewayService(missing_pseudonym_key, telemetry_runtime).validate_readiness()

    unsafe_mock = _settings().model_copy(
        update={"app_environment": DeploymentEnvironment.PRODUCTION}
    )
    service = GatewayService(unsafe_mock, telemetry_runtime)
    with pytest.raises(ServiceConfigurationError, match="this environment"):
        service.validate_readiness()
    with pytest.raises(ServiceConfigurationError, match="not configured"):
        service._pseudonymizer()


def test_service_uses_explicit_key_and_collects_anthropic_summary(
    telemetry_runtime: TelemetryRuntime,
) -> None:
    settings = _settings(
        analytics_provider=ProviderName.ANTHROPIC,
        anthropic_analytics_api_key=SecretStr("synthetic-api-key"),
        pseudonymization_key=SecretStr("synthetic-pseudonym-key"),
    )
    source = anthropic_record_from_payload(anthropic_activity_payload())
    client = InMemoryClient(ProviderName.ANTHROPIC, (source,))
    received_settings: list[AppSettings] = []

    def factory(value: AppSettings) -> Any:
        received_settings.append(value)
        return client

    service = GatewayService(
        settings,
        telemetry_runtime,
        anthropic_client_factory=factory,
    )
    summary = asyncio.run(service.collect(REPORTING_DATE))

    assert summary.provider is ProviderName.ANTHROPIC
    assert summary.total_users == 1
    assert received_settings == [settings]


@pytest.mark.parametrize(
    ("failure", "expected_type"),
    [
        (ProviderTransportError("synthetic provider detail"), ProviderTransportError),
        (RuntimeError("synthetic local detail"), CollectionFailedError),
        (
            ServiceConfigurationError("synthetic config detail"),
            ServiceConfigurationError,
        ),
    ],
)
def test_collection_preserves_expected_errors_and_wraps_other_failures(
    telemetry_runtime: TelemetryRuntime,
    failure: Exception,
    expected_type: type[Exception],
) -> None:
    settings = _settings()
    client = InMemoryClient[MockUserActivityRecord](
        ProviderName.MOCK,
        exception=failure,
    )
    service = GatewayService(
        settings,
        telemetry_runtime,
        mock_client_factory=lambda: client,
    )

    with pytest.raises(expected_type) as error:
        asyncio.run(service.collect(REPORTING_DATE))

    if expected_type is CollectionFailedError:
        assert "synthetic local detail" not in str(error.value)


def test_preview_loading_handles_disabled_missing_invalid_and_os_errors(
    telemetry_runtime: TelemetryRuntime,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    disabled = GatewayService(_settings(), telemetry_runtime)
    with pytest.raises(ServiceConfigurationError, match="disabled"):
        disabled.read_preview()

    output_path = tmp_path / "usage-preview.json"
    enabled = GatewayService(
        _settings(preview_enabled=True, preview_output_path=output_path),
        telemetry_runtime,
    )
    with pytest.raises(PreviewNotFoundError, match="unavailable"):
        enabled.read_preview()

    output_path.write_text("not valid preview json", encoding="utf-8")
    with pytest.raises(PreviewReadError, match="invalid"):
        enabled.read_preview()

    def fail_read(_: Path) -> bytes:
        raise OSError("synthetic private path detail")

    monkeypatch.setattr(Path, "read_bytes", fail_read)
    with pytest.raises(PreviewReadError, match="could not be read") as error:
        enabled.read_preview()
    assert "synthetic private path detail" not in str(error.value)


def test_default_service_factory_returns_provider_selected_service(
    telemetry_runtime: TelemetryRuntime,
) -> None:
    service = create_gateway_service(_settings(), telemetry_runtime)

    assert isinstance(service, GatewayService)
    assert service.validate_readiness() is ProviderName.MOCK
