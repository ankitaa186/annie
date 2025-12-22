"""
Status emission infrastructure for real-time status updates.

Provides a simple, fire-and-forget API to emit status updates from any async function
without complex callback threading. Uses contextvars for request-scoped status context
with async-safe isolation between concurrent requests.

This module follows the same pattern as Langfuse tracing (backend/api/observability/tracing.py):
- Singleton ContextVar for request-scoped state
- Fire-and-forget emission with graceful error handling
- No manual context passing required
"""
from contextvars import ContextVar
from functools import wraps
from typing import Callable, Optional, Dict, Any
import time

from api.logging import get_logger

logger = get_logger(__name__)


class StatusEmitter:
    """Handles status emission for a single request.

    This class is created once per request via StatusContext and provides
    fire-and-forget status emission to a callback (typically an SSE stream).
    """

    def __init__(self, conversation_id: str, callback: Callable[[str], None]):
        """Initialize status emitter for a request.

        Args:
            conversation_id: Conversation ID for correlation
            callback: Callback function to deliver status messages
        """
        self.conversation_id = conversation_id
        self.callback = callback

    def emit(self, message: str) -> None:
        """Emit a status message via the callback.

        Fire-and-forget pattern: never blocks or crashes on errors.
        All exceptions are caught and logged without propagating.

        Args:
            message: Formatted status message (with icon prefix)
        """
        start_time = time.perf_counter()

        try:
            # Call the callback to deliver status
            self.callback(message)

            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.debug(
                "Status emitted",
                extra={
                    "conversation_id": self.conversation_id,
                    "status_message": message,
                    "duration_ms": duration_ms
                }
            )

            # Create Langfuse span for observability
            self._create_langfuse_span(message, duration_ms)

        except Exception as e:
            # Fire-and-forget: log error but never crash
            logger.warning(
                "Failed to emit status",
                extra={
                    "conversation_id": self.conversation_id,
                    "status_message": message,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )

    def _create_langfuse_span(self, message: str, duration_ms: float) -> None:
        """Create Langfuse span for status emission (non-blocking).

        Args:
            message: Status message that was emitted
            duration_ms: Emission duration in milliseconds
        """
        try:
            from api.observability.tracing import get_current_trace

            trace = get_current_trace()
            if trace:
                # Create span under current trace
                trace.span(
                    name="status_emission",
                    metadata={
                        "message": message,
                        "conversation_id": self.conversation_id,
                        "duration_ms": duration_ms
                    }
                )
                logger.debug(
                    "Created Langfuse span for status emission",
                    extra={"status_message": message}
                )
        except Exception as e:
            # Fire-and-forget: trace failures should never block status
            logger.debug(
                "Failed to create Langfuse span for status",
                extra={"error": str(e)}
            )


# Request-scoped context variable (async-safe)
_status_context: ContextVar[Optional[StatusEmitter]] = ContextVar('status', default=None)


def emit_status(message: str, icon: str = "🔄") -> None:
    """Emit a status update from anywhere in the call stack.

    This function looks up the current status context via ContextVar and emits
    a status message if a context is active. If no context exists, it's a no-op.

    Fire-and-forget pattern with <10ms overhead:
    - Simple O(1) contextvar lookup
    - No blocking I/O
    - Graceful degradation when no context active

    Args:
        message: Status message to emit (without icon prefix)
        icon: Icon to prefix the message (default: "🔄")

    Examples:
        emit_status("Processing user query")
        emit_status("Searching the web", icon="🔍")
        emit_status("Storing memory", icon="💾")
    """
    # Look up current status emitter from context
    emitter = _status_context.get()

    if emitter:
        # Format message with icon and emit
        formatted_message = f"{icon} {message}"
        emitter.emit(formatted_message)
    # No-op if no context active (graceful degradation)


def with_status(message: str, icon: str = "🔄"):
    """Decorator to emit status on function entry.

    Wraps async functions to automatically emit a status update when the function
    is called. Preserves function signature and metadata via @wraps.

    Args:
        message: Status message to emit on function entry
        icon: Icon to prefix the message (default: "🔄")

    Returns:
        Decorator function

    Examples:
        @with_status("Calling search tool", icon="🔍")
        async def search_tool(query: str):
            ...

        @with_status("Storing conversation memory", icon="💾")
        async def store_memory(conversation: str):
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Emit status on function entry
            emit_status(message, icon)
            # Call original function
            return await func(*args, **kwargs)
        return wrapper
    return decorator


class StatusContext:
    """Async context manager for status emission scope.

    Sets up status context for a request, allowing any function in the call stack
    to emit status updates via emit_status(). Uses ContextVar for async-safe
    isolation between concurrent requests.

    Args:
        conversation_id: Conversation ID for correlation
        status_callback: Callback function to deliver status messages

    Examples:
        async with StatusContext(conversation_id, callback):
            emit_status("Processing request")
            await process_request()
            # Status context automatically cleaned up on exit
    """

    def __init__(self, conversation_id: str, status_callback: Callable[[str], None]):
        """Initialize status context for a request.

        Args:
            conversation_id: Conversation ID for correlation
            status_callback: Callback function to deliver status messages
        """
        self.emitter = StatusEmitter(conversation_id, status_callback)
        self.token = None

    async def __aenter__(self):
        """Enter context: set status emitter in ContextVar.

        Returns:
            StatusEmitter instance for this request
        """
        self.token = _status_context.set(self.emitter)
        logger.debug(
            "Status context activated",
            extra={"conversation_id": self.emitter.conversation_id}
        )
        return self.emitter

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context: reset ContextVar to clean up.

        Properly cleans up context even if exceptions occur.
        Returns False to propagate exceptions.
        """
        if self.token:
            _status_context.reset(self.token)
            logger.debug(
                "Status context deactivated",
                extra={"conversation_id": self.emitter.conversation_id}
            )
        # Return False to propagate exceptions
        return False
