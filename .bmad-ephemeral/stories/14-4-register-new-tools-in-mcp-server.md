# Story 14.4: Register New Tools in MCP Server

**Epic:** 14 - Direct Memory Storage Enhancement
**Story ID:** 14.4
**Status:** done
**Estimated Effort:** 1 hour

---

## User Story

**As a** developer,
**I want** the updated store_memory and new delete_memory tools registered in MCP server,
**So that** both tools appear in the `tools/list` response and are executable via MCP protocol.

---

## Acceptance Criteria

### AC #1: delete_memory Tool Registration
**Given** MCP server is initialized,
**When** `register_default_tools()` is called,
**Then:**
- `delete_memory_tool` is imported from `mcp_server/tools.py`
- `delete_memory_tool` is registered with `self.tool_registry.register()`
- Tool appears in `tools/list` response with correct schema

### AC #2: store_memory Tool Updated Registration
**Given** MCP server is initialized,
**When** `register_default_tools()` is called,
**Then:**
- Updated `store_memory_tool` (with new direct API schema) is registered
- Tool appears in `tools/list` response with updated schema
- Schema includes `content` field (required) and optional typed fields

### AC #3: Tools Executable via MCP Protocol
**Given** both tools are registered,
**When** `tools/call` request is made,
**Then:**
- `store_memory` tool executes correctly via MCP protocol
- `delete_memory` tool executes correctly via MCP protocol
- JSON-RPC 2.0 responses are properly formatted

### AC #4: tools/list Response
**Given** MCP server is running,
**When** GET `/tools/list` is called,
**Then:**
- Response includes both `store_memory` and `delete_memory` tools
- Each tool has `name`, `description`, and `inputSchema` fields
- Total tool count increases by 1 (delete_memory is new)

---

## Tasks

### Task 1: Import delete_memory_tool
- [ ] Add `delete_memory_tool` to import statement in `mcp_server/server.py`
- [ ] Verify `delete_memory_tool` is exported from `mcp_server/tools.py` (Story 14.3)

### Task 2: Register delete_memory Tool
- [ ] Add `self.tool_registry.register(delete_memory_tool)` in `register_default_tools()`
- [ ] Place after `compact_memories_tool` registration (keep memory tools grouped)
- [ ] Add comment indicating Epic 14 addition

### Task 3: Verify store_memory Tool Update
- [ ] Confirm updated `store_memory_tool` schema is being imported
- [ ] No change to registration needed (already registered)
- [ ] Verify tool description mentions direct API usage

### Task 4: Syntax Verification
- [ ] Run `python3 -m py_compile mcp_server/server.py`
- [ ] Ensure no import errors

### Task 5: Verify tools/list Response
- [ ] Start MCP server locally
- [ ] Call GET `/tools/list` endpoint
- [ ] Verify `delete_memory` appears in response
- [ ] Verify `store_memory` has updated schema
- [ ] Confirm total tool count increased

---

## Dev Notes

### Technical Notes
- This story depends on Story 14.3 (delete_memory tool implementation)
- This story depends on Story 14.1 & 14.2 (store_memory tool updates)
- MCP server uses HTTP transport with FastAPI
- Tool registration follows established patterns from Epic 13 (trigger tools)

### Current Tool Registration Pattern
```python
# In mcp_server/server.py
from mcp_server.tools import (
    ToolRegistry,
    health_check_tool,
    store_memory_tool,
    retrieve_memories_tool,
    compact_memories_tool,
    # ... other tools
)

def register_default_tools(self):
    self.tool_registry.register(health_check_tool)
    self.tool_registry.register(store_memory_tool)
    self.tool_registry.register(retrieve_memories_tool)
    self.tool_registry.register(compact_memories_tool)
    # ... other tools
```

### Required Changes
```python
# In mcp_server/server.py imports
from mcp_server.tools import (
    # ... existing imports ...
    delete_memory_tool,  # NEW - Epic 14
)

def register_default_tools(self):
    self.tool_registry.register(health_check_tool)
    self.tool_registry.register(store_memory_tool)      # Updated in Story 14.1/14.2
    self.tool_registry.register(retrieve_memories_tool)
    self.tool_registry.register(compact_memories_tool)
    self.tool_registry.register(delete_memory_tool)     # NEW - Epic 14
    # ... other tools
```

### Files to Modify
- `mcp_server/server.py` - Add import and registration for delete_memory_tool

### Dependencies
- **Story 14.1** - Update store_memory tool schema (must be complete)
- **Story 14.2** - Update store_memory tool handler (must be complete)
- **Story 14.3** - Add delete_memory tool (must be complete)

### Verification Commands
```bash
# Syntax check
python3 -m py_compile mcp_server/server.py

# Start MCP server
docker compose up mcp-server

# Test tools/list endpoint
curl http://localhost:8002/tools/list | jq '.result.tools[] | .name'

# Expected output should include:
# "store_memory"
# "delete_memory"
```

---

## Dev Agent Record

### Context Reference
- **Tech Spec:** `.bmad-ephemeral/stories/tech-spec-epic-14.md` (Section: AC-14.4)
- **Epic Document:** `docs/epics/epic-14-direct-memory-storage.md` (Story 14.4)
- **Server File:** `mcp_server/server.py` (current state with 18 registered tools)
- **Tools File:** `mcp_server/tools.py` (contains tool definitions)

### Traceability
| AC ID | Spec Section | Test Type |
|-------|--------------|-----------|
| AC #1 | AC-14.4.1 | Unit: registration check |
| AC #2 | AC-14.4.2 | Unit: schema verification |
| AC #3 | AC-14.4.3 | Integration: tool execution |
| AC #4 | AC-14.4.1-2 | Integration: tools/list response |

### Implementation Notes
- **Date:** TBD
- **Implementation Approach:** TBD
- **Files Modified:** TBD
- **Verification Status:** TBD

### Verification Checklist
- [ ] `delete_memory_tool` imported in server.py
- [ ] `delete_memory_tool` registered in `register_default_tools()`
- [ ] Python syntax verification passes
- [ ] `tools/list` includes both store_memory and delete_memory
- [ ] store_memory tool schema shows updated `content` field
- [ ] delete_memory tool schema shows `memory_id` and `reason` fields
- [ ] Both tools executable via `tools/call` endpoint
- [ ] Tool count increased from 18 to 19

---

## Related Stories

| Story | Dependency Type | Status |
|-------|-----------------|--------|
| 14.1 - Update store_memory Tool Schema | Blocking | TBD |
| 14.2 - Update store_memory Tool Handler | Blocking | TBD |
| 14.3 - Add delete_memory Tool | Blocking | TBD |
| 14.5 - Add Memory Instructions to System Prompt | Non-blocking | TBD |
