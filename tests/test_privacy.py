from datetime import date
from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from genai_usage_observability_gateway.config import AppSettings, ProviderName
from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
    normalize_anthropic_record,
    normalize_anthropic_records,
)
from genai_usage_observability_gateway.preview import (
    AnthropicUsagePreview,
    build_anthropic_usage_preview,
    render_usage_preview,
)
from genai_usage_observability_gateway.privacy import (
    AnthropicPrivacySafeCollection,
    AnthropicPrivacySafeExtension,
    AnthropicPrivacySafeUsageRecord,
    HmacSha256Pseudonymizer,
    PseudonymizationKeyRequiredError,
    protect_anthropic_collection,
    protect_anthropic_record,
)
from tests.factories import (
    anthropic_activity_payload,
    anthropic_record_from_payload,
)

REPORTING_DATE = date(2026, 2, 3)
SYNTHETIC_KEY = "synthetic-pseudonymization-key"


def _pseudonymizer(key: str = SYNTHETIC_KEY) -> HmacSha256Pseudonymizer:
    return HmacSha256Pseudonymizer(SecretStr(key))


def _normalized_record(user_number: int = 1) -> AnthropicNormalizedUsageRecord:
    return normalize_anthropic_record(
        anthropic_record_from_payload(anthropic_activity_payload(user_number))
    )


def _normalized_records() -> tuple[AnthropicNormalizedUsageRecord, ...]:
    return normalize_anthropic_records(
        anthropic_record_from_payload(anthropic_activity_payload(user_number))
        for user_number in (1, 2)
    )


def _settings(**values: object) -> AppSettings:
    options: dict[str, Any] = {"_env_file": None, **values}
    return AppSettings(**options)


def test_hmac_sha256_pseudonym_matches_stable_known_value() -> None:
    pseudonym = _pseudonymizer().pseudonymize(
        ProviderName.ANTHROPIC, "synthetic-user-001"
    )

    assert pseudonym == "4550495ae0ec1e8b"
    assert len(pseudonym) == 16
    assert set(pseudonym) <= set("0123456789abcdef")


def test_pseudonyms_are_deterministic_and_namespaced() -> None:
    pseudonymizer = _pseudonymizer()

    first = pseudonymizer.pseudonymize(ProviderName.ANTHROPIC, "synthetic-user-001")

    assert (
        pseudonymizer.pseudonymize(ProviderName.ANTHROPIC, "synthetic-user-001")
        == first
    )
    assert (
        pseudonymizer.pseudonymize(ProviderName.ANTHROPIC, "synthetic-user-002")
        != first
    )
    assert pseudonymizer.pseudonymize(ProviderName.MOCK, "synthetic-user-001") != first
    assert (
        _pseudonymizer("different-synthetic-key").pseudonymize(
            ProviderName.ANTHROPIC, "synthetic-user-001"
        )
        != first
    )


def test_pseudonymizer_repr_and_errors_never_reveal_secret() -> None:
    pseudonymizer = _pseudonymizer()

    assert SYNTHETIC_KEY not in repr(pseudonymizer)
    assert "**********" in repr(pseudonymizer)

    with pytest.raises(ValueError) as error:
        pseudonymizer.pseudonymize(ProviderName.ANTHROPIC, "  ")

    assert SYNTHETIC_KEY not in str(error.value)


def test_empty_pseudonymization_key_is_rejected_safely() -> None:
    with pytest.raises(PseudonymizationKeyRequiredError) as error:
        HmacSha256Pseudonymizer(SecretStr("  "))

    assert "key must not be empty" in str(error.value)


def test_pseudonymizer_builds_from_configured_settings() -> None:
    pseudonymizer = HmacSha256Pseudonymizer.from_settings(
        _settings(pseudonymization_key=SYNTHETIC_KEY)
    )

    assert (
        pseudonymizer.pseudonymize(ProviderName.ANTHROPIC, "synthetic-user-001")
        == "4550495ae0ec1e8b"
    )


def test_pseudonymizer_requires_key_when_privacy_processing_runs() -> None:
    with pytest.raises(
        PseudonymizationKeyRequiredError, match="PSEUDONYMIZATION_KEY is required"
    ):
        HmacSha256Pseudonymizer.from_settings(_settings())


def test_protected_record_removes_raw_identity_and_preserves_activity() -> None:
    normalized = _normalized_record()

    protected = protect_anthropic_record(normalized, _pseudonymizer())
    serialized = protected.model_dump_json()

    assert protected.pseudonymous_user_id == "4550495ae0ec1e8b"
    assert protected.activity == normalized.activity
    assert protected.provider_extension.web_search_count == 2
    assert "identity" not in protected.__class__.model_fields
    assert normalized.identity.provider_user_id not in serialized
    assert str(normalized.identity.email) not in serialized
    assert SYNTHETIC_KEY not in serialized


@pytest.mark.parametrize(
    "unsafe_field", ["email", "provider_user_id", "organizational_groups"]
)
def test_privacy_safe_extension_rejects_identity_and_group_fields(
    unsafe_field: str,
) -> None:
    protected = protect_anthropic_record(_normalized_record(), _pseudonymizer())
    payload = protected.provider_extension.model_dump()
    payload[unsafe_field] = "must-not-cross-privacy-boundary"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AnthropicPrivacySafeExtension.model_validate(payload)


def test_privacy_safe_record_rejects_malformed_pseudonym() -> None:
    protected = protect_anthropic_record(_normalized_record(), _pseudonymizer())
    payload = protected.model_dump()
    payload["pseudonymous_user_id"] = "not-a-pseudonym"

    with pytest.raises(ValidationError, match="String should match pattern"):
        AnthropicPrivacySafeUsageRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("provider", "remove_extension"),
    [(ProviderName.MOCK, False), (ProviderName.ANTHROPIC, True)],
)
def test_protect_record_rejects_incompatible_normalized_input(
    provider: ProviderName, remove_extension: bool
) -> None:
    record = _normalized_record().model_copy(
        update={
            "provider": provider,
            **({"provider_extension": None} if remove_extension else {}),
        }
    )

    with pytest.raises(ValueError, match="requires a normalized Anthropic record"):
        protect_anthropic_record(record, _pseudonymizer())


def test_protected_collection_has_unique_pseudonyms_and_consistent_metadata() -> None:
    collection = protect_anthropic_collection(_normalized_records(), _pseudonymizer())

    assert collection.metadata.reporting_date == REPORTING_DATE
    assert collection.metadata.provider is ProviderName.ANTHROPIC
    assert collection.metadata.record_count == 2
    assert collection.organization_summary.total_users == 2
    assert len(collection.usage_records) == 2
    assert (
        len({record.pseudonymous_user_id for record in collection.usage_records}) == 2
    )


def _collection_payload() -> dict[str, object]:
    return protect_anthropic_collection(
        _normalized_records(), _pseudonymizer()
    ).model_dump()


def _mapping(payload: dict[str, object], field: str) -> dict[str, object]:
    value = payload[field]
    assert isinstance(value, dict)
    return value


def test_collection_rejects_metadata_summary_mismatch() -> None:
    payload = _collection_payload()
    _mapping(payload, "metadata")["reporting_date"] = date(2026, 2, 4)

    with pytest.raises(ValidationError, match="does not match organization summary"):
        AnthropicPrivacySafeCollection.model_validate(payload)


def test_collection_rejects_record_count_mismatch() -> None:
    payload = _collection_payload()
    _mapping(payload, "metadata")["record_count"] = 3

    with pytest.raises(ValidationError, match="record counts are inconsistent"):
        AnthropicPrivacySafeCollection.model_validate(payload)


def test_collection_rejects_record_metadata_mismatch() -> None:
    collection = protect_anthropic_collection(_normalized_records(), _pseudonymizer())
    mismatched = collection.usage_records[1].model_copy(
        update={"reporting_date": date(2026, 2, 4)}
    )

    with pytest.raises(ValidationError, match="do not match collection metadata"):
        AnthropicPrivacySafeCollection(
            metadata=collection.metadata,
            organization_summary=collection.organization_summary,
            usage_records=(collection.usage_records[0], mismatched),
        )


def test_collection_rejects_duplicate_pseudonyms() -> None:
    collection = protect_anthropic_collection(_normalized_records(), _pseudonymizer())
    duplicate = collection.usage_records[1].model_copy(
        update={
            "pseudonymous_user_id": collection.usage_records[0].pseudonymous_user_id
        }
    )

    with pytest.raises(ValidationError, match="duplicate pseudonymous identifiers"):
        AnthropicPrivacySafeCollection(
            metadata=collection.metadata,
            organization_summary=collection.organization_summary,
            usage_records=(collection.usage_records[0], duplicate),
        )


@pytest.fixture
def privacy_outputs() -> tuple[
    tuple[AnthropicNormalizedUsageRecord, ...],
    AnthropicPrivacySafeCollection,
    AnthropicUsagePreview,
]:
    records = _normalized_records()
    pseudonymizer = _pseudonymizer()
    collection = protect_anthropic_collection(records, pseudonymizer)
    preview = build_anthropic_usage_preview(records, pseudonymizer)
    return records, collection, preview


def _assert_raw_identity_absent(
    output: str, records: tuple[AnthropicNormalizedUsageRecord, ...]
) -> None:
    for record in records:
        assert record.identity.provider_user_id not in output
        assert str(record.identity.email) not in output
    assert SYNTHETIC_KEY not in output


def test_raw_identity_absent_from_future_telemetry_log_source(
    privacy_outputs: tuple[
        tuple[AnthropicNormalizedUsageRecord, ...],
        AnthropicPrivacySafeCollection,
        AnthropicUsagePreview,
    ],
) -> None:
    records, collection, _ = privacy_outputs
    output = "\n".join(record.model_dump_json() for record in collection.usage_records)

    _assert_raw_identity_absent(output, records)
    assert collection.usage_records[0].pseudonymous_user_id in output


def test_raw_identity_absent_from_future_metric_attribute_source(
    privacy_outputs: tuple[
        tuple[AnthropicNormalizedUsageRecord, ...],
        AnthropicPrivacySafeCollection,
        AnthropicUsagePreview,
    ],
) -> None:
    records, collection, _ = privacy_outputs
    output = collection.organization_summary.model_dump_json()

    _assert_raw_identity_absent(output, records)
    for protected in collection.usage_records:
        assert protected.pseudonymous_user_id not in output


def test_raw_identity_absent_from_future_trace_attribute_source(
    privacy_outputs: tuple[
        tuple[AnthropicNormalizedUsageRecord, ...],
        AnthropicPrivacySafeCollection,
        AnthropicUsagePreview,
    ],
) -> None:
    records, collection, _ = privacy_outputs
    output = collection.metadata.model_dump_json()

    _assert_raw_identity_absent(output, records)
    for protected in collection.usage_records:
        assert protected.pseudonymous_user_id not in output


def test_raw_identity_absent_from_preview_output(
    privacy_outputs: tuple[
        tuple[AnthropicNormalizedUsageRecord, ...],
        AnthropicPrivacySafeCollection,
        AnthropicUsagePreview,
    ],
) -> None:
    records, collection, preview = privacy_outputs
    output = render_usage_preview(preview)

    _assert_raw_identity_absent(output, records)
    for protected in collection.usage_records:
        assert protected.pseudonymous_user_id in output


def test_grouping_data_is_removed_before_every_export_boundary() -> None:
    payload = anthropic_activity_payload()
    payload["rbac_group_id"] = "synthetic-private-group-id"
    payload["rbac_group_name"] = "Synthetic Private Group"
    normalized = normalize_anthropic_record(anthropic_record_from_payload(payload))
    collection = protect_anthropic_collection((normalized,), _pseudonymizer())
    preview = build_anthropic_usage_preview((normalized,), _pseudonymizer())
    outputs = (
        collection.metadata.model_dump_json(),
        collection.organization_summary.model_dump_json(),
        collection.usage_records[0].model_dump_json(),
        render_usage_preview(preview),
    )

    for output in outputs:
        assert "synthetic-private-group-id" not in output
        assert "Synthetic Private Group" not in output
        assert "rbac_group" not in output
