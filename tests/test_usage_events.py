"""Tests for structured privacy-safe per-user usage events."""

import json
from io import StringIO
from typing import Any, cast

import pytest
from opentelemetry._logs import SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)
from pydantic import SecretStr, ValidationError

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    normalize_anthropic_records,
)
from genai_usage_observability_gateway.privacy import (
    AnthropicPrivacySafeCollection,
    HmacSha256Pseudonymizer,
    protect_anthropic_collection,
)
from genai_usage_observability_gateway.usage_events import (
    USAGE_EVENT_LOGGER_NAME,
    USAGE_EVENT_NAME,
    AnthropicUsageEvent,
    UsageEventEmitter,
)
from tests.factories import (
    anthropic_activity_payload,
    anthropic_record_from_payload,
)

SYNTHETIC_KEY = "synthetic-usage-event-key"


def _collection() -> tuple[
    tuple[AnthropicNormalizedUsageRecord, ...],
    AnthropicPrivacySafeCollection,
]:
    payloads = [anthropic_activity_payload(user_number) for user_number in (1, 2)]
    payloads[0]["rbac_group_id"] = "synthetic-private-group-id"
    payloads[0]["rbac_group_name"] = "Synthetic Private Group"
    records = normalize_anthropic_records(
        anthropic_record_from_payload(payload) for payload in payloads
    )
    collection = protect_anthropic_collection(
        records,
        HmacSha256Pseudonymizer(SecretStr(SYNTHETIC_KEY)),
    )
    return records, collection


def _emit_collection() -> tuple[
    tuple[AnthropicNormalizedUsageRecord, ...],
    AnthropicPrivacySafeCollection,
    list[dict[str, Any]],
    list[dict[str, Any]],
]:
    records, collection = _collection()
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    provider = LoggerProvider(shutdown_on_exit=False)
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    stream = StringIO()
    emitter = UsageEventEmitter(provider, local_stream=stream)
    try:
        emitted_count = emitter.emit_collection(collection)
        exported = exporter.get_finished_logs()
        assert emitted_count == len(collection.usage_records)
        assert len(exported) == len(collection.usage_records)
        otel_bodies: list[dict[str, Any]] = []
        for readable in exported:
            log_record = readable.log_record
            assert log_record.event_name == USAGE_EVENT_NAME
            assert log_record.severity_number is SeverityNumber.INFO
            assert log_record.severity_text == "INFO"
            assert log_record.attributes == {}
            assert readable.instrumentation_scope is not None
            assert readable.instrumentation_scope.name == USAGE_EVENT_LOGGER_NAME
            assert isinstance(log_record.body, dict)
            otel_bodies.append(cast(dict[str, Any], log_record.body))
        local_bodies = [json.loads(line) for line in stream.getvalue().splitlines()]
        return records, collection, otel_bodies, local_bodies
    finally:
        provider.shutdown()


def test_exactly_one_matching_local_and_otel_event_is_emitted_per_user() -> None:
    _, collection, otel_bodies, local_bodies = _emit_collection()

    assert len(otel_bodies) == len(collection.usage_records) == 2
    assert local_bodies == otel_bodies
    assert {body["pseudonymous_user_id"] for body in otel_bodies} == {
        record.pseudonymous_user_id for record in collection.usage_records
    }


def test_event_body_contains_the_allowlisted_common_and_provider_activity() -> None:
    _, collection, otel_bodies, _ = _emit_collection()
    first_record = collection.usage_records[0]
    first_event = otel_bodies[0]

    assert set(first_event) == {
        "event_name",
        "reporting_date",
        "provider",
        "pseudonymous_user_id",
        "common_activity",
        "anthropic_activity",
    }
    assert first_event["event_name"] == USAGE_EVENT_NAME
    assert first_event["reporting_date"] == "2026-02-03"
    assert first_event["provider"] == "anthropic"
    assert first_event["common_activity"] == first_record.activity.model_dump(
        mode="json"
    )
    assert first_event["anthropic_activity"] == (
        first_record.provider_extension.model_dump(mode="json")
    )
    anthropic_activity = cast(dict[str, Any], first_event["anthropic_activity"])
    assert anthropic_activity["web_search_count"] == 2
    assert (
        anthropic_activity["claude_code_metrics"]["core_metrics"]["commit_count"] == 2
    )


def test_raw_identities_groups_and_sensitive_values_never_appear() -> None:
    records, _, otel_bodies, local_bodies = _emit_collection()
    serialized = json.dumps(
        {"otel": otel_bodies, "local": local_bodies}, sort_keys=True
    )

    for record in records:
        assert record.identity.provider_user_id not in serialized
        assert str(record.identity.email) not in serialized
    for forbidden in (
        SYNTHETIC_KEY,
        "synthetic-private-group-id",
        "Synthetic Private Group",
        "rbac_group",
        "credential",
        "authorization",
        "x-api-key",
        "file_path",
        "api_endpoint",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    "unsafe_field",
    [
        "email",
        "provider_user_id",
        "organizational_groups",
        "credential",
        "authentication_headers",
        "file_path",
        "api_endpoint",
    ],
)
def test_event_schema_rejects_unsafe_extra_fields(unsafe_field: str) -> None:
    _, collection = _collection()
    event = AnthropicUsageEvent.from_record(collection.usage_records[0])
    payload = event.model_dump()
    payload[unsafe_field] = "must-not-be-exported"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AnthropicUsageEvent.model_validate(payload)


def test_event_builder_rejects_mismatched_provider() -> None:
    _, collection = _collection()
    record = collection.usage_records[0].model_copy(
        update={"provider": ProviderName.MOCK}
    )

    with pytest.raises(ValueError, match="require an Anthropic record"):
        AnthropicUsageEvent.from_record(record)


def test_otel_export_does_not_require_local_logging() -> None:
    _, collection = _collection()
    exporter = InMemoryLogRecordExporter()  # type: ignore[no-untyped-call]
    provider = LoggerProvider(shutdown_on_exit=False)
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    emitter = UsageEventEmitter(provider)
    try:
        assert emitter.emit_collection(collection) == 2
        assert len(exporter.get_finished_logs()) == 2
    finally:
        provider.shutdown()
