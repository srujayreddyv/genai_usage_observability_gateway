from collections.abc import Sequence
from datetime import date

import pytest
from pydantic import ValidationError

from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationUsageSummary,
    DuplicateProviderUserError,
    EmptyAggregationError,
    IncompatibleProviderError,
    MixedReportingDatesError,
    UnavailableCommonMetricError,
    aggregate_anthropic_usage,
)
from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models import CommonUsageActivity, UserIdentity
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    AnthropicUsageExtension,
    normalize_anthropic_record,
    normalize_anthropic_records,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicUserActivityRecord,
)
from tests.factories import (
    anthropic_activity_payload,
    anthropic_record_from_payload,
)

REPORTING_DATE = date(2026, 2, 3)


def _nested(payload: dict[str, object], *path: str) -> dict[str, object]:
    current = payload
    for part in path:
        value = current[part]
        assert isinstance(value, dict)
        current = value
    return current


def _zero_counts(value: object) -> None:
    if not isinstance(value, dict):
        return
    for key, nested in value.items():
        if type(nested) is int:
            value[key] = 0
        else:
            _zero_counts(nested)


def _raw_record(
    user_number: int = 1, reporting_date: date = REPORTING_DATE
) -> AnthropicUserActivityRecord:
    return anthropic_record_from_payload(
        anthropic_activity_payload(user_number), reporting_date
    )


def _normalized_records(
    count: int = 2,
) -> tuple[AnthropicNormalizedUsageRecord, ...]:
    return normalize_anthropic_records(
        _raw_record(user_number) for user_number in range(1, count + 1)
    )


def test_anthropic_record_maps_common_identity_and_activity() -> None:
    normalized = normalize_anthropic_record(_raw_record())

    assert normalized.reporting_date == REPORTING_DATE
    assert normalized.provider is ProviderName.ANTHROPIC
    assert normalized.identity.provider_user_id == "synthetic-user-001"
    assert str(normalized.identity.email) == "fictional.user1@example.com"
    assert normalized.activity.is_active
    assert normalized.activity.chat_interaction_count == 8
    assert normalized.activity.developer_session_count == 3
    assert normalized.activity.accepted_tool_action_count == 8
    assert normalized.activity.rejected_tool_action_count == 4


def test_anthropic_extension_preserves_every_supported_product_category() -> None:
    extension = normalize_anthropic_record(_raw_record()).provider_extension

    assert extension is not None
    assert extension.chat_metrics.distinct_conversation_count == 3
    assert extension.claude_code_metrics.core_metrics.commit_count == 2
    assert extension.cowork_metrics.action_count == 4
    assert extension.design_metrics.message_count == 4
    assert extension.office_metrics.excel.message_count == 5
    assert extension.office_metrics.outlook.message_count == 5
    assert extension.office_metrics.powerpoint.message_count == 5
    assert extension.office_metrics.word.message_count == 5
    assert extension.science_metrics.remote_compute_job_count == 1
    assert extension.web_search_count == 2
    assert extension.last_activity_date == REPORTING_DATE


def test_extension_excludes_identity_grouping_cost_and_token_data() -> None:
    extension = normalize_anthropic_record(_raw_record()).provider_extension
    assert extension is not None

    serialized = str(extension.model_dump()).lower()

    assert "synthetic-user" not in serialized
    assert "@example.com" not in serialized
    assert "rbac" not in serialized
    assert "group" not in serialized
    assert "cost" not in serialized
    assert "token" not in serialized


@pytest.mark.parametrize(
    ("path", "field"),
    [
        (("chat_metrics",), "message_count"),
        (("claude_code_metrics", "core_metrics"), "distinct_session_count"),
        (("cowork_metrics",), "message_count"),
        (("cowork_metrics",), "action_count"),
    ],
)
def test_documented_anthropic_active_signals_map_to_active(
    path: tuple[str, ...], field: str
) -> None:
    payload = anthropic_activity_payload()
    _zero_counts(payload)
    _nested(payload, *path)[field] = 1

    normalized = normalize_anthropic_record(anthropic_record_from_payload(payload))

    assert normalized.activity.is_active


def test_provider_specific_activity_does_not_redefine_common_active_user() -> None:
    payload = anthropic_activity_payload()
    _zero_counts(payload)
    _nested(payload, "design_metrics")["message_count"] = 1
    _nested(payload, "office_metrics", "excel")["message_count"] = 1
    _nested(payload, "science_metrics")["message_count"] = 1
    payload["web_search_count"] = 1

    normalized = normalize_anthropic_record(anthropic_record_from_payload(payload))

    assert not normalized.activity.is_active
    assert normalized.provider_extension is not None
    assert normalized.provider_extension.design_metrics.message_count == 1
    assert normalized.provider_extension.office_metrics.excel.message_count == 1
    assert normalized.provider_extension.science_metrics.message_count == 1
    assert normalized.provider_extension.web_search_count == 1


def test_normalize_records_preserves_input_order() -> None:
    records = normalize_anthropic_records((_raw_record(2), _raw_record(1)))

    assert [record.identity.provider_user_id for record in records] == [
        "synthetic-user-002",
        "synthetic-user-001",
    ]


def test_anthropic_extension_rejects_negative_counts() -> None:
    extension = normalize_anthropic_record(_raw_record()).provider_extension
    assert extension is not None
    payload = extension.model_dump()
    payload["web_search_count"] = -1

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        AnthropicUsageExtension.model_validate(payload)


def test_aggregation_calculates_every_common_and_provider_total() -> None:
    summary = aggregate_anthropic_usage(_normalized_records())

    assert summary.reporting_date == REPORTING_DATE
    assert summary.provider is ProviderName.ANTHROPIC
    assert summary.total_users == 2
    assert summary.active_users == 2
    assert summary.chat_interaction_count == 16
    assert summary.developer_session_count == 6
    assert summary.accepted_tool_action_count == 16
    assert summary.rejected_tool_action_count == 8
    assert summary.tool_action_acceptance_rate == pytest.approx(2 / 3)
    assert 0 <= summary.tool_action_acceptance_rate <= 1

    provider = summary.provider_activity
    assert provider.commit_count == 4
    assert provider.pull_request_count == 2
    assert provider.lines_added_count == 40
    assert provider.lines_removed_count == 8
    assert provider.cowork.action_count == 8
    assert provider.cowork.connector_invocation_count == 4
    assert provider.cowork.dispatch_turn_count == 2
    assert provider.cowork.message_count == 12
    assert provider.cowork.session_count == 6
    assert provider.cowork.skill_invocation_count == 6
    assert provider.design.message_count == 8
    assert provider.design.project_created_count == 2
    assert provider.design.session_count == 4
    _assert_office_totals(summary)
    assert provider.science.delegation_count == 2
    assert provider.science.message_count == 6
    assert provider.science.remote_compute_job_count == 2
    assert provider.science.session_count == 4
    assert provider.science.skill_invocation_count == 4
    assert provider.web_search_count == 4


def _assert_office_totals(summary: AnthropicOrganizationUsageSummary) -> None:
    office_products = (
        summary.provider_activity.office.excel,
        summary.provider_activity.office.outlook,
        summary.provider_activity.office.powerpoint,
        summary.provider_activity.office.word,
    )
    for product in office_products:
        assert product.connector_invocation_count == 4
        assert product.message_count == 10
        assert product.session_count == 6
        assert product.skill_invocation_count == 4


def test_zero_tool_actions_return_zero_acceptance_rate() -> None:
    payload = anthropic_activity_payload()
    actions = _nested(payload, "claude_code_metrics", "tool_actions")
    _zero_counts(actions)
    record = normalize_anthropic_record(anthropic_record_from_payload(payload))

    summary = aggregate_anthropic_usage((record,))

    assert summary.accepted_tool_action_count == 0
    assert summary.rejected_tool_action_count == 0
    assert summary.tool_action_acceptance_rate == 0


def test_active_user_total_excludes_inactive_normalized_records() -> None:
    inactive_payload = anthropic_activity_payload(2)
    _zero_counts(inactive_payload)
    records = normalize_anthropic_records(
        (_raw_record(1), anthropic_record_from_payload(inactive_payload))
    )

    summary = aggregate_anthropic_usage(records)

    assert summary.total_users == 2
    assert summary.active_users == 1


def test_organization_summary_contains_no_individual_identity_or_group_data() -> None:
    records = _normalized_records()

    serialized = str(aggregate_anthropic_usage(records).model_dump()).lower()

    for record in records:
        assert record.identity.provider_user_id.lower() not in serialized
        assert str(record.identity.email).lower() not in serialized
    assert "rbac" not in serialized
    assert "group" not in serialized


def test_empty_collection_is_rejected() -> None:
    with pytest.raises(EmptyAggregationError, match="requires records"):
        aggregate_anthropic_usage(())


def test_duplicate_provider_user_for_same_date_is_rejected() -> None:
    first = _normalized_records(1)[0]
    duplicate = first.model_copy()

    with pytest.raises(
        DuplicateProviderUserError, match="duplicate provider user identifier"
    ):
        aggregate_anthropic_usage((first, duplicate))


def test_mixed_reporting_dates_are_rejected() -> None:
    first, second = _normalized_records()
    second_date = second.model_copy(
        update={
            "reporting_date": date(2026, 2, 4),
            "identity": UserIdentity(
                provider_user_id="synthetic-user-different-date",
                email="different.date@example.com",
            ),
        }
    )

    with pytest.raises(MixedReportingDatesError, match="one reporting date"):
        aggregate_anthropic_usage((first, second_date))


def test_non_anthropic_provider_is_rejected() -> None:
    record = _normalized_records(1)[0].model_copy(
        update={"provider": ProviderName.MOCK}
    )

    with pytest.raises(IncompatibleProviderError, match="only Anthropic records"):
        aggregate_anthropic_usage((record,))


def test_missing_anthropic_extension_is_rejected() -> None:
    record = _normalized_records(1)[0].model_copy(update={"provider_extension": None})

    with pytest.raises(IncompatibleProviderError, match="missing its provider"):
        aggregate_anthropic_usage((record,))


@pytest.mark.parametrize(
    "field",
    [
        "chat_interaction_count",
        "developer_session_count",
        "accepted_tool_action_count",
        "rejected_tool_action_count",
    ],
)
def test_unavailable_required_common_metric_is_rejected(field: str) -> None:
    record = _normalized_records(1)[0]
    activity_values = record.activity.model_dump()
    activity_values[field] = None
    invalid_activity = CommonUsageActivity.model_validate(activity_values)
    record = record.model_copy(update={"activity": invalid_activity})

    with pytest.raises(UnavailableCommonMetricError, match="is unavailable"):
        aggregate_anthropic_usage((record,))


@pytest.mark.parametrize("rate", [-0.01, 1.01])
def test_summary_model_rejects_acceptance_rate_outside_unit_interval(
    rate: float,
) -> None:
    summary = aggregate_anthropic_usage(_normalized_records(1))
    values = summary.model_dump()
    values["tool_action_acceptance_rate"] = rate

    with pytest.raises(ValidationError):
        AnthropicOrganizationUsageSummary.model_validate(values)


def accepts_normalized_records(
    records: Sequence[AnthropicNormalizedUsageRecord],
) -> Sequence[AnthropicNormalizedUsageRecord]:
    return records


def test_normalized_record_alias_is_statically_usable() -> None:
    records = _normalized_records(1)

    assert accepts_normalized_records(records) is records
