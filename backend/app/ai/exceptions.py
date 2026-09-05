"""Custom exceptions for the AI integration layer.

All AI-related exceptions inherit from AIError, allowing callers
to catch broadly (AIError) or narrowly (e.g., AITimeoutError).

IMPORTANT: None of these exceptions should ever include API keys
or other sensitive data in their messages.
"""


class AIError(Exception):
    """Base exception for all AI-related errors."""
    pass


class AIConfigurationError(AIError):
    """Raised when AI configuration is missing or invalid.

    Examples: missing API key when trying to use the provider,
    invalid model name, malformed configuration values.
    """
    pass


class AIProviderUnavailableError(AIError):
    """Raised when the AI provider is not configured or is disabled.

    This is a soft error — the application continues to function,
    but AI features are not available.
    """
    pass


class AITimeoutError(AIError):
    """Raised when an AI API call exceeds the configured timeout."""
    pass


class AIProviderError(AIError):
    """Raised when the upstream AI API returns an error.

    Examples: rate limiting, server errors, authentication failures.
    The original error message is preserved but API keys are stripped.
    """
    pass


class AIInvalidResponseError(AIError):
    """Raised when the AI provider returns a response that doesn't
    match the expected format or schema.

    Examples: empty response, malformed JSON when a schema was
    requested, missing required fields.
    """
    pass
