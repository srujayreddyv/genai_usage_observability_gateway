"""Common normalized usage models and provider extension boundary."""

from datetime import date
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from genai_usage_observability_gateway.config import ProviderName

NonNegativeCount = Annotated[int, Field(ge=0)]
NonEmptyString = Annotated[str, Field(min_length=1)]


class StrictDomainModel(BaseModel):
    """Immutable base model that rejects coercion and unknown fields."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        strict=True,
    )


class UserIdentity(StrictDomainModel):
    """Raw identity retained only at the ingestion and normalization boundary."""

    provider_user_id: NonEmptyString
    email: EmailStr | None = None


class CommonUsageActivity(StrictDomainModel):
    """Observable activity concepts that can apply across providers.

    An absent count means the provider does not expose that signal. Zero means
    the provider exposes it and reported no activity for the reporting period.
    """

    is_active: bool
    chat_interaction_count: NonNegativeCount | None = None
    developer_session_count: NonNegativeCount | None = None
    accepted_tool_action_count: NonNegativeCount | None = None
    rejected_tool_action_count: NonNegativeCount | None = None


class ProviderUsageExtension(StrictDomainModel):
    """Base for adapter-owned data that does not belong in the common schema."""


ProviderExtensionT = TypeVar(
    "ProviderExtensionT", bound=ProviderUsageExtension, default=ProviderUsageExtension
)


class NormalizedUsageRecord(StrictDomainModel, Generic[ProviderExtensionT]):
    """A provider-independent usage record with an adapter-owned extension."""

    reporting_date: date
    provider: ProviderName
    identity: UserIdentity
    activity: CommonUsageActivity
    provider_extension: ProviderExtensionT | None = None
