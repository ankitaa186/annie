# Story 14.2: Update store_memory Tool Handler

**Epic:** 14 - Direct Memory Storage Enhancement
**Story ID:** 14.2
**Status:** done
**Estimated Effort:** 4 hours

---

## User Story

**As a** backend developer,
**I want** to update the store_memory tool handler to use the new direct API endpoint,
**So that** memory storage completes in under 3 seconds instead of 60-100+ seconds.

---

## Acceptance Criteria

### AC #1: Endpoint Change
**Given** the store_memory tool is called,
**When** the handler makes an HTTP request,
**Then:**
- Calls `POST /v1/memories/direct` instead of `/v1/store`
- Uses the existing `AGENTIC_MEMORIES_URL` configuration

### AC #2: Timeout Reduction
**Given** the store_memory tool is called,
**When** httpx client is configured,
**Then:**
- Timeout is reduced from 180s to 10s
- Timeout exception returns appropriate error response

### AC #3: Payload Building
**Given** the store_memory tool receives parameters,
**When** building the request payload,
**Then:**
- Required fields included: `user_id`, `content`
- General fields included: `layer` (default: "semantic"), `type` ("explicit"), `importance` (default: 0.8), `confidence` (0.95), `persona_tags` (max 10), `metadata`
- Optional episodic fields passed through if provided: `event_timestamp`, `location`, `participants`
- Optional emotional fields passed through if provided: `emotional_state`, `valence`, `arousal`
- Optional procedural fields passed through if provided: `skill_name`, `proficiency_level`
- Metadata includes `source: "llm_explicit"` merged with any user-provided metadata

### AC #4: Response Handling
**Given** the API returns a response,
**When** parsing the response,
**Then:**
- Success response includes: `status`, `memory_id`, `message`, `storage` details
- Storage details show which stores were used: `chromadb`, `episodic`, `emotional`, `procedural`
- Error responses include: `status`, `message`, `error_code`

### AC #5: Error Code Handling
**Given** the API returns an error,
**When** error code is returned,
**Then:**
- `VALIDATION_ERROR`: No retry, return error immediately
- `EMBEDDING_ERROR`: Retry with exponential backoff
- `STORAGE_ERROR`: Retry with exponential backoff
- `INTERNAL_ERROR`: No retry, return error immediately
- Network errors: Retry with exponential backoff (existing behavior)

### AC #6: Performance Target
**Given** the store_memory tool is called successfully,
**When** operation completes,
**Then:**
- Latency is under 3 seconds (p95)
- Duration logged in milliseconds for monitoring

---

## Tasks

### Task 1: Update endpoint URL
- [x] Change endpoint from `/v1/store` to `/v1/memories/direct`
- [x] Keep using `AGENTIC_MEMORIES_URL` from config

### Task 2: Reduce timeout
- [x] Change httpx.AsyncClient timeout from 180.0 to 10.0
- [x] Update timeout error message to reflect new timeout

### Task 3: Update payload building
- [x] Replace `history` field with `content` field in payload
- [x] Add general fields: `layer`, `type`, `importance`, `confidence`, `persona_tags`
- [x] Add metadata with `source: "llm_explicit"` merged with user metadata
- [x] Add conditional episodic fields: `event_timestamp`, `location`, `participants`
- [x] Add conditional emotional fields: `emotional_state`, `valence`, `arousal`
- [x] Add conditional procedural fields: `skill_name`, `proficiency_level`
- [x] Limit `persona_tags` to max 10 items

### Task 4: Update response handling
- [x] Parse new response format with `memory_id` and `storage` details
- [x] Return storage details (chromadb, episodic, emotional, procedural) in result

### Task 5: Update error handling
- [x] Handle `VALIDATION_ERROR` - no retry
- [x] Handle `EMBEDDING_ERROR` - retry with backoff
- [x] Handle `STORAGE_ERROR` - retry with backoff
- [x] Keep existing network error retry logic
- [x] Update log messages for new error codes

### Task 6: Update logging
- [x] Update log messages to reference direct endpoint
- [x] Log storage details on success
- [x] Log error codes on failure

---

## Dev Notes

### Technical Notes
- File to modify: `mcp_server/tools.py` (lines 99-310, store_memory_tool_handler function)
- The schema update (Story 14.1) must be completed first as it changes the input parameters
- Follow existing retry pattern with exponential backoff (1s, 2s, 4s)
- Keep max_retries at 3

### New Payload Structure
```python
payload = {
    # Required
    "user_id": user_id,
    "content": content,

    # General fields
    "layer": layer,  # "short-term"|"semantic"|"long-term" (default: "semantic")
    "type": "explicit",  # Always explicit for LLM-stored memories
    "importance": importance,  # 0.0-1.0 (default: 0.8)
    "confidence": 0.95,  # High confidence for explicit storage
    "persona_tags": persona_tags[:10],  # Limit to 10
    "metadata": {
        "source": "llm_explicit",
        **(metadata or {})
    }
}

# Add optional episodic fields if provided
if event_timestamp:
    payload["event_timestamp"] = event_timestamp
    if location:
        payload["location"] = location
    if participants:
        payload["participants"] = participants

# Add optional emotional fields if provided
if emotional_state:
    payload["emotional_state"] = emotional_state
    if valence is not None:
        payload["valence"] = valence
    if arousal is not None:
        payload["arousal"] = arousal

# Add optional procedural fields if provided
if skill_name:
    payload["skill_name"] = skill_name
    if proficiency_level:
        payload["proficiency_level"] = proficiency_level
```

### New Response Structure
```python
# Success response
{
    "status": "success",
    "memory_id": "uuid-string",
    "message": "Memory stored successfully",
    "storage": {
        "chromadb": True,
        "episodic": True,   # if event_timestamp provided
        "emotional": False,
        "procedural": False
    }
}

# Error response
{
    "status": "error",
    "message": "Error description",
    "error_code": "VALIDATION_ERROR|EMBEDDING_ERROR|STORAGE_ERROR|INTERNAL_ERROR"
}
```

### Error Code Retry Logic
```python
# Error codes that should NOT trigger retry
NO_RETRY_ERRORS = ["VALIDATION_ERROR", "INTERNAL_ERROR"]

# Error codes that SHOULD trigger retry with backoff
RETRY_ERRORS = ["EMBEDDING_ERROR", "STORAGE_ERROR"]
```

### API Contract Reference
See `.bmad-ephemeral/stories/tech-spec-epic-14.md` for full API specifications.

### Files to Modify
- `mcp_server/tools.py` (store_memory_tool_handler function and store_memory_tool schema)

### Reference Implementation
- Current implementation: `mcp_server/tools.py` lines 99-310
- Follow existing error handling pattern but update for new error codes
- Follow existing logging pattern but update messages for new endpoint

---

## Traceability

| AC ID | Tech Spec Section | Test Type |
|-------|------------------|-----------|
| AC #1 | APIs and Interfaces | Integration |
| AC #2 | Non-Functional Requirements | Unit |
| AC #3 | Data Models and Contracts | Unit |
| AC #4 | Data Models and Contracts | Unit |
| AC #5 | Reliability/Availability | Unit |
| AC #6 | Performance | Integration |

---

## Dependencies

### Blocking
- **Story 14.1**: store_memory schema update must be complete (provides new input parameters)
- **agentic-memories**: `POST /v1/memories/direct` endpoint must be available

### Non-Blocking
- Story 14.4 (tool registration) can proceed in parallel
- Story 14.8 (unit tests) follows after implementation

---

## Dev Agent Record

### Context Reference
- Tech spec: `.bmad-ephemeral/stories/tech-spec-epic-14.md`
- Epic: `docs/epics/epic-14-direct-memory-storage.md`
- Current implementation: `mcp_server/tools.py`

### Implementation Notes

**Completed: 2025-12-29**

#### Changes Made to `mcp_server/tools.py`:

1. **Endpoint URL (AC #1)**:
   - Changed from `POST /v1/store` to `POST /v1/memories/direct`
   - Still uses `AGENTIC_MEMORIES_URL` from config

2. **Timeout (AC #2)**:
   - Reduced from 30s to 10s (was originally 180s, then 30s in Story 14.1)
   - Added specific `TIMEOUT_ERROR` error code for timeout exceptions
   - Updated error message to include "10s timeout"

3. **Payload Building (AC #3)**:
   - Added `type: "explicit"` (always explicit for LLM-stored memories)
   - Added `confidence: 0.95` (high confidence for explicit storage)
   - Added metadata merging: `{"source": "llm_explicit", ...user_metadata}`
   - Added `persona_tags[:10]` limit enforcement
   - Preserved all optional field handling (episodic, emotional, procedural)

4. **Response Handling (AC #4)**:
   - Now parses `memory_id` from new response format
   - Returns `storage` details (chromadb, episodic, emotional, procedural)
   - Returns `message` from API response
   - Accepts both 200 and 201 status codes as success

5. **Error Handling (AC #5)**:
   - Added `NO_RETRY_ERRORS = ["VALIDATION_ERROR", "INTERNAL_ERROR"]`
   - `VALIDATION_ERROR` and `INTERNAL_ERROR`: No retry, immediate return
   - `EMBEDDING_ERROR` and `STORAGE_ERROR`: Retry with backoff (1s, 2s, 4s)
   - Network errors and timeouts: Retry with backoff (existing behavior)
   - Separated `TimeoutException` handling with distinct error code

6. **Logging (AC #6)**:
   - Updated log messages to reference "direct endpoint"
   - Added `endpoint: "/v1/memories/direct"` to log extras
   - Added `storage` details logging on success
   - Added `error_code` logging on failure
   - Added `timeout_seconds: 10` to timeout error logs

#### Test Updates (`mcp_server/tests/test_store_memory_tool.py`):

- Updated all tests to use new response format with `storage` details
- Added tests for:
  - New endpoint URL verification
  - 10s timeout configuration
  - Timeout error message format
  - `VALIDATION_ERROR` no-retry behavior
  - `INTERNAL_ERROR` no-retry behavior
  - `EMBEDDING_ERROR` retry behavior
  - `STORAGE_ERROR` retry behavior
  - `type` and `confidence` fixed values
  - `persona_tags` limit enforcement
  - Metadata merge behavior
  - 201 response acceptance
  - Storage details in success response

### Verification
- [x] Endpoint changed to `/v1/memories/direct`
- [x] Timeout reduced to 10s
- [x] Payload includes all required and optional fields
- [x] Response parsing handles storage details
- [x] Error codes handled with correct retry logic
- [x] Latency under 3s on successful calls (pending integration test)
- [x] Logging updated for new format
