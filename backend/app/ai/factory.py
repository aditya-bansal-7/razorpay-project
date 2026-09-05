"""AI provider factory.

Entry point for the rest of the application to obtain an AI provider
instance.  Returns ``None`` when AI is disabled or unconfigured so
callers can guard usage cleanly without try/except.
"""

from __future__ import annotations

import logging

from .config import AIConfig
from .base import AIProvider

logger = logging.getLogger(__name__)


def get_ai_provider() -> AIProvider | None:
    """Return a configured AI provider, or ``None`` if unavailable.

    The function reads configuration from environment variables via
    :class:`AIConfig` and returns the appropriate provider.  It never
    raises on missing configuration — callers should check for ``None``.

    Returns:
        A configured :class:`AIProvider` instance, or ``None`` if
        AI is disabled or the API key is missing.
    """
    config = AIConfig.from_env()

    if not config.enabled:
        logger.info("AI integration is disabled (AI_ENABLED != true)")
        return None

    if not config.api_key:
        logger.info(
            "AI integration not configured: GEMINI_API_KEY is not set"
        )
        return None

    from .providers.gemini import GeminiProvider  # noqa: delayed import

    provider = GeminiProvider(config)

    if provider.is_available():
        logger.info(
            "AI provider initialised: %s (model=%s)",
            GeminiProvider.PROVIDER_NAME,
            config.model_name,
        )
    else:
        logger.warning(
            "AI provider failed to initialise — returning None"
        )
        return None

    return provider
