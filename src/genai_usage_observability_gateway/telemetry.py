"""OpenTelemetry provider lifecycle, exporters, and application emitters."""

from __future__ import annotations

import re
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from threading import RLock
from urllib.parse import unquote

from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogRecordExporter,
    LogRecordExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    ConsoleMetricExporter,
    MetricExporter,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
    SpanExporter,
)
from opentelemetry.semconv.attributes.deployment_attributes import (
    DEPLOYMENT_ENVIRONMENT_NAME,
)
from opentelemetry.semconv.attributes.service_attributes import (
    SERVICE_NAME,
    SERVICE_VERSION,
)

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
)
from genai_usage_observability_gateway.lifecycle_events import (
    CollectionLifecycleEmitter,
)
from genai_usage_observability_gateway.organization_metrics import (
    OrganizationMetricEmitter,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    TELEMETRY_SOURCE as TELEMETRY_SOURCE,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    TELEMETRY_SOURCE_VALUE as TELEMETRY_SOURCE_VALUE,
)
from genai_usage_observability_gateway.usage_events import UsageEventEmitter

SERVICE_NAME_VALUE = "genai-usage-observability-gateway"

_HEADER_NAME_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")


class TelemetryExportMode(StrEnum):
    """Configured telemetry destination."""

    CONSOLE = "console"
    OTLP_HTTP = "otlp_http"
    NONE = "none"


def build_resource(settings: AppSettings) -> Resource:
    """Create the resource shared by the trace, metric, and log providers."""

    return Resource.create(
        {
            SERVICE_NAME: SERVICE_NAME_VALUE,
            SERVICE_VERSION: __version__,
            DEPLOYMENT_ENVIRONMENT_NAME: settings.app_environment.value,
            TELEMETRY_SOURCE: TELEMETRY_SOURCE_VALUE,
        }
    )


def parse_otlp_headers(configured_headers: str | None) -> Mapping[str, str]:
    """Parse percent-encoded ``key=value`` OTLP headers without exposing values."""

    if configured_headers is None:
        return {}

    headers: dict[str, str] = {}
    for item in configured_headers.split(","):
        raw_name, separator, raw_value = item.partition("=")
        name = unquote(raw_name).strip()
        value = unquote(raw_value).strip()
        if (
            not separator
            or not _HEADER_NAME_PATTERN.fullmatch(name)
            or not value
            or "\r" in value
            or "\n" in value
            or name.casefold() in {existing.casefold() for existing in headers}
        ):
            raise ValueError("OTLP headers must be unique, valid key=value pairs")
        headers[name] = value

    return headers


def _signal_endpoint(base_endpoint: str, signal: str) -> str:
    """Build the standard OTLP/HTTP per-signal path from a configured base URL."""

    return f"{base_endpoint.rstrip('/')}/v1/{signal}"


@dataclass(slots=True)
class TelemetryRuntime:
    """One shareable set of SDK providers and its coordinated lifecycle."""

    resource: Resource
    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider
    export_mode: TelemetryExportMode
    organization_metrics: OrganizationMetricEmitter = field(init=False)
    usage_events: UsageEventEmitter = field(init=False)
    lifecycle_events: CollectionLifecycleEmitter = field(init=False)
    _shutdown: bool = field(default=False, init=False, repr=False)
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        """Create organization instruments once for this provider runtime."""

        environment = self.resource.attributes.get(DEPLOYMENT_ENVIRONMENT_NAME)
        if not isinstance(environment, str):
            raise ValueError("telemetry resource requires a deployment environment")
        deployment_environment = DeploymentEnvironment(environment)
        self.organization_metrics = OrganizationMetricEmitter(
            self.meter_provider,
            deployment_environment,
        )
        self.usage_events = UsageEventEmitter(
            self.logger_provider,
            local_stream=(
                sys.stdout
                if deployment_environment is DeploymentEnvironment.DEVELOPMENT
                else None
            ),
        )
        self.lifecycle_events = CollectionLifecycleEmitter(
            self.logger_provider,
            local_stream=(
                sys.stdout
                if deployment_environment is DeploymentEnvironment.DEVELOPMENT
                else None
            ),
        )

    @property
    def is_shutdown(self) -> bool:
        """Return whether provider shutdown has completed."""

        with self._lock:
            return self._shutdown

    def force_flush(self) -> bool:
        """Force all three signal providers to flush pending telemetry."""

        with self._lock:
            if self._shutdown:
                return True
            results = (
                self.logger_provider.force_flush(),
                self.meter_provider.force_flush(),
                self.tracer_provider.force_flush(),
            )
            return all(results)

    def shutdown(self) -> None:
        """Flush and shut down all providers exactly once."""

        with self._lock:
            if self._shutdown:
                return
            try:
                self.force_flush()
            finally:
                try:
                    self.logger_provider.shutdown()
                finally:
                    try:
                        self.meter_provider.shutdown()
                    finally:
                        self.tracer_provider.shutdown()
                        self._shutdown = True


def create_telemetry_runtime(settings: AppSettings) -> TelemetryRuntime:
    """Build providers and exporters for the configured runtime environment."""

    resource = build_resource(settings)
    tracer_provider = TracerProvider(resource=resource, shutdown_on_exit=False)
    logger_provider = LoggerProvider(resource=resource, shutdown_on_exit=False)
    span_exporter: SpanExporter
    metric_exporter: MetricExporter
    log_exporter: LogRecordExporter

    if settings.otel_exporter_otlp_endpoint is not None:
        mode = TelemetryExportMode.OTLP_HTTP
        endpoint = str(settings.otel_exporter_otlp_endpoint)
        configured_headers = settings.otel_exporter_otlp_headers
        headers = parse_otlp_headers(
            configured_headers.get_secret_value()
            if configured_headers is not None
            else None
        )
        span_exporter = OTLPSpanExporter(
            endpoint=_signal_endpoint(endpoint, "traces"), headers=dict(headers)
        )
        metric_exporter = OTLPMetricExporter(
            endpoint=_signal_endpoint(endpoint, "metrics"), headers=dict(headers)
        )
        log_exporter = OTLPLogExporter(
            endpoint=_signal_endpoint(endpoint, "logs"), headers=dict(headers)
        )
    elif settings.app_environment is DeploymentEnvironment.DEVELOPMENT:
        mode = TelemetryExportMode.CONSOLE
        span_exporter = ConsoleSpanExporter()
        metric_exporter = ConsoleMetricExporter()
        log_exporter = ConsoleLogRecordExporter()
    else:
        mode = TelemetryExportMode.NONE
        meter_provider = MeterProvider(resource=resource, shutdown_on_exit=False)
        return TelemetryRuntime(
            resource=resource,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
            logger_provider=logger_provider,
            export_mode=mode,
        )

    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
        shutdown_on_exit=False,
    )
    return TelemetryRuntime(
        resource=resource,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        export_mode=mode,
    )


RuntimeFactory = Callable[[AppSettings], TelemetryRuntime]


class TelemetryManager:
    """Lease one process-local telemetry runtime across lifespan entries."""

    def __init__(
        self, runtime_factory: RuntimeFactory = create_telemetry_runtime
    ) -> None:
        self._runtime_factory = runtime_factory
        self._runtime: TelemetryRuntime | None = None
        self._leases = 0
        self._lock = RLock()

    @property
    def active_runtime(self) -> TelemetryRuntime | None:
        """Return the current runtime for observability and testing."""

        with self._lock:
            return self._runtime

    def initialize(self, settings: AppSettings) -> TelemetryRuntime:
        """Initialize once, then return the existing runtime on repeated calls."""

        with self._lock:
            if self._runtime is None:
                self._runtime = self._runtime_factory(settings)
            self._leases += 1
            return self._runtime

    def shutdown(self) -> None:
        """Release a lifespan lease and stop providers after the final release."""

        with self._lock:
            if self._runtime is None:
                return
            self._leases = max(0, self._leases - 1)
            if self._leases:
                return
            runtime = self._runtime
            self._runtime = None
        runtime.shutdown()


telemetry_manager = TelemetryManager()
