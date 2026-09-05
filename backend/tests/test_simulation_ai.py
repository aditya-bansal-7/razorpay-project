"""Tests for AI integration into the Simulation system."""

import json
from unittest.mock import patch, MagicMock

import pytest

from app import create_app
from app.extensions import db
from app.services.merchant_service import MerchantService
from app.services.simulation_service import SimulationService
from app.ai.providers.simulation import SimulationAIProvider
from app.ai.config import AIConfig


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


def test_simulation_ai_provider_is_deterministic():
    """Verify that the SimulationAIProvider makes logical decisions without API calls."""
    provider = SimulationAIProvider(AIConfig(api_key="test", model_name="test", timeout=1, enabled=True))
    
    # Test Cooldown (Wait)
    prompt_cooldown = json.dumps({"customer_metrics": {"daysSinceLastCollectionAction": 1, "daysOverdue": 10}})
    resp = json.loads(provider.generate(prompt_cooldown))
    assert resp["recommendedAction"] == "WAIT"
    
    # Test Escalation
    prompt_escalate = json.dumps({"customer_metrics": {"daysOverdue": 50, "outstandingAmount": 1000}})
    resp = json.loads(provider.generate(prompt_escalate))
    assert resp["recommendedAction"] == "ESCALATE"
    
    # Test Partial Offer
    prompt_partial = json.dumps({"customer_metrics": {"partialPaymentRate": 0.8, "outstandingAmount": 1000}})
    resp = json.loads(provider.generate(prompt_partial))
    assert resp["recommendedAction"] == "OFFER_PARTIAL"
    assert resp["recommendedAmount"] == 250.0  # 25%

    # Default Reminder
    prompt_reminder = json.dumps({"customer_metrics": {"daysOverdue": 10, "outstandingAmount": 1000}})
    resp = json.loads(provider.generate(prompt_reminder))
    assert resp["recommendedAction"] == "SEND_REMINDER"


def test_ai_strategy_strips_simulator_secrets(app):
    """Ensure the AI is evaluated on identical customers but NEVER sees latent variables."""
    with app.app_context():
        import datetime
        dataset = SimulationService.generate_dataset(42, 5, datetime.date(2026, 9, 5))
        
        # Verify the dataset HAS the secrets
        assert "profile" in dataset["customers"][0]
        assert "responseDraw" in dataset["customers"][0]
        
        # We will patch recommend_action to just assert on what it receives
        from app.ai.strategist import AICollectionStrategist
        original_recommend = AICollectionStrategist.recommend_action
        
        called = False
        def mock_recommend(customer_id, metrics, provider=None):
            nonlocal called
            called = True
            # ASSERT SECRETS ARE STRIPPED
            assert "profile" not in metrics
            assert "responseDraw" not in metrics
            assert "scenarioId" not in metrics
            assert "behaviorProfile" not in metrics
            
            # Delegate back to the real method so evaluation continues
            return original_recommend(customer_id, metrics, provider)
            
        with patch.object(AICollectionStrategist, "recommend_action", side_effect=mock_recommend):
            SimulationService._evaluate_strategy(dataset, "ai")
            
        assert called


def test_evaluate_seeds_with_all_strategies(app):
    """Test the full evaluation loop over baseline, rules, and AI."""
    with app.app_context():
        # Evaluate a small set to ensure it doesn't crash and computes metrics
        result = SimulationService.evaluate_seeds([1, 2], customer_count=5, strategies=["baseline", "collectionRules", "ai"])
        
        assert "baseline" in result["strategies"]
        assert "collectionRules" in result["strategies"]
        assert "ai" in result["strategies"]
        
        # Verify uplifts are calculated for all combinations
        assert "rules_vs_baseline" in result["uplift"]
        assert "ai_vs_baseline" in result["uplift"]
        assert "ai_vs_rules" in result["uplift"]
        
        # Ensure we ran over the 2 seeds
        assert result["seedCount"] == 2
        assert len(result["perSeed"]) == 2
        
        first_seed = result["perSeed"][0]
        assert "baseline" in first_seed
        assert "collectionRules" in first_seed
        assert "ai" in first_seed


def test_api_simulation_evaluate_all_strategies(client):
    """Test the evaluate endpoint requests all strategies."""
    response = client.post("/api/simulation/evaluate", json={
        "seeds": [42],
        "customerCount": 10,
        "strategies": ["baseline", "collectionRules", "ai"]
    })
    assert response.status_code == 200
    data = response.get_json()["data"]
    
    # Assert strategies are present
    assert "baseline" in data["strategies"]
    assert "collectionRules" in data["strategies"]
    assert "ai" in data["strategies"]
    
    # Ensure uplifting exists for ai vs baseline
    assert "ai_vs_baseline" in data["uplift"]
