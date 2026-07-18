"""Secret-safe provider integration errors."""


class ProviderError(RuntimeError):
    """Base error for analytics provider failures."""


class ProviderAuthenticationError(ProviderError):
    """The provider rejected the configured credential."""


class ProviderAuthorizationError(ProviderError):
    """The credential cannot access the requested analytics resource."""


class ProviderRateLimitError(ProviderError):
    """The provider rejected a request because of rate limiting."""

    def __init__(self, retry_after_seconds: int | None = None) -> None:
        super().__init__("analytics provider rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


class ProviderReportingDateUnavailableError(ProviderError):
    """Analytics are not available for the requested reporting date."""


class ProviderResponseValidationError(ProviderError):
    """The provider returned a malformed or unexpected response."""


class ProviderServerError(ProviderError):
    """The provider returned a server-side failure."""

    def __init__(self, status_code: int) -> None:
        super().__init__("analytics provider server failure")
        self.status_code = status_code


class ProviderTransportError(ProviderError):
    """The provider request failed before a valid response arrived."""
