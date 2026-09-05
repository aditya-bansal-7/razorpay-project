"""Tests for the AI Collection Strategist and its API endpoint."""

import json
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from app.extensions import db
from app.models.customer import Customer
from app.models.ledger import LedgerEntry
from app.services.merchant_service import MerchantService


@pytest.fixture
def app():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })
    return application


@pytest.fixture
def client(app):
    with app.app_context():
        db.create_all()
        MerchantService.ensure_default_merchant()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture
def test_customer(app):
    with app.app_context():
        customer = Customer(
            merchant_id="merchant-001",
            name="Strategist Test Customer",
            phone="9000000000"
        )
        db.session.add(customer)
        db.session.commit()
        
        # Add an outstanding balance of 10000
        credit = LedgerEntry(
            merchant_id="merchant-001",
            customer_id=customer.id,
            type="credit",
            amount=10000,
            description="Initial balance",
            transaction_date=None,
            due_date=None
        )
        db.session.add(credit)
        db.session.commit()
        
        return customer.id


def mock_generate_content(mock_client, response_text):
    """Helper to setup the mock Gemini client to return specific text."""
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_client.models.generate_content.return_value = mock_response


class TestAICollectionStrategist:

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_successful_ai_recommendation(self, mock_provider_cls, client, test_customer, monkeypatch):
        """A valid JSON response within rules is accepted."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "true")
        
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        # Provide valid JSON output conforming to rules
        mock_instance.generate.return_value = json.dumps({
            "recommendedAction": "OFFER_PARTIAL",
            "confidence": 0.85,
            "recommendedAmount": 2500,
            "reason": "Customer is likely to pay a partial amount.",
            "recommendedChannel": "whatsapp",
            "riskFlags": [],
            "alternativeAction": "WAIT"
        })
        mock_provider_cls.return_value = mock_instance

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "ai"
        assert data["decision"]["action"] == "OFFER_PARTIAL"
        assert data["decision"]["confidence"] == 0.85
        assert data["decision"]["recommendedAmount"] == 2500.0
        assert data["validation"]["valid"] is True
        # Expected recovery should be mapped from deterministic engine
        assert data["decision"]["expectedRecovery"] > 0

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_fallback_on_invalid_action(self, mock_provider_cls, client, test_customer, monkeypatch):
        """Invalid action forces deterministic fallback."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.generate.return_value = json.dumps({
            "recommendedAction": "SEND_POLICE",  # Not supported
            "confidence": 0.9,
            "recommendedAmount": 10000,
            "reason": "Test"
        })
        mock_provider_cls.return_value = mock_instance

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert data["validation"]["valid"] is True  # The fallback itself is valid
        assert any("Invalid action" in adj for adj in data["validation"]["adjustments"])
        # Action is chosen by deterministic rules (likely SEND_REMINDER or OFFER_PARTIAL)
        assert data["decision"]["action"] in ("SEND_REMINDER", "OFFER_PARTIAL", "WAIT")

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_fallback_amount_exceeds_outstanding(self, mock_provider_cls, client, test_customer, monkeypatch):
        """AI cannot recommend an amount higher than the outstanding balance."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.generate.return_value = json.dumps({
            "recommendedAction": "OFFER_PARTIAL",
            "confidence": 0.8,
            "recommendedAmount": 50000,  # Outstanding is only 10000
            "reason": "Test"
        })
        mock_provider_cls.return_value = mock_instance

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert any("exceeds outstanding" in adj for adj in data["validation"]["adjustments"])

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_fallback_escalate_before_30_days(self, mock_provider_cls, client, test_customer, monkeypatch):
        """ESCALATE is blocked if daysOverdue < 30."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.generate.return_value = json.dumps({
            "recommendedAction": "ESCALATE",
            "confidence": 0.9,
            "recommendedAmount": 10000,
            "reason": "Test"
        })
        mock_provider_cls.return_value = mock_instance

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert any("Cannot ESCALATE" in adj for adj in data["validation"]["adjustments"])

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_fallback_cooldown_enforced(self, mock_provider_cls, client, test_customer, monkeypatch):
        """If a collection action happened within 3 days, WAIT is forced."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        
        # We need to simulate a recent collection action.
        # We'll just mock the metrics extraction temporarily to inject the cooldown condition.
        from app.services.collection_task_service import CollectionTaskService
        original_metrics = CollectionTaskService._metrics
        
        def mocked_metrics(customer):
            m = original_metrics(customer)
            m["daysSinceLastCollectionAction"] = 1  # 1 day ago
            return m
            
        with patch.object(CollectionTaskService, "_metrics", side_effect=mocked_metrics):
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance.generate.return_value = json.dumps({
                "recommendedAction": "SEND_REMINDER",
                "confidence": 0.9,
                "recommendedAmount": 10000,
                "reason": "Test"
            })
            mock_provider_cls.return_value = mock_instance
    
            response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
            
            assert response.status_code == 200
            data = response.get_json()
            assert data["decision"]["source"] == "deterministic_fallback"
            assert data["decision"]["action"] == "WAIT"
            assert any("Cooldown enforced" in adj for adj in data["validation"]["adjustments"])

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_fallback_on_malformed_json(self, mock_provider_cls, client, test_customer, monkeypatch):
        """Malformed JSON from provider triggers fallback."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.generate.return_value = "This is not JSON"
        mock_provider_cls.return_value = mock_instance

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert any("Malformed JSON" in adj for adj in data["validation"]["adjustments"])

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_fallback_on_provider_error(self, mock_provider_cls, client, test_customer, monkeypatch):
        """Any AIProviderError triggers fallback."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        from app.ai.exceptions import AITimeoutError
        
        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.generate.side_effect = AITimeoutError("Timeout reached")
        mock_provider_cls.return_value = mock_instance

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert any("Timeout reached" in adj for adj in data["validation"]["adjustments"])

    def test_fallback_when_ai_disabled(self, client, test_customer, monkeypatch):
        """If AI is disabled or key is missing, fallback is seamless."""
        monkeypatch.setenv("AI_ENABLED", "false")

        response = client.post("/api/ai/collection-strategy", json={"customerId": test_customer})
        
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert any("Provider unavailable" in adj for adj in data["validation"]["adjustments"])
        
    def test_missing_customer_id(self, client):
        response = client.post("/api/ai/collection-strategy", json={})
        assert response.status_code == 400

    def test_customer_not_found(self, client):
        response = client.post("/api/ai/collection-strategy", json={"customerId": "not-a-real-id"})
        assert response.status_code == 404

    def test_customer_with_no_balance(self, client, app):
        """Customers with no balance shouldn't trigger an AI call."""
        with app.app_context():
            customer = Customer(merchant_id="merchant-001", name="Zero Balance", phone="1234567890")
            db.session.add(customer)
            db.session.commit()
            cust_id = customer.id
            
        response = client.post("/api/ai/collection-strategy", json={"customerId": cust_id})
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["action"] == "WAIT"
        assert data["decision"]["recommendedAmount"] == 0
        assert data["decision"]["source"] == "deterministic_fallback"
