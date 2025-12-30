# Story 15.3: Reddit Search Tool (PRAW + JSON API)

**Status:** done
**Priority:** P1
**Estimated Effort:** 2 days
**Prerequisites:** Reddit OAuth credentials (optional - fallback to JSON API)

---

## Story

**As a** user of Annie,
**I want** Annie to search Reddit for community discussions and opinions,
**So that** she can provide insights from real user experiences and discussions.

**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Tech Spec Reference:** `.bmad-ephemeral/stories/tech-spec-epic-15.md` (AC 15.3.1-15.3.10)

## Acceptance Criteria

### AC #1: PRAW Integration (Tech Spec 15.3.1)
**Given** the reddit_search tool is called
**When** REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET are configured
**Then** the tool uses PRAW with OAuth for authenticated Reddit access

**Mapped to Tasks:** Task 1

---

### AC #2: JSON API Fallback (Tech Spec 15.3.2)
**Given** the reddit_search tool is called
**When** PRAW is unavailable (no credentials or OAuth failure)
**Then** the tool falls back to Reddit's public JSON API (`https://www.reddit.com/search.json`)

**Mapped to Tasks:** Task 2

---

### AC #3: Search Posts with Subreddit Filtering (Tech Spec 15.3.3)
**Given** the reddit_search tool is called with a query
**When** subreddit parameter is provided
**Then** search is limited to that subreddit; otherwise searches all of Reddit ("all")

**Mapped to Tasks:** Task 1, Task 2

---

### AC #4: Sort Options (Tech Spec 15.3.4)
**Given** the reddit_search tool is called with sort parameter
**When** sort is "relevance", "hot", "top", or "new"
**Then** results are sorted accordingly (default: "relevance")

**Mapped to Tasks:** Task 1, Task 2

---

### AC #5: Time Filter (Tech Spec 15.3.5)
**Given** the reddit_search tool is called with time_filter parameter
**When** time_filter is "hour", "day", "week", "month", "year", or "all"
**Then** results are filtered to that time range (default: "all")

**Mapped to Tasks:** Task 1, Task 2

---

### AC #6: Include Comments (Tech Spec 15.3.6)
**Given** the reddit_search tool is called with include_comments=True
**When** posts are returned
**Then** top 5 comments per post are included (each truncated to 500 chars)

**Note:** JSON API fallback cannot include comments - only PRAW supports this feature.

**Mapped to Tasks:** Task 1

---

### AC #7: Rate Limiting (Tech Spec 15.3.7)
**Given** the reddit_search tool makes API requests
**When** rate limits are encountered
**Then** PRAW auto-handles rate limits (60 req/min); JSON API uses exponential backoff

**Mapped to Tasks:** Task 1, Task 2

---

### AC #8: Error Handling (Tech Spec 15.3.8)
**Given** the reddit_search tool encounters an error
**When** private subreddit or deleted content is accessed
**Then** appropriate error handling returns clear messages with error codes

**Error Cases:**
- Private subreddit: Return `{"status": "error", "error_message": "Subreddit is private"}`
- Deleted content: Filter out deleted posts/comments gracefully
- Rate limited: Retry with backoff, fallback to JSON API if persistent
- Network timeout: Return `{"status": "error", "error_message": "Request timed out"}`

**Mapped to Tasks:** Task 1, Task 2

---

### AC #9: Unit Tests (Tech Spec 15.3.9)
**Given** the reddit_search tool implementation
**When** tests are run
**Then** mocked PRAW/JSON API responses achieve >80% coverage

**Coverage Requirements:**
- All parameters tested (query, subreddit, sort, time_filter, limit, include_comments)
- Both PRAW and JSON API paths covered
- Fallback trigger conditions tested
- Error handling paths covered

**Mapped to Tasks:** Task 3

---

### AC #10: Status Summarizer (Tech Spec 15.3.10)
**Given** the reddit_search tool is executing
**When** the tool starts and completes
**Then** status updates are emitted via SSE:
- Start: "Searching Reddit..."
- Complete: "Found N posts" or "Found N posts in r/{subreddit}"

**Mapped to Tasks:** Task 4

---

## MCP Tool Schema

The `reddit_search` tool must be registered with this schema in the MCP server:

```json
{
    "name": "reddit_search",
    "description": "Search Reddit for posts, comments, and community discussions. Useful for finding real user experiences, reviews, and opinions on topics.",
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
                "description": "Type of content to search (default: posts)",
                "default": "posts"
            },
            "sort": {
                "type": "string",
                "enum": ["relevance", "hot", "top", "new"],
                "description": "Sort order for results (default: relevance)",
                "default": "relevance"
            },
            "time_filter": {
                "type": "string",
                "enum": ["hour", "day", "week", "month", "year", "all"],
                "description": "Time filter for results (default: all)",
                "default": "all"
            },
            "limit": {
                "type": "integer",
                "description": "Maximum results (default: 10, max: 25)",
                "default": 10,
                "minimum": 1,
                "maximum": 25
            },
            "include_comments": {
                "type": "boolean",
                "description": "Include top comments for posts (default: true, PRAW only)",
                "default": true
            }
        },
        "required": ["query"]
    }
}
```

---

## Tasks / Subtasks

### Task 1: Implement PRAW Primary Provider
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #3, AC #4, AC #5, AC #6, AC #7, AC #8

**Implementation Details:**

Add `reddit_search_tool_handler` to `mcp_server/tools.py`:

```python
import praw

async def reddit_search_tool_handler(
    query: str,
    subreddit: str = None,
    search_type: str = "posts",
    sort: str = "relevance",
    time_filter: str = "all",
    limit: int = 10,
    include_comments: bool = True
) -> Dict[str, Any]:
    """Search Reddit using PRAW with JSON API fallback."""
    start_time = time.time()

    config = get_config()
    client_id = config.get("REDDIT_CLIENT_ID")
    client_secret = config.get("REDDIT_CLIENT_SECRET")

    if client_id and client_secret:
        try:
            return await _praw_search(
                query, subreddit, search_type, sort,
                time_filter, limit, include_comments,
                client_id, client_secret
            )
        except Exception as e:
            logger.warning(f"PRAW search failed: {e}, falling back to JSON API")

    # Fallback to JSON API (no auth required)
    return await _reddit_json_search(query, subreddit, sort, time_filter, limit)

def _praw_search(...) -> Dict[str, Any]:
    """Search Reddit using PRAW (synchronous, wrapped in thread)."""
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=config.get("REDDIT_USER_AGENT", "annie-bot/1.0")
    )

    sub = reddit.subreddit(subreddit if subreddit else "all")

    results = []
    for submission in sub.search(query, sort=sort, time_filter=time_filter, limit=limit):
        post = {
            "type": "post",
            "title": submission.title,
            "subreddit": f"r/{submission.subreddit.display_name}",
            "author": f"u/{submission.author.name}" if submission.author else "[deleted]",
            "score": submission.score,
            "url": f"https://reddit.com{submission.permalink}",
            "selftext": submission.selftext[:1000] if submission.selftext else None,
            "comments": []
        }

        if include_comments:
            submission.comments.replace_more(limit=0)
            for comment in submission.comments[:5]:
                post["comments"].append({
                    "author": f"u/{comment.author.name}" if comment.author else "[deleted]",
                    "score": comment.score,
                    "body": comment.body[:500],
                    "replies_count": len(comment.replies)
                })

        results.append(post)

    return {
        "status": "success",
        "provider": "praw",
        "query": query,
        "subreddit": subreddit or "all",
        "results": results
    }
```

**Subtasks:**
- [ ] Add `praw>=7.7.0` to `mcp_server/requirements.txt`
- [ ] Add REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT to `mcp_server/config.py`
- [ ] Implement `reddit_search_tool_handler` main entry point
- [ ] Implement `_praw_search()` helper function
- [ ] Handle subreddit filtering (None = "all")
- [ ] Implement sort options (relevance, hot, top, new)
- [ ] Implement time_filter options (hour, day, week, month, year, all)
- [ ] Implement include_comments with `submission.comments.replace_more(limit=0)` and limit to 5 comments
- [ ] Truncate comment body to 500 characters
- [ ] Truncate post selftext to 1000 characters
- [ ] Handle private subreddits gracefully with clear error message
- [ ] Handle deleted content gracefully (filter out `[deleted]` authors)
- [ ] Add logging with `event="reddit_search.started"` and `event="reddit_search.completed"`

---

### Task 2: Implement JSON API Fallback
**Status:** TODO
**Acceptance Criteria:** AC #2, AC #3, AC #4, AC #5, AC #7, AC #8

**Implementation Details:**

```python
async def _reddit_json_search(
    query: str,
    subreddit: str,
    sort: str,
    time_filter: str,
    limit: int
) -> Dict[str, Any]:
    """Search Reddit using public JSON API as fallback."""
    try:
        base_url = "https://www.reddit.com"
        if subreddit:
            url = f"{base_url}/r/{subreddit}/search.json"
        else:
            url = f"{base_url}/search.json"

        params = {
            "q": query,
            "sort": sort,
            "t": time_filter,
            "limit": min(limit, 25),
            "restrict_sr": "on" if subreddit else "off"
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                url,
                params=params,
                headers={"User-Agent": "annie-bot/1.0"},
                follow_redirects=True
            )

            if response.status_code == 429:
                # Rate limited - wait and retry
                await asyncio.sleep(2)
                response = await client.get(url, params=params, headers=headers)

            if response.status_code != 200:
                return {
                    "status": "error",
                    "provider": "json_api",
                    "query": query,
                    "error_message": f"HTTP {response.status_code}"
                }

            data = response.json()
            results = []

            for post_data in data.get("data", {}).get("children", []):
                post = post_data.get("data", {})
                results.append({
                    "type": "post",
                    "title": post.get("title"),
                    "subreddit": f"r/{post.get('subreddit')}",
                    "author": f"u/{post.get('author', '[deleted]')}",
                    "score": post.get("score", 0),
                    "url": f"https://reddit.com{post.get('permalink')}",
                    "selftext": post.get("selftext", "")[:1000],
                    "comments": []  # JSON API doesn't include comments in search
                })

            return {
                "status": "success",
                "provider": "json_api",
                "query": query,
                "subreddit": subreddit or "all",
                "results": results
            }
    except Exception as e:
        return {
            "status": "error",
            "provider": "json_api",
            "query": query,
            "error_message": str(e)
        }
```

**Subtasks:**
- [ ] Implement `_reddit_json_search()` async function
- [ ] Build URL correctly for subreddit filtering (`/r/{subreddit}/search.json` vs `/search.json`)
- [ ] Map sort and time_filter to `sort` and `t` query parameters
- [ ] Set `restrict_sr=on` when searching specific subreddit
- [ ] Implement rate limiting with exponential backoff (1s, 2s, 4s retry on 429)
- [ ] Set proper User-Agent header (`annie-bot/1.0`)
- [ ] Handle HTTP errors gracefully (4xx, 5xx)
- [ ] Handle JSON parse errors gracefully
- [ ] Parse Reddit JSON response format (`data.children[].data`)
- [ ] Return empty comments array (JSON API limitation - document this clearly)
- [ ] Set 15 second timeout for HTTP requests
- [ ] Log fallback activation with `event="reddit_search.fallback"`

---

### Task 3: Unit Tests
**Status:** TODO
**Acceptance Criteria:** AC #9

**Implementation Details:**

Create `mcp_server/tests/test_reddit_search_tool.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

@pytest.fixture
def mock_praw_submission():
    submission = MagicMock()
    submission.title = "Test Post"
    submission.subreddit.display_name = "test"
    submission.author.name = "testuser"
    submission.score = 100
    submission.permalink = "/r/test/comments/abc123/test_post"
    submission.selftext = "Post content..."
    submission.comments = MagicMock()
    submission.comments.replace_more = MagicMock()
    submission.comments.__iter__ = lambda self: iter([])
    return submission

@pytest.mark.asyncio
async def test_praw_search_success(mock_praw_submission):
    with patch("praw.Reddit") as mock_reddit:
        mock_reddit.return_value.subreddit.return_value.search.return_value = [mock_praw_submission]
        # Test implementation...

@pytest.mark.asyncio
async def test_fallback_to_json_api():
    # No credentials, verify JSON API called
    pass

@pytest.mark.asyncio
async def test_subreddit_filtering():
    # Test specific subreddit search
    pass

@pytest.mark.asyncio
async def test_include_comments():
    # Test comment inclusion
    pass
```

**Subtasks:**
- [ ] Create `mcp_server/tests/test_reddit_search_tool.py`
- [ ] Create `mock_praw_submission` fixture with realistic data
- [ ] Create `mock_praw_comment` fixture
- [ ] Create `mock_json_api_response` fixture
- [ ] Test PRAW success path with mocked Reddit client
- [ ] Test PRAW failure triggers JSON API fallback (mock exception)
- [ ] Test fallback when no credentials configured (mock config)
- [ ] Test subreddit filtering for both providers
- [ ] Test all sort options (relevance, hot, top, new)
- [ ] Test all time_filter options (hour, day, week, month, year, all)
- [ ] Test include_comments=True returns comments (PRAW)
- [ ] Test include_comments=False excludes comments
- [ ] Test limit parameter (default 10, max 25)
- [ ] Test rate limiting handling (mock 429 response)
- [ ] Test private subreddit error handling
- [ ] Test deleted content filtering
- [ ] Test timeout handling
- [ ] Run coverage report: `pytest --cov=mcp_server.tools --cov-report=term-missing`
- [ ] Achieve >80% coverage on reddit_search functions

---

### Task 4: Status Summarizer
**Status:** TODO
**Acceptance Criteria:** AC #10

**Implementation Details:**

Add to `backend/api/status_summarizers.py`:

```python
def reddit_search_summarizer(tool_name: str, tool_args: Dict, result: Dict) -> str:
    """Generate status summary for reddit_search tool."""
    if result.get("status") == "success":
        count = len(result.get("results", []))
        subreddit = result.get("subreddit", "all")
        if subreddit != "all":
            return f"Found {count} post{'s' if count != 1 else ''} in r/{subreddit}"
        return f"Found {count} post{'s' if count != 1 else ''}"
    else:
        return "Reddit search failed"

# Register in TOOL_SUMMARIZERS
TOOL_SUMMARIZERS["reddit_search"] = reddit_search_summarizer
```

**Subtasks:**
- [ ] Implement `summarize_reddit_search_result()` function in `backend/api/status_summarizers.py`
- [ ] Handle success case: "Found N posts" or "Found N posts in r/{subreddit}"
- [ ] Handle error case: Return error message (truncated to 500 chars)
- [ ] Handle edge case: "No posts found" when results empty
- [ ] Register in `SUMMARIZERS` dict with key `"reddit_search"`
- [ ] Test summarizer with various result shapes

**Note:** The "Searching Reddit..." message is emitted by the stream handler before tool execution, not by the summarizer. The summarizer only handles completion status.

---

### Task 5: Tool Registration
**Status:** TODO
**Acceptance Criteria:** AC #1 (tool must be accessible)

**Implementation Details:**

Register the tool in `mcp_server/server.py` or the tool registry:

```python
# In tool registration section
{
    "name": "reddit_search",
    "description": "Search Reddit for posts, comments, and community discussions. Useful for finding real user experiences, reviews, and opinions on topics.",
    "inputSchema": { ... },  # See MCP Tool Schema section above
    "handler": reddit_search_tool_handler
}
```

**Subtasks:**
- [ ] Register `reddit_search` tool with schema in MCP server
- [ ] Verify tool appears in `tools/list` JSON-RPC response
- [ ] Update system prompt in `backend/api/prompts.py` with usage guidance
- [ ] Add example usage scenarios for the LLM

**System Prompt Addition (suggested):**
```
- reddit_search: Search Reddit for community discussions and real user experiences. Useful for product reviews, opinions, troubleshooting advice, and community sentiment on topics.
```

---

## Definition of Done

- [ ] **Tasks 1-5 completed** with all subtasks checked off
- [ ] **All 10 acceptance criteria validated** (mapped to tech spec 15.3.1-15.3.10)
- [ ] `reddit_search` tool registered in MCP server and appears in `tools/list`
- [ ] PRAW integration working with OAuth credentials (when configured)
- [ ] JSON API fallback working when PRAW unavailable (no credentials or failure)
- [ ] Subreddit filtering working for both providers
- [ ] Sort options (relevance, hot, top, new) working
- [ ] Time filter options (hour, day, week, month, year, all) working
- [ ] include_comments option working (max 5 comments, PRAW only)
- [ ] Rate limiting handled gracefully (PRAW auto, JSON API backoff)
- [ ] Error handling returning clear messages for all error cases
- [ ] Unit tests passing with >80% coverage
- [ ] Status summarizer registered and emitting correct updates
- [ ] System prompt updated with tool usage guidance
- [ ] Logging implemented with proper events and metadata
- [ ] No regressions in other MCP tools (run full test suite)
- [ ] Manual E2E test: Ask Annie "What do people think about X?" and verify Reddit tool is called

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **reddit_search tool** (`mcp_server/tools.py`): MCP tool for Reddit search
- **PRAW**: Primary Reddit API client (OAuth) - full-featured
- **JSON API**: Public Reddit API (no auth) - fallback with limitations

**Flow:**
```
LLM function call
    ↓
reddit_search_tool_handler
    ↓
Check: REDDIT_CLIENT_ID & REDDIT_CLIENT_SECRET configured?
    ├── YES → _praw_search() → Return results
    │              ↓ (on exception)
    │          _reddit_json_search() (fallback)
    └── NO  → _reddit_json_search() (direct)
```

### Technical Constraints

1. **PRAW (Primary Provider):**
   - Requires OAuth2 credentials (client_id, client_secret)
   - Rate limit: 60 requests/minute (auto-handled by PRAW)
   - Supports all Reddit features including comments
   - User agent required (e.g., `annie-bot/1.0 by /u/yourname`)
   - Script-type application (no user authorization needed)

2. **JSON API (Fallback):**
   - No authentication required
   - Unofficial but stable (used by many tools)
   - Rate limit: ~1 req/sec recommended (no official limit)
   - **Limitation:** Cannot fetch comments in search results
   - Requires custom User-Agent to avoid blocking

3. **Timeout Configuration:**
   - 15 seconds per request (httpx timeout)
   - PRAW may need additional time for OAuth token refresh on first request
   - MCP_TOOL_TIMEOUT (30s default) is the outer limit

4. **Content Truncation:**
   - Post selftext: 1000 characters max
   - Comment body: 500 characters max
   - Top-level comments: 5 per post max

5. **Reddit OAuth App Setup:**
   - Go to https://www.reddit.com/prefs/apps
   - Create "script" type application
   - Note: Redirect URI doesn't matter for script apps
   - Use client_id (below app name) and client_secret

### Dependencies

**Python Packages (add to `mcp_server/requirements.txt`):**
```
praw>=7.7.0          # Reddit API wrapper with OAuth support
```

**Existing Packages (already available):**
- `httpx>=0.24.0` - Async HTTP client for JSON API fallback

**Environment Variables (add to `env.example`):**
```bash
# Reddit Search (Story 15.3) - Optional, enables PRAW
REDDIT_CLIENT_ID=...              # From Reddit app preferences
REDDIT_CLIENT_SECRET=...          # From Reddit app preferences
REDDIT_USER_AGENT=annie-bot/1.0   # Optional, default provided
```

**Service Dependencies:**
- None (Reddit APIs are external, no local services needed)

### Key Files to Modify

**Files to Create/Modify:**
| File | Action | Description |
|------|--------|-------------|
| `mcp_server/tools.py` | Modify | Add `reddit_search_tool_handler`, `_praw_search`, `_reddit_json_search` |
| `mcp_server/requirements.txt` | Modify | Add `praw>=7.7.0` |
| `mcp_server/config.py` | Modify | Add `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT` |
| `mcp_server/server.py` | Modify | Register `reddit_search` tool with schema |
| `mcp_server/tests/test_reddit_search_tool.py` | Create | Unit tests for reddit search |
| `backend/api/status_summarizers.py` | Modify | Add `summarize_reddit_search_result` and register |
| `backend/api/prompts.py` | Modify | Add tool usage guidance to system prompt |
| `env.example` | Modify | Add `REDDIT_*` environment variables |

**Reference Files (read-only):**
- `.bmad-ephemeral/stories/tech-spec-epic-15.md` - Epic 15 technical specification (authoritative ACs)
- `docs/epics/epic-15-extended-mcp-tools.md` - Epic overview and schema
- `backend/api/status_summarizers.py` - Pattern reference for summarizer implementation
- `mcp_server/tools.py` - Pattern reference for existing tool implementations

### Testing Strategy

**Unit Tests (Required - Task 3):**
```bash
# Run tests
docker compose exec mcp-server python -m pytest tests/test_reddit_search_tool.py -v

# Run with coverage
docker compose exec mcp-server python -m pytest tests/test_reddit_search_tool.py --cov=. --cov-report=term-missing
```

**Test Cases:**
| Category | Test Case | Expected Result |
|----------|-----------|-----------------|
| PRAW Success | Valid query with credentials | Returns results with provider="praw" |
| Fallback | PRAW exception thrown | Falls back to JSON API, provider="json_api" |
| Fallback | No credentials configured | Uses JSON API directly |
| Parameters | subreddit="python" | Results only from r/python |
| Parameters | sort="top", time_filter="week" | Top posts from past week |
| Parameters | include_comments=True | Comments array populated (PRAW only) |
| Parameters | limit=25 | Returns max 25 results |
| Error | Private subreddit | Returns error with clear message |
| Error | Rate limited (429) | Retries with backoff or falls back |
| Error | Timeout | Returns error after 15s |

**Integration Tests (Optional - skippable):**
```bash
# Run with live API (requires credentials)
docker compose exec mcp-server python -m pytest tests/test_reddit_search_tool.py -v --run-integration
```

**Manual E2E Test:**
1. Start services: `make start`
2. Send message to Annie: "What do Redditors think about the new iPhone?"
3. Verify: Reddit tool is called, results are used in response

### Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Latency P95 | <4s | Langfuse trace duration |
| Success rate | >98% | Langfuse success/error ratio |
| Coverage | >80% | pytest --cov report |
| Cost | Free | Both PRAW and JSON API are free |

### Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| "invalid_grant" OAuth error | Check client_id/secret, regenerate if needed |
| 403 Forbidden on JSON API | Check User-Agent header is set |
| Empty results | Verify query spelling, try broader terms |
| Slow first request | PRAW OAuth token refresh, normal |
| Rate limited | PRAW handles automatically, JSON needs backoff |

---

## References

1. **Epic 15 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-15.md`)
   - AC 15.3.1-15.3.10 acceptance criteria (authoritative)
   - Data models and contracts
   - Test strategy

2. **Epic 15 Overview** (`docs/epics/epic-15-extended-mcp-tools.md`)
   - Story 15.3 details and schema
   - Architecture diagrams

3. **PRAW Documentation** (https://praw.readthedocs.io)
   - Reddit API client usage
   - OAuth setup guide
   - Rate limit handling

4. **Reddit JSON API** (https://www.reddit.com/dev/api)
   - Public API endpoints
   - Response format documentation

5. **Existing Tool Examples** (`mcp_server/tools.py`)
   - Pattern reference for tool implementation
   - Error handling patterns

6. **Status Summarizer Pattern** (`backend/api/status_summarizers.py`)
   - Summarizer implementation pattern
   - Registration in SUMMARIZERS dict

---

**Created:** 2025-12-30
**Last Updated:** 2025-12-30
**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Story:** 15.3 - Reddit Search Tool (PRAW + JSON API)
**Status:** backlog
**Author:** BMAD Story Workflow
