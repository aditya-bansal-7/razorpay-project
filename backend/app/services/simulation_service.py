from datetime import date, datetime, timedelta
from decimal import Decimal
import random

from app.extensions import db
from app.models.simulation_run import SimulationRun


class SimulationValidationError(ValueError):
    pass


class SimulationService:
    DEFAULT_COUNT = 500
    MAX_COUNT = 5000
    DEFAULT_AS_OF = date(2026, 9, 5)
    PROFILES = ("reliable", "late_payer", "partial_payer", "responsive", "resistant")

    @staticmethod
    def _money(value):
        return round(float(value), 2)

    @staticmethod
    def _profile(rng):
        return rng.choices(
            SimulationService.PROFILES,
            weights=(20, 22, 20, 18, 20),
            k=1,
        )[0]

    @staticmethod
    def generate_dataset(seed, customer_count, as_of):
        rng = random.Random(seed)
        customers = []
        for index in range(customer_count):
            profile = SimulationService._profile(rng)
            is_overdue = rng.random() < 0.62
            outstanding = Decimal(str(rng.randint(800, 65000))).quantize(Decimal("0.01"))
            overdue_days = rng.randint(1, 75) if is_overdue else 0
            payment_count = rng.randint(0, 5)
            partial_rate = {
                "partial_payer": 0.75,
                "late_payer": 0.35,
                "reliable": 0.15,
                "responsive": 0.2,
                "resistant": 0.1,
            }[profile]
            successful_reminders = rng.randint(0, 4) if profile in {"responsive", "reliable"} else rng.randint(0, 2)
            reminder_count = max(successful_reminders, rng.randint(0, 4))
            last_action_days = rng.randint(0, 20) if reminder_count else None
            customers.append({
                "id": f"sim-customer-{index + 1:04d}",
                "name": f"Synthetic Customer {index + 1:04d}",
                "profile": profile,
                "outstandingAmount": SimulationService._money(outstanding),
                "daysOverdue": overdue_days,
                "paymentCount": payment_count,
                "partialPaymentRate": partial_rate if payment_count else 0,
                "reminderCount": reminder_count,
                "reminderSuccessRate": successful_reminders / reminder_count if reminder_count else 0,
                "averagePaymentDelay": rng.randint(1, 12) if payment_count else 0,
                "daysSinceLastCollectionAction": last_action_days,
            })
        return {"asOfDate": as_of.isoformat(), "customers": customers}

    @staticmethod
    def _recommendation(customer):
        days = customer["daysOverdue"]
        last_action = customer["daysSinceLastCollectionAction"]
        if last_action is not None and last_action <= 3:
            return "WAIT", 15, 0.95, "A collection action happened within the last 3 days; wait for the cooldown period."
        if days >= 30:
            return "ESCALATE", 90 + min(days, 30), 0.94, "The balance has been overdue for 30 days or more."
        if customer["partialPaymentRate"] >= 0.5 and customer["paymentCount"] >= 2:
            return "OFFER_PARTIAL", 70 + min(days, 20), 0.88, "This customer frequently makes partial payments; offer a smaller payment amount."
        if customer["reminderSuccessRate"] >= 0.5 and customer["reminderCount"] > 0:
            return "SEND_REMINDER", 55 + min(days, 20), 0.86, "Previous reminders have resulted in payments."
        if 0 < days <= 14:
            return "SEND_REMINDER", 50 + days, 0.82, "The balance is recently overdue and should receive a timely reminder."
        return "SEND_REMINDER", 30 + min(days, 20), 0.65, "The customer has an outstanding balance and no recent collection outcome."

    @staticmethod
    def _priority(score):
        if score >= 90:
            return "critical"
        if score >= 70:
            return "high"
        if score >= 45:
            return "medium"
        return "low"

    @staticmethod
    def _payment_probability(profile, action):
        base = {
            "reliable": 0.78,
            "late_payer": 0.52,
            "partial_payer": 0.58,
            "responsive": 0.86,
            "resistant": 0.16,
        }[profile]
        if action == "SEND_REMINDER" and profile in {"responsive", "reliable"}:
            return min(0.98, base + 0.08)
        if action == "OFFER_PARTIAL" and profile == "partial_payer":
            return min(0.95, base + 0.15)
        if action == "ESCALATE" and profile == "resistant":
            return max(0.05, base - 0.04)
        return base

    @staticmethod
    def _evaluate_strategy(dataset, strategy, seed):
        targeted = 0
        actions = 0
        amount_targeted = Decimal("0")
        amount_recovered = Decimal("0")
        action_counts = {}
        customer_results = []
        for customer in dataset["customers"]:
            if customer["daysOverdue"] <= 0 or customer["outstandingAmount"] <= 0:
                continue
            if strategy == "baseline":
                action = "SEND_REMINDER"
                score = None
                confidence = None
                reason = "Baseline targets every overdue customer with one reminder."
                target_amount = Decimal(str(customer["outstandingAmount"]))
            else:
                action, score, confidence, reason = SimulationService._recommendation(customer)
                if action == "WAIT":
                    continue
                target_amount = Decimal(str(customer["outstandingAmount"]))
                if action == "OFFER_PARTIAL":
                    target_amount = max(Decimal("1"), (target_amount * Decimal("0.25")).quantize(Decimal("0.01")))
            targeted += 1
            actions += 1
            amount_targeted += target_amount
            action_counts[action] = action_counts.get(action, 0) + 1
            action_rng = random.Random(f"{seed}:{strategy}:{customer['id']}")
            recovered = Decimal("0")
            if action_rng.random() < SimulationService._payment_probability(customer["profile"], action):
                recovery_fraction = Decimal("0.25") if customer["profile"] == "partial_payer" and action != "OFFER_PARTIAL" else Decimal("1")
                recovered = min(target_amount, (target_amount * recovery_fraction).quantize(Decimal("0.01")))
            amount_recovered += recovered
            customer_results.append({
                "customerId": customer["id"],
                "action": action,
                "targetedAmount": SimulationService._money(target_amount),
                "recoveredAmount": SimulationService._money(recovered),
                "profile": customer["profile"],
                "priority": SimulationService._priority(score) if score is not None else "baseline",
                "reason": reason,
                "confidence": confidence,
            })
        recovery_rate = amount_recovered / amount_targeted if amount_targeted else Decimal("0")
        recovery_per_action = amount_recovered / actions if actions else Decimal("0")
        return {
            "strategy": strategy,
            "customersTargeted": targeted,
            "collectionActions": actions,
            "amountTargeted": SimulationService._money(amount_targeted),
            "amountRecovered": SimulationService._money(amount_recovered),
            "recoveryRate": SimulationService._money(recovery_rate),
            "recoveryPerAction": SimulationService._money(recovery_per_action),
            "actionCounts": action_counts,
            "customerResults": customer_results,
        }

    @staticmethod
    def _validate_payload(payload, default_seed=None):
        payload = payload if isinstance(payload, dict) else {}
        try:
            count = int(payload.get("customerCount", SimulationService.DEFAULT_COUNT))
            seed = int(payload.get("seed", default_seed if default_seed is not None else 42))
        except (TypeError, ValueError) as exc:
            raise SimulationValidationError("customerCount and seed must be integers") from exc
        if count < 1 or count > SimulationService.MAX_COUNT:
            raise SimulationValidationError(f"customerCount must be between 1 and {SimulationService.MAX_COUNT}")
        as_of = date.fromisoformat(str(payload.get("asOfDate", SimulationService.DEFAULT_AS_OF.isoformat())))
        return seed, count, as_of

    @staticmethod
    def generate(merchant_id, payload):
        seed, count, as_of = SimulationService._validate_payload(payload)
        run = SimulationRun(
            merchant_id=merchant_id,
            seed=seed,
            customer_count=count,
            status="generated",
            dataset=SimulationService.generate_dataset(seed, count, as_of),
        )
        db.session.add(run)
        db.session.commit()
        return run

    @staticmethod
    def run(run_id):
        run = db.session.get(SimulationRun, run_id)
        if not run:
            raise LookupError("Simulation run not found")
        baseline = SimulationService._evaluate_strategy(run.dataset, "baseline", run.seed)
        collection = SimulationService._evaluate_strategy(run.dataset, "collection_rules", run.seed)
        baseline_recovered = Decimal(str(baseline["amountRecovered"]))
        collection_recovered = Decimal(str(collection["amountRecovered"]))
        uplift_amount = collection_recovered - baseline_recovered
        uplift_rate = uplift_amount / baseline_recovered if baseline_recovered else Decimal("0")
        run.results = {
            "runId": run.id,
            "seed": run.seed,
            "customerCount": run.customer_count,
            "asOfDate": run.dataset["asOfDate"],
            "baseline": baseline,
            "collectionRules": collection,
            "uplift": {
                "amount": SimulationService._money(uplift_amount),
                "rate": SimulationService._money(uplift_rate),
                "recoveryRateDelta": SimulationService._money(Decimal(str(collection["recoveryRate"])) - Decimal(str(baseline["recoveryRate"]))),
            },
        }
        run.status = "completed"
        run.updated_at = datetime.utcnow()
        db.session.commit()
        return run

    @staticmethod
    def get(run_id):
        run = db.session.get(SimulationRun, run_id)
        if not run:
            raise LookupError("Simulation run not found")
        return run
