# Story 12.5: Flush Orchestrator Buffer on Session End

**Status:** drafted
**Epic:** 12 - Memory Storage Enhancements
**Sprint:** Current
**Estimated Effort:** 0.5 days

---

## Story

**As a** user,
**I want** my messages to be stored even if I only send one message or leave without saying goodbye,
**So that** Annie remembers important information I share regardless of conversation length.

---

## Problem Statement

The agentic-memories orchestrator only flushes buffered messages when:
1. Batch size threshold reached (2+ messages), OR
2. A new message arrives 30+ seconds after the first buffered message

**This means single messages or final messages are NEVER stored if:**
- User sends one message and leaves
- User sends a message, gets response, and closes the app
- User's last message before session timeout

**Risk:** Critical information (allergies, preferences, decisions) can be permanently lost.

---

## Acceptance Criteria

| AC# | Description | Verification |
|-----|-------------|--------------|
| **AC1** | Background worker runs every 5 minutes to check for stale sessions | Code review |
| **AC2** | Sessions inactive for 10+ minutes trigger orchestrator flush | Integration test |
| **AC3** | Flush uses `flush=true` parameter via `stream_conversation_message()` | Code review |
| **AC4** | Flush happens asynchronously, doesn't block any user operations | Log verification |
| **AC5** | If orchestrator unavailable during flush, log warning (graceful degradation) | Log verification |
| **AC6** | Single-message conversations are stored within ~15 minutes of inactivity | Manual test |

---

## Tasks / Subtasks

- [ ] **Task 1: Research flush mechanism options**
  - [ ] Option A: Add `flush=true` on last message before session expires
  - [ ] Option B: Call `/v1/orchestrator/flush` endpoint on session cleanup
  - [ ] Option C: Background worker that checks for stale sessions
  - [ ] Decide best approach based on Redis TTL events vs polling

- [ ] **Task 2: Implement session-end flush trigger**
  - [ ] Hook into session expiry mechanism (Redis keyspace notifications OR polling)
  - [ ] Call `MemoryManager.stream_conversation_message(..., flush=True)`
  - [ ] OR call dedicated flush endpoint for conversation_id

- [ ] **Task 3: Add flush method to MemoryClient (if using dedicated endpoint)**
  - [ ] Add `flush_conversation(conversation_id, user_id)` method
  - [ ] Handle errors gracefully (log, don't crash)

- [ ] **Task 4: Test scenarios**
  - [ ] Single message → wait 60s → verify stored
  - [ ] Multiple messages → close session → verify all stored
  - [ ] Orchestrator down during flush → verify graceful degradation

---

## Technical Options

### Option A: Flush on Final Stream Message
When we detect session is about to expire (e.g., activity check), send final message with `flush=true`.

```python
# In background task or session cleanup
await memory_manager.stream_conversation_message(
    user_id=user_id,
    conversation_id=conversation_id,
    role="system",
    content="[session_end]",  # Or empty content
    flush=True  # Forces orchestrator to flush buffer
)
```

**Pros:** Simple, uses existing infrastructure
**Cons:** Requires detecting "session about to expire"

### Option B: Redis Keyspace Notifications
Listen for Redis key expiry events and trigger flush.

```python
# Subscribe to keyspace notifications
pubsub.psubscribe('__keyevent@0__:expired')

# On session:* key expiry
async def on_session_expired(key):
    user_id = extract_user_id(key)
    await flush_user_buffer(user_id)
```

**Pros:** Real-time, event-driven
**Cons:** Requires Redis config change, more complex

### Option C: Background Polling Worker (RECOMMENDED)
Periodically check for inactive sessions and flush their buffers.

```python
# Every 5 minutes (generous interval - this is a fallback)
FLUSH_CHECK_INTERVAL = 300  # 5 minutes
INACTIVE_THRESHOLD = 600    # 10 minutes

async def flush_stale_sessions():
    stale = await find_sessions_inactive_for(seconds=INACTIVE_THRESHOLD)
    for session in stale:
        await flush_and_mark_flushed(session)
```

**Pros:** Simple, works with any Redis config, low overhead
**Cons:** Up to 15 min delay (10 min inactive + 5 min poll cycle)

### Recommendation
**Option C (Background Polling)** with generous timeouts:
- 5-minute poll interval (low overhead)
- 10-minute inactivity threshold (avoids false positives)
- This is a FALLBACK mechanism - most conversations will have 2+ messages
- Can piggyback on existing retry worker pattern

---

## Dev Notes

### Current Flow (Problem)
```
User message → chat.py → orchestrator.stream_message(flush=False)
                              ↓
                       Buffered in orchestrator
                              ↓
                       Waiting for batch threshold...
                              ↓
                       User leaves → buffer abandoned
```

### Proposed Flow (Solution)
```
User message → chat.py → orchestrator.stream_message(flush=False)
                              ↓
                       Buffered in orchestrator
                              ↓
Background worker (every 5 minutes):
  - Find sessions inactive > 10 minutes
  - For each: stream_message(role="system", content="", flush=True)
  - Mark session as "flushed" in Redis
                              ↓
                       Buffer flushed → memories stored
```

### Configuration Constants
```python
FLUSH_CHECK_INTERVAL = 300   # 5 minutes between checks
INACTIVE_THRESHOLD = 600     # 10 minutes of inactivity before flush
FLUSH_MARKER_TTL = 3600      # 1 hour TTL for "already flushed" marker
```

### Files Likely Modified
- `backend/api/memory.py` - Add flush logic to MemoryManager
- `backend/api/memory_client.py` - Add flush_conversation() if needed
- `backend/api/routes/chat.py` - Possibly modify background worker
- `backend/api/main.py` - Add background flush worker to lifespan

### References
- [Source: agentic-memories/src/memory_orchestrator/ingestion.py] - Batching logic
- [Source: agentic-memories/src/memory_orchestrator/policies.py] - Flush interval config
- [Source: backend/api/memory.py] - Existing retry worker pattern

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

<!-- To be filled by dev agent -->

### Debug Log References

<!-- To be filled during implementation -->

### Completion Notes List

<!-- To be filled after implementation -->

### File List

| Status | File Path | Notes |
|--------|-----------|-------|
| | | |

---

## Changelog

| Date | Author | Change |
|------|--------|--------|
| 2025-12-20 | Dev | Story drafted to address buffer flush gap |
