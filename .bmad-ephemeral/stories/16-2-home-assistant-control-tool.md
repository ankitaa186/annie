# Story 16.2: Home Assistant Control Tool (Allowlist-Enforced)

Status: done

## Story

**As a** user of Annie,
**I want** to control my Home Assistant entities (lights, switches, climate, covers) through voice commands,
**So that** Annie can execute actions like "Turn on the living room lights" or "Set the thermostat to 72" with proper security enforcement.

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P0
**Estimated Effort:** 1.5 days
**Prerequisites:** Story 16.1 (HomeAssistantClient base class)

## Acceptance Criteria

### AC #1: Allowlist Parsing
**Given** the `HA_CONTROL_ALLOWLIST` environment variable is set
**When** the tool initializes
**Then** the allowlist is parsed into a list of allowed entity patterns

**Testable:** Set HA_CONTROL_ALLOWLIST="light.living_room,switch.fan", verify parsing returns 2 entries

---

### AC #2: Exact Match Allowlist
**Given** an entity ID "light.living_room" in the allowlist
**When** a control request is made for "light.living_room"
**Then** the request is allowed and executed

**Testable:** Control exact-match entity, verify success response

---

### AC #3: Wildcard Allowlist Support
**Given** a pattern "light.*" in the allowlist
**When** a control request is made for "light.bedroom" or "light.kitchen"
**Then** the request is allowed for any entity in the "light" domain

**Testable:** Control "light.any_room" with "light.*" in allowlist, verify success

---

### AC #4: Empty Allowlist Blocks All Control
**Given** `HA_CONTROL_ALLOWLIST` is empty or not set
**When** any control request is made
**Then** the request returns FORBIDDEN error with message explaining all control is disabled

**Testable:** Unset HA_CONTROL_ALLOWLIST, attempt control, verify FORBIDDEN

---

### AC #5: FORBIDDEN Error Includes Allowed Entities
**Given** an entity "light.bedroom" NOT in the allowlist
**When** a control request is made for that entity
**Then** the error response includes the list of actually allowed entities

**Testable:** Control non-allowed entity, verify error_message contains allowed list

---

### AC #6: Action to Service Mapping
**Given** control actions (turn_on, turn_off, toggle, set_brightness, set_temperature, set_position, set_hvac_mode)
**When** the tool executes an action
**Then** the action maps to the correct Home Assistant service call

| Action | Domain | HA Service | Parameters |
|--------|--------|------------|------------|
| turn_on | light/switch/fan | turn_on | entity_id |
| turn_off | light/switch/fan | turn_off | entity_id |
| toggle | light/switch | toggle | entity_id |
| set_brightness | light | turn_on | entity_id, brightness (0-255) |
| set_temperature | climate | set_temperature | entity_id, temperature |
| set_hvac_mode | climate | set_hvac_mode | entity_id, hvac_mode |
| set_position | cover | set_cover_position | entity_id, position (0-100) |

**Testable:** Test each action maps to correct POST /api/services/{domain}/{service}

---

### AC #7: Previous and New State in Response
**Given** a successful control operation
**When** the operation completes
**Then** the response includes `previous_state` (before action) and `new_state` (after action)

**Testable:** Control a light, verify response has both state fields

---

### AC #8: Audit Logging for All Attempts
**Given** any control request (allowed or denied)
**When** the request is processed
**Then** structured logs include: tool_name, entity_id, action, allowed (true/false), duration_ms

**Testable:** Check logs after allowed and denied requests, verify all fields present

---

### AC #9: Unit Tests for Allowlist and Control
**Given** the tool implementation
**When** unit tests are run
**Then** all test cases pass with >90% code coverage

**Testable:** Run pytest with coverage, verify threshold met

---

## Tasks / Subtasks

### Task 1: Implement AllowlistValidator Class (AC: #1, #2, #3, #4)
- [x] Create `AllowlistValidator` class in `mcp_server/tools/home_assistant.py`
- [x] Parse `HA_CONTROL_ALLOWLIST` env var (comma-separated)
- [x] Implement `is_allowed(entity_id: str) -> bool` method
- [x] Handle exact match: "light.living_room" matches "light.living_room"
- [x] Handle wildcard: "light.*" matches any "light.xxx"
- [x] Handle empty allowlist: return False for all entities
- [x] Implement `get_allowed_list() -> List[str]` for error messages

### Task 2: Implement Control Methods in HomeAssistantClient (AC: #6, #7)
- [x] Add `call_service(domain: str, service: str, entity_id: str, data: dict) -> dict` method
  - POST `/api/services/{domain}/{service}` with Bearer auth
  - Parse response for success/failure
- [x] Implement `get_domain_from_entity(entity_id: str) -> str` helper
  - Extract domain from entity_id (e.g., "light" from "light.living_room")
- [x] Implement `map_action_to_service(action: str, entity_id: str) -> tuple[str, str, dict]`
  - Returns (domain, service_name, additional_data)
  - Handle all 7 action types

### Task 3: Create MCP Tool Handler (AC: #5, #7, #8)
- [x] Create `home_assistant_control` tool function
- [x] Define input schema with entity_id, action, parameters
- [x] Check allowlist BEFORE making any API call
- [x] If denied: return FORBIDDEN with allowed entities list
- [x] If allowed:
  - Get current state first (for previous_state)
  - Call the service
  - Get new state after (for new_state)
- [x] Format success response: status, provider, entity_id, action, parameters, previous_state, new_state
- [x] Add structured logging with allowed=true/false

### Task 4: Write Unit Tests (AC: #9)
- [x] Create tests in `mcp_server/tests/test_home_assistant_control.py`
- [x] Test: `test_allowlist_parsing()` - comma-separated parsing
- [x] Test: `test_allowlist_exact_match()` - exact entity match
- [x] Test: `test_allowlist_wildcard_match()` - domain wildcard
- [x] Test: `test_allowlist_empty_blocks_all()` - empty list behavior
- [x] Test: `test_control_allowed_entity()` - successful control
- [x] Test: `test_control_forbidden_entity()` - denied with allowed list
- [x] Test: `test_control_turn_on()` - turn_on action mapping
- [x] Test: `test_control_turn_off()` - turn_off action mapping
- [x] Test: `test_control_toggle()` - toggle action mapping
- [x] Test: `test_control_set_brightness()` - brightness with parameters
- [x] Test: `test_control_set_temperature()` - climate control
- [x] Test: `test_control_set_hvac_mode()` - HVAC mode
- [x] Test: `test_control_set_position()` - cover position
- [x] Test: `test_control_returns_states()` - previous/new state
- [x] Test: `test_audit_logging()` - verify log fields
- [x] Use pytest-httpx or respx for mocking
- [x] Verify >90% code coverage

### Task 5: Tool Registration (Deferred to Story 16.5)
- [x] Note: Tool will be exported and registered in Story 16.5
- [x] Prepare tool for export in `mcp_server/tools/__init__.py`

---

## Dev Notes

### Implementation Approach

This story EXTENDS the `home_assistant.py` file created in Story 16.1:
- Reuse `HomeAssistantClient` class for HTTP requests
- Add `AllowlistValidator` as new class
- Add `home_assistant_control` as second tool function

### Security: Allowlist is CRITICAL

**NEVER bypass the allowlist check.** The code path must be:

```python
def home_assistant_control(entity_id, action, parameters):
    # STEP 1: Check allowlist FIRST
    if not allowlist_validator.is_allowed(entity_id):
        return {
            "status": "error",
            "error_code": "FORBIDDEN",
            "error_message": f"Entity '{entity_id}' not in allowlist. Allowed: {allowlist_validator.get_allowed_list()}",
            "entity_id": entity_id
        }

    # STEP 2: Only if allowed, proceed with control
    ...
```

### Allowlist Patterns

```python
# Parsing examples:
"light.living_room,switch.fan" → ["light.living_room", "switch.fan"]
"light.*,climate.thermostat" → ["light.*", "climate.thermostat"]
"" → []  # Empty = block all

# Matching logic:
def is_allowed(entity_id: str) -> bool:
    for pattern in self.patterns:
        if pattern.endswith(".*"):
            domain = pattern[:-2]  # Remove ".*"
            if entity_id.startswith(f"{domain}."):
                return True
        elif pattern == entity_id:
            return True
    return False
```

### Service Call Mapping

```python
ACTION_MAP = {
    "turn_on": lambda entity_id: (get_domain(entity_id), "turn_on", {}),
    "turn_off": lambda entity_id: (get_domain(entity_id), "turn_off", {}),
    "toggle": lambda entity_id: (get_domain(entity_id), "toggle", {}),
    "set_brightness": lambda entity_id: ("light", "turn_on", {}),  # brightness in parameters
    "set_temperature": lambda entity_id: ("climate", "set_temperature", {}),
    "set_hvac_mode": lambda entity_id: ("climate", "set_hvac_mode", {}),
    "set_position": lambda entity_id: ("cover", "set_cover_position", {}),
}
```

### Tool Schema

```python
{
    "name": "home_assistant_control",
    "description": (
        "Control Home Assistant entities. SECURITY: Only entities in "
        "HA_CONTROL_ALLOWLIST can be controlled. Attempting to control "
        "non-allowlisted entities returns FORBIDDEN error."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": "Entity ID to control (e.g., 'light.living_room')"
            },
            "action": {
                "type": "string",
                "enum": ["turn_on", "turn_off", "toggle", "set_brightness", "set_temperature", "set_position", "set_hvac_mode"],
                "description": "Action to perform"
            },
            "parameters": {
                "type": "object",
                "description": "Action parameters (e.g., {brightness: 128}, {temperature: 72})",
                "additionalProperties": true
            }
        },
        "required": ["entity_id", "action"]
    }
}
```

### Response Formats

**Success:**
```python
{
    "status": "success",
    "provider": "home_assistant",
    "entity_id": "light.living_room",
    "action": "turn_on",
    "parameters": {"brightness": 200},
    "previous_state": "off",
    "new_state": "on"
}
```

**Forbidden:**
```python
{
    "status": "error",
    "provider": "home_assistant",
    "error_code": "FORBIDDEN",
    "error_message": "Entity 'light.bedroom' not in allowlist. Allowed: light.living_room, switch.fan",
    "entity_id": "light.bedroom"
}
```

### Project Structure Notes

- Extends: `mcp_server/tools/home_assistant.py` (from Story 16.1)
- New test file: `mcp_server/tests/test_home_assistant_control.py`
- Config dependency: `HA_CONTROL_ALLOWLIST` env var (added in Story 16.4)

### Performance Targets

| Metric | Target |
|--------|--------|
| Control latency p95 | <1s |
| Allowlist check | <1ms |
| Success rate | >99% (local network) |

### Learnings from Previous Story

**From Story 16-1 (Status: drafted)**

- **HomeAssistantClient**: Reuse the HTTP client class with Bearer auth, timeout handling
- **Error codes**: Use same error format (CONFIG_ERROR, UNAUTHORIZED, TIMEOUT, NETWORK_ERROR)
- **Logging pattern**: Include tool_name, entity_id, duration_ms in all logs
- **File location**: Same file `mcp_server/tools/home_assistant.py`

[Source: stories/16-1-home-assistant-query-tool.md]

### References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.2]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-16.md#Detailed-Design]
- [Source: Home Assistant REST API - Services](https://developers.home-assistant.io/docs/api/rest#post-apiservicesdomainservice)

---

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/16-2-home-assistant-control-tool.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Used singleton pattern for AllowlistValidator with reset function for testing
- Added asyncio.sleep(0.2) after service call to allow HA to process state changes

### Completion Notes List

- Implemented AllowlistValidator class with exact match and wildcard pattern support
- Added call_service() method to HomeAssistantClient for POST /api/services/{domain}/{service}
- Created map_action_to_service() function handling all 7 action types
- home_assistant_control_handler checks allowlist FIRST (security critical)
- Returns FORBIDDEN with allowed list when entity not permitted
- Captures previous_state and new_state for all control operations
- Audit logging includes allowed=true/false for all control attempts
- 37 unit tests covering all acceptance criteria
- All 68 Home Assistant tests pass (31 query + 37 control)

### File List

**Modified:**
- `mcp_server/tools/home_assistant.py` (extended from 445 to 914 lines)
- `mcp_server/tools/__init__.py` (added control tool exports)

**Created:**
- `mcp_server/tests/test_home_assistant_control.py` (37 tests, all passing)

---

## Senior Developer Review (AI)

### Reviewer
Ankit

### Date
2026-01-10

### Outcome
**APPROVE**

All acceptance criteria are fully implemented with comprehensive test coverage. The security-critical allowlist enforcement is properly implemented - the check occurs BEFORE any API call to Home Assistant. Code quality is high, following established patterns from Epic 15 tools.

### Summary

Story 16.2 implements a complete Home Assistant control tool with mandatory allowlist enforcement. The implementation correctly extends Story 16.1's HomeAssistantClient with control capabilities. Key security requirement (allowlist check first) is properly enforced. All 37 tests pass.

### Key Findings

**No blocking issues found.**

| Severity | Finding | Location |
|----------|---------|----------|
| - | No issues | - |

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC#1 | Allowlist Parsing | IMPLEMENTED | `home_assistant.py:29-51` - AllowlistValidator parses comma-separated patterns |
| AC#2 | Exact Match Allowlist | IMPLEMENTED | `home_assistant.py:72-73` - exact match in is_allowed() |
| AC#3 | Wildcard Allowlist Support | IMPLEMENTED | `home_assistant.py:67-71` - wildcard with ".*" suffix |
| AC#4 | Empty Allowlist Blocks All | IMPLEMENTED | `home_assistant.py:63-64, 747-748` - returns False, FORBIDDEN error |
| AC#5 | FORBIDDEN Error Includes Allowed | IMPLEMENTED | `home_assistant.py:744-746` - error message includes allowed list |
| AC#6 | Action to Service Mapping | IMPLEMENTED | `home_assistant.py:519-575` - all 7 actions mapped |
| AC#7 | Previous and New State | IMPLEMENTED | `home_assistant.py:797-801, 823-830, 855-856` |
| AC#8 | Audit Logging for All Attempts | IMPLEMENTED | `home_assistant.py:750-760` (denied), `835-847` (allowed) |
| AC#9 | Unit Tests >90% Coverage | IMPLEMENTED | 37 tests, all passing |

**Summary: 9 of 9 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked | Verified | Evidence |
|------|--------|----------|----------|
| Task 1: AllowlistValidator Class (7 subtasks) | [x] | VERIFIED | `home_assistant.py:29-104` |
| Task 2: Control Methods (3 subtasks) | [x] | VERIFIED | `home_assistant.py:401-575` |
| Task 3: MCP Tool Handler (8 subtasks) | [x] | VERIFIED | `home_assistant.py:715-913` |
| Task 4: Unit Tests (17 subtasks) | [x] | VERIFIED | `test_home_assistant_control.py` - 37 tests |
| Task 5: Tool Export (2 subtasks) | [x] | VERIFIED | `__init__.py:120-131, 220-229` |

**Summary: 27 of 27 completed tasks verified, 0 questionable, 0 falsely marked complete**

### Test Coverage and Gaps

- **37 unit tests** covering all ACs
- Test classes organized by functionality:
  - `TestAllowlistValidator` (10 tests) - AC#1-4
  - `TestActionMapping` (12 tests) - AC#6
  - `TestHomeAssistantControlHandler` (6 tests) - AC#5, 7, 8
  - `TestHomeAssistantControlToolSchema` (3 tests)
  - `TestHomeAssistantClientControl` (4 tests)
  - `TestControlWithParameters` (2 tests)

**No test gaps identified.**

### Architectural Alignment

- Extends HomeAssistantClient from Story 16.1 as specified
- Uses singleton pattern for AllowlistValidator (efficient, testable)
- Follows MCP tool patterns (async handler, tool dict, structured logging)
- Security constraint enforced: allowlist check BEFORE any API call

### Security Notes

- CRITICAL security requirement met: allowlist check at line 736-768 occurs BEFORE any API call
- Empty allowlist (HA_CONTROL_ALLOWLIST="") blocks ALL control with FORBIDDEN error
- All control attempts logged with `allowed=true/false` for audit trail
- Bearer token authentication properly implemented

### Best-Practices and References

- [Home Assistant REST API - Services](https://developers.home-assistant.io/docs/api/rest#post-apiservicesdomainservice)
- Pattern: Singleton for validators with reset function for testing
- Pattern: Async HTTP client with context manager

### Action Items

**Code Changes Required:**
- None

**Advisory Notes:**
- Note: Tool registration in server.py will happen in Story 16.5
- Note: The 0.2s sleep after service call allows HA to process state changes - consider making this configurable if latency becomes an issue
- Note: Consider adding retry logic for transient network errors in production

---

**Created:** 2025-01-10
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.2 - Home Assistant Control Tool (Allowlist-Enforced)
