"""Traced in-memory collection workflow orchestration."""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from opentelemetry.semconv.attributes.exception_attributes import (
    EXCEPTION_MESSAGE,
    EXCEPTION_STACKTRACE,
    EXCEPTION_TYPE,
)
from opentelemetry.trace import Status, StatusCode, Tracer

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.normalization import (
    normalize_anthropic_records,
)
from genai_usage_observability_gateway.preview import (
    AnthropicUsagePreview,
    build_anthropic_usage_preview_from_collection,
)
from genai_usage_observability_gateway.privacy import (
    HmacSha256Pseudonymizer,
    protect_anthropic_collection,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.providers.base import AnalyticsClient
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


class CollectionClientType(StrEnum):
    """Bounded client implementations safe for trace attributes."""

    ANTHROPIC_API = "anthropic_api"
    IN_MEMORY = "in_memory"


class AnthropicCollectionWorkflow:
    """Run the complete Anthropic collection path inside one safe span."""

    def __init__(
        self,
        *,
        client: AnalyticsClient[AnthropicUserActivityRecord],
        client_type: CollectionClientType,
        pseudonymizer: HmacSha256Pseudonymizer,
        telemetry: TelemetryRuntime,
    ) -> None:
        self._client = client
        self._client_type = client_type
        self._pseudonymizer = pseudonymizer
        self._telemetry = telemetry
        self._tracer: Tracer = telemetry.tracer_provider.get_tracer(
            COLLECTION_TRACER_NAME,
            __version__,
        )

    async def collect(self, reporting_date: date) -> AnthropicUsagePreview:
        """Collect, protect, emit, and preview one UTC reporting date."""

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
                if self._client.provider is not ProviderName.ANTHROPIC:
                    raise ValueError(
                        "Anthropic collection requires an Anthropic client"
                    )
                provider_records = await self._client.get_usage_analytics(
                    reporting_date
                )
                normalized_records = normalize_anthropic_records(provider_records)
                collection = protect_anthropic_collection(
                    normalized_records,
                    self._pseudonymizer,
                )
                self._telemetry.organization_metrics.emit(
                    collection.organization_summary
                )
                self._telemetry.usage_events.emit_collection(collection)
                preview = build_anthropic_usage_preview_from_collection(collection)
            except Exception as exception:
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

            span.set_attribute(RECORD_COUNT_ATTRIBUTE, len(normalized_records))
            span.set_attribute(
                COLLECTION_STATUS_ATTRIBUTE,
                COLLECTION_STATUS_SUCCESS,
            )
            return preview
