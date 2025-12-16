# Story 11.1: Status Emitter Infrastructure

Status: done

## Story

As a developer,
I want a simple API to emit status updates from any function,
so that I can add status visibility without complex callback threading.

## Acceptance Criteria

1. **AC #1: emit_status() Function**
   - Callable from any async function without explicit parameters
   - Uses contextvars to find active status context
   - Fire-and-forget pattern, <10ms overhead
   - No-op if no context active (graceful degradation)
   - Accepts message string and optional icon parameter

2. **AC #2: with_status() Decorator**
   - Wraps async functions with status emission
   - Emits status on function entry
   - Supports string interpolation for dynamic messages (e.g., `{tool_name}`)
   - Preserves function signature and metadata

3. **AC #3: StatusContext Manager**
   - Context manager that initializes status context for a request
   - Stores conversation_id for correlation
   - Provides callback mechanism for status delivery to SSE stream
   - Async-safe across concurrent requests using contextvars
   - Properly cleans up context on exit

4. **AC #4: Langfuse Integration**
   - Status emissions traced as spans in Langfuse
   - Links to parent request trace via existing tracing context
   - Non-blocking (follows existing fire-and-forget pattern)

## Tasks / Subtasks

- [x] Task 1: Create status module structure (AC: #1, #2, #3)
  - [x] Create `backend/api/status.py` module
  - [x] Define `StatusEmitter` class with emit method
  - [x] Define `_status_context: ContextVar[StatusEmitter]` contextvar

- [x] Task 2: Implement emit_status() function (AC: #1)
  - [x] Implement context lookup via `_status_context.get(None)`
  - [x] Handle None case gracefully (no-op)
  - [x] Accept message and optional icon parameter (default: "🔄")
  - [x] Format message as `f"{icon} {message}"`
  - [x] Call emitter callback if context exists

- [x] Task 3: Implement with_status() decorator (AC: #2)
  - [x] Create decorator factory accepting message and optional icon
  - [x] Use `@wraps(func)` to preserve function metadata
  - [x] Support both sync and async functions
  - [x] Call emit_status() on function entry

- [x] Task 4: Implement StatusContext manager (AC: #3)
  - [x] Create async context manager class
  - [x] Accept conversation_id and status_callback parameters
  - [x] Set contextvar token on enter
  - [x] Reset contextvar on exit
  - [x] Handle exceptions gracefully

- [x] Task 5: Add Langfuse tracing integration (AC: #4)
  - [x] Import existing Langfuse tracing utilities
  - [x] Create span for each status emission
  - [x] Link to current trace context
  - [x] Non-blocking span creation

- [x] Task 6: Write unit tests
  - [x] Test emit_status with active context
  - [x] Test emit_status without context (no-op)
  - [x] Test with_status decorator
  - [x] Test StatusContext isolation across concurrent requests
  - [x] Test Langfuse span creation

## Dev Notes

### Architecture Pattern

Follow the existing Langfuse tracing pattern in `backend/api/observability/tracing.py`:
- Singleton contextvar for request-scoped state
- Fire-and-forget emission
- Graceful degradation when context unavailable

### Key Implementation Details

```python
# backend/api/status.py
from contextvars import ContextVar
from functools import wraps
from typing import Callable, Optional

class StatusEmitter:
    def __init__(self, conversation_id: str, callback: Callable[[str], None]):
        self.conversation_id = conversation_id
        self.callback = callback

    def emit(self, message: str) -> None:
        """Fire-and-forget status emission"""
        try:
            self.callback(message)
        except Exception:
            pass  # Never fail on status

_status_context: ContextVar[Optional[StatusEmitter]] = ContextVar('status', default=None)

def emit_status(message: str, icon: str = "🔄") -> None:
    """Call from anywhere - fire and forget"""
    if emitter := _status_context.get():
        emitter.emit(f"{icon} {message}")

def with_status(message: str, icon: str = "🔄"):
    """Decorator for wrapping functions with status emission"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            emit_status(message, icon)
            return await func(*args, **kwargs)
        return wrapper
    return decorator

class StatusContext:
    """Async context manager for status emission scope"""
    def __init__(self, conversation_id: str, callback: Callable[[str], None]):
        self.emitter = StatusEmitter(conversation_id, callback)
        self.token = None

    async def __aenter__(self):
        self.token = _status_context.set(self.emitter)
        return self.emitter

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        _status_context.reset(self.token)
        return False
```

### Project Structure Notes

- New file: `backend/api/status.py`
- Follows existing patterns in `backend/api/observability/`
- No changes to existing files in this story

### Performance Requirements

- emit_status() must complete in <10ms
- No blocking I/O in the emission path
- Callback execution is the caller's responsibility

### References

- [Source: docs/epics/epic-11-realtime-status-updates.md#Story-11.1]
- [Source: backend/api/observability/tracing.py] - Pattern reference for contextvars usage
- [Source: backend/api/observability/langfuse_client.py] - Pattern for fire-and-forget

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-16 | Story drafted from Epic 11 brainstorm | SM (Bob) |

## Dev Agent Record

### Context Reference

- [Story Context XML](.bmad-ephemeral/stories/11-1-status-emitter-infrastructure-context.xml)
  - Generated: 2025-12-16
  - Contains: Architecture patterns, code examples, acceptance criteria mapping, test strategy
  - Pattern references: backend/api/observability/tracing.py (ContextVar pattern)
  - Integration points: SSE streaming (Story 11.2), Langfuse tracing

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

N/A - All tests passed on first run after fixing logging field name conflict.

### Completion Notes List

**Implementation Summary:**
- Created `backend/api/status.py` with all required components:
  - `StatusEmitter` class with fire-and-forget emit() method
  - `emit_status()` function with ContextVar lookup and graceful degradation
  - `with_status()` decorator preserving function metadata via @wraps
  - `StatusContext` async context manager with proper token-based cleanup
  - Langfuse span creation integrated via `_create_langfuse_span()`

**Key Implementation Details:**
- Followed existing ContextVar pattern from `backend/api/observability/tracing.py`
- Fire-and-forget error handling: all exceptions caught and logged, never propagated
- Performance: emit_status() overhead <1ms per call (well under 10ms requirement)
- Async-safe isolation between concurrent requests via ContextVar
- Langfuse spans created with metadata (message, conversation_id, duration_ms)
- Fixed logging field conflict: renamed "message" to "status_message" in logger extras (Python's LogRecord reserves "message" field)

**Testing:**
- Created comprehensive test suite in `backend/tests/unit/test_status.py`
- All 25 tests passing:
  - 6 tests for emit_status() function (AC #1)
  - 5 tests for with_status() decorator (AC #2)
  - 5 tests for StatusContext manager (AC #3)
  - 5 tests for Langfuse integration (AC #4)
  - 4 edge case tests
- Test coverage includes:
  - Fire-and-forget pattern verification
  - Async-safe isolation across concurrent requests
  - Graceful degradation when no context active
  - Exception handling and error propagation
  - Performance validation (<10ms overhead)
  - Unicode and edge case handling

**Acceptance Criteria Verification:**
- AC #1 (emit_status): PASS - Context lookup, fire-and-forget, <10ms overhead, graceful degradation
- AC #2 (with_status): PASS - Async wrapping, status emission, metadata preservation via @wraps
- AC #3 (StatusContext): PASS - Context initialization, async-safe isolation, proper cleanup
- AC #4 (Langfuse): PASS - Span creation, trace linking, non-blocking pattern

**No Changes to Existing Files:**
This story created pure infrastructure with no modifications to existing code. Integration with SSE streaming will happen in Story 11.2.

### File List

**New Files Created:**
- `/home/ankit/dev/annie/backend/api/status.py` (235 lines)
  - Core status emission infrastructure
  - StatusEmitter, emit_status(), with_status(), StatusContext
  - Langfuse integration via get_current_trace()

- `/home/ankit/dev/annie/backend/tests/unit/test_status.py` (451 lines)
  - Comprehensive unit tests for all acceptance criteria
  - 25 tests covering all components and edge cases
  - Mock-based testing for callbacks and Langfuse integration

**Files Modified:**
- None (pure infrastructure story)
