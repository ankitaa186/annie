# Story 13.5: Subconscious Gate

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.5
**Status:** ready-for-dev
**Estimated Effort:** 0.5 days

---

## User Story

**As a** user,
**I want** Annie to respect my boundaries and not spam me,
**So that** proactive messages remain helpful rather than annoying.

---

## Acceptance Criteria

### AC #1: Recent Contact Check
**Given** user messaged recently,
**When** gate checked,
**Then:**
- Blocks if user messaged < 1 hour ago
- Returns `GateResult(allowed=False, reason="recent_contact")`

### AC #2: Daily Limit Check
**Given** daily limit tracking,
**When** gate checked,
**Then:**
- Tracks count in Redis: `proactive:{user_id}:daily:{date}`
- TTL: 24 hours
- Blocks if count >= 5
- Returns `GateResult(allowed=False, reason="daily_limit")`

### AC #3: Quiet Hours Check
**Given** user timezone,
**When** gate checked,
**Then:**
- Checks user's local time
- Blocks if 22:00 - 08:00
- Returns `GateResult(allowed=False, reason="quiet_hours", defer_until=...)`

### AC #4: User Opt-Out Check
**Given** user preferences,
**When** gate checked,
**Then:**
- Checks `proactive_enabled` in user profile
- Blocks if explicitly disabled
- Returns `GateResult(allowed=False, reason="user_opt_out")`

### AC #5: Gate Result Model
**Given** gate check complete,
**Then** returns:
```python
GateResult(
    allowed: bool,
    reason: Optional[str],
    defer_until: Optional[datetime]
)
```

---

## Tasks

### Task 1: Create gate module structure
- [x] Create `backend/api/proactive/gate.py`
- [x] Define `GateResult` dataclass
- [x] Create `SubconsciousGate` class

### Task 2: Implement recent contact check
- [x] Check `session:{user_id}` for last_activity timestamp
- [x] Compare against 1 hour threshold
- [x] Return blocked result if too recent

### Task 3: Implement daily limit check
- [x] Read `proactive:{user_id}:daily:{date}` counter
- [x] Block if count >= 5
- [x] Created `increment_daily_count` method for post-send increment

### Task 4: Implement quiet hours check
- [x] Get user timezone from profile (default to UTC)
- [x] Calculate user's local time
- [x] Block if 22:00 - 08:00 local time
- [x] Calculate defer_until (next 08:00 local)

### Task 5: Implement user opt-out check
- [x] Fetch user profile via ProfileManager
- [x] Check `proactive_enabled` field in preferences
- [x] Block if explicitly False

### Task 6: Create main gate check function
- [x] `async def should_fire(trigger, user_id: str) -> GateResult`
- [x] Run all checks in fail-fast order
- [x] Return first blocking result or allowed=True
- [x] Log gate decisions for debugging with Langfuse tracing

---

## Dev Notes

### Technical Notes
- See Design Doc Section 12.1
- Increment daily count only on successful send (not on gate check)
- Gate checks should be fast (all Redis-based)

### Files to Create/Modify
- `backend/api/proactive/gate.py` (new)

### Check Order (fail-fast)
1. User opt-out (fastest - single Redis read)
2. Recent contact (single Redis read)
3. Daily limit (single Redis read)
4. Quiet hours (requires timezone calculation)

### Redis Keys
- `user:{user_id}:last_activity` - ISO timestamp
- `proactive:{user_id}:daily:{YYYY-MM-DD}` - integer counter
- Profile cache for timezone/preferences

---

## Dev Agent Record

### Context Reference
- Story Context: `.bmad-ephemeral/stories/13-5-subconscious-gate.context.xml`
- Design Doc: `docs/design/proactive-ai-architecture.md` (Section 12.1)
- Related Code: `backend/api/state.py` (session/last_activity), `backend/api/profile.py` (timezone/preferences)

### Implementation Notes

**Implementation Complete - 2025-12-25**

Created `/Users/ankit/dev/annie/backend/api/proactive/gate.py` with full subconscious gate implementation.

**Key Implementation Details:**

1. **GateResult Dataclass:**
   - Fields: `allowed`, `reason`, `defer_until`, `checks_passed`
   - `checks_passed` list tracks which checks succeeded (for debugging)
   - `__post_init__` ensures `checks_passed` is always a list

2. **SubconsciousGate Class:**
   - Fail-fast ordering: opt-out → recent contact → daily limit → quiet hours
   - Redis connection management with owned/shared pattern (same as ProfileManager)
   - Integrates with ProfileManager for user preferences and timezone
   - All checks wrapped in try/except for graceful error handling

3. **Check Methods:**
   - `_check_opt_out`: Reads `profile.preferences.proactive_enabled`, defaults to True (enabled)
   - `_check_recent_contact`: Reads `session:{user_id}` for last_activity, blocks if < 1 hour
   - `_check_daily_limit`: Reads `proactive:{user_id}:daily:{date}` counter, blocks if >= 5
   - `_check_quiet_hours`: Calculates user local time, blocks 22:00-08:00, returns defer_until

4. **should_fire Method:**
   - Main orchestration method with Langfuse `@observe` tracing
   - Runs all checks in order, returns first blocking result
   - Continues running checks even on failure (for debugging/logging)
   - Fail-safe: On exception, blocks to prevent spam

5. **increment_daily_count Method:**
   - Increments `proactive:{user_id}:daily:{date}` counter
   - Sets 24h TTL on first increment
   - Returns new count value
   - Called AFTER successful message delivery

6. **Error Handling Strategy:**
   - Opt-out errors: Fail open (allow) - preference errors shouldn't block
   - Recent contact errors: Fail open (allow) - session errors shouldn't block
   - Daily limit errors: Fail closed (block) - prevents spam on error
   - Quiet hours errors: Fail open (allow) - timezone errors shouldn't block
   - Overall gate errors: Fail closed (block) - safety first

7. **Timezone Handling:**
   - Uses pytz for timezone conversions
   - Reads timezone from `profile.basics.timezone`
   - Graceful fallback to UTC on invalid timezone
   - Calculates defer_until for next 8 AM in user's local time

8. **Logging:**
   - Structured logging with extra fields for debugging
   - DEBUG level for individual check results
   - INFO level for gate decisions (allow/block)
   - ERROR level for check failures
   - All logs include user_id, trigger_id, trigger_type

**Updated Files:**
- Created: `/Users/ankit/dev/annie/backend/api/proactive/gate.py`
- Updated: `/Users/ankit/dev/annie/backend/api/proactive/__init__.py` (added exports)

**Redis Key Patterns:**
- `session:{user_id}` - Contains last_activity timestamp (read-only)
- `proactive:{user_id}:daily:{YYYY-MM-DD}` - Daily counter (read during check, increment after send)
- `profile:{user_id}` - User profile cache (accessed via ProfileManager)

### Verification
- [x] Gate blocks when user messaged < 1 hour ago (recent contact check implemented)
- [x] Gate blocks after 5 proactive messages per day (daily limit check implemented)
- [x] Gate blocks during quiet hours (10pm - 8am local) (quiet hours check implemented)
- [x] Gate blocks when user has opted out (opt-out check implemented)
- [x] Gate allows when all checks pass (should_fire returns allowed=True)
- [x] defer_until correctly calculated for quiet hours (calculates next 8 AM in user timezone)
- [x] Timezone errors handled gracefully (fallback to UTC)
- [x] Missing profile handled gracefully (returns allowed by default)
- [x] Missing session handled gracefully (no last_activity = allow)
- [x] Logging provides sufficient debugging info (structured logging with extra fields)
- [x] Langfuse tracing enabled for observability (@observe decorators added)
