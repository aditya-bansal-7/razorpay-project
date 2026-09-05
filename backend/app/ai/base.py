"""Abstract base class for AI providers.

All providers implement this interface so the rest of the application
depends on `AIProvider`, never on a specific vendor SDK.
"""

from __future__ import annotations


class AIProvider:
    """Provider-independent interface for LLM interactions.

    Subclasses must implement all methods.  The ``response_schema``
    parameter on :meth:`generate` is the hook for future structured
    JSON output — providers should pass it through to their SDK when
    present.
    """

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_schema: dict | None = None,
    ) -> str:
        """Send a prompt to the LLM and return the text response.

        Args:
            prompt: The user/task prompt.
            system_prompt: Optional system-level instruction.
            response_schema: Optional JSON-schema dict for structured
                output.  When provided, the provider should request
                JSON output conforming to this schema.

        Returns:
            The model's text response.

        Raises:
            AIProviderUnavailableError: Provider is not configured.
            AITimeoutError: The request timed out.
            AIProviderError: The upstream API returned an error.
            AIInvalidResponseError: The response was empty or malformed.
        """
        raise NotImplementedError

    def is_available(self) -> bool:
        """Return True if the provider is configured and ready."""
        raise NotImplementedError

    def health(self) -> dict:
        """Return a health-check dict without calling the API.

        Expected keys: enabled, provider, configured, model.
        """
        raise NotImplementedError
