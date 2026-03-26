"""
Unit tests for MemoryManager
"""

import json
import pytest
import time
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from api.memory import MemoryManager
from api.memory_client import MemoryNetworkError, MemoryAPIError


@pytest.fixture
def memory_manager():
    """Create MemoryManager instance for testing."""
    return MemoryManager()


@pytest.fixture
def sample_conversation():
    """Sample conversation history for testing."""
    return [
        {"role": "user", "content": "I want to invest in stocks", "timestamp": "2025-11-11T10:00:00Z"},
        {"role": "assistant", "content": "What's your risk tolerance?", "timestamp": "2025-11-11T10:00:05Z"},
        {"role": "user", "content": "I'm moderate, looking for long-term growth", "timestamp": "2025-11-11T10:00:15Z"},
        {"role": "assistant", "content": "I recommend diversified index funds", "timestamp": "2025-11-11T10:00:20Z"},
        {"role": "user", "content": "Sounds good, I'll buy VTSAX", "timestamp": "2025-11-11T10:00:30Z"}
    ]


@pytest.fixture
def sample_memory_data():
    """Sample memory data structure."""
    return {
        "conversation_summary": "User wants to invest in stocks with moderate risk tolerance",
        "decisions": [
            {
                "decision": "Buy VTSAX index fund",
                "options_considered": ["VTSAX", "Individual stocks", "Bonds"],
                "reasoning": "Long-term growth with diversification",
                "outcome": None
            }
        ],
        "preferences": {
            "risk_tolerance": "moderate",
            "priorities": ["long-term growth", "diversification"],
            "constraints": []
        },
        "topics": ["stock_investing", "index_funds", "VTSAX"],
        "sentiment": "positive"
    }


class TestMemoryManagerInit:
    """Test MemoryManager initialization."""

    def test_init(self, memory_manager):
        """Test initialization."""
        assert memory_manager.config is not None
        assert memory_manager._circuit_breaker_failures == 0
        assert memory_manager._circuit_breaker_opened_at is None


class TestCircuitBreaker:
    """Test circuit breaker logic."""

    def test_circuit_breaker_closed_initially(self, memory_manager):
        """Test circuit breaker is closed initially."""
        assert memory_manager._is_circuit_breaker_open() is False

    def test_circuit_breaker_opens_when_set(self, memory_manager):
        """Test circuit breaker opens when failures exceed threshold."""
        memory_manager._circuit_breaker_failures = 5
        memory_manager._circuit_breaker_opened_at = time.time()

        assert memory_manager._is_circuit_breaker_open() is True

    def test_circuit_breaker_closes_after_timeout(self, memory_manager):
        """Test circuit breaker closes after timeout expires."""
        # Open circuit breaker in the past (beyond timeout)
        memory_manager._circuit_breaker_failures = 5
        memory_manager._circuit_breaker_opened_at = time.time() - 1000  # 1000 seconds ago

        assert memory_manager._is_circuit_breaker_open() is False
        # Should reset failures
        assert memory_manager._circuit_breaker_failures == 0
        assert memory_manager._circuit_breaker_opened_at is None


class TestQueueMemoryForRetry:
    """Test Redis queue for retry."""

    @pytest.mark.asyncio
    async def test_queue_memory_for_retry(self, memory_manager, sample_conversation):
        """Test queueing memory for retry."""
        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()
            mock_state.redis_client.rpush = AsyncMock()
            mock_state.redis_client.expire = AsyncMock()
            mock_state_class.return_value = mock_state

            await memory_manager._queue_memory_for_retry(
                "user123",
                "conv_abc",
                sample_conversation,
                "telegram"
            )

            # Verify Redis operations
            mock_state.redis_client.rpush.assert_called_once()
            mock_state.redis_client.expire.assert_called_once()

            # Check queue key
            rpush_call = mock_state.redis_client.rpush.call_args
            assert rpush_call[0][0] == "memory_queue:user123"

    @pytest.mark.asyncio
    async def test_queue_memory_for_retry_handles_error(self, memory_manager, sample_conversation):
        """Test queueing handles Redis errors gracefully."""
        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()
            mock_state.redis_client.rpush = AsyncMock(side_effect=Exception("Redis error"))
            mock_state_class.return_value = mock_state

            # Should not raise exception
            await memory_manager._queue_memory_for_retry(
                "user123",
                "conv_abc",
                sample_conversation,
                "telegram"
            )


class TestRetryQueuedMemories:
    """Test retry worker for queued messages."""

    @pytest.mark.asyncio
    async def test_retry_queued_memories_empty_queue(self, memory_manager):
        """Test retry worker with empty queue."""
        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()
            # Return empty scan result
            mock_state.redis_client.scan = AsyncMock(return_value=(0, []))
            mock_state_class.return_value = mock_state

            # Should complete without error
            await memory_manager.retry_queued_memories()

    @pytest.mark.asyncio
    async def test_retry_queued_memories_success(self, memory_manager):
        """Test retry worker successfully processes queue."""
        queue_key = b"message_queue:user123"
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
        queue_json = json.dumps(queue_payload)

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

            with patch('api.memory.MemoryClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.stream_message = AsyncMock(return_value={"injections": []})
                mock_client_class.return_value = mock_client

                await memory_manager.retry_queued_memories()

                # Verify message was popped and streamed
                mock_state.redis_client.lpop.assert_called_once_with(queue_key)
                mock_client.stream_message.assert_called_once_with(
                    conversation_id="conv_abc",
                    role="user",
                    content="Test message",
                    user_id="user123",
                    message_id=None,
                    flush=False,
                )

    @pytest.mark.asyncio
    async def test_retry_queued_memories_requeues_on_failure(self, memory_manager):
        """Test retry worker requeues on failure."""
        queue_key = b"message_queue:user123"
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
        queue_json = json.dumps(queue_payload)

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

            with patch('api.memory.MemoryClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.stream_message = AsyncMock(side_effect=MemoryNetworkError("Failed"))
                mock_client_class.return_value = mock_client

                await memory_manager.retry_queued_memories()

                # Verify message was re-queued
                mock_state.redis_client.rpush.assert_called_once()


class TestFormatMemoriesForLLM:
    """Test format_memories_for_llm method."""

    @pytest.mark.asyncio
    async def test_format_memories_success(self, memory_manager):
        """Test formatting memories for LLM with full data."""
        memories = [
            {
                "memory_id": "mem_1",
                "conversation_summary": "User asked for stock investment advice for AAPL",
                "decisions": [
                    {
                        "decision": "Buy 10 shares of AAPL",
                        "outcome": "Gained 15% in 2 weeks",
                        "reasoning": "Strong fundamentals and positive trend"
                    }
                ],
                "preferences": {
                    "risk_tolerance": "moderate",
                    "priorities": ["long-term growth", "dividend income"],
                    "constraints": ["max 20% tech exposure"]
                },
                "topics": ["stock_trading", "AAPL"],
                "relevance_score": 0.95,
                "timestamp": "2025-11-10T10:00:00Z"
            },
            {
                "memory_id": "mem_2",
                "conversation_summary": "Discussed career change options",
                "decisions": [],
                "preferences": {},
                "topics": ["career"],
                "relevance_score": 0.75,
                "timestamp": "2025-11-09T15:30:00Z"
            }
        ]

        result = await memory_manager.format_memories_for_llm(memories)

        # Verify formatted output structure
        assert isinstance(result, str)
        assert "Here is the user's past decision history" in result
        assert "User asked for stock investment advice for AAPL" in result
        assert "Buy 10 shares of AAPL" in result
        assert "Gained 15% in 2 weeks" in result
        assert "Strong fundamentals and positive trend" in result
        assert "Risk tolerance: moderate" in result
        assert "Priorities: long-term growth, dividend income" in result
        assert "Constraints: max 20% tech exposure" in result
        assert "Tags: stock_trading, AAPL" in result
        assert "Relevance: 95%" in result
        assert "2025-11-10" in result
        assert "Use this history to personalize your recommendations" in result

    @pytest.mark.asyncio
    async def test_format_memories_empty_list(self, memory_manager):
        """Test formatting empty memory list."""
        result = await memory_manager.format_memories_for_llm([])

        assert result == "No past decision history available for this user."

    @pytest.mark.asyncio
    async def test_format_memories_minimal_data(self, memory_manager):
        """Test formatting memories with minimal data."""
        memories = [
            {
                "conversation_summary": "Basic conversation",
                "decisions": [],
                "preferences": {},
                "topics": [],
                "timestamp": "2025-11-10T10:00:00Z"
            }
        ]

        result = await memory_manager.format_memories_for_llm(memories)

        assert "Basic conversation" in result
        assert "No past decision history available" not in result

    @pytest.mark.asyncio
    async def test_format_memories_string_decisions(self, memory_manager):
        """Test formatting memories with string decisions (not dicts)."""
        memories = [
            {
                "conversation_summary": "Simple decision",
                "decisions": ["Buy stocks", "Diversify portfolio"],
                "preferences": {},
                "topics": [],
                "timestamp": "2025-11-10T10:00:00Z"
            }
        ]

        result = await memory_manager.format_memories_for_llm(memories)

        assert "Buy stocks" in result
        assert "Diversify portfolio" in result

    @pytest.mark.asyncio
    async def test_format_memories_no_summary(self, memory_manager):
        """Test formatting memories without conversation_summary."""
        memories = [
            {
                "summary": "Alternative summary field",
                "decisions": [],
                "preferences": {},
                "topics": [],
                "timestamp": "2025-11-10T10:00:00Z"
            }
        ]

        result = await memory_manager.format_memories_for_llm(memories)

        assert "Alternative summary field" in result

    @pytest.mark.asyncio
    async def test_format_memories_with_all_fields(self, memory_manager):
        """Test formatting with all possible fields populated."""
        memories = [
            {
                "memory_id": "mem_full",
                "conversation_summary": "Complete memory object",
                "decisions": [
                    {
                        "decision": "Make decision A",
                        "options_considered": ["A", "B", "C"],
                        "reasoning": "Best option based on criteria",
                        "outcome": "Successful outcome"
                    }
                ],
                "preferences": {
                    "risk_tolerance": "high",
                    "priorities": ["growth", "innovation"],
                    "constraints": ["budget limit", "time limit"]
                },
                "topics": ["topic1", "topic2", "topic3"],
                "sentiment": "positive",
                "relevance_score": 0.99,
                "timestamp": "2025-11-10T14:30:45Z"
            }
        ]

        result = await memory_manager.format_memories_for_llm(memories)

        # Verify all fields are present
        assert "Complete memory object" in result
        assert "Make decision A" in result
        assert "Best option based on criteria" in result
        assert "Successful outcome" in result
        assert "Risk tolerance: high" in result
        assert "Priorities: growth, innovation" in result
        assert "Constraints: budget limit, time limit" in result
        assert "Tags: topic1, topic2, topic3" in result
        assert "Relevance: 99%" in result
        assert "2025-11-10" in result


class TestStreamConversationMessage:
    """Test stream_conversation_message method for orchestrator integration."""

    @pytest.mark.asyncio
    async def test_stream_conversation_message_success(self, memory_manager):
        """Test successful message streaming through orchestrator."""
        mock_injections = [
            {
                "memory_id": "mem_abc",
                "content": "User prefers tech stocks",
                "source": "LONG_TERM",
                "channel": "INLINE",
                "score": 0.85,
                "metadata": {}
            }
        ]

        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(return_value={"injections": mock_injections})
            mock_client_class.return_value = mock_client

            result = await memory_manager.stream_conversation_message(
                user_id="user_123",
                conversation_id="conv_456",
                role="user",
                content="What stocks should I buy?"
            )

            # Verify result
            assert result is not None
            assert len(result) == 1
            assert result[0]["memory_id"] == "mem_abc"
            assert result[0]["score"] == 0.85

            # Verify stream_message was called correctly
            mock_client.stream_message.assert_called_once_with(
                conversation_id="conv_456",
                role="user",
                content="What stocks should I buy?",
                user_id="user_123",
                message_id=None,
                flush=False,
            )

    @pytest.mark.asyncio
    async def test_stream_conversation_message_with_flush(self, memory_manager):
        """Test message streaming with flush=True."""
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(return_value={"injections": []})
            mock_client_class.return_value = mock_client

            await memory_manager.stream_conversation_message(
                user_id="user_123",
                conversation_id="conv_456",
                role="assistant",
                content="Here is my response",
                flush=True
            )

            # Verify flush parameter was passed
            call_args = mock_client.stream_message.call_args
            assert call_args[1]["flush"] is True

    @pytest.mark.asyncio
    async def test_stream_conversation_message_empty_injections(self, memory_manager):
        """Test message streaming with no injections returned."""
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(return_value={"injections": []})
            mock_client_class.return_value = mock_client

            result = await memory_manager.stream_conversation_message(
                user_id="user_123",
                conversation_id="conv_456",
                role="user",
                content="Hello"
            )

            assert result == []

    @pytest.mark.asyncio
    async def test_stream_conversation_message_network_error_queues_for_retry(self, memory_manager):
        """Test message streaming queues for retry on network error."""
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(
                side_effect=MemoryNetworkError("Connection refused")
            )
            mock_client_class.return_value = mock_client

            with patch.object(memory_manager, '_queue_message_for_retry', new_callable=AsyncMock) as mock_queue:
                result = await memory_manager.stream_conversation_message(
                    user_id="user_123",
                    conversation_id="conv_456",
                    role="user",
                    content="Test"
                )

                # Should return None instead of raising
                assert result is None
                # Circuit breaker should increment
                assert memory_manager._circuit_breaker_failures == 1
                # Should queue for retry
                mock_queue.assert_called_once_with(
                    user_id="user_123",
                    conversation_id="conv_456",
                    role="user",
                    content="Test",
                    message_id=None,
                    flush=False
                )

    @pytest.mark.asyncio
    async def test_stream_conversation_message_api_error_queues_for_retry(self, memory_manager):
        """Test message streaming queues for retry on API error."""
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(
                side_effect=MemoryAPIError("Internal server error", status_code=500)
            )
            mock_client_class.return_value = mock_client

            with patch.object(memory_manager, '_queue_message_for_retry', new_callable=AsyncMock) as mock_queue:
                result = await memory_manager.stream_conversation_message(
                    user_id="user_123",
                    conversation_id="conv_456",
                    role="user",
                    content="Test"
                )

                # Should return None instead of raising
                assert result is None
                # Should queue for retry
                mock_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_conversation_message_circuit_breaker_open_queues(self, memory_manager):
        """Test message streaming queues when circuit breaker is open."""
        # Open circuit breaker
        memory_manager._circuit_breaker_failures = 5
        memory_manager._circuit_breaker_opened_at = time.time()

        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value = mock_client

            with patch.object(memory_manager, '_queue_message_for_retry', new_callable=AsyncMock) as mock_queue:
                result = await memory_manager.stream_conversation_message(
                    user_id="user_123",
                    conversation_id="conv_456",
                    role="user",
                    content="Test"
                )

                # Should return None immediately
                assert result is None
                # MemoryClient should not have been instantiated
                mock_client_class.assert_not_called()
                # Should queue for retry
                mock_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_stream_conversation_message_resets_circuit_breaker_on_success(self, memory_manager):
        """Test successful streaming resets circuit breaker."""
        # Set some failures
        memory_manager._circuit_breaker_failures = 3

        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(return_value={"injections": []})
            mock_client_class.return_value = mock_client

            await memory_manager.stream_conversation_message(
                user_id="user_123",
                conversation_id="conv_456",
                role="user",
                content="Test"
            )

            # Circuit breaker should be reset
            assert memory_manager._circuit_breaker_failures == 0
            assert memory_manager._circuit_breaker_opened_at is None

    @pytest.mark.asyncio
    async def test_stream_conversation_message_opens_circuit_breaker_after_threshold(self, memory_manager):
        """Test circuit breaker opens after threshold failures."""
        with patch('api.memory.MemoryClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.stream_message = AsyncMock(
                side_effect=MemoryNetworkError("Connection refused")
            )
            mock_client_class.return_value = mock_client

            with patch.object(memory_manager, '_queue_message_for_retry', new_callable=AsyncMock):
                # Make 5 failing calls (threshold)
                for i in range(5):
                    await memory_manager.stream_conversation_message(
                        user_id="user_123",
                        conversation_id="conv_456",
                        role="user",
                        content=f"Test {i}"
                    )

                # Circuit breaker should be open
                assert memory_manager._circuit_breaker_failures == 5
                assert memory_manager._circuit_breaker_opened_at is not None
                assert memory_manager._is_circuit_breaker_open() is True


class TestFlushStaleSessions:
    """Test flush_stale_sessions method for Story 12-5."""

    @pytest.mark.asyncio
    async def test_flush_stale_sessions_empty(self, memory_manager):
        """Test flush worker with no sessions."""
        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()
            # Return empty scan result
            mock_state.redis_client.scan = AsyncMock(return_value=(0, []))
            mock_state_class.return_value = mock_state

            # Should complete without error
            await memory_manager.flush_stale_sessions()

    @pytest.mark.asyncio
    async def test_flush_stale_sessions_flushes_inactive(self, memory_manager):
        """Test flush worker flushes sessions inactive > 10 minutes."""
        # Create a stale session (15 minutes old)
        datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        # Simulate 15 minutes ago by manipulating the session data
        from datetime import timedelta
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")

        session_data = {
            "user_id": "user_123",
            "conversation_id": "conv_456",
            "platform": "telegram",
            "created_at": stale_time,
            "last_activity": stale_time,
            "message_count": 1
        }

        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            # Mock scan to return one session
            mock_state.redis_client.scan = AsyncMock(return_value=(0, [b"session:user_123"]))
            mock_state.redis_client.get = AsyncMock(return_value=json.dumps(session_data))
            mock_state.redis_client.exists = AsyncMock(return_value=False)  # Not already flushed
            mock_state.redis_client.setex = AsyncMock()
            mock_state_class.return_value = mock_state

            with patch.object(memory_manager, 'stream_conversation_message', new_callable=AsyncMock) as mock_stream:
                mock_stream.return_value = []

                await memory_manager.flush_stale_sessions()

                # Verify flush was called with flush=True
                mock_stream.assert_called_once_with(
                    user_id="user_123",
                    conversation_id="conv_456",
                    role="system",
                    content="",
                    flush=True
                )

                # Verify flush marker was set
                mock_state.redis_client.setex.assert_called_once()
                call_args = mock_state.redis_client.setex.call_args
                assert call_args[0][0] == "flushed:conv_456"
                assert call_args[0][1] == memory_manager.FLUSH_MARKER_TTL

    @pytest.mark.asyncio
    async def test_flush_stale_sessions_skips_recently_active(self, memory_manager):
        """Test flush worker skips sessions active within 10 minutes."""
        # Create a recent session (2 minutes old)
        from datetime import timedelta
        recent_time = (datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")

        session_data = {
            "user_id": "user_123",
            "conversation_id": "conv_456",
            "platform": "telegram",
            "created_at": recent_time,
            "last_activity": recent_time,
            "message_count": 1
        }

        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            # Mock scan to return one session
            mock_state.redis_client.scan = AsyncMock(return_value=(0, [b"session:user_123"]))
            mock_state.redis_client.get = AsyncMock(return_value=json.dumps(session_data))
            mock_state.redis_client.exists = AsyncMock(return_value=False)
            mock_state_class.return_value = mock_state

            with patch.object(memory_manager, 'stream_conversation_message', new_callable=AsyncMock) as mock_stream:
                await memory_manager.flush_stale_sessions()

                # Flush should NOT have been called
                mock_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_stale_sessions_skips_already_flushed(self, memory_manager):
        """Test flush worker skips sessions already flushed."""
        from datetime import timedelta
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")

        session_data = {
            "user_id": "user_123",
            "conversation_id": "conv_456",
            "platform": "telegram",
            "created_at": stale_time,
            "last_activity": stale_time,
            "message_count": 1
        }

        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            # Mock scan to return one session
            mock_state.redis_client.scan = AsyncMock(return_value=(0, [b"session:user_123"]))
            mock_state.redis_client.get = AsyncMock(return_value=json.dumps(session_data))
            mock_state.redis_client.exists = AsyncMock(return_value=True)  # Already flushed!
            mock_state_class.return_value = mock_state

            with patch.object(memory_manager, 'stream_conversation_message', new_callable=AsyncMock) as mock_stream:
                await memory_manager.flush_stale_sessions()

                # Flush should NOT have been called
                mock_stream.assert_not_called()

    @pytest.mark.asyncio
    async def test_flush_stale_sessions_graceful_degradation(self, memory_manager):
        """Test flush worker continues on individual session failures."""
        from datetime import timedelta
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")

        session_data = {
            "user_id": "user_123",
            "conversation_id": "conv_456",
            "platform": "telegram",
            "created_at": stale_time,
            "last_activity": stale_time,
            "message_count": 1
        }

        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            mock_state.redis_client.scan = AsyncMock(return_value=(0, [b"session:user_123"]))
            mock_state.redis_client.get = AsyncMock(return_value=json.dumps(session_data))
            mock_state.redis_client.exists = AsyncMock(return_value=False)
            mock_state_class.return_value = mock_state

            with patch.object(memory_manager, 'stream_conversation_message', new_callable=AsyncMock) as mock_stream:
                # Simulate orchestrator failure
                mock_stream.side_effect = Exception("Orchestrator unavailable")

                # Should not raise
                await memory_manager.flush_stale_sessions()

    @pytest.mark.asyncio
    async def test_flush_stale_sessions_handles_string_keys(self, memory_manager):
        """Test flush worker handles string Redis keys (not just bytes)."""
        from datetime import timedelta
        stale_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat().replace("+00:00", "Z")

        session_data = {
            "user_id": "user_123",
            "conversation_id": "conv_456",
            "platform": "telegram",
            "created_at": stale_time,
            "last_activity": stale_time,
            "message_count": 1
        }

        with patch('api.memory.StateManager') as mock_state_class:
            mock_state = AsyncMock()
            mock_state.__aenter__.return_value = mock_state
            mock_state.__aexit__.return_value = None
            mock_state.redis_client = AsyncMock()

            # Return string key (not bytes) - can happen with decode_responses=True
            mock_state.redis_client.scan = AsyncMock(return_value=(0, ["session:user_123"]))
            mock_state.redis_client.get = AsyncMock(return_value=json.dumps(session_data))
            mock_state.redis_client.exists = AsyncMock(return_value=False)
            mock_state.redis_client.setex = AsyncMock()
            mock_state_class.return_value = mock_state

            with patch.object(memory_manager, 'stream_conversation_message', new_callable=AsyncMock) as mock_stream:
                mock_stream.return_value = []

                await memory_manager.flush_stale_sessions()

                # Should still work correctly
                mock_stream.assert_called_once()


class TestFlushWorkerConstants:
    """Test flush worker configuration constants."""

    def test_flush_check_interval(self, memory_manager):
        """Test flush check interval is 5 minutes."""
        assert memory_manager.FLUSH_CHECK_INTERVAL == 300

    def test_inactive_threshold(self, memory_manager):
        """Test inactive threshold is 10 minutes."""
        assert memory_manager.INACTIVE_THRESHOLD == 600

    def test_flush_marker_ttl(self, memory_manager):
        """Test flush marker TTL is 1 hour."""
        assert memory_manager.FLUSH_MARKER_TTL == 3600
