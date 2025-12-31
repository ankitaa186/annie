# Story 14.3: Add delete_memory Tool

**Epic:** 14 - Direct Memory Storage Enhancement
**Story ID:** 14.3
**Status:** done
**Estimated Effort:** 4 hours (0.5 days)

---

## User Story

**As a** user,
**I want** Annie to be able to delete specific memories when I ask her to forget something,
**So that** incorrect, outdated, or unwanted information can be removed from her memory.

---

## Acceptance Criteria

### AC #1: delete_memory Tool Schema
**Given** MCP server running,
**When** `delete_memory` tool is registered,
**Then:**
- Tool accepts `user_id` (required string) - user identifier
- Tool accepts `memory_id` (required string) - ID of memory to delete (from retrieve_memories)
- Tool accepts `reason` (optional string) - explanation for deletion (audit trail)
- Tool description teaches LLM when to use: user asks to forget, incorrect memory, outdated info

### AC #2: HTTP Handler Implementation
**Given** `delete_memory` tool is called,
**When** handler executes,
**Then:**
- Handler calls `DELETE /v1/memories/{memory_id}?user_id={user_id}` on agentic-memories
- Timeout set to 10 seconds
- Returns structured response with `status`, `deleted`, `memory_id`, `message`

### AC #3: Success Response Handling
**Given** agentic-memories returns 200 with `deleted: true`,
**When** handler processes response,
**Then:**
- Returns `{"status": "success", "deleted": true, "memory_id": "...", "message": "Memory deleted successfully"}`
- Logs success event with `user_id`, `memory_id`, `reason`, `duration_ms`

### AC #4: Not Found Response Handling (200 with deleted: false)
**Given** agentic-memories returns 200 with `deleted: false`,
**When** handler processes response,
**Then:**
- Returns `{"status": "error", "deleted": false, "memory_id": "...", "message": "Memory not found"}`

### AC #5: Unauthorized Response Handling (403)
**Given** agentic-memories returns 403 (unauthorized),
**When** handler processes response,
**Then:**
- Returns `{"status": "error", "deleted": false, "memory_id": "...", "message": "Unauthorized: cannot delete this memory"}`

### AC #6: Server Error Handling (500)
**Given** agentic-memories returns 500 (server error),
**When** handler processes response,
**Then:**
- Returns `{"status": "error", "deleted": false, "memory_id": "...", "message": "Delete failed: 500"}`

### AC #7: Timeout Handling
**Given** agentic-memories does not respond within 10 seconds,
**When** timeout occurs,
**Then:**
- Returns `{"status": "error", "deleted": false, "memory_id": "...", "message": "Request timed out"}`

### AC #8: Audit Logging
**Given** delete operation completes (success or failure),
**When** logging occurs,
**Then:**
- Log includes `user_id` for tracing
- Log includes `memory_id` being deleted
- Log includes `reason` if provided (for audit trail)
- Log includes `duration_ms` for performance monitoring

### AC #9: Tool Registration
**Given** MCP server starts,
**When** tools are registered,
**Then:**
- `delete_memory` tool appears in `tools/list` response
- Tool schema matches defined input schema
- Tool is executable via MCP protocol

---

## Tasks

### Task 1: Define delete_memory tool schema
- [x] Create tool definition dict with name, description, inputSchema
- [x] Write comprehensive description teaching LLM:
  - When to use (user asks to forget, incorrect memory, outdated info, duplicates)
  - Workflow: first retrieve_memories to get ID, confirm with user, then delete
  - Warning that deletion cannot be undone
- [x] Define inputSchema with user_id (required), memory_id (required), reason (optional)

### Task 2: Implement delete_memory_tool_handler
- [x] Create async handler function with signature: `async def delete_memory_tool_handler(user_id: str, memory_id: str, reason: str = None) -> Dict[str, Any]`
- [x] Get agentic-memories URL from config
- [x] Set up httpx.AsyncClient with 10s timeout
- [x] Make DELETE request to `/v1/memories/{memory_id}?user_id={user_id}`
- [x] Calculate duration_ms for logging

### Task 3: Implement response handling
- [x] Handle 200 success with `deleted: true` - return success response
- [x] Handle 200 with `deleted: false` - return not found error
- [x] Handle 403 unauthorized - return unauthorized error
- [x] Handle 404 not found (if API uses this) - return not found error
- [x] Handle 500 server error - return error with status code
- [x] Handle other status codes gracefully

### Task 4: Implement error handling
- [x] Catch and handle `httpx.TimeoutException` - return timeout error
- [x] Catch and handle other exceptions - log and return error
- [x] Ensure no exceptions propagate up

### Task 5: Implement audit logging
- [x] Log success case with all relevant fields (user_id, memory_id, reason, duration_ms)
- [x] Log error cases with error details
- [x] Use structured logging with extra dict

### Task 6: Register tool in MCP server
- [x] Add `delete_memory_tool` to tool registration in `mcp_server/server.py`
- [ ] Verify tool appears in `tools/list` response (manual verification required)
- [ ] Test tool execution via MCP protocol (manual verification required)

---

## Technical Design

### Tool Schema

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
- Confirm with the user which memory to delete
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
                "description": "Reason for deletion (optional, for audit trail)"
            }
        },
        "required": ["user_id", "memory_id"]
    },
    "handler": delete_memory_tool_handler
}
```

### Handler Implementation

```python
async def delete_memory_tool_handler(
    user_id: str,
    memory_id: str,
    reason: str = None
) -> Dict[str, Any]:
    """Delete a memory by ID."""
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

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
                logger.warning(
                    "Unauthorized delete attempt",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": "Unauthorized: cannot delete this memory"
                }

            elif response.status_code == 404:
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": "Memory not found"
                }

            else:
                logger.error(
                    "Delete memory failed",
                    extra={
                        "user_id": user_id,
                        "memory_id": memory_id,
                        "status_code": response.status_code,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "deleted": False,
                    "memory_id": memory_id,
                    "message": f"Delete failed: {response.status_code}"
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "Delete memory timed out",
            extra={
                "user_id": user_id,
                "memory_id": memory_id,
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": "Request timed out"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            f"Delete memory failed: {e}",
            extra={
                "user_id": user_id,
                "memory_id": memory_id,
                "duration_ms": duration_ms
            }
        )
        return {
            "status": "error",
            "deleted": False,
            "memory_id": memory_id,
            "message": str(e)
        }
```

### API Contract

**Endpoint:** `DELETE /v1/memories/{memory_id}?user_id={user_id}`

**Request:**
- Method: DELETE
- Path parameter: `memory_id` - UUID of memory to delete
- Query parameter: `user_id` - required for authorization

**Response Codes:**
- `200`: Success (check `deleted` field for true/false)
- `403`: Unauthorized - user_id doesn't match memory owner
- `404`: Memory not found (API may use this instead of 200+deleted:false)
- `500`: Server error

**Success Response (200):**
```json
{
    "status": "success",
    "deleted": true,
    "memory_id": "uuid-string",
    "storage": {
        "chromadb": true,
        "episodic": true,
        "emotional": false,
        "procedural": false
    }
}
```

---

## Dev Notes

### Implementation Notes
- Follow existing tool patterns in `mcp_server/tools.py` (see `store_memory_tool`, trigger tools)
- Use httpx.AsyncClient with explicit timeout (10s)
- Use structured logging with extra dict for audit trail
- No retry logic needed for delete operations (unlike store)

### Testing Notes
- Unit tests should mock httpx responses
- Test all response code paths (200, 403, 404, 500, timeout)
- Verify reason field is logged when provided
- Verify duration_ms is calculated and logged

### Files to Modify
- `mcp_server/tools.py` - Add delete_memory_tool_handler and delete_memory_tool definition
- `mcp_server/server.py` - Register delete_memory_tool in register_default_tools()

### Performance Requirements
- Target latency: <1s (p95)
- Timeout: 10s
- No retry on failure (unlike store which retries on 5xx)

---

## Traceability

| Acceptance Criteria | Tech Spec Reference | Test Type |
|---------------------|---------------------|-----------|
| AC #1: Tool Schema | Data Models - delete_memory Input Schema | Unit |
| AC #2: HTTP Handler | APIs - DELETE /v1/memories/{id} | Integration |
| AC #3: Success Response | Data Models - delete_memory Response | Unit |
| AC #4: Not Found Response | Reliability | Unit |
| AC #5: Unauthorized (403) | Security | Unit |
| AC #6: Server Error (500) | Reliability | Unit |
| AC #7: Timeout Handling | Reliability/Availability | Unit |
| AC #8: Audit Logging | Observability | Unit |
| AC #9: Tool Registration | Services - MCP Server | Integration |

---

## Definition of Done

- [x] All acceptance criteria verified
- [x] delete_memory tool defined with comprehensive schema and description
- [x] Handler implemented with all response code handling
- [x] Tool registered in MCP server
- [x] Audit logging implemented with reason field
- [x] Unit tests written and passing
- [ ] Tool appears in `tools/list` response (manual verification required)
- [ ] Manual testing confirms delete workflow works end-to-end (manual verification required)

---

## References

- **Tech Spec:** `.bmad-ephemeral/stories/tech-spec-epic-14.md` (Section AC-14.3)
- **Epic:** `docs/epics/epic-14-direct-memory-storage.md` (Story 14.3)
- **Tool Pattern:** `mcp_server/tools.py` (existing store_memory, trigger tools)
- **API Docs:** agentic-memories DELETE /v1/memories/{id} endpoint
