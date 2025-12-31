# Epic: Direct Memory Storage Enhancement

> **Epic ID**: 14
> **Status**: Draft
> **Priority**: High
> **Estimated Effort**: 5-8 days
> **Dependencies**: agentic-memories direct API (see `agentic-memories/docs/design-direct-memory-api.md`)

---

## 1. Overview

### 1.1 Problem Statement

The current `store_memory` MCP tool has unacceptable latency (60-100+ seconds) because it calls the `/v1/store` endpoint which triggers the full LangGraph extraction pipeline. This makes explicit memory storage impractical during conversations.

Additionally, there is no way for the LLM to delete incorrect or outdated memories.

### 1.2 Solution

1. **Update `store_memory` tool** to use the new fast `/v1/memories/direct` endpoint (target: <3s)
2. **Add `delete_memory` tool** using the new `DELETE /v1/memories/{id}` endpoint
3. **Update system prompt** with memory management instructions
4. **Inform LLM** that background extraction already runs automatically

### 1.3 Success Criteria

| Metric | Current | Target |
|--------|---------|--------|
| `store_memory` latency p95 | 60-100s | <3s |
| `delete_memory` latency p95 | N/A | <1s |
| Memory storage success rate | ~95% | >99% |
| LLM understands when to use tools | Low | High |

---

## 2. Architecture

### 2.1 Current Flow (Slow)

```
LLM → store_memory tool → MCP Server → POST /v1/store → agentic-memories
                                              ↓
                                    LangGraph Pipeline (60-100s)
                                    - Worthiness check
                                    - Extraction
                                    - Deduplication
                                    - Multi-layer routing
```

### 2.2 New Flow (Fast)

```
LLM → store_memory tool → MCP Server → POST /v1/memories/direct → agentic-memories
                                              ↓
                                    Direct Storage (1-2s)
                                    - Generate embedding
                                    - Store to ChromaDB (always)
                                      + stored_in_* metadata flags
                                    - Conditional typed table storage:
                                      - episodic_memories (if event_timestamp)
                                      - emotional_memories (if emotional_state)
                                      - procedural_memories (if skill_name)
```

### 2.3 Delete Flow (New)

```
LLM → delete_memory tool → MCP Server → DELETE /v1/memories/{id} → agentic-memories
                                              ↓
                                    Metadata-driven Deletion (<500ms)
                                    - Get metadata from ChromaDB (check flags)
                                    - Delete from ChromaDB (always)
                                    - Delete from typed tables based on
                                      stored_in_* flags (efficient)
```

---

## 3. Stories

### Story 14.1: Update store_memory Tool Schema

**Priority**: P0
**Estimate**: 2 hours

Update the `store_memory` tool to accept pre-formatted memory content with optional typed memory fields.

**File**: `mcp_server/tools.py`

**Current Schema**:
```python
{
    "user_id": str,
    "history": List[{role, content}],  # Conversation messages
    "metadata": Optional[Dict]
}
```

**New Schema**:
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
    "event_timestamp": Optional[datetime],  # When event occurred
    "location": Optional[str],              # Where it happened
    "participants": Optional[List[str]],    # Who was involved

    # Optional emotional fields → triggers emotional_memories write
    "emotional_state": Optional[str],  # e.g., "happy", "anxious"
    "valence": Optional[float],        # -1.0 to 1.0
    "arousal": Optional[float],        # 0.0 to 1.0

    # Optional procedural fields → triggers procedural_memories write
    "skill_name": Optional[str],       # Name of skill/procedure
    "proficiency_level": Optional[str] # e.g., "beginner", "expert"
}
```

**Storage Routing**:
- ChromaDB (always) - includes stored_in_* flags for deletion
- episodic_memories (if event_timestamp provided)
- emotional_memories (if emotional_state provided)
- procedural_memories (if skill_name provided)

**Acceptance Criteria**:
- [ ] Schema updated with new fields
- [ ] `history` field removed
- [ ] `content` field required
- [ ] Optional episodic/emotional/procedural fields added
- [ ] Default values set correctly
- [ ] Descriptions updated for LLM guidance

---

### Story 14.2: Update store_memory Tool Handler

**Priority**: P0
**Estimate**: 4 hours

Update the handler to call the new `/v1/memories/direct` endpoint with storage routing.

**File**: `mcp_server/tools.py` (lines 99-310)

**Changes**:

1. **Endpoint**: Change from `/v1/store` to `/v1/memories/direct`

2. **Timeout**: Reduce from 180s to 10s

3. **Payload**: Build new request format with optional typed fields:
   ```python
   payload = {
       # Required
       "user_id": user_id,
       "content": content,

       # General fields
       "layer": layer,
       "type": "explicit",  # Always explicit for LLM-stored memories
       "importance": importance,
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
       payload["location"] = location
       payload["participants"] = participants

   # Add optional emotional fields if provided
   if emotional_state:
       payload["emotional_state"] = emotional_state
       payload["valence"] = valence
       payload["arousal"] = arousal

   # Add optional procedural fields if provided
   if skill_name:
       payload["skill_name"] = skill_name
       payload["proficiency_level"] = proficiency_level
   ```

4. **Response Handling**: Parse new response format with typed storage:
   ```python
   {
       "status": "success",
       "memory_id": "mem_abc123",
       "message": "Memory stored successfully",
       "storage": {
           "chromadb": true,
           "episodic": true,   # if event_timestamp provided
           "emotional": false,
           "procedural": false
       }
   }
   ```

5. **Error Codes**: Handle new error codes:
   - `VALIDATION_ERROR` → No retry
   - `EMBEDDING_ERROR` → Retry with backoff
   - `STORAGE_ERROR` → Retry with backoff
   - `INTERNAL_ERROR` → No retry

**Acceptance Criteria**:
- [ ] Handler calls `/v1/memories/direct`
- [ ] Timeout reduced to 10s
- [ ] Optional episodic/emotional/procedural fields passed through
- [ ] Retry logic updated for new error codes
- [ ] Logging updated with new payload format
- [ ] Returns memory_id and storage details on success

---

### Story 14.3: Add delete_memory Tool

**Priority**: P0
**Estimate**: 4 hours

Create a new MCP tool for deleting memories by ID.

**File**: `mcp_server/tools.py`

**Tool Schema**:
```python
delete_memory_tool = {
    "name": "delete_memory",
    "description": """Delete a specific memory by ID.

Use this tool when:
- User explicitly asks to forget something
- A memory is identified as incorrect or outdated
- Removing duplicate or conflicting information

IMPORTANT:
- First use retrieve_memories to find the memory ID
- Only delete memories that belong to the current user
- Cannot be undone - use with care

Args:
    user_id: The user's ID (from system message)
    memory_id: The ID of the memory to delete (from retrieve_memories)
    reason: Brief explanation for deletion (for audit trail)
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "memory_id": {
                "type": "string",
                "description": "Memory ID to delete (from retrieve_memories)"
            },
            "reason": {
                "type": "string",
                "description": "Reason for deletion"
            }
        },
        "required": ["user_id", "memory_id"]
    },
    "handler": delete_memory_tool_handler
}
```

**Handler Implementation**:
```python
async def delete_memory_tool_handler(
    user_id: str,
    memory_id: str,
    reason: str = None
) -> Dict[str, Any]:
    """Delete a memory by ID."""

    config = get_config()
    memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")

    start_time = time.time()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/memories/{memory_id}",
                params={"user_id": user_id}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                if result.get("deleted"):
                    logger.info(
                        "Memory deleted successfully",
                        extra={
                            "user_id": user_id,
                            "memory_id": memory_id,
                            "reason": reason,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "success",
                        "deleted": True,
                        "memory_id": memory_id,
                        "message": "Memory deleted successfully"
                    }
                else:
                    return {
                        "status": "error",
                        "deleted": False,
                        "memory_id": memory_id,
                        "message": result.get("message", "Memory not found")
                    }

            elif response.status_code == 403:
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": "Unauthorized: cannot delete this memory"
                }

            else:
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": f"Delete failed: {response.status_code}"
                }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": "Request timed out"
        }
    except Exception as e:
        logger.error(f"Delete memory failed: {e}")
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": str(e)
        }
```

**Response Handling** (updated for typed storage):
```python
{
    "status": "success",
    "deleted": True,
    "memory_id": "uuid-string",
    "storage": {
        "chromadb": true,
        "episodic": true,    # based on stored_in_episodic flag
        "emotional": false,
        "procedural": false
    }
}
```

**Delete Logic**:
1. API gets metadata from ChromaDB to check stored_in_* flags
2. Deletes from ChromaDB (always)
3. Deletes from typed tables based on flags (efficient - no querying all tables)

**Acceptance Criteria**:
- [ ] Tool registered in ToolRegistry
- [ ] Handler calls `DELETE /v1/memories/{id}`
- [ ] User authorization enforced via user_id param
- [ ] Reason logged for audit trail
- [ ] Error handling for 403, 404, 500 cases
- [ ] Handles typed storage response (chromadb, episodic, emotional, procedural)
- [ ] Timeout set to 10s

---

### Story 14.4: Register New Tools in MCP Server

**Priority**: P0
**Estimate**: 1 hour

Register the updated store_memory and new delete_memory tools.

**File**: `mcp_server/server.py`

**Changes**:
```python
def register_default_tools(self):
    # ... existing tools ...
    self.tool_registry.register(store_memory_tool)      # Updated
    self.tool_registry.register(delete_memory_tool)     # New
    # ... other tools ...
```

**Acceptance Criteria**:
- [ ] delete_memory tool registered
- [ ] store_memory tool updated
- [ ] Tools appear in `tools/list` response

---

### Story 14.5: Add Memory Instructions to System Prompt

**Priority**: P1
**Estimate**: 3 hours

Add memory management instructions to the system prompt.

**File**: `backend/api/prompts.py`

**New Section** (add after PROACTIVE_CAPABILITIES_SECTION):

```python
MEMORY_MANAGEMENT_SECTION = """
## MEMORY MANAGEMENT

Annie automatically extracts and stores memories from conversations in the background.
You do NOT need to call store_memory for routine information.

### When to Use store_memory (Explicit Storage)

ONLY use store_memory for CRITICAL information that:
1. User explicitly asks you to remember ("Remember that I...", "Don't forget...")
2. Is a permanent preference/constraint ("I'm allergic to...", "Never recommend...")
3. Is a life-changing decision with lasting impact
4. Would be dangerous to forget (medical conditions, safety constraints)

Example good uses:
- "User is severely allergic to shellfish - carries EpiPen"
- "User's risk tolerance is conservative - never recommend high-risk investments"
- "User's mother passed away in March 2024 - sensitive topic"

Example bad uses (background extraction handles these):
- Daily activities or routine conversations
- Temporary preferences or moods
- Information already in their profile
- Topics just discussed (already being extracted)

### When to Use delete_memory

Use delete_memory when:
1. User says something was remembered incorrectly
2. User explicitly asks to forget something
3. You find conflicting or duplicate memories
4. Information is outdated and causing confusion

To delete a memory:
1. First call retrieve_memories to find the memory ID
2. Confirm with the user which memory to delete
3. Call delete_memory with the memory_id

### When to Use retrieve_memories

Use retrieve_memories LIBERALLY when:
1. User asks about past decisions or conversations
2. Making recommendations that should consider history
3. User references something from the past
4. You need context about user preferences

Retrieval is fast (<2s) and should be used proactively.
"""
```

**Update build_system_prompt()**:

```python
def build_system_prompt(
    user_id: Optional[str] = None,
    platform: str = "api",
    include_tool_instructions: bool = True,
    profile: Optional[Dict[str, Any]] = None,
    portfolio: Optional[Dict[str, Any]] = None,
    triggers: Optional[list] = None,
    proactive_context: Optional[Dict[str, Any]] = None
) -> str:
    prompt_parts = [BASE_SYSTEM_PROMPT]
    prompt_parts.append(PROACTIVE_CAPABILITIES_SECTION)
    prompt_parts.append(MEMORY_MANAGEMENT_SECTION)  # NEW

    # ... rest of function ...
```

**Acceptance Criteria**:
- [ ] MEMORY_MANAGEMENT_SECTION constant added
- [ ] Section included in build_system_prompt()
- [ ] Clear guidance on when to use each tool
- [ ] Examples provided for good/bad usage

---

### Story 14.6: Update Tool Usage Instructions

**Priority**: P1
**Estimate**: 1 hour

Update the TOOL_USAGE_INSTRUCTIONS to include memory tools.

**File**: `backend/api/prompts.py`

**Current**:
```python
TOOL_USAGE_INSTRUCTIONS = """
IMPORTANT: When using memory tools (store_memory, retrieve_memories), ALWAYS use the exact user_id provided in the system message.
Never use generic IDs like 'anonymous_user' - always use the specific user_id.
"""
```

**Updated**:
```python
TOOL_USAGE_INSTRUCTIONS = """
## TOOL USAGE REQUIREMENTS

### Memory Tools (store_memory, retrieve_memories, delete_memory)
- ALWAYS use the exact user_id from the system message
- Never use generic IDs like 'anonymous_user'
- store_memory: Only for critical, permanent information (see Memory Management section)
- delete_memory: First retrieve the memory to get its ID, then delete
- retrieve_memories: Use liberally for context and personalization

### User ID
Current user ID for all tool calls: {user_id}
"""
```

**Acceptance Criteria**:
- [ ] Instructions updated for all memory tools
- [ ] delete_memory workflow explained
- [ ] User ID prominently displayed

---

### Story 14.7: Add Status Summarizers for Memory Tools

**Priority**: P2
**Estimate**: 1 hour

Add status summarizers for the updated tools.

**File**: `backend/api/status_summarizers.py`

**Add/Update**:
```python
def summarize_store_memory(result: Dict[str, Any]) -> str:
    """Summarize store_memory result."""
    if result.get("status") == "success":
        memory_id = result.get("memory_id", "unknown")
        return f"Memory saved ({memory_id[:12]}...)"
    else:
        return f"Save failed: {result.get('message', 'unknown error')}"


def summarize_delete_memory(result: Dict[str, Any]) -> str:
    """Summarize delete_memory result."""
    if result.get("deleted"):
        return "Memory deleted"
    else:
        return f"Delete failed: {result.get('message', 'not found')}"


# Update summarizer registry
SUMMARIZERS = {
    # ... existing ...
    "store_memory": summarize_store_memory,
    "delete_memory": summarize_delete_memory,
}
```

**Acceptance Criteria**:
- [ ] store_memory summarizer updated
- [ ] delete_memory summarizer added
- [ ] Concise status messages for user feedback

---

### Story 14.8: Unit Tests for store_memory Tool

**Priority**: P1
**Estimate**: 3 hours

Add comprehensive unit tests for the updated store_memory tool.

**File**: `mcp_server/tests/test_store_memory_tool.py`

**Test Cases**:
```python
class TestStoreMemoryDirect:
    """Tests for updated store_memory using direct API."""

    async def test_store_success_minimal(self):
        """Store with only required fields."""

    async def test_store_success_all_fields(self):
        """Store with all optional fields."""

    async def test_store_validation_error(self):
        """Handle validation error response."""

    async def test_store_embedding_error_retry(self):
        """Retry on embedding error."""

    async def test_store_timeout(self):
        """Handle timeout (10s)."""

    async def test_store_network_error(self):
        """Handle network connectivity issues."""

    async def test_persona_tags_limit(self):
        """Limit persona_tags to 10."""

    async def test_importance_validation(self):
        """Validate importance is 0.0-1.0."""
```

**Acceptance Criteria**:
- [ ] All test cases implemented
- [ ] Mocked httpx responses
- [ ] Edge cases covered
- [ ] Tests pass in CI

---

### Story 14.9: Unit Tests for delete_memory Tool

**Priority**: P1
**Estimate**: 2 hours

Add comprehensive unit tests for the new delete_memory tool.

**File**: `mcp_server/tests/test_delete_memory_tool.py`

**Test Cases**:
```python
class TestDeleteMemory:
    """Tests for delete_memory tool."""

    async def test_delete_success(self):
        """Successfully delete a memory."""

    async def test_delete_not_found(self):
        """Handle memory not found."""

    async def test_delete_unauthorized(self):
        """Handle 403 unauthorized."""

    async def test_delete_with_reason(self):
        """Include reason in audit log."""

    async def test_delete_timeout(self):
        """Handle timeout."""

    async def test_delete_network_error(self):
        """Handle network issues."""
```

**Acceptance Criteria**:
- [ ] All test cases implemented
- [ ] Mocked httpx responses
- [ ] Authorization tested
- [ ] Tests pass in CI

---

### Story 14.10: Integration Tests

**Priority**: P1
**Estimate**: 3 hours

Add integration tests for the memory lifecycle.

**File**: `backend/tests/integration/test_memory_lifecycle.py`

**Test Cases**:
```python
class TestMemoryLifecycle:
    """End-to-end memory tests with agentic-memories."""

    async def test_store_retrieve_delete_cycle(self):
        """Full lifecycle: store → retrieve → delete → verify gone."""

    async def test_store_performance(self):
        """Verify store completes in <3s."""

    async def test_delete_performance(self):
        """Verify delete completes in <1s."""

    async def test_concurrent_operations(self):
        """Handle multiple simultaneous operations."""
```

**Acceptance Criteria**:
- [ ] Tests run against local agentic-memories
- [ ] Performance assertions included
- [ ] Cleanup after tests

---

### Story 14.11: Update Documentation

**Priority**: P2
**Estimate**: 2 hours

Update CLAUDE.md and API documentation.

**Files**:
- `CLAUDE.md`
- `docs/api/mcp-tools.md` (create if needed)

**Changes**:
1. Document new `store_memory` schema
2. Document new `delete_memory` tool
3. Update memory storage section
4. Add performance expectations

**Acceptance Criteria**:
- [ ] CLAUDE.md updated
- [ ] Tool documentation complete
- [ ] Examples provided

---

## 4. Implementation Order

```
Phase 1: Core Changes (Stories 14.1-14.4)
├── 14.1 Update store_memory schema
├── 14.2 Update store_memory handler
├── 14.3 Add delete_memory tool
└── 14.4 Register tools

Phase 2: System Integration (Stories 14.5-14.7)
├── 14.5 Add memory instructions to prompt
├── 14.6 Update tool usage instructions
└── 14.7 Add status summarizers

Phase 3: Testing (Stories 14.8-14.10)
├── 14.8 Unit tests for store_memory
├── 14.9 Unit tests for delete_memory
└── 14.10 Integration tests

Phase 4: Documentation (Story 14.11)
└── 14.11 Update documentation
```

---

## 5. Dependencies

### Blocking Dependencies

| Dependency | Owner | Status |
|------------|-------|--------|
| `POST /v1/memories/direct` endpoint | agentic-memories | Not started |
| `DELETE /v1/memories/{id}` endpoint | agentic-memories | Not started |

### Non-Blocking Dependencies

| Dependency | Impact |
|------------|--------|
| Langfuse tracing | Observability (can add later) |
| Redis fallback queue | Reliability (can add later) |

---

## 6. Rollback Plan

If issues are detected after deployment:

### Quick Rollback (Annie only)

1. Revert `store_memory` to use `/v1/store` endpoint
2. Disable `delete_memory` tool registration
3. Remove MEMORY_MANAGEMENT_SECTION from prompt

### Full Rollback

1. Revert all Annie changes
2. Disable agentic-memories direct endpoints
3. Monitor for stability

---

## 7. Monitoring

### Metrics to Track

| Metric | Target | Alert Threshold |
|--------|--------|-----------------|
| `store_memory` latency p95 | <2s | >3s |
| `store_memory` error rate | <1% | >5% |
| `delete_memory` latency p95 | <500ms | >1s |
| `delete_memory` error rate | <1% | >5% |
| Tool usage frequency | Baseline | >50% change |

### Log Patterns

```
# Successful store
[mcp.store_memory] Memory stored user_id=X memory_id=Y duration_ms=Z

# Successful delete
[mcp.delete_memory] Memory deleted user_id=X memory_id=Y reason=Z

# Errors
[mcp.store_memory.error] Storage failed user_id=X error_code=Y
[mcp.delete_memory.error] Delete failed user_id=X memory_id=Y status=Z
```

---

## 8. Technical Notes

### Key Files to Modify

| File | Changes |
|------|---------|
| `mcp_server/tools.py` | Update store_memory, add delete_memory |
| `mcp_server/server.py` | Register delete_memory tool |
| `backend/api/prompts.py` | Add MEMORY_MANAGEMENT_SECTION |
| `backend/api/status_summarizers.py` | Add summarizers |

### Code Patterns to Follow

1. **Tool Handler Pattern** (from existing tools):
   ```python
   async def tool_handler(**args) -> Dict[str, Any]:
       config = get_config()
       url = config.get("AGENTIC_MEMORIES_URL")
       start_time = time.time()
       try:
           async with httpx.AsyncClient(timeout=10.0) as client:
               response = await client.post/delete(...)
           # Handle response
       except httpx.TimeoutException:
           # Handle timeout
       except Exception as e:
           # Handle error
   ```

2. **Logging Pattern**:
   ```python
   logger.info(
       "Operation description",
       extra={
           "user_id": user_id,
           "duration_ms": duration_ms,
           "status": "success"|"error"
       }
   )
   ```

3. **Response Pattern**:
   ```python
   return {
       "status": "success"|"error",
       "message": str,
       # Tool-specific fields
   }
   ```

---

## 9. Appendix

### A. Related Documents

- `docs/design/direct-memory-storage-design.md` - Full system design
- `agentic-memories/docs/design-direct-memory-api.md` - API implementation
- `CLAUDE.md` - Project overview

### B. API Contract Summary

**POST /v1/memories/direct**
```json
{
  "user_id": "string",
  "content": "string",

  // General fields (always stored in ChromaDB)
  "layer": "semantic",
  "type": "explicit",
  "importance": 0.8,
  "confidence": 0.9,
  "persona_tags": ["tag1", "tag2"],
  "metadata": {},

  // Optional episodic fields → triggers episodic_memories write
  "event_timestamp": "2025-12-15T10:30:00Z",
  "location": "Seattle, WA",
  "participants": ["spouse"],

  // Optional emotional fields → triggers emotional_memories write
  "emotional_state": "anxious",
  "valence": -0.3,
  "arousal": 0.7,

  // Optional procedural fields → triggers procedural_memories write
  "skill_name": "cooking",
  "proficiency_level": "intermediate"
}
```

**Response:**
```json
{
  "status": "success",
  "memory_id": "uuid",
  "message": "Memory stored successfully",
  "storage": {
    "chromadb": true,
    "episodic": true,
    "emotional": false,
    "procedural": false
  }
}
```

**DELETE /v1/memories/{memory_id}?user_id={user_id}**

Logic:
1. Get metadata from ChromaDB (check stored_in_* flags)
2. Delete from ChromaDB (always)
3. Delete from typed tables based on flags

Response:
```json
{
  "status": "success",
  "deleted": true,
  "memory_id": "uuid",
  "storage": {
    "chromadb": true,
    "episodic": true,
    "emotional": false,
    "procedural": false
  }
}
```

- Returns 200 with `{deleted: true/false, storage: {...}}`
- Returns 403 if unauthorized
- Returns 500 on error
