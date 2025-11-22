"""
Integration tests for Langfuse health check endpoint.

Tests AC #3: Health check endpoint includes Langfuse status.
"""
import pytest
import os
from unittest.mock import patch
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    # Skip environment validation for testing
    os.environ["SKIP_ENV_VALIDATION"] = "true"

    from api.main import app
    client = TestClient(app)
    yield client

    # Clean up
    del os.environ["SKIP_ENV_VALIDATION"]


class TestLangfuseHealthEndpoint:
    """Test AC #3: Health endpoint includes Langfuse status."""

    def test_health_endpoint_includes_langfuse_when_enabled(self, test_client):
        """Test that /health/detailed includes Langfuse status when enabled."""
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-test-12345",
            "LANGFUSE_SECRET_KEY": "sk-test-67890"
        }):
            # Clear lru_cache for config functions
            from api.config import (
                get_langfuse_public_key,
                get_langfuse_secret_key,
                is_langfuse_enabled
            )
            get_langfuse_public_key.cache_clear()
            get_langfuse_secret_key.cache_clear()
            is_langfuse_enabled.cache_clear()

            # Mock Langfuse client to be available
            with patch("api.main.check_langfuse_health") as mock_health:
                mock_health.return_value = {
                    "enabled": True,
                    "client_available": True,
                    "last_flush": None
                }

                response = test_client.get("/health/detailed")

                # Verify response
                assert response.status_code == 200
                data = response.json()

                # Verify Langfuse status is included
                assert "langfuse" in data["components"]
                langfuse_status = data["components"]["langfuse"]

                # Verify structure matches AC #3 requirements
                assert "enabled" in langfuse_status
                assert "client_available" in langfuse_status
                assert "last_flush" in langfuse_status

                # Verify values
                assert langfuse_status["enabled"] is True
                assert langfuse_status["client_available"] is True

    def test_health_endpoint_shows_langfuse_disabled(self, test_client):
        """Test that /health/detailed shows Langfuse as disabled when keys missing."""
        with patch.dict(os.environ, {}, clear=True):
            # Clear lru_cache for config functions
            from api.config import (
                get_langfuse_public_key,
                get_langfuse_secret_key,
                is_langfuse_enabled
            )
            get_langfuse_public_key.cache_clear()
            get_langfuse_secret_key.cache_clear()
            is_langfuse_enabled.cache_clear()

            response = test_client.get("/health/detailed")

            # Verify response
            assert response.status_code == 200
            data = response.json()

            # Verify Langfuse status is included but disabled
            assert "langfuse" in data["components"]
            langfuse_status = data["components"]["langfuse"]

            assert langfuse_status["enabled"] is False
            assert langfuse_status["client_available"] is False

    def test_health_endpoint_handles_langfuse_unavailable(self, test_client):
        """Test that /health/detailed handles Langfuse being unavailable."""
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-test-12345",
            "LANGFUSE_SECRET_KEY": "sk-test-67890"
        }):
            # Clear lru_cache
            from api.config import (
                get_langfuse_public_key,
                get_langfuse_secret_key,
                is_langfuse_enabled
            )
            get_langfuse_public_key.cache_clear()
            get_langfuse_secret_key.cache_clear()
            is_langfuse_enabled.cache_clear()

            # Mock Langfuse client initialization failure
            with patch("langfuse.Langfuse", side_effect=Exception("Connection refused")):
                response = test_client.get("/health/detailed")

                # Verify response (should still succeed with AC #5 fire-and-forget)
                assert response.status_code == 200
                data = response.json()

                # Verify Langfuse status shows client unavailable
                assert "langfuse" in data["components"]
                langfuse_status = data["components"]["langfuse"]

                # Enabled should be True (keys configured) but client unavailable
                assert langfuse_status["enabled"] is True
                assert langfuse_status["client_available"] is False

    def test_basic_health_endpoint_still_works(self, test_client):
        """Test that basic /health endpoint continues to work."""
        response = test_client.get("/health")

        # Verify response
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "ok"
        assert "timestamp" in data

    def test_health_endpoint_response_structure(self, test_client):
        """Test that detailed health endpoint has expected structure."""
        response = test_client.get("/health/detailed")

        assert response.status_code == 200
        data = response.json()

        # Verify top-level structure
        assert "status" in data
        assert "components" in data
        assert "timestamp" in data

        # Verify components include all services
        components = data["components"]
        assert "mcp_server" in components
        assert "redis" in components
        assert "llm_api" in components
        assert "agentic_memories" in components
        assert "langfuse" in components

        # Verify Langfuse status has required fields (AC #3)
        langfuse_status = components["langfuse"]
        assert isinstance(langfuse_status, dict)
        assert "enabled" in langfuse_status
        assert "client_available" in langfuse_status
        assert "last_flush" in langfuse_status
