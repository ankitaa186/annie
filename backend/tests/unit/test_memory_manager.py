"""
Unit tests for MemoryManager
"""

import json
import pytest
import time
from unittest.mock import AsyncMock, Mock, patch, MagicMock
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
    """Test retry worker for queued memories."""

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
    async def test_retry_queued_memories_success(self, memory_manager, sample_conversation):
        """Test retry worker successfully processes queue."""
        queue_key = b"memory_queue:user123"
        queue_payload = {
            "user_id": "user123",
            "conversation_id": "conv_abc",
            "history": sample_conversation,
            "platform": "telegram",
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
                mock_client.store_memory = AsyncMock(return_value={"memories_created": 2})
                mock_client_class.return_value = mock_client

                await memory_manager.retry_queued_memories()

                # Verify memory was popped and stored
                mock_state.redis_client.lpop.assert_called_once_with(queue_key)
                mock_client.store_memory.assert_called_once()

    @pytest.mark.asyncio
    async def test_retry_queued_memories_requeues_on_failure(self, memory_manager, sample_conversation):
        """Test retry worker requeues on failure."""
        queue_key = b"memory_queue:user123"
        queue_payload = {
            "user_id": "user123",
            "conversation_id": "conv_abc",
            "history": sample_conversation,
            "platform": "telegram",
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
                mock_client.store_memory = AsyncMock(side_effect=MemoryNetworkError("Failed"))
                mock_client_class.return_value = mock_client

                await memory_manager.retry_queued_memories()

                # Verify memory was re-queued
                mock_state.redis_client.rpush.assert_called_once_with(queue_key, queue_json.encode())


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
        assert "Topics: stock_trading, AAPL" in result
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
    async def test_format_memories_token_warning(self, memory_manager):
        """Test that long formatted output logs warning for >2000 tokens."""
        # Create memories that would exceed 2000 tokens (rough est: 8000+ characters)
        long_summary = "A" * 2000
        memories = [
            {
                "conversation_summary": long_summary,
                "decisions": [
                    {"decision": "Decision " + str(i), "reasoning": "Reasoning " * 50}
                    for i in range(10)
                ],
                "preferences": {
                    "risk_tolerance": "moderate",
                    "priorities": ["priority" + str(i) for i in range(20)]
                },
                "topics": ["topic" + str(i) for i in range(20)],
                "timestamp": "2025-11-10T10:00:00Z"
            }
        ]

        with patch('api.memory.logger') as mock_logger:
            result = await memory_manager.format_memories_for_llm(memories)

            # Verify warning was logged for exceeding token limit
            mock_logger.warning.assert_called()
            call_args = str(mock_logger.warning.call_args)
            assert "2000 token" in call_args

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
        assert "Topics: topic1, topic2, topic3" in result
        assert "Relevance: 99%" in result
        assert "2025-11-10" in result
