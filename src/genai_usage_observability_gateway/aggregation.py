"""Validated organization-level aggregation of normalized usage records."""

from collections.abc import Iterable, Sequence
from datetime import date
from typing import Annotated, Generic, TypeVar

from pydantic import Field

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models.usage import (
    NonNegativeCount,
    StrictDomainModel,
)
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    AnthropicUsageExtension,
    MockNormalizedUsageRecord,
    MockUsageExtension,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicOfficeProductMetrics,
)
from genai_usage_observability_gateway.providers.mock import MockOfficeProductMetrics

AcceptanceRate = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class AggregationError(ValueError):
    """Base error for collections that cannot be aggregated honestly."""


class EmptyAggregationError(AggregationError):
    """Aggregation requires at least one normalized record."""


class MixedReportingDatesError(AggregationError):
    """Records from multiple UTC reporting dates cannot be combined."""


class DuplicateProviderUserError(AggregationError):
    """A provider user appears more than once for the reporting date."""


class IncompatibleProviderError(AggregationError):
    """A record is incompatible with the selected provider aggregation."""


class UnavailableCommonMetricError(AggregationError):
    """A required common metric is unavailable on an input record."""


class CoworkActivityTotals(StrictDomainModel):
    """Additive organization Cowork activity."""

    action_count: NonNegativeCount
    connector_invocation_count: NonNegativeCount
    dispatch_turn_count: NonNegativeCount
    message_count: NonNegativeCount
    session_count: NonNegativeCount
    skill_invocation_count: NonNegativeCount


class DesignActivityTotals(StrictDomainModel):
    """Additive organization Claude Design activity."""

    message_count: NonNegativeCount
    project_created_count: NonNegativeCount
    session_count: NonNegativeCount


class OfficeProductActivityTotals(StrictDomainModel):
    """Additive organization activity for one Office product."""

    connector_invocation_count: NonNegativeCount
    message_count: NonNegativeCount
    session_count: NonNegativeCount
    skill_invocation_count: NonNegativeCount


class OfficeActivityTotals(StrictDomainModel):
    """Additive organization Office activity by product."""

    excel: OfficeProductActivityTotals
    outlook: OfficeProductActivityTotals
    powerpoint: OfficeProductActivityTotals
    word: OfficeProductActivityTotals


class ScienceActivityTotals(StrictDomainModel):
    """Additive organization Claude Science activity."""

    delegation_count: NonNegativeCount
    message_count: NonNegativeCount
    remote_compute_job_count: NonNegativeCount
    session_count: NonNegativeCount
    skill_invocation_count: NonNegativeCount


class ProviderOrganizationActivityTotals(StrictDomainModel):
    """Base for additive totals that retain provider-specific semantics."""


class AnthropicOrganizationActivityTotals(ProviderOrganizationActivityTotals):
    """Anthropic-specific organization totals with unambiguous semantics."""

    commit_count: NonNegativeCount
    pull_request_count: NonNegativeCount
    lines_added_count: NonNegativeCount
    lines_removed_count: NonNegativeCount
    cowork: CoworkActivityTotals
    design: DesignActivityTotals
    office: OfficeActivityTotals
    science: ScienceActivityTotals
    web_search_count: NonNegativeCount


class MockCoworkActivityTotals(StrictDomainModel):
    """Additive synthetic Cowork activity exposed by the mock schema."""

    action_count: NonNegativeCount
    message_count: NonNegativeCount
    session_count: NonNegativeCount


class MockDesignActivityTotals(StrictDomainModel):
    """Additive synthetic Design activity exposed by the mock schema."""

    message_count: NonNegativeCount
    project_used_count: NonNegativeCount
    session_count: NonNegativeCount


class MockOfficeProductActivityTotals(StrictDomainModel):
    """Additive synthetic Office activity for one product."""

    message_count: NonNegativeCount
    session_count: NonNegativeCount


class MockOfficeActivityTotals(StrictDomainModel):
    """Additive synthetic Office activity by product."""

    excel: MockOfficeProductActivityTotals
    outlook: MockOfficeProductActivityTotals
    powerpoint: MockOfficeProductActivityTotals
    word: MockOfficeProductActivityTotals


class MockScienceActivityTotals(StrictDomainModel):
    """Additive synthetic Science activity exposed by the mock schema."""

    delegation_count: NonNegativeCount
    message_count: NonNegativeCount
    remote_compute_job_count: NonNegativeCount
    session_count: NonNegativeCount


class MockOrganizationActivityTotals(ProviderOrganizationActivityTotals):
    """Synthetic provider totals retained under a mock-labeled summary."""

    commit_count: NonNegativeCount
    pull_request_count: NonNegativeCount
    lines_added_count: NonNegativeCount
    lines_removed_count: NonNegativeCount
    cowork: MockCoworkActivityTotals
    design: MockDesignActivityTotals
    office: MockOfficeActivityTotals
    science: MockScienceActivityTotals
    web_search_count: NonNegativeCount


ProviderActivityT = TypeVar(
    "ProviderActivityT",
    bound=ProviderOrganizationActivityTotals,
    default=ProviderOrganizationActivityTotals,
)


class OrganizationUsageSummary(StrictDomainModel, Generic[ProviderActivityT]):
    """Privacy-safe organization totals for one provider and UTC date."""

    reporting_date: date
    provider: ProviderName
    total_users: NonNegativeCount
    active_users: NonNegativeCount
    chat_interaction_count: NonNegativeCount
    developer_session_count: NonNegativeCount
    accepted_tool_action_count: NonNegativeCount
    rejected_tool_action_count: NonNegativeCount
    tool_action_acceptance_rate: AcceptanceRate
    provider_activity: ProviderActivityT


AnthropicOrganizationUsageSummary = OrganizationUsageSummary[
    AnthropicOrganizationActivityTotals
]
MockOrganizationUsageSummary = OrganizationUsageSummary[MockOrganizationActivityTotals]


def _sum_available(values: Iterable[int | None], metric_name: str) -> int:
    total = 0
    for value in values:
        if value is None:
            raise UnavailableCommonMetricError(
                f"{metric_name} is unavailable for an input record"
            )
        total += value
    return total


def _validated_extensions(
    records: Sequence[AnthropicNormalizedUsageRecord],
) -> tuple[AnthropicUsageExtension, ...]:
    extensions: list[AnthropicUsageExtension] = []
    for record in records:
        if record.provider is not ProviderName.ANTHROPIC:
            raise IncompatibleProviderError(
                "organization aggregation requires only Anthropic records"
            )
        extension = record.provider_extension
        if not isinstance(extension, AnthropicUsageExtension):
            raise IncompatibleProviderError(
                "normalized Anthropic record is missing its provider extension"
            )
        extensions.append(extension)
    return tuple(extensions)


def _validate_collection(
    records: Sequence[AnthropicNormalizedUsageRecord],
) -> tuple[date, tuple[AnthropicUsageExtension, ...]]:
    if not records:
        raise EmptyAggregationError("organization aggregation requires records")

    reporting_date = records[0].reporting_date
    if any(record.reporting_date != reporting_date for record in records[1:]):
        raise MixedReportingDatesError(
            "organization aggregation requires one reporting date"
        )

    user_ids: set[str] = set()
    for record in records:
        user_id = record.identity.provider_user_id
        if user_id in user_ids:
            raise DuplicateProviderUserError(
                "duplicate provider user identifier for reporting date"
            )
        user_ids.add(user_id)

    return reporting_date, _validated_extensions(records)


def _office_product_totals(
    products: Iterable[AnthropicOfficeProductMetrics],
) -> OfficeProductActivityTotals:
    product_list = tuple(products)
    return OfficeProductActivityTotals(
        connector_invocation_count=sum(
            product.connectors_used_count for product in product_list
        ),
        message_count=sum(product.message_count for product in product_list),
        session_count=sum(product.distinct_session_count for product in product_list),
        skill_invocation_count=sum(
            product.skills_used_count for product in product_list
        ),
    )


def aggregate_anthropic_usage(
    records: Sequence[AnthropicNormalizedUsageRecord],
) -> AnthropicOrganizationUsageSummary:
    """Aggregate one date of unique Anthropic users without identity fields."""

    reporting_date, extensions = _validate_collection(records)
    accepted_actions = _sum_available(
        (record.activity.accepted_tool_action_count for record in records),
        "accepted tool action count",
    )
    rejected_actions = _sum_available(
        (record.activity.rejected_tool_action_count for record in records),
        "rejected tool action count",
    )
    total_actions = accepted_actions + rejected_actions
    acceptance_rate = accepted_actions / total_actions if total_actions else 0.0

    return AnthropicOrganizationUsageSummary(
        reporting_date=reporting_date,
        provider=ProviderName.ANTHROPIC,
        total_users=len(records),
        active_users=sum(record.activity.is_active for record in records),
        chat_interaction_count=_sum_available(
            (record.activity.chat_interaction_count for record in records),
            "chat interaction count",
        ),
        developer_session_count=_sum_available(
            (record.activity.developer_session_count for record in records),
            "developer session count",
        ),
        accepted_tool_action_count=accepted_actions,
        rejected_tool_action_count=rejected_actions,
        tool_action_acceptance_rate=acceptance_rate,
        provider_activity=AnthropicOrganizationActivityTotals(
            commit_count=sum(
                extension.claude_code_metrics.core_metrics.commit_count
                for extension in extensions
            ),
            pull_request_count=sum(
                extension.claude_code_metrics.core_metrics.pull_request_count
                for extension in extensions
            ),
            lines_added_count=sum(
                extension.claude_code_metrics.core_metrics.lines_of_code.added_count
                for extension in extensions
            ),
            lines_removed_count=sum(
                extension.claude_code_metrics.core_metrics.lines_of_code.removed_count
                for extension in extensions
            ),
            cowork=CoworkActivityTotals(
                action_count=sum(
                    extension.cowork_metrics.action_count for extension in extensions
                ),
                connector_invocation_count=sum(
                    extension.cowork_metrics.connectors_used_count
                    for extension in extensions
                ),
                dispatch_turn_count=sum(
                    extension.cowork_metrics.dispatch_turn_count
                    for extension in extensions
                ),
                message_count=sum(
                    extension.cowork_metrics.message_count for extension in extensions
                ),
                session_count=sum(
                    extension.cowork_metrics.distinct_session_count
                    for extension in extensions
                ),
                skill_invocation_count=sum(
                    extension.cowork_metrics.skills_used_count
                    for extension in extensions
                ),
            ),
            design=DesignActivityTotals(
                message_count=sum(
                    extension.design_metrics.message_count for extension in extensions
                ),
                project_created_count=sum(
                    extension.design_metrics.distinct_projects_created_count
                    for extension in extensions
                ),
                session_count=sum(
                    extension.design_metrics.distinct_session_count
                    for extension in extensions
                ),
            ),
            office=OfficeActivityTotals(
                excel=_office_product_totals(
                    extension.office_metrics.excel for extension in extensions
                ),
                outlook=_office_product_totals(
                    extension.office_metrics.outlook for extension in extensions
                ),
                powerpoint=_office_product_totals(
                    extension.office_metrics.powerpoint for extension in extensions
                ),
                word=_office_product_totals(
                    extension.office_metrics.word for extension in extensions
                ),
            ),
            science=ScienceActivityTotals(
                delegation_count=sum(
                    extension.science_metrics.delegation_count
                    for extension in extensions
                ),
                message_count=sum(
                    extension.science_metrics.message_count for extension in extensions
                ),
                remote_compute_job_count=sum(
                    extension.science_metrics.remote_compute_job_count
                    for extension in extensions
                ),
                session_count=sum(
                    extension.science_metrics.distinct_session_count
                    for extension in extensions
                ),
                skill_invocation_count=sum(
                    extension.science_metrics.skills_used_count
                    for extension in extensions
                ),
            ),
            web_search_count=sum(
                extension.web_search_count for extension in extensions
            ),
        ),
    )


def _validated_mock_collection(
    records: Sequence[MockNormalizedUsageRecord],
) -> tuple[date, tuple[MockUsageExtension, ...]]:
    if not records:
        raise EmptyAggregationError("organization aggregation requires records")
    reporting_date = records[0].reporting_date
    if any(record.reporting_date != reporting_date for record in records[1:]):
        raise MixedReportingDatesError(
            "organization aggregation requires one reporting date"
        )

    extensions: list[MockUsageExtension] = []
    user_ids: set[str] = set()
    for record in records:
        user_id = record.identity.provider_user_id
        if user_id in user_ids:
            raise DuplicateProviderUserError(
                "duplicate provider user identifier for reporting date"
            )
        user_ids.add(user_id)
        extension = record.provider_extension
        if record.provider is not ProviderName.MOCK or not isinstance(
            extension, MockUsageExtension
        ):
            raise IncompatibleProviderError(
                "organization aggregation requires only mock records"
            )
        extensions.append(extension)
    return reporting_date, tuple(extensions)


def _mock_office_product_totals(
    products: Iterable[MockOfficeProductMetrics],
) -> MockOfficeProductActivityTotals:
    product_list = tuple(products)
    return MockOfficeProductActivityTotals(
        message_count=sum(product.message_count for product in product_list),
        session_count=sum(product.distinct_session_count for product in product_list),
    )


def aggregate_mock_usage(
    records: Sequence[MockNormalizedUsageRecord],
) -> MockOrganizationUsageSummary:
    """Aggregate one date of unique fictional users without identity fields."""

    reporting_date, extensions = _validated_mock_collection(records)
    accepted_actions = _sum_available(
        (record.activity.accepted_tool_action_count for record in records),
        "accepted tool action count",
    )
    rejected_actions = _sum_available(
        (record.activity.rejected_tool_action_count for record in records),
        "rejected tool action count",
    )
    total_actions = accepted_actions + rejected_actions
    acceptance_rate = accepted_actions / total_actions if total_actions else 0.0

    return MockOrganizationUsageSummary(
        reporting_date=reporting_date,
        provider=ProviderName.MOCK,
        total_users=len(records),
        active_users=sum(record.activity.is_active for record in records),
        chat_interaction_count=_sum_available(
            (record.activity.chat_interaction_count for record in records),
            "chat interaction count",
        ),
        developer_session_count=_sum_available(
            (record.activity.developer_session_count for record in records),
            "developer session count",
        ),
        accepted_tool_action_count=accepted_actions,
        rejected_tool_action_count=rejected_actions,
        tool_action_acceptance_rate=acceptance_rate,
        provider_activity=MockOrganizationActivityTotals(
            commit_count=sum(
                extension.claude_code_metrics.commit_count for extension in extensions
            ),
            pull_request_count=sum(
                extension.claude_code_metrics.pull_request_count
                for extension in extensions
            ),
            lines_added_count=sum(
                extension.claude_code_metrics.lines_of_code.added_count
                for extension in extensions
            ),
            lines_removed_count=sum(
                extension.claude_code_metrics.lines_of_code.removed_count
                for extension in extensions
            ),
            cowork=MockCoworkActivityTotals(
                action_count=sum(
                    extension.cowork_metrics.action_count for extension in extensions
                ),
                message_count=sum(
                    extension.cowork_metrics.message_count for extension in extensions
                ),
                session_count=sum(
                    extension.cowork_metrics.distinct_session_count
                    for extension in extensions
                ),
            ),
            design=MockDesignActivityTotals(
                message_count=sum(
                    extension.design_metrics.message_count for extension in extensions
                ),
                project_used_count=sum(
                    extension.design_metrics.distinct_projects_used_count
                    for extension in extensions
                ),
                session_count=sum(
                    extension.design_metrics.distinct_session_count
                    for extension in extensions
                ),
            ),
            office=MockOfficeActivityTotals(
                excel=_mock_office_product_totals(
                    extension.office_metrics.excel for extension in extensions
                ),
                outlook=_mock_office_product_totals(
                    extension.office_metrics.outlook for extension in extensions
                ),
                powerpoint=_mock_office_product_totals(
                    extension.office_metrics.powerpoint for extension in extensions
                ),
                word=_mock_office_product_totals(
                    extension.office_metrics.word for extension in extensions
                ),
            ),
            science=MockScienceActivityTotals(
                delegation_count=sum(
                    extension.science_metrics.delegation_count
                    for extension in extensions
                ),
                message_count=sum(
                    extension.science_metrics.message_count for extension in extensions
                ),
                remote_compute_job_count=sum(
                    extension.science_metrics.remote_compute_job_count
                    for extension in extensions
                ),
                session_count=sum(
                    extension.science_metrics.distinct_session_count
                    for extension in extensions
                ),
            ),
            web_search_count=sum(
                extension.web_search_count for extension in extensions
            ),
        ),
    )
