# Story 15.6: Environment Configuration & Documentation

Status: done

## Story

**As a** developer or operator,
**I want** clear documentation of new environment variables and tool configurations,
**So that** I can properly set up and maintain the extended MCP tools.

**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Prerequisites:** Stories 15.1-15.5 completed
**Estimated Effort:** 0.5 days

## Acceptance Criteria

### AC #1: Environment Variables in env.example (AC 15.6.1)
**Given** the env.example file
**When** a developer reviews it
**Then** all new environment variables are documented with:
  - Clear descriptions of each variable's purpose
  - Links to obtain API keys where applicable
  - Default values where applicable
  - Cost estimates in comments
  - Grouping under Epic 15 section

**Testable:** Verify env.example contains TAVILY_API_KEY, DUCKDUCKGO_ENABLED, JINA_API_KEY, REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT with descriptions

**Mapped to Tasks:** Task 1

---

### AC #2: CLAUDE.md Tool Documentation (AC 15.6.2)
**Given** the CLAUDE.md file
**When** Claude reads it for context
**Then** all 4 new tools are documented with:
  - Tool name and description
  - Complete input schema with all parameters
  - Usage examples showing when to use each tool
  - Provider information (primary and fallback)
  - Response format

**Testable:** Verify CLAUDE.md contains sections for web_search, web_crawl, reddit_search, update_user_profile with schemas and examples

**Mapped to Tasks:** Task 2

---

### AC #3: Fallback Behavior Documented (AC 15.6.3)
**Given** the documentation
**When** a developer reads it
**Then** fallback behavior for each tool is clearly explained:
  - What triggers fallback (error, rate limit, timeout, missing credentials)
  - Which provider is used as fallback
  - How fallback affects response (e.g., different fields, reduced features)

**Testable:** Verify CLAUDE.md contains fallback behavior table with trigger conditions for each tool

**Mapped to Tasks:** Task 2

---

### AC #4: Cost Estimates Documented (AC 15.6.4)
**Given** the documentation
**When** an operator reviews costs
**Then** cost estimates for each tool/provider are documented:
  - Tavily: ~$0.001/search, 1000 free requests/month
  - DuckDuckGo: Free (no API key required)
  - crawl4ai: Free (local library)
  - Jina Reader: Free tier available
  - PRAW/Reddit: Free (OAuth required)
  - Profile API: Free (self-hosted agentic-memories)

**Testable:** Verify cost information present in env.example comments and CLAUDE.md tables

**Mapped to Tasks:** Task 1, Task 2

---

### AC #5: Rate Limit Documentation (AC 15.6.5)
**Given** the documentation
**When** a developer reviews it
**Then** rate limits for each provider are documented:
  - Tavily: 1000/month (free tier)
  - DuckDuckGo: ~1 request/second recommended
  - PRAW: 60 requests/minute (auto-handled by PRAW)
  - Reddit JSON API: Unofficial, ~1/second
  - crawl4ai: No limit (local, but respect target sites)
  - Jina Reader: Variable (free tier limits)
  - agentic-memories: No limit (self-hosted)

**Testable:** Verify rate limit information present in CLAUDE.md

**Mapped to Tasks:** Task 2

---

### AC #6: Config.py Files Updated
**Given** the config.py files in mcp_server/ and backend/
**When** a developer reviews them
**Then** all new environment variables are loaded with:
  - Proper default values
  - Type validation where applicable
  - Optional vs required designation
  - Masked logging for sensitive values (API keys)

**Testable:** Verify config.py files load new env vars correctly

**Mapped to Tasks:** Task 4

---

## Tasks / Subtasks

### Task 1: Update env.example
**Status:** TODO
**Acceptance Criteria:** AC #1, AC #4

**Implementation Details:**

Add new environment variables to `env.example` under Epic 15 section:

```bash
# ============================================================================
# Epic 15: Extended MCP Tools
# ============================================================================
# These tools provide additional web access and profile management capabilities

# Web Search (Story 15.1)
# -----------------------
# Tavily API Key - Primary web search provider
# Get your API key from: https://tavily.com
# Cost: ~$0.001 per search, 1000 free requests/month
# Required: Yes (for web_search tool)
TAVILY_API_KEY=REPLACE_ME

# Enable DuckDuckGo fallback when Tavily fails (default: true)
# DuckDuckGo is free and requires no API key
# Set to "false" to disable fallback
DUCKDUCKGO_ENABLED=true

# Web Crawl (Story 15.2)
# ----------------------
# Jina Reader API Key - Fallback web crawler (optional)
# Get your API key from: https://jina.ai/reader
# Free tier available, key required for higher rate limits
# Primary provider (crawl4ai) is local and requires no key
# Required: No (optional fallback)
JINA_API_KEY=

# Reddit Search (Story 15.3)
# --------------------------
# Reddit OAuth credentials - Required for PRAW (official Reddit API)
# Create an app at: https://www.reddit.com/prefs/apps
# Select "script" as the app type
# Without these, the tool falls back to Reddit's JSON API (less reliable)
# Required: No (improves reliability but JSON API works without auth)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=

# Reddit User Agent - Identifies your app to Reddit (required for PRAW)
# Format: <platform>:<app ID>:<version> (by /u/<username>)
# Must be unique and descriptive per Reddit API rules
REDDIT_USER_AGENT=annie-bot/1.0 (by /u/your_username)
```

**Subtasks:**
- [ ] Add Epic 15 section header with description
- [ ] Add TAVILY_API_KEY with required status, cost, and link
- [ ] Add DUCKDUCKGO_ENABLED with default value (true)
- [ ] Add JINA_API_KEY (optional) with description and link
- [ ] Add REDDIT_CLIENT_ID with setup instructions and link
- [ ] Add REDDIT_CLIENT_SECRET with setup instructions
- [ ] Add REDDIT_USER_AGENT with format example
- [ ] Verify all variables are grouped under Epic 15 section
- [ ] Add cost estimates in comments for each provider
- [ ] Add rate limit notes where relevant

---

### Task 2: Update CLAUDE.md
**Status:** TODO
**Acceptance Criteria:** AC #2, AC #3, AC #4, AC #5

**Implementation Details:**

Add new section to `CLAUDE.md` after the "External Services" section:

```markdown
## Extended MCP Tools (Epic 15)

Annie has additional MCP tools for web access and profile management:

### Web Search Tool (`web_search`)
Search the web for current information using Tavily (primary) or DuckDuckGo (fallback).

**When to Use:**
- Current events, news, real-time data
- Product reviews, comparisons, prices
- Information that may have changed since knowledge cutoff
- Fact-checking or verification

**Providers:**
| Provider | Cost | Rate Limit | Notes |
|----------|------|------------|-------|
| Tavily | ~$0.001/search | 1000/month (free) | Primary, high quality |
| DuckDuckGo | Free | ~1 req/sec | Fallback on Tavily failure |

**Schema:**
```json
{
  "query": "string (required)",
  "max_results": "int (1-10, default 5)",
  "search_depth": "basic|advanced (default basic)",
  "include_domains": ["array of domains to whitelist"],
  "exclude_domains": ["array of domains to blacklist"]
}
```

**Response includes:** title, url, snippet, relevance score

---

### Web Crawl Tool (`web_crawl`)
Fetch and parse full webpage content using crawl4ai (local) or Jina Reader (fallback).

**When to Use:**
- Reading full content from URLs user shares
- Extracting detailed information from specific pages
- Following up on web search results
- Parsing articles, documentation, or blog posts

**Providers:**
| Provider | Cost | Notes |
|----------|------|-------|
| crawl4ai | Free | Local library, JS rendering support |
| Jina Reader | Free | API, simpler parsing, rate limits |

**Schema:**
```json
{
  "url": "string (required)",
  "include_images": "bool (default false)",
  "max_length": "int (default 10000 chars)",
  "wait_for_js": "bool (default false) - wait for JavaScript rendering"
}
```

**Response includes:** title, content (markdown), metadata, truncated indicator

---

### Reddit Search Tool (`reddit_search`)
Search Reddit for community discussions using PRAW (OAuth) or JSON API (public).

**When to Use:**
- Real user opinions and experiences
- Product/service recommendations from community
- Community-specific discussions
- Finding relevant subreddits for topics

**Providers:**
| Provider | Cost | Rate Limit | Auth Required |
|----------|------|------------|---------------|
| PRAW | Free | 60 req/min (auto-handled) | OAuth credentials |
| JSON API | Free | ~1 req/sec | None |

**Schema:**
```json
{
  "query": "string (required)",
  "subreddit": "string (optional, without r/ prefix)",
  "search_type": "posts|comments|subreddits (default posts)",
  "sort": "relevance|hot|top|new (default relevance)",
  "time_filter": "hour|day|week|month|year|all",
  "limit": "int (1-25, default 10)",
  "include_comments": "bool (default true) - include top comments"
}
```

**Response includes:** title, subreddit, author, score, selftext, top comments

---

### Update User Profile Tool (`update_user_profile`)
Update user profile fields in agentic-memories.

**When to Use:**
- User explicitly shares new personal information
- User corrects previously known information
- User states new preferences or goals
- NEVER update without clear user intent

**Schema:**
```json
{
  "user_id": "string (required)",
  "category": "basics|preferences|goals|interests|background (required)",
  "field_name": "string (required)",
  "value": "any (required) - string, number, boolean, or array",
  "reason": "string (optional) - reason for update (audit trail)"
}
```

**Categories & Common Fields:**
| Category | Fields |
|----------|--------|
| basics | name, age, location, occupation, timezone |
| preferences | communication_style, topics_of_interest, response_length |
| goals | short_term, long_term, current_focus |
| interests | hobbies, favorite_topics, dislikes |
| background | education, work_history, family |

---

### Fallback Behavior

All external tools implement fallback providers for resilience:

| Tool | Fallback Trigger | Fallback Action |
|------|------------------|-----------------|
| web_search | Tavily error/rate limit/timeout (10s) | Use DuckDuckGo |
| web_crawl | crawl4ai parse failure/timeout (15s) | Use Jina Reader |
| reddit_search | PRAW OAuth failure/no credentials | Use JSON API |
| update_user_profile | N/A (single provider) | Retry with exponential backoff |

### Performance Targets

| Tool | Latency P95 | Success Rate Target |
|------|-------------|---------------------|
| web_search | <3s | >98% |
| web_crawl | <5s | >98% |
| reddit_search | <4s | >98% |
| update_user_profile | <1s | >98% |
```

**Subtasks:**
- [ ] Add Extended MCP Tools section header
- [ ] Document web_search with schema, providers, usage examples
- [ ] Document web_crawl with schema, providers, usage examples
- [ ] Document reddit_search with schema, providers, usage examples
- [ ] Document update_user_profile with categories and fields
- [ ] Add fallback behavior table with trigger conditions
- [ ] Add performance targets table
- [ ] Add cost estimates in provider tables
- [ ] Add rate limit information in provider tables
- [ ] Ensure JSON schema examples are properly formatted

---

### Task 3: Update README.md (Optional)
**Status:** TODO
**Acceptance Criteria:** AC #4

**Implementation Details:**

Add brief mention in README.md in Features section:

```markdown
## Extended Tools

Annie includes additional MCP tools for web access:

- **Web Search**: Search the web via Tavily/DuckDuckGo
- **Web Crawl**: Fetch full page content via crawl4ai/Jina
- **Reddit Search**: Search Reddit via PRAW/JSON API
- **Profile Update**: Update user profile via agentic-memories

See CLAUDE.md for detailed documentation.

### API Keys Required for Extended Tools

| Tool | Required | Provider | Cost |
|------|----------|----------|------|
| Web Search | Yes | Tavily | Free tier: 1000/month |
| Web Crawl | No | crawl4ai (local) | Free |
| Reddit Search | Optional | Reddit OAuth | Free |
| Profile Update | No | agentic-memories | Free (self-hosted) |
```

**Subtasks:**
- [ ] Add Extended Tools section to README
- [ ] List API key requirements with costs
- [ ] Reference CLAUDE.md for detailed docs
- [ ] Review placement in README structure

---

### Task 4: Update config.py Files
**Status:** TODO
**Acceptance Criteria:** AC #6

**Implementation Details:**

**A. Update `mcp_server/config.py`:**

Add new environment variable loading:

```python
# Epic 15: Extended MCP Tools Configuration
# ------------------------------------------

# Web Search (Story 15.1)
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
DUCKDUCKGO_ENABLED = os.getenv("DUCKDUCKGO_ENABLED", "true").lower() == "true"

# Web Crawl (Story 15.2)
JINA_API_KEY = os.getenv("JINA_API_KEY", "")

# Reddit Search (Story 15.3)
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "annie-bot/1.0")
```

**B. Add validation function:**

```python
def validate_epic15_config():
    """Validate Epic 15 configuration with warnings for missing optional keys."""
    issues = []

    # Required for web_search
    if not TAVILY_API_KEY:
        issues.append("TAVILY_API_KEY not set - web_search will not be available")

    # Optional warnings
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        logger.warning("Reddit OAuth credentials not set - using JSON API fallback")

    return issues
```

**C. Ensure sensitive values are masked in logs:**

```python
def get_masked_config():
    """Return config with sensitive values masked for logging."""
    return {
        "TAVILY_API_KEY": mask_secret(TAVILY_API_KEY),
        "JINA_API_KEY": mask_secret(JINA_API_KEY),
        "REDDIT_CLIENT_ID": mask_secret(REDDIT_CLIENT_ID),
        "REDDIT_CLIENT_SECRET": mask_secret(REDDIT_CLIENT_SECRET),
        "REDDIT_USER_AGENT": REDDIT_USER_AGENT,
        "DUCKDUCKGO_ENABLED": DUCKDUCKGO_ENABLED,
    }
```

**Subtasks:**
- [ ] Add TAVILY_API_KEY to mcp_server/config.py
- [ ] Add DUCKDUCKGO_ENABLED with boolean parsing
- [ ] Add JINA_API_KEY (optional)
- [ ] Add REDDIT_CLIENT_ID (optional)
- [ ] Add REDDIT_CLIENT_SECRET (optional)
- [ ] Add REDDIT_USER_AGENT with default value
- [ ] Add validation function with appropriate warnings
- [ ] Ensure API keys are masked in log output
- [ ] Add to get_config() dictionary if exists
- [ ] Test config loading in dev environment

---

## Test Requirements

### Manual Verification (All Tasks)

1. **env.example Verification:**
   - [ ] All 6 new environment variables present
   - [ ] Each variable has a description comment
   - [ ] Cost estimates included for Tavily
   - [ ] Links to obtain API keys are correct and working
   - [ ] Variables grouped under Epic 15 section
   - [ ] Default values documented where applicable

2. **CLAUDE.md Verification:**
   - [ ] All 4 tools documented (web_search, web_crawl, reddit_search, update_user_profile)
   - [ ] Each tool has complete schema with all parameters
   - [ ] Usage examples are clear and relevant
   - [ ] Provider tables include cost and rate limit info
   - [ ] Fallback behavior table is complete and accurate
   - [ ] Performance targets match tech spec

3. **config.py Verification:**
   - [ ] All new env vars loaded correctly
   - [ ] Default values work as expected
   - [ ] Boolean parsing for DUCKDUCKGO_ENABLED works
   - [ ] Missing API keys don't crash startup
   - [ ] Sensitive values are masked in logs

### Automated Tests (Task 4)

**File:** `mcp_server/tests/test_config.py`

```python
def test_epic15_config_defaults():
    """Test Epic 15 config loads with defaults."""
    # Clear env vars
    for var in ["TAVILY_API_KEY", "DUCKDUCKGO_ENABLED", "JINA_API_KEY",
                "REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET", "REDDIT_USER_AGENT"]:
        os.environ.pop(var, None)

    # Reload config
    importlib.reload(config)

    assert config.TAVILY_API_KEY == ""
    assert config.DUCKDUCKGO_ENABLED == True  # default
    assert config.REDDIT_USER_AGENT == "annie-bot/1.0"  # default

def test_duckduckgo_boolean_parsing():
    """Test DUCKDUCKGO_ENABLED parses boolean correctly."""
    test_cases = [
        ("true", True),
        ("True", True),
        ("TRUE", True),
        ("false", False),
        ("False", False),
        ("", False),
        ("1", False),  # Only "true" variations should be True
    ]
    for value, expected in test_cases:
        os.environ["DUCKDUCKGO_ENABLED"] = value
        importlib.reload(config)
        assert config.DUCKDUCKGO_ENABLED == expected

def test_config_masking():
    """Test sensitive values are masked."""
    os.environ["TAVILY_API_KEY"] = "tvly-secret12345"
    importlib.reload(config)

    masked = config.get_masked_config()
    assert "tvly" in masked["TAVILY_API_KEY"]
    assert "secret12345" not in masked["TAVILY_API_KEY"]
```

---

## Definition of Done

- [ ] Task 1: env.example updated with all Epic 15 variables
- [ ] Task 2: CLAUDE.md updated with all 4 tool documentations
- [ ] Task 3: README.md updated (optional)
- [ ] Task 4: config.py files updated with new env var loading
- [ ] All 6 acceptance criteria validated
- [ ] Manual verification checklist completed
- [ ] Automated config tests pass
- [ ] Documentation reviewed for accuracy against implementation
- [ ] No broken links in documentation
- [ ] Consistent formatting across all documentation updates

---

## Dev Notes

### Documentation Locations

| File | Purpose | Audience | Priority |
|------|---------|----------|----------|
| env.example | Environment setup | Operators, Developers | Required |
| CLAUDE.md | AI context | Claude, Developers | Required |
| README.md | Quick start | All users | Optional |
| mcp_server/config.py | Runtime config | Developers | Required |

### Documentation Style Guidelines

1. **env.example:**
   - Use comments for descriptions (# prefix)
   - Include default values where applicable
   - Group related variables under section headers
   - Add links to obtain API keys (https://)
   - Include cost estimates in comments
   - Mark required vs optional clearly

2. **CLAUDE.md:**
   - Technical but concise
   - Include complete JSON schemas
   - Use tables for comparison data
   - Provide "When to Use" guidance
   - Document response formats
   - Keep consistent with existing CLAUDE.md style

3. **config.py:**
   - Use os.getenv() with sensible defaults
   - Parse booleans explicitly (.lower() == "true")
   - Group Epic 15 vars together with comment header
   - Implement masking for sensitive values

### Dependencies

**Blocking:**
- Stories 15.1-15.5 should be complete for accurate documentation
- Need to verify actual implementation matches documented schemas

**Non-Blocking:**
- Can draft documentation in parallel with implementation
- Update post-implementation if schemas changed

### Key Files to Modify

| File | Changes | Story Ref |
|------|---------|-----------|
| `env.example` | Add 6 new env vars | 15.6 AC1 |
| `CLAUDE.md` | Add Extended MCP Tools section | 15.6 AC2 |
| `README.md` | Add Extended Tools section (optional) | 15.6 AC4 |
| `mcp_server/config.py` | Add env var loading | 15.6 AC6 |

### Verification Strategy

1. **Pre-merge Review:**
   - Review env.example against tech spec
   - Verify CLAUDE.md schemas match implementation
   - Cross-check costs/limits against provider docs

2. **Post-merge Verification:**
   - Test env var loading in Docker environment
   - Verify Claude can read and understand tool docs
   - Confirm masked logging works correctly

---

## References

1. **Epic 15 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-15.md`)
   - AC 15.6.1-15.6.5 acceptance criteria
   - Provider cost and rate limit details
   - Data model schemas

2. **Epic 15 Overview** (`docs/epics/epic-15-extended-mcp-tools.md`)
   - Story 15.6 details
   - Environment variable list
   - Architecture overview

3. **Provider Documentation:**
   - Tavily: https://docs.tavily.com
   - crawl4ai: https://github.com/unclecode/crawl4ai
   - PRAW: https://praw.readthedocs.io
   - Jina Reader: https://jina.ai/reader
   - DuckDuckGo Search: https://pypi.org/project/duckduckgo-search/

4. **Existing Configuration Files:**
   - `env.example` - Current environment template
   - `CLAUDE.md` - Current AI context documentation
   - `mcp_server/config.py` - Current config implementation

---

**Created:** 2025-12-30
**Updated:** 2025-12-30
**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Story:** 15.6 - Environment Configuration & Documentation
**Status:** backlog
