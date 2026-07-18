"""Strict synthetic analytics provider used for local development and tests."""

from datetime import date

from pydantic import EmailStr

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models.usage import (
    NonEmptyString,
    NonNegativeCount,
    StrictDomainModel,
)


class MockAnalyticsUser(StrictDomainModel):
    """Fictional identity returned by the mock provider."""

    id: NonEmptyString
    email_address: EmailStr


class ToolActionCounts(StrictDomainModel):
    """Synthetic accepted and rejected proposals for one edit tool."""

    accepted_count: NonNegativeCount
    rejected_count: NonNegativeCount


class MockToolActions(StrictDomainModel):
    """Synthetic file-modification tool activity."""

    edit_tool: ToolActionCounts
    multi_edit_tool: ToolActionCounts
    notebook_edit_tool: ToolActionCounts
    write_tool: ToolActionCounts


class MockLinesOfCode(StrictDomainModel):
    """Synthetic lines added and removed through developer activity."""

    added_count: NonNegativeCount
    removed_count: NonNegativeCount


class MockChatMetrics(StrictDomainModel):
    """Synthetic chat activity."""

    message_count: NonNegativeCount
    distinct_conversation_count: NonNegativeCount


class MockClaudeCodeMetrics(StrictDomainModel):
    """Synthetic Claude Code activity modeled on publicly exposed signals."""

    distinct_session_count: NonNegativeCount
    commit_count: NonNegativeCount
    pull_request_count: NonNegativeCount
    lines_of_code: MockLinesOfCode
    tool_actions: MockToolActions


class MockCoworkMetrics(StrictDomainModel):
    """Synthetic Cowork activity."""

    message_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    action_count: NonNegativeCount


class MockDesignMetrics(StrictDomainModel):
    """Synthetic Claude Design activity."""

    message_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    distinct_projects_used_count: NonNegativeCount


class MockOfficeProductMetrics(StrictDomainModel):
    """Synthetic activity for one Office Agent product."""

    message_count: NonNegativeCount
    distinct_session_count: NonNegativeCount


class MockOfficeMetrics(StrictDomainModel):
    """Synthetic Office Agent activity by product."""

    excel: MockOfficeProductMetrics
    outlook: MockOfficeProductMetrics
    powerpoint: MockOfficeProductMetrics
    word: MockOfficeProductMetrics


class MockScienceMetrics(StrictDomainModel):
    """Synthetic Claude Science activity."""

    message_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    delegation_count: NonNegativeCount
    remote_compute_job_count: NonNegativeCount


class MockUserActivityRecord(StrictDomainModel):
    """One validated synthetic provider response record."""

    reporting_date: date
    user: MockAnalyticsUser
    organizational_groups: tuple[NonEmptyString, ...]
    chat_metrics: MockChatMetrics
    claude_code_metrics: MockClaudeCodeMetrics
    cowork_metrics: MockCoworkMetrics
    design_metrics: MockDesignMetrics
    office_metrics: MockOfficeMetrics
    science_metrics: MockScienceMetrics
    web_search_count: NonNegativeCount


def _tool_actions(
    *,
    edit: tuple[int, int] = (0, 0),
    multi_edit: tuple[int, int] = (0, 0),
    notebook_edit: tuple[int, int] = (0, 0),
    write: tuple[int, int] = (0, 0),
) -> MockToolActions:
    """Build typed synthetic accepted/rejected tool action counts."""

    return MockToolActions(
        edit_tool=ToolActionCounts(accepted_count=edit[0], rejected_count=edit[1]),
        multi_edit_tool=ToolActionCounts(
            accepted_count=multi_edit[0], rejected_count=multi_edit[1]
        ),
        notebook_edit_tool=ToolActionCounts(
            accepted_count=notebook_edit[0], rejected_count=notebook_edit[1]
        ),
        write_tool=ToolActionCounts(accepted_count=write[0], rejected_count=write[1]),
    )


def _code_metrics(
    *,
    sessions: int = 0,
    commits: int = 0,
    pull_requests: int = 0,
    lines_added: int = 0,
    lines_removed: int = 0,
    tool_actions: MockToolActions | None = None,
) -> MockClaudeCodeMetrics:
    """Build synthetic developer activity with explicit zero defaults."""

    return MockClaudeCodeMetrics(
        distinct_session_count=sessions,
        commit_count=commits,
        pull_request_count=pull_requests,
        lines_of_code=MockLinesOfCode(
            added_count=lines_added,
            removed_count=lines_removed,
        ),
        tool_actions=tool_actions or _tool_actions(),
    )


def _office_metrics(
    *,
    excel: tuple[int, int] = (0, 0),
    outlook: tuple[int, int] = (0, 0),
    powerpoint: tuple[int, int] = (0, 0),
    word: tuple[int, int] = (0, 0),
) -> MockOfficeMetrics:
    """Build synthetic Office activity as message/session pairs."""

    return MockOfficeMetrics(
        excel=MockOfficeProductMetrics(
            message_count=excel[0], distinct_session_count=excel[1]
        ),
        outlook=MockOfficeProductMetrics(
            message_count=outlook[0], distinct_session_count=outlook[1]
        ),
        powerpoint=MockOfficeProductMetrics(
            message_count=powerpoint[0], distinct_session_count=powerpoint[1]
        ),
        word=MockOfficeProductMetrics(
            message_count=word[0], distinct_session_count=word[1]
        ),
    )


def build_synthetic_usage(
    reporting_date: date,
) -> tuple[MockUserActivityRecord, ...]:
    """Create exactly five fictional users with varied observable activity."""

    records = (
        MockUserActivityRecord(
            reporting_date=reporting_date,
            user=MockAnalyticsUser(
                id="mock_user_001", email_address="avery.river@example.com"
            ),
            organizational_groups=("Synthetic Engineering",),
            chat_metrics=MockChatMetrics(
                message_count=12, distinct_conversation_count=4
            ),
            claude_code_metrics=_code_metrics(
                sessions=5,
                commits=3,
                pull_requests=1,
                lines_added=180,
                lines_removed=42,
                tool_actions=_tool_actions(edit=(8, 2), write=(3, 1)),
            ),
            cowork_metrics=MockCoworkMetrics(
                message_count=2, distinct_session_count=1, action_count=3
            ),
            design_metrics=MockDesignMetrics(
                message_count=0,
                distinct_session_count=0,
                distinct_projects_used_count=0,
            ),
            office_metrics=_office_metrics(),
            science_metrics=MockScienceMetrics(
                message_count=0,
                distinct_session_count=0,
                delegation_count=0,
                remote_compute_job_count=0,
            ),
            web_search_count=3,
        ),
        MockUserActivityRecord(
            reporting_date=reporting_date,
            user=MockAnalyticsUser(
                id="mock_user_002", email_address="blair.summit@example.com"
            ),
            organizational_groups=("Synthetic Operations",),
            chat_metrics=MockChatMetrics(
                message_count=20, distinct_conversation_count=7
            ),
            claude_code_metrics=_code_metrics(),
            cowork_metrics=MockCoworkMetrics(
                message_count=9, distinct_session_count=3, action_count=14
            ),
            design_metrics=MockDesignMetrics(
                message_count=0,
                distinct_session_count=0,
                distinct_projects_used_count=0,
            ),
            office_metrics=_office_metrics(outlook=(5, 2), word=(7, 2)),
            science_metrics=MockScienceMetrics(
                message_count=0,
                distinct_session_count=0,
                delegation_count=0,
                remote_compute_job_count=0,
            ),
            web_search_count=4,
        ),
        MockUserActivityRecord(
            reporting_date=reporting_date,
            user=MockAnalyticsUser(
                id="mock_user_003", email_address="casey.forest@example.com"
            ),
            organizational_groups=(),
            chat_metrics=MockChatMetrics(
                message_count=4, distinct_conversation_count=2
            ),
            claude_code_metrics=_code_metrics(
                sessions=9,
                commits=6,
                pull_requests=2,
                lines_added=420,
                lines_removed=115,
                tool_actions=_tool_actions(
                    edit=(15, 3), multi_edit=(5, 2), notebook_edit=(2, 1)
                ),
            ),
            cowork_metrics=MockCoworkMetrics(
                message_count=0, distinct_session_count=0, action_count=0
            ),
            design_metrics=MockDesignMetrics(
                message_count=0,
                distinct_session_count=0,
                distinct_projects_used_count=0,
            ),
            office_metrics=_office_metrics(),
            science_metrics=MockScienceMetrics(
                message_count=0,
                distinct_session_count=0,
                delegation_count=0,
                remote_compute_job_count=0,
            ),
            web_search_count=1,
        ),
        MockUserActivityRecord(
            reporting_date=reporting_date,
            user=MockAnalyticsUser(
                id="mock_user_004", email_address="devon.harbor@example.com"
            ),
            organizational_groups=("Synthetic Research", "Synthetic Design"),
            chat_metrics=MockChatMetrics(
                message_count=8, distinct_conversation_count=3
            ),
            claude_code_metrics=_code_metrics(),
            cowork_metrics=MockCoworkMetrics(
                message_count=5, distinct_session_count=2, action_count=6
            ),
            design_metrics=MockDesignMetrics(
                message_count=11,
                distinct_session_count=4,
                distinct_projects_used_count=2,
            ),
            office_metrics=_office_metrics(excel=(6, 2), powerpoint=(4, 1)),
            science_metrics=MockScienceMetrics(
                message_count=10,
                distinct_session_count=3,
                delegation_count=2,
                remote_compute_job_count=1,
            ),
            web_search_count=6,
        ),
        MockUserActivityRecord(
            reporting_date=reporting_date,
            user=MockAnalyticsUser(
                id="mock_user_005", email_address="ellis.meadow@example.com"
            ),
            organizational_groups=(),
            chat_metrics=MockChatMetrics(
                message_count=0, distinct_conversation_count=0
            ),
            claude_code_metrics=_code_metrics(),
            cowork_metrics=MockCoworkMetrics(
                message_count=0, distinct_session_count=0, action_count=0
            ),
            design_metrics=MockDesignMetrics(
                message_count=0,
                distinct_session_count=0,
                distinct_projects_used_count=0,
            ),
            office_metrics=_office_metrics(),
            science_metrics=MockScienceMetrics(
                message_count=0,
                distinct_session_count=0,
                delegation_count=0,
                remote_compute_job_count=0,
            ),
            web_search_count=0,
        ),
    )

    if len(records) != 5:  # pragma: no cover - protects the sample invariant
        raise AssertionError("synthetic usage must contain exactly five users")
    return records


class MockAnalyticsClient:
    """Asynchronous analytics client backed only by synthetic data."""

    @property
    def provider(self) -> ProviderName:
        """Return the mock provider identifier."""

        return ProviderName.MOCK

    async def get_usage_analytics(
        self, reporting_date: date
    ) -> tuple[MockUserActivityRecord, ...]:
        """Return the complete synthetic sample for the requested UTC date."""

        return build_synthetic_usage(reporting_date)
