# Story 3.1: Memory Storage Integration

Status: done

## Story

**As a** user,
**I want** Annie to remember our conversations and decisions,
**So that** future advice is personalized based on my history.

**Epic:** Epic 3 - Memory & Persistence
**Prerequisites:** Story 2.4 (Function Calling for MCP Tools), Story 1.6 (MCP Server Foundation)
**Estimated Effort:** 3 points (2.5 days)

## Acceptance Criteria

### AC #1: Conversation context stored when conversation ends
**Given** agentic-memories service is available
**When** a conversation ends (user sends "thanks" or conversation times out)
**Then** conversation context is stored via `store_memory` tool with:
- user_id
- conversation summary
- key decisions made
- user preferences expressed
- timestamp

**Mapped to Tasks:** Task 1, Task 2, Task 3

---

### AC #2: Memory stored with proper structure in agentic-memories
**Given** memory storage is triggered
**When** I check agentic-memories
**Then** the conversation is stored with proper structure and can be retrieved later

**Mapped to Tasks:** Task 1, Task 2

---

### AC #3: System continues when agentic-memories is down (graceful degradation)
**Given** agentic-memories service is down
**When** a conversation ends
**Then** the system continues without error, logs the failure, and stores memory in Redis temporarily for retry

**Mapped to Tasks:** Task 4, Task 5

---

### AC #4: User informed when memory storage fails
**Given** memory storage fails
**When** I send another message
**Then** Annie continues working without memory context but informs the user: "Note: I'm having trouble accessing your memory right now, but I can still help."

**Mapped to Tasks:** Task 4

---

### AC #5: Memory includes decision context, preferences, and outcomes
**Given** memory is stored
**When** I check the stored data
**Then** it includes:
- Decision context (what decision was made, options considered)
- User preferences (risk tolerance, priorities)
- Conversation flow (key topics discussed)
- Outcomes (if user provides feedback)

**Mapped to Tasks:** Task 2, Task 3

---

### AC #6: Memory storage completes within 500ms (p95)
**Given** memory storage is triggered
**When** I check performance
**Then** memory storage completes within 500ms (p95)

**Mapped to Tasks:** Task 6

---

## Tasks / Subtasks

### Task 1: Create agentic-memories HTTP Client Module
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #2

**Implementation Details:**
- Create `backend/api/memory_client.py` module
- Implement `MemoryClient` class with async HTTP client (httpx.AsyncClient)
- Initialize client with configuration from environment:
  ```python
  client = httpx.AsyncClient(
      base_url=os.getenv("AGENTIC_MEMORIES_URL"),
      timeout=httpx.Timeout(5.0),
      headers={"Content-Type": "application/json"}
  )
  ```
- Implement methods:
  - `async def store_memory(user_id: str, memory: dict) -> dict` - POST /memories
  - `async def health_check() -> bool` - GET /health
- Use async context manager pattern (`__aenter__`, `__aexit__`) for resource cleanup
- Add structured logging for all operations
- Handle connection errors gracefully (catch `httpx.HTTPError`)
- Custom exception hierarchy: `MemoryClientError`, `MemoryNetworkError`, `MemoryAPIError`

**Technical Notes:**
- Follow same async patterns as `MCPClient` from Story 2.4
- Use connection pooling (automatic with httpx.AsyncClient)
- Set timeouts to prevent hanging (5s for storage operations)
- Reuse structured logging patterns from `backend/api/logging.py`

**Subtasks:**
- [ ] Create `MemoryClient` class skeleton with __init__
- [ ] Implement async context manager (__aenter__, __aaexit__)
- [ ] Implement store_memory method
- [ ] Implement health_check method
- [ ] Add custom exception classes
- [ ] Add structured logging
- [ ] Add unit tests with mocked httpx responses

---

### Task 2: Implement store_memory MCP Tool
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #2, AC #5

**Implementation Details:**
- Add `store_memory` tool to `mcp_server/tools.py`
- Tool schema (JSON-RPC 2.0):
  ```python
  {
      "name": "store_memory",
      "description": "Store conversation memory in agentic-memories service",
      "inputSchema": {
          "type": "object",
          "properties": {
              "user_id": {"type": "string", "description": "User identifier"},
              "conversation_summary": {"type": "string", "description": "Summary of conversation"},
              "decisions": {
                  "type": "array",
                  "items": {
                      "type": "object",
                      "properties": {
                          "decision": {"type": "string"},
                          "options_considered": {"type": "array", "items": {"type": "string"}},
                          "reasoning": {"type": "string"},
                          "outcome": {"type": "string", "nullable": True}
                      }
                  }
              },
              "preferences": {
                  "type": "object",
                  "properties": {
                      "risk_tolerance": {"type": "string", "nullable": True},
                      "priorities": {"type": "array", "items": {"type": "string"}},
                      "constraints": {"type": "array", "items": {"type": "string"}}
                  }
              },
              "topics": {"type": "array", "items": {"type": "string"}},
              "sentiment": {"type": "string", "nullable": True}
          },
          "required": ["user_id", "conversation_summary"]
      }
  }
  ```
- Implementation calls `MemoryClient.store_memory()`
- Return success/failure response in JSON-RPC format
- Add retry logic with exponential backoff (3 retries, 1s/2s/4s delays)
- Log all operations with duration tracking

**Technical Notes:**
- Register tool with MCP server tool registry
- Tool callable from LLM via function calling (Story 2.4 pattern)
- Memory object follows schema from tech-spec-epic-3.md lines 205-231
- Use same error handling patterns as other MCP tools

**Subtasks:**
- [ ] Define tool schema in tools.py
- [ ] Implement store_memory function
- [ ] Add retry logic with exponential backoff
- [ ] Register tool with MCP server
- [ ] Add structured logging
- [ ] Test tool via docker exec pattern
- [ ] Add integration test with mocked agentic-memories

---

### Task 3: Implement Conversation Summarization Logic
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #5

**Implementation Details:**
- Add `MemoryManager` class to `backend/api/memory.py`
- Implement method: `async def summarize_conversation(conversation_history: List[dict]) -> dict`
- Use LLM to generate conversation summary:
  ```python
  summary_prompt = """
  Analyze this conversation and extract:
  1. Conversation summary (2-3 sentences)
  2. Key decisions made (with options considered and reasoning)
  3. User preferences expressed (risk tolerance, priorities, constraints)
  4. Main topics discussed
  5. Overall sentiment (positive/neutral/negative)

  Conversation:
  {conversation_history}

  Return structured JSON matching the memory schema.
  """
  ```
- Call LLM non-streaming endpoint for analysis
- Parse LLM response into structured Memory Object
- Validate required fields (user_id, conversation_summary)
- Add fallback for parsing errors (simple heuristic summarization)

**Technical Notes:**
- Reuse `LLMClient` from Story 2.2
- Use gpt-4 model for better analysis (if available), fallback to grok-4
- Summary generation should complete within 3 seconds
- Cache summaries to avoid re-summarizing (use conversation_id as key)

**Subtasks:**
- [ ] Create MemoryManager class
- [ ] Implement summarize_conversation method
- [ ] Add LLM prompt for summarization
- [ ] Implement response parsing
- [ ] Add validation logic
- [ ] Add fallback heuristic summarization
- [ ] Test with sample conversations
- [ ] Add performance monitoring

---

### Task 4: Add Graceful Degradation with Redis Fallback
**Status:** TODO
**Acceptance Criteria:** AC #3, AC #4

**Implementation Details:**
- Extend `MemoryManager` to handle agentic-memories failures
- Implement Redis fallback queue:
  ```python
  async def store_memory_with_fallback(memory: dict) -> bool:
      try:
          # Try agentic-memories first
          await memory_client.store_memory(user_id, memory)
          return True
      except MemoryNetworkError:
          # Store in Redis fallback queue
          await redis_client.rpush(
              f"memory_queue:{user_id}",
              json.dumps(memory)
          )
          logger.warning("Memory stored in Redis fallback queue",
                        extra={"user_id": user_id})
          return False
  ```
- Implement retry worker (background task):
  - Check fallback queue every 5 minutes
  - Attempt to flush queued memories to agentic-memories
  - Remove from queue on success, keep on failure
  - Log retry attempts and success/failure rates
- Add user notification when memory unavailable:
  - Return flag `memory_available: false` in response
  - Frontend/bot displays: "Note: I'm having trouble accessing your memory right now, but I can still help."

**Technical Notes:**
- Reuse `StateManager` Redis patterns from Story 2.5
- Redis fallback queue uses List data structure (same as conversation history)
- Background retry worker runs in separate asyncio task
- Set TTL on fallback queue (24 hours) to prevent indefinite accumulation
- Circuit breaker pattern: After 5 consecutive failures, stop trying for 15 minutes

**Subtasks:**
- [ ] Implement store_memory_with_fallback method
- [ ] Create Redis fallback queue structure
- [ ] Implement background retry worker
- [ ] Add circuit breaker logic
- [ ] Add user notification flag
- [ ] Test failure scenarios
- [ ] Test retry worker
- [ ] Monitor fallback queue size

---

### Task 5: Integrate Memory Storage into Chat Flow
**Status:** TODO
**Acceptance Criteria:** AC #3, AC #4

**Implementation Details:**
- Modify `backend/api/routes/chat.py` to trigger memory storage
- Detect conversation end triggers:
  - User sends farewell message ("thanks", "bye", "goodbye", etc.)
  - Conversation timeout (30 minutes since last message)
  - Explicit end signal from user
- On conversation end:
  1. Retrieve full conversation history from Redis
  2. Call `MemoryManager.summarize_conversation()`
  3. Call `MemoryManager.store_memory_with_fallback()`
  4. Log success/failure
  5. Clear conversation from Redis (optional - conversation TTL handles this)
- Add background task for timeout detection:
  - Check active sessions every 5 minutes
  - Identify sessions with last_activity > 30 minutes ago
  - Trigger memory storage for timed-out sessions
- Handle concurrent requests (prevent duplicate storage)

**Technical Notes:**
- Memory storage is async and non-blocking (don't wait for completion)
- Use asyncio.create_task() to run storage in background
- Farewell detection: Simple keyword matching (case-insensitive)
- Conversation timeout worker runs independently
- Add distributed lock (Redis) to prevent duplicate storage

**Subtasks:**
- [ ] Implement conversation end detection
- [ ] Add memory storage trigger in chat endpoint
- [ ] Implement background timeout worker
- [ ] Add distributed lock for duplicate prevention
- [ ] Test farewell detection
- [ ] Test timeout worker
- [ ] Test concurrent requests
- [ ] Monitor memory storage success rate

---

### Task 6: Performance Optimization and Monitoring
**Status:** TODO
**Acceptance Criteria:** AC #6

**Implementation Details:**
- Add timing instrumentation to all memory operations:
  ```python
  start_time = time.time()
  await memory_client.store_memory(user_id, memory)
  duration_ms = int((time.time() - start_time) * 1000)
  logger.info("Memory stored", extra={
      "user_id": user_id,
      "duration_ms": duration_ms,
      "memory_size_bytes": len(json.dumps(memory))
  })
  ```
- Track metrics:
  - Memory storage time (target: <500ms p95)
  - Conversation summarization time (target: <3s)
  - Redis fallback queue size
  - Retry success rate
  - Memory size distribution
- Optimization strategies:
  - Compress large memories (gzip JSON for >10KB)
  - Batch retry operations (process multiple queued memories at once)
  - Cache conversation summaries (avoid re-summarizing)
  - Use connection pooling (httpx handles this)
  - Limit conversation history size for summarization (max 50 messages)
- Set up alerts for:
  - p95 > 500ms (performance degradation)
  - Fallback queue size > 100 (service outage)
  - Retry failure rate > 50% (agentic-memories issue)

**Technical Notes:**
- Performance target: 500ms p95 for end-to-end storage
- Breakdown: LLM summarization (~2s) + HTTP POST (~300ms) + processing (~200ms)
- Most time spent on LLM summarization - optimize by caching
- Network latency depends on agentic-memories deployment
- Monitor agentic-memories API response times

**Subtasks:**
- [ ] Add timing instrumentation
- [ ] Track performance metrics
- [ ] Implement compression for large memories
- [ ] Optimize summarization caching
- [ ] Set up performance alerts
- [ ] Load test with 100 concurrent storage operations
- [ ] Identify and optimize bottlenecks
- [ ] Document performance characteristics

---

### Task 7: Unit and Integration Tests
**Status:** TODO
**Acceptance Criteria:** All ACs

**Implementation Details:**
- Create `backend/tests/unit/test_memory_client.py` for MemoryClient tests
- Create `backend/tests/unit/test_memory_manager.py` for MemoryManager tests
- Create `backend/tests/integration/test_memory_storage_e2e.py` for end-to-end tests
- Create `mcp_server/tests/test_store_memory_tool.py` for MCP tool tests
- Test coverage:
  - **Unit Tests**:
    - Test MemoryClient.store_memory with success/failure scenarios
    - Test MemoryClient error handling (network errors, API errors)
    - Test MemoryManager.summarize_conversation with sample conversations
    - Test memory schema validation
    - Test Redis fallback logic
    - Test retry logic with exponential backoff
    - Mock httpx responses and LLM calls
  - **Integration Tests**:
    - Test full memory storage flow (conversation → summary → storage)
    - Test graceful degradation (agentic-memories down)
    - Test Redis fallback and retry worker
    - Test conversation end detection (farewell keywords, timeout)
    - Test concurrent storage requests
    - Test performance requirements (<500ms p95)
    - Use mocked agentic-memories API (httpretty or respx)
  - **MCP Tool Tests**:
    - Test store_memory tool via docker exec
    - Test tool schema validation
    - Test tool error responses
- Use pytest-asyncio for async test support
- Mock external services (agentic-memories, LLM) for deterministic tests
- Target: >80% code coverage for memory modules

**Technical Notes:**
- Use respx library for mocking httpx requests (cleaner than httpretty)
- Mock LLM responses with pre-generated summaries
- Test both success and failure paths comprehensively
- Verify structured logging output
- Test edge cases: empty conversations, very long conversations, malformed data

**Subtasks:**
- [ ] Write unit tests for MemoryClient
- [ ] Write unit tests for MemoryManager
- [ ] Write MCP tool tests
- [ ] Write integration tests for full flow
- [ ] Write graceful degradation tests
- [ ] Write performance tests
- [ ] Achieve >80% code coverage
- [ ] All tests passing

---

### Task 8: Documentation and Integration Updates
**Status:** TODO
**Acceptance Criteria:** All ACs

**Implementation Details:**
- Add docstrings to `MemoryClient`, `MemoryManager`, and `store_memory` tool
- Document memory storage flow in module docstrings:
  ```
  Memory Storage Flow:
  1. Conversation ends (farewell or timeout)
  2. Retrieve conversation history from Redis
  3. LLM summarizes conversation → Memory Object
  4. Store Memory Object via agentic-memories HTTP API
  5. On failure: Store in Redis fallback queue for retry
  ```
- Update CLAUDE.md with memory storage details
- Add environment variables to env.example:
  - AGENTIC_MEMORIES_URL (required)
  - MEMORY_STORAGE_ENABLED (default: true)
  - MEMORY_RETRY_INTERVAL_SECONDS (default: 300)
- Add structured logging documentation:
  - Memory storage events: `{"event":"memory_stored","user_id":"...","memory_id":"...","duration_ms":...}`
  - Fallback events: `{"event":"memory_fallback","user_id":"...","reason":"..."}`
  - Retry events: `{"event":"memory_retry","user_id":"...","attempt":...,"success":...}`
- Document Memory Object schema in code comments
- Add API documentation for memory storage configuration
- Update tech-spec-epic-3.md with implementation notes (if needed)

**Technical Notes:**
- Use `get_logger(__name__)` for structured logging (established in Epic 1)
- Log at INFO level for successful operations, WARNING for fallbacks, ERROR for failures
- Include user_id and memory_id in all log entries for tracing
- Memory storage is foundation for Story 3.2 (Memory Retrieval)

**Subtasks:**
- [ ] Add docstrings to all classes and methods
- [ ] Document memory storage flow
- [ ] Update CLAUDE.md
- [ ] Update env.example
- [ ] Document structured logging patterns
- [ ] Add code comments for complex logic
- [ ] Update architecture diagrams (if needed)
- [ ] Review documentation completeness

---

## Definition of Done

- [ ] All 8 tasks completed
- [ ] All 6 acceptance criteria validated with evidence
- [ ] MemoryClient module created (`backend/api/memory_client.py`)
- [ ] MemoryManager module created (`backend/api/memory.py`)
- [ ] store_memory MCP tool implemented (`mcp_server/tools.py`)
- [ ] Conversation summarization with LLM working
- [ ] agentic-memories HTTP API integration working
- [ ] Graceful degradation with Redis fallback implemented
- [ ] Background retry worker operational
- [ ] Memory storage integrated into chat flow
- [ ] Conversation end detection working (farewell + timeout)
- [ ] Performance requirements met (<500ms p95 for storage)
- [ ] Unit tests created and passing (>80% coverage)
- [ ] Integration tests created and passing
- [ ] MCP tool tests created and passing
- [ ] Documentation and structured logging implemented
- [ ] Code reviewed and approved
- [ ] No regressions in existing functionality (Story 2.1-2.5 tests still pass)

---

## Learnings from Previous Story

**From Story 2.5: Conversation State Management (Status: done)**

**New Patterns/Services Created:**
- **StateManager Module**: Created `backend/api/state.py` (632 lines) with Redis-based state management
  - Use `StateManager` class with async context manager pattern (`async with StateManager()`)
  - Custom exception hierarchy: `StateError`, `RedisConnectionError`, `StateValidationError` for granular error handling
  - Redis key patterns: `session:{user_id}`, `conversation:{conversation_id}`
  - TTL management: 3600s for sessions, 1800s for conversations
  - Async operations with redis.asyncio.Redis client

**Architectural Patterns Established:**
- Async context managers for resource cleanup (`__aenter__`, `__aexit__`)
- Structured logging with extra fields: `logger.info("message", extra={"key": "value", "duration_ms": ...})`
- Performance monitoring with duration tracking: `start_time = time.time()` → `duration_ms = int((time.time() - start_time) * 1000)`
- Custom exception classes for domain-specific errors
- Graceful degradation when external service fails (continue without feature)

**Files to Reuse/Extend:**
- `backend/api/state.py` - StateManager for retrieving conversation history to summarize
- `backend/api/routes/chat.py` - Integrate memory storage trigger on conversation end
- `backend/api/llm_client.py` - Use LLM for conversation summarization
- `backend/api/mcp_client.py` - Call store_memory tool via MCP (Story 2.4 pattern)
- `backend/api/config.py` - Add agentic-memories configuration
- `backend/api/logging.py` - Use for memory storage logging
- `mcp_server/tools.py` - Add store_memory tool implementation

**Redis Patterns to Follow:**
- Use redis.asyncio.Redis for async operations
- Implement connection pooling (automatic with redis-py)
- Set timeouts to prevent hanging (5s socket timeout)
- Handle connection errors gracefully (catch redis.exceptions.ConnectionError)
- Use Redis Lists for ordered data (RPUSH, LRANGE pattern)
- Use Redis Strings with JSON for complex objects (SET, GET with json.dumps/loads)
- Set TTL on all keys to prevent memory bloat

**Testing Patterns:**
- pytest-asyncio for async tests
- AsyncMock for mocking async methods: `mock_method = AsyncMock(return_value=...)`
- Context manager mocking: `MockClass.return_value.__aenter__.return_value = mock_instance`
- Comprehensive error scenario testing (network failures, timeouts, edge cases)
- Use fakeredis for deterministic Redis tests
- 100% test pass rate achieved - maintain this standard

**Technical Debt:**
- None carried forward to this story

**Recommendations for This Story:**
- Follow same async/await patterns as StateManager for MemoryClient
- Use similar custom exception hierarchy for memory errors (MemoryClientError, MemoryNetworkError, etc.)
- Apply same structured logging pattern with duration tracking
- Use async context manager for HTTP client (httpx.AsyncClient)
- Reuse Redis patterns for fallback queue (RPUSH/LRANGE)
- Test both success and failure paths comprehensively
- Monitor performance metrics from day 1 (500ms p95 target)
- Use StateManager.get_conversation_history() to retrieve messages for summarization

[Source: .bmad-ephemeral/stories/2-5-conversation-state-management.md#Dev-Agent-Record]

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **MemoryClient** (`backend/api/memory_client.py`): HTTP client for agentic-memories API
- **MemoryManager** (`backend/api/memory.py`): Orchestrates conversation summarization and memory storage
- **store_memory MCP Tool** (`mcp_server/tools.py`): MCP tool interface for memory storage
- **agentic-memories Service** (External): Persistent memory storage with semantic search
- **Redis Fallback Queue**: Temporary storage when agentic-memories unavailable

**Data Flow:**
```
1. User → POST /api/chat (sends "thanks" or 30-min timeout)
2. Backend → Conversation end detected
3. Backend → StateManager.get_conversation_history(conversation_id)
4. Backend → MemoryManager.summarize_conversation(history)
5. LLM → Generates structured Memory Object (summary, decisions, preferences, topics)
6. Backend → MemoryManager.store_memory_with_fallback(memory)
7. Try: MemoryClient.store_memory() → agentic-memories HTTP POST /memories
8. Success: Return {"status": "stored", "memory_id": "..."}
9. Failure: Redis ← RPUSH memory_queue:{user_id} {memory_json}
10. Background Worker (every 5 min) → Retry queued memories
11. Success: Redis → LREM memory_queue:{user_id} {memory_json}
```

**Memory Object Schema** (from tech-spec-epic-3.md):
```json
{
  "user_id": "12345",
  "memory_id": "mem_abc123",
  "timestamp": "2025-11-11T10:00:00Z",
  "conversation_summary": "User asked for stock investment advice for AAPL...",
  "decisions": [
    {
      "decision": "Buy 10 shares of AAPL",
      "options_considered": ["Buy AAPL", "Buy MSFT", "Hold cash"],
      "reasoning": "Strong fundamentals, positive trend",
      "outcome": null
    }
  ],
  "preferences": {
    "risk_tolerance": "moderate",
    "priorities": ["long-term growth", "dividend income"],
    "constraints": ["max 20% tech exposure"]
  },
  "topics": ["stock_trading", "investment_advice", "AAPL"],
  "sentiment": "positive"
}
```

**agentic-memories API Contract:**
```
POST /memories
Request:
{
  "user_id": "12345",
  "memory": { ... Memory Object ... }
}

Response (Success):
{
  "status": "success",
  "memory_id": "mem_abc123",
  "stored_at": "2025-11-11T10:00:00Z"
}

Response (Error):
{
  "status": "error",
  "error_code": "STORAGE_FAILED",
  "message": "Failed to store memory"
}
```

### Technical Constraints

1. **Performance Requirements**:
   - Memory storage: <500ms (p95) end-to-end
   - Breakdown: Summarization (~2s) + HTTP POST (~300ms) + Processing (~200ms)
   - Storage must be async/non-blocking (don't delay user response)
   - Use asyncio.create_task() for background storage

2. **Graceful Degradation**:
   - Continue chat functionality when agentic-memories down
   - Store in Redis fallback queue (TTL: 24 hours)
   - Retry every 5 minutes with exponential backoff
   - Circuit breaker: After 5 failures, pause for 15 minutes
   - Inform user: "I'm having trouble accessing your memory right now"

3. **Conversation End Detection**:
   - Farewell keywords: "thanks", "thank you", "bye", "goodbye" (case-insensitive)
   - Timeout: 30 minutes since last message
   - Explicit end signal (future enhancement)
   - Prevent duplicate storage with distributed lock (Redis)

4. **Memory Size Limits**:
   - Max conversation history for summarization: 50 messages
   - Max memory size: 10KB (compress if larger)
   - Conversation summary: Max 500 characters
   - Topics: Max 10 topics
   - Decisions: Max 5 decisions per memory

### Dependencies

**New Python Dependencies:**
- No new dependencies! Reuse existing:
  - `httpx>=0.25.0` - Already added in Story 2.2 for LLM client
  - `redis>=5.0.0` - Already added in Story 2.5 for state management
  - `pytest-asyncio>=0.21.0` - Already added for async testing

**Optional Dev Dependencies:**
- `respx>=0.20.0` - For mocking httpx requests in tests (cleaner than httpretty)

Add to `backend/requirements-dev.txt`:
```
respx>=0.20.0
```

**External Services:**
- agentic-memories service (must be running)
- Configuration: `AGENTIC_MEMORIES_URL` in .env

**Existing Dependencies (from previous stories):**
- LLMClient (Story 2.2) - For conversation summarization
- StateManager (Story 2.5) - For retrieving conversation history
- MCPClient (Story 2.4) - For calling store_memory tool
- Redis (Epic 1) - For fallback queue
- Logging infrastructure (Epic 1) - For structured logging

### Key Files to Create/Modify

**New Files:**
- `backend/api/memory_client.py` - MemoryClient class for agentic-memories HTTP API
- `backend/api/memory.py` - MemoryManager class for summarization and storage orchestration
- `backend/tests/unit/test_memory_client.py` - Unit tests for MemoryClient
- `backend/tests/unit/test_memory_manager.py` - Unit tests for MemoryManager
- `backend/tests/integration/test_memory_storage_e2e.py` - End-to-end memory storage tests
- `mcp_server/tests/test_store_memory_tool.py` - MCP tool tests

**Files to Modify:**
- `backend/api/routes/chat.py` - Add conversation end detection and memory storage trigger
- `mcp_server/tools.py` - Add store_memory tool implementation
- `backend/requirements-dev.txt` - Add respx for HTTP mocking
- `env.example` - Add AGENTIC_MEMORIES_URL, MEMORY_STORAGE_ENABLED

**Reference Files:**
- `.bmad-ephemeral/stories/tech-spec-epic-3.md` - Epic 3 technical specification
  - Lines 51-72: Data Flow diagram
  - Lines 123-153: Services/Modules table (memory.py, memory_client.py, memory_manager.py)
  - Lines 205-231: Memory Object schema
  - Lines 233-284: agentic-memories API contracts
  - Lines 286-317: store_memory MCP tool spec
  - Lines 356-394: Storage Flow (9 steps with success/failure paths)
  - Lines 497-508: Performance requirements (<300ms retrieval, <500ms storage)
  - Lines 647-675: AC 3.1.1-3.1.6 traceability
- `.bmad-ephemeral/stories/2-5-conversation-state-management.md` - Previous story (Redis patterns)
- `docs/epics-and-stories.md` - Epic breakdown (lines 508-546: Story 3.1)
- `docs/02-architecture/ARCHITECTURE_PLAN.md` - System architecture
- `CLAUDE.md` - agentic-memories configuration details

### Testing Strategy

**Unit Tests** (Fast, Deterministic):
- Test MemoryClient.store_memory with mocked httpx responses (success/failure/timeout)
- Test MemoryClient error handling (ConnectionError, Timeout, HTTP errors)
- Test MemoryManager.summarize_conversation with sample conversations
- Test memory schema validation (required fields, data types)
- Test Redis fallback logic (store, retrieve, retry)
- Test retry logic with exponential backoff (3 retries, 1s/2s/4s)
- Mock all external services (agentic-memories, LLM, Redis)
- Use respx for httpx mocking
- Target: <1s per test, >80% code coverage

**Integration Tests** (Slower, Real Integrations):
- Test full memory storage flow (conversation → summary → storage)
- Test graceful degradation (agentic-memories down, Redis fallback)
- Test retry worker (queued memories, background processing)
- Test conversation end detection (farewell keywords, timeout)
- Test concurrent storage requests (distributed lock)
- Test performance requirements (500ms p95 storage)
- Use mocked agentic-memories API (httpretty or respx)
- Use fakeredis or Docker Redis
- Test with both empty and populated conversations

**MCP Tool Tests**:
- Test store_memory tool via docker exec pattern
- Test tool schema validation (JSON-RPC 2.0)
- Test tool success/failure responses
- Test tool error codes and messages

**Performance Validation:**
- Measure memory storage time (target: 500ms p95)
- Measure summarization time (target: 3s)
- Measure HTTP POST time (target: 300ms)
- Load test with 100 concurrent storage operations
- Monitor Redis fallback queue size
- Monitor retry success rate

### Implementation Approach

**Phase 1: MemoryClient Foundation (Task 1)**
1. Create `MemoryClient` class with httpx.AsyncClient
2. Implement store_memory method (HTTP POST)
3. Implement health_check method
4. Add custom exception classes
5. Test with mocked httpx responses

**Phase 2: MCP Tool Implementation (Task 2)**
1. Define store_memory tool schema
2. Implement tool function calling MemoryClient
3. Add retry logic with exponential backoff
4. Register tool with MCP server
5. Test via docker exec pattern

**Phase 3: Conversation Summarization (Task 3)**
1. Create MemoryManager class
2. Implement summarize_conversation method
3. Add LLM prompt for summarization
4. Parse LLM response into Memory Object
5. Add validation and fallback logic
6. Test with sample conversations

**Phase 4: Graceful Degradation (Task 4)**
1. Implement store_memory_with_fallback method
2. Create Redis fallback queue
3. Implement background retry worker
4. Add circuit breaker logic
5. Add user notification flag
6. Test failure scenarios

**Phase 5: Chat Integration (Task 5)**
1. Add conversation end detection (farewell + timeout)
2. Integrate memory storage into chat endpoint
3. Implement background timeout worker
4. Add distributed lock for duplicate prevention
5. Test end-to-end flow

**Phase 6: Performance & Testing (Task 6, Task 7, Task 8)**
1. Add performance monitoring
2. Optimize bottlenecks (caching, compression)
3. Create comprehensive unit tests
4. Create integration tests
5. Update documentation
6. Code review and validation

### Success Metrics

- ✅ All 6 acceptance criteria implemented and validated
- ✅ Memory storage: <500ms p95 end-to-end
- ✅ Conversation summarization: LLM generates structured Memory Object
- ✅ agentic-memories integration: HTTP API working
- ✅ Graceful degradation: Redis fallback and retry worker operational
- ✅ Conversation end detection: Farewell keywords and timeout working
- ✅ Performance: <500ms p95 storage, <3s summarization
- ✅ Test coverage: >80% for memory modules
- ✅ Zero regressions in Story 2.1-2.5 functionality

---

## References

1. **Epic 3 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-3.md`)
   - Lines 51-72: Data Flow diagram (Backend → agentic-memories)
   - Lines 123-153: Services/Modules table (memory.py, memory_client.py, memory_manager.py)
   - Lines 205-231: Memory Object schema (decisions, preferences, topics)
   - Lines 233-284: agentic-memories API contracts (POST /memories)
   - Lines 286-317: store_memory MCP tool specification (JSON-RPC 2.0)
   - Lines 356-394: Storage Flow (9 steps: detect end → retrieve history → summarize → store)
   - Lines 497-508: Performance requirements (<500ms storage, <300ms retrieval)
   - Lines 647-675: AC 3.1.1-3.1.6 traceability mapping

2. **Story 2.5: Conversation State Management** (`.bmad-ephemeral/stories/2-5-conversation-state-management.md`)
   - Redis patterns with redis.asyncio.Redis
   - Async context manager patterns
   - Custom exception hierarchy for error handling
   - Structured logging patterns with duration tracking
   - Testing patterns with pytest-asyncio and fakeredis
   - StateManager.get_conversation_history() for retrieving messages

3. **Story 2.4: Function Calling for MCP Tools** (`.bmad-ephemeral/stories/2-4-function-calling-mcp-tools.md`)
   - MCPClient async patterns with httpx.AsyncClient
   - MCP tool schema definitions (JSON-RPC 2.0)
   - Tool registration patterns
   - Error handling with custom exceptions

4. **Epic & Story Breakdown** (`docs/epics-and-stories.md`)
   - Lines 508-546: Story 3.1 user story and acceptance criteria

5. **Architecture Plan** (`docs/02-architecture/ARCHITECTURE_PLAN.md`)
   - Memory integration architecture
   - agentic-memories service integration patterns

6. **Project Instructions** (`CLAUDE.md`)
   - agentic-memories configuration (AGENTIC_MEMORIES_URL)
   - Environment variable patterns

---

**Created:** 2025-11-11
**Epic:** Epic 3 - Memory & Persistence
**Story:** 3.1 - Memory Storage Integration
**Status:** drafted

---

## Dev Agent Record

### Context Reference

**Story Context XML:** `.bmad-ephemeral/stories/3-1-memory-storage-integration.context.xml`

Generated: 2025-11-11
Generated by: story-context workflow
Contains: Technical specification, documentation artifacts, code interfaces, dependencies, development constraints, testing standards and ideas

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List
