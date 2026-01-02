# Epic 11: Real-Time Status Updates

**Status:** Planned
**Priority:** High (UX Enhancement)
**Estimated Effort:** 3 days
**Author:** John (PM) with Winston (Architect), Sally (UX)
**Date:** 2025-12-16

---

## Overview

Enable real-time status updates to Telegram showing users exactly what Annie is doing while processing their request. Similar to the "thinking" indicators in Gemini and ChatGPT, but more granular - explicitly showing MCP tool calls, memory operations, and processing phases.

**Key Features:**
- Immediate acknowledgment on message receipt
- Granular status updates during processing
- Explicit tool call visibility with results
- Single-message edit pattern (no spam)
- Pending message handling for consecutive user messages

---

## Business Value

1. **Reduced Anxiety**: Users know their message was received and is being processed
2. **Transparency**: Users see exactly what Annie is doing (tools, memory, analysis)
3. **Trust Building**: Visible work process builds confidence in Annie's capabilities
4. **Modern UX**: Matches user expectations set by Gemini, ChatGPT, Claude
5. **Debugging Aid**: Users can report exactly where things went wrong

**Strategic Driver:** Transform Annie from "black box that eventually responds" to "transparent assistant working with you."

---

## Technical Architecture

### Status System Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Status System                         │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌─────────────────┐     ┌──────────────────────────┐   │
│  │ @with_status()  │     │ emit_status(msg)         │   │
│  │ Decorator       │────▶│ Context-based emitter    │   │
│  └─────────────────┘     └───────────┬──────────────┘   │
│                                      │                   │
│                          ┌───────────▼──────────────┐   │
│                          │ StatusContext (contextvar)│   │
│                          │ - conversation_id         │   │
│                          │ - status_callback         │   │
│                          └───────────┬──────────────┘   │
│                                      │                   │
└──────────────────────────────────────┼───────────────────┘
                                       │
                          ┌────────────▼────────────┐
                          │ SSE Status Frame        │
                          │ {"type": "status",      │
                          │  "message": "..."}      │
                          └────────────┬────────────┘
                                       │
                          ┌────────────▼────────────┐
                          │ Telegram Bot            │
                          │ edit_message_text()     │
                          └─────────────────────────┘
```

### Status Emission API

Both patterns available for flexibility:

```python
# backend/api/status.py
from contextvars import ContextVar

_status_context: ContextVar[StatusEmitter] = ContextVar('status')

def emit_status(message: str, icon: str = "🔄") -> None:
    """Call from anywhere - fire and forget, <10ms overhead"""
    if ctx := _status_context.get(None):
        ctx.emit(f"{icon} {message}")

def with_status(message: str, icon: str = "🔄"):
    """Decorator for wrapping entire functions"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            emit_status(message, icon)
            result = await func(*args, **kwargs)
            return result
        return wrapper
    return decorator
```

### SSE Protocol Extension

Extend existing SSE streaming with status frames:

```python
# Existing token frame
{"type": "token", "content": "Hello"}

# New status frame
{"type": "status", "message": "🔧 Calling get_portfolio..."}

# Status with result preview
{"type": "status", "message": "✅ Portfolio loaded: 3 holdings, $15,420 value"}

# Completion frame (existing)
{"type": "done", "tokens_used": {...}}
```

### Pending Message Handling

Single pending slot per user - not a queue:

```
┌─────────────────────────────────────────────────────────┐
│                    Message Flow                          │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  User: "What's my portfolio?"                           │
│        ↓                                                 │
│  [PROCESSING] ← Active request                          │
│  [PENDING: null]                                        │
│                                                          │
│  User: "Also check AAPL"                                │
│        ↓                                                 │
│  [PROCESSING] ← Still working                           │
│  [PENDING: "Also check AAPL"]                           │
│                                                          │
│  User: "And GOOGL"                                      │
│        ↓                                                 │
│  [PROCESSING] ← Still working                           │
│  [PENDING: "Also check AAPL\nAnd GOOGL"] ← Appended     │
│                                                          │
│  Processing completes → Response sent                    │
│        ↓                                                 │
│  [PROCESSING: pending message] ← Picks up combined      │
│  [PENDING: null]                                        │
│                                                          │
│  LLM sees natural chat history:                         │
│    User: "What's my portfolio?"                         │
│    Annie: "You have 3 holdings..."                      │
│    User: "Also check AAPL\nAnd GOOGL"                   │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

**Key Design Decision:** LLM handles multiple messages naturally via chat history. No complex coalescing logic - just simple string concatenation for pending messages.

---

## UX Flow

### Status Message Progression

```
User: "What's my portfolio worth and how is AAPL doing?"

Annie: "🔄 Annie is thinking..."
Annie: "🔍 Retrieving your memories..."
Annie: "📊 Calling get_portfolio..."
Annie: "✅ Portfolio loaded: 3 holdings"
Annie: "📈 Calling get_stock_data for AAPL..."
Annie: "✅ AAPL analysis complete: $175.50 (+2.3%)"
Annie: "🧠 Composing response..."
[Message cleared, actual response streams in]
Annie: "Your portfolio is worth $15,420, up 12% overall..."
```

### Consecutive Message Handling

```
User: "What's my portfolio?"
Annie: "🔄 Annie is thinking..."
Annie: "📊 Calling get_portfolio..."

User: "Also check AAPL"
Annie: "📝 Got it - will handle after current request..."

User: "And GOOGL"
Annie: "📝 Added to pending (2 follow-up messages)..."

[First response streams]
Annie: "You have 3 holdings worth $15,420..."

[Auto-picks up pending]
Annie: "🔄 Annie is thinking..."
Annie: "📈 Calling get_stock_data for AAPL..."
Annie: "📈 Calling get_stock_data for GOOGL..."
[Response streams]
```

### Icon Set (Generic)

| Icon | Usage |
|------|-------|
| 🔄 | Default/thinking |
| 🔍 | Search/retrieval |
| 🔧 | Tool call start |
| ✅ | Operation complete |
| 📝 | Message queued |
| 🧠 | LLM composing |

---

## Stories Breakdown

### Story 11.1: Status Emitter Infrastructure

**Goal:** Create the core status emission system using contextvars.

**As a** developer,
**I want** a simple API to emit status updates from any function,
**So that** I can add status visibility without complex callback threading.

**Acceptance Criteria:**

**AC #1: emit_status() Function**
- Callable from any async function without parameters
- Uses contextvars to find active status context
- Fire-and-forget, <10ms overhead
- No-op if no context active (graceful degradation)

**AC #2: with_status() Decorator**
- Wraps async functions with status emission
- Emits on function entry
- Supports string interpolation for dynamic messages

**AC #3: StatusContext Manager**
- Initializes status context for a request
- Provides callback mechanism for status delivery
- Async-safe across concurrent requests

**AC #4: Langfuse Integration**
- Status emissions traced as spans
- Links to parent request trace

**Technical Notes:**
- New file: `backend/api/status.py`
- Pattern mirrors existing Langfuse tracing contextvars
- Must be non-blocking

**Estimated Effort:** 0.5 day

---

### Story 11.2: SSE Status Frame Support

**Goal:** Extend SSE streaming protocol to include status frames.

**As a** developer,
**I want** status updates delivered via the existing SSE stream,
**So that** Telegram bot can receive status without a separate channel.

**Acceptance Criteria:**

**AC #1: Status Frame Type**
- New SSE frame: `{"type": "status", "message": "..."}`
- Interleaved with existing token frames
- Maintains frame ordering

**AC #2: Stream Route Updates**
- `/api/stream/{conversation_id}` emits status frames
- Status context initialized at stream start
- Status callback writes to SSE response

**AC #3: Backward Compatibility**
- Existing token/done/error frames unchanged
- Clients ignoring status frames continue working

**Technical Notes:**
- Update: `backend/api/routes/stream.py`
- StatusContext callback → SSE write

**Estimated Effort:** 0.5 day

---

### Story 11.3: Telegram Status Message Handler

**Goal:** Telegram bot edits a single message with status updates, then replaces with response.

**As a** user,
**I want** to see status updates in a single updating message,
**So that** my chat isn't spammed with multiple status messages.

**Acceptance Criteria:**

**AC #1: Initial Status Message**
- On receiving user message, immediately send "🔄 Annie is thinking..."
- Store message_id for subsequent edits
- Target: <100ms from message receipt

**AC #2: Status Message Editing**
- Each status frame triggers `edit_message_text()`
- Reuse existing rate limit handling
- Debounce if needed (existing logic)

**AC #3: Transition to Response**
- On first token frame, clear status message
- Begin streaming actual response in same message
- Or: Delete status message, send new response message

**AC #4: Pending Message Indicator**
- When message queued, show: "📝 Got it - will handle after current request..."
- Update count if multiple pending: "📝 Added to pending (2 follow-up messages)..."

**Technical Notes:**
- Update: `telegram_bot/bot.py`
- Leverage existing message edit infrastructure
- Store status_message_id in conversation state

**Estimated Effort:** 0.5 day

---

### Story 11.4: Instrument MCP Tools with Status

**Goal:** All MCP tool calls emit status updates showing tool name and results.

**As a** user,
**I want** to see which tools Annie is calling and their results,
**So that** I understand how Annie is gathering information.

**Acceptance Criteria:**

**AC #1: Tool Call Start Status**
- Emit: "🔧 Calling {tool_name}..."
- Before tool execution begins

**AC #2: Tool Result Status**
- Emit: "✅ {tool_name} complete: {brief_result}"
- Brief result examples:
  - get_portfolio: "3 holdings, $15,420 value"
  - get_stock_data: "AAPL $175.50 (+2.3%)"
  - internet_search: "Found 5 results"
  - get_user_profile: "Profile loaded (67% complete)"

**AC #3: Tool Error Status**
- Emit: "⚠️ {tool_name} failed: {brief_error}"
- Continue processing (existing graceful degradation)

**AC #4: All Tools Instrumented**
- get_portfolio
- add_holding / update_holding / remove_holding
- get_stock_data / get_stock_history
- get_user_profile
- store_memory / retrieve_memories
- internet_search (if using MCP, not Grok Live Search)

**Technical Notes:**
- Update: `backend/api/mcp_client.py`
- Use decorator or emit_status() at call sites
- Result summarization logic per tool type

**Estimated Effort:** 0.5 day

---

### Story 11.5: Instrument Memory, Profile, and LLM Phases

**Goal:** Status updates for memory retrieval, profile loading, and LLM phases.

**As a** user,
**I want** to see when Annie is checking my memories and composing a response,
**So that** I understand the full processing pipeline.

**Acceptance Criteria:**

**AC #1: Memory Operations**
- "🔍 Retrieving your memories..."
- "✅ Found 3 relevant memories" (or "No relevant memories found")
- "💾 Saving conversation to memory..."

**AC #2: Profile Operations**
- "👤 Loading your profile..."
- "✅ Profile loaded (67% complete)"
- Background refresh: no status (silent)

**AC #3: LLM Phases**
- "🧠 Composing response..." (just before streaming starts)
- Emitted after all tool calls complete

**AC #4: Grok Live Search (if applicable)**
- "🌐 Searching the web..."
- "✅ Found {n} sources"

**Technical Notes:**
- Update: `backend/api/memory.py`
- Update: `backend/api/profile.py`
- Update: `backend/api/routes/stream.py` (LLM phase)

**Estimated Effort:** 0.5 day

---

### Story 11.6: Pending Message Slot

**Goal:** Handle consecutive user messages with single pending slot that auto-processes.

**As a** user,
**I want** to send follow-up messages while Annie is working,
**So that** I can add context without waiting for the response.

**Acceptance Criteria:**

**AC #1: Processing Flag**
- Redis key `processing:{user_id}` indicates active request
- Set on request start, cleared on completion
- TTL: 3 minutes (safety)

**AC #2: Single Pending Slot**
- Redis key `pending_message:{user_id}` stores pending message(s)
- New messages append to existing pending (newline separated)
- Not a queue - single concatenated string
- TTL: 5 minutes (safety)

**AC #3: Status Update for Pending**
- First pending message: "📝 Got it - will handle after current request..."
- Subsequent: "📝 Added to pending ({n} follow-up messages)..."

**AC #4: Auto-Pickup on Completion**
- After response completes, check for pending
- If pending exists: clear pending, process as new request
- LLM sees natural chat history flow

**AC #5: Concurrent Request Safety**
- Only one active processing per user
- Pending slot prevents race conditions
- Redis atomic operations for safety

**Technical Notes:**
- Update: `telegram_bot/bot.py` (message handling)
- Update: `backend/api/routes/chat.py` (processing flag)
- Redis keys with TTL for safety

**Estimated Effort:** 0.5 day

---

## Dependencies

### Prerequisites
- Epic 2: SSE streaming infrastructure (complete)
- Epic 5: Telegram bot message handling (complete)
- Existing Telegram edit rate limit handling (complete)

### No Blocking Dependencies
- Can start immediately

---

## Success Metrics

### Functional Metrics
- [ ] Status message appears <100ms after user sends message
- [ ] All MCP tool calls surface as status updates
- [ ] Tool results show brief summary (not raw data)
- [ ] Pending messages processed correctly after completion
- [ ] No message loss on consecutive messages

### Performance Metrics
- [ ] emit_status() overhead <10ms
- [ ] No degradation to response latency
- [ ] Telegram edit rate limits not exceeded

### UX Metrics
- [ ] Single message edited (no spam)
- [ ] Clean transition from status to response
- [ ] Pending message count accurate

---

## Testing Strategy

### Unit Tests
- StatusContext isolation across concurrent requests
- emit_status() no-op when no context
- Pending message concatenation logic

### Integration Tests
- SSE frames received in correct order
- Status → token transition
- Pending message auto-pickup

### E2E Tests
- Telegram message edits (not new messages)
- Multiple consecutive messages handled
- Full flow: status → tools → response

---

## Rollout Strategy

### Phase 1: Infrastructure (Stories 11.1, 11.2)
- Status system in place but no emissions
- SSE protocol extended

### Phase 2: Telegram Integration (Story 11.3)
- Basic "Annie is thinking..." working
- Edit-in-place pattern validated

### Phase 3: Instrumentation (Stories 11.4, 11.5)
- All tools and phases emit status
- Full visibility into processing

### Phase 4: Pending Messages (Story 11.6)
- Consecutive message handling
- Complete feature set

---

## References

- **SSE Streaming**: `backend/api/routes/stream.py`
- **Telegram Bot**: `telegram_bot/bot.py`
- **MCP Client**: `backend/api/mcp_client.py`
- **Memory Manager**: `backend/api/memory.py`
- **Profile Manager**: `backend/api/profile.py`
- **Langfuse Tracing Pattern**: `backend/api/observability/tracing.py`

---

_This epic transforms Annie's UX from "silent processing" to "transparent assistant" - users see exactly what Annie is doing, building trust and reducing wait anxiety._
