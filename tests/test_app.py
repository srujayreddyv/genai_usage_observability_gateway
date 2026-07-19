"""Tests for the FastAPI service contract and secret-safe error boundary."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from genai_usage_observability_gateway.aggregation import (
    MockOrganizationUsageSummary,
    aggregate_mock_usage,
)
from genai_usage_observability_gateway.app import create_app
from genai_usage_observability_gateway.config import (
    AppSettings,
    DeploymentEnvironment,
    ProviderName,
)
from genai_usage_observability_gateway.normalization import normalize_mock_records
from genai_usage_observability_gateway.preview import (
    MockUsagePreview,
    PreviewDocument,
    build_mock_usage_preview_from_collection,
)
from genai_usage_observability_gateway.privacy import (
    HmacSha256Pseudonymizer,
    protect_mock_collection,
)
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
from genai_usage_observability_gateway.providers.mock import build_synthetic_usage
from genai_usage_observability_gateway.service import (
    CollectionFailedError,
    OrganizationSummary,
    PreviewNotFoundError,
    PreviewReadError,
    ServiceConfigurationError,
)
from genai_usage_observability_gateway.telemetry import TelemetryManager

REPORTING_DATE = date(2026, 2, 3)


def _summary() -> MockOrganizationUsageSummary:
    return aggregate_mock_usage(
        normalize_mock_records(build_synthetic_usage(REPORTING_DATE))
    )


def _preview() -> MockUsagePreview:
    collection = protect_mock_collection(
        normalize_mock_records(build_synthetic_usage(REPORTING_DATE)),
        HmacSha256Pseudonymizer(SecretStr("synthetic-app-test-key")),
    )
    return build_mock_usage_preview_from_collection(
        collection,
        collection_timestamp=datetime(2026, 2, 3, 12, tzinfo=UTC),
    )


@dataclass
class FakeGatewayService:
    preview_enabled: bool = False
    readiness_result: ProviderName = ProviderName.MOCK
    readiness_exception: Exception | None = None
    collect_result: OrganizationSummary | None = None
    collect_exception: Exception | None = None
    preview_result: PreviewDocument | None = None
    preview_exception: Exception | None = None
    readiness_calls: int = 0
    collection_calls: int = 0
    preview_calls: int = 0

    def validate_readiness(self) -> ProviderName:
        self.readiness_calls += 1
        if self.readiness_exception is not None:
            raise self.readiness_exception
        return self.readiness_result

    async def collect(self, reporting_date: date) -> OrganizationSummary:
        self.collection_calls += 1
        assert reporting_date == REPORTING_DATE
        if self.collect_exception is not None:
            raise self.collect_exception
        assert self.collect_result is not None
        return self.collect_result

    def read_preview(self) -> PreviewDocument:
        self.preview_calls += 1
        if self.preview_exception is not None:
            raise self.preview_exception
        assert self.preview_result is not None
        return self.preview_result


@contextmanager
def _client(
    service: FakeGatewayService,
    *,
    settings: AppSettings | None = None,
) -> Iterator[TestClient]:
    selected_settings = settings or AppSettings(
        app_environment=DeploymentEnvironment.TEST
    )
    manager = TelemetryManager()
    application = create_app(
        settings_factory=lambda: selected_settings,
        manager=manager,
        service_factory=lambda _settings, _telemetry: service,
    )
    with TestClient(application, raise_server_exceptions=False) as client:
        yield client
    assert manager.active_runtime is None


def test_root_documents_exact_service_endpoints() -> None:
    service = FakeGatewayService()

    with _client(service) as client:
        response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service_name"] == "genai-usage-observability-gateway"
    assert body["version"] == "0.1.0"
    assert "privacy" in body["description"].lower()
    assert {(item["method"], item["path"]) for item in body["endpoints"]} == {
        ("GET", "/"),
        ("GET", "/health"),
        ("GET", "/health/live"),
        ("GET", "/health/ready"),
        ("POST", "/collect"),
        ("GET", "/preview"),
    }


def test_health_and_liveness_do_not_check_provider_readiness() -> None:
    service = FakeGatewayService(
        readiness_exception=ServiceConfigurationError("sensitive configuration")
    )

    with _client(service) as client:
        health = client.get("/health")
        liveness = client.get("/health/live")

    assert health.status_code == 200
    assert health.json() == {"status": "healthy"}
    assert liveness.status_code == 200
    assert liveness.json() == {"status": "alive"}
    assert service.readiness_calls == 0


def test_readiness_returns_only_safe_selected_provider() -> None:
    service = FakeGatewayService(readiness_result=ProviderName.ANTHROPIC)

    with _client(service) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "provider": "anthropic"}
    assert service.readiness_calls == 1


def test_configuration_error_is_consistent_and_secret_safe() -> None:
    sensitive = "synthetic-sensitive-configuration-detail"
    service = FakeGatewayService(
        readiness_exception=ServiceConfigurationError(sensitive)
    )

    with _client(service) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "configuration_error",
            "message": "service configuration is not ready",
            "retryable": False,
        }
    }
    assert sensitive not in response.text


@pytest.mark.parametrize("query", ["", "?reporting_date=not-a-date"])
def test_collect_requires_a_valid_date_without_echoing_input(query: str) -> None:
    service = FakeGatewayService(collect_result=_summary())

    with _client(service) as client:
        response = client.post(f"/collect{query}")

    assert response.status_code == 422
    assert response.json() == {
        "error": {
            "code": "invalid_request",
            "message": "request validation failed",
            "retryable": False,
        }
    }
    assert "not-a-date" not in response.text
    assert service.collection_calls == 0


def test_collect_returns_only_safe_organization_summary() -> None:
    service = FakeGatewayService(collect_result=_summary())

    with _client(service) as client:
        response = client.post("/collect?reporting_date=2026-02-03")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["total_users"] == 5
    assert body["active_users"] == 4
    assert "usage_records" not in body
    assert "pseudonymous_user_id" not in response.text
    assert "email" not in response.text
    assert service.collection_calls == 1


def test_preview_disabled_returns_clear_response_without_reading_file() -> None:
    service = FakeGatewayService(preview_enabled=False)

    with _client(service) as client:
        response = client.get("/preview")

    assert response.status_code == 200
    assert response.json() == {
        "status": "disabled",
        "message": "development preview is disabled",
    }
    assert service.preview_calls == 0


def test_preview_returns_parsed_privacy_safe_document() -> None:
    service = FakeGatewayService(preview_enabled=True, preview_result=_preview())

    with _client(service) as client:
        response = client.get("/preview")

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert body["collection_timestamp"] == "2026-02-03T12:00:00Z"
    assert len(body["usage_records"]) == 5
    assert all("pseudonymous_user_id" in record for record in body["usage_records"])
    assert "email" not in response.text


@pytest.mark.parametrize(
    ("exception", "status_code", "code", "retryable"),
    [
        (
            ProviderReportingDateUnavailableError("sensitive upstream detail"),
            422,
            "reporting_date_unavailable",
            False,
        ),
        (
            ProviderAuthenticationError("sensitive credential detail"),
            502,
            "upstream_authentication_failed",
            False,
        ),
        (
            ProviderAuthorizationError("sensitive authorization detail"),
            502,
            "upstream_authorization_failed",
            False,
        ),
        (ProviderRateLimitError(17), 429, "upstream_rate_limited", True),
        (
            ProviderResponseValidationError("sensitive response body"),
            502,
            "upstream_response_invalid",
            False,
        ),
        (ProviderServerError(529), 502, "upstream_server_error", True),
        (
            ProviderTransportError("sensitive request URL"),
            503,
            "upstream_unavailable",
            True,
        ),
        (
            ProviderError("sensitive provider rejection"),
            502,
            "upstream_request_failed",
            False,
        ),
        (
            CollectionFailedError("sensitive local file path"),
            500,
            "collection_failed",
            False,
        ),
    ],
)
def test_collection_errors_use_safe_consistent_json(
    exception: Exception,
    status_code: int,
    code: str,
    retryable: bool,
) -> None:
    service = FakeGatewayService(collect_exception=exception)

    with _client(service) as client:
        response = client.post("/collect?reporting_date=2026-02-03")

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert response.json()["error"]["retryable"] is retryable
    if not isinstance(exception, ProviderRateLimitError):
        assert str(exception) not in response.text
    if isinstance(exception, ProviderRateLimitError):
        assert response.headers["retry-after"] == "17"


@pytest.mark.parametrize(
    ("exception", "status_code", "code"),
    [
        (PreviewNotFoundError("sensitive preview path"), 404, "preview_not_found"),
        (PreviewReadError("sensitive preview content"), 500, "preview_invalid"),
    ],
)
def test_preview_errors_are_safe_and_consistent(
    exception: Exception,
    status_code: int,
    code: str,
) -> None:
    service = FakeGatewayService(
        preview_enabled=True,
        preview_exception=exception,
    )

    with _client(service) as client:
        response = client.get("/preview")

    assert response.status_code == status_code
    assert response.json()["error"]["code"] == code
    assert str(exception) not in response.text


def test_unknown_routes_and_methods_use_consistent_errors() -> None:
    service = FakeGatewayService()

    with _client(service) as client:
        missing = client.get("/not-a-real-route")
        method = client.delete("/health")

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert method.status_code == 405
    assert method.json()["error"]["code"] == "http_error"


def test_unexpected_errors_never_echo_exception_details() -> None:
    sensitive = "synthetic unexpected credential and path detail"
    service = FakeGatewayService(collect_exception=RuntimeError(sensitive))

    with _client(service) as client:
        response = client.post("/collect?reporting_date=2026-02-03")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert sensitive not in response.text


def test_default_mock_service_collects_five_users_and_serves_preview(
    tmp_path: Path,
) -> None:
    output_path = tmp_path / "api" / "usage-preview.json"
    settings = AppSettings(
        app_environment=DeploymentEnvironment.TEST,
        preview_enabled=True,
        preview_output_path=output_path,
    )
    manager = TelemetryManager()
    application = create_app(
        settings_factory=lambda: settings,
        manager=manager,
    )

    with TestClient(application) as client:
        collection = client.post("/collect?reporting_date=2026-02-03")
        preview = client.get("/preview")

    assert collection.status_code == 200
    assert collection.json()["provider"] == "mock"
    assert collection.json()["total_users"] == 5
    assert "usage_records" not in collection.json()
    assert preview.status_code == 200
    assert preview.json()["provider"] == "mock"
    assert len(preview.json()["usage_records"]) == 5
    assert all(
        len(record["pseudonymous_user_id"]) == 16
        for record in preview.json()["usage_records"]
    )
    assert output_path.exists()
    assert manager.active_runtime is None
