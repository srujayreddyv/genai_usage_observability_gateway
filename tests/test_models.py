from datetime import date

import pytest
from pydantic import Field, ValidationError

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models import (
    CommonUsageActivity,
    NormalizedUsageRecord,
    ProviderUsageExtension,
    UserIdentity,
)
from genai_usage_observability_gateway.models.usage import NonNegativeCount


class ExampleProviderExtension(ProviderUsageExtension):
    category: str
    provider_specific_count: NonNegativeCount = Field(default=0)


def make_record() -> NormalizedUsageRecord[ExampleProviderExtension]:
    return NormalizedUsageRecord[ExampleProviderExtension](
        reporting_date=date(2026, 1, 15),
        provider=ProviderName.MOCK,
        identity=UserIdentity(
            provider_user_id="fictional-user-001",
            email="alex.river@example.com",
        ),
        activity=CommonUsageActivity(
            is_active=True,
            chat_interaction_count=4,
            developer_session_count=None,
            accepted_tool_action_count=2,
            rejected_tool_action_count=0,
        ),
        provider_extension=ExampleProviderExtension(
            category="synthetic-category",
            provider_specific_count=3,
        ),
    )


def test_normalized_record_preserves_common_and_extension_data() -> None:
    record = make_record()

    assert record.provider is ProviderName.MOCK
    assert record.identity.email == "alex.river@example.com"
    assert record.activity.developer_session_count is None
    assert record.provider_extension is not None
    assert record.provider_extension.provider_specific_count == 3
    assert record.model_dump()["provider_extension"] == {
        "category": "synthetic-category",
        "provider_specific_count": 3,
    }


def test_absent_count_is_distinct_from_zero() -> None:
    activity = CommonUsageActivity(
        is_active=False,
        chat_interaction_count=0,
        developer_session_count=None,
    )

    assert activity.chat_interaction_count == 0
    assert activity.developer_session_count is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("chat_interaction_count", -1),
        ("developer_session_count", -1),
        ("accepted_tool_action_count", -1),
        ("rejected_tool_action_count", -1),
    ],
)
def test_activity_rejects_negative_counts(field: str, value: int) -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CommonUsageActivity(is_active=True, **{field: value})


def test_activity_rejects_coerced_values() -> None:
    with pytest.raises(ValidationError):
        CommonUsageActivity.model_validate(
            {"is_active": True, "chat_interaction_count": "1"}
        )


def test_identity_rejects_invalid_email() -> None:
    with pytest.raises(ValidationError):
        UserIdentity(provider_user_id="fictional-user", email="not-an-email")


def test_identity_rejects_empty_provider_user_id() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        UserIdentity(provider_user_id="")


def test_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CommonUsageActivity.model_validate({"is_active": True, "unknown_count": 1})


def test_provider_extension_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExampleProviderExtension.model_validate(
            {
                "category": "synthetic-category",
                "provider_specific_count": 1,
                "unknown_provider_value": 2,
            }
        )


def test_normalized_record_rejects_coerced_reporting_date() -> None:
    with pytest.raises(ValidationError):
        NormalizedUsageRecord.model_validate(
            {
                "reporting_date": "2026-01-15",
                "provider": ProviderName.MOCK,
                "identity": UserIdentity(provider_user_id="fictional-user"),
                "activity": CommonUsageActivity(is_active=False),
            }
        )


def test_normalized_record_is_immutable() -> None:
    record = make_record()

    with pytest.raises(ValidationError, match="Instance is frozen"):
        record.provider = ProviderName.ANTHROPIC
