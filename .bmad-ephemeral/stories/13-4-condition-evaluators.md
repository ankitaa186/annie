# Story 13.4: Condition Evaluators

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.4
**Status:** ready-for-dev
**Estimated Effort:** 0.5 days

---

## User Story

**As a** system,
**I want** fast condition evaluators for different trigger types,
**So that** condition triggers can be evaluated without LLM calls.

---

## Acceptance Criteria

### AC #1: Price Evaluator
**Given** price condition trigger,
**When** evaluated,
**Then:**
- Fetches current price via yfinance
- Parses expression (e.g., "NVDA < 130")
- Supports operators: `<`, `>`, `<=`, `>=`
- Returns True if condition met
- Caches price for 60 seconds (avoid rate limits)
- **Reliability handling** (yfinance is unofficial scraper):
  - Retry with exponential backoff (3 attempts)
  - Fail-safe: return False on error (don't fire on error)
  - Log errors for monitoring

### AC #2: Portfolio Evaluator
**Given** portfolio condition trigger,
**When** evaluated,
**Then:**
- Fetches portfolio via get_portfolio
- Supports expressions:
  - `any_holding_change > X%`
  - `any_holding_down > X%`
  - `total_value >= X`
  - `total_change > X%`
- Returns True if condition met

### AC #3: Silence Evaluator
**Given** silence condition trigger,
**When** evaluated,
**Then:**
- Checks Redis for `user:{user_id}:last_activity`
- Compares against threshold from expression
- Returns True if silence exceeded

### AC #4: Error Handling
**Given** evaluator failure,
**When** exception occurs,
**Then:**
- Returns False (fail-safe, don't fire on error)
- Logs error with trigger details
- Does not crash worker

---

## Tasks

### Task 1: Create evaluators module structure
- [x] Create `backend/api/proactive/evaluators.py`
- [x] Define `EvaluatorResult` dataclass (met: bool, reason: str, data: dict)
- [x] Create base `Evaluator` class with `evaluate()` method

### Task 2: Implement Price Evaluator
- [x] Create `PriceEvaluator` class
- [x] Parse expression to extract ticker and comparison
- [x] Fetch price via yfinance with retry logic
- [x] Implement 60-second price caching in Redis
- [x] Handle yfinance failures gracefully (return False)

### Task 3: Implement Portfolio Evaluator
- [x] Create `PortfolioEvaluator` class
- [x] Parse expression types (any_holding_change, any_holding_down, total_value, total_change)
- [x] Fetch portfolio via existing get_portfolio infrastructure
- [x] Calculate changes and compare against thresholds

### Task 4: Implement Silence Evaluator
- [x] Create `SilenceEvaluator` class
- [x] Parse silence threshold from expression (e.g., "silence > 4h")
- [x] Check Redis for last activity timestamp
- [x] Calculate time since last activity

### Task 5: Create evaluator factory
- [x] Create `get_evaluator(condition_type: str) -> Evaluator`
- [x] Map condition types to evaluator classes
- [x] Handle unknown condition types gracefully

---

## Dev Notes

### Technical Notes
- These are FAST evaluations (no LLM)
- LLM only invoked after condition passes
- See Design Doc Section 3.3
- yfinance is unofficial API - handle failures gracefully

### Files to Create/Modify
- `backend/api/proactive/evaluators.py` (new)
- `backend/api/proactive/__init__.py` (new - package init)

### Expression Parsing Examples
```python
# Price: "NVDA < 130"
ticker = "NVDA", operator = "<", value = 130

# Portfolio: "any_holding_change > 5%"
type = "any_holding_change", operator = ">", value = 5

# Silence: "silence > 4h"
type = "silence", operator = ">", value = timedelta(hours=4)
```

### Caching Strategy
- Price cache key: `price_cache:{ticker}`
- TTL: 60 seconds
- Prevents rate limiting on yfinance

---

## Dev Agent Record

### Context Reference
- **Story Context:** `.bmad-ephemeral/stories/13-4-condition-evaluators.context.xml`
- **Design Document:** `docs/design/proactive-ai-architecture.md` (Section 3.3)
- **Epic Document:** `docs/epics/epic-13-proactive-ai.md`

### Implementation Notes

**File Created:** `/Users/ankit/dev/annie/backend/api/proactive/evaluators.py`

**Implementation Summary:**

1. **Base Classes:**
   - `EvaluatorResult` dataclass with `met`, `reason`, and `data` fields
   - `Evaluator` abstract base class with Redis connection management
   - All evaluators inherit from base and implement `evaluate()` method

2. **PriceEvaluator:**
   - Uses yfinance for stock price fetching
   - Expression parsing regex: `([A-Z0-9\.]+)\s*([<>]=?)\s*([\d.]+)`
   - 60-second Redis caching with key pattern: `price_cache:{ticker}`
   - 3-attempt retry with exponential backoff (1s, 2s, 4s)
   - Ticker validation using pattern: `[A-Z0-9\.]{1,10}`
   - Tries multiple yfinance price fields (currentPrice, regularMarketPrice, fast_info.lastPrice)
   - Fail-safe: returns False on any error

3. **PortfolioEvaluator:**
   - Uses MCP client to call `get_portfolio` tool
   - Expression parsing regex: `(any_holding_change|any_holding_down|total_value|total_change)\s*([<>]=?)\s*([\d.]+)%?`
   - Supports 4 expression types:
     - `any_holding_change`: Max absolute change across all holdings
     - `any_holding_down`: Max negative change (only down movements)
     - `total_value`: Total portfolio value comparison
     - `total_change`: Total portfolio change percentage
   - Fail-safe: returns False on MCP errors or portfolio fetch failures

4. **SilenceEvaluator:**
   - Expression parsing regex: `silence\s*([<>]=?)\s*(\d+)(h|d|m)`
   - Supports hours (h), days (d), minutes (m) units
   - Redis key pattern: `user:{user_id}:last_activity`
   - Compares current time vs last activity timestamp
   - Human-readable duration formatting in results
   - Fail-safe: returns False if no activity timestamp found

5. **Factory Function:**
   - `get_evaluator(condition_type)` maps type to evaluator class
   - `evaluate_condition()` convenience function with automatic cleanup

6. **Features Implemented:**
   - Langfuse tracing on all evaluators with `@observe` decorators
   - Structured logging with duration tracking
   - Comprehensive error handling with fail-safe behavior
   - Redis connection pooling and cleanup
   - All operators supported: `<`, `>`, `<=`, `>=`

### Verification
- [x] Price evaluator correctly evaluates <, >, <=, >= operators
- [x] Portfolio evaluator handles all expression types
- [x] Silence evaluator correctly calculates time since activity
- [x] All evaluators return False on error (fail-safe)
- [x] Price caching reduces yfinance calls (60s TTL)
