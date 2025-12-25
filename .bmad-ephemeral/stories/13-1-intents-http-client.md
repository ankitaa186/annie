# Story 13.1: Intents HTTP Client

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.1
**Status:** ready-for-dev
**Estimated Effort:** 0.5 days

---

## User Story

**As a** backend developer,
**I want** an HTTP client to communicate with agentic-memories Intents API,
**So that** Annie can create, manage, and execute proactive triggers.

---

## Acceptance Criteria

### AC #1: CRUD Operations
**Given** IntentsClient initialized,
**When** CRUD methods called,
**Then:**
- `create_intent(data)` → POST `/v1/intents`
- `list_intents(user_id, filters)` → GET `/v1/intents?user_id=X`
- `get_intent(id)` → GET `/v1/intents/{id}`
- `update_intent(id, data)` → PUT `/v1/intents/{id}`
- `delete_intent(id)` → DELETE `/v1/intents/{id}`

### AC #2: Polling & Worker Operations
**Given** IntentsClient initialized,
**When** polling methods called,
**Then:**
- `get_pending(trigger_type, user_id)` → GET `/v1/intents/pending`
  - Returns due intents, excludes already-claimed intents
  - Includes `in_cooldown` flag in metadata for condition triggers
- `claim_intent(id)` → POST `/v1/intents/{id}/claim`
  - Claims intent for exclusive processing (prevents race conditions)
  - Returns `IntentClaimResponse` with `intent` and `claimed_at`
  - Returns 409 Conflict if already claimed within 5 minutes
  - Uses `FOR UPDATE SKIP LOCKED` for multi-worker safety
- `fire_intent(id, report)` → POST `/v1/intents/{id}/fire`
  - Reports execution result: `success`, `failed`, `gate_blocked`, `condition_not_met`
  - Clears `claimed_at` (releases claim)
  - Returns `cooldown_active`, `cooldown_remaining_hours`, `last_condition_fire`
  - Updates `execution_count` and `last_executed`
- `get_history(id, limit, offset)` → GET `/v1/intents/{id}/history`
  - Returns execution audit trail ordered by `executed_at DESC`
  - Includes timing metrics (evaluation_ms, generation_ms, delivery_ms)

### AC #3: Error Handling
**Given** network error,
**When** any method fails,
**Then:**
- Raises `IntentsClientError` with context
- Logs error with trigger/user details
- Circuit breaker integration (reuse pattern from MemoryClient)

### AC #4: Observability
**Given** Langfuse enabled,
**When** methods called,
**Then:**
- Operations traced as spans
- Duration and success/failure logged

---

## Tasks

### Task 1: Create IntentsClient class structure
- [x] Create `backend/api/proactive/intents_client.py`
- [x] Define `IntentsClientError` exception class (+ IntentsNetworkError, IntentsAPIError)
- [x] Create `IntentsClient` class with `__init__` accepting base URL from env
- [x] Add type hints and docstrings

### Task 2: Implement CRUD methods
- [x] Implement `create_intent(data: dict) -> dict`
- [x] Implement `list_intents(user_id: str, filters: dict = None) -> list`
- [x] Implement `get_intent(id: str) -> dict`
- [x] Implement `update_intent(id: str, data: dict) -> dict`
- [x] Implement `delete_intent(id: str) -> bool`

### Task 3: Implement polling & worker methods
- [x] Implement `get_pending(trigger_type: str = None, user_id: str = None) -> list`
- [x] Implement `claim_intent(id: str) -> ClaimResult` (handle 409 Conflict)
- [x] Implement `fire_intent(id: str, report: IntentFireRequest) -> IntentFireResponse`
- [x] Implement `get_history(id: str, limit: int = 50, offset: int = 0) -> list`

### Task 4: Add circuit breaker integration
- [x] Note: Circuit breaker deferred to IntentsManager (Story 13.2) following MemoryManager pattern
- [x] IntentsClient provides health_check() method for availability testing

### Task 5: Add Langfuse tracing
- [x] Note: Per context guidance, @observe() decorator not needed for client methods (too granular)
- [x] Client will be called from traced contexts (IntentsManager, MCP tools) which will have @observe()
- [x] Duration logging implemented via duration_ms in all method logs

### Task 6: Add to health check
- [ ] Add intents client status to `/health/full` endpoint
- [ ] Check connectivity to agentic-memories intents endpoint

---

## Dev Notes

### Technical Notes
- Follow existing `MemoryClient` pattern in `backend/api/memory_client.py`
- Reuse circuit breaker infrastructure from `backend/api/memory.py`
- Base URL from `AGENTIC_MEMORIES_URL` environment variable
- All endpoints prefixed with `/v1/intents`

### API Schema Reference (from agentic-memories)
**Trigger Types:** `cron`, `interval`, `once`, `price`, `silence`, `portfolio`
**Action Types:** `notify`, `check_in`, `briefing`, `analysis`, `reminder`
**Fire Status:** `success`, `failed`, `gate_blocked`, `condition_not_met`

**ScheduledIntentCreate fields:**
- `user_id`, `intent_name`, `description`, `trigger_type`
- `trigger_schedule`: {cron, interval_minutes, trigger_at, check_interval_minutes, timezone}
- `trigger_condition`: {expression, condition_type, cooldown_hours, fire_mode}
- `action_type`, `action_context`, `action_priority`
- `expires_at`, `max_executions`, `metadata`

**IntentFireRequest fields:**
- `status`, `message_id`, `message_preview`, `trigger_data`, `gate_result`
- `evaluation_ms`, `generation_ms`, `delivery_ms`, `error_message`

### Files to Create/Modify
- `backend/api/intents_client.py` (new)
- `backend/api/routes/health.py` (add intents health check)
- `backend/api/config.py` (if new env vars needed)

### Reference Implementation
- See `backend/api/memory_client.py` for HTTP client pattern
- See `backend/api/memory.py` for circuit breaker pattern

---

## Dev Agent Record

### Context Reference
- Story context file: `.bmad-ephemeral/stories/13-1-intents-http-client.context.xml`
- Generated: 2025-12-24
- Contains: API schema, existing patterns (MemoryClient, circuit breaker), implementation guidance

### Implementation Notes

**File Created:** `backend/api/proactive/intents_client.py` (1,563 lines)

**Key Implementation Details:**

1. **Exception Hierarchy:**
   - `IntentsClientError` (base)
   - `IntentsNetworkError` (service unreachable, inherits from base)
   - `IntentsAPIError` (API error response, includes status_code and response_data)

2. **IntentsClient Class:**
   - Async HTTP client using httpx.AsyncClient
   - Default URL: `http://host.docker.internal:8080` (from AGENTIC_MEMORIES_URL config)
   - Default timeout: 30 seconds (appropriate for intent operations)
   - Async context manager support (__aenter__, __aexit__, close())

3. **CRUD Methods Implemented:**
   - `create_intent(data)` → POST /v1/intents
   - `list_intents(user_id, filters)` → GET /v1/intents?user_id=X
   - `get_intent(intent_id)` → GET /v1/intents/{id}
   - `update_intent(intent_id, data)` → PUT /v1/intents/{id}
   - `delete_intent(intent_id)` → DELETE /v1/intents/{id}

4. **Worker Methods Implemented:**
   - `get_pending(trigger_type, user_id)` → GET /v1/intents/pending
   - `claim_intent(intent_id)` → POST /v1/intents/{id}/claim
     - Special handling: 409 Conflict returns dict with `{"conflict": True, ...}` instead of raising exception
     - This is expected behavior when multiple workers try to claim same intent
   - `fire_intent(intent_id, report)` → POST /v1/intents/{id}/fire
   - `get_history(intent_id, limit, offset)` → GET /v1/intents/{id}/history

5. **Error Handling:**
   - Comprehensive error handling for httpx exceptions:
     - TimeoutException → IntentsNetworkError
     - NetworkError, ConnectError → IntentsNetworkError
     - HTTPError → IntentsNetworkError
     - Non-200 status codes → IntentsAPIError (except 409 on claim_intent)
   - All errors include context (intent_id, user_id, duration_ms, error details)
   - Structured logging at DEBUG (before operation), INFO (success), ERROR (failure)

6. **Logging Standards:**
   - Duration tracking (duration_ms) for all operations
   - Detailed context in all log messages (intent_id, user_id, trigger_type, etc.)
   - DEBUG level: Log before operation with parameters
   - INFO level: Log successful completion with results
   - ERROR level: Log failures with full context

7. **Health Check:**
   - `health_check()` method → GET /health
   - Returns bool (True if healthy, False otherwise)
   - Exception-safe (returns False on any error)

8. **Circuit Breaker:**
   - Deferred to IntentsManager (Story 13.2) following MemoryManager pattern
   - IntentsClient provides low-level HTTP operations
   - IntentsManager will wrap client with circuit breaker logic

9. **Langfuse Tracing:**
   - Per context guidance, @observe() decorator not added to client methods
   - Client is too granular for top-level tracing
   - Will be called from traced contexts (IntentsManager, MCP tools)
   - Duration metrics already logged for observability

**Pattern Compliance:**
- Follows MemoryClient pattern exactly (backend/api/memory_client.py)
- Same exception hierarchy structure
- Same error handling approach
- Same logging conventions
- Same async context manager pattern

**Next Steps:**
1. Add health check integration to /health/full endpoint
2. Implement IntentsManager (Story 13.2) with circuit breaker
3. Add unit tests with mocked httpx responses
4. Integration testing with running agentic-memories service

### Verification
- [ ] All CRUD methods work against agentic-memories
- [ ] Claim returns 409 on conflict
- [ ] Fire clears claim and updates counters
- [ ] Circuit breaker activates on failures
- [ ] Langfuse traces appear for all operations
