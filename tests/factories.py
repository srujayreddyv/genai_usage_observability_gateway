"""Synthetic Anthropic response factories shared across test modules."""

import json
from datetime import date

from genai_usage_observability_gateway.providers.anthropic import (
    AnthropicUserActivityPage,
    AnthropicUserActivityRecord,
)


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


def anthropic_activity_payload(user_number: int = 1) -> dict[str, object]:
    """Build a complete fictional public User Activity response item."""

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


def anthropic_page_payload(
    activities: list[dict[str, object]], next_page: str | None = None
) -> dict[str, object]:
    """Wrap fictional activities in the public cursor-page shape."""

    return {"data": activities, "next_page": next_page}


def anthropic_record_from_payload(
    payload: dict[str, object], reporting_date: date = date(2026, 2, 3)
) -> AnthropicUserActivityRecord:
    """Validate a fictional JSON payload and attach its requested UTC date."""

    page = AnthropicUserActivityPage.model_validate_json(
        json.dumps(anthropic_page_payload([payload]))
    )
    return AnthropicUserActivityRecord(
        reporting_date=reporting_date,
        activity=page.data[0],
    )
