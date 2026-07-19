"""Tests for OpenTelemetry resource, exporters, and provider lifecycle."""

import asyncio
from io import StringIO
from typing import cast
from unittest.mock import Mock, create_autospec

import pytest
from fastapi.routing import APIRoute
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import ConsoleLogRecordExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import ConsoleSpanExporter
from pydantic import AnyHttpUrl, SecretStr

from genai_usage_observability_gateway.app import create_app
from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
)
from genai_usage_observability_gateway.telemetry import (
    SERVICE_NAME_VALUE,
    TELEMETRY_SOURCE,
    TELEMETRY_SOURCE_VALUE,
    TelemetryExportMode,
    TelemetryManager,
    TelemetryRuntime,
    build_resource,
    create_telemetry_runtime,
    parse_otlp_headers,
)


def test_resource_uses_current_conventions_and_marks_custom_source() -> None:
    resource = build_resource(
        AppSettings(
            app_environment=DeploymentEnvironment.STAGING,
            pseudonymization_key=SecretStr("synthetic-pseudonymization-key"),
        )
    )

    assert resource.attributes["service.name"] == SERVICE_NAME_VALUE
    assert resource.attributes["service.version"] == "0.1.0"
    assert resource.attributes["deployment.environment.name"] == "staging"
    assert "deployment.environment" not in resource.attributes
    assert resource.attributes[TELEMETRY_SOURCE] == TELEMETRY_SOURCE_VALUE


def test_parse_otlp_headers_supports_percent_encoding() -> None:
    assert parse_otlp_headers(None) == {}

    headers = parse_otlp_headers(
        "Authorization=Bearer%20synthetic-token,x-test=synthetic%2Cvalue"
    )

    assert headers == {
        "Authorization": "Bearer synthetic-token",
        "x-test": "synthetic,value",
    }


@pytest.mark.parametrize(
    "configured_headers",
    [
        "missing-separator",
        "invalid header=value",
        "x-test=",
        "x-test=one,X-Test=two",
        "x-test=value%0D%0Ainjected=true",
    ],
)
def test_parse_otlp_headers_rejects_unsafe_values_without_echoing_them(
    configured_headers: str,
) -> None:
    with pytest.raises(ValueError) as exc_info:
        parse_otlp_headers(configured_headers)

    assert configured_headers not in str(exc_info.value)


def test_development_defaults_to_console_export() -> None:
    runtime = create_telemetry_runtime(AppSettings())

    try:
        assert runtime.export_mode is TelemetryExportMode.CONSOLE
        assert runtime.tracer_provider.resource is runtime.resource
        assert runtime.logger_provider.resource is runtime.resource
    finally:
        runtime.shutdown()


def test_nonlocal_runtime_without_endpoint_has_no_exporter() -> None:
    runtime = create_telemetry_runtime(
        AppSettings(app_environment=DeploymentEnvironment.TEST)
    )

    try:
        assert runtime.export_mode is TelemetryExportMode.NONE
    finally:
        runtime.shutdown()


def test_otlp_http_uses_configured_base_endpoint_and_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: dict[str, tuple[str, dict[str, str]]] = {}
    output = StringIO()

    def span_exporter(*, endpoint: str, headers: dict[str, str]) -> ConsoleSpanExporter:
        calls["traces"] = (endpoint, headers)
        return ConsoleSpanExporter(out=output)

    def metric_exporter(
        *, endpoint: str, headers: dict[str, str]
    ) -> ConsoleMetricExporter:
        calls["metrics"] = (endpoint, headers)
        return ConsoleMetricExporter(out=output)

    def log_exporter(
        *, endpoint: str, headers: dict[str, str]
    ) -> ConsoleLogRecordExporter:
        calls["logs"] = (endpoint, headers)
        return ConsoleLogRecordExporter(out=output)

    monkeypatch.setattr(
        "genai_usage_observability_gateway.telemetry.OTLPSpanExporter",
        span_exporter,
    )
    monkeypatch.setattr(
        "genai_usage_observability_gateway.telemetry.OTLPMetricExporter",
        metric_exporter,
    )
    monkeypatch.setattr(
        "genai_usage_observability_gateway.telemetry.OTLPLogExporter",
        log_exporter,
    )
    runtime = create_telemetry_runtime(
        AppSettings(
            app_environment=DeploymentEnvironment.TEST,
            otel_exporter_otlp_endpoint=AnyHttpUrl(
                "https://collector.example.test/otel/"
            ),
            otel_exporter_otlp_headers=SecretStr("x-test=synthetic-value"),
        )
    )

    try:
        assert runtime.export_mode is TelemetryExportMode.OTLP_HTTP
        assert "synthetic-value" not in repr(runtime)
        assert calls == {
            "traces": (
                "https://collector.example.test/otel/v1/traces",
                {"x-test": "synthetic-value"},
            ),
            "metrics": (
                "https://collector.example.test/otel/v1/metrics",
                {"x-test": "synthetic-value"},
            ),
            "logs": (
                "https://collector.example.test/otel/v1/logs",
                {"x-test": "synthetic-value"},
            ),
        }
    finally:
        runtime.shutdown()


def test_runtime_flushes_and_shuts_down_each_provider_once() -> None:
    tracer_mock: Mock = create_autospec(TracerProvider, instance=True)
    meter_mock: Mock = create_autospec(MeterProvider, instance=True)
    logger_mock: Mock = create_autospec(LoggerProvider, instance=True)
    tracer_mock.force_flush.return_value = True
    meter_mock.force_flush.return_value = True
    logger_mock.force_flush.return_value = True
    runtime = TelemetryRuntime(
        resource=build_resource(AppSettings()),
        tracer_provider=cast(TracerProvider, tracer_mock),
        meter_provider=cast(MeterProvider, meter_mock),
        logger_provider=cast(LoggerProvider, logger_mock),
        export_mode=TelemetryExportMode.NONE,
    )

    assert runtime.force_flush()
    runtime.shutdown()
    runtime.shutdown()

    assert runtime.is_shutdown
    assert runtime.force_flush()
    assert tracer_mock.force_flush.call_count == 2
    assert meter_mock.force_flush.call_count == 2
    assert logger_mock.force_flush.call_count == 2
    tracer_mock.shutdown.assert_called_once_with()
    meter_mock.shutdown.assert_called_once_with()
    logger_mock.shutdown.assert_called_once_with()


def test_runtime_requires_deployment_environment_resource_attribute() -> None:
    with pytest.raises(ValueError, match="requires a deployment environment"):
        TelemetryRuntime(
            resource=Resource.create({}),
            tracer_provider=cast(
                TracerProvider, create_autospec(TracerProvider, instance=True)
            ),
            meter_provider=cast(
                MeterProvider, create_autospec(MeterProvider, instance=True)
            ),
            logger_provider=cast(
                LoggerProvider, create_autospec(LoggerProvider, instance=True)
            ),
            export_mode=TelemetryExportMode.NONE,
        )


def test_manager_initialization_is_idempotent_and_reference_counted() -> None:
    created: list[TelemetryRuntime] = []

    def runtime_factory(settings: AppSettings) -> TelemetryRuntime:
        runtime = create_telemetry_runtime(settings)
        created.append(runtime)
        return runtime

    manager = TelemetryManager(runtime_factory)
    settings = AppSettings(app_environment=DeploymentEnvironment.TEST)

    manager.shutdown()
    first = manager.initialize(settings)
    second = manager.initialize(settings)
    manager.shutdown()

    assert first is second
    assert first.organization_metrics is second.organization_metrics
    assert first.usage_events is second.usage_events
    assert first.lifecycle_events is second.lifecycle_events
    assert created == [first]
    assert manager.active_runtime is first
    assert not first.is_shutdown

    manager.shutdown()

    assert manager.active_runtime is None
    assert first.is_shutdown


def test_fastapi_lifespan_initializes_and_stops_telemetry() -> None:
    manager = TelemetryManager()
    settings = AppSettings(app_environment=DeploymentEnvironment.TEST)
    application = create_app(settings_factory=lambda: settings, manager=manager)

    assert manager.active_runtime is None
    assert {
        route.path for route in application.routes if isinstance(route, APIRoute)
    } == {
        "/",
        "/health",
        "/health/live",
        "/health/ready",
        "/collect",
        "/preview",
    }

    async def enter_lifespan() -> TelemetryRuntime:
        async with application.router.lifespan_context(application):
            active_runtime = manager.active_runtime
            assert active_runtime is not None
            state_runtime = cast(TelemetryRuntime, application.state.telemetry)
            assert state_runtime is active_runtime
            assert not active_runtime.is_shutdown
            return active_runtime

    runtime = asyncio.run(enter_lifespan())

    assert manager.active_runtime is None
    assert runtime.is_shutdown
