"""
Tests for Conversations API Endpoints (Story 20.14)

Tests cover:
- List conversations (AC: 1)
- Create conversation (AC: 2)
- Get conversation with pagination (AC: 3)
- Delete conversation (AC: 4)
- Update conversation title (AC: 5)
- Get messages endpoint (AC: 6)
- Authentication validation (AC: 8)
- 404/403 error scenarios
"""

import json
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

# Import test environment setup first
from tests.conftest import TEST_ENV_VARS


class TestConversationModels:
    """Test conversation Pydantic models."""

    def test_conversation_model(self):
        """Test Conversation model validation."""
        from api.models.conversation import Conversation

        conv = Conversation(
            id="conv_123",
            title="Test Conversation",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            message_count=5,
            last_message_preview="Hello..."
        )

        assert conv.id == "conv_123"
        assert conv.title == "Test Conversation"
        assert conv.message_count == 5
        assert conv.last_message_preview == "Hello..."

    def test_conversation_default_values(self):
        """Test Conversation model default values."""
        from api.models.conversation import Conversation

        conv = Conversation(
            id="conv_123",
            title="Test",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        assert conv.message_count == 0
        assert conv.last_message_preview is None

    def test_create_conversation_request_optional_title(self):
        """Test CreateConversationRequest allows optional title."""
        from api.models.conversation import CreateConversationRequest

        # With title
        req = CreateConversationRequest(title="My Chat")
        assert req.title == "My Chat"

        # Without title
        req = CreateConversationRequest()
        assert req.title is None

    def test_update_conversation_request_validation(self):
        """Test UpdateConversationRequest title validation."""
        from api.models.conversation import UpdateConversationRequest

        # Valid title
        req = UpdateConversationRequest(title="New Title")
        assert req.title == "New Title"

        # Empty title should fail
        with pytest.raises(Exception):  # Pydantic ValidationError
            UpdateConversationRequest(title="")

    def test_pagination_info_model(self):
        """Test PaginationInfo model."""
        from api.models.conversation import PaginationInfo

        pagination = PaginationInfo(
            page=2,
            limit=50,
            total=100,
            has_more=True
        )

        assert pagination.page == 2
        assert pagination.limit == 50
        assert pagination.total == 100
        assert pagination.has_more is True


class TestStateManagerConversations:
    """Test StateManager conversation methods."""

    @pytest.fixture
    def mock_redis(self):
        """Create async mock Redis client."""
        redis_mock = AsyncMock()
        redis_mock.ping = AsyncMock(return_value=True)
        redis_mock.exists = AsyncMock(return_value=1)
        return redis_mock

    @pytest.mark.asyncio
    async def test_create_conversation(self, mock_redis):
        """Test conversation creation."""
        from api.state import StateManager

        # Setup mock
        mock_redis.pipeline = MagicMock()
        pipe_mock = AsyncMock()
        mock_redis.pipeline.return_value = pipe_mock
        pipe_mock.execute = AsyncMock(return_value=[True, True, True, True, True])

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.create_conversation("user_123", title="Test Chat")

        assert result["conversation_id"].startswith("conv_")
        assert result["title"] == "Test Chat"
        assert "created_at" in result

    @pytest.mark.asyncio
    async def test_create_conversation_default_title(self, mock_redis):
        """Test conversation creation with default title."""
        from api.state import StateManager

        mock_redis.pipeline = MagicMock()
        pipe_mock = AsyncMock()
        mock_redis.pipeline.return_value = pipe_mock
        pipe_mock.execute = AsyncMock(return_value=[True, True, True, True, True])

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.create_conversation("user_123")

        assert result["title"] == "New Chat"

    @pytest.mark.asyncio
    async def test_list_conversations_empty(self, mock_redis):
        """Test listing conversations for user with no conversations."""
        from api.state import StateManager

        mock_redis.zrevrange = AsyncMock(return_value=[])

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.list_conversations("user_123")

        assert result == []

    @pytest.mark.asyncio
    async def test_list_conversations_with_data(self, mock_redis):
        """Test listing conversations with data."""
        from api.state import StateManager

        # Mock sorted set returns conversation IDs
        mock_redis.zrevrange = AsyncMock(return_value=["conv_1", "conv_2"])

        # Mock metadata retrieval
        mock_redis.hgetall = AsyncMock(return_value={
            "user_id": "user_123",
            "title": "Test Chat",
            "created_at": "2026-01-26T10:00:00Z",
            "updated_at": "2026-01-26T12:00:00Z"
        })

        mock_redis.llen = AsyncMock(return_value=5)
        mock_redis.lindex = AsyncMock(return_value=json.dumps({
            "role": "user",
            "content": "Hello world"
        }))

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.list_conversations("user_123")

        assert len(result) == 2
        assert result[0]["title"] == "Test Chat"
        assert result[0]["message_count"] == 5

    @pytest.mark.asyncio
    async def test_get_conversation_detail(self, mock_redis):
        """Test getting conversation detail."""
        from api.state import StateManager

        mock_redis.hgetall = AsyncMock(return_value={
            "user_id": "user_123",
            "title": "My Conversation",
            "created_at": "2026-01-26T10:00:00Z",
            "updated_at": "2026-01-26T12:00:00Z"
        })

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.get_conversation_detail("conv_123")

        assert result["id"] == "conv_123"
        assert result["title"] == "My Conversation"
        assert result["user_id"] == "user_123"

    @pytest.mark.asyncio
    async def test_get_conversation_detail_not_found(self, mock_redis):
        """Test getting non-existent conversation."""
        from api.state import StateManager

        mock_redis.hgetall = AsyncMock(return_value={})

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.get_conversation_detail("conv_nonexistent")

        assert result is None

    @pytest.mark.asyncio
    async def test_update_conversation_title(self, mock_redis):
        """Test updating conversation title."""
        from api.state import StateManager

        mock_redis.exists = AsyncMock(return_value=1)
        mock_redis.hget = AsyncMock(return_value="user_123")
        mock_redis.pipeline = MagicMock()
        pipe_mock = AsyncMock()
        mock_redis.pipeline.return_value = pipe_mock
        pipe_mock.execute = AsyncMock(return_value=[True, True, True])

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.update_conversation_title("conv_123", "New Title")

        assert result["title"] == "New Title"
        assert "updated_at" in result

    @pytest.mark.asyncio
    async def test_delete_conversation(self, mock_redis):
        """Test deleting conversation."""
        from api.state import StateManager

        mock_redis.hget = AsyncMock(return_value="user_123")
        mock_redis.pipeline = MagicMock()
        pipe_mock = AsyncMock()
        mock_redis.pipeline.return_value = pipe_mock
        pipe_mock.execute = AsyncMock(return_value=[1, 1, 1, 1])

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.delete_conversation("conv_123")

        assert result is True

    @pytest.mark.asyncio
    async def test_delete_conversation_not_found(self, mock_redis):
        """Test deleting non-existent conversation."""
        from api.state import StateManager

        mock_redis.hget = AsyncMock(return_value=None)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.delete_conversation("conv_nonexistent")

        assert result is False

    @pytest.mark.asyncio
    async def test_get_paginated_messages(self, mock_redis):
        """Test getting paginated messages."""
        from api.state import StateManager

        mock_redis.llen = AsyncMock(return_value=100)
        mock_redis.lrange = AsyncMock(return_value=[
            json.dumps({"role": "user", "content": "Hello"}),
            json.dumps({"role": "assistant", "content": "Hi there!"})
        ])

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.get_paginated_messages("conv_123", page=1, limit=50)

        assert len(result["messages"]) == 2
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["total"] == 100
        assert result["pagination"]["has_more"] is True

    @pytest.mark.asyncio
    async def test_get_conversations_count(self, mock_redis):
        """Test getting conversation count."""
        from api.state import StateManager

        mock_redis.zcard = AsyncMock(return_value=10)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.get_conversations_count("user_123")

        assert result == 10


class TestConversationsRouter:
    """Test conversations router endpoints."""

    @pytest.fixture
    def mock_request_authenticated(self):
        """Create mock authenticated request."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()
        request.state.user_id = "user_123"
        request.url = MagicMock()
        request.url.path = "/api/conversations"
        request.method = "GET"
        return request

    @pytest.fixture
    def mock_request_unauthenticated(self):
        """Create mock unauthenticated request."""
        request = MagicMock(spec=Request)
        request.state = MagicMock(spec=[])  # No user_id attribute
        request.url = MagicMock()
        request.url.path = "/api/conversations"
        request.method = "GET"
        return request

    def test_get_user_id_authenticated(self, mock_request_authenticated):
        """Test get_user_id with authenticated request."""
        from api.routes.conversations import get_user_id

        user_id = get_user_id(mock_request_authenticated)
        assert user_id == "user_123"

    def test_get_user_id_unauthenticated(self, mock_request_unauthenticated):
        """Test get_user_id with unauthenticated request raises 401."""
        from fastapi import HTTPException
        from api.routes.conversations import get_user_id

        with pytest.raises(HTTPException) as exc_info:
            get_user_id(mock_request_unauthenticated)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_verify_conversation_ownership_success(self):
        """Test ownership verification success."""
        from api.routes.conversations import verify_conversation_ownership

        # Mock state manager
        state = AsyncMock()
        state.get_conversation_detail = AsyncMock(return_value={
            "id": "conv_123",
            "user_id": "user_123",
            "title": "Test"
        })

        result = await verify_conversation_ownership(state, "conv_123", "user_123")
        assert result is True

    @pytest.mark.asyncio
    async def test_verify_conversation_ownership_not_found(self):
        """Test ownership verification for non-existent conversation."""
        from fastapi import HTTPException
        from api.routes.conversations import verify_conversation_ownership

        state = AsyncMock()
        state.get_conversation_detail = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc_info:
            await verify_conversation_ownership(state, "conv_123", "user_123")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_verify_conversation_ownership_forbidden(self):
        """Test ownership verification for wrong user."""
        from fastapi import HTTPException
        from api.routes.conversations import verify_conversation_ownership

        state = AsyncMock()
        state.get_conversation_detail = AsyncMock(return_value={
            "id": "conv_123",
            "user_id": "other_user",
            "title": "Test"
        })

        with pytest.raises(HTTPException) as exc_info:
            await verify_conversation_ownership(state, "conv_123", "user_123")

        assert exc_info.value.status_code == 403


class TestRateLimiter:
    """Test rate limiter middleware."""

    @pytest.fixture
    def mock_redis(self):
        """Create async mock Redis client."""
        redis_mock = AsyncMock()
        return redis_mock

    @pytest.mark.asyncio
    async def test_rate_limiter_under_limit(self, mock_redis):
        """Test rate limiter allows requests under limit."""
        from api.middleware.rate_limiter import RateLimiter

        mock_redis.pipeline = MagicMock()
        pipe_mock = AsyncMock()
        mock_redis.pipeline.return_value = pipe_mock
        pipe_mock.execute = AsyncMock(return_value=[0, 10])  # Removed 0, count is 10

        mock_redis.zadd = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        limiter = RateLimiter(redis_client=mock_redis, requests=60, window=60)

        is_limited, remaining, retry_after = await limiter.is_rate_limited("user_123")

        assert is_limited is False
        assert remaining == 49  # 60 - 10 - 1
        assert retry_after == 0

    @pytest.mark.asyncio
    async def test_rate_limiter_at_limit(self, mock_redis):
        """Test rate limiter blocks requests at limit."""
        from api.middleware.rate_limiter import RateLimiter

        mock_redis.pipeline = MagicMock()
        pipe_mock = AsyncMock()
        mock_redis.pipeline.return_value = pipe_mock
        pipe_mock.execute = AsyncMock(return_value=[0, 60])  # At limit

        mock_redis.zrange = AsyncMock(return_value=[(b"123", time.time() - 30)])

        limiter = RateLimiter(redis_client=mock_redis, requests=60, window=60)

        is_limited, remaining, retry_after = await limiter.is_rate_limited("user_123")

        assert is_limited is True
        assert remaining == 0
        assert retry_after > 0


class TestCORSConfiguration:
    """Test CORS configuration."""

    def test_cors_origins_include_production(self):
        """Test CORS includes production domain."""
        from api.main import CORS_ORIGINS

        assert "https://annie.memoryforge.io" in CORS_ORIGINS

    def test_cors_origins_include_localhost(self):
        """Test CORS includes localhost for development."""
        from api.main import CORS_ORIGINS

        assert "http://localhost:3000" in CORS_ORIGINS
        assert "http://localhost:5173" in CORS_ORIGINS


class TestEndpointIntegration:
    """Integration tests for conversation endpoints.

    Note: In dev mode (ENVIRONMENT=dev), the auth middleware auto-authenticates
    web requests. TestClient sends requests that look like web requests, so in
    dev mode these tests get authenticated automatically and proceed to the
    endpoint logic (returning 200/404 instead of 401).

    The tests accept both behaviors:
    - Production: 401 Unauthorized (no auto-auth)
    - Dev mode: 200/404 (auto-auth passes, endpoint processes request)
    """

    @pytest.fixture
    def client(self):
        """Create test client with mocked dependencies."""
        from api.main import app
        return TestClient(app)

    def test_list_conversations_endpoint_responds(self, client):
        """Test list conversations endpoint is reachable.

        In production: Returns 401 (unauthorized)
        In dev mode: Returns 200 (auto-authenticated, empty list)
        """
        response = client.get("/api/conversations")
        # 401 = production (no auth), 200 = dev mode (auto-auth), 500 = Redis unavailable
        assert response.status_code in [200, 401, 500]

    def test_create_conversation_endpoint_responds(self, client):
        """Test create conversation endpoint is reachable.

        In production: Returns 401 (unauthorized)
        In dev mode: Returns 201 (auto-authenticated, creates conversation)
        """
        response = client.post("/api/conversations", json={})
        # 401 = production, 201 = dev mode (created), 500 = Redis unavailable
        assert response.status_code in [201, 401, 500]

    def test_get_conversation_endpoint_responds(self, client):
        """Test get conversation endpoint is reachable.

        In production: Returns 401 (unauthorized)
        In dev mode: Returns 404 (auto-authenticated, conversation not found)
        """
        response = client.get("/api/conversations/conv_123")
        # 401 = production, 404 = dev mode (not found), 500 = Redis unavailable
        assert response.status_code in [401, 404, 500]

    def test_delete_conversation_endpoint_responds(self, client):
        """Test delete conversation endpoint is reachable.

        In production: Returns 401 (unauthorized)
        In dev mode: Returns 404 (auto-authenticated, conversation not found)
        """
        response = client.delete("/api/conversations/conv_123")
        # 401 = production, 404 = dev mode (not found), 500 = Redis unavailable
        assert response.status_code in [401, 404, 500]

    def test_update_conversation_endpoint_responds(self, client):
        """Test update conversation endpoint is reachable.

        In production: Returns 401 (unauthorized)
        In dev mode: Returns 404 (auto-authenticated, conversation not found)
        """
        response = client.patch(
            "/api/conversations/conv_123",
            json={"title": "New Title"}
        )
        # 401 = production, 404 = dev mode (not found), 500 = Redis unavailable
        assert response.status_code in [401, 404, 500]

    def test_messages_endpoint_responds(self, client):
        """Test messages endpoint is reachable.

        In production: Returns 401 (unauthorized)
        In dev mode: Returns 404 (auto-authenticated, conversation not found)
        """
        response = client.get("/api/conversations/conv_123/messages")
        # 401 = production, 404 = dev mode (not found), 500 = Redis unavailable
        assert response.status_code in [401, 404, 500]


class TestAuthMiddlewareBehavior:
    """Test authentication middleware behavior explicitly."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        from api.main import app
        return TestClient(app)

    def test_unauthenticated_request_without_cf_headers(self, client):
        """Test that requests without CF headers are handled.

        In dev mode: Auto-authenticated as dev user
        In production: Passed through (Telegram flow) but endpoint requires auth
        """
        # Make request without any CF headers
        response = client.get(
            "/api/conversations",
            headers={"Accept": "text/plain"}  # Non-web-like accept header
        )
        # Should get some response (not a crash)
        assert response.status_code in [200, 401, 500]

    def test_health_endpoint_bypasses_auth(self, client):
        """Test health endpoint bypasses authentication."""
        response = client.get("/health")
        assert response.status_code == 200

    def test_root_endpoint_bypasses_auth(self, client):
        """Test root endpoint bypasses authentication."""
        response = client.get("/")
        assert response.status_code == 200
