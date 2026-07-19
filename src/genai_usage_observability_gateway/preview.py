"""Privacy-safe in-memory preview generation."""

from collections.abc import Sequence

from genai_usage_observability_gateway.normalization import (
    AnthropicNormalizedUsageRecord,
)
from genai_usage_observability_gateway.privacy import (
    AnthropicPrivacySafeCollection,
    HmacSha256Pseudonymizer,
    protect_anthropic_collection,
)


class AnthropicUsagePreview(AnthropicPrivacySafeCollection):
    """JSON-serializable preview containing only privacy-safe collection data."""


def build_anthropic_usage_preview(
    records: Sequence[AnthropicNormalizedUsageRecord],
    pseudonymizer: HmacSha256Pseudonymizer,
) -> AnthropicUsagePreview:
    """Protect and aggregate records before constructing preview output."""

    collection = protect_anthropic_collection(records, pseudonymizer)
    return build_anthropic_usage_preview_from_collection(collection)


def build_anthropic_usage_preview_from_collection(
    collection: AnthropicPrivacySafeCollection,
) -> AnthropicUsagePreview:
    """Construct a preview from an already protected and aggregated collection."""

    return AnthropicUsagePreview.model_validate(collection.model_dump())


def render_usage_preview(preview: AnthropicUsagePreview) -> str:
    """Render deterministic JSON without writing a local file."""

    return preview.model_dump_json(indent=2)
