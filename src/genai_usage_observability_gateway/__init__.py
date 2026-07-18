"""GenAI Usage Observability Gateway."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("genai-usage-observability-gateway")
except PackageNotFoundError:  # pragma: no cover - source tree without installation
    __version__ = "0.0.0"

__all__ = ["__version__"]
