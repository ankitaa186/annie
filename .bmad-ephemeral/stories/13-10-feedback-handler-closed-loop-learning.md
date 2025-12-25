# Story 13.10: Feedback Handler (Closed Loop Learning)

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.10
**Status:** ready-for-dev
**Estimated Effort:** 0.5 days

---

## User Story

**As a** user,
**I want** Annie to learn from my reactions to proactive messages,
**So that** future proactive messages better match my preferences.

---

## Acceptance Criteria

### AC #1: Record Proactive Message
**Given** proactive message sent,
**When** delivery succeeds,
**Then:**
- Stores in Redis: `proactive_message:{user_id}:last`
- Includes: trigger_id, message_id, sent_at
- TTL: 2 hours (feedback window)

### AC #2: Detect Feedback in Chat Route
**Given** user sends message,
**When** chat route processes,
**Then:**
- Checks if last message was proactive (within 2 hours)
- If yes, adds trigger context to system prompt
- Context includes: trigger name, time sent, full trigger details

### AC #3: Feedback Prompt Enhancement
**Given** feedback context detected,
**When** building system prompt,
**Then** includes:
- Acknowledgment that user is replying to proactive message
- Guidance for handling feedback types:
  - Negative ("This is annoying") → Offer to adjust or disable
  - Threshold feedback ("Don't wake me for 1% moves") → Update execution_instructions
  - Length feedback ("Make these shorter") → Update message_guidance
  - Disable request ("Stop the morning updates") → update_trigger with enabled=false
  - Positive ("This is helpful") → Acknowledge

### AC #4: Auto-Update Triggers
**Given** user provides actionable feedback,
**When** LLM processes,
**Then:**
- LLM can call `update_trigger` to modify action_context
- Changes applied to the specific trigger
- Confirmation sent to user

### AC #5: Clear Feedback Context
**Given** feedback processed,
**Then:**
- Clear Redis key after processing
- Prevents repeated linking to same proactive message

---

## Tasks

### Task 1: Create feedback module
- [x] Create `backend/api/proactive/feedback.py`
- [x] Define `get_proactive_context()` function

### Task 2: Implement proactive message recording
- [x] Already implemented in `telegram_delivery.py` (Story 13.9)
- [x] Function: `record_proactive_message(user_id, trigger_id, message_id)`
- [x] Stores in Redis with 2-hour TTL

### Task 3: Implement feedback detection
- [x] Created `get_proactive_context(user_id, redis_client) -> Optional[dict]`
- [x] Checks if last message was proactive (within 2-hour window)
- [x] Returns trigger context with full details from agentic-memories
- [x] Graceful degradation on errors

### Task 4: Integrate with chat route
- [x] Added feedback detection in chat endpoint (after line 349)
- [x] Stores proactive context in Redis for streaming endpoint
- [x] Uses key pattern: `proactive_context:{conversation_id}`
- [x] TTL: 5 minutes (follows profile/memory cache pattern)

### Task 5: Add feedback handling guidance to prompt
- [x] Created `PROACTIVE_FEEDBACK_GUIDANCE` constant in prompts.py
- [x] Created `format_proactive_context_for_prompt()` function
- [x] Updated `build_system_prompt()` to accept `proactive_context` parameter
- [x] Guidance covers all feedback types (negative, threshold, length, timing, frequency, positive, conversational)

### Task 6: Integrate with stream route
- [x] Added proactive context loading in stream endpoint (after line 1018)
- [x] Loads context from Redis cache
- [x] Passes context to `build_system_prompt()`
- [x] Clears Redis key after loading (one-time use)

### Task 7: Update proactive __init__.py
- [x] Exported `get_proactive_context` from feedback module
- [x] Added to __all__ list

---

## Dev Notes

### Technical Notes
- See Design Doc Section 8.4
- Minimal invasive change to chat route
- Enables closed-loop learning

### Files to Create/Modify
- `backend/api/proactive/feedback.py` (new)
- `backend/api/routes/chat.py` (add feedback detection)
- `backend/api/prompts.py` (add feedback guidance)

### Feedback Types and Actions
| Feedback | Action |
|----------|--------|
| "This is annoying" | Offer to disable or adjust frequency |
| "Don't wake me for small moves" | Update threshold in execution_instructions |
| "Make these shorter" | Update message_guidance length |
| "Stop morning updates" | Disable trigger (enabled=false) |
| "This is helpful" | Acknowledge, reinforce behavior |

### Redis Key
- Key: `proactive_message:{user_id}:last`
- Value: JSON with trigger_id, message_id, sent_at
- TTL: 2 hours (7200 seconds)

---

## Dev Agent Record

### Context Reference
- Context File: `.bmad-ephemeral/stories/13-10-feedback-handler-closed-loop-learning.context.xml`
- Generated: 2025-12-24
- Design Reference: `docs/design/proactive-ai-architecture.md` Section 8.4

### Implementation Notes
- **Implemented:** 2025-12-25
- **Approach:** Followed existing Redis caching patterns from profile/memory integration
- **Key Design Decisions:**
  - Used fire-and-forget pattern for feedback detection (non-blocking)
  - Reused `record_proactive_message()` from Story 13.9 (telegram_delivery.py)
  - One-time context use: Redis key deleted after loading in stream route
  - Graceful degradation: Errors never block chat flow
  - Comprehensive LLM guidance covering 6 feedback types
- **Files Modified:**
  - `/Users/ankit/dev/annie/backend/api/proactive/feedback.py` (new)
  - `/Users/ankit/dev/annie/backend/api/routes/chat.py` (lines 365-406)
  - `/Users/ankit/dev/annie/backend/api/routes/stream.py` (lines 1020-1063)
  - `/Users/ankit/dev/annie/backend/api/prompts.py` (lines 262-416, 676, 724-731)
  - `/Users/ankit/dev/annie/backend/api/proactive/__init__.py` (lines 60-62, 95)

### Verification
- [x] Proactive messages recorded after delivery (already in Story 13.9)
- [x] Feedback context detection implemented with 2-hour window check
- [x] LLM receives trigger context via enhanced system prompt
- [x] LLM guidance includes update_trigger usage patterns for all feedback types
- [x] Context cleared after processing (one-time use)
- [x] All syntax checks passed (python3 -m py_compile)
- [x] Fire-and-forget pattern ensures non-blocking chat flow
- [x] Graceful degradation on Redis/API failures
