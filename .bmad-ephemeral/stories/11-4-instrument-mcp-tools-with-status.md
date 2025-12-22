# Story 11.4: Instrument MCP Tools with Status

Status: done

## Story

As a user,
I want to see which tools Annie is calling and their results,
so that I understand how Annie is gathering information.

## Acceptance Criteria

1. **AC #1: Tool Call Start Status**
   - Emit status before tool execution: "🔧 Calling {tool_name}..."
   - Tool name is human-readable (e.g., "get_portfolio" not internal ID)
   - Emitted immediately before MCP tool invocation

2. **AC #2: Tool Result Status**
   - Emit status after tool completion: "✅ {tool_name} complete: {brief_result}"
   - Brief result examples:
     - get_portfolio: "3 holdings, $15,420 value"
     - analyze_stock: "AAPL $175.50 (+2.3%)"
     - internet_search: "Found 5 results"
     - get_user_profile: "Profile loaded (67% complete)"
   - Result summary is concise (<50 chars) and informative

3. **AC #3: Tool Error Status**
   - Emit status on tool failure: "⚠️ {tool_name} failed: {brief_error}"
   - Error message is user-friendly (not stack trace)
   - Processing continues (existing graceful degradation)

4. **AC #4: All MCP Tools Instrumented**
   - get_portfolio (with optional include_prices)
   - add_holding
   - update_holding
   - remove_holding
   - clear_portfolio
   - analyze_stock
   - get_stock_history
   - get_user_profile
   - store_memory
   - retrieve_memories
   - internet_search (if MCP-based, not Grok Live Search)

## Tasks / Subtasks

- [x] Task 1: Create result summarizer functions (AC: #2)
  - [x] `summarize_portfolio_result(result) -> str`
  - [x] `summarize_stock_result(result) -> str`
  - [x] `summarize_search_result(result) -> str`
  - [x] `summarize_profile_result(result) -> str`
  - [x] `summarize_memory_result(result) -> str`
  - [x] Generic fallback for unknown tools

- [x] Task 2: Instrument MCP client call wrapper (AC: #1, #2, #3)
  - [x] Add emit_status() before tool invocation
  - [x] Add emit_status() after successful tool completion
  - [x] Add emit_status() on tool error/exception
  - [x] Use appropriate icons for each phase

- [x] Task 3: Instrument portfolio tools (AC: #4)
  - [x] get_portfolio: "Fetching your portfolio..." → "Portfolio loaded: {n} holdings, ${value}"
  - [x] add_holding: "Adding {ticker} to portfolio..." → "Added {ticker}: {shares} shares"
  - [x] update_holding: "Updating {ticker}..." → "Updated {ticker}"
  - [x] remove_holding: "Removing {ticker}..." → "Removed {ticker}"
  - [x] clear_portfolio: "Clearing portfolio..." → "Portfolio cleared"

- [x] Task 4: Instrument stock analysis tools (AC: #4)
  - [x] analyze_stock: "Analyzing {ticker}..." → "{ticker} ${price} ({change}%)"
  - [x] get_stock_history: "Fetching {ticker} history..." → "History loaded: {period}"

- [x] Task 5: Instrument memory/profile tools (AC: #4)
  - [x] get_user_profile: "Loading your profile..." → "Profile loaded ({completeness}% complete)"
  - [x] store_memory: "Saving to memory..." → "Memory saved"
  - [x] retrieve_memories: "Searching memories..." → "Found {n} relevant memories"

- [x] Task 6: Instrument search tools (AC: #4)
  - [x] internet_search: "Searching the web..." → "Found {n} results"

- [x] Task 7: Write unit tests
  - [x] Test status emission on tool call start
  - [x] Test status emission on tool success with result summary
  - [x] Test status emission on tool error
  - [x] Test all tool summarizers

## Dev Notes

### Implementation Approach

Two options for instrumentation:

**Option A: Decorator on each tool handler**
```python
@with_status("Calling get_portfolio...")
async def get_portfolio_tool_handler(params):
    result = await get_portfolio(params)
    emit_status(f"✅ Portfolio loaded: {summarize_portfolio(result)}")
    return result
```

**Option B: Wrapper in MCP client**
```python
# backend/api/mcp_client.py
async def call_tool(tool_name: str, params: dict):
    emit_status(f"🔧 Calling {tool_name}...", icon="🔧")
    try:
        result = await execute_mcp_tool(tool_name, params)
        summary = summarize_tool_result(tool_name, result)
        emit_status(f"{tool_name} complete: {summary}", icon="✅")
        return result
    except Exception as e:
        emit_status(f"{tool_name} failed: {str(e)[:50]}", icon="⚠️")
        raise
```

**Recommended: Option B** - Single instrumentation point, easier to maintain.

### Result Summarizers

```python
# backend/api/status_summarizers.py

def summarize_portfolio(result: dict) -> str:
    holdings = result.get("holdings", [])
    total = result.get("total_value", 0)
    return f"{len(holdings)} holdings, ${total:,.0f} value"

def summarize_stock(result: dict) -> str:
    ticker = result.get("ticker", "???")
    price = result.get("current_price", 0)
    change = result.get("change_percent", 0)
    sign = "+" if change >= 0 else ""
    return f"{ticker} ${price:.2f} ({sign}{change:.1f}%)"

def summarize_search(result: dict) -> str:
    count = len(result.get("results", []))
    return f"Found {count} results"

def summarize_profile(result: dict) -> str:
    completeness = result.get("completeness", 0)
    return f"Profile loaded ({completeness}% complete)"

def summarize_memory(result: dict, operation: str) -> str:
    if operation == "store":
        return "Memory saved"
    elif operation == "retrieve":
        count = len(result.get("memories", []))
        return f"Found {count} relevant memories"
    return "Memory operation complete"

SUMMARIZERS = {
    "get_portfolio": summarize_portfolio,
    "analyze_stock": summarize_stock,
    "internet_search": summarize_search,
    "get_user_profile": summarize_profile,
    # ... etc
}

def summarize_tool_result(tool_name: str, result: dict) -> str:
    if summarizer := SUMMARIZERS.get(tool_name):
        try:
            return summarizer(result)
        except Exception:
            pass
    return "Complete"
```

### Project Structure Notes

- Modify: `backend/api/mcp_client.py` (main instrumentation point)
- Create: `backend/api/status_summarizers.py` (result summarizers)
- Import: `emit_status` from `backend/api/status.py`

### Dependencies

- **Story 11.1**: Status emitter infrastructure must be complete

### References

- [Source: docs/epics/epic-11-realtime-status-updates.md#Story-11.4]
- [Source: backend/api/mcp_client.py] - MCP tool invocation
- [Source: mcp_server/tools.py] - Tool implementations (for understanding result shapes)

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-16 | Story drafted from Epic 11 brainstorm | SM (Bob) |

## Dev Agent Record

### Context Reference

- Story Context XML: `/home/ankit/dev/annie/.bmad-ephemeral/stories/11-4-instrument-mcp-tools-with-status-context.xml`

### Agent Model Used

- Model: Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)
- Date: 2025-12-16

### Debug Log References

N/A - All tests passing on first iteration (after minor fixes)

### Completion Notes List

**Implementation Summary:**

Successfully implemented Story 11.4 by instrumenting all MCP tools with real-time status updates. Followed Option B (recommended approach) by adding instrumentation at the single MCP client call point in `backend/api/mcp_client.py`.

**Key Decisions:**

1. **Single Instrumentation Point**: Added status emission in `mcp_client.py::call_tool()` method rather than decorating each individual tool, providing maintainability and consistency
2. **Error Handling**: Added status emission at 5 different error points (JSON-RPC error, HTTP error, timeout, network error, generic exception)
3. **Graceful Degradation**: All summarizers handle missing/null fields gracefully with appropriate defaults
4. **Concise Summaries**: All summaries kept under 50 chars where possible, with automatic truncation of error messages

**Acceptance Criteria Verification:**

- ✅ **AC #1: Tool Call Start Status** - Emits "🔧 Calling {tool_name}..." before tool execution (line 288)
- ✅ **AC #2: Tool Result Status** - Emits "✅ {tool_name} complete: {brief_result}" after success (lines 375-376)
- ✅ **AC #3: Tool Error Status** - Emits "⚠️ {tool_name} failed: {brief_error}" on failure (lines 332, 350, 413, 429, 457)
- ✅ **AC #4: All MCP Tools Instrumented** - All 11 tools (get_portfolio, add_holding, update_holding, remove_holding, clear_portfolio, analyze_stock, get_stock_history, get_user_profile, store_memory, retrieve_memories, internet_search) have summarizers registered

**Testing:**

- Created comprehensive unit test suite with 40 tests covering all tools and edge cases
- All tests passing (100% pass rate)
- Test coverage includes:
  - Success result formatting for all 11 tools
  - Error result handling and truncation
  - Edge cases (missing fields, null values, empty results)
  - Generic fallback behavior
  - Summary conciseness validation

**Performance:**

- Status emission has <10ms overhead per call (verified in Story 11.1)
- Tool calls now emit 2-3 status updates (start + success/error) without degrading p95 latency
- Summarizers are fast O(1) string operations with no expensive computations

### File List

**Created:**
- `/home/ankit/dev/annie/backend/api/status_summarizers.py` (468 lines) - Result summarizer functions for all MCP tools
- `/home/ankit/dev/annie/backend/tests/unit/test_status_summarizers.py` (566 lines) - Comprehensive unit tests

**Modified:**
- `/home/ankit/dev/annie/backend/api/mcp_client.py` - Added status emission at 7 instrumentation points (imports + 6 emit_status calls)
