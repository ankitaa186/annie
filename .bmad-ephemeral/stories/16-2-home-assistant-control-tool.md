# Story 16.2: Home Assistant Control Tool (Allowlist-Enforced)

Status: drafted

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
- [ ] Create `AllowlistValidator` class in `mcp_server/tools/home_assistant.py`
- [ ] Parse `HA_CONTROL_ALLOWLIST` env var (comma-separated)
- [ ] Implement `is_allowed(entity_id: str) -> bool` method
- [ ] Handle exact match: "light.living_room" matches "light.living_room"
- [ ] Handle wildcard: "light.*" matches any "light.xxx"
- [ ] Handle empty allowlist: return False for all entities
- [ ] Implement `get_allowed_list() -> List[str]` for error messages

### Task 2: Implement Control Methods in HomeAssistantClient (AC: #6, #7)
- [ ] Add `call_service(domain: str, service: str, entity_id: str, data: dict) -> dict` method
  - POST `/api/services/{domain}/{service}` with Bearer auth
  - Parse response for success/failure
- [ ] Implement `get_domain_from_entity(entity_id: str) -> str` helper
  - Extract domain from entity_id (e.g., "light" from "light.living_room")
- [ ] Implement `map_action_to_service(action: str, entity_id: str) -> tuple[str, str, dict]`
  - Returns (domain, service_name, additional_data)
  - Handle all 7 action types

### Task 3: Create MCP Tool Handler (AC: #5, #7, #8)
- [ ] Create `home_assistant_control` tool function
- [ ] Define input schema with entity_id, action, parameters
- [ ] Check allowlist BEFORE making any API call
- [ ] If denied: return FORBIDDEN with allowed entities list
- [ ] If allowed:
  - Get current state first (for previous_state)
  - Call the service
  - Get new state after (for new_state)
- [ ] Format success response: status, provider, entity_id, action, parameters, previous_state, new_state
- [ ] Add structured logging with allowed=true/false

### Task 4: Write Unit Tests (AC: #9)
- [ ] Create tests in `mcp_server/tests/test_home_assistant_control.py`
- [ ] Test: `test_allowlist_parsing()` - comma-separated parsing
- [ ] Test: `test_allowlist_exact_match()` - exact entity match
- [ ] Test: `test_allowlist_wildcard_match()` - domain wildcard
- [ ] Test: `test_allowlist_empty_blocks_all()` - empty list behavior
- [ ] Test: `test_control_allowed_entity()` - successful control
- [ ] Test: `test_control_forbidden_entity()` - denied with allowed list
- [ ] Test: `test_control_turn_on()` - turn_on action mapping
- [ ] Test: `test_control_turn_off()` - turn_off action mapping
- [ ] Test: `test_control_toggle()` - toggle action mapping
- [ ] Test: `test_control_set_brightness()` - brightness with parameters
- [ ] Test: `test_control_set_temperature()` - climate control
- [ ] Test: `test_control_set_hvac_mode()` - HVAC mode
- [ ] Test: `test_control_set_position()` - cover position
- [ ] Test: `test_control_returns_states()` - previous/new state
- [ ] Test: `test_audit_logging()` - verify log fields
- [ ] Use pytest-httpx or respx for mocking
- [ ] Verify >90% code coverage

### Task 5: Tool Registration (Deferred to Story 16.5)
- [ ] Note: Tool will be exported and registered in Story 16.5
- [ ] Prepare tool for export in `mcp_server/tools/__init__.py`

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

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

---

**Created:** 2025-01-10
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.2 - Home Assistant Control Tool (Allowlist-Enforced)
