"""Phase 18: a provider error abstraction distinguishing every failure
category a real read-only HTTP provider integration can hit, so the rest of
the system never has to inspect a raw HTTP status code or a provider-
specific exception type. No raw provider internals (response bodies,
headers, stack traces) are ever exposed to a caller through these -- see
`str(exc)` usage in tests for the exact, safe message shape.
"""
from __future__ import annotations


class ProviderError(Exception):
    """Base for every adapter-layer failure. `category` is a stable,
    machine-readable string (mirrors the API's own {code, message} error
    contract discipline, app.api.errors) -- never a raw exception repr."""

    category: str = "PROVIDER_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ProviderAuthenticationError(ProviderError):
    category = "AUTHENTICATION_FAILED"


class ProviderAuthorizationError(ProviderError):
    category = "AUTHORIZATION_FAILED"


class ProviderRateLimitError(ProviderError):
    category = "RATE_LIMITED"

    def __init__(self, message: str, retry_after_seconds: float | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderTimeoutError(ProviderError):
    category = "TIMEOUT"


class ProviderNetworkError(ProviderError):
    category = "NETWORK_ERROR"


class ProviderNotFoundError(ProviderError):
    category = "NOT_FOUND"


class ProviderResponseError(ProviderError):
    """The provider responded, but the payload could not be safely
    interpreted -- malformed JSON, an unexpected type, a missing
    financially-meaningful field, or an unrecognized nested structure.
    Never silently reinterpreted; always raised."""

    category = "INVALID_RESPONSE"


class ProviderSchemaMismatchError(ProviderResponseError):
    category = "SCHEMA_MISMATCH"


class ProviderPaginationError(ProviderError):
    category = "PAGINATION_ERROR"
