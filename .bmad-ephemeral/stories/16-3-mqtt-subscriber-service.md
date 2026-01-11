# Story 16.3: MQTT Subscriber Service

Status: ready-for-dev

## Story

**As a** user of Annie,
**I want** to receive proactive alerts from my Home Assistant automations via Telegram,
**So that** Annie can notify me about important home events like motion detection, door left open, or temperature changes without me asking.

**Epic:** Epic 16 - Home Assistant Integration
**Priority:** P1
**Estimated Effort:** 1.5 days
**Prerequisites:** Story 16.4 (Configuration for MQTT env vars)

## Acceptance Criteria

### AC #1: Connect to Mosquitto Broker on Startup
**Given** `HA_MQTT_BROKER` is configured
**When** the backend service starts
**Then** the MQTT subscriber connects to the broker at `HA_MQTT_BROKER:HA_MQTT_PORT`

**Testable:** Start service with valid broker config, verify connection in logs

---

### AC #2: Subscribe to Configured Topics
**Given** `HA_MQTT_TOPICS=annie/alerts/#`
**When** the MQTT client connects
**Then** it subscribes to all topics matching the pattern (wildcard # supported)

**Testable:** Verify subscription to "annie/alerts/#" in mock client calls

---

### AC #3: Parse JSON Messages
**Given** a message in JSON format: `{"title": "...", "message": "...", "entity_id": "...", "state": "..."}`
**When** the subscriber receives the message
**Then** it extracts title, message, and optional fields correctly

**Testable:** Send JSON message, verify parsed fields

---

### AC #4: Parse Plain Text Messages
**Given** a message in plain text format
**When** the subscriber receives the message
**Then** it uses the text as the message body with a default title

**Testable:** Send plain text, verify message body used

---

### AC #5: Forward Messages to Telegram
**Given** a parsed MQTT message and `HA_MQTT_ALERT_USER_ID` configured
**When** the message is received
**Then** it is forwarded to Telegram via `TelegramDelivery.send_message()`

**Format:**
```
**{title}**

{message}

_Topic: {topic}_
```

**Testable:** Mock TelegramDelivery, verify send_message called with correct format

---

### AC #6: Auto-Reconnect on Connection Loss
**Given** the MQTT connection is lost
**When** the subscriber detects disconnection
**Then** it attempts reconnection with 5-second backoff, max 30 seconds to reconnect

**Testable:** Simulate disconnect, verify reconnect attempts with backoff

---

### AC #7: Log All Received Messages
**Given** any MQTT message is received
**When** the message is processed
**Then** structured logs include: topic, message_type (json/text), forwarded (true/false)

**Testable:** Check logs for required fields after message processing

---

### AC #8: Graceful Shutdown on SIGTERM
**Given** the backend receives SIGTERM signal
**When** shutdown is initiated
**Then** the MQTT client disconnects cleanly before process exit

**Testable:** Send SIGTERM, verify clean disconnect in logs

---

### AC #9: Skip if MQTT Not Configured
**Given** `HA_MQTT_BROKER` is empty or not set
**When** the backend service starts
**Then** the MQTT subscriber is not started (no error, just skipped)

**Testable:** Start without HA_MQTT_BROKER, verify no MQTT connection attempted

---

### AC #10: Unit Tests with Mocked MQTT Client
**Given** the subscriber implementation
**When** unit tests are run
**Then** all test cases pass with >90% code coverage using mocked aiomqtt client

**Testable:** Run pytest with coverage, verify threshold met

---

## Tasks / Subtasks

### Task 1: Create MQTT Subscriber Class (AC: #1, #2, #6, #8, #9)
- [ ] Create `backend/api/mqtt_subscriber.py`
- [ ] Implement `MQTTSubscriber` class with aiomqtt client
- [ ] Add configuration loading: HA_MQTT_BROKER, HA_MQTT_PORT, HA_MQTT_USERNAME, HA_MQTT_PASSWORD, HA_MQTT_TOPICS
- [ ] Implement `start()` method to connect and subscribe
- [ ] Implement `stop()` method for graceful shutdown
- [ ] Add connection check: skip if HA_MQTT_BROKER not configured
- [ ] Implement reconnection with 5s backoff on disconnect
- [ ] Handle authentication if username/password provided

### Task 2: Implement Message Parsing (AC: #3, #4)
- [ ] Implement `parse_message(payload: bytes, topic: str) -> dict` method
- [ ] Try JSON parsing first: extract title, message, entity_id, state
- [ ] Fall back to plain text: use payload as message, default title
- [ ] Handle malformed JSON gracefully (treat as plain text)
- [ ] Validate required fields (at minimum: message content)

### Task 3: Implement Telegram Forwarding (AC: #5, #7)
- [ ] Import and use existing `TelegramDelivery` class
- [ ] Format message with Markdown:
  ```
  **{title}**

  {message}

  _Topic: {topic}_
  ```
- [ ] Call `TelegramDelivery.send_message(user_id, formatted_text)`
- [ ] Use `HA_MQTT_ALERT_USER_ID` as target user
- [ ] Add structured logging with topic, message_type, forwarded

### Task 4: Integrate with Backend Startup (AC: #8)
- [ ] Add MQTT subscriber to backend startup in `main.py`
- [ ] Register shutdown handler for SIGTERM
- [ ] Ensure subscriber runs as background task (asyncio)
- [ ] Handle startup gracefully if MQTT not configured

### Task 5: Write Unit Tests (AC: #10)
- [ ] Create `backend/tests/test_mqtt_subscriber.py`
- [ ] Test: `test_mqtt_connect()` - connection establishment
- [ ] Test: `test_mqtt_subscribe_topics()` - topic subscription
- [ ] Test: `test_mqtt_receive_json_message()` - JSON parsing
- [ ] Test: `test_mqtt_receive_plain_text()` - plain text handling
- [ ] Test: `test_mqtt_malformed_json()` - fallback to text
- [ ] Test: `test_mqtt_forward_to_telegram()` - Telegram delivery
- [ ] Test: `test_mqtt_reconnect_on_disconnect()` - reconnection logic
- [ ] Test: `test_mqtt_graceful_shutdown()` - SIGTERM handling
- [ ] Test: `test_mqtt_skip_when_not_configured()` - skip behavior
- [ ] Use `unittest.mock.AsyncMock` for aiomqtt mocking
- [ ] Verify >90% code coverage

---

## Dev Notes

### Implementation Approach

This is a NEW service in the backend (not MCP server):
- Location: `backend/api/mqtt_subscriber.py`
- Runs as async background task in FastAPI
- Uses aiomqtt library for async MQTT client
- Integrates with existing TelegramDelivery class

### aiomqtt Usage Pattern

```python
import aiomqtt

class MQTTSubscriber:
    def __init__(self, broker: str, port: int, topics: str, ...):
        self.broker = broker
        self.port = port
        self.topics = topics.split(",")  # Support multiple topics
        self.client = None
        self.running = False

    async def start(self):
        if not self.broker:
            logger.info("MQTT not configured, skipping subscriber")
            return

        self.running = True
        while self.running:
            try:
                async with aiomqtt.Client(
                    hostname=self.broker,
                    port=self.port,
                    username=self.username or None,
                    password=self.password or None,
                ) as client:
                    for topic in self.topics:
                        await client.subscribe(topic)

                    async for message in client.messages:
                        await self.handle_message(message)
            except aiomqtt.MqttError as e:
                if self.running:
                    logger.warning(f"MQTT disconnected: {e}, reconnecting in 5s")
                    await asyncio.sleep(5)

    async def stop(self):
        self.running = False
```

### Message Format

**Expected from Home Assistant automations:**
```json
{
    "title": "Motion Detected",
    "message": "Motion detected in backyard at 10:45 PM",
    "entity_id": "binary_sensor.backyard_motion",
    "state": "on"
}
```

**Telegram output:**
```
**Motion Detected**

Motion detected in backyard at 10:45 PM

_Topic: annie/alerts/motion_
```

### Configuration Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| HA_MQTT_BROKER | No | "" | Mosquitto broker hostname |
| HA_MQTT_PORT | No | 1883 | Broker port |
| HA_MQTT_USERNAME | No | "" | Optional auth username |
| HA_MQTT_PASSWORD | No | "" | Optional auth password (SENSITIVE) |
| HA_MQTT_TOPICS | No | "annie/alerts/#" | Topics to subscribe |
| HA_MQTT_ALERT_USER_ID | No | "" | Telegram user ID for alerts |

### Integration with Backend

```python
# In backend/api/main.py
from api.mqtt_subscriber import MQTTSubscriber

mqtt_subscriber = None

@app.on_event("startup")
async def startup():
    global mqtt_subscriber
    mqtt_subscriber = MQTTSubscriber(
        broker=config.HA_MQTT_BROKER,
        port=config.HA_MQTT_PORT,
        ...
    )
    asyncio.create_task(mqtt_subscriber.start())

@app.on_event("shutdown")
async def shutdown():
    if mqtt_subscriber:
        await mqtt_subscriber.stop()
```

### Project Structure Notes

- New file: `backend/api/mqtt_subscriber.py`
- New test file: `backend/tests/test_mqtt_subscriber.py`
- Dependency: `aiomqtt>=2.0.0` (added in Story 16.5)
- Uses: `TelegramDelivery` from existing proactive AI infrastructure

### Learnings from Previous Stories

**From Story 16-2 (Status: drafted)**
- Follow same structured logging pattern
- Use consistent error handling approach
- Config variables defined in Story 16.4

[Source: stories/16-2-home-assistant-control-tool.md]

### References

- [Source: docs/epics/epic-16-home-assistant-integration.md#Story-16.3]
- [Source: .bmad-ephemeral/stories/tech-spec-epic-16.md#MQTT-Alert-Flow]
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
**Epic:** Epic 16 - Home Assistant Integration
**Story:** 16.3 - MQTT Subscriber Service
