# Story 2.5: Conversation State Management

Status: drafted

## Story

**As a** user,
**I want** Annie to remember our conversation context,
**So that** I don't have to repeat information.

**Epic:** Epic 2 - Core Chat & LLM Integration
**Prerequisites:** Story 2.1 (Backend API Foundation)
**Estimated Effort:** 3 points (3 days)

## Acceptance Criteria

### AC #1: Session is created in Redis with proper structure
**Given** a user sends a message
**When** the backend processes it
**Then** a session is created in Redis with structure:
```json
{
  "user_id": "12345",
  "platform": "telegram",
  "conversation_id": "conv_abc123",
  "created_at": "2025-11-10T12:00:00Z",
  "last_activity": "2025-11-10T12:00:00Z"
}
```

**Mapped to Tasks:** Task 1, Task 2

---

### AC #2: Conversation history is retrieved from Redis
**Given** an active session exists
**When** the user sends another message
**Then** the conversation history is retrieved from Redis with all previous messages

**Mapped to Tasks:** Task 3, Task 4

---

### AC #3: LLM uses full conversation context
**Given** conversation history exists
**When** the LLM generates a response
**Then** it uses the full conversation context (up to last 20 messages or 20,000 tokens, whichever is smaller)

**Mapped to Tasks:** Task 4, Task 5

---

### AC #4: Session expires after 1 hour of inactivity
**Given** a session is inactive for 1 hour
**When** I check Redis
**Then** the session has expired (TTL enforced) and a new session is created on next message

**Mapped to Tasks:** Task 2

---

### AC #5: Conversation history API supports pagination
**Given** I want to retrieve conversation state
**When** I call `GET /api/conversations/{user_id}`
**Then** it returns conversation history with pagination support (max 50 messages per page)

**Mapped to Tasks:** Task 6

---

### AC #6: System continues when Redis connection fails
**Given** Redis connection fails
**When** a message is processed
**Then** the system continues without conversation context but logs the error

**Mapped to Tasks:** Task 7

---

### AC #7: Conversation retrieval completes within 500ms (p95)
**Given** conversation state is requested
**When** I check performance
**Then** conversation retrieval completes within 500ms (p95)

**Mapped to Tasks:** Task 8

---

## Tasks

### Task 1: Create State Management Module with Redis Client
**Status:** TODO
**Acceptance Criteria:** AC #1

**Implementation Details:**
- Create `backend/api/state.py` module
- Implement `StateManager` class with Redis connection pooling
- Initialize Redis client with configuration from environment:
  ```python
  redis_client = redis.asyncio.Redis(
      host=os.getenv("REDIS_HOST", "redis"),
      port=int(os.getenv("REDIS_PORT", 6379)),
      db=0,
      decode_responses=True,
      socket_connect_timeout=5,
      socket_timeout=5
  )
  ```
- Add connection health check method: `async def check_health() -> bool`
- Implement context manager for resource cleanup (`__aenter__`, `__aexit__`)
- Add structured logging for Redis operations
- Handle connection errors gracefully (catch `redis.exceptions.ConnectionError`)

**Technical Notes:**
- Use `redis.asyncio.Redis` for async support (same async pattern as httpx.AsyncClient)
- Connection pooling is automatic with redis-py
- Decode responses as UTF-8 strings for easier JSON handling
- Set timeouts to prevent hanging on Redis failures

---

### Task 2: Implement Session Creation and Management
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #4

**Implementation Details:**
- Add method to `StateManager`: `async def create_session(user_id: str, platform: str) -> dict`
- Generate unique conversation ID: `conv_{uuid.uuid4().hex[:16]}`
- Create session structure:
  ```python
  session = {
      "user_id": user_id,
      "platform": platform,
      "conversation_id": conversation_id,
      "created_at": datetime.now(timezone.utc).isoformat(),
      "last_activity": datetime.now(timezone.utc).isoformat(),
      "message_count": 0
  }
  ```
- Store in Redis with key: `session:{user_id}`
- Set TTL to 3600 seconds (1 hour): `redis.setex(key, 3600, json.dumps(session))`
- Add method: `async def get_session(user_id: str) -> Optional[dict]`
  - Returns session if exists, None if expired/not found
- Add method: `async def update_session_activity(user_id: str) -> None`
  - Update `last_activity` timestamp
  - Reset TTL to 3600 seconds
  - Increment `message_count`
- Add structured logging for session lifecycle events

**Technical Notes:**
- Use ISO 8601 format for timestamps (same as elsewhere in project)
- Redis key pattern: `session:{user_id}` for easy querying
- TTL automatically expires sessions after 1 hour of inactivity
- JSON serialization for complex objects

---

### Task 3: Implement Conversation History Storage
**Status:** TODO
**Acceptance Criteria:** AC #2

**Implementation Details:**
- Add method: `async def add_message(conversation_id: str, message: dict) -> None`
- Message structure:
  ```python
  {
      "role": str,  # "user" | "assistant" | "system" | "tool"
      "content": str,
      "timestamp": datetime.now(timezone.utc).isoformat(),
      "tool_calls": []  # Optional: for function calling results
  }
  ```
- Store messages in Redis List: `conversation:{conversation_id}`
- Use `RPUSH` to append messages to list
- Set TTL to 1800 seconds (30 minutes) on first message
- Update TTL on each new message to keep conversation alive
- Add method: `async def get_conversation_history(conversation_id: str, limit: int = 20) -> List[dict]`
  - Retrieve last N messages using `LRANGE conversation:{conversation_id} -limit -1`
  - Default limit is 20 messages (for LLM context)
  - Parse JSON for each message
  - Return in chronological order (oldest first)

**Technical Notes:**
- Redis List is perfect for ordered message storage
- LRANGE with negative indices gets last N items efficiently
- 30-minute TTL prevents stale conversations from consuming memory
- Consider using Redis Streams in future for more advanced features

---

### Task 4: Implement Context Building for LLM
**Status:** TODO
**Acceptance Criteria:** AC #2, AC #3

**Implementation Details:**
- Add method: `async def build_llm_context(conversation_id: str) -> List[dict]`
- Retrieve last 20 messages from conversation history
- Calculate total token count using simple heuristic: `sum(len(msg["content"]) // 4 for msg in messages)`
- If token count > 20000:
  - Truncate from the beginning (keep most recent context)
  - Always keep system message if present
  - Recalculate until under 20000 tokens
- Return messages in format expected by LLMClient:
  ```python
  [
      {"role": "system", "content": "You are Annie, a helpful AI companion..."},
      {"role": "user", "content": "What's the weather?"},
      {"role": "assistant", "content": "Let me check for you..."}
  ]
  ```
- Add structured logging with context size metrics

**Technical Notes:**
- Token counting heuristic: ~4 characters per token (GPT models)
- For exact token counting, use tiktoken library (future enhancement)
- LLM context should include system prompt + conversation history
- Truncation preserves conversation coherence by keeping recent messages
- 20 message limit prevents excessive context, 20k token limit handles long messages
- Typical conversation: ~10-15 exchanges fits comfortably within limits

---

### Task 5: Integrate State Management into Chat Endpoint
**Status:** TODO
**Acceptance Criteria:** AC #3

**Implementation Details:**
- Modify `backend/api/routes/chat.py` to use `StateManager`
- On POST /api/chat:
  1. Extract user_id and platform from request
  2. Check if session exists: `session = await state_manager.get_session(user_id)`
  3. If no session: `session = await state_manager.create_session(user_id, platform)`
  4. If session exists: `await state_manager.update_session_activity(user_id)`
  5. Add user message to conversation history: `await state_manager.add_message(conversation_id, user_message)`
  6. Build LLM context: `messages = await state_manager.build_llm_context(conversation_id)`
  7. Pass context to LLM client
  8. After LLM response, add assistant message to history
- Return conversation_id in response for streaming endpoint
- Add error handling for Redis failures (graceful degradation)

**Technical Notes:**
- StateManager should be initialized once at app startup (dependency injection)
- Use FastAPI's dependency injection: `state: StateManager = Depends(get_state_manager)`
- Preserve existing streaming functionality from Story 2.3
- Conversation context replaces hard-coded test messages

---

### Task 6: Implement Conversation History API Endpoint
**Status:** TODO
**Acceptance Criteria:** AC #5

**Implementation Details:**
- Create new endpoint in `backend/api/routes/chat.py`: `GET /api/conversations/{user_id}`
- Query parameters:
  - `page`: int (default: 1)
  - `limit`: int (default: 50, max: 50)
- Implementation:
  1. Get session for user_id
  2. If no session: return 404 with error message
  3. Calculate offset: `offset = (page - 1) * limit`
  4. Retrieve conversation history with pagination
  5. Get total message count: `LLEN conversation:{conversation_id}`
  6. Return response:
     ```python
     {
         "user_id": user_id,
         "conversation_id": conversation_id,
         "messages": [...],
         "pagination": {
             "page": page,
             "limit": limit,
             "total": total_messages,
             "has_more": (offset + limit) < total_messages
         }
     }
     ```
- Add OpenAPI documentation for endpoint
- Add structured logging

**Technical Notes:**
- Pagination prevents large responses for long conversations
- Use Redis LRANGE with calculated offsets
- Return has_more flag for client-side pagination UI
- Include conversation metadata (created_at, last_activity) in response

---

### Task 7: Error Handling and Graceful Degradation
**Status:** TODO
**Acceptance Criteria:** AC #6

**Implementation Details:**
- Wrap all Redis operations in try/except blocks
- Catch specific exceptions:
  - `redis.exceptions.ConnectionError` - Redis unavailable
  - `redis.exceptions.TimeoutError` - Operation timeout
  - `redis.exceptions.RedisError` - General Redis errors
- On Redis failure:
  - Log error with full context (operation, user_id, conversation_id)
  - Return None for get operations (treated as no session/history)
  - Skip storage operations (continue without persistence)
  - Set health check flag to degraded
- Modify chat endpoint to handle None session gracefully:
  - If session creation fails: proceed with empty context
  - Log warning about degraded mode
  - User still receives LLM response (without conversation memory)
- Add health check endpoint integration:
  - Update `/health/detailed` to include Redis status
  - Mark as "degraded" if Redis unavailable

**Technical Notes:**
- Graceful degradation ensures Annie remains functional even if Redis fails
- Users experience stateless chat (no memory) rather than complete failure
- Alert/monitoring should trigger on Redis failures
- Consider circuit breaker pattern for repeated failures

---

### Task 8: Performance Optimization and Monitoring
**Status:** TODO
**Acceptance Criteria:** AC #7

**Implementation Details:**
- Add timing instrumentation to all Redis operations:
  ```python
  start_time = time.time()
  result = await redis_client.get(key)
  duration_ms = int((time.time() - start_time) * 1000)
  logger.info("Redis GET completed", extra={"key": key, "duration_ms": duration_ms})
  ```
- Track metrics:
  - Session creation time (target: <1000ms)
  - Conversation retrieval time (target: <500ms p95)
  - Message append time (target: <200ms)
- Optimization strategies:
  - Use connection pooling (default with redis.asyncio)
  - Batch operations where possible
  - Use Redis pipelining for multiple commands
  - Keep message payloads small (no large attachments)
- Add performance logging to identify slow operations
- Set up alerts for p95 > 500ms

**Technical Notes:**
- Redis is fast - most operations should complete in <100ms on local network
- If performance degrades, check:
  - Network latency between backend and Redis
  - Redis memory usage (swapping to disk)
  - Redis command queue depth
- Consider Redis Cluster for horizontal scaling in production

---

### Task 9: Unit and Integration Tests
**Status:** TODO
**Acceptance Criteria:** All ACs

**Implementation Details:**
- Create `backend/tests/unit/test_state.py` for StateManager tests
- Create `backend/tests/integration/test_conversation_e2e.py` for end-to-end tests
- Test coverage:
  - **Unit Tests**:
    - Test session creation with proper structure
    - Test session retrieval and expiration
    - Test message storage and retrieval
    - Test context building with 20 message / 20k token limits
    - Test truncation for long messages exceeding 20k tokens
    - Test error handling (Redis failures)
    - Mock Redis responses
  - **Integration Tests**:
    - Test full conversation flow (multiple messages)
    - Test session TTL expiration (mock time)
    - Test conversation history API with pagination
    - Test graceful degradation (Redis down)
    - Test performance requirements (<500ms p95)
    - Use real Redis container or fakeredis for deterministic tests
- Use pytest-asyncio for async test support
- Mock Redis with fakeredis library or use Docker Redis container
- Target: >80% code coverage for state management module

**Technical Notes:**
- fakeredis library provides in-memory Redis for fast unit tests
- For integration tests, use Docker Compose test profile
- Test edge cases: empty conversations, very long conversations, expired sessions
- Verify TTL behavior with time mocking

---

### Task 10: Documentation and Integration Updates
**Status:** TODO
**Acceptance Criteria:** All ACs

**Implementation Details:**
- Add docstrings to `StateManager` class and all methods
- Document Redis key patterns in module docstring:
  ```
  Redis Key Patterns:
  - session:{user_id} -> Session data (JSON, TTL: 1 hour)
  - conversation:{conversation_id} -> Message list (JSON array, TTL: 30 min)
  ```
- Update `backend/api/routes/stream.py` to use conversation context from Redis
- Remove hard-coded test messages
- Update CLAUDE.md with state management details
- Add environment variables to env.example:
  - REDIS_HOST (default: redis)
  - REDIS_PORT (default: 6379)
- Add structured logging:
  - Session lifecycle events: `{"event":"session_created","user_id":"...","conversation_id":"..."}`
  - Message events: `{"event":"message_added","conversation_id":"...","role":"user"}`
  - Performance metrics: `{"event":"redis_operation","operation":"get","duration_ms":...}`
- Document state management flow in code comments

**Technical Notes:**
- Use `get_logger(__name__)` for structured logging (established in Epic 1)
- Log at INFO level for normal operations, ERROR for failures
- Include conversation_id in all log entries for tracing
- State management is foundation for Epic 3 (Memory Integration)

---

## Definition of Done

- [ ] All 10 tasks completed
- [ ] All 7 acceptance criteria validated with evidence
- [ ] State management module created (`backend/api/state.py`)
- [ ] Redis client configured with connection pooling and error handling
- [ ] Session creation and management implemented with TTL
- [ ] Conversation history storage implemented with Redis Lists
- [ ] Context building for LLM with limits (20 messages or 20,000 tokens)
- [ ] Chat endpoint integrated with state management
- [ ] Conversation history API endpoint created with pagination
- [ ] Error handling for Redis failures with graceful degradation
- [ ] Performance requirements met (<500ms p95 for retrieval, <1000ms for session creation)
- [ ] Unit tests created and passing (`backend/tests/unit/test_state.py`)
- [ ] Integration tests created and passing (`backend/tests/integration/test_conversation_e2e.py`)
- [ ] Code coverage >80% for state management module
- [ ] Documentation and structured logging implemented
- [ ] Code reviewed and approved
- [ ] No regressions in existing functionality (Story 2.1-2.4 tests still pass)

---

## Learnings from Previous Story

**From Story 2.4: Function Calling for MCP Tools (Status: done)**

**New Patterns/Services Created:**
- **MCP Client Module**: Created `backend/api/mcp_client.py` (378 lines) with async JSON-RPC 2.0 support
  - Use `MCPClient` class with async context manager pattern (`async with MCPClient()`)
  - Custom exception hierarchy: `MCPClientError`, `MCPNetworkError`, `MCPToolError` for granular error handling
  - Tool schema caching with 5-minute TTL - apply same pattern for Redis operations if beneficial
  - httpx.AsyncClient with connection pooling - same async HTTP pattern to follow

**Architectural Patterns Established:**
- Async context managers for resource cleanup (`__aenter__`, `__aexit__`)
- Structured logging with extra fields: `logger.info("message", extra={"key": "value", "duration_ms": ...})`
- Performance monitoring with duration tracking: `start_time = time.time()` → `duration_ms = int((time.time() - start_time) * 1000)`
- Custom exception classes for domain-specific errors
- Configuration loading from environment via `get_config()`

**Files to Reuse/Extend:**
- `backend/api/llm_client.py` - Will use conversation context from Redis instead of hard-coded messages
- `backend/api/routes/stream.py` - Update to load conversation history before calling LLM
- `backend/api/routes/chat.py` - Integrate state management for session handling
- `backend/api/config.py` - Add Redis configuration (REDIS_HOST, REDIS_PORT)
- `backend/api/logging.py` - Use for state management logging

**Testing Patterns:**
- pytest-asyncio for async tests
- AsyncMock for mocking async methods: `mock_method = AsyncMock(return_value=...)`
- Context manager mocking: `MockClass.return_value.__aenter__.return_value = mock_instance`
- Comprehensive error scenario testing (network failures, timeouts, edge cases)
- 100% test pass rate achieved - maintain this standard

**Technical Debt:**
- None carried forward to this story

**Recommendations for This Story:**
- Follow same async/await patterns as MCPClient for StateManager (Redis client)
- Use similar custom exception hierarchy for state errors (StateError, RedisConnectionError, etc.)
- Apply same structured logging pattern with duration tracking
- Use async context manager for Redis connection management
- Test both success and failure paths comprehensively
- Monitor performance metrics from day 1 (500ms p95 target)

[Source: .bmad-ephemeral/stories/2-4-function-calling-mcp-tools.md#Dev-Agent-Record]

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **State Manager** (`backend/api/state.py`): New module for Redis-based conversation state management
- **Redis**: Data store for sessions and conversation history (existing service from Epic 1)
- **Chat Endpoint** (`backend/api/routes/chat.py`): Extended to create/manage sessions
- **Stream Endpoint** (`backend/api/routes/stream.py`): Extended to use conversation context

**Data Flow:**
```
1. User → POST /api/chat (first message)
2. Backend → StateManager.get_session(user_id) → None (no session)
3. Backend → StateManager.create_session(user_id, platform)
4. Redis ← SET session:{user_id} {session_data} EX 3600
5. Backend → StateManager.add_message(conversation_id, user_message)
6. Redis ← RPUSH conversation:{conversation_id} {message_json}
7. Backend → StateManager.build_llm_context(conversation_id)
8. Redis → LRANGE conversation:{conversation_id} -20 -1 (last 20 messages, check 20k token limit)
9. Backend → LLMClient.chat_completion_stream(messages=context)
10. Backend → StateManager.add_message(conversation_id, assistant_message)
11. User receives streamed response

Subsequent messages:
1. User → POST /api/chat (second message)
2. Backend → StateManager.get_session(user_id) → session (exists)
3. Backend → StateManager.update_session_activity(user_id)
4. Redis ← SET session:{user_id} {updated_session} EX 3600 (reset TTL)
5-11. [Same as above, but with accumulated conversation history]
```

**Redis Data Structures:**

Session (String with JSON):
```
Key: session:{user_id}
Value: {"user_id":"12345","platform":"telegram","conversation_id":"conv_abc123","created_at":"2025-11-11T10:00:00Z","last_activity":"2025-11-11T10:05:00Z","message_count":5}
TTL: 3600 seconds (1 hour)
```

Conversation History (List):
```
Key: conversation:{conversation_id}
Value: [
  '{"role":"user","content":"Hello","timestamp":"2025-11-11T10:00:00Z"}',
  '{"role":"assistant","content":"Hi! How can I help?","timestamp":"2025-11-11T10:00:05Z"}',
  ...
]
TTL: 1800 seconds (30 minutes)
```

### Technical Constraints

1. **Conversation Context Limits**: Max 20 messages OR 20,000 tokens (whichever is smaller)
   - Retrieve last 20 messages from Redis
   - Calculate token count, truncate from beginning if > 20k tokens
   - Always preserve system message
   - Use simple token estimation: ~4 chars per token

2. **Session TTL**: 1 hour inactivity timeout
   - Automatically expires in Redis
   - Creates new session on next message
   - Prevents memory bloat

3. **Performance Requirements**:
   - Conversation retrieval: <500ms (p95)
   - Session creation: <1000ms
   - Message append: <200ms
   - All operations async/non-blocking

4. **Graceful Degradation**: Continue without Redis
   - Stateless mode (no conversation memory)
   - Log errors but don't crash
   - Update health check to "degraded"

### Dependencies

**New Python Dependencies:**
- `redis>=5.0.0` - Async Redis client with connection pooling
- `fakeredis>=2.20.0` - Redis mock for unit tests (dev dependency)

Add to `backend/requirements.txt`:
```
redis>=5.0.0
```

Add to `backend/requirements-dev.txt`:
```
fakeredis>=2.20.0
pytest-asyncio>=0.21.0  # Already added in Story 2.2
```

**Existing Dependencies (Epic 1):**
- Redis 7.2 container (port 6379)
- Docker Compose service orchestration

**Infrastructure:**
- Redis configured with AOF persistence (already set up in Epic 1)
- Redis memory limit: 256MB (configured in docker-compose.yml)

### Key Files to Create/Modify

**New Files:**
- `backend/api/state.py` - State management module with StateManager class
- `backend/tests/unit/test_state.py` - Unit tests for state management
- `backend/tests/integration/test_conversation_e2e.py` - End-to-end conversation tests

**Files to Modify:**
- `backend/api/routes/chat.py` - Integrate session creation and management
- `backend/api/routes/stream.py` - Use conversation context from Redis instead of hard-coded messages
- `backend/requirements.txt` - Add redis>=5.0.0
- `backend/requirements-dev.txt` - Add fakeredis>=2.20.0

**Reference Files:**
- `.bmad-ephemeral/stories/tech-spec-epic-2.md` - Epic 2 technical specification
  - Lines 97-110: Session Model and Conversation History Model
  - Lines 250-273: GET /api/conversations endpoint spec
  - Lines 431-454: Session Management Flow
  - Lines 468-469: Performance requirements (Note: Relaxed to 500ms p95 in this story)
  - Note: Context limits adjusted to 20 messages or 20k tokens (more practical than spec's 4k)
  - Lines 917-953: Story 2.5 acceptance criteria (AC 2.5.1-2.5.7)
  - Lines 1024-1030: Traceability mapping for Story 2.5
- `.bmad-ephemeral/stories/2-4-function-calling-mcp-tools.md` - Previous story (async patterns)
- `docs/epics-and-stories.md` - Epic breakdown (lines 407-445: Story 2.5)
- `docs/02-architecture/ARCHITECTURE_PLAN.md` - System architecture
- `CLAUDE.md` - Redis configuration details

### Testing Strategy

**Unit Tests** (Fast, Deterministic):
- Test session creation with proper structure
- Test session retrieval and expiration (mock TTL)
- Test message storage and retrieval
- Test context building with 20 message / 20k token limits
- Test truncation logic for messages exceeding 20k tokens
- Test error handling (Redis connection failures, timeouts)
- Mock Redis with fakeredis library
- Target: <1s per test, >80% code coverage

**Integration Tests** (Slower, Real Integrations):
- Test full multi-message conversation flow
- Test session TTL expiration (use fakeredis with time mocking)
- Test conversation history API with pagination
- Test graceful degradation (Redis down scenario)
- Test performance requirements (500ms p95 retrieval)
- Use Docker Redis container or fakeredis
- Test with both empty and populated conversations

**Performance Validation:**
- Measure conversation retrieval time (target: 500ms p95)
- Measure session creation time (target: 1000ms)
- Measure message append time (target: 200ms)
- Load test with 100 concurrent users
- Monitor Redis memory usage

### Implementation Approach

**Phase 1: State Manager Foundation (Task 1, Task 2)**
1. Create `StateManager` class with Redis client
2. Implement session creation and management
3. Add health check and error handling
4. Test with unit tests (fakeredis)

**Phase 2: Conversation Storage (Task 3, Task 4)**
1. Implement message storage in Redis Lists
2. Implement conversation history retrieval
3. Implement context building with token limits
4. Test truncation and limits

**Phase 3: Chat Integration (Task 5)**
1. Modify chat endpoint to use StateManager
2. Create/update sessions on each request
3. Build LLM context from conversation history
4. Store assistant responses
5. Test end-to-end flow

**Phase 4: History API (Task 6)**
1. Create conversation history endpoint
2. Implement pagination logic
3. Add OpenAPI documentation
4. Test with multiple pages

**Phase 5: Error Handling & Performance (Task 7, Task 8)**
1. Add comprehensive error handling
2. Implement graceful degradation
3. Add performance monitoring
4. Optimize Redis operations
5. Test failure scenarios

**Phase 6: Testing & Documentation (Task 9, Task 10)**
1. Create comprehensive unit tests
2. Create integration tests
3. Update documentation
4. Update streaming endpoint to use Redis context
5. Code review and validation

### Success Metrics

- ✅ All 7 acceptance criteria implemented and validated
- ✅ Session management: TTL enforced, proper structure
- ✅ Conversation persistence: Messages stored and retrieved
- ✅ Context limits: 20 messages or 20,000 tokens enforced
- ✅ Performance: <500ms p95 retrieval, <1000ms session creation
- ✅ Graceful degradation: System continues when Redis fails
- ✅ Pagination: Conversation history API works correctly
- ✅ Test coverage: >80% for state management module
- ✅ Zero regressions in Story 2.1-2.4 functionality

---

## References

1. **Epic 2 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-2.md`)
   - Lines 97-110: Session Model and Conversation History Model (data structures)
   - Lines 250-273: GET /api/conversations endpoint specification
   - Lines 431-454: Session Management Flow (detailed workflow)
   - Lines 468-469: Performance requirements (relaxed to 500ms p95, 1000ms session creation)
   - Lines 917-953: Story 2.5 acceptance criteria (AC 2.5.1-2.5.7)
   - Lines 1024-1030: Traceability mapping for Story 2.5

2. **Story 2.4: Function Calling for MCP Tools** (`.bmad-ephemeral/stories/2-4-function-calling-mcp-tools.md`)
   - Async patterns with httpx.AsyncClient and context managers
   - Custom exception hierarchy for error handling
   - Structured logging patterns
   - Performance monitoring techniques
   - Testing patterns with pytest-asyncio

3. **Epic & Story Breakdown** (`docs/epics-and-stories.md`)
   - Lines 407-445: Story 2.5 user story and acceptance criteria

4. **Architecture Plan** (`docs/02-architecture/ARCHITECTURE_PLAN.md`)
   - Backend API service architecture
   - Redis integration patterns
   - State management component design

5. **Project Instructions** (`CLAUDE.md`)
   - Redis configuration (REDIS_HOST, REDIS_PORT)
   - Docker Compose service setup
   - Environment variable patterns

---

**Created:** 2025-11-11
**Epic:** Epic 2 - Core Chat & LLM Integration
**Story:** 2.5 - Conversation State Management
**Status:** drafted

---

## Dev Agent Record

### Context Reference

**Story Context XML:** `.bmad-ephemeral/stories/2-5-conversation-state-management.context.xml`

Generated: 2025-11-11
Generated by: story-context workflow
Contains: Architecture details, Redis data structures, implementation patterns, testing strategy, learnings from Story 2.4

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

### Completion Notes List

### File List
