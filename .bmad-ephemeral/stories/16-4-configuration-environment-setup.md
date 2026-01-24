# Story 16.4: Configuration & Environment Setup

Status: done

## Story

**As a** developer or operator,
**I want** all Home Assistant integration environment variables properly documented and loaded,
**So that** I can configure the HA connection, allowlists, and MQTT settings for Annie.

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P0
**Estimated Effort:** 0.5 days
**Prerequisites:** None (should be implemented early, but can be done in parallel)

## Acceptance Criteria

### AC #1: All Env Vars in env.example
**Given** the env.example file
**When** a developer reviews it
**Then** all Home Assistant environment variables are documented with:
  - Clear descriptions
  - Default values where applicable
  - Links to obtain tokens
  - Grouping under Epic 16 section

**Variables:**
- HA_URL
- HA_ACCESS_TOKEN
- HA_CONTROL_ALLOWLIST
- HA_TIMEOUT
- HA_MQTT_BROKER
- HA_MQTT_PORT
- HA_MQTT_USERNAME
- HA_MQTT_PASSWORD
- HA_MQTT_TOPICS
- HA_MQTT_ALERT_USER_ID

**Testable:** Verify env.example contains all 10 variables with descriptions

---

### AC #2: HA_ACCESS_TOKEN in SENSITIVE_VARS
**Given** the logging configuration
**When** HA_ACCESS_TOKEN is logged
**Then** it is masked (e.g., "eyJ0...4x9z" → "eyJ0...9z")

**Testable:** Log config, verify token is masked

---

### AC #3: HA_MQTT_PASSWORD in SENSITIVE_VARS
**Given** the logging configuration
**When** HA_MQTT_PASSWORD is logged
**Then** it is masked

**Testable:** Log config, verify password is masked

---

### AC #4: Config Loading in mcp_server/config.py
**Given** the MCP server config module
**When** the server starts
**Then** HA_URL, HA_ACCESS_TOKEN, HA_CONTROL_ALLOWLIST, HA_TIMEOUT are loaded

**Testable:** Import config, verify variables accessible

---

### AC #5: Config Loading in backend/api/config.py
**Given** the backend config module
**When** the backend starts
**Then** all MQTT variables are loaded (HA_MQTT_*)

**Testable:** Import config, verify MQTT variables accessible

---

### AC #6: Docker Compose Env Vars
**Given** docker-compose.yml
**When** containers start
**Then** HA environment variables are passed to appropriate services

**Testable:** Check docker-compose.yml includes HA_* variables

---

### AC #7: Graceful Handling When HA Not Configured
**Given** HA_URL or HA_ACCESS_TOKEN is empty
**When** the tools are called
**Then** they return CONFIG_ERROR without crashing

**Testable:** Start without HA_URL, call tool, verify CONFIG_ERROR response

---

## Tasks / Subtasks

### Task 1: Update env.example (AC: #1)
- [x] Add Epic 16 section header with description
- [x] Add HA_URL with description and example
- [x] Add HA_ACCESS_TOKEN with instructions to generate token
- [x] Add HA_CONTROL_ALLOWLIST with wildcard syntax documentation
- [x] Add HA_TIMEOUT with default value (10)
- [x] Add HA_MQTT_BROKER (optional)
- [x] Add HA_MQTT_PORT with default (1883)
- [x] Add HA_MQTT_USERNAME (optional)
- [x] Add HA_MQTT_PASSWORD (optional, note: sensitive)
- [x] Add HA_MQTT_TOPICS with default pattern
- [x] Add HA_MQTT_ALERT_USER_ID

### Task 2: Update mcp_server/config.py (AC: #2, #4)
- [x] Add HA_URL loading with empty default
- [x] Add HA_ACCESS_TOKEN loading with empty default
- [x] Add HA_ACCESS_TOKEN to SENSITIVE_VARS list
- [x] Add HA_CONTROL_ALLOWLIST loading with empty default
- [x] Add HA_TIMEOUT loading with default 10
- [x] Add validation function for HA config
- [x] Ensure masking works in get_masked_config()

### Task 3: Update backend/api/config.py (AC: #3, #5)
- [x] Add HA_MQTT_BROKER loading with empty default
- [x] Add HA_MQTT_PORT loading with default 1883
- [x] Add HA_MQTT_USERNAME loading with empty default
- [x] Add HA_MQTT_PASSWORD loading with empty default
- [x] Add HA_MQTT_PASSWORD to SENSITIVE_VARS list
- [x] Add HA_MQTT_TOPICS loading with default "annie/alerts/#"
- [x] Add HA_MQTT_ALERT_USER_ID loading with empty default
- [x] Ensure masking works for MQTT password

### Task 4: Update docker-compose.yml (AC: #6)
- [x] Add HA_* environment variables to mcp-server service
- [x] Add HA_MQTT_* environment variables to backend service
- [x] Verify variable passthrough from host .env

### Task 5: Add Config Validation (AC: #7)
- [x] Implement `validate_ha_config()` in mcp_server/config.py
  - Check HA_URL and HA_ACCESS_TOKEN are set
  - Return list of missing/invalid configs
- [x] Implement `validate_mqtt_config()` in backend/api/config.py
  - Only validate if HA_MQTT_BROKER is set
  - Check HA_MQTT_ALERT_USER_ID if broker is configured

---

## Dev Notes

### Environment Variables Reference

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

### Config Loading Pattern

Follow existing patterns in config.py files:

```python
# mcp_server/config.py

# Epic 16: Home Assistant Integration
HA_URL = os.getenv("HA_URL", "")
HA_ACCESS_TOKEN = os.getenv("HA_ACCESS_TOKEN", "")
HA_CONTROL_ALLOWLIST = os.getenv("HA_CONTROL_ALLOWLIST", "")
HA_TIMEOUT = int(os.getenv("HA_TIMEOUT", "10"))

# Add to SENSITIVE_VARS
SENSITIVE_VARS = [
    "GROK_API_KEY",
    "CHATGPT_API_KEY",
    "HA_ACCESS_TOKEN",  # NEW
    # ...
]
```

```python
# backend/api/config.py

# Epic 16: MQTT Configuration
HA_MQTT_BROKER = os.getenv("HA_MQTT_BROKER", "")
HA_MQTT_PORT = int(os.getenv("HA_MQTT_PORT", "1883"))
HA_MQTT_USERNAME = os.getenv("HA_MQTT_USERNAME", "")
HA_MQTT_PASSWORD = os.getenv("HA_MQTT_PASSWORD", "")
HA_MQTT_TOPICS = os.getenv("HA_MQTT_TOPICS", "annie/alerts/#")
HA_MQTT_ALERT_USER_ID = os.getenv("HA_MQTT_ALERT_USER_ID", "")

# Add to SENSITIVE_VARS
SENSITIVE_VARS = [
    # ... existing ...
    "HA_MQTT_PASSWORD",  # NEW
]
```

### Docker Compose Updates

```yaml
# docker-compose.yml

services:
  mcp-server:
    environment:
      - HA_URL=${HA_URL}
      - HA_ACCESS_TOKEN=${HA_ACCESS_TOKEN}
      - HA_CONTROL_ALLOWLIST=${HA_CONTROL_ALLOWLIST}
      - HA_TIMEOUT=${HA_TIMEOUT}

  backend:
    environment:
      - HA_MQTT_BROKER=${HA_MQTT_BROKER}
      - HA_MQTT_PORT=${HA_MQTT_PORT}
      - HA_MQTT_USERNAME=${HA_MQTT_USERNAME}
      - HA_MQTT_PASSWORD=${HA_MQTT_PASSWORD}
      - HA_MQTT_TOPICS=${HA_MQTT_TOPICS}
      - HA_MQTT_ALERT_USER_ID=${HA_MQTT_ALERT_USER_ID}
```

### Project Structure Notes

Files to modify:
- `env.example` - Add all 10 new variables
- `mcp_server/config.py` - Add HA_* variables
- `backend/api/config.py` - Add HA_MQTT_* variables
- `docker-compose.yml` - Pass variables to services

### Validation Functions

```python
def validate_ha_config() -> list[str]:
    """Return list of configuration issues."""
    issues = []
    if not HA_URL:
        issues.append("HA_URL not configured")
    if not HA_ACCESS_TOKEN:
        issues.append("HA_ACCESS_TOKEN not configured")
    return issues

def is_ha_configured() -> bool:
    """Check if HA is configured (for graceful skip)."""
    return bool(HA_URL and HA_ACCESS_TOKEN)
```

### Learnings from Previous Story

**From Story 15-6 (Status: done)**
- Document env vars with clear descriptions and links
- Group under epic section header
- Add to SENSITIVE_VARS for masking
- Use `os.getenv()` with sensible defaults

[Source: stories/15-6-env-config-documentation.md]

### References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.4]
- [Source: Home Assistant Long-Lived Access Tokens](https://www.home-assistant.io/docs/authentication/#your-account-profile)

---

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/16-4-configuration-environment-setup.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Fixed endless log spam issue: Moved MQTT status logging from validate_environment() to startup_event() in main.py

### Completion Notes List

- All 10 HA environment variables added to env.example with comprehensive documentation
- HA_ACCESS_TOKEN added to SENSITIVE_VARS in mcp_server/config.py
- HA_MQTT_PASSWORD added to SENSITIVE_VARS in backend/api/config.py
- validate_ha_config() and is_ha_configured() implemented in mcp_server/config.py
- validate_mqtt_config() and is_mqtt_configured() implemented in backend/api/config.py
- Docker Compose updated to pass HA_* vars to mcp-server, HA_MQTT_* vars to backend
- 33 unit tests created and passing (15 MCP server + 18 backend)

### File List

**Modified:**
- env.example (lines 146-207: Epic 16 section with all 10 HA variables)
- mcp_server/config.py (HA_* config loading, SENSITIVE_VARS, validation functions)
- backend/api/config.py (HA_MQTT_* config loading, SENSITIVE_VARS, validation functions)
- backend/api/main.py (MQTT status logging moved to startup_event)
- docker-compose.yml (HA_* to mcp-server, HA_MQTT_* to backend)

**Created:**
- mcp_server/tests/test_ha_config.py (15 tests)
- backend/tests/unit/test_mqtt_config.py (18 tests)

---

**Created:** 2025-01-10
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.4 - Configuration & Environment Setup
