# Epic Technical Specification: Extended MCP Tools - Web & Profile

Date: 2025-12-30
Author: Ankit
Epic ID: 15
Status: Draft

---

## Overview

Epic 15 extends Annie's MCP tool ecosystem with four new capabilities for external information gathering and profile management. Currently, Annie has limited web access (only via Grok-4 Live Search, which is expensive and provider-locked), no ability to fetch full webpage content, no Reddit access for community insights, and no mechanism for the LLM to directly update user profile fields.

This epic adds four new MCP tools:
1. **web_search** - Search the web using Tavily (primary, ~$0.001/search) with DuckDuckGo as a free fallback
2. **web_crawl** - Fetch and parse full webpage content using crawl4ai (local) with Jina Reader fallback
3. **reddit_search** - Search Reddit subreddits, posts, and comments using PRAW (OAuth) with JSON API fallback
4. **update_user_profile** - Update specific user profile fields via the agentic-memories profile API

These tools enable Annie to provide richer, more informed advice by accessing real-time web information, community discussions, and maintaining an up-to-date user profile.

## Objectives and Scope

### In-Scope

- **Story 15.1**: Implement `web_search` tool with Tavily primary provider and DuckDuckGo fallback
- **Story 15.2**: Implement `web_crawl` tool with crawl4ai primary and Jina Reader fallback
- **Story 15.3**: Implement `reddit_search` tool with PRAW primary and JSON API fallback
- **Story 15.4**: Implement `update_user_profile` tool using agentic-memories profile API
- **Story 15.5**: Tool registration in MCP server, system prompt updates, status summarizers, integration tests
- **Story 15.6**: Environment configuration (new API keys) and documentation updates

### Out-of-Scope

- Caching of web search results (future enhancement)
- Semantic search ranking using embeddings
- Additional sources (Twitter/X, HackerNews, StackOverflow)
- Bulk profile update operations
- Rate limiting dashboard or cost monitoring UI

## System Architecture Alignment

This epic extends the existing MCP Server tool architecture established in Epic 1 (Story 1.6) and follows the tool patterns from Epics 10 and 14.

**Architecture Components Referenced:**

```
LLM (Grok-4/Gemini/ChatGPT)
    ↓ Function Call
Backend API (Chat Logic)
    ↓ HTTP
MCP Server (Tool Hosting)
    ├── web_search      → Tavily API / DuckDuckGo
    ├── web_crawl       → crawl4ai (local) / Jina Reader
    ├── reddit_search   → PRAW / Reddit JSON API
    └── update_user_profile → agentic-memories profile API
```

**Constraints:**
- All tools must follow existing MCP JSON-RPC 2.0 protocol patterns
- Tools must implement status summarizers for real-time Telegram updates (Epic 11)
- Tools must support Langfuse tracing for observability (Epic 8)
- Tool timeouts must respect configured limits (MCP_TOOL_TIMEOUT, default 30s)
- Fallback providers ensure graceful degradation on primary failure

## Detailed Design

### Services and Modules

| Module | File | Responsibility | Owner |
|--------|------|----------------|-------|
| `web_search_tool_handler` | `mcp_server/tools.py` | Execute web searches via Tavily/DuckDuckGo | MCP Server |
| `web_crawl_tool_handler` | `mcp_server/tools.py` | Fetch and parse webpage content via crawl4ai/Jina | MCP Server |
| `reddit_search_tool_handler` | `mcp_server/tools.py` | Search Reddit posts/comments via PRAW/JSON API | MCP Server |
| `update_user_profile_tool_handler` | `mcp_server/tools.py` | Update profile fields via agentic-memories | MCP Server |
| `WebSearchStatusSummarizer` | `backend/api/status_summarizers.py` | Real-time status updates for web_search | Backend |
| `WebCrawlStatusSummarizer` | `backend/api/status_summarizers.py` | Real-time status updates for web_crawl | Backend |
| `RedditSearchStatusSummarizer` | `backend/api/status_summarizers.py` | Real-time status updates for reddit_search | Backend |
| `ProfileUpdateStatusSummarizer` | `backend/api/status_summarizers.py` | Real-time status updates for update_user_profile | Backend |

### Data Models and Contracts

#### Web Search Request/Response

```python
# Request (from LLM function call)
WebSearchRequest = {
    "query": str,                    # Required: Search query
    "max_results": int,              # Optional: 1-10, default 5
    "search_depth": str,             # Optional: "basic" or "advanced", default "basic"
    "include_domains": List[str],    # Optional: Whitelist domains
    "exclude_domains": List[str]     # Optional: Blacklist domains
}

# Response
WebSearchResponse = {
    "status": "success" | "error",
    "provider": "tavily" | "duckduckgo",
    "results": [
        {
            "title": str,
            "url": str,
            "snippet": str,
            "score": float  # Relevance score (0.0-1.0)
        }
    ],
    "query": str,
    "error_message": Optional[str]  # Present on error
}
```

#### Web Crawl Request/Response

```python
# Request
WebCrawlRequest = {
    "url": str,                      # Required: URL to crawl
    "include_images": bool,          # Optional: default False
    "max_length": int,               # Optional: default 10000 chars
    "wait_for_js": bool              # Optional: Wait for JS rendering, default False
}

# Response
WebCrawlResponse = {
    "status": "success" | "error",
    "provider": "crawl4ai" | "jina",
    "url": str,
    "title": str,
    "content": str,                  # Clean markdown content
    "metadata": {
        "description": Optional[str],
        "author": Optional[str],
        "published_date": Optional[str],
        "links_count": int
    },
    "truncated": bool,               # True if content exceeded max_length
    "error_message": Optional[str]
}
```

#### Reddit Search Request/Response

```python
# Request
RedditSearchRequest = {
    "query": str,                    # Required: Search query
    "subreddit": Optional[str],      # Optional: Limit to specific subreddit
    "search_type": str,              # Optional: "posts", "comments", "subreddits", default "posts"
    "sort": str,                     # Optional: "relevance", "hot", "top", "new", default "relevance"
    "time_filter": str,              # Optional: "hour", "day", "week", "month", "year", "all"
    "limit": int,                    # Optional: 1-25, default 10
    "include_comments": bool         # Optional: Include top comments, default True
}

# Response
RedditSearchResponse = {
    "status": "success" | "error",
    "provider": "praw" | "json_api",
    "query": str,
    "subreddit": str,                # "all" or specific subreddit
    "results": [
        {
            "type": "post" | "comment" | "subreddit",
            "title": str,
            "subreddit": str,
            "author": str,
            "score": int,
            "url": str,
            "selftext": Optional[str],
            "comments": [
                {
                    "author": str,
                    "score": int,
                    "body": str,
                    "replies_count": int
                }
            ]
        }
    ],
    "error_message": Optional[str]
}
```

#### Update User Profile Request/Response

```python
# Request
UpdateUserProfileRequest = {
    "user_id": str,                  # Required: User identifier
    "category": str,                 # Required: "basics", "preferences", "goals", "interests", "background"
    "field_name": str,               # Required: Field within category
    "value": Any,                    # Required: New value (string, number, boolean, array)
    "reason": Optional[str]          # Optional: Reason for update (audit trail)
}

# Response
UpdateUserProfileResponse = {
    "status": "success" | "error",
    "user_id": str,
    "category": str,
    "field_name": str,
    "value": Any,
    "previous_value": Optional[Any],
    "confidence": float,             # Always 100.0 for explicit updates
    "last_updated": str,             # ISO timestamp
    "error_message": Optional[str]
}
```

### APIs and Interfaces

#### External API Integrations

| API | Endpoint | Auth | Rate Limit | Cost |
|-----|----------|------|------------|------|
| Tavily Search | `https://api.tavily.com/search` | API Key | 1000/month (free) | $0.001/search |
| DuckDuckGo | `https://api.duckduckgo.com/` | None | ~1/second | Free |
| crawl4ai | Local library | None | N/A | Free |
| Jina Reader | `https://r.jina.ai/{url}` | API Key (optional) | Variable | Free tier |
| Reddit (PRAW) | OAuth via PRAW SDK | OAuth2 | 60/minute | Free |
| Reddit JSON | `https://www.reddit.com/.json` | None | Unofficial | Free |
| agentic-memories | `PUT /v1/profile/{category}/{field}` | None | Self-hosted | Free |

#### MCP Tool Schemas

All tools follow the established MCP JSON-RPC 2.0 pattern:

```python
# Tool registration format
{
    "name": "tool_name",
    "description": "Tool description for LLM",
    "inputSchema": {
        "type": "object",
        "properties": {...},
        "required": [...]
    },
    "handler": async_handler_function
}
```

### Workflows and Sequencing

#### Web Search Flow (Story 15.1)

```
1. LLM decides to search → web_search(query, ...)
2. MCP Server receives tool call
3. Status summarizer: "Searching the web..."
4. Try Tavily API:
   a. Build request with query, max_results, filters
   b. POST to Tavily search endpoint
   c. Parse results → return on success
5. On Tavily failure → Fallback to DuckDuckGo:
   a. Build DDG query
   b. Use duckduckgo-search library
   c. Parse results → return
6. Status summarizer: "Found {n} results"
7. Return results to LLM
```

#### Web Crawl Flow (Story 15.2)

```
1. LLM needs page content → web_crawl(url, ...)
2. MCP Server receives tool call
3. Status summarizer: "Reading webpage..."
4. Try crawl4ai (local):
   a. AsyncWebCrawler.arun(url)
   b. Optional: wait for JS if wait_for_js=True
   c. Extract markdown, metadata
   d. Truncate if > max_length
   e. Return on success
5. On crawl4ai failure → Fallback to Jina Reader:
   a. GET https://r.jina.ai/{url}
   b. Parse markdown response
   c. Return
6. Status summarizer: "Page loaded ({title})"
7. Return content to LLM
```

#### Reddit Search Flow (Story 15.3)

```
1. LLM needs Reddit info → reddit_search(query, ...)
2. MCP Server receives tool call
3. Status summarizer: "Searching Reddit..."
4. Check for PRAW credentials:
   a. If available → Use PRAW:
      - Initialize praw.Reddit client
      - Search subreddit (all or specific)
      - Apply sort, time_filter, limit
      - Optionally fetch top comments
   b. If no credentials → Use JSON API:
      - GET reddit.com/search.json?q={query}
      - Parse response
5. Status summarizer: "Found {n} posts"
6. Return results to LLM
```

#### Profile Update Flow (Story 15.4)

```
1. LLM learns new info → update_user_profile(...)
2. MCP Server receives tool call
3. Status summarizer: "Updating profile..."
4. Validate category against allowed list
5. PUT /v1/profile/{category}/{field_name}
   - Body: {user_id, value, source: "llm_explicit"}
6. Handle responses:
   - 200: Success, return updated profile
   - 404: Profile not found (may need to create)
   - 400: Invalid category/field
7. Status summarizer: "Profile updated"
8. Return result to LLM
```

## Non-Functional Requirements

### Performance

| Tool | Metric | Target | Source |
|------|--------|--------|--------|
| `web_search` | Latency P95 | <3s | Epic 15 Success Criteria |
| `web_crawl` | Latency P95 | <5s | Epic 15 Success Criteria |
| `reddit_search` | Latency P95 | <4s | Epic 15 Success Criteria |
| `update_user_profile` | Latency P95 | <1s | Epic 15 Success Criteria |
| All tools | Success rate | >98% | Epic 15 Success Criteria |

**Implementation Notes:**
- Tavily API typical response: 1-2s
- DuckDuckGo fallback: ~1s (local library)
- crawl4ai local: 2-4s (depends on page complexity, JS rendering adds 1-2s)
- PRAW: 2-3s (includes OAuth overhead on first request)
- agentic-memories: <500ms (self-hosted, local network)

### Security

| Requirement | Implementation | Source |
|-------------|----------------|--------|
| API Key Protection | All API keys stored in environment variables, never logged | Architecture Plan |
| Sensitive Data Masking | API keys masked in logs (e.g., `tvly...1234`) | Logging Infrastructure (Epic 1) |
| Input Validation | All tool inputs validated against JSON schema before processing | MCP Protocol |
| URL Validation | web_crawl validates URL format, blocks internal/private IP ranges | Security best practice |
| Rate Limit Handling | Respect API rate limits, implement backoff on 429 errors | API Provider requirements |
| Profile Update Audit | All profile updates logged with source="llm_explicit" for audit trail | Epic 15 Story 15.4 |
| Reddit OAuth Secrets | REDDIT_CLIENT_ID/SECRET stored securely, tokens not persisted | Security best practice |

### Reliability/Availability

| Requirement | Implementation | Source |
|-------------|----------------|--------|
| Fallback Providers | Each tool has primary/fallback provider pattern | Epic 15 Architecture |
| Graceful Degradation | Tool returns partial results or clear error on provider failure | Architecture Plan |
| Retry Logic | Exponential backoff (1s, 2s, 4s) for transient errors (5xx, timeouts) | Existing tool patterns |
| Circuit Breaker | Skip failing provider after 5 consecutive failures for 15 minutes | Memory storage pattern (Epic 3) |
| Timeout Handling | Respect MCP_TOOL_TIMEOUT (default 30s), clean timeout on excess | Architecture Plan |

**Fallback Strategy:**
| Tool | Primary | Fallback | Trigger |
|------|---------|----------|---------|
| web_search | Tavily | DuckDuckGo | API error, rate limit, timeout |
| web_crawl | crawl4ai | Jina Reader | Parse failure, timeout, blocked |
| reddit_search | PRAW | JSON API | OAuth failure, no credentials |
| update_user_profile | agentic-memories | N/A (critical path) | Retry only |

### Observability

| Signal | Implementation | Tool |
|--------|----------------|------|
| Tool Call Tracing | Langfuse @observe() decorator on all handlers | All tools |
| Latency Metrics | `duration_ms` logged for every tool call | All tools |
| Provider Tracking | `provider` field in response (tavily/duckduckgo, etc.) | All tools |
| Error Logging | Structured error logs with error_code, provider, attempt | All tools |
| Cost Tracking | Log Tavily search count for cost estimation | web_search |
| Rate Limit Events | Log rate limit hits with provider and retry timing | All tools |
| Status Updates | Real-time status via SSE for Telegram updates | All tools |

**Key Log Events:**
```python
# web_search
logger.info("web_search.started", extra={"query": query, "provider": "tavily"})
logger.info("web_search.completed", extra={"results_count": n, "duration_ms": 1234, "provider": "tavily"})
logger.warning("web_search.fallback", extra={"primary": "tavily", "fallback": "duckduckgo", "reason": "rate_limit"})

# web_crawl
logger.info("web_crawl.started", extra={"url": url, "wait_for_js": False})
logger.info("web_crawl.completed", extra={"url": url, "content_length": 5000, "truncated": False})

# reddit_search
logger.info("reddit_search.started", extra={"query": query, "subreddit": "all"})
logger.info("reddit_search.completed", extra={"results_count": n, "provider": "praw"})

# update_user_profile
logger.info("profile_update.started", extra={"user_id": user_id, "category": category, "field": field})
logger.info("profile_update.completed", extra={"user_id": user_id, "success": True})
```

## Dependencies and Integrations

### Python Package Dependencies

**MCP Server (`mcp_server/requirements.txt`):**
```
# Existing dependencies (no changes)
pydantic>=2.9.0
mcp>=0.1.0
fastapi>=0.104.0
uvicorn>=0.24.0
requests>=2.31.0
httpx>=0.24.0
pytz>=2024.1
pytest>=9.0.0
pytest-asyncio>=1.3.0
yfinance>=0.2.48
pandas>=2.0.0
redis>=5.0.0

# NEW: Epic 15 dependencies
tavily-python>=0.3.0          # Web search (Story 15.1)
duckduckgo-search>=6.0.0      # Fallback web search (Story 15.1)
crawl4ai>=0.3.0               # Web crawling (Story 15.2)
praw>=7.7.0                   # Reddit API - optional (Story 15.3)
```

**Backend (`backend/requirements.txt`):**
No new dependencies required. Status summarizers use existing patterns.

### External Service Dependencies

| Service | Purpose | Required | Story |
|---------|---------|----------|-------|
| Tavily API | Primary web search | Yes | 15.1 |
| DuckDuckGo | Fallback web search | No (built-in) | 15.1 |
| crawl4ai | Primary web crawling | Yes (local lib) | 15.2 |
| Jina Reader | Fallback web crawling | No (free tier) | 15.2 |
| Reddit OAuth | Primary Reddit search | Optional | 15.3 |
| Reddit JSON API | Fallback Reddit search | No (public) | 15.3 |
| agentic-memories | Profile API | Yes (existing) | 15.4 |

### Environment Variables (New)

```bash
# Web Search (Story 15.1)
TAVILY_API_KEY=tvly-...               # Required for web_search
DUCKDUCKGO_ENABLED=true               # Enable DDG fallback (default: true)

# Web Crawl (Story 15.2)
JINA_API_KEY=...                      # Optional for Jina Reader fallback

# Reddit (Story 15.3)
REDDIT_CLIENT_ID=...                  # Optional for PRAW
REDDIT_CLIENT_SECRET=...              # Optional for PRAW
REDDIT_USER_AGENT=annie-bot/1.0       # Optional, default provided
```

### Integration Points

| From | To | Protocol | Notes |
|------|----|----------|-------|
| MCP Server | Tavily API | HTTPS | API key auth |
| MCP Server | DuckDuckGo | Library | No auth |
| MCP Server | crawl4ai | Local | Python library |
| MCP Server | Jina Reader | HTTPS | Optional API key |
| MCP Server | Reddit (PRAW) | HTTPS | OAuth2 |
| MCP Server | Reddit JSON | HTTPS | No auth |
| MCP Server | agentic-memories | HTTP | Local network |
| Backend | MCP Server | HTTP | Internal network |

### Version Constraints

| Package | Min Version | Reason |
|---------|-------------|--------|
| `tavily-python` | 0.3.0 | Async support, search_depth parameter |
| `duckduckgo-search` | 6.0.0 | Stable async API |
| `crawl4ai` | 0.3.0 | AsyncWebCrawler, markdown output |
| `praw` | 7.7.0 | Python 3.12 compatibility, async support |

## Acceptance Criteria (Authoritative)

### Story 15.1: Web Search Tool

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| 15.1.1 | Tavily API integration with API key from TAVILY_API_KEY environment variable | Yes |
| 15.1.2 | DuckDuckGo fallback activated on Tavily failure (error, rate limit, timeout) | Yes |
| 15.1.3 | Search depth options (basic/advanced) passed to Tavily API | Yes |
| 15.1.4 | Domain filtering (include_domains, exclude_domains) applied correctly | Yes |
| 15.1.5 | Results limited to max_results parameter (1-10, default 5) | Yes |
| 15.1.6 | Error handling for rate limits (429), timeouts (10s), network errors | Yes |
| 15.1.7 | Unit tests with mocked Tavily/DDG responses achieve >80% coverage | Yes |
| 15.1.8 | Status summarizer displays "Searching the web..." and "Found N results" | Yes |

### Story 15.2: Web Crawl Tool

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| 15.2.1 | crawl4ai integration using AsyncWebCrawler for primary crawling | Yes |
| 15.2.2 | Jina Reader fallback (GET https://r.jina.ai/{url}) on crawl4ai failure | Yes |
| 15.2.3 | JavaScript rendering option (wait_for_js=True) supported | Yes |
| 15.2.4 | Clean markdown output from crawled content | Yes |
| 15.2.5 | Content truncated at max_length with truncated=True indicator | Yes |
| 15.2.6 | Non-HTML content (PDF, images) handled gracefully with error message | Yes |
| 15.2.7 | Error handling for blocked sites, timeouts (15s), invalid URLs | Yes |
| 15.2.8 | Unit tests with mocked responses achieve >80% coverage | Yes |
| 15.2.9 | Status summarizer displays "Reading webpage..." and "Page loaded (title)" | Yes |

### Story 15.3: Reddit Search Tool

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| 15.3.1 | PRAW integration with OAuth credentials (REDDIT_CLIENT_ID/SECRET) | Yes |
| 15.3.2 | JSON API fallback (reddit.com/search.json) when PRAW unavailable | Yes |
| 15.3.3 | Search posts by query with subreddit filtering | Yes |
| 15.3.4 | Sort options (relevance, hot, top, new) applied correctly | Yes |
| 15.3.5 | Time filter (hour, day, week, month, year, all) applied correctly | Yes |
| 15.3.6 | Top comments included when include_comments=True (max 5 per post) | Yes |
| 15.3.7 | Rate limiting handled gracefully (PRAW auto-handles, JSON API backoff) | Yes |
| 15.3.8 | Error handling for private subreddits, deleted content | Yes |
| 15.3.9 | Unit tests with mocked responses achieve >80% coverage | Yes |
| 15.3.10 | Status summarizer displays "Searching Reddit..." and "Found N posts" | Yes |

### Story 15.4: Update User Profile Tool

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| 15.4.1 | PUT request to agentic-memories /v1/profile/{category}/{field} | Yes |
| 15.4.2 | Category validated against allowed list (basics, preferences, goals, interests, background) | Yes |
| 15.4.3 | All value types supported (string, number, boolean, array) | Yes |
| 15.4.4 | Source field set to "llm_explicit" for audit trail | Yes |
| 15.4.5 | Handle 404 (profile not found) with clear error message | Yes |
| 15.4.6 | Handle 400 (invalid category/field) with validation error | Yes |
| 15.4.7 | Retry with exponential backoff for transient failures (5xx) | Yes |
| 15.4.8 | Unit tests with mocked responses achieve >80% coverage | Yes |
| 15.4.9 | Status summarizer displays "Updating profile..." and "Profile updated" | Yes |
| 15.4.10 | System prompt updated with usage guidance for profile updates | Yes |

### Story 15.5: Tool Registration & Integration Testing

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| 15.5.1 | All 4 tools registered in MCP server tool registry | Yes |
| 15.5.2 | All tools appear in `tools/list` JSON-RPC response | Yes |
| 15.5.3 | System prompt includes usage guidance for all 4 new tools | Yes |
| 15.5.4 | Status summarizers implemented for all 4 tools | Yes |
| 15.5.5 | Integration tests with live services (can be skipped with flag) | Yes |
| 15.5.6 | End-to-end test via /api/chat endpoint triggers tools correctly | Yes |

### Story 15.6: Environment Configuration & Documentation

| AC# | Acceptance Criteria | Testable |
|-----|---------------------|----------|
| 15.6.1 | All new env vars documented in env.example with descriptions | Yes |
| 15.6.2 | CLAUDE.md updated with tool descriptions and usage examples | Yes |
| 15.6.3 | Fallback behavior documented (when each fallback triggers) | Yes |
| 15.6.4 | Cost estimates documented (Tavily ~$0.001/search, others free) | Yes |
| 15.6.5 | Rate limit handling documented for each provider | Yes |

## Traceability Mapping

| AC | Spec Section | Component/API | Test Idea |
|----|--------------|---------------|-----------|
| 15.1.1 | APIs and Interfaces | `web_search_tool_handler`, Tavily API | Mock Tavily, verify API key header |
| 15.1.2 | Workflows/Sequencing | `web_search_tool_handler`, DDG | Force Tavily error, verify DDG called |
| 15.1.3 | Data Models | `WebSearchRequest.search_depth` | Test basic vs advanced parameter |
| 15.1.4 | Data Models | `include_domains`, `exclude_domains` | Verify domains filter applied |
| 15.1.5 | Data Models | `WebSearchRequest.max_results` | Test default (5) and custom values |
| 15.1.6 | Reliability | Error handling | Inject 429, timeout, network error |
| 15.1.7 | Test Strategy | pytest | Run coverage report |
| 15.1.8 | Observability | `WebSearchStatusSummarizer` | Verify SSE status events |
| 15.2.1 | Services/Modules | `web_crawl_tool_handler`, crawl4ai | Mock AsyncWebCrawler |
| 15.2.2 | Workflows/Sequencing | `web_crawl_tool_handler`, Jina | Force crawl4ai error, verify Jina |
| 15.2.3 | Data Models | `wait_for_js` parameter | Test JS rendering path |
| 15.2.4 | Data Models | `WebCrawlResponse.content` | Verify markdown output format |
| 15.2.5 | Data Models | `max_length`, `truncated` | Test truncation at boundary |
| 15.2.6 | Reliability | Error handling | Test PDF, image URLs |
| 15.2.7 | Reliability | Error handling | Inject blocked, timeout, invalid URL |
| 15.2.8 | Test Strategy | pytest | Run coverage report |
| 15.2.9 | Observability | `WebCrawlStatusSummarizer` | Verify SSE status events |
| 15.3.1 | APIs and Interfaces | `reddit_search_tool_handler`, PRAW | Mock PRAW client |
| 15.3.2 | Workflows/Sequencing | JSON API fallback | No credentials, verify JSON API |
| 15.3.3 | Data Models | `query`, `subreddit` | Test specific subreddit filtering |
| 15.3.4-5 | Data Models | `sort`, `time_filter` | Verify parameters passed |
| 15.3.6 | Data Models | `include_comments` | Test with/without comments |
| 15.3.7 | Reliability | Rate limiting | PRAW handles, verify JSON backoff |
| 15.3.8 | Reliability | Error handling | Test private sub, deleted content |
| 15.3.9 | Test Strategy | pytest | Run coverage report |
| 15.3.10 | Observability | `RedditSearchStatusSummarizer` | Verify SSE status events |
| 15.4.1 | APIs and Interfaces | `update_user_profile_tool_handler` | Mock agentic-memories PUT |
| 15.4.2 | Data Models | Category validation | Test invalid category rejected |
| 15.4.3 | Data Models | Value types | Test string, number, bool, array |
| 15.4.4 | Security | Audit trail | Verify source="llm_explicit" in request |
| 15.4.5-6 | Reliability | HTTP error handling | Mock 404, 400 responses |
| 15.4.7 | Reliability | Retry logic | Mock 503, verify backoff |
| 15.4.8 | Test Strategy | pytest | Run coverage report |
| 15.4.9 | Observability | `ProfileUpdateStatusSummarizer` | Verify SSE status events |
| 15.4.10 | Detailed Design | System prompt | Review prompt includes tool guidance |
| 15.5.1-2 | Services/Modules | MCP Server registry | Test tools/list response |
| 15.5.3-4 | Observability | prompts.py, status_summarizers.py | Review code, test status events |
| 15.5.5-6 | Test Strategy | Integration tests | E2E test with live/mocked services |
| 15.6.1-5 | Dependencies | env.example, CLAUDE.md | Documentation review |

## Risks, Assumptions, Open Questions

### Risks

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| **R1**: Tavily API rate limits exceeded | Medium | Low | DuckDuckGo fallback, usage monitoring, upgrade to paid plan if needed |
| **R2**: Reddit API changes/deprecation | Medium | Low | JSON API as backup, version pinning, monitor Reddit changelog |
| **R3**: crawl4ai fails on complex JS sites | Medium | Medium | Jina Reader fallback, document limitations |
| **R4**: Profile API not available in agentic-memories | High | Low | Verify API exists before implementation, coordinate with agentic-memories team |
| **R5**: Large crawled content exceeds LLM context | Low | Medium | Strict max_length limit, truncation indicator |
| **R6**: Cost overrun on Tavily (high usage) | Low | Low | Monitor usage, set alerts, DDG fallback is free |

### Assumptions

| # | Assumption | Validation |
|---|------------|------------|
| **A1** | Tavily free tier (1000 requests/month) is sufficient for development | Monitor usage during sprint |
| **A2** | agentic-memories has /v1/profile/{category}/{field} PUT endpoint | Verify API contract before Story 15.4 |
| **A3** | crawl4ai works in Docker container environment | Test in Docker during Story 15.2 |
| **A4** | PRAW OAuth flow works in long-running service | Test OAuth refresh during Story 15.3 |
| **A5** | Reddit JSON API is stable enough for fallback | Has been stable for years, low risk |
| **A6** | Jina Reader free tier has sufficient capacity | Fallback only, low usage expected |

### Open Questions

| # | Question | Owner | Due |
|---|----------|-------|-----|
| **Q1** | Should we cache web search results? If yes, what TTL? | Dev | Before Story 15.1 |
| **Q2** | What's the max reasonable comment depth for Reddit posts? | Dev | Before Story 15.3 |
| **Q3** | Should profile updates require user confirmation first? | PM | Before Story 15.4 |
| **Q4** | Are there any profile fields that should be read-only (not LLM-updatable)? | PM | Before Story 15.4 |
| **Q5** | Should we add HackerNews, Twitter/X in this epic or defer? | PM | Before Story 15.6 |

## Test Strategy Summary

### Test Levels

| Level | Scope | Framework | Coverage Target |
|-------|-------|-----------|-----------------|
| Unit Tests | Individual tool handlers | pytest, pytest-asyncio | >80% |
| Integration Tests | Tool + External API | pytest with mocks | Key paths |
| E2E Tests | Chat endpoint -> Tool -> Response | pytest | Happy path + errors |

### Test Categories by Story

**Story 15.1 (web_search):**
- Unit: Mock Tavily API responses, test DDG fallback trigger
- Integration: Live Tavily call (skippable)
- Edge cases: Rate limit handling, empty results, timeout

**Story 15.2 (web_crawl):**
- Unit: Mock crawl4ai responses, test Jina fallback trigger
- Integration: Live crawl of test URL (skippable)
- Edge cases: JS-heavy sites, non-HTML content, very long pages

**Story 15.3 (reddit_search):**
- Unit: Mock PRAW responses, test JSON API fallback
- Integration: Live Reddit call (skippable)
- Edge cases: Private subreddits, deleted posts, rate limits

**Story 15.4 (update_user_profile):**
- Unit: Mock agentic-memories API responses
- Integration: Live profile update (skippable)
- Edge cases: Invalid category, 404 not found, retry logic

**Story 15.5 (registration):**
- Unit: Verify tool registration
- Integration: E2E chat flow with tool calls
- Edge cases: Multiple tool calls in sequence

### Test Fixtures

```python
# Shared test fixtures
@pytest.fixture
def mock_tavily_response():
    return {
        "results": [
            {"title": "Test", "url": "https://example.com", "snippet": "..."}
        ]
    }

@pytest.fixture
def mock_reddit_post():
    return {
        "title": "Test Post",
        "subreddit": "test",
        "score": 100,
        "comments": []
    }

@pytest.fixture
def mock_crawl_result():
    return {
        "markdown": "# Page Title\n\nContent...",
        "metadata": {"title": "Page Title"}
    }
```

### Coverage Requirements

- All tool handlers: >80% line coverage
- Error handling paths: 100% coverage
- Fallback logic: 100% coverage
- Status summarizers: >70% coverage

### CI/CD Integration

- Unit tests run on every PR
- Integration tests run with `--run-integration` flag
- Live service tests skipped by default (require API keys)
- Coverage report generated and tracked
