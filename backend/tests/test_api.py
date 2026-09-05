import pytest

from app import create_app
from app.extensions import db
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


def test_collection_queue_rules_and_task_lifecycle(client):
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
    assert approve_response.get_json()["data"]["status"] == "approved"

    reject_response = client.post(f"/api/collections/{task['id']}/reject")
    assert reject_response.status_code == 200
    assert reject_response.get_json()["data"]["status"] == "rejected"
