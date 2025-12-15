# Story 10.1: Portfolio Access MCP Tools

Status: done

## Story

As a **user**,
I want **Annie to see my investment portfolio**,
so that **she can give me personalized financial advice based on what I own**.

## Acceptance Criteria

**AC #1:** Given `get_portfolio` MCP tool, when called with user_id, then tool makes HTTP GET to `{AGENTIC_MEMORIES_URL}/v1/portfolio?user_id={user_id}` and returns structured portfolio data with holdings array, total_holdings count, and last_updated timestamp

**AC #2:** Given `add_holding` MCP tool, when called with holding data (user_id, ticker, shares, avg_price), then tool makes HTTP POST to `{AGENTIC_MEMORIES_URL}/v1/portfolio/holding` with proper payload and returns created/updated holding with `created: true/false` flag

**AC #3:** Given portfolio tools registered, when user asks "what stocks do I own?", then LLM calls `get_portfolio` tool via function calling and Annie responds with formatted portfolio summary

**AC #4:** Given agentic-memories unavailable, when portfolio tool called, then tool returns graceful error message and Annie informs user without crashing

**AC #5:** Given user provides lowercase ticker (e.g., "aapl"), when adding holding, then ticker is normalized to uppercase ("AAPL") and invalid tickers (>10 chars, special chars) are rejected with clear error

## Tasks / Subtasks

- [x] **Task 1: Create get_portfolio tool handler** (AC: #1, #4)
  - [x] Create async `get_portfolio_tool_handler(user_id: str)` function
  - [x] Make HTTP GET to `{AGENTIC_MEMORIES_URL}/v1/portfolio?user_id={user_id}`
  - [x] Parse response and return structured data
  - [x] Handle empty portfolio (return empty holdings array)
  - [x] Add timeout handling (5s timeout)
  - [x] Add network error handling with graceful degradation
  - [x] Add structured logging with duration_ms

- [x] **Task 2: Create get_portfolio tool definition** (AC: #1, #3)
  - [x] Define tool schema with proper inputSchema
  - [x] Write clear description for LLM to know when to use this tool

- [x] **Task 3: Create add_holding tool handler** (AC: #2, #4, #5)
  - [x] Create async `add_holding_tool_handler(user_id, ticker, asset_name=None, shares=None, avg_price=None)` function
  - [x] Normalize ticker to uppercase using regex pattern `^[A-Z0-9\.]{1,10}$`
  - [x] Validate ticker format (reject invalid)
  - [x] Make HTTP POST to `{AGENTIC_MEMORIES_URL}/v1/portfolio/holding`
  - [x] Handle 201 (created) vs 200 (updated) status codes
  - [x] Return result with `created: true/false` flag
  - [x] Add error handling and logging

- [x] **Task 4: Create add_holding tool definition** (AC: #2, #3)
  - [x] Define tool schema with proper inputSchema

- [x] **Task 5: Register tools in MCP server** (AC: #1, #2, #3)
  - [x] Add tool definitions to `mcp_server/tools.py`
  - [x] Register tools in the tool registry (server.py)
  - [x] Export tools for server.py to use

- [x] **Task 6: Testing** (AC: #1, #2, #3, #4, #5)
  - [x] Test get_portfolio with existing user (has holdings) ✓
  - [x] Test get_portfolio with new user (empty holdings) ✓
  - [x] Test add_holding creates new holding (201 response) ✓
  - [x] Test add_holding updates existing holding (200 response) ✓
  - [x] Test ticker normalization (lowercase → uppercase) ✓
  - [x] Test invalid ticker rejection ✓
  - [ ] Test graceful degradation when agentic-memories down (manual)
  - [ ] Test via Telegram: "What stocks do I own?" (manual)
  - [ ] Test via Telegram: "Add 10 shares of AAPL at $175" (manual)

## Dev Notes

### Architecture Pattern

Follow existing MCP tool pattern from `store_memory_tool` and `get_user_profile_tool`:
1. Async handler function with httpx client
2. Tool definition dict with name, description, inputSchema, handler
3. Structured logging with extra context
4. Graceful error handling (never crash)

### API Endpoints (agentic-memories)

**GET /v1/portfolio**
- Query param: `user_id` (required)
- Response:
```json
{
  "user_id": "123",
  "holdings": [
    {
      "ticker": "AAPL",
      "asset_name": "Apple Inc.",
      "shares": 10.0,
      "avg_price": 150.00,
      "first_acquired": "2025-01-15T10:00:00Z",
      "last_updated": "2025-12-14T10:00:00Z"
    }
  ],
  "total_holdings": 1,
  "last_updated": "2025-12-14T10:00:00Z"
}
```

**POST /v1/portfolio/holding**
- Body:
```json
{
  "user_id": "123",
  "ticker": "AAPL",
  "asset_name": "Apple Inc.",
  "shares": 10,
  "avg_price": 150.00
}
```
- Response (201 Created or 200 Updated):
```json
{
  "id": "uuid",
  "ticker": "AAPL",
  "asset_name": "Apple Inc.",
  "shares": 10.0,
  "avg_price": 150.00,
  "first_acquired": "2025-12-14T10:00:00Z",
  "last_updated": "2025-12-14T10:00:00Z",
  "created": true
}
```

### Ticker Validation

From agentic-memories `portfolio_service.py`:
```python
import re
TICKER_PATTERN = re.compile(r'^[A-Z0-9\.]{1,10}$')

def normalize_ticker(ticker: str) -> Optional[str]:
    if not ticker:
        return None
    normalized = ticker.upper().strip()
    if not normalized or not TICKER_PATTERN.match(normalized):
        return None
    return normalized
```

### Error Handling

Always return graceful error response, never raise exceptions:
```python
{
    "status": "error",
    "message": "Portfolio service unavailable. Please try again later.",
    "error_code": "NETWORK_ERROR"
}
```

### Files to Modify

- `mcp_server/tools.py` - Add new tool handlers and definitions

### Testing Commands

```bash
# Start services
make start

# Test via curl (MCP tools are called via LLM, but can test agentic-memories directly)
curl "http://localhost:8080/v1/portfolio?user_id=test_user"

# Test via Telegram bot
# Send: "What stocks do I own?"
# Send: "Add 10 shares of AAPL at $175 to my portfolio"
```

## References

- Epic 10: `docs/epics/epic-10-portfolio-management.md`
- Existing MCP tools: `mcp_server/tools.py`
- agentic-memories portfolio API: `/home/ankit/dev/agentic-memories/src/routers/portfolio.py`
