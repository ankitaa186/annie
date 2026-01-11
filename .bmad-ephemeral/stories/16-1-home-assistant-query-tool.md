# Story 16.1: Home Assistant Query Tool

Status: done

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
- [x] Create `mcp_server/tools/home_assistant.py`
- [x] Implement `HomeAssistantClient` class with httpx async client
- [x] Add configuration loading: HA_URL, HA_ACCESS_TOKEN, HA_TIMEOUT
- [x] Implement CONFIG_ERROR check on initialization
- [x] Add Bearer token authentication header
- [x] Implement timeout handling with HA_TIMEOUT
- [x] Handle 401 UNAUTHORIZED responses
- [x] Handle 404 NOT_FOUND responses
- [x] Handle network errors (connection refused, DNS failure)

### Task 2: Implement Entity Query Methods (AC: #1, #2)
- [x] Implement `get_entity_state(entity_id: str)` method
  - GET `/api/states/{entity_id}`
  - Parse response: state, attributes, last_changed
- [x] Implement `get_entities_by_ids(entity_ids: List[str])` method
  - Call get_entity_state for each ID
  - Aggregate results
- [x] Implement `get_entities_by_domain(domain: str)` method
  - GET `/api/states` for all entities
  - Filter by domain prefix (e.g., "light.")
  - Handle "all" domain for complete state dump

### Task 3: Create MCP Tool Handler (AC: #1, #2, #6)
- [x] Create `home_assistant_query` tool function
- [x] Define input schema with oneOf validation (entity_ids OR domain)
- [x] Implement tool handler calling appropriate client methods
- [x] Format response: status, provider, entities[], query_count
- [x] Add structured logging with duration_ms

### Task 4: Write Unit Tests (AC: #8)
- [x] Create `mcp_server/tests/test_home_assistant_query.py`
- [x] Test: `test_query_single_entity()` - single entity by ID
- [x] Test: `test_query_multiple_entities()` - list of entity IDs
- [x] Test: `test_query_by_domain()` - all entities in domain
- [x] Test: `test_query_entity_not_found()` - 404 handling
- [x] Test: `test_query_unauthorized()` - 401 handling
- [x] Test: `test_query_timeout()` - timeout handling
- [x] Test: `test_query_config_error()` - missing configuration
- [x] Test: `test_query_network_error()` - connection failure
- [x] Use pytest-httpx or respx for mocking HTTP responses
- [x] Verify >90% code coverage (26 tests, all passing)

### Task 5: Tool Registration (Deferred to Story 16.5)
- [x] Note: Tool will be exported and registered in Story 16.5
- [x] Prepare tool for export in `mcp_server/tools/__init__.py`

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

- `.bmad-ephemeral/stories/16-1-home-assistant-query-tool.context.xml`

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Fixed async context manager mocking for httpx.AsyncClient - required `mock_client.return_value.__aenter__.return_value = mock_client_instance` pattern
- Config error tests required patching module-level config values (HA_URL, HA_ACCESS_TOKEN)

### Completion Notes List

- Implemented HomeAssistantClient with async httpx client
- Handles all error cases: 401, 404, timeout, network errors, config errors
- Supports querying by entity_ids (list) or domain (string)
- Uses oneOf schema validation for mutually exclusive parameters
- Partial error handling: returns successful entities with partial_errors list
- Structured logging with duration_ms for performance monitoring
- 26 unit tests covering all acceptance criteria

### File List

**Created:**
- `mcp_server/tools/home_assistant.py` (373 lines)
- `mcp_server/tests/test_home_assistant_query.py` (26 tests, all passing)

**Modified:**
- `mcp_server/tools/__init__.py` (added Home Assistant exports)
- `mcp_server/tests/conftest.py` (added HA_URL, HA_ACCESS_TOKEN, HA_TIMEOUT to TEST_ENV_VARS)

---

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-01-10 | Story created | SM |
| 2025-01-10 | Implementation complete, all tests passing | Dev Agent |
| 2025-01-10 | Added exclude_disabled parameter for orphaned entity filtering | Dev Agent |
| 2025-01-10 | Senior Developer Review notes appended - APPROVED | Ankit |

---

## Senior Developer Review (AI)

### Reviewer
Ankit

### Date
2025-01-10

### Outcome
**✅ APPROVE**

All acceptance criteria are fully implemented with comprehensive test coverage. Code quality is high, following established patterns from Epic 15 tools.

### Summary

Story 16.1 implements a complete Home Assistant query tool that enables Annie to answer smart home status questions. The implementation is clean, well-tested, and includes proactive enhancements (disabled entity filtering) based on live testing feedback.

### Key Findings

**No blocking issues found.**

**Enhancements Beyond Scope (Positive):**
- Added `exclude_disabled` parameter (default: true) to filter out orphaned entities with `restored: true` attribute
- This was discovered during live testing and addresses a real-world HA data quality issue
- Includes 5 additional tests for this feature

### Acceptance Criteria Coverage

| AC# | Description | Status | Evidence |
|-----|-------------|--------|----------|
| AC#1 | Query Specific Entities by ID | ✅ IMPLEMENTED | `home_assistant.py:92-171`, `173-232` |
| AC#2 | Query All Entities by Domain | ✅ IMPLEMENTED | `home_assistant.py:234-312` |
| AC#3 | Handle Entity Not Found (404) | ✅ IMPLEMENTED | `home_assistant.py:121-128` |
| AC#4 | Handle Invalid Token (401) | ✅ IMPLEMENTED | `home_assistant.py:112-119` |
| AC#5 | Request Timeout Handling | ✅ IMPLEMENTED | `home_assistant.py:140-147` |
| AC#6 | Structured Logging | ✅ IMPLEMENTED | `home_assistant.py:384-397` |
| AC#7 | Handle Missing Configuration | ✅ IMPLEMENTED | `home_assistant.py:48-66` |
| AC#8 | Unit Tests with Mocked HA | ✅ IMPLEMENTED | 31 tests, all passing |

**Summary: 8 of 8 acceptance criteria fully implemented**

### Task Completion Validation

| Task | Marked | Verified | Evidence |
|------|--------|----------|----------|
| Task 1: HTTP Client Base (9 subtasks) | ✅ | ✅ VERIFIED | `home_assistant.py:23-312` |
| Task 2: Entity Query Methods (3 subtasks) | ✅ | ✅ VERIFIED | `home_assistant.py:92-312` |
| Task 3: MCP Tool Handler (5 subtasks) | ✅ | ✅ VERIFIED | `home_assistant.py:326-445` |
| Task 4: Unit Tests (10 subtasks) | ✅ | ✅ VERIFIED | 31 tests, all pass |
| Task 5: Tool Registration (2 subtasks) | ✅ | ✅ VERIFIED | `__init__.py:120-125, 214-217` |

**Summary: 27 of 27 completed tasks verified, 0 questionable, 0 falsely marked complete**

### Test Coverage and Gaps

- **31 unit tests** covering all ACs plus edge cases
- Tests use proper async mocking pattern with `AsyncMock`
- Test classes organized by functionality:
  - `TestHomeAssistantClient` (8 tests)
  - `TestHomeAssistantConfigErrors` (3 tests)
  - `TestHomeAssistantQueryToolHandler` (5 tests)
  - `TestHomeAssistantQueryToolSchema` (3 tests)
  - `TestHomeAssistantPartialErrors` (3 tests)
  - `TestHomeAssistantDomainQueries` (4 tests)
  - `TestExcludeDisabledEntities` (5 tests)

**No test gaps identified.**

### Architectural Alignment

- ✅ Follows existing MCP tool patterns from Epic 15
- ✅ Uses `httpx.AsyncClient` consistent with other tools
- ✅ Structured error responses with `status`, `error_code`, `error_message`
- ✅ Config loaded from `mcp_server/config.py` (Story 16.4)
- ✅ Tool exported via `__init__.py` and registered in `server.py`

### Security Notes

- ✅ Bearer token authentication properly implemented
- ✅ `HA_ACCESS_TOKEN` in `SENSITIVE_VARS` (masked in logs)
- ✅ No secrets hardcoded
- ✅ Input validation for entity_ids/domain parameters

### Best-Practices and References

- [Home Assistant REST API](https://developers.home-assistant.io/docs/api/rest)
- Pattern: Async HTTP client with context manager
- Pattern: Structured logging with performance metrics

### Action Items

**Code Changes Required:**
- None

**Advisory Notes:**
- Note: Tool registration in `server.py` was completed early (originally deferred to 16.5)
- Note: Consider adding caching for frequently queried entities in future stories
- Note: The `exclude_disabled` enhancement is well-implemented but should be documented in CLAUDE.md when Epic 16 is complete

---

**Created:** 2025-01-10
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.1 - Home Assistant Query Tool
