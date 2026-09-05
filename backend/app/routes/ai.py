"""AI health-check route.

Provides a lightweight endpoint to verify AI integration status
without making any external API calls.
"""

from flask import Blueprint, jsonify

from ..ai.config import AIConfig
from ..ai.factory import get_ai_provider

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


@ai_bp.route("/health")
def ai_health():
    """Return the current AI integration status.

    Response example::

        {
            "enabled": true,
            "provider": "gemini",
            "configured": true,
            "model": "gemini-2.0-flash"
        }

    This endpoint never calls the Gemini API — it only inspects
    the local configuration state.
    """
    config = AIConfig.from_env()

    if not config.enabled:
        return jsonify({
            "enabled": False,
            "provider": "gemini",
            "configured": False,
            "model": config.model_name,
        })

    provider = get_ai_provider()

    if provider is not None:
        return jsonify(provider.health())

    # Enabled but not configured (missing API key)
    return jsonify({
        "enabled": True,
        "provider": "gemini",
        "configured": False,
        "model": config.model_name,
    })
