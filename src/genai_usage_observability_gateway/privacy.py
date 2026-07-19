"""Privacy boundary for pseudonymous usage export data."""

from __future__ import annotations

import hmac
from collections.abc import Sequence
from datetime import date
from hashlib import sha256
from typing import Annotated, Generic, TypeVar

from pydantic import Field, SecretStr, model_validator

from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationUsageSummary,
    MockOrganizationUsageSummary,
    aggregate_anthropic_usage,
    aggregate_mock_usage,
)
from genai_usage_observability_gateway.config import AppSettings, ProviderName
from genai_usage_observability_gateway.models.usage import (
    CommonUsageActivity,
    NonNegativeCount,
    ProviderUsageExtension,
    StrictDomainModel,
)
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    AnthropicUsageExtension,
    MockNormalizedUsageRecord,
    MockUsageExtension,
)
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicChatMetrics,
    AnthropicClaudeCodeMetrics,
    AnthropicCoworkMetrics,
    AnthropicDesignMetrics,
    AnthropicOfficeMetrics,
    AnthropicScienceMetrics,
)
from genai_usage_observability_gateway.providers.mock import (
    MockChatMetrics,
    MockClaudeCodeMetrics,
    MockCoworkMetrics,
    MockDesignMetrics,
    MockOfficeMetrics,
    MockScienceMetrics,
)

PseudonymousIdentifier = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]


class PseudonymizationKeyRequiredError(ValueError):
    """Pseudonymization cannot run without a configured secret."""


class HmacSha256Pseudonymizer:
    """Generate stable provider-namespaced pseudonyms without exposing the key."""

    __slots__ = ("_key",)

    def __init__(self, key: SecretStr) -> None:
        if not key.get_secret_value().strip():
            raise PseudonymizationKeyRequiredError(
                "pseudonymization key must not be empty"
            )
        self._key = key

    @classmethod
    def from_settings(cls, settings: AppSettings) -> HmacSha256Pseudonymizer:
        """Build from validated settings without returning or logging the secret."""

        if settings.pseudonymization_key is None:
            raise PseudonymizationKeyRequiredError(
                "PSEUDONYMIZATION_KEY is required for privacy processing"
            )
        return cls(settings.pseudonymization_key)

    def __repr__(self) -> str:
        return "HmacSha256Pseudonymizer(key=**********)"

    def pseudonymize(self, provider: ProviderName, provider_user_id: str) -> str:
        """Return the first sixteen hexadecimal characters of an HMAC-SHA256."""

        if not provider_user_id.strip():
            raise ValueError("provider user identifier must not be empty")
        message = f"{provider.value}:{provider_user_id}".encode()
        digest = hmac.new(
            self._key.get_secret_value().encode(),
            message,
            digestmod=sha256,
        ).hexdigest()
        return digest[:16]


class AnthropicPrivacySafeExtension(ProviderUsageExtension):
    """Anthropic activity explicitly approved for export after privacy review."""

    chat_metrics: AnthropicChatMetrics
    claude_code_metrics: AnthropicClaudeCodeMetrics
    cowork_metrics: AnthropicCoworkMetrics
    design_metrics: AnthropicDesignMetrics
    office_metrics: AnthropicOfficeMetrics
    science_metrics: AnthropicScienceMetrics
    web_search_count: NonNegativeCount
    last_activity_date: date | None = None


class MockPrivacySafeExtension(ProviderUsageExtension):
    """Synthetic activity explicitly approved beyond the privacy boundary."""

    chat_metrics: MockChatMetrics
    claude_code_metrics: MockClaudeCodeMetrics
    cowork_metrics: MockCoworkMetrics
    design_metrics: MockDesignMetrics
    office_metrics: MockOfficeMetrics
    science_metrics: MockScienceMetrics
    web_search_count: NonNegativeCount


PrivacyExtensionT = TypeVar(
    "PrivacyExtensionT",
    bound=ProviderUsageExtension,
    default=ProviderUsageExtension,
)


class PrivacySafeUsageRecord(StrictDomainModel, Generic[PrivacyExtensionT]):
    """Usage record with no raw identity fields."""

    reporting_date: date
    provider: ProviderName
    pseudonymous_user_id: PseudonymousIdentifier
    activity: CommonUsageActivity
    provider_extension: PrivacyExtensionT


AnthropicPrivacySafeUsageRecord = PrivacySafeUsageRecord[AnthropicPrivacySafeExtension]
MockPrivacySafeUsageRecord = PrivacySafeUsageRecord[MockPrivacySafeExtension]


class PrivacySafeCollectionMetadata(StrictDomainModel):
    """Low-cardinality collection context suitable for future trace attributes."""

    reporting_date: date
    provider: ProviderName
    record_count: NonNegativeCount


class AnthropicPrivacySafeCollection(StrictDomainModel):
    """Sanitized source data for future telemetry and preview generation."""

    metadata: PrivacySafeCollectionMetadata
    organization_summary: AnthropicOrganizationUsageSummary
    usage_records: tuple[AnthropicPrivacySafeUsageRecord, ...]

    @model_validator(mode="after")
    def validate_consistency(self) -> AnthropicPrivacySafeCollection:
        """Reject inconsistent dates, providers, counts, or pseudonyms."""

        summary = self.organization_summary
        if (
            summary.reporting_date != self.metadata.reporting_date
            or summary.provider is not self.metadata.provider
        ):
            raise ValueError("collection metadata does not match organization summary")
        if (
            len(self.usage_records) != self.metadata.record_count
            or summary.total_users != self.metadata.record_count
        ):
            raise ValueError("collection record counts are inconsistent")
        if any(
            record.reporting_date != self.metadata.reporting_date
            or record.provider is not self.metadata.provider
            for record in self.usage_records
        ):
            raise ValueError("collection records do not match collection metadata")
        pseudonyms = {record.pseudonymous_user_id for record in self.usage_records}
        if len(pseudonyms) != len(self.usage_records):
            raise ValueError("collection contains duplicate pseudonymous identifiers")
        return self


class MockPrivacySafeCollection(StrictDomainModel):
    """Sanitized synthetic source for telemetry and preview generation."""

    metadata: PrivacySafeCollectionMetadata
    organization_summary: MockOrganizationUsageSummary
    usage_records: tuple[MockPrivacySafeUsageRecord, ...]

    @model_validator(mode="after")
    def validate_consistency(self) -> MockPrivacySafeCollection:
        """Reject inconsistent dates, providers, counts, or pseudonyms."""

        summary = self.organization_summary
        if (
            summary.reporting_date != self.metadata.reporting_date
            or summary.provider is not self.metadata.provider
        ):
            raise ValueError("collection metadata does not match organization summary")
        if (
            len(self.usage_records) != self.metadata.record_count
            or summary.total_users != self.metadata.record_count
        ):
            raise ValueError("collection record counts are inconsistent")
        if any(
            record.reporting_date != self.metadata.reporting_date
            or record.provider is not self.metadata.provider
            for record in self.usage_records
        ):
            raise ValueError("collection records do not match collection metadata")
        pseudonyms = {record.pseudonymous_user_id for record in self.usage_records}
        if len(pseudonyms) != len(self.usage_records):
            raise ValueError("collection contains duplicate pseudonymous identifiers")
        return self


def protect_anthropic_record(
    record: AnthropicNormalizedUsageRecord,
    pseudonymizer: HmacSha256Pseudonymizer,
) -> AnthropicPrivacySafeUsageRecord:
    """Remove raw identity and copy only explicitly approved provider activity."""

    extension = record.provider_extension
    if record.provider is not ProviderName.ANTHROPIC or not isinstance(
        extension, AnthropicUsageExtension
    ):
        raise ValueError("privacy processing requires a normalized Anthropic record")

    return AnthropicPrivacySafeUsageRecord(
        reporting_date=record.reporting_date,
        provider=record.provider,
        pseudonymous_user_id=pseudonymizer.pseudonymize(
            record.provider,
            record.identity.provider_user_id,
        ),
        activity=record.activity,
        provider_extension=AnthropicPrivacySafeExtension(
            chat_metrics=extension.chat_metrics,
            claude_code_metrics=extension.claude_code_metrics,
            cowork_metrics=extension.cowork_metrics,
            design_metrics=extension.design_metrics,
            office_metrics=extension.office_metrics,
            science_metrics=extension.science_metrics,
            web_search_count=extension.web_search_count,
            last_activity_date=extension.last_activity_date,
        ),
    )


def protect_anthropic_collection(
    records: Sequence[AnthropicNormalizedUsageRecord],
    pseudonymizer: HmacSha256Pseudonymizer,
) -> AnthropicPrivacySafeCollection:
    """Create the only collection representation allowed beyond privacy handling."""

    summary = aggregate_anthropic_usage(records)
    protected_records = tuple(
        protect_anthropic_record(record, pseudonymizer) for record in records
    )
    return AnthropicPrivacySafeCollection(
        metadata=PrivacySafeCollectionMetadata(
            reporting_date=summary.reporting_date,
            provider=summary.provider,
            record_count=len(protected_records),
        ),
        organization_summary=summary,
        usage_records=protected_records,
    )


def protect_mock_record(
    record: MockNormalizedUsageRecord,
    pseudonymizer: HmacSha256Pseudonymizer,
) -> MockPrivacySafeUsageRecord:
    """Remove fictional raw identity and retain only the mock activity schema."""

    extension = record.provider_extension
    if record.provider is not ProviderName.MOCK or not isinstance(
        extension, MockUsageExtension
    ):
        raise ValueError("privacy processing requires a normalized mock record")
    return MockPrivacySafeUsageRecord(
        reporting_date=record.reporting_date,
        provider=ProviderName.MOCK,
        pseudonymous_user_id=pseudonymizer.pseudonymize(
            ProviderName.MOCK,
            record.identity.provider_user_id,
        ),
        activity=record.activity,
        provider_extension=MockPrivacySafeExtension(
            chat_metrics=extension.chat_metrics,
            claude_code_metrics=extension.claude_code_metrics,
            cowork_metrics=extension.cowork_metrics,
            design_metrics=extension.design_metrics,
            office_metrics=extension.office_metrics,
            science_metrics=extension.science_metrics,
            web_search_count=extension.web_search_count,
        ),
    )


def protect_mock_collection(
    records: Sequence[MockNormalizedUsageRecord],
    pseudonymizer: HmacSha256Pseudonymizer,
) -> MockPrivacySafeCollection:
    """Create the only synthetic collection allowed beyond privacy handling."""

    summary = aggregate_mock_usage(records)
    protected_records = tuple(
        protect_mock_record(record, pseudonymizer) for record in records
    )
    return MockPrivacySafeCollection(
        metadata=PrivacySafeCollectionMetadata(
            reporting_date=summary.reporting_date,
            provider=ProviderName.MOCK,
            record_count=len(protected_records),
        ),
        organization_summary=summary,
        usage_records=protected_records,
    )
