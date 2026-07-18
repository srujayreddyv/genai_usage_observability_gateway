import asyncio
from collections.abc import Callable
from copy import deepcopy
from datetime import date
from math import inf, nan

import httpx
import pytest
from pydantic import SecretStr

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.providers.anthropic import (
    ANTHROPIC_API_VERSION,
    AnthropicAnalyticsClient,
    AnthropicUserActivityRecord,
)
from genai_usage_observability_gateway.providers.base import AnalyticsClient
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

REPORTING_DATE = date(2026, 2, 3)
SYNTHETIC_API_KEY = "synthetic-analytics-key"
Handler = Callable[[httpx.Request], httpx.Response]


def _tool_action_counts() -> dict[str, int]:
    return {"accepted_count": 2, "rejected_count": 1}


def _office_product_metrics() -> dict[str, int]:
    return {
        "connectors_used_count": 2,
        "distinct_connectors_used_count": 1,
        "distinct_session_count": 3,
        "distinct_skills_used_count": 1,
        "message_count": 5,
        "skills_used_count": 2,
    }


def _activity(user_number: int = 1) -> dict[str, object]:
    return {
        "chat_metrics": {
            "connectors_used_count": 2,
            "distinct_artifacts_created_count": 1,
            "distinct_connectors_used_count": 1,
            "distinct_conversation_count": 3,
            "distinct_files_uploaded_count": 1,
            "distinct_projects_created_count": 1,
            "distinct_projects_used_count": 2,
            "distinct_shared_artifacts_viewed_count": 1,
            "distinct_skills_used_count": 1,
            "message_count": 8,
            "shared_conversations_viewed_count": 1,
            "thinking_message_count": 2,
        },
        "claude_code_metrics": {
            "core_metrics": {
                "commit_count": 2,
                "distinct_session_count": 3,
                "lines_of_code": {"added_count": 20, "removed_count": 4},
                "pull_request_count": 1,
            },
            "tool_actions": {
                "edit_tool": _tool_action_counts(),
                "multi_edit_tool": _tool_action_counts(),
                "notebook_edit_tool": _tool_action_counts(),
                "write_tool": _tool_action_counts(),
            },
        },
        "cowork_metrics": {
            "action_count": 4,
            "connectors_used_count": 2,
            "dispatch_turn_count": 1,
            "distinct_connectors_used_count": 1,
            "distinct_session_count": 3,
            "distinct_skills_used_count": 2,
            "message_count": 6,
            "skills_used_count": 3,
            "distinct_plugins_used_count": 1,
            "edit_tool_count": 1,
            "file_edit_count": 1,
            "multi_edit_tool_count": 0,
            "notebook_edit_tool_count": 0,
            "plugins_used_count": 2,
            "sessions_with_file_edits_count": 1,
            "write_tool_count": 1,
        },
        "design_metrics": {
            "distinct_projects_created_count": 1,
            "distinct_projects_used_count": 2,
            "distinct_session_count": 2,
            "message_count": 4,
        },
        "office_metrics": {
            "excel": _office_product_metrics(),
            "outlook": _office_product_metrics(),
            "powerpoint": _office_product_metrics(),
            "word": _office_product_metrics(),
        },
        "science_metrics": {
            "delegation_count": 1,
            "distinct_session_count": 2,
            "message_count": 3,
            "remote_compute_job_count": 1,
            "skills_used_count": 2,
        },
        "web_search_count": 2,
        "last_activity_date": "2026-02-03",
        "user": {
            "id": f"synthetic-user-{user_number:03d}",
            "email_address": f"fictional.user{user_number}@example.com",
        },
    }


def _page(
    activities: list[dict[str, object]], next_page: str | None = None
) -> dict[str, object]:
    return {"data": activities, "next_page": next_page}


async def _invoke(
    handler: Handler,
    *,
    reporting_date: date = REPORTING_DATE,
    result_limit: int = 100,
    timeout_seconds: float = 10.0,
) -> tuple[AnthropicUserActivityRecord, ...]:
    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http_client:
        client = AnthropicAnalyticsClient(
            api_key=SecretStr(SYNTHETIC_API_KEY),
            result_limit=result_limit,
            timeout_seconds=timeout_seconds,
            http_client=http_client,
        )
        return await client.get_usage_analytics(reporting_date)


def test_client_retrieves_every_cursor_page_with_documented_request() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.method == "GET"
        assert request.url.path == "/v1/organizations/analytics/users"
        assert request.url.params["date"] == "2026-02-03"
        assert request.url.params["limit"] == "250"
        assert request.headers["x-api-key"] == SYNTHETIC_API_KEY
        assert request.headers["anthropic-version"] == ANTHROPIC_API_VERSION
        assert "authorization" not in request.headers
        assert request.extensions["timeout"] == {
            "connect": 12.5,
            "read": 12.5,
            "write": 12.5,
            "pool": 12.5,
        }

        if len(requests) == 1:
            assert "page" not in request.url.params
            return httpx.Response(200, json=_page([_activity(1)], "cursor-two"))

        assert request.url.params["page"] == "cursor-two"
        return httpx.Response(200, json=_page([_activity(2)]))

    records = asyncio.run(_invoke(handler, result_limit=250, timeout_seconds=12.5))

    assert len(requests) == 2
    assert len(records) == 2
    assert all(record.reporting_date == REPORTING_DATE for record in records)
    assert records[0].activity.user.id == "synthetic-user-001"
    assert records[1].activity.chat_metrics.message_count == 8
    assert records[1].activity.claude_code_metrics.core_metrics.commit_count == 2


def test_client_satisfies_provider_protocol() -> None:
    client = AnthropicAnalyticsClient(api_key=SecretStr(SYNTHETIC_API_KEY))

    assert isinstance(client, AnalyticsClient)
    assert client.provider is ProviderName.ANTHROPIC


def test_client_can_manage_its_own_mocked_http_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    http_client = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json=_page([_activity()]))
        )
    )
    monkeypatch.setattr(
        "genai_usage_observability_gateway.providers.anthropic.httpx.AsyncClient",
        lambda: http_client,
    )
    client = AnthropicAnalyticsClient(api_key=SecretStr(SYNTHETIC_API_KEY))

    records = asyncio.run(client.get_usage_analytics(REPORTING_DATE))

    assert len(records) == 1
    assert http_client.is_closed


def test_optional_cowork_and_group_fields_accept_missing_or_null() -> None:
    activity = _activity()
    cowork = activity["cowork_metrics"]
    assert isinstance(cowork, dict)
    for field in (
        "distinct_plugins_used_count",
        "edit_tool_count",
        "file_edit_count",
        "multi_edit_tool_count",
        "notebook_edit_tool_count",
        "plugins_used_count",
        "sessions_with_file_edits_count",
        "write_tool_count",
    ):
        cowork.pop(field)
    activity["distinct_user_count"] = None
    activity["last_activity_date"] = None
    activity["rbac_group_id"] = None
    activity["rbac_group_name"] = None

    records = asyncio.run(
        _invoke(lambda _: httpx.Response(200, json=_page([activity])))
    )

    assert records[0].activity.cowork_metrics.edit_tool_count is None
    assert records[0].activity.rbac_group_id is None


def test_empty_page_returns_no_records() -> None:
    records = asyncio.run(_invoke(lambda _: httpx.Response(200, json=_page([]))))

    assert records == ()


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (400, ProviderReportingDateUnavailableError),
        (401, ProviderAuthenticationError),
        (403, ProviderAuthorizationError),
        (404, ProviderError),
    ],
)
def test_client_maps_provider_rejections_to_safe_errors(
    status_code: int, error_type: type[ProviderError]
) -> None:
    upstream_detail = "upstream-secret-detail"

    with pytest.raises(error_type) as error:
        asyncio.run(
            _invoke(
                lambda _: httpx.Response(
                    status_code,
                    json={"error": {"message": upstream_detail}},
                )
            )
        )

    assert upstream_detail not in str(error.value)
    assert SYNTHETIC_API_KEY not in str(error.value)


@pytest.mark.parametrize("status_code", [500, 504, 529])
def test_client_maps_server_failures_without_copying_response(
    status_code: int,
) -> None:
    with pytest.raises(ProviderServerError) as error:
        asyncio.run(
            _invoke(
                lambda _: httpx.Response(
                    status_code,
                    text="sensitive-upstream-server-detail",
                )
            )
        )

    assert error.value.status_code == status_code
    assert "sensitive-upstream-server-detail" not in str(error.value)


@pytest.mark.parametrize(
    ("retry_after", "expected"),
    [("17", 17), ("not-a-number", None), (None, None)],
)
def test_rate_limit_error_parses_only_integer_retry_after(
    retry_after: str | None, expected: int | None
) -> None:
    headers = {"retry-after": retry_after} if retry_after is not None else None

    with pytest.raises(ProviderRateLimitError) as error:
        asyncio.run(
            _invoke(lambda _: httpx.Response(429, headers=headers, text="private"))
        )

    assert error.value.retry_after_seconds == expected
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "content",
    [
        b"not-json",
        b'{"data": [], "next_page": null, "unexpected": true}',
        b'{"data": [{}], "next_page": null}',
    ],
)
def test_malformed_or_unexpected_response_is_rejected(content: bytes) -> None:
    with pytest.raises(ProviderResponseValidationError) as error:
        asyncio.run(_invoke(lambda _: httpx.Response(200, content=content)))

    assert str(error.value) == "analytics provider returned an invalid response"
    assert error.value.__cause__ is None


def test_negative_metric_is_rejected() -> None:
    activity = _activity()
    chat_metrics = activity["chat_metrics"]
    assert isinstance(chat_metrics, dict)
    chat_metrics["message_count"] = -1

    with pytest.raises(ProviderResponseValidationError):
        asyncio.run(_invoke(lambda _: httpx.Response(200, json=_page([activity]))))


def test_repeated_pagination_cursor_is_rejected() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_page([deepcopy(_activity())], "repeat"))

    with pytest.raises(
        ProviderResponseValidationError, match="repeated pagination cursor"
    ):
        asyncio.run(_invoke(handler))


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_transport_errors_are_wrapped_without_request_details(
    error_type: type[httpx.RequestError],
) -> None:
    request = httpx.Request(
        "GET", f"https://api.anthropic.com/private?credential={SYNTHETIC_API_KEY}"
    )

    def handler(_: httpx.Request) -> httpx.Response:
        raise error_type("transport-private-detail", request=request)

    with pytest.raises(ProviderTransportError) as error:
        asyncio.run(_invoke(handler))

    assert str(error.value) == "analytics provider request failed"
    assert error.value.__cause__ is None
    assert SYNTHETIC_API_KEY not in str(error.value)
    assert "transport-private-detail" not in str(error.value)


def test_reporting_dates_before_public_analytics_window_do_not_make_request() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_page([]))

    with pytest.raises(ProviderReportingDateUnavailableError):
        asyncio.run(_invoke(handler, reporting_date=date(2025, 12, 31)))

    assert calls == 0


def test_api_key_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="api_key must not be empty"):
        AnthropicAnalyticsClient(api_key=SecretStr("  "))


@pytest.mark.parametrize("result_limit", [0, 1001])
def test_result_limit_must_match_provider_bounds(result_limit: int) -> None:
    with pytest.raises(ValueError, match="between 1 and 1000"):
        AnthropicAnalyticsClient(
            api_key=SecretStr(SYNTHETIC_API_KEY), result_limit=result_limit
        )


@pytest.mark.parametrize("result_limit", [True, 1.5, "100"])
def test_result_limit_must_be_an_integer(result_limit: object) -> None:
    with pytest.raises(TypeError, match="must be an integer"):
        AnthropicAnalyticsClient(
            api_key=SecretStr(SYNTHETIC_API_KEY),
            result_limit=result_limit,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize("timeout_seconds", [0.0, -1.0, inf, nan])
def test_timeout_must_be_finite_and_positive(timeout_seconds: float) -> None:
    with pytest.raises(ValueError, match="finite and positive"):
        AnthropicAnalyticsClient(
            api_key=SecretStr(SYNTHETIC_API_KEY), timeout_seconds=timeout_seconds
        )


@pytest.mark.parametrize("timeout_seconds", [True, "10"])
def test_timeout_must_be_numeric(timeout_seconds: object) -> None:
    with pytest.raises(TypeError, match="must be numeric"):
        AnthropicAnalyticsClient(
            api_key=SecretStr(SYNTHETIC_API_KEY),
            timeout_seconds=timeout_seconds,  # type: ignore[arg-type]
        )
