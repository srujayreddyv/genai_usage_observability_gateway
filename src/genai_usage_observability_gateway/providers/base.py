"""Provider-independent analytics client contract."""

from datetime import date
from typing import Protocol, TypeVar, runtime_checkable

from pydantic import BaseModel

from genai_usage_observability_gateway.config import ProviderName

ProviderRecordT = TypeVar("ProviderRecordT", bound=BaseModel, covariant=True)


@runtime_checkable
class AnalyticsClient(Protocol[ProviderRecordT]):
    """Retrieve validated provider-owned usage records for one UTC date."""

    @property
    def provider(self) -> ProviderName:
        """Return the provider represented by this client."""

        ...

    async def get_usage_analytics(
        self, reporting_date: date
    ) -> tuple[ProviderRecordT, ...]:
        """Return all validated usage records for the reporting date."""

        ...
