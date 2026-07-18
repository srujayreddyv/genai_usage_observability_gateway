"""FastAPI application construction and process lifecycle."""

from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from fastapi import FastAPI

from genai_usage_observability_gateway.config import AppSettings, get_settings
from genai_usage_observability_gateway.telemetry import (
    TelemetryManager,
    telemetry_manager,
)

SettingsFactory = Callable[[], AppSettings]
Lifespan = Callable[[FastAPI], AbstractAsyncContextManager[None]]


def create_lifespan(
    *,
    settings_factory: SettingsFactory = get_settings,
    manager: TelemetryManager = telemetry_manager,
) -> Lifespan:
    """Create a FastAPI lifespan that owns one telemetry-manager lease."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        runtime = manager.initialize(settings_factory())
        application.state.telemetry = runtime
        try:
            yield
        finally:
            manager.shutdown()

    return lifespan


def create_app(
    *,
    settings_factory: SettingsFactory = get_settings,
    manager: TelemetryManager = telemetry_manager,
) -> FastAPI:
    """Create the endpoint-free application shell for lifecycle initialization."""

    return FastAPI(
        title="GenAI Usage Observability Gateway",
        docs_url=None,
        lifespan=create_lifespan(
            settings_factory=settings_factory,
            manager=manager,
        ),
        openapi_url=None,
        redoc_url=None,
    )


app = create_app()
