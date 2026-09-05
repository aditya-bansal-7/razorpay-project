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
            "model": "gemini-3.6-flash"
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


@ai_bp.route("/collection-strategy", methods=["POST"])
def collection_strategy():
    """Get an AI collection recommendation for a customer.
    
    Expects JSON: {"customerId": "<id>"}
    """
    from flask import request
    from app.extensions import db
    from app.models.customer import Customer
    from app.services.collection_task_service import CollectionTaskService
    from app.ai.strategist import AICollectionStrategist

    data = request.get_json() or {}
    customer_id = data.get("customerId")
    
    if not customer_id:
        return jsonify({"error": "customerId is required"}), 400
        
    customer = db.session.get(Customer, customer_id)
    if not customer:
        return jsonify({"error": "Customer not found"}), 404
        
    # Extract clean observable metrics (excludes hidden simulation logic)
    metrics = CollectionTaskService._metrics(customer)
    
    # If there is no balance, no action is needed
    if metrics["outstandingAmount"] <= 0:
        return jsonify({
            "customerId": customer_id,
            "decision": {
                "source": "deterministic_fallback",
                "action": "WAIT",
                "confidence": 1.0,
                "recommendedAmount": 0,
                "reason": "Customer has no outstanding balance.",
                "expectedRecovery": 0,
                "alternativeAction": "",
            },
            "validation": {"valid": True, "adjustments": []}
        })
        
    decision = AICollectionStrategist.recommend_action(customer_id, metrics)
    
    return jsonify({
        "customerId": customer_id,
        "decision": {
            "source": decision["source"],
            "action": decision["action"],
            "confidence": decision["confidence"],
            "recommendedAmount": decision["recommendedAmount"],
            "reason": decision["reason"],
            "expectedRecovery": decision["expectedRecovery"],
            "alternativeAction": decision["alternativeAction"],
        },
        "validation": decision["validation"],
        "promptVersion": decision.get("promptVersion", "unknown"),
    })
