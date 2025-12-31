# Story 15.4: Update User Profile Tool

**Status:** done
**Sprint:** Completed
**Estimated Effort:** 0.5 days
**Priority:** P0

---

## Story

**As a** user of Annie,
**I want** Annie to update my profile with new information she learns about me,
**So that** her understanding of me stays current and she can provide more personalized advice.

**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Prerequisites:** agentic-memories profile API available at PUT /v1/profile/{category}/{field_name}
**Dependencies:** None (standalone tool implementation)

## Acceptance Criteria

### AC #1: PUT to Profile API
**Given** the update_user_profile tool is called
**When** user_id, category, field_name, and value are provided
**Then** the tool makes a PUT request to agentic-memories /v1/profile/{category}/{field}

**Mapped to Tasks:** Task 1

---

### AC #2: Category Validation
**Given** the update_user_profile tool is called
**When** category is provided
**Then** it is validated against allowed list: basics, preferences, goals, interests, background

**Mapped to Tasks:** Task 1

---

### AC #3: Value Types Support
**Given** the update_user_profile tool is called with a value
**When** value is string, number, boolean, or array
**Then** the tool correctly serializes and sends the value

**Mapped to Tasks:** Task 1

---

### AC #4: Audit Trail
**Given** the update_user_profile tool makes an API call
**When** the request is sent
**Then** source field is set to "llm_explicit" for audit trail

**Mapped to Tasks:** Task 1

---

### AC #5: Handle 404 (Not Found)
**Given** the update_user_profile tool is called
**When** the profile or field doesn't exist (404 response)
**Then** a clear error message is returned explaining the issue

**Mapped to Tasks:** Task 1

---

### AC #6: Handle 400 (Invalid Request)
**Given** the update_user_profile tool is called with invalid data
**When** invalid category or field is provided (400 response)
**Then** a validation error is returned with details

**Mapped to Tasks:** Task 1

---

### AC #7: Retry Logic
**Given** the update_user_profile tool encounters a transient error
**When** 5xx error or timeout occurs
**Then** retry with exponential backoff (1s, 2s, 4s) is applied

**Mapped to Tasks:** Task 1

---

### AC #8: Unit Tests
**Given** the update_user_profile tool implementation
**When** tests are run
**Then** mocked agentic-memories responses achieve >80% coverage

**Mapped to Tasks:** Task 2

---

### AC #9: Status Summarizer
**Given** the update_user_profile tool is executing
**When** the tool starts and completes
**Then** status updates "Updating profile..." and "Profile updated" are emitted

**Mapped to Tasks:** Task 3

---

### AC #10: System Prompt Guidance
**Given** the system prompt
**When** the LLM reads it
**Then** clear guidance is provided on when to use update_user_profile

**Mapped to Tasks:** Task 4

---

## Tasks / Subtasks

### Task 1: Implement Profile Update Handler
**Status:** DONE
**Acceptance Criteria:** AC #1, AC #2, AC #3, AC #4, AC #5, AC #6, AC #7

**Implementation Details:**

Add `update_user_profile_tool_handler` to `mcp_server/tools.py`:

```python
ALLOWED_CATEGORIES = {"basics", "preferences", "goals", "interests", "background"}

async def update_user_profile_tool_handler(
    user_id: str,
    category: str,
    field_name: str,
    value: Any,
    reason: str = None
) -> Dict[str, Any]:
    """Update a user profile field in agentic-memories."""
    start_time = time.time()

    # Validate category
    if category not in ALLOWED_CATEGORIES:
        return {
            "status": "error",
            "error_message": f"Invalid category '{category}'. Allowed: {', '.join(ALLOWED_CATEGORIES)}",
            "error_code": "VALIDATION_ERROR"
        }

    config = get_config()
    memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")

    payload = {
        "user_id": user_id,
        "value": value,
        "source": "llm_explicit"  # AC #4: Audit trail
    }

    if reason:
        payload["reason"] = reason

    max_retries = 3
    retry_delays = [1, 2, 4]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                response = await client.put(
                    f"{memories_url}/v1/profile/{category}/{field_name}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                duration_ms = int((time.time() - start_time) * 1000)

                if response.status_code in (200, 201):
                    result = response.json()
                    return {
                        "status": "success",
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "value": result.get("value"),
                        "previous_value": result.get("previous_value"),
                        "confidence": 100.0,
                        "last_updated": result.get("last_updated")
                    }
                elif response.status_code == 404:
                    return {
                        "status": "error",
                        "error_message": f"Profile field not found: {category}/{field_name}",
                        "error_code": "NOT_FOUND"
                    }
                elif response.status_code == 400:
                    error_data = response.json()
                    return {
                        "status": "error",
                        "error_message": error_data.get("message", "Invalid request"),
                        "error_code": "VALIDATION_ERROR"
                    }
                elif response.status_code >= 500:
                    # Retry on server errors
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delays[attempt])
                        continue
                    return {
                        "status": "error",
                        "error_message": f"Server error after {max_retries} attempts",
                        "error_code": "SERVER_ERROR"
                    }
                else:
                    return {
                        "status": "error",
                        "error_message": f"HTTP {response.status_code}",
                        "error_code": response.status_code
                    }
            except httpx.TimeoutException:
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue
                return {
                    "status": "error",
                    "error_message": f"Timeout after {max_retries} attempts",
                    "error_code": "TIMEOUT_ERROR"
                }
            except Exception as e:
                return {
                    "status": "error",
                    "error_message": str(e),
                    "error_code": "INTERNAL_ERROR"
                }

    return {"status": "error", "error_message": "Unknown error", "error_code": "UNKNOWN"}

# Tool definition
update_user_profile_tool = {
    "name": "update_user_profile",
    "description": """Update a specific field in the user's profile.

Use this tool when the user:
1. Explicitly tells you new information about themselves
2. Corrects previously known information
3. Expresses a preference or goal change

Categories and common fields:
- basics: name, age, location, occupation, timezone
- preferences: communication_style, topics_of_interest, response_length
- goals: short_term, long_term, current_focus
- interests: hobbies, favorite_topics, dislikes
- background: education, work_history, family

Do NOT use for:
- Information already in their profile
- Temporary moods or states
- Speculative information""",
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
                "description": "New value (string, number, boolean, or array)"
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for the update (for audit trail)"
            }
        },
        "required": ["user_id", "category", "field_name", "value"]
    },
    "handler": update_user_profile_tool_handler
}
```

**Subtasks:**
- [ ] Implement update_user_profile_tool_handler
- [ ] Add category validation
- [ ] Handle all value types (string, number, boolean, array)
- [ ] Set source="llm_explicit" in all requests
- [ ] Handle 404 responses with clear message
- [ ] Handle 400 responses with validation details
- [ ] Implement retry logic with exponential backoff
- [ ] Add logging for profile updates

---

### Task 2: Unit Tests
**Status:** DONE
**Acceptance Criteria:** AC #8

**Implementation Details:**

Create `mcp_server/tests/test_update_user_profile_tool.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from mcp_server.tools import update_user_profile_tool_handler, ALLOWED_CATEGORIES


@pytest.fixture
def mock_profile_response():
    """Success response from agentic-memories profile API."""
    return {
        "user_id": "user123",
        "category": "preferences",
        "field_name": "communication_style",
        "value": "formal",
        "previous_value": "casual",
        "confidence": 100.0,
        "last_updated": "2025-12-30T12:00:00Z"
    }


@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx responses."""
    def _create(status_code: int, json_data: dict = None):
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = json_data or {}
        return mock_response
    return _create


class TestUpdateUserProfileTool:
    """Test suite for update_user_profile tool."""

    @pytest.mark.asyncio
    async def test_success_path(self, mock_profile_response, mock_httpx_response):
        """AC #1: PUT to Profile API succeeds."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(200, mock_profile_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            assert result["status"] == "success"
            assert result["value"] == "formal"
            assert result["previous_value"] == "casual"
            assert result["confidence"] == 100.0

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self):
        """AC #2: Category validation rejects invalid categories."""
        result = await update_user_profile_tool_handler(
            user_id="user123",
            category="invalid_category",
            field_name="test",
            value="test"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "Invalid category" in result["error_message"]

    @pytest.mark.asyncio
    async def test_all_valid_categories(self, mock_profile_response, mock_httpx_response):
        """AC #2: All valid categories are accepted."""
        for category in ALLOWED_CATEGORIES:
            with patch("httpx.AsyncClient") as mock_client:
                mock_instance = AsyncMock()
                response_data = {**mock_profile_response, "category": category}
                mock_instance.put.return_value = mock_httpx_response(200, response_data)
                mock_client.return_value.__aenter__.return_value = mock_instance

                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category=category,
                    field_name="test_field",
                    value="test_value"
                )

                assert result["status"] == "success", f"Category {category} should be valid"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value_type,test_value", [
        ("string", "test string"),
        ("number", 42),
        ("float", 3.14),
        ("boolean_true", True),
        ("boolean_false", False),
        ("array", ["item1", "item2", "item3"]),
    ])
    async def test_all_value_types(self, value_type, test_value, mock_httpx_response):
        """AC #3: All value types (string, number, boolean, array) supported."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(200, {
                "user_id": "user123",
                "value": test_value,
                "confidence": 100.0,
                "last_updated": "2025-12-30T12:00:00Z"
            })
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="test_field",
                value=test_value
            )

            assert result["status"] == "success", f"Value type {value_type} should work"

    @pytest.mark.asyncio
    async def test_source_llm_explicit_in_request(self, mock_httpx_response):
        """AC #4: source='llm_explicit' is set in all requests."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(200, {
                "user_id": "user123",
                "value": "test",
                "confidence": 100.0,
                "last_updated": "2025-12-30T12:00:00Z"
            })
            mock_client.return_value.__aenter__.return_value = mock_instance

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="test",
                value="test"
            )

            # Verify PUT was called with source="llm_explicit"
            call_args = mock_instance.put.call_args
            request_body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert request_body["source"] == "llm_explicit"

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_httpx_response):
        """AC #5: Handle 404 (Not Found) with clear error message."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(404, {})
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="nonexistent",
                value="test"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "NOT_FOUND"
            assert "not found" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_400_validation_error(self, mock_httpx_response):
        """AC #6: Handle 400 (Invalid Request) with validation error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(400, {
                "message": "Field name contains invalid characters"
            })
            mock_client.return_value.__aenter__.return_value = mock_instance

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="invalid!field",
                value="test"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_retry_on_500(self, mock_profile_response, mock_httpx_response):
        """AC #7: Retry with exponential backoff on 5xx errors."""
        call_count = 0

        async def mock_put(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return mock_httpx_response(503, {})
            return mock_httpx_response(200, mock_profile_response)

        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.side_effect = mock_put
            mock_client.return_value.__aenter__.return_value = mock_instance

            with patch("asyncio.sleep", new_callable=AsyncMock):  # Skip actual sleep
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="test",
                    value="test"
                )

            assert result["status"] == "success"
            assert call_count == 3  # Two failures + one success

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_error(self, mock_httpx_response):
        """AC #7: After max retries, return error."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(503, {})
            mock_client.return_value.__aenter__.return_value = mock_instance

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="test",
                    value="test"
                )

            assert result["status"] == "error"
            assert result["error_code"] == "SERVER_ERROR"
            assert "after 3 attempts" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """AC #7: Timeout errors trigger retry."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.side_effect = httpx.TimeoutException("Connection timed out")
            mock_client.return_value.__aenter__.return_value = mock_instance

            with patch("asyncio.sleep", new_callable=AsyncMock):
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="test",
                    value="test"
                )

            assert result["status"] == "error"
            assert result["error_code"] == "TIMEOUT_ERROR"

    @pytest.mark.asyncio
    async def test_reason_included_in_payload(self, mock_profile_response, mock_httpx_response):
        """Optional reason parameter is included in request."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_instance = AsyncMock()
            mock_instance.put.return_value = mock_httpx_response(200, mock_profile_response)
            mock_client.return_value.__aenter__.return_value = mock_instance

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal",
                reason="User explicitly stated preference in conversation"
            )

            call_args = mock_instance.put.call_args
            request_body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert request_body.get("reason") == "User explicitly stated preference in conversation"
```

**Subtasks:**
- [ ] Test success path (AC #1)
- [ ] Test invalid category rejection (AC #2)
- [ ] Test all valid categories accepted (AC #2)
- [ ] Test all value types: string, number, boolean, array (AC #3)
- [ ] Test source="llm_explicit" in request payload (AC #4)
- [ ] Test 404 handling with clear error message (AC #5)
- [ ] Test 400 handling with validation error (AC #6)
- [ ] Test retry on 5xx with exponential backoff (AC #7)
- [ ] Test retry exhaustion returns error (AC #7)
- [ ] Test timeout handling triggers retry (AC #7)
- [ ] Test optional reason parameter inclusion
- [ ] Achieve >80% coverage

---

### Task 3: Status Summarizer
**Status:** DONE
**Acceptance Criteria:** AC #9

**Implementation Details:**

Add to `backend/api/status_summarizers.py`:

```python
def summarize_update_user_profile_result(result: Dict[str, Any]) -> str:
    """Summarize update_user_profile tool result.

    Result shape:
        {
            "status": "success"|"error",
            "user_id": str,
            "category": str,
            "field_name": str,
            "value": any,
            "previous_value": any,
            "confidence": 100.0,
            "last_updated": str,
            "error_message": str  # On error
        }

    Args:
        result: Tool result dictionary

    Returns:
        Concise summary string

    Examples:
        "Updated communication_style"
        "Profile update failed: Field not found"
    """
    if result.get("status") == "error":
        error_msg = result.get("error_message", "Failed")
        return f"Profile update failed: {error_msg}"[:50]

    field_name = result.get("field_name", "profile")
    category = result.get("category", "")

    # Show field with category context if available
    if category:
        return f"Updated {category}/{field_name}"[:50]
    return f"Updated {field_name}"[:50]


# Add to SUMMARIZERS dict (around line 439)
# "update_user_profile": summarize_update_user_profile_result,
```

Update the `SUMMARIZERS` registry:
```python
SUMMARIZERS = {
    # ... existing entries ...
    "update_user_profile": summarize_update_user_profile_result,  # Story 15.4
}
```

**Note:** The status summarizer is called automatically by `mcp_client.py` after tool execution.
The "Calling {tool_name}..." message is emitted by `mcp_client.py` at line 298 when tool starts.
The completion summary uses `summarize_tool_result()` which looks up the tool in the SUMMARIZERS dict.

**Subtasks:**
- [ ] Implement `summarize_update_user_profile_result` function in `backend/api/status_summarizers.py`
- [ ] Register in SUMMARIZERS dict
- [ ] Handle success case: "Updated {category}/{field_name}"
- [ ] Handle error case: "Profile update failed: {error_message}"
- [ ] Add unit test for status summarizer

---

### Task 4: System Prompt Update
**Status:** DONE
**Acceptance Criteria:** AC #10

**Implementation Details:**

Add to system prompt in `backend/api/prompts.py`:

```python
PROFILE_UPDATE_GUIDANCE = """
## Profile Updates

When the user shares new information about themselves, use the update_user_profile tool:

**Use when:**
- User explicitly shares personal details: "I just moved to Seattle"
- User corrects information: "Actually, I prefer formal communication"
- User states new goals: "I'm now focusing on retirement planning"

**Do NOT use when:**
- Information is temporary: "I'm feeling tired today"
- Already in profile (check first)
- Speculative: "You seem like someone who..."

**Categories:**
- basics: name, location, occupation, age
- preferences: communication_style, topics_of_interest
- goals: short_term, long_term, current_focus
- interests: hobbies, favorite_topics
- background: education, work_history
"""
```

**Subtasks:**
- [ ] Add PROFILE_UPDATE_GUIDANCE to prompts.py
- [ ] Include in system prompt construction
- [ ] Provide clear examples of when to use/not use

---

### Task 5: Tool Registration
**Status:** DONE
**Acceptance Criteria:** AC #1

**Implementation Details:**

Register the tool in the MCP server tool registry (`mcp_server/server.py`):

```python
# Import the tool definition
from mcp_server.tools import update_user_profile_tool

# In the initialization section where other tools are registered
tool_registry.register(update_user_profile_tool)
```

Verify tool appears in `tools/list` response:
```bash
# Manual verification
curl http://localhost:8002/tools/list | jq '.result.tools[] | select(.name == "update_user_profile")'
```

**Subtasks:**
- [ ] Import update_user_profile_tool in server.py
- [ ] Register tool with tool_registry.register()
- [ ] Verify tool appears in tools/list endpoint
- [ ] Verify tool schema is correct (all required params)
- [ ] Test tool can be called via tools/call endpoint

---

## Definition of Done

- [ ] Task 1-5 completed
- [ ] All 10 acceptance criteria validated
- [ ] update_user_profile tool registered in MCP server
- [ ] PUT to /v1/profile/{category}/{field} working
- [ ] Category validation working (5 allowed categories)
- [ ] All value types supported
- [ ] source="llm_explicit" in all requests
- [ ] 404 handling with clear message
- [ ] 400 handling with validation error
- [ ] Retry logic with backoff for 5xx
- [ ] Unit tests passing with >80% coverage
- [ ] Status summarizer emitting updates
- [ ] System prompt includes usage guidance
- [ ] No regressions in other MCP tools

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **update_user_profile tool** (`mcp_server/tools.py`): MCP tool for profile updates
- **agentic-memories**: Profile storage service

**Flow:**
```
LLM -> update_user_profile tool -> PUT /v1/profile/{category}/{field}
                                          ↓
                                   agentic-memories
```

### Technical Constraints

1. **API Contract:**
   - PUT /v1/profile/{category}/{field_name}
   - Body: {user_id, value, source}
   - Response: updated profile with previous_value

2. **Category Validation:**
   - Must be one of: basics, preferences, goals, interests, background
   - Client-side validation before API call

3. **Timeout:**
   - 10 seconds per request
   - Self-hosted, should be fast (<500ms)

4. **Audit Trail:**
   - source="llm_explicit" distinguishes LLM updates from manual

### Dependencies

**Blocking:**
- agentic-memories profile API must be available
- API contract must be verified

**Non-Blocking:**
- Status summarizer (can be added later)
- System prompt (can be added later)

### Key Files to Modify

**Files to Create/Modify:**
- `mcp_server/tools.py` - Add update_user_profile_tool_handler and update_user_profile_tool
- `mcp_server/tests/test_update_user_profile_tool.py` - Unit tests
- `backend/api/status_summarizers.py` - Add profile_update_summarizer
- `backend/api/prompts.py` - Add PROFILE_UPDATE_GUIDANCE

**Reference Files:**
- `.bmad-ephemeral/stories/tech-spec-epic-15.md` - Epic 15 technical specification
- `docs/epics/epic-15-extended-mcp-tools.md` - Epic overview

### Testing Strategy

**Unit Tests:**
- Mock agentic-memories API responses
- Test all error scenarios (404, 400, 5xx, timeout)
- Test value type handling (string, number, boolean, array)
- Test category validation
- Test source="llm_explicit" in payload
- Target: >80% coverage

**Integration Tests (skippable):**
- Live profile update with real agentic-memories
- E2E via chat endpoint: User says "I moved to Seattle" -> tool updates profile

**Manual Verification:**
```bash
# 1. Verify tool registration
curl http://localhost:8002/tools/list | jq '.result.tools[] | select(.name == "update_user_profile")'

# 2. Test tool call directly
curl -X POST http://localhost:8002/tools/call \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "method": "tools/call",
    "params": {
      "name": "update_user_profile",
      "arguments": {
        "user_id": "test123",
        "category": "preferences",
        "field_name": "communication_style",
        "value": "formal"
      }
    },
    "id": 1
  }'

# 3. Verify via agentic-memories (optional)
curl http://host.docker.internal:8080/v1/profile/test123 | jq
```

### Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Latency P95 | <1s | Langfuse traces / log duration_ms |
| Success rate | >98% | Monitor status="success" vs "error" |
| Cost | $0 | Self-hosted agentic-memories |
| Test coverage | >80% | pytest --cov report |

---

## References

1. **Epic 15 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-15.md`)
   - AC 15.4.1-15.4.10 acceptance criteria

2. **Epic 15 Overview** (`docs/epics/epic-15-extended-mcp-tools.md`)
   - Story 15.4 details and schema

3. **agentic-memories API** (verify contract before implementation)
   - PUT /v1/profile/{category}/{field}

---

## API Contract Reference

### agentic-memories Profile Update API

**Endpoint:** `PUT /v1/profile/{category}/{field_name}`

**Request:**
```json
{
  "user_id": "string",       // Required: User identifier
  "value": "any",            // Required: New value (string, number, boolean, array)
  "source": "llm_explicit"   // Required: Always "llm_explicit" for audit trail
}
```

**Successful Response (200/201):**
```json
{
  "user_id": "string",
  "category": "string",      // basics, preferences, goals, interests, background
  "field_name": "string",
  "value": "any",
  "previous_value": "any",   // Previous value before update (null if new)
  "confidence": 100.0,       // Always 100.0 for explicit updates
  "last_updated": "ISO8601"  // Timestamp of update
}
```

**Error Responses:**
- `400 Bad Request`: Invalid category or field name
- `404 Not Found`: Profile or field not found
- `5xx Server Error`: Transient error (retry with backoff)

**Valid Categories:**
- `basics`: name, age, location, occupation, timezone
- `preferences`: communication_style, topics_of_interest, response_length
- `goals`: short_term, long_term, current_focus
- `interests`: hobbies, favorite_topics, dislikes
- `background`: education, work_history, family

---

**Created:** 2025-12-30
**Last Updated:** 2025-12-30
**Epic:** Epic 15 - Extended MCP Tools - Web & Profile
**Story:** 15.4 - Update User Profile Tool
**Status:** backlog
**Author:** Claude (via create-story workflow)
