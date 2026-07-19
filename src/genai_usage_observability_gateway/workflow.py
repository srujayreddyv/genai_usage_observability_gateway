"""Traced in-memory collection workflow orchestration."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, date, datetime
from time import monotonic_ns

from opentelemetry.semconv.attributes.exception_attributes import (
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
)
from opentelemetry.trace import Status, StatusCode, Tracer

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.lifecycle_events import (
    CollectionClientType,
    CollectionLifecycleEvent,
    CollectionLifecycleEventName,
    CollectionLifecycleStatus,
)
from genai_usage_observability_gateway.normalization import (
    normalize_anthropic_records,
    normalize_mock_records,
)
from genai_usage_observability_gateway.preview import (
    AnthropicUsagePreview,
    DevelopmentPreviewWriter,
    MockUsagePreview,
    build_anthropic_usage_preview_from_collection,
    build_mock_usage_preview_from_collection,
)
from genai_usage_observability_gateway.privacy import (
    HmacSha256Pseudonymizer,
    protect_anthropic_collection,
    protect_mock_collection,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.providers.base import AnalyticsClient
from genai_usage_observability_gateway.providers.mock import MockUserActivityRecord
from genai_usage_observability_gateway.telemetry import TelemetryRuntime
from genai_usage_observability_gateway.telemetry_attributes import (
    CLIENT_TYPE_ATTRIBUTE,
    COLLECTION_STATUS_ATTRIBUTE,
    PROVIDER_ATTRIBUTE,
    RECORD_COUNT_ATTRIBUTE,
    REPORTING_DATE_ATTRIBUTE,
)

COLLECTION_SPAN_NAME = "genai.usage.collection"
COLLECTION_TRACER_NAME = "genai_usage_observability_gateway.collection_workflow"
COLLECTION_STATUS_STARTED = "started"
COLLECTION_STATUS_SUCCESS = "success"
COLLECTION_STATUS_FAILED = "failed"
_SAFE_EXCEPTION_ATTRIBUTES = {
    EXCEPTION_TYPE: "collection_workflow_error",
    EXCEPTION_MESSAGE: "collection workflow failed",
    EXCEPTION_STACKTRACE: "suppressed by privacy policy",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


class AnthropicCollectionWorkflow:
    """Run the complete Anthropic collection path inside one safe span."""

    def __init__(
        self,
        *,
        client: AnalyticsClient[AnthropicUserActivityRecord],
        client_type: CollectionClientType,
        pseudonymizer: HmacSha256Pseudonymizer,
        telemetry: TelemetryRuntime,
        clock_ns: Callable[[], int] = monotonic_ns,
        utc_now: Callable[[], datetime] = _utc_now,
        preview_writer: DevelopmentPreviewWriter | None = None,
    ) -> None:
        self._client = client
        self._client_type = client_type
        self._pseudonymizer = pseudonymizer
        self._telemetry = telemetry
        self._clock_ns = clock_ns
        self._utc_now = utc_now
        self._preview_writer = preview_writer
        self._tracer: Tracer = telemetry.tracer_provider.get_tracer(
            COLLECTION_TRACER_NAME,
            __version__,
        )

    async def collect(self, reporting_date: date) -> AnthropicUsagePreview:
        """Collect, protect, emit, and preview one UTC reporting date."""

        started_ns = self._clock_ns()
        record_count: int | None = None
        attributes = {
            PROVIDER_ATTRIBUTE: ProviderName.ANTHROPIC.value,
            CLIENT_TYPE_ATTRIBUTE: self._client_type.value,
            REPORTING_DATE_ATTRIBUTE: reporting_date.isoformat(),
            COLLECTION_STATUS_ATTRIBUTE: COLLECTION_STATUS_STARTED,
        }
        with self._tracer.start_as_current_span(
            COLLECTION_SPAN_NAME,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                self._emit_lifecycle(
                    CollectionLifecycleEventName.STARTED,
                    CollectionLifecycleStatus.STARTED,
                    reporting_date,
                    duration_ms=0,
                )
                collection_timestamp = self._utc_now()
                if self._client.provider is not ProviderName.ANTHROPIC:
                    raise ValueError(
                        "Anthropic collection requires an Anthropic client"
                    )
                provider_records = await self._client.get_usage_analytics(
                    reporting_date
                )
                normalized_records = normalize_anthropic_records(provider_records)
                record_count = len(normalized_records)
                self._emit_lifecycle(
                    CollectionLifecycleEventName.RECORDS_MAPPED,
                    CollectionLifecycleStatus.IN_PROGRESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                collection = protect_anthropic_collection(
                    normalized_records,
                    self._pseudonymizer,
                )
                self._emit_lifecycle(
                    CollectionLifecycleEventName.AGGREGATION_COMPLETED,
                    CollectionLifecycleStatus.IN_PROGRESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                self._telemetry.organization_metrics.emit(
                    collection.organization_summary
                )
                self._telemetry.usage_events.emit_collection(collection)
                preview = build_anthropic_usage_preview_from_collection(
                    collection,
                    collection_timestamp=collection_timestamp,
                )
                if self._preview_writer is not None:
                    self._preview_writer.write(preview)
                self._emit_lifecycle(
                    CollectionLifecycleEventName.PREVIEW_WRITTEN,
                    CollectionLifecycleStatus.IN_PROGRESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                self._emit_lifecycle(
                    CollectionLifecycleEventName.COMPLETED,
                    CollectionLifecycleStatus.SUCCESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
            except Exception as exception:
                self._emit_lifecycle(
                    CollectionLifecycleEventName.FAILED,
                    CollectionLifecycleStatus.FAILED,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                span.set_attribute(
                    COLLECTION_STATUS_ATTRIBUTE,
                    COLLECTION_STATUS_FAILED,
                )
                span.record_exception(
                    exception,
                    attributes=_SAFE_EXCEPTION_ATTRIBUTES,
                    escaped=True,
                )
                span.set_status(Status(StatusCode.ERROR))
                raise

            span.set_attribute(RECORD_COUNT_ATTRIBUTE, record_count)
            span.set_attribute(
                COLLECTION_STATUS_ATTRIBUTE,
                COLLECTION_STATUS_SUCCESS,
            )
            return preview

    def _elapsed_ms(self, started_ns: int) -> int:
        """Return nonnegative elapsed monotonic time in whole milliseconds."""

        return max(0, (self._clock_ns() - started_ns) // 1_000_000)

    def _emit_lifecycle(
        self,
        event_name: CollectionLifecycleEventName,
        status: CollectionLifecycleStatus,
        reporting_date: date,
        *,
        duration_ms: int,
        record_count: int | None = None,
    ) -> None:
        """Build and emit one strict lifecycle event inside the active span."""

        self._telemetry.lifecycle_events.emit(
            CollectionLifecycleEvent(
                event_name=event_name,
                reporting_date=reporting_date,
                provider=ProviderName.ANTHROPIC,
                client_type=self._client_type,
                collection_status=status,
                duration_ms=duration_ms,
                record_count=record_count,
            )
        )


class MockCollectionWorkflow:
    """Run the complete synthetic collection path inside one safe span."""

    def __init__(
        self,
        *,
        client: AnalyticsClient[MockUserActivityRecord],
        pseudonymizer: HmacSha256Pseudonymizer,
        telemetry: TelemetryRuntime,
        clock_ns: Callable[[], int] = monotonic_ns,
        utc_now: Callable[[], datetime] = _utc_now,
        preview_writer: DevelopmentPreviewWriter | None = None,
    ) -> None:
        self._client = client
        self._pseudonymizer = pseudonymizer
        self._telemetry = telemetry
        self._clock_ns = clock_ns
        self._utc_now = utc_now
        self._preview_writer = preview_writer
        self._tracer: Tracer = telemetry.tracer_provider.get_tracer(
            COLLECTION_TRACER_NAME,
            __version__,
        )

    async def collect(self, reporting_date: date) -> MockUsagePreview:
        """Collect, protect, emit, and preview one synthetic reporting date."""

        started_ns = self._clock_ns()
        record_count: int | None = None
        attributes = {
            PROVIDER_ATTRIBUTE: ProviderName.MOCK.value,
            CLIENT_TYPE_ATTRIBUTE: CollectionClientType.IN_MEMORY.value,
            REPORTING_DATE_ATTRIBUTE: reporting_date.isoformat(),
            COLLECTION_STATUS_ATTRIBUTE: COLLECTION_STATUS_STARTED,
        }
        with self._tracer.start_as_current_span(
            COLLECTION_SPAN_NAME,
            attributes=attributes,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            try:
                self._emit_lifecycle(
                    CollectionLifecycleEventName.STARTED,
                    CollectionLifecycleStatus.STARTED,
                    reporting_date,
                    duration_ms=0,
                )
                collection_timestamp = self._utc_now()
                if self._client.provider is not ProviderName.MOCK:
                    raise ValueError("mock collection requires a mock client")
                provider_records = await self._client.get_usage_analytics(
                    reporting_date
                )
                normalized_records = normalize_mock_records(provider_records)
                record_count = len(normalized_records)
                self._emit_lifecycle(
                    CollectionLifecycleEventName.RECORDS_MAPPED,
                    CollectionLifecycleStatus.IN_PROGRESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                collection = protect_mock_collection(
                    normalized_records,
                    self._pseudonymizer,
                )
                self._emit_lifecycle(
                    CollectionLifecycleEventName.AGGREGATION_COMPLETED,
                    CollectionLifecycleStatus.IN_PROGRESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                self._telemetry.organization_metrics.emit(
                    collection.organization_summary
                )
                self._telemetry.usage_events.emit_collection(collection)
                preview = build_mock_usage_preview_from_collection(
                    collection,
                    collection_timestamp=collection_timestamp,
                )
                if self._preview_writer is not None:
                    self._preview_writer.write(preview)
                self._emit_lifecycle(
                    CollectionLifecycleEventName.PREVIEW_WRITTEN,
                    CollectionLifecycleStatus.IN_PROGRESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                self._emit_lifecycle(
                    CollectionLifecycleEventName.COMPLETED,
                    CollectionLifecycleStatus.SUCCESS,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
            except Exception as exception:
                self._emit_lifecycle(
                    CollectionLifecycleEventName.FAILED,
                    CollectionLifecycleStatus.FAILED,
                    reporting_date,
                    duration_ms=self._elapsed_ms(started_ns),
                    record_count=record_count,
                )
                span.set_attribute(
                    COLLECTION_STATUS_ATTRIBUTE,
                    COLLECTION_STATUS_FAILED,
                )
                span.record_exception(
                    exception,
                    attributes=_SAFE_EXCEPTION_ATTRIBUTES,
                    escaped=True,
                )
                span.set_status(Status(StatusCode.ERROR))
                raise

            span.set_attribute(RECORD_COUNT_ATTRIBUTE, record_count)
            span.set_attribute(
                COLLECTION_STATUS_ATTRIBUTE,
                COLLECTION_STATUS_SUCCESS,
            )
            return preview

    def _elapsed_ms(self, started_ns: int) -> int:
        return max(0, (self._clock_ns() - started_ns) // 1_000_000)

    def _emit_lifecycle(
        self,
        event_name: CollectionLifecycleEventName,
        status: CollectionLifecycleStatus,
        reporting_date: date,
        *,
        duration_ms: int,
        record_count: int | None = None,
    ) -> None:
        self._telemetry.lifecycle_events.emit(
            CollectionLifecycleEvent(
                event_name=event_name,
                reporting_date=reporting_date,
                provider=ProviderName.MOCK,
                client_type=CollectionClientType.IN_MEMORY,
                collection_status=status,
                duration_ms=duration_ms,
                record_count=record_count,
            )
        )
