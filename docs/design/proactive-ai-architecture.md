# Proactive AI Architecture Design Document

**Document ID:** DESIGN-001
**Version:** 1.0
**Status:** Draft
**Author:** Ankit + Claude Code
**Date:** 2025-12-24
**Related Epic:** Epic 13 - Proactive AI Worker

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Design Philosophy](#2-design-philosophy)
3. [Trigger Types](#3-trigger-types)
4. [Action Context Specification](#4-action-context-specification)
5. [MCP Tool Definitions](#5-mcp-tool-definitions)
6. [System Prompt Enhancements](#6-system-prompt-enhancements)
7. [Wake-Up Agent Design](#7-wake-up-agent-design)
8. [Technical Architecture](#8-technical-architecture)
9. [Data Models](#9-data-models)
10. [Flow Diagrams](#10-flow-diagrams)
11. [Examples](#11-examples)
12. [Security & Safety](#12-security--safety)
13. [Observability](#13-observability)
14. [Dependencies](#14-dependencies)
15. [Glossary](#15-glossary)

---

## 1. Executive Summary

### 1.1 Purpose

This document defines the architecture for transforming Annie from a reactive chatbot into a proactive AI companion. Annie will autonomously initiate contact with users based on scheduled times, price conditions, portfolio events, and user inactivity.

### 1.2 Key Design Decision: LLM-Driven Architecture

**Traditional Approach (Rejected):**
- Code determines what context to gather per trigger type
- Hardcoded prompt templates per trigger type
- Rigid, requires code changes for new trigger types

**Our Approach (LLM-Driven):**
- Creation LLM captures full user intent in rich `action_context`
- Wake-up LLM reads `action_context` as a briefing document
- Wake-up LLM has full tool access to gather data and compose messages
- Flexible, handles novel trigger types without code changes

### 1.3 Core Principles

1. **LLM at Both Ends**: LLM creates triggers, LLM executes triggers
2. **Rich Context Handoff**: Creation LLM writes comprehensive briefing for wake-up LLM
3. **Minimal Trigger Types**: Only 2 types (scheduled, condition) - everything else is context
4. **Tool Autonomy**: Wake-up LLM decides which tools to call based on briefing
5. **Spam Prevention**: Subconscious gate prevents over-messaging

---

## 2. Design Philosophy

### 2.1 Why LLM-Driven?

The user's intent when creating a trigger contains nuance that structured fields cannot capture:

**User says:** "Every Friday, tell me how my tech stocks did compared to the S&P this week, but keep it casual"

**Structured approach would lose:**
- "compared to the S&P" (comparative analysis)
- "this week" (weekly aggregation)
- "keep it casual" (tone preference)

**LLM-driven approach preserves everything** in natural language briefing.

### 2.2 Two LLMs, One Intent

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│   USER REQUEST                                                               │
│   "Every Friday, tell me how my tech stocks did vs S&P, keep it casual"     │
│                                                                              │
│                                    │                                         │
│                                    ▼                                         │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                         CREATION LLM                                │    │
│   │                                                                     │    │
│   │   Understands intent → Crafts schedule → Writes rich briefing      │    │
│   │                                                                     │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                         action_context                              │    │
│   │                     (Comprehensive Briefing)                        │    │
│   │                                                                     │    │
│   │   - Original request                                                │    │
│   │   - Intent summary                                                  │    │
│   │   - User context                                                    │    │
│   │   - Execution instructions                                          │    │
│   │   - Message guidance                                                │    │
│   │   - Available tools                                                 │    │
│   │   - Edge cases                                                      │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                              (Stored in                                      │
│                           agentic-memories)                                  │
│                                    │                                         │
│                              [Time passes]                                   │
│                                    │                                         │
│                                    ▼                                         │
│   ┌────────────────────────────────────────────────────────────────────┐    │
│   │                         WAKE-UP LLM                                 │    │
│   │                                                                     │    │
│   │   Reads briefing → Calls tools → Evaluates → Composes message      │    │
│   │                                                                     │    │
│   └────────────────────────────────────────────────────────────────────┘    │
│                                    │                                         │
│                                    ▼                                         │
│                                                                              │
│   "Hey! Your tech holdings crushed it this week - up 4.2% vs S&P's 1.1%.    │
│    NVDA doing the heavy lifting. Have a great weekend!"                      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.3 The Briefing Handoff

Think of `action_context` as a **handoff document** from one AI to another:

- Creation LLM is like a manager writing instructions for a future employee
- Wake-up LLM is the employee who reads instructions and executes
- The better the instructions, the better the execution

---

## 3. Trigger Types

### 3.1 Overview

We use exactly **two** trigger types based on **wake-up mechanism**:

| Type | Wake-Up Mechanism | Use Cases |
|------|-------------------|-----------|
| `scheduled` | Fire at specific times | Reminders, daily check-ins, scheduled reports |
| `condition` | Fire when condition becomes true | Price alerts, portfolio milestones, silence detection |

Everything else (tone, data to gather, when to skip) is handled by `action_context`.

### 3.2 Type: `scheduled`

Fires at specific times determined by cron expression or one-time datetime.

#### 3.2.1 Cron Mode (Recurring)

```json
{
    "trigger_type": "scheduled",
    "schedule": {
        "mode": "cron",
        "cron_expression": "0 9 * * 1-5",
        "timezone": "America/Los_Angeles"
    }
}
```

**Cron Expression Reference:**

```
┌───────────── minute (0-59)
│ ┌─────────── hour (0-23)
│ │ ┌───────── day of month (1-31)
│ │ │ ┌─────── month (1-12)
│ │ │ │ ┌───── day of week (0-6, Sunday=0)
│ │ │ │ │
* * * * *
```

**Common Patterns:**

| User Says | Cron Expression |
|-----------|-----------------|
| "every morning" | `0 9 * * *` |
| "every morning at 8" | `0 8 * * *` |
| "every weekday morning" | `0 9 * * 1-5` |
| "every Friday at 5pm" | `0 17 * * 5` |
| "every Monday at 9am" | `0 9 * * 1` |
| "twice a day (9am and 5pm)" | `0 9,17 * * *` |
| "every hour" | `0 * * * *` |
| "first of every month" | `0 9 1 * *` |
| "every Sunday evening" | `0 18 * * 0` |
| "market open (weekdays 9:30am ET)" | `30 9 * * 1-5` (with ET timezone) |
| "market close (weekdays 4pm ET)" | `0 16 * * 1-5` (with ET timezone) |

#### 3.2.2 Once Mode (One-Time)

```json
{
    "trigger_type": "scheduled",
    "schedule": {
        "mode": "once",
        "datetime": "2025-12-31T09:00:00",
        "timezone": "America/Los_Angeles"
    }
}
```

**Behavior:**
- Fires exactly once at specified datetime
- Automatically disabled after firing
- Cannot recur

**Use Cases:**
- "Remind me on December 31st"
- "Ping me tomorrow morning"
- "In 2 hours, remind me to..."

#### 3.2.3 Schedule Lifecycle

```
CREATE                          FIRE                           NEXT
   │                              │                              │
   ▼                              ▼                              ▼
┌──────────┐  next_check    ┌──────────┐  calculate next   ┌──────────┐
│  Store   │ ────────────►  │  Wake    │ ────────────────► │  Update  │
│  Trigger │  = first       │   Up     │  from cron        │next_check│
└──────────┘  occurrence    └──────────┘                   └──────────┘
                                 │                              │
                                 │ (for "once" mode)            │
                                 ▼                              │
                            ┌──────────┐                        │
                            │ Disable  │                        │
                            │ Trigger  │                        │
                            └──────────┘                        │
                                                                │
                                 ◄──────────────────────────────┘
                                        (loop for cron)
```

### 3.3 Type: `condition`

Fires when a condition becomes true. Requires periodic evaluation.

#### 3.3.1 Condition Structure

```json
{
    "trigger_type": "condition",
    "condition": {
        "type": "price",
        "expression": "NVDA < 130",
        "check_interval_minutes": 5,
        "cooldown_hours": 24,
        "fire_mode": "once"
    }
}
```

#### 3.3.2 Condition Types

**Price Condition:**
```json
{
    "type": "price",
    "expression": "NVDA < 130",
    "check_interval_minutes": 5
}
```

Evaluator fetches current price, compares against threshold.

**⚠️ Data Source Reliability Note:**

The default price data source (yfinance) is an **unofficial scraper** with known limitations:
- Rate-limited and can fail during high load
- Not suitable for precision alerts ("alert at exactly $130.00")
- Can have delayed data (15-20 min during market hours)
- Occasionally breaks when Yahoo changes their API

**Mitigations implemented:**
1. **Aggressive caching**: Cache prices for 60 seconds minimum
2. **Fail-safe behavior**: On error, skip evaluation (don't fire)
3. **Retry with backoff**: 3 retries with exponential backoff
4. **Threshold tolerance**: Alert fires at "approximately" target, not exact

For production use with strict timing requirements, consider:
- Using your portfolio provider's API if it includes price data
- Polygon.io, Alpha Vantage, or other paid APIs
- The MCP server's existing stock tools if they provide real-time data

**Portfolio Condition:**
```json
{
    "type": "portfolio",
    "expression": "any_holding_change > 5%",
    "check_interval_minutes": 15
}
```

Supported portfolio expressions:
- `any_holding_change > X%` - Any single holding up/down more than X%
- `any_holding_down > X%` - Any holding down more than X%
- `any_holding_up > X%` - Any holding up more than X%
- `total_value >= X` - Portfolio total hits milestone
- `total_change > X%` - Portfolio daily change exceeds X%

**Silence Condition:**
```json
{
    "type": "silence",
    "expression": "inactive_hours > 48",
    "check_interval_minutes": 60
}
```

Checks time since user's last activity.

#### 3.3.3 Condition Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `type` | string | Condition category (price/portfolio/silence) | Required |
| `expression` | string | Human-readable condition | Required |
| `check_interval_minutes` | integer | How often to evaluate | 5 |
| `cooldown_hours` | integer | Minimum hours between fires | 24 |
| `fire_mode` | string | "once" (disable after fire) or "recurring" | "recurring" |

#### 3.3.4 Condition Lifecycle

```
CREATE                     CHECK                      FIRE
   │                         │                          │
   ▼                         ▼                          ▼
┌──────────┐           ┌──────────┐              ┌──────────┐
│  Store   │           │ Evaluate │  condition   │  Wake    │
│  Trigger │ ────────► │Condition │ ───TRUE────► │   Up     │
└──────────┘           └──────────┘              └──────────┘
     │                       │                        │
     │                       │ FALSE                  │
     │                       ▼                        ▼
     │                 ┌──────────┐            ┌──────────────┐
     │                 │  Update  │            │   Apply      │
     │                 │next_check│            │  Cooldown    │
     │                 │ += interval           │next_check += │
     │                 └──────────┘            │cooldown_hours│
     │                       │                 └──────────────┘
     │                       │                        │
     └───────────────────────┴────────────────────────┘
                            (loop)
```

### 3.4 Why Only 2 Types?

**Before (Many Types):**
```
trigger_type: "price" → code handles price logic
trigger_type: "cron" → code handles cron logic
trigger_type: "silence" → code handles silence logic
trigger_type: "portfolio" → code handles portfolio logic
```

Each type needed its own:
- Condition evaluator
- Context gatherer
- Prompt template

**After (2 Types):**
```
trigger_type: "scheduled" → Time-based wake-up
trigger_type: "condition" → Condition-based wake-up
```

The LLM handles everything else via `action_context`.

---

## 4. Action Context Specification

### 4.1 Overview

`action_context` is a comprehensive briefing document written by the creation LLM for the wake-up LLM. It should contain everything the wake-up LLM needs to:

1. Understand the user's original intent
2. Know what data to gather
3. Decide whether to send a message
4. Compose an appropriate message
5. Handle edge cases

### 4.2 Required Sections

#### 4.2.1 original_request

**Purpose:** Preserve the user's exact words.

**Type:** string

**Example:**
```json
"original_request": "Every weekday morning, give me a quick portfolio update. Keep it short. Skip the boring days."
```

**Why Important:** Provides ground truth for the wake-up LLM. If unsure about intent, refer back to original request.

---

#### 4.2.2 intent_summary

**Purpose:** Distilled statement of what this trigger should accomplish.

**Type:** string

**Example:**
```json
"intent_summary": "Brief weekday morning portfolio check-in. User prioritizes brevity over depth. Only message if something meaningful happened."
```

**Guidelines:**
- 1-3 sentences
- Capture the WHY, not just the WHAT
- Note any user preferences or constraints

---

#### 4.2.3 user_context

**Purpose:** Relevant **invariant** information about the user.

**Type:** object

**⚠️ CRITICAL: Avoid Stale Context**

**DO NOT snapshot dynamic data** like portfolio holdings, current positions, or account balances. This data becomes stale and can contradict fresh tool output, confusing the wake-up LLM.

```
❌ BAD: "User owns 50 shares of AAPL at $175 avg"
   → Two weeks later, user sold all AAPL
   → Wake-up agent reads stale context, writes message about AAPL ownership
   → get_portfolio returns 0 shares, but action_context says 50
   → Confused, potentially embarrassing message

✅ GOOD: "User is interested in tech stocks, particularly Apple"
   → execution_instructions: "Fetch current portfolio first"
   → Wake-up agent calls get_portfolio, sees current state
   → Writes accurate message based on fresh data
```

**Structure:**
```json
"user_context": {
    "name": "Ankit",
    "timezone": "America/Los_Angeles",
    "communication_style": "Prefers concise, casual communication. Dislikes verbosity.",
    "invariant_preferences": [
        "Risk tolerance: moderate",
        "Investment style: long-term holder",
        "Previously said: 'I don't need hand-holding, just the facts'"
    ],
    "general_interests": "Interested in tech stocks, has mentioned NVDA and AAPL frequently",
    "relevant_history": "Has expressed concern about tech concentration in past"
}
```

**What to Include (Invariant - Changes Rarely):**
- Name and timezone (always)
- Communication style preferences
- Risk tolerance and investment philosophy
- Tone preferences from past statements
- General interests and concerns they've expressed

**What to EXCLUDE (Dynamic - Fetch Fresh Instead):**
- ❌ Current portfolio holdings or values
- ❌ Specific share counts or positions
- ❌ Average cost basis or purchase prices
- ❌ Current stock prices or performance
- ❌ Account balances or total portfolio value
- ❌ Any data that changes with market activity

**The execution_instructions section MUST include:** "Retrieve the current portfolio and profile state immediately upon waking up."

---

#### 4.2.4 execution_instructions

**Purpose:** Step-by-step guide for the wake-up LLM.

**Type:** string (multiline)

**Example:**
```json
"execution_instructions": """
When this trigger fires, follow these steps:

1. GATHER DATA
   - Call get_portfolio with include_prices=true
   - Note the overnight change percentage
   - Identify any holdings that moved > 1%

2. EVALUATE WHETHER TO SEND
   - If NO holdings moved more than 1%: DO NOT SEND (return skip=true)
   - If portfolio change is < 0.5% and no individual movers: DO NOT SEND
   - Otherwise: Proceed to compose message

3. COMPOSE MESSAGE
   - Lead with total portfolio value and overnight change
   - Mention any notable movers (> 1% change)
   - Keep to 2-3 sentences MAX
   - End with optional soft invitation

4. ESCALATION
   - If any holding is DOWN more than 5%: Mention first, slightly urgent tone
   - If portfolio is down > 3%: More serious (but don't panic user)
"""
```

**Guidelines:**
- Use numbered steps
- Be explicit about decision points
- Include skip conditions
- Include escalation conditions
- Reference specific tool calls

---

#### 4.2.5 message_guidance

**Purpose:** Detailed guidance on message composition.

**Type:** string (multiline)

**Example:**
```json
"message_guidance": """
TONE: Casual, friendly, like a knowledgeable friend checking in. Not robotic.

LENGTH: 2-3 sentences maximum. User explicitly said "keep it short."

INCLUDE:
- Total portfolio value (round to nearest $100)
- Overnight/daily percentage change
- Top mover if significant (name + percentage)

EXCLUDE:
- Detailed analysis (save for if they ask)
- News or explanations (unless urgent)
- Recommendations or action items
- Anything requiring response

VOICE EXAMPLES (Good):
✅ "Morning! Portfolio's at $45.2k, up 1.2% overnight. NVDA doing the heavy lifting at +3%."
✅ "Quick AM check: $45k even, basically flat. Nothing dramatic overnight. ☕"
✅ "Heads up - portfolio dipped to $44.1k (-2.4%). GOOGL took a hit. Not a crisis, just FYI."

VOICE EXAMPLES (Bad):
❌ "Good morning Ankit! I hope you're having a wonderful day. I wanted to inform you that your investment portfolio has experienced a positive change of 1.2%..."
❌ "ALERT: Portfolio value changed. Current value: $45,234.56. Change: +1.23%."
❌ "Your portfolio is up! Have you considered rebalancing? Here are my recommendations..."
"""
```

**What to Specify:**
- Tone description
- Length constraints
- What to include (with specifics)
- What to exclude
- Multiple good examples
- Multiple bad examples (helps LLM understand boundaries)

---

#### 4.2.6 available_tools

**Purpose:** Inform wake-up LLM which tools are relevant and how to use them.

**Type:** string (multiline)

**Example:**
```json
"available_tools": """
For this trigger, you have access to:

PRIMARY (Use First):
- get_portfolio(user_id, include_prices=True)
  Returns all holdings with current prices, values, daily changes
  THIS IS YOUR MAIN DATA SOURCE

SECONDARY (Use If Needed):
- analyze_stock(ticker)
  Deep analysis of single stock - only if major move needs explanation

- retrieve_memories(user_id, query)
  Search past conversations - use to reference past decisions

AVOID FOR THIS TRIGGER:
- internet_search: User wants quick update, not research
- get_stock_history: Not needed for daily check-in

EFFICIENCY NOTE:
User wants speed. One tool call (get_portfolio) should suffice for normal days.
Only call additional tools if something unusual requires explanation.
"""
```

---

#### 4.2.7 edge_cases

**Purpose:** Handle unusual situations gracefully.

**Type:** string (multiline)

**Example:**
```json
"edge_cases": """
MARKET CLOSED (Weekend/Holiday):
- Data will show Friday's close
- Either skip OR say "Markets closed, here's where you stand: ..."
- User knows markets are closed, don't explain it

API ERROR / CAN'T FETCH DATA:
- Don't send broken or partial message
- Skip this occurrence (return skip=true with reason)
- Will retry next scheduled time

USER MESSAGED RECENTLY (< 1 hour):
- Subconscious gate should block, but if it fires:
- Be extra brief, acknowledge you just talked
- "Quick note since we just chatted: ..."

FIRST TIME TRIGGER FIRES:
- Act normal, don't announce "this is your first update!"
- Just execute naturally

PORTFOLIO IS EMPTY:
- If no holdings: "Noticed you don't have any holdings set up yet. Want help?"
- Or skip entirely

EXTREME MARKET MOVE (> 5% portfolio change):
- Lead with this information
- Slightly more urgent tone
- "Significant move overnight - your portfolio..."

HOLIDAY (Market Closed Midweek):
- Check if data is stale (same as previous day)
- Can mention "Markets closed for [holiday] - here's where things stand"
"""
```

---

#### 4.2.8 meta

**Purpose:** Metadata about the trigger itself.

**Type:** object

**Example:**
```json
"meta": {
    "created_at": "2025-12-24T14:30:00Z",
    "created_by": "User request via chat",
    "creation_conversation_id": "conv_abc123",
    "last_modified": null,
    "modification_history": [],
    "notes": "User specifically emphasized 'skip boring days' - respect this preference strongly"
}
```

### 4.3 Complete Example

```json
{
    "action_context": {
        "original_request": "Every weekday morning at 8:30, give me a quick portfolio update. Keep it short and skip the boring days when nothing happened.",

        "intent_summary": "Brief weekday morning portfolio check-in at 8:30 AM. User prioritizes brevity and only wants to be bothered if something meaningful happened (> 1% moves). Casual tone preferred.",

        "user_context": {
            "name": "Ankit",
            "timezone": "America/Los_Angeles",
            "communication_style": "Prefers concise, casual communication. Dislikes verbosity. Appreciates data but not walls of text.",
            "relevant_preferences": [
                "Risk tolerance: moderate",
                "Investment style: long-term holder, not active trader",
                "Has said before: 'Just the highlights, I'll ask if I want details'"
            ],
            "portfolio_context": "5-6 holdings, tech-heavy (NVDA, AAPL, GOOGL). Total around $45k. Has expressed concern about concentration in tech."
        },

        "execution_instructions": """
When this trigger fires at 8:30 AM PT on weekdays:

1. GATHER DATA
   - Call get_portfolio(user_id, include_prices=true)
   - Calculate overnight/daily change percentage
   - Identify holdings with > 1% individual moves

2. EVALUATE WHETHER TO SEND
   Skip Conditions (return skip=true):
   - No holdings moved more than 1% AND portfolio change < 0.5%
   - Market is closed AND data is same as yesterday
   - Portfolio is empty

   Proceed Conditions:
   - Any holding moved > 1%
   - Portfolio overall moved > 0.5%
   - Something notable happened

3. COMPOSE MESSAGE (if proceeding)
   - Lead with total value and change
   - Mention notable movers by name and percentage
   - Keep to 2-3 sentences
   - Optional soft closing (not required)

4. ESCALATION HANDLING
   - Any holding DOWN > 5%: Lead with this, slightly concerned tone
   - Portfolio DOWN > 3%: More prominent mention, but don't panic user
   - Portfolio UP > 5%: Celebrate briefly, mention top performer
        """,

        "message_guidance": """
TONE:
Casual and friendly, like a knowledgeable friend giving you the quick lowdown.
Not robotic, not overly enthusiastic, not alarmist.

LENGTH:
2-3 sentences maximum. User was explicit about "keep it short."

STRUCTURE:
[Value + Change] + [Notable Mover if any] + [Optional soft close]

INCLUDE:
- Total portfolio value (round to nearest $100)
- Daily/overnight percentage change
- Top mover if > 2% (ticker + percentage)

EXCLUDE:
- Detailed analysis
- News explanations
- Recommendations
- Questions requiring response
- Greetings beyond simple "Morning!"

GOOD EXAMPLES:
✅ "Morning! Portfolio's at $45.2k, up 1.2% overnight. NVDA leading at +3.1%."
✅ "Quick AM update: $44.8k, basically flat (+0.2%). Quiet night across the board."
✅ "Heads up - down to $43.5k (-2.8%). GOOGL dragging things down at -4.2%. Not panic territory, just FYI."
✅ "Nice overnight: $46.1k (+2.5%). Tech rally lifted everything, NVDA +5%."

BAD EXAMPLES:
❌ "Good morning Ankit! I hope you're having a wonderful start to your day. I wanted to take a moment to inform you about the current status of your investment portfolio..."
❌ "PORTFOLIO ALERT: Value has changed. Current: $45,234.56. Previous: $44,987.23. Delta: +$247.33 (+0.55%)."
❌ "Great news! Your portfolio is up! Have you considered taking profits? Here are some thoughts on rebalancing..."
❌ "Hi! 👋 Your portfolio is doing great today! 🚀📈 NVDA to the moon! 🌙"
        """,

        "available_tools": """
PRIMARY TOOL (Always Use):
┌─────────────────────────────────────────────────────────────────────┐
│ get_portfolio(user_id, include_prices=True)                         │
│                                                                      │
│ Returns:                                                             │
│ - holdings[]: Array of positions with current prices                 │
│ - total_value: Portfolio total                                       │
│ - total_cost_basis: What user paid                                   │
│ - total_gain_loss: Dollar gain/loss                                  │
│ - total_gain_loss_pct: Percentage gain/loss                          │
│                                                                      │
│ Each holding includes:                                               │
│ - ticker, shares, avg_price, current_price                           │
│ - current_value, cost_basis, gain_loss, gain_loss_pct                │
└─────────────────────────────────────────────────────────────────────┘

SECONDARY TOOLS (Use Only If Needed):
- analyze_stock(ticker): If a major mover needs brief explanation
- retrieve_memories(user_id, query): If referencing past user statements

AVOID FOR THIS TRIGGER:
- internet_search: Too slow, user wants quick update
- get_stock_history: Not relevant for daily snapshot

EFFICIENCY:
One get_portfolio call should suffice 95% of the time. User values speed.
        """,

        "edge_cases": """
WEEKEND/HOLIDAY (Market Closed):
- Data will be stale (Friday's close)
- Option 1: Skip entirely (user knows markets closed)
- Option 2: "Markets closed - still at $45.2k from Friday"
- Don't explain that markets are closed, user knows

CAN'T FETCH PORTFOLIO DATA:
- Don't send broken message
- Return skip=true with reason="data_unavailable"
- Will retry tomorrow

USER MESSAGED IN LAST HOUR:
- Subconscious gate should prevent this
- If somehow fires: Be extra brief
- "Quick note since we just chatted - portfolio at $45k, all stable."

FIRST TRIGGER FIRE EVER:
- Don't announce "This is your first morning update!"
- Just act natural, as if you've always done this

PORTFOLIO EMPTY (No Holdings):
- Skip with reason="no_holdings"
- Or: "No holdings to report on yet. Want help setting up your portfolio?"

SINGLE HOLDING DOMINATES (>80% of portfolio):
- Worth mentioning concentration
- "Portfolio at $45k (+1%). Note: NVDA is 85% of your holdings."

EXTREME MOVE (Portfolio > 5% change):
- Lead with this prominently
- More serious tone (but not panicked)
- "Big move overnight - portfolio at $42k, down 6%. NVDA dropped 8% on earnings."

ALL HOLDINGS FLAT (< 0.1% each):
- This triggers skip condition
- Return skip=true with reason="no_significant_moves"
        """,

        "meta": {
            "created_at": "2025-12-24T14:30:00Z",
            "created_by": "User request via chat",
            "creation_conversation_id": "conv_abc123",
            "last_modified": null,
            "modification_history": [],
            "notes": "User emphasized 'skip boring days' twice. Take this seriously - they don't want noise."
        }
    }
}
```

---

## 5. MCP Tool Definitions

### 5.1 create_trigger

**Purpose:** Create a new proactive trigger.

```python
{
    "name": "create_trigger",
    "description": """
Create a proactive trigger that will cause Annie to initiate contact with the user.

USE THIS WHEN USER WANTS:
- Reminders: "Remind me to...", "Every morning tell me...", "On Friday..."
- Alerts: "Let me know if NVDA drops...", "Alert me when..."
- Check-ins: "Check on me if I go quiet..."

BEFORE CALLING:
1. Clarify the user's intent if ambiguous
2. Confirm the schedule/condition with the user
3. Explain what Annie will do when it fires

TRIGGER TYPES:
- "scheduled": Fires at specific times (cron or one-time)
- "condition": Fires when condition becomes true (price, portfolio, silence)

CRON EXPRESSION EXAMPLES:
- "0 9 * * *"     = Daily at 9 AM
- "0 9 * * 1-5"   = Weekdays at 9 AM
- "0 17 * * 5"    = Fridays at 5 PM
- "30 8 * * *"    = Daily at 8:30 AM

CRITICAL: Write comprehensive action_context!
The wake-up LLM only has action_context to work with. Include:
- original_request: User's exact words
- intent_summary: Distilled purpose
- user_context: Relevant preferences
- execution_instructions: Step-by-step guide
- message_guidance: Tone, length, examples
- available_tools: What to call and when
- edge_cases: Unusual situations
    """,
    "input_schema": {
        "type": "object",
        "properties": {
            "intent_name": {
                "type": "string",
                "description": "Short descriptive name (e.g., 'Morning portfolio brief')"
            },
            "trigger_type": {
                "type": "string",
                "enum": ["scheduled", "condition"],
                "description": "Wake-up mechanism"
            },
            "schedule": {
                "type": "object",
                "description": "For trigger_type='scheduled'",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["cron", "once"]
                    },
                    "cron_expression": {
                        "type": "string",
                        "description": "Cron expression for recurring (e.g., '0 9 * * 1-5')"
                    },
                    "datetime": {
                        "type": "string",
                        "description": "ISO datetime for one-time (e.g., '2025-12-31T09:00:00')"
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone (default: user's profile timezone)"
                    }
                }
            },
            "condition": {
                "type": "object",
                "description": "For trigger_type='condition'",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["price", "portfolio", "silence"]
                    },
                    "expression": {
                        "type": "string",
                        "description": "Condition expression (e.g., 'NVDA < 130')"
                    },
                    "check_interval_minutes": {
                        "type": "integer",
                        "description": "How often to check (default: 5)"
                    },
                    "cooldown_hours": {
                        "type": "integer",
                        "description": "Minimum hours between fires (default: 24)"
                    }
                }
            },
            "action_context": {
                "type": "object",
                "description": "Comprehensive briefing for wake-up LLM (see documentation)"
            },
            "expires_at": {
                "type": "string",
                "description": "Optional: ISO datetime when trigger auto-deletes"
            }
        },
        "required": ["intent_name", "trigger_type", "action_context"]
    }
}
```

### 5.2 list_triggers

**Purpose:** List user's triggers.

```python
{
    "name": "list_triggers",
    "description": """
List all triggers for the current user.

USE WHEN USER ASKS:
- "What reminders do I have?"
- "Show my alerts"
- "What notifications are set up?"
- "List my triggers"

Returns array of triggers with:
- id: Unique identifier
- intent_name: Display name
- trigger_type: scheduled/condition
- schedule/condition: Configuration
- enabled: Active status
- next_check: When it will next evaluate
- fire_count: Times it has fired
- last_fired: When it last fired
    """,
    "input_schema": {
        "type": "object",
        "properties": {
            "trigger_type": {
                "type": "string",
                "enum": ["scheduled", "condition", "all"],
                "description": "Filter by type (default: all)"
            },
            "include_disabled": {
                "type": "boolean",
                "description": "Include paused triggers (default: false)"
            }
        }
    }
}
```

### 5.3 update_trigger

**Purpose:** Modify an existing trigger.

```python
{
    "name": "update_trigger",
    "description": """
Update an existing trigger's configuration.

USE WHEN USER WANTS TO:
- Change schedule: "Make it 8am instead of 9am"
- Modify condition: "Change to alert at $125 instead of $130"
- Update preferences: "Make the messages shorter"
- Pause: "Stop the morning updates for now"
- Resume: "Turn my alerts back on"

PROCESS:
1. Call list_triggers to find the trigger ID
2. Call update_trigger with the changes
3. Confirm the update with user

PAUSING VS DELETING:
- Use enabled=false to pause (can resume later)
- Use delete_trigger to permanently remove

Only include fields you want to change. Omitted fields keep current values.
    """,
    "input_schema": {
        "type": "object",
        "properties": {
            "trigger_id": {
                "type": "string",
                "description": "ID from list_triggers"
            },
            "intent_name": {
                "type": "string",
                "description": "New display name"
            },
            "schedule": {
                "type": "object",
                "description": "New schedule configuration"
            },
            "condition": {
                "type": "object",
                "description": "New condition configuration"
            },
            "action_context": {
                "type": "object",
                "description": "Updated briefing (merges with existing)"
            },
            "enabled": {
                "type": "boolean",
                "description": "Enable (true) or pause (false)"
            }
        },
        "required": ["trigger_id"]
    }
}
```

### 5.4 delete_trigger

**Purpose:** Permanently remove a trigger.

```python
{
    "name": "delete_trigger",
    "description": """
Permanently delete a trigger.

USE WHEN USER WANTS TO:
- "Stop the morning reminders" (permanently)
- "Cancel the NVDA alert"
- "Remove all my triggers"
- "I don't need that anymore"

IMPORTANT:
- ALWAYS confirm with user before deleting
- This is permanent - cannot be undone
- For temporary stop, use update_trigger with enabled=false

PROCESS:
1. Call list_triggers to show user what exists
2. Confirm which trigger(s) to delete
3. Call delete_trigger with confirm=true
4. Confirm deletion to user
    """,
    "input_schema": {
        "type": "object",
        "properties": {
            "trigger_id": {
                "type": "string",
                "description": "ID from list_triggers"
            },
            "confirm": {
                "type": "boolean",
                "description": "Must be true to confirm deletion"
            }
        },
        "required": ["trigger_id", "confirm"]
    }
}
```

---

## 6. System Prompt Enhancements

### 6.1 Proactive Capabilities Section

Add to Annie's main system prompt:

```
## PROACTIVE CAPABILITIES

You can initiate contact with users autonomously! This is a key differentiator.

### When to Offer Proactive Features

Listen for these signals and OFFER to set up triggers:

| User Says | Trigger Type | Example Response |
|-----------|--------------|------------------|
| "I want to keep an eye on NVDA" | condition (price) | "Want me to alert you if NVDA crosses a certain price?" |
| "Remind me every morning..." | scheduled (cron) | "I'll check in every morning at 9. What time works best?" |
| "Let me know if..." | condition | "I can watch for that. What threshold should I use?" |
| "Every Friday..." | scheduled (cron) | "Got it - I'll ping you every Friday. What time?" |
| "Check on me if I go quiet" | condition (silence) | "I'll check in if I don't hear from you. How long should I wait?" |

### Creating Triggers - Best Practices

1. CLARIFY before creating:
   "Just to confirm - you want me to alert you when NVDA drops below $130?"

2. CONFIRM the schedule:
   "I'll ping you weekdays at 9 AM Pacific. Sound right?"

3. EXPLAIN what happens:
   "When it fires, I'll check your portfolio and give you the highlights."

4. OFFER customization:
   "Want me to skip days when nothing significant happened?"

### Schedule Translation

| User Says | Interpretation |
|-----------|----------------|
| "every morning" | 9 AM daily |
| "every weekday morning" | 9 AM Mon-Fri |
| "every Friday" | Friday 9 AM (or 5 PM if "Friday evening") |
| "twice a day" | 9 AM and 5 PM |
| "market open" | 9:30 AM ET weekdays |
| "end of day" | 5 PM |
| "tomorrow morning" | One-time, tomorrow 9 AM |
| "in 2 hours" | One-time, calculated |

### Managing Existing Triggers

When user asks about triggers:
1. Call list_triggers to see what exists
2. Present clearly with human-readable descriptions
3. Offer to modify or delete

For modifications:
- "Pause my reminders" → update_trigger with enabled=false
- "Stop permanently" → delete_trigger (confirm first!)
- "Change to 8am" → update_trigger with new schedule

### Writing Good action_context

When creating triggers, your action_context is a briefing for a future AI.
Be THOROUGH. Include:
- The user's exact words
- Their communication preferences
- Step-by-step execution instructions
- Good and bad message examples
- Edge case handling

The wake-up LLM only sees action_context. Make it comprehensive!
```

### 6.2 Active Triggers in Context

Include current triggers in system prompt:

```
## YOUR ACTIVE TRIGGERS

{triggers_summary}

Example format:
1. "Morning portfolio brief" - Weekdays 8:30 AM PT - Last fired: yesterday
2. "NVDA price alert" - When NVDA < $130 - Never fired yet
3. "Weekly check-in" - Fridays 5 PM PT - Last fired: 2 days ago
```

---

## 7. Wake-Up Agent Design

### 7.1 Overview

When a trigger fires, the wake-up agent:
1. Receives the stored `action_context`
2. **Receives dynamic state injection** (current time, recent context)
3. Has access to all tools
4. Decides what data to gather
5. Decides whether to send a message
6. Composes the message
7. Returns result to worker

### 7.2 Dynamic State Injection

**Problem:** The `action_context` is static (written at trigger creation). The wake-up agent needs current context to make good decisions.

**Solution:** Inject dynamic state at execution time, separate from the stored `action_context`.

```python
@dataclass
class DynamicState:
    """Fresh context injected at wake-up time."""

    # Temporal context
    current_datetime: datetime          # Current date/time in user's timezone
    day_of_week: str                   # "Friday" - needed for "skip boring days" logic
    is_market_hours: bool              # Are US markets currently open?
    is_holiday: bool                   # Is today a market holiday?

    # User activity context
    hours_since_last_activity: float   # How long since user messaged
    last_message_preview: Optional[str] # First 100 chars of last user message

    # Recent conversation summary (from agentic-memories)
    recent_context: Optional[str]      # 2-3 sentence summary of recent conversations
                                       # e.g., "User discussed breakup 2 hours ago"
                                       # Helps wake-up agent adjust tone

    # User profile snapshot
    user_profile: dict                 # Current profile (fetched fresh, not from action_context)
```

**Why This Matters:**

| Dynamic State | Why Needed | Example |
|---------------|------------|---------|
| `current_datetime` | "Every Friday" logic | Agent needs to know it's actually Friday |
| `day_of_week` | "Skip weekends" logic | Explicit day name for clarity |
| `is_market_hours` | Market-related triggers | Skip or adjust if markets closed |
| `hours_since_last_activity` | Spam prevention | Extra brief if user just messaged |
| `recent_context` | **Tone adjustment** | Don't send chirpy message if user just discussed a breakup |
| `user_profile` | Fresh preferences | User may have updated their preferences |

### 7.3 Wake-Up Agent Prompt

```python
WAKE_UP_AGENT_PROMPT = """
You are Annie's proactive subsystem. A trigger has fired and you need to decide
whether to send a message and what to say.

## Trigger Information

Trigger Name: {trigger_name}
Trigger Type: {trigger_type}
Fire Count: {fire_count} (times this has fired before)
Last Fired: {last_fired}

## DYNAMIC CONTEXT (Current State)

This is LIVE information at the moment of execution:

Current Time: {current_datetime} ({day_of_week})
Market Status: {market_status}
Hours Since User Last Messaged: {hours_since_activity}

### Recent Conversation Summary
{recent_context}

### Current User Profile
{user_profile_summary}

⚠️ IMPORTANT: If recent_context indicates the user is going through something
difficult (personal issues, bad news, stress), adjust your tone accordingly.
A chirpy "Great news about your portfolio!" is inappropriate after a breakup discussion.

## Your Briefing (Created at Trigger Setup)

The following action_context was written when this trigger was created.
It contains the user's original intent and preferences:

{action_context}

## Available Tools

You have access to ALL read-only tools from the MCP server:

{available_tools_list}

Use any tools you need to accomplish your briefing's intent.
The action_context's "available_tools" section provides suggestions, but you have full flexibility.
ALWAYS fetch fresh data - do not rely on any holdings/values mentioned in user_context.

## Your Task

1. Note the current date/time and recent context
2. Read your briefing carefully
3. Follow the execution_instructions step by step
4. Fetch fresh data using tools (REQUIRED for financial data)
5. Apply any skip conditions from your briefing
6. Consider the recent_context when choosing tone
7. If proceeding, compose a message following message_guidance
8. Handle any edge_cases that apply

## Response Format

Return JSON:
{
    "skip": true/false,
    "skip_reason": "reason if skipping",
    "message": "the message to send if not skipping",
    "tools_called": ["list of tools you called"],
    "reasoning": "brief explanation of your decision"
}

## Critical Rules

1. FETCH FRESH DATA - Never trust portfolio data from action_context
2. FOLLOW YOUR BRIEFING - it was written specifically for this trigger
3. RESPECT SKIP CONDITIONS - don't message when briefing says not to
4. CONSIDER RECENT CONTEXT - adjust tone based on user's recent state
5. MATCH THE TONE - use the voice examples as guide
6. BE CONCISE - respect length guidelines
7. DON'T OVER-FETCH - only call tools you need
"""
```

### 7.4 Wake-Up Agent Flow

```python
async def wake_up_agent(trigger: dict, user_id: str) -> WakeUpResult:
    """
    Execute a fired trigger.

    Args:
        trigger: The trigger document including action_context
        user_id: The user who owns this trigger

    Returns:
        WakeUpResult with skip status, message if any, and metadata
    """

    action_context = trigger["action_context"]

    # 1. Gather dynamic state (FRESH at execution time)
    dynamic_state = await gather_dynamic_state(user_id)

    # 2. Get available tools dynamically from MCP server
    available_tools = await get_available_tools()
    tools_list = format_tools_for_prompt(available_tools)

    # 3. Build the prompt with both static and dynamic context
    prompt = WAKE_UP_AGENT_PROMPT.format(
        # Trigger info
        trigger_name=trigger["intent_name"],
        trigger_type=trigger["trigger_type"],
        fire_count=trigger.get("fire_count", 0),
        last_fired=trigger.get("last_fired", "Never"),

        # Dynamic state (fresh)
        current_datetime=dynamic_state.current_datetime.isoformat(),
        day_of_week=dynamic_state.day_of_week,
        market_status="Open" if dynamic_state.is_market_hours else "Closed",
        hours_since_activity=f"{dynamic_state.hours_since_last_activity:.1f}",
        recent_context=dynamic_state.recent_context or "No recent conversations",
        user_profile_summary=json.dumps(dynamic_state.user_profile, indent=2),

        # Available tools (fresh from MCP)
        available_tools_list=tools_list,

        # Static briefing
        action_context=json.dumps(action_context, indent=2)
    )

    # 4. Execute with full tool access (no artificial limits)
    response = await llm_client.generate_with_tools(
        system_prompt=prompt,
        user_prompt="Execute this trigger now. Follow your briefing.",
        tools=available_tools,
        timeout_seconds=600,  # 10 minutes
    )

    # 5. Parse response
    result = json.loads(response.content)

    return WakeUpResult(
        skip=result.get("skip", False),
        skip_reason=result.get("skip_reason"),
        message=result.get("message"),
        tools_called=result.get("tools_called", []),
        reasoning=result.get("reasoning"),
    )


async def gather_dynamic_state(user_id: str) -> DynamicState:
    """Gather fresh context at wake-up time."""

    user_tz = await get_user_timezone(user_id)
    now = datetime.now(user_tz)

    # Get last activity
    last_activity = await redis.get(f"user:{user_id}:last_activity")
    hours_since = None
    if last_activity:
        last_dt = datetime.fromisoformat(last_activity)
        hours_since = (now - last_dt).total_seconds() / 3600

    # Get recent conversation summary from agentic-memories
    recent_context = await memory_client.get_recent_summary(
        user_id=user_id,
        hours=24,  # Last 24 hours of context
        max_sentences=3
    )

    # Get fresh user profile
    user_profile = await profile_client.get_profile(user_id)

    return DynamicState(
        current_datetime=now,
        day_of_week=now.strftime("%A"),  # "Friday"
        is_market_hours=is_us_market_open(now),
        is_holiday=is_market_holiday(now),
        hours_since_last_activity=hours_since,
        last_message_preview=None,  # Can add if needed
        recent_context=recent_context,
        user_profile=user_profile,
    )
```

### 7.5 Guardrails & Tool Access

**Philosophy:** The wake-up agent is given **extreme flexibility** to operate. It has access to all MCP tools and can make its own decisions based on the action_context briefing.

```python
class WakeUpGuardrails:
    """Minimal safety limits for wake-up agent."""

    TIMEOUT_SECONDS = 600        # Maximum execution time (10 minutes)

    # Tools that should NEVER be used proactively (state-modifying)
    RESTRICTED_TOOLS = [
        "add_holding",      # Don't modify portfolio proactively
        "update_holding",
        "remove_holding",
        "create_trigger",   # Don't self-create triggers
        "delete_trigger",   # Don't self-delete triggers
    ]
```

**Dynamic Tool Discovery:**

The wake-up agent queries the MCP server fresh at execution time to get the complete list of available tools:

```python
async def get_available_tools() -> List[ToolDefinition]:
    """Query MCP server for current tool list, filtering restricted tools."""
    all_tools = await mcp_client.list_tools()

    return [
        tool for tool in all_tools
        if tool.name not in WakeUpGuardrails.RESTRICTED_TOOLS
    ]
```

**Why Dynamic Discovery:**
- New tools added to MCP server are automatically available
- No need to update wake-up agent code when tools change
- Agent has full flexibility to use any read-only tool
- Only state-modifying operations are restricted

**No Hard Limits:**
- No limit on tool calls
- No limit on message length
- No limit on LLM tokens
- Action_context provides guidance, agent is trusted to follow it

---

## 8. Technical Architecture

### 8.1 System Components

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ANNIE BACKEND                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                     PROACTIVE SUBSYSTEM                              │    │
│  │                                                                      │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐               │    │
│  │  │   Intents    │  │   Worker     │  │   Wake-Up    │               │    │
│  │  │   Client     │  │   (Arq)      │  │   Agent      │               │    │
│  │  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘               │    │
│  │         │                 │                 │                        │    │
│  │         │                 │                 │                        │    │
│  │  ┌──────▼───────┐  ┌──────▼───────┐  ┌──────▼───────┐               │    │
│  │  │  Subconscious│  │  Condition   │  │   Message    │               │    │
│  │  │    Gate      │  │  Evaluators  │  │   Delivery   │               │    │
│  │  └──────────────┘  └──────────────┘  └──────────────┘               │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                        MCP SERVER                                    │    │
│  │                                                                      │    │
│  │  ┌──────────────────────────────────────────────────────────────┐   │    │
│  │  │  Trigger Tools: create_trigger, list_triggers,               │   │    │
│  │  │                 update_trigger, delete_trigger               │   │    │
│  │  └──────────────────────────────────────────────────────────────┘   │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    │ HTTP
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          AGENTIC-MEMORIES                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      INTENTS API                                     │    │
│  │                                                                      │    │
│  │  POST   /v1/intents           - Create trigger                       │    │
│  │  GET    /v1/intents           - List triggers                        │    │
│  │  GET    /v1/intents/{id}      - Get trigger                          │    │
│  │  PUT    /v1/intents/{id}      - Update trigger                       │    │
│  │  DELETE /v1/intents/{id}      - Delete trigger                       │    │
│  │  GET    /v1/intents/pending   - Get due triggers                     │    │
│  │  POST   /v1/intents/{id}/fire - Report trigger execution             │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      TIMESCALE DB                                    │    │
│  │                                                                      │    │
│  │  Table: intents                                                      │    │
│  │  - id, user_id, intent_name, trigger_type                            │    │
│  │  - schedule, condition, action_context                               │    │
│  │  - enabled, next_check, fire_count, last_fired                       │    │
│  │  - created_at, updated_at, expires_at                                │    │
│  │                                                                      │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 File Structure

```
backend/
├── api/
│   ├── proactive/
│   │   ├── __init__.py
│   │   ├── worker.py           # Arq background worker
│   │   ├── agent.py            # Wake-up agent logic
│   │   ├── gate.py             # Subconscious gate
│   │   ├── evaluators.py       # Condition evaluators
│   │   └── delivery.py         # Telegram message delivery
│   ├── intents_client.py       # HTTP client for intents API
│   └── ...

mcp_server/
├── tools/
│   ├── triggers.py             # Trigger management tools
│   └── ...
├── server.py
└── ...
```

### 8.3 Worker Architecture

```python
# backend/api/proactive/worker.py

from arq import cron
from arq.connections import RedisSettings

async def poll_scheduled_triggers(ctx):
    """Poll for due scheduled triggers. Runs every 30 seconds."""
    client = IntentsClient()

    # Get triggers where next_check <= now
    pending = await client.get_pending(trigger_type="scheduled")

    for trigger in pending:
        await process_trigger(trigger)

async def poll_condition_triggers(ctx):
    """Evaluate condition triggers. Runs every minute."""
    client = IntentsClient()

    # Get condition triggers due for evaluation
    conditions = await client.get_pending(trigger_type="condition")

    for trigger in conditions:
        # Fast evaluation (no LLM)
        condition_met = await evaluate_condition(trigger)

        if condition_met:
            await process_trigger(trigger)
        else:
            # Update next_check for next evaluation
            await client.update_next_check(
                trigger["id"],
                next_check=now() + timedelta(minutes=trigger["condition"]["check_interval_minutes"])
            )

async def process_trigger(trigger: dict):
    """Process a fired trigger through the full pipeline."""
    user_id = trigger["user_id"]

    # 1. Subconscious gate check
    gate_result = await check_subconscious_gate(user_id)
    if not gate_result.allowed:
        await report_fire(trigger, status="gate_blocked", reason=gate_result.reason)
        return

    # 2. Wake-up agent
    result = await wake_up_agent(trigger, user_id)

    if result.skip:
        await report_fire(trigger, status="skipped", reason=result.skip_reason)
        return

    # 3. Deliver message
    message_id = await deliver_to_telegram(user_id, result.message)

    # 4. Report success
    await report_fire(
        trigger,
        status="success",
        message_id=message_id,
        tools_called=result.tools_called
    )

class WorkerSettings:
    """Arq worker configuration."""

    functions = [poll_scheduled_triggers, poll_condition_triggers]

    cron_jobs = [
        cron(poll_scheduled_triggers, second={0, 30}),      # Every 30 seconds
        cron(poll_condition_triggers, minute={0, 1, 2, ...}),  # Every minute
    ]

    redis_settings = RedisSettings.from_dsn(os.getenv("REDIS_URL"))

    max_jobs = 10
    job_timeout = 60
```

### 8.4 Feedback Handler

The proactive system is currently "open loop" - it sends messages but doesn't learn from user reactions. The Feedback Handler closes this loop.

#### 8.4.1 Problem: No Learning from User Reactions

```
Trigger fires → Message sent → User replies "This is annoying"
                                     ↓
                             System doesn't know this was about the trigger
                             No automatic adjustment happens
```

#### 8.4.2 Solution: Feedback Loop Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        FEEDBACK HANDLER FLOW                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  1. Proactive message sent                                                   │
│     └─► Store in Redis: proactive_message:{user_id}:last = {                │
│             trigger_id: "abc123",                                            │
│             message_id: "98765",                                             │
│             sent_at: "2025-12-26T08:30:15Z"                                  │
│         }                                                                    │
│         TTL: 2 hours                                                         │
│                                                                              │
│  2. User replies via chat route                                              │
│     └─► Chat route checks: was last message proactive?                       │
│         └─► If yes AND within 2 hours: flag as trigger_feedback              │
│                                                                              │
│  3. Feedback detected                                                        │
│     └─► Include trigger context in chat system prompt:                       │
│         "User is replying to proactive message from trigger 'Morning brief'" │
│                                                                              │
│  4. LLM detects feedback intent                                              │
│     └─► Negative: "This is annoying", "Don't wake me for 1% moves"          │
│     └─► Positive: "Thanks, this is helpful", "Can you add more detail?"     │
│                                                                              │
│  5. Auto-update action_context                                               │
│     └─► LLM calls update_trigger to modify:                                  │
│         - message_guidance (if tone/length feedback)                         │
│         - execution_instructions (if threshold feedback like "1% is too low")│
│         - enabled=false (if user wants to stop)                              │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

#### 8.4.3 Implementation

**File:** `backend/api/proactive/feedback.py`

```python
from datetime import datetime, timedelta

FEEDBACK_WINDOW = timedelta(hours=2)

async def record_proactive_message(
    user_id: str,
    trigger_id: str,
    message_id: str
) -> None:
    """Record that a proactive message was sent for feedback linking."""
    await redis.set(
        f"proactive_message:{user_id}:last",
        json.dumps({
            "trigger_id": trigger_id,
            "message_id": message_id,
            "sent_at": datetime.utcnow().isoformat(),
        }),
        ex=int(FEEDBACK_WINDOW.total_seconds())
    )

async def get_proactive_context(user_id: str) -> Optional[dict]:
    """Check if user's last message was proactive (for feedback detection)."""
    data = await redis.get(f"proactive_message:{user_id}:last")
    if not data:
        return None

    context = json.loads(data)
    sent_at = datetime.fromisoformat(context["sent_at"])

    # Only valid within feedback window
    if datetime.utcnow() - sent_at > FEEDBACK_WINDOW:
        return None

    return context

async def clear_proactive_context(user_id: str) -> None:
    """Clear after processing to avoid repeated linking."""
    await redis.delete(f"proactive_message:{user_id}:last")
```

**Integration in Chat Route:** `backend/api/routes/chat.py`

```python
async def handle_chat(user_id: str, message: str):
    # Check if this is feedback to a proactive message
    proactive_context = await get_proactive_context(user_id)

    if proactive_context:
        # Fetch the trigger details
        trigger = await intents_client.get_intent(proactive_context["trigger_id"])

        # Add to system prompt
        feedback_prompt = f"""
## PROACTIVE FEEDBACK CONTEXT

The user is replying to a proactive message you sent.

Trigger: "{trigger['intent_name']}"
Message sent: {proactive_context['sent_at']}

If the user is giving feedback about this proactive message (positive or negative),
you should:
1. Acknowledge their feedback
2. If negative: Offer to adjust (threshold, timing, tone) or disable
3. If requesting changes: Use update_trigger to modify the action_context
4. If they want to stop: Use update_trigger with enabled=false

Examples of feedback you might receive:
- "This is annoying" → Offer to pause or adjust frequency
- "Don't wake me for 1% moves" → Update execution_instructions threshold
- "Make these shorter" → Update message_guidance length
- "This is helpful, thanks" → Acknowledge positively
"""

        # Clear context after processing
        await clear_proactive_context(user_id)
```

#### 8.4.4 Feedback Types and Actions

| User Feedback | Detected Intent | Action |
|---------------|-----------------|--------|
| "This is annoying" | negative_general | Offer to pause or adjust |
| "Don't message me about small moves" | threshold_too_low | Update skip threshold in execution_instructions |
| "These are too long" | message_too_long | Update length in message_guidance |
| "Make these more detailed" | message_too_short | Update message_guidance |
| "Stop the morning updates" | disable_request | update_trigger with enabled=false |
| "This is helpful" | positive | Acknowledge, no change |
| "Can you also include X?" | feature_request | Update execution_instructions |

---

## 9. Data Models

### 9.1 Trigger Model (agentic-memories)

```python
class Trigger(BaseModel):
    """Trigger stored in agentic-memories."""

    id: str                          # UUID
    user_id: str                     # Owner
    intent_name: str                 # Display name

    trigger_type: Literal["scheduled", "condition"]

    # For scheduled triggers
    schedule: Optional[ScheduleConfig] = None

    # For condition triggers
    condition: Optional[ConditionConfig] = None

    # The briefing document
    action_context: dict             # Rich JSON, see specification

    # State
    enabled: bool = True
    next_check: datetime             # When to next evaluate
    fire_count: int = 0
    last_fired: Optional[datetime] = None

    # Metadata
    created_at: datetime
    updated_at: datetime
    expires_at: Optional[datetime] = None

class ScheduleConfig(BaseModel):
    mode: Literal["cron", "once"]
    cron_expression: Optional[str] = None    # For cron mode
    datetime: Optional[str] = None           # For once mode (ISO format)
    timezone: str = "UTC"

class ConditionConfig(BaseModel):
    type: Literal["price", "portfolio", "silence"]
    expression: str                          # Human-readable condition
    check_interval_minutes: int = 5
    cooldown_hours: int = 24
    fire_mode: Literal["once", "recurring"] = "recurring"
```

### 9.2 Fire Report Model

```python
class FireReport(BaseModel):
    """Report sent to agentic-memories after trigger execution."""

    trigger_id: str
    fired_at: datetime
    status: Literal["success", "skipped", "gate_blocked", "error"]

    # For success
    message_preview: Optional[str] = None
    message_id: Optional[str] = None         # Telegram message ID

    # For skipped
    skip_reason: Optional[str] = None

    # For gate_blocked
    gate_reason: Optional[str] = None
    gate_defer_until: Optional[datetime] = None

    # For error
    error_message: Optional[str] = None

    # Metadata
    tools_called: List[str] = []
    execution_time_ms: int
```

### 9.3 Wake-Up Result Model

```python
class WakeUpResult(BaseModel):
    """Result from wake-up agent execution."""

    skip: bool
    skip_reason: Optional[str] = None

    message: Optional[str] = None

    tools_called: List[str] = []
    reasoning: str

    # Telemetry
    llm_tokens_used: int
    execution_time_ms: int
```

---

## 10. Flow Diagrams

### 10.1 Trigger Creation Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ USER: "Every weekday morning at 8:30, give me a portfolio update"           │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ CREATION LLM (Normal Chat Context)                                           │
│                                                                              │
│ 1. Recognize proactive intent                                                │
│ 2. Clarify with user: "Weekdays at 8:30 AM Pacific?"                        │
│ 3. User confirms                                                             │
│ 4. Craft comprehensive action_context                                        │
│ 5. Call create_trigger tool                                                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ MCP TOOL: create_trigger                                                     │
│                                                                              │
│ {                                                                            │
│   intent_name: "Morning portfolio brief",                                    │
│   trigger_type: "scheduled",                                                 │
│   schedule: { mode: "cron", cron_expression: "30 8 * * 1-5", tz: "PT" },    │
│   action_context: { ... comprehensive briefing ... }                         │
│ }                                                                            │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ INTENTS CLIENT                                                               │
│                                                                              │
│ POST /v1/intents → agentic-memories                                          │
│                                                                              │
│ Calculates next_check = next occurrence of "30 8 * * 1-5" in user timezone   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ AGENTIC-MEMORIES                                                             │
│                                                                              │
│ Stores trigger in TimescaleDB                                                │
│ Returns: { id: "trigger_abc123", next_check: "2025-12-26T08:30:00-08:00" }   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ CREATION LLM CONFIRMS                                                        │
│                                                                              │
│ "All set! I'll check in weekday mornings at 8:30 AM with a quick portfolio   │
│  update. First one will be Thursday. Say 'show my triggers' anytime."        │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.2 Trigger Execution Flow (Scheduled)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TIME: 8:30:00 AM PT, Thursday                                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ ARQ WORKER: poll_scheduled_triggers()                                        │
│                                                                              │
│ GET /v1/intents/pending?trigger_type=scheduled                               │
│                                                                              │
│ Returns: [{ id: "trigger_abc123", ... action_context ... }]                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ SUBCONSCIOUS GATE CHECK                                                      │
│                                                                              │
│ ✓ Recent contact? No (last message 18 hours ago)                             │
│ ✓ Daily limit? No (0 proactive messages today)                               │
│ ✓ Quiet hours? No (8:30 AM is fine)                                          │
│ ✓ User opted out? No                                                         │
│                                                                              │
│ Result: ALLOWED                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ WAKE-UP AGENT                                                                │
│                                                                              │
│ Reads action_context briefing                                                │
│                                                                              │
│ Step 1: Call get_portfolio(user_id, include_prices=True)                     │
│         Result: { total_value: 45230, change_pct: 1.2, holdings: [...] }     │
│                                                                              │
│ Step 2: Evaluate skip conditions                                             │
│         - NVDA moved +3.1% (> 1% threshold) → Don't skip                     │
│                                                                              │
│ Step 3: Compose message per message_guidance                                 │
│         "Morning! Portfolio at $45.2k, up 1.2%. NVDA leading at +3.1%."      │
│                                                                              │
│ Result: { skip: false, message: "Morning! ..." }                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ TELEGRAM DELIVERY                                                            │
│                                                                              │
│ send_message(chat_id=ankit_telegram, text="Morning! Portfolio at $45.2k...") │
│                                                                              │
│ Result: message_id = 98765                                                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ FIRE REPORT                                                                  │
│                                                                              │
│ POST /v1/intents/trigger_abc123/fire                                         │
│ {                                                                            │
│   status: "success",                                                         │
│   message_id: 98765,                                                         │
│   message_preview: "Morning! Portfolio at $45.2k...",                        │
│   tools_called: ["get_portfolio"]                                            │
│ }                                                                            │
│                                                                              │
│ agentic-memories updates:                                                    │
│ - fire_count: 1                                                              │
│ - last_fired: "2025-12-26T08:30:15-08:00"                                    │
│ - next_check: "2025-12-27T08:30:00-08:00" (next weekday)                     │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ USER'S TELEGRAM                                                              │
│                                                                              │
│ ┌─────────────────────────────────────────────────────────────────────────┐ │
│ │ 🤖 Annie                                                       8:30 AM │ │
│ │                                                                          │ │
│ │ Morning! Portfolio at $45.2k, up 1.2%. NVDA leading at +3.1%.            │ │
│ └─────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 10.3 Condition Trigger Flow (Price Alert)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ TRIGGER: "NVDA price alert" - Condition: NVDA < 130                          │
│ check_interval_minutes: 5                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────┼──────────────────────────┐
         │                          │                          │
         ▼                          ▼                          ▼
    10:00 AM                   10:05 AM                   10:10 AM
         │                          │                          │
         ▼                          ▼                          ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ Evaluate        │      │ Evaluate        │      │ Evaluate        │
│ NVDA = $132.50  │      │ NVDA = $131.20  │      │ NVDA = $129.80  │
│ 132.50 < 130?   │      │ 131.20 < 130?   │      │ 129.80 < 130?   │
│ FALSE           │      │ FALSE           │      │ TRUE ✓          │
└────────┬────────┘      └────────┬────────┘      └────────┬────────┘
         │                        │                        │
         ▼                        ▼                        ▼
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ Update          │      │ Update          │      │ FIRE TRIGGER    │
│ next_check      │      │ next_check      │      │                 │
│ += 5 minutes    │      │ += 5 minutes    │      │ → Gate check    │
└─────────────────┘      └─────────────────┘      │ → Wake-up agent │
                                                  │ → Deliver       │
                                                  │ → Apply cooldown│
                                                  └─────────────────┘
                                                           │
                                                           ▼
                                                  ┌─────────────────┐
                                                  │ Update          │
                                                  │ next_check      │
                                                  │ += 24 hours     │
                                                  │ (cooldown)      │
                                                  └─────────────────┘
```

---

## 11. Examples

### 11.1 Morning Portfolio Brief

**User Request:**
> "Every weekday morning at 8:30, give me a quick portfolio update. Keep it short and skip the boring days."

**Created Trigger:**
```json
{
    "intent_name": "Morning portfolio brief",
    "trigger_type": "scheduled",
    "schedule": {
        "mode": "cron",
        "cron_expression": "30 8 * * 1-5",
        "timezone": "America/Los_Angeles"
    },
    "action_context": {
        "original_request": "Every weekday morning at 8:30, give me a quick portfolio update. Keep it short and skip the boring days.",
        "intent_summary": "Brief weekday morning portfolio check-in. User prioritizes brevity. Skip if nothing meaningful happened.",
        "user_context": {
            "name": "Ankit",
            "timezone": "America/Los_Angeles",
            "communication_style": "Concise, casual",
            "portfolio_context": "5-6 holdings, tech-heavy, ~$45k"
        },
        "execution_instructions": "1. Fetch portfolio\n2. Skip if no holdings moved > 1%\n3. Compose 2-3 sentence summary",
        "message_guidance": "TONE: Casual\nLENGTH: 2-3 sentences\nExamples: 'Morning! Portfolio at $45k, up 1.2%. NVDA +3%.'",
        "available_tools": "Primary: get_portfolio. Avoid: internet_search (too slow)",
        "edge_cases": "Weekend: Skip. Empty portfolio: Skip or offer help."
    }
}
```

**Example Outputs:**
- Normal day: "Morning! Portfolio at $45.2k, up 1.2%. NVDA leading at +3.1%."
- Flat day: *(skipped - no message sent)*
- Down day: "Heads up - portfolio at $44.1k, down 2.4%. GOOGL dragging at -4%."

---

### 11.2 Price Alert

**User Request:**
> "Let me know when NVDA drops below $130"

**Created Trigger:**
```json
{
    "intent_name": "NVDA price alert",
    "trigger_type": "condition",
    "condition": {
        "type": "price",
        "expression": "NVDA < 130",
        "check_interval_minutes": 5,
        "cooldown_hours": 24
    },
    "action_context": {
        "original_request": "Let me know when NVDA drops below $130",
        "intent_summary": "Alert when NVDA crosses below $130. User likely sees this as buying opportunity.",
        "user_context": {
            "name": "Ankit",
            "current_nvda_position": "Owns 10 shares at $142 avg",
            "relevant_history": "Mentioned wanting to add on dips"
        },
        "execution_instructions": "1. Note exact current price\n2. Include how far below $130\n3. Brief context on daily move",
        "message_guidance": "TONE: Informative, not alarmist\nExamples: 'Hey! NVDA hit $128.50 - below your $130 target. Down 2% today.'",
        "edge_cases": "Barely crossed ($129.90): Mention it's right at the line. Big drop ($115): More serious tone."
    }
}
```

**Example Output:**
> "Hey! NVDA just hit $128.50 - below your $130 target. Down 2.1% today on broader tech weakness. Want me to dig into why?"

---

### 11.3 Silence Check-in

**User Request:**
> "Check on me if I go quiet for a couple days"

**Created Trigger:**
```json
{
    "intent_name": "Silence check-in",
    "trigger_type": "condition",
    "condition": {
        "type": "silence",
        "expression": "inactive_hours > 48",
        "check_interval_minutes": 60,
        "cooldown_hours": 72
    },
    "action_context": {
        "original_request": "Check on me if I go quiet for a couple days",
        "intent_summary": "Gentle check-in after 48h inactivity. Relationship-building, not pushy.",
        "user_context": {
            "name": "Ankit",
            "typical_usage": "Usually messages every 1-2 days"
        },
        "execution_instructions": "1. Note how long since last contact\n2. Fetch portfolio for something to mention\n3. Compose warm, brief check-in",
        "message_guidance": "TONE: Warm, caring, NOT needy\nLENGTH: 1-2 sentences\nExamples: 'Hey, hope you're having a good week! Portfolio holding steady if you were curious.'",
        "edge_cases": "User just messaged (race condition): Be extra brief. Something bad happened in portfolio: Don't lead with bad news in check-in."
    }
}
```

**Example Output:**
> "Hey, haven't heard from you in a couple days - hope all's well! Portfolio's at $45k, up slightly while you were away. No rush to respond!"

---

### 11.4 Weekly Tech vs S&P Comparison

**User Request:**
> "Every Friday, tell me how my tech stocks did compared to the S&P this week. Keep it casual."

**Created Trigger:**
```json
{
    "intent_name": "Weekly tech vs S&P",
    "trigger_type": "scheduled",
    "schedule": {
        "mode": "cron",
        "cron_expression": "0 17 * * 5",
        "timezone": "America/Los_Angeles"
    },
    "action_context": {
        "original_request": "Every Friday, tell me how my tech stocks did compared to the S&P this week. Keep it casual.",
        "intent_summary": "Weekly comparative analysis: user's tech holdings vs S&P 500. Casual tone, focus on relative performance.",
        "user_context": {
            "name": "Ankit",
            "holdings": "Primarily tech: NVDA, AAPL, GOOGL, MSFT"
        },
        "execution_instructions": "1. Fetch portfolio with weekly performance\n2. Calculate aggregate tech performance\n3. Fetch S&P 500 weekly performance\n4. Compare and compose message",
        "message_guidance": "TONE: Casual, celebratory if outperformed, reassuring if underperformed\nExamples: 'Week in review: Your tech holdings crushed it at +4.2% vs S&P's +1.1%. NVDA did the heavy lifting.'",
        "available_tools": "get_portfolio, analyze_stock (for S&P comparison)",
        "edge_cases": "Short week (holiday): Mention it. Significant underperformance: Reassure, don't alarm."
    }
}
```

**Example Output:**
> "Week in review: Your tech holdings up 4.2% vs S&P's 1.1%. NVDA doing the heavy lifting at +7%. Nice week! 🎉"

---

## 12. Security & Safety

### 12.1 Subconscious Gate

Prevents Annie from becoming annoying or spammy.

| Check | Limit | Behavior |
|-------|-------|----------|
| Recent contact | 1 hour | Skip if user messaged < 1h ago |
| Daily limit | 5 messages | Skip if 5 proactive messages sent today |
| Quiet hours | 10 PM - 8 AM | Defer to 8 AM next day |
| User opt-out | Flag | Skip entirely if user disabled |

```python
async def check_subconscious_gate(user_id: str) -> GateResult:
    """Check if proactive message is allowed."""

    # Check 1: Recent contact
    last_activity = await redis.get(f"user:{user_id}:last_activity")
    if last_activity and (now() - last_activity) < timedelta(hours=1):
        return GateResult(allowed=False, reason="recent_contact")

    # Check 2: Daily limit
    daily_count = await redis.get(f"proactive:{user_id}:daily:{today()}")
    if daily_count and int(daily_count) >= 5:
        return GateResult(allowed=False, reason="daily_limit")

    # Check 3: Quiet hours
    user_tz = await get_user_timezone(user_id)
    user_hour = now().astimezone(user_tz).hour
    if 22 <= user_hour or user_hour < 8:
        return GateResult(
            allowed=False,
            reason="quiet_hours",
            defer_until=next_8am(user_tz)
        )

    # Check 4: User preference
    prefs = await get_user_preferences(user_id)
    if not prefs.get("proactive_enabled", True):
        return GateResult(allowed=False, reason="user_opt_out")

    return GateResult(allowed=True)
```

### 12.2 Rate Limiting

| Resource | Limit |
|----------|-------|
| Triggers per user | 20 max |
| Condition checks per minute | 100 across all users |
| LLM calls per trigger fire | 5 max |
| Message length | 500 characters |

### 12.3 Content Safety

- Wake-up agent uses same content policies as chat
- No ability to modify portfolio (restricted tools)
- No ability to delete own triggers from wake-up context
- All messages logged for review

---

## 13. Observability

### 13.1 Langfuse Tracing

Every trigger execution is traced:

```python
@observe(name="trigger_execution")
async def process_trigger(trigger: dict):
    langfuse.update_current_observation(
        metadata={
            "trigger_id": trigger["id"],
            "trigger_type": trigger["trigger_type"],
            "user_id": trigger["user_id"],
        }
    )

    # ... execution ...

    langfuse.update_current_observation(
        output={
            "status": result.status,
            "message_sent": result.message is not None,
            "tools_called": result.tools_called,
        }
    )
```

### 13.2 Metrics

| Metric | Description |
|--------|-------------|
| `proactive.triggers.created` | Triggers created |
| `proactive.triggers.fired` | Trigger fire attempts |
| `proactive.triggers.success` | Successful message sends |
| `proactive.triggers.skipped` | Skipped by action_context logic |
| `proactive.triggers.gate_blocked` | Blocked by subconscious gate |
| `proactive.triggers.error` | Errors during execution |
| `proactive.wake_up.latency_ms` | Wake-up agent execution time |
| `proactive.wake_up.tools_called` | Average tools per execution |

### 13.3 Logging

```python
logger.info(
    "Trigger fired",
    extra={
        "trigger_id": trigger["id"],
        "trigger_name": trigger["intent_name"],
        "trigger_type": trigger["trigger_type"],
        "user_id": trigger["user_id"],
        "status": result.status,
        "tools_called": result.tools_called,
        "execution_time_ms": execution_time,
    }
)
```

---

## 14. Dependencies

### 14.1 External Dependencies

| Dependency | Status | Notes |
|------------|--------|-------|
| agentic-memories Intents API | Required | Epic 5 - CRUD, /pending, /fire |
| Redis | Existing | Activity tracking, gate state |
| Telegram Bot | Existing | Message delivery |

### 14.2 New Python Dependencies

```
arq>=0.25.0          # Background worker
croniter>=2.0.0      # Cron expression parsing
yfinance>=0.2.0      # Stock price fetching (for condition evaluation)
```

### 14.3 agentic-memories API Requirements

**Required Endpoints:**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/intents` | POST | Create trigger |
| `/v1/intents` | GET | List triggers |
| `/v1/intents/{id}` | GET | Get trigger |
| `/v1/intents/{id}` | PUT | Update trigger |
| `/v1/intents/{id}` | DELETE | Delete trigger |
| `/v1/intents/pending` | GET | Get due triggers |
| `/v1/intents/{id}/fire` | POST | Report execution |

---

## 15. Glossary

| Term | Definition |
|------|------------|
| **Trigger** | A stored instruction that causes Annie to initiate contact |
| **Scheduled Trigger** | Fires at specific times (cron or one-time) |
| **Condition Trigger** | Fires when a condition becomes true |
| **action_context** | Rich briefing document for wake-up LLM |
| **Creation LLM** | The LLM that creates triggers during normal chat |
| **Wake-up LLM** | The LLM that executes triggers when they fire |
| **Subconscious Gate** | Spam prevention layer |
| **Fire** | When a trigger activates and sends a message |
| **Skip** | When a trigger activates but decides not to send |
| **Cooldown** | Minimum time between fires for condition triggers |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-12-24 | Ankit + Claude Code | Initial draft |
| 1.1 | 2025-12-24 | Ankit + Claude Code | Added: (A) Stale context prevention in user_context, (B) Feedback Handler for closed-loop learning, (C) yfinance reliability notes, (D) Dynamic state injection for wake-up agent |
| 1.2 | 2025-12-24 | Ankit + Claude Code | Removed guardrails (tool limits), added dynamic tool discovery from MCP, 10-min timeout. Created agentic-memories Epic 6 for API alignment. |

---

*End of Document*
