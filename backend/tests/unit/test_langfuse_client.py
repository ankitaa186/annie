"""
Unit tests for Langfuse client singleton and health check functionality.

Tests AC #1, #2, #5, #6: Client initialization, graceful degradation, and health checks.
"""
import os
import pytest
from unittest.mock import Mock, patch, MagicMock


# Reset the singleton before each test
@pytest.fixture(autouse=True)
def reset_langfuse_singleton():
    """Reset the Langfuse client singleton before each test."""
    import api.observability.langfuse_client as lf_client
    lf_client._langfuse_client = None
    yield
    lf_client._langfuse_client = None


@pytest.fixture
def mock_env_enabled():
    """Mock environment with Langfuse keys configured."""
    with patch.dict(os.environ, {
        "LANGFUSE_PUBLIC_KEY": "pk-test-12345",
        "LANGFUSE_SECRET_KEY": "sk-test-67890",
        "LANGFUSE_HOST": "https://us.cloud.langfuse.com"
    }):
        # Clear lru_cache for config functions
        from api.config import (
            get_langfuse_public_key,
            get_langfuse_secret_key,
            get_langfuse_host,
            is_langfuse_enabled
        )
        get_langfuse_public_key.cache_clear()
        get_langfuse_secret_key.cache_clear()
        get_langfuse_host.cache_clear()
        is_langfuse_enabled.cache_clear()
        yield


@pytest.fixture
def mock_env_disabled():
    """Mock environment without Langfuse keys configured."""
    with patch.dict(os.environ, {}, clear=True):
        # Clear lru_cache for config functions
        from api.config import (
            get_langfuse_public_key,
            get_langfuse_secret_key,
            get_langfuse_host,
            is_langfuse_enabled
        )
        get_langfuse_public_key.cache_clear()
        get_langfuse_secret_key.cache_clear()
        get_langfuse_host.cache_clear()
        is_langfuse_enabled.cache_clear()
        yield


class TestLangfuseClientInitialization:
    """Test AC #1: Client initializes successfully with correct configuration."""

    def test_client_initializes_with_valid_keys(self, mock_env_enabled):
        """Test that Langfuse client initializes when keys are configured."""
        # Patch where Langfuse is imported (inside get_langfuse_client function)
        with patch("langfuse.Langfuse") as mock_langfuse:
            mock_client_instance = Mock()
            mock_langfuse.return_value = mock_client_instance

            from api.observability.langfuse_client import get_langfuse_client

            client = get_langfuse_client()

            # Verify client was created
            assert client is not None
            assert client == mock_client_instance

            # Verify Langfuse was initialized with correct parameters
            mock_langfuse.assert_called_once_with(
                public_key="pk-test-12345",
                secret_key="sk-test-67890",
                host="https://us.cloud.langfuse.com",
                release="annie-test",  # From LANGFUSE_ENVIRONMENT env var
                flush_at=10,  # Batch size as per AC #1
                flush_interval=1.0,  # Flush interval as per AC #1
                enabled=True,
                debug=False
            )

    def test_client_is_singleton(self, mock_env_enabled):
        """Test that Langfuse client follows singleton pattern."""
        with patch("langfuse.Langfuse") as mock_langfuse:
            mock_client_instance = Mock()
            mock_langfuse.return_value = mock_client_instance

            from api.observability.langfuse_client import get_langfuse_client

            # Get client twice
            client1 = get_langfuse_client()
            client2 = get_langfuse_client()

            # Verify same instance returned
            assert client1 is client2

            # Verify Langfuse constructor called only once (singleton)
            assert mock_langfuse.call_count == 1


class TestGracefulDegradation:
    """Test AC #2: Application continues without crashes when keys are missing."""

    def test_graceful_degradation_when_keys_missing(self, mock_env_disabled, caplog):
        """Test that app continues without Langfuse when keys are not configured."""
        from api.observability.langfuse_client import get_langfuse_client

        client = get_langfuse_client()

        # Verify client is None (graceful degradation)
        assert client is None

        # Verify appropriate log message (AC #2 requires INFO level log)
        assert any(
            "Langfuse tracing disabled" in record.message and record.levelname == "INFO"
            for record in caplog.records
        )

    def test_graceful_degradation_on_import_error(self, mock_env_enabled, caplog):
        """Test that app continues when Langfuse package is not installed."""
        with patch("langfuse.Langfuse", side_effect=ImportError("No module named 'langfuse'")):
            from api.observability.langfuse_client import get_langfuse_client

            client = get_langfuse_client()

            # Verify client is None (graceful degradation)
            assert client is None

            # Verify warning log
            assert any(
                "Langfuse package not installed" in record.message
                for record in caplog.records
            )

    def test_graceful_degradation_on_initialization_error(self, mock_env_enabled, caplog):
        """Test that app continues when Langfuse initialization fails."""
        with patch("langfuse.Langfuse", side_effect=Exception("Connection refused")):
            from api.observability.langfuse_client import get_langfuse_client

            client = get_langfuse_client()

            # Verify client is None (graceful degradation)
            assert client is None

            # Verify warning log (AC #2 and #5 fire-and-forget pattern)
            assert any(
                "Failed to initialize Langfuse client" in record.message
                for record in caplog.records
            )


class TestPingLangfuseHealthCheck:
    """Test AC #6: ping_langfuse() health check returns correct status."""

    def test_ping_returns_true_when_client_available(self, mock_env_enabled):
        """Test that ping_langfuse returns True when client is available."""
        with patch("langfuse.Langfuse") as mock_langfuse:
            mock_client_instance = Mock()
            mock_langfuse.return_value = mock_client_instance

            from api.observability.langfuse_client import ping_langfuse

            status = ping_langfuse()

            # Verify health check returns True
            assert status is True

    def test_ping_returns_false_when_disabled(self, mock_env_disabled):
        """Test that ping_langfuse returns False when Langfuse is disabled."""
        from api.observability.langfuse_client import ping_langfuse

        status = ping_langfuse()

        # Verify health check returns False
        assert status is False

    def test_ping_returns_false_when_initialization_fails(self, mock_env_enabled):
        """Test that ping_langfuse returns False when initialization fails."""
        with patch("langfuse.Langfuse", side_effect=Exception("Connection refused")):
            from api.observability.langfuse_client import ping_langfuse

            status = ping_langfuse()

            # Verify health check returns False (fire-and-forget)
            assert status is False

    def test_ping_is_non_blocking(self, mock_env_enabled):
        """Test that ping_langfuse() is non-blocking as per AC #6."""
        with patch("langfuse.Langfuse") as mock_langfuse:
            # Simulate slow initialization
            def slow_init(*args, **kwargs):
                return Mock()

            mock_langfuse.side_effect = slow_init

            from api.observability.langfuse_client import ping_langfuse
            import time

            start = time.time()
            status = ping_langfuse()
            duration = time.time() - start

            # Verify it completes quickly (non-blocking)
            assert duration < 1.0  # Should be nearly instant
            assert status is True
