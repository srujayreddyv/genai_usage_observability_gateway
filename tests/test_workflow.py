"""Tests for successful and failed collection workflow spans."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import date
from time import monotonic_ns

import pytest
from opentelemetry import trace
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs._internal import ReadableLogRecord
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.trace import StatusCode
from pydantic import SecretStr

from genai_usage_observability_gateway.aggregation import EmptyAggregationError
from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
    ProviderName,
)
from genai_usage_observability_gateway.lifecycle_events import (
    COLLECTION_LIFECYCLE_LOGGER_NAME,
    CollectionClientType,
    CollectionLifecycleEventName,
    CollectionLifecycleStatus,
)
from genai_usage_observability_gateway.preview import render_usage_preview
from genai_usage_observability_gateway.privacy import HmacSha256Pseudonymizer
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.telemetry import (
    TelemetryExportMode,
    TelemetryRuntime,
    build_resource,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    CLIENT_TYPE_ATTRIBUTE,
    COLLECTION_DURATION_MS_ATTRIBUTE,
    COLLECTION_LIFECYCLE_ATTRIBUTE_KEYS,
    COLLECTION_STATUS_ATTRIBUTE,
    COLLECTION_TRACE_ATTRIBUTE_KEYS,
    PROVIDER_ATTRIBUTE,
    RECORD_COUNT_ATTRIBUTE,
    REPORTING_DATE_ATTRIBUTE,
)
from genai_usage_observability_gateway.usage_events import USAGE_EVENT_LOGGER_NAME
from genai_usage_observability_gateway.workflow import (
    COLLECTION_SPAN_NAME,
    COLLECTION_STATUS_FAILED,
    COLLECTION_STATUS_SUCCESS,
    COLLECTION_TRACER_NAME,
    AnthropicCollectionWorkflow,
)
from tests.factories import (
    anthropic_activity_payload,
    anthropic_record_from_payload,
)

REPORTING_DATE = date(2026, 2, 3)
SYNTHETIC_KEY = "synthetic-workflow-pseudonymization-key"


class SyntheticCollectionError(RuntimeError):
    """Synthetic provider failure used to test trace behavior."""


class InMemoryAnthropicClient:
    """Small validated client double with observable call behavior."""

    def __init__(
        self,
        records: tuple[AnthropicUserActivityRecord, ...] = (),
        *,
        provider: ProviderName = ProviderName.ANTHROPIC,
        exception: Exception | None = None,
    ) -> None:
        self._records = records
        self._provider = provider
        self._exception = exception
        self.requested_dates: list[date] = []
        self.provider_call_had_active_span = False

    @property
    def provider(self) -> ProviderName:
        return self._provider

    async def get_usage_analytics(
        self, reporting_date: date
    ) -> tuple[AnthropicUserActivityRecord, ...]:
        self.requested_dates.append(reporting_date)
        self.provider_call_had_active_span = (
            trace.get_current_span().get_span_context().is_valid
        )
        if self._exception is not None:
            raise self._exception
        return self._records


@dataclass(frozen=True)
class TelemetryHarness:
    runtime: TelemetryRuntime
    span_exporter: InMemorySpanExporter
    metric_reader: InMemoryMetricReader
    log_exporter: InMemoryLogRecordExporter


@pytest.fixture
def telemetry_harness() -> Iterator[TelemetryHarness]:
    settings = AppSettings(app_environment=DeploymentEnvironment.TEST)
    resource = build_resource(settings)
    span_exporter = InMemorySpanExporter()
    tracer_provider = TracerProvider(resource=resource, shutdown_on_exit=False)
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[metric_reader],
        shutdown_on_exit=False,
    )
    log_exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    logger_provider = LoggerProvider(resource=resource, shutdown_on_exit=False)
    logger_provider.add_log_record_processor(SimpleLogRecordProcessor(log_exporter))
    runtime = TelemetryRuntime(
        resource=resource,
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
        export_mode=TelemetryExportMode.NONE,
    )
    try:
        yield TelemetryHarness(
            runtime=runtime,
            span_exporter=span_exporter,
            metric_reader=metric_reader,
            log_exporter=log_exporter,
        )
    finally:
        runtime.shutdown()


def _raw_records() -> tuple[AnthropicUserActivityRecord, ...]:
    payloads = [anthropic_activity_payload(user_number) for user_number in (1, 2)]
    payloads[0]["rbac_group_id"] = "synthetic-private-group-id"
    payloads[0]["rbac_group_name"] = "Synthetic Private Group"
    return tuple(anthropic_record_from_payload(payload) for payload in payloads)


def _workflow(
    client: InMemoryAnthropicClient,
    telemetry: TelemetryRuntime,
    *,
    clock_ns: Callable[[], int] = monotonic_ns,
) -> AnthropicCollectionWorkflow:
    return AnthropicCollectionWorkflow(
        client=client,
        client_type=CollectionClientType.IN_MEMORY,
        pseudonymizer=HmacSha256Pseudonymizer(SecretStr(SYNTHETIC_KEY)),
        telemetry=telemetry,
        clock_ns=clock_ns,
    )


def _metric_count(reader: InMemoryMetricReader) -> int:
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    return sum(
        len(scope_metrics.metrics)
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
    )


def _logs_for_scope(
    exporter: InMemoryLogRecordExporter,
    scope_name: str,
) -> tuple[ReadableLogRecord, ...]:
    return tuple(
        readable
        for readable in exporter.get_finished_logs()
        if readable.instrumentation_scope is not None
        and readable.instrumentation_scope.name == scope_name
    )


def test_successful_workflow_has_one_safe_span_and_complete_outputs(
    telemetry_harness: TelemetryHarness,
) -> None:
    client = InMemoryAnthropicClient(_raw_records())
    clock_values = iter(
        (
            10_000_000_000,
            10_002_000_000,
            10_005_000_000,
            10_009_000_000,
            10_015_000_000,
        )
    )
    preview = asyncio.run(
        _workflow(
            client,
            telemetry_harness.runtime,
            clock_ns=lambda: next(clock_values),
        ).collect(REPORTING_DATE)
    )

    spans = telemetry_harness.span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.name == COLLECTION_SPAN_NAME
    assert span.instrumentation_scope is not None
    assert span.instrumentation_scope.name == COLLECTION_TRACER_NAME
    assert span.status.status_code is StatusCode.UNSET
    assert span.events == ()
    assert span.attributes == {
        PROVIDER_ATTRIBUTE: "anthropic",
        CLIENT_TYPE_ATTRIBUTE: "in_memory",
        REPORTING_DATE_ATTRIBUTE: "2026-02-03",
        COLLECTION_STATUS_ATTRIBUTE: COLLECTION_STATUS_SUCCESS,
        RECORD_COUNT_ATTRIBUTE: 2,
    }
    assert set(span.attributes) == COLLECTION_TRACE_ATTRIBUTE_KEYS
    assert client.requested_dates == [REPORTING_DATE]
    assert client.provider_call_had_active_span
    assert preview.metadata.record_count == 2
    assert _metric_count(telemetry_harness.metric_reader) == 42

    usage_logs = _logs_for_scope(
        telemetry_harness.log_exporter,
        USAGE_EVENT_LOGGER_NAME,
    )
    assert len(usage_logs) == 2
    for readable in usage_logs:
        assert readable.log_record.trace_id == span.context.trace_id
        assert readable.log_record.span_id == span.context.span_id

    lifecycle_logs = _logs_for_scope(
        telemetry_harness.log_exporter,
        COLLECTION_LIFECYCLE_LOGGER_NAME,
    )
    assert [readable.log_record.event_name for readable in lifecycle_logs] == [
        CollectionLifecycleEventName.STARTED.value,
        CollectionLifecycleEventName.RECORDS_MAPPED.value,
        CollectionLifecycleEventName.AGGREGATION_COMPLETED.value,
        CollectionLifecycleEventName.PREVIEW_WRITTEN.value,
        CollectionLifecycleEventName.COMPLETED.value,
    ]
    lifecycle_attributes = []
    for readable in lifecycle_logs:
        attributes = readable.log_record.attributes
        assert attributes is not None
        lifecycle_attributes.append(attributes)
    assert [
        attributes[COLLECTION_DURATION_MS_ATTRIBUTE]
        for attributes in lifecycle_attributes
    ] == [0, 2, 5, 9, 15]
    assert [
        attributes[COLLECTION_STATUS_ATTRIBUTE] for attributes in lifecycle_attributes
    ] == [
        CollectionLifecycleStatus.STARTED.value,
        CollectionLifecycleStatus.IN_PROGRESS.value,
        CollectionLifecycleStatus.IN_PROGRESS.value,
        CollectionLifecycleStatus.IN_PROGRESS.value,
        CollectionLifecycleStatus.SUCCESS.value,
    ]
    for index, readable in enumerate(lifecycle_logs):
        log_record = readable.log_record
        assert log_record.body is None
        assert log_record.trace_id == span.context.trace_id
        assert log_record.span_id == span.context.span_id
        assert log_record.attributes is not None
        expected_keys = COLLECTION_LIFECYCLE_ATTRIBUTE_KEYS
        if index == 0:
            expected_keys = expected_keys - {RECORD_COUNT_ATTRIBUTE}
        assert set(log_record.attributes) == expected_keys
        if index > 0:
            assert log_record.attributes[RECORD_COUNT_ATTRIBUTE] == 2


def test_success_span_attributes_and_preview_exclude_sensitive_data(
    telemetry_harness: TelemetryHarness,
) -> None:
    raw_records = _raw_records()
    preview = asyncio.run(
        _workflow(
            InMemoryAnthropicClient(raw_records), telemetry_harness.runtime
        ).collect(REPORTING_DATE)
    )
    span = telemetry_harness.span_exporter.get_finished_spans()[0]
    serialized_attributes = repr(dict(span.attributes or {}))
    serialized_preview = render_usage_preview(preview)
    serialized_lifecycle = repr(
        [
            readable.log_record.attributes
            for readable in _logs_for_scope(
                telemetry_harness.log_exporter,
                COLLECTION_LIFECYCLE_LOGGER_NAME,
            )
        ]
    )

    for raw_record in raw_records:
        raw_identity = raw_record.activity.user
        assert raw_identity.id not in serialized_attributes
        assert str(raw_identity.email_address) not in serialized_attributes
        assert raw_identity.id not in serialized_preview
        assert str(raw_identity.email_address) not in serialized_preview
        assert raw_identity.id not in serialized_lifecycle
        assert str(raw_identity.email_address) not in serialized_lifecycle
    for protected in preview.usage_records:
        assert protected.pseudonymous_user_id not in serialized_attributes
    for forbidden in (
        SYNTHETIC_KEY,
        "synthetic-private-group-id",
        "Synthetic Private Group",
        "credential",
        "authorization",
        "file.path",
        "api.endpoint",
    ):
        assert forbidden not in serialized_attributes
        assert forbidden not in serialized_lifecycle


def test_failed_workflow_records_exception_and_reraises_same_instance(
    telemetry_harness: TelemetryHarness,
) -> None:
    failure = SyntheticCollectionError("synthetic upstream failure detail")
    client = InMemoryAnthropicClient(exception=failure)
    clock_values = iter((20_000_000_000, 20_007_000_000))

    with pytest.raises(SyntheticCollectionError) as exc_info:
        asyncio.run(
            _workflow(
                client,
                telemetry_harness.runtime,
                clock_ns=lambda: next(clock_values),
            ).collect(REPORTING_DATE)
        )

    assert exc_info.value is failure
    spans = telemetry_harness.span_exporter.get_finished_spans()
    assert len(spans) == 1
    span = spans[0]
    assert span.status.status_code is StatusCode.ERROR
    assert span.status.description is None
    assert span.attributes == {
        PROVIDER_ATTRIBUTE: "anthropic",
        CLIENT_TYPE_ATTRIBUTE: "in_memory",
        REPORTING_DATE_ATTRIBUTE: "2026-02-03",
        COLLECTION_STATUS_ATTRIBUTE: COLLECTION_STATUS_FAILED,
    }
    assert RECORD_COUNT_ATTRIBUTE not in (span.attributes or {})
    assert "synthetic upstream failure detail" not in repr(span.attributes)
    assert len(span.events) == 1
    exception_event = span.events[0]
    assert exception_event.name == "exception"
    assert exception_event.attributes is not None
    assert exception_event.attributes == {
        "exception.type": "collection_workflow_error",
        "exception.message": "collection workflow failed",
        "exception.stacktrace": "suppressed by privacy policy",
        "exception.escaped": "True",
    }
    assert str(failure) not in repr(exception_event.attributes)
    assert (
        _logs_for_scope(
            telemetry_harness.log_exporter,
            USAGE_EVENT_LOGGER_NAME,
        )
        == ()
    )
    lifecycle_logs = _logs_for_scope(
        telemetry_harness.log_exporter,
        COLLECTION_LIFECYCLE_LOGGER_NAME,
    )
    assert [readable.log_record.event_name for readable in lifecycle_logs] == [
        CollectionLifecycleEventName.STARTED.value,
        CollectionLifecycleEventName.FAILED.value,
    ]
    failed_log = lifecycle_logs[-1].log_record
    assert failed_log.severity_number is SeverityNumber.ERROR
    assert failed_log.body is None
    assert failed_log.attributes == {
        REPORTING_DATE_ATTRIBUTE: "2026-02-03",
        PROVIDER_ATTRIBUTE: "anthropic",
        CLIENT_TYPE_ATTRIBUTE: "in_memory",
        COLLECTION_STATUS_ATTRIBUTE: CollectionLifecycleStatus.FAILED.value,
        COLLECTION_DURATION_MS_ATTRIBUTE: 7,
    }
    assert str(failure) not in repr(failed_log.attributes)


def test_mismatched_provider_fails_inside_the_collection_span(
    telemetry_harness: TelemetryHarness,
) -> None:
    client = InMemoryAnthropicClient(provider=ProviderName.MOCK)

    with pytest.raises(ValueError, match="requires an Anthropic client"):
        asyncio.run(
            _workflow(client, telemetry_harness.runtime).collect(REPORTING_DATE)
        )

    spans = telemetry_harness.span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].status.status_code is StatusCode.ERROR
    assert spans[0].attributes is not None
    assert spans[0].attributes[COLLECTION_STATUS_ATTRIBUTE] == COLLECTION_STATUS_FAILED
    assert client.requested_dates == []


def test_failed_lifecycle_includes_record_count_when_mapping_completed(
    telemetry_harness: TelemetryHarness,
) -> None:
    clock_values = iter((30_000_000_000, 30_003_000_000, 30_008_000_000))

    with pytest.raises(
        EmptyAggregationError,
        match="organization aggregation requires records",
    ):
        asyncio.run(
            _workflow(
                InMemoryAnthropicClient(),
                telemetry_harness.runtime,
                clock_ns=lambda: next(clock_values),
            ).collect(REPORTING_DATE)
        )

    lifecycle_logs = _logs_for_scope(
        telemetry_harness.log_exporter,
        COLLECTION_LIFECYCLE_LOGGER_NAME,
    )
    assert [readable.log_record.event_name for readable in lifecycle_logs] == [
        CollectionLifecycleEventName.STARTED.value,
        CollectionLifecycleEventName.RECORDS_MAPPED.value,
        CollectionLifecycleEventName.FAILED.value,
    ]
    failed_attributes = lifecycle_logs[-1].log_record.attributes
    assert failed_attributes is not None
    assert failed_attributes[COLLECTION_STATUS_ATTRIBUTE] == (
        CollectionLifecycleStatus.FAILED.value
    )
    assert failed_attributes[COLLECTION_DURATION_MS_ATTRIBUTE] == 8
    assert failed_attributes[RECORD_COUNT_ATTRIBUTE] == 0
