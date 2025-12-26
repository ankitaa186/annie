# Epic 13: Proactive AI Worker

**Status:** Ready (Pending agentic-memories Epic 6 merge)
**Priority:** P1 (Key Differentiator)
**Estimated Effort:** 5-6 days
**Author:** Ankit + Claude Code
**Date:** 2025-12-24 (Revised)
**Updated:** Stories aligned with claims-based worker pattern

---

## Design Document

**CRITICAL:** This epic implements the architecture defined in:

📄 **[Proactive AI Architecture Design Document](../design/proactive-ai-architecture.md)**

All implementation decisions should reference that document. This epic provides the story breakdown and implementation plan.

---

## Overview

Transform Annie from a reactive chatbot (responds to user messages) into a proactive AI companion that initiates contact based on:

- **Scheduled triggers**: Daily check-ins, weekly summaries, one-time reminders
- **Condition triggers**: Price alerts, portfolio milestones, silence detection

### Key Design Decision: LLM-Driven Architecture

Unlike traditional approaches with hardcoded trigger handlers, we use an **LLM-driven architecture**:

1. **Creation LLM** captures full user intent in rich `action_context`
2. **Wake-up LLM** reads `action_context` as a briefing document
3. Wake-up LLM has **full tool access** to gather data and compose messages
4. **Minimal trigger types** (only 2) - everything else is context

This enables handling of **novel trigger types without code changes**.

---

## Business Value

1. **Proactive Engagement**: Annie initiates contact instead of waiting
2. **Timely Alerts**: Price drops, scheduled reminders delivered at the right moment
3. **Relationship Building**: Silence detection enables natural check-ins
4. **Flexibility**: LLM handles novel trigger types without new code
5. **User Control**: Users can create, modify, and delete triggers conversationally

---

## Dependencies

### External Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| **agentic-memories Epic 5** | ✅ Complete | Intents API (CRUD, `/pending`, `/fire`) |
| **agentic-memories Epic 6** | 🔄 In Review | API Alignment (timezone, expressions, cooldown, claims) |

**STATUS UPDATE (2025-12-24):**
- Epic 5 (Intents API) is complete
- Epic 6 Story 6.3 (Cooldown Logic) is in review - includes claims API:
  - `POST /v1/intents/{id}/claim` - Claims intent for processing (409 if claimed)
  - `claimed_at` field with 5-minute timeout
  - `FOR UPDATE SKIP LOCKED` for multi-worker safety
  - `in_cooldown` flag returned from `/pending` endpoint
  - `last_condition_fire` tracking for condition triggers

Epic 6 adds:
- Timezone support for user-local scheduling
- Flexible condition expressions ("NVDA < 130", "any_holding_change > 5%")
- Cooldown logic (minimum hours between fires) ✅ Implemented
- Fire mode (once vs recurring for conditions)
- Portfolio condition type
- **Claims API for multi-worker safety** ✅ Implemented

### Internal Dependencies

| Component | Status | Notes |
|-----------|--------|-------|
| Telegram Bot | Complete | Delivery channel |
| LLM Client | Complete | Message generation |
| MCP Server | Complete | Tool hosting |
| Redis | Complete | Activity tracking, gate state |

---

## Architecture Summary

See [Design Document](../design/proactive-ai-architecture.md) for full details.

### Trigger Types (Only 2)

| Type | Wake-Up Mechanism | Examples |
|------|-------------------|----------|
| `scheduled` | Fire at specific times | Cron (recurring), Once (one-time) |
| `condition` | Fire when condition true | Price alerts, portfolio, silence |

### Component Flow

```
┌─────────────────────────────────────────────────────────────────┐
│  USER: "Every morning, give me a portfolio update"              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  CREATION LLM                                                    │
│  - Understands intent                                            │
│  - Crafts rich action_context (briefing for future LLM)         │
│  - Calls create_trigger MCP tool                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  AGENTIC-MEMORIES                                                │
│  - Stores trigger with action_context                            │
│  - Manages next_check scheduling                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                       [Time passes]
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  ARQ WORKER (polls every 30s)                                    │
│  - Gets due triggers from /pending                               │
│  - For condition triggers: evaluates condition                   │
│  - Passes to processing pipeline                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  SUBCONSCIOUS GATE                                               │
│  - Recent contact check (1h)                                     │
│  - Daily limit check (5/day)                                     │
│  - Quiet hours check (10pm-8am)                                  │
│  - User opt-out check                                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  WAKE-UP LLM (Agent)                                             │
│  - Reads action_context briefing                                 │
│  - Calls tools as instructed (get_portfolio, etc.)               │
│  - Applies skip conditions from briefing                         │
│  - Composes message following message_guidance                   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  TELEGRAM DELIVERY + FIRE REPORT                                 │
│  - Sends message to user                                         │
│  - Reports execution to agentic-memories                         │
│  - Updates next_check for recurring triggers                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Stories Breakdown

### Story 13.1: Intents HTTP Client

**Goal:** Create HTTP client to communicate with agentic-memories Intents API.

**File:** `backend/api/intents_client.py`

**Acceptance Criteria:**

**AC #1: CRUD Operations**
Given IntentsClient, when CRUD methods called, then:
- `create_intent(data)` → POST `/v1/intents`
- `list_intents(user_id, filters)` → GET `/v1/intents?user_id=X`
- `get_intent(id)` → GET `/v1/intents/{id}`
- `update_intent(id, data)` → PUT `/v1/intents/{id}`
- `delete_intent(id)` → DELETE `/v1/intents/{id}`

**AC #2: Polling & Worker Operations**
Given IntentsClient, when polling methods called, then:
- `get_pending(trigger_type)` → GET `/v1/intents/pending`
  - Returns due intents, excludes already-claimed intents
  - Includes `in_cooldown` flag for condition triggers
- `claim_intent(id)` → POST `/v1/intents/{id}/claim`
  - Claims intent for exclusive processing (prevents race conditions)
  - Returns `IntentClaimResponse` with `intent` and `claimed_at`
  - Returns 409 Conflict if already claimed within 5 minutes
  - Uses `FOR UPDATE SKIP LOCKED` for multi-worker safety
- `fire_intent(id, report)` → POST `/v1/intents/{id}/fire`
  - Reports execution result (success/skipped/gate_blocked/error)
  - Clears `claimed_at` (releases claim)
  - Updates `last_condition_fire` for condition triggers
  - Updates `fire_count` and `last_fired`

**AC #3: Error Handling**
Given network error, when any method fails, then:
- Raises `IntentsClientError` with context
- Logs error with trigger/user details
- Circuit breaker integration (reuse pattern from MemoryClient)

**AC #4: Observability**
Given Langfuse enabled, when methods called, then:
- Operations traced as spans
- Duration and success/failure logged

**Technical Notes:**
- Follow existing `MemoryClient` pattern
- Reuse circuit breaker infrastructure
- Add to health check endpoint

**Estimated Effort:** 0.5 days

---

### Story 13.2: MCP Tools for Trigger Management

**Goal:** Expose trigger CRUD to LLM via MCP tools with comprehensive documentation.

**Files:** `mcp_server/tools/triggers.py`, `mcp_server/server.py`

**Acceptance Criteria:**

**AC #1: create_trigger Tool**
Given MCP server, when `create_trigger` registered, then:
- Full schema as defined in [Design Doc Section 5.1](../design/proactive-ai-architecture.md#51-create_trigger)
- Comprehensive description teaching LLM:
  - When to use (reminders, alerts, check-ins)
  - Cron expression examples
  - How to write rich action_context
- Returns created trigger with ID and next_check

**AC #2: list_triggers Tool**
Given MCP server, when `list_triggers` registered, then:
- Filter by trigger_type (scheduled/condition/all)
- Option to include disabled triggers
- Returns array with id, intent_name, schedule/condition, enabled, next_check, fire_count

**AC #3: update_trigger Tool**
Given MCP server, when `update_trigger` registered, then:
- Accepts trigger_id + partial updates
- Can modify schedule, condition, action_context, enabled
- Description explains pause vs delete difference

**AC #4: delete_trigger Tool**
Given MCP server, when `delete_trigger` registered, then:
- Requires trigger_id + confirm=true
- Description emphasizes confirmation with user first
- Returns success confirmation

**AC #5: Tool Execution**
Given LLM calls any trigger tool, when executed, then:
- Tool calls IntentsClient
- User ID extracted from session context
- Returns structured success/failure
- Errors include clear messages for LLM

**Technical Notes:**
- See [Design Doc Section 5](../design/proactive-ai-architecture.md#5-mcp-tool-definitions) for complete schemas
- Tool descriptions are critical - they teach the LLM

**Estimated Effort:** 1 day

---

### Story 13.3: System Prompt Enhancement

**Goal:** Add proactive capabilities section to Annie's system prompt.

**Files:** `backend/api/prompts.py`

**Acceptance Criteria:**

**AC #1: Proactive Capabilities Section**
Given system prompt, when loaded, then includes:
- Explanation of proactive capabilities
- When to offer triggers (signal phrases)
- Schedule translation examples (natural language → cron)
- Best practices for trigger creation
- How to manage existing triggers

**AC #2: Active Triggers in Context**
Given user has triggers, when system prompt built, then:
- Includes summary of active triggers
- Shows intent_name, schedule/condition, last fired
- Helps LLM reference existing triggers

**AC #3: action_context Guidance**
Given system prompt, when LLM creates trigger, then:
- Prompt teaches comprehensive action_context structure
- Emphasizes this is briefing for future LLM
- Lists required sections

**Technical Notes:**
- See [Design Doc Section 6](../design/proactive-ai-architecture.md#6-system-prompt-enhancements) for full prompt content
- May need to fetch trigger summary from IntentsClient

**Estimated Effort:** 0.5 days

---

### Story 13.4: Condition Evaluators

**Goal:** Implement fast condition evaluators for different condition types.

**File:** `backend/api/proactive/evaluators.py`

**Acceptance Criteria:**

**AC #1: Price Evaluator**
Given price condition trigger, when evaluated, then:
- Fetches current price via yfinance
- Parses expression (e.g., "NVDA < 130")
- Supports operators: `<`, `>`, `<=`, `>=`
- Returns True if condition met
- Caches price for 60 seconds (avoid rate limits)
- **Reliability handling** (yfinance is unofficial scraper):
  - Retry with exponential backoff (3 attempts)
  - Fail-safe: return False on error (don't fire on error)
  - Log errors for monitoring

**AC #2: Portfolio Evaluator**
Given portfolio condition trigger, when evaluated, then:
- Fetches portfolio via get_portfolio
- Supports expressions:
  - `any_holding_change > X%`
  - `any_holding_down > X%`
  - `total_value >= X`
  - `total_change > X%`
- Returns True if condition met

**AC #3: Silence Evaluator**
Given silence condition trigger, when evaluated, then:
- Checks Redis for `user:{user_id}:last_activity`
- Compares against threshold from expression
- Returns True if silence exceeded

**AC #4: Error Handling**
Given evaluator failure, when exception occurs, then:
- Returns False (fail-safe, don't fire on error)
- Logs error with trigger details
- Does not crash worker

**Technical Notes:**
- These are FAST evaluations (no LLM)
- LLM only invoked after condition passes
- See [Design Doc Section 3.3](../design/proactive-ai-architecture.md#33-type-condition)

**Estimated Effort:** 0.5 days

---

### Story 13.5: Subconscious Gate

**Goal:** Implement spam prevention layer.

**File:** `backend/api/proactive/gate.py`

**Acceptance Criteria:**

**AC #1: Recent Contact Check**
Given user messaged recently, when gate checked, then:
- Blocks if user messaged < 1 hour ago
- Returns `GateResult(allowed=False, reason="recent_contact")`

**AC #2: Daily Limit Check**
Given daily limit tracking, when gate checked, then:
- Tracks count in Redis: `proactive:{user_id}:daily:{date}`
- TTL: 24 hours
- Blocks if count >= 5
- Returns `GateResult(allowed=False, reason="daily_limit")`

**AC #3: Quiet Hours Check**
Given user timezone, when gate checked, then:
- Checks user's local time
- Blocks if 22:00 - 08:00
- Returns `GateResult(allowed=False, reason="quiet_hours", defer_until=...)`

**AC #4: User Opt-Out Check**
Given user preferences, when gate checked, then:
- Checks `proactive_enabled` in user profile
- Blocks if explicitly disabled
- Returns `GateResult(allowed=False, reason="user_opt_out")`

**AC #5: Gate Result Model**
Given gate check complete, returns:
```python
GateResult(
    allowed: bool,
    reason: Optional[str],
    defer_until: Optional[datetime]
)
```

**Technical Notes:**
- See [Design Doc Section 12.1](../design/proactive-ai-architecture.md#121-subconscious-gate)
- Increment daily count only on successful send

**Estimated Effort:** 0.5 days

---

### Story 13.6: Wake-Up Agent

**Goal:** Implement LLM-driven agent that executes fired triggers with dynamic state injection.

**File:** `backend/api/proactive/agent.py`

**Acceptance Criteria:**

**AC #1: Dynamic State Injection**
Given trigger fires, when agent invoked, then gathers fresh context:
- Current datetime and day of week (in user's timezone)
- Market status (open/closed/holiday)
- Hours since user last messaged
- Recent conversation summary (from agentic-memories, last 24h)
- Fresh user profile (not from action_context)

**AC #2: Agent Prompt**
Given trigger fires and gate passes, when agent invoked, then:
- Receives comprehensive prompt with:
  - Trigger metadata (name, type, fire_count, last_fired)
  - **Dynamic state** (current time, recent context, fresh profile)
  - Full action_context as briefing
  - Available tools list
  - Response format specification
  - **Tone adjustment guidance** based on recent_context (e.g., don't be chirpy if user discussed breakup)

**AC #3: Dynamic Tool Access**
Given wake-up agent, when executing, then:
- Queries MCP server fresh for complete tool list
- Has access to ALL read-only tools
- Only restricts state-modifying tools (add_holding, update_holding, remove_holding, create_trigger, delete_trigger)
- No artificial limits on which tools can be used

**AC #4: Skip Logic**
Given action_context with skip conditions, when agent evaluates, then:
- Follows execution_instructions from briefing
- Returns `skip=True` with reason when appropriate
- Does not send message for skipped triggers

**AC #5: Message Composition**
Given action_context with message_guidance, when composing, then:
- Follows tone, length, include/exclude guidelines
- References good/bad examples from briefing
- Returns composed message
- **Adjusts tone based on recent_context** (e.g., more gentle if user is going through something)

**AC #6: Response Format**
Given agent execution complete, returns:
```python
WakeUpResult(
    skip: bool,
    skip_reason: Optional[str],
    message: Optional[str],
    tools_called: List[str],
    reasoning: str
)
```

**AC #7: Guardrails**
Given agent execution, then enforces:
- 10 minute timeout (600 seconds)
- Restricted tools list (no portfolio modification - add_holding, update_holding, delete_trigger)
- No hard limits on tool calls or message length (agent is trusted to follow action_context guidance)

**Technical Notes:**
- See [Design Doc Section 7](../design/proactive-ai-architecture.md#7-wake-up-agent-design)
- Uses same LLM client as chat
- Traced in Langfuse with trigger metadata

**Estimated Effort:** 1 day

---

### Story 13.7: Arq Background Worker

**Goal:** Implement the polling worker that orchestrates trigger execution.

**Files:** `backend/api/proactive/worker.py`, `backend/api/proactive/__init__.py`

**Acceptance Criteria:**

**AC #1: Scheduled Trigger Polling**
Given worker running, when poll interval reached (30s), then:
- Calls `IntentsClient.get_pending(trigger_type="scheduled")`
- For each due trigger:
  1. Claims trigger via `IntentsClient.claim_intent(id)`
  2. If 409 Conflict → Skip (already claimed by another worker)
  3. If claimed → Pass to processing pipeline

**AC #2: Condition Trigger Polling**
Given worker running, when poll interval reached (60s), then:
- Calls `IntentsClient.get_pending(trigger_type="condition")`
- For each trigger:
  1. Skip if `in_cooldown` flag is true
  2. Claims trigger via `IntentsClient.claim_intent(id)`
  3. If 409 Conflict → Skip (already claimed by another worker)
  4. Evaluates condition via evaluators (fast, no LLM)
  5. If condition met → Pass to processing pipeline
  6. If not met → Call `fire_intent()` with status="condition_not_met" (clears claim, updates next_check)

**AC #3: Processing Pipeline**
Given claimed trigger to process, executes in order:
1. Subconscious gate check
2. Wake-up agent execution
3. Telegram delivery (if not skipped)
4. Fire report to agentic-memories (clears claim)

**AC #4: Fire Reporting**
Given trigger processed, when reporting to agentic-memories, then:
- Calls `IntentsClient.fire_intent()` with:
  - status: success/skipped/gate_blocked/error
  - message_id (if sent)
  - message_preview
  - skip_reason (if skipped)
  - tools_called
  - execution_time_ms

**AC #5: Error Resilience**
Given worker failure, when exception occurs, then:
- Worker continues running (doesn't crash)
- Failed trigger logged
- Will retry on next poll cycle
- Error logged to Langfuse

**AC #6: Worker Configuration**
Given Arq worker, configuration includes:
- Cron job: scheduled polling every 30s
- Cron job: condition polling every 60s
- Redis connection from environment
- Max concurrent jobs: 10
- Job timeout: 60s

**Technical Notes:**
- See [Design Doc Section 8.3](../design/proactive-ai-architecture.md#83-worker-architecture)
- New dependency: `arq>=0.25.0`
- Runs as separate process/container

**Estimated Effort:** 1 day

---

### Story 13.8: User Activity Tracking

**Goal:** Track user activity for silence detection and gate checks.

**Files:** `backend/api/routes/chat.py`, `backend/api/proactive/activity.py`

**Acceptance Criteria:**

**AC #1: Activity Update on Message**
Given user sends message, when chat endpoint processes, then:
- Updates Redis: `user:{user_id}:last_activity`
- Value: ISO timestamp
- TTL: 7 days

**AC #2: Activity Retrieval**
Given activity check needed, when queried, then:
- Returns last activity timestamp
- Handles missing key (new user) gracefully
- Returns None for users with no history

**AC #3: Integration with Gate**
Given subconscious gate check, uses activity for:
- Recent contact check (< 1 hour)
- Can be extended for other checks

**Technical Notes:**
- Minimal change to chat.py
- Activity module provides utility functions

**Estimated Effort:** 0.25 days

---

### Story 13.9: Telegram Delivery Integration

**Goal:** Enable proactive message delivery to Telegram.

**File:** `backend/api/proactive/delivery.py`

**Acceptance Criteria:**

**AC #1: Delivery Function**
Given message to send, when deliver called, then:
- Looks up user's Telegram chat_id from Redis/profile
- Sends message via Telegram Bot API
- Returns message_id for tracking

**AC #2: Rate Limit Handling**
Given Telegram rate limit hit, when sending, then:
- Respects 429 responses
- Implements exponential backoff
- Retries up to 3 times

**AC #3: Error Handling**
Given delivery failure, when exception occurs, then:
- Returns None for message_id
- Logs error with context
- Does not crash worker

**Technical Notes:**
- Reuse existing Telegram client infrastructure
- May need to add chat_id lookup if not already available

**Estimated Effort:** 0.25 days

---

### Story 13.10: Feedback Handler (Closed Loop Learning)

**Goal:** Enable the system to learn from user reactions to proactive messages.

**Files:** `backend/api/proactive/feedback.py`, `backend/api/routes/chat.py`

**Acceptance Criteria:**

**AC #1: Record Proactive Message**
Given proactive message sent, when delivery succeeds, then:
- Stores in Redis: `proactive_message:{user_id}:last`
- Includes: trigger_id, message_id, sent_at
- TTL: 2 hours (feedback window)

**AC #2: Detect Feedback in Chat Route**
Given user sends message, when chat route processes, then:
- Checks if last message was proactive (within 2 hours)
- If yes, adds trigger context to system prompt
- Context includes: trigger name, time sent, full trigger details

**AC #3: Feedback Prompt Enhancement**
Given feedback context detected, when building system prompt, then includes:
- Acknowledgment that user is replying to proactive message
- Guidance for handling feedback types:
  - Negative ("This is annoying") → Offer to adjust or disable
  - Threshold feedback ("Don't wake me for 1% moves") → Update execution_instructions
  - Length feedback ("Make these shorter") → Update message_guidance
  - Disable request ("Stop the morning updates") → update_trigger with enabled=false
  - Positive ("This is helpful") → Acknowledge

**AC #4: Auto-Update Triggers**
Given user provides actionable feedback, when LLM processes, then:
- LLM can call `update_trigger` to modify action_context
- Changes applied to the specific trigger
- Confirmation sent to user

**AC #5: Clear Feedback Context**
Given feedback processed, then:
- Clear Redis key after processing
- Prevents repeated linking to same proactive message

**Technical Notes:**
- See [Design Doc Section 8.4](../design/proactive-ai-architecture.md#84-feedback-handler)
- Minimal invasive change to chat route
- Enables closed-loop learning

**Estimated Effort:** 0.5 days

---

### Story 13.11: Integration Testing

**Goal:** End-to-end testing of proactive system.

**Files:** `backend/tests/test_proactive/`

**Acceptance Criteria:**

**AC #1: Trigger Creation Tests**
Given test environment, when creating triggers, then:
- Create scheduled trigger via MCP tool
- Create condition trigger via MCP tool
- Verify stored correctly in mock agentic-memories

**AC #2: Condition Evaluator Tests**
Given mock data, when evaluating conditions, then:
- Price evaluator: test <, >, <=, >= operators
- Portfolio evaluator: test various expressions
- Silence evaluator: test with mock activity times

**AC #3: Subconscious Gate Tests**
Given various scenarios, when checking gate, then:
- Verify recent contact blocking
- Verify daily limit blocking
- Verify quiet hours blocking
- Verify opt-out blocking

**AC #4: Wake-Up Agent Tests**
Given mock trigger with action_context, when agent executes, then:
- Verify tool calls match briefing
- Verify skip conditions respected
- Verify message matches guidelines

**AC #5: Full Flow Test**
Given complete mock environment, when trigger fires, then:
- Gate passes
- Agent executes
- Message "sent" (mock Telegram)
- Fire reported correctly

**AC #6: Feedback Handler Tests**
Given proactive message sent, when user replies, then:
- Feedback context correctly detected
- System prompt includes trigger context
- Update trigger works for feedback-based changes
- Feedback context cleared after processing

**Technical Notes:**
- Use pytest fixtures for mocking
- Mock agentic-memories, Telegram, LLM
- Time mocking with `freezegun`

**Estimated Effort:** 0.5 days

---

## Story Sequencing

```
13.1 Intents HTTP Client ─────┐
                              │
13.2 MCP Tools ───────────────┼───► 13.3 System Prompt
                              │
13.4 Condition Evaluators ────┤
                              │
13.5 Subconscious Gate ───────┤
                              ├───► 13.7 Arq Worker ───► 13.10 Feedback Handler
13.6 Wake-Up Agent ───────────┤                                │
                              │                                ▼
13.8 User Activity Tracking ──┤                      13.11 Integration Tests
                              │
13.9 Telegram Delivery ───────┘
```

**Recommended Execution Order:**

1. **Phase 1: Foundation** (Day 1-2)
   - 13.1 Intents HTTP Client
   - 13.2 MCP Tools for Trigger Management
   - 13.3 System Prompt Enhancement

2. **Phase 2: Evaluation & Safety** (Day 2-3)
   - 13.4 Condition Evaluators
   - 13.5 Subconscious Gate
   - 13.8 User Activity Tracking

3. **Phase 3: Execution** (Day 3-4)
   - 13.6 Wake-Up Agent (with dynamic state injection)
   - 13.9 Telegram Delivery

4. **Phase 4: Orchestration & Feedback** (Day 4-5)
   - 13.7 Arq Background Worker
   - 13.10 Feedback Handler (closed-loop learning)

5. **Phase 5: Testing** (Day 5-6)
   - 13.11 Integration Testing

---

## Success Metrics

- [ ] MCP tools allow LLM to create/list/update/delete triggers
- [ ] LLM correctly interprets natural language into cron expressions
- [ ] LLM writes comprehensive action_context briefings
- [ ] Background worker polls and processes triggers
- [ ] Condition evaluators correctly detect price/portfolio/silence conditions
- [ ] Subconscious gate prevents spam (< 5 proactive messages/day)
- [ ] Wake-up agent follows action_context instructions
- [ ] Messages match tone and length from briefing
- [ ] All executions logged in agentic-memories
- [ ] Langfuse traces for all proactive operations
- [ ] No user complaints about spam or timing

---

## New Files Summary

| File | Purpose |
|------|---------|
| `backend/api/intents_client.py` | HTTP client for Intents API |
| `backend/api/proactive/__init__.py` | Package init |
| `backend/api/proactive/worker.py` | Arq background worker |
| `backend/api/proactive/agent.py` | Wake-up agent logic + dynamic state injection |
| `backend/api/proactive/gate.py` | Subconscious gate |
| `backend/api/proactive/evaluators.py` | Condition evaluators |
| `backend/api/proactive/delivery.py` | Telegram delivery |
| `backend/api/proactive/activity.py` | User activity tracking |
| `backend/api/proactive/feedback.py` | Feedback handler for closed-loop learning |
| `mcp_server/tools/triggers.py` | Trigger management MCP tools |
| `backend/tests/test_proactive/` | Test suite |

---

## Dependencies to Add

```
# backend/requirements.txt
arq>=0.25.0          # Background worker
croniter>=2.0.0      # Cron expression parsing
yfinance>=0.2.0      # Stock price fetching
```

---

## References

- **Design Document**: [Proactive AI Architecture](../design/proactive-ai-architecture.md)
- **agentic-memories Epic 5**: Intents API (required dependency)
- **Arq Documentation**: https://arq-docs.helpmanual.io/
- **yfinance Documentation**: https://pypi.org/project/yfinance/

---

*This epic transforms Annie into a proactive companion that reaches out at the right moments, with full LLM intelligence guiding every interaction.*
