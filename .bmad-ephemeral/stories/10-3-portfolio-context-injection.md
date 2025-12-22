# Story 10.3: Portfolio Context Injection

Status: done

## Story

As a **developer**,
I want **portfolio data formatted and injected into LLM system prompts**,
So that **Annie has portfolio awareness in every financial conversation**.

## Acceptance Criteria

**AC #1:** Given user has portfolio, when chat request processed, then portfolio summary is injected into system prompt under "USER PORTFOLIO:" header showing holdings with ticker, shares, and avg_price

**AC #2:** Given portfolio caching, when portfolio loaded, then data is cached in Redis with 5-minute TTL (more dynamic than profile's 15 min)

**AC #3:** Given portfolio cache load, then performance is <10ms (p95) with no blocking of chat response

**AC #4:** Given agentic-memories unavailable, when portfolio loaded, then graceful degradation (empty portfolio, no crash)

**AC #5:** Given portfolio injection, when Annie responds to financial query, then she references user's actual holdings in her response

## Tasks / Subtasks

- [ ] **Task 1: Create PortfolioManager class** (AC: #1, #2, #3, #4)
  - [ ] Create `backend/api/portfolio_context.py`
  - [ ] Implement `PortfolioManager` with Redis caching (5 min TTL)
  - [ ] Implement `load_portfolio_from_cache()` - non-blocking, <10ms
  - [ ] Implement `refresh_portfolio_background()` - fetches via MCP tool
  - [ ] Add Langfuse tracing with `@observe` decorators

- [ ] **Task 2: Create portfolio formatting function** (AC: #1)
  - [ ] Add `format_portfolio_for_prompt()` in `backend/api/prompts.py`
  - [ ] Format holdings as readable text:
    ```
    USER PORTFOLIO:
    Total Holdings: 3 stocks

    Holdings:
    - AAPL: 10 shares @ $175.50 avg
    - GOOGL: 5 shares @ $145.00 avg
    - MSFT: 15 shares @ $420.00 avg
    ```

- [ ] **Task 3: Update build_system_prompt** (AC: #1)
  - [ ] Add `portfolio` parameter to `build_system_prompt()`
  - [ ] Inject formatted portfolio after USER PROFILE section

- [ ] **Task 4: Update stream route** (AC: #1, #2, #3)
  - [ ] Load portfolio from cache in stream.py (like profile)
  - [ ] Pass portfolio to `build_system_prompt()`
  - [ ] Cache portfolio during chat endpoint (like profile)

- [ ] **Task 5: Testing** (AC: #1, #2, #3, #4, #5)
  - [ ] Test portfolio appears in system prompt
  - [ ] Test cache hit/miss behavior
  - [ ] Test graceful degradation when service down
  - [ ] Test via Telegram: Ask financial question, verify Annie mentions holdings

## Dev Notes

### Pattern: Follow Profile Injection

This follows the same pattern as Story 7.1 (Profile Integration):
- `ProfileManager` → `PortfolioManager`
- `format_profile_for_prompt()` → `format_portfolio_for_prompt()`
- Redis cache: `profile:{user_id}` → `portfolio:{user_id}`

### Key Differences from Profile

| Aspect | Profile | Portfolio |
|--------|---------|-----------|
| TTL | 15 minutes | 5 minutes (more dynamic) |
| Refresh Triggers | Every 5 msgs or 15 min | On first load, then TTL-based |
| Complexity | 5 categories, 21 fields | Simple list of holdings |
| Source | `get_user_profile` MCP tool | `get_portfolio` MCP tool |

### Redis Keys

- `portfolio:{user_id}` - Cached portfolio data (TTL: 300s = 5 min)

### Files to Modify/Create

- **Create:** `backend/api/portfolio_context.py`
- **Modify:** `backend/api/prompts.py` - Add `format_portfolio_for_prompt()`
- **Modify:** `backend/api/prompts.py` - Update `build_system_prompt()`
- **Modify:** `backend/api/routes/stream.py` - Load and inject portfolio
- **Modify:** `backend/api/routes/chat.py` - Cache portfolio on chat start

### Example System Prompt Injection

```
Current user ID: 123456

USER PROFILE:
Profile Completeness: 45%
Name: Ankit
Location: San Francisco
...

USER PORTFOLIO:
Total Holdings: 3 stocks

Holdings:
- AAPL: 10 shares @ $175.50 avg
- GOOGL: 5 shares @ $145.00 avg
- MSFT: 15 shares @ $420.00 avg

Current date and time (Pacific): 2025-12-14T22:00:00-08:00
...
```

## References

- Profile pattern: `backend/api/profile.py`
- Prompts: `backend/api/prompts.py`
- Stream route: `backend/api/routes/stream.py`
- Epic 10: `docs/epics/epic-10-portfolio-management.md`
