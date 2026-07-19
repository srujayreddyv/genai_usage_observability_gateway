"""Structured, privacy-safe collection lifecycle events."""

from __future__ import annotations

import json
import logging
from datetime import date
from enum import StrEnum
from typing import TextIO

from opentelemetry._logs import Logger, SeverityNumber
from opentelemetry.sdk._logs import LoggerProvider
from pydantic import model_validator

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models.usage import (
    NonNegativeCount,
    StrictDomainModel,
)
from genai_usage_observability_gateway.telemetry_attributes import (
    CLIENT_TYPE_ATTRIBUTE,
    COLLECTION_DURATION_MS_ATTRIBUTE,
    COLLECTION_STATUS_ATTRIBUTE,
    PROVIDER_ATTRIBUTE,
    RECORD_COUNT_ATTRIBUTE,
    REPORTING_DATE_ATTRIBUTE,
)

COLLECTION_LIFECYCLE_LOGGER_NAME = (
    "genai_usage_observability_gateway.collection_lifecycle"
)


class CollectionLifecycleEventName(StrEnum):
    """Fixed event names required by the collection lifecycle contract."""

    STARTED = "collection_started"
    RECORDS_MAPPED = "records_mapped"
    AGGREGATION_COMPLETED = "aggregation_completed"
    PREVIEW_WRITTEN = "preview_written"
    COMPLETED = "collection_completed"
    FAILED = "collection_failed"


class CollectionLifecycleStatus(StrEnum):
    """Bounded workflow states safe for lifecycle event attributes."""

    STARTED = "started"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"


class CollectionClientType(StrEnum):
    """Bounded client implementations safe for telemetry attributes."""

    ANTHROPIC_API = "anthropic_api"
    IN_MEMORY = "in_memory"


_EXPECTED_STATUS = {
    CollectionLifecycleEventName.STARTED: CollectionLifecycleStatus.STARTED,
    CollectionLifecycleEventName.RECORDS_MAPPED: (
        CollectionLifecycleStatus.IN_PROGRESS
    ),
    CollectionLifecycleEventName.AGGREGATION_COMPLETED: (
        CollectionLifecycleStatus.IN_PROGRESS
    ),
    CollectionLifecycleEventName.PREVIEW_WRITTEN: (
        CollectionLifecycleStatus.IN_PROGRESS
    ),
    CollectionLifecycleEventName.COMPLETED: CollectionLifecycleStatus.SUCCESS,
    CollectionLifecycleEventName.FAILED: CollectionLifecycleStatus.FAILED,
}
_RECORD_COUNT_REQUIRED_EVENTS = frozenset(
    {
        CollectionLifecycleEventName.RECORDS_MAPPED,
        CollectionLifecycleEventName.AGGREGATION_COMPLETED,
        CollectionLifecycleEventName.PREVIEW_WRITTEN,
        CollectionLifecycleEventName.COMPLETED,
    }
)


class CollectionLifecycleEvent(StrictDomainModel):
    """One allowlisted operational checkpoint with no sensitive fields."""

    event_name: CollectionLifecycleEventName
    reporting_date: date
    provider: ProviderName
    client_type: CollectionClientType
    collection_status: CollectionLifecycleStatus
    duration_ms: NonNegativeCount
    record_count: NonNegativeCount | None = None

    @model_validator(mode="after")
    def validate_checkpoint(self) -> CollectionLifecycleEvent:
        """Keep event status and record availability semantically consistent."""

        if self.collection_status is not _EXPECTED_STATUS[self.event_name]:
            raise ValueError("lifecycle event has an incompatible collection status")
        if (
            self.event_name in _RECORD_COUNT_REQUIRED_EVENTS
            and self.record_count is None
        ):
            raise ValueError("lifecycle checkpoint requires a record count")
        return self

    def otel_attributes(self) -> dict[str, str | int]:
        """Map the strict event to the project's custom attribute allowlist."""

        attributes: dict[str, str | int] = {
            REPORTING_DATE_ATTRIBUTE: self.reporting_date.isoformat(),
            PROVIDER_ATTRIBUTE: self.provider.value,
            CLIENT_TYPE_ATTRIBUTE: self.client_type.value,
            COLLECTION_STATUS_ATTRIBUTE: self.collection_status.value,
            COLLECTION_DURATION_MS_ATTRIBUTE: self.duration_ms,
        }
        if self.record_count is not None:
            attributes[RECORD_COUNT_ATTRIBUTE] = self.record_count
        return attributes


class CollectionLifecycleEmitter:
    """Mirror lifecycle checkpoints to local JSON and OpenTelemetry events."""

    def __init__(
        self,
        logger_provider: LoggerProvider,
        *,
        local_stream: TextIO | None = None,
    ) -> None:
        self._otel_logger: Logger = logger_provider.get_logger(
            COLLECTION_LIFECYCLE_LOGGER_NAME,
            __version__,
        )
        self._local_logger = self._create_local_logger(local_stream)

    @staticmethod
    def _create_local_logger(stream: TextIO | None) -> logging.Logger | None:
        if stream is None:
            return None
        logger = logging.Logger(COLLECTION_LIFECYCLE_LOGGER_NAME)
        logger.propagate = False
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        return logger

    def emit(self, event: CollectionLifecycleEvent) -> None:
        """Emit one checkpoint with fixed severity and safe custom attributes."""

        severity = (
            SeverityNumber.ERROR
            if event.event_name is CollectionLifecycleEventName.FAILED
            else SeverityNumber.INFO
        )
        local_body = event.model_dump(mode="json", exclude_none=True)
        if self._local_logger is not None:
            self._local_logger.log(
                logging.ERROR if severity is SeverityNumber.ERROR else logging.INFO,
                json.dumps(
                    local_body,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
            )
        self._otel_logger.emit(
            severity_number=severity,
            attributes=event.otel_attributes(),
            event_name=event.event_name.value,
        )
