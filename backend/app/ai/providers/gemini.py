"""Gemini AI provider implementation.

Isolates all Google Gemini SDK usage behind the AIProvider interface.
No other module in the application should import from google.genai
directly.
"""

from __future__ import annotations

import logging

from ..base import AIProvider
from ..config import AIConfig
from ..exceptions import (
    AIInvalidResponseError,
    AIProviderError,
    AIProviderUnavailableError,
    AITimeoutError,
)

logger = logging.getLogger(__name__)


class GeminiProvider(AIProvider):
    """AIProvider implementation backed by the Google Gemini API.

    Args:
        config: An ``AIConfig`` instance holding API key, model name,
            timeout, and enabled state.
    """

    PROVIDER_NAME = "gemini"

    def __init__(self, config: AIConfig) -> None:
        self._config = config
        self._client = None

        if config.is_configured:
            try:
                from google import genai  # noqa: delayed import

                self._client = genai.Client(api_key=config.api_key)
            except Exception as exc:
                logger.warning(
                    "Failed to initialise Gemini client: %s", exc
                )

    # ------------------------------------------------------------------
    # AIProvider interface
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_schema: dict | None = None,
    ) -> str:
        """Generate a response using the Gemini API.

        Args:
            prompt: The user/task prompt.
            system_prompt: Optional system-level instruction.
            response_schema: Optional JSON-schema dict.  When provided,
                the API is asked to return ``application/json`` output
                conforming to this schema.

        Returns:
            The model's text response.
        """
        if self._client is None:
            raise AIProviderUnavailableError(
                "Gemini provider is not configured. "
                "Set GEMINI_API_KEY to enable AI features."
            )

        try:
            from google.genai import types  # noqa: delayed import

            # Build generation config
            generation_config_kwargs: dict = {}
            if response_schema is not None:
                generation_config_kwargs["response_mime_type"] = (
                    "application/json"
                )
                generation_config_kwargs["response_schema"] = response_schema

            generation_config = (
                types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    **generation_config_kwargs,
                )
                if system_prompt or generation_config_kwargs
                else None
            )

            response = self._client.models.generate_content(
                model=self._config.model_name,
                contents=prompt,
                config=generation_config,
            )

            if not response or not response.text:
                raise AIInvalidResponseError(
                    "Gemini returned an empty response."
                )

            return response.text

        except AIInvalidResponseError:
            raise
        except AIProviderUnavailableError:
            raise
        except Exception as exc:
            error_str = str(exc).lower()
            # Map known error patterns to our exception hierarchy
            if "timeout" in error_str or "deadline" in error_str:
                raise AITimeoutError(
                    f"Gemini API request timed out: {exc}"
                ) from exc
            raise AIProviderError(
                f"Gemini API error: {exc}"
            ) from exc

    def is_available(self) -> bool:
        """True when the Gemini client was successfully initialised."""
        return self._client is not None

    def health(self) -> dict:
        """Return health status without calling the API."""
        return {
            "enabled": self._config.enabled,
            "provider": self.PROVIDER_NAME,
            "configured": self._config.is_configured,
            "model": self._config.model_name,
        }
