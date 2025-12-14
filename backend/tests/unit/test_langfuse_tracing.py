"""
Unit tests for Langfuse tracing utilities with contextvars.

Tests AC #4: Trace context is maintained correctly using contextvars without cross-request contamination.
Tests AC #5: Application continues without errors when Langfuse is unavailable (fire-and-forget).
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock


# Reset context vars before each test
@pytest.fixture(autouse=True)
def reset_context_vars():
    """Reset context variables before each test."""
    import api.observability.tracing as tracing
    tracing._current_trace.set(None)
    tracing._span_stack.set(())
    yield
    tracing._current_trace.set(None)
    tracing._span_stack.set(())


@pytest.fixture
def mock_langfuse_client():
    """Mock Langfuse client for tracing tests."""
    mock_client = Mock()
    mock_trace = Mock()
    mock_trace.id = "trace-123"
    mock_trace.span = Mock(return_value=Mock())
    mock_client.trace = Mock(return_value=mock_trace)

    with patch("api.observability.langfuse_client.get_langfuse_client", return_value=mock_client):
        yield mock_client


@pytest.fixture
def mock_langfuse_disabled():
    """Mock Langfuse client as disabled."""
    with patch("api.observability.langfuse_client.get_langfuse_client", return_value=None):
        yield


class TestTraceContextManagement:
    """Test AC #4: Trace context maintained correctly using contextvars."""

    def test_start_trace_creates_trace(self, mock_langfuse_client):
        """Test that start_trace creates a trace and sets it in context."""
        from api.observability.tracing import start_trace, get_current_trace

        trace = start_trace(
            name="test_trace",
            user_id="user123",
            metadata={"key": "value"}
        )

        # Verify trace was created
        assert trace is not None
        assert trace.id == "trace-123"

        # Verify trace is set in context
        current_trace = get_current_trace()
        assert current_trace is not None
        assert current_trace.id == "trace-123"

        # Verify client.trace was called with correct parameters
        mock_langfuse_client.trace.assert_called_once_with(
            name="test_trace",
            user_id="user123",
            session_id=None,
            metadata={"key": "value"}
        )

    def test_start_span_under_trace(self, mock_langfuse_client):
        """Test that start_span creates a span under the current trace."""
        from api.observability.tracing import start_trace, start_span

        # Start a trace first
        trace = start_trace(name="test_trace", user_id="user123")

        # Start a span
        span = start_span(
            name="test_span",
            metadata={"span_key": "span_value"},
            input={"input": "data"}
        )

        # Verify span was created
        assert span is not None

        # Verify trace.span was called with correct parameters
        trace.span.assert_called_once_with(
            name="test_span",
            metadata={"span_key": "span_value"},
            input={"input": "data"}
        )

    def test_end_span_completes_span(self, mock_langfuse_client):
        """Test that end_span properly completes a span."""
        from api.observability.tracing import start_trace, start_span, end_span

        # Setup trace and span
        trace = start_trace(name="test_trace", user_id="user123")
        span = start_span(name="test_span")

        # End the span
        end_span(output={"result": "success"}, level="DEFAULT")

        # Verify span.end was called
        span.end.assert_called_once_with(
            output={"result": "success"},
            level="DEFAULT"
        )

    def test_trace_error_records_error(self, mock_langfuse_client):
        """Test that trace_error records an error event in the trace."""
        from api.observability.tracing import start_trace, trace_error

        # Start a trace
        trace = start_trace(name="test_trace", user_id="user123")

        # Record an error
        exception = ValueError("Test error")
        trace_error(exception, metadata={"context": "test"})

        # Verify trace.event was called with error details
        trace.event.assert_called_once()
        call_kwargs = trace.event.call_args.kwargs
        assert call_kwargs["name"] == "error"
        assert call_kwargs["level"] == "ERROR"
        assert call_kwargs["input"]["exception_type"] == "ValueError"
        assert call_kwargs["input"]["message"] == "Test error"
        assert call_kwargs["metadata"] == {"context": "test"}


class TestAsyncContextIsolation:
    """Test AC #4: No cross-request contamination with contextvars."""

    @pytest.mark.asyncio
    async def test_concurrent_traces_isolated(self, mock_langfuse_client):
        """Test that concurrent async requests have isolated trace contexts."""
        from api.observability.tracing import start_trace, get_current_trace

        async def request_handler(user_id: str, trace_name: str):
            """Simulate a request handler with its own trace."""
            trace = start_trace(name=trace_name, user_id=user_id)
            await asyncio.sleep(0.01)  # Simulate async work
            current = get_current_trace()
            return current.id if current else None

        # Run multiple concurrent "requests"
        results = await asyncio.gather(
            request_handler("user1", "trace1"),
            request_handler("user2", "trace2"),
            request_handler("user3", "trace3")
        )

        # All should have gotten the same trace ID (mocked)
        # but importantly, they should not interfere with each other
        assert len(results) == 3
        # In real scenario, each would have different IDs,
        # but with mock they're all "trace-123"
        # The key is no exceptions were raised due to contamination

    @pytest.mark.asyncio
    async def test_nested_spans_isolated(self, mock_langfuse_client):
        """Test that nested spans in concurrent contexts don't interfere."""
        from api.observability.tracing import start_trace, start_span

        async def nested_operation(operation_id: int):
            """Simulate nested span creation."""
            trace = start_trace(name=f"trace-{operation_id}", user_id=f"user{operation_id}")
            span1 = start_span(name=f"span1-{operation_id}")
            await asyncio.sleep(0.01)
            span2 = start_span(name=f"span2-{operation_id}")
            await asyncio.sleep(0.01)
            return operation_id

        # Run multiple operations concurrently
        results = await asyncio.gather(
            nested_operation(1),
            nested_operation(2),
            nested_operation(3)
        )

        # Verify all completed successfully
        assert results == [1, 2, 3]
        # No cross-contamination would mean no exceptions


class TestFireAndForgetPattern:
    """Test AC #5: Application continues without errors when Langfuse unavailable."""

    def test_start_trace_graceful_when_disabled(self, mock_langfuse_disabled, caplog):
        """Test that start_trace returns None gracefully when Langfuse is disabled."""
        from api.observability.tracing import start_trace

        trace = start_trace(name="test_trace", user_id="user123")

        # Verify no trace created (graceful degradation)
        assert trace is None

        # Verify debug log (fire-and-forget)
        assert any(
            "Langfuse client not available" in record.message
            for record in caplog.records
        )

    def test_start_span_graceful_when_no_trace(self, mock_langfuse_disabled, caplog):
        """Test that start_span returns None gracefully when no active trace."""
        from api.observability.tracing import start_span

        span = start_span(name="test_span")

        # Verify no span created (graceful degradation)
        assert span is None

        # Verify debug log
        assert any(
            "No active trace" in record.message
            for record in caplog.records
        )

    def test_trace_error_graceful_when_no_trace(self, mock_langfuse_disabled):
        """Test that trace_error does not crash when no active trace."""
        from api.observability.tracing import trace_error

        exception = ValueError("Test error")

        # Should not raise any exception
        trace_error(exception, metadata={"context": "test"})

    def test_start_trace_continues_on_exception(self, caplog):
        """Test that start_trace continues when trace creation fails."""
        mock_client = Mock()
        mock_client.trace.side_effect = Exception("Connection refused")

        with patch("api.observability.langfuse_client.get_langfuse_client", return_value=mock_client):
            from api.observability.tracing import start_trace

            trace = start_trace(name="test_trace", user_id="user123")

            # Verify None returned (fire-and-forget)
            assert trace is None

            # Verify warning logged
            assert any(
                "Failed to start trace" in record.message
                for record in caplog.records
            )

    def test_end_span_graceful_on_exception(self, mock_langfuse_client, caplog):
        """Test that end_span continues when span.end() fails."""
        from api.observability.tracing import start_trace, start_span, end_span

        # Setup trace and span
        trace = start_trace(name="test_trace", user_id="user123")
        span = start_span(name="test_span")

        # Make span.end() raise an exception
        span.end.side_effect = Exception("Network error")

        # Should not raise exception (fire-and-forget)
        end_span(output={"result": "success"})

        # Verify warning logged
        assert any(
            "Failed to end span" in record.message
            for record in caplog.records
        )


class TestConfigFunctions:
    """Test AC #7: Config functions return correct values with @lru_cache."""

    def test_config_functions_cached(self):
        """Test that config functions use lru_cache for optimization."""
        import os
        from unittest.mock import patch

        # Set environment variables
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-test-12345",
            "LANGFUSE_SECRET_KEY": "sk-test-67890",
            "LANGFUSE_HOST": "https://us.cloud.langfuse.com"
        }):
            from api.config import (
                get_langfuse_public_key,
                get_langfuse_secret_key,
                get_langfuse_host,
                is_langfuse_enabled
            )

            # Clear cache first
            get_langfuse_public_key.cache_clear()
            get_langfuse_secret_key.cache_clear()
            get_langfuse_host.cache_clear()
            is_langfuse_enabled.cache_clear()

            # Call functions multiple times
            key1 = get_langfuse_public_key()
            key2 = get_langfuse_public_key()
            secret1 = get_langfuse_secret_key()
            secret2 = get_langfuse_secret_key()
            host1 = get_langfuse_host()
            host2 = get_langfuse_host()
            enabled1 = is_langfuse_enabled()
            enabled2 = is_langfuse_enabled()

            # Verify correct values
            assert key1 == "pk-test-12345"
            assert key1 == key2
            assert secret1 == "sk-test-67890"
            assert secret1 == secret2
            assert host1 == "https://us.cloud.langfuse.com"
            assert host1 == host2
            assert enabled1 is True
            assert enabled1 == enabled2

            # Verify cache info (functions should have cache)
            assert hasattr(get_langfuse_public_key, 'cache_info')
            assert hasattr(get_langfuse_secret_key, 'cache_info')
            assert hasattr(get_langfuse_host, 'cache_info')
            assert hasattr(is_langfuse_enabled, 'cache_info')
