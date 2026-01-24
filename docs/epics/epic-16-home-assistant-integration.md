# Epic: Home Assistant Integration

> **Epic ID**: 16
> **Status**: Draft
> **Priority**: Medium
> **Estimated Effort**: 5-7 days
> **Dependencies**: Home Assistant REST API, Mosquitto MQTT Broker

---

## 1. Overview

### 1.1 Problem Statement

Annie currently has no awareness of or control over the physical home environment:

- **No State Awareness**: Cannot answer questions like "Is the garage door closed?" or "What's the thermostat set to?"
- **No Device Control**: Cannot perform actions like "Turn on the living room lights" even with explicit user permission
- **No Proactive Alerts**: Cannot receive notifications about home events (motion detected, door left open, temperature changes)

This limits Annie's usefulness as a personal AI companion in daily life scenarios where home automation context is valuable.

### 1.2 Solution

Implement bidirectional Home Assistant integration through two channels:

1. **Annie → Home Assistant (MCP Tools)**
   - `home_assistant_query` - Read entity states (lights, switches, climate, sensors)
   - `home_assistant_control` - Control entities with allowlist enforcement

2. **Home Assistant → Annie (MQTT)**
   - Subscribe to Mosquitto broker for event notifications
   - Forward alerts to user via Telegram

### 1.3 Success Criteria

| Metric | Target |
|--------|--------|
| `home_assistant_query` latency p95 | <500ms |
| `home_assistant_control` latency p95 | <1s |
| MQTT message delivery latency | <2s |
| Tool success rate | >99% (local network) |
| Allowlist enforcement | 100% (no bypass) |
| MQTT reconnection time | <30s |

---

## 2. Architecture

### 2.1 Query Flow (Annie → HA)

```
User: "Is my garage door closed?"
         ↓
       LLM
         ↓
home_assistant_query tool
         ↓
    MCP Server
         ↓ HTTP GET /api/states/{entity_id}
    Home Assistant REST API
         ↓
    Entity State Response
    - state: "closed"
    - attributes: {...}
    - last_changed: timestamp
         ↓
    Formatted Response to User
```

### 2.2 Control Flow (Annie → HA, Allowlist-Enforced)

```
User: "Turn on the living room lights"
         ↓
       LLM
         ↓
home_assistant_control tool
         ↓
    MCP Server
         ↓
    ┌─────────────────────────────────┐
    │ SECURITY: Allowlist Check       │
    │ Is light.living_room in         │
    │ HA_CONTROL_ALLOWLIST?           │
    └─────────────────────────────────┘
         ↓ YES                    ↓ NO
    POST /api/services/        Return FORBIDDEN
    light/turn_on              error to LLM
         ↓
    Success Response
    - previous_state: "off"
    - new_state: "on"
```

### 2.3 Alert Flow (HA → Annie via MQTT)

```
Home Assistant Automation
    ↓
Mosquitto Broker
    ↓ Publish to annie/alerts/motion
    ↓
Backend MQTT Subscriber
    ↓ Parse message
    ↓
Telegram Delivery
    ↓
User receives: "Motion detected in backyard"
```

### 2.4 System Context

```
┌─────────────────────────────────────────────────────────────────┐
│                        Annie System                              │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐       │
│  │  Telegram   │────▶│   Backend   │────▶│ MCP Server  │       │
│  │    Bot      │◀────│    API      │◀────│             │       │
│  └─────────────┘     └──────┬──────┘     └──────┬──────┘       │
│                             │                    │               │
│                      MQTT   │              REST  │               │
│                   Subscribe │              API   │               │
└─────────────────────────────┼────────────────────┼───────────────┘
                              │                    │
┌─────────────────────────────┼────────────────────┼───────────────┐
│                    Local Network                                 │
│  ┌─────────────────┐        │                    │               │
│  │   Mosquitto     │◀───────┘                    │               │
│  │  MQTT Broker    │                             │               │
│  └────────┬────────┘                             │               │
│           │                                      ▼               │
│           │              ┌───────────────────────────────┐      │
│           └─────────────▶│      Home Assistant           │      │
│                          │   - REST API (:8123)          │      │
│                          │   - MQTT Integration          │      │
│                          │   - Automations               │      │
│                          └───────────────────────────────┘      │
└──────────────────────────────────────────────────────────────────┘
```

---

## 3. Stories

### Story 16.1: Home Assistant Query Tool

**Priority**: P0
**Estimate**: 1 day

Implement `home_assistant_query` MCP tool for reading entity states from Home Assistant.

**File**: `mcp_server/tools/home_assistant.py`

**Schema**:
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
                "description": "List of entity IDs to query (e.g., ['light.living_room', 'sensor.temperature'])"
            },
            "domain": {
                "type": "string",
                "enum": ["light", "switch", "sensor", "climate", "binary_sensor", "cover", "fan", "all"],
                "description": "Query all entities in a domain. Use 'all' for complete state dump."
            }
        },
        "oneOf": [
            {"required": ["entity_ids"]},
            {"required": ["domain"]}
        ]
    }
}
```

**Response**:
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
                "color_temp": 350,
                "friendly_name": "Living Room Light"
            },
            "last_changed": "2025-01-09T10:30:00Z"
        },
        {
            "entity_id": "sensor.temperature",
            "state": "72.5",
            "attributes": {
                "unit_of_measurement": "°F",
                "friendly_name": "Indoor Temperature"
            },
            "last_changed": "2025-01-09T10:45:00Z"
        }
    ],
    "query_count": 2
}
```

**Acceptance Criteria**:
- [ ] Query specific entities by ID list
- [ ] Query all entities in a domain
- [ ] Return state, attributes, and last_changed for each entity
- [ ] Handle 404 (entity not found) gracefully
- [ ] Handle 401 (invalid token) with clear error
- [ ] Timeout after HA_TIMEOUT seconds (default: 10)
- [ ] Structured logging with duration_ms
- [ ] Unit tests with mocked HA responses

---

### Story 16.2: Home Assistant Control Tool (Allowlist-Enforced)

**Priority**: P0
**Estimate**: 1.5 days

Implement `home_assistant_control` MCP tool with mandatory allowlist enforcement.

**File**: `mcp_server/tools/home_assistant.py`

**Schema**:
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

**Response (Success)**:
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

**Response (Forbidden)**:
```python
{
    "status": "error",
    "provider": "home_assistant",
    "error_code": "FORBIDDEN",
    "error_message": "Entity 'light.bedroom' not in allowlist. Allowed: light.living_room, switch.fan, climate.thermostat",
    "entity_id": "light.bedroom"
}
```

**Allowlist Configuration**:
```bash
# Exact entity IDs
HA_CONTROL_ALLOWLIST=light.living_room,switch.fan,climate.thermostat

# Domain wildcards supported
HA_CONTROL_ALLOWLIST=light.*,switch.fan  # All lights + specific switch

# Empty allowlist = all control disabled
HA_CONTROL_ALLOWLIST=
```

**Acceptance Criteria**:
- [ ] Allowlist parsing from HA_CONTROL_ALLOWLIST env var
- [ ] Support exact match (light.living_room)
- [ ] Support domain wildcards (light.*)
- [ ] Empty allowlist blocks all control operations
- [ ] FORBIDDEN error includes list of allowed entities
- [ ] Map actions to HA service calls correctly
- [ ] Return previous_state and new_state
- [ ] Log all control attempts (allowed and denied)
- [ ] Unit tests for allowlist enforcement
- [ ] Unit tests for all action types

---

### Story 16.3: MQTT Subscriber Service

**Priority**: P1
**Estimate**: 1.5 days

Implement MQTT subscriber in the backend to receive Home Assistant alerts.

**File**: `backend/api/mqtt_subscriber.py`

**Configuration**:
```bash
HA_MQTT_BROKER=192.168.1.x        # Mosquitto broker host
HA_MQTT_PORT=1883                 # Broker port
HA_MQTT_USERNAME=                 # Optional auth
HA_MQTT_PASSWORD=                 # Optional auth
HA_MQTT_TOPICS=annie/alerts/#    # Topics to subscribe
HA_MQTT_ALERT_USER_ID=12345      # Telegram user for alerts
```

**Message Format** (from HA automations):
```json
{
    "title": "Motion Detected",
    "message": "Motion detected in backyard at 10:45 PM",
    "entity_id": "binary_sensor.backyard_motion",
    "state": "on"
}
```

**Telegram Output**:
```
**Motion Detected**

Motion detected in backyard at 10:45 PM

_Topic: annie/alerts/motion_
```

**Acceptance Criteria**:
- [ ] Connect to Mosquitto broker on startup (if configured)
- [ ] Subscribe to configured topics
- [ ] Parse JSON and plain text messages
- [ ] Forward messages to Telegram via TelegramDelivery
- [ ] Auto-reconnect on connection loss (5s backoff)
- [ ] Log all received messages
- [ ] Graceful shutdown on SIGTERM
- [ ] Skip if HA_MQTT_BROKER not configured
- [ ] Unit tests with mocked MQTT client

---

### Story 16.4: Configuration & Environment Setup

**Priority**: P0
**Estimate**: 0.5 days

Add all required environment variables and configuration.

**Files**:
- `env.example`
- `mcp_server/config.py`
- `backend/api/config.py`
- `docker-compose.yml`

**New Environment Variables**:
```bash
# ============================================================================
# Home Assistant Integration (Epic 16)
# ============================================================================

# Home Assistant REST API
# Base URL of your Home Assistant instance
HA_URL=http://192.168.1.x:8123

# Long-Lived Access Token
# Generate in HA: Profile -> Security -> Long-Lived Access Tokens
HA_ACCESS_TOKEN=REPLACE_ME

# Control Allowlist (comma-separated entity IDs)
# Only these entities can be controlled via home_assistant_control tool
# Supports wildcards: light.* allows all lights
# Empty = no control allowed (query-only mode)
HA_CONTROL_ALLOWLIST=

# Request timeout in seconds (default: 10)
HA_TIMEOUT=10

# MQTT Configuration (Optional - for HA->Annie alerts)
HA_MQTT_BROKER=
HA_MQTT_PORT=1883
HA_MQTT_USERNAME=
HA_MQTT_PASSWORD=
HA_MQTT_TOPICS=annie/alerts/#
HA_MQTT_ALERT_USER_ID=
```

**Acceptance Criteria**:
- [ ] All env vars added to env.example with documentation
- [ ] HA_ACCESS_TOKEN added to SENSITIVE_VARS (masked in logs)
- [ ] HA_MQTT_PASSWORD added to SENSITIVE_VARS
- [ ] Config loading in mcp_server/config.py
- [ ] Config loading in backend/api/config.py
- [ ] Docker Compose updated to pass env vars
- [ ] Graceful handling when HA not configured

---

### Story 16.5: Integration Testing & Documentation

**Priority**: P1
**Estimate**: 1 day

Register tools, write tests, and update documentation.

**Files**:
- `mcp_server/tools/__init__.py` - Export tools
- `mcp_server/server.py` - Register tools
- `mcp_server/tests/test_home_assistant_tools.py`
- `backend/tests/test_mqtt_subscriber.py`
- `mcp_server/requirements.txt` - Add aiomqtt
- `backend/requirements.txt` - Add aiomqtt
- `CLAUDE.md` - Tool documentation

**Test Cases**:
```python
# Query tool tests
test_query_single_entity()
test_query_multiple_entities()
test_query_by_domain()
test_query_entity_not_found()
test_query_unauthorized()
test_query_timeout()

# Control tool tests
test_control_allowed_entity()
test_control_denied_not_in_allowlist()
test_control_wildcard_allowlist()
test_control_empty_allowlist_blocks_all()
test_control_turn_on()
test_control_set_brightness()
test_control_set_temperature()

# MQTT tests
test_mqtt_connect()
test_mqtt_receive_json_message()
test_mqtt_receive_plain_text()
test_mqtt_reconnect_on_disconnect()
test_mqtt_forward_to_telegram()
```

**Acceptance Criteria**:
- [ ] Tools exported in __init__.py
- [ ] Tools registered in server.py
- [ ] Unit tests with >90% coverage
- [ ] Integration test (skippable) with real HA
- [ ] CLAUDE.md updated with tool documentation
- [ ] aiomqtt>=2.0.0 in requirements.txt

---

### Story 16.6: Voice Message Tool for Smart Home Speakers

**Priority**: P1
**Estimate**: 1 day

Implement `send_voice_message_to_smart_home` MCP tool enabling Annie to speak through Alexa devices via Home Assistant's `notify.alexa_media` service. This gives Annie an ambient voice presence in the home with emotional expression capabilities.

**File**: `mcp_server/tools/home_assistant.py`

**Schema**:
```python
{
    "name": "send_voice_message_to_smart_home",
    "description": (
        "Send a voice message to smart home speakers (Alexa devices) via Home Assistant. "
        "USE WITH DISCRETION - CONSTRAINTS: "
        "1) Only effective when user is physically at home. "
        "2) COMPLEMENT to text responses, not replacement - always send text too. "
        "3) 60-second cooldown between messages. "
        "VOICE TYPES - choose based on emotional context: "
        "- 'say': Neutral delivery (default) "
        "- 'announce': Attention tone first - for urgent matters "
        "- 'whisper': Soft, intimate - for gentle reminders, private moments "
        "- 'excited': Happy, enthusiastic - for celebrations, good news "
        "- 'disappointed': Empathetic, sympathetic - for comfort, bad news "
        "- 'conversational': Casual, friendly - like chatting with a friend "
        "- 'news': Formal delivery - for factual information "
        "- 'fun': Animated, playful - for greetings, lighthearted moments "
        "AVOID: routine responses, sensitive info, late night (unless urgent)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message for Annie to speak aloud"
            },
            "devices": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Target device entity IDs (e.g., ['media_player.kitchen_echo', 'media_player.bedroom_echo'])"
            },
            "voice_type": {
                "type": "string",
                "enum": ["say", "announce", "whisper", "excited", "disappointed", "conversational", "news", "fun"],
                "default": "say",
                "description": (
                    "How to deliver the message. "
                    "'say': Neutral (default). "
                    "'announce': Attention tone first. "
                    "'whisper': Soft, intimate. "
                    "'excited': Happy, enthusiastic. "
                    "'disappointed': Empathetic, sympathetic. "
                    "'conversational': Casual, friendly. "
                    "'news': Formal, factual. "
                    "'fun': Animated, playful."
                )
            }
        },
        "required": ["message", "devices"]
    }
}
```

**Response (Success)**:
```python
{
    "status": "success",
    "provider": "home_assistant",
    "devices": ["media_player.kitchen_echo", "media_player.bedroom_echo"],
    "message": "Dinner is ready!",
    "voice_type": "announce",
    "cooldown_seconds": 60
}
```

**Response (Cooldown)**:
```python
{
    "status": "error",
    "provider": "home_assistant",
    "error_code": "COOLDOWN",
    "error_message": "Voice message on cooldown. Try again in 45 seconds.",
    "seconds_remaining": 45
}
```

**Response (Invalid Device)**:
```python
{
    "status": "error",
    "provider": "home_assistant",
    "error_code": "INVALID_DEVICE",
    "error_message": "Unknown device(s): ['media_player.fake_echo']",
    "invalid_devices": ["media_player.fake_echo"],
    "valid_devices": ["media_player.kitchen_echo", "media_player.bedroom_echo", "media_player.living_room_echo"]
}
```

**Voice Type SSML Mapping**:
```python
VOICE_TYPES = {
    # Basic delivery
    "say": {"method": "tts", "ssml": None},
    "announce": {"method": "announce", "ssml": None},

    # Effects (SSML wrapped)
    "whisper": {
        "method": "tts",
        "ssml": '<amazon:effect name="whispered">{message}</amazon:effect>'
    },

    # Emotions (SSML wrapped)
    "excited": {
        "method": "tts",
        "ssml": '<amazon:emotion name="excited" intensity="medium">{message}</amazon:emotion>'
    },
    "disappointed": {
        "method": "tts",
        "ssml": '<amazon:emotion name="disappointed" intensity="medium">{message}</amazon:emotion>'
    },

    # Speaking Styles (SSML wrapped)
    "conversational": {
        "method": "tts",
        "ssml": '<amazon:domain name="conversational">{message}</amazon:domain>'
    },
    "news": {
        "method": "tts",
        "ssml": '<amazon:domain name="news">{message}</amazon:domain>'
    },
    "fun": {
        "method": "tts",
        "ssml": '<amazon:domain name="fun">{message}</amazon:domain>'
    },
}
```

**Implementation Flow**:
```
send_voice_message_to_smart_home(message, devices, voice_type)
│
├─→ Check cooldown (fail fast if < 60s since last success)
│   └─→ Return COOLDOWN error with seconds_remaining
│
├─→ Validate inputs
│   ├─→ message not empty
│   └─→ devices list not empty
│
├─→ Query HA for valid media_player entities
│   └─→ home_assistant_query(domain="media_player")
│
├─→ Validate ALL requested devices exist
│   ├─→ All valid: proceed
│   └─→ Any invalid: return INVALID_DEVICE + valid_devices list
│       (fail entire request, no partial sends)
│
├─→ Build SSML-wrapped message based on voice_type
│
├─→ Call notify.alexa_media service
│   POST /api/services/notify/alexa_media
│   {
│       "message": "<ssml-wrapped-message>",
│       "target": ["media_player.kitchen_echo", ...],
│       "data": {"type": "tts" | "announce"}
│   }
│
├─→ On success: update _last_voice_message_time
│
└─→ Return result
```

**Acceptance Criteria**:
- [ ] Tool `send_voice_message_to_smart_home` registered in MCP server
- [ ] Calls `notify.alexa_media` service with SSML-wrapped message
- [ ] Supports single or multiple device targets (entity IDs)
- [ ] Supports 8 voice types: say, announce, whisper, excited, disappointed, conversational, news, fun
- [ ] Wraps emotions/styles in appropriate SSML tags
- [ ] Enforces 60-second cooldown between successful sends
- [ ] Cooldown NOT consumed on failed attempts (errors, invalid devices)
- [ ] Validates devices against live HA `media_player` domain query
- [ ] Fails entire request if ANY device is invalid (no partial sends)
- [ ] On invalid device: returns error with `valid_devices` list for Annie to learn
- [ ] Returns clear status codes: success, COOLDOWN, INVALID_DEVICE, NETWORK_ERROR, CONFIG_ERROR
- [ ] Tool description guides Annie's discretion (home-only, complement to text, voice type selection)
- [ ] Logs all invocations with devices, voice_type, cooldown state, duration_ms
- [ ] Unit tests for cooldown enforcement
- [ ] Unit tests for device validation
- [ ] Unit tests for SSML wrapping
- [ ] Integration test (skippable) with real HA + Alexa

**Out of Scope**:
- Device registry / friendly name mapping (future story)
- Quiet hours / time-based restrictions (future story)
- Per-device cooldowns (single global cooldown for MVP)
- Intensity parameter for emotions (fixed at "medium" for MVP)

---

## 4. Technical Considerations

### 4.1 Home Assistant REST API

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/states` | GET | Get all entity states |
| `/api/states/{entity_id}` | GET | Get single entity state |
| `/api/services/{domain}/{service}` | POST | Call a service (turn_on, etc.) |

**Authentication**: Bearer token in Authorization header
```
Authorization: Bearer <long_lived_access_token>
```

### 4.2 Service Mapping

| Action | Domain | Service | Parameters |
|--------|--------|---------|------------|
| turn_on | light/switch/fan | turn_on | entity_id |
| turn_off | light/switch/fan | turn_off | entity_id |
| toggle | light/switch | toggle | entity_id |
| set_brightness | light | turn_on | entity_id, brightness (0-255) |
| set_temperature | climate | set_temperature | entity_id, temperature |
| set_hvac_mode | climate | set_hvac_mode | entity_id, hvac_mode |
| set_position | cover | set_cover_position | entity_id, position (0-100) |

### 4.3 Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| CONFIG_ERROR | N/A | HA_URL or HA_ACCESS_TOKEN not configured |
| FORBIDDEN | N/A | Entity not in allowlist (control only) |
| UNAUTHORIZED | 401 | Invalid access token |
| NOT_FOUND | 404 | Entity doesn't exist |
| TIMEOUT | N/A | Request exceeded HA_TIMEOUT |
| NETWORK_ERROR | N/A | Connection to HA failed |
| SERVER_ERROR | 5xx | Home Assistant error |

### 4.4 MQTT Topics

Recommended HA automation topic structure:
```
annie/alerts/motion      # Motion detection
annie/alerts/door        # Door open/close
annie/alerts/climate     # Temperature alerts
annie/alerts/security    # Security events
```

---

## 5. Dependencies

### 5.1 External Services

| Service | Required | Purpose |
|---------|----------|---------|
| Home Assistant | Yes | Smart home platform |
| Mosquitto | Optional | MQTT broker for alerts |

### 5.2 Python Packages

```
# MCP Server
httpx>=0.24.0  # Already present

# Backend (for MQTT)
aiomqtt>=2.0.0
```

### 5.3 Home Assistant Setup

1. **Generate Long-Lived Access Token**:
   - HA → Profile → Security → Long-Lived Access Tokens → Create Token

2. **Create Automations for Annie Alerts** (example):
   ```yaml
   alias: "Notify Annie - Motion Detected"
   trigger:
     - platform: state
       entity_id: binary_sensor.backyard_motion
       to: "on"
   action:
     - service: mqtt.publish
       data:
         topic: "annie/alerts/motion"
         payload: >
           {"title": "Motion Detected", "message": "Motion in backyard"}
   ```

---

## 6. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| HA API unavailable | High | Low | Graceful degradation, clear error messages |
| Token exposure in logs | High | Low | SENSITIVE_VARS masking |
| Unauthorized control | Critical | Low | Allowlist enforcement, no bypass possible |
| MQTT broker unreachable | Medium | Low | Auto-reconnect, skip if not configured |
| Network latency | Low | Medium | Configurable timeout, no caching |

---

## 7. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Query response time | <500ms p95 | Structured logs duration_ms |
| Control response time | <1s p95 | Structured logs duration_ms |
| Allowlist enforcement | 100% | No FORBIDDEN bypass in logs |
| MQTT uptime | >99% | Reconnection frequency |
| User satisfaction | Qualitative | Actual usage patterns |

---

## 8. Future Considerations

- **Entity Discovery**: Auto-discover available entities from HA
- **Scene Support**: Activate HA scenes ("Movie mode", "Good night")
- **Voice Commands**: Integration with voice-to-text for hands-free control
- **Presence Detection**: Use HA presence sensors for context
- **Energy Monitoring**: Query energy consumption data
- **Calendar Integration**: HA calendar events for scheduling
- **Camera Snapshots**: Fetch camera images on request
