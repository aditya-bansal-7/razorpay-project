from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import random

from app.extensions import db
from app.models.simulation_run import SimulationRun
from app.services.collection_task_service import CollectionTaskService


class SimulationValidationError(ValueError):
    pass


class SimulationService:
    DEFAULT_COUNT = 500
    MAX_COUNT = 5000
    DEFAULT_AS_OF = date(2026, 9, 5)
    PROFILES = ("reliable", "late_payer", "partial_payer", "responsive", "resistant")

    @staticmethod
    def _money(value):
        return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _profile(rng):
        return rng.choices(SimulationService.PROFILES, weights=(20, 22, 20, 18, 20), k=1)[0]

    @staticmethod
    def _iso(value):
        return value.isoformat()

    @staticmethod
    def generate_dataset(seed, customer_count, as_of):
        rng = random.Random(seed)
        customers = []
        for index in range(customer_count):
            profile = SimulationService._profile(rng)
            customer_id = f"sim-customer-{index + 1:04d}"
            credit_count = rng.randint(1, 4)
            transactions = []
            reminder_events = []
            total_credit = Decimal("0")
            total_payment = Decimal("0")
            latest_due_date = None
            credit_dates = []
            for credit_index in range(credit_count):
                credit_date = as_of - timedelta(days=rng.randint(35, 210))
                credit_dates.append(credit_date)
                due_date = credit_date + timedelta(days=rng.randint(14, 35))
                amount = Decimal(rng.randint(2500, 45000)).quantize(Decimal("0.01"))
                total_credit += amount
                latest_due_date = max(latest_due_date, due_date) if latest_due_date else due_date
                transactions.append({
                    "type": "credit",
                    "amount": SimulationService._money(amount),
                    "date": SimulationService._iso(credit_date),
                    "dueDate": SimulationService._iso(due_date),
                    "description": f"Udhaar order {credit_index + 1}",
                })

            payment_count = {
                "reliable": rng.randint(2, 5),
                "late_payer": rng.randint(1, 3),
                "partial_payer": rng.randint(2, 5),
                "responsive": rng.randint(1, 4),
                "resistant": rng.randint(0, 2),
            }[profile]
            for payment_index in range(payment_count):
                payment_date = min(credit_dates) + timedelta(days=rng.randint(7, max(7, (as_of - min(credit_dates)).days)))
                if profile == "partial_payer":
                    fraction = Decimal(str(rng.choice((0.10, 0.20, 0.25, 0.35))))
                elif profile == "reliable":
                    fraction = Decimal(str(rng.choice((0.35, 0.50, 0.75, 1.00))))
                else:
                    fraction = Decimal(str(rng.choice((0.15, 0.25, 0.50, 0.75))))
                payment_amount = min(total_credit - total_payment, (total_credit * fraction).quantize(Decimal("0.01")))
                if payment_amount <= 0:
                    break
                total_payment += payment_amount
                transactions.append({
                    "type": "payment",
                    "amount": SimulationService._money(payment_amount),
                    "date": SimulationService._iso(payment_date),
                    "description": "Historical payment",
                })

            overdue = latest_due_date < as_of and total_credit > total_payment
            if not overdue:
                latest_due_date = as_of - timedelta(days=rng.randint(1, 75))
            reminder_count = rng.randint(0, 4)
            success_rate = {"reliable": 0.70, "responsive": 0.85, "late_payer": 0.45, "partial_payer": 0.55, "resistant": 0.15}[profile]
            for reminder_index in range(reminder_count):
                reminder_date = as_of - timedelta(days=rng.randint(4, 90))
                reminder_events.append({
                    "type": "reminder_sent",
                    "date": SimulationService._iso(reminder_date),
                    "channel": "whatsapp",
                    "outcome": "paid" if rng.random() < success_rate else "ignored",
                })
            transactions.sort(key=lambda item: item["date"])
            reminder_events.sort(key=lambda item: item["date"])
            timeline = sorted(
                [{**event, "eventType": event["type"]} for event in transactions]
                + [{**event, "eventType": event["type"]} for event in reminder_events],
                key=lambda event: event["date"],
            )
            outstanding = max(Decimal("0"), total_credit - total_payment)
            overdue_days = max(0, (as_of - latest_due_date).days) if overdue and outstanding > 0 else 0
            last_action = reminder_events[-1]["date"] if reminder_events else None
            last_action_days = (as_of - date.fromisoformat(last_action)).days if last_action else None
            payment_events = [event for event in transactions if event["type"] == "payment"]
            partial_rate = sum(Decimal(str(event["amount"])) < total_credit * Decimal("0.5") for event in payment_events) / len(payment_events) if payment_events else Decimal("0")
            customers.append({
                "id": customer_id,
                "name": f"Synthetic Customer {index + 1:04d}",
                "profile": profile,
                "transactions": transactions,
                "collectionEvents": reminder_events,
                "timeline": timeline,
                "outstandingAmount": SimulationService._money(outstanding),
                "daysOverdue": overdue_days,
                "paymentCount": len(payment_events),
                "partialPaymentRate": SimulationService._money(partial_rate),
                "reminderCount": reminder_count,
                "reminderSuccessRate": SimulationService._money(sum(event["outcome"] == "paid" for event in reminder_events) / reminder_count if reminder_count else 0),
                "averagePaymentDelay": {"reliable": 5, "responsive": 8, "partial_payer": 22, "late_payer": 35, "resistant": 60}[profile],
                "daysSinceLastCollectionAction": last_action_days,
                "behaviorProfile": profile,
                "responseDraw": rng.random(),
            })
        return {"asOfDate": as_of.isoformat(), "customers": customers}

    @staticmethod
    def _recommendation(customer):
        selected = CollectionTaskService.evaluate_actions(customer)["selected"]
        return selected["action"], selected["priorityScore"], selected["confidence"], selected["reason"]

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
        features = {"behaviorProfile": profile, "outstandingAmount": 1, "daysOverdue": 0, "reminderSuccessRate": 0, "partialPaymentRate": 0, "paymentCount": 0, "averagePaymentDelay": 0, "daysSinceLastCollectionAction": None}
        return next(item["probability"] for item in CollectionTaskService.evaluate_actions(features)["actions"] if item["action"] == action)

    @staticmethod
    def _evaluate_strategy(dataset, strategy):
        targeted = 0
        amount_targeted = Decimal("0")
        amount_recovered = Decimal("0")
        expected_recovery = Decimal("0")
        action_counts = {}
        customer_results = []
        for customer in dataset["customers"]:
            if customer["daysOverdue"] <= 0 or customer["outstandingAmount"] <= 0:
                continue
            action_evaluation = CollectionTaskService.evaluate_actions(customer)
            if strategy == "baseline":
                action, score, confidence, reason = "SEND_REMINDER", None, None, "Baseline targets every overdue customer with one reminder."
                target_amount = Decimal(str(customer["outstandingAmount"]))
                selected_action = next(item for item in action_evaluation["actions"] if item["action"] == action)
            else:
                selected_action = action_evaluation["selected"]
                action, score, confidence, reason = selected_action["action"], selected_action["priorityScore"], selected_action["confidence"], selected_action["reason"]
                if action == "WAIT":
                    continue
                target_amount = Decimal(str(selected_action["expectedAmount"]))
            targeted += 1
            amount_targeted += target_amount
            expected_recovery += Decimal(str(selected_action["expectedRecovery"]))
            action_counts[action] = action_counts.get(action, 0) + 1
            probability = selected_action["probability"]
            recovered = Decimal("0")
            if customer["responseDraw"] < probability:
                recovery_fraction = Decimal("0.25") if customer["profile"] == "partial_payer" and action != "OFFER_PARTIAL" else Decimal("1")
                recovered = min(target_amount, (target_amount * recovery_fraction).quantize(Decimal("0.01")))
            amount_recovered += recovered
            customer_results.append({
                "customerId": customer["id"],
                "scenarioId": customer["id"],
                "action": action,
                "targetedAmount": SimulationService._money(target_amount),
                "recoveredAmount": SimulationService._money(recovered),
                "expectedRecovery": selected_action["expectedRecovery"],
                "responseDraw": customer["responseDraw"],
                "profile": customer["profile"],
                "priority": SimulationService._priority(score) if score is not None else "baseline",
                "reason": reason,
                "confidence": confidence,
            })
        recovery_rate = amount_recovered / amount_targeted if amount_targeted else Decimal("0")
        return {
            "strategy": strategy,
            "customersTargeted": targeted,
            "collectionActions": targeted,
            "amountTargeted": SimulationService._money(amount_targeted),
            "amountRecovered": SimulationService._money(amount_recovered),
            "expectedRecovery": SimulationService._money(expected_recovery),
            "recoveryRate": SimulationService._money(recovery_rate),
            "recoveryPerAction": SimulationService._money(amount_recovered / targeted if targeted else 0),
            "actionCounts": action_counts,
            "customerResults": customer_results,
        }

    @staticmethod
    def _validate_payload(payload):
        payload = payload if isinstance(payload, dict) else {}
        try:
            count = int(payload.get("customerCount", SimulationService.DEFAULT_COUNT))
            seed = int(payload.get("seed", 42))
            as_of = date.fromisoformat(str(payload.get("asOfDate", SimulationService.DEFAULT_AS_OF.isoformat())))
        except (TypeError, ValueError) as exc:
            raise SimulationValidationError("customerCount, seed, and asOfDate must be valid") from exc
        if count < 1 or count > SimulationService.MAX_COUNT:
            raise SimulationValidationError(f"customerCount must be between 1 and {SimulationService.MAX_COUNT}")
        return seed, count, as_of

    @staticmethod
    def generate(merchant_id, payload):
        seed, count, as_of = SimulationService._validate_payload(payload)
        run = SimulationRun(merchant_id=merchant_id, seed=seed, customer_count=count, status="generated", dataset=SimulationService.generate_dataset(seed, count, as_of))
        db.session.add(run)
        db.session.commit()
        return run

    @staticmethod
    def run(run_id):
        run = db.session.get(SimulationRun, run_id)
        if not run:
            raise LookupError("Simulation run not found")
        baseline = SimulationService._evaluate_strategy(run.dataset, "baseline")
        collection = SimulationService._evaluate_strategy(run.dataset, "collection_rules")
        baseline_recovered = Decimal(str(baseline["amountRecovered"]))
        rules_recovered = Decimal(str(collection["amountRecovered"]))
        uplift_amount = rules_recovered - baseline_recovered
        run.results = {
            "runId": run.id,
            "seed": run.seed,
            "customerCount": run.customer_count,
            "asOfDate": run.dataset["asOfDate"],
            "baseline": baseline,
            "collectionRules": collection,
            "uplift": {
                "amount": SimulationService._money(uplift_amount),
                "rate": SimulationService._money(uplift_amount / baseline_recovered if baseline_recovered else 0),
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
