# Technical Research Report: Proactive AI Architecture for Annie

**Date:** 2025-12-21
**Prepared by:** Ankit
**Project Context:** Extending Annie from reactive to proactive AI companion

---

## Executive Summary

This research evaluated approaches to extend Annie from a reactive chatbot (responds to messages) to a proactive AI companion (initiates contact autonomously). The goal: enable Annie to send reminders, trading signals, market briefings, and contextual check-ins without user prompting.

### Key Recommendation

**Primary Choice:** Arq (async Redis queue) + Agentic-Memories PostgreSQL

**Rationale:** This approach leverages existing infrastructure (agentic-memories already has PostgreSQL), provides full audit trails, enables LLM-controllable triggers via tool calls, and maintains clean separation of concerns - Annie handles evaluation and generation, agentic-memories owns trigger state.

**Key Benefits:**
- **No new infrastructure** - Extends existing agentic-memories service
- **Full audit trail** - Execution history, queryable analytics
- **LLM-controllable** - Annie creates/manages triggers via `create_trigger`, `list_triggers`, `update_trigger`, `delete_trigger` tools
- **Durable** - Triggers survive restarts, ACID-compliant storage
- **Observable** - Langfuse tracing already integrated

### Architecture Overview

```
Annie Backend                           Agentic-Memories
├── MCP Tools (LLM creates triggers)    ├── /v1/intents API (CRUD)
├── Arq Worker (polls every 30s)        ├── scheduled_intents table
├── Condition Evaluators (yfinance)     ├── intent_executions history
├── Subconscious Gate (spam prevention) └── State management (/fire endpoint)
└── Initiator Mode LLM → Telegram
```

### State Ownership

| Component | Owner |
|-----------|-------|
| Trigger definitions, schedules | Agentic-memories |
| `next_check`, `last_executed` calculation | Agentic-memories |
| Condition evaluation (price checks) | Annie |
| Subconscious gate (cooldowns, quiet hours) | Annie |
| LLM generation, Telegram delivery | Annie |

---

## 1. Research Objectives

### Technical Question

How to implement proactive/autonomous messaging for Annie - moving from reactive (respond to requests) to proactive (initiate contact autonomously)?

### Project Context

- **Project:** Annie - personal AI companion chatbot
- **Field Type:** Brownfield (extending existing system)
- **Current State:** Reactive architecture (Telegram → Backend → LLM → Response)
- **Target State:** Proactive architecture with stimulus-response pattern
- **User Scale:** 1-10 users (personal use)

### Requirements and Constraints

#### Functional Requirements

| Category | Capability | Example |
|----------|------------|---------|
| **Scheduled Intents** | User-requested reminders | "Remind me to check RKLB earnings Tuesday" |
| **Silence Detection** | Inactivity-triggered check-ins | "Haven't heard from you in 48h" |
| **Market Events** | Portfolio/stock movement alerts | "NVDA dropped 5%", "Portfolio hit ATH" |
| **Trading Signals** | Buy/sell timing alerts | "NVDA hit your target entry at $130", "RSI oversold" |
| **Time-Based** | Scheduled briefings | "Market close summary", "Morning brief" |
| **Calendar Integration** | Meeting/event awareness | "Your 1:1 with Sarah is in 30 mins" |
| **News/RSS Monitoring** | Relevant news detection | "Breaking: Fed announces rate decision" |
| **Health/Habit Check-ins** | Wellness prompts | "Time for your afternoon walk?" |
| **Custom Data Sources** | Extensible trigger system | Webhooks, APIs, any data feed |
| **Shadow Thoughts** | Reflective follow-ups | "How did the standup go?" |

#### Non-Functional Requirements

| Dimension | Target |
|-----------|--------|
| **Latency** | < 60 seconds for market events |
| **Reliability** | Durable execution (survives restarts) |
| **Scalability** | Design for multi-user, optimize for single |
| **Spam Prevention** | Max 5-10 proactive messages/day, 2hr cooldown |
| **Quiet Hours** | Respect 10pm-7am unless market-critical |

#### Technical Constraints

| Constraint | Decision |
|------------|----------|
| **Market Data** | yfinance (15-20 min delay acceptable) |
| **Simplicity** | Minimal infrastructure, single worker |
| **LLM-Controllable** | All triggers via tool calls, data-driven |
| **Existing Stack** | Redis, FastAPI, Telegram - no new services |

#### Key Architectural Decision

**LLM-Controllable Trigger System** - Annie manages her own triggers:
- `create_trigger(type, condition, action, context)`
- `list_triggers(user_id)`
- `update_trigger(trigger_id, changes)`
- `delete_trigger(trigger_id)`

---

## 2. Technology Options Evaluated

### Scheduler Layer Options

| Option | Description | Pros | Cons | Verdict |
|--------|-------------|------|------|---------|
| **APScheduler 3.x** | In-process Python scheduler with Redis job store | Stable, no broker needed, Redis persistence | Not fully async, single process | ✅ Good |
| **APScheduler 4.0** | Async-native rewrite with AnyIO support | Modern async, Redis support | Pre-release (NOT production ready) | ❌ Too risky |
| **Arq** | Asyncio-native Redis queue | FastAPI-friendly, lightweight, I/O optimized | Separate worker process | ✅ Recommended |
| **Celery Beat** | Distributed task scheduler | Battle-tested, scalable | Overkill for 1-10 users, complex setup | ❌ Too heavy |
| **FastAPI BackgroundTasks** | Built-in background task support | Zero dependencies | Not persistent, no scheduling | ❌ Too simple |

### Rule Engine Options

| Option | Description | Pros | Cons | Verdict |
|--------|-------------|------|------|---------|
| **Custom Python** | Hand-rolled condition evaluation | Zero deps, full control, LLM can generate | Must build yourself | ✅ Recommended |
| **py-rules-engine** | Pure Python rules with JSON/YAML | Pythonic, no deps | Learning curve | ⚠️ Alternative |
| **rule-engine** | Safe expression evaluation | Sandboxed execution | Custom syntax | ⚠️ Alternative |

### Storage Options

| Option | Description | Pros | Cons | Verdict |
|--------|-------------|------|------|---------|
| **Redis (Annie)** | Store triggers in Annie's Redis | Already in stack, fast | No audit trail, limited queries | ❌ Insufficient |
| **PostgreSQL (Annie)** | Add Postgres to Annie | Queryable, durable | New infrastructure | ❌ Redundant |
| **Agentic-Memories PostgreSQL** | Extend existing agentic-memories | Already has Postgres, audit trail, Langfuse | API call overhead | ✅ Recommended |

---

## 3. Detailed Technology Profiles

### 3.1 Arq (Async Redis Queue)

**Overview:** ARQ is a lightweight, asyncio-native task queue built explicitly for modern Python applications. It uses Redis as its sole message broker and state backend.

**Current Status (2025):**
- Actively maintained
- Native asyncio support
- Redis-only (no RabbitMQ option)

**Key Features:**
- Seamless FastAPI integration
- Deferred job execution (`defer_until`)
- Cron-style scheduling (`cron_jobs`)
- Retry logic with backoff
- Job result storage

**Why Arq for Annie:**
- Annie's backend is already async (FastAPI)
- Already has Redis in the stack
- Lightweight - no additional broker
- Perfect for I/O-bound tasks (API calls, Telegram messages)

**Sources:**
- [Celery vs ARQ Comparison](https://leapcell.io/blog/celery-versus-arq-choosing-the-right-task-queue-for-python-applications)
- [FastAPI Background Tasks vs ARQ](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/)

### 3.2 Agentic-Memories Storage

**Overview:** Agentic-memories is an existing service in the Annie ecosystem providing polyglot persistence with specialized databases.

**Database Stack:**

| Database | Purpose | Current Usage |
|----------|---------|---------------|
| **PostgreSQL** | Structured data | Procedural memories, profiles, portfolio |
| **TimescaleDB** | Time-series | Episodic memories, emotional states |
| **ChromaDB** | Vector search | Semantic memory retrieval |
| **Neo4j** | Graph relationships | Skill dependencies (planned) |
| **Redis** | Hot cache | Sessions, activity tracking |

**Why Extend Agentic-Memories:**
- PostgreSQL already available - no new infrastructure
- Existing API patterns (FastAPI REST)
- Langfuse tracing already integrated
- Can link triggers to memories for context
- Audit trail and execution history for free

---

## 4. Comparative Analysis

### Decision Matrix

| Criterion | Weight | Arq + Custom Rules + Agentic-Memories | APScheduler + Redis | Celery + PostgreSQL |
|-----------|--------|---------------------------------------|---------------------|---------------------|
| Simplicity | 25% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| Existing Stack | 20% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐ |
| Durability | 20% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| Queryability | 15% | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| LLM-Controllable | 15% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| Async-Native | 5% | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐ |
| **Total** | 100% | **4.85** | **3.45** | **3.20** |

### Decision Priorities

1. **Simplicity** - Minimal new infrastructure
2. **Existing Stack** - Leverage what's already deployed
3. **Durability** - Triggers must survive restarts
4. **Queryability** - "What NVDA alerts do I have?"
5. **LLM-Controllable** - Annie manages her own triggers

---

## 5. Trade-offs and Decision Factors

### Key Trade-offs

| Trade-off | Chosen Path | Sacrifice | Mitigation |
|-----------|-------------|-----------|------------|
| **Storage Location** | Agentic-memories | Extra API hop | Local cache in Redis for hot triggers |
| **Scheduler** | Arq (separate worker) | Process complexity | Docker Compose orchestration |
| **Rule Engine** | Custom Python | No library support | Keep rules simple, well-tested |
| **Real-time Data** | yfinance (delayed) | 15-20 min lag | Acceptable for swing trading signals |

### Why Not Alternatives?

**Why not Temporal.io?**
- Overkill for 1-10 users
- Significant operational overhead
- Learning curve not justified

**Why not Celery?**
- Too heavy for the use case
- Complex broker setup
- Designed for distributed systems

**Why not store triggers in Annie's Redis?**
- No audit trail
- Limited query capabilities
- Can't answer "which signals were profitable?"

---

## 6. Real-World Evidence

### Proactive AI Patterns in 2025

Based on research, successful proactive AI implementations share these characteristics:

1. **Event-Driven Architecture** - Triggers fire on events, not polling
2. **Subconscious Filter** - Cheap/fast gate before expensive LLM calls
3. **Context Injection** - Proactive messages include relevant history
4. **Spam Prevention** - Cooldowns, quiet hours, significance thresholds

**Industry Examples:**
- Meta's proactive AI chatbots initiate contact based on user behavior patterns
- Trading platforms use event-driven alerts with configurable thresholds
- Health apps use time-based and inactivity triggers for check-ins

**Sources:**
- [Meta's Proactive AI](https://www.justthink.ai/blog/metas-proactive-ai-chatbots-that-message-you-first-redefine-digital-engagement)
- [Proactive Chatbot Engagement](https://www.visiativ.com/en/actualites/news/choose-a-proactive-chatbot/)

---

## 7. Architecture Pattern Analysis

### Stimulus-Response Architecture

The recommended architecture follows a four-layer stimulus-response pattern:

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 1: STIMULUS (Triggers)                                   │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐   │
│  │  Time   │ │  Price  │ │ Silence │ │  Event  │ │ Calendar│   │
│  │  (cron) │ │ (NVDA<X)│ │ (48h)   │ │ (news)  │ │ (meeting│   │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘   │
│       └──────────┬┴──────────┬┴──────────┬┴──────────┬┘         │
└──────────────────┼───────────────────────────────────┼──────────┘
                   ▼                                   │
┌──────────────────────────────────────────────────────┼──────────┐
│  LAYER 2: SUBCONSCIOUS (Filter/Gate)                 │          │
│  ┌─────────────────────────────────────────────────┐ │          │
│  │  Should I bother them?                          │ │          │
│  │  ├── Cooldown check (last proactive msg > 2h?)  │ │          │
│  │  ├── Active conversation? (last msg < 30 min?)  │ │          │
│  │  ├── Quiet hours? (10pm-7am?)                   │ │          │
│  │  ├── Daily limit reached? (max 5-10/day)        │ │          │
│  │  └── Significance threshold met?                │ │          │
│  └─────────────────────────────────────────────────┘ │          │
│       │ PASS                          │ BLOCK        │          │
│       ▼                               ▼              │          │
│    Continue                      Log & Skip          │          │
└───────┼──────────────────────────────────────────────┼──────────┘
        ▼                                              │
┌───────────────────────────────────────────────────────┼─────────┐
│  LAYER 3: CONSCIOUS (LLM Generation)                  │         │
│  ┌──────────────────────────────────────────────────┐ │         │
│  │  Initiator Mode Prompt:                          │ │         │
│  │  "You are INITIATING contact, not responding.   │ │         │
│  │   Context: {trigger_context}                    │ │         │
│  │   Last spoke: {hours_ago} hours ago             │ │         │
│  │   Be natural, brief, conversational."           │ │         │
│  └──────────────────────────────────────────────────┘ │         │
└───────┼─────────────────────────────────────────────────────────┘
        ▼
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 4: DELIVERY                                              │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │  Telegram Bot send_message(user_id, generated_text)         ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
```

### Component Ownership

```
┌─────────────────────────────────────────────────────────────────┐
│                         ANNIE BACKEND                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  MCP Tools (LLM-Callable)                                 │  │
│  │  ├── create_trigger() ──► POST /v1/intents                │  │
│  │  ├── list_triggers()  ──► GET  /v1/intents                │  │
│  │  ├── update_trigger() ──► PUT  /v1/intents/{id}           │  │
│  │  └── delete_trigger() ──► DELETE /v1/intents/{id}         │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Background Worker (Arq)                                  │  │
│  │  ├── Poll: GET /v1/intents/pending (every 30-60s)         │  │
│  │  ├── Evaluate conditions (price checks via yfinance)      │  │
│  │  ├── Subconscious Gate (spam prevention logic)            │  │
│  │  ├── LLM Generation (initiator mode)                      │  │
│  │  ├── Telegram Delivery                                    │  │
│  │  └── Report: POST /v1/intents/{id}/fire                   │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Subconscious Gate (Python module)                        │  │
│  │  ├── get_user_state() from Redis                          │  │
│  │  ├── check_cooldown()                                     │  │
│  │  ├── check_quiet_hours()                                  │  │
│  │  ├── check_daily_limit()                                  │  │
│  │  └── check_significance()                                 │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      AGENTIC-MEMORIES                           │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  PostgreSQL: scheduled_intents table                      │  │
│  │  ├── Trigger definitions (type, condition, context)       │  │
│  │  ├── Schedule management (next_check, last_executed)      │  │
│  │  ├── Execution history (audit trail)                      │  │
│  │  └── State transitions (on /fire endpoint)                │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  API Endpoints                                            │  │
│  │  ├── POST   /v1/intents           Create trigger          │  │
│  │  ├── GET    /v1/intents           List triggers           │  │
│  │  ├── GET    /v1/intents/pending   Due triggers            │  │
│  │  ├── PUT    /v1/intents/{id}      Update trigger          │  │
│  │  ├── DELETE /v1/intents/{id}      Delete trigger          │  │
│  │  ├── POST   /v1/intents/{id}/fire Mark as executed        │  │
│  │  └── GET    /v1/intents/{id}/history Execution log        │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  State Management (owned by agentic-memories)             │  │
│  │  ├── Calculate next_check based on trigger type           │  │
│  │  ├── Update last_executed on fire                         │  │
│  │  ├── Increment execution_count                            │  │
│  │  ├── Disable one-time triggers after fire                 │  │
│  │  └── Log to execution_history table                       │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 8. Detailed Design

### 8.1 Database Schema (Agentic-Memories PostgreSQL)

#### Primary Table: `scheduled_intents`

```sql
-- Migration: 010_scheduled_intents.up.sql

CREATE TABLE scheduled_intents (
    -- Identity
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    intent_name VARCHAR(256) NOT NULL,
    description TEXT,

    -- Trigger Definition
    trigger_type VARCHAR(32) NOT NULL,      -- 'cron', 'interval', 'once', 'price', 'silence', 'event'
    trigger_schedule JSONB,                  -- For time-based: {"cron": "0 9 * * 1"} or {"interval_minutes": 60}
    trigger_condition JSONB,                 -- For event-based: {"ticker": "NVDA", "operator": "<", "value": 130}

    -- Action Configuration
    action_type VARCHAR(64) DEFAULT 'notify', -- 'notify', 'check_in', 'briefing', 'analysis'
    action_context TEXT,                      -- "NVDA buy opportunity" - passed to LLM
    action_priority VARCHAR(16) DEFAULT 'normal', -- 'low', 'normal', 'high', 'critical'

    -- Scheduling State (OWNED BY AGENTIC-MEMORIES)
    next_check TIMESTAMPTZ,                  -- When to next EVALUATE this trigger
    last_checked TIMESTAMPTZ,                -- When condition was last evaluated
    last_executed TIMESTAMPTZ,               -- When trigger last FIRED (message sent)
    execution_count INT DEFAULT 0,           -- Total times fired

    -- Execution Results
    last_execution_status VARCHAR(32),       -- 'success', 'failed', 'skipped', 'gate_blocked'
    last_execution_error TEXT,               -- Error message if failed
    last_message_id VARCHAR(128),            -- Telegram message ID for reference

    -- Control
    enabled BOOLEAN DEFAULT true,
    expires_at TIMESTAMPTZ,                  -- Optional: auto-disable after this time
    max_executions INT,                      -- Optional: disable after N fires

    -- Audit
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by VARCHAR(64),                  -- 'user', 'llm', 'system'

    -- Flexible metadata
    metadata JSONB DEFAULT '{}',

    -- Constraints
    CONSTRAINT chk_trigger_type CHECK (
        trigger_type IN ('cron', 'interval', 'once', 'price', 'silence', 'event', 'calendar', 'news')
    ),
    CONSTRAINT chk_action_type CHECK (
        action_type IN ('notify', 'check_in', 'briefing', 'analysis', 'reminder')
    ),
    CONSTRAINT chk_priority CHECK (
        action_priority IN ('low', 'normal', 'high', 'critical')
    )
);

-- Indexes for efficient querying
CREATE INDEX idx_intents_user_enabled
    ON scheduled_intents (user_id, enabled)
    WHERE enabled = true;

CREATE INDEX idx_intents_pending
    ON scheduled_intents (next_check)
    WHERE enabled = true AND next_check IS NOT NULL;

CREATE INDEX idx_intents_type
    ON scheduled_intents (user_id, trigger_type);

CREATE INDEX idx_intents_created
    ON scheduled_intents (created_at DESC);

-- Trigger for updated_at
CREATE TRIGGER update_scheduled_intents_updated_at
    BEFORE UPDATE ON scheduled_intents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
```

#### Execution History Table: `intent_executions`

```sql
-- Track every execution attempt for audit and analytics

CREATE TABLE intent_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    intent_id UUID NOT NULL REFERENCES scheduled_intents(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,

    -- Execution Details
    executed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    trigger_type VARCHAR(32) NOT NULL,
    trigger_data JSONB,                      -- Snapshot of condition at execution time

    -- Result
    status VARCHAR(32) NOT NULL,             -- 'success', 'failed', 'gate_blocked', 'condition_not_met'
    gate_result JSONB,                       -- {"passed": false, "reason": "cooldown", "details": {...}}

    -- Message Details (if sent)
    message_id VARCHAR(128),                 -- Telegram message ID
    message_preview TEXT,                    -- First 200 chars of generated message

    -- Performance
    evaluation_ms INT,                       -- Time to evaluate condition
    generation_ms INT,                       -- Time for LLM generation
    delivery_ms INT,                         -- Time to send via Telegram

    -- Error tracking
    error_message TEXT,
    error_stack TEXT,

    -- Context snapshot
    context_snapshot JSONB                   -- User state at execution time
);

CREATE INDEX idx_executions_intent
    ON intent_executions (intent_id, executed_at DESC);

CREATE INDEX idx_executions_user
    ON intent_executions (user_id, executed_at DESC);

CREATE INDEX idx_executions_status
    ON intent_executions (status, executed_at DESC);
```

### 8.2 Trigger Type Definitions

| Type | `trigger_schedule` | `trigger_condition` | `next_check` Calculation |
|------|-------------------|---------------------|--------------------------|
| **cron** | `{"cron": "0 9 * * 1-5"}` | null | Parse cron, get next occurrence |
| **interval** | `{"interval_minutes": 240}` | null | `now() + interval` |
| **once** | `{"datetime": "2025-12-25T09:00:00Z"}` | null | The specified datetime, then null |
| **price** | `{"check_interval_minutes": 1}` | `{"ticker": "NVDA", "op": "<", "value": 130}` | `now() + check_interval` |
| **silence** | `{"threshold_hours": 48}` | null | `last_user_interaction + threshold` |
| **event** | `{"source": "news", "check_interval": 15}` | `{"keywords": ["NVDA", "Fed"]}` | `now() + check_interval` |
| **calendar** | `{"minutes_before": 30}` | `{"event_type": "meeting"}` | Next calendar event - minutes_before |

### 8.3 How `/pending` Works (The Scheduling Engine)

The `/v1/intents/pending` endpoint is intentionally simple - just a database query:

```sql
SELECT * FROM scheduled_intents
WHERE enabled = true
  AND next_check <= NOW()
ORDER BY next_check ASC;
```

**No complex logic. No scheduler. Just a filtered query.**

Annie's worker polls this endpoint every 30 seconds. Agentic-memories doesn't "push" - it just answers "which triggers are due?"

#### The `next_check` Lifecycle

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        next_check LIFECYCLE                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  1. CREATE TRIGGER                                                          │
│     └── Agentic-memories calculates initial next_check:                     │
│         ├── cron "0 9 * * *"     → 2025-12-22 09:00:00 (next occurrence)    │
│         ├── interval 60 min      → NOW() + 60 minutes                       │
│         ├── once "Dec 25 9am"    → 2025-12-25 09:00:00                      │
│         ├── price (NVDA < 130)   → NOW() + 1 minute (check_interval)        │
│         └── silence (48h)        → NOW() + 5 minutes                        │
│                                                                             │
│  2. ANNIE POLLS /pending                                                    │
│     └── Returns triggers WHERE next_check <= NOW() AND enabled = true       │
│                                                                             │
│  3. ANNIE EVALUATES & FIRES                                                 │
│     └── POST /fire with result: success | condition_not_met | gate_blocked  │
│                                                                             │
│  4. AGENTIC-MEMORIES UPDATES next_check                                     │
│     └── Based on trigger type and result:                                   │
│                                                                             │
│         ┌─────────────────┬──────────────────────────────────────────────┐  │
│         │ Result          │ next_check calculation                       │  │
│         ├─────────────────┼──────────────────────────────────────────────┤  │
│         │ success (cron)  │ croniter.get_next() → next cron occurrence   │  │
│         │ success (interval)│ NOW() + interval_minutes                   │  │
│         │ success (once)  │ NULL + enabled=false (done!)                 │  │
│         │ success (price) │ NOW() + check_interval (keep checking)       │  │
│         │ condition_not_met│ NOW() + 5 minutes (retry soon)              │  │
│         │ gate_blocked    │ NOW() + 5 minutes (retry soon)               │  │
│         │ failed          │ NOW() + 15 minutes (backoff)                 │  │
│         └─────────────────┴──────────────────────────────────────────────┘  │
│                                                                             │
│  5. ANNIE POLLS /pending AGAIN                                              │
│     └── Trigger not returned (next_check is in future)                      │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### Example Timeline: Daily Cron

```
Day 1, 09:00:00  Trigger created (cron: "0 9 * * *")
                 next_check = 2025-12-22 09:00:00 (tomorrow)

Day 2, 08:59:30  Annie polls /pending → Empty (not due yet)

Day 2, 09:00:30  Annie polls /pending → Returns trigger (next_check <= NOW)

Day 2, 09:00:32  Annie evaluates, generates, sends to Telegram
                 POST /fire {status: "success"}

Day 2, 09:00:32  Agentic-memories updates:
                 ├── last_executed = 2025-12-22 09:00:32
                 ├── execution_count = 1
                 └── next_check = 2025-12-23 09:00:00 (tomorrow)

Day 2, 09:01:00  Annie polls /pending → Empty (next_check is tomorrow)
```

#### Example Timeline: Price Alert

```
10:00:00  Trigger created (price: NVDA < 130, check_interval: 1 min)
          next_check = 10:01:00

10:01:00  Annie polls, evaluates NVDA = $145 → condition NOT met
          POST /fire {status: "condition_not_met"}
          next_check = 10:06:00 (retry in 5 min)

10:06:00  Annie polls, evaluates NVDA = $142 → condition NOT met
          next_check = 10:11:00

10:11:00  Annie polls, evaluates NVDA = $128 → condition MET!
          Gate passes, LLM generates "NVDA dropped below $130!"
          POST /fire {status: "success"}
          next_check = 10:12:00 (keep checking - might want to alert again)

          Note: Subconscious gate will block for 2 hours after success
```

### 8.4 State Ownership Model

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STATE OWNERSHIP                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────┐    ┌─────────────────────────────────┐│
│  │         ANNIE OWNS              │    │     AGENTIC-MEMORIES OWNS       ││
│  ├─────────────────────────────────┤    ├─────────────────────────────────┤│
│  │                                 │    │                                 ││
│  │  • Polling pending intents      │    │  • Trigger definitions          ││
│  │  • Evaluating conditions        │    │  • next_check calculation       ││
│  │    (yfinance price checks)      │    │  • last_executed timestamp      ││
│  │  • Subconscious gate logic      │    │  • last_checked timestamp       ││
│  │  • LLM generation               │    │  • execution_count              ││
│  │  • Telegram delivery            │    │  • Disabling one-time triggers  ││
│  │  • User state in Redis          │    │  • Execution history logging    ││
│  │    (last_interaction,           │    │  • Audit trail                  ││
│  │     proactive_msg_count)        │    │                                 ││
│  │                                 │    │                                 ││
│  └─────────────────────────────────┘    └─────────────────────────────────┘│
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐│
│  │                         INTERACTION FLOW                                ││
│  ├─────────────────────────────────────────────────────────────────────────┤│
│  │                                                                         ││
│  │  1. Annie Worker: GET /v1/intents/pending                               ││
│  │     └─► Returns intents where next_check <= NOW() AND enabled = true    ││
│  │                                                                         ││
│  │  2. Annie: Evaluate each trigger's condition                            ││
│  │     └─► Price triggers: check yfinance                                  ││
│  │     └─► Silence triggers: check last_interaction from Redis             ││
│  │     └─► Time triggers: condition already met (next_check passed)        ││
│  │                                                                         ││
│  │  3. Annie: Run through Subconscious Gate                                ││
│  │     └─► If blocked: POST /v1/intents/{id}/fire {status: "gate_blocked"} ││
│  │     └─► If passed: continue to LLM                                      ││
│  │                                                                         ││
│  │  4. Annie: Generate message with LLM (initiator mode)                   ││
│  │                                                                         ││
│  │  5. Annie: Send via Telegram                                            ││
│  │                                                                         ││
│  │  6. Annie: POST /v1/intents/{id}/fire                                   ││
│  │     └─► Body: {status: "success", message_id: "123", trigger_data: {}}  ││
│  │                                                                         ││
│  │  7. Agentic-Memories: Process /fire request                             ││
│  │     └─► Update last_executed = NOW()                                    ││
│  │     └─► Update last_checked = NOW()                                     ││
│  │     └─► Increment execution_count                                       ││
│  │     └─► Calculate next_check based on trigger_type                      ││
│  │     └─► If one-time and fired: enabled = false, next_check = null       ││
│  │     └─► If max_executions reached: enabled = false                      ││
│  │     └─► Log to intent_executions table                                  ││
│  │                                                                         ││
│  └─────────────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.4 API Design (Agentic-Memories)

#### Request/Response Models

```python
# schemas.py additions

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime
from uuid import UUID

class TriggerSchedule(BaseModel):
    """Time-based trigger configuration"""
    cron: Optional[str] = None                    # "0 9 * * 1-5"
    interval_minutes: Optional[int] = None        # 60
    datetime: Optional[datetime] = None           # For one-time
    check_interval_minutes: Optional[int] = 1     # For event-based polling

class TriggerCondition(BaseModel):
    """Event-based trigger condition"""
    ticker: Optional[str] = None                  # "NVDA"
    operator: Optional[Literal["<", ">", "<=", ">=", "==", "!="]] = None
    value: Optional[float] = None                 # 130.0
    keywords: Optional[list[str]] = None          # ["Fed", "rate"]
    threshold_hours: Optional[int] = None         # For silence detection

class ScheduledIntentCreate(BaseModel):
    """Create a new scheduled intent"""
    user_id: str
    intent_name: str
    description: Optional[str] = None

    trigger_type: Literal["cron", "interval", "once", "price", "silence", "event", "calendar", "news"]
    trigger_schedule: Optional[TriggerSchedule] = None
    trigger_condition: Optional[TriggerCondition] = None

    action_type: Literal["notify", "check_in", "briefing", "analysis", "reminder"] = "notify"
    action_context: str                           # "NVDA buy opportunity"
    action_priority: Literal["low", "normal", "high", "critical"] = "normal"

    expires_at: Optional[datetime] = None
    max_executions: Optional[int] = None
    metadata: Optional[dict] = None

class ScheduledIntentResponse(BaseModel):
    """Response for scheduled intent"""
    id: UUID
    user_id: str
    intent_name: str
    description: Optional[str]

    trigger_type: str
    trigger_schedule: Optional[dict]
    trigger_condition: Optional[dict]

    action_type: str
    action_context: str
    action_priority: str

    next_check: Optional[datetime]
    last_checked: Optional[datetime]
    last_executed: Optional[datetime]
    execution_count: int

    enabled: bool
    created_at: datetime
    updated_at: datetime

class ScheduledIntentUpdate(BaseModel):
    """Update an existing intent"""
    intent_name: Optional[str] = None
    description: Optional[str] = None
    trigger_schedule: Optional[TriggerSchedule] = None
    trigger_condition: Optional[TriggerCondition] = None
    action_context: Optional[str] = None
    action_priority: Optional[str] = None
    enabled: Optional[bool] = None
    expires_at: Optional[datetime] = None
    max_executions: Optional[int] = None

class IntentFireRequest(BaseModel):
    """Report intent execution from Annie"""
    status: Literal["success", "failed", "gate_blocked", "condition_not_met"]
    message_id: Optional[str] = None              # Telegram message ID
    message_preview: Optional[str] = None         # First 200 chars
    trigger_data: Optional[dict] = None           # Snapshot of trigger state
    gate_result: Optional[dict] = None            # Gate decision details
    error_message: Optional[str] = None
    evaluation_ms: Optional[int] = None
    generation_ms: Optional[int] = None
    delivery_ms: Optional[int] = None

class IntentFireResponse(BaseModel):
    """Response after firing an intent"""
    id: UUID
    next_check: Optional[datetime]                # Calculated by agentic-memories
    enabled: bool                                 # May be disabled if one-time
    execution_count: int
```

#### API Endpoints

```python
# app.py additions

from croniter import croniter
from datetime import timedelta

# ============================================================
# INPUT VALIDATION (Guardrails without over-engineering)
# ============================================================

LIMITS = {
    "max_triggers_per_user": 25,           # Don't let trigger list get unmanageable
    "min_cron_interval_seconds": 60,       # 1 minute minimum
    "min_interval_minutes": 5,             # 5 minute minimum for interval type
    "min_check_interval_minutes": 1,       # 1 minute for price/event checks
    "max_cron_fires_per_day": 96,          # ~every 15 min max for cron
}

async def validate_intent_create(body: ScheduledIntentCreate, user_id: str):
    """
    Sensible guardrails without over-engineering.
    Catches obvious mistakes at creation time.
    Runtime protection handled by Annie's subconscious gate.
    """
    errors = []

    # 1. Max triggers per user
    existing = await db.count(ScheduledIntent, user_id=user_id, enabled=True)
    if existing >= LIMITS["max_triggers_per_user"]:
        errors.append(f"Limit reached: {LIMITS['max_triggers_per_user']} active triggers max")

    # 2. Validate cron frequency
    if body.trigger_type == "cron" and body.trigger_schedule and body.trigger_schedule.cron:
        cron_expr = body.trigger_schedule.cron
        try:
            now = datetime.utcnow()
            cron = croniter(cron_expr, now)
            next1 = cron.get_next(datetime)
            next2 = cron.get_next(datetime)
            interval_sec = (next2 - next1).total_seconds()

            if interval_sec < LIMITS["min_cron_interval_seconds"]:
                errors.append(f"Cron too frequent: every {interval_sec}s. Minimum: 60s")

            # Estimate daily fires
            daily_fires = 86400 / interval_sec
            if daily_fires > LIMITS["max_cron_fires_per_day"]:
                errors.append(f"Cron would fire {int(daily_fires)}x/day. Max: {LIMITS['max_cron_fires_per_day']}")

        except Exception as e:
            errors.append(f"Invalid cron expression: {cron_expr}")

    # 3. Validate interval minimum
    if body.trigger_type == "interval" and body.trigger_schedule:
        interval_min = body.trigger_schedule.interval_minutes or 0
        if interval_min < LIMITS["min_interval_minutes"]:
            errors.append(f"Interval too short: {interval_min}m. Minimum: {LIMITS['min_interval_minutes']}m")

    # 4. Validate check_interval for event-based
    if body.trigger_type in ("price", "event", "news") and body.trigger_schedule:
        check_min = body.trigger_schedule.check_interval_minutes or 1
        if check_min < LIMITS["min_check_interval_minutes"]:
            errors.append(f"Check interval too short: {check_min}m. Minimum: {LIMITS['min_check_interval_minutes']}m")

    # 5. Validate one-time is in the future
    if body.trigger_type == "once" and body.trigger_schedule and body.trigger_schedule.datetime:
        if body.trigger_schedule.datetime <= datetime.utcnow():
            errors.append("One-time trigger must be in the future")

    # 6. Required fields by type
    if body.trigger_type in ("cron", "interval", "once") and not body.trigger_schedule:
        errors.append(f"trigger_schedule required for type '{body.trigger_type}'")

    if body.trigger_type == "price" and not body.trigger_condition:
        errors.append("trigger_condition required for price triggers")

    if body.trigger_type == "price" and body.trigger_condition:
        if not body.trigger_condition.ticker:
            errors.append("ticker required for price triggers")
        if body.trigger_condition.value is None:
            errors.append("value required for price triggers")

    # 7. Validate action_context isn't empty
    if not body.action_context or len(body.action_context.strip()) < 5:
        errors.append("action_context required (minimum 5 characters)")

    if errors:
        raise HTTPException(status_code=400, detail={"errors": errors})


# Validation catches these bad inputs:
# | Check              | Example Bad Input        | Error                                      |
# |--------------------|--------------------------|-------------------------------------------|
# | Too many triggers  | User has 25 active       | "Limit reached: 25 active triggers max"   |
# | Cron too fast      | `* * * * * *` (every sec)| "Cron too frequent: every 1s. Min: 60s"   |
# | Cron too chatty    | `* * * * *` (every min)  | "Cron would fire 1440x/day. Max: 96"      |
# | Bad cron syntax    | `not a cron`             | "Invalid cron expression"                 |
# | Interval too short | 1 minute                 | "Interval too short: 1m. Minimum: 5m"     |
# | Past one-time      | Yesterday                | "One-time trigger must be in the future"  |
# | Missing schedule   | Cron with no schedule    | "trigger_schedule required"               |
# | Missing ticker     | Price with no ticker     | "ticker required for price triggers"      |
# | Empty context      | ""                       | "action_context required"                 |


# ============================================================
# SCHEDULED INTENTS API
# ============================================================

@app.post("/v1/intents", response_model=ScheduledIntentResponse, tags=["Intents"])
async def create_intent(body: ScheduledIntentCreate) -> ScheduledIntentResponse:
    """
    Create a new scheduled intent.

    Called by Annie's LLM via create_trigger() tool.
    Agentic-memories calculates initial next_check.
    """
    # Validate input first
    await validate_intent_create(body, body.user_id)

    intent = ScheduledIntent(
        user_id=body.user_id,
        intent_name=body.intent_name,
        description=body.description,
        trigger_type=body.trigger_type,
        trigger_schedule=body.trigger_schedule.dict() if body.trigger_schedule else None,
        trigger_condition=body.trigger_condition.dict() if body.trigger_condition else None,
        action_type=body.action_type,
        action_context=body.action_context,
        action_priority=body.action_priority,
        expires_at=body.expires_at,
        max_executions=body.max_executions,
        metadata=body.metadata or {},
        enabled=True,
        next_check=calculate_next_check(body.trigger_type, body.trigger_schedule),
        created_by="llm"
    )

    await db.save(intent)
    return intent


@app.get("/v1/intents", response_model=list[ScheduledIntentResponse], tags=["Intents"])
async def list_intents(
    user_id: str,
    enabled: Optional[bool] = None,
    trigger_type: Optional[str] = None,
    limit: int = 50
) -> list[ScheduledIntentResponse]:
    """
    List all intents for a user.

    Called by Annie's LLM via list_triggers() tool.
    """
    query = select(ScheduledIntent).where(ScheduledIntent.user_id == user_id)

    if enabled is not None:
        query = query.where(ScheduledIntent.enabled == enabled)
    if trigger_type:
        query = query.where(ScheduledIntent.trigger_type == trigger_type)

    query = query.order_by(ScheduledIntent.created_at.desc()).limit(limit)

    return await db.fetch_all(query)


@app.get("/v1/intents/pending", response_model=list[ScheduledIntentResponse], tags=["Intents"])
async def get_pending_intents(user_id: Optional[str] = None) -> list[ScheduledIntentResponse]:
    """
    Get intents due for evaluation.

    Called by Annie's background worker every 30-60 seconds.
    Returns intents where next_check <= NOW() AND enabled = true.
    """
    query = select(ScheduledIntent).where(
        ScheduledIntent.enabled == True,
        ScheduledIntent.next_check <= datetime.utcnow()
    )

    if user_id:
        query = query.where(ScheduledIntent.user_id == user_id)

    query = query.order_by(ScheduledIntent.next_check.asc())

    return await db.fetch_all(query)


@app.get("/v1/intents/{intent_id}", response_model=ScheduledIntentResponse, tags=["Intents"])
async def get_intent(intent_id: UUID) -> ScheduledIntentResponse:
    """Get a specific intent by ID."""
    intent = await db.get(ScheduledIntent, intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")
    return intent


@app.put("/v1/intents/{intent_id}", response_model=ScheduledIntentResponse, tags=["Intents"])
async def update_intent(intent_id: UUID, body: ScheduledIntentUpdate) -> ScheduledIntentResponse:
    """
    Update an existing intent.

    Called by Annie's LLM via update_trigger() tool.
    Recalculates next_check if schedule changes.
    """
    intent = await db.get(ScheduledIntent, intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    # Apply updates
    update_data = body.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(intent, field, value)

    # Recalculate next_check if schedule changed
    if body.trigger_schedule:
        intent.next_check = calculate_next_check(
            intent.trigger_type,
            body.trigger_schedule
        )

    intent.updated_at = datetime.utcnow()
    await db.save(intent)

    return intent


@app.delete("/v1/intents/{intent_id}", tags=["Intents"])
async def delete_intent(intent_id: UUID) -> dict:
    """
    Delete an intent.

    Called by Annie's LLM via delete_trigger() tool.
    """
    intent = await db.get(ScheduledIntent, intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    await db.delete(intent)
    return {"status": "deleted", "id": str(intent_id)}


@app.post("/v1/intents/{intent_id}/fire", response_model=IntentFireResponse, tags=["Intents"])
async def fire_intent(intent_id: UUID, body: IntentFireRequest) -> IntentFireResponse:
    """
    Report intent execution from Annie.

    THIS IS THE KEY ENDPOINT - agentic-memories owns state transitions.

    Called by Annie after:
    1. Evaluating trigger condition
    2. Running through subconscious gate
    3. Generating message (if passed gate)
    4. Sending via Telegram (if successful)

    Agentic-memories then:
    1. Updates last_executed (if success)
    2. Updates last_checked (always)
    3. Increments execution_count (if success)
    4. Calculates next_check based on trigger type
    5. Disables one-time triggers after fire
    6. Logs to intent_executions table
    """
    intent = await db.get(ScheduledIntent, intent_id)
    if not intent:
        raise HTTPException(status_code=404, detail="Intent not found")

    now = datetime.utcnow()

    # Always update last_checked
    intent.last_checked = now

    # If successfully fired
    if body.status == "success":
        intent.last_executed = now
        intent.execution_count += 1
        intent.last_execution_status = "success"
        intent.last_message_id = body.message_id
    else:
        intent.last_execution_status = body.status
        intent.last_execution_error = body.error_message

    # Calculate next_check based on trigger type
    intent.next_check = calculate_next_check_after_fire(
        trigger_type=intent.trigger_type,
        trigger_schedule=intent.trigger_schedule,
        status=body.status
    )

    # Disable if one-time and fired successfully
    if intent.trigger_type == "once" and body.status == "success":
        intent.enabled = False
        intent.next_check = None

    # Disable if max_executions reached
    if intent.max_executions and intent.execution_count >= intent.max_executions:
        intent.enabled = False
        intent.next_check = None

    # Disable if expired
    if intent.expires_at and now > intent.expires_at:
        intent.enabled = False
        intent.next_check = None

    intent.updated_at = now
    await db.save(intent)

    # Log execution to history
    execution = IntentExecution(
        intent_id=intent_id,
        user_id=intent.user_id,
        trigger_type=intent.trigger_type,
        trigger_data=body.trigger_data,
        status=body.status,
        gate_result=body.gate_result,
        message_id=body.message_id,
        message_preview=body.message_preview,
        evaluation_ms=body.evaluation_ms,
        generation_ms=body.generation_ms,
        delivery_ms=body.delivery_ms,
        error_message=body.error_message
    )
    await db.save(execution)

    return IntentFireResponse(
        id=intent.id,
        next_check=intent.next_check,
        enabled=intent.enabled,
        execution_count=intent.execution_count
    )


@app.get("/v1/intents/{intent_id}/history", response_model=list[dict], tags=["Intents"])
async def get_intent_history(
    intent_id: UUID,
    limit: int = 50
) -> list[dict]:
    """Get execution history for an intent."""
    query = select(IntentExecution).where(
        IntentExecution.intent_id == intent_id
    ).order_by(
        IntentExecution.executed_at.desc()
    ).limit(limit)

    return await db.fetch_all(query)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def calculate_next_check(
    trigger_type: str,
    trigger_schedule: Optional[TriggerSchedule]
) -> Optional[datetime]:
    """Calculate initial next_check for a new intent."""
    now = datetime.utcnow()

    if trigger_type == "cron" and trigger_schedule and trigger_schedule.cron:
        return croniter(trigger_schedule.cron, now).get_next(datetime)

    elif trigger_type == "interval" and trigger_schedule and trigger_schedule.interval_minutes:
        return now + timedelta(minutes=trigger_schedule.interval_minutes)

    elif trigger_type == "once" and trigger_schedule and trigger_schedule.datetime:
        return trigger_schedule.datetime

    elif trigger_type in ("price", "event", "news"):
        # Check frequently for event-based triggers
        interval = trigger_schedule.check_interval_minutes if trigger_schedule else 1
        return now + timedelta(minutes=interval)

    elif trigger_type == "silence":
        # Will be evaluated against last_interaction from Redis
        return now + timedelta(minutes=5)  # Check every 5 minutes

    elif trigger_type == "calendar":
        # Requires calendar integration - placeholder
        return now + timedelta(minutes=15)

    return now + timedelta(minutes=1)  # Default: check in 1 minute


def calculate_next_check_after_fire(
    trigger_type: str,
    trigger_schedule: Optional[dict],
    status: str
) -> Optional[datetime]:
    """Calculate next_check after a fire event."""
    now = datetime.utcnow()

    # If gate blocked or condition not met, retry sooner
    if status in ("gate_blocked", "condition_not_met"):
        return now + timedelta(minutes=5)

    # If failed, back off a bit
    if status == "failed":
        return now + timedelta(minutes=15)

    # Success - calculate next based on type
    if trigger_type == "cron" and trigger_schedule and trigger_schedule.get("cron"):
        return croniter(trigger_schedule["cron"], now).get_next(datetime)

    elif trigger_type == "interval" and trigger_schedule:
        interval = trigger_schedule.get("interval_minutes", 60)
        return now + timedelta(minutes=interval)

    elif trigger_type == "once":
        return None  # Will be disabled

    elif trigger_type in ("price", "event", "news"):
        interval = trigger_schedule.get("check_interval_minutes", 1) if trigger_schedule else 1
        return now + timedelta(minutes=interval)

    elif trigger_type == "silence":
        return now + timedelta(minutes=5)

    return now + timedelta(minutes=1)
```

### 8.5 Annie Integration

#### MCP Tools for LLM

```python
# mcp_server/tools.py additions

@registry.register
def create_trigger(
    trigger_type: str,
    intent_name: str,
    action_context: str,
    trigger_schedule: Optional[dict] = None,
    trigger_condition: Optional[dict] = None,
    description: Optional[str] = None,
    action_priority: str = "normal",
    expires_at: Optional[str] = None,
    max_executions: Optional[int] = None
) -> dict:
    """
    Create a new trigger/scheduled intent.

    Args:
        trigger_type: One of 'cron', 'interval', 'once', 'price', 'silence', 'event'
        intent_name: Human-readable name for this trigger
        action_context: Context passed to LLM when trigger fires (e.g., "NVDA buy opportunity")
        trigger_schedule: For time-based triggers: {"cron": "0 9 * * 1"} or {"interval_minutes": 60}
        trigger_condition: For event triggers: {"ticker": "NVDA", "operator": "<", "value": 130}
        description: Optional longer description
        action_priority: 'low', 'normal', 'high', or 'critical'
        expires_at: ISO datetime when trigger auto-disables
        max_executions: Max times to fire before auto-disable

    Examples:
        # Daily morning briefing
        create_trigger(
            trigger_type="cron",
            intent_name="Morning Market Briefing",
            trigger_schedule={"cron": "0 9 * * 1-5"},
            action_context="Provide morning market briefing"
        )

        # Price alert
        create_trigger(
            trigger_type="price",
            intent_name="NVDA Buy Alert",
            trigger_condition={"ticker": "NVDA", "operator": "<", "value": 130},
            action_context="NVDA has dropped below target entry price",
            action_priority="high"
        )

        # One-time reminder
        create_trigger(
            trigger_type="once",
            intent_name="Check RKLB Earnings",
            trigger_schedule={"datetime": "2025-12-24T16:00:00Z"},
            action_context="Reminder to check RKLB earnings report"
        )
    """
    response = requests.post(
        f"{AGENTIC_MEMORIES_URL}/v1/intents",
        json={
            "user_id": get_current_user_id(),
            "intent_name": intent_name,
            "description": description,
            "trigger_type": trigger_type,
            "trigger_schedule": trigger_schedule,
            "trigger_condition": trigger_condition,
            "action_type": "notify",
            "action_context": action_context,
            "action_priority": action_priority,
            "expires_at": expires_at,
            "max_executions": max_executions
        }
    )
    return response.json()


@registry.register
def list_triggers(
    enabled_only: bool = True,
    trigger_type: Optional[str] = None
) -> dict:
    """
    List all triggers for the current user.

    Args:
        enabled_only: If True, only return active triggers
        trigger_type: Filter by type ('cron', 'price', etc.)

    Returns:
        List of triggers with their status and next scheduled check time.
    """
    params = {"user_id": get_current_user_id()}
    if enabled_only:
        params["enabled"] = True
    if trigger_type:
        params["trigger_type"] = trigger_type

    response = requests.get(
        f"{AGENTIC_MEMORIES_URL}/v1/intents",
        params=params
    )
    return response.json()


@registry.register
def update_trigger(
    trigger_id: str,
    intent_name: Optional[str] = None,
    trigger_schedule: Optional[dict] = None,
    trigger_condition: Optional[dict] = None,
    action_context: Optional[str] = None,
    enabled: Optional[bool] = None
) -> dict:
    """
    Update an existing trigger.

    Args:
        trigger_id: UUID of the trigger to update
        intent_name: New name (optional)
        trigger_schedule: New schedule (optional)
        trigger_condition: New condition (optional)
        action_context: New context (optional)
        enabled: Enable/disable (optional)

    Example:
        # Change price target
        update_trigger(
            trigger_id="abc-123",
            trigger_condition={"ticker": "NVDA", "operator": "<", "value": 125}
        )
    """
    body = {}
    if intent_name:
        body["intent_name"] = intent_name
    if trigger_schedule:
        body["trigger_schedule"] = trigger_schedule
    if trigger_condition:
        body["trigger_condition"] = trigger_condition
    if action_context:
        body["action_context"] = action_context
    if enabled is not None:
        body["enabled"] = enabled

    response = requests.put(
        f"{AGENTIC_MEMORIES_URL}/v1/intents/{trigger_id}",
        json=body
    )
    return response.json()


@registry.register
def delete_trigger(trigger_id: str) -> dict:
    """
    Delete a trigger.

    Args:
        trigger_id: UUID of the trigger to delete
    """
    response = requests.delete(
        f"{AGENTIC_MEMORIES_URL}/v1/intents/{trigger_id}"
    )
    return response.json()
```

#### Background Worker (Arq)

```python
# backend/worker.py

import asyncio
from arq import create_pool, cron
from arq.connections import RedisSettings
from datetime import datetime, timedelta
import httpx
import yfinance as yf

from api.config import get_config
from api.llm_client import get_llm_client
from api.telegram_client import send_telegram_message

config = get_config()

AGENTIC_MEMORIES_URL = config["AGENTIC_MEMORIES_URL"]
REDIS_HOST = config["REDIS_HOST"]
REDIS_PORT = config["REDIS_PORT"]


# ============================================================
# SUBCONSCIOUS GATE
# ============================================================

async def should_initiate_contact(user_id: str, intent: dict, redis) -> tuple[bool, dict]:
    """
    The 'Should I bother them?' gate.

    Returns (should_proceed, gate_result_details)
    """
    now = datetime.utcnow()
    gate_result = {"passed": True, "checks": {}}

    # Get user state from Redis
    last_interaction = await redis.get(f"user:{user_id}:last_interaction")
    last_proactive = await redis.get(f"user:{user_id}:last_proactive")
    daily_count = await redis.get(f"user:{user_id}:proactive_count:{now.date()}")

    # Parse timestamps
    if last_interaction:
        last_interaction = datetime.fromisoformat(last_interaction.decode())
    if last_proactive:
        last_proactive = datetime.fromisoformat(last_proactive.decode())
    daily_count = int(daily_count or 0)

    # Check 1: Cooldown since last proactive message (2 hours)
    if last_proactive:
        hours_since_proactive = (now - last_proactive).total_seconds() / 3600
        if hours_since_proactive < 2:
            gate_result["passed"] = False
            gate_result["reason"] = "cooldown"
            gate_result["checks"]["cooldown"] = {
                "passed": False,
                "hours_since": round(hours_since_proactive, 2),
                "required": 2
            }
            return False, gate_result
        gate_result["checks"]["cooldown"] = {"passed": True}

    # Check 2: Don't interrupt active conversations (30 min)
    if last_interaction:
        mins_since_interaction = (now - last_interaction).total_seconds() / 60
        if mins_since_interaction < 30:
            gate_result["passed"] = False
            gate_result["reason"] = "active_conversation"
            gate_result["checks"]["active_conversation"] = {
                "passed": False,
                "mins_since": round(mins_since_interaction, 2),
                "required": 30
            }
            return False, gate_result
        gate_result["checks"]["active_conversation"] = {"passed": True}

    # Check 3: Daily limit (max 10 proactive messages)
    max_daily = 10
    if daily_count >= max_daily:
        gate_result["passed"] = False
        gate_result["reason"] = "daily_limit"
        gate_result["checks"]["daily_limit"] = {
            "passed": False,
            "current": daily_count,
            "max": max_daily
        }
        return False, gate_result
    gate_result["checks"]["daily_limit"] = {"passed": True, "current": daily_count}

    # Check 4: Quiet hours (10pm - 7am) unless critical
    user_hour = now.hour  # TODO: Convert to user's timezone
    is_quiet_hours = user_hour >= 22 or user_hour < 7
    is_critical = intent.get("action_priority") == "critical"

    if is_quiet_hours and not is_critical:
        gate_result["passed"] = False
        gate_result["reason"] = "quiet_hours"
        gate_result["checks"]["quiet_hours"] = {
            "passed": False,
            "current_hour": user_hour,
            "is_critical": is_critical
        }
        return False, gate_result
    gate_result["checks"]["quiet_hours"] = {"passed": True}

    return True, gate_result


# ============================================================
# CONDITION EVALUATORS
# ============================================================

async def evaluate_condition(intent: dict) -> tuple[bool, dict]:
    """
    Evaluate trigger condition.

    Returns (condition_met, trigger_data_snapshot)
    """
    trigger_type = intent["trigger_type"]
    condition = intent.get("trigger_condition") or {}
    trigger_data = {}

    if trigger_type in ("cron", "interval", "once"):
        # Time-based triggers: condition is met if we're past next_check
        return True, {"type": "time_based", "scheduled": intent["next_check"]}

    elif trigger_type == "price":
        ticker = condition.get("ticker")
        operator = condition.get("operator", "<")
        target = condition.get("value")

        if not ticker or target is None:
            return False, {"error": "Missing ticker or value"}

        # Fetch current price
        try:
            stock = yf.Ticker(ticker)
            current_price = stock.info.get("regularMarketPrice") or stock.info.get("currentPrice")

            trigger_data = {
                "ticker": ticker,
                "current_price": current_price,
                "target": target,
                "operator": operator
            }

            # Evaluate condition
            if operator == "<" and current_price < target:
                return True, trigger_data
            elif operator == ">" and current_price > target:
                return True, trigger_data
            elif operator == "<=" and current_price <= target:
                return True, trigger_data
            elif operator == ">=" and current_price >= target:
                return True, trigger_data
            elif operator == "==" and abs(current_price - target) < 0.01:
                return True, trigger_data

            return False, trigger_data

        except Exception as e:
            return False, {"error": str(e)}

    elif trigger_type == "silence":
        threshold_hours = condition.get("threshold_hours", 48)
        # This would check last_interaction from Redis
        # For now, return True to demonstrate
        return True, {"threshold_hours": threshold_hours}

    # Default: condition met
    return True, trigger_data


# ============================================================
# LLM GENERATION (INITIATOR MODE)
# ============================================================

INITIATOR_SYSTEM_PROMPT = """You are Annie, Ankit's AI companion. You are INITIATING contact, not responding to a message.

Context:
- Trigger: {trigger_context}
- Last conversation: {hours_ago} hours ago
- Trigger data: {trigger_data}

Guidelines:
- Be natural and conversational, not robotic
- Keep it brief - you're starting a chat, not writing an essay
- Reference the specific trigger context
- Don't ask multiple questions - one thought is enough
- If it's a price alert, be excited but not over the top
- Match the time of day (morning greeting vs evening)
- Do NOT say "I noticed" or "I wanted to let you know" - just say it naturally
"""

async def generate_proactive_message(
    intent: dict,
    trigger_data: dict,
    last_interaction: datetime
) -> str:
    """Generate a proactive message using the LLM."""
    hours_ago = 0
    if last_interaction:
        hours_ago = round((datetime.utcnow() - last_interaction).total_seconds() / 3600, 1)

    system_prompt = INITIATOR_SYSTEM_PROMPT.format(
        trigger_context=intent["action_context"],
        hours_ago=hours_ago,
        trigger_data=trigger_data
    )

    llm_client = get_llm_client()
    response = await llm_client.generate(
        messages=[{"role": "user", "content": "Generate a proactive message."}],
        system_prompt=system_prompt,
        max_tokens=200
    )

    return response.content


# ============================================================
# MAIN WORKER TASK
# ============================================================

async def process_pending_intents(ctx):
    """
    Main worker task - runs every 30 seconds.

    1. Fetch pending intents from agentic-memories
    2. Evaluate conditions
    3. Run through subconscious gate
    4. Generate message with LLM
    5. Send via Telegram
    6. Report back to agentic-memories
    """
    redis = ctx["redis"]

    async with httpx.AsyncClient() as client:
        # 1. Fetch pending intents
        response = await client.get(f"{AGENTIC_MEMORIES_URL}/v1/intents/pending")
        pending_intents = response.json()

        for intent in pending_intents:
            intent_id = intent["id"]
            user_id = intent["user_id"]

            start_time = datetime.utcnow()

            try:
                # 2. Evaluate condition
                eval_start = datetime.utcnow()
                condition_met, trigger_data = await evaluate_condition(intent)
                evaluation_ms = int((datetime.utcnow() - eval_start).total_seconds() * 1000)

                if not condition_met:
                    # Report condition not met
                    await client.post(
                        f"{AGENTIC_MEMORIES_URL}/v1/intents/{intent_id}/fire",
                        json={
                            "status": "condition_not_met",
                            "trigger_data": trigger_data,
                            "evaluation_ms": evaluation_ms
                        }
                    )
                    continue

                # 3. Run through subconscious gate
                should_proceed, gate_result = await should_initiate_contact(
                    user_id, intent, redis
                )

                if not should_proceed:
                    # Report gate blocked
                    await client.post(
                        f"{AGENTIC_MEMORIES_URL}/v1/intents/{intent_id}/fire",
                        json={
                            "status": "gate_blocked",
                            "trigger_data": trigger_data,
                            "gate_result": gate_result,
                            "evaluation_ms": evaluation_ms
                        }
                    )
                    continue

                # 4. Generate message with LLM
                gen_start = datetime.utcnow()
                last_interaction_raw = await redis.get(f"user:{user_id}:last_interaction")
                last_interaction = None
                if last_interaction_raw:
                    last_interaction = datetime.fromisoformat(last_interaction_raw.decode())

                message = await generate_proactive_message(
                    intent, trigger_data, last_interaction
                )
                generation_ms = int((datetime.utcnow() - gen_start).total_seconds() * 1000)

                # 5. Send via Telegram
                delivery_start = datetime.utcnow()
                telegram_user_id = await redis.get(f"user:{user_id}:telegram_id")
                message_id = await send_telegram_message(
                    telegram_user_id.decode(),
                    message
                )
                delivery_ms = int((datetime.utcnow() - delivery_start).total_seconds() * 1000)

                # Update user state
                now = datetime.utcnow()
                await redis.set(
                    f"user:{user_id}:last_proactive",
                    now.isoformat()
                )
                await redis.incr(f"user:{user_id}:proactive_count:{now.date()}")
                await redis.expire(
                    f"user:{user_id}:proactive_count:{now.date()}",
                    86400  # 24 hours
                )

                # 6. Report success to agentic-memories
                await client.post(
                    f"{AGENTIC_MEMORIES_URL}/v1/intents/{intent_id}/fire",
                    json={
                        "status": "success",
                        "message_id": str(message_id),
                        "message_preview": message[:200],
                        "trigger_data": trigger_data,
                        "gate_result": gate_result,
                        "evaluation_ms": evaluation_ms,
                        "generation_ms": generation_ms,
                        "delivery_ms": delivery_ms
                    }
                )

            except Exception as e:
                # Report failure
                await client.post(
                    f"{AGENTIC_MEMORIES_URL}/v1/intents/{intent_id}/fire",
                    json={
                        "status": "failed",
                        "error_message": str(e)
                    }
                )


# ============================================================
# WORKER CONFIGURATION
# ============================================================

async def startup(ctx):
    """Worker startup - initialize Redis connection."""
    ctx["redis"] = await create_pool(
        RedisSettings(host=REDIS_HOST, port=REDIS_PORT)
    )

async def shutdown(ctx):
    """Worker shutdown - cleanup."""
    await ctx["redis"].close()


class WorkerSettings:
    """Arq worker settings."""
    functions = [process_pending_intents]
    cron_jobs = [
        cron(process_pending_intents, second={0, 30})  # Run every 30 seconds
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = RedisSettings(host=REDIS_HOST, port=REDIS_PORT)
```

---

## 9. Implementation Roadmap

### Phase 1: Foundation (Agentic-Memories)
1. Create `scheduled_intents` migration
2. Create `intent_executions` migration
3. Implement CRUD endpoints (`/v1/intents/*`)
4. Implement `/fire` endpoint with state management
5. Add Langfuse tracing to intent operations

### Phase 2: Annie MCP Tools
1. Add `create_trigger` tool
2. Add `list_triggers` tool
3. Add `update_trigger` tool
4. Add `delete_trigger` tool
5. Test LLM can create/manage triggers

### Phase 3: Background Worker
1. Set up Arq with Redis
2. Implement `process_pending_intents` task
3. Implement condition evaluators (price, time, silence)
4. Implement subconscious gate logic
5. Implement initiator mode LLM generation
6. Wire up Telegram delivery

### Phase 4: Polish & Monitoring
1. Add execution history queries
2. Add trigger analytics endpoints
3. Implement quiet hours with timezone support
4. Add trigger management UI commands (/triggers in Telegram)
5. Load testing and performance tuning

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Worker crashes | Arq has retry logic; triggers persist in PostgreSQL |
| Spam | Subconscious gate with multiple checks |
| API latency | Cache hot triggers in Redis |
| yfinance rate limits | Batch price checks, cache results |
| LLM costs | Only generate when gate passes |

---

## 10. Architecture Decision Record (ADR)

### ADR-001: Proactive AI Architecture

**Status:** Proposed

**Context:**
Annie currently operates in reactive mode - responding to user messages. To become a true AI companion, Annie needs the ability to initiate contact autonomously based on events, time, and user behavior patterns.

**Decision Drivers:**
- Simplicity - minimize new infrastructure
- Durability - triggers must survive restarts
- LLM-controllable - Annie manages her own triggers
- Queryability - support analytics and audit trails
- Existing stack - leverage current services

**Considered Options:**
1. Temporal.io + Redis
2. Celery Beat + PostgreSQL (new)
3. APScheduler + Redis (Annie)
4. Arq + Agentic-Memories PostgreSQL (extend existing)

**Decision:**
Option 4: Arq + Agentic-Memories PostgreSQL

**Rationale:**
- Agentic-memories already has PostgreSQL - no new infrastructure
- Arq is asyncio-native, matches FastAPI stack
- Triggers become part of the memory ecosystem
- Full audit trail via execution history
- Langfuse tracing already integrated

**Consequences:**

*Positive:*
- No new databases to deploy
- Triggers can reference memories
- Built-in observability
- Clean separation: Annie evaluates/generates, agentic-memories owns state

*Negative:*
- API hop adds latency (~10-50ms)
- Agentic-memories becomes more critical (already was)

*Neutral:*
- Requires migration to agentic-memories schema
- New Arq worker process in Annie

---

## 11. References and Resources

### Official Documentation
- [Arq Documentation](https://arq-docs.helpmanual.io/)
- [APScheduler Documentation](https://apscheduler.readthedocs.io/)
- [FastAPI Background Tasks](https://fastapi.tiangolo.com/tutorial/background-tasks/)

### Comparisons and Best Practices
- [Celery vs ARQ Comparison](https://leapcell.io/blog/celery-versus-arq-choosing-the-right-task-queue-for-python-applications)
- [APScheduler vs Celery Beat](https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat)
- [FastAPI Background Tasks vs ARQ](https://davidmuraya.com/blog/fastapi-background-tasks-arq-vs-built-in/)
- [Python Rule Engines 2025](https://www.nected.ai/us/blog-us/python-rule-engines-automate-and-enforce-with-python)

### Proactive AI Patterns
- [Meta's Proactive AI Chatbots](https://www.justthink.ai/blog/metas-proactive-ai-chatbots-that-message-you-first-redefine-digital-engagement)
- [Proactive Chatbot Engagement](https://www.visiativ.com/en/actualites/news/choose-a-proactive-chatbot/)

---

_This technical research report was generated using the BMad Method Research Workflow, combining systematic technology evaluation frameworks with real-time research and analysis. All version numbers and technical claims are backed by current 2025 sources._
