from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
import copy
import random
import statistics

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
    STRESS_SCENARIOS = (
        {"name": "high_resistant", "seedStart": 101, "seedCount": 5, "resistantShare": 0.80},
        {"name": "low_payment_probability", "seedStart": 201, "seedCount": 5, "resistantShare": 1.0, "responseDraw": 0.99},
        {"name": "weak_reminders", "seedStart": 301, "seedCount": 5, "reminderSuccessRate": 0.05},
        {"name": "high_partial_payment", "seedStart": 401, "seedCount": 5, "partialShare": 0.80, "partialPaymentRate": 0.90},
        {"name": "very_old_overdue", "seedStart": 501, "seedCount": 5, "daysOverdue": 90},
        {"name": "mostly_small_balances", "seedStart": 601, "seedCount": 5, "balanceMultiplier": 0.15},
        {"name": "mostly_large_balances", "seedStart": 701, "seedCount": 5, "balanceMultiplier": 3.0},
        {"name": "mixed_behavior", "seedStart": 801, "seedCount": 5},
    )

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
                expected_recovery_val = selected_action["expectedRecovery"]
                probability = selected_action["probability"]
            elif strategy == "ai":
                from app.ai.config import AIConfig
                from app.ai.providers.simulation import SimulationAIProvider
                from app.ai.strategist import AICollectionStrategist
                
                sim_provider = SimulationAIProvider(AIConfig(
                    api_key="sim-key", model_name="sim-model", timeout=10, enabled=True
                ))
                # Strip hidden variables before passing to AI
                clean_metrics = {
                    k: v for k, v in customer.items() 
                    if k not in ("profile", "responseDraw", "scenarioId", "behaviorProfile", "id", "timeline", "collectionEvents", "transactions")
                }
                decision = AICollectionStrategist.recommend_action(
                    customer_id=customer["id"], metrics=clean_metrics, provider=sim_provider
                )
                action = decision["action"]
                confidence = decision["confidence"]
                reason = decision["reason"]
                target_amount = Decimal(str(decision["recommendedAmount"]))
                expected_recovery_val = decision["expectedRecovery"]
                
                # We need the probability from the deterministic engine to simulate response
                if action == "WAIT":
                    probability = 0
                    score = 0
                else:
                    det_action = next(item for item in action_evaluation["actions"] if item["action"] == action)
                    probability = det_action["probability"]
                    score = det_action["priorityScore"]
                    
                if action == "WAIT":
                    continue
            else:
                selected_action = action_evaluation["selected"]
                action, score, confidence, reason = selected_action["action"], selected_action["priorityScore"], selected_action["confidence"], selected_action["reason"]
                if action == "WAIT":
                    continue
                target_amount = Decimal(str(selected_action["expectedAmount"]))
                expected_recovery_val = selected_action["expectedRecovery"]
                probability = selected_action["probability"]
            targeted += 1
            amount_targeted += target_amount
            expected_recovery += Decimal(str(expected_recovery_val))
            action_counts[action] = action_counts.get(action, 0) + 1
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
                "expectedRecovery": expected_recovery_val,
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
    def _apply_stress_scenario(dataset, config):
        stressed = copy.deepcopy(dataset)
        customers = stressed["customers"]
        resistant_share = config.get("resistantShare")
        partial_share = config.get("partialShare")
        response_draw = config.get("responseDraw")
        for index, customer in enumerate(customers):
            if resistant_share is not None and index < round(len(customers) * resistant_share):
                customer["profile"] = "resistant"
                customer["behaviorProfile"] = "resistant"
            if partial_share is not None and index < round(len(customers) * partial_share):
                customer["profile"] = "partial_payer"
                customer["behaviorProfile"] = "partial_payer"
                customer["partialPaymentRate"] = config.get("partialPaymentRate", 0.90)
                customer["paymentCount"] = max(customer["paymentCount"], 3)
            if config.get("reminderSuccessRate") is not None:
                customer["reminderSuccessRate"] = config["reminderSuccessRate"]
                for event in customer["collectionEvents"]:
                    event["outcome"] = "paid" if config["reminderSuccessRate"] >= 0.5 else "ignored"
            if response_draw is not None:
                customer["responseDraw"] = response_draw
            if config.get("daysOverdue") is not None and customer["outstandingAmount"] > 0:
                customer["daysOverdue"] = config["daysOverdue"]
                customer["daysSinceLastCollectionAction"] = 10
            if config.get("balanceMultiplier") is not None:
                customer["outstandingAmount"] = SimulationService._money(Decimal(str(customer["outstandingAmount"])) * Decimal(str(config["balanceMultiplier"])))
        stressed["stressScenario"] = config["name"]
        return stressed

    @staticmethod
    def evaluate_stress_scenarios(customer_count=DEFAULT_COUNT, as_of=None, scenarios=None, materially_worse_threshold=0.10):
        as_of = as_of or SimulationService.DEFAULT_AS_OF
        scenarios = scenarios or SimulationService.STRESS_SCENARIOS
        results = []
        for config in scenarios:
            seeds = list(range(config["seedStart"], config["seedStart"] + config["seedCount"]))
            stressed_results = []
            for seed in seeds:
                dataset = SimulationService._apply_stress_scenario(SimulationService.generate_dataset(seed, customer_count, as_of), config)
                baseline = SimulationService._evaluate_strategy(dataset, "baseline")
                rules = SimulationService._evaluate_strategy(dataset, "collection_rules")
                baseline_amount = baseline["amountRecovered"]
                rules_amount = rules["amountRecovered"]
                uplift_amount = SimulationService._money(Decimal(str(rules_amount)) - Decimal(str(baseline_amount)))
                stressed_results.append({
                    "seed": seed,
                    "baseline": {key: baseline[key] for key in ("customersTargeted", "collectionActions", "amountRecovered", "recoveryRate", "recoveryPerAction", "expectedRecovery")},
                    "collectionRules": {key: rules[key] for key in ("customersTargeted", "collectionActions", "amountRecovered", "recoveryRate", "recoveryPerAction", "expectedRecovery")},
                    "uplift": {
                        "amount": uplift_amount,
                        "percentage": SimulationService._money(uplift_amount / baseline_amount if baseline_amount else 0),
                    },
                })
            metrics = ("amountRecovered", "recoveryRate", "recoveryPerAction", "customersTargeted", "expectedRecovery")
            summary = {strategy: {metric: SimulationService._summary([item[strategy][metric] for item in stressed_results]) for metric in metrics} for strategy in ("baseline", "collectionRules")}
            uplift = {metric: SimulationService._summary([item["uplift"][metric] for item in stressed_results]) for metric in ("amount", "percentage")}
            worse = [item["seed"] for item in stressed_results if item["baseline"]["amountRecovered"] > 0 and item["collectionRules"]["amountRecovered"] < item["baseline"]["amountRecovered"] * (1 - materially_worse_threshold)]
            results.append({"name": config["name"], "config": config, "seedCount": len(seeds), "summary": summary, "uplift": uplift, "materiallyWorseSeeds": worse, "perSeed": stressed_results})
        return {
            "customerCount": customer_count,
            "asOfDate": as_of.isoformat(),
            "materiallyWorseThreshold": materially_worse_threshold,
            "scenarios": results,
            "scenarioCount": len(results),
            "worstCaseUplift": min((scenario["uplift"]["amount"]["min"] for scenario in results), default=0),
            "bestCaseUplift": max((scenario["uplift"]["amount"]["max"] for scenario in results), default=0),
            "scenariosWhereRulesLose": sum(bool(scenario["materiallyWorseSeeds"]) for scenario in results),
        }

    @staticmethod
    def _summary(values):
        if not values:
            return {"mean": 0, "median": 0, "min": 0, "max": 0, "standardDeviation": 0}
        return {
            "mean": SimulationService._money(statistics.mean(values)),
            "median": SimulationService._money(statistics.median(values)),
            "min": SimulationService._money(min(values)),
            "max": SimulationService._money(max(values)),
            "standardDeviation": SimulationService._money(statistics.pstdev(values)),
        }

    @staticmethod
    def evaluate_seeds(seeds, customer_count=DEFAULT_COUNT, as_of=None, materially_worse_threshold=0.10, strategies=None):
        if not seeds:
            raise SimulationValidationError("At least one seed is required")
        if customer_count < 1 or customer_count > SimulationService.MAX_COUNT:
            raise SimulationValidationError(f"customerCount must be between 1 and {SimulationService.MAX_COUNT}")
        if materially_worse_threshold < 0 or materially_worse_threshold > 1:
            raise SimulationValidationError("materiallyWorseThreshold must be between 0 and 1")
        strategies = strategies or ["baseline", "collectionRules", "ai"]
        as_of = as_of or SimulationService.DEFAULT_AS_OF
        per_seed = []
        for seed in seeds:
            dataset = SimulationService.generate_dataset(int(seed), customer_count, as_of)
            seed_result = {
                "seed": int(seed),
                "customerCount": customer_count,
            }
            if "baseline" in strategies:
                baseline = SimulationService._evaluate_strategy(dataset, "baseline")
                seed_result["baseline"] = {key: baseline[key] for key in ("customersTargeted", "collectionActions", "amountTargeted", "amountRecovered", "expectedRecovery", "recoveryRate", "recoveryPerAction", "actionCounts")}
            if "collectionRules" in strategies:
                rules = SimulationService._evaluate_strategy(dataset, "collection_rules")
                seed_result["collectionRules"] = {key: rules[key] for key in ("customersTargeted", "collectionActions", "amountTargeted", "amountRecovered", "recoveryRate", "recoveryPerAction", "actionCounts", "expectedRecovery")}
            if "ai" in strategies:
                ai_strat = SimulationService._evaluate_strategy(dataset, "ai")
                seed_result["ai"] = {key: ai_strat[key] for key in ("customersTargeted", "collectionActions", "amountTargeted", "amountRecovered", "recoveryRate", "recoveryPerAction", "actionCounts", "expectedRecovery")}
            
            uplift_info = {}
            if "baseline" in strategies and "collectionRules" in strategies:
                baseline_amount = baseline["amountRecovered"]
                rules_amount = rules["amountRecovered"]
                uplift_amount = SimulationService._money(Decimal(str(rules_amount)) - Decimal(str(baseline_amount)))
                uplift_rate = SimulationService._money(uplift_amount / baseline_amount if baseline_amount else 0)
                uplift_info["rules_vs_baseline"] = {"amount": uplift_amount, "rate": uplift_rate, "recoveryRateDelta": SimulationService._money(Decimal(str(rules["recoveryRate"])) - Decimal(str(baseline["recoveryRate"])))}
            
            if "baseline" in strategies and "ai" in strategies:
                baseline_amount = baseline["amountRecovered"]
                ai_amount = ai_strat["amountRecovered"]
                uplift_amount = SimulationService._money(Decimal(str(ai_amount)) - Decimal(str(baseline_amount)))
                uplift_rate = SimulationService._money(uplift_amount / baseline_amount if baseline_amount else 0)
                uplift_info["ai_vs_baseline"] = {"amount": uplift_amount, "rate": uplift_rate, "recoveryRateDelta": SimulationService._money(Decimal(str(ai_strat["recoveryRate"])) - Decimal(str(baseline["recoveryRate"])))}
                
            if "collectionRules" in strategies and "ai" in strategies:
                rules_amount = rules["amountRecovered"]
                ai_amount = ai_strat["amountRecovered"]
                uplift_amount = SimulationService._money(Decimal(str(ai_amount)) - Decimal(str(rules_amount)))
                uplift_rate = SimulationService._money(uplift_amount / rules_amount if rules_amount else 0)
                uplift_info["ai_vs_rules"] = {"amount": uplift_amount, "rate": uplift_rate, "recoveryRateDelta": SimulationService._money(Decimal(str(ai_strat["recoveryRate"])) - Decimal(str(rules["recoveryRate"])))}
                
            seed_result["uplift"] = uplift_info
            per_seed.append(seed_result)

        metric_names = ("amountRecovered", "recoveryRate", "recoveryPerAction", "customersTargeted", "expectedRecovery")
        strategy_stats = {}
        for strategy in strategies:
            strategy_stats[strategy] = {metric: SimulationService._summary([result[strategy][metric] for result in per_seed]) for metric in metric_names}
        
        uplift_stats = {}
        if "baseline" in strategies and "collectionRules" in strategies:
            uplift_stats["rules_vs_baseline"] = {metric: SimulationService._summary([result["uplift"]["rules_vs_baseline"][metric] for result in per_seed]) for metric in ("amount", "rate", "recoveryRateDelta")}
        if "baseline" in strategies and "ai" in strategies:
            uplift_stats["ai_vs_baseline"] = {metric: SimulationService._summary([result["uplift"]["ai_vs_baseline"][metric] for result in per_seed]) for metric in ("amount", "rate", "recoveryRateDelta")}
        if "collectionRules" in strategies and "ai" in strategies:
            uplift_stats["ai_vs_rules"] = {metric: SimulationService._summary([result["uplift"]["ai_vs_rules"][metric] for result in per_seed]) for metric in ("amount", "rate", "recoveryRateDelta")}

        materially_worse = []
        for result in per_seed:
            baseline_amt = result.get("baseline", {}).get("amountRecovered", 0)
            rules_amt = result.get("collectionRules", {}).get("amountRecovered", 0)
            ai_amt = result.get("ai", {}).get("amountRecovered", 0)
            
            flag = False
            if "baseline" in strategies and "collectionRules" in strategies:
                if baseline_amt > 0 and rules_amt < baseline_amt * (1 - materially_worse_threshold):
                    flag = True
            if "baseline" in strategies and "ai" in strategies:
                if baseline_amt > 0 and ai_amt < baseline_amt * (1 - materially_worse_threshold):
                    flag = True
            if "collectionRules" in strategies and "ai" in strategies:
                if rules_amt > 0 and ai_amt < rules_amt * (1 - materially_worse_threshold):
                    flag = True
            
            if flag:
                materially_worse.append(result["seed"])

        return {
            "seedCount": len(per_seed),
            "seeds": [result["seed"] for result in per_seed],
            "customerCount": customer_count,
            "asOfDate": as_of.isoformat(),
            "materiallyWorseThreshold": materially_worse_threshold,
            "strategies": strategy_stats,
            "uplift": uplift_stats,
            "materiallyWorseSeeds": materially_worse,
            "perSeed": per_seed,
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
