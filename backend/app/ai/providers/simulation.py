"""Deterministic Simulation AI Provider.

This provider implements the AIProvider interface but never calls
an external LLM. It parses the provided prompt (which contains the JSON metrics)
and uses simple, fast deterministic heuristics to generate a JSON response
that perfectly conforms to the expected AI schema.

This is ONLY used during bulk simulation to avoid flooding the real API
while still evaluating the AI architecture path.
"""

import json

from app.ai.base import AIProvider
from app.ai.exceptions import AIInvalidResponseError


class SimulationAIProvider(AIProvider):
    """A deterministic AI provider for simulation benchmarking."""

    PROVIDER_NAME = "simulation_deterministic"

    def __init__(self, config=None):
        self._config = config

    def generate(
        self,
        prompt: str,
        *,
        system_prompt: str | None = None,
        response_schema: dict | None = None,
    ) -> str:
        """Parse metrics from prompt and deterministically generate an action."""
        try:
            payload = json.loads(prompt)
            metrics = payload.get("customer_metrics", {})
        except json.JSONDecodeError:
            raise AIInvalidResponseError("Simulated provider failed to parse prompt JSON")

        days_overdue = metrics.get("daysOverdue", 0)
        outstanding = metrics.get("outstandingAmount", 0)
        days_since_action = metrics.get("daysSinceLastCollectionAction")
        partial_rate = metrics.get("partialPaymentRate", 0)

        # 1. Enforce Cooldown
        if days_since_action is not None and days_since_action <= 3:
            return self._build_response("WAIT", 0, 0.99, "Enforcing 3-day cooldown.")

        # 2. Enforce Escalation Rule
        if days_overdue >= 45:
            # High overdue + valid for escalation
            return self._build_response("ESCALATE", outstanding, 0.95, "Severely overdue account requires escalation.")

        # 3. Assess Partial Payment Behavior
        if partial_rate >= 0.5:
            amount = max(1, round(outstanding * 0.25, 2))
            return self._build_response("OFFER_PARTIAL", amount, 0.88, "Customer has a history of partial payments.")

        # 4. Default to Reminder
        return self._build_response("SEND_REMINDER", outstanding, 0.85, "Standard reminder is the best next step.")

    def _build_response(self, action: str, amount: float, confidence: float, reason: str) -> str:
        """Format the output exactly matching the expected JSON schema."""
        decision = {
            "recommendedAction": action,
            "confidence": confidence,
            "recommendedAmount": amount,
            "reason": reason,
            "recommendedChannel": "whatsapp",
            "riskFlags": [],
            "alternativeAction": "WAIT" if action != "WAIT" else "SEND_REMINDER",
        }
        return json.dumps(decision)

    def is_available(self) -> bool:
        return True

    def health(self) -> dict:
        return {
            "enabled": True,
            "provider": self.PROVIDER_NAME,
            "configured": True,
            "model": "deterministic_simulator",
        }
