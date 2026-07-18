"""Tests for privacy-safe organization metric emission."""

from dataclasses import dataclass
from typing import cast

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    Gauge,
    InMemoryMetricReader,
)

from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationUsageSummary,
    aggregate_anthropic_usage,
)
from genai_usage_observability_gateway.config import (
    DeploymentEnvironment,
    ProviderName,
)
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    normalize_anthropic_records,
)
from genai_usage_observability_gateway.organization_metrics import (
    ALL_ORGANIZATION_METRICS,
    ANTHROPIC_ORGANIZATION_METRICS,
    GENERIC_ORGANIZATION_METRICS,
    METER_NAME,
    OrganizationMetricEmitter,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    DEPLOYMENT_ENVIRONMENT_NAME,
    ORGANIZATION_METRIC_ATTRIBUTE_KEYS,
    PROVIDER_ATTRIBUTE,
    REPORTING_DATE_ATTRIBUTE,
    TELEMETRY_SOURCE,
    TELEMETRY_SOURCE_VALUE,
)
from tests.factories import (
    anthropic_activity_payload,
    anthropic_record_from_payload,
)


@dataclass(frozen=True)
class ObservedMetric:
    value: int | float
    attributes: dict[str, object]
    unit: str


def _normalized_records() -> tuple[AnthropicNormalizedUsageRecord, ...]:
    payloads = [anthropic_activity_payload(user_number) for user_number in (1, 2)]
    payloads[0]["rbac_group_id"] = "synthetic-private-group-id"
    payloads[0]["rbac_group_name"] = "Synthetic Private Group"
    return normalize_anthropic_records(
        anthropic_record_from_payload(payload) for payload in payloads
    )


def _summary() -> AnthropicOrganizationUsageSummary:
    return aggregate_anthropic_usage(_normalized_records())


def _collect(reader: InMemoryMetricReader) -> dict[str, ObservedMetric]:
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    observed: dict[str, ObservedMetric] = {}
    for resource_metrics in metrics_data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            assert scope_metrics.scope.name == METER_NAME
            for metric in scope_metrics.metrics:
                assert isinstance(metric.data, Gauge)
                assert len(metric.data.data_points) == 1
                point = metric.data.data_points[0]
                assert point.attributes is not None
                assert metric.unit is not None
                observed[metric.name] = ObservedMetric(
                    value=point.value,
                    attributes=cast(dict[str, object], dict(point.attributes)),
                    unit=metric.unit,
                )
    return observed


@pytest.fixture
def emitted_metrics() -> tuple[
    AnthropicOrganizationUsageSummary,
    tuple[AnthropicNormalizedUsageRecord, ...],
    dict[str, ObservedMetric],
]:
    records = _normalized_records()
    summary = aggregate_anthropic_usage(records)
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    emitter = OrganizationMetricEmitter(provider, DeploymentEnvironment.TEST)
    try:
        emitter.emit(summary)
        return summary, records, _collect(reader)
    finally:
        provider.shutdown()


def _expected_values() -> dict[str, int | float]:
    values: dict[str, int | float] = {
        "genai.usage.organization.user.count": 2,
        "genai.usage.organization.active_user.count": 2,
        "genai.usage.organization.chat_interaction.count": 16,
        "genai.usage.organization.developer_session.count": 6,
        "genai.usage.organization.tool_action.accepted.count": 16,
        "genai.usage.organization.tool_action.rejected.count": 8,
        "genai.usage.organization.tool_action.acceptance_ratio": 2 / 3,
        "anthropic.usage.organization.claude_code.commit.count": 4,
        "anthropic.usage.organization.claude_code.pull_request.count": 2,
        "anthropic.usage.organization.claude_code.line.added.count": 40,
        "anthropic.usage.organization.claude_code.line.removed.count": 8,
        "anthropic.usage.organization.cowork.action.count": 8,
        "anthropic.usage.organization.cowork.connector_invocation.count": 4,
        "anthropic.usage.organization.cowork.dispatch_turn.count": 2,
        "anthropic.usage.organization.cowork.message.count": 12,
        "anthropic.usage.organization.cowork.session.count": 6,
        "anthropic.usage.organization.cowork.skill_invocation.count": 6,
        "anthropic.usage.organization.design.message.count": 8,
        "anthropic.usage.organization.design.project_created.count": 2,
        "anthropic.usage.organization.design.session.count": 4,
        "anthropic.usage.organization.science.delegation.count": 2,
        "anthropic.usage.organization.science.message.count": 6,
        "anthropic.usage.organization.science.remote_compute_job.count": 2,
        "anthropic.usage.organization.science.session.count": 4,
        "anthropic.usage.organization.science.skill_invocation.count": 4,
        "anthropic.usage.organization.web_search.count": 4,
    }
    for product in ("excel", "outlook", "powerpoint", "word"):
        prefix = f"anthropic.usage.organization.office.{product}"
        values.update(
            {
                f"{prefix}.connector_invocation.count": 4,
                f"{prefix}.message.count": 10,
                f"{prefix}.session.count": 6,
                f"{prefix}.skill_invocation.count": 4,
            }
        )
    return values


def test_metric_names_and_values_match_the_complete_summary(
    emitted_metrics: tuple[
        AnthropicOrganizationUsageSummary,
        tuple[AnthropicNormalizedUsageRecord, ...],
        dict[str, ObservedMetric],
    ],
) -> None:
    _, _, observed = emitted_metrics
    expected = _expected_values()

    assert len(GENERIC_ORGANIZATION_METRICS) == 7
    assert len(ANTHROPIC_ORGANIZATION_METRICS) == 35
    assert {spec.name for spec in ALL_ORGANIZATION_METRICS} == set(expected)
    assert set(observed) == set(expected)
    for name, expected_value in expected.items():
        assert observed[name].value == pytest.approx(expected_value)


def test_metrics_use_declared_units(
    emitted_metrics: tuple[
        AnthropicOrganizationUsageSummary,
        tuple[AnthropicNormalizedUsageRecord, ...],
        dict[str, ObservedMetric],
    ],
) -> None:
    _, _, observed = emitted_metrics

    assert {name: metric.unit for name, metric in observed.items()} == {
        spec.name: spec.unit for spec in ALL_ORGANIZATION_METRICS
    }


def test_every_metric_has_only_allowlisted_low_cardinality_attributes(
    emitted_metrics: tuple[
        AnthropicOrganizationUsageSummary,
        tuple[AnthropicNormalizedUsageRecord, ...],
        dict[str, ObservedMetric],
    ],
) -> None:
    summary, _, observed = emitted_metrics
    expected_attributes = {
        REPORTING_DATE_ATTRIBUTE: summary.reporting_date.isoformat(),
        DEPLOYMENT_ENVIRONMENT_NAME: "test",
        TELEMETRY_SOURCE: TELEMETRY_SOURCE_VALUE,
        PROVIDER_ATTRIBUTE: "anthropic",
    }

    assert set(expected_attributes) == ORGANIZATION_METRIC_ATTRIBUTE_KEYS
    for metric in observed.values():
        assert metric.attributes == expected_attributes


def test_metric_output_contains_no_identity_group_or_secret_data(
    emitted_metrics: tuple[
        AnthropicOrganizationUsageSummary,
        tuple[AnthropicNormalizedUsageRecord, ...],
        dict[str, ObservedMetric],
    ],
) -> None:
    _, records, observed = emitted_metrics
    serialized = repr(observed)

    for record in records:
        assert record.identity.provider_user_id not in serialized
        assert str(record.identity.email) not in serialized
    for forbidden in (
        "synthetic-private-group-id",
        "Synthetic Private Group",
        "pseudonymous_user_id",
        "file.path",
        "http.url",
        "api.endpoint",
        "credential",
        "authorization",
    ):
        assert forbidden not in serialized


def test_repeated_emission_replaces_daily_gauge_values_instead_of_accumulating() -> (
    None
):
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    emitter = OrganizationMetricEmitter(provider, DeploymentEnvironment.TEST)
    summary = _summary()
    updated = summary.model_copy(update={"total_users": 3})
    try:
        emitter.emit(summary)
        emitter.emit(updated)
        observed = _collect(reader)
    finally:
        provider.shutdown()

    assert observed["genai.usage.organization.user.count"].value == 3


def test_anthropic_instruments_reject_mismatched_provider() -> None:
    reader = InMemoryMetricReader()
    provider = MeterProvider(metric_readers=[reader], shutdown_on_exit=False)
    emitter = OrganizationMetricEmitter(provider, DeploymentEnvironment.TEST)
    mismatched = _summary().model_copy(update={"provider": ProviderName.MOCK})
    try:
        with pytest.raises(ValueError, match="require an Anthropic summary"):
            emitter.emit(mismatched)
    finally:
        provider.shutdown()
