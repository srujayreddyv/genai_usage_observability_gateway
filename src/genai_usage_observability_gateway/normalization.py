"""Provider adapters that create common normalized usage records."""

from collections.abc import Iterable
from datetime import date

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models.usage import (
    CommonUsageActivity,
    NonNegativeCount,
    NormalizedUsageRecord,
    ProviderUsageExtension,
    UserIdentity,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicChatMetrics,
    AnthropicClaudeCodeMetrics,
    AnthropicCoworkMetrics,
    AnthropicDesignMetrics,
    AnthropicOfficeMetrics,
    AnthropicScienceMetrics,
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.providers.mock import (
    MockChatMetrics,
    MockClaudeCodeMetrics,
    MockCoworkMetrics,
    MockDesignMetrics,
    MockOfficeMetrics,
    MockScienceMetrics,
    MockUserActivityRecord,
)


class AnthropicUsageExtension(ProviderUsageExtension):
    """Anthropic activity that must retain its provider-specific semantics."""

    chat_metrics: AnthropicChatMetrics
    claude_code_metrics: AnthropicClaudeCodeMetrics
    cowork_metrics: AnthropicCoworkMetrics
    design_metrics: AnthropicDesignMetrics
    office_metrics: AnthropicOfficeMetrics
    science_metrics: AnthropicScienceMetrics
    web_search_count: NonNegativeCount
    last_activity_date: date | None = None


AnthropicNormalizedUsageRecord = NormalizedUsageRecord[AnthropicUsageExtension]


class MockUsageExtension(ProviderUsageExtension):
    """Synthetic activity retained without pretending it is a real provider."""

    chat_metrics: MockChatMetrics
    claude_code_metrics: MockClaudeCodeMetrics
    cowork_metrics: MockCoworkMetrics
    design_metrics: MockDesignMetrics
    office_metrics: MockOfficeMetrics
    science_metrics: MockScienceMetrics
    web_search_count: NonNegativeCount


MockNormalizedUsageRecord = NormalizedUsageRecord[MockUsageExtension]


def _tool_action_counts(record: AnthropicUserActivityRecord) -> tuple[int, int]:
    actions = record.activity.claude_code_metrics.tool_actions
    action_types = (
        actions.edit_tool,
        actions.multi_edit_tool,
        actions.notebook_edit_tool,
        actions.write_tool,
    )
    return (
        sum(action.accepted_count for action in action_types),
        sum(action.rejected_count for action in action_types),
    )


def _is_active(record: AnthropicUserActivityRecord) -> bool:
    """Apply Anthropic's public daily active-user definition."""

    activity = record.activity
    return any(
        (
            activity.chat_metrics.message_count,
            activity.claude_code_metrics.core_metrics.distinct_session_count,
            activity.cowork_metrics.message_count,
            activity.cowork_metrics.action_count,
        )
    )


def normalize_anthropic_record(
    record: AnthropicUserActivityRecord,
) -> AnthropicNormalizedUsageRecord:
    """Map one validated Anthropic record without inventing unavailable data."""

    activity = record.activity
    accepted_actions, rejected_actions = _tool_action_counts(record)

    return NormalizedUsageRecord[AnthropicUsageExtension](
        reporting_date=record.reporting_date,
        provider=ProviderName.ANTHROPIC,
        identity=UserIdentity(
            provider_user_id=activity.user.id,
            email=activity.user.email_address,
        ),
        activity=CommonUsageActivity(
            is_active=_is_active(record),
            chat_interaction_count=activity.chat_metrics.message_count,
            developer_session_count=(
                activity.claude_code_metrics.core_metrics.distinct_session_count
            ),
            accepted_tool_action_count=accepted_actions,
            rejected_tool_action_count=rejected_actions,
        ),
        provider_extension=AnthropicUsageExtension(
            chat_metrics=activity.chat_metrics,
            claude_code_metrics=activity.claude_code_metrics,
            cowork_metrics=activity.cowork_metrics,
            design_metrics=activity.design_metrics,
            office_metrics=activity.office_metrics,
            science_metrics=activity.science_metrics,
            web_search_count=activity.web_search_count,
            last_activity_date=activity.last_activity_date,
        ),
    )


def normalize_anthropic_records(
    records: Iterable[AnthropicUserActivityRecord],
) -> tuple[AnthropicNormalizedUsageRecord, ...]:
    """Normalize Anthropic records while preserving input order."""

    return tuple(normalize_anthropic_record(record) for record in records)


def _mock_tool_action_counts(record: MockUserActivityRecord) -> tuple[int, int]:
    actions = record.claude_code_metrics.tool_actions
    action_types = (
        actions.edit_tool,
        actions.multi_edit_tool,
        actions.notebook_edit_tool,
        actions.write_tool,
    )
    return (
        sum(action.accepted_count for action in action_types),
        sum(action.rejected_count for action in action_types),
    )


def normalize_mock_record(
    record: MockUserActivityRecord,
) -> MockNormalizedUsageRecord:
    """Map one strict synthetic record into common and mock-owned concepts."""

    accepted_actions, rejected_actions = _mock_tool_action_counts(record)
    return NormalizedUsageRecord[MockUsageExtension](
        reporting_date=record.reporting_date,
        provider=ProviderName.MOCK,
        identity=UserIdentity(
            provider_user_id=record.user.id,
            email=record.user.email_address,
        ),
        activity=CommonUsageActivity(
            is_active=any(
                (
                    record.chat_metrics.message_count,
                    record.claude_code_metrics.distinct_session_count,
                    record.cowork_metrics.message_count,
                    record.cowork_metrics.action_count,
                )
            ),
            chat_interaction_count=record.chat_metrics.message_count,
            developer_session_count=(record.claude_code_metrics.distinct_session_count),
            accepted_tool_action_count=accepted_actions,
            rejected_tool_action_count=rejected_actions,
        ),
        provider_extension=MockUsageExtension(
            chat_metrics=record.chat_metrics,
            claude_code_metrics=record.claude_code_metrics,
            cowork_metrics=record.cowork_metrics,
            design_metrics=record.design_metrics,
            office_metrics=record.office_metrics,
            science_metrics=record.science_metrics,
            web_search_count=record.web_search_count,
        ),
    )


def normalize_mock_records(
    records: Iterable[MockUserActivityRecord],
) -> tuple[MockNormalizedUsageRecord, ...]:
    """Normalize synthetic records while preserving input order."""

    return tuple(normalize_mock_record(record) for record in records)
