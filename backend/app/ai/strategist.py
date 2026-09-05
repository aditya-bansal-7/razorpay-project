"""AI Collection Strategist layer.

This module provides the AI decision-making layer for the collections system.
It utilizes the AIProvider to generate recommendations based on observable
metrics, validates the response against strict policies, and leverages the
existing deterministic engine for fallback and expected-recovery calculations.
"""

import json
import logging
from decimal import Decimal

from .factory import get_ai_provider
from .exceptions import AIError
from app.services.collection_task_service import CollectionTaskService

logger = logging.getLogger(__name__)


class AICollectionStrategist:
    """Strategist that evaluates a customer and recommends a collection action."""

    SUPPORTED_ACTIONS = {"SEND_REMINDER", "OFFER_PARTIAL", "ESCALATE", "WAIT"}

    SYSTEM_PROMPT = (
        "You are an expert financial collection strategist. Your goal is to maximize "
        "realistic debt recovery while avoiding unnecessary contact and respecting "
        "customer payment behavior. "
        "\n\n"
        "Guidelines:\n"
        "- Recommend the best next action: SEND_REMINDER, OFFER_PARTIAL, ESCALATE, or WAIT.\n"
        "- Base your decision entirely on the provided metrics (observable behavior).\n"
        "- Never exceed the outstanding amount for a recommended amount.\n"
        "- Never invent facts about the customer.\n"
        "- Use WAIT if the customer was contacted very recently (e.g., within 3 days).\n"
        "- Return ONLY the requested strict JSON schema."
    )

    RESPONSE_SCHEMA = {
        "type": "object",
        "properties": {
            "recommendedAction": {
                "type": "string",
                "enum": ["SEND_REMINDER", "OFFER_PARTIAL", "ESCALATE", "WAIT"],
            },
            "confidence": {"type": "number"},
            "recommendedAmount": {"type": "number"},
            "reason": {"type": "string"},
            "recommendedChannel": {"type": "string"},
            "riskFlags": {
                "type": "array",
                "items": {"type": "string"},
            },
            "alternativeAction": {"type": "string"},
        },
        "required": [
            "recommendedAction",
            "confidence",
            "recommendedAmount",
            "reason",
        ],
    }

    @classmethod
    def recommend_action(cls, customer_id: str, metrics: dict, provider=None) -> dict:
        """Get a collection recommendation for a customer.

        Args:
            customer_id: The identifier for the customer (for logging/audit).
            metrics: The observable customer metrics dictionary generated
                by CollectionTaskService._metrics().
            provider: Optional AIProvider override (used by simulator).

        Returns:
            A dictionary containing the validated decision and validation details.
        """
        provider = provider or get_ai_provider()
        
        # If AI is unavailable, use deterministic fallback
        if not provider:
            logger.info("AI provider not available, using deterministic fallback for %s", customer_id)
            return cls._deterministic_fallback(metrics, "Provider unavailable")

        # Prepare the prompt payload
        prompt = json.dumps(
            {
                "task": "Recommend best collection action.",
                "customer_metrics": metrics,
            },
            indent=2,
        )

        try:
            raw_response = provider.generate(
                prompt=prompt,
                system_prompt=cls.SYSTEM_PROMPT,
                response_schema=cls.RESPONSE_SCHEMA,
            )
            # Some models might wrap JSON in markdown block even with response_mime_type
            if raw_response.startswith("```json"):
                raw_response = raw_response.strip("` \n").removeprefix("json\n")
            elif raw_response.startswith("```"):
                raw_response = raw_response.strip("` \n")

            ai_decision = json.loads(raw_response)
        except AIError as exc:
            logger.warning("AI provider error for %s: %s", customer_id, exc)
            return cls._deterministic_fallback(metrics, str(exc))
        except json.JSONDecodeError as exc:
            logger.warning("Malformed JSON from AI provider for %s: %s", customer_id, exc)
            return cls._deterministic_fallback(metrics, "Malformed JSON")

        validation = cls._validate_decision(ai_decision, metrics)

        if not validation["valid"]:
            logger.info("AI decision rejected for %s: %s", customer_id, validation["adjustments"])
            return cls._deterministic_fallback(
                metrics, 
                f"Validation failed: {', '.join(validation['adjustments'])}"
            )

        action = validation["finalAction"]
        amount = validation["finalAmount"]
        confidence = float(ai_decision.get("confidence", 0.0))

        # Retrieve expected recovery from the deterministic engine
        expected_recovery = cls._calculate_expected_recovery(metrics, action)

        return {
            "source": "ai",
            "action": action,
            "confidence": confidence,
            "recommendedAmount": amount,
            "reason": str(ai_decision.get("reason", "")),
            "expectedRecovery": expected_recovery,
            "alternativeAction": str(ai_decision.get("alternativeAction", "")),
            "validation": validation,
        }

    @classmethod
    def _validate_decision(cls, decision: dict, metrics: dict) -> dict:
        """Deterministically validate the AI recommendation."""
        adjustments = []
        action = decision.get("recommendedAction")

        if action not in cls.SUPPORTED_ACTIONS:
            adjustments.append(f"Invalid action: {action}")
            return {"valid": False, "adjustments": adjustments}

        try:
            confidence = float(decision.get("confidence", -1.0))
        except (ValueError, TypeError):
            confidence = -1.0

        if not (0.0 <= confidence <= 1.0):
            adjustments.append(f"Invalid confidence: {confidence}")

        try:
            amount = float(decision.get("recommendedAmount", -1.0))
        except (ValueError, TypeError):
            amount = -1.0

        if amount < 0:
            adjustments.append(f"Invalid amount: {amount}")

        outstanding = float(metrics.get("outstandingAmount", 0.0))
        if amount > outstanding:
            adjustments.append(f"Amount {amount} exceeds outstanding {outstanding}")

        if action == "WAIT" and amount > 0:
            adjustments.append("Action WAIT must have recommendedAmount = 0")

        days_overdue = metrics.get("daysOverdue", 0)
        if action == "ESCALATE" and days_overdue < 30:
            adjustments.append(f"Cannot ESCALATE: days overdue {days_overdue} < 30")

        days_since_action = metrics.get("daysSinceLastCollectionAction")
        cooldown_enforced = False
        if days_since_action is not None and days_since_action <= 3:
            if action != "WAIT":
                adjustments.append(f"Cooldown enforced: days since last action {days_since_action} <= 3")
                cooldown_enforced = True

        if adjustments or cooldown_enforced:
            return {"valid": False, "adjustments": adjustments}

        # Format amount to 2 decimal places
        final_amount = float(Decimal(str(amount)).quantize(Decimal("0.01")))

        return {
            "valid": True,
            "finalAction": action,
            "finalAmount": final_amount,
            "adjustments": [],
        }

    @classmethod
    def _calculate_expected_recovery(cls, metrics: dict, action: str) -> float:
        """Obtain the deterministic expected recovery for a specific action."""
        evaluation = CollectionTaskService.evaluate_actions(metrics)
        for act in evaluation["actions"]:
            if act["action"] == action:
                return act["expectedRecovery"]
        return 0.0

    @classmethod
    def _deterministic_fallback(cls, metrics: dict, reason: str) -> dict:
        """Create a decision based purely on the deterministic strategy."""
        evaluation = CollectionTaskService.evaluate_actions(metrics)
        selected = evaluation["selected"]
        
        return {
            "source": "deterministic_fallback",
            "action": selected["action"],
            "confidence": selected["confidence"],
            "recommendedAmount": selected["expectedAmount"],
            "reason": selected["reason"],
            "expectedRecovery": selected["expectedRecovery"],
            "alternativeAction": "",
            "validation": {
                "valid": True,
                "adjustments": [f"Fallback triggered: {reason}"]
            },
        }
