"""
Tracing utilities for Langfuse integration.

Provides request-scoped trace context using contextvars for async-safe operation.
This ensures trace context is isolated between concurrent requests without manual
context passing.
"""
from contextvars import ContextVar
from typing import Optional, Dict, Any

from api.logging import get_logger

logger = get_logger(__name__)

# Request-scoped context variables (async-safe)
_current_trace: ContextVar[Optional[Any]] = ContextVar('current_trace', default=None)
_current_span: ContextVar[Optional[Any]] = ContextVar('current_span', default=None)


def start_trace(name: str, user_id: str, metadata: Optional[Dict[str, Any]] = None, session_id: Optional[str] = None) -> Optional[Any]:
    """Start a new trace for a request.

    This creates a new trace context that will be isolated to the current
    async context (request). All spans created within this request will
    automatically be associated with this trace.

    Args:
        name: Name of the trace (e.g., "chat_request", "memory_storage")
        user_id: User ID for grouping traces
        metadata: Additional metadata to attach to the trace
        session_id: Optional session ID to link related traces (e.g., conversation_id)

    Returns:
        Trace object if Langfuse is enabled, None otherwise.
    """
    from api.observability.langfuse_client import get_langfuse_client

    client = get_langfuse_client()
    if not client:
        logger.debug("Langfuse client not available, skipping trace start")
        return None

    try:
        trace = client.trace(name=name, user_id=user_id, session_id=session_id, metadata=metadata or {})
        _current_trace.set(trace)
        logger.info(
            f"[LANGFUSE] Started trace: {name}",
            extra={
                "trace_name": name,
                "user_id": user_id,
                "session_id": session_id,
                "trace_id": trace.id if hasattr(trace, 'id') else None,
                "metadata": metadata
            }
        )
        return trace
    except Exception as e:
        # Fire-and-forget: log warning but don't crash
        logger.warning(
            f"[LANGFUSE] Failed to start trace: {name}",
            extra={"trace_name": name, "error": str(e), "error_type": type(e).__name__}
        )
        return None


def get_current_trace() -> Optional[Any]:
    """Get the current trace from context.

    Returns:
        Current trace object or None if no trace is active.
    """
    return _current_trace.get()


def start_span(name: str, metadata: Optional[Dict[str, Any]] = None, input: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Start a new span within the current trace or parent span.

    Spans automatically nest under the current trace. If a parent span exists
    in the context, the new span will be created as a child of that span.

    Args:
        name: Name of the span (e.g., "llm_call", "tool_execution", "memory_retrieval")
        metadata: Additional metadata to attach to the span
        input: Input data for the span (will be recorded in Langfuse)

    Returns:
        Span object if trace exists, None otherwise.
    """
    trace = get_current_trace()
    if not trace:
        logger.debug("No active trace, skipping span start")
        return None

    try:
        # Get current parent span (if any) to create nested hierarchy
        parent_span = _current_span.get()

        # Create span as child of parent span, or directly under trace
        if parent_span:
            span = parent_span.span(name=name, metadata=metadata or {}, input=input)
            logger.debug(
                "Started nested span",
                extra={
                    "span_name": name,
                    "parent_span_id": parent_span.id if hasattr(parent_span, 'id') else None
                }
            )
        else:
            span = trace.span(name=name, metadata=metadata or {}, input=input)
            logger.debug("Started top-level span", extra={"span_name": name})

        # Set as current span for potential child spans
        _current_span.set(span)

        return span
    except Exception as e:
        # Fire-and-forget: log warning but don't crash
        logger.warning(
            "Failed to start span",
            extra={"span_name": name, "error": str(e)}
        )
        return None


def end_span(output: Optional[Dict[str, Any]] = None, level: str = "DEFAULT") -> None:
    """End the current span.

    Args:
        output: Output data from the span (will be recorded in Langfuse)
        level: Log level (DEFAULT, WARNING, ERROR)
    """
    span = _current_span.get()
    if span:
        try:
            span.end(output=output, level=level)
            logger.debug("Ended span", extra={"level": level})
            # Clear the current span from context
            _current_span.set(None)
        except Exception as e:
            # Fire-and-forget: log warning but don't crash
            logger.warning("Failed to end span", extra={"error": str(e)})


def trace_error(exception: Exception, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Record an error event in the current trace.

    This creates an error event associated with the current trace, making it
    visible in Langfuse for debugging and monitoring.

    Args:
        exception: The exception that occurred
        metadata: Additional context about the error
    """
    trace = get_current_trace()
    if not trace:
        return

    try:
        trace.event(
            name="error",
            input={
                "exception_type": type(exception).__name__,
                "message": str(exception)
            },
            metadata=metadata or {},
            level="ERROR"
        )
        logger.debug(
            "Recorded error event in trace",
            extra={
                "exception_type": type(exception).__name__,
                "message": str(exception)
            }
        )
    except Exception as e:
        # Fire-and-forget: log warning but don't crash
        logger.warning("Failed to record error event", extra={"error": str(e)})
