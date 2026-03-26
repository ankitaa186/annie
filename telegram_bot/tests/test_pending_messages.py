"""
Unit tests for pending message handling (Story 11.6)

Tests the pending message slot feature including:
- Processing flag management
- Pending message storage and retrieval
- Status message updates
- Auto-pickup after completion
- Concurrent request safety

Note: These tests use a mock Redis client for isolation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Import functions to test
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from handlers.message import (
    append_pending_message,
    count_pending_messages,
    get_and_clear_pending,
    handle_pending_messages
)


@pytest.mark.asyncio
async def test_append_pending_message_empty(mock_redis_client):
    """Test appending a message to an empty pending slot."""
    user_id = "12345"
    message = "Hello, Annie!"

    await append_pending_message(mock_redis_client, user_id, message)

    # Verify stored in Redis
    key = f"pending_message:{user_id}"
    stored = await mock_redis_client.get(key)
    assert stored == message

    # Verify TTL is set (should be 300 seconds)
    ttl = await mock_redis_client.ttl(key)
    assert ttl == 300


@pytest.mark.asyncio
async def test_append_pending_message_with_existing(mock_redis_client):
    """Test appending to existing pending messages."""
    user_id = "12345"
    message1 = "First message"
    message2 = "Second message"

    await append_pending_message(mock_redis_client, user_id, message1)
    await append_pending_message(mock_redis_client, user_id, message2)

    # Verify both messages stored with newline separator
    key = f"pending_message:{user_id}"
    stored = await mock_redis_client.get(key)
    assert stored == f"{message1}\n{message2}"


@pytest.mark.asyncio
async def test_append_pending_message_max_size(mock_redis_client):
    """Test that pending messages are truncated at 4000 chars."""
    user_id = "12345"

    # Create a message that will exceed limit when appended
    large_message = "A" * 3000
    another_message = "B" * 2000

    await append_pending_message(mock_redis_client, user_id, large_message)
    await append_pending_message(mock_redis_client, user_id, another_message)

    # Verify total is truncated to 4000 chars
    key = f"pending_message:{user_id}"
    stored = await mock_redis_client.get(key)
    assert len(stored) == 4000
    # Verify it kept the most recent (should end with B's)
    assert stored.endswith("B" * 100)


@pytest.mark.asyncio
async def test_count_pending_messages_empty(mock_redis_client):
    """Test counting with no pending messages."""
    user_id = "12345"

    count = await count_pending_messages(mock_redis_client, user_id)
    assert count == 0


@pytest.mark.asyncio
async def test_count_pending_messages_single(mock_redis_client):
    """Test counting a single pending message."""
    user_id = "12345"
    message = "Test message"

    await append_pending_message(mock_redis_client, user_id, message)
    count = await count_pending_messages(mock_redis_client, user_id)

    assert count == 1


@pytest.mark.asyncio
async def test_count_pending_messages_multiple(mock_redis_client):
    """Test counting multiple pending messages."""
    user_id = "12345"

    await append_pending_message(mock_redis_client, user_id, "Message 1")
    await append_pending_message(mock_redis_client, user_id, "Message 2")
    await append_pending_message(mock_redis_client, user_id, "Message 3")

    count = await count_pending_messages(mock_redis_client, user_id)
    assert count == 3


@pytest.mark.asyncio
async def test_get_and_clear_pending_empty(mock_redis_client):
    """Test get and clear with no pending messages."""
    user_id = "12345"

    pending = await get_and_clear_pending(mock_redis_client, user_id)
    assert pending is None


@pytest.mark.asyncio
async def test_get_and_clear_pending_atomicity(mock_redis_client):
    """Test that get and clear is atomic."""
    user_id = "12345"
    message = "Test message"

    # Store a pending message
    await append_pending_message(mock_redis_client, user_id, message)

    # Get and clear
    pending = await get_and_clear_pending(mock_redis_client, user_id)

    # Verify retrieved correctly
    assert pending == message

    # Verify cleared from Redis
    key = f"pending_message:{user_id}"
    stored = await mock_redis_client.get(key)
    assert stored is None


@pytest.mark.asyncio
async def test_get_and_clear_pending_multiple_messages(mock_redis_client):
    """Test retrieving multiple pending messages."""
    user_id = "12345"

    await append_pending_message(mock_redis_client, user_id, "Message 1")
    await append_pending_message(mock_redis_client, user_id, "Message 2")

    pending = await get_and_clear_pending(mock_redis_client, user_id)

    # Verify both messages retrieved
    assert pending == "Message 1\nMessage 2"

    # Verify cleared
    key = f"pending_message:{user_id}"
    stored = await mock_redis_client.get(key)
    assert stored is None


@pytest.mark.asyncio
async def test_processing_flag_lifecycle(mock_redis_client):
    """Test processing flag set, check, and clear lifecycle."""
    user_id = "12345"
    processing_key = f"processing:{user_id}"

    # Initially no flag
    is_processing = await mock_redis_client.get(processing_key)
    assert is_processing is None

    # Set flag with SETNX (atomic)
    flag_set = await mock_redis_client.set(processing_key, "1", ex=180, nx=True)
    assert flag_set is True

    # Verify flag is set
    is_processing = await mock_redis_client.get(processing_key)
    assert is_processing == "1"

    # Verify TTL is set (should be 180 seconds)
    ttl = await mock_redis_client.ttl(processing_key)
    assert ttl == 180

    # Try to set again (should fail due to NX flag)
    flag_set_again = await mock_redis_client.set(processing_key, "1", ex=180, nx=True)
    assert flag_set_again is None

    # Clear flag
    await mock_redis_client.delete(processing_key)

    # Verify cleared
    is_processing = await mock_redis_client.get(processing_key)
    assert is_processing is None


@pytest.mark.asyncio
async def test_concurrent_message_safety(mock_redis_client):
    """Test that concurrent messages use processing flag correctly."""
    user_id = "12345"
    processing_key = f"processing:{user_id}"

    # Simulate first message setting processing flag
    flag_set = await mock_redis_client.set(processing_key, "1", ex=180, nx=True)
    assert flag_set is True

    # Simulate second message trying to process (should fail)
    flag_set_second = await mock_redis_client.set(processing_key, "1", ex=180, nx=True)
    assert flag_set_second is None

    # Second message should go to pending instead
    await append_pending_message(mock_redis_client, user_id, "Second message")

    count = await count_pending_messages(mock_redis_client, user_id)
    assert count == 1

    # First message completes and clears flag
    await mock_redis_client.delete(processing_key)

    # Now get and process pending
    pending = await get_and_clear_pending(mock_redis_client, user_id)
    assert pending == "Second message"


@pytest.mark.asyncio
async def test_multiple_users_isolation(mock_redis_client):
    """Test that different users have isolated pending slots."""
    user1 = "111"
    user2 = "222"

    # Both users send messages while processing
    await append_pending_message(mock_redis_client, user1, "User 1 message")
    await append_pending_message(mock_redis_client, user2, "User 2 message")

    # Verify isolation
    pending1 = await get_and_clear_pending(mock_redis_client, user1)
    pending2 = await get_and_clear_pending(mock_redis_client, user2)

    assert pending1 == "User 1 message"
    assert pending2 == "User 2 message"


@pytest.mark.asyncio
async def test_handle_pending_messages_mock(mock_redis_client):
    """Test handle_pending_messages function with mocked dependencies."""
    user_id = 12345
    chat_id = 67890
    pending_text = "Pending message"

    # Mock context and backend client
    mock_context = MagicMock()
    mock_context.bot.send_message = AsyncMock(return_value=MagicMock(
        chat_id=chat_id,
        edit_text=AsyncMock()
    ))

    # Mock backend client
    mock_backend_client = MagicMock()
    mock_backend_client.send_message = AsyncMock(return_value={
        "conversation_id": "test-conv-id"
    })

    with patch('handlers.message.get_redis_client', return_value=mock_redis_client), \
         patch('handlers.message.get_backend_client', return_value=mock_backend_client), \
         patch('handlers.message.stream_response_to_telegram', new_callable=AsyncMock) as mock_stream:

        mock_stream.return_value = 100  # Response length

        # Call the function
        await handle_pending_messages(user_id, chat_id, pending_text, mock_context)

        # Verify backend was called with pending message
        mock_backend_client.send_message.assert_called_once_with(
            user_id=user_id,
            message=pending_text,
            message_type="text"
        )

        # Verify status message was sent
        mock_context.bot.send_message.assert_called_once()

        # Verify streaming was initiated
        mock_stream.assert_called_once()


@pytest.mark.asyncio
async def test_recursive_pending_handling(mock_redis_client):
    """Test that recursive pending handling works correctly."""
    user_id = "12345"

    # Simulate scenario: 3 messages arrive during processing
    # First one is being processed, next 2 go to pending
    await append_pending_message(mock_redis_client, user_id, "Second message")
    await append_pending_message(mock_redis_client, user_id, "Third message")

    # First message completes, should pick up pending
    pending = await get_and_clear_pending(mock_redis_client, user_id)
    assert pending == "Second message\nThird message"

    # Verify pending slot is now empty
    remaining = await get_and_clear_pending(mock_redis_client, user_id)
    assert remaining is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
