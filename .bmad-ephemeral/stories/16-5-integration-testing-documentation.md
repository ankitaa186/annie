# Story 16.5: Integration Testing & Documentation

Status: ready-for-dev

## Story

**As a** developer,
**I want** the Home Assistant tools properly registered, tested, and documented,
**So that** the integration is complete, maintainable, and Claude can understand how to use the tools.

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P1
**Estimated Effort:** 1 day
**Prerequisites:** Stories 16.1, 16.2, 16.3, 16.4

## Acceptance Criteria

### AC #1: Tools Exported in __init__.py
**Given** the MCP tools module
**When** the server imports tools
**Then** `home_assistant_query` and `home_assistant_control` are exported

**Testable:** `from mcp_server.tools import home_assistant_query, home_assistant_control` works

---

### AC #2: Tools Registered in server.py
**Given** the MCP server
**When** tools/list is called
**Then** both HA tools appear in the tool list with correct schemas

**Testable:** Call /tools/list, verify both tools in response

---

### AC #3: Unit Tests with >90% Coverage
**Given** all Epic 16 implementation
**When** pytest is run with coverage
**Then** coverage exceeds 90% for home_assistant.py and mqtt_subscriber.py

**Testable:** Run `pytest --cov=mcp_server/tools/home_assistant --cov=backend/api/mqtt_subscriber`

---

### AC #4: Integration Test with Real HA (Skippable)
**Given** a real Home Assistant instance is available
**When** integration tests run
**Then** they verify actual API calls work (skipped if HA not available)

**Testable:** Run with `--run-integration` flag, verify passes or skips gracefully

---

### AC #5: CLAUDE.md Updated with Tool Documentation
**Given** the CLAUDE.md file
**When** Claude reads it
**Then** both HA tools are documented with:
  - Tool name and description
  - Complete input schema
  - Usage examples
  - Response format
  - Security notes (allowlist for control)

**Testable:** Verify CLAUDE.md contains home_assistant_query and home_assistant_control sections

---

### AC #6: aiomqtt in requirements.txt
**Given** the requirements files
**When** dependencies are installed
**Then** aiomqtt>=2.0.0 is available for MQTT subscriber

**Testable:** Verify `aiomqtt>=2.0.0` in backend/requirements.txt

---

## Tasks / Subtasks

### Task 1: Export Tools in __init__.py (AC: #1)
- [ ] Update `mcp_server/tools/__init__.py`
- [ ] Add `from .home_assistant import home_assistant_query, home_assistant_control`
- [ ] Add to `__all__` list

### Task 2: Register Tools in server.py (AC: #2)
- [ ] Update `mcp_server/server.py`
- [ ] Import home_assistant_query and home_assistant_control
- [ ] Register with tool schemas (copy from story docs)
- [ ] Verify tools appear in /tools/list response

### Task 3: Create Integration Test Suite (AC: #3, #4)
- [ ] Create `mcp_server/tests/test_home_assistant_integration.py`
- [ ] Consolidate tests from 16.1 and 16.2 test files
- [ ] Add end-to-end tests:
  - `test_query_then_control_flow()` - query state, control, verify change
  - `test_full_allowlist_enforcement()` - comprehensive security test
- [ ] Add real HA integration tests (skippable):
  ```python
  @pytest.mark.skipif(not os.getenv("HA_URL"), reason="HA not configured")
  def test_real_ha_query():
      ...
  ```
- [ ] Verify >90% coverage

### Task 4: Create MQTT Integration Tests (AC: #3)
- [ ] Consolidate tests in `backend/tests/test_mqtt_subscriber.py`
- [ ] Add integration test for full flow:
  - MQTT message → Parse → Telegram delivery
- [ ] Mock TelegramDelivery for unit tests

### Task 5: Update CLAUDE.md (AC: #5)
- [ ] Add "Home Assistant Integration (Epic 16)" section
- [ ] Document home_assistant_query tool:
  - When to use
  - Input schema
  - Response format
  - Example queries
- [ ] Document home_assistant_control tool:
  - When to use
  - Input schema with all actions
  - SECURITY: Allowlist enforcement
  - Response format (success and forbidden)
- [ ] Add troubleshooting notes

### Task 6: Add aiomqtt Dependency (AC: #6)
- [ ] Add `aiomqtt>=2.0.0` to `backend/requirements.txt`
- [ ] Verify installation works in Docker build

---

## Dev Notes

### Tool Registration Pattern

Follow existing patterns in server.py:

```python
# mcp_server/server.py

from mcp_server.tools.home_assistant import (
    home_assistant_query,
    home_assistant_control,
    HOME_ASSISTANT_QUERY_SCHEMA,
    HOME_ASSISTANT_CONTROL_SCHEMA,
)

# Register tools
tools_registry.register(
    name="home_assistant_query",
    handler=home_assistant_query,
    schema=HOME_ASSISTANT_QUERY_SCHEMA,
)

tools_registry.register(
    name="home_assistant_control",
    handler=home_assistant_control,
    schema=HOME_ASSISTANT_CONTROL_SCHEMA,
)
```

### CLAUDE.md Documentation

Add section after "Extended MCP Tools (Epic 15)":

```markdown
## Home Assistant Integration (Epic 16)

Annie integrates with Home Assistant for smart home control and monitoring.

### Home Assistant Query Tool (`home_assistant_query`)

Query entity states from your Home Assistant instance.

**When to Use:**
- Check device status ("Is the garage door closed?")
- Read sensor values ("What's the indoor temperature?")
- Get entity states before making decisions

**Schema:**
```json
{
  "entity_ids": ["light.living_room", "sensor.temperature"],
  // OR
  "domain": "light"  // Query all lights
}
```

**Response:** entity_id, state, attributes, last_changed

---

### Home Assistant Control Tool (`home_assistant_control`)

Control Home Assistant entities with security enforcement.

**SECURITY:** Only entities in HA_CONTROL_ALLOWLIST can be controlled.

**When to Use:**
- User explicitly requests device control
- NEVER control without clear user intent

**Schema:**
```json
{
  "entity_id": "light.living_room",
  "action": "turn_on",  // turn_on, turn_off, toggle, set_brightness, set_temperature, set_position, set_hvac_mode
  "parameters": {"brightness": 200}  // Optional
}
```

**Response (Success):** entity_id, action, previous_state, new_state
**Response (Forbidden):** error_code="FORBIDDEN", list of allowed entities
```

### Test Structure

```
mcp_server/tests/
├── test_home_assistant_query.py      # From Story 16.1
├── test_home_assistant_control.py    # From Story 16.2
└── test_home_assistant_integration.py # NEW - end-to-end tests

backend/tests/
└── test_mqtt_subscriber.py           # From Story 16.3
```

### Coverage Target

Run coverage for Epic 16 modules:

```bash
# MCP Server
pytest mcp_server/tests/test_home_assistant*.py \
  --cov=mcp_server/tools/home_assistant \
  --cov-report=term-missing \
  --cov-fail-under=90

# Backend
pytest backend/tests/test_mqtt_subscriber.py \
  --cov=backend/api/mqtt_subscriber \
  --cov-report=term-missing \
  --cov-fail-under=90
```

### Dependency Addition

```txt
# backend/requirements.txt

# MQTT client for Home Assistant alerts (Epic 16 - Story 16.3)
aiomqtt>=2.0.0
```

### Learnings from Previous Stories

**From Story 15-5 (Tool Registration & Integration Tests)**
- Follow existing registration patterns in server.py
- Use pytest markers for skippable integration tests
- Document tools with schemas and examples in CLAUDE.md

[Source: Sprint status shows 15-5 done with same pattern]

### References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.5]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-16.md#Test-Strategy]

---

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/16-5-integration-testing-documentation.context.xml

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

---

**Created:** 2025-01-10
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.5 - Integration Testing & Documentation
