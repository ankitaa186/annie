# Story 10.4: Portfolio Update & Remove Tools

Status: done

## Story

As a **user**,
I want **to update or remove holdings from my portfolio**,
So that **my portfolio stays accurate as I buy/sell stocks**.

## Acceptance Criteria

**AC #1:** Given `update_holding` MCP tool, when called with ticker and updates, then tool makes HTTP PUT to `/v1/portfolio/holding/{ticker}` and updates specific fields (shares, avg_price, asset_name) while preserving fields not included in update

**AC #2:** Given `remove_holding` MCP tool, when called with user_id and ticker, then tool makes HTTP DELETE to `/v1/portfolio/holding/{ticker}?user_id=xxx` and removes the holding, returning confirmation

**AC #3:** Given `clear_portfolio` MCP tool, when called with user_id, then tool makes HTTP DELETE to `/v1/portfolio?user_id=xxx&confirmation=DELETE_ALL` and removes ALL holdings, returning count of removed holdings

**AC #4:** Given user says "I sold my Apple stock", then Annie asks "How many shares did you sell?" and updates or removes holding accordingly, confirming "I've updated your portfolio. You now have X shares of AAPL remaining."

**AC #5:** Given invalid ticker or non-existent holding, then tool returns 404 error with clear message

**AC #6:** Given clear_portfolio without user confirmation in conversation, then Annie asks for confirmation before proceeding with the dangerous operation

## Tasks / Subtasks

- [x] **Task 1: Implement update_holding MCP tool** (AC: #1, #4, #5)
  - [x] Create `update_holding_tool_handler()` in `mcp_server/tools.py`
  - [x] Make HTTP PUT to `/v1/portfolio/holding/{ticker}`
  - [x] Support partial updates (only update provided fields)
  - [x] Handle 404 for non-existent holdings
  - [x] Add Langfuse tracing

- [x] **Task 2: Implement remove_holding MCP tool** (AC: #2, #4, #5)
  - [x] Create `remove_holding_tool_handler()` in `mcp_server/tools.py`
  - [x] Make HTTP DELETE to `/v1/portfolio/holding/{ticker}?user_id=xxx`
  - [x] Handle 404 for non-existent holdings
  - [x] Return confirmation with deleted ticker

- [x] **Task 3: Implement clear_portfolio MCP tool** (AC: #3, #6)
  - [x] Create `clear_portfolio_tool_handler()` in `mcp_server/tools.py`
  - [x] Make HTTP DELETE to `/v1/portfolio?user_id=xxx&confirmation=DELETE_ALL`
  - [x] Return count of deleted holdings
  - [x] Tool description emphasizes this is destructive

- [x] **Task 4: Register tools in MCP server** (AC: #1, #2, #3)
  - [x] Import tools in `mcp_server/server.py`
  - [x] Register all three tools

- [x] **Task 5: Testing** (AC: #1, #2, #3, #4, #5, #6)
  - [x] Test update_holding via MCP endpoint
  - [x] Test remove_holding via MCP endpoint
  - [x] Test clear_portfolio via MCP endpoint
  - [ ] Test via Telegram: "Update my AAPL shares to 15"
  - [ ] Test via Telegram: "Remove GOOGL from my portfolio"

## Dev Notes

### API Endpoints (agentic-memories)

| Tool | Method | Endpoint | Body/Params |
|------|--------|----------|-------------|
| update_holding | PUT | `/v1/portfolio/holding/{ticker}` | `{"user_id": "xxx", "shares": 15, "avg_price": 150.00}` |
| remove_holding | DELETE | `/v1/portfolio/holding/{ticker}` | Query: `?user_id=xxx` |
| clear_portfolio | DELETE | `/v1/portfolio` | Query: `?user_id=xxx&confirmation=DELETE_ALL` |

### Key Behaviors

1. **update_holding**:
   - Returns 404 if holding doesn't exist (unlike POST which creates)
   - Supports partial updates - only provided fields are updated
   - Ticker in URL path, user_id in body

2. **remove_holding**:
   - Returns 404 if holding doesn't exist
   - Returns `{"deleted": true, "ticker": "AAPL"}`

3. **clear_portfolio**:
   - Requires `confirmation=DELETE_ALL` parameter for safety
   - Returns `{"deleted": true, "holdings_removed": 5}`
   - Can return 0 holdings_removed if portfolio was already empty

### Files to Modify

- **Modify:** `mcp_server/tools.py` - Add three new tool handlers
- **Modify:** `mcp_server/server.py` - Register new tools

### Example Tool Responses

```json
// update_holding success
{
  "status": "success",
  "ticker": "AAPL",
  "asset_name": "Apple Inc.",
  "shares": 15,
  "avg_price": 175.50,
  "message": "Updated AAPL in your portfolio."
}

// remove_holding success
{
  "status": "success",
  "deleted": true,
  "ticker": "AAPL",
  "message": "Removed AAPL from your portfolio."
}

// clear_portfolio success
{
  "status": "success",
  "deleted": true,
  "holdings_removed": 5,
  "message": "Cleared your entire portfolio. 5 holdings removed."
}
```

## References

- Epic 10: `docs/epics/epic-10-portfolio-management.md`
- agentic-memories portfolio router: `/home/ankit/dev/agentic-memories/src/routers/portfolio.py`
- Existing portfolio tools: `mcp_server/tools.py` (get_portfolio, add_holding)
- Previous story: Story 10.1 (Portfolio Access MCP Tools)
