"""Provider-selected collection service used by the HTTP boundary."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date
from typing import Protocol

from pydantic import SecretStr, TypeAdapter, ValidationError

from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationUsageSummary,
    MockOrganizationUsageSummary,
)
from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
    ProviderName,
)
from genai_usage_observability_gateway.lifecycle_events import CollectionClientType
from genai_usage_observability_gateway.preview import (
    PreviewDocument,
    preview_writer_from_settings,
)
from genai_usage_observability_gateway.privacy import HmacSha256Pseudonymizer
from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicAnalyticsClient,
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.providers.base import AnalyticsClient
from genai_usage_observability_gateway.providers.errors import ProviderError
from genai_usage_observability_gateway.providers.mock import (
    MockAnalyticsClient,
    MockUserActivityRecord,
)
from genai_usage_observability_gateway.telemetry import TelemetryRuntime
from genai_usage_observability_gateway.workflow import (
    AnthropicCollectionWorkflow,
    MockCollectionWorkflow,
)

OrganizationSummary = AnthropicOrganizationUsageSummary | MockOrganizationUsageSummary
_PREVIEW_ADAPTER: TypeAdapter[PreviewDocument] = TypeAdapter(PreviewDocument)
_LOCAL_MOCK_KEY = SecretStr("synthetic-local-mock-pseudonymization-only")


class ServiceConfigurationError(RuntimeError):
    """Selected-provider configuration cannot safely run a collection."""


class PreviewNotFoundError(FileNotFoundError):
    """The enabled preview destination does not contain an artifact."""


class PreviewReadError(RuntimeError):
    """The configured preview cannot be safely read and validated."""


class CollectionFailedError(RuntimeError):
    """A non-provider collection stage failed."""


class GatewayOperations(Protocol):
    """Operations consumed by the FastAPI route layer."""

    @property
    def preview_enabled(self) -> bool: ...

    def validate_readiness(self) -> ProviderName: ...

    async def collect(self, reporting_date: date) -> OrganizationSummary: ...

    def read_preview(self) -> PreviewDocument: ...


MockClientFactory = Callable[[], AnalyticsClient[MockUserActivityRecord]]
AnthropicClientFactory = Callable[
    [AppSettings], AnalyticsClient[AnthropicUserActivityRecord]
]


def _anthropic_client_from_settings(
    settings: AppSettings,
) -> AnalyticsClient[AnthropicUserActivityRecord]:
    api_key = settings.anthropic_analytics_api_key
    if api_key is None:
        raise ServiceConfigurationError(
            "Anthropic analytics credentials are not configured"
        )
    return AnthropicAnalyticsClient(
        api_key=api_key,
        result_limit=settings.anthropic_result_limit,
        timeout_seconds=settings.anthropic_request_timeout_seconds,
    )


class GatewayService:
    """Select and execute one privacy-safe provider collection workflow."""

    def __init__(
        self,
        settings: AppSettings,
        telemetry: TelemetryRuntime,
        *,
        mock_client_factory: MockClientFactory = MockAnalyticsClient,
        anthropic_client_factory: AnthropicClientFactory = (
            _anthropic_client_from_settings
        ),
    ) -> None:
        self._settings = settings
        self._telemetry = telemetry
        self._mock_client_factory = mock_client_factory
        self._anthropic_client_factory = anthropic_client_factory
        try:
            self._preview_writer = preview_writer_from_settings(settings)
        except ValueError:
            raise ServiceConfigurationError(
                "preview output configuration is invalid"
            ) from None

    @property
    def preview_enabled(self) -> bool:
        return self._preview_writer is not None

    def validate_readiness(self) -> ProviderName:
        """Validate selected-provider requirements without contacting it."""

        provider = self._settings.analytics_provider
        if provider is ProviderName.ANTHROPIC:
            if self._settings.anthropic_analytics_api_key is None:
                raise ServiceConfigurationError(
                    "Anthropic analytics credentials are not configured"
                )
            if self._settings.pseudonymization_key is None:
                raise ServiceConfigurationError(
                    "pseudonymization is not configured for Anthropic analytics"
                )
        elif (
            self._settings.app_environment
            not in {DeploymentEnvironment.DEVELOPMENT, DeploymentEnvironment.TEST}
            and self._settings.pseudonymization_key is None
        ):
            raise ServiceConfigurationError(
                "pseudonymization is not configured for this environment"
            )
        return provider

    def _pseudonymizer(self) -> HmacSha256Pseudonymizer:
        key = self._settings.pseudonymization_key
        if key is not None:
            return HmacSha256Pseudonymizer(key)
        if (
            self._settings.analytics_provider is ProviderName.MOCK
            and self._settings.app_environment
            in {DeploymentEnvironment.DEVELOPMENT, DeploymentEnvironment.TEST}
        ):
            return HmacSha256Pseudonymizer(_LOCAL_MOCK_KEY)
        raise ServiceConfigurationError("pseudonymization is not configured")

    async def collect(self, reporting_date: date) -> OrganizationSummary:
        """Execute the selected workflow and return only its organization summary."""

        self.validate_readiness()
        pseudonymizer = self._pseudonymizer()
        try:
            if self._settings.analytics_provider is ProviderName.MOCK:
                workflow = MockCollectionWorkflow(
                    client=self._mock_client_factory(),
                    pseudonymizer=pseudonymizer,
                    telemetry=self._telemetry,
                    preview_writer=self._preview_writer,
                )
                preview = await workflow.collect(reporting_date)
                return preview.organization_snapshot

            anthropic_workflow = AnthropicCollectionWorkflow(
                client=self._anthropic_client_factory(self._settings),
                client_type=CollectionClientType.ANTHROPIC_API,
                pseudonymizer=pseudonymizer,
                telemetry=self._telemetry,
                preview_writer=self._preview_writer,
            )
            anthropic_preview = await anthropic_workflow.collect(reporting_date)
            return anthropic_preview.organization_snapshot
        except ServiceConfigurationError:
            raise
        except Exception as exception:
            if isinstance(exception, ProviderError):
                raise
            raise CollectionFailedError("collection workflow failed") from None

    def read_preview(self) -> PreviewDocument:
        """Read and validate the enabled local preview without exposing its path."""

        if self._preview_writer is None:
            raise ServiceConfigurationError("development preview is disabled")
        try:
            payload = self._preview_writer.output_path.read_bytes()
        except FileNotFoundError:
            raise PreviewNotFoundError("development preview is unavailable") from None
        except OSError:
            raise PreviewReadError("development preview could not be read") from None
        try:
            return _PREVIEW_ADAPTER.validate_json(payload)
        except ValidationError:
            raise PreviewReadError("development preview is invalid") from None


GatewayServiceFactory = Callable[[AppSettings, TelemetryRuntime], GatewayOperations]


def create_gateway_service(
    settings: AppSettings,
    telemetry: TelemetryRuntime,
) -> GatewayOperations:
    """Build the default provider-selected service."""

    return GatewayService(settings, telemetry)
