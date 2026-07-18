import asyncio
from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.providers import (
    AnalyticsClient,
    MockAnalyticsClient,
)
from genai_usage_observability_gateway.providers.mock import (
    MockAnalyticsUser,
    MockChatMetrics,
    MockCoworkMetrics,
    MockDesignMetrics,
    MockLinesOfCode,
    MockOfficeProductMetrics,
    MockScienceMetrics,
    MockUserActivityRecord,
    ToolActionCounts,
    build_synthetic_usage,
)

REPORTING_DATE = date(2026, 1, 15)


def collect() -> tuple[MockUserActivityRecord, ...]:
    return asyncio.run(MockAnalyticsClient().get_usage_analytics(REPORTING_DATE))


def accepts_mock_client(
    client: AnalyticsClient[MockUserActivityRecord],
) -> AnalyticsClient[MockUserActivityRecord]:
    return client


def test_mock_client_satisfies_provider_protocol() -> None:
    client = MockAnalyticsClient()

    assert accepts_mock_client(client) is client
    assert isinstance(client, AnalyticsClient)
    assert client.provider is ProviderName.MOCK


def test_mock_client_returns_exactly_five_unique_fictional_users() -> None:
    records = collect()

    assert len(records) == 5
    assert len({record.user.id for record in records}) == 5
    assert len({str(record.user.email_address) for record in records}) == 5
    assert all(
        str(record.user.email_address).endswith("@example.com") for record in records
    )
    assert {record.reporting_date for record in records} == {REPORTING_DATE}


def test_synthetic_users_exercise_group_membership_patterns() -> None:
    records = collect()

    assert any(len(record.organizational_groups) > 1 for record in records)
    assert any(len(record.organizational_groups) == 1 for record in records)
    assert any(not record.organizational_groups for record in records)


def test_synthetic_users_exercise_developer_activity_patterns() -> None:
    records = collect()
    session_counts = [
        record.claude_code_metrics.distinct_session_count for record in records
    ]

    assert sum(count > 0 for count in session_counts) == 2
    assert sum(count == 0 for count in session_counts) == 3
    assert sum(record.claude_code_metrics.commit_count for record in records) == 9
    assert sum(record.claude_code_metrics.pull_request_count for record in records) == 3


def test_synthetic_users_include_accepted_and_rejected_tool_actions() -> None:
    records = collect()
    action_counts = [
        action
        for record in records
        for action in (
            record.claude_code_metrics.tool_actions.edit_tool,
            record.claude_code_metrics.tool_actions.multi_edit_tool,
            record.claude_code_metrics.tool_actions.notebook_edit_tool,
            record.claude_code_metrics.tool_actions.write_tool,
        )
    ]

    assert sum(action.accepted_count for action in action_counts) == 33
    assert sum(action.rejected_count for action in action_counts) == 9


def test_synthetic_sample_exercises_documented_product_categories() -> None:
    records = collect()

    assert any(record.chat_metrics.message_count > 0 for record in records)
    assert any(record.cowork_metrics.action_count > 0 for record in records)
    assert any(record.design_metrics.message_count > 0 for record in records)
    assert any(record.office_metrics.excel.message_count > 0 for record in records)
    assert any(record.office_metrics.outlook.message_count > 0 for record in records)
    assert any(record.office_metrics.powerpoint.message_count > 0 for record in records)
    assert any(record.office_metrics.word.message_count > 0 for record in records)
    assert any(record.science_metrics.message_count > 0 for record in records)
    assert any(record.web_search_count > 0 for record in records)


def test_synthetic_sample_includes_inactive_user() -> None:
    inactive = collect()[-1]

    assert inactive.user.id == "mock_user_005"
    assert inactive.chat_metrics.message_count == 0
    assert inactive.claude_code_metrics.distinct_session_count == 0
    assert inactive.cowork_metrics.distinct_session_count == 0
    assert inactive.design_metrics.distinct_session_count == 0
    assert inactive.science_metrics.distinct_session_count == 0
    assert inactive.web_search_count == 0


@pytest.mark.parametrize(
    ("model", "field"),
    [
        (MockChatMetrics, "message_count"),
        (MockCoworkMetrics, "action_count"),
        (MockDesignMetrics, "distinct_session_count"),
        (MockLinesOfCode, "added_count"),
        (MockOfficeProductMetrics, "message_count"),
        (MockScienceMetrics, "remote_compute_job_count"),
        (ToolActionCounts, "rejected_count"),
    ],
)
def test_count_models_reject_negative_values(model: type[Any], field: str) -> None:
    valid_values: dict[str, dict[str, int]] = {
        "MockChatMetrics": {"message_count": 0, "distinct_conversation_count": 0},
        "MockCoworkMetrics": {
            "message_count": 0,
            "distinct_session_count": 0,
            "action_count": 0,
        },
        "MockDesignMetrics": {
            "message_count": 0,
            "distinct_session_count": 0,
            "distinct_projects_used_count": 0,
        },
        "MockLinesOfCode": {"added_count": 0, "removed_count": 0},
        "MockOfficeProductMetrics": {
            "message_count": 0,
            "distinct_session_count": 0,
        },
        "MockScienceMetrics": {
            "message_count": 0,
            "distinct_session_count": 0,
            "delegation_count": 0,
            "remote_compute_job_count": 0,
        },
        "ToolActionCounts": {"accepted_count": 0, "rejected_count": 0},
    }
    payload = valid_values[model.__name__]
    payload[field] = -1

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        model.model_validate(payload)


def test_counts_reject_non_integer_coercion() -> None:
    with pytest.raises(ValidationError):
        ToolActionCounts.model_validate({"accepted_count": "1", "rejected_count": 0})


def test_mock_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MockAnalyticsUser.model_validate(
            {
                "id": "mock_user_dynamic",
                "email_address": "dynamic.user@example.com",
                "unknown_identity_field": "not-allowed",
            }
        )


def test_mock_record_rejects_unknown_top_level_fields() -> None:
    payload = build_synthetic_usage(REPORTING_DATE)[0].model_dump()
    payload["prompt"] = "synthetic content that must not be accepted"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        MockUserActivityRecord.model_validate(payload)


def test_synthetic_records_contain_no_prompt_or_response_fields() -> None:
    serialized = str([record.model_dump() for record in collect()]).lower()

    assert "prompt" not in serialized
    assert "response" not in serialized
