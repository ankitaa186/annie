# Epic Technical Specification: Direct Memory Storage Enhancement

Date: 2025-12-29
Author: Ankit
Epic ID: 14
Status: Draft

---

## Overview

This epic addresses a critical UX issue where the `store_memory` MCP tool takes 60-100+ seconds to complete due to the full LangGraph extraction pipeline in agentic-memories. This blocks user responses while the LLM waits for the tool to return.

The solution leverages a new fast direct storage API (`POST /v1/memories/direct`) in agentic-memories that bypasses the LLM extraction pipeline, achieving 1-2 second storage times. Additionally, a new `delete_memory` tool enables the LLM to remove incorrect or outdated memories.

**Key insight**: Annie already has automatic background memory extraction via the Memory Orchestrator (`/v1/orchestrator/message`), so the LLM only needs `store_memory` for **critical explicit memories** that users specifically ask to be remembered.

## Objectives and Scope

**In Scope:**
- Update `store_memory` tool schema to accept pre-formatted content with optional typed fields (episodic, emotional, procedural)
- Update `store_memory` handler to call `/v1/memories/direct` endpoint (target: <3s)
- Add new `delete_memory` tool using `DELETE /v1/memories/{id}` endpoint
- Register updated/new tools in MCP server
- Add memory management instructions to system prompt
- Unit and integration tests for both tools
- Documentation updates

**Out of Scope:**
- Changes to retrieve_memories (already fast)
- Modifications to the background Memory Orchestrator
- Redis fallback queue (deferred - can add later for reliability)
- Langfuse tracing for memory tools (deferred - can add later)
- UI changes in Telegram bot

## System Architecture Alignment

This epic integrates with the existing Annie architecture:

**MCP Server** (`mcp_server/`):
- `tools.py`: Update `store_memory` tool schema and handler; add `delete_memory` tool
- `server.py`: Register the new `delete_memory` tool

**Backend API** (`backend/`):
- `api/prompts.py`: Add MEMORY_MANAGEMENT_SECTION to system prompt
- `api/status_summarizers.py`: Add/update summarizers for memory tools

**External Service** (agentic-memories):
- New `POST /v1/memories/direct` endpoint (dependency)
- New `DELETE /v1/memories/{id}` endpoint (dependency)

**Storage Routing** (handled by agentic-memories):
- ChromaDB (always) - with stored_in_* metadata flags
- episodic_memories (if event_timestamp provided)
- emotional_memories (if emotional_state provided)
- procedural_memories (if skill_name provided)

## Detailed Design

### Services and Modules

| Module | File | Responsibility | Changes |
|--------|------|----------------|---------|
| **store_memory tool** | `mcp_server/tools.py` | Store pre-formatted memories | Update schema, change endpoint to `/v1/memories/direct`, reduce timeout |
| **delete_memory tool** | `mcp_server/tools.py` | Delete memories by ID | New tool, calls `DELETE /v1/memories/{id}` |
| **MCP Server** | `mcp_server/server.py` | Tool registration | Register `delete_memory` tool |
| **System Prompt** | `backend/api/prompts.py` | LLM instructions | Add MEMORY_MANAGEMENT_SECTION |
| **Status Summarizers** | `backend/api/status_summarizers.py` | Tool result formatting | Add/update summarizers |

### Data Models and Contracts

**store_memory Input Schema (Updated):**
```python
{
    # Required
    "user_id": str,
    "content": str,                    # Pre-formatted memory content

    # General fields (always stored in ChromaDB)
    "importance": float,               # 0.0-1.0 (default: 0.8)
    "layer": str,                      # "short-term"|"semantic"|"long-term" (default: "semantic")
    "persona_tags": List[str],         # Max 10 tags (default: [])
    "metadata": Optional[Dict],        # source, conversation_id, trigger

    # Optional episodic fields → triggers episodic_memories write
    "event_timestamp": Optional[datetime],
    "location": Optional[str],
    "participants": Optional[List[str]],

    # Optional emotional fields → triggers emotional_memories write
    "emotional_state": Optional[str],  # e.g., "happy", "anxious"
    "valence": Optional[float],        # -1.0 to 1.0
    "arousal": Optional[float],        # 0.0 to 1.0

    # Optional procedural fields → triggers procedural_memories write
    "skill_name": Optional[str],
    "proficiency_level": Optional[str]
}
```

**store_memory Response:**
```python
{
    "status": "success"|"error",
    "memory_id": str,                  # UUID
    "message": str,
    "storage": {
        "chromadb": bool,              # Always true on success
        "episodic": bool,              # True if event_timestamp provided
        "emotional": bool,             # True if emotional_state provided
        "procedural": bool             # True if skill_name provided
    }
}
```

**delete_memory Input Schema (New):**
```python
{
    "user_id": str,                    # User identifier
    "memory_id": str,                  # Memory ID to delete
    "reason": Optional[str]            # Reason for deletion (audit)
}
```

**delete_memory Response:**
```python
{
    "status": "success"|"error",
    "deleted": bool,
    "memory_id": str,
    "message": str,
    "storage": {
        "chromadb": bool,
        "episodic": bool,
        "emotional": bool,
        "procedural": bool
    }
}
```

### APIs and Interfaces

**POST /v1/memories/direct** (agentic-memories)
- Method: POST
- Content-Type: application/json
- Body: DirectMemoryRequest schema (see above)
- Response: 200 (success), 400 (validation error), 500 (server error)
- Latency target: <3s (p95)

**DELETE /v1/memories/{memory_id}** (agentic-memories)
- Method: DELETE
- Query params: `user_id` (required for authorization)
- Response: 200 (success with deleted=true/false), 403 (unauthorized), 500 (error)
- Latency target: <1s (p95)

### Workflows and Sequencing

**Store Memory Flow:**
```
1. LLM decides to store critical memory
2. LLM calls store_memory tool with content + optional typed fields
3. MCP Server receives tool call
4. Handler builds payload for /v1/memories/direct
5. HTTP POST to agentic-memories (timeout: 10s)
6. agentic-memories:
   a. Generates embedding (~500ms)
   b. Stores in ChromaDB with stored_in_* flags (~100ms)
   c. Conditionally stores in typed tables (~100ms)
7. Returns memory_id and storage details
8. MCP Server returns result to LLM
9. LLM continues conversation
```

**Delete Memory Flow:**
```
1. User asks to forget something or LLM identifies incorrect memory
2. LLM calls retrieve_memories to find memory ID
3. LLM confirms with user which memory to delete
4. LLM calls delete_memory with memory_id
5. MCP Server receives tool call
6. Handler calls DELETE /v1/memories/{id}?user_id={user_id}
7. agentic-memories:
   a. Gets metadata from ChromaDB (check stored_in_* flags)
   b. Deletes from ChromaDB
   c. Deletes from typed tables based on flags
8. Returns deletion confirmation
9. LLM informs user of successful deletion
```

## Non-Functional Requirements

### Performance

| Metric | Current | Target | Alert Threshold |
|--------|---------|--------|-----------------|
| `store_memory` latency p95 | 60-100s | <3s | >5s |
| `delete_memory` latency p95 | N/A | <1s | >2s |
| Memory storage success rate | ~95% | >99% | <95% |
| Tool error rate | - | <1% | >5% |
| Embedding generation | - | <500ms | >1s |

**Performance Requirements:**
- First token delay: No impact (tools execute asynchronously)
- Concurrent operations: Support 10+ simultaneous memory operations per user
- Cold start: <500ms additional latency on first call after container restart

### Security

**Authentication & Authorization:**
- All memory operations require `user_id` parameter
- `user_id` MUST match the current user (enforced by LLM via system prompt)
- Delete operations verify ownership before deletion (403 on mismatch)
- No cross-user memory access possible

**Data Handling:**
- Memory content may contain sensitive user data
- API keys masked in logs (existing pattern)
- `user_id` and `memory_id` logged for audit trail
- `reason` field for delete operations logged for compliance

**Input Validation:**
- `importance` validated: 0.0-1.0 range
- `valence` validated: -1.0 to 1.0 range
- `arousal` validated: 0.0 to 1.0 range
- `persona_tags` limited to 10 items max
- `content` max length: 5000 characters

### Reliability/Availability

**Degradation Behavior:**
- If agentic-memories unavailable:
  - `store_memory`: Returns error, LLM informs user
  - `delete_memory`: Returns error, LLM informs user
  - Background extraction continues independently
- Timeout handling: 10s timeout with clean error message
- No retry for validation errors
- Exponential backoff retry for transient errors (embedding, storage)

**Recovery:**
- Stateless tool handlers - no recovery needed on Annie side
- Memory consistency managed by agentic-memories

### Observability

**Required Log Events:**
```
# Successful store
[mcp.store_memory] Memory stored user_id={} memory_id={} duration_ms={}

# Successful delete
[mcp.delete_memory] Memory deleted user_id={} memory_id={} reason={} duration_ms={}

# Errors
[mcp.store_memory.error] Storage failed user_id={} error_code={}
[mcp.delete_memory.error] Delete failed user_id={} memory_id={} status={}
```

**Metrics to Track:**
- `memory_store_duration_ms` - histogram
- `memory_delete_duration_ms` - histogram
- `memory_store_success_total` - counter
- `memory_store_error_total` - counter by error_code
- `memory_delete_success_total` - counter
- `memory_delete_error_total` - counter by status

## Dependencies and Integrations

### Blocking Dependencies

| Dependency | Owner | Status | Notes |
|------------|-------|--------|-------|
| `POST /v1/memories/direct` endpoint | agentic-memories | **Required** | Fast path for direct storage |
| `DELETE /v1/memories/{id}` endpoint | agentic-memories | **Required** | Memory deletion |

### Non-Blocking Dependencies

| Dependency | Impact | Status |
|------------|--------|--------|
| Langfuse tracing for memory tools | Observability enhancement | Deferred |
| Redis fallback queue for store failures | Reliability improvement | Deferred |

### Internal Dependencies

| Package/Module | Version | Purpose |
|----------------|---------|---------|
| `httpx` | >=0.24.0 | Async HTTP client for API calls |
| `mcp` | >=0.1.0 | MCP SDK for tool registration |
| `pydantic` | >=2.0 | Request/response validation |

### Integration Points

1. **agentic-memories** (external service)
   - URL: `AGENTIC_MEMORIES_URL` env var (default: `http://host.docker.internal:8080`)
   - Protocol: HTTP/REST
   - Auth: None (internal network)
   - Timeout: 10s

2. **MCP Server ↔ Backend**
   - Communication: Docker exec with stdio
   - Protocol: JSON-RPC 2.0
   - Tool schemas exposed via `tools/list`

3. **LLM (Gemini) ↔ Backend**
   - Tool definitions sent in system prompt
   - Function calling for tool invocation
   - Results injected into conversation context

## Acceptance Criteria (Authoritative)

### AC-14.1: store_memory Schema Update
1. `store_memory` tool accepts `content` field (required) instead of `history`
2. Schema includes optional typed fields: `event_timestamp`, `location`, `participants` (episodic)
3. Schema includes optional typed fields: `emotional_state`, `valence`, `arousal` (emotional)
4. Schema includes optional typed fields: `skill_name`, `proficiency_level` (procedural)
5. Default values work correctly (`importance`: 0.8, `layer`: "semantic")
6. LLM-readable descriptions guide proper tool usage

### AC-14.2: store_memory Handler Update
1. Handler calls `POST /v1/memories/direct` endpoint
2. Timeout reduced to 10s (from 180s)
3. Optional typed fields are passed through to API
4. Response includes `memory_id` and `storage` details
5. Error codes handled: VALIDATION_ERROR (no retry), EMBEDDING_ERROR (retry), STORAGE_ERROR (retry)
6. Latency <3s (p95) on successful storage

### AC-14.3: delete_memory Tool
1. New `delete_memory` tool registered in MCP server
2. Tool accepts `user_id`, `memory_id` (required), `reason` (optional)
3. Handler calls `DELETE /v1/memories/{id}?user_id={user_id}`
4. 403 response handled (unauthorized)
5. 404 response handled (not found)
6. `reason` logged for audit trail
7. Latency <1s (p95) on successful deletion

### AC-14.4: Tool Registration
1. `delete_memory` tool appears in `tools/list` response
2. Updated `store_memory` schema appears in `tools/list` response
3. Both tools executable via MCP protocol

### AC-14.5: System Prompt
1. MEMORY_MANAGEMENT_SECTION added to system prompt
2. Clear guidance on when to use `store_memory` (critical explicit only)
3. Clear guidance on when to use `delete_memory`
4. Examples of good/bad usage provided
5. LLM understands that background extraction handles routine info

### AC-14.6: Integration
1. Full lifecycle works: store → retrieve → delete → verify gone
2. store_memory completes in <3s
3. delete_memory completes in <1s
4. Concurrent operations supported

## Traceability Mapping

| AC ID | Spec Section | Component | Test Type |
|-------|--------------|-----------|-----------|
| AC-14.1.1 | Data Models | `mcp_server/tools.py` | Unit: schema validation |
| AC-14.1.2 | Data Models | `mcp_server/tools.py` | Unit: episodic fields |
| AC-14.1.3 | Data Models | `mcp_server/tools.py` | Unit: emotional fields |
| AC-14.1.4 | Data Models | `mcp_server/tools.py` | Unit: procedural fields |
| AC-14.1.5 | Data Models | `mcp_server/tools.py` | Unit: defaults |
| AC-14.2.1 | APIs | `mcp_server/tools.py` | Integration: endpoint call |
| AC-14.2.2 | APIs | `mcp_server/tools.py` | Unit: timeout config |
| AC-14.2.3 | Workflows | `mcp_server/tools.py` | Unit: payload building |
| AC-14.2.4 | Data Models | `mcp_server/tools.py` | Unit: response parsing |
| AC-14.2.5 | Reliability | `mcp_server/tools.py` | Unit: error handling |
| AC-14.2.6 | Performance | Integration | Integration: latency test |
| AC-14.3.1 | Services | `mcp_server/server.py` | Unit: registration |
| AC-14.3.2 | Data Models | `mcp_server/tools.py` | Unit: schema |
| AC-14.3.3 | APIs | `mcp_server/tools.py` | Integration: delete call |
| AC-14.3.4 | Security | `mcp_server/tools.py` | Unit: 403 handling |
| AC-14.3.5 | Reliability | `mcp_server/tools.py` | Unit: 404 handling |
| AC-14.3.6 | Observability | `mcp_server/tools.py` | Unit: logging |
| AC-14.3.7 | Performance | Integration | Integration: latency test |
| AC-14.4.1 | Services | `mcp_server/server.py` | Integration: tools/list |
| AC-14.4.2 | Services | `mcp_server/server.py` | Integration: tools/list |
| AC-14.5.1 | System Arch | `backend/api/prompts.py` | Unit: prompt content |
| AC-14.5.2 | System Arch | `backend/api/prompts.py` | Manual: LLM behavior |
| AC-14.6.1 | Workflows | Integration test | E2E: lifecycle test |
| AC-14.6.2 | Performance | Integration test | E2E: store latency |
| AC-14.6.3 | Performance | Integration test | E2E: delete latency |

## Risks, Assumptions, Open Questions

### Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **R1**: agentic-memories API not ready | Blocks epic | Medium | Design doc complete, can start Annie implementation in parallel |
| **R2**: Embedding latency exceeds target | Degrades UX | Low | OpenAI embeddings typically <500ms; can add caching if needed |
| **R3**: LLM overuses store_memory | Increased costs | Medium | Clear system prompt guidance + examples of when NOT to use |
| **R4**: Delete operation used maliciously | Data loss | Low | Requires user_id authorization; LLM confirms with user first |

### Assumptions

| Assumption | Rationale | Validation |
|------------|-----------|------------|
| **A1**: agentic-memories will implement the direct API as specified | Design doc reviewed and approved | Confirm with agentic-memories owner |
| **A2**: Embedding generation is the primary latency contributor | Based on current /v1/store profiling | Measure in production |
| **A3**: LLM will follow system prompt guidance | Gemini generally follows instructions well | Monitor store_memory usage patterns |
| **A4**: 10s timeout is sufficient for all operations | Direct storage should be 1-2s | Adjust if needed based on data |

### Open Questions

| Question | Owner | Decision Date | Status |
|----------|-------|---------------|--------|
| **Q1**: Should we add Langfuse tracing for memory tools? | Dev team | Post-launch | Deferred |
| **Q2**: Is Redis fallback queue needed for store failures? | Dev team | Post-launch | Deferred |
| **Q3**: Should we version the memory API schema? | agentic-memories | Before implementation | Open |

## Test Strategy Summary

### Test Levels

| Level | Scope | Framework | Coverage Target |
|-------|-------|-----------|-----------------|
| **Unit** | Tool handlers, schema validation | pytest + pytest-asyncio | 80% |
| **Integration** | MCP Server ↔ agentic-memories | pytest + httpx mocks | Key flows |
| **E2E** | Full memory lifecycle | pytest with live agentic-memories | Happy path + errors |

### Unit Tests

**store_memory tests** (`mcp_server/tests/test_store_memory_tool.py`):
- Schema validation (required fields, defaults, ranges)
- Payload building with optional fields
- Response parsing
- Error code handling (VALIDATION_ERROR, EMBEDDING_ERROR, STORAGE_ERROR)
- Timeout handling

**delete_memory tests** (`mcp_server/tests/test_delete_memory_tool.py`):
- Schema validation
- Successful deletion
- Not found (404)
- Unauthorized (403)
- Timeout handling
- Reason logging

### Integration Tests

**Memory lifecycle** (`backend/tests/integration/test_memory_lifecycle.py`):
- Store → Retrieve → Delete → Verify gone
- Performance assertions (<3s store, <1s delete)
- Concurrent operations
- Error recovery

### Test Data

- Use dedicated test user_id: `test_user_epic14`
- Clean up test memories after each test
- Mock httpx for unit tests
- Use real agentic-memories for integration tests

### Edge Cases to Cover

1. Empty content field
2. Content at max length (5000 chars)
3. 11 persona_tags (should truncate to 10)
4. Invalid importance values (-0.1, 1.1)
5. Invalid valence values (-1.1, 1.1)
6. Missing required fields
7. Network timeout
8. Service unavailable
