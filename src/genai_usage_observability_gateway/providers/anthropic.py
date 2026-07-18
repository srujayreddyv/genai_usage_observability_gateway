"""Anthropic Claude Enterprise User Activity API integration."""

from datetime import date
from math import isfinite

import httpx
from pydantic import EmailStr, SecretStr, ValidationError

from genai_usage_observability_gateway.config import ProviderName
from genai_usage_observability_gateway.models.usage import (
    NonEmptyString,
    NonNegativeCount,
    StrictDomainModel,
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

ANTHROPIC_API_BASE_URL = "https://api.anthropic.com"
USER_ACTIVITY_PATH = "/v1/organizations/analytics/users"
ANTHROPIC_API_VERSION = "2023-06-01"
EARLIEST_REPORTING_DATE = date(2026, 1, 1)


class AnthropicAnalyticsUser(StrictDomainModel):
    """User identity returned by the Anthropic analytics API."""

    id: NonEmptyString
    email_address: EmailStr


class AnthropicChatMetrics(StrictDomainModel):
    """Publicly documented Claude chat metrics."""

    connectors_used_count: NonNegativeCount
    distinct_artifacts_created_count: NonNegativeCount
    distinct_connectors_used_count: NonNegativeCount
    distinct_conversation_count: NonNegativeCount
    distinct_files_uploaded_count: NonNegativeCount
    distinct_projects_created_count: NonNegativeCount
    distinct_projects_used_count: NonNegativeCount
    distinct_shared_artifacts_viewed_count: NonNegativeCount
    distinct_skills_used_count: NonNegativeCount
    message_count: NonNegativeCount
    shared_conversations_viewed_count: NonNegativeCount
    thinking_message_count: NonNegativeCount


class AnthropicLinesOfCode(StrictDomainModel):
    """Lines changed through Claude Code."""

    added_count: NonNegativeCount
    removed_count: NonNegativeCount


class AnthropicClaudeCodeCoreMetrics(StrictDomainModel):
    """Publicly documented core Claude Code metrics."""

    commit_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    lines_of_code: AnthropicLinesOfCode
    pull_request_count: NonNegativeCount


class AnthropicToolActionCounts(StrictDomainModel):
    """Accepted and rejected proposals for one Claude Code tool."""

    accepted_count: NonNegativeCount
    rejected_count: NonNegativeCount


class AnthropicToolActions(StrictDomainModel):
    """Publicly documented Claude Code edit-tool actions."""

    edit_tool: AnthropicToolActionCounts
    multi_edit_tool: AnthropicToolActionCounts
    notebook_edit_tool: AnthropicToolActionCounts
    write_tool: AnthropicToolActionCounts


class AnthropicClaudeCodeMetrics(StrictDomainModel):
    """Publicly documented Claude Code activity block."""

    core_metrics: AnthropicClaudeCodeCoreMetrics
    tool_actions: AnthropicToolActions


class AnthropicCoworkMetrics(StrictDomainModel):
    """Publicly documented Cowork activity metrics."""

    action_count: NonNegativeCount
    connectors_used_count: NonNegativeCount
    dispatch_turn_count: NonNegativeCount
    distinct_connectors_used_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    distinct_skills_used_count: NonNegativeCount
    message_count: NonNegativeCount
    skills_used_count: NonNegativeCount
    distinct_plugins_used_count: NonNegativeCount | None = None
    edit_tool_count: NonNegativeCount | None = None
    file_edit_count: NonNegativeCount | None = None
    multi_edit_tool_count: NonNegativeCount | None = None
    notebook_edit_tool_count: NonNegativeCount | None = None
    plugins_used_count: NonNegativeCount | None = None
    sessions_with_file_edits_count: NonNegativeCount | None = None
    write_tool_count: NonNegativeCount | None = None


class AnthropicDesignMetrics(StrictDomainModel):
    """Publicly documented Claude Design metrics."""

    distinct_projects_created_count: NonNegativeCount
    distinct_projects_used_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    message_count: NonNegativeCount


class AnthropicOfficeProductMetrics(StrictDomainModel):
    """Publicly documented metrics for one Office product."""

    connectors_used_count: NonNegativeCount
    distinct_connectors_used_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    distinct_skills_used_count: NonNegativeCount
    message_count: NonNegativeCount
    skills_used_count: NonNegativeCount


class AnthropicOfficeMetrics(StrictDomainModel):
    """Publicly documented Office activity by product."""

    excel: AnthropicOfficeProductMetrics
    outlook: AnthropicOfficeProductMetrics
    powerpoint: AnthropicOfficeProductMetrics
    word: AnthropicOfficeProductMetrics


class AnthropicScienceMetrics(StrictDomainModel):
    """Publicly documented Claude Science metrics."""

    delegation_count: NonNegativeCount
    distinct_session_count: NonNegativeCount
    message_count: NonNegativeCount
    remote_compute_job_count: NonNegativeCount
    skills_used_count: NonNegativeCount


class AnthropicUserActivityData(StrictDomainModel):
    """One upstream user activity object before reporting-date attachment."""

    chat_metrics: AnthropicChatMetrics
    claude_code_metrics: AnthropicClaudeCodeMetrics
    cowork_metrics: AnthropicCoworkMetrics
    design_metrics: AnthropicDesignMetrics
    office_metrics: AnthropicOfficeMetrics
    science_metrics: AnthropicScienceMetrics
    web_search_count: NonNegativeCount
    user: AnthropicAnalyticsUser
    distinct_user_count: NonNegativeCount | None = None
    last_activity_date: date | None = None
    rbac_group_id: NonEmptyString | None = None
    rbac_group_name: NonEmptyString | None = None


class AnthropicUserActivityPage(StrictDomainModel):
    """Validated cursor page from the Anthropic User Activity API."""

    data: tuple[AnthropicUserActivityData, ...]
    next_page: NonEmptyString | None


class AnthropicUserActivityRecord(StrictDomainModel):
    """Validated activity coupled to the UTC date used to retrieve it."""

    reporting_date: date
    activity: AnthropicUserActivityData


class AnthropicAnalyticsClient:
    """Async client for the Claude Enterprise User Activity API."""

    def __init__(
        self,
        *,
        api_key: SecretStr,
        result_limit: int = 100,
        timeout_seconds: float = 10.0,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not api_key.get_secret_value().strip():
            raise ValueError("api_key must not be empty")
        if isinstance(result_limit, bool) or not isinstance(result_limit, int):
            raise TypeError("result_limit must be an integer")
        if not 1 <= result_limit <= 1000:
            raise ValueError("result_limit must be between 1 and 1000")
        if isinstance(timeout_seconds, bool) or not isinstance(
            timeout_seconds, int | float
        ):
            raise TypeError("timeout_seconds must be numeric")
        if not isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")

        self._api_key = api_key
        self._result_limit = result_limit
        self._timeout = httpx.Timeout(float(timeout_seconds))
        self._http_client = http_client

    @property
    def provider(self) -> ProviderName:
        """Return the Anthropic provider identifier."""

        return ProviderName.ANTHROPIC

    async def get_usage_analytics(
        self, reporting_date: date
    ) -> tuple[AnthropicUserActivityRecord, ...]:
        """Retrieve and validate every cursor page for one UTC date."""

        if reporting_date < EARLIEST_REPORTING_DATE:
            raise ProviderReportingDateUnavailableError(
                "analytics provider does not support the requested reporting date"
            )

        if self._http_client is not None:
            return await self._retrieve_all_pages(self._http_client, reporting_date)

        async with httpx.AsyncClient() as client:
            return await self._retrieve_all_pages(client, reporting_date)

    async def _retrieve_all_pages(
        self, client: httpx.AsyncClient, reporting_date: date
    ) -> tuple[AnthropicUserActivityRecord, ...]:
        records: list[AnthropicUserActivityRecord] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()

        while True:
            page = await self._retrieve_page(client, reporting_date, cursor)
            records.extend(
                AnthropicUserActivityRecord(
                    reporting_date=reporting_date,
                    activity=activity,
                )
                for activity in page.data
            )

            cursor = page.next_page
            if cursor is None:
                return tuple(records)
            if cursor in seen_cursors:
                raise ProviderResponseValidationError(
                    "analytics provider returned a repeated pagination cursor"
                )
            seen_cursors.add(cursor)

    async def _retrieve_page(
        self,
        client: httpx.AsyncClient,
        reporting_date: date,
        cursor: str | None,
    ) -> AnthropicUserActivityPage:
        params: dict[str, str | int] = {
            "date": reporting_date.isoformat(),
            "limit": self._result_limit,
        }
        if cursor is not None:
            params["page"] = cursor

        try:
            response = await client.get(
                f"{ANTHROPIC_API_BASE_URL}{USER_ACTIVITY_PATH}",
                headers=self._request_headers(),
                params=params,
                timeout=self._timeout,
            )
        except httpx.RequestError:
            raise ProviderTransportError("analytics provider request failed") from None

        self._raise_for_error_status(response)

        try:
            return AnthropicUserActivityPage.model_validate_json(response.content)
        except ValidationError:
            raise ProviderResponseValidationError(
                "analytics provider returned an invalid response"
            ) from None

    def _request_headers(self) -> dict[str, str]:
        return {
            "anthropic-version": ANTHROPIC_API_VERSION,
            "x-api-key": self._api_key.get_secret_value(),
        }

    @staticmethod
    def _raise_for_error_status(response: httpx.Response) -> None:
        status_code = response.status_code
        if status_code < 400:
            return
        if status_code == 400:
            raise ProviderReportingDateUnavailableError(
                "analytics are unavailable for the requested reporting date"
            )
        if status_code == 401:
            raise ProviderAuthenticationError(
                "analytics provider authentication failed"
            )
        if status_code == 403:
            raise ProviderAuthorizationError("analytics provider authorization failed")
        if status_code == 429:
            retry_after = response.headers.get("retry-after")
            retry_after_seconds = (
                int(retry_after) if retry_after and retry_after.isdigit() else None
            )
            raise ProviderRateLimitError(retry_after_seconds)
        if status_code >= 500:
            raise ProviderServerError(status_code)
        raise ProviderError("analytics provider request was rejected")
