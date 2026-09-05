import hashlib
import hmac
import json
from decimal import Decimal

import pytest

from app import create_app
from app.extensions import db
from app.models.collection_task import CollectionTask
from app.services.collection_task_service import CollectionTaskService
from app.services.simulation_service import SimulationService
from app.services.merchant_service import MerchantService
from app.services.razorpay_service import RazorpayService


@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })

    with app.app_context():
        db.create_all()
        MerchantService.ensure_default_merchant()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_customer_crud_and_balance(client):
    merchant_response = client.get("/api/merchants")
    assert merchant_response.status_code == 200
    merchants = merchant_response.get_json()["data"]
    assert any(merchant["id"] == "merchant-001" for merchant in merchants)

    response = client.post(
        "/api/customers",
        json={"name": "Ramesh General Store", "phone": "9876543210", "email": "ramesh@example.com"},
    )
    assert response.status_code == 201
    customer = response.get_json()["data"]
    assert customer["name"] == "Ramesh General Store"
    assert customer["phone"] == "9876543210"

    list_response = client.get("/api/customers")
    assert list_response.status_code == 200
    customers = list_response.get_json()["data"]
    assert len(customers) == 1

    detail_response = client.get(f"/api/customers/{customer['id']}")
    assert detail_response.status_code == 200
    assert detail_response.get_json()["data"]["id"] == customer["id"]

    credit_response = client.post(
        f"/api/customers/{customer['id']}/ledger",
        json={"type": "credit", "amount": 25000, "description": "Wholesale order", "transactionDate": "2026-08-01", "dueDate": "2026-08-15"},
    )
    assert credit_response.status_code == 201

    payment_response = client.post(
        f"/api/customers/{customer['id']}/ledger",
        json={"type": "payment", "amount": 8000, "description": "Partial payment", "transactionDate": "2026-08-10"},
    )
    assert payment_response.status_code == 201

    balance = client.get(f"/api/customers/{customer['id']}/balance")
    assert balance.status_code == 200
    payload = balance.get_json()["data"]
    assert payload["total_credit"] == 25000
    assert payload["total_payment"] == 8000
    assert payload["outstanding_balance"] == 17000
    assert payload["customer_status"] in {"active", "overdue", "settled"}

    ledger_response = client.get(f"/api/customers/{customer['id']}/ledger")
    assert ledger_response.status_code == 200
    assert len(ledger_response.get_json()["data"]) == 2

    update_response = client.put(
        f"/api/customers/{customer['id']}",
        json={"name": "Ramesh Stores", "phone": "9876543211", "email": "ramesh@example.com"},
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["name"] == "Ramesh Stores"

    delete_response = client.delete(f"/api/customers/{customer['id']}")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["success"] is True


def test_overdue_status_and_dashboard_metrics(client):
    customer_response = client.post(
        "/api/customers",
        json={"name": "Anita Traders", "phone": "9812345678"},
    )
    customer_id = customer_response.get_json()["data"]["id"]

    credit = client.post(
        f"/api/customers/{customer_id}/ledger",
        json={"type": "credit", "amount": 10000, "description": "Monthly stock", "transactionDate": "2024-01-01", "dueDate": "2024-01-15"},
    )
    assert credit.status_code == 201

    status_response = client.get(f"/api/customers/{customer_id}/balance")
    assert status_response.status_code == 200
    assert status_response.get_json()["data"]["customer_status"] == "overdue"

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    payload = dashboard.get_json()["data"]
    assert payload["totalCustomers"] >= 1
    assert payload["totalOutstandingBalance"] >= 10000
    assert payload["overdueAmount"] >= 10000


def test_payment_and_collection_recording(client, monkeypatch):
    razorpay_payload = {}

    class FakePaymentLinks:
        def create(self, payload):
            razorpay_payload.update(payload)
            return {"id": "plink_test", "short_url": "https://rzp.io/i/test", "expire_by": None}

    class FakeRazorpayClient:
        payment_link = FakePaymentLinks()

    monkeypatch.setattr(
        RazorpayService,
        "_client",
        lambda: FakeRazorpayClient(),
    )
    customer_response = client.post(
        "/api/customers",
        json={"name": "Patel Electricals", "phone": "9988776655"},
    )
    customer_id = customer_response.get_json()["data"]["id"]

    client.post(
        f"/api/customers/{customer_id}/ledger",
        json={"type": "credit", "amount": 10000, "description": "Repair contract", "transactionDate": "2026-09-01", "dueDate": "2026-09-15"},
    )

    ledger_response = client.get(f"/api/customers/{customer_id}/ledger")
    assert ledger_response.status_code == 200
    ledger_entry = ledger_response.get_json()["data"][0]
    assert ledger_entry["transactionDate"] is not None
    assert ledger_entry["dueDate"] == "2026-09-15T00:00:00"

    payment_response = client.post(
        "/api/payments",
        json={"customerId": customer_id, "amount": 5000, "currency": "INR", "status": "completed", "provider": "internal", "paidAt": "2026-09-07T12:30:00"},
    )
    assert payment_response.status_code == 201
    assert payment_response.get_json()["data"]["paidAt"] == "2026-09-07T12:30:00"

    link_response = client.post(
        "/api/payment-links",
        json={"customerId": customer_id, "amount": 2500, "currency": "INR", "provider": "internal", "status": "draft"},
    )
    assert link_response.status_code == 201
    assert razorpay_payload["amount"] == 250000
    assert link_response.get_json()["data"]["provider"] == "razorpay"
    assert link_response.get_json()["data"]["status"] == "issued"

    event_response = client.post(
        "/api/collection-events",
        json={"customerId": customer_id, "eventType": "reminder_generated", "channel": "whatsapp", "status": "scheduled"},
    )
    assert event_response.status_code == 201

    assert client.get("/api/payments").status_code == 200
    assert client.get("/api/payment-links").status_code == 200
    assert client.get("/api/collection-events").status_code == 200


def test_collection_queue_rules_and_task_lifecycle(client, monkeypatch):
    provider_args = {}

    def fake_create_payment_link(**kwargs):
        provider_args.update(kwargs)
        return {"id": "plink_task", "short_url": "https://rzp.io/i/task", "expire_by": None}

    monkeypatch.setattr(
        RazorpayService,
        "create_payment_link",
        fake_create_payment_link,
    )
    customer_response = client.post(
        "/api/customers",
        json={"name": "Overdue Wholesale", "phone": "9000012345"},
    )
    customer_id = customer_response.get_json()["data"]["id"]
    credit_response = client.post(
        f"/api/customers/{customer_id}/ledger",
        json={
            "type": "credit",
            "amount": 12000,
            "description": "Overdue stock order",
            "dueDate": "2024-01-01",
        },
    )
    assert credit_response.status_code == 201

    queue_response = client.get("/api/collections/queue")
    assert queue_response.status_code == 200
    tasks = queue_response.get_json()["data"]
    assert len(tasks) == 1
    task = tasks[0]
    assert task["customerId"] == customer_id
    assert task["action"] == "ESCALATE"
    assert task["priority"] in {"high", "critical"}
    assert task["metrics"]["outstandingAmount"] == 12000

    duplicate_response = client.post(f"/api/collections/evaluate/{customer_id}")
    assert duplicate_response.status_code == 200
    assert duplicate_response.get_json()["data"]["id"] == task["id"]

    approve_response = client.post(f"/api/collections/{task['id']}/approve")
    assert approve_response.status_code == 200
    assert approve_response.get_json()["data"]["status"] == "executed"
    assert approve_response.get_json()["data"]["paymentLinkUrl"] == "https://rzp.io/i/task"
    assert provider_args["reference_id"] == task["id"]
    assert provider_args["notes"]["customer_id"] == customer_id

    reject_response = client.post(f"/api/collections/{task['id']}/reject")
    assert reject_response.status_code == 409

    duplicate_approval = client.post(f"/api/collections/{task['id']}/approve")
    assert duplicate_approval.status_code == 409


def test_collection_task_send_reminder_and_offer_partial(client, monkeypatch):
    calls = []

    def fake_create_payment_link(**kwargs):
        calls.append(kwargs)
        return {"id": f"plink-{len(calls)}", "short_url": f"https://rzp.io/i/{len(calls)}", "expire_by": None}

    monkeypatch.setattr(RazorpayService, "create_payment_link", fake_create_payment_link)

    reminder_customer = client.post("/api/customers", json={"name": "Reminder Customer", "phone": "9000011111"}).get_json()["data"]["id"]
    client.post(f"/api/customers/{reminder_customer}/ledger", json={"type": "credit", "amount": 5000, "dueDate": "2026-09-01"})
    reminder_task = client.get("/api/collections/queue").get_json()["data"][-1]
    assert reminder_task["action"] == "SEND_REMINDER"
    assert client.post(f"/api/collections/{reminder_task['id']}/approve").status_code == 200
    assert calls[-1]["accept_partial"] is False
    assert calls[-1]["amount"] == pytest.approx(5000)

    partial_customer = client.post("/api/customers", json={"name": "Partial Customer", "phone": "9000022222"}).get_json()["data"]["id"]
    client.post(f"/api/customers/{partial_customer}/ledger", json={"type": "credit", "amount": 10000, "dueDate": "2099-01-01"})
    client.post(f"/api/customers/{partial_customer}/ledger", json={"type": "payment", "amount": 1000})
    client.post(f"/api/customers/{partial_customer}/ledger", json={"type": "payment", "amount": 1000})
    partial_tasks = client.get("/api/collections/queue").get_json()["data"]
    partial_task = next(task for task in partial_tasks if task["customerId"] == partial_customer)
    assert partial_task["action"] == "OFFER_PARTIAL"
    assert client.post(f"/api/collections/{partial_task['id']}/approve").status_code == 200
    assert calls[-1]["accept_partial"] is True
    assert calls[-1]["first_min_partial_amount"] == pytest.approx(partial_task["recommendedAmount"])


def test_collection_task_provider_failure_is_persisted(client, monkeypatch):
    customer_id = client.post("/api/customers", json={"name": "Failed Link", "phone": "9000033333"}).get_json()["data"]["id"]
    client.post(f"/api/customers/{customer_id}/ledger", json={"type": "credit", "amount": 3000, "dueDate": "2026-08-01"})
    task = next(task for task in client.get("/api/collections/queue").get_json()["data"] if task["customerId"] == customer_id)
    monkeypatch.setattr(RazorpayService, "create_payment_link", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("provider unavailable")))
    response = client.post(f"/api/collections/{task['id']}/approve")
    assert response.status_code == 502
    assert response.get_json()["error"] == "Razorpay payment link creation failed"
    assert response.get_json()["details"]["status"] == "failed"
    assert "provider unavailable" in response.get_json()["details"]["executionError"]
    with client.application.app_context():
        failed = db.session.get(CollectionTask, task["id"])
        assert failed.status == "failed"
        assert "provider unavailable" in failed.execution_error


def test_collection_task_webhook_partial_and_full_payment(client, monkeypatch):
    secret = "test-webhook-secret"
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", secret)
    customer_id = client.post("/api/customers", json={"name": "Webhook Customer", "phone": "9000044444"}).get_json()["data"]["id"]
    client.post(f"/api/customers/{customer_id}/ledger", json={"type": "credit", "amount": 10000, "dueDate": "2026-08-01"})
    monkeypatch.setattr(RazorpayService, "create_payment_link", lambda **kwargs: {"id": "plink_webhook", "short_url": "https://rzp.io/i/webhook", "expire_by": None})
    task = next(task for task in client.get("/api/collections/queue").get_json()["data"] if task["customerId"] == customer_id)
    assert client.post(f"/api/collections/{task['id']}/approve").status_code == 200

    def post_webhook(payment_id, amount_paid):
        payload = {"event": "payment_link.partially_paid" if amount_paid < 1000000 else "payment_link.paid", "payload": {"payment_link": {"entity": {"id": "plink_webhook", "amount_paid": amount_paid}}, "payment": {"entity": {"id": payment_id}}}}
        body = json.dumps(payload).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        return client.post("/api/webhooks/razorpay", data=body, content_type="application/json", headers={"X-Razorpay-Signature": signature})

    partial = post_webhook("pay_partial", 300000)
    assert partial.status_code == 200
    assert partial.get_json()["data"]["paymentLink"]["status"] == "active"
    assert client.get(f"/api/customers/{customer_id}/balance").get_json()["data"]["outstanding_balance"] == 7000
    full = post_webhook("pay_full", 1000000)
    assert full.status_code == 200
    assert full.get_json()["data"]["paymentLink"]["status"] == "completed"
    assert client.get(f"/api/customers/{customer_id}/balance").get_json()["data"]["outstanding_balance"] == 0


def test_simulation_generate_run_and_reproducibility(client):
    generate = client.post("/api/simulation/generate", json={"seed": 77, "customerCount": 50})
    assert generate.status_code == 201
    generated = generate.get_json()["data"]
    assert generated["customerCount"] == 50
    assert generated["seed"] == 77
    assert generated["status"] == "generated"

    run = client.post("/api/simulation/run", json={"runId": generated["id"]})
    assert run.status_code == 200
    result = run.get_json()["data"]
    assert result["status"] == "completed"
    assert result["results"]["baseline"]["customersTargeted"] >= result["results"]["collectionRules"]["customersTargeted"]
    assert "amountRecovered" in result["results"]["baseline"]
    assert "recoveryPerAction" in result["results"]["collectionRules"]
    assert "uplift" in result["results"]

    stored = client.get(f"/api/simulation/results/{generated['id']}")
    assert stored.status_code == 200
    assert stored.get_json()["data"]["results"] == result["results"]

    second = client.post("/api/simulation/generate", json={"seed": 77, "customerCount": 50})
    second_run = client.post("/api/simulation/run", json={"id": second.get_json()["data"]["id"]})
    first_reproducible = {key: value for key, value in result["results"].items() if key != "runId"}
    second_reproducible = {key: value for key, value in second_run.get_json()["data"]["results"].items() if key != "runId"}
    assert second_reproducible == first_reproducible


def test_simulation_validates_customer_count(client):
    response = client.post("/api/simulation/generate", json={"customerCount": 0})
    assert response.status_code == 400
    assert "customerCount" in response.get_json()["error"]


def test_simulation_strategies_share_scenarios_and_calculate_metrics():
    dataset = SimulationService.generate_dataset(123, 200, SimulationService.DEFAULT_AS_OF)
    baseline = SimulationService._evaluate_strategy(dataset, "baseline")
    rules = SimulationService._evaluate_strategy(dataset, "collection_rules")
    scenarios = {customer["id"]: customer for customer in dataset["customers"]}
    assert all(customer["transactions"] for customer in dataset["customers"])
    assert all("collectionEvents" in customer for customer in dataset["customers"])
    assert all(customer["timeline"] == sorted(customer["timeline"], key=lambda event: event["date"]) for customer in dataset["customers"])
    assert all("responseDraw" in customer for customer in dataset["customers"])

    baseline_by_id = {result["customerId"]: result for result in baseline["customerResults"]}
    rules_by_id = {result["customerId"]: result for result in rules["customerResults"]}
    common_ids = set(baseline_by_id) & set(rules_by_id)
    assert common_ids
    assert all(baseline_by_id[customer_id]["scenarioId"] == customer_id for customer_id in common_ids)
    assert all(baseline_by_id[customer_id]["responseDraw"] == scenarios[customer_id]["responseDraw"] for customer_id in common_ids)
    assert all(rules_by_id[customer_id]["responseDraw"] == scenarios[customer_id]["responseDraw"] for customer_id in common_ids)

    baseline_targeted = sum(Decimal(str(result["targetedAmount"])) for result in baseline["customerResults"])
    baseline_recovered = sum(Decimal(str(result["recoveredAmount"])) for result in baseline["customerResults"])
    rules_targeted = sum(Decimal(str(result["targetedAmount"])) for result in rules["customerResults"])
    rules_recovered = sum(Decimal(str(result["recoveredAmount"])) for result in rules["customerResults"])
    assert baseline["amountTargeted"] == float(baseline_targeted)
    assert baseline["amountRecovered"] == float(baseline_recovered)
    assert rules["amountTargeted"] == float(rules_targeted)
    assert rules["amountRecovered"] == float(rules_recovered)
    assert rules["expectedRecovery"] == float(sum(Decimal(str(result["expectedRecovery"])) for result in rules["customerResults"]))
    assert any(baseline_by_id[customer_id]["recoveredAmount"] != rules_by_id[customer_id]["recoveredAmount"] for customer_id in common_ids)


def test_collection_action_selection_maximizes_expected_recovery_with_cooldown():
    features = {
        "outstandingAmount": 10000,
        "daysOverdue": 12,
        "reminderSuccessRate": 0.2,
        "partialPaymentRate": 0.9,
        "paymentCount": 4,
        "averagePaymentDelay": 20,
        "daysSinceLastCollectionAction": 10,
        "behaviorProfile": "partial_payer",
    }
    evaluation = CollectionTaskService.evaluate_actions(features)
    eligible = [action for action in evaluation["actions"] if action["action"] not in {"WAIT", "ESCALATE"}]
    assert evaluation["selected"]["expectedRecovery"] == max(action["expectedRecovery"] for action in eligible)
    assert evaluation["selected"]["action"] == "OFFER_PARTIAL"

    features["daysSinceLastCollectionAction"] = 2
    assert CollectionTaskService.evaluate_actions(features)["selected"]["action"] == "WAIT"


def test_multi_seed_simulation_evaluation_is_reproducible(client):
    payload = {"startSeed": 10, "seedCount": 20, "customerCount": 500}
    first = client.post("/api/simulation/evaluate", json=payload)
    assert first.status_code == 200
    result = first.get_json()["data"]
    assert result["seedCount"] == 20
    assert result["customerCount"] == 500
    for strategy in ("baseline", "collectionRules"):
        for metric in ("amountRecovered", "recoveryRate", "recoveryPerAction", "customersTargeted"):
            assert set(result["strategies"][strategy][metric]) == {"mean", "median", "min", "max", "standardDeviation"}
    assert set(result["uplift"]) == {"amount", "rate", "recoveryRateDelta"}
    assert len(result["perSeed"]) == 20

    second = client.post("/api/simulation/evaluate", json=payload)
    assert second.status_code == 200
    assert second.get_json()["data"] == result
