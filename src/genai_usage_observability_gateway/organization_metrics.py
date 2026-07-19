"""Privacy-safe organization metric instruments.

Every instrument and non-standard attribute in this module is custom project
telemetry. None is presented as an official OpenTelemetry semantic convention.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from opentelemetry.sdk.metrics import MeterProvider

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationActivityTotals,
    AnthropicOrganizationUsageSummary,
    MockOrganizationActivityTotals,
    MockOrganizationUsageSummary,
    OfficeProductActivityTotals,
)
from genai_usage_observability_gateway.config import (
    DeploymentEnvironment,
    ProviderName,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    DEPLOYMENT_ENVIRONMENT_NAME,
    PROVIDER_ATTRIBUTE,
    REPORTING_DATE_ATTRIBUTE,
    TELEMETRY_SOURCE,
    TELEMETRY_SOURCE_VALUE,
)

METER_NAME = "genai_usage_observability_gateway.organization_metrics"


class GaugeInstrument(Protocol):
    """The synchronous gauge operation used by the emitter."""

    def set(
        self,
        amount: int | float,
        attributes: dict[str, str] | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class OrganizationMetricSpec:
    """Definition of one custom organization gauge."""

    name: str
    unit: str
    description: str


GENERIC_ORGANIZATION_METRICS = (
    OrganizationMetricSpec(
        "genai.usage.organization.user.count",
        "{user}",
        "Users represented in the provider report for one UTC date.",
    ),
    OrganizationMetricSpec(
        "genai.usage.organization.active_user.count",
        "{user}",
        "Users meeting the provider-independent normalized active-user contract.",
    ),
    OrganizationMetricSpec(
        "genai.usage.organization.chat_interaction.count",
        "{interaction}",
        "Normalized chat interactions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "genai.usage.organization.developer_session.count",
        "{session}",
        "Normalized developer sessions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "genai.usage.organization.tool_action.accepted.count",
        "{action}",
        "Normalized accepted tool actions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "genai.usage.organization.tool_action.rejected.count",
        "{action}",
        "Normalized rejected tool actions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "genai.usage.organization.tool_action.acceptance_ratio",
        "1",
        "Accepted tool actions divided by all observed tool actions.",
    ),
)

_ANTHROPIC_BASE_METRICS = (
    OrganizationMetricSpec(
        "anthropic.usage.organization.claude_code.commit.count",
        "{commit}",
        "Anthropic Claude Code commits for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.claude_code.pull_request.count",
        "{pull_request}",
        "Anthropic Claude Code pull requests for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.claude_code.line.added.count",
        "{line}",
        "Anthropic Claude Code added lines for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.claude_code.line.removed.count",
        "{line}",
        "Anthropic Claude Code removed lines for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.cowork.action.count",
        "{action}",
        "Anthropic Cowork actions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.cowork.connector_invocation.count",
        "{invocation}",
        "Anthropic Cowork connector invocations for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.cowork.dispatch_turn.count",
        "{turn}",
        "Anthropic Cowork dispatch turns for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.cowork.message.count",
        "{message}",
        "Anthropic Cowork messages for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.cowork.session.count",
        "{session}",
        "Anthropic Cowork sessions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.cowork.skill_invocation.count",
        "{invocation}",
        "Anthropic Cowork skill invocations for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.design.message.count",
        "{message}",
        "Anthropic Claude Design messages for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.design.project_created.count",
        "{project}",
        "Anthropic Claude Design projects created for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.design.session.count",
        "{session}",
        "Anthropic Claude Design sessions for the organization and UTC date.",
    ),
)

_OFFICE_PRODUCTS = ("excel", "outlook", "powerpoint", "word")
_OFFICE_ACTIVITIES = (
    ("connector_invocation", "{invocation}"),
    ("message", "{message}"),
    ("session", "{session}"),
    ("skill_invocation", "{invocation}"),
)
_ANTHROPIC_OFFICE_METRICS = tuple(
    OrganizationMetricSpec(
        f"anthropic.usage.organization.office.{product}.{activity}.count",
        unit,
        f"Anthropic Office {product} {activity.replace('_', ' ')}s "
        "for the organization and UTC date.",
    )
    for product in _OFFICE_PRODUCTS
    for activity, unit in _OFFICE_ACTIVITIES
)

_ANTHROPIC_TRAILING_METRICS = (
    OrganizationMetricSpec(
        "anthropic.usage.organization.science.delegation.count",
        "{delegation}",
        "Anthropic Claude Science delegations for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.science.message.count",
        "{message}",
        "Anthropic Claude Science messages for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.science.remote_compute_job.count",
        "{job}",
        "Anthropic Claude Science remote jobs for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.science.session.count",
        "{session}",
        "Anthropic Claude Science sessions for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.science.skill_invocation.count",
        "{invocation}",
        "Anthropic Claude Science skill invocations for the organization and UTC date.",
    ),
    OrganizationMetricSpec(
        "anthropic.usage.organization.web_search.count",
        "{search}",
        "Anthropic web searches for the organization and UTC date.",
    ),
)

ANTHROPIC_ORGANIZATION_METRICS = (
    _ANTHROPIC_BASE_METRICS + _ANTHROPIC_OFFICE_METRICS + _ANTHROPIC_TRAILING_METRICS
)
ALL_ORGANIZATION_METRICS = GENERIC_ORGANIZATION_METRICS + ANTHROPIC_ORGANIZATION_METRICS


def _office_values(product: str, totals: OfficeProductActivityTotals) -> dict[str, int]:
    prefix = f"anthropic.usage.organization.office.{product}"
    return {
        f"{prefix}.connector_invocation.count": totals.connector_invocation_count,
        f"{prefix}.message.count": totals.message_count,
        f"{prefix}.session.count": totals.session_count,
        f"{prefix}.skill_invocation.count": totals.skill_invocation_count,
    }


OrganizationSummary = AnthropicOrganizationUsageSummary | MockOrganizationUsageSummary


def _generic_metric_values(
    summary: OrganizationSummary,
) -> dict[str, int | float]:
    return {
        "genai.usage.organization.user.count": summary.total_users,
        "genai.usage.organization.active_user.count": summary.active_users,
        "genai.usage.organization.chat_interaction.count": (
            summary.chat_interaction_count
        ),
        "genai.usage.organization.developer_session.count": (
            summary.developer_session_count
        ),
        "genai.usage.organization.tool_action.accepted.count": (
            summary.accepted_tool_action_count
        ),
        "genai.usage.organization.tool_action.rejected.count": (
            summary.rejected_tool_action_count
        ),
        "genai.usage.organization.tool_action.acceptance_ratio": (
            summary.tool_action_acceptance_rate
        ),
    }


def _anthropic_metric_values(
    summary: AnthropicOrganizationUsageSummary,
) -> dict[str, int | float]:
    provider = summary.provider_activity
    science = provider.science
    values: dict[str, int | float] = {
        "anthropic.usage.organization.claude_code.commit.count": (
            provider.commit_count
        ),
        "anthropic.usage.organization.claude_code.pull_request.count": (
            provider.pull_request_count
        ),
        "anthropic.usage.organization.claude_code.line.added.count": (
            provider.lines_added_count
        ),
        "anthropic.usage.organization.claude_code.line.removed.count": (
            provider.lines_removed_count
        ),
        "anthropic.usage.organization.cowork.action.count": (
            provider.cowork.action_count
        ),
        "anthropic.usage.organization.cowork.connector_invocation.count": (
            provider.cowork.connector_invocation_count
        ),
        "anthropic.usage.organization.cowork.dispatch_turn.count": (
            provider.cowork.dispatch_turn_count
        ),
        "anthropic.usage.organization.cowork.message.count": (
            provider.cowork.message_count
        ),
        "anthropic.usage.organization.cowork.session.count": (
            provider.cowork.session_count
        ),
        "anthropic.usage.organization.cowork.skill_invocation.count": (
            provider.cowork.skill_invocation_count
        ),
        "anthropic.usage.organization.design.message.count": (
            provider.design.message_count
        ),
        "anthropic.usage.organization.design.project_created.count": (
            provider.design.project_created_count
        ),
        "anthropic.usage.organization.design.session.count": (
            provider.design.session_count
        ),
        "anthropic.usage.organization.science.delegation.count": (
            science.delegation_count
        ),
        "anthropic.usage.organization.science.message.count": science.message_count,
        "anthropic.usage.organization.science.remote_compute_job.count": (
            science.remote_compute_job_count
        ),
        "anthropic.usage.organization.science.session.count": science.session_count,
        "anthropic.usage.organization.science.skill_invocation.count": (
            science.skill_invocation_count
        ),
        "anthropic.usage.organization.web_search.count": provider.web_search_count,
    }
    for product_name, product_totals in (
        ("excel", provider.office.excel),
        ("outlook", provider.office.outlook),
        ("powerpoint", provider.office.powerpoint),
        ("word", provider.office.word),
    ):
        values.update(_office_values(product_name, product_totals))
    return values


class OrganizationMetricEmitter:
    """Create once and emit identity-free organization gauges per collection."""

    def __init__(
        self,
        meter_provider: MeterProvider,
        deployment_environment: DeploymentEnvironment,
    ) -> None:
        meter = meter_provider.get_meter(METER_NAME, __version__)
        self._deployment_environment = deployment_environment.value
        self._gauges: dict[str, GaugeInstrument] = {
            spec.name: meter.create_gauge(
                spec.name,
                unit=spec.unit,
                description=spec.description,
            )
            for spec in ALL_ORGANIZATION_METRICS
        }

    def emit(self, summary: OrganizationSummary) -> None:
        """Record one complete organization summary with allowlisted attributes."""

        values = _generic_metric_values(summary)
        if summary.provider is ProviderName.ANTHROPIC:
            if not isinstance(
                summary.provider_activity,
                AnthropicOrganizationActivityTotals,
            ):
                raise ValueError("Anthropic metrics require an Anthropic summary")
            values.update(_anthropic_metric_values(summary))
        elif not isinstance(summary.provider_activity, MockOrganizationActivityTotals):
            raise ValueError("mock metrics require a mock summary")
        attributes = {
            REPORTING_DATE_ATTRIBUTE: summary.reporting_date.isoformat(),
            DEPLOYMENT_ENVIRONMENT_NAME: self._deployment_environment,
            TELEMETRY_SOURCE: TELEMETRY_SOURCE_VALUE,
            PROVIDER_ATTRIBUTE: summary.provider.value,
        }
        for name, value in values.items():
            self._gauges[name].set(value, attributes)
