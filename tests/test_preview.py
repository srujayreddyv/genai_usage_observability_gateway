"""Tests for privacy-safe preview documents and atomic persistence."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
)
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    normalize_anthropic_records,
)
from genai_usage_observability_gateway.preview import (
    AnthropicUsagePreview,
    DevelopmentPreviewWriter,
    build_anthropic_usage_preview,
    preview_writer_from_settings,
    render_usage_preview,
)
from genai_usage_observability_gateway.privacy import HmacSha256Pseudonymizer
from tests.factories import (
    anthropic_activity_payload,
    anthropic_record_from_payload,
)

SYNTHETIC_KEY = "synthetic-development-preview-key"


def _normalized_records() -> tuple[AnthropicNormalizedUsageRecord, ...]:
    return normalize_anthropic_records(
        anthropic_record_from_payload(anthropic_activity_payload(user_number))
        for user_number in (1, 2)
    )


def _preview(
    timestamp: datetime = datetime(2026, 2, 3, 12, 34, 56, tzinfo=UTC),
) -> AnthropicUsagePreview:
    return build_anthropic_usage_preview(
        _normalized_records(),
        HmacSha256Pseudonymizer(SecretStr(SYNTHETIC_KEY)),
        collection_timestamp=timestamp,
    )


def _settings(**values: object) -> AppSettings:
    options: dict[str, Any] = {"_env_file": None, **values}
    return AppSettings(**options)


def test_preview_document_has_required_readable_fields_and_utc_timestamp() -> None:
    source_timestamp = datetime(
        2026,
        2,
        3,
        4,
        34,
        56,
        tzinfo=timezone(timedelta(hours=-8)),
    )

    preview = _preview(source_timestamp)
    payload = json.loads(render_usage_preview(preview))

    assert set(payload) == {
        "reporting_date",
        "collection_timestamp",
        "provider",
        "usage_records",
        "organization_snapshot",
    }
    assert payload["reporting_date"] == "2026-02-03"
    assert payload["collection_timestamp"] == "2026-02-03T12:34:56Z"
    assert payload["provider"] == "anthropic"
    assert len(payload["usage_records"]) == 2
    assert payload["organization_snapshot"]["total_users"] == 2
    assert '\n  "usage_records"' in render_usage_preview(preview)


def test_writer_creates_parent_directories_and_writes_complete_json(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "nested" / "artifacts" / "usage-preview.json"
    writer = DevelopmentPreviewWriter(output_path)
    preview = _preview()

    written_path = writer.write(preview)

    assert written_path == output_path
    assert output_path.read_text(encoding="utf-8") == (
        f"{render_usage_preview(preview)}\n"
    )
    assert (
        json.loads(output_path.read_text(encoding="utf-8"))["collection_timestamp"]
        == "2026-02-03T12:34:56Z"
    )
    assert list(output_path.parent.glob(".usage-preview.json.*.tmp")) == []


def test_atomic_replace_failure_preserves_previous_complete_preview(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "usage-preview.json"
    previous = '{\n  "previous_complete_preview": true\n}\n'
    output_path.write_text(previous, encoding="utf-8")

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("synthetic atomic replacement failure")

    monkeypatch.setattr(
        "genai_usage_observability_gateway.preview.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="synthetic atomic replacement failure"):
        DevelopmentPreviewWriter(output_path).write(_preview())

    assert output_path.read_text(encoding="utf-8") == previous
    assert list(tmp_path.glob(".usage-preview.json.*.tmp")) == []


def test_writer_closes_descriptor_and_cleans_up_when_opening_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_close = os.close
    closed_descriptors: list[int] = []

    def fail_fdopen(*args: object, **kwargs: object) -> None:
        raise OSError("synthetic descriptor opening failure")

    def tracking_close(descriptor: int) -> None:
        closed_descriptors.append(descriptor)
        real_close(descriptor)

    monkeypatch.setattr(
        "genai_usage_observability_gateway.preview.os.fdopen",
        fail_fdopen,
    )
    monkeypatch.setattr(
        "genai_usage_observability_gateway.preview.os.close",
        tracking_close,
    )

    with pytest.raises(OSError, match="synthetic descriptor opening failure"):
        DevelopmentPreviewWriter(tmp_path / "usage-preview.json").write(_preview())

    assert len(closed_descriptors) == 1
    assert list(tmp_path.glob(".usage-preview.json.*.tmp")) == []


def test_preview_file_contains_no_raw_identity_group_or_secret_data(
    tmp_path: Path,
) -> None:
    raw_records = tuple(
        anthropic_record_from_payload(anthropic_activity_payload(user_number))
        for user_number in (1, 2)
    )
    output_path = tmp_path / "usage-preview.json"

    DevelopmentPreviewWriter(output_path).write(_preview())
    serialized = output_path.read_text(encoding="utf-8")

    assert str(tmp_path) not in serialized
    for record in raw_records:
        assert record.activity.user.id not in serialized
        assert str(record.activity.user.email_address) not in serialized
    assert SYNTHETIC_KEY not in serialized
    for forbidden in (
        "rbac_group",
        "credential",
        "authorization",
        "file_path",
        "api_endpoint",
    ):
        assert forbidden not in serialized


def test_writer_factory_uses_environment_aware_enablement(tmp_path: Path) -> None:
    development = _settings(preview_output_path=tmp_path / "development.json")
    test = _settings(
        app_environment=DeploymentEnvironment.TEST,
        preview_output_path=tmp_path / "test.json",
    )
    explicitly_enabled = _settings(
        app_environment=DeploymentEnvironment.TEST,
        preview_enabled=True,
        preview_output_path=tmp_path / "enabled.json",
    )

    development_writer = preview_writer_from_settings(development)
    assert development_writer is not None
    assert development_writer.output_path == tmp_path / "development.json"
    assert preview_writer_from_settings(test) is None
    assert preview_writer_from_settings(explicitly_enabled) == (
        DevelopmentPreviewWriter(tmp_path / "enabled.json")
    )


def test_preview_rejects_naive_collection_timestamp() -> None:
    with pytest.raises(ValueError, match="must be timezone-aware"):
        _preview(datetime(2026, 2, 3, 12, 34, 56))


def test_preview_model_rejects_non_utc_timestamp() -> None:
    preview = _preview()

    with pytest.raises(ValidationError, match="timestamp must be UTC"):
        AnthropicUsagePreview.model_validate(
            preview.model_dump()
            | {
                "collection_timestamp": datetime(
                    2026,
                    2,
                    3,
                    12,
                    34,
                    56,
                    tzinfo=timezone(timedelta(hours=1)),
                )
            }
        )


def test_preview_model_rejects_inconsistent_snapshot() -> None:
    preview = _preview()
    mismatched_snapshot = preview.organization_snapshot.model_copy(
        update={"total_users": 3}
    )

    with pytest.raises(ValidationError, match="does not match organization snapshot"):
        AnthropicUsagePreview.model_validate(
            preview.model_dump()
            | {"organization_snapshot": mismatched_snapshot.model_dump()}
        )


def test_preview_model_rejects_inconsistent_record() -> None:
    preview = _preview()
    mismatched_record = preview.usage_records[0].model_copy(
        update={"reporting_date": preview.reporting_date + timedelta(days=1)}
    )

    with pytest.raises(ValidationError, match="records do not match"):
        AnthropicUsagePreview(
            reporting_date=preview.reporting_date,
            collection_timestamp=preview.collection_timestamp,
            provider=preview.provider,
            usage_records=(mismatched_record, preview.usage_records[1]),
            organization_snapshot=preview.organization_snapshot,
        )


def test_writer_requires_a_file_name() -> None:
    with pytest.raises(ValueError, match="must name a file"):
        DevelopmentPreviewWriter(Path("."))
