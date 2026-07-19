"""FastAPI application, lifespan, routes, and secret-safe error boundary."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import date
from typing import Annotated, Literal, cast

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from genai_usage_observability_gateway import __version__
from genai_usage_observability_gateway.aggregation import (
    AnthropicOrganizationUsageSummary,
    MockOrganizationUsageSummary,
)
from genai_usage_observability_gateway.config import (
    AppSettings,
    ProviderName,
    get_settings,
)
from genai_usage_observability_gateway.models.usage import StrictDomainModel
from genai_usage_observability_gateway.preview import PreviewDocument
from genai_usage_observability_gateway.providers.errors import (
    ProviderAuthenticationError,
    ProviderAuthorizationError,
    ProviderError,
    ProviderRateLimitError,
    ProviderReportingDateUnavailableError,
    ProviderResponseValidationError,
    ProviderServerError,
    ProviderTransportError,
)
from genai_usage_observability_gateway.service import (
    CollectionFailedError,
    GatewayOperations,
    GatewayServiceFactory,
    PreviewNotFoundError,
    PreviewReadError,
    ServiceConfigurationError,
    create_gateway_service,
)
from genai_usage_observability_gateway.telemetry import (
    SERVICE_NAME_VALUE,
    TelemetryManager,
    telemetry_manager,
)

SERVICE_DESCRIPTION = (
    "Privacy-conscious enterprise GenAI usage analytics collection and telemetry."
)

SettingsFactory = Callable[[], AppSettings]
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


class EndpointInformation(StrictDomainModel):
    method: Literal["GET", "POST"]
    path: str
    description: str


class RootResponse(StrictDomainModel):
    service_name: str
    version: str
    description: str
    endpoints: tuple[EndpointInformation, ...]


class HealthResponse(StrictDomainModel):
    status: Literal["healthy"] = "healthy"


class LivenessResponse(StrictDomainModel):
    status: Literal["alive"] = "alive"


class ReadinessResponse(StrictDomainModel):
    status: Literal["ready"] = "ready"
    provider: ProviderName


class PreviewDisabledResponse(StrictDomainModel):
    status: Literal["disabled"] = "disabled"
    message: Literal["development preview is disabled"] = (
        "development preview is disabled"
    )


class ErrorDetail(StrictDomainModel):
    code: str
    message: str
    retryable: bool


class ErrorResponse(StrictDomainModel):
    error: ErrorDetail


ENDPOINTS = (
    EndpointInformation(
        method="GET", path="/", description="Service and endpoint information."
    ),
    EndpointInformation(
        method="GET", path="/health", description="Aggregate process health."
    ),
    EndpointInformation(
        method="GET",
        path="/health/live",
        description="Process liveness without provider access.",
    ),
    EndpointInformation(
        method="GET",
        path="/health/ready",
        description="Selected-provider configuration readiness.",
    ),
    EndpointInformation(
        method="POST",
        path="/collect",
        description="Collect one UTC reporting date.",
    ),
    EndpointInformation(
        method="GET",
        path="/preview",
        description="Read the enabled privacy-safe preview.",
    ),
)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    retryable: bool = False,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorDetail(code=code, message=message, retryable=retryable)
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )


def _gateway_service(request: Request) -> GatewayOperations:
    return cast(GatewayOperations, request.app.state.gateway_service)


def create_lifespan(
    *,
    settings_factory: SettingsFactory = get_settings,
    manager: TelemetryManager = telemetry_manager,
    service_factory: GatewayServiceFactory = create_gateway_service,
) -> Lifespan:
    """Create a lifespan owning settings, service, and one telemetry lease."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        settings = settings_factory()
        runtime = manager.initialize(settings)
        try:
            application.state.settings = settings
            application.state.gateway_service = service_factory(settings, runtime)
            application.state.telemetry = runtime
            yield
        finally:
            manager.shutdown()

    return lifespan


def _install_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(RequestValidationError)
    async def request_validation_handler(
        _: Request,
        __: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            422,
            "invalid_request",
            "request validation failed",
        )

    @application.exception_handler(ServiceConfigurationError)
    async def configuration_handler(
        _: Request,
        __: ServiceConfigurationError,
    ) -> JSONResponse:
        return _error_response(
            503,
            "configuration_error",
            "service configuration is not ready",
        )

    @application.exception_handler(PreviewNotFoundError)
    async def preview_not_found_handler(
        _: Request,
        __: PreviewNotFoundError,
    ) -> JSONResponse:
        return _error_response(
            404,
            "preview_not_found",
            "development preview is unavailable",
        )

    @application.exception_handler(PreviewReadError)
    async def preview_read_handler(
        _: Request,
        __: PreviewReadError,
    ) -> JSONResponse:
        return _error_response(
            500,
            "preview_invalid",
            "development preview could not be loaded",
        )

    @application.exception_handler(CollectionFailedError)
    async def collection_failed_handler(
        _: Request,
        __: CollectionFailedError,
    ) -> JSONResponse:
        return _error_response(
            500,
            "collection_failed",
            "collection workflow failed",
        )

    @application.exception_handler(ProviderError)
    async def provider_error_handler(
        _: Request,
        exception: ProviderError,
    ) -> JSONResponse:
        if isinstance(exception, ProviderReportingDateUnavailableError):
            return _error_response(
                422,
                "reporting_date_unavailable",
                "analytics are unavailable for the requested reporting date",
            )
        if isinstance(exception, ProviderAuthenticationError):
            return _error_response(
                502,
                "upstream_authentication_failed",
                "analytics provider authentication failed",
            )
        if isinstance(exception, ProviderAuthorizationError):
            return _error_response(
                502,
                "upstream_authorization_failed",
                "analytics provider authorization failed",
            )
        if isinstance(exception, ProviderRateLimitError):
            retry_after = exception.retry_after_seconds
            return _error_response(
                429,
                "upstream_rate_limited",
                "analytics provider rate limit exceeded",
                retryable=True,
                headers=(
                    {"Retry-After": str(retry_after)}
                    if retry_after is not None
                    else None
                ),
            )
        if isinstance(exception, ProviderResponseValidationError):
            return _error_response(
                502,
                "upstream_response_invalid",
                "analytics provider returned an invalid response",
            )
        if isinstance(exception, ProviderServerError):
            return _error_response(
                502,
                "upstream_server_error",
                "analytics provider returned a server error",
                retryable=True,
            )
        if isinstance(exception, ProviderTransportError):
            return _error_response(
                503,
                "upstream_unavailable",
                "analytics provider is unavailable",
                retryable=True,
            )
        return _error_response(
            502,
            "upstream_request_failed",
            "analytics provider request failed",
        )

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        _: Request,
        exception: StarletteHTTPException,
    ) -> JSONResponse:
        if exception.status_code == 404:
            return _error_response(404, "not_found", "resource not found")
        return _error_response(
            exception.status_code,
            "http_error",
            "request could not be completed",
        )

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, __: Exception) -> JSONResponse:
        return _error_response(
            500,
            "internal_error",
            "an unexpected error occurred",
        )


def _install_routes(application: FastAPI) -> None:
    @application.get("/", response_model=RootResponse)
    async def root() -> RootResponse:
        return RootResponse(
            service_name=SERVICE_NAME_VALUE,
            version=__version__,
            description=SERVICE_DESCRIPTION,
            endpoints=ENDPOINTS,
        )

    @application.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse()

    @application.get("/health/live", response_model=LivenessResponse)
    async def liveness() -> LivenessResponse:
        return LivenessResponse()

    @application.get("/health/ready", response_model=ReadinessResponse)
    async def readiness(request: Request) -> ReadinessResponse:
        provider = _gateway_service(request).validate_readiness()
        return ReadinessResponse(provider=provider)

    @application.post(
        "/collect",
        response_model=(
            AnthropicOrganizationUsageSummary | MockOrganizationUsageSummary
        ),
    )
    async def collect(
        request: Request,
        reporting_date: Annotated[
            date,
            Query(description="UTC reporting date in YYYY-MM-DD format."),
        ],
    ) -> AnthropicOrganizationUsageSummary | MockOrganizationUsageSummary:
        return await _gateway_service(request).collect(reporting_date)

    @application.get(
        "/preview",
        response_model=PreviewDocument | PreviewDisabledResponse,
    )
    async def preview(
        request: Request,
    ) -> PreviewDocument | PreviewDisabledResponse:
        service = _gateway_service(request)
        if not service.preview_enabled:
            return PreviewDisabledResponse()
        return service.read_preview()


def create_app(
    *,
    settings_factory: SettingsFactory = get_settings,
    manager: TelemetryManager = telemetry_manager,
    service_factory: GatewayServiceFactory = create_gateway_service,
) -> FastAPI:
    """Create the service with explicit routes and privacy-safe errors."""

    application = FastAPI(
        title="GenAI Usage Observability Gateway",
        description=SERVICE_DESCRIPTION,
        version=__version__,
        docs_url=None,
        lifespan=create_lifespan(
            settings_factory=settings_factory,
            manager=manager,
            service_factory=service_factory,
        ),
        openapi_url=None,
        redoc_url=None,
    )
    _install_exception_handlers(application)
    _install_routes(application)
    return application


app = create_app()
