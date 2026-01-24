# Epic Technical Specification: Home Assistant Integration

Date: 2025-01-10
Author: Ankit
Epic ID: 16
Status: Draft

---

## Overview

Epic 16 implements bidirectional integration between Annie and Home Assistant, enabling Annie to query device states, control smart home entities, and receive proactive alerts via MQTT. This transforms Annie from a conversational AI into a home-aware assistant capable of answering questions like "Is the garage door closed?" and executing commands like "Turn on the living room lights."

The integration follows Annie's established MCP tool pattern, adding two new tools (`home_assistant_query`, `home_assistant_control`) to the MCP server, while the backend gains an MQTT subscriber for receiving Home Assistant automation alerts.

[Source: docs/epics/epic-16-home-assistant-integration.md]

## Objectives and Scope

### In Scope

- **Query Tool**: Read entity states (lights, switches, sensors, climate, covers, fans) via Home Assistant REST API
- **Control Tool**: Execute actions on allowlisted entities with security enforcement
- **MQTT Subscriber**: Receive and forward Home Assistant alerts to user via Telegram
- **Configuration**: Environment variables for HA connection, allowlists, and MQTT settings
- **Error Handling**: Graceful degradation when HA is unavailable, timeout handling, clear error messages

### Out of Scope

- Entity discovery UI or automatic entity listing
- Scene/script execution (future consideration)
- Voice command integration
- Camera snapshot fetching
- Energy monitoring dashboards
- Calendar integration
- Presence detection logic

[Source: docs/epics/epic-16-home-assistant-integration.md#Section-8]

## System Architecture Alignment

### Component Integration

| Component | Role | Epic 16 Changes |
|-----------|------|-----------------|
| MCP Server | Tool hosting | Add `home_assistant_query`, `home_assistant_control` tools |
| Backend API | Chat logic, MQTT | Add MQTT subscriber service for HA alerts |
| Telegram Bot | User interface | Receive forwarded MQTT alerts via existing TelegramDelivery |
| Redis | State management | No changes (existing infrastructure) |

### Communication Patterns

```
Annie → Home Assistant (Query/Control):
  User → Telegram → Backend → MCP Server → HA REST API → Response

Home Assistant → Annie (Alerts):
  HA Automation → Mosquitto MQTT → Backend Subscriber → TelegramDelivery → User
```

### Architectural Constraints

- **Local Network**: HA typically runs on local network; ensure backend can reach HA_URL
- **Authentication**: Bearer token authentication for REST API (long-lived access token)
- **Security**: Control operations MUST be allowlist-enforced; no bypass permitted
- **Async Pattern**: Use httpx.AsyncClient consistent with other MCP tools

[Source: docs/epics/epic-16-home-assistant-integration.md#Section-2]

## Detailed Design

### Services and Modules

| Module | Location | Responsibility |
|--------|----------|----------------|
| `HomeAssistantClient` | `mcp_server/tools/home_assistant.py` | HTTP client for HA REST API with auth and error handling |
| `home_assistant_query` | `mcp_server/tools/home_assistant.py` | MCP tool for reading entity states |
| `home_assistant_control` | `mcp_server/tools/home_assistant.py` | MCP tool for controlling entities with allowlist |
| `AllowlistValidator` | `mcp_server/tools/home_assistant.py` | Parse and validate entity allowlist |
| `MQTTSubscriber` | `backend/api/mqtt_subscriber.py` | Subscribe to MQTT topics, forward alerts |
| Config updates | `mcp_server/config.py`, `backend/api/config.py` | HA environment variables |

### Data Models and Contracts

#### Entity State Response

```python
@dataclass
class EntityState:
    entity_id: str       # e.g., "light.living_room"
    state: str           # e.g., "on", "off", "72.5"
    attributes: dict     # Domain-specific attributes
    last_changed: str    # ISO 8601 timestamp
```

#### Query Tool Response

```python
{
    "status": "success" | "error",
    "provider": "home_assistant",
    "entities": [EntityState, ...],  # On success
    "query_count": int,              # On success
    "error_code": str,               # On error: CONFIG_ERROR|NOT_FOUND|UNAUTHORIZED|TIMEOUT|NETWORK_ERROR
    "error_message": str             # On error
}
```

#### Control Tool Response

```python
# Success
{
    "status": "success",
    "provider": "home_assistant",
    "entity_id": str,
    "action": str,
    "parameters": dict,
    "previous_state": str,
    "new_state": str
}

# Forbidden (allowlist violation)
{
    "status": "error",
    "provider": "home_assistant",
    "error_code": "FORBIDDEN",
    "error_message": str,  # Includes allowed entities list
    "entity_id": str
}
```

#### MQTT Message Format

```python
# From Home Assistant automation
{
    "title": str,       # Alert title
    "message": str,     # Alert body
    "entity_id": str,   # Optional: triggering entity
    "state": str        # Optional: entity state
}
```

### APIs and Interfaces

#### Home Assistant REST API Endpoints Used

| Endpoint | Method | Purpose | Auth |
|----------|--------|---------|------|
| `/api/states` | GET | Get all entity states | Bearer token |
| `/api/states/{entity_id}` | GET | Get single entity state | Bearer token |
| `/api/services/{domain}/{service}` | POST | Call service (turn_on, etc.) | Bearer token |

#### MCP Tool: home_assistant_query

```python
{
    "name": "home_assistant_query",
    "description": "Query entity states from Home Assistant smart home system.",
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

#### MCP Tool: home_assistant_control

```python
{
    "name": "home_assistant_control",
    "description": "Control Home Assistant entities. Only allowlisted entities permitted.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "entity_id": {"type": "string"},
            "action": {
                "type": "string",
                "enum": ["turn_on", "turn_off", "toggle", "set_brightness", "set_temperature", "set_position", "set_hvac_mode"]
            },
            "parameters": {
                "type": "object",
                "additionalProperties": true
            }
        },
        "required": ["entity_id", "action"]
    }
}
```

#### Service Mapping

| Action | Domain | HA Service | Parameters |
|--------|--------|------------|------------|
| turn_on | light/switch/fan | turn_on | entity_id |
| turn_off | light/switch/fan | turn_off | entity_id |
| toggle | light/switch | toggle | entity_id |
| set_brightness | light | turn_on | entity_id, brightness (0-255) |
| set_temperature | climate | set_temperature | entity_id, temperature |
| set_hvac_mode | climate | set_hvac_mode | entity_id, hvac_mode |
| set_position | cover | set_cover_position | entity_id, position (0-100) |

### Workflows and Sequencing

#### Query Flow

```
1. User: "Is my garage door closed?"
2. LLM selects home_assistant_query tool
3. MCP Server receives tool call with entity_ids=["cover.garage"]
4. HomeAssistantClient.get_entity_state("cover.garage")
   - Validate config (HA_URL, HA_ACCESS_TOKEN)
   - GET /api/states/cover.garage with Bearer auth
   - Parse response (state, attributes, last_changed)
5. Return formatted response to LLM
6. LLM: "Yes, your garage door is closed."
```

#### Control Flow with Allowlist

```
1. User: "Turn on the living room lights"
2. LLM selects home_assistant_control tool
3. MCP Server receives: entity_id="light.living_room", action="turn_on"
4. AllowlistValidator.is_allowed("light.living_room")
   - Parse HA_CONTROL_ALLOWLIST
   - Check exact match OR wildcard match (light.*)
5a. If ALLOWED:
   - GET current state (for previous_state)
   - POST /api/services/light/turn_on {entity_id: "light.living_room"}
   - Return success with previous/new state
5b. If DENIED:
   - Return FORBIDDEN error with allowed entities list
```

#### MQTT Alert Flow

```
1. HA Automation triggers (motion detected)
2. Automation publishes to Mosquitto: annie/alerts/motion
3. Backend MQTTSubscriber receives message
4. Parse JSON payload (title, message)
5. TelegramDelivery.send_message(user_id, formatted_alert)
6. User receives Telegram: "Motion Detected: Motion in backyard"
```

[Source: docs/epics/epic-16-home-assistant-integration.md#Section-2]

## Non-Functional Requirements

### Performance

| Metric | Target | Measurement |
|--------|--------|-------------|
| `home_assistant_query` latency p95 | <500ms | Structured logs `duration_ms` |
| `home_assistant_control` latency p95 | <1s | Structured logs `duration_ms` |
| MQTT message delivery | <2s | End-to-end from HA to Telegram |
| Tool success rate | >99% | Local network assumption |

### Security

- **Token Protection**: HA_ACCESS_TOKEN and HA_MQTT_PASSWORD added to SENSITIVE_VARS (masked in logs)
- **Allowlist Enforcement**: 100% enforcement rate; no code path bypasses allowlist check
- **Audit Logging**: All control attempts logged (allowed AND denied) with entity_id, action, outcome
- **Principle of Least Privilege**: Empty allowlist = no control operations permitted
- **No Token in Responses**: Access tokens never returned in tool responses

### Reliability/Availability

| Scenario | Behavior |
|----------|----------|
| HA unavailable | Return NETWORK_ERROR, graceful degradation |
| Invalid token | Return UNAUTHORIZED with clear message |
| MQTT disconnect | Auto-reconnect with 5s backoff, max 30s reconnection |
| HA slow response | Timeout after HA_TIMEOUT (default 10s) |
| Entity not found | Return NOT_FOUND, continue processing other entities |

### Observability

**Structured Logging Fields:**
- `tool_name`: "home_assistant_query" or "home_assistant_control"
- `entity_id` / `entity_count`: Entity being accessed
- `action`: For control operations
- `duration_ms`: Request latency
- `status`: success/error
- `error_code`: For failures
- `allowed`: true/false for control operations (audit trail)

**Metrics to Track:**
- Query/control request count by outcome
- Latency histograms
- Allowlist denial rate
- MQTT reconnection frequency

[Source: docs/epics/epic-16-home-assistant-integration.md#Section-3, Section-7]

## Dependencies and Integrations

### External Services

| Service | Required | Purpose | Notes |
|---------|----------|---------|-------|
| Home Assistant | Yes | Smart home platform | REST API on :8123 |
| Mosquitto MQTT | Optional | Alert broker | Only needed for HA→Annie alerts |

### Python Packages

**MCP Server (`mcp_server/requirements.txt`):**
```
httpx>=0.24.0  # Already present - async HTTP client
```

**Backend (`backend/requirements.txt`):**
```
aiomqtt>=2.0.0  # NEW - async MQTT client for subscriber
```

### Environment Variables

```bash
# Home Assistant REST API
HA_URL=http://192.168.1.x:8123
HA_ACCESS_TOKEN=REPLACE_ME  # Long-lived access token
HA_CONTROL_ALLOWLIST=       # Comma-separated, supports wildcards (light.*)
HA_TIMEOUT=10               # Request timeout in seconds

# MQTT (Optional)
HA_MQTT_BROKER=             # Mosquitto host
HA_MQTT_PORT=1883
HA_MQTT_USERNAME=           # Optional auth
HA_MQTT_PASSWORD=           # Optional auth (SENSITIVE)
HA_MQTT_TOPICS=annie/alerts/#
HA_MQTT_ALERT_USER_ID=      # Telegram user ID for alerts
```

### Integration Points

| System | Integration | Protocol |
|--------|-------------|----------|
| Home Assistant | REST API | HTTP + Bearer auth |
| Mosquitto | MQTT Subscribe | TCP + optional auth |
| TelegramDelivery | Alert forwarding | Internal Python call |
| Langfuse | Tracing (via @observe) | Decorator pattern |

[Source: docs/epics/epic-16-home-assistant-integration.md#Section-5]

## Acceptance Criteria (Authoritative)

### Story 16.1: Home Assistant Query Tool

| AC ID | Criteria | Testable |
|-------|----------|----------|
| 16.1.1 | Query specific entities by ID list returns state, attributes, last_changed | Unit test with mocked response |
| 16.1.2 | Query by domain returns all entities in that domain | Unit test filtering |
| 16.1.3 | 404 returns graceful NOT_FOUND error | Unit test with 404 mock |
| 16.1.4 | 401 returns UNAUTHORIZED with clear message | Unit test with 401 mock |
| 16.1.5 | Timeout after HA_TIMEOUT seconds | Unit test with delayed mock |
| 16.1.6 | Structured logging includes duration_ms | Log inspection |
| 16.1.7 | Unit tests with >90% coverage | pytest --cov |

### Story 16.2: Home Assistant Control Tool

| AC ID | Criteria | Testable |
|-------|----------|----------|
| 16.2.1 | Allowlist parsed from HA_CONTROL_ALLOWLIST | Unit test parsing |
| 16.2.2 | Exact match allowlist works | Unit test allowed entity |
| 16.2.3 | Wildcard allowlist (light.*) works | Unit test wildcard match |
| 16.2.4 | Empty allowlist blocks ALL control | Unit test empty list |
| 16.2.5 | FORBIDDEN includes allowed entities list | Unit test error format |
| 16.2.6 | Actions map to correct HA services | Unit test each action |
| 16.2.7 | Returns previous_state and new_state | Unit test response format |
| 16.2.8 | All attempts logged (allowed + denied) | Log inspection |

### Story 16.3: MQTT Subscriber

| AC ID | Criteria | Testable |
|-------|----------|----------|
| 16.3.1 | Connect to Mosquitto on startup (if configured) | Integration test |
| 16.3.2 | Subscribe to configured topics | Mock verification |
| 16.3.3 | Parse JSON and plain text messages | Unit test both formats |
| 16.3.4 | Forward to Telegram via TelegramDelivery | Mock call verification |
| 16.3.5 | Auto-reconnect with 5s backoff | Unit test reconnect logic |
| 16.3.6 | Graceful shutdown on SIGTERM | Signal handler test |
| 16.3.7 | Skip if HA_MQTT_BROKER not configured | Config check test |

### Story 16.4: Configuration

| AC ID | Criteria | Testable |
|-------|----------|----------|
| 16.4.1 | All env vars in env.example with docs | File inspection |
| 16.4.2 | HA_ACCESS_TOKEN in SENSITIVE_VARS | Masked in logs |
| 16.4.3 | HA_MQTT_PASSWORD in SENSITIVE_VARS | Masked in logs |
| 16.4.4 | Config loading in both config.py files | Unit test loading |
| 16.4.5 | Graceful handling when HA not configured | Unit test missing config |

### Story 16.5: Integration & Documentation

| AC ID | Criteria | Testable |
|-------|----------|----------|
| 16.5.1 | Tools exported in __init__.py | Import test |
| 16.5.2 | Tools registered in server.py | Registration test |
| 16.5.3 | Unit tests >90% coverage | pytest --cov |
| 16.5.4 | CLAUDE.md updated with tool docs | File inspection |
| 16.5.5 | aiomqtt in requirements.txt | File inspection |

[Source: docs/epics/epic-16-home-assistant-integration.md#Section-3]

## Traceability Mapping

| AC | Spec Section | Component | Test Approach |
|----|--------------|-----------|---------------|
| 16.1.1-7 | Query Tool | `home_assistant.py:home_assistant_query` | pytest + httpx mock |
| 16.2.1-8 | Control Tool | `home_assistant.py:home_assistant_control` | pytest + allowlist unit tests |
| 16.3.1-7 | MQTT Subscriber | `mqtt_subscriber.py` | pytest + aiomqtt mock |
| 16.4.1-5 | Configuration | `config.py` files, `env.example` | Config loading tests |
| 16.5.1-5 | Integration | `__init__.py`, `server.py`, `CLAUDE.md` | Import tests, docs review |

## Risks, Assumptions, Open Questions

### Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| HA API unavailable | High | Low | Graceful degradation, clear error messages |
| Token exposure in logs | High | Low | SENSITIVE_VARS masking, code review |
| Unauthorized control | Critical | Low | Allowlist enforcement, no bypass code path |
| MQTT broker unreachable | Medium | Low | Auto-reconnect, skip if not configured |
| Network latency spikes | Low | Medium | Configurable timeout, no caching |

### Assumptions

- Home Assistant is running on local network accessible from backend/mcp-server containers
- User has generated a long-lived access token in HA
- Mosquitto broker (if used) allows connections from backend container
- HA automations publishing to `annie/alerts/*` topics are configured by user

### Open Questions

1. **Entity Discovery**: Should we add a tool to list available entities for users unfamiliar with entity IDs?
   - *Decision*: Out of scope for Epic 16; users can check HA UI

2. **Rate Limiting**: Should we implement rate limiting for control operations?
   - *Decision*: Not needed; allowlist is the primary security control

3. **Caching**: Should we cache entity states for faster repeated queries?
   - *Decision*: No caching; always return fresh state for accuracy

## Test Strategy Summary

### Test Levels

| Level | Scope | Framework | Coverage Target |
|-------|-------|-----------|-----------------|
| Unit | Individual functions, classes | pytest | >90% |
| Integration | Tool registration, end-to-end flow | pytest | Key paths |
| Manual | Real HA instance | Skipable decorator | Optional |

### Test Fixtures

```python
# Mock HA responses
@pytest.fixture
def mock_entity_state():
    return {
        "entity_id": "light.living_room",
        "state": "on",
        "attributes": {"brightness": 255},
        "last_changed": "2025-01-09T10:30:00Z"
    }

@pytest.fixture
def mock_ha_client(respx_mock):
    # Configure respx or httpx mock for HA API
    ...
```

### Key Test Cases

**Query Tool:**
- `test_query_single_entity()` - Basic happy path
- `test_query_multiple_entities()` - Batch query
- `test_query_by_domain()` - Domain filtering
- `test_query_entity_not_found()` - 404 handling
- `test_query_unauthorized()` - 401 handling
- `test_query_timeout()` - Timeout behavior
- `test_query_config_error()` - Missing configuration

**Control Tool:**
- `test_control_allowed_entity()` - Happy path
- `test_control_denied_not_in_allowlist()` - Security enforcement
- `test_control_wildcard_allowlist()` - Wildcard matching
- `test_control_empty_allowlist_blocks_all()` - Empty list behavior
- `test_control_turn_on/off/toggle()` - Action mapping
- `test_control_set_brightness()` - Parameter passing
- `test_control_set_temperature()` - Climate control

**MQTT Subscriber:**
- `test_mqtt_connect()` - Connection establishment
- `test_mqtt_receive_json_message()` - JSON parsing
- `test_mqtt_receive_plain_text()` - Plain text handling
- `test_mqtt_reconnect_on_disconnect()` - Reconnection logic
- `test_mqtt_forward_to_telegram()` - Alert delivery

### Mocking Strategy

- Use `respx` or `pytest-httpx` for Home Assistant REST API mocking
- Use `unittest.mock.AsyncMock` for aiomqtt client mocking
- Use environment variable patching for config tests
- Use `pytest.mark.skipif` for optional real HA integration tests

[Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.5]
