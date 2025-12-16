# Story 11.6: Pending Message Slot

Status: done

## Story

As a user,
I want to send follow-up messages while Annie is working,
so that I can add context without waiting for the response.

## Acceptance Criteria

1. **AC #1: Processing Flag**
   - Redis key `processing:{user_id}` indicates active request
   - Set to "1" on request start, deleted on completion
   - TTL: 3 minutes (safety - prevents stuck state)
   - Atomic operations for concurrency safety

2. **AC #2: Single Pending Slot**
   - Redis key `pending_message:{user_id}` stores pending message(s)
   - New messages append to existing pending (newline separated)
   - NOT a queue - single concatenated string
   - TTL: 5 minutes (safety)
   - Max size limit: 4000 chars (prevent abuse)

3. **AC #3: Status Update for Pending**
   - First pending message: "📝 Got it - will handle after current request..."
   - Subsequent: "📝 Added to pending ({n} follow-up messages)..."
   - Status shown as Telegram reply or edited message

4. **AC #4: Auto-Pickup on Completion**
   - After response completes, check for pending message
   - If pending exists: clear pending, process as new request
   - LLM sees natural chat history flow (previous messages + responses + pending)
   - Recursive handling if more messages arrive during pending processing

5. **AC #5: Concurrent Request Safety**
   - Only one active processing per user at a time
   - Pending slot prevents race conditions
   - Redis atomic operations (SETNX, GET+DELETE) for safety

## Tasks / Subtasks

- [x] Task 1: Implement processing flag (AC: #1, #5)
  - [x] Create Redis key `processing:{user_id}` with SETNX
  - [x] Set TTL of 180 seconds (3 minutes)
  - [x] Delete on request completion (success or error)
  - [x] Check flag before starting new request

- [x] Task 2: Implement pending message storage (AC: #2)
  - [x] Create/append to Redis key `pending_message:{user_id}`
  - [x] Newline-separate multiple messages
  - [x] Set TTL of 300 seconds (5 minutes)
  - [x] Implement max size check (4000 chars)

- [x] Task 3: Implement pending message status (AC: #3)
  - [x] Count pending messages (split by newline)
  - [x] Send appropriate status message
  - [x] Track pending status message_id for updates

- [x] Task 4: Implement auto-pickup logic (AC: #4)
  - [x] After response completion, check for pending
  - [x] Atomically GET and DELETE pending message
  - [x] Recursively call message handler with pending content
  - [x] Ensure chat history includes prior exchange

- [x] Task 5: Implement concurrency safety (AC: #5)
  - [x] Use Redis SETNX for processing flag (atomic set-if-not-exists)
  - [x] Use Redis transaction for pending GET+DELETE
  - [x] Handle edge cases (flag expired but still processing)

- [x] Task 6: Write integration tests
  - [x] Test single message processing (no pending)
  - [x] Test message during processing (creates pending)
  - [x] Test multiple messages during processing (appends)
  - [x] Test auto-pickup after completion
  - [x] Test concurrent message handling

## Dev Notes

### Redis Key Schema

```
processing:{user_id}     = "1"           TTL: 180s
pending_message:{user_id} = "msg1\nmsg2"  TTL: 300s
```

### Implementation Flow

```python
# telegram_bot/bot.py

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message_text = update.message.text
    redis = get_redis_client()

    # Check if already processing
    if await redis.get(f"processing:{user_id}"):
        # Append to pending
        await append_pending_message(redis, user_id, message_text)
        count = await count_pending_messages(redis, user_id)
        if count == 1:
            await update.message.reply_text("📝 Got it - will handle after current request...")
        else:
            # Update existing pending indicator
            await update.message.reply_text(f"📝 Added to pending ({count} follow-up messages)...")
        return

    # Set processing flag
    await redis.set(f"processing:{user_id}", "1", ex=180, nx=True)

    try:
        # Process message normally
        await process_and_stream_response(user_id, message_text, update, context)
    finally:
        # Clear processing flag
        await redis.delete(f"processing:{user_id}")

        # Check for pending messages
        pending = await get_and_clear_pending(redis, user_id)
        if pending:
            # Process pending messages (recursive call)
            await handle_pending_messages(user_id, pending, update, context)


async def append_pending_message(redis, user_id: str, message: str):
    key = f"pending_message:{user_id}"
    existing = await redis.get(key) or ""
    if existing:
        combined = f"{existing}\n{message}"
    else:
        combined = message

    # Max size check
    if len(combined) > 4000:
        combined = combined[-4000:]  # Keep most recent

    await redis.set(key, combined, ex=300)


async def count_pending_messages(redis, user_id: str) -> int:
    pending = await redis.get(f"pending_message:{user_id}")
    if not pending:
        return 0
    return len(pending.split("\n"))


async def get_and_clear_pending(redis, user_id: str) -> Optional[str]:
    key = f"pending_message:{user_id}"
    # Atomic GET and DELETE
    pipe = redis.pipeline()
    pipe.get(key)
    pipe.delete(key)
    results = await pipe.execute()
    return results[0]  # The GET result


async def handle_pending_messages(user_id: str, pending: str, update, context):
    # Set processing flag again
    redis = get_redis_client()
    await redis.set(f"processing:{user_id}", "1", ex=180)

    try:
        # Send status
        status_msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="🔄 Annie is thinking..."
        )
        # Process pending (LLM will see full chat history + pending messages)
        await process_and_stream_response(user_id, pending, update, context, status_msg)
    finally:
        await redis.delete(f"processing:{user_id}")
        # Check for more pending (recursive)
        more_pending = await get_and_clear_pending(redis, user_id)
        if more_pending:
            await handle_pending_messages(user_id, more_pending, update, context)
```

### LLM Context with Pending Messages

When processing pending messages, the LLM sees natural conversation:

```
[Chat History]
User: "What's my portfolio?"
Assistant: "You have 3 holdings worth $15,420..."

[Current Request - from pending]
User: "Also check AAPL
And GOOGL"
```

The LLM naturally handles multi-line user input as a continuation.

### Edge Cases

1. **Processing flag expires during long request**: Set generous TTL (3 min), re-check before clearing
2. **User sends 100 messages**: Max size limit (4000 chars) truncates oldest
3. **Network failure during pending pickup**: TTL ensures pending messages expire
4. **Concurrent requests from same user**: SETNX ensures only one processes

### Project Structure Notes

- Modify: `telegram_bot/bot.py` (main message handler)
- Uses: Existing Redis client
- Independent of Stories 11.1-11.5 (can be implemented in parallel)

### Dependencies

- None - this story is independent and can be developed in parallel with other Epic 11 stories

### References

- [Source: docs/epics/epic-11-realtime-status-updates.md#Story-11.6]
- [Source: telegram_bot/bot.py] - Message handling
- [Source: backend/api/config.py] - Redis configuration

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-16 | Story drafted from Epic 11 brainstorm | SM (Bob) |

## Dev Agent Record

### Context Reference

- **Story Context XML**: `/home/ankit/dev/annie/.bmad-ephemeral/stories/11-6-pending-message-slot-context.xml`
  - Generated: 2025-12-16
  - Contains: Technical implementation details, Redis patterns, code snippets, concurrency safety analysis

### Agent Model Used

claude-sonnet-4-5-20250929 (Sonnet 4.5)

### Debug Log References

No debug logs generated during implementation.

### Completion Notes List

1. **Redis Client Integration**
   - Added Redis client initialization using redis.asyncio
   - Follows same pattern as backend StateManager
   - Global redis_client initialized on first use
   - Connection configured with decode_responses=True for string operations
   - 5-second socket timeouts for reliability

2. **Processing Flag Implementation**
   - Redis key: `processing:{user_id}` with value "1"
   - TTL: 180 seconds (3 minutes) - safety net for stuck states
   - Atomic operations using SETNX (set-if-not-exists) flag
   - Prevents concurrent processing for same user
   - Cleared on both success and error paths
   - Graceful degradation if Redis unavailable

3. **Pending Message Slot**
   - Redis key: `pending_message:{user_id}` stores concatenated messages
   - Multiple messages separated by newline (\n)
   - TTL: 300 seconds (5 minutes) - prevents indefinite queueing
   - Max size: 4000 characters (keeps most recent if exceeded)
   - NOT a queue - single slot that accumulates messages

4. **Status Messages**
   - First pending: "📝 Got it - will handle after current request..."
   - Subsequent: "📝 Added to pending (n follow-up messages)..."
   - Count calculated by splitting on newline
   - Sent via message.reply_text()

5. **Auto-Pickup Logic**
   - After stream completion, atomically GET and DELETE pending
   - Uses Redis pipeline for atomic operation
   - Recursive call to handle_pending_messages()
   - Continues checking for more pending after each completion
   - Works on both success and error paths

6. **Recursive Pending Handler**
   - New function: handle_pending_messages()
   - Sets processing flag before processing
   - Creates status message: "🔄 Annie is thinking..."
   - Sends pending message to backend as new request
   - Uses MockMessage wrapper to edit status message
   - Recursively checks for more pending after completion

7. **Voice Message Handling**
   - Voice messages cannot be queued (design decision)
   - Processing flag checked before voice processing
   - If busy, user informed: "Voice messages can't be queued - please wait"
   - After voice processing, text pending messages are picked up
   - Same flag clearing and pending check as text messages

8. **Concurrency Safety**
   - SETNX ensures only one processing flag set per user
   - Pipeline ensures atomic GET+DELETE of pending
   - Race condition handling: re-queue if flag set between check and set
   - User-scoped keys isolate different users
   - TTLs prevent indefinite blocking

9. **Error Handling**
   - Redis errors logged but don't block message processing
   - Graceful degradation if Redis unavailable
   - Processing flag cleared in all error paths
   - Pending messages still checked after errors
   - Silent failures on cleanup operations

10. **Testing**
    - Comprehensive test suite: test_pending_messages.py
    - 15 integration tests covering all acceptance criteria
    - Tests atomic operations, TTL expiry, max size, concurrency
    - Mocked dependencies for handle_pending_messages testing
    - Tests use separate Redis database (db=15)

11. **Implementation Details**
    - Total lines added: ~500 lines (including tests)
    - No breaking changes - backward compatible
    - No backend modifications required
    - All logic in telegram_bot service
    - Follows existing patterns (StateManager, ProfileManager)

12. **Edge Cases Handled**
    - Processing flag expires during long request (TTL safety net)
    - User sends many messages (max size truncation)
    - Redis connection failures (graceful degradation)
    - Messages arrive during pending processing (re-queue)
    - Race conditions between check and set (SETNX handles)

### File List

**Modified Files:**
- `/home/ankit/dev/annie/telegram_bot/handlers/message.py`
  - Added Redis client import and initialization
  - Added helper functions: append_pending_message, count_pending_messages, get_and_clear_pending, get_redis_client
  - Added handle_pending_messages() for recursive pending processing
  - Modified handle_message() to check processing flag and handle pending
  - Modified handle_voice_message() to check processing flag and handle pending
  - Added processing flag management (set, check, clear) in both handlers
  - Added status message sending for pending messages
  - Added auto-pickup logic after stream completion
  - Lines modified: ~350 lines (additions and modifications)

- `/home/ankit/dev/annie/telegram_bot/requirements.txt`
  - Added pytest>=8.0.0 for testing
  - Added pytest-asyncio>=0.23.0 for async test support
  - Redis already present (redis==5.0.0)

**New Files:**
- `/home/ankit/dev/annie/telegram_bot/tests/__init__.py`
  - Tests module initialization

- `/home/ankit/dev/annie/telegram_bot/tests/test_pending_messages.py`
  - Comprehensive integration tests (15 test cases)
  - Tests all acceptance criteria
  - Tests edge cases and concurrency
  - Tests atomic operations and TTL behavior
  - Lines: ~450 lines

**Total Changes:**
- 2 files modified
- 2 files created
- ~800 lines of code added (including tests and documentation)
