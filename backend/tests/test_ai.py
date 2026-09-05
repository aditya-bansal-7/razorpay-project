"""Tests for the AI integration layer.

All tests are fully mocked — no real Gemini API calls are made.
Tests cover: configuration, factory, provider initialisation,
generation, error handling, and the health-check endpoint.
"""

import pytest
from unittest.mock import patch, MagicMock

from app import create_app
from app.ai.config import AIConfig
from app.ai.factory import get_ai_provider
from app.ai.exceptions import (
    AIConfigurationError,
    AIError,
    AIInvalidResponseError,
    AIProviderError,
    AIProviderUnavailableError,
    AITimeoutError,
)


# ================================================================
# Fixtures
# ================================================================


@pytest.fixture
def app():
    """Create a test Flask app with AI blueprint registered."""
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })
    return application


@pytest.fixture
def client(app):
    with app.app_context():
        from app.extensions import db
        from app.services.merchant_service import MerchantService

        db.create_all()
        MerchantService.ensure_default_merchant()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


# ================================================================
# AIConfig tests
# ================================================================


class TestAIConfig:
    """Tests for AIConfig.from_env()."""

    def test_config_with_api_key(self, monkeypatch):
        """When GEMINI_API_KEY is set, config should be configured."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "true")

        config = AIConfig.from_env()

        assert config.api_key == "test-key-123"
        assert config.enabled is True
        assert config.is_configured is True
        assert config.model_name == "gemini-2.0-flash"
        assert config.timeout == 30

    def test_config_without_api_key(self, monkeypatch):
        """When GEMINI_API_KEY is not set, config should not be configured."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("AI_ENABLED", "true")

        config = AIConfig.from_env()

        assert config.api_key is None
        assert config.enabled is True
        assert config.is_configured is False

    def test_config_ai_disabled(self, monkeypatch):
        """When AI_ENABLED is false, config should not be configured."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "false")

        config = AIConfig.from_env()

        assert config.api_key == "test-key-123"
        assert config.enabled is False
        assert config.is_configured is False

    def test_config_custom_model_and_timeout(self, monkeypatch):
        """Custom model name and timeout should be respected."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key")
        monkeypatch.setenv("AI_MODEL_NAME", "gemini-2.5-pro")
        monkeypatch.setenv("AI_TIMEOUT", "60")
        monkeypatch.setenv("AI_ENABLED", "true")

        config = AIConfig.from_env()

        assert config.model_name == "gemini-2.5-pro"
        assert config.timeout == 60

    def test_config_invalid_timeout_uses_default(self, monkeypatch):
        """Non-integer timeout should fall back to the default."""
        monkeypatch.setenv("AI_TIMEOUT", "not-a-number")

        config = AIConfig.from_env()

        assert config.timeout == 30

    def test_config_empty_api_key_treated_as_missing(self, monkeypatch):
        """An empty GEMINI_API_KEY string should be treated as missing."""
        monkeypatch.setenv("GEMINI_API_KEY", "")
        monkeypatch.setenv("AI_ENABLED", "true")

        config = AIConfig.from_env()

        assert config.api_key is None
        assert config.is_configured is False


# ================================================================
# Factory tests
# ================================================================


class TestFactory:
    """Tests for get_ai_provider()."""

    @patch("app.ai.providers.gemini.GeminiProvider", create=False)
    def test_factory_returns_provider_when_configured(
        self, mock_gemini_cls, monkeypatch
    ):
        """Factory should return a GeminiProvider when key is present."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "true")

        mock_instance = MagicMock()
        mock_instance.is_available.return_value = True
        mock_gemini_cls.return_value = mock_instance
        mock_gemini_cls.PROVIDER_NAME = "gemini"

        provider = get_ai_provider()

        assert provider is not None
        mock_gemini_cls.assert_called_once()

    def test_factory_returns_none_when_disabled(self, monkeypatch):
        """Factory should return None when AI_ENABLED is false."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "false")

        provider = get_ai_provider()

        assert provider is None

    def test_factory_returns_none_when_key_missing(self, monkeypatch):
        """Factory should return None when GEMINI_API_KEY is not set."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("AI_ENABLED", "true")

        provider = get_ai_provider()

        assert provider is None

    def test_factory_does_not_crash_on_missing_config(self, monkeypatch):
        """Factory must never raise — it returns None instead."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("AI_ENABLED", raising=False)

        provider = get_ai_provider()
        # Default AI_ENABLED is "true", but key is missing → None
        assert provider is None


# ================================================================
# GeminiProvider tests
# ================================================================


class TestGeminiProvider:
    """Tests for GeminiProvider init and generate()."""

    @patch("app.ai.providers.gemini.genai", create=True)
    def test_provider_initialises_with_valid_config(self, mock_genai_module):
        """Provider should create a client when config is valid."""
        # We need to mock the import inside __init__
        mock_client = MagicMock()
        with patch.dict(
            "sys.modules",
            {"google": MagicMock(), "google.genai": MagicMock()},
        ):
            with patch(
                "google.genai.Client", return_value=mock_client
            ) as mock_client_cls:
                from app.ai.providers.gemini import GeminiProvider

                config = AIConfig(
                    api_key="test-key",
                    model_name="gemini-2.0-flash",
                    timeout=30,
                    enabled=True,
                )
                provider = GeminiProvider(config)

                assert provider.is_available() is True
                mock_client_cls.assert_called_once_with(api_key="test-key")

    def test_provider_unavailable_without_key(self):
        """Provider should not be available without an API key."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key=None,
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )
        provider = GeminiProvider(config)

        assert provider.is_available() is False

    def test_generate_raises_when_not_configured(self):
        """generate() should raise AIProviderUnavailableError."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key=None,
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )
        provider = GeminiProvider(config)

        with pytest.raises(AIProviderUnavailableError):
            provider.generate("Hello")

    def test_generate_returns_text(self):
        """generate() should return the model's text response."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Hello from Gemini!"
        mock_client.models.generate_content.return_value = mock_response

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = mock_client

        result = provider.generate("Say hello")

        assert result == "Hello from Gemini!"
        mock_client.models.generate_content.assert_called_once()

    def test_generate_passes_system_prompt(self):
        """generate() should forward system_prompt to the SDK."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = "Structured response"
        mock_client.models.generate_content.return_value = mock_response

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = mock_client

        # We do not mock google.genai.types because we want to verify the real
        # GenerateContentConfig object that gets passed to the client.
        result = provider.generate(
            "Analyse this",
            system_prompt="You are a financial analyst",
        )

        assert result == "Structured response"
        
        # Verify the config passed to generate_content
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        generation_config = call_kwargs.get("config")
        assert generation_config is not None
        assert generation_config.system_instruction == "You are a financial analyst"

    def test_generate_passes_response_schema(self):
        """generate() should pass response_schema for structured output."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"action": "SEND_REMINDER"}'
        mock_client.models.generate_content.return_value = mock_response

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = mock_client

        schema = {"type": "object", "properties": {"action": {"type": "string"}}}

        # We do not mock google.genai.types because we want to verify the real
        # GenerateContentConfig object that gets passed to the client.
        result = provider.generate("Pick an action", response_schema=schema)

        assert result == '{"action": "SEND_REMINDER"}'
        
        # Verify the config passed to generate_content
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        generation_config = call_kwargs.get("config")
        assert generation_config is not None
        assert generation_config.response_mime_type == "application/json"
        assert generation_config.response_schema == schema

    def test_generate_empty_response_raises(self):
        """generate() should raise AIInvalidResponseError on empty response."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = ""
        mock_client.models.generate_content.return_value = mock_response

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = mock_client

        with pytest.raises(AIInvalidResponseError):
            provider.generate("Hello")

    def test_generate_timeout_raises(self):
        """generate() should raise AITimeoutError on timeout exceptions."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "Request timeout exceeded"
        )

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = mock_client

        with pytest.raises(AITimeoutError):
            provider.generate("Hello")

    def test_generate_api_error_raises(self):
        """generate() should raise AIProviderError on general API errors."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = Exception(
            "Rate limit exceeded"
        )

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = mock_client

        with pytest.raises(AIProviderError):
            provider.generate("Hello")

    def test_health_returns_status_without_api_call(self):
        """health() should return config status without calling the API."""
        from app.ai.providers.gemini import GeminiProvider

        config = AIConfig(
            api_key="test-key",
            model_name="gemini-2.0-flash",
            timeout=30,
            enabled=True,
        )

        provider = GeminiProvider.__new__(GeminiProvider)
        provider._config = config
        provider._client = MagicMock()

        health = provider.health()

        assert health == {
            "enabled": True,
            "provider": "gemini",
            "configured": True,
            "model": "gemini-2.0-flash",
        }
        # Verify no API calls were made
        provider._client.models.generate_content.assert_not_called()


# ================================================================
# Exception hierarchy tests
# ================================================================


class TestExceptionHierarchy:
    """Verify that all custom exceptions are properly structured."""

    def test_all_exceptions_inherit_from_ai_error(self):
        """All AI exceptions should be catchable via AIError."""
        exceptions = [
            AIConfigurationError("test"),
            AIProviderUnavailableError("test"),
            AITimeoutError("test"),
            AIProviderError("test"),
            AIInvalidResponseError("test"),
        ]
        for exc in exceptions:
            assert isinstance(exc, AIError)
            assert isinstance(exc, Exception)


# ================================================================
# Health-check endpoint tests
# ================================================================


class TestAIHealthEndpoint:
    """Tests for the GET /api/ai/health endpoint."""

    def test_health_endpoint_with_key(self, client, monkeypatch):
        """Endpoint should report configured=true when key is present."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "true")

        # Mock GeminiProvider where it's defined — factory imports it lazily
        with patch("app.ai.providers.gemini.GeminiProvider") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance.health.return_value = {
                "enabled": True,
                "provider": "gemini",
                "configured": True,
                "model": "gemini-2.0-flash",
            }
            mock_cls.return_value = mock_instance
            mock_cls.PROVIDER_NAME = "gemini"

            response = client.get("/api/ai/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["enabled"] is True
        assert data["provider"] == "gemini"
        assert data["configured"] is True

    def test_health_endpoint_without_key(self, client, monkeypatch):
        """Endpoint should report configured=false when key is missing."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.setenv("AI_ENABLED", "true")

        response = client.get("/api/ai/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["enabled"] is True
        assert data["configured"] is False

    def test_health_endpoint_ai_disabled(self, client, monkeypatch):
        """Endpoint should report enabled=false when AI is disabled."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "false")

        response = client.get("/api/ai/health")

        assert response.status_code == 200
        data = response.get_json()
        assert data["enabled"] is False
        assert data["configured"] is False

    def test_health_endpoint_does_not_call_api(self, client, monkeypatch):
        """The health endpoint must never make an external API call."""
        monkeypatch.setenv("GEMINI_API_KEY", "test-key-123")
        monkeypatch.setenv("AI_ENABLED", "true")

        with patch("app.ai.providers.gemini.GeminiProvider") as mock_cls:
            mock_instance = MagicMock()
            mock_instance.is_available.return_value = True
            mock_instance.health.return_value = {
                "enabled": True,
                "provider": "gemini",
                "configured": True,
                "model": "gemini-2.0-flash",
            }
            mock_cls.return_value = mock_instance
            mock_cls.PROVIDER_NAME = "gemini"

            client.get("/api/ai/health")

            # generate_content should never be called
            mock_instance.generate.assert_not_called()
