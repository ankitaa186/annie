# Story 12.1: Add stream_message() to MemoryClient

**Status:** done
**Epic:** 12 - Memory Storage Enhancements
**Sprint:** Current
**Estimated Effort:** 0.25 days

---

## Story

**As a** developer,
**I want** a `stream_message()` method in MemoryClient that calls the orchestrator endpoint,
**So that** Annie can leverage agentic-memories' intelligent batching for memory storage.

---

## Acceptance Criteria

| AC# | Description | Verification |
|-----|-------------|--------------|
| **AC1** | `stream_message()` POSTs to `/v1/orchestrator/message` | Code review + test |
| **AC2** | Payload contains: `conversation_id`, `role`, `content`, `metadata: {user_id}` | Code review |
| **AC3** | Returns dict with `injections` list (relevant memories) | Unit test |
| **AC4** | Network errors raise `MemoryNetworkError` | Unit test |
| **AC5** | API errors raise `MemoryAPIError` with status code | Unit test |
| **AC6** | Logs request/response with `duration_ms`, `conversation_id`, `injections_count` | Log inspection |

---

## Tasks / Subtasks

- [ ] **Task 1: Implement stream_message() method** (AC: 1, 2, 3)
  - [ ] Add method signature with parameters: `conversation_id`, `role`, `content`, `user_id`, `message_id` (optional)
  - [ ] Build request payload matching orchestrator schema
  - [ ] POST to `{memories_url}/v1/orchestrator/message`
  - [ ] Parse response and return `{injections: [...]}` structure

- [ ] **Task 2: Implement error handling** (AC: 4, 5)
  - [ ] Handle `httpx.TimeoutException` → raise `MemoryNetworkError`
  - [ ] Handle `httpx.NetworkError`, `httpx.ConnectError` → raise `MemoryNetworkError`
  - [ ] Handle non-200 status codes → raise `MemoryAPIError`
  - [ ] Follow same patterns as existing `store_memory()` method

- [ ] **Task 3: Add structured logging** (AC: 6)
  - [ ] Log request start with `conversation_id`, `role`, `user_id`
  - [ ] Log success with `duration_ms`, `injections_count`
  - [ ] Log errors with context

- [ ] **Task 4: Write tests**
  - [ ] Test successful call returns injections
  - [ ] Test network error raises `MemoryNetworkError`
  - [ ] Test API error raises `MemoryAPIError`
  - [ ] Test timeout handling

---

## Dev Notes

### API Endpoint

**POST** `{AGENTIC_MEMORIES_URL}/v1/orchestrator/message`

**Request Body:**
```json
{
  "conversation_id": "conv_123",
  "role": "user",
  "content": "What stocks should I buy?",
  "metadata": {
    "user_id": "user_456"
  },
  "message_id": "msg_789"  // optional
}
```

**Response:**
```json
{
  "injections": [
    {
      "memory_id": "mem_abc",
      "content": "User prefers tech stocks",
      "source": "conversation",
      "channel": "telegram",
      "score": 0.85,
      "metadata": {}
    }
  ]
}
```

### Implementation Pattern

Follow the existing `store_memory()` method pattern:
1. Build URL: `f"{self.memories_url}/v1/orchestrator/message"`
2. Build payload with required fields
3. POST with httpx client
4. Handle errors with try/except
5. Log with structured extras
6. Return parsed response

### Method Signature

```python
async def stream_message(
    self,
    conversation_id: str,
    role: str,
    content: str,
    user_id: str,
    message_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Stream a single message through the orchestrator for batched storage.

    Args:
        conversation_id: Conversation identifier
        role: Message role ("user", "assistant", "system", "tool")
        content: Message content
        user_id: User ID (passed in metadata for storage)
        message_id: Optional message ID for tracking

    Returns:
        dict: Response with "injections" list of relevant memories

    Raises:
        MemoryNetworkError: If agentic-memories service is unreachable
        MemoryAPIError: If API returns an error
    """
```

### Project Structure Notes

- **File to modify:** `backend/api/memory_client.py`
- **Add after:** `store_memory()` method (line ~255)
- **Pattern follows:** Existing `store_memory()` and `retrieve_memories()` methods
- **No new dependencies required**

### References

- [Source: docs/epics/epic-12-memory-storage-enhancements.md#Story-12.1]
- [Source: backend/api/memory_client.py] - Existing patterns
- [Source: agentic-memories/src/routers/app.py] - Orchestrator endpoint

---

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

Claude Opus 4.5

### Debug Log References

None - straightforward implementation

### Completion Notes List

- Added `stream_message()` method to MemoryClient (lines 413-578)
- POSTs to `/v1/orchestrator/message` with payload: `conversation_id`, `role`, `content`, `metadata.user_id`, `flush`
- Returns dict with `injections` list
- Handles timeout, network, and API errors following existing patterns
- Added 8 unit tests all passing

### File List

| Status | File Path | Notes |
|--------|-----------|-------|
| MODIFIED | backend/api/memory_client.py | Added stream_message() method (~165 lines) |
| MODIFIED | backend/tests/unit/test_memory_client.py | Added TestStreamMessage class with 8 tests |

---

## Changelog

| Date | Author | Change |
|------|--------|--------|
| 2025-12-20 | SM (Bob) | Story drafted from Epic 12 |
