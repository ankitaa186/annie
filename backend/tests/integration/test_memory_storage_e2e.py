"""
Integration tests for end-to-end memory storage flow

Tests the complete flow: chat request → farewell detection → memory storage
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, Mock, patch

from api.routes.chat import ChatRequest, create_chat, is_conversation_ending
from api.memory import MemoryManager
from api.state import StateManager
from fastapi import BackgroundTasks


class TestFarewellDetection:
    """Test conversation ending detection."""

    def test_is_conversation_ending_exact_match(self):
        """Test farewell detection with exact keyword match."""
        assert is_conversation_ending("thanks") is True
        assert is_conversation_ending("bye") is True
        assert is_conversation_ending("goodbye") is True
        assert is_conversation_ending("thank you") is True

    def test_is_conversation_ending_with_punctuation(self):
        """Test farewell detection with punctuation."""
        assert is_conversation_ending("thanks!") is True
        assert is_conversation_ending("bye!") is True
        assert is_conversation_ending("goodbye!") is True

    def test_is_conversation_ending_at_end_of_message(self):
        """Test farewell detection when keyword is at end."""
        assert is_conversation_ending("Okay, thanks") is True
        assert is_conversation_ending("Got it, bye") is True
        assert is_conversation_ending("That's all, thanks!") is True

    def test_is_conversation_ending_case_insensitive(self):
        """Test farewell detection is case insensitive."""
        assert is_conversation_ending("THANKS") is True
        assert is_conversation_ending("Thanks") is True
        assert is_conversation_ending("BYE") is True

    def test_is_conversation_ending_false_for_non_farewell(self):
        """Test non-farewell messages return False."""
        assert is_conversation_ending("Hello") is False
        assert is_conversation_ending("What should I invest in?") is False
        assert is_conversation_ending("thankful") is False  # Substring doesn't count
        assert is_conversation_ending("I'm thinking about buying stocks") is False


class TestMemoryStorageE2E:
    """Test end-to-end memory storage integration."""

    @pytest.mark.asyncio
    async def test_chat_with_farewell_triggers_memory_storage(self):
        """Test that farewell message triggers background memory storage."""
        # Create chat request with farewell
        chat_request = ChatRequest(
            user_id="test_user_123",
            platform="telegram",
            message="Thanks!",  # Simple farewell that matches keyword
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

            # Call chat endpoint
            response = await create_chat(chat_request, background_tasks)

            # Verify background task was added
            assert task_added is True
            assert response.conversation_id == "conv_test123"
            assert response.status == "streaming"

    @pytest.mark.asyncio
    async def test_chat_without_farewell_no_memory_storage(self):
        """Test that regular message does not trigger memory storage."""
        # Create chat request without farewell
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

            # Call chat endpoint
            response = await create_chat(chat_request, background_tasks)

            # Verify no background task was added
            assert task_added is False
            assert response.conversation_id == "conv_test123"
            assert response.status == "streaming"

    @pytest.mark.asyncio
    async def test_background_memory_storage_success(self):
        """Test background memory storage task executes successfully."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"

        # Mock conversation history
        mock_conversation = [
            {"role": "user", "content": "I want to invest"},
            {"role": "assistant", "content": "What's your risk tolerance?"},
            {"role": "user", "content": "Moderate"},
            {"role": "assistant", "content": "I recommend index funds"},
            {"role": "user", "content": "Thanks!"}
        ]

        # Mock StateManager
        with patch('api.routes.chat.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.get_conversation_history = AsyncMock(return_value=mock_conversation)
            mock_state_class.return_value = mock_state

            # Mock MemoryManager
            with patch('api.routes.chat.MemoryManager') as mock_memory_class:
                mock_memory = Mock()
                mock_memory.store_conversation_memory = AsyncMock(return_value=True)
                mock_memory_class.return_value = mock_memory

                # Execute background task
                await store_conversation_memory_background(user_id, conversation_id)

                # Verify memory was stored
                mock_memory.store_conversation_memory.assert_called_once_with(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    conversation_history=mock_conversation,
                    platform="telegram"
                )

    @pytest.mark.asyncio
    async def test_background_memory_storage_skips_short_conversation(self):
        """Test background storage skips conversations that are too short."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"

        # Mock very short conversation (less than 2 messages)
        mock_conversation = [
            {"role": "user", "content": "Hi"}
        ]

        # Mock StateManager
        with patch('api.routes.chat.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.get_conversation_history = AsyncMock(return_value=mock_conversation)
            mock_state_class.return_value = mock_state

            # Mock MemoryManager
            with patch('api.routes.chat.MemoryManager') as mock_memory_class:
                mock_memory = Mock()
                mock_memory.store_conversation_memory = AsyncMock()
                mock_memory_class.return_value = mock_memory

                # Execute background task
                await store_conversation_memory_background(user_id, conversation_id)

                # Verify memory was NOT stored (conversation too short)
                mock_memory.store_conversation_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_background_memory_storage_handles_errors_gracefully(self):
        """Test background storage handles errors without crashing."""
        from api.routes.chat import store_conversation_memory_background

        user_id = "test_user_123"
        conversation_id = "conv_test123"

        # Mock StateManager that raises error
        with patch('api.routes.chat.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.get_conversation_history = AsyncMock(side_effect=Exception("Redis error"))
            mock_state_class.return_value = mock_state

            # Should not raise exception
            await store_conversation_memory_background(user_id, conversation_id)


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
    """Test retry worker for queued memories."""

    @pytest.mark.asyncio
    async def test_retry_worker_processes_queue(self):
        """Test retry worker processes queued memories."""
        memory_manager = MemoryManager()

        conversation_history = [
            {"role": "user", "content": "Test message 1"},
            {"role": "assistant", "content": "Test response 1"}
        ]

        queue_payload = {
            "user_id": "user123",
            "conversation_id": "conv_abc",
            "history": conversation_history,
            "platform": "telegram",
            "queued_at": "2025-11-11T10:00:00Z"
        }

        queue_key = b"memory_queue:user123"
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
                mock_client.store_memory = AsyncMock(return_value={"memories_created": 2})
                mock_client_class.return_value = mock_client

                # Run retry worker
                await memory_manager.retry_queued_memories()

                # Verify memory was stored
                mock_client.store_memory.assert_called_once()
                call_args = mock_client.store_memory.call_args
                assert call_args[0][0] == "user123"
                assert call_args[0][1] == conversation_history

    @pytest.mark.asyncio
    async def test_retry_worker_requeues_on_failure(self):
        """Test retry worker requeues memories that fail."""
        from api.memory_client import MemoryNetworkError

        memory_manager = MemoryManager()

        conversation_history = [
            {"role": "user", "content": "Test message 1"},
            {"role": "assistant", "content": "Test response 1"}
        ]

        queue_payload = {
            "user_id": "user123",
            "conversation_id": "conv_abc",
            "history": conversation_history,
            "platform": "telegram",
            "queued_at": "2025-11-11T10:00:00Z"
        }

        queue_key = b"memory_queue:user123"
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
                mock_client.store_memory = AsyncMock(side_effect=MemoryNetworkError("Connection failed"))
                mock_client_class.return_value = mock_client

                # Run retry worker
                await memory_manager.retry_queued_memories()

                # Verify memory was re-queued
                mock_state.redis_client.rpush.assert_called_once_with(queue_key, queue_json.encode())
