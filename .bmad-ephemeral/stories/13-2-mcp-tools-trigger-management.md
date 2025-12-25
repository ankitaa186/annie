# Story 13.2: MCP Tools for Trigger Management

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.2
**Status:** ready-for-dev
**Estimated Effort:** 1 day

---

## User Story

**As a** user,
**I want** to create and manage triggers through conversation with Annie,
**So that** I can set up proactive reminders and alerts naturally.

---

## Acceptance Criteria

### AC #1: create_trigger Tool
**Given** MCP server running,
**When** `create_trigger` tool registered,
**Then:**
- Full schema as defined in Design Doc Section 5.1
- Comprehensive description teaching LLM:
  - When to use (reminders, alerts, check-ins)
  - Cron expression examples
  - How to write rich action_context
- Returns created trigger with ID and next_check

### AC #2: list_triggers Tool
**Given** MCP server running,
**When** `list_triggers` tool registered,
**Then:**
- Filter by trigger_type: `cron`, `interval`, `once`, `price`, `silence`, `portfolio`, or `all`
- Option to include disabled triggers
- Returns array with id, intent_name, schedule/condition, enabled, next_check, execution_count

### AC #3: update_trigger Tool
**Given** MCP server running,
**When** `update_trigger` tool registered,
**Then:**
- Accepts trigger_id + partial updates
- Can modify schedule, condition, action_context, enabled
- Description explains pause vs delete difference

### AC #4: delete_trigger Tool
**Given** MCP server running,
**When** `delete_trigger` tool registered,
**Then:**
- Requires trigger_id + confirm=true
- Description emphasizes confirmation with user first
- Returns success confirmation

### AC #5: Tool Execution
**Given** LLM calls any trigger tool,
**When** executed,
**Then:**
- Tool calls IntentsClient
- User ID extracted from session context
- Returns structured success/failure
- Errors include clear messages for LLM

---

## Tasks

### Task 1: Create trigger tools module
- [x] Create trigger tools in `mcp_server/tools.py` (added directly to existing file)
- [x] Import IntentsClient pattern (used direct HTTP calls to agentic-memories API)
- [x] Define tool handler functions

### Task 2: Implement create_trigger tool
- [x] Define comprehensive JSON schema for create_trigger
- [x] Write detailed tool description (teaches LLM when/how to use)
- [x] Include cron expression examples in description
- [x] Implement handler calling agentic-memories `/v1/intents` endpoint
- [x] Return created trigger with ID and next_check

### Task 3: Implement list_triggers tool
- [x] Define schema with trigger_type and include_disabled filters
- [x] Implement handler calling agentic-memories `/v1/intents` GET endpoint
- [x] Format response with key fields (id, name, schedule/condition, enabled, next_check, fire_count)

### Task 4: Implement update_trigger tool
- [x] Define schema accepting trigger_id + partial update fields
- [x] Write description explaining pause vs delete
- [x] Implement handler calling agentic-memories `/v1/intents/{id}` PUT endpoint

### Task 5: Implement delete_trigger tool
- [x] Define schema requiring trigger_id and confirm=true
- [x] Write description emphasizing user confirmation first
- [x] Implement handler calling agentic-memories `/v1/intents/{id}` DELETE endpoint

### Task 6: Register tools in MCP server
- [x] Import trigger tools in `mcp_server/server.py`
- [x] Register all 4 tools with schemas
- [x] Add status emission for tool calls (handled by existing logging infrastructure)

---

## Dev Notes

### Technical Notes
- See Design Doc Section 5 for complete tool schemas
- Tool descriptions are CRITICAL - they teach the LLM how to use proactive features
- MCP server needs to call backend API (IntentsClient is in backend)
- Consider: MCP tool → Backend endpoint → IntentsClient → agentic-memories

### API Schema Reference (from agentic-memories)
**Trigger Types:** `cron`, `interval`, `once`, `price`, `silence`, `portfolio`
**Action Types:** `notify`, `check_in`, `briefing`, `analysis`, `reminder`
**Priority Levels:** `low`, `normal`, `high`, `critical`

**Create Intent Required Fields:**
- `user_id`, `intent_name`, `trigger_type`, `action_context`
- For time-based: `trigger_schedule` with cron/interval_minutes/trigger_at
- For condition-based: `trigger_condition` with expression, condition_type, cooldown_hours

### Files to Create/Modify
- `mcp_server/tools/triggers.py` (new)
- `mcp_server/server.py` (register tools)
- `backend/api/routes/` (may need backend endpoints for MCP to call)

### Tool Description Guidelines
- Explain WHEN to use the tool (signal phrases, user intent)
- Provide EXAMPLES of cron expressions
- Describe action_context structure and purpose
- Emphasize confirmation before destructive actions

---

## Dev Agent Record

### Context Reference
- **Story Context File:** `.bmad-ephemeral/stories/13-2-mcp-tools-trigger-management.context.xml`
- **Generated:** 2025-12-24
- **Architecture Reference:** `docs/design/proactive-ai-architecture.md` (Sections 3, 4, 5)
- **Tool Pattern Reference:** `mcp_server/tools.py` (existing tool patterns)
- **HTTP Client Pattern:** `backend/api/memory_client.py` (async client pattern)

### Implementation Notes
- **Date:** 2025-12-25
- **Implementation Approach:** Added trigger management tools directly to `mcp_server/tools.py` following existing patterns
- **API Integration:** Tools make direct HTTP calls to agentic-memories `/v1/intents` endpoints (no backend intermediary)
- **Tool Count:** 4 new tools registered: create_trigger, list_triggers, update_trigger, delete_trigger
- **Key Design Decisions:**
  1. Used user-friendly terminology ("trigger" in tool names and descriptions, mapped to "intent" in backend API)
  2. Comprehensive tool descriptions teach LLM when and how to use proactive features
  3. Included cron expression examples and guidance in create_trigger description
  4. Required confirmation for destructive delete operation (confirm=true parameter)
  5. Explained pause vs delete difference in update_trigger description
  6. All tools follow established patterns: async handlers, httpx client, structured logging, error handling
- **Files Modified:**
  - `/Users/ankit/dev/annie/mcp_server/tools.py` - Added 4 tool handlers and definitions (~900 lines)
  - `/Users/ankit/dev/annie/mcp_server/server.py` - Imported and registered new tools
- **Syntax Verification:** Both files compile successfully with python3 -m py_compile

### Verification
- [x] Tools registered in MCP server (16 total tools including 4 new trigger tools)
- [x] create_trigger tool has comprehensive schema with schedule and condition parameters
- [x] create_trigger tool has detailed description with cron examples and action_context guidance
- [x] list_triggers tool has filtering by trigger_type and include_disabled parameters
- [x] update_trigger tool has partial update support and pause vs delete explanation
- [x] delete_trigger tool requires confirm=true parameter for safety
- [x] All tools call agentic-memories `/v1/intents` endpoints directly
- [x] All tools follow established patterns (async, httpx, logging, error handling)
- [x] Python syntax verified with py_compile

**Ready for Integration Testing:**
- [ ] LLM can create scheduled triggers via conversation
- [ ] LLM can create condition triggers via conversation
- [ ] LLM can list user's triggers
- [ ] LLM can update/pause triggers
- [ ] LLM confirms before deleting triggers

**Note:** Integration testing requires agentic-memories service with intents API endpoints (Epic 5) to be implemented first.
