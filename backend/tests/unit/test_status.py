"""
Unit tests for status emission infrastructure.

Tests all acceptance criteria from Story 11.1:
- AC #1: emit_status() function (contextvar lookup, fire-and-forget, graceful degradation)
- AC #2: with_status() decorator (async wrapping, status emission, metadata preservation)
- AC #3: StatusContext manager (context initialization, async-safe isolation, cleanup)
- AC #4: Langfuse integration (span creation, trace linking, non-blocking)
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, patch, MagicMock


# Reset context vars before each test
@pytest.fixture(autouse=True)
def reset_status_context():
    """Reset status context variable before each test."""
    import api.status as status
    status._status_context.set(None)
    yield
    status._status_context.set(None)


@pytest.fixture
def mock_callback():
    """Mock callback for status emission."""
    return Mock()


@pytest.fixture
def mock_langfuse_trace():
    """Mock Langfuse trace for testing span creation."""
    mock_trace = Mock()
    mock_trace.id = "trace-123"
    mock_trace.span = Mock(return_value=Mock())
    return mock_trace


class TestEmitStatusFunction:
    """Test AC #1: emit_status() function."""

    @pytest.mark.asyncio
    async def test_emit_status_with_active_context(self, mock_callback):
        """Test that emit_status calls callback when context is active."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-123", mock_callback):
            emit_status("Processing request")

        # Verify callback was called with formatted message
        mock_callback.assert_called_once_with("🔄 Processing request")

    @pytest.mark.asyncio
    async def test_emit_status_with_custom_icon(self, mock_callback):
        """Test that emit_status accepts custom icon parameter."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-123", mock_callback):
            emit_status("Searching the web", icon="🔍")

        # Verify callback was called with custom icon
        mock_callback.assert_called_once_with("🔍 Searching the web")

    def test_emit_status_without_context(self, caplog):
        """Test that emit_status is a no-op when no context is active (graceful degradation)."""
        from api.status import emit_status

        # Should not raise exception
        emit_status("This should be ignored")

        # No callback should be called (test passes if no exception)

    @pytest.mark.asyncio
    async def test_emit_status_fire_and_forget(self, caplog):
        """Test that emit_status doesn't propagate callback exceptions."""
        from api.status import StatusContext, emit_status

        # Create callback that raises exception
        failing_callback = Mock(side_effect=Exception("Callback failed"))

        async with StatusContext("conv-123", failing_callback):
            # Should not raise exception (fire-and-forget)
            emit_status("This should not crash")

        # Verify warning was logged
        assert any(
            "Failed to emit status" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_emit_status_performance(self, mock_callback):
        """Test that emit_status has <10ms overhead."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-123", mock_callback):
            start = time.perf_counter()
            for _ in range(100):
                emit_status("Test message")
            duration = time.perf_counter() - start

        # Average should be well under 10ms per call
        average_ms = (duration / 100) * 1000
        assert average_ms < 10, f"Average overhead {average_ms}ms exceeds 10ms threshold"

    @pytest.mark.asyncio
    async def test_emit_status_multiple_messages(self, mock_callback):
        """Test emitting multiple status messages in sequence."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-123", mock_callback):
            emit_status("Step 1", icon="1️⃣")
            emit_status("Step 2", icon="2️⃣")
            emit_status("Step 3", icon="3️⃣")

        # Verify all messages were emitted
        assert mock_callback.call_count == 3
        assert mock_callback.call_args_list[0][0][0] == "1️⃣ Step 1"
        assert mock_callback.call_args_list[1][0][0] == "2️⃣ Step 2"
        assert mock_callback.call_args_list[2][0][0] == "3️⃣ Step 3"


class TestWithStatusDecorator:
    """Test AC #2: with_status() decorator."""

    @pytest.mark.asyncio
    async def test_with_status_emits_on_entry(self, mock_callback):
        """Test that @with_status emits status on function entry."""
        from api.status import StatusContext, with_status

        @with_status("Processing data")
        async def process_data():
            return "result"

        async with StatusContext("conv-123", mock_callback):
            result = await process_data()

        # Verify status was emitted
        mock_callback.assert_called_once_with("🔄 Processing data")
        # Verify function returned normally
        assert result == "result"

    @pytest.mark.asyncio
    async def test_with_status_custom_icon(self, mock_callback):
        """Test that @with_status accepts custom icon."""
        from api.status import StatusContext, with_status

        @with_status("Searching database", icon="🔍")
        async def search_db():
            return "found"

        async with StatusContext("conv-123", mock_callback):
            result = await search_db()

        mock_callback.assert_called_once_with("🔍 Searching database")
        assert result == "found"

    @pytest.mark.asyncio
    async def test_with_status_preserves_function_metadata(self):
        """Test that @with_status preserves function name and docstring."""
        from api.status import with_status

        @with_status("Testing metadata")
        async def my_function():
            """This is my docstring."""
            pass

        # Verify @wraps preserved metadata
        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "This is my docstring."

    @pytest.mark.asyncio
    async def test_with_status_without_context(self):
        """Test that @with_status works gracefully without active context."""
        from api.status import with_status

        @with_status("Processing")
        async def process():
            return "done"

        # Should work without StatusContext (no-op)
        result = await process()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_with_status_exception_propagation(self, mock_callback):
        """Test that @with_status propagates exceptions from decorated function."""
        from api.status import StatusContext, with_status

        @with_status("Failing operation")
        async def failing_function():
            raise ValueError("Test error")

        async with StatusContext("conv-123", mock_callback):
            with pytest.raises(ValueError, match="Test error"):
                await failing_function()

        # Status should have been emitted before exception
        mock_callback.assert_called_once_with("🔄 Failing operation")


class TestStatusContextManager:
    """Test AC #3: StatusContext async context manager."""

    @pytest.mark.asyncio
    async def test_status_context_initialization(self, mock_callback):
        """Test that StatusContext initializes status emitter."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-456", mock_callback) as emitter:
            # Emitter should be available
            assert emitter is not None
            assert emitter.conversation_id == "conv-456"

            # emit_status should work
            emit_status("Test message")

        mock_callback.assert_called_once_with("🔄 Test message")

    @pytest.mark.asyncio
    async def test_status_context_cleanup(self, mock_callback):
        """Test that StatusContext properly cleans up on exit."""
        from api.status import StatusContext, emit_status, _status_context

        async with StatusContext("conv-789", mock_callback):
            # Context should be active
            assert _status_context.get() is not None

        # Context should be cleaned up after exit
        assert _status_context.get() is None

        # emit_status should now be a no-op
        emit_status("Should be ignored")
        mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_status_context_exception_handling(self, mock_callback):
        """Test that StatusContext cleans up properly even on exceptions."""
        from api.status import StatusContext, _status_context

        with pytest.raises(ValueError, match="Test error"):
            async with StatusContext("conv-999", mock_callback):
                # Context should be active
                assert _status_context.get() is not None
                raise ValueError("Test error")

        # Context should still be cleaned up
        assert _status_context.get() is None

    @pytest.mark.asyncio
    async def test_status_context_isolation(self, mock_callback):
        """Test that concurrent StatusContexts are isolated (async-safe)."""
        from api.status import StatusContext, emit_status

        callback1 = Mock()
        callback2 = Mock()
        callback3 = Mock()

        async def request_handler(conv_id: str, callback: Mock, message: str):
            """Simulate a request handler with its own status context."""
            async with StatusContext(conv_id, callback):
                await asyncio.sleep(0.01)  # Simulate async work
                emit_status(message)
                await asyncio.sleep(0.01)
            return conv_id

        # Run multiple concurrent "requests"
        results = await asyncio.gather(
            request_handler("conv-1", callback1, "Request 1"),
            request_handler("conv-2", callback2, "Request 2"),
            request_handler("conv-3", callback3, "Request 3")
        )

        # Verify all completed successfully
        assert results == ["conv-1", "conv-2", "conv-3"]

        # Verify each callback received only its own message (no cross-contamination)
        callback1.assert_called_once_with("🔄 Request 1")
        callback2.assert_called_once_with("🔄 Request 2")
        callback3.assert_called_once_with("🔄 Request 3")

    @pytest.mark.asyncio
    async def test_status_context_nested_contexts(self, mock_callback):
        """Test that nested StatusContexts work correctly (inner context takes precedence)."""
        from api.status import StatusContext, emit_status

        callback_outer = Mock()
        callback_inner = Mock()

        async with StatusContext("conv-outer", callback_outer):
            emit_status("Outer message 1")

            async with StatusContext("conv-inner", callback_inner):
                emit_status("Inner message")

            emit_status("Outer message 2")

        # Verify callbacks were called correctly
        assert callback_outer.call_count == 2
        callback_outer.assert_any_call("🔄 Outer message 1")
        callback_outer.assert_any_call("🔄 Outer message 2")

        callback_inner.assert_called_once_with("🔄 Inner message")


class TestLangfuseIntegration:
    """Test AC #4: Langfuse integration."""

    @pytest.mark.asyncio
    async def test_status_emission_creates_langfuse_span(self, mock_callback, mock_langfuse_trace):
        """Test that status emission creates a Langfuse span when trace is active."""
        from api.status import StatusContext, emit_status

        with patch("api.observability.tracing.get_current_trace", return_value=mock_langfuse_trace):
            async with StatusContext("conv-123", mock_callback):
                emit_status("Testing Langfuse span")

        # Verify callback was called
        mock_callback.assert_called_once()

        # Verify Langfuse span was created
        mock_langfuse_trace.span.assert_called_once()
        span_call = mock_langfuse_trace.span.call_args
        assert span_call.kwargs["name"] == "status_emission"
        assert "message" in span_call.kwargs["metadata"]
        assert "🔄 Testing Langfuse span" in span_call.kwargs["metadata"]["message"]

    @pytest.mark.asyncio
    async def test_status_emission_graceful_without_langfuse(self, mock_callback):
        """Test that status emission works when Langfuse is unavailable (fire-and-forget)."""
        from api.status import StatusContext, emit_status

        with patch("api.observability.tracing.get_current_trace", return_value=None):
            async with StatusContext("conv-123", mock_callback):
                # Should not raise exception
                emit_status("Testing without Langfuse")

        # Callback should still work
        mock_callback.assert_called_once_with("🔄 Testing without Langfuse")

    @pytest.mark.asyncio
    async def test_langfuse_span_failure_non_blocking(self, mock_callback, caplog):
        """Test that Langfuse span creation failures don't block status emission."""
        from api.status import StatusContext, emit_status

        # Mock trace that raises exception on span creation
        failing_trace = Mock()
        failing_trace.span.side_effect = Exception("Langfuse API error")

        with patch("api.observability.tracing.get_current_trace", return_value=failing_trace):
            async with StatusContext("conv-123", mock_callback):
                # Should not raise exception (fire-and-forget)
                emit_status("Testing Langfuse failure")

        # Callback should still work
        mock_callback.assert_called_once_with("🔄 Testing Langfuse failure")

        # Debug log should mention the failure
        assert any(
            "Failed to create Langfuse span" in record.message
            for record in caplog.records
        )

    @pytest.mark.asyncio
    async def test_langfuse_span_includes_conversation_id(self, mock_callback, mock_langfuse_trace):
        """Test that Langfuse span metadata includes conversation_id."""
        from api.status import StatusContext, emit_status

        with patch("api.observability.tracing.get_current_trace", return_value=mock_langfuse_trace):
            async with StatusContext("conv-special-123", mock_callback):
                emit_status("Test with conversation ID")

        # Verify conversation_id in span metadata
        span_call = mock_langfuse_trace.span.call_args
        assert span_call.kwargs["metadata"]["conversation_id"] == "conv-special-123"

    @pytest.mark.asyncio
    async def test_langfuse_span_includes_duration(self, mock_callback, mock_langfuse_trace):
        """Test that Langfuse span metadata includes duration_ms."""
        from api.status import StatusContext, emit_status

        with patch("api.observability.tracing.get_current_trace", return_value=mock_langfuse_trace):
            async with StatusContext("conv-123", mock_callback):
                emit_status("Test duration tracking")

        # Verify duration_ms in span metadata
        span_call = mock_langfuse_trace.span.call_args
        assert "duration_ms" in span_call.kwargs["metadata"]
        assert isinstance(span_call.kwargs["metadata"]["duration_ms"], (int, float))
        assert span_call.kwargs["metadata"]["duration_ms"] >= 0


class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_empty_message(self, mock_callback):
        """Test emitting empty message."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-123", mock_callback):
            emit_status("")

        # Should still emit with icon
        mock_callback.assert_called_once_with("🔄 ")

    @pytest.mark.asyncio
    async def test_unicode_message(self, mock_callback):
        """Test emitting message with unicode characters."""
        from api.status import StatusContext, emit_status

        async with StatusContext("conv-123", mock_callback):
            emit_status("正在处理请求 🌟", icon="✨")

        mock_callback.assert_called_once_with("✨ 正在处理请求 🌟")

    @pytest.mark.asyncio
    async def test_long_message(self, mock_callback):
        """Test emitting very long message."""
        from api.status import StatusContext, emit_status

        long_message = "A" * 1000
        async with StatusContext("conv-123", mock_callback):
            emit_status(long_message)

        # Should handle long messages
        assert mock_callback.call_count == 1
        assert len(mock_callback.call_args[0][0]) > 1000

    @pytest.mark.asyncio
    async def test_multiple_decorators(self, mock_callback):
        """Test function with multiple @with_status decorators (stacking)."""
        from api.status import StatusContext, with_status

        @with_status("Outer operation")
        @with_status("Inner operation")
        async def multi_decorated():
            return "done"

        async with StatusContext("conv-123", mock_callback):
            result = await multi_decorated()

        # Both decorators should emit (inner first, then outer)
        assert mock_callback.call_count == 2
        # Note: Due to decorator stacking, outer executes first
        assert result == "done"
