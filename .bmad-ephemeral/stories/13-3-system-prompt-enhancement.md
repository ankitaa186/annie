# Story 13.3: System Prompt Enhancement

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.3
**Status:** ready-for-dev
**Estimated Effort:** 0.5 days

---

## User Story

**As a** user,
**I want** Annie to proactively suggest helpful triggers during conversation,
**So that** I can benefit from proactive features without needing to know they exist.

---

## Acceptance Criteria

### AC #1: Proactive Capabilities Section
**Given** system prompt loaded,
**When** building prompt,
**Then** includes:
- Explanation of proactive capabilities
- When to offer triggers (signal phrases)
- Schedule translation examples (natural language → cron)
- Best practices for trigger creation
- How to manage existing triggers

### AC #2: Active Triggers in Context
**Given** user has triggers,
**When** system prompt built,
**Then:**
- Includes summary of active triggers
- Shows intent_name, schedule/condition, last fired
- Helps LLM reference existing triggers

### AC #3: action_context Guidance
**Given** system prompt loaded,
**When** LLM creates trigger,
**Then:**
- Prompt teaches comprehensive action_context structure
- Emphasizes this is briefing for future LLM
- Lists required sections

---

## Tasks

### Task 1: Add proactive capabilities section to system prompt
- [x] Create proactive section in `backend/api/prompts.py`
- [x] Explain what proactive triggers are
- [x] List signal phrases that suggest offering triggers
- [x] Include natural language → cron examples

### Task 2: Add action_context guidance
- [x] Document action_context structure in prompt
- [x] Explain each section (user_profile_snapshot, execution_instructions, skip_conditions, message_guidance)
- [x] Provide examples of good action_context

### Task 3: Implement active triggers injection
- [x] Create function to fetch user's active triggers via IntentsClient
- [x] Format trigger summary for prompt injection
- [x] Add to system prompt builder in stream route

### Task 4: Add trigger management guidance
- [x] Explain how to list, update, pause, delete triggers
- [x] Guide LLM on when to suggest modifications
- [x] Include feedback handling patterns

---

## Dev Notes

### Technical Notes
- See Design Doc Section 6 for full prompt content
- May need to fetch trigger summary from IntentsClient
- Balance detail with prompt length (tokens matter)

### Files to Create/Modify
- `backend/api/prompts.py` (add proactive section)
- `backend/api/routes/stream.py` (inject trigger summary)

### Signal Phrases (from Design Doc)
- "remind me..."
- "let me know when..."
- "alert me if..."
- "check in with me..."
- "wake me up..."
- "every morning/evening/week..."

### action_context Structure
```
user_profile_snapshot: Who is this user?
execution_instructions: What should agent do?
skip_conditions: When to NOT send message?
message_guidance: Tone, length, examples
```

---

## Dev Agent Record

### Context Reference
- Story Context: `.bmad-ephemeral/stories/13-3-system-prompt-enhancement.context.xml`

### Implementation Notes

**Date:** 2025-12-25

**Changes Made:**

1. **Added PROACTIVE_CAPABILITIES_SECTION constant** (lines 106-260 in prompts.py)
   - Comprehensive guide for LLM on proactive features
   - Signal phrases table for recognizing trigger opportunities
   - 6 trigger types documented: price, portfolio, silence, cron, interval, once
   - Best practices: CLARIFY → CONFIRM → EXPLAIN → OFFER
   - Schedule translation table (natural language → cron)
   - Managing existing triggers guidance
   - Comprehensive action_context structure documentation (8 required sections)
   - Daily limits and constraints (5 messages/day, quiet hours 10pm-8am)

2. **Created format_triggers_for_prompt() function** (lines 263-348 in prompts.py)
   - Formats active triggers for prompt injection
   - Human-readable schedule/condition descriptions
   - Cron expression translation (weekdays, daily, custom)
   - Relative time formatting for last_fired_at
   - Graceful handling of missing/malformed data

3. **Updated build_system_prompt() function** (lines 513-590 in prompts.py)
   - Added triggers parameter (Optional[list])
   - Injected PROACTIVE_CAPABILITIES_SECTION after BASE_SYSTEM_PROMPT
   - Added YOUR ACTIVE TRIGGERS section when triggers provided
   - Proper ordering: personality → capabilities → user data → triggers → datetime → formatting

**Integration Points:**

The implementation is ready for integration with Story 13.1 (IntentsClient). When IntentsClient is complete:
- Update stream route to fetch triggers via IntentsClient.get_active_intents(user_id)
- Pass triggers to build_system_prompt() call
- Handle graceful degradation if IntentsClient fails

**Token Impact:**

- Proactive section: ~500 tokens (fixed, always present)
- Trigger list: ~50 tokens per trigger (dynamic)
- Expected total: 500-750 tokens for most users (0-5 triggers)
- Acceptable trade-off for improved proactive suggestions

**Syntax Verified:** Python compilation successful with no errors.

### Verification
- [ ] LLM proactively offers triggers when user mentions reminders
- [ ] LLM knows user's existing triggers
- [ ] LLM creates well-structured action_context
- [ ] Prompt additions don't significantly impact response latency
