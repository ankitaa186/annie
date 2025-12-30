# Story 15.1: Web Search Tool (Tavily + DuckDuckGo)

**Status:** done

## Story

**As a** user of Annie,
**I want** Annie to search the web for current information,
**So that** she can provide accurate, up-to-date answers about news, products, services, and real-time data.

**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Priority:** P0
**Prerequisites:** Tavily API key obtained (sign up at https://tavily.com)
**Estimated Effort:** 1 day

---

## Acceptance Criteria

### AC #1: Tavily API Integration (15.1.1)
**Given** the web_search tool is called
**When** TAVILY_API_KEY is configured in environment
**Then** the tool makes a POST request to `https://api.tavily.com/search` with the query and parameters
**And** API key is passed in request body (not headers per Tavily docs)

**Mapped to Tasks:** Task 1
**Testable:** Yes - Mock Tavily API, verify request format

---

### AC #2: DuckDuckGo Fallback (15.1.2)
**Given** the web_search tool is called
**When** Tavily fails (error, rate limit 429, timeout >10s, network error)
**Then** the tool automatically falls back to DuckDuckGo search
**And** returns results from DDG with `provider: "duckduckgo"` in response

**Mapped to Tasks:** Task 2
**Testable:** Yes - Force Tavily error, verify DDG called

---

### AC #3: Search Depth Options (15.1.3)
**Given** the web_search tool is called with `search_depth` parameter
**When** search_depth is "basic" (default, faster/cheaper) or "advanced" (deeper, more expensive)
**Then** the depth is passed to Tavily API correctly in request body

**Mapped to Tasks:** Task 1
**Testable:** Yes - Test basic vs advanced parameter passed correctly

---

### AC #4: Domain Filtering (15.1.4)
**Given** the web_search tool is called with `include_domains` or `exclude_domains`
**When** domains are specified as arrays
**Then** results are filtered to include only / exclude the specified domains

**Mapped to Tasks:** Task 1
**Testable:** Yes - Verify domain filters applied in request

---

### AC #5: Results Limiting (15.1.5)
**Given** the web_search tool is called with `max_results` parameter
**When** max_results is between 1-10 (default 5)
**Then** no more than `max_results` results are returned
**And** values above 10 are capped to 10

**Mapped to Tasks:** Task 1, Task 2
**Testable:** Yes - Test default (5) and custom values

---

### AC #6: Error Handling (15.1.6)
**Given** the web_search tool encounters an error
**When** rate limit (429), timeout (10s), or network error occurs
**Then** appropriate error handling with retry/fallback is applied:
  - 429: Immediate fallback to DuckDuckGo
  - 5xx: Retry once with backoff, then fallback
  - Timeout (>10s): Cancel and fallback
  - Network error: Immediate fallback

**Mapped to Tasks:** Task 1, Task 2
**Testable:** Yes - Inject 429, timeout, network errors

---

### AC #7: Unit Tests (15.1.7)
**Given** the web_search tool implementation
**When** tests are run with `pytest mcp_server/tests/test_web_search_tool.py`
**Then** mocked Tavily/DDG responses achieve >80% code coverage
**And** all edge cases (fallback, errors, parameter validation) are covered

**Mapped to Tasks:** Task 3
**Testable:** Yes - Run coverage report

---

### AC #8: Status Summarizer (15.1.8)
**Given** the web_search tool is executing
**When** the tool starts execution
**Then** status update "Searching the web..." is emitted via SSE
**When** the tool completes
**Then** status update "Found N results" (or "No results found") is emitted

**Mapped to Tasks:** Task 4
**Testable:** Yes - Verify SSE status events

---

## Tasks / Subtasks

### Task 1: Implement Tavily Search Provider
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #3, AC #4, AC #5, AC #6

**Implementation Details:**

Create `web_search_tool_handler` in `mcp_server/tools.py`:

```python
import time
from typing import Dict, Any, List, Optional
import httpx

async def web_search_tool_handler(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Execute web search using Tavily with DuckDuckGo fallback.

    Args:
        query: Search query string
        max_results: Maximum results to return (1-10, default 5)
        search_depth: "basic" (faster/cheaper) or "advanced" (deeper)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains

    Returns:
        dict with status, provider, query, and results array
    """
    start_time = time.time()

    # Validate and cap max_results
    max_results = max(1, min(max_results, 10))

    # Validate search_depth
    if search_depth not in ("basic", "advanced"):
        search_depth = "basic"

    try:
        config = get_config()
        tavily_api_key = config.get("TAVILY_API_KEY")

        if tavily_api_key:
            result = await _tavily_search(
                query=query,
                max_results=max_results,
                search_depth=search_depth,
                include_domains=include_domains or [],
                exclude_domains=exclude_domains or [],
                api_key=tavily_api_key
            )
            if result["status"] == "success":
                logger.info(
                    "web_search.completed",
                    extra={
                        "query": query,
                        "provider": "tavily",
                        "results_count": len(result.get("results", [])),
                        "duration_ms": int((time.time() - start_time) * 1000)
                    }
                )
                return result
            # Tavily failed, fall through to DuckDuckGo
            logger.warning(
                "web_search.fallback",
                extra={
                    "primary": "tavily",
                    "fallback": "duckduckgo",
                    "reason": result.get("error_message", "unknown")
                }
            )
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}, falling back to DDG")

    # Fallback to DuckDuckGo
    return await _duckduckgo_search(query, max_results)
```

**Tavily API Implementation:**

```python
async def _tavily_search(
    query: str,
    max_results: int,
    search_depth: str,
    include_domains: List[str],
    exclude_domains: List[str],
    api_key: str
) -> Dict[str, Any]:
    """Execute Tavily search API call."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,  # Tavily uses body, not header
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": max_results,
                    "include_domains": include_domains,
                    "exclude_domains": exclude_domains
                }
            )

            if response.status_code == 429:
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": "Rate limit exceeded",
                    "error_code": "RATE_LIMIT"
                }

            if response.status_code >= 500:
                return {
                    "status": "error",
                    "provider": "tavily",
                    "error_message": f"Server error: {response.status_code}",
                    "error_code": "SERVER_ERROR"
                }

            response.raise_for_status()
            data = response.json()

            return {
                "status": "success",
                "provider": "tavily",
                "query": query,
                "results": [
                    {
                        "title": r.get("title", ""),
                        "url": r.get("url", ""),
                        "snippet": r.get("content", ""),
                        "score": r.get("score", None)  # Relevance score if available
                    }
                    for r in data.get("results", [])[:max_results]
                ]
            }
    except httpx.TimeoutException:
        return {
            "status": "error",
            "provider": "tavily",
            "error_message": "Request timed out",
            "error_code": "TIMEOUT"
        }
    except Exception as e:
        return {
            "status": "error",
            "provider": "tavily",
            "error_message": str(e),
            "error_code": "UNKNOWN"
        }
```

**Subtasks:**
- [ ] Add TAVILY_API_KEY to `mcp_server/config.py` SENSITIVE_VARS list
- [ ] Add TAVILY_API_KEY loading in `validate_environment()` (optional with warning)
- [ ] Implement `_tavily_search()` async function
- [ ] Handle search_depth parameter (basic/advanced)
- [ ] Implement domain filtering (include_domains, exclude_domains)
- [ ] Cap max_results to range 1-10
- [ ] Add 10s timeout for Tavily requests
- [ ] Handle 429 rate limit (immediate fallback)
- [ ] Handle 5xx server errors (retry once, then fallback)
- [ ] Log search metrics with Langfuse tracing

---

### Task 2: Implement DuckDuckGo Fallback
**Status:** TODO
**Acceptance Criteria:** AC #2, AC #5, AC #6

**Implementation Details:**

```python
from duckduckgo_search import DDGS

async def _duckduckgo_search(query: str, max_results: int) -> Dict[str, Any]:
    """
    Search using DuckDuckGo as fallback.

    Note: duckduckgo-search is synchronous, run in executor.
    """
    try:
        import asyncio

        def _sync_search():
            ddgs = DDGS()
            return list(ddgs.text(query, max_results=max_results))

        # Run sync library in executor to not block event loop
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _sync_search)

        return {
            "status": "success",
            "provider": "duckduckgo",
            "query": query,
            "results": [
                {
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                    "score": None  # DDG doesn't provide relevance scores
                }
                for r in results
            ]
        }
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return {
            "status": "error",
            "provider": "duckduckgo",
            "query": query,
            "results": [],
            "error_message": str(e)
        }
```

**Subtasks:**
- [ ] Add `duckduckgo-search>=6.0.0` to `mcp_server/requirements.txt`
- [ ] Implement `_duckduckgo_search()` async function
- [ ] Run sync DDG library in executor (non-blocking)
- [ ] Map DDG response fields to standard format (title, url, snippet)
- [ ] Handle DDG rate limiting (~1 req/sec recommended)
- [ ] Comprehensive error handling for DDG failures
- [ ] Test fallback triggers correctly from Tavily failures

---

### Task 3: Unit Tests
**Status:** TODO
**Acceptance Criteria:** AC #7

**Implementation Details:**

Create `mcp_server/tests/test_web_search_tool.py`:

```python
"""
Unit tests for web_search MCP tool

Story 15.1: Web Search Tool (Tavily + DuckDuckGo)
- Tests Tavily API integration
- Tests DuckDuckGo fallback mechanism
- Tests parameter handling (search_depth, domains, max_results)
- Tests error scenarios (rate limit, timeout, network error)
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
import httpx

from mcp_server.tools import web_search_tool_handler, web_search_tool


class TestWebSearchToolHandler:
    """Test web_search_tool_handler function."""

    @pytest.fixture
    def mock_tavily_response(self):
        """Standard Tavily success response."""
        return {
            "results": [
                {
                    "title": "Test Result 1",
                    "url": "https://example.com/1",
                    "content": "First test result content",
                    "score": 0.95
                },
                {
                    "title": "Test Result 2",
                    "url": "https://example.com/2",
                    "content": "Second test result content",
                    "score": 0.87
                }
            ]
        }

    @pytest.mark.asyncio
    async def test_tavily_search_success(self, mock_tavily_response):
        """Test successful Tavily search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                result = await web_search_tool_handler(query="test query")

                assert result["status"] == "success"
                assert result["provider"] == "tavily"
                assert len(result["results"]) == 2
                assert result["results"][0]["title"] == "Test Result 1"

    @pytest.mark.asyncio
    async def test_fallback_to_duckduckgo_on_tavily_failure(self):
        """Test DuckDuckGo fallback when Tavily fails."""
        # Mock Tavily to raise an exception
        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=Exception("Tavily unavailable"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('mcp_server.tools.DDGS') as mock_ddgs_class:
                    mock_ddgs = Mock()
                    mock_ddgs.text.return_value = [
                        {"title": "DDG Result", "href": "https://ddg.com", "body": "DDG content"}
                    ]
                    mock_ddgs_class.return_value = mock_ddgs

                    result = await web_search_tool_handler(query="test query")

                    assert result["status"] == "success"
                    assert result["provider"] == "duckduckgo"

    @pytest.mark.asyncio
    async def test_rate_limit_triggers_fallback(self):
        """Test 429 rate limit triggers DuckDuckGo fallback."""
        mock_response = Mock()
        mock_response.status_code = 429

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('mcp_server.tools._duckduckgo_search') as mock_ddg:
                    mock_ddg.return_value = {
                        "status": "success",
                        "provider": "duckduckgo",
                        "results": []
                    }

                    result = await web_search_tool_handler(query="test")

                    mock_ddg.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_triggers_fallback(self):
        """Test timeout triggers DuckDuckGo fallback."""
        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("Timeout"))
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                with patch('mcp_server.tools._duckduckgo_search') as mock_ddg:
                    mock_ddg.return_value = {
                        "status": "success",
                        "provider": "duckduckgo",
                        "results": []
                    }

                    result = await web_search_tool_handler(query="test")

                    mock_ddg.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_depth_parameter(self, mock_tavily_response):
        """Test search_depth parameter passed correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    search_depth="advanced"
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["search_depth"] == "advanced"

    @pytest.mark.asyncio
    async def test_domain_filtering(self, mock_tavily_response):
        """Test domain filtering parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    include_domains=["example.com"],
                    exclude_domains=["spam.com"]
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["include_domains"] == ["example.com"]
                assert payload["exclude_domains"] == ["spam.com"]

    @pytest.mark.asyncio
    async def test_max_results_limiting(self, mock_tavily_response):
        """Test max_results is capped at 10."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_tavily_response
        mock_response.raise_for_status = Mock()

        with patch('mcp_server.tools.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            with patch('mcp_server.tools.get_config') as mock_config:
                mock_config.return_value = {"TAVILY_API_KEY": "test-key"}

                await web_search_tool_handler(
                    query="test",
                    max_results=50  # Over limit
                )

                call_args = mock_client.post.call_args
                payload = call_args[1]["json"]
                assert payload["max_results"] == 10  # Capped

    @pytest.mark.asyncio
    async def test_no_api_key_uses_duckduckgo(self):
        """Test missing API key goes directly to DuckDuckGo."""
        with patch('mcp_server.tools.get_config') as mock_config:
            mock_config.return_value = {}  # No API key

            with patch('mcp_server.tools._duckduckgo_search') as mock_ddg:
                mock_ddg.return_value = {
                    "status": "success",
                    "provider": "duckduckgo",
                    "results": []
                }

                result = await web_search_tool_handler(query="test")

                assert result["provider"] == "duckduckgo"


class TestWebSearchToolSchema:
    """Test web_search tool schema definition."""

    def test_tool_schema_structure(self):
        """Verify tool schema has required fields."""
        assert web_search_tool["name"] == "web_search"
        assert "description" in web_search_tool
        assert "inputSchema" in web_search_tool
        assert "handler" in web_search_tool

    def test_input_schema_properties(self):
        """Verify input schema has all expected properties."""
        schema = web_search_tool["inputSchema"]
        props = schema["properties"]

        assert "query" in props
        assert "max_results" in props
        assert "search_depth" in props
        assert "include_domains" in props
        assert "exclude_domains" in props

    def test_required_fields(self):
        """Verify only query is required."""
        schema = web_search_tool["inputSchema"]
        assert schema["required"] == ["query"]
```

**Subtasks:**
- [ ] Create `mcp_server/tests/test_web_search_tool.py`
- [ ] Test Tavily success path with mocked response
- [ ] Test Tavily failure triggers DDG fallback
- [ ] Test 429 rate limit handling
- [ ] Test timeout handling (10s)
- [ ] Test network error handling
- [ ] Test search_depth parameter (basic/advanced)
- [ ] Test domain filtering (include/exclude)
- [ ] Test max_results limiting (1-10, cap at 10)
- [ ] Test no API key goes to DDG
- [ ] Test tool schema structure
- [ ] Achieve >80% code coverage
- [ ] Run: `pytest mcp_server/tests/test_web_search_tool.py -v --cov=mcp_server.tools`

---

### Task 4: Status Summarizer
**Status:** TODO
**Acceptance Criteria:** AC #8

**Implementation Details:**

Add to `backend/api/status_summarizers.py`:

```python
def summarize_web_search_result(result: Dict[str, Any]) -> str:
    """
    Summarize web_search tool result.

    Result shape:
        {
            "status": "success" | "error",
            "provider": "tavily" | "duckduckgo",
            "results": [...],
            "query": "..."
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Found 5 results"
        "No results found"
        "Search failed: rate limit"
    """
    if result.get("status") == "error":
        error_msg = result.get("error_message", "Failed")
        return f"Search failed: {error_msg}"[:50]

    results = result.get("results", [])
    count = len(results)

    if count == 0:
        return "No results found"
    elif count == 1:
        return "Found 1 result"
    else:
        return f"Found {count} results"


# Add to SUMMARIZERS registry
SUMMARIZERS["web_search"] = summarize_web_search_result
```

**Subtasks:**
- [ ] Implement `summarize_web_search_result()` function
- [ ] Register in SUMMARIZERS dict as `"web_search"`
- [ ] Return "Found N results" on success
- [ ] Return "No results found" when empty
- [ ] Return "Search failed: {reason}" on error
- [ ] Keep summary under 50 characters

---

### Task 5: Tool Registration
**Status:** TODO
**Acceptance Criteria:** (Part of Story 15.5, but needed here for completeness)

**Implementation Details:**

Add tool definition in `mcp_server/tools.py`:

```python
# Web search tool definition
web_search_tool = {
    "name": "web_search",
    "description": "Search the web for current information using Tavily (primary) with DuckDuckGo fallback. Returns relevant results with titles, URLs, and snippets. Use for finding up-to-date information about news, products, services, facts, or any topic requiring current web data.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query - be specific for better results"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 5, max: 10)",
                "default": 5,
                "minimum": 1,
                "maximum": 10
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "description": "Search depth: 'basic' (faster, cheaper) or 'advanced' (deeper, more thorough)",
                "default": "basic"
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results from these domains (e.g., ['reddit.com', 'stackoverflow.com'])"
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results from these domains (e.g., ['pinterest.com'])"
            }
        },
        "required": ["query"]
    },
    "handler": web_search_tool_handler
}
```

Register in tool registry (in `mcp_server/server.py` or wherever tools are registered):

```python
registry.register(web_search_tool)
```

**Subtasks:**
- [ ] Define `web_search_tool` dict with schema
- [ ] Write clear description for LLM understanding
- [ ] Define all input properties with descriptions
- [ ] Register tool in MCP server registry
- [ ] Verify tool appears in `tools/list` response

---

## Definition of Done

### Implementation
- [ ] `web_search_tool_handler` implemented in `mcp_server/tools.py`
- [ ] `_tavily_search` helper function implemented
- [ ] `_duckduckgo_search` helper function implemented
- [ ] Tool schema defined with all parameters
- [ ] Tool registered in MCP server

### Configuration
- [ ] `TAVILY_API_KEY` added to `mcp_server/config.py`
- [ ] `tavily-python>=0.3.0` added to `mcp_server/requirements.txt`
- [ ] `duckduckgo-search>=6.0.0` added to `mcp_server/requirements.txt`
- [ ] Environment variable documented in `env.example`

### Testing
- [ ] Unit tests in `mcp_server/tests/test_web_search_tool.py`
- [ ] >80% code coverage achieved
- [ ] All 8 acceptance criteria validated
- [ ] Tests pass: `pytest mcp_server/tests/test_web_search_tool.py -v`

### Integration
- [ ] Status summarizer added to `backend/api/status_summarizers.py`
- [ ] Langfuse tracing annotations added (@observe)
- [ ] Tool appears in `tools/list` MCP response
- [ ] E2E test via chat endpoint (manual or automated)

### Quality
- [ ] No regressions in other MCP tools
- [ ] Error handling covers all edge cases
- [ ] Logging includes duration_ms and provider metrics
- [ ] Code follows existing patterns in `tools.py`

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **web_search tool** (`mcp_server/tools.py`): MCP tool for web search
- **Tavily API**: Primary search provider (~$0.001/search, 1000/month free)
- **DuckDuckGo**: Free fallback provider (no auth required)
- **Status Summarizer** (`backend/api/status_summarizers.py`): Real-time updates

**Flow:**
```
LLM decides to search
    ↓
web_search tool called via MCP
    ↓
Try Tavily API (if TAVILY_API_KEY configured)
    ↓
[On success] Return results with provider="tavily"
    ↓
[On failure] Fallback to DuckDuckGo
    ↓
Return results with provider="duckduckgo"
```

### Technical Constraints

1. **Tavily Rate Limits:**
   - Free tier: 1000 requests/month
   - Paid tier: Higher limits available
   - Rate limit (429): Immediate fallback to DDG
   - Cost: ~$0.001 per search (very cheap)

2. **DuckDuckGo Limits:**
   - Unofficial API via `duckduckgo-search` library
   - ~1 request/second recommended
   - No authentication required
   - May be less reliable than Tavily

3. **Timeout:**
   - 10 seconds per request to Tavily
   - Total tool timeout: 30 seconds (MCP_TOOL_TIMEOUT)
   - DuckDuckGo is typically faster

4. **Performance Target:**
   - Latency P95: <3 seconds
   - Success rate: >98%

### Dependencies

**Blocking:**
- `tavily-python>=0.3.0` package
- `duckduckgo-search>=6.0.0` package
- `TAVILY_API_KEY` environment variable (for Tavily, DDG works without)

**Non-Blocking:**
- Status summarizer (can be added after core implementation)

### Key Files to Modify

**Files to Create:**
- `mcp_server/tests/test_web_search_tool.py` - Unit tests

**Files to Modify:**
- `mcp_server/tools.py` - Add `web_search_tool_handler`, `_tavily_search`, `_duckduckgo_search`, `web_search_tool`
- `mcp_server/requirements.txt` - Add tavily-python, duckduckgo-search
- `mcp_server/config.py` - Add TAVILY_API_KEY to config loading
- `mcp_server/server.py` - Register web_search_tool (if not auto-registered)
- `backend/api/status_summarizers.py` - Add `summarize_web_search_result`
- `env.example` - Document TAVILY_API_KEY

**Reference Files:**
- `.bmad-ephemeral/stories/tech-spec-epic-15.md` - Technical specification
- `docs/epics/epic-15-extended-mcp-tools.md` - Epic overview
- `mcp_server/tests/test_store_memory_tool.py` - Test patterns to follow

### Testing Strategy

**Unit Tests:**
- Mock Tavily API responses (httpx.AsyncClient)
- Mock DuckDuckGo responses (DDGS class)
- Test fallback trigger conditions (429, timeout, exception)
- Test all parameter combinations
- Test edge cases (empty results, malformed responses)

**Integration Tests (Story 15.5):**
- Live Tavily call with real API key (skippable via `--skip-live`)
- E2E via chat endpoint triggering web_search

**Coverage Requirements:**
- Line coverage: >80%
- Error handling paths: 100%
- Fallback logic: 100%

### Success Metrics

| Metric | Target |
|--------|--------|
| Latency P95 | <3s |
| Success rate | >98% |
| Cost per search | ~$0.001 (Tavily) |
| Test coverage | >80% |

---

## Traceability Matrix

| AC# | Tech Spec | Component | Test |
|-----|-----------|-----------|------|
| 15.1.1 | APIs and Interfaces | `_tavily_search` | `test_tavily_search_success` |
| 15.1.2 | Workflows/Sequencing | `_duckduckgo_search` | `test_fallback_to_duckduckgo_on_tavily_failure` |
| 15.1.3 | Data Models | `search_depth` param | `test_search_depth_parameter` |
| 15.1.4 | Data Models | `include/exclude_domains` | `test_domain_filtering` |
| 15.1.5 | Data Models | `max_results` param | `test_max_results_limiting` |
| 15.1.6 | Reliability | Error handling | `test_rate_limit_triggers_fallback`, `test_timeout_triggers_fallback` |
| 15.1.7 | Test Strategy | pytest | Coverage report |
| 15.1.8 | Observability | Status summarizer | SSE verification |

---

## References

1. **Epic 15 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-15.md`)
   - AC 15.1.1-15.1.8 acceptance criteria
   - Data models and contracts
   - Non-functional requirements

2. **Epic 15 Overview** (`docs/epics/epic-15-extended-mcp-tools.md`)
   - Story 15.1 details and schema
   - API provider comparison
   - Architecture diagrams

3. **Tavily API Documentation** (`https://docs.tavily.com`)
   - Search endpoint specification
   - Rate limits and pricing
   - Response format

4. **Existing Tool Patterns:**
   - `mcp_server/tools.py` - store_memory_tool pattern
   - `mcp_server/tests/test_store_memory_tool.py` - Test patterns
   - `backend/api/status_summarizers.py` - Summarizer patterns

---

**Created:** 2025-12-30
**Last Updated:** 2025-12-30
**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Story:** 15.1 - Web Search Tool (Tavily + DuckDuckGo)
**Status:** done
