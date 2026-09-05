"""AI integration package.

Provides a provider-independent abstraction layer for LLM interactions.

Quick start::

    from app.ai import get_ai_provider, AIProvider

    provider = get_ai_provider()
    if provider is not None:
        response = provider.generate("Hello, world!")
"""

from .base import AIProvider
from .factory import get_ai_provider
from .strategist import AICollectionStrategist

__all__ = [
    "AIProvider",
    "get_ai_provider",
    "AICollectionStrategist",
]
