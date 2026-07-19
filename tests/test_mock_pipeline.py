"""Tests for the synthetic provider's complete privacy-safe pipeline."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone

import pytest
from pydantic import SecretStr, ValidationError

from genai_usage_observability_gateway.aggregation import (
    DuplicateProviderUserError,
    EmptyAggregationError,
    IncompatibleProviderError,
    MixedReportingDatesError,
    aggregate_mock_usage,
)
from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.normalization import (
    MockNormalizedUsageRecord,
    normalize_mock_records,
)
from genai_usage_observability_gateway.preview import (
    MockUsagePreview,
    build_mock_usage_preview_from_collection,
    render_usage_preview,
)
from genai_usage_observability_gateway.privacy import (
    HmacSha256Pseudonymizer,
    MockPrivacySafeCollection,
    protect_mock_collection,
    protect_mock_record,
)
from genai_usage_observability_gateway.providers.mock import build_synthetic_usage
from genai_usage_observability_gateway.usage_events import MockUsageEvent

REPORTING_DATE = date(2026, 2, 3)
SYNTHETIC_KEY = "synthetic-mock-pipeline-key"


def _normalized() -> tuple[MockNormalizedUsageRecord, ...]:
    return normalize_mock_records(build_synthetic_usage(REPORTING_DATE))


def _pseudonymizer() -> HmacSha256Pseudonymizer:
    return HmacSha256Pseudonymizer(SecretStr(SYNTHETIC_KEY))


def _collection() -> MockPrivacySafeCollection:
    return protect_mock_collection(_normalized(), _pseudonymizer())


def _preview() -> MockUsagePreview:
    return build_mock_usage_preview_from_collection(
        _collection(),
        collection_timestamp=datetime(2026, 2, 3, 12, tzinfo=UTC),
    )


def test_mock_normalization_and_aggregation_preserve_synthetic_semantics() -> None:
    records = _normalized()
    summary = aggregate_mock_usage(records)

    assert len(records) == 5
    assert summary.model_dump(exclude={"provider_activity"}) == {
        "reporting_date": REPORTING_DATE,
        "provider": ProviderName.MOCK,
        "total_users": 5,
        "active_users": 4,
        "chat_interaction_count": 44,
        "developer_session_count": 14,
        "accepted_tool_action_count": 33,
        "rejected_tool_action_count": 9,
        "tool_action_acceptance_rate": 33 / 42,
    }
    activity = summary.provider_activity
    assert (activity.commit_count, activity.pull_request_count) == (9, 3)
    assert (activity.lines_added_count, activity.lines_removed_count) == (600, 157)
    assert activity.cowork.model_dump() == {
        "action_count": 23,
        "message_count": 16,
        "session_count": 6,
    }
    assert activity.design.model_dump() == {
        "message_count": 11,
        "project_used_count": 2,
        "session_count": 4,
    }
    assert activity.science.model_dump() == {
        "delegation_count": 2,
        "message_count": 10,
        "remote_compute_job_count": 1,
        "session_count": 3,
    }
    assert activity.web_search_count == 14


def test_mock_privacy_boundary_removes_raw_identity_and_groups() -> None:
    records = _normalized()
    collection = protect_mock_collection(records, _pseudonymizer())
    serialized = collection.model_dump_json()

    assert len(collection.usage_records) == 5
    assert (
        len({record.pseudonymous_user_id for record in collection.usage_records}) == 5
    )
    for record in records:
        assert record.identity.provider_user_id not in serialized
        assert str(record.identity.email) not in serialized
    for forbidden in (SYNTHETIC_KEY, "Synthetic Engineering", "organizational_groups"):
        assert forbidden not in serialized


def test_mock_aggregation_rejects_invalid_collections() -> None:
    records = _normalized()
    with pytest.raises(EmptyAggregationError):
        aggregate_mock_usage(())
    with pytest.raises(MixedReportingDatesError):
        aggregate_mock_usage(
            (
                records[0],
                records[1].model_copy(update={"reporting_date": date(2026, 2, 4)}),
            )
        )
    with pytest.raises(DuplicateProviderUserError):
        aggregate_mock_usage((records[0], records[0]))
    incompatible = records[0].model_copy(update={"provider": ProviderName.ANTHROPIC})
    with pytest.raises(IncompatibleProviderError):
        aggregate_mock_usage((incompatible,))


def test_mock_privacy_rejects_an_incompatible_record() -> None:
    incompatible = _normalized()[0].model_copy(
        update={"provider": ProviderName.ANTHROPIC}
    )

    with pytest.raises(ValueError, match="normalized mock record"):
        protect_mock_record(incompatible, _pseudonymizer())


def test_mock_collection_rejects_inconsistent_content() -> None:
    collection = _collection()
    metadata_mismatch = collection.metadata.model_copy(
        update={"reporting_date": date(2026, 2, 4)}
    )
    with pytest.raises(ValidationError, match="does not match organization summary"):
        MockPrivacySafeCollection(
            metadata=metadata_mismatch,
            organization_summary=collection.organization_summary,
            usage_records=collection.usage_records,
        )

    count_mismatch = collection.metadata.model_copy(update={"record_count": 6})
    with pytest.raises(ValidationError, match="record counts are inconsistent"):
        MockPrivacySafeCollection(
            metadata=count_mismatch,
            organization_summary=collection.organization_summary,
            usage_records=collection.usage_records,
        )

    record_mismatch = collection.usage_records[0].model_copy(
        update={"reporting_date": date(2026, 2, 4)}
    )
    with pytest.raises(ValidationError, match="do not match collection metadata"):
        MockPrivacySafeCollection(
            metadata=collection.metadata,
            organization_summary=collection.organization_summary,
            usage_records=(record_mismatch, *collection.usage_records[1:]),
        )

    duplicate = collection.usage_records[1].model_copy(
        update={
            "pseudonymous_user_id": collection.usage_records[0].pseudonymous_user_id
        }
    )
    with pytest.raises(ValidationError, match="duplicate pseudonymous identifiers"):
        MockPrivacySafeCollection(
            metadata=collection.metadata,
            organization_summary=collection.organization_summary,
            usage_records=(
                collection.usage_records[0],
                duplicate,
                *collection.usage_records[2:],
            ),
        )


def test_mock_preview_rejects_inconsistent_or_non_utc_content() -> None:
    collection = _collection()
    with pytest.raises(ValueError, match="timezone-aware"):
        build_mock_usage_preview_from_collection(
            collection,
            collection_timestamp=datetime(2026, 2, 3, 12),
        )

    preview = _preview()
    with pytest.raises(ValidationError, match="timestamp must be UTC"):
        MockUsagePreview.model_validate(
            preview.model_dump()
            | {
                "collection_timestamp": datetime(
                    2026, 2, 3, 12, tzinfo=timezone(timedelta(hours=1))
                )
            }
        )
    with pytest.raises(ValidationError, match="does not match organization snapshot"):
        MockUsagePreview.model_validate(
            preview.model_dump()
            | {
                "organization_snapshot": preview.organization_snapshot.model_copy(
                    update={"total_users": 6}
                )
            }
        )
    mismatched_record = preview.usage_records[0].model_copy(
        update={"reporting_date": date(2026, 2, 4)}
    )
    with pytest.raises(ValidationError, match="records do not match preview metadata"):
        MockUsagePreview(
            reporting_date=preview.reporting_date,
            collection_timestamp=preview.collection_timestamp,
            provider=preview.provider,
            usage_records=(mismatched_record, *preview.usage_records[1:]),
            organization_snapshot=preview.organization_snapshot,
        )


def test_mock_preview_and_usage_event_contain_only_post_privacy_data() -> None:
    preview = _preview()
    rendered = render_usage_preview(preview)
    event = MockUsageEvent.from_record(preview.usage_records[0])

    assert event.provider is ProviderName.MOCK
    assert event.pseudonymous_user_id in rendered
    assert "mock_activity" in event.model_dump_json()
    incompatible = preview.usage_records[0].model_copy(
        update={"provider": ProviderName.ANTHROPIC}
    )
    with pytest.raises(ValueError, match="require a mock record"):
        MockUsageEvent.from_record(incompatible)
