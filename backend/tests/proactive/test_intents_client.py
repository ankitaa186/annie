"""
Tests for IntentsClient - HTTP client for agentic-memories Intents API.

Tests:
- CRUD operations (create, get, update, delete, list)
- Worker operations (get_pending, claim, fire)
- Error handling (network, API, timeout)
- Health check
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
import httpx

from api.proactive.intents_client import (
    IntentsClient,
    IntentsClientError,
    IntentsNetworkError,
    IntentsAPIError,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    return AsyncMock()


@pytest.fixture
def sample_intent():
    """Sample intent object."""
    return {
        "id": "intent_123",
        "user_id": "user_456",
        "intent_name": "Daily Briefing",
        "trigger_type": "cron",
        "schedule": {"cron": "0 9 * * *"},
        "action_context": "Send daily market update",
        "enabled": True,
        "fire_count": 5,
        "last_fired_at": "2025-12-24T09:00:00Z"
    }


# ============================================================================
# Exception Tests
# ============================================================================

def test_intents_client_error():
    """Test base IntentsClientError."""
    error = IntentsClientError("Test error")
    assert str(error) == "Test error"


def test_intents_network_error():
    """Test IntentsNetworkError with original error."""
    original = Exception("Connection refused")
    error = IntentsNetworkError("Network error", original_error=original)

    assert error.message == "Network error"
    assert error.original_error is original


def test_intents_api_error():
    """Test IntentsAPIError with status code."""
    error = IntentsAPIError(
        message="Not found",
        status_code=404,
        response_data={"error": "Intent not found"}
    )

    assert error.status_code == 404
    assert "404" in str(error)


# ============================================================================
# Initialization Tests
# ============================================================================

def test_intents_client_init_with_defaults():
    """Test IntentsClient initialization with defaults."""
    with patch('api.proactive.intents_client.get_config') as mock_config:
        mock_config.return_value = {"AGENTIC_MEMORIES_URL": "http://localhost:8080"}

        client = IntentsClient()

        assert client.intents_url == "http://localhost:8080"


def test_intents_client_init_with_custom_url():
    """Test IntentsClient initialization with custom URL."""
    client = IntentsClient(intents_url="http://custom:9000")

    assert client.intents_url == "http://custom:9000"


def test_intents_client_context_manager():
    """Test IntentsClient async context manager."""
    client = IntentsClient(intents_url="http://localhost:8080")

    assert hasattr(client, '__aenter__')
    assert hasattr(client, '__aexit__')


# ============================================================================
# CRUD Operation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_create_intent(sample_intent):
    """Test creating an intent."""
    client = IntentsClient(intents_url="http://localhost:8080")

    # Mock the httpx client response - implementation expects 200
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = sample_intent

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.create_intent({
            "user_id": "user_456",
            "intent_name": "Daily Briefing",
            "trigger_type": "cron",
            "schedule": {"cron": "0 9 * * *"}
        })

        assert result["id"] == "intent_123"
        mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_get_intent(sample_intent):
    """Test getting an intent by ID."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = sample_intent

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await client.get_intent("intent_123")

        assert result["id"] == "intent_123"
        assert result["intent_name"] == "Daily Briefing"


@pytest.mark.asyncio
async def test_update_intent(sample_intent):
    """Test updating an intent."""
    client = IntentsClient(intents_url="http://localhost:8080")

    updated = {**sample_intent, "enabled": False}
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = updated

    with patch.object(client.client, 'put', new_callable=AsyncMock) as mock_put:
        mock_put.return_value = mock_response

        result = await client.update_intent("intent_123", {"enabled": False})

        assert result["enabled"] is False


@pytest.mark.asyncio
async def test_delete_intent():
    """Test deleting an intent."""
    client = IntentsClient(intents_url="http://localhost:8080")

    # Implementation expects 200 for success
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"deleted": True}

    with patch.object(client.client, 'delete', new_callable=AsyncMock) as mock_delete:
        mock_delete.return_value = mock_response

        result = await client.delete_intent("intent_123")

        assert result is True


@pytest.mark.asyncio
async def test_list_intents(sample_intent):
    """Test listing intents for a user."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [sample_intent]

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await client.list_intents("user_456")

        assert len(result) == 1
        assert result[0]["id"] == "intent_123"


# ============================================================================
# Worker Operation Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_pending_intents(sample_intent):
    """Test getting pending intents."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [sample_intent]

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await client.get_pending()

        assert len(result) == 1


@pytest.mark.asyncio
async def test_claim_intent_success(sample_intent):
    """Test claiming an intent successfully."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = sample_intent

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.claim_intent("intent_123")

        assert result["id"] == "intent_123"
        assert result.get("conflict") is not True


@pytest.mark.asyncio
async def test_claim_intent_conflict():
    """Test claim conflict returns conflict flag."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 409
    mock_response.json.return_value = {"error": "Already claimed"}

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.claim_intent("intent_123")

        assert result.get("conflict") is True


@pytest.mark.asyncio
async def test_fire_intent_success():
    """Test firing an intent with success status."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "success"}

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.fire_intent("intent_123", {
            "status": "success",
            "message_id": "msg_789",
            "delivery_ms": 150
        })

        assert result["status"] == "success"


@pytest.mark.asyncio
async def test_fire_intent_gate_blocked():
    """Test firing intent with gate_blocked status."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "gate_blocked"}

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.fire_intent("intent_123", {
            "status": "gate_blocked",
            "reason": "daily_limit"
        })

        assert result["status"] == "gate_blocked"


@pytest.mark.asyncio
async def test_fire_intent_condition_not_met():
    """Test firing intent with condition_not_met status."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "condition_not_met"}

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        result = await client.fire_intent("intent_123", {
            "status": "condition_not_met",
            "trigger_data": {"current_price": 140.0, "threshold": 130.0}
        })

        assert result["status"] == "condition_not_met"


# ============================================================================
# Error Handling Tests
# ============================================================================

@pytest.mark.asyncio
async def test_network_error():
    """Test network error handling."""
    import httpx
    client = IntentsClient(intents_url="http://localhost:8080")

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        with pytest.raises(IntentsNetworkError):
            await client.get_intent("intent_123")


@pytest.mark.asyncio
async def test_api_error_404():
    """Test 404 API error."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 404
    mock_response.json.return_value = {"error": "Not found"}

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        with pytest.raises(IntentsAPIError) as exc_info:
            await client.get_intent("nonexistent")

        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_api_error_500():
    """Test 500 API error."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"error": "Internal server error"}

    with patch.object(client.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response

        with pytest.raises(IntentsAPIError) as exc_info:
            await client.create_intent({"user_id": "user_456"})

        assert exc_info.value.status_code == 500


@pytest.mark.asyncio
async def test_timeout_error():
    """Test timeout error handling."""
    import httpx
    client = IntentsClient(intents_url="http://localhost:8080")

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Request timeout")

        with pytest.raises(IntentsNetworkError):
            await client.get_pending()


# ============================================================================
# Health Check Tests
# ============================================================================

@pytest.mark.asyncio
async def test_health_check_ok():
    """Test health check returns True when healthy."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"status": "ok"}

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await client.health_check()

        assert result is True


@pytest.mark.asyncio
async def test_health_check_error():
    """Test health check returns False on error."""
    import httpx
    client = IntentsClient(intents_url="http://localhost:8080")

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")

        result = await client.health_check()

        assert result is False


# ============================================================================
# History Tests
# ============================================================================

@pytest.mark.asyncio
async def test_get_history():
    """Test getting intent fire history."""
    client = IntentsClient(intents_url="http://localhost:8080")

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {"fired_at": "2025-12-24T09:00:00Z", "status": "success"},
        {"fired_at": "2025-12-23T09:00:00Z", "status": "success"},
    ]

    with patch.object(client.client, 'get', new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_response

        result = await client.get_history("intent_123", limit=10)

        assert len(result) == 2
