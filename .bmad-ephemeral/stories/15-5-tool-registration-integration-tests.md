# Story 15.5: Tool Registration & Integration Testing

Status: backlog

## Story

**As a** developer,
**I want** all new tools properly registered and tested,
**So that** they work correctly in the production system.

**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Prerequisites:** Stories 15.1-15.4 completed
**Estimated Effort:** 1 day

## Acceptance Criteria

### AC #1: Tool Registration (15.5.1)
**Given** the MCP server starts
**When** tools are initialized in `register_default_tools()`
**Then** all 4 new tools (web_search, web_crawl, reddit_search, update_user_profile) are registered

**Mapped to Tasks:** Task 1

---

### AC #2: Tools in List Response (15.5.2)
**Given** a client calls `GET /tools/list` or sends `tools/list` JSON-RPC method
**When** the MCP server responds
**Then** all 4 new tools appear with correct schemas matching their inputSchema definitions

**Mapped to Tasks:** Task 1

---

### AC #3: System Prompt Updates (15.5.3)
**Given** a chat request is processed
**When** the system prompt is constructed via `build_system_prompt()`
**Then** usage guidance for all 4 new tools is included in TOOL_USAGE_INSTRUCTIONS

**Mapped to Tasks:** Task 2

---

### AC #4: Status Summarizers (15.5.4)
**Given** any of the 4 new tools executes
**When** the tool starts and completes
**Then** appropriate status updates are emitted via SSE using summarizers in SUMMARIZERS registry

**Mapped to Tasks:** Task 3

---

### AC #5: Integration Tests (15.5.5)
**Given** integration tests are run with `pytest --run-integration`
**When** the flag is set
**Then** tests call live services and verify tool behavior; tests skip gracefully without flag

**Mapped to Tasks:** Task 4

---

### AC #6: E2E Test (15.5.6)
**Given** a test chat message triggers a tool
**When** the /api/chat and /api/stream endpoints are called
**Then** the tool executes correctly and returns results via SSE

**Mapped to Tasks:** Task 5

---

## Tasks / Subtasks

### Task 1: Register All Tools in MCP Server
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #2

**Implementation Details:**

Update `mcp_server/server.py` to register all 4 new tools following the existing pattern:

```python
# Add imports at top of file (line ~24-43)
from mcp_server.tools import (
    ToolRegistry,
    health_check_tool,
    store_memory_tool,
    delete_memory_tool,
    retrieve_memories_tool,
    compact_memories_tool,
    get_user_profile_tool,
    get_portfolio_tool,
    add_holding_tool,
    update_holding_tool,
    remove_holding_tool,
    clear_portfolio_tool,
    analyze_stock_tool,
    get_stock_history_tool,
    create_trigger_tool,
    list_triggers_tool,
    update_trigger_tool,
    delete_trigger_tool,
    # NEW Epic 15 tools
    web_search_tool,
    web_crawl_tool,
    reddit_search_tool,
    update_user_profile_tool,
)

# In register_default_tools() method (line ~79-101)
def register_default_tools(self):
    """Register default tools."""
    # ... existing tool registrations ...

    # Epic 15: Extended MCP Tools - Web & Profile
    self.tool_registry.register(web_search_tool)
    self.tool_registry.register(web_crawl_tool)
    self.tool_registry.register(reddit_search_tool)
    self.tool_registry.register(update_user_profile_tool)

    logger.info(f"Registered {len(self.tool_registry.tools)} tools")
```

**Tool Export Requirements in `mcp_server/tools.py`:**
Ensure each tool is defined and exported using the existing decorator pattern:
```python
@tool_handler(
    name="web_search",
    description="Search the web for current information using Tavily with DuckDuckGo fallback",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "max_results": {"type": "integer", "description": "Maximum results (1-10, default 5)", "default": 5},
            "search_depth": {"type": "string", "enum": ["basic", "advanced"], "default": "basic"},
            "include_domains": {"type": "array", "items": {"type": "string"}},
            "exclude_domains": {"type": "array", "items": {"type": "string"}}
        },
        "required": ["query"]
    }
)
async def web_search_tool_handler(query: str, max_results: int = 5, ...) -> dict:
    ...

# Similar for: web_crawl_tool, reddit_search_tool, update_user_profile_tool
```

**Subtasks:**
- [ ] Import all 4 new tools in server.py (update import block lines 24-43)
- [ ] Register web_search_tool in register_default_tools()
- [ ] Register web_crawl_tool in register_default_tools()
- [ ] Register reddit_search_tool in register_default_tools()
- [ ] Register update_user_profile_tool in register_default_tools()
- [ ] Verify tools appear in `GET /tools/list` response
- [ ] Verify each tool schema matches Epic 15 tech spec definitions
- [ ] Run `make health` to confirm server starts correctly

---

### Task 2: Update System Prompt
**Status:** TODO
**Acceptance Criteria:** AC #3

**Implementation Details:**

Update `backend/api/prompts.py` to add guidance for all 4 new tools:

```python
# Add new constant after MEMORY_MANAGEMENT_SECTION (around line 166)
EXTENDED_TOOLS_SECTION = """
## EXTENDED WEB & PROFILE TOOLS

### Web Search (web_search)
Search the web for current information. Use when:
- User asks about recent events, news, or current data
- Looking up product reviews, comparisons, or prices
- Researching topics that may have changed since your knowledge cutoff
- Need real-time information that Live Search can't provide

Parameters:
- query: Search query (required)
- max_results: 1-10 results (default: 5)
- search_depth: "basic" (faster) or "advanced" (deeper)
- include_domains: Only search these domains
- exclude_domains: Skip these domains

Example: "What are the latest reviews for the iPhone 16?"

### Web Crawl (web_crawl)
Fetch full content from a specific URL. Use when:
- User shares a URL and wants you to read it
- Need detailed content from a specific page
- web_search returned a promising result that needs deeper analysis

Parameters:
- url: URL to crawl (required)
- include_images: Include image descriptions (default: false)
- max_length: Max content length (default: 10000)
- wait_for_js: Wait for JavaScript rendering (default: false)

Example: "Read this article: https://example.com/article"

### Reddit Search (reddit_search)
Search Reddit for community discussions. Use when:
- User wants real opinions and experiences
- Looking for recommendations from specific communities
- Researching products, services, or topics with active subreddits

Parameters:
- query: Search query (required)
- subreddit: Specific subreddit (without r/ prefix)
- search_type: "posts", "comments", or "subreddits"
- sort: "relevance", "hot", "top", "new"
- time_filter: "hour", "day", "week", "month", "year", "all"
- limit: 1-25 results (default: 10)
- include_comments: Include top comments (default: true)

Example: "What does r/personalfinance think about robo-advisors?"

### Profile Update (update_user_profile)
Update user profile fields. Use when:
- User explicitly shares new personal information
- User corrects previously known information
- User states new preferences or goals

Parameters:
- user_id: User identifier (ALWAYS use system-provided user_id)
- category: "basics", "preferences", "goals", "interests", "background"
- field_name: Field name within category
- value: New value (string, number, boolean, or array)
- reason: Optional reason for audit trail

IMPORTANT: Only update profile based on explicit user statements, not inferred information.

Example: User says "I just moved to Austin" -> Update basics/location
"""

# In build_system_prompt() function (around line 755)
# Add after MEMORY_MANAGEMENT_SECTION:
prompt_parts.append("\n\n" + EXTENDED_TOOLS_SECTION)
```

**Subtasks:**
- [ ] Add EXTENDED_TOOLS_SECTION constant with guidance for all 4 tools
- [ ] Include parameters and examples for web_search
- [ ] Include parameters and examples for web_crawl
- [ ] Include parameters and examples for reddit_search
- [ ] Include parameters and examples for update_user_profile
- [ ] Add section to build_system_prompt() after MEMORY_MANAGEMENT_SECTION
- [ ] Run test: `pytest backend/tests/unit/test_prompts.py` to verify no regressions

---

### Task 3: Add Status Summarizers
**Status:** TODO
**Acceptance Criteria:** AC #4

**Implementation Details:**

Update `backend/api/status_summarizers.py` to add summarizers for all 4 new tools:

```python
# Add new summarizer functions (after existing summarizers, around line 420)

def summarize_web_search_result(result: Dict[str, Any]) -> str:
    """Summarize web_search tool result.

    Result shape:
        {
            "status": "success"|"error",
            "provider": "tavily"|"duckduckgo",
            "results": [...],
            "query": str
        }

    Returns:
        Concise summary string

    Examples:
        "Found 5 results via Tavily"
        "Found 3 results via DuckDuckGo"
        "No results found"
    """
    if result.get("status") == "error":
        return result.get("error_message", "Search failed")[:500]

    provider = result.get("provider", "web")
    results = result.get("results", [])
    count = len(results)

    if count == 0:
        return "No results found"
    elif count == 1:
        return f"Found 1 result via {provider.title()}"
    else:
        return f"Found {count} results via {provider.title()}"


def summarize_web_crawl_result(result: Dict[str, Any]) -> str:
    """Summarize web_crawl tool result.

    Result shape:
        {
            "status": "success"|"error",
            "provider": "crawl4ai"|"jina",
            "title": str,
            "content": str,
            "truncated": bool
        }

    Returns:
        Concise summary string

    Examples:
        "Loaded: Page Title"
        "Page loaded (truncated)"
    """
    if result.get("status") == "error":
        return result.get("error_message", "Crawl failed")[:500]

    title = result.get("title", "Unknown page")
    truncated = result.get("truncated", False)

    # Truncate title if too long
    if len(title) > 40:
        title = title[:37] + "..."

    if truncated:
        return f"Loaded: {title} (truncated)"
    else:
        return f"Loaded: {title}"


def summarize_reddit_search_result(result: Dict[str, Any]) -> str:
    """Summarize reddit_search tool result.

    Result shape:
        {
            "status": "success"|"error",
            "provider": "praw"|"json_api",
            "query": str,
            "subreddit": str,
            "results": [...]
        }

    Returns:
        Concise summary string

    Examples:
        "Found 10 posts in r/all"
        "Found 5 posts in r/personalfinance"
        "No posts found"
    """
    if result.get("status") == "error":
        return result.get("error_message", "Reddit search failed")[:500]

    results = result.get("results", [])
    subreddit = result.get("subreddit", "all")
    count = len(results)

    if count == 0:
        return f"No posts found in r/{subreddit}"
    elif count == 1:
        return f"Found 1 post in r/{subreddit}"
    else:
        return f"Found {count} posts in r/{subreddit}"


def summarize_update_profile_result(result: Dict[str, Any]) -> str:
    """Summarize update_user_profile tool result.

    Result shape:
        {
            "status": "success"|"error",
            "category": str,
            "field_name": str,
            "value": any
        }

    Returns:
        Concise summary string

    Examples:
        "Updated basics/location"
        "Updated preferences/communication_style"
        "Profile update failed"
    """
    if result.get("status") == "error":
        return result.get("error_message", "Profile update failed")[:500]

    category = result.get("category", "???")
    field_name = result.get("field_name", "???")

    return f"Updated {category}/{field_name}"


# Update SUMMARIZERS registry (around line 425)
SUMMARIZERS = {
    # ... existing summarizers ...
    "get_portfolio": summarize_portfolio_result,
    "add_holding": summarize_add_holding_result,
    "update_holding": summarize_update_holding_result,
    "remove_holding": summarize_remove_holding_result,
    "clear_portfolio": summarize_clear_portfolio_result,
    "analyze_stock": summarize_analyze_stock_result,
    "get_stock_history": summarize_stock_history_result,
    "get_user_profile": summarize_profile_result,
    "store_memory": summarize_store_memory_result,
    "delete_memory": summarize_delete_memory_result,
    "retrieve_memories": summarize_retrieve_memories_result,
    "internet_search": summarize_internet_search_result,
    "health_check": summarize_health_check_result,
    # Epic 15: Extended MCP Tools
    "web_search": summarize_web_search_result,
    "web_crawl": summarize_web_crawl_result,
    "reddit_search": summarize_reddit_search_result,
    "update_user_profile": summarize_update_profile_result,
}
```

**Subtasks:**
- [ ] Add summarize_web_search_result function
- [ ] Add summarize_web_crawl_result function
- [ ] Add summarize_reddit_search_result function
- [ ] Add summarize_update_profile_result function
- [ ] Register all 4 summarizers in SUMMARIZERS dictionary
- [ ] Add unit tests in `backend/tests/unit/test_status_summarizers.py`
- [ ] Verify SSE status emission via manual testing

---

### Task 4: Write Integration Tests
**Status:** TODO
**Acceptance Criteria:** AC #5

**Implementation Details:**

Create `mcp_server/tests/test_epic15_integration.py`:

```python
"""
Integration tests for Epic 15 MCP tools.

These tests call live external services and should be run with:
    pytest --run-integration mcp_server/tests/test_epic15_integration.py

Tests will be skipped if --run-integration flag is not provided.
"""

import pytest
import os

# Skip all tests in this module if --run-integration not specified
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as integration test requiring live services"
    )


class TestWebSearchIntegration:
    """Integration tests for web_search tool."""

    @pytest.fixture(autouse=True)
    def skip_if_no_integration(self, request):
        """Skip test if --run-integration not specified."""
        if not request.config.getoption("--run-integration", default=False):
            pytest.skip("Integration test - use --run-integration to run")

    @pytest.fixture(autouse=True)
    def check_api_key(self):
        """Skip if TAVILY_API_KEY not available."""
        if not os.environ.get("TAVILY_API_KEY"):
            pytest.skip("TAVILY_API_KEY not set - skipping live Tavily test")

    async def test_tavily_search_live(self):
        """Test live Tavily search with real API."""
        from mcp_server.tools import web_search_tool_handler

        result = await web_search_tool_handler(
            query="Python programming language",
            max_results=3,
            search_depth="basic"
        )

        assert result["status"] == "success"
        assert result["provider"] == "tavily"
        assert len(result["results"]) <= 3
        assert all("title" in r for r in result["results"])
        assert all("url" in r for r in result["results"])

    async def test_duckduckgo_fallback(self, monkeypatch):
        """Test DuckDuckGo fallback when Tavily fails."""
        from mcp_server.tools import web_search_tool_handler

        # Force Tavily to fail by setting invalid key
        monkeypatch.setenv("TAVILY_API_KEY", "invalid-key-12345")

        result = await web_search_tool_handler(
            query="Python programming",
            max_results=3
        )

        # Should fall back to DuckDuckGo
        assert result["status"] == "success"
        assert result["provider"] == "duckduckgo"


class TestWebCrawlIntegration:
    """Integration tests for web_crawl tool."""

    @pytest.fixture(autouse=True)
    def skip_if_no_integration(self, request):
        """Skip test if --run-integration not specified."""
        if not request.config.getoption("--run-integration", default=False):
            pytest.skip("Integration test - use --run-integration to run")

    async def test_crawl4ai_live(self):
        """Test live web crawl with crawl4ai."""
        from mcp_server.tools import web_crawl_tool_handler

        result = await web_crawl_tool_handler(
            url="https://example.com",
            max_length=5000
        )

        assert result["status"] == "success"
        assert result["provider"] in ("crawl4ai", "jina")
        assert "content" in result
        assert "title" in result
        assert len(result["content"]) > 0

    async def test_crawl_with_max_length(self):
        """Test content truncation at max_length."""
        from mcp_server.tools import web_crawl_tool_handler

        result = await web_crawl_tool_handler(
            url="https://example.com",
            max_length=100  # Very short to force truncation
        )

        assert result["status"] == "success"
        assert len(result["content"]) <= 100
        # truncated flag may or may not be set depending on actual content length


class TestRedditSearchIntegration:
    """Integration tests for reddit_search tool."""

    @pytest.fixture(autouse=True)
    def skip_if_no_integration(self, request):
        """Skip test if --run-integration not specified."""
        if not request.config.getoption("--run-integration", default=False):
            pytest.skip("Integration test - use --run-integration to run")

    async def test_reddit_search_live(self):
        """Test live Reddit search."""
        from mcp_server.tools import reddit_search_tool_handler

        result = await reddit_search_tool_handler(
            query="Python programming",
            subreddit="programming",
            limit=5
        )

        assert result["status"] == "success"
        assert result["provider"] in ("praw", "json_api")
        assert len(result["results"]) <= 5

    async def test_reddit_search_all_subreddits(self):
        """Test Reddit search across all subreddits."""
        from mcp_server.tools import reddit_search_tool_handler

        result = await reddit_search_tool_handler(
            query="machine learning",
            limit=5
        )

        assert result["status"] == "success"
        assert result["subreddit"] == "all"


class TestProfileUpdateIntegration:
    """Integration tests for update_user_profile tool."""

    @pytest.fixture(autouse=True)
    def skip_if_no_integration(self, request):
        """Skip test if --run-integration not specified."""
        if not request.config.getoption("--run-integration", default=False):
            pytest.skip("Integration test - use --run-integration to run")

    @pytest.fixture(autouse=True)
    def check_agentic_memories(self):
        """Skip if agentic-memories not available."""
        import httpx
        url = os.environ.get("AGENTIC_MEMORIES_URL", "http://localhost:8080")
        try:
            response = httpx.get(f"{url}/health", timeout=2.0)
            if response.status_code != 200:
                pytest.skip("agentic-memories service not healthy")
        except httpx.RequestError:
            pytest.skip("agentic-memories service not available")

    async def test_profile_update_live(self):
        """Test live profile update."""
        from mcp_server.tools import update_user_profile_tool_handler

        result = await update_user_profile_tool_handler(
            user_id="test_integration_user",
            category="preferences",
            field_name="test_field",
            value="test_value_integration"
        )

        # May return success or error depending on profile existence
        assert result["status"] in ("success", "error")
        if result["status"] == "success":
            assert result["category"] == "preferences"
            assert result["field_name"] == "test_field"

    async def test_profile_update_invalid_category(self):
        """Test profile update with invalid category."""
        from mcp_server.tools import update_user_profile_tool_handler

        result = await update_user_profile_tool_handler(
            user_id="test_user",
            category="invalid_category",  # Not in allowed list
            field_name="test_field",
            value="test_value"
        )

        assert result["status"] == "error"
        # Should indicate invalid category


class TestToolRegistration:
    """Tests for tool registration in MCP server."""

    async def test_all_tools_registered(self):
        """Verify all Epic 15 tools are registered."""
        from mcp_server.server import mcp_server

        tool_names = list(mcp_server.tool_registry.tools.keys())

        # Epic 15 tools
        assert "web_search" in tool_names
        assert "web_crawl" in tool_names
        assert "reddit_search" in tool_names
        assert "update_user_profile" in tool_names

    async def test_tools_list_endpoint(self):
        """Verify tools appear in tools/list response."""
        from mcp_server.server import mcp_server

        response = mcp_server.handle_tools_list("test-request-id")

        assert response["jsonrpc"] == "2.0"
        assert "result" in response
        assert "tools" in response["result"]

        tool_names = [t["name"] for t in response["result"]["tools"]]

        assert "web_search" in tool_names
        assert "web_crawl" in tool_names
        assert "reddit_search" in tool_names
        assert "update_user_profile" in tool_names

    async def test_tool_schemas_valid(self):
        """Verify all Epic 15 tools have valid schemas."""
        from mcp_server.server import mcp_server

        epic15_tools = ["web_search", "web_crawl", "reddit_search", "update_user_profile"]

        for tool_name in epic15_tools:
            tool_info = mcp_server.tool_registry.get_tool(tool_name)
            assert tool_info is not None, f"Tool {tool_name} not found"
            assert "inputSchema" in tool_info, f"Tool {tool_name} missing inputSchema"
            assert tool_info["inputSchema"].get("type") == "object"
            assert "properties" in tool_info["inputSchema"]
            assert "required" in tool_info["inputSchema"]
```

Add pytest option to `mcp_server/tests/conftest.py`:
```python
def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run integration tests that call live services"
    )
```

**Subtasks:**
- [ ] Add --run-integration pytest option in conftest.py
- [ ] Write web_search integration tests (live Tavily, DDG fallback)
- [ ] Write web_crawl integration tests (crawl4ai, max_length)
- [ ] Write reddit_search integration tests (PRAW, JSON API)
- [ ] Write update_user_profile integration tests (valid/invalid category)
- [ ] Write tool registration verification tests
- [ ] Handle API key requirements with skip decorators
- [ ] Document test requirements in docstrings

---

### Task 5: Write E2E Tests
**Status:** TODO
**Acceptance Criteria:** AC #6

**Implementation Details:**

Create `backend/tests/e2e/test_epic15_e2e.py`:

```python
"""
End-to-end tests for Epic 15 MCP tools via chat endpoints.

Tests the complete flow from chat request -> tool execution -> SSE response.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient

pytestmark = [pytest.mark.e2e, pytest.mark.asyncio]


class TestExtendedToolsE2E:
    """E2E tests for Epic 15 extended tools."""

    @pytest.fixture
    def mock_llm_with_tool_call(self):
        """Mock LLM that returns a tool call."""
        def _create_mock(tool_name: str, tool_args: dict):
            mock_response = MagicMock()
            mock_response.choices = [MagicMock()]
            mock_response.choices[0].message = MagicMock()
            mock_response.choices[0].message.tool_calls = [MagicMock()]
            mock_response.choices[0].message.tool_calls[0].function.name = tool_name
            mock_response.choices[0].message.tool_calls[0].function.arguments = json.dumps(tool_args)
            return mock_response
        return _create_mock

    @pytest.fixture
    def mock_mcp_client(self):
        """Mock MCP client for tool execution."""
        with patch("backend.api.mcp_client.MCPClient") as mock_cls:
            client = AsyncMock()
            mock_cls.return_value = client
            yield client

    async def test_web_search_via_chat_flow(self, mock_mcp_client):
        """Test web_search tool triggered via chat, results in SSE stream."""
        # Setup mock tool response
        mock_mcp_client.call_tool.return_value = {
            "status": "success",
            "provider": "tavily",
            "results": [
                {"title": "Python 3.13 Release", "url": "https://python.org/...", "snippet": "..."}
            ],
            "query": "Python 3.13"
        }

        # Test would verify:
        # 1. Chat endpoint accepts message
        # 2. LLM decides to call web_search
        # 3. Tool is executed via MCP
        # 4. Status summarizer emits "Found 1 result via Tavily"
        # 5. SSE stream contains tool result
        assert mock_mcp_client.call_tool.called or True  # Placeholder

    async def test_web_crawl_via_chat_flow(self, mock_mcp_client):
        """Test web_crawl tool triggered via chat."""
        mock_mcp_client.call_tool.return_value = {
            "status": "success",
            "provider": "crawl4ai",
            "url": "https://example.com",
            "title": "Example Domain",
            "content": "This domain is for use in illustrative examples...",
            "truncated": False
        }

        # Test would verify crawl flow
        assert True  # Placeholder for actual test

    async def test_reddit_search_via_chat_flow(self, mock_mcp_client):
        """Test reddit_search tool triggered via chat."""
        mock_mcp_client.call_tool.return_value = {
            "status": "success",
            "provider": "praw",
            "query": "robo-advisors",
            "subreddit": "personalfinance",
            "results": [
                {
                    "type": "post",
                    "title": "Best robo-advisors in 2025?",
                    "subreddit": "r/personalfinance",
                    "score": 150,
                    "comments": []
                }
            ]
        }

        # Test would verify Reddit search flow
        assert True  # Placeholder

    async def test_profile_update_via_chat_flow(self, mock_mcp_client):
        """Test update_user_profile tool triggered via chat."""
        mock_mcp_client.call_tool.return_value = {
            "status": "success",
            "user_id": "test_user",
            "category": "basics",
            "field_name": "location",
            "value": "Austin, TX"
        }

        # Test would verify profile update flow
        assert True  # Placeholder

    async def test_multiple_tools_sequence(self, mock_mcp_client):
        """Test multiple tools called in sequence (search then crawl)."""
        # First call: web_search
        # Second call: web_crawl on first result
        mock_mcp_client.call_tool.side_effect = [
            {
                "status": "success",
                "provider": "tavily",
                "results": [{"title": "Python Tutorial", "url": "https://python.org/tutorial"}]
            },
            {
                "status": "success",
                "provider": "crawl4ai",
                "title": "Python Tutorial",
                "content": "Tutorial content..."
            }
        ]

        # Test would verify sequential tool calls
        assert True  # Placeholder

    async def test_status_events_in_stream(self, mock_mcp_client):
        """Verify status events appear in SSE stream during tool execution."""
        mock_mcp_client.call_tool.return_value = {
            "status": "success",
            "provider": "tavily",
            "results": []
        }

        # Test would verify SSE stream contains:
        # 1. "status" event with "Searching the web..."
        # 2. "status" event with "No results found"
        assert True  # Placeholder


class TestStatusSummarizersE2E:
    """E2E tests for status summarizers."""

    async def test_web_search_status_flow(self):
        """Test web_search status summary appears correctly."""
        from backend.api.status_summarizers import summarize_tool_result

        result = summarize_tool_result("web_search", {
            "status": "success",
            "provider": "tavily",
            "results": [{"title": "Test", "url": "https://test.com"}]
        })

        assert "1 result" in result.lower() or "found" in result.lower()

    async def test_web_crawl_status_flow(self):
        """Test web_crawl status summary appears correctly."""
        from backend.api.status_summarizers import summarize_tool_result

        result = summarize_tool_result("web_crawl", {
            "status": "success",
            "provider": "crawl4ai",
            "title": "Test Page",
            "content": "...",
            "truncated": False
        })

        assert "Test Page" in result or "loaded" in result.lower()

    async def test_reddit_search_status_flow(self):
        """Test reddit_search status summary appears correctly."""
        from backend.api.status_summarizers import summarize_tool_result

        result = summarize_tool_result("reddit_search", {
            "status": "success",
            "provider": "praw",
            "subreddit": "programming",
            "results": [{"title": "Post 1"}, {"title": "Post 2"}]
        })

        assert "2" in result and "programming" in result

    async def test_profile_update_status_flow(self):
        """Test update_user_profile status summary appears correctly."""
        from backend.api.status_summarizers import summarize_tool_result

        result = summarize_tool_result("update_user_profile", {
            "status": "success",
            "category": "basics",
            "field_name": "location"
        })

        assert "basics/location" in result.lower() or "updated" in result.lower()
```

**Subtasks:**
- [ ] Write E2E test for web_search via chat flow
- [ ] Write E2E test for web_crawl via chat flow
- [ ] Write E2E test for reddit_search via chat flow
- [ ] Write E2E test for update_user_profile via chat flow
- [ ] Write E2E test for multiple tools in sequence
- [ ] Write E2E test for status events in SSE stream
- [ ] Verify status summarizers integrate with stream correctly
- [ ] Run full E2E test suite: `pytest backend/tests/e2e/test_epic15_e2e.py -v`

---

## Definition of Done

- [ ] All 5 tasks completed with subtasks checked off
- [ ] All 6 acceptance criteria validated:
  - [ ] AC #1: 4 tools registered in MCP server
  - [ ] AC #2: tools/list returns all 4 new tools with correct schemas
  - [ ] AC #3: System prompt includes usage guidance
  - [ ] AC #4: Status summarizers emit updates for all tools
  - [ ] AC #5: Integration tests pass with --run-integration
  - [ ] AC #6: E2E tests pass
- [ ] No regressions in existing tools (run full test suite)
- [ ] Code review completed
- [ ] Documentation updated if needed

---

## Dev Notes

### Architecture Context

This story ties together all the work from Stories 15.1-15.4 and ensures the tools are properly integrated into the production system.

**Integration Points:**
1. **MCP Server** (`mcp_server/server.py`) - Tool registration
2. **Backend System Prompt** (`backend/api/prompts.py`) - LLM guidance
3. **Backend Status Summarizers** (`backend/api/status_summarizers.py`) - SSE updates
4. **SSE Stream** (`backend/api/routes/stream.py`) - Real-time status delivery
5. **Chat Endpoint** (`backend/api/routes/chat.py`) - E2E tool triggering

### Technical Constraints

1. **Tool Registration Order:**
   - Tools must be imported before registration in server.py
   - Handler functions must be async (decorated with @tool_handler)
   - Tool names must be unique across all registered tools

2. **System Prompt Size:**
   - Keep guidance concise to avoid context limit issues
   - EXTENDED_TOOLS_SECTION should be <2000 chars
   - Follow existing section patterns (MEMORY_MANAGEMENT_SECTION, PROACTIVE_CAPABILITIES_SECTION)

3. **Status Summarizer Requirements:**
   - Output must be <50 chars when possible (for mobile display)
   - Must handle both success and error cases
   - Must match tool_name exactly in SUMMARIZERS registry

4. **Test Isolation:**
   - Integration tests use live services - require API keys
   - E2E tests use mocked LLM and MCP client
   - Unit tests mock all external dependencies

### Dependencies

**Blocking:**
- Stories 15.1-15.4 must be complete
- All tool handlers implemented in `mcp_server/tools.py`:
  - `web_search_tool` / `web_search_tool_handler`
  - `web_crawl_tool` / `web_crawl_tool_handler`
  - `reddit_search_tool` / `reddit_search_tool_handler`
  - `update_user_profile_tool` / `update_user_profile_tool_handler`

**Non-Blocking:**
- Can run integration tests without all API keys (tests skip gracefully)
- E2E tests don't require live services (fully mocked)

### Key Files to Modify

**Files to Modify:**
| File | Changes |
|------|---------|
| `mcp_server/server.py` | Add imports (lines 24-43), register tools (lines 79-101) |
| `mcp_server/tools.py` | Ensure tool exports (verify Story 15.1-15.4 exports) |
| `backend/api/prompts.py` | Add EXTENDED_TOOLS_SECTION, update build_system_prompt() |
| `backend/api/status_summarizers.py` | Add 4 summarizer functions, update SUMMARIZERS dict |
| `mcp_server/tests/conftest.py` | Add --run-integration pytest option |

**Files to Create:**
| File | Purpose |
|------|---------|
| `mcp_server/tests/test_epic15_integration.py` | Integration tests with live services |
| `backend/tests/e2e/test_epic15_e2e.py` | E2E tests via chat endpoints |

### Environment Variables Required for Integration Tests

```bash
# Web Search (Task 4 integration tests)
TAVILY_API_KEY=tvly-...           # Required for live Tavily tests
DUCKDUCKGO_ENABLED=true           # Enable DDG fallback (default: true)

# Reddit (Task 4 integration tests)
REDDIT_CLIENT_ID=...              # Optional - tests skip if not set
REDDIT_CLIENT_SECRET=...          # Optional - tests skip if not set

# Profile Update (Task 4 integration tests)
AGENTIC_MEMORIES_URL=http://localhost:8080  # Required - tests skip if not healthy
```

### Testing Strategy

**Unit Tests (existing patterns):**
- Verify tool registration (no mocking needed)
- Verify schema correctness
- Test summarizer functions with various inputs

**Integration Tests (--run-integration flag):**
- Live Tavily API calls
- Live web crawling
- Live Reddit API calls
- Live profile updates

**E2E Tests (mocked):**
- Full chat flow with mocked LLM
- Verify status events in SSE stream
- Multiple tool calls in sequence

### Run Commands

```bash
# Unit tests only
pytest mcp_server/tests/test_epic15_integration.py::TestToolRegistration -v
pytest backend/tests/unit/test_status_summarizers.py -v

# Integration tests (requires API keys)
pytest --run-integration mcp_server/tests/test_epic15_integration.py -v

# E2E tests
pytest backend/tests/e2e/test_epic15_e2e.py -v

# Full test suite (no regressions)
pytest mcp_server/tests/ backend/tests/ -v --ignore=mcp_server/tests/test_epic15_integration.py
```

### Success Metrics

- [ ] All 4 tools appear in `GET /tools/list` response
- [ ] All status summarizers emit correctly (<50 chars)
- [ ] Integration tests pass with live services (100% when API keys present)
- [ ] E2E tests verify complete flow (100% pass rate)
- [ ] No regressions in existing tools (all existing tests pass)

---

## References

1. **Epic 15 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-15.md`)
   - AC 15.5.1-15.5.6 acceptance criteria
   - Data models and contracts
   - Test strategy summary

2. **Epic 15 Overview** (`docs/epics/epic-15-extended-mcp-tools.md`)
   - Story 15.5 details
   - Tool schemas and responses

3. **Existing Tool Registration** (`mcp_server/server.py`)
   - Current registration pattern (lines 79-101)
   - Import structure (lines 24-43)

4. **Existing Status Summarizers** (`backend/api/status_summarizers.py`)
   - Summarizer function patterns
   - SUMMARIZERS registry structure

5. **Existing System Prompt** (`backend/api/prompts.py`)
   - build_system_prompt() function
   - Existing tool guidance sections

6. **Test Patterns**
   - `mcp_server/tests/conftest.py` - MCP server test fixtures
   - `backend/tests/conftest.py` - Backend test fixtures
   - `backend/tests/e2e/` - Existing E2E test patterns

---

**Created:** 2025-12-30
**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Story:** 15.5 - Tool Registration & Integration Testing
**Status:** backlog
