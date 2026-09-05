"""Tests for the AI Collection Strategist and its API endpoint.

Verifies:
- Gemini receives candidate financial evaluations alongside customer metrics.
- Gemini does NOT receive hidden simulator fields.
- expectedRecovery always comes from the backend candidate evaluation.
- Gemini cannot override action eligibility.
- Invalid / malformed / timed-out responses → deterministic fallback.
- Confidence, amount, cooldown, and escalation validators remain active.
- promptVersion is included in every response.
"""

import json
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from app.extensions import db
from app.models.customer import Customer
from app.models.ledger import LedgerEntry
from app.services.merchant_service import MerchantService
from app.ai.strategist import AICollectionStrategist, PROMPT_VERSION


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
            phone="9000000000",
        )
        db.session.add(customer)
        db.session.commit()

        credit = LedgerEntry(
            merchant_id="merchant-001",
            customer_id=customer.id,
            type="credit",
            amount=10000,
            description="Initial balance",
            transaction_date=None,
            due_date=None,
        )
        db.session.add(credit)
        db.session.commit()

        return customer.id


# ---------------------------------------------------------------------------
# Helper: capture the exact prompt sent to the mocked provider
# ---------------------------------------------------------------------------

def _make_mock_provider(response_json: dict | str | None = None,
                         side_effect=None):
    """Return a mock AIProvider whose .generate() returns the given JSON."""
    mock = MagicMock()
    mock.is_available.return_value = True
    if side_effect:
        mock.generate.side_effect = side_effect
    else:
        text = response_json if isinstance(response_json, str) else json.dumps(response_json)
        mock.generate.return_value = text
    return mock


class TestPromptPayload:
    """Verify the structure of the prompt sent to the AI provider."""

    def test_gemini_receives_candidate_evaluations(self, app):
        """The prompt must include candidateActions with financial data."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 10000,
                "daysOverdue": 15,
                "paymentCount": 3,
                "averagePaymentDelay": 5,
                "reminderCount": 2,
                "reminderSuccessRate": 0.5,
                "partialPaymentRate": 0.3,
                "daysSinceLastCollectionAction": None,
            }

            captured_prompt = {}

            def capture_generate(prompt, *, system_prompt=None, response_schema=None):
                captured_prompt["payload"] = json.loads(prompt)
                return json.dumps({
                    "recommendedAction": "SEND_REMINDER",
                    "confidence": 0.8,
                    "recommendedAmount": 10000,
                    "reason": "Test",
                })

            mock_provider = MagicMock()
            mock_provider.is_available.return_value = True
            mock_provider.generate.side_effect = capture_generate

            AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock_provider,
            )

            payload = captured_prompt["payload"]

            # Must contain candidateActions
            assert "candidateActions" in payload
            candidates = payload["candidateActions"]
            assert len(candidates) == 4  # SEND_REMINDER, OFFER_PARTIAL, ESCALATE, WAIT

            # Each candidate must have the required fields
            for c in candidates:
                assert "action" in c
                assert "eligible" in c
                assert "successProbability" in c
                assert "expectedAmount" in c
                assert "expectedRecovery" in c
                assert "constraints" in c

    def test_gemini_does_not_receive_hidden_fields(self, app):
        """Ensure profile, responseDraw, scenarioId, behaviorProfile are stripped."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000,
                "daysOverdue": 10,
                "paymentCount": 1,
                "averagePaymentDelay": 3,
                "reminderCount": 1,
                "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1,
                "daysSinceLastCollectionAction": None,
                # These should NEVER appear in the prompt:
                "profile": "resistant",
                "responseDraw": 0.42,
                "scenarioId": "sim-123",
                "behaviorProfile": "resistant",
            }

            captured = {}

            def capture(prompt, *, system_prompt=None, response_schema=None):
                captured["raw"] = prompt
                return json.dumps({
                    "recommendedAction": "SEND_REMINDER",
                    "confidence": 0.7,
                    "recommendedAmount": 5000,
                    "reason": "Test",
                })

            mock = MagicMock()
            mock.is_available.return_value = True
            mock.generate.side_effect = capture

            AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            raw = captured["raw"]
            assert "profile" not in raw.split('"customerBehavior"')[1].split('"candidateActions"')[0]
            assert "responseDraw" not in raw
            assert "scenarioId" not in raw
            assert "behaviorProfile" not in raw

    def test_escalate_marked_ineligible_under_30_days(self, app):
        """ESCALATE candidate must be marked ineligible when daysOverdue < 30."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 8000,
                "daysOverdue": 15,
                "paymentCount": 2,
                "averagePaymentDelay": 5,
                "reminderCount": 1,
                "reminderSuccessRate": 0.5,
                "partialPaymentRate": 0.2,
                "daysSinceLastCollectionAction": None,
            }

            captured = {}

            def capture(prompt, *, system_prompt=None, response_schema=None):
                captured["payload"] = json.loads(prompt)
                return json.dumps({
                    "recommendedAction": "SEND_REMINDER",
                    "confidence": 0.8,
                    "recommendedAmount": 8000,
                    "reason": "Test",
                })

            mock = MagicMock()
            mock.is_available.return_value = True
            mock.generate.side_effect = capture

            AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            escalate = next(
                c for c in captured["payload"]["candidateActions"]
                if c["action"] == "ESCALATE"
            )
            assert escalate["eligible"] is False
            assert any("daysOverdue" in con for con in escalate["constraints"])


class TestExpectedRecovery:
    """Verify expectedRecovery is ALWAYS sourced from the backend."""

    def test_expected_recovery_from_backend_not_llm(self, app):
        """Even if the LLM were to hallucinate a recovery value, the backend
        candidate evaluation must be the source of truth."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 10000,
                "daysOverdue": 20,
                "paymentCount": 2,
                "averagePaymentDelay": 5,
                "reminderCount": 1,
                "reminderSuccessRate": 0.5,
                "partialPaymentRate": 0.2,
                "daysSinceLastCollectionAction": None,
            }

            mock = _make_mock_provider({
                "recommendedAction": "SEND_REMINDER",
                "confidence": 0.85,
                "recommendedAmount": 10000,
                "reason": "Test",
            })

            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            # The backend expectedRecovery for SEND_REMINDER must match
            from app.services.collection_task_service import CollectionTaskService
            evaluation = CollectionTaskService.evaluate_actions(metrics)
            backend_er = next(
                a["expectedRecovery"]
                for a in evaluation["actions"]
                if a["action"] == "SEND_REMINDER"
            )
            assert result["expectedRecovery"] == backend_er
            assert result["source"] == "ai"


class TestPolicyValidation:
    """Verify the deterministic policy validator catches bad LLM output."""

    def test_ineligible_action_triggers_fallback(self, app):
        """If Gemini recommends ESCALATE but it's ineligible, fallback."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 10000,
                "daysOverdue": 10,  # < 30 → ESCALATE ineligible
                "paymentCount": 1,
                "averagePaymentDelay": 5,
                "reminderCount": 1,
                "reminderSuccessRate": 0.5,
                "partialPaymentRate": 0.1,
                "daysSinceLastCollectionAction": None,
            }

            mock = _make_mock_provider({
                "recommendedAction": "ESCALATE",
                "confidence": 0.9,
                "recommendedAmount": 10000,
                "reason": "Escalate please",
            })

            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            assert result["source"] == "deterministic_fallback"
            assert any(
                "ineligible" in adj for adj in result["validation"]["adjustments"]
            )

    def test_invalid_action_triggers_fallback(self, app):
        """A completely unknown action triggers fallback."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000,
                "daysOverdue": 10,
                "paymentCount": 1,
                "averagePaymentDelay": 3,
                "reminderCount": 1,
                "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1,
                "daysSinceLastCollectionAction": None,
            }

            mock = _make_mock_provider({
                "recommendedAction": "CALL_POLICE",
                "confidence": 0.9,
                "recommendedAmount": 5000,
                "reason": "Bad",
            })

            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            assert result["source"] == "deterministic_fallback"
            assert any(
                "Invalid action" in adj
                for adj in result["validation"]["adjustments"]
            )

    def test_invalid_confidence_triggers_fallback(self, app):
        """Confidence outside [0, 1] triggers fallback."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000,
                "daysOverdue": 10,
                "paymentCount": 1,
                "averagePaymentDelay": 3,
                "reminderCount": 1,
                "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1,
                "daysSinceLastCollectionAction": None,
            }

            mock = _make_mock_provider({
                "recommendedAction": "SEND_REMINDER",
                "confidence": 1.5,
                "recommendedAmount": 5000,
                "reason": "Bad",
            })

            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            assert result["source"] == "deterministic_fallback"
            assert any(
                "Invalid confidence" in adj
                for adj in result["validation"]["adjustments"]
            )

    def test_amount_exceeds_outstanding_triggers_fallback(self, app):
        """recommendedAmount > outstandingAmount triggers fallback."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000,
                "daysOverdue": 10,
                "paymentCount": 1,
                "averagePaymentDelay": 3,
                "reminderCount": 1,
                "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1,
                "daysSinceLastCollectionAction": None,
            }

            mock = _make_mock_provider({
                "recommendedAction": "SEND_REMINDER",
                "confidence": 0.8,
                "recommendedAmount": 50000,  # 10x outstanding
                "reason": "Bad",
            })

            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            assert result["source"] == "deterministic_fallback"
            assert any(
                "exceeds outstanding" in adj
                for adj in result["validation"]["adjustments"]
            )

    def test_cooldown_forcing_wait(self, app):
        """daysSinceLastCollectionAction <= 3 forces WAIT."""
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000,
                "daysOverdue": 10,
                "paymentCount": 1,
                "averagePaymentDelay": 3,
                "reminderCount": 1,
                "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1,
                "daysSinceLastCollectionAction": 1,  # Within cooldown
            }

            mock = _make_mock_provider({
                "recommendedAction": "SEND_REMINDER",
                "confidence": 0.9,
                "recommendedAmount": 5000,
                "reason": "Bad",
            })

            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )

            assert result["source"] == "deterministic_fallback"
            assert result["action"] == "WAIT"
            assert any(
                "Cooldown" in adj
                for adj in result["validation"]["adjustments"]
            )


class TestErrorHandling:
    """Verify graceful degradation on provider errors."""

    def test_malformed_json_triggers_fallback(self, app):
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000, "daysOverdue": 10,
                "paymentCount": 1, "averagePaymentDelay": 3,
                "reminderCount": 1, "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1, "daysSinceLastCollectionAction": None,
            }
            mock = _make_mock_provider("This is not JSON at all")
            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )
            assert result["source"] == "deterministic_fallback"
            assert any(
                "Malformed JSON" in adj
                for adj in result["validation"]["adjustments"]
            )

    def test_provider_timeout_triggers_fallback(self, app):
        from app.ai.exceptions import AITimeoutError

        with app.app_context():
            metrics = {
                "outstandingAmount": 5000, "daysOverdue": 10,
                "paymentCount": 1, "averagePaymentDelay": 3,
                "reminderCount": 1, "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1, "daysSinceLastCollectionAction": None,
            }
            mock = _make_mock_provider(side_effect=AITimeoutError("Timeout"))
            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )
            assert result["source"] == "deterministic_fallback"
            assert any(
                "Timeout" in adj
                for adj in result["validation"]["adjustments"]
            )

    def test_provider_unavailable_triggers_fallback(self, app, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("AI_ENABLED", "false")
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000, "daysOverdue": 10,
                "paymentCount": 1, "averagePaymentDelay": 3,
                "reminderCount": 1, "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1, "daysSinceLastCollectionAction": None,
            }
            # provider=None means "use get_ai_provider()" which returns None
            # when AI_ENABLED=false
            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=None,
            )
            assert result["source"] == "deterministic_fallback"
            assert any(
                "Provider unavailable" in adj
                for adj in result["validation"]["adjustments"]
            )


class TestPromptVersion:
    """Verify promptVersion is always returned."""

    def test_prompt_version_on_ai_response(self, app):
        with app.app_context():
            metrics = {
                "outstandingAmount": 10000, "daysOverdue": 20,
                "paymentCount": 2, "averagePaymentDelay": 5,
                "reminderCount": 1, "reminderSuccessRate": 0.5,
                "partialPaymentRate": 0.2, "daysSinceLastCollectionAction": None,
            }
            mock = _make_mock_provider({
                "recommendedAction": "SEND_REMINDER",
                "confidence": 0.8,
                "recommendedAmount": 10000,
                "reason": "Test",
            })
            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=mock,
            )
            assert result["promptVersion"] == PROMPT_VERSION

    def test_prompt_version_on_fallback(self, app, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("AI_ENABLED", "false")
        with app.app_context():
            metrics = {
                "outstandingAmount": 5000, "daysOverdue": 10,
                "paymentCount": 1, "averagePaymentDelay": 3,
                "reminderCount": 1, "reminderSuccessRate": 0.4,
                "partialPaymentRate": 0.1, "daysSinceLastCollectionAction": None,
            }
            result = AICollectionStrategist.recommend_action(
                "test-cust", metrics, provider=None,
            )
            assert result["promptVersion"] == PROMPT_VERSION


class TestEndpoint:
    """Verify the /api/ai/collection-strategy endpoint."""

    @patch("app.ai.providers.gemini.GeminiProvider")
    def test_successful_endpoint(self, mock_cls, client, test_customer, monkeypatch):
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "true")

        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_instance.generate.return_value = json.dumps({
            "recommendedAction": "OFFER_PARTIAL",
            "confidence": 0.85,
            "recommendedAmount": 2500,
            "reason": "Customer is likely to pay a partial amount.",
            "recommendedChannel": "whatsapp",
            "riskFlags": [],
            "alternativeAction": "WAIT",
        })
        mock_cls.return_value = mock_instance

        response = client.post(
            "/api/ai/collection-strategy",
            json={"customerId": test_customer},
        )
        assert response.status_code == 200
        data = response.get_json()

        assert data["decision"]["source"] == "ai"
        assert data["decision"]["action"] == "OFFER_PARTIAL"
        assert data["decision"]["confidence"] == 0.85
        assert data["decision"]["recommendedAmount"] == 2500.0
        assert data["decision"]["expectedRecovery"] > 0
        assert data["validation"]["valid"] is True
        assert data["promptVersion"] == PROMPT_VERSION

    def test_fallback_when_ai_disabled(self, client, test_customer, monkeypatch):
        monkeypatch.setenv("AI_ENABLED", "false")
        response = client.post(
            "/api/ai/collection-strategy",
            json={"customerId": test_customer},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["source"] == "deterministic_fallback"
        assert data["promptVersion"] == PROMPT_VERSION

    def test_missing_customer_id(self, client):
        response = client.post("/api/ai/collection-strategy", json={})
        assert response.status_code == 400

    def test_customer_not_found(self, client):
        response = client.post(
            "/api/ai/collection-strategy",
            json={"customerId": "not-a-real-id"},
        )
        assert response.status_code == 404

    def test_no_razorpay_execution(self, client, test_customer, monkeypatch):
        """The AI endpoint must NEVER create Razorpay payment links."""
        monkeypatch.setenv("AI_ENABLED", "false")

        with patch("app.services.razorpay_service.RazorpayService.create_payment_link") as mock_rp:
            response = client.post(
                "/api/ai/collection-strategy",
                json={"customerId": test_customer},
            )
            assert response.status_code == 200
            mock_rp.assert_not_called()

    def test_customer_with_no_balance(self, client, app):
        with app.app_context():
            customer = Customer(
                merchant_id="merchant-001",
                name="Zero Balance",
                phone="1234567890",
            )
            db.session.add(customer)
            db.session.commit()
            cust_id = customer.id

        response = client.post(
            "/api/ai/collection-strategy",
            json={"customerId": cust_id},
        )
        assert response.status_code == 200
        data = response.get_json()
        assert data["decision"]["action"] == "WAIT"
        assert data["decision"]["recommendedAmount"] == 0
