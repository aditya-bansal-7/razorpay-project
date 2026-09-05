"""AI configuration layer.

Reads AI-related settings from environment variables with sensible
defaults.  The application never fails to start when the API key is
missing — it simply reports AI as unconfigured.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AIConfig:
    """Immutable AI configuration container.

    Attributes:
        api_key: Gemini API key (None if not set).
        model_name: Model identifier to use for generation.
        timeout: Request timeout in seconds.
        enabled: Whether AI features are globally enabled.
    """

    api_key: str | None
    model_name: str
    timeout: int
    enabled: bool

    @classmethod
    def from_env(cls) -> "AIConfig":
        """Build configuration from environment variables.

        Environment variables:
            GEMINI_API_KEY   — API key (optional, AI works without it)
            AI_MODEL_NAME    — defaults to 'gemini-2.0-flash'
            AI_TIMEOUT       — defaults to 30 (seconds)
            AI_ENABLED       — defaults to 'true'
        """
        api_key = os.getenv("GEMINI_API_KEY") or None

        model_name = os.getenv("AI_MODEL_NAME", "gemini-2.0-flash")

        try:
            timeout = int(os.getenv("AI_TIMEOUT", "30"))
        except (ValueError, TypeError):
            timeout = 30

        enabled_raw = os.getenv("AI_ENABLED", "true").lower().strip()
        enabled = enabled_raw in ("true", "1", "yes")

        return cls(
            api_key=api_key,
            model_name=model_name,
            timeout=timeout,
            enabled=enabled,
        )

    @property
    def is_configured(self) -> bool:
        """True when AI is enabled AND the API key is present."""
        return self.enabled and self.api_key is not None
