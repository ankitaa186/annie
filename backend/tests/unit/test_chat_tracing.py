"""
Unit tests for chat endpoint Langfuse tracing.

Tests AC #1, #2: Chat endpoint trace creation and completion
"""
import pytest
import os
from unittest.mock import patch, Mock, MagicMock
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


class TestChatEndpointTracing:
    """Test AC #1 and #2: Chat endpoint tracing."""

    @patch("api.routes.chat.start_trace")
    @patch("api.routes.chat.trace_error")
    def test_trace_created_on_chat_request(self, mock_trace_error, mock_start_trace, test_client):
        """Test that trace is created with correct metadata when chat request is received."""
        # Mock trace object
        mock_trace = Mock()
        mock_trace.update = Mock()
        mock_start_trace.return_value = mock_trace

        # Mock other dependencies
        with patch("api.routes.chat.StateManager") as mock_state, \
             patch("api.routes.chat.ProfileManager") as mock_profile:

            mock_state_instance = MagicMock()
            mock_state.__aenter__ = MagicMock(return_value=mock_state_instance)
            mock_state.__aexit__ = MagicMock(return_value=None)

            mock_state_instance.get_session = MagicMock(return_value={
                "conversation_id": "test_conv_123",
                "platform": "telegram"
            })
            mock_state_instance.add_message = MagicMock()

            mock_profile_instance = MagicMock()
            mock_profile.return_value = mock_profile_instance
            mock_profile_instance.get_profile = MagicMock(return_value={"name": "Test User"})

            # Make request
            response = test_client.post(
                "/api/chat",
                json={
                    "user_id": "test_user_123",
                    "platform": "telegram",
                    "message": "Hello, Annie!"
                }
            )

            # Verify trace was started with correct metadata
            mock_start_trace.assert_called_once()
            call_args = mock_start_trace.call_args

            assert call_args[1]["name"] == "chat_request"
            assert call_args[1]["user_id"] == "test_user_123"
            assert "platform" in call_args[1]["metadata"]
            assert call_args[1]["metadata"]["platform"] == "telegram"
            assert "message_length" in call_args[1]["metadata"]
            assert call_args[1]["metadata"]["message_length"] == len("Hello, Annie!")

    @patch("api.routes.chat.start_trace")
    def test_trace_updated_with_conversation_id(self, mock_start_trace, test_client):
        """Test that trace is updated with conversation_id after session creation."""
        # Mock trace object
        mock_trace = Mock()
        mock_trace.update = Mock()
        mock_start_trace.return_value = mock_trace

        # Mock dependencies
        with patch("api.routes.chat.StateManager") as mock_state, \
             patch("api.routes.chat.ProfileManager") as mock_profile:

            mock_state_instance = MagicMock()
            mock_state.__aenter__ = MagicMock(return_value=mock_state_instance)
            mock_state.__aexit__ = MagicMock(return_value=None)

            mock_state_instance.get_session = MagicMock(return_value={
                "conversation_id": "conv_abc123",
                "platform": "api"
            })
            mock_state_instance.add_message = MagicMock()

            mock_profile_instance = MagicMock()
            mock_profile.return_value = mock_profile_instance
            mock_profile_instance.get_profile = MagicMock(return_value={})

            # Make request
            response = test_client.post(
                "/api/chat",
                json={
                    "user_id": "test_user",
                    "platform": "api",
                    "message": "Test message"
                }
            )

            # Verify trace was updated with conversation_id
            mock_trace.update.assert_called()
            update_calls = [call for call in mock_trace.update.call_args_list
                          if "conversation_id" in str(call)]
            assert len(update_calls) > 0

    @patch("api.routes.chat.start_trace")
    @patch("api.routes.chat.trace_error")
    def test_trace_error_recorded_on_exception(self, mock_trace_error, mock_start_trace, test_client):
        """Test that errors are recorded in trace when exceptions occur."""
        # Mock trace
        mock_trace = Mock()
        mock_start_trace.return_value = mock_trace

        # Mock StateManager to raise exception
        with patch("api.routes.chat.StateManager") as mock_state:
            mock_state_instance = MagicMock()
            mock_state.__aenter__ = MagicMock(return_value=mock_state_instance)
            mock_state.__aexit__ = MagicMock(return_value=None)

            # Simulate StateError
            from api.state import StateError
            mock_state_instance.get_session = MagicMock(side_effect=StateError("Redis connection failed"))

            # Make request (should fail)
            response = test_client.post(
                "/api/chat",
                json={
                    "user_id": "test_user",
                    "platform": "api",
                    "message": "Test"
                }
            )

            # Verify error was recorded
            mock_trace_error.assert_called_once()
            call_args = mock_trace_error.call_args
            assert isinstance(call_args[0][0], StateError)
            assert "error_type" in call_args[1]["metadata"]

    @patch("api.routes.chat.start_trace")
    def test_tracing_gracefully_degrades_when_disabled(self, mock_start_trace, test_client):
        """Test AC #6: Application continues when Langfuse is unavailable."""
        # Mock start_trace to return None (tracing disabled)
        mock_start_trace.return_value = None

        # Mock dependencies
        with patch("api.routes.chat.StateManager") as mock_state, \
             patch("api.routes.chat.ProfileManager") as mock_profile:

            mock_state_instance = MagicMock()
            mock_state.__aenter__ = MagicMock(return_value=mock_state_instance)
            mock_state.__aexit__ = MagicMock(return_value=None)

            mock_state_instance.get_session = MagicMock(return_value={
                "conversation_id": "conv_123",
                "platform": "api"
            })
            mock_state_instance.add_message = MagicMock()

            mock_profile_instance = MagicMock()
            mock_profile.return_value = mock_profile_instance
            mock_profile_instance.get_profile = MagicMock(return_value={})

            # Make request
            response = test_client.post(
                "/api/chat",
                json={
                    "user_id": "test_user",
                    "platform": "api",
                    "message": "Test"
                }
            )

            # Verify request succeeded despite tracing being disabled
            assert response.status_code == 200

    # test_trace_includes_conversation_ending_flag removed - farewell detection no longer exists
    # (Story 12.4: Memory storage now happens on every message via orchestrator batching)
