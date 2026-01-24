# Story 16.3: Intelligent Event Processing System

Status: ready-for-dev

## Story

**As a** user of Annie,
**I want** external events (starting with Home Assistant) intelligently processed and aggregated,
**So that** I receive only meaningful notifications, Annie can act on my behalf, and I can respond conversationally.

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P1
**Estimated Effort:** 3 days (revised from 1.5 days)
**Prerequisites:** Story 16.4 (Configuration for MQTT env vars), Epic 13 (Proactive AI)

## Scope Change Notice

> **Original Scope:** Simple MQTT pass-through to Telegram
> **Revised Scope:** Intelligent event processing with aggregation, LLM decision-making, and two-way conversation
>
> **Rationale:** Party mode design session (2025-01-19) determined that simple pass-through would spam the user. Events need intelligent filtering, aggregation, and Annie should decide what's noteworthy.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│              GENERIC EVENT PROCESSING SYSTEM                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
│  │ MQTT/HA     │  │ Future:     │  │ Future:     │                 │
│  │ Events      │  │ Webhooks    │  │ Email/IMAP  │                 │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                 │
│         │                │                │                         │
│         └────────────────┼────────────────┘                         │
│                          ↓                                          │
│         ┌────────────────────────────────┐                         │
│         │ UNIFIED EVENT BUFFER (Redis)   │  ← Zero LLM cost        │
│         │ Key: events:{source}:{window}  │                         │
│         │ Rolling window aggregation     │                         │
│         └────────────────────────────────┘                         │
│                          ↓                                          │
│         ┌────────────────────────────────┐                         │
│         │ EVENT PROCESSOR (1/min max)    │  ← Rate limited         │
│         │ - Source-agnostic bundling     │                         │
│         │ - Feeds proactive system       │                         │
│         └────────────────────────────────┘                         │
│                          ↓                                          │
│         ┌────────────────────────────────┐                         │
│         │ EXISTING PROACTIVE SYSTEM      │  ← LLM cost here        │
│         │ - Subconscious gate            │                         │
│         │ - Wake-up agent decides        │                         │
│         │ - IGNORE / NOTIFY / ACT        │                         │
│         └────────────────────────────────┘                         │
│                          ↓                                          │
│         ┌────────────────────────────────┐                         │
│         │ DELIVERY + USER RESPONSE       │                         │
│         │ - Telegram notification        │                         │
│         │ - User reply → /api/chat       │                         │
│         └────────────────────────────────┘                         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Event format to LLM | Raw list | Let LLM interpret, simpler code |
| Aggregation | Redis rolling window, 1 msg/min cap | Cost control, prevent spam |
| Learning | Deferred to future | Simplify v1 |
| Autonomous actions | Always notify user | Trust/safety principle |
| User replies | Via `/api/chat` | Reuse existing infrastructure |
| Infrastructure | Extend Epic 13 proactive system | Don't rebuild |
| Event schema | Generic (source-agnostic) | HA is first, others can plug in |

### LLM Decision Options

| Decision | When to Use | User Sees |
|----------|-------------|-----------|
| `IGNORE` | Routine, noise, expected | Nothing |
| `NOTIFY` | Noteworthy, user should know | Telegram message |
| `ACT_AND_NOTIFY` | Obvious action + inform user | Action taken + Telegram message |

**Note:** No silent actions. Annie ALWAYS notifies when she acts autonomously.

---

## Acceptance Criteria

### AC #1: MQTT Subscriber Connects and Buffers Events
**Given** `HA_MQTT_BROKER` is configured
**When** the backend service starts
**Then** the MQTT subscriber connects and writes events to Redis buffer

**Testable:** Start service, publish MQTT message, verify event in Redis buffer

---

### AC #2: Events Aggregated in Rolling Window
**Given** multiple events arrive within 60 seconds
**When** the event processor runs
**Then** events are bundled by source and time window

**Testable:** Send 10 events in 30s, verify single bundle created

---

### AC #3: Rate-Limited Processing (Max 1/min)
**Given** events are in the Redis buffer
**When** the processor checks for work
**Then** it processes at most once per minute regardless of event volume

**Testable:** Send 100 events, verify only 1-2 processing cycles occur

---

### AC #4: Event Bundle Fed to Proactive System
**Given** an aggregated event bundle
**When** the processor runs
**Then** the bundle is passed to the wake-up agent via the existing proactive system

**Testable:** Mock wake-up agent, verify it receives event bundle

---

### AC #5: LLM Decides IGNORE / NOTIFY / ACT_AND_NOTIFY
**Given** an event bundle is processed by the wake-up agent
**When** the LLM evaluates the events
**Then** it returns one of: IGNORE, NOTIFY, or ACT_AND_NOTIFY

**Testable:** Send various event patterns, verify appropriate decisions

---

### AC #6: Notifications Sent via Telegram
**Given** LLM decides NOTIFY or ACT_AND_NOTIFY
**When** the decision is executed
**Then** a Telegram message is sent to `HA_MQTT_ALERT_USER_ID`

**Testable:** Mock Telegram, verify message sent with event context

---

### AC #7: Actions Executed via HA Control Tool
**Given** LLM decides ACT_AND_NOTIFY
**When** the decision is executed
**Then** `home_assistant_control` tool is called AND user is notified

**Testable:** Verify both HA API call and Telegram message

---

### AC #8: User Replies Handled via /api/chat
**Given** user receives a notification and replies
**When** the reply is received
**Then** it flows through normal `/api/chat` with full Annie context

**Testable:** Send reply, verify chat endpoint processes it with HA tools available

---

### AC #9: Existing Triggers Unaffected (Backward Compatibility)
**Given** existing user-defined triggers from Epic 13
**When** the event processing system is added
**Then** all existing triggers continue to work unchanged

**Testable:** Regression tests for time-based and condition triggers

---

### AC #10: Generic Event Schema
**Given** an event from any source
**When** it is written to the buffer
**Then** it conforms to the generic event schema (source, event_type, timestamp, payload)

**Testable:** Verify schema validation for HA events

---

### AC #11: Skip if MQTT Not Configured
**Given** `HA_MQTT_BROKER` is empty or not set
**When** the backend service starts
**Then** MQTT subscriber is not started (no error, just skipped)

**Testable:** Start without config, verify no connection attempt

---

### AC #12: Auto-Reconnect on MQTT Disconnect
**Given** the MQTT connection is lost
**When** the subscriber detects disconnection
**Then** it attempts reconnection with 5-second backoff

**Testable:** Simulate disconnect, verify reconnect attempts

---

### AC #13: Graceful Shutdown
**Given** the backend receives SIGTERM
**When** shutdown is initiated
**Then** MQTT client and event processor stop cleanly

**Testable:** Send SIGTERM, verify clean shutdown in logs

---

## Tasks / Subtasks

### Task 1: Create Generic Event Schema and Buffer (AC: #2, #10)
- [ ] Create `backend/api/events/schema.py`
- [ ] Define `Event` dataclass:
  ```python
  @dataclass
  class Event:
      source: str          # "ha", "webhook", "email", etc.
      event_type: str      # Source-specific type
      timestamp: datetime
      payload: dict        # Source-specific data
  ```
- [ ] Create `backend/api/events/buffer.py`
- [ ] Implement `EventBuffer` class with Redis backend
- [ ] Key pattern: `events:{source}:{minute_bucket}`
- [ ] Methods: `push(event)`, `pop_bundle(source)`, `get_pending_sources()`
- [ ] TTL: 5 minutes for auto-cleanup

### Task 2: Create MQTT Subscriber (AC: #1, #11, #12, #13)
- [ ] Create `backend/api/events/mqtt_subscriber.py`
- [ ] Implement `MQTTSubscriber` class with aiomqtt
- [ ] Parse MQTT messages (JSON or plain text)
- [ ] Convert to generic `Event` schema with `source="ha"`
- [ ] Push events to `EventBuffer`
- [ ] Auto-reconnect with 5s backoff
- [ ] Graceful shutdown support

### Task 3: Create Event Processor (AC: #3, #4)
- [ ] Create `backend/api/events/processor.py`
- [ ] Implement `EventProcessor` class
- [ ] Run as async background task (every 60s)
- [ ] Pop event bundles from buffer
- [ ] Format bundle as raw list for LLM:
  ```json
  {
    "event_type": "ha_event_bundle",
    "window": "2025-01-19T10:00:00Z to 10:01:00Z",
    "events": [
      {"entity_id": "binary_sensor.motion", "state": "on", "count": 7},
      {"entity_id": "light.porch", "state": "on", "count": 1}
    ]
  }
  ```
- [ ] Pass bundle to proactive system

### Task 4: Integrate with Proactive System (AC: #4, #5, #6, #7, #9)
- [ ] Modify `backend/api/proactive/system_prompt_builder.py`
- [ ] Add HA event processing instructions to wake-up prompt:
  ```markdown
  ## Home Assistant Event Processing

  You have received a bundle of Home Assistant events.
  Analyze and decide:

  1. **IGNORE** - Not noteworthy, stay silent
  2. **NOTIFY** - Tell user about this
  3. **ACT_AND_NOTIFY** - Take action AND tell user

  Consider: time of day, event frequency, user context.
  NEVER act without notifying the user.
  ```
- [ ] Modify `backend/api/proactive/wake_up_agent.py`
- [ ] Add `process_event_bundle()` method (parallel to existing trigger path)
- [ ] Handle LLM response: IGNORE / NOTIFY / ACT_AND_NOTIFY
- [ ] For ACT_AND_NOTIFY: call `home_assistant_control` tool
- [ ] Ensure existing trigger processing unchanged

### Task 5: Integrate with Backend Startup (AC: #13)
- [ ] Modify `backend/api/main.py`
- [ ] Start MQTT subscriber on startup (if configured)
- [ ] Start event processor on startup
- [ ] Register shutdown handlers for both
- [ ] Handle graceful degradation if MQTT not configured

### Task 6: Write Unit Tests (AC: all)
- [ ] Create `backend/tests/events/test_schema.py`
- [ ] Create `backend/tests/events/test_buffer.py`
- [ ] Create `backend/tests/events/test_mqtt_subscriber.py`
- [ ] Create `backend/tests/events/test_processor.py`
- [ ] Test cases:
  - Event schema validation
  - Buffer push/pop/aggregation
  - MQTT connect/disconnect/reconnect
  - Rate limiting (1/min max)
  - LLM decision handling (IGNORE/NOTIFY/ACT_AND_NOTIFY)
  - Telegram delivery
  - HA control execution
- [ ] Verify >90% code coverage

### Task 7: Write Regression Tests (AC: #9)
- [ ] Create `backend/tests/test_proactive_regression.py`
- [ ] Test existing triggers still work:
  - Time-based triggers
  - Condition-based triggers
  - Trigger CRUD operations
  - Feedback loop
- [ ] Ensure event system doesn't break existing functionality

### Task 8: Add Dependencies
- [ ] Add `aiomqtt>=2.0.0` to `backend/requirements.txt`
- [ ] Verify Docker build succeeds

---

## Dev Notes

### Generic Event Schema

The system is designed to be **source-agnostic**. HA/MQTT is the first implementation, but the architecture supports future event sources:

```python
# HA Event Example
Event(
    source="ha",
    event_type="state_change",
    timestamp=datetime.now(),
    payload={
        "entity_id": "binary_sensor.backyard_motion",
        "state": "on",
        "old_state": "off",
        "attributes": {"friendly_name": "Backyard Motion"}
    }
)

# Future: Webhook Event
Event(
    source="webhook",
    event_type="github_pr",
    timestamp=datetime.now(),
    payload={
        "repo": "annie",
        "action": "opened",
        "pr_number": 42
    }
)
```

### Redis Buffer Pattern

```
Key: events:ha:202501191000  (source:minute_bucket)
Value: JSON array of events
TTL: 300 seconds (5 minutes)

Processor pops all events for current-1 minute bucket
(ensures we have complete window before processing)
```

### Proactive System Integration

The event processor feeds into the **existing** proactive system from Epic 13:

```
MQTT Event → EventBuffer → EventProcessor → wake_up_agent.process_event_bundle()
                                                    ↓
User Trigger → condition_evaluators → wake_up_agent.process_trigger()  [unchanged]
```

These are **parallel paths**. The event system does NOT replace or modify trigger handling.

### LLM Cost Estimation

- Events: 100-200/hr
- After aggregation: ~60 bundles/hr max (1/min)
- After relevance filtering: ~10-20 LLM calls/hr expected
- Cost: Minimal (short prompts, fast decisions)

### Configuration Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| HA_MQTT_BROKER | No | "" | Mosquitto broker hostname |
| HA_MQTT_PORT | No | 1883 | Broker port |
| HA_MQTT_USERNAME | No | "" | Optional auth username |
| HA_MQTT_PASSWORD | No | "" | Optional auth password (SENSITIVE) |
| HA_MQTT_TOPICS | No | "annie/alerts/#" | Topics to subscribe |
| HA_MQTT_ALERT_USER_ID | No | "" | Telegram user ID for alerts |
| EVENT_PROCESS_INTERVAL | No | 60 | Seconds between processing cycles |

### File Structure

```
backend/api/events/
├── __init__.py
├── schema.py           # Generic Event dataclass
├── buffer.py           # Redis-backed EventBuffer
├── mqtt_subscriber.py  # MQTT → EventBuffer
└── processor.py        # EventBuffer → Proactive System

backend/api/proactive/
├── system_prompt_builder.py  # MODIFY: Add event instructions
└── wake_up_agent.py          # MODIFY: Add process_event_bundle()

backend/tests/events/
├── test_schema.py
├── test_buffer.py
├── test_mqtt_subscriber.py
└── test_processor.py

backend/tests/
└── test_proactive_regression.py  # NEW: Ensure triggers still work
```

### Backward Compatibility Checklist

- [ ] Existing triggers fire correctly
- [ ] Trigger CRUD via MCP tools works
- [ ] Feedback handler captures responses
- [ ] Telegram delivery unchanged
- [ ] `/api/chat` unchanged
- [ ] No new required environment variables (all optional)

---

## Test Scenarios

| Scenario | Input | Expected Decision | Expected Output |
|----------|-------|-------------------|-----------------|
| Single motion event | 1 motion | IGNORE | Nothing |
| Repeated motion (7x) | 7 motion same sensor | NOTIFY | "Activity detected in backyard" |
| Door opened late night | door open @ 2am | NOTIFY | "Front door opened at 2am" |
| Motion + context | motion @ front + expecting package | ACT_AND_NOTIFY | Turn on porch light + notify |
| Temperature reading | temp: 72°F | IGNORE | Nothing |
| Temperature spike | temp: 95°F | NOTIFY | "Unusual temperature spike" |
| Light turned on | light.porch → on | IGNORE | Nothing (routine) |
| Smoke detector | smoke alarm → on | NOTIFY | Immediate alert |

---

## References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.3]
- [Source: Epic 13 Proactive AI Implementation]
- [Party Mode Design Session: 2025-01-19]
- [aiomqtt Documentation](https://sbtinstruments.github.io/aiomqtt/)

---

## Dev Agent Record

### Context Reference

- `.bmad-ephemeral/stories/16-3-mqtt-subscriber-service.context.xml`

### Agent Model Used

{{agent_model_name_version}}

### Debug Log References

### Completion Notes List

### File List

---

**Created:** 2025-01-10
**Revised:** 2025-01-19 (Party Mode Design Session)
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.3 - Intelligent Event Processing System
