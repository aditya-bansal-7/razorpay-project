import pytest

from app import create_app
from app.extensions import db


@pytest.fixture
def client():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })

    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def test_customer_crud(client):
    response = client.post(
        "/api/customers",
        json={"name": "Ramesh General Store", "phone": "9876543210"},
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

    update_response = client.put(
        f"/api/customers/{customer['id']}",
        json={"name": "Ramesh Stores", "phone": "9876543211", "email": "ramesh@example.com"},
    )
    assert update_response.status_code == 200
    assert update_response.get_json()["data"]["name"] == "Ramesh Stores"

    delete_response = client.delete(f"/api/customers/{customer['id']}")
    assert delete_response.status_code == 200
    assert delete_response.get_json()["success"] is True


def test_ledger_and_balance(client):
    customer_response = client.post(
        "/api/customers",
        json={"name": "Anita Traders", "phone": "9812345678"},
    )
    customer_id = customer_response.get_json()["data"]["id"]

    credit = client.post(
        "/api/customers/{}/ledger".format(customer_id),
        json={"type": "credit", "amount": 25000, "description": "Wholesale order"},
    )
    assert credit.status_code == 201

    payment = client.post(
        "/api/customers/{}/ledger".format(customer_id),
        json={"type": "payment", "amount": 8000, "description": "Partial payment"},
    )
    assert payment.status_code == 201

    balance = client.get(f"/api/customers/{customer_id}/balance")
    assert balance.status_code == 200
    payload = balance.get_json()["data"]
    assert payload["total_credit"] == 25000
    assert payload["total_payment"] == 8000
    assert payload["outstanding_balance"] == 17000

    ledger_response = client.get(f"/api/customers/{customer_id}/ledger")
    assert ledger_response.status_code == 200
    assert len(ledger_response.get_json()["data"]) == 2
