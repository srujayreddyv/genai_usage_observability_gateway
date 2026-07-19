"""Tests for structured privacy-safe collection lifecycle events."""

import json
from datetime import date
from io import StringIO
from typing import Any, cast

import pytest
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from pydantic import ValidationError

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.lifecycle_events import (
    COLLECTION_LIFECYCLE_LOGGER_NAME,
    CollectionClientType,
    CollectionLifecycleEmitter,
    CollectionLifecycleEvent,
    CollectionLifecycleEventName,
    CollectionLifecycleStatus,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    CLIENT_TYPE_ATTRIBUTE,
    COLLECTION_DURATION_MS_ATTRIBUTE,
    COLLECTION_LIFECYCLE_ATTRIBUTE_KEYS,
    COLLECTION_STATUS_ATTRIBUTE,
    PROVIDER_ATTRIBUTE,
    RECORD_COUNT_ATTRIBUTE,
    REPORTING_DATE_ATTRIBUTE,
)

REPORTING_DATE = date(2026, 2, 3)


def _event(
    event_name: CollectionLifecycleEventName,
    status: CollectionLifecycleStatus,
    *,
    record_count: int | None,
    duration_ms: int = 12,
) -> CollectionLifecycleEvent:
    return CollectionLifecycleEvent(
        event_name=event_name,
        reporting_date=REPORTING_DATE,
        provider=ProviderName.ANTHROPIC,
        client_type=CollectionClientType.IN_MEMORY,
        collection_status=status,
        duration_ms=duration_ms,
        record_count=record_count,
    )


def test_emitter_writes_safe_local_json_and_otel_events() -> None:
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    provider = LoggerProvider(shutdown_on_exit=False)
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    stream = StringIO()
    emitter = CollectionLifecycleEmitter(provider, local_stream=stream)
    completed = _event(
        CollectionLifecycleEventName.COMPLETED,
        CollectionLifecycleStatus.SUCCESS,
        record_count=2,
    )
    failed = _event(
        CollectionLifecycleEventName.FAILED,
        CollectionLifecycleStatus.FAILED,
        record_count=None,
        duration_ms=19,
    )

    try:
        emitter.emit(completed)
        emitter.emit(failed)
        exported = exporter.get_finished_logs()
        assert len(exported) == 2
        assert [record.log_record.event_name for record in exported] == [
            "collection_completed",
            "collection_failed",
        ]
        assert [record.log_record.severity_number for record in exported] == [
            SeverityNumber.INFO,
            SeverityNumber.ERROR,
        ]
        for record in exported:
            assert record.instrumentation_scope is not None
            assert record.instrumentation_scope.name == COLLECTION_LIFECYCLE_LOGGER_NAME
            assert record.log_record.body is None

        assert exported[0].log_record.attributes == completed.otel_attributes()
        assert exported[1].log_record.attributes == failed.otel_attributes()
        assert set(completed.otel_attributes()) == COLLECTION_LIFECYCLE_ATTRIBUTE_KEYS
        assert set(failed.otel_attributes()) == (
            COLLECTION_LIFECYCLE_ATTRIBUTE_KEYS - {RECORD_COUNT_ATTRIBUTE}
        )
        local_events = [
            cast(dict[str, Any], json.loads(line))
            for line in stream.getvalue().splitlines()
        ]
        assert local_events == [
            completed.model_dump(mode="json", exclude_none=True),
            failed.model_dump(mode="json", exclude_none=True),
        ]
    finally:
        provider.shutdown()


def test_event_attributes_are_exactly_the_safe_operational_allowlist() -> None:
    event = _event(
        CollectionLifecycleEventName.RECORDS_MAPPED,
        CollectionLifecycleStatus.IN_PROGRESS,
        record_count=2,
    )

    assert event.otel_attributes() == {
        REPORTING_DATE_ATTRIBUTE: "2026-02-03",
        PROVIDER_ATTRIBUTE: "anthropic",
        CLIENT_TYPE_ATTRIBUTE: "in_memory",
        COLLECTION_STATUS_ATTRIBUTE: "in_progress",
        COLLECTION_DURATION_MS_ATTRIBUTE: 12,
        RECORD_COUNT_ATTRIBUTE: 2,
    }


def test_event_rejects_status_incompatible_with_checkpoint() -> None:
    with pytest.raises(ValidationError, match="incompatible collection status"):
        _event(
            CollectionLifecycleEventName.COMPLETED,
            CollectionLifecycleStatus.FAILED,
            record_count=2,
        )


def test_noninitial_success_checkpoint_requires_record_count() -> None:
    with pytest.raises(ValidationError, match="requires a record count"):
        _event(
            CollectionLifecycleEventName.AGGREGATION_COMPLETED,
            CollectionLifecycleStatus.IN_PROGRESS,
            record_count=None,
        )


@pytest.mark.parametrize(
    ("unsafe_field", "unsafe_value"),
    [
        ("email", "synthetic-user@example.com"),
        ("provider_user_id", "synthetic-raw-user-id"),
        ("credential", "synthetic-secret-value"),
        ("authentication_headers", {"x-api-key": "synthetic-secret-value"}),
        ("file_path", "/synthetic/private/path"),
        ("api_endpoint", "https://private.example.test"),
    ],
)
def test_event_schema_rejects_sensitive_extra_fields(
    unsafe_field: str,
    unsafe_value: object,
) -> None:
    payload = _event(
        CollectionLifecycleEventName.STARTED,
        CollectionLifecycleStatus.STARTED,
        record_count=None,
        duration_ms=0,
    ).model_dump()
    payload[unsafe_field] = unsafe_value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CollectionLifecycleEvent.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_ms", -1), ("record_count", -1)],
)
def test_event_rejects_negative_operational_values(field: str, value: int) -> None:
    payload = _event(
        CollectionLifecycleEventName.COMPLETED,
        CollectionLifecycleStatus.SUCCESS,
        record_count=2,
    ).model_dump()
    payload[field] = value

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CollectionLifecycleEvent.model_validate(payload)
