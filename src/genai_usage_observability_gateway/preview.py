"""Privacy-safe preview generation and atomic development persistence."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import model_validator

from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationUsageSummary,
    MockOrganizationUsageSummary,
)
from genai_usage_observability_gateway.config import AppSettings, ProviderName
from genai_usage_observability_gateway.models.usage import StrictDomainModel
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
)
from genai_usage_observability_gateway.privacy import (
    AnthropicPrivacySafeCollection,
    AnthropicPrivacySafeUsageRecord,
    HmacSha256Pseudonymizer,
    MockPrivacySafeCollection,
    MockPrivacySafeUsageRecord,
    protect_anthropic_collection,
)


class AnthropicUsagePreview(StrictDomainModel):
    """Readable preview document containing only privacy-safe collection data."""

    reporting_date: date
    collection_timestamp: datetime
    provider: Literal[ProviderName.ANTHROPIC]
    usage_records: tuple[AnthropicPrivacySafeUsageRecord, ...]
    organization_snapshot: AnthropicOrganizationUsageSummary

    @model_validator(mode="after")
    def validate_consistency(self) -> AnthropicUsagePreview:
        """Require UTC time and consistent dates, providers, and record counts."""

        if self.collection_timestamp.utcoffset() != timedelta(0):
            raise ValueError("preview collection timestamp must be UTC")
        summary = self.organization_snapshot
        if (
            summary.reporting_date != self.reporting_date
            or summary.provider is not self.provider
            or summary.total_users != len(self.usage_records)
        ):
            raise ValueError("preview metadata does not match organization snapshot")
        if any(
            record.reporting_date != self.reporting_date
            or record.provider is not self.provider
            for record in self.usage_records
        ):
            raise ValueError("preview records do not match preview metadata")
        return self


class MockUsagePreview(StrictDomainModel):
    """Readable synthetic preview containing only post-privacy data."""

    reporting_date: date
    collection_timestamp: datetime
    provider: Literal[ProviderName.MOCK]
    usage_records: tuple[MockPrivacySafeUsageRecord, ...]
    organization_snapshot: MockOrganizationUsageSummary

    @model_validator(mode="after")
    def validate_consistency(self) -> MockUsagePreview:
        """Require UTC time and consistent dates, providers, and record counts."""

        if self.collection_timestamp.utcoffset() != timedelta(0):
            raise ValueError("preview collection timestamp must be UTC")
        summary = self.organization_snapshot
        if (
            summary.reporting_date != self.reporting_date
            or summary.provider is not self.provider
            or summary.total_users != len(self.usage_records)
        ):
            raise ValueError("preview metadata does not match organization snapshot")
        if any(
            record.reporting_date != self.reporting_date
            or record.provider is not self.provider
            for record in self.usage_records
        ):
            raise ValueError("preview records do not match preview metadata")
        return self


PreviewDocument = AnthropicUsagePreview | MockUsagePreview


def build_anthropic_usage_preview(
    records: Sequence[AnthropicNormalizedUsageRecord],
    pseudonymizer: HmacSha256Pseudonymizer,
    *,
    collection_timestamp: datetime | None = None,
) -> AnthropicUsagePreview:
    """Protect and aggregate records before constructing preview output."""

    collection = protect_anthropic_collection(records, pseudonymizer)
    return build_anthropic_usage_preview_from_collection(
        collection,
        collection_timestamp=collection_timestamp,
    )


def build_anthropic_usage_preview_from_collection(
    collection: AnthropicPrivacySafeCollection,
    *,
    collection_timestamp: datetime | None = None,
) -> AnthropicUsagePreview:
    """Construct a preview from an already protected and aggregated collection."""

    timestamp = collection_timestamp or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("preview collection timestamp must be timezone-aware")
    metadata = collection.metadata
    return AnthropicUsagePreview(
        reporting_date=metadata.reporting_date,
        collection_timestamp=timestamp.astimezone(UTC),
        provider=ProviderName.ANTHROPIC,
        usage_records=collection.usage_records,
        organization_snapshot=collection.organization_summary,
    )


def render_usage_preview(preview: PreviewDocument) -> str:
    """Render readable deterministic JSON without writing a local file."""

    return preview.model_dump_json(indent=2)


def build_mock_usage_preview_from_collection(
    collection: MockPrivacySafeCollection,
    *,
    collection_timestamp: datetime | None = None,
) -> MockUsagePreview:
    """Construct a preview from a protected synthetic collection."""

    timestamp = collection_timestamp or datetime.now(UTC)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("preview collection timestamp must be timezone-aware")
    metadata = collection.metadata
    return MockUsagePreview(
        reporting_date=metadata.reporting_date,
        collection_timestamp=timestamp.astimezone(UTC),
        provider=ProviderName.MOCK,
        usage_records=collection.usage_records,
        organization_snapshot=collection.organization_summary,
    )


@dataclass(frozen=True, slots=True)
class DevelopmentPreviewWriter:
    """Atomically replace one configured local preview document."""

    output_path: Path

    def __post_init__(self) -> None:
        if not self.output_path.name:
            raise ValueError("preview output path must name a file")

    def write(self, preview: PreviewDocument) -> Path:
        """Write a complete preview using a temporary sibling and replacement."""

        destination = self.output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        try:
            stream = os.fdopen(
                descriptor,
                mode="w",
                encoding="utf-8",
                newline="\n",
            )
            descriptor = -1
            with stream:
                stream.write(f"{render_usage_preview(preview)}\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, destination)
        finally:
            if descriptor >= 0:
                os.close(descriptor)
            temporary_path.unlink(missing_ok=True)
        return destination


def preview_writer_from_settings(
    settings: AppSettings,
) -> DevelopmentPreviewWriter | None:
    """Create a writer only when environment-aware preview output is enabled."""

    if not settings.preview_generation_enabled:
        return None
    return DevelopmentPreviewWriter(settings.preview_output_path)
