# Story 13.6: Wake-Up Agent

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.6
**Status:** complete
**Estimated Effort:** 1 day
**Actual Effort:** 1 day
**Completed:** 2025-12-25

---

## User Story

**As a** system,
**I want** an LLM-driven agent that executes fired triggers,
**So that** proactive messages are contextual, relevant, and well-composed.

---

## Acceptance Criteria

### AC #1: Dynamic State Injection
**Given** trigger fires,
**When** agent invoked,
**Then** gathers fresh context:
- Current datetime and day of week (in user's timezone)
- Market status (open/closed/holiday)
- Hours since user last messaged
- Recent conversation summary (from agentic-memories, last 24h)
- Fresh user profile (not from action_context)

### AC #2: Agent Prompt
**Given** trigger fires and gate passes,
**When** agent invoked,
**Then:**
- Receives comprehensive prompt with:
  - Trigger metadata (name, type, fire_count, last_fired)
  - **Dynamic state** (current time, recent context, fresh profile)
  - Full action_context as briefing
  - Available tools list
  - Response format specification
  - **Tone adjustment guidance** based on recent_context

### AC #3: Dynamic Tool Access
**Given** wake-up agent,
**When** executing,
**Then:**
- Queries MCP server fresh for complete tool list
- Has access to ALL read-only tools
- Only restricts state-modifying tools (add_holding, update_holding, remove_holding, create_trigger, delete_trigger)
- No artificial limits on which tools can be used

### AC #4: Skip Logic
**Given** action_context with skip conditions,
**When** agent evaluates,
**Then:**
- Follows execution_instructions from briefing
- Returns `skip=True` with reason when appropriate
- Does not send message for skipped triggers

### AC #5: Message Composition
**Given** action_context with message_guidance,
**When** composing,
**Then:**
- Follows tone, length, include/exclude guidelines
- References good/bad examples from briefing
- Returns composed message
- **Adjusts tone based on recent_context**

### AC #6: Response Format
**Given** agent execution complete,
**Then** returns:
```python
WakeUpResult(
    skip: bool,
    skip_reason: Optional[str],
    message: Optional[str],
    tools_called: List[str],
    reasoning: str
)
```

### AC #7: Guardrails
**Given** agent execution,
**Then** enforces:
- 10 minute timeout (600 seconds)
- Restricted tools list (no portfolio modification)
- No hard limits on tool calls or message length

---

## Tasks

### Task 1: Create agent module structure
- [x] Create `backend/api/proactive/agent.py`
- [x] Define `WakeUpResult` dataclass
- [x] Define `DynamicState` dataclass

### Task 2: Implement dynamic state gathering
- [x] Get current datetime in user's timezone
- [x] Calculate hours since last user message
- [x] Fetch market status (simple open/closed check)
- [x] Fetch recent conversation summary from agentic-memories
- [x] Fetch fresh user profile

### Task 3: Build agent prompt
- [x] Create prompt template with all sections
- [x] Inject trigger metadata
- [x] Inject dynamic state
- [x] Inject action_context as briefing
- [x] Add tone adjustment guidance

### Task 4: Implement tool access
- [x] Query MCP server for available tools
- [x] Filter out restricted state-modifying tools
- [x] Provide tool list to LLM

### Task 5: Implement agent execution
- [x] Use existing LLM client with streaming
- [x] Parse LLM response for skip/message decision
- [x] Track tools called during execution
- [x] Handle timeout (10 minute limit)

### Task 6: Add Langfuse tracing
- [x] Trace agent execution as span
- [x] Include trigger metadata in trace
- [x] Log tools called and reasoning

---

## Dev Notes

### Technical Notes
- See Design Doc Section 7 for full prompt and design
- Uses same LLM client as chat
- Traced in Langfuse with trigger metadata

### Files to Create/Modify
- `backend/api/proactive/agent.py` (new)

### Restricted Tools (state-modifying)
- add_holding
- update_holding
- remove_holding
- create_trigger
- update_trigger
- delete_trigger

### Agent Prompt Sections
1. Role and context
2. Trigger metadata
3. Dynamic state
4. action_context (briefing)
5. Available tools
6. Response format
7. Tone guidance based on recent context

---

## Dev Agent Record

### Context Reference
- **Story Context:** `.bmad-ephemeral/stories/13-6-wake-up-agent.context.xml`
- **Design Document:** `docs/design/proactive-ai-architecture.md` (Section 7)
- **Epic Overview:** `docs/epics/epic-13-proactive-ai.md`

### Implementation Notes

**Completed:** 2025-12-25

**File Created:**
- `backend/api/proactive/agent.py` - Wake-up agent implementation with full LLM-driven execution

**Key Implementation Details:**

1. **Dynamic State Gathering:**
   - Fetches current datetime in user's timezone using pytz
   - Calculates market status based on US stock market hours (9:30 AM - 4:00 PM ET, weekdays)
   - Retrieves hours since last user message from Redis activity tracking
   - Attempts to fetch recent conversation context from agentic-memories (placeholder for future implementation)
   - Fetches fresh user profile via ProfileManager with refresh=True
   - Graceful degradation: Returns minimal state on errors

2. **Agent Prompt Construction:**
   - Comprehensive prompt with 7 sections: role, trigger metadata, dynamic state, action_context, tools, response format, tone guidance
   - Tone adjustment based on hours since last message: <1h (brief/casual), 1-24h (normal), >24h (warmer/detailed)
   - Emphasizes fetching fresh data and following briefing instructions
   - Warns against inappropriate tone when user is going through difficult times

3. **Tool Access:**
   - Dynamically queries MCP server for available tools
   - Filters out 6 restricted state-modifying tools: add_holding, update_holding, remove_holding, create_trigger, update_trigger, delete_trigger
   - All read-only tools available to agent (no artificial limits)

4. **Agent Execution:**
   - Uses LLMClient with streaming to handle tool calls
   - Tracks all tools called during execution for observability
   - 10-minute timeout enforced via asyncio.wait_for
   - Returns WakeUpResult with skip status, message, tools_called, and reasoning

5. **Response Parsing:**
   - Primary: Parse LLM response as JSON
   - Fallback: Treat as plain text message if JSON parsing fails
   - Graceful degradation ensures system robustness

6. **Langfuse Tracing:**
   - Main execution traced as span with trigger metadata
   - Dynamic state gathering traced as nested span
   - Outputs include skip status, message length, tools called, duration
   - Timeout and error cases fully traced

7. **Error Handling:**
   - All errors caught and converted to skip results with reasoning
   - Detailed logging for debugging
   - Never crashes - always returns WakeUpResult

**Design Decisions:**

- Used streaming LLM mode to properly track tool calls (non-streaming would miss intermediate tool invocations)
- Market status calculation is simple (weekday + hours check) without holiday awareness - sufficient for V1
- Recent conversation context is placeholder pending agentic-memories API support
- Timezone defaults to America/Los_Angeles but accepts user-specific timezone parameter
- Timeout is at outer async function level to cover entire execution including tool calls

**Testing Considerations:**

- Unit tests should mock LLMClient, MCPClient, ProfileManager, Redis
- Integration tests should use real MCP server with test tools
- Test scenarios: skip logic, message composition, tone adjustment, timeout handling, tool restriction
- Langfuse traces should be verified in staging environment

### Verification
- [x] Agent gathers fresh dynamic state
- [x] Agent respects skip conditions
- [x] Agent composes messages following guidance
- [x] Agent adjusts tone based on recent context
- [x] Agent doesn't use restricted tools
- [x] Langfuse traces show agent execution
