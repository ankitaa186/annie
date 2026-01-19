# Story 16.6: Voice Message Tool for Smart Home Speakers

Status: ready-for-dev

## Story

**As a** user (Ankit),
**I want** Annie to send voice messages through my Alexa devices,
**So that** Annie can provide ambient, hands-free communication when I'm at home with emotional expression capabilities.

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P1
**Estimated Effort:** 1 day
**Prerequisites:** Stories 16.1, 16.2, 16.4 (HA client and configuration)

## Acceptance Criteria

### AC #1: Tool Registration
**Given** the MCP server
**When** tools/list is called
**Then** `send_voice_message_to_smart_home` appears with correct schema

**Testable:** Verify tool in /tools/list response with all parameters

---

### AC #2: notify.alexa_media Service Call
**Given** valid message and devices
**When** the tool is invoked
**Then** it calls Home Assistant `notify.alexa_media` service with SSML-wrapped message

**Testable:** Mock HA API, verify POST to /api/services/notify/alexa_media with correct payload

---

### AC #3: Multi-Device Support
**Given** a devices array with multiple entity IDs
**When** the tool is invoked
**Then** all specified devices receive the message

**Testable:** Call with `["media_player.kitchen", "media_player.bedroom"]`, verify both in target array

---

### AC #4: Voice Type Support (8 types)
**Given** any of the 8 voice types: say, announce, whisper, excited, disappointed, conversational, news, fun
**When** the tool is invoked with that voice_type
**Then** the message is wrapped in appropriate SSML tags

**Testable:**
- `say` → plain message, method=tts
- `announce` → plain message, method=announce
- `whisper` → `<amazon:effect name="whispered">{msg}</amazon:effect>`
- `excited` → `<amazon:emotion name="excited" intensity="medium">{msg}</amazon:emotion>`
- `disappointed` → `<amazon:emotion name="disappointed" intensity="medium">{msg}</amazon:emotion>`
- `conversational` → `<amazon:domain name="conversational">{msg}</amazon:domain>`
- `news` → `<amazon:domain name="news">{msg}</amazon:domain>`
- `fun` → `<amazon:domain name="fun">{msg}</amazon:domain>`

---

### AC #5: 60-Second Cooldown Enforcement
**Given** a successful voice message send
**When** another send is attempted within 60 seconds
**Then** returns COOLDOWN error with `seconds_remaining`

**Testable:**
- Send message → success
- Immediately send again → COOLDOWN error with seconds_remaining > 0
- Wait 60s → success

---

### AC #6: Cooldown NOT Consumed on Errors
**Given** a failed voice message attempt (invalid device, network error)
**When** another send is attempted
**Then** it proceeds without cooldown (errors don't start cooldown)

**Testable:** Send to invalid device → error → immediately send to valid device → success

---

### AC #7: Device Validation via Live HA Query
**Given** device entity IDs in the request
**When** the tool is invoked
**Then** it validates all devices exist by querying HA `media_player` domain

**Testable:** Mock `home_assistant_query(domain="media_player")`, verify it's called before sending

---

### AC #8: Fail-All on Invalid Device
**Given** a mix of valid and invalid device IDs
**When** the tool is invoked
**Then** entire request fails with INVALID_DEVICE error (no partial sends)
**And** response includes `valid_devices` list

**Testable:** Send to `["media_player.kitchen", "media_player.fake"]` → error with valid_devices list

---

### AC #9: Clear Error Codes
**Given** various error conditions
**When** errors occur
**Then** returns appropriate error codes: COOLDOWN, INVALID_DEVICE, NETWORK_ERROR, CONFIG_ERROR

**Testable:** Trigger each error condition, verify correct error_code

---

### AC #10: LLM-Guiding Tool Description
**Given** the tool schema
**When** Annie's LLM reads it
**Then** description clearly communicates:
- Only effective when user is at home
- Complement to text (not replacement)
- 60-second cooldown
- Voice type guidance for emotional context

**Testable:** Verify tool description contains all constraint guidance

---

### AC #11: Structured Logging
**Given** any tool invocation
**When** the handler executes
**Then** logs include: devices, voice_type, cooldown_state, duration_ms, status

**Testable:** Check log output contains all required fields

---

### AC #12: Unit Tests for Cooldown
**Given** the cooldown mechanism
**When** tests run
**Then** >90% coverage for cooldown logic

**Testable:** pytest --cov with cooldown test cases

---

### AC #13: Unit Tests for Device Validation
**Given** the device validation logic
**When** tests run
**Then** >90% coverage for validation paths

**Testable:** pytest --cov with validation test cases

---

### AC #14: Unit Tests for SSML Wrapping
**Given** all 8 voice types
**When** tests run
**Then** each voice type produces correct SSML output

**Testable:** Unit test for each VOICE_TYPES entry

---

### AC #15: Integration Test (Skippable)
**Given** a real Home Assistant + Alexa setup
**When** integration tests run
**Then** verifies actual voice message delivery (skipped if HA not configured)

**Testable:** pytest --run-integration with @pytest.mark.skipif decorator

---

## Tasks / Subtasks

### Task 1: Implement VOICE_TYPES Mapping (AC: #4)
- [ ] Define VOICE_TYPES dict in `mcp_server/tools/home_assistant.py`
- [ ] Map each voice_type to method (tts/announce) and SSML template
- [ ] Implement `build_ssml_message(message, voice_type)` helper function

### Task 2: Implement Cooldown Mechanism (AC: #5, #6)
- [ ] Add module-level `_last_voice_message_time: Optional[float] = None`
- [ ] Add `VOICE_MESSAGE_COOLDOWN_SECONDS = 60`
- [ ] Implement cooldown check at start of handler
- [ ] Only update timestamp on SUCCESS (not on errors)
- [ ] Return `seconds_remaining` in COOLDOWN error

### Task 3: Implement Device Validation (AC: #7, #8)
- [ ] Call `home_assistant_query_handler(domain="media_player")`
- [ ] Extract valid entity IDs from response
- [ ] Compare requested devices against valid set
- [ ] If any invalid: return INVALID_DEVICE with `valid_devices` list
- [ ] Fail entire request (no partial sends)

### Task 4: Implement notify.alexa_media Service Call (AC: #2, #3)
- [ ] Build service call payload:
  ```python
  {
      "message": ssml_wrapped_message,
      "target": devices,  # List of entity_ids
      "data": {"type": "tts" | "announce"}
  }
  ```
- [ ] POST to `/api/services/notify/alexa_media`
- [ ] Handle success and error responses

### Task 5: Implement Main Handler (AC: #1, #9, #11)
- [ ] Create `send_voice_message_to_smart_home_handler(message, devices, voice_type="say")`
- [ ] Implement flow:
  1. Check cooldown (fail fast)
  2. Validate inputs (message not empty, devices not empty)
  3. Query HA for valid media_player entities
  4. Validate all requested devices exist
  5. Build SSML-wrapped message
  6. Call notify.alexa_media service
  7. On success: update cooldown timestamp
  8. Return result
- [ ] Add structured logging with all required fields

### Task 6: Create Tool Schema Definition (AC: #1, #10)
- [ ] Define `send_voice_message_to_smart_home_tool` dict with:
  - name
  - description (with LLM guidance)
  - inputSchema with message, devices, voice_type
- [ ] Export from home_assistant.py

### Task 7: Register Tool in MCP Server (AC: #1)
- [ ] Update `mcp_server/tools/__init__.py` to export new tool
- [ ] Update `mcp_server/server.py` to register tool
- [ ] Verify appears in /tools/list

### Task 8: Write Unit Tests (AC: #12, #13, #14)
- [ ] Create `mcp_server/tests/test_voice_message_tool.py`
- [ ] Test cooldown enforcement:
  - `test_cooldown_blocks_rapid_sends()`
  - `test_cooldown_allows_after_60s()`
  - `test_cooldown_not_consumed_on_error()`
- [ ] Test device validation:
  - `test_valid_devices_pass()`
  - `test_invalid_device_returns_valid_list()`
  - `test_mixed_devices_fail_all()`
- [ ] Test SSML wrapping:
  - `test_voice_type_say()`
  - `test_voice_type_announce()`
  - `test_voice_type_whisper()`
  - `test_voice_type_excited()`
  - `test_voice_type_disappointed()`
  - `test_voice_type_conversational()`
  - `test_voice_type_news()`
  - `test_voice_type_fun()`
- [ ] Verify >90% coverage

### Task 9: Write Integration Test (AC: #15)
- [ ] Add skippable integration test:
  ```python
  @pytest.mark.skipif(not os.getenv("HA_URL"), reason="HA not configured")
  def test_real_voice_message():
      ...
  ```

### Task 10: Update CLAUDE.md Documentation
- [ ] Add `send_voice_message_to_smart_home` tool section
- [ ] Document when to use
- [ ] Document voice types with emotional guidance
- [ ] Document constraints (home-only, cooldown, complement)

---

## Dev Notes

### Existing Infrastructure to Reuse

From `mcp_server/tools/home_assistant.py`:
- `HomeAssistantClient` class (line 105) - HTTP client with auth
- `home_assistant_query_handler()` - For validating media_player entities
- Logging patterns with `duration_ms`
- Error code patterns (CONFIG_ERROR, NETWORK_ERROR, etc.)

### SSML Tag Reference

```python
VOICE_TYPES = {
    "say": {"method": "tts", "ssml": None},
    "announce": {"method": "announce", "ssml": None},
    "whisper": {"method": "tts", "ssml": '<amazon:effect name="whispered">{message}</amazon:effect>'},
    "excited": {"method": "tts", "ssml": '<amazon:emotion name="excited" intensity="medium">{message}</amazon:emotion>'},
    "disappointed": {"method": "tts", "ssml": '<amazon:emotion name="disappointed" intensity="medium">{message}</amazon:emotion>'},
    "conversational": {"method": "tts", "ssml": '<amazon:domain name="conversational">{message}</amazon:domain>'},
    "news": {"method": "tts", "ssml": '<amazon:domain name="news">{message}</amazon:domain>'},
    "fun": {"method": "tts", "ssml": '<amazon:domain name="fun">{message}</amazon:domain>'},
}
```

### Service Call Format

```python
# POST /api/services/notify/alexa_media
{
    "message": "<amazon:emotion name='excited' intensity='medium'>Great news!</amazon:emotion>",
    "target": ["media_player.kitchen_echo", "media_player.bedroom_echo"],
    "data": {"type": "tts"}  # or "announce" for attention tone
}
```

### Cooldown Implementation Pattern

```python
_last_voice_message_time: Optional[float] = None
VOICE_MESSAGE_COOLDOWN_SECONDS = 60

def _check_cooldown() -> Optional[Dict[str, Any]]:
    global _last_voice_message_time
    if _last_voice_message_time:
        elapsed = time.time() - _last_voice_message_time
        if elapsed < VOICE_MESSAGE_COOLDOWN_SECONDS:
            remaining = int(VOICE_MESSAGE_COOLDOWN_SECONDS - elapsed)
            return {
                "status": "error",
                "error_code": "COOLDOWN",
                "error_message": f"Voice message on cooldown. Try again in {remaining} seconds.",
                "seconds_remaining": remaining
            }
    return None
```

### Learnings from Previous Story

**From Story 16-5 (Integration Testing & Documentation)**
- Status: in-progress
- Tool registration pattern established in server.py
- CLAUDE.md documentation patterns for HA tools
- Test structure in `mcp_server/tests/test_home_assistant_*.py`
- Coverage target >90%

**Interfaces to Reuse:**
- `HomeAssistantClient.call_service()` - may need adaptation for notify service
- `home_assistant_query_handler(domain="media_player")` - for device validation

[Source: stories/16-5-integration-testing-documentation.md#Dev-Notes]

### Project Structure Notes

**Files to Create/Modify:**
- `mcp_server/tools/home_assistant.py` - Add handler and tool definition
- `mcp_server/tools/__init__.py` - Export new tool
- `mcp_server/server.py` - Register tool
- `mcp_server/tests/test_voice_message_tool.py` - Unit tests
- `CLAUDE.md` - Documentation

**No Conflicts Expected:**
- Extends existing home_assistant.py module
- Follows established patterns from 16.1, 16.2

### References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.6]
- [Source: Amazon SSML Reference](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html)
- [Source: mcp_server/tools/home_assistant.py - HomeAssistantClient]

---

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/16-6-voice-message-tool-for-smart-home-speakers.context.xml

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

---

**Created:** 2026-01-19
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.6 - Voice Message Tool for Smart Home Speakers
