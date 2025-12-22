# Epic 10: Portfolio Management & Financial Tools

**Status:** Planned
**Priority:** High (Foundation for Stock Trading Features)
**Estimated Effort:** 6.5-7.5 days
**Author:** John (PM) with Winston (Architect)
**Date:** 2025-12-14

---

## Overview

Enable Annie to access, manage, and understand the user's investment portfolio through integration with agentic-memories' portfolio service. This epic establishes the foundation for all stock trading and financial advisory features.

**Key Insight:** The agentic-memories service already provides a rich portfolio management system with holdings tracking, intent management (hold/watch/buy/sell), and multiple asset types. Annie needs MCP tools to leverage this existing infrastructure.

---

## Business Value

1. **Personalized Financial Advice**: Annie can see what the user owns before making recommendations
2. **Portfolio Awareness**: "You already have 20% in tech stocks" type insights
3. **Watchlist Management**: Track stocks the user is interested in buying
4. **Investment Tracking**: Record purchases, track cost basis, monitor performance
5. **Stock Analysis & Recommendations**: Full stock analysis and personalized advice capabilities

**Strategic Driver:** Without portfolio access, Annie's stock advice is generic. With it, advice becomes personalized and actionable.

---

## Technical Architecture

### Integration with agentic-memories

```
Annie Backend
    │
    ▼
MCP Server (Portfolio Tools)
    │
    ▼ HTTP
agentic-memories /v1/portfolio API
    │
    ▼
TimescaleDB (portfolio_holdings table)
```

### Available agentic-memories Endpoints

| Endpoint | Method | Status | Description |
|----------|--------|--------|-------------|
| `/v1/portfolio` | GET | ✅ Ready | Get all holdings for user |
| `/v1/portfolio/holding` | POST | ✅ Ready | Add/update holding (UPSERT) |
| `/v1/portfolio/holding/{ticker}` | PUT | ✅ Ready | Update specific holding (partial updates) |
| `/v1/portfolio/holding/{ticker}` | DELETE | ✅ Ready | Delete single holding |
| `/v1/portfolio` | DELETE | ✅ Ready | Clear all holdings (requires confirmation) |

### Portfolio Data Model (from agentic-memories)

```python
PortfolioHolding:
  - ticker: str              # Stock symbol (e.g., "AAPL")
  - asset_name: str          # Human name (e.g., "Apple Inc.")
  - asset_type: enum         # public_equity, etf, crypto, cash, bond, etc.
  - shares: float            # Number of shares owned
  - avg_price: float         # Average purchase price
  - current_value: float     # Current market value
  - cost_basis: float        # Total cost basis
  - position: enum           # long, short
  - intent: enum             # hold, wants-to-buy, wants-to-sell, watch
  - target_price: float      # Target sell price
  - stop_loss: float         # Stop loss price
  - time_horizon: enum       # days, weeks, months, years
  - notes: str               # User notes
```

---

## Stories Breakdown

### Story 10.1: Portfolio Access MCP Tools

**Goal:** Create MCP tools to read portfolio and add holdings using existing agentic-memories endpoints.

**As a** user,
**I want** Annie to see my investment portfolio,
**So that** she can give me personalized financial advice based on what I own.

**Acceptance Criteria:**

**AC #1: get_portfolio MCP Tool**
Given `get_portfolio` MCP tool, when called with user_id, then tool:
- Makes HTTP GET to `{AGENTIC_MEMORIES_URL}/v1/portfolio?user_id={user_id}`
- Returns structured portfolio data:
  ```json
  {
    "user_id": "123",
    "holdings": [
      {"ticker": "AAPL", "shares": 10, "avg_price": 150.00, ...},
      {"ticker": "GOOGL", "shares": 5, "avg_price": 140.00, ...}
    ],
    "total_holdings": 2,
    "last_updated": "2025-12-14T10:00:00Z"
  }
  ```
- Returns empty holdings array if user has no portfolio

**AC #2: add_holding MCP Tool**
Given `add_holding` MCP tool, when called with holding data, then tool:
- Makes HTTP POST to `{AGENTIC_MEMORIES_URL}/v1/portfolio/holding`
- Request body:
  ```json
  {
    "user_id": "123",
    "ticker": "AAPL",
    "asset_name": "Apple Inc.",
    "shares": 10,
    "avg_price": 150.00
  }
  ```
- Returns created/updated holding with `created: true/false` flag
- Handles UPSERT: updates if ticker exists, creates if new

**AC #3: LLM Integration**
Given portfolio tools registered, when user asks "what stocks do I own?", then:
- LLM calls `get_portfolio` tool via function calling
- Annie responds with formatted portfolio summary
- Example: "You currently own 10 shares of AAPL at $150 avg and 5 shares of GOOGL at $140 avg."

**AC #4: Error Handling**
Given agentic-memories unavailable, when portfolio tool called, then:
- Tool returns graceful error message
- Annie informs user: "I'm having trouble accessing your portfolio right now."
- No crash, conversation continues

**AC #5: Ticker Normalization**
Given user provides lowercase ticker (e.g., "aapl"), when adding holding, then:
- Ticker normalized to uppercase ("AAPL")
- Invalid tickers (>10 chars, special chars) rejected with clear error

**Prerequisites:** Story 1.6 (MCP Server Foundation), Story 2.4 (Function Calling)

**Technical Notes:**
- MCP tool file: `mcp_server/tools/portfolio.py`
- Tool schemas registered in `mcp_server/tools.py`
- Use existing HTTP client pattern from memory tools
- Langfuse tracing for portfolio operations

**Estimated Effort:** 1 day

---

### Story 10.2: Watchlist & Intent Tracking

**Goal:** Enable Annie to track stocks the user is watching or interested in buying, separate from actual holdings.

**As a** user,
**I want** Annie to remember stocks I'm interested in but don't own yet,
**So that** she can alert me to opportunities and track my research.

**Acceptance Criteria:**

**AC #1: get_watchlist Tool**
Given `get_watchlist` MCP tool, when called, then:
- Retrieves holdings with intent = `watch` or `wants-to-buy`
- Returns structured watchlist:
  ```json
  {
    "watchlist": [
      {"ticker": "NVDA", "intent": "wants-to-buy", "target_price": 800.00, "notes": "Wait for dip"},
      {"ticker": "TSLA", "intent": "watch", "notes": "Monitoring Q4 earnings"}
    ]
  }
  ```

**AC #2: add_to_watchlist Tool**
Given `add_to_watchlist` MCP tool, when called, then:
- Creates holding with intent = `watch` or `wants-to-buy`
- Does NOT add to actual portfolio (speculative entries filtered by agentic-memories)
- Stores target_price, notes, time_horizon if provided

**AC #3: Intent Distinction**
Given LLM context, when user says "I want to buy NVDA", then:
- Annie recognizes buy intent
- Adds to watchlist with intent = `wants-to-buy`
- Does NOT add to portfolio holdings
- Responds: "I've added NVDA to your watchlist. I'll keep an eye on it for you."

**AC #4: Watchlist vs Holdings Separation**
Given user asks "what do I own?", then:
- Only actual holdings returned (intent = `hold` or null)
- Watchlist items NOT included in portfolio value

**Prerequisites:** Story 10.1

**Technical Notes:**
- Leverages agentic-memories intent filtering (SPECULATIVE_INTENTS already filtered)
- May need separate tool or filter parameter on get_portfolio
- Consider: Should watchlist items be stored differently?

**Estimated Effort:** 0.5 days

---

### Story 10.3: Portfolio Summary for LLM Context

**Goal:** Format portfolio data into LLM-digestible context for informed decision making.

**As a** developer,
**I want** portfolio data formatted for LLM system prompts,
**So that** Annie has portfolio awareness in every financial conversation.

**Acceptance Criteria:**

**AC #1: Portfolio Context Injection**
Given user has portfolio, when chat request processed, then:
- Portfolio summary injected into system prompt (like profile injection)
- Format:
  ```
  USER PORTFOLIO:
  Total Holdings: 5 stocks

  Holdings:
  - AAPL: 10 shares @ $150 avg (current: $175, +16.7%)
  - GOOGL: 5 shares @ $140 avg (current: $145, +3.6%)
  - MSFT: 8 shares @ $380 avg (current: $390, +2.6%)

  Watchlist:
  - NVDA (wants-to-buy, target: $800)
  - TSLA (watching)

  Sector Exposure: 60% Tech, 20% Finance, 20% Healthcare
  ```

**AC #2: Caching Strategy**
Given portfolio caching, when portfolio loaded, then:
- Portfolio cached in Redis (like profile caching)
- TTL: 5 minutes (more dynamic than profile)
- Background refresh on financial queries

**AC #3: Performance Requirements**
Given portfolio context injection, then:
- Cache load: <10ms (p95)
- No blocking of chat response
- Graceful degradation if unavailable

**AC #4: Smart Injection**
Given conversation context, when financial topic detected, then:
- Portfolio injected into context
- For non-financial queries, portfolio may be omitted (reduce token usage)

**Prerequisites:** Story 10.1, Story 7.1 (Profile pattern to follow)

**Technical Notes:**
- Follow pattern from `backend/api/profile.py`
- New module: `backend/api/portfolio_context.py`
- Injection point: `backend/api/routes/stream.py`
- Consider sector calculation (may need external data)

**Estimated Effort:** 1 day

---

### Story 10.4: Portfolio Update & Remove Tools

**Goal:** Enable full CRUD operations on portfolio when agentic-memories endpoints are ready.

**As a** user,
**I want** to update or remove holdings from my portfolio,
**So that** my portfolio stays accurate as I buy/sell stocks.

**Acceptance Criteria:**

**AC #1: update_holding Tool**
Given `update_holding` MCP tool, when called, then:
- Makes HTTP PUT to `{AGENTIC_MEMORIES_URL}/v1/portfolio/holding/{id}`
- Updates specific fields (shares, avg_price, notes, etc.)
- Preserves fields not included in update

**AC #2: remove_holding Tool**
Given `remove_holding` MCP tool, when called with ticker, then:
- Removes holding from portfolio
- Returns confirmation

**AC #3: clear_portfolio Tool**
Given `clear_portfolio` MCP tool, when called, then:
- Removes ALL holdings for user
- Requires confirmation (double-check with user)
- Returns count of removed holdings

**AC #4: Conversational Updates**
Given user says "I sold my Apple stock", then:
- Annie asks: "How many shares did you sell?"
- Updates or removes holding accordingly
- Confirms: "I've updated your portfolio. You now have X shares of AAPL remaining."

**Prerequisites:** Story 10.1, agentic-memories PUT/DELETE endpoints ✅

**Technical Notes:**
- agentic-memories endpoints now available:
  - PUT `/v1/portfolio/holding/{ticker}` - Update with partial updates support
  - DELETE `/v1/portfolio/holding/{ticker}?user_id=xxx` - Delete single holding
  - DELETE `/v1/portfolio?user_id=xxx&confirmation=DELETE_ALL` - Clear all holdings
- Clear portfolio requires confirmation="DELETE_ALL" for safety

**Estimated Effort:** 0.5 days

**Status:** UNBLOCKED - Ready for implementation

---

### Story 10.5: Portfolio Value & Performance Tracking (Simplified)

**Goal:** Enhance `get_portfolio` tool to optionally include current prices and performance metrics.

**As a** user,
**I want** to know how my portfolio is performing,
**So that** I can make informed decisions about buying or selling.

**Design Decision:** Instead of creating a separate `get_portfolio_summary` tool, enhance the existing `get_portfolio` tool with an optional `include_prices` parameter. The LLM can calculate gains/losses from the enriched data, reducing tool proliferation and saving implementation effort.

**Acceptance Criteria:**

**AC #1: Enhanced get_portfolio with Prices**
Given `get_portfolio` tool with `include_prices=true`, when called, then:
- Fetch current prices for all tickers in a single batch (yfinance supports this)
- Enrich each holding with current price and calculated values
- Return enhanced response:
  ```json
  {
    "user_id": "123",
    "holdings": [
      {
        "ticker": "AAPL",
        "shares": 10,
        "avg_price": 150.00,
        "current_price": 175.50,
        "current_value": 1755.00,
        "cost_basis": 1500.00,
        "gain_loss": 255.00,
        "gain_loss_pct": 17.0
      }
    ],
    "total_holdings": 2,
    "total_value": 3500.00,
    "total_cost_basis": 2800.00,
    "total_gain_loss": 700.00,
    "total_gain_loss_pct": 25.0,
    "last_updated": "2025-12-14T10:00:00Z"
  }
  ```

**AC #2: Backward Compatibility**
Given `get_portfolio` without `include_prices` (or `include_prices=false`), then:
- Returns original response format (no price fetching)
- Fast response for simple "what do I own?" queries

**AC #3: Batch Price Fetching**
Given portfolio with multiple holdings, when prices requested, then:
- Use single batch call to yfinance (not N individual calls)
- Handle partial failures gracefully (some tickers may fail)
- Cache prices for 5 minutes to reduce API load

**AC #4: Performance Display**
Given user asks "how is my portfolio doing?", then:
- LLM calls `get_portfolio` with `include_prices=true`
- LLM interprets the enriched data and responds naturally:
  "Your portfolio is worth $15,000, up $3,000 (25%) from your $12,000 cost basis. 
   AAPL is your top performer at +45%, while TSLA needs attention at -10%."

**AC #5: Error Handling**
Given price fetch fails for some tickers, then:
- Return holdings with `current_price: null` for failed tickers
- Include `price_fetch_errors` array with failed tickers
- LLM can still provide partial information

**Prerequisites:** Story 10.1, Story 10.6 (Yahoo Finance integration)

**Technical Notes:**
- Modify existing `get_portfolio_tool_handler` in `mcp_server/tools.py`
- Add `include_prices: bool = false` parameter to tool schema
- Use `yfinance.download(tickers, period="1d")` for batch fetching
- Cache layer: Redis with 5-minute TTL keyed by ticker
- LLM calculates top/worst performers from the data (good at this)

**Estimated Effort:** 1 day (reduced from 1.5 days - no new tool needed)

---

### Story 10.6: Stock Market Analysis Tool ✅ COMPLETE

**Status:** ✅ Implemented  
**Completed:** 2025-12-15

**Goal:** Enable Annie to analyze stocks and provide market insights using real-time data.

**As a** user,
**I want** Annie to analyze stocks and provide market insights,
**So that** I can make informed investment decisions.

*Moved from Epic 4 Story 4.2*

**Implementation Summary:**
- `analyze_stock` tool: `mcp_server/tools.py:1787`
- `get_stock_history` tool: `mcp_server/tools.py:2006`
- Both registered in `mcp_server/server.py:83-84`

**Acceptance Criteria:** All Complete ✅

| AC | Description | Status |
|----|-------------|--------|
| AC #1 | analyze_stock with price, change, 52-week range, P/E, market cap, volume | ✅ |
| AC #2 | Technical indicators (RSI, 50/200 MA, trend, volume analysis) | ✅ |
| AC #3 | get_stock_history with multiple period options | ✅ |
| AC #4 | LLM integration via tool registration | ✅ |
| AC #5 | Error handling for invalid tickers | ✅ |

**Deferred to Story 10.5:**
- Price caching (5-minute TTL) - will be implemented as part of batch price fetching

**Actual Effort:** ~1 day (tools already implemented)

---

### Story 10.7: Personalized Stock Recommendations

**Status:** ❌ REJECTED
**Decision Date:** 2025-12-16
**Rationale:** Redundant - LLM already handles personalized recommendations naturally via portfolio context injection (Story 10.3). With portfolio data, user profile, and stock analysis tools available in LLM context, a dedicated recommendation tool would constrain rather than enhance the LLM's reasoning capabilities.

~~**Goal:** Provide personalized stock recommendations based on user's portfolio, risk profile, and preferences.~~

**As a** user,
**I want** Annie to give me personalized stock recommendations,
**So that** investment advice matches my situation and preferences.

*Moved from Epic 4 Story 4.3*

**Acceptance Criteria:**

**AC #1: recommend_action Tool**
Given `recommend_action` MCP tool, when called with ticker and user context, then:
- Analyzes stock via 10.6
- Considers user's portfolio (via 10.1)
- Considers user's profile/preferences (via 7.1)
- Returns structured recommendation:
  ```json
  {
    "ticker": "AAPL",
    "action": "HOLD",
    "confidence": "medium",
    "reasoning": [
      "You already own 10 shares at $150 avg",
      "Current price $175 = 16.7% gain",
      "RSI neutral, no strong buy/sell signal",
      "Your tech exposure is already at 40%"
    ],
    "risk_assessment": "low",
    "time_horizon": "long-term"
  }
  ```

**AC #2: Portfolio-Aware Recommendations**
Given user asks "Should I buy more AAPL?", then Annie considers:
- Current holdings (already own 10 shares)
- Cost basis and current gain/loss
- Sector exposure (40% tech might be too concentrated)
- Risk tolerance from profile

**AC #3: Risk Profile Integration**
Given user's risk profile from memories, then:
- Conservative: Focus on stability, dividends, lower volatility
- Moderate: Balanced growth and income
- Aggressive: Growth focus, higher risk tolerance

**AC #4: Diversification Awareness**
Given user's portfolio, when recommending, then Annie:
- Warns about over-concentration: "You already have 40% in tech"
- Suggests diversification: "Consider adding healthcare or utilities"
- Notes correlation risks

**AC #5: Personalized Response**
Given user asks "What should I invest in?", then Annie:
- Reviews portfolio composition
- Identifies gaps and opportunities
- Provides 2-3 personalized suggestions with reasoning
- References past decisions from memory if available

**Prerequisites:** Story 10.1, 10.3, 10.6, 7.1

**Technical Notes:**
- Combine data from multiple sources (portfolio, profile, market data)
- No financial advice disclaimer needed (Annie is a personal tool)
- Consider sector classification for exposure analysis
- May integrate with memory retrieval for past investment decisions

**Estimated Effort:** 1.5 days

---

## Dependencies

### External Dependencies
- agentic-memories service running with portfolio endpoints
- Yahoo Finance API (via `yfinance` library) for stock data

### Internal Dependencies
- Epic 1.6: MCP Server Foundation ✅
- Epic 2.4: Function Calling ✅
- Story 7.1: Profile pattern (for caching approach) ✅

### Blocking Dependencies
- Story 10.4 blocked on agentic-memories PUT/DELETE endpoint development

---

## Success Metrics

### Functional Metrics
- [ ] Annie can retrieve user portfolio via conversation
- [ ] Annie can add holdings via conversation
- [ ] Watchlist separate from actual holdings
- [ ] Portfolio context available in financial conversations

### Performance Metrics
- [ ] Portfolio retrieval <500ms (p95)
- [ ] Portfolio cache load <10ms (p95)
- [ ] No impact on non-financial conversation latency

### Quality Metrics
- [ ] 80%+ test coverage for portfolio tools
- [ ] All tools traced in Langfuse
- [ ] Graceful degradation when agentic-memories unavailable

---

## Rollout Strategy

### Phase 1: Foundation (Stories 10.1, 10.2)
- Implement GET/POST portfolio tools
- Basic watchlist functionality
- Can demo: "What stocks do I own?" and "Add AAPL to my portfolio"

### Phase 2: Integration (Story 10.3)
- Portfolio context injection
- Annie becomes portfolio-aware in all financial conversations

### Phase 3: Full CRUD (Story 10.4)
- When agentic-memories endpoints ready
- Complete portfolio management via conversation

### Phase 4: Performance (Story 10.5)
- Price integration
- Gain/loss tracking
- Full portfolio advisor capability

---

## Story Sequencing

```
10.1 Portfolio Access Tools (GET/POST) ✅
  │
  ├──► 10.2 Watchlist & Intent (BLOCKED)
  │
  ├──► 10.3 Portfolio Context Injection ✅
  │
  └──► 10.6 Stock Market Analysis (Yahoo Finance) ✅
         │
         └──► 10.5 Portfolio Value & Performance ✅

10.4 Update/Remove Tools ✅

Note: 10.7 REJECTED - LLM handles recommendations naturally via context
```

**Recommended Execution Order:**
1. ~~10.1 - Portfolio Access Tools (foundation)~~ ✅ DONE
2. 10.2 - Watchlist & Intent (BLOCKED - waiting on agentic-memories)
3. ~~10.6 - Stock Market Analysis (Yahoo Finance - needed for prices)~~ ✅ DONE
4. ~~10.4 - Update/Remove Tools~~ ✅ DONE
5. ~~10.3 - Portfolio Context Injection (LLM awareness)~~ ✅ DONE
6. ~~10.5 - Portfolio Value & Performance (enhance get_portfolio with prices)~~ ✅ DONE
7. ~~10.7 - Personalized Recommendations~~ ❌ REJECTED (LLM handles via context)

---

## References

- **agentic-memories Portfolio Router:** `/home/ankit/dev/agentic-memories/src/routers/portfolio.py`
- **agentic-memories Portfolio Service:** `/home/ankit/dev/agentic-memories/src/services/portfolio_service.py`
- **Annie MCP Server:** `mcp_server/tools.py`
- **Annie Profile Pattern:** `backend/api/profile.py`
- **Yahoo Finance Library:** `yfinance` - https://github.com/ranaroussi/yfinance

---

_This epic provides Annie's complete financial advisory capabilities - from portfolio management through stock analysis to personalized recommendations._
