# Epic: Extended MCP Tools - Web & Profile

> **Epic ID**: 15
> **Status**: Draft
> **Priority**: High
> **Estimated Effort**: 8-12 days
> **Dependencies**: Tavily API, Reddit API (optional), agentic-memories profile API

---

## 1. Overview

### 1.1 Problem Statement

Annie currently has limited external information gathering capabilities:
- **Web Search**: Only Grok-4 Live Search (expensive, provider-locked)
- **Web Crawling**: No ability to fetch full page content from URLs
- **Reddit Access**: No ability to search Reddit for community insights, discussions, or reviews
- **Profile Updates**: No way for the LLM to directly update user profile fields

### 1.2 Solution

Add four new MCP tools to extend Annie's capabilities:

1. **`web_search`** - Search the web using Tavily (primary) with DuckDuckGo fallback
2. **`web_crawl`** - Fetch and parse full webpage content from URLs
3. **`reddit_search`** - Search Reddit subreddits, threads, and comments
4. **`update_user_profile`** - Update specific user profile fields via agentic-memories

### 1.3 Success Criteria

| Metric | Target |
|--------|--------|
| `web_search` latency p95 | <3s |
| `web_crawl` latency p95 | <5s |
| `reddit_search` latency p95 | <4s |
| `update_user_profile` latency p95 | <1s |
| Tool success rate | >98% |
| Cost per web search | <$0.01 (Tavily) |

---

## 2. Architecture

### 2.1 Web Search Flow

```
LLM → web_search tool → MCP Server → Tavily API
                                        ↓
                              Search Results (1-2s)
                              - Title, URL, snippet
                              - Optional: full content
                              ↓
                        [On Failure] → DuckDuckGo API (fallback)
```

### 2.2 Web Crawl Flow

```
LLM → web_crawl tool → MCP Server → crawl4ai (local)
                                        ↓
                              Full Page Content (2-4s)
                              - JavaScript rendering
                              - Clean markdown output
                              - Metadata extraction
                              ↓
                        [On Failure] → Jina Reader API (fallback)
```

### 2.3 Reddit Search Flow

```
LLM → reddit_search tool → MCP Server → PRAW (Reddit API)
                                              ↓
                                    Search Results (2-3s)
                                    - Subreddit posts
                                    - Thread content + comments
                                    - User context
                                              ↓
                                    [On Failure] → JSON API fallback
```

### 2.4 Profile Update Flow

```
LLM → update_user_profile tool → MCP Server → PUT /v1/profile/{category}/{field}
                                                      ↓
                                            agentic-memories (<500ms)
                                            - Validate category
                                            - Update field value
                                            - Set confidence to 100%
```

---

## 3. Stories

### Story 15.1: Web Search Tool (Tavily + DuckDuckGo)

**Priority**: P0
**Estimate**: 1 day

Implement `web_search` tool with Tavily as primary provider and DuckDuckGo as fallback.

**File**: `mcp_server/tools.py`

**Schema**:
```python
{
    "name": "web_search",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum results to return (default: 5, max: 10)",
                "default": 5
            },
            "search_depth": {
                "type": "string",
                "enum": ["basic", "advanced"],
                "description": "basic (faster, cheaper) or advanced (deeper, more expensive)",
                "default": "basic"
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Only include results from these domains"
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Exclude results from these domains"
            }
        },
        "required": ["query"]
    }
}
```

**Response**:
```python
{
    "status": "success",
    "provider": "tavily",  # or "duckduckgo"
    "results": [
        {
            "title": "...",
            "url": "...",
            "snippet": "...",
            "score": 0.95  # relevance score if available
        }
    ],
    "query": "original query"
}
```

**Acceptance Criteria**:
- [ ] Tavily API integration with API key from env
- [ ] DuckDuckGo fallback on Tavily failure
- [ ] Search depth options (basic/advanced)
- [ ] Domain filtering (include/exclude)
- [ ] Results limited to max_results
- [ ] Error handling for rate limits, timeouts
- [ ] Unit tests with mocked responses
- [ ] Status summarizer for real-time updates

---

### Story 15.2: Web Crawl Tool (crawl4ai + Jina Fallback)

**Priority**: P0
**Estimate**: 1 day

Implement `web_crawl` tool to fetch and parse full webpage content using crawl4ai.

**File**: `mcp_server/tools.py`

**Schema**:
```python
{
    "name": "web_crawl",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "URL to crawl and extract content from"
            },
            "include_images": {
                "type": "boolean",
                "description": "Include image descriptions (default: false)",
                "default": false
            },
            "max_length": {
                "type": "integer",
                "description": "Maximum content length in characters (default: 10000)",
                "default": 10000
            },
            "wait_for_js": {
                "type": "boolean",
                "description": "Wait for JavaScript to render (slower but better for SPAs)",
                "default": false
            }
        },
        "required": ["url"]
    }
}
```

**Response**:
```python
{
    "status": "success",
    "provider": "crawl4ai",  # or "jina"
    "url": "...",
    "title": "Page Title",
    "content": "Cleaned markdown content...",
    "metadata": {
        "description": "...",
        "author": "...",
        "published_date": "...",
        "links_count": 42
    },
    "truncated": false  # true if content exceeded max_length
}
```

**Implementation Notes**:
```python
from crawl4ai import AsyncWebCrawler

async with AsyncWebCrawler() as crawler:
    result = await crawler.arun(url=url)
    # result.markdown - clean markdown content
    # result.metadata - page metadata
```

**Acceptance Criteria**:
- [ ] crawl4ai integration (primary)
- [ ] Fallback to Jina Reader (`https://r.jina.ai/{url}`)
- [ ] JavaScript rendering option (wait_for_js)
- [ ] Clean markdown output
- [ ] Length limiting with truncation indicator
- [ ] Handle non-HTML content gracefully
- [ ] Error handling for blocked sites, timeouts
- [ ] Unit tests with mocked responses
- [ ] Status summarizer

---

### Story 15.3: Reddit Search Tool

**Priority**: P1
**Estimate**: 2 days

Implement `reddit_search` tool for searching subreddits, posts, and comments.

**File**: `mcp_server/tools.py`

**Schema**:
```python
{
    "name": "reddit_search",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Search query"
            },
            "subreddit": {
                "type": "string",
                "description": "Limit search to specific subreddit (without r/ prefix)"
            },
            "search_type": {
                "type": "string",
                "enum": ["posts", "comments", "subreddits"],
                "description": "Type of content to search",
                "default": "posts"
            },
            "sort": {
                "type": "string",
                "enum": ["relevance", "hot", "top", "new"],
                "description": "Sort order for results",
                "default": "relevance"
            },
            "time_filter": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year", "all"],
                "description": "Time filter for results",
                "default": "all"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 10, max: 25)",
                "default": 10
            },
            "include_comments": {
                "type": "boolean",
                "description": "Include top comments for posts (default: true)",
                "default": true
            }
        },
        "required": ["query"]
    }
}
```

**Response**:
```python
{
    "status": "success",
    "query": "...",
    "subreddit": "all",  # or specific subreddit
    "results": [
        {
            "type": "post",
            "title": "...",
            "subreddit": "r/...",
            "author": "u/...",
            "score": 1234,
            "url": "...",
            "selftext": "...",  # post content if text post
            "comments": [
                {
                    "author": "u/...",
                    "score": 567,
                    "body": "...",
                    "replies_count": 12
                }
            ]
        }
    ]
}
```

**Implementation** (PRAW):
```python
import praw

reddit = praw.Reddit(
    client_id=os.getenv("REDDIT_CLIENT_ID"),
    client_secret=os.getenv("REDDIT_CLIENT_SECRET"),
    user_agent="annie-bot/1.0"
)

# Search posts
for submission in reddit.subreddit("all").search(query, limit=10):
    # submission.title, submission.selftext, submission.score
    # submission.comments.list() for top comments
```

**Fallback** (JSON API - no auth):
```python
import httpx
response = await httpx.get(f"https://www.reddit.com/search.json?q={query}&limit=10")
```

**Acceptance Criteria**:
- [ ] PRAW integration with OAuth credentials
- [ ] Fallback to JSON API on auth failure
- [ ] Search posts by query
- [ ] Filter by subreddit
- [ ] Sort options (relevance, hot, top, new)
- [ ] Time filter support
- [ ] Include top comments with posts (configurable depth)
- [ ] Handle rate limiting gracefully (PRAW handles this)
- [ ] Error handling for private subreddits, deleted content
- [ ] Unit tests with mocked responses
- [ ] Status summarizer

---

### Story 15.4: Update User Profile Tool

**Priority**: P0
**Estimate**: 0.5 days

Implement `update_user_profile` tool using agentic-memories profile API.

**File**: `mcp_server/tools.py`

**Schema**:
```python
{
    "name": "update_user_profile",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "category": {
                "type": "string",
                "enum": ["basics", "preferences", "goals", "interests", "background"],
                "description": "Profile category to update"
            },
            "field_name": {
                "type": "string",
                "description": "Field name within the category"
            },
            "value": {
                "description": "New value for the field (string, number, boolean, or array)"
            },
            "reason": {
                "type": "string",
                "description": "Reason for the update (for audit trail)"
            }
        },
        "required": ["user_id", "category", "field_name", "value"]
    }
}
```

**API Contract** (agentic-memories):
```
PUT /v1/profile/{category}/{field_name}
Body: {
    "user_id": string,
    "value": any,
    "source": "llm_explicit"  # Distinguish from manual updates
}

Response: {
    "user_id": string,
    "category": string,
    "field_name": string,
    "value": any,
    "confidence": 100.0,
    "last_updated": ISO timestamp
}
```

**Profile Categories & Common Fields**:
- **basics**: name, age, location, occupation, timezone
- **preferences**: communication_style, topics_of_interest, response_length
- **goals**: short_term, long_term, current_focus
- **interests**: hobbies, favorite_topics, dislikes
- **background**: education, work_history, family

**Acceptance Criteria**:
- [ ] PUT to agentic-memories profile API
- [ ] Validate category against allowed list
- [ ] Support all value types (string, number, boolean, array)
- [ ] Set source to "llm_explicit" for audit trail
- [ ] Handle 404 (profile not found - create first)
- [ ] Handle 400 (invalid category/field)
- [ ] Error handling with retry for transient failures
- [ ] Unit tests with mocked responses
- [ ] Status summarizer
- [ ] Update system prompt with usage guidance

---

### Story 15.5: Tool Registration & Integration Testing

**Priority**: P0
**Estimate**: 1 day

Register all new tools and write integration tests.

**Files**:
- `mcp_server/server.py` - Tool registration
- `mcp_server/tests/test_web_search_tool.py`
- `mcp_server/tests/test_web_crawl_tool.py`
- `mcp_server/tests/test_reddit_search_tool.py`
- `mcp_server/tests/test_update_profile_tool.py`
- `backend/api/prompts.py` - System prompt updates
- `backend/api/status_summarizers.py` - Status summarizers

**Acceptance Criteria**:
- [ ] All 4 tools registered in MCP server
- [ ] Tools appear in `tools/list` response
- [ ] System prompt includes usage guidance for all tools
- [ ] Status summarizers for real-time updates
- [ ] Integration tests with live services (skippable)
- [ ] End-to-end test via chat endpoint

---

### Story 15.6: Environment Configuration & Documentation

**Priority**: P1
**Estimate**: 0.5 days

Add environment variables and documentation for new tools.

**Files**:
- `env.example` - New API keys
- `CLAUDE.md` - Tool documentation
- `README.md` - Setup instructions

**New Environment Variables**:
```bash
# Web Search
TAVILY_API_KEY=tvly-...           # Required for web_search and web_crawl
DUCKDUCKGO_ENABLED=true           # Enable DDG fallback (default: true)

# Reddit (choose one approach)
REDDIT_CLIENT_ID=...              # For official API
REDDIT_CLIENT_SECRET=...
REDDIT_USER_AGENT=annie-bot/1.0

# Optional
JINA_API_KEY=...                  # For Jina Reader fallback
FIRECRAWL_API_KEY=...             # For Firecrawl fallback
```

**Acceptance Criteria**:
- [ ] All env vars documented in env.example
- [ ] CLAUDE.md updated with tool descriptions
- [ ] Fallback behavior documented
- [ ] Cost estimates documented
- [ ] Rate limit handling documented

---

## 4. Technical Considerations

### 4.1 API Providers

| Tool | Primary | Fallback | Cost |
|------|---------|----------|------|
| web_search | Tavily ($0.001/search) | duckduckgo-search (free) | ~$0.001 |
| web_crawl | crawl4ai (free, local) | Jina Reader (free) | **Free** |
| reddit_search | PRAW (free, OAuth) | JSON API (free, no auth) | **Free** |
| update_user_profile | agentic-memories | N/A | **Free** |

### 4.2 Rate Limits

- **Tavily**: 1000 requests/month (free), higher on paid
- **DuckDuckGo**: ~1 request/second recommended
- **PRAW/Reddit**: 60 requests/minute (OAuth), PRAW handles rate limiting automatically
- **crawl4ai**: No limit (local), but be respectful of target sites
- **agentic-memories**: No limit (self-hosted)

### 4.3 Error Handling Strategy

1. **Retry with backoff** for transient errors (5xx, timeouts)
2. **Fallback to secondary provider** on primary failure
3. **Return partial results** if some sources succeed
4. **Clear error messages** for user-facing failures

---

## 5. Dependencies

### 5.1 External Services

- **Tavily API**: Sign up at https://tavily.com
- **Reddit**: Either register an OAuth app or use JSON API
- **agentic-memories**: Must be running with profile API enabled

### 5.2 Python Packages

```
tavily-python>=0.3.0
duckduckgo-search>=6.0.0
crawl4ai>=0.3.0
praw>=7.7.0  # If using official Reddit API (optional)
```

---

## 6. Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Tavily API rate limits | Medium | DuckDuckGo fallback, caching |
| Reddit API changes | Medium | JSON API as backup, version pinning |
| Content extraction failures | Low | Multiple fallback providers |
| Profile API unavailable | Low | Retry with backoff, graceful degradation |

---

## 7. Success Metrics

Post-implementation monitoring:

1. **Tool Usage**: Track which tools are called most frequently
2. **Success Rate**: Monitor failures by tool and error type
3. **Latency**: P50, P95, P99 latency per tool
4. **Cost**: Monthly API costs for web tools
5. **User Satisfaction**: Quality of search/crawl results

---

## 8. Future Considerations

- **Caching**: Cache web search results for common queries
- **Semantic Search**: Use embeddings to rank results
- **More Sources**: Add Twitter/X, HackerNews, StackOverflow
- **Bulk Operations**: Batch profile updates
