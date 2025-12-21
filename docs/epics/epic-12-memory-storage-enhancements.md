# Epic 12: Memory Storage Enhancements

**Status:** Planned
**Priority:** Medium (Cost Optimization)
**Estimated Effort:** 1-2 days
**Author:** Ankit
**Date:** 2025-12-20

---

## Overview

Switch Annie's background memory storage from direct `/v1/store` calls to the agentic-memories orchestrator's `/v1/orchestrator/message` endpoint. The orchestrator provides intelligent batching that reduces LLM extraction costs by ~70%.

---

## Business Value

1. **Cost Reduction**: Batch 2-8 messages before LLM extraction instead of extracting every message
2. **Cleaner Code**: Remove unused farewell detection logic
3. **Better Architecture**: Leverage agentic-memories' built-in batching instead of reinventing it

---

## Technical Background

### Current Flow (Inefficient)
```
User message → chat.py → /v1/store → LLM extraction (every message)
```
- Every user message triggers a separate LLM extraction call
- 10 messages = 10 extraction calls

### New Flow (Optimized)
```
User message → chat.py → /v1/orchestrator/message → batching → LLM extraction
```
- Orchestrator batches 2-8 messages based on conversation volume
- 30-second flush timeout ensures nothing is lost
- 10 messages = ~2-3 extraction calls (~70% reduction)

### Orchestrator Batching Logic (from agentic-memories)
```python
low_volume_batch_size: 2   # Early conversation: batch every 2 messages
medium_volume_batch_size: 5
high_volume_batch_size: 8  # Active conversation: batch every 8 messages
flush_interval: 30 seconds # Max time before forced flush
max_buffer_size: 15        # Safety cap
```

---

## What Changes

| Component | Change |
|-----------|--------|
| `backend/api/memory_client.py` | Add `stream_message()` method |
| `backend/api/memory.py` | Add `stream_conversation_message()` method |
| `backend/api/routes/chat.py` | Switch background task to use orchestrator |
| `backend/api/routes/chat.py` | Remove `FAREWELL_KEYWORDS`, `is_conversation_ending()` |

## What Stays the Same

| Component | Notes |
|-----------|-------|
| MCP `store_memory` tool | Unchanged - still calls `/v1/store` directly |
| Memory retrieval | Unchanged |
| Circuit breaker logic | Reused for orchestrator calls |

---

## Stories Breakdown

### Story 12.1: Add stream_message() to MemoryClient

**Goal:** Create HTTP client method to call `/v1/orchestrator/message`

**Acceptance Criteria:**

**AC #1:** Given MemoryClient, when `stream_message()` called, then:
- POST to `{AGENTIC_MEMORIES_URL}/v1/orchestrator/message`
- Payload: `{conversation_id, role, content, metadata: {user_id}}`
- Returns `{injections: [...]}` (relevant memories if any)

**AC #2:** Given network error, when `stream_message()` fails, then:
- Raises `MemoryNetworkError` (existing exception)
- Logs error with context
- Does not block caller

**AC #3:** Given Langfuse enabled, when method called, then:
- Operation traced as span
- Duration and success/failure logged

**Estimated Effort:** 0.25 days

---

### Story 12.2: Update MemoryManager for Orchestrator

**Goal:** Add method to stream messages through orchestrator with circuit breaker

**Acceptance Criteria:**

**AC #1:** Given MemoryManager, when `stream_conversation_message()` called, then:
- Checks circuit breaker (reuse existing logic)
- Calls `MemoryClient.stream_message()`
- Returns memory injections (or None on failure)

**AC #2:** Given agentic-memories unavailable, when method fails, then:
- Increments circuit breaker failure count
- Logs warning
- Returns None (graceful degradation)

**AC #3:** Given circuit breaker open, when method called, then:
- Returns None immediately (no network call)
- Logs that circuit breaker is open

**Estimated Effort:** 0.25 days

---

### Story 12.3: Switch Chat Endpoint to Orchestrator

**Goal:** Replace `/v1/store` background task with orchestrator call

**Acceptance Criteria:**

**AC #1:** Given user sends message, when chat endpoint processes it, then:
- Background task calls `stream_conversation_message()` (not `store_conversation_memory()`)
- Passes: user_id, conversation_id, message content, role="user"

**AC #2:** Given background task, when executed, then:
- Fire-and-forget pattern maintained
- No blocking of chat response
- Errors logged but not propagated

**AC #3:** Given existing tests, when run after change, then:
- All tests pass
- No behavioral regression for user

**Estimated Effort:** 0.25 days

---

### Story 12.4: Remove Farewell Detection Code

**Goal:** Clean up unused farewell detection logic

**Acceptance Criteria:**

**AC #1:** Given chat.py, when reviewed after changes, then:
- `FAREWELL_KEYWORDS` set removed
- `is_conversation_ending()` function removed
- `conversation_is_ending` variable removed
- `needs_decision_support` kept (still used for memory retrieval)

**AC #2:** Given code removal, when tests run, then:
- All tests pass
- No references to removed code remain

**AC #3:** Given cleanup, when code reviewed, then:
- No orphaned imports
- No dead code paths

**Estimated Effort:** 0.25 days

---

### Story 12.5: Flush Orchestrator Buffer on Session End

**Goal:** Ensure single messages and final messages are not lost when user leaves

**Problem:** The orchestrator only flushes buffers when:
1. Batch threshold reached (2+ messages), OR
2. New message arrives 30+ seconds after first buffered message

Single messages or final messages stay buffered indefinitely if user leaves.

**Acceptance Criteria:**

**AC #1:** Given session inactivity > 10 minutes, when background worker runs, then:
- Orchestrator buffer is flushed for that conversation
- Memories are extracted and stored

**AC #2:** Given single-message conversation, when user leaves, then:
- Message is stored within ~15 minutes (10 min inactivity + 5 min worker cycle)
- This is a fallback - most conversations have 2+ messages and batch normally

**AC #3:** Given orchestrator unavailable during flush, when flush attempted, then:
- Warning logged (graceful degradation)
- No crash or user-facing error

**Estimated Effort:** 0.5 days

---

## Dependencies

### Prerequisites
- agentic-memories running with `/v1/orchestrator/message` endpoint

### No Blocking Dependencies
- Can start immediately

---

## Success Metrics

- [x] Memory storage uses orchestrator endpoint
- [ ] ~70% reduction in LLM extraction calls (verify via Langfuse)
- [x] Farewell detection code removed
- [x] All existing tests pass
- [ ] Single messages stored within ~15 minutes of inactivity (fallback)
- [ ] No regression in user experience

---

## Rollout Strategy

### Phase 1: Implementation
- Implement all 4 stories
- Test locally with agentic-memories

### Phase 2: Validation
- Monitor Langfuse for extraction call counts
- Verify batching is working (should see fewer but larger extractions)

### Phase 3: Cleanup
- Remove any commented-out code
- Update CLAUDE.md if needed

---

## References

- **agentic-memories Orchestrator:** `/home/ankit/dev/agentic-memories/src/memory_orchestrator/orchestrator.py`
- **agentic-memories Policies:** `/home/ankit/dev/agentic-memories/src/memory_orchestrator/policies.py`
- **Annie Memory Client:** `backend/api/memory_client.py`
- **Annie Memory Manager:** `backend/api/memory.py`
- **Annie Chat Route:** `backend/api/routes/chat.py`
