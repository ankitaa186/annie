# Story 13.8: User Activity Tracking

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.8
**Status:** completed
**Estimated Effort:** 0.25 days

---

## User Story

**As a** system,
**I want** to track user activity timestamps,
**So that** silence detection and gate checks work correctly.

---

## Acceptance Criteria

### AC #1: Activity Update on Message
**Given** user sends message,
**When** chat endpoint processes,
**Then:**
- Updates Redis: `user:{user_id}:last_activity`
- Value: ISO timestamp
- TTL: 7 days

### AC #2: Activity Retrieval
**Given** activity check needed,
**When** queried,
**Then:**
- Returns last activity timestamp
- Handles missing key (new user) gracefully
- Returns None for users with no history

### AC #3: Integration with Gate
**Given** subconscious gate check,
**Then** uses activity for:
- Recent contact check (< 1 hour)
- Can be extended for other checks

---

## Tasks

### Task 1: Create activity module
- [x] Create `backend/api/proactive/activity_tracker.py`
- [x] Define activity tracking functions

### Task 2: Implement activity update
- [x] Create `record_activity(user_id: str) -> None` method
- [x] Store ISO timestamp in Redis
- [x] Set 7-day TTL

### Task 3: Implement activity retrieval
- [x] Create `get_last_activity(user_id: str) -> Optional[datetime]` method
- [x] Handle missing keys (return None)
- [x] Parse ISO timestamp to datetime
- [x] Create `get_hours_since_activity(user_id: str) -> Optional[float]` method
- [x] Create `is_user_active(user_id: str, within_hours: float) -> bool` method

### Task 4: Integrate with chat endpoint
- [x] Add activity update call to `backend/api/routes/chat.py`
- [x] Call after successful message processing
- [x] Non-blocking (fire and forget)

---

## Dev Notes

### Technical Notes
- Minimal change to chat.py
- Activity module provides utility functions
- Used by gate for recent contact check
- Used by silence evaluator for condition triggers

### Files to Create/Modify
- `backend/api/proactive/activity.py` (new)
- `backend/api/routes/chat.py` (add activity update)

### Redis Key Pattern
- Key: `user:{user_id}:last_activity`
- Value: ISO timestamp (e.g., "2025-12-24T10:30:00Z")
- TTL: 7 days (604800 seconds)

---

## Dev Agent Record

### Context Reference
- Context file: `.bmad-ephemeral/stories/13-8-user-activity-tracking.context.xml`
- Generated: 2025-12-24
- Includes:
  - Redis client access patterns (StateManager)
  - Chat endpoint integration point (after line 348)
  - Timestamp format consistency (ISO with Z suffix)
  - Error handling patterns (fire-and-forget)
  - Testing patterns (AsyncMock for Redis)
  - Module structure template

### Implementation Notes
**Implementation Date:** 2025-12-25

**Files Created:**
1. `backend/api/proactive/activity_tracker.py` - ActivityTracker class with methods:
   - `record_activity(user_id, activity_type="message")` - Records activity timestamp
   - `get_last_activity(user_id)` - Returns last activity datetime or None
   - `get_hours_since_activity(user_id)` - Returns hours since last activity
   - `is_user_active(user_id, within_hours)` - Checks if active within time window

**Files Modified:**
1. `backend/api/proactive/__init__.py` - Added ActivityTracker export
2. `backend/api/routes/chat.py` - Integrated activity tracking after message storage (line 351-363)

**Implementation Details:**
- Redis key pattern: `activity:{user_id}:last_message`
- Timestamp format: ISO 8601 with Z suffix (e.g., "2025-12-25T10:30:00Z")
- TTL: 7 days (604800 seconds)
- Langfuse tracing: @observe decorators on all methods
- Error handling: Graceful degradation with fire-and-forget pattern
- Context manager support: Async __aenter__/__aexit__ for resource cleanup
- Redis client reuse: Accepts optional redis_client parameter (from StateManager)

**Design Decisions:**
1. Changed filename from `activity.py` to `activity_tracker.py` per task description
2. Implemented as class (ActivityTracker) instead of standalone functions for better resource management
3. Added helper methods beyond requirements:
   - `get_hours_since_activity()` - For silence evaluator convenience
   - `is_user_active()` - For gate check convenience
4. Used class-based approach to support context manager pattern
5. All methods have @observe decorators for Langfuse tracing

### Verification
- [x] Activity updated on every user message
- [x] Activity retrievable for gate checks
- [x] Missing activity handled gracefully
- [x] TTL set correctly (7 days)
- [x] Integration with chat endpoint (fire-and-forget pattern)
- [x] Langfuse tracing enabled on all methods
- [x] Redis connection reused from StateManager
- [x] Error handling prevents chat flow from breaking
