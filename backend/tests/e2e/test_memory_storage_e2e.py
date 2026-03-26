"""
Integration tests for end-to-end memory storage flow

Tests the complete flow: chat request → memory storage (fire-and-forget on every message)
"""

import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from api.routes.chat import ChatRequest, create_chat
from api.memory import MemoryManager
from fastapi import BackgroundTasks
from starlette.requests import Request
from starlette.datastructures import Headers


class TestMemoryStorageE2E:
    """Test end-to-end memory storage integration."""

    @pytest.mark.asyncio
    async def test_chat_triggers_memory_storage(self):
        """Test that every message triggers background memory storage (fire-and-forget)."""
        # Create chat request
        chat_request = ChatRequest(
            user_id="test_user_123",
            platform="telegram",
            message="What should I invest in?",
            context={}
        )

        # Mock background tasks
        background_tasks = BackgroundTasks()
        task_added = False
        original_add_task = background_tasks.add_task

        def mock_add_task(*args, **kwargs):
            nonlocal task_added
            task_added = True
            return original_add_task(*args, **kwargs)

        background_tasks.add_task = mock_add_task

        # Mock StateManager
        with patch('api.routes.chat.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None

            # Mock session and conversation
            mock_state.get_session = AsyncMock(return_value={
                "user_id": "test_user_123",
                "conversation_id": "conv_test123",
                "platform": "telegram"
            })
            mock_state.update_session_activity = AsyncMock()
            mock_state.add_message = AsyncMock()
            mock_state_class.return_value = mock_state

            # Create mock HTTP request
            mock_http_request = Mock(spec=Request)
            mock_http_request.client = Mock()
            mock_http_request.client.host = "127.0.0.1"
            mock_http_request.headers = Headers({})
            mock_http_request.state = Mock()
            mock_http_request.state.user_id = None  # No auth override

            # Call chat endpoint
            response = await create_chat(chat_request, background_tasks, mock_http_request)

            # Verify background task was added (memory storage on every message)
            assert task_added is True
            assert response.conversation_id == "conv_test123"
            assert response.status == "streaming"

    @pytest.mark.asyncio
    async def test_background_memory_storage_success(self):
        """Test background memory storage task streams message to orchestrator successfully."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"
        message_content = "What should I invest in?"
        role = "user"

        # Mock MemoryManager
        with patch('api.routes.chat.MemoryManager') as mock_memory_class:
            mock_memory = Mock()
            mock_memory.stream_conversation_message = AsyncMock(return_value=[])
            mock_memory_class.return_value = mock_memory

            # Execute background task
            await store_conversation_memory_background(
                user_id, conversation_id, message_content, role
            )

            # Verify stream_conversation_message was called
            mock_memory.stream_conversation_message.assert_called_once_with(
                user_id=user_id,
                conversation_id=conversation_id,
                role=role,
                content=message_content
            )

    @pytest.mark.asyncio
    async def test_background_memory_storage_with_injections(self):
        """Test background storage returns injections from orchestrator."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"
        message_content = "Should I invest in tech stocks?"
        role = "user"

        mock_injections = [
            {"memory_id": "mem_1", "content": "User prefers tech", "score": 0.9}
        ]

        # Mock MemoryManager
        with patch('api.routes.chat.MemoryManager') as mock_memory_class:
            mock_memory = Mock()
            mock_memory.stream_conversation_message = AsyncMock(return_value=mock_injections)
            mock_memory_class.return_value = mock_memory

            # Execute background task (should not raise, even though we don't use injections)
            await store_conversation_memory_background(
                user_id, conversation_id, message_content, role
            )

            # Verify stream was called
            mock_memory.stream_conversation_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_background_memory_storage_handles_errors_gracefully(self):
        """Test background storage handles errors without crashing."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"
        message_content = "Test message"
        role = "user"

        # Mock MemoryManager that raises error
        with patch('api.routes.chat.MemoryManager') as mock_memory_class:
            mock_memory = Mock()
            mock_memory.stream_conversation_message = AsyncMock(
                side_effect=Exception("Unexpected error")
            )
            mock_memory_class.return_value = mock_memory

            # Should not raise exception (fire-and-forget pattern)
            await store_conversation_memory_background(
                user_id, conversation_id, message_content, role
            )

    @pytest.mark.asyncio
    async def test_background_memory_storage_graceful_degradation(self):
        """Test background storage continues when orchestrator returns None."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"
        message_content = "Test message"
        role = "user"

        # Mock MemoryManager returning None (circuit breaker open or error)
        with patch('api.routes.chat.MemoryManager') as mock_memory_class:
            mock_memory = Mock()
            mock_memory.stream_conversation_message = AsyncMock(return_value=None)
            mock_memory_class.return_value = mock_memory

            # Should not raise exception
            await store_conversation_memory_background(
                user_id, conversation_id, message_content, role
            )


class TestMemoryStorageWithFallback:
    """Test memory storage with Redis fallback and retry."""

    @pytest.mark.asyncio
    async def test_memory_storage_fallback_on_network_error(self):
        """Test memory storage queues to Redis on network error."""
        from api.memory_client import MemoryNetworkError

        memory_manager = MemoryManager()

        conversation_history = [
            {"role": "user", "content": "Test message 1"},
            {"role": "assistant", "content": "Test response 1"}
        ]

        # Mock MemoryClient to fail
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.store_memory = AsyncMock(side_effect=MemoryNetworkError("Connection failed"))
            mock_client_class.return_value = mock_client

            # Mock queue function
            with patch.object(memory_manager, '_queue_memory_for_retry', new_callable=AsyncMock) as mock_queue:
                result = await memory_manager.store_conversation_memory(
                    "user123",
                    "conv_abc",
                    conversation_history,
                    "telegram"
                )

                # Verify result is False (queued)
                assert result is False

                # Verify memory was queued
                mock_queue.assert_called_once()
                queue_call_args = mock_queue.call_args
                assert queue_call_args[0][0] == "user123"
                assert queue_call_args[0][1] == "conv_abc"
                assert queue_call_args[0][2] == conversation_history
                assert queue_call_args[0][3] == "telegram"

    @pytest.mark.asyncio
    async def test_circuit_breaker_prevents_repeated_failures(self):
        """Test circuit breaker opens after repeated failures."""
        from api.memory_client import MemoryNetworkError

        memory_manager = MemoryManager()

        conversation_history = [
            {"role": "user", "content": "Test message 1"},
            {"role": "assistant", "content": "Test response 1"}
        ]

        # Mock MemoryClient to always fail
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.store_memory = AsyncMock(side_effect=MemoryNetworkError("Connection failed"))
            mock_client_class.return_value = mock_client

            with patch.object(memory_manager, '_queue_memory_for_retry', new_callable=AsyncMock):
                # Fail 5 times (threshold)
                for i in range(5):
                    await memory_manager.store_conversation_memory(
                        "user123",
                        "conv_abc",
                        conversation_history.copy(),
                        "telegram"
                    )

                # Circuit breaker should be open
                assert memory_manager._circuit_breaker_failures == 5
                assert memory_manager._circuit_breaker_opened_at is not None

                # Next attempt should not even try to store
                await memory_manager.store_conversation_memory(
                    "user123",
                    "conv_abc",
                    conversation_history.copy(),
                    "telegram"
                )

                # Store should only have been called 5 times (not 6)
                assert mock_client.store_memory.call_count == 5


class TestMemoryRetryWorker:
    """Test retry worker for queued messages."""

    @pytest.mark.asyncio
    async def test_retry_worker_processes_queue(self):
        """Test retry worker processes queued messages."""
        memory_manager = MemoryManager()

        queue_payload = {
            "type": "orchestrator_message",
            "user_id": "user123",
            "conversation_id": "conv_abc",
            "role": "user",
            "content": "Test message",
            "message_id": None,
            "flush": False,
            "queued_at": "2025-11-11T10:00:00Z"
        }

        queue_key = b"message_queue:user123"
        queue_json = json.dumps(queue_payload)

        # Mock StateManager
        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            # Mock scan to return one queue
            mock_state.redis_client.scan = AsyncMock(return_value=(0, [queue_key]))
            mock_state.redis_client.llen = AsyncMock(return_value=1)
            mock_state.redis_client.lpop = AsyncMock(return_value=queue_json.encode())
            mock_state_class.return_value = mock_state

            # Mock MemoryClient to succeed
            with patch('api.memory.MemoryClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.stream_message = AsyncMock(return_value={"injections": []})
                mock_client_class.return_value = mock_client

                # Run retry worker
                await memory_manager.retry_queued_memories()

                # Verify message was streamed
                mock_client.stream_message.assert_called_once_with(
                    conversation_id="conv_abc",
                    role="user",
                    content="Test message",
                    user_id="user123",
                    message_id=None,
                    flush=False,
                )

    @pytest.mark.asyncio
    async def test_retry_worker_requeues_on_failure(self):
        """Test retry worker requeues messages that fail."""
        from api.memory_client import MemoryNetworkError

        memory_manager = MemoryManager()

        queue_payload = {
            "type": "orchestrator_message",
            "user_id": "user123",
            "conversation_id": "conv_abc",
            "role": "user",
            "content": "Test message",
            "message_id": None,
            "flush": False,
            "queued_at": "2025-11-11T10:00:00Z"
        }

        queue_key = b"message_queue:user123"
        queue_json = json.dumps(queue_payload)

        # Mock StateManager
        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            # Mock scan to return one queue
            mock_state.redis_client.scan = AsyncMock(return_value=(0, [queue_key]))
            mock_state.redis_client.llen = AsyncMock(return_value=1)
            mock_state.redis_client.lpop = AsyncMock(return_value=queue_json.encode())
            mock_state.redis_client.rpush = AsyncMock()
            mock_state_class.return_value = mock_state

            # Mock MemoryClient to fail
            with patch('api.memory.MemoryClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.stream_message = AsyncMock(side_effect=MemoryNetworkError("Connection failed"))
                mock_client_class.return_value = mock_client

                # Run retry worker
                await memory_manager.retry_queued_memories()

                # Verify message was re-queued
                mock_state.redis_client.rpush.assert_called_once()
