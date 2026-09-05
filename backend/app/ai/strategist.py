"""AI Collection Strategist layer.

This module provides the AI decision-making layer for the collections system.
It utilizes the AIProvider to generate recommendations based on observable
metrics AND backend-calculated candidate financial evaluations. The backend
is always the source of truth for expected recovery and eligibility.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

from .factory import get_ai_provider
from .exceptions import AIError
from app.services.collection_task_service import CollectionTaskService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompt Versioning
# ---------------------------------------------------------------------------
PROMPT_VERSION = "v2.0.0"

# ---------------------------------------------------------------------------
# System Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """\
You are an AI collection strategist. Your role is to select the most \
appropriate customer-facing collection action using observed payment \
behavior and backend-calculated financial outcomes.

## Available Actions
| Action | Description |
|---|---|
| SEND_REMINDER | Send a payment reminder via the recommended channel. |
| OFFER_PARTIAL | Offer the customer a reduced partial-payment amount. |
| ESCALATE | Escalate the case (formal notice / senior contact). |
| WAIT | Take no action during the cooldown period. |

## Decision Criteria
1. **Prefer financially sensible actions.** Choose the action whose \
backend-calculated expected recovery is highest among eligible candidates, \
unless customer behavior signals strongly suggest another action.
2. **Consider communication fatigue.** If the customer has received many \
reminders with low success, a reminder is unlikely to help.
3. **Avoid unnecessary escalation.** Only recommend ESCALATE when the \
account is severely overdue AND softer actions have low expected recovery.
4. **Respect eligibility.** Never recommend an action marked as \
"eligible": false in the candidate evaluations.
5. **Respect cooldown.** If daysSinceLastCollectionAction <= 3, \
recommend WAIT.
6. **Use backend financial values.** The candidate evaluations contain \
precomputed successProbability and expectedRecovery. Do NOT invent your \
own financial numbers — only select from the candidates.

## Prohibited Behavior
- Never invent facts about the customer.
- Never calculate your own expectedRecovery or successProbability.
- Never exceed the outstanding balance for recommendedAmount.
- Never recommend an ineligible action.
- Never execute financial operations yourself.
- Do not reference information that was not provided.

## Output Schema
Return ONLY a JSON object with these fields:
```json
{
  "recommendedAction": "SEND_REMINDER | OFFER_PARTIAL | ESCALATE | WAIT",
  "confidence": 0.85,
  "recommendedAmount": 10000.00,
  "reason": "Concise explanation based on provided features only.",
  "recommendedChannel": "whatsapp",
  "riskFlags": [],
  "alternativeAction": "WAIT"
}
```

## Example Reasoning
Given a customer with:
- outstandingAmount: 15000, daysOverdue: 45, reminderSuccessRate: 0.10
- SEND_REMINDER eligible, expectedRecovery: 2700
- OFFER_PARTIAL eligible, expectedRecovery: 3500
- ESCALATE eligible, expectedRecovery: 4200

Correct reasoning: "ESCALATE has the highest expected recovery (4200) and \
the account is severely overdue (45 days). Low reminder success rate (0.10) \
makes softer actions unlikely to succeed."

Given a customer with:
- outstandingAmount: 8000, daysOverdue: 12, partialPaymentRate: 0.70
- SEND_REMINDER eligible, expectedRecovery: 2800
- OFFER_PARTIAL eligible, expectedRecovery: 3100
- ESCALATE NOT eligible (daysOverdue < 30)

Correct reasoning: "OFFER_PARTIAL has the best expected recovery (3100) and \
aligns with the customer's strong partial-payment history (0.70). ESCALATE \
is ineligible."
"""


class AICollectionStrategist:
    """Strategist that evaluates a customer and recommends a collection action.

    Architecture
    ------------
    1. Build observable feature payload from customer metrics.
    2. Compute candidate action evaluations via the deterministic engine.
    3. Send features + candidates to the AI provider.
    4. Validate the AI response against strict policy rules.
    5. Map the selected action back to the backend candidate to set
       expectedRecovery (the backend is always the financial source of truth).
    """

    SUPPORTED_ACTIONS = {"SEND_REMINDER", "OFFER_PARTIAL", "ESCALATE", "WAIT"}

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

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    @classmethod
    def recommend_action(cls, customer_id: str, metrics: dict, provider=None) -> dict:
        """Get a collection recommendation for a customer.

        Args:
            customer_id: The identifier for the customer (for logging/audit).
            metrics: The observable customer metrics dictionary generated
                by ``CollectionTaskService._metrics()``.
            provider: Optional ``AIProvider`` override (used by simulator).

        Returns:
            A dictionary containing the validated decision, validation
            details, and audit metadata.
        """
        provider = provider or get_ai_provider()

        # Always compute the deterministic candidate evaluation first
        evaluation = CollectionTaskService.evaluate_actions(metrics)
        candidates = cls._build_candidates(evaluation, metrics)

        # If AI is unavailable, use deterministic fallback
        if not provider:
            logger.info(
                "AI provider not available, using deterministic fallback for %s",
                customer_id,
            )
            return cls._deterministic_fallback(
                evaluation, "Provider unavailable"
            )

        # Build structured prompt payload
        prompt_payload = cls._build_prompt_payload(metrics, candidates)
        prompt = json.dumps(prompt_payload, indent=2)

        try:
            raw_response = provider.generate(
                prompt=prompt,
                system_prompt=SYSTEM_PROMPT,
                response_schema=cls.RESPONSE_SCHEMA,
            )
            # Strip markdown fences some models add
            if raw_response.startswith("```json"):
                raw_response = (
                    raw_response.strip("` \n").removeprefix("json\n")
                )
            elif raw_response.startswith("```"):
                raw_response = raw_response.strip("` \n")

            ai_decision = json.loads(raw_response)
        except AIError as exc:
            logger.warning("AI provider error for %s: %s", customer_id, exc)
            return cls._deterministic_fallback(evaluation, str(exc))
        except json.JSONDecodeError as exc:
            logger.warning(
                "Malformed JSON from AI provider for %s: %s", customer_id, exc
            )
            return cls._deterministic_fallback(evaluation, "Malformed JSON")

        # Validate against policy
        validation = cls._validate_decision(
            ai_decision, metrics, candidates
        )

        if not validation["valid"]:
            logger.info(
                "AI decision rejected for %s: %s",
                customer_id,
                validation["adjustments"],
            )
            return cls._deterministic_fallback(
                evaluation,
                f"Validation failed: {', '.join(validation['adjustments'])}",
            )

        action = validation["finalAction"]
        amount = validation["finalAmount"]
        confidence = float(ai_decision.get("confidence", 0.0))

        # Map expectedRecovery from the backend candidate (never from LLM)
        expected_recovery = cls._backend_expected_recovery(
            candidates, action
        )

        return {
            "source": "ai",
            "action": action,
            "confidence": confidence,
            "recommendedAmount": amount,
            "reason": str(ai_decision.get("reason", "")),
            "expectedRecovery": expected_recovery,
            "alternativeAction": str(
                ai_decision.get("alternativeAction", "")
            ),
            "promptVersion": PROMPT_VERSION,
            "validation": validation,
        }

    # ------------------------------------------------------------------
    # Candidate evaluation builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_candidates(cls, evaluation: dict, metrics: dict) -> list:
        """Transform the raw deterministic evaluation into a compact
        candidate list with eligibility information.

        Each candidate contains only production-safe fields:
        action, eligible, successProbability, expectedAmount,
        expectedRecovery, constraints.
        """
        days_overdue = metrics.get("daysOverdue", 0)
        days_since_action = metrics.get("daysSinceLastCollectionAction")
        cooldown = (
            days_since_action is not None and days_since_action <= 3
        )

        candidates = []
        for act in evaluation["actions"]:
            action_name = act["action"]

            # Determine eligibility
            eligible = True
            constraints = []

            if action_name == "ESCALATE" and days_overdue < 30:
                eligible = False
                constraints.append(
                    f"Requires daysOverdue >= 30 (current: {days_overdue})"
                )

            if cooldown and action_name != "WAIT":
                eligible = False
                constraints.append(
                    f"Cooldown active: daysSinceLastCollectionAction={days_since_action}"
                )

            candidates.append({
                "action": action_name,
                "eligible": eligible,
                "successProbability": act["probability"],
                "expectedAmount": act["expectedAmount"],
                "expectedRecovery": act["expectedRecovery"],
                "constraints": constraints,
            })
        return candidates

    # ------------------------------------------------------------------
    # Prompt payload builder
    # ------------------------------------------------------------------

    @classmethod
    def _build_prompt_payload(cls, metrics: dict, candidates: list) -> dict:
        """Assemble the JSON object sent to the AI provider.

        Only observable customer behaviour and backend-calculated
        candidate evaluations are included.  Hidden simulator
        variables are never present.
        """
        # Pick only the production-observable keys
        customer_behavior = {
            "outstandingAmount": metrics.get("outstandingAmount"),
            "daysOverdue": metrics.get("daysOverdue"),
            "paymentCount": metrics.get("paymentCount"),
            "averagePaymentDelay": metrics.get("averagePaymentDelay"),
            "reminderCount": metrics.get("reminderCount"),
            "reminderSuccessRate": metrics.get("reminderSuccessRate"),
            "partialPaymentRate": metrics.get("partialPaymentRate"),
            "daysSinceLastCollectionAction": metrics.get(
                "daysSinceLastCollectionAction"
            ),
        }

        return {
            "task": "Select the best collection action for this customer.",
            "customerBehavior": customer_behavior,
            "candidateActions": candidates,
        }

    # ------------------------------------------------------------------
    # Policy Validator
    # ------------------------------------------------------------------

    @classmethod
    def _validate_decision(
        cls, decision: dict, metrics: dict, candidates: list
    ) -> dict:
        """Deterministically validate the AI recommendation."""
        adjustments = []
        action = decision.get("recommendedAction")

        # 1. Must be a supported action
        if action not in cls.SUPPORTED_ACTIONS:
            adjustments.append(f"Invalid action: {action}")
            return {"valid": False, "adjustments": adjustments}

        # 2. Must be eligible per backend candidates
        candidate = next(
            (c for c in candidates if c["action"] == action), None
        )
        if candidate and not candidate["eligible"]:
            adjustments.append(
                f"Action {action} is ineligible: "
                + "; ".join(candidate["constraints"])
            )
            return {"valid": False, "adjustments": adjustments}

        # 3. Confidence must be in [0, 1]
        try:
            confidence = float(decision.get("confidence", -1.0))
        except (ValueError, TypeError):
            confidence = -1.0

        if not (0.0 <= confidence <= 1.0):
            adjustments.append(f"Invalid confidence: {confidence}")

        # 4. Amount must be >= 0
        try:
            amount = float(decision.get("recommendedAmount", -1.0))
        except (ValueError, TypeError):
            amount = -1.0

        if amount < 0:
            adjustments.append(f"Invalid amount: {amount}")

        # 5. Amount must not exceed outstanding
        outstanding = float(metrics.get("outstandingAmount", 0.0))
        if amount > outstanding:
            adjustments.append(
                f"Amount {amount} exceeds outstanding {outstanding}"
            )

        # 6. WAIT must have amount == 0
        if action == "WAIT" and amount > 0:
            adjustments.append("Action WAIT must have recommendedAmount = 0")

        # 7. ESCALATE must have daysOverdue >= 30
        days_overdue = metrics.get("daysOverdue", 0)
        if action == "ESCALATE" and days_overdue < 30:
            adjustments.append(
                f"Cannot ESCALATE: days overdue {days_overdue} < 30"
            )

        # 8. Cooldown check
        days_since_action = metrics.get("daysSinceLastCollectionAction")
        if (
            days_since_action is not None
            and days_since_action <= 3
            and action != "WAIT"
        ):
            adjustments.append(
                f"Cooldown enforced: days since last action "
                f"{days_since_action} <= 3"
            )

        if adjustments:
            return {"valid": False, "adjustments": adjustments}

        # Round amount
        final_amount = float(
            Decimal(str(amount)).quantize(Decimal("0.01"))
        )

        return {
            "valid": True,
            "finalAction": action,
            "finalAmount": final_amount,
            "adjustments": [],
        }

    # ------------------------------------------------------------------
    # Backend expected recovery lookup
    # ------------------------------------------------------------------

    @classmethod
    def _backend_expected_recovery(
        cls, candidates: list, action: str
    ) -> float:
        """Return the backend-calculated expectedRecovery for *action*."""
        for c in candidates:
            if c["action"] == action:
                return c["expectedRecovery"]
        return 0.0

    # ------------------------------------------------------------------
    # Deterministic fallback
    # ------------------------------------------------------------------

    @classmethod
    def _deterministic_fallback(
        cls, evaluation: dict, reason: str
    ) -> dict:
        """Create a decision based purely on the deterministic strategy.

        ``evaluation`` is the result of
        ``CollectionTaskService.evaluate_actions(metrics)``.
        """
        selected = evaluation["selected"]

        return {
            "source": "deterministic_fallback",
            "action": selected["action"],
            "confidence": selected["confidence"],
            "recommendedAmount": selected["expectedAmount"],
            "reason": selected["reason"],
            "expectedRecovery": selected["expectedRecovery"],
            "alternativeAction": "",
            "promptVersion": PROMPT_VERSION,
            "validation": {
                "valid": True,
                "adjustments": [f"Fallback triggered: {reason}"],
            },
        }
