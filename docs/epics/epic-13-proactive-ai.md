# Epic 13: Proactive AI Worker

**Status:** Proposed
**Priority:** P1 (Key Differentiator)
**Estimated Effort:** 3-4 days
**Author:** Claude Code (Based on technical research 2025-12-21)
**Date:** 2025-12-21

---

## Overview

Transform Annie from a reactive chatbot (responds to user messages) into a proactive AI companion that initiates contact based on scheduled triggers, price alerts, silence detection, and other conditions. Annie will send messages autonomously when conditions are met, filtered through a "subconscious gate" to prevent spam.

---

## Business Value

1. **Proactive Engagement**: Annie initiates contact instead of waiting for the user
2. **Timely Alerts**: Price thresholds, scheduled reminders, and calendar events delivered at the right moment
3. **Relationship Building**: Silence detection enables natural "check-in" behavior
4. **User Control**: LLM can manage its own triggers via tool calls

---

## Dependencies

### External Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| **agentic-memories Epic 5** | Proposed | Scheduled Intents API (storage, CRUD, `/pending`, `/fire`) |

**CRITICAL**: This epic cannot start until agentic-memories Epic 5 is complete. Annie depends on the intents API for durable trigger storage.

### Internal Dependencies

| Component | Status | Notes |
|-----------|--------|-------|
| Telegram Bot | Complete | Delivery channel |
| LLM Client | Complete | Message generation |
| MCP Server | Complete | Tool hosting |

---

## Architecture

### Stimulus-Response Pattern

```
┌─────────────────────────────────────────────────────────────────┐
│  BACKGROUND WORKER (Arq)                                        │
│  ├── Poll /pending every 30 seconds                             │
│  ├── For each due trigger:                                      │
│  │   ├── 1. Evaluate condition (price, time, silence)           │
│  │   ├── 2. Subconscious gate (spam prevention)                 │
│  │   ├── 3. LLM generation (if gate passes)                     │
│  │   ├── 4. Telegram delivery                                   │
│  │   └── 5. Report to /fire (agentic-memories updates state)    │
│  └── Log results to Langfuse                                    │
└─────────────────────────────────────────────────────────────────┘
```

### Component Flow

```
agentic-memories                    Annie
     │                                │
     │  GET /v1/intents/pending       │
     │◄───────────────────────────────┤
     │                                │
     │  [due triggers]                │
     ├───────────────────────────────►│
     │                                │
     │                    ┌───────────┴───────────┐
     │                    │ For each trigger:     │
     │                    │ 1. Evaluate condition │
     │                    │ 2. Subconscious gate  │
     │                    │ 3. LLM generation     │
     │                    │ 4. Telegram send      │
     │                    └───────────┬───────────┘
     │                                │
     │  POST /v1/intents/{id}/fire    │
     │◄───────────────────────────────┤
     │  {status, trigger_data, ...}   │
     │                                │
     │  (updates next_check, logs)    │
     ├───────────────────────────────►│
     │  {next_check, enabled}         │
     │                                │
```

---

## What's New in Annie

| Component | Purpose |
|-----------|---------|
| `backend/api/proactive/worker.py` | Arq background worker |
| `backend/api/proactive/evaluators.py` | Condition evaluators (price, silence, time) |
| `backend/api/proactive/gate.py` | Subconscious gate (spam prevention) |
| `backend/api/proactive/generator.py` | Initiator mode LLM prompting |
| `backend/api/intents_client.py` | HTTP client for intents API |
| `mcp_server/tools/intents.py` | MCP tools for trigger management |

---

## MCP Tools for LLM Control

Annie's LLM will manage triggers via these tools:

### `create_trigger`
```python
# Schema
{
    "intent_name": "NVDA price alert",
    "trigger_type": "price",
    "trigger_condition": {"ticker": "NVDA", "operator": "<", "value": 130},
    "action_context": "Alert user about NVDA dropping below $130",
    "expires_at": "2025-01-31T23:59:59Z"  # optional
}
```

### `list_triggers`
```python
# Returns all active triggers for user
# Optional filter by trigger_type
```

### `update_trigger`
```python
# Update existing trigger by ID
# Can modify condition, schedule, or disable
```

### `delete_trigger`
```python
# Remove trigger by ID
```

---

## Subconscious Gate

Prevents Annie from becoming spammy. Checks before any proactive message:

| Check | Limit | Behavior |
|-------|-------|----------|
| Recent contact cooldown | 1 hour | Skip if user messaged < 1h ago |
| Daily proactive limit | 5 messages/day | Skip if limit reached |
| Quiet hours | 22:00 - 08:00 user local | Defer to 08:00 |
| User preference | opt-out flag | Skip entirely |

Configuration stored in user profile (Redis).

---

## Condition Evaluators

### Price Evaluator
```python
# Uses yfinance for stock data
def evaluate_price(condition: dict) -> bool:
    ticker = condition["ticker"]
    operator = condition["operator"]  # <, >, <=, >=
    target = condition["value"]
    current = yfinance.Ticker(ticker).info["currentPrice"]
    return apply_operator(current, operator, target)
```

### Silence Evaluator
```python
# Checks last user activity in Redis
def evaluate_silence(condition: dict, user_id: str) -> bool:
    threshold_hours = condition.get("threshold_hours", 48)
    last_activity = redis.get(f"user:{user_id}:last_activity")
    return (now - last_activity) > timedelta(hours=threshold_hours)
```

### Time Evaluator
```python
# For cron/interval/once - handled by agentic-memories
# Annie just checks if trigger is in pending list
def evaluate_time(trigger) -> bool:
    return True  # Already filtered by /pending endpoint
```

---

## Initiator Mode LLM Prompting

When Annie initiates contact, the LLM uses a different persona:

```python
INITIATOR_SYSTEM_PROMPT = """
You are Annie, a proactive AI companion. You are initiating contact with the user.

Context:
- Trigger: {trigger_name}
- Reason: {action_context}
- Last interaction: {time_since_last}

Guidelines:
- Start naturally, don't be jarring
- Reference the trigger reason
- Keep it brief (1-3 sentences)
- End with an invitation to respond or dismiss

Examples:
- "Hey! NVDA just dropped below $130 - wanted to make sure you saw that."
- "It's been a couple days - how's the trading week going?"
- "Quick heads up: your daily portfolio review is ready."
"""
```

---

## Stories Breakdown

### Story 13.1: Intents HTTP Client

**Goal:** Create client to communicate with agentic-memories intents API

**Acceptance Criteria:**

**AC #1:** Given IntentsClient, when CRUD methods called, then:
- `create_intent()` → POST /v1/intents
- `list_intents()` → GET /v1/intents?user_id=X
- `get_intent()` → GET /v1/intents/{id}
- `update_intent()` → PUT /v1/intents/{id}
- `delete_intent()` → DELETE /v1/intents/{id}
- `get_pending()` → GET /v1/intents/pending
- `fire_intent()` → POST /v1/intents/{id}/fire

**AC #2:** Given network error, when any method fails, then:
- Raises `IntentsClientError`
- Logs error with context
- Circuit breaker integration (reuse from MemoryClient)

**AC #3:** Given Langfuse enabled, when methods called, then:
- Operations traced as spans
- Duration and success/failure logged

**Estimated Effort:** 0.5 days

---

### Story 13.2: MCP Tools for Trigger Management

**Goal:** Expose trigger CRUD to LLM via MCP tools

**Acceptance Criteria:**

**AC #1:** Given MCP server, when tools registered, then:
- `create_trigger` tool available with full schema
- `list_triggers` tool with optional type filter
- `update_trigger` tool for modifications
- `delete_trigger` tool for removal

**AC #2:** Given LLM calls tool, when executed, then:
- Tool calls IntentsClient
- Returns success/failure with details
- User ID extracted from session context

**AC #3:** Given validation error from API, when tool returns, then:
- Clear error message for LLM to understand
- Suggests correction if possible

**Estimated Effort:** 0.5 days

---

### Story 13.3: Condition Evaluators

**Goal:** Implement evaluators for different trigger types

**Acceptance Criteria:**

**AC #1:** Given price trigger, when evaluated, then:
- Fetches current price via yfinance
- Applies operator (<, >, <=, >=)
- Returns True if condition met
- Caches price for 60 seconds (avoid rate limits)

**AC #2:** Given silence trigger, when evaluated, then:
- Checks Redis for user's last activity timestamp
- Compares against threshold_hours
- Returns True if silence exceeded

**AC #3:** Given time-based trigger (cron/interval/once), when evaluated, then:
- Always returns True (filtered by /pending)
- No additional evaluation needed

**AC #4:** Given evaluator failure, when exception occurs, then:
- Returns False (fail-safe)
- Logs error with trigger details
- Does not crash worker

**Estimated Effort:** 0.5 days

---

### Story 13.4: Subconscious Gate

**Goal:** Implement spam prevention layer

**Acceptance Criteria:**

**AC #1:** Given recent user contact, when gate checked, then:
- Blocks if user messaged < 1 hour ago
- Returns `{allowed: false, reason: "recent_contact"}`

**AC #2:** Given daily limit reached, when gate checked, then:
- Tracks daily proactive count in Redis (TTL: 24h)
- Blocks if count >= 5
- Returns `{allowed: false, reason: "daily_limit"}`

**AC #3:** Given quiet hours, when gate checked, then:
- Checks user timezone (default: UTC)
- Blocks if 22:00 - 08:00 local time
- Returns `{allowed: false, reason: "quiet_hours", defer_until: "08:00"}`

**AC #4:** Given user opted out, when gate checked, then:
- Checks user profile in Redis
- Blocks if `proactive_enabled: false`
- Returns `{allowed: false, reason: "user_opt_out"}`

**Estimated Effort:** 0.5 days

---

### Story 13.5: Initiator Mode LLM Generator

**Goal:** Generate proactive messages using LLM

**Acceptance Criteria:**

**AC #1:** Given trigger fires and gate passes, when generator called, then:
- Uses initiator system prompt (not responder)
- Includes trigger context in prompt
- Generates 1-3 sentence message

**AC #2:** Given trigger with action_context, when generating, then:
- action_context guides the message content
- LLM references the specific trigger reason

**AC #3:** Given LLM generation, when complete, then:
- Traced in Langfuse with trigger metadata
- Token usage and latency logged

**Estimated Effort:** 0.5 days

---

### Story 13.6: Arq Background Worker

**Goal:** Implement the polling worker that orchestrates everything

**Acceptance Criteria:**

**AC #1:** Given worker running, when poll interval reached (30s), then:
- Calls IntentsClient.get_pending()
- Iterates through due triggers
- Processes each with evaluate → gate → generate → deliver → fire

**AC #2:** Given trigger processing, when complete, then:
- Calls fire_intent() with status:
  - `success` if delivered
  - `condition_not_met` if evaluator returned False
  - `gate_blocked` if subconscious gate blocked
  - `failed` if exception occurred

**AC #3:** Given Telegram delivery, when message sent, then:
- Uses existing Telegram client
- Stores message_id in fire request
- Handles rate limits gracefully

**AC #4:** Given worker failure, when exception occurs, then:
- Worker continues running (doesn't crash)
- Failed trigger logged, will retry on next poll
- Error logged to Langfuse

**Estimated Effort:** 1 day

---

### Story 13.7: User Activity Tracking

**Goal:** Track user activity for silence detection

**Acceptance Criteria:**

**AC #1:** Given user sends message, when chat endpoint processes, then:
- Updates Redis key `user:{user_id}:last_activity`
- Timestamp in ISO format
- TTL: 7 days (covers max silence threshold)

**AC #2:** Given user profile load, when checking activity, then:
- Activity timestamp accessible
- Handles missing key (new user) gracefully

**Estimated Effort:** 0.25 days

---

### Story 13.8: Integration Testing

**Goal:** End-to-end testing with agentic-memories

**Acceptance Criteria:**

**AC #1:** Given test environment, when integration tests run, then:
- Create trigger via MCP tool
- Verify trigger appears in pending (mock time)
- Fire trigger and verify state update

**AC #2:** Given subconscious gate, when tested, then:
- Verify cooldown blocking
- Verify daily limit blocking
- Verify quiet hours blocking

**AC #3:** Given full flow, when trigger fires, then:
- Telegram message sent (mock or test bot)
- Execution logged in agentic-memories
- next_check updated correctly

**Estimated Effort:** 0.5 days

---

## Success Metrics

- [ ] MCP tools allow LLM to create/manage triggers
- [ ] Background worker polls and processes triggers
- [ ] Price alerts fire correctly (test with real yfinance data)
- [ ] Silence detection works after 48h inactivity
- [ ] Subconscious gate prevents spam (< 5 proactive messages/day)
- [ ] All executions logged in agentic-memories
- [ ] Langfuse traces for all proactive operations
- [ ] No user complaints about spam or timing

---

## Rollout Strategy

### Phase 1: Foundation
- Implement stories 13.1-13.4 (client, tools, evaluators, gate)
- Test with manual trigger creation

### Phase 2: Generation
- Implement story 13.5 (initiator LLM)
- Test message quality

### Phase 3: Worker
- Implement stories 13.6-13.7 (worker, activity tracking)
- Test full loop with test triggers

### Phase 4: Validation
- Implement story 13.8 (integration tests)
- Monitor Langfuse for issues
- Gradual rollout with low trigger counts

---

## Technical Considerations

### Arq Worker Setup

```python
# backend/api/proactive/worker.py
from arq import create_pool
from arq.connections import RedisSettings

async def poll_pending_triggers(ctx):
    """Main worker task - runs every 30 seconds"""
    client = IntentsClient()
    pending = await client.get_pending()

    for trigger in pending:
        await process_trigger(trigger)

class WorkerSettings:
    functions = [poll_pending_triggers]
    cron_jobs = [cron(poll_pending_triggers, second=0, minute={0, 30})]  # Every 30s
    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL"))
```

### Dependencies to Add

```
# backend/requirements.txt
arq>=0.25.0        # Background worker
yfinance>=0.2.0    # Stock data
croniter>=2.0.0    # Cron parsing (if needed locally)
```

---

## References

- **Technical Research**: `/home/ankit/dev/annie/docs/research-technical-2025-12-21.md`
- **agentic-memories Epic 5**: `/home/ankit/dev/agentic-memories/docs/epic-5-scheduled-intents.md`
- **Arq Documentation**: https://arq-docs.helpmanual.io/
- **yfinance Documentation**: https://pypi.org/project/yfinance/
