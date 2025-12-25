# Story 13.9: Telegram Delivery Integration

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.9
**Status:** ready-for-dev
**Estimated Effort:** 0.25 days

---

## User Story

**As a** system,
**I want** to send proactive messages to users via Telegram,
**So that** trigger messages reach users through their preferred channel.

---

## Acceptance Criteria

### AC #1: Delivery Function
**Given** message to send,
**When** deliver called,
**Then:**
- Looks up user's Telegram chat_id from Redis/profile
- Sends message via Telegram Bot API
- Returns message_id for tracking

### AC #2: Rate Limit Handling
**Given** Telegram rate limit hit,
**When** sending,
**Then:**
- Respects 429 responses
- Implements exponential backoff
- Retries up to 3 times

### AC #3: Error Handling
**Given** delivery failure,
**When** exception occurs,
**Then:**
- Returns None for message_id
- Logs error with context
- Does not crash worker

---

## Tasks

### Task 1: Create delivery module
- [x] Create `backend/api/proactive/telegram_delivery.py`
- [x] Define `DeliveryResult` dataclass

### Task 2: Implement chat_id lookup
- [x] Get chat_id from user_id (they are the same for Telegram)
- [x] Handle invalid chat_id gracefully

### Task 3: Implement message sending
- [x] Create `send_proactive_message(user_id: str, message: str, trigger_id: str) -> DeliveryResult`
- [x] Use Telegram Bot API to send message
- [x] Return message_id on success

### Task 4: Implement rate limit handling
- [x] Detect 429 Too Many Requests (RetryAfter exception)
- [x] Implement exponential backoff with retry_after timing
- [x] Retry up to 3 times

### Task 5: Add error handling
- [x] Wrap in try/except with multiple exception types
- [x] Log errors with user_id, trigger_id, and message length
- [x] Return DeliveryResult with success=False on failure

---

## Dev Notes

### Technical Notes
- Reuse existing Telegram client infrastructure
- May need to add chat_id lookup if not already available
- Proactive messages use same bot as regular chat

### Files to Create/Modify
- `backend/api/proactive/telegram_delivery.py` (created)
- `backend/api/proactive/__init__.py` (updated)
- `backend/requirements.txt` (updated)

### Telegram Rate Limits
- 30 messages per second to different chats
- 1 message per second to same chat
- Use exponential backoff on 429

### DeliveryResult Structure
```python
@dataclass
class DeliveryResult:
    success: bool
    message_id: Optional[str]  # String (Telegram message IDs are ints, stored as strings)
    error: Optional[str]
    delivery_ms: int  # Delivery time in milliseconds
```

---

## Dev Agent Record

### Context Reference
- Context file: `.bmad-ephemeral/stories/13-9-telegram-delivery-integration.context.xml`
- Generated: 2025-12-24
- Key finding: user_id in system IS Telegram chat_id (no separate lookup needed)

### Implementation Notes

**Implemented Components:**

1. **DeliveryResult Dataclass** (`backend/api/proactive/telegram_delivery.py`):
   - `success: bool` - Delivery status
   - `message_id: Optional[str]` - Telegram message ID (string)
   - `error: Optional[str]` - Error message if failed
   - `delivery_ms: int` - Delivery time in milliseconds

2. **TelegramDelivery Class**:
   - `__init__(bot_token, redis_client)` - Initialize with Telegram bot token and Redis client
   - `send_proactive_message(user_id, message, trigger_id)` - Main delivery method
   - Async context manager support (`__aenter__`, `__aexit__`)
   - Rate limit handling with exponential backoff (max 3 retries)
   - Comprehensive error handling (BadRequest, TelegramError, generic exceptions)
   - Langfuse tracing with `@observe` decorator

3. **record_proactive_message Function**:
   - Stores message metadata in Redis for feedback tracking (Story 13.10)
   - Key: `proactive_message:{user_id}:last`
   - Value: JSON with `trigger_id`, `message_id`, `sent_at`
   - TTL: 2 hours (feedback window)
   - Langfuse tracing with `@observe` decorator

**Key Design Decisions:**

1. **Direct Bot API Integration**: Used `python-telegram-bot` library's `Bot` class directly, allowing the backend to send messages independently from the telegram-bot service's polling loop.

2. **user_id = chat_id**: As discovered in context analysis, our system's `user_id` IS the Telegram `chat_id`. The code converts string `user_id` to int for Telegram API calls.

3. **Graceful Degradation**: If recording the proactive message fails, the delivery still succeeds. This ensures delivery reliability.

4. **Performance Tracking**: All operations include timing metrics (`delivery_ms`) for observability.

5. **Structured Logging**: All log events include structured fields (`user_id`, `trigger_id`, `event`, `delivery_ms`) for easy filtering and analysis.

**Dependencies Added:**
- `python-telegram-bot==20.7` to `backend/requirements.txt`

**Integration Points:**
- Exports added to `backend/api/proactive/__init__.py`
- Ready for Wake-Up Agent (Story 13.6) to call
- Prepares for Feedback Handler (Story 13.10) via Redis tracking

### Verification
- [x] DeliveryResult dataclass created with all required fields
- [x] TelegramDelivery class implements send_proactive_message method
- [x] Rate limits handled with RetryAfter exception and backoff
- [x] Delivery failures logged with full context and don't crash
- [x] Message_id returned on success as string
- [x] Redis tracking implemented for feedback detection
- [x] Langfuse tracing added for observability
- [x] Input validation for user_id, message, and trigger_id
- [x] Performance timing tracked with delivery_ms
