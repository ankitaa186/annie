# Story 16.1: Home Assistant Query Tool

Status: drafted

## Story

**As a** user of Annie,
**I want** to query the state of my Home Assistant entities (lights, sensors, climate, etc.),
**So that** Annie can answer questions about my smart home status like "Is the garage door closed?" or "What's the thermostat set to?"

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P0
**Estimated Effort:** 1 day

## Acceptance Criteria

### AC #1: Query Specific Entities by ID
**Given** a list of entity IDs (e.g., `["light.living_room", "sensor.temperature"]`)
**When** the `home_assistant_query` tool is called with `entity_ids` parameter
**Then** the tool returns state, attributes, and last_changed for each entity

**Testable:** Call tool with 2+ entity IDs, verify all entities returned with complete data

---

### AC #2: Query All Entities by Domain
**Given** a domain name (e.g., "light", "sensor", "climate")
**When** the `home_assistant_query` tool is called with `domain` parameter
**Then** the tool returns all entities in that domain with state, attributes, and last_changed

**Testable:** Call tool with domain="light", verify all light entities returned

---

### AC #3: Handle Entity Not Found (404)
**Given** an entity ID that doesn't exist in Home Assistant
**When** the `home_assistant_query` tool is called with that entity ID
**Then** the tool returns a graceful error with status="error", error_code="NOT_FOUND"

**Testable:** Call tool with non-existent entity, verify error response format

---

### AC #4: Handle Invalid Token (401)
**Given** an invalid or expired HA_ACCESS_TOKEN
**When** the `home_assistant_query` tool is called
**Then** the tool returns status="error", error_code="UNAUTHORIZED" with clear message

**Testable:** Set invalid token, call tool, verify UNAUTHORIZED error

---

### AC #5: Request Timeout Handling
**Given** Home Assistant takes longer than HA_TIMEOUT seconds to respond
**When** the `home_assistant_query` tool is called
**Then** the tool returns status="error", error_code="TIMEOUT" after HA_TIMEOUT seconds (default: 10)

**Testable:** Mock slow HA response, verify timeout at configured threshold

---

### AC #6: Structured Logging
**Given** any tool call (success or failure)
**When** the operation completes
**Then** structured logs include: tool_name, entity_count, duration_ms, status

**Testable:** Check logs for required fields after tool calls

---

### AC #7: Handle Missing Configuration
**Given** HA_URL or HA_ACCESS_TOKEN is not configured
**When** the `home_assistant_query` tool is called
**Then** the tool returns status="error", error_code="CONFIG_ERROR" with clear message

**Testable:** Remove HA_URL from env, call tool, verify CONFIG_ERROR

---

### AC #8: Unit Tests with Mocked HA Responses
**Given** the tool implementation
**When** unit tests are run
**Then** all test cases pass with >90% code coverage using mocked HTTP responses

**Testable:** Run pytest with coverage, verify threshold met

---

## Tasks / Subtasks

### Task 1: Create Home Assistant HTTP Client Base (AC: #3, #4, #5, #7)
- [ ] Create `mcp_server/tools/home_assistant.py`
- [ ] Implement `HomeAssistantClient` class with httpx async client
- [ ] Add configuration loading: HA_URL, HA_ACCESS_TOKEN, HA_TIMEOUT
- [ ] Implement CONFIG_ERROR check on initialization
- [ ] Add Bearer token authentication header
- [ ] Implement timeout handling with HA_TIMEOUT
- [ ] Handle 401 UNAUTHORIZED responses
- [ ] Handle 404 NOT_FOUND responses
- [ ] Handle network errors (connection refused, DNS failure)

### Task 2: Implement Entity Query Methods (AC: #1, #2)
- [ ] Implement `get_entity_state(entity_id: str)` method
  - GET `/api/states/{entity_id}`
  - Parse response: state, attributes, last_changed
- [ ] Implement `get_entities_by_ids(entity_ids: List[str])` method
  - Call get_entity_state for each ID
  - Aggregate results
- [ ] Implement `get_entities_by_domain(domain: str)` method
  - GET `/api/states` for all entities
  - Filter by domain prefix (e.g., "light.")
  - Handle "all" domain for complete state dump

### Task 3: Create MCP Tool Handler (AC: #1, #2, #6)
- [ ] Create `home_assistant_query` tool function
- [ ] Define input schema with oneOf validation (entity_ids OR domain)
- [ ] Implement tool handler calling appropriate client methods
- [ ] Format response: status, provider, entities[], query_count
- [ ] Add structured logging with duration_ms

### Task 4: Write Unit Tests (AC: #8)
- [ ] Create `mcp_server/tests/test_home_assistant_query.py`
- [ ] Test: `test_query_single_entity()` - single entity by ID
- [ ] Test: `test_query_multiple_entities()` - list of entity IDs
- [ ] Test: `test_query_by_domain()` - all entities in domain
- [ ] Test: `test_query_entity_not_found()` - 404 handling
- [ ] Test: `test_query_unauthorized()` - 401 handling
- [ ] Test: `test_query_timeout()` - timeout handling
- [ ] Test: `test_query_config_error()` - missing configuration
- [ ] Test: `test_query_network_error()` - connection failure
- [ ] Use pytest-httpx or respx for mocking HTTP responses
- [ ] Verify >90% code coverage

### Task 5: Tool Registration (Deferred to Story 16.5)
- [ ] Note: Tool will be exported and registered in Story 16.5
- [ ] Prepare tool for export in `mcp_server/tools/__init__.py`

---

## Dev Notes

### Implementation Approach

Follow existing MCP tool patterns from Epic 15:
- Use `httpx.AsyncClient` for HTTP requests (consistent with other tools)
- Implement provider pattern similar to web_search tool
- Use structured error responses with status, error_code, error_message

### Home Assistant REST API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/states` | GET | Get all entity states |
| `/api/states/{entity_id}` | GET | Get single entity state |

**Authentication:** Bearer token in Authorization header
```
Authorization: Bearer <long_lived_access_token>
```

### Response Format

```python
{
    "status": "success",
    "provider": "home_assistant",
    "entities": [
        {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {
                "brightness": 255,
                "friendly_name": "Living Room Light"
            },
            "last_changed": "2025-01-09T10:30:00Z"
        }
    ],
    "query_count": 1
}
```

### Error Response Format

```python
{
    "status": "error",
    "provider": "home_assistant",
    "error_code": "NOT_FOUND|UNAUTHORIZED|TIMEOUT|CONFIG_ERROR|NETWORK_ERROR",
    "error_message": "Human readable error description",
    "entity_id": "light.nonexistent"  # optional, for entity-specific errors
}
```

### Tool Schema

```python
{
    "name": "home_assistant_query",
    "description": (
        "Query entity states from Home Assistant smart home system. "
        "Returns current state, attributes, and last_changed timestamp. "
        "Use for checking device status, sensor readings, and home state."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "entity_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of entity IDs to query"
            },
            "domain": {
                "type": "string",
                "enum": ["light", "switch", "sensor", "climate", "binary_sensor", "cover", "fan", "all"],
                "description": "Query all entities in a domain"
            }
        },
        "oneOf": [
            {"required": ["entity_ids"]},
            {"required": ["domain"]}
        ]
    }
}
```

### Project Structure Notes

- New file: `mcp_server/tools/home_assistant.py`
- New test file: `mcp_server/tests/test_home_assistant_query.py`
- Follows existing tool structure in `mcp_server/tools/`
- Uses shared config from `mcp_server/config.py` (env vars added in Story 16.4)

### Performance Targets

| Metric | Target |
|--------|--------|
| Query latency p95 | <500ms |
| Success rate | >99% (local network) |

### Dependencies

- `httpx>=0.24.0` (already present)
- Home Assistant instance with REST API enabled
- Long-Lived Access Token from HA

### Learnings from Previous Story

**From Story 15-6 (Status: done)**

- **Documentation Patterns**: env.example should have comments, costs, links (will apply in Story 16.4)
- **Config Loading**: Use `os.getenv()` with sensible defaults, mask sensitive values in logs
- **Tool Documentation**: Follow CLAUDE.md style with schemas, usage examples, tables

[Source: stories/15-6-env-config-documentation.md]

### References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.1]
- [Source: Home Assistant REST API Docs](https://developers.home-assistant.io/docs/api/rest)

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
**Story:** 16.1 - Home Assistant Query Tool
