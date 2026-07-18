"""GenAI Usage Observability Gateway."""

from importlib.metadata import PackageNotFoundError, version

from genai_usage_observability_gateway.config import get_settings
from genai_usage_observability_gateway.models import NormalizedUsageRecord
from genai_usage_observability_gateway.providers import AnalyticsClient

try:
    __version__ = version("genai-usage-observability-gateway")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.0.0"

__all__ = ["AnalyticsClient", "NormalizedUsageRecord", "__version__", "get_settings"]
