"""Structured, privacy-safe per-user usage events."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Literal, TextIO

from opentelemetry._logs import Logger, SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models.usage import (
    CommonUsageActivity,
    StrictDomainModel,
)
from genai_usage_observability_gateway.privacy import (
    AnthropicPrivacySafeCollection,
    AnthropicPrivacySafeExtension,
    AnthropicPrivacySafeUsageRecord,
    MockPrivacySafeCollection,
    MockPrivacySafeExtension,
    MockPrivacySafeUsageRecord,
    PseudonymousIdentifier,
)

USAGE_EVENT_NAME: Literal["genai_user_usage"] = "genai_user_usage"
USAGE_EVENT_LOGGER_NAME = "genai_usage_observability_gateway.usage_events"


class AnthropicUsageEvent(StrictDomainModel):
    """One explicitly allowlisted event body produced after privacy processing."""

    event_name: Literal["genai_user_usage"] = USAGE_EVENT_NAME
    reporting_date: date
    provider: Literal[ProviderName.ANTHROPIC]
    pseudonymous_user_id: PseudonymousIdentifier
    common_activity: CommonUsageActivity
    anthropic_activity: AnthropicPrivacySafeExtension

    @classmethod
    def from_record(
        cls, record: AnthropicPrivacySafeUsageRecord
    ) -> AnthropicUsageEvent:
        """Build an event only from the post-privacy record boundary."""

        if record.provider is not ProviderName.ANTHROPIC:
            raise ValueError("Anthropic usage events require an Anthropic record")
        return cls(
            reporting_date=record.reporting_date,
            provider=ProviderName.ANTHROPIC,
            pseudonymous_user_id=record.pseudonymous_user_id,
            common_activity=record.activity,
            anthropic_activity=record.provider_extension,
        )


class MockUsageEvent(StrictDomainModel):
    """One allowlisted event body produced from a protected synthetic record."""

    event_name: Literal["genai_user_usage"] = USAGE_EVENT_NAME
    reporting_date: date
    provider: Literal[ProviderName.MOCK]
    pseudonymous_user_id: PseudonymousIdentifier
    common_activity: CommonUsageActivity
    mock_activity: MockPrivacySafeExtension

    @classmethod
    def from_record(cls, record: MockPrivacySafeUsageRecord) -> MockUsageEvent:
        """Build an event only from the synthetic post-privacy boundary."""

        if record.provider is not ProviderName.MOCK:
            raise ValueError("mock usage events require a mock record")
        return cls(
            reporting_date=record.reporting_date,
            provider=ProviderName.MOCK,
            pseudonymous_user_id=record.pseudonymous_user_id,
            common_activity=record.activity,
            mock_activity=record.provider_extension,
        )


UsageEvent = AnthropicUsageEvent | MockUsageEvent
PrivacySafeCollection = AnthropicPrivacySafeCollection | MockPrivacySafeCollection


class UsageEventEmitter:
    """Mirror each logical usage event to local JSON and OpenTelemetry logs."""

    def __init__(
        self,
        logger_provider: LoggerProvider,
        *,
        local_stream: TextIO | None = None,
    ) -> None:
        self._otel_logger: Logger = logger_provider.get_logger(
            USAGE_EVENT_LOGGER_NAME,
            __version__,
        )
        self._local_logger = self._create_local_logger(local_stream)

    @staticmethod
    def _create_local_logger(stream: TextIO | None) -> logging.Logger | None:
        if stream is None:
            return None
        logger = logging.Logger(USAGE_EVENT_LOGGER_NAME, level=logging.INFO)
        logger.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        return logger

    def emit_collection(self, collection: PrivacySafeCollection) -> int:
        """Emit exactly one event for each protected record in the collection."""

        if isinstance(collection, AnthropicPrivacySafeCollection):
            for anthropic_record in collection.usage_records:
                self.emit(AnthropicUsageEvent.from_record(anthropic_record))
        else:
            for mock_record in collection.usage_records:
                self.emit(MockUsageEvent.from_record(mock_record))
        return len(collection.usage_records)

    def emit(self, event: UsageEvent) -> None:
        """Emit one structured event to every configured destination."""

        body = event.model_dump(mode="json")
        if self._local_logger is not None:
            self._local_logger.info(
                json.dumps(
                    body,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                )
            )
        self._otel_logger.emit(
            severity_number=SeverityNumber.INFO,
            severity_text="INFO",
            body=body,
            event_name=USAGE_EVENT_NAME,
        )
