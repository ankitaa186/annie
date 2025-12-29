# Story 14.5: Update System Prompt for Memory Management

**Epic:** 14 - Direct Memory Storage Enhancement
**Story ID:** 14.5
**Status:** done
**Estimated Effort:** 0.5 days
**Priority:** P1

---

## User Story

**As a** user,
**I want** Annie to understand when to use memory tools appropriately,
**So that** critical information is stored reliably without overusing the store_memory tool.

---

## Description

Add memory management instructions to the system prompt to guide the LLM on proper usage of `store_memory`, `delete_memory`, and `retrieve_memories` tools. The LLM needs to understand that:

1. **Background extraction already runs automatically** via the Memory Orchestrator
2. `store_memory` is only for **critical explicit memories** the user specifically asks to remember
3. `delete_memory` is for correcting mistakes or honoring user requests to forget
4. `retrieve_memories` should be used liberally for context and personalization

Additionally, update status summarizers to handle the new response format from the updated `store_memory` tool and the new `delete_memory` tool.

---

## Acceptance Criteria

### AC #1: MEMORY_MANAGEMENT_SECTION Constant Added
**Given** the system prompt is being built,
**When** the prompt includes memory tool guidance,
**Then:**
- A new `MEMORY_MANAGEMENT_SECTION` constant is defined in `prompts.py`
- The section clearly explains background extraction handles routine info
- The section specifies when to use `store_memory` (critical explicit only)
- The section specifies when to use `delete_memory`
- The section specifies when to use `retrieve_memories` (liberally)
- Good and bad usage examples are provided

### AC #2: TOOL_USAGE_INSTRUCTIONS Updated
**Given** the tool usage instructions,
**When** the LLM reads the instructions,
**Then:**
- `delete_memory` is included in the memory tools list
- The workflow for delete_memory is explained (retrieve first, then delete)
- The user_id requirement is prominently displayed

### AC #3: System Prompt Integration
**Given** `build_system_prompt()` is called,
**When** generating the complete system prompt,
**Then:**
- `MEMORY_MANAGEMENT_SECTION` is included after `PROACTIVE_CAPABILITIES_SECTION`
- The section appears in the correct order in the final prompt

### AC #4: Status Summarizers Updated
**Given** a `store_memory` or `delete_memory` tool result,
**When** generating a status summary,
**Then:**
- `summarize_store_memory_result()` handles the new response format with `memory_id` and `storage` details
- New `summarize_delete_memory_result()` function is added
- Both summarizers are registered in the `SUMMARIZERS` registry
- Error cases are handled gracefully

---

## Technical Details

### Files to Modify

1. **`backend/api/prompts.py`**
   - Add `MEMORY_MANAGEMENT_SECTION` constant
   - Update `TOOL_USAGE_INSTRUCTIONS` constant
   - Update `build_system_prompt()` to include memory management section

2. **`backend/api/status_summarizers.py`**
   - Update `summarize_store_memory_result()` for new response format
   - Add `summarize_delete_memory_result()` function
   - Register new summarizer in `SUMMARIZERS` registry

### MEMORY_MANAGEMENT_SECTION Content

```python
MEMORY_MANAGEMENT_SECTION = """
## MEMORY MANAGEMENT

Annie automatically extracts and stores memories from conversations in the background.
You do NOT need to call store_memory for routine information.

### When to Use store_memory (Explicit Storage)

ONLY use store_memory for CRITICAL information that:
1. User explicitly asks you to remember ("Remember that I...", "Don't forget...")
2. Is a permanent preference/constraint ("I'm allergic to...", "Never recommend...")
3. Is a life-changing decision with lasting impact
4. Would be dangerous to forget (medical conditions, safety constraints)

**Good Examples:**
- "User is severely allergic to shellfish - carries EpiPen"
- "User's risk tolerance is conservative - never recommend high-risk investments"
- "User's mother passed away in March 2024 - sensitive topic"

**Bad Examples (background extraction handles these):**
- Daily activities or routine conversations
- Temporary preferences or moods
- Information already in their profile
- Topics just discussed (already being extracted)

### When to Use delete_memory

Use delete_memory when:
1. User says something was remembered incorrectly
2. User explicitly asks to forget something
3. You find conflicting or duplicate memories
4. Information is outdated and causing confusion

**Deletion Workflow:**
1. First call retrieve_memories to find the memory ID
2. Confirm with the user which memory to delete
3. Call delete_memory with the memory_id

**Important:** Deletion cannot be undone. Always confirm with the user before deleting.

### When to Use retrieve_memories

Use retrieve_memories LIBERALLY when:
1. User asks about past decisions or conversations
2. Making recommendations that should consider history
3. User references something from the past
4. You need context about user preferences

Retrieval is fast (<2s) and should be used proactively.
"""
```

### Updated TOOL_USAGE_INSTRUCTIONS

```python
TOOL_USAGE_INSTRUCTIONS = """
## TOOL USAGE REQUIREMENTS

### Memory Tools (store_memory, retrieve_memories, delete_memory)
- ALWAYS use the exact user_id from the system message
- Never use generic IDs like 'anonymous_user'
- store_memory: Only for critical, permanent information (see Memory Management section)
- delete_memory: First retrieve the memory to get its ID, then confirm with user, then delete
- retrieve_memories: Use liberally for context and personalization

### User ID
Current user ID for all tool calls: {user_id}
"""
```

### store_memory Result Format (Updated)

```python
{
    "status": "success"|"error",
    "memory_id": str,              # UUID of stored memory
    "message": str,
    "storage": {
        "chromadb": bool,          # Always true on success
        "episodic": bool,          # True if event_timestamp provided
        "emotional": bool,         # True if emotional_state provided
        "procedural": bool         # True if skill_name provided
    }
}
```

### delete_memory Result Format (New)

```python
{
    "status": "success"|"error",
    "deleted": bool,
    "memory_id": str,
    "message": str,
    "storage": {
        "chromadb": bool,
        "episodic": bool,
        "emotional": bool,
        "procedural": bool
    }
}
```

---

## Tasks

### Task 1: Add MEMORY_MANAGEMENT_SECTION constant
- [x] Create `MEMORY_MANAGEMENT_SECTION` constant in `prompts.py`
- [x] Include guidance on when to use `store_memory` (critical explicit only)
- [x] Include guidance on when to use `delete_memory`
- [x] Include guidance on when to use `retrieve_memories`
- [x] Add good and bad usage examples

### Task 2: Update TOOL_USAGE_INSTRUCTIONS
- [x] Update `TOOL_USAGE_INSTRUCTIONS` in `prompts.py`
- [x] Include `delete_memory` in memory tools list
- [x] Explain delete workflow (retrieve → confirm → delete)
- [x] Keep user_id requirement prominent

### Task 3: Integrate into build_system_prompt()
- [x] Add `MEMORY_MANAGEMENT_SECTION` to `build_system_prompt()`
- [x] Place after `PROACTIVE_CAPABILITIES_SECTION`
- [x] Verify prompt order is correct

### Task 4: Update store_memory summarizer
- [x] Update `summarize_store_memory_result()` in `status_summarizers.py`
- [x] Handle new response format with `memory_id`
- [x] Show truncated memory_id in summary (first 12 chars)
- [x] Handle error cases

### Task 5: Add delete_memory summarizer
- [x] Create `summarize_delete_memory_result()` function
- [x] Handle success case ("Memory deleted")
- [x] Handle failure cases (not found, unauthorized)
- [x] Register in `SUMMARIZERS` registry

### Task 6: Verify integration
- [x] Run syntax check on modified files
- [x] Verify prompt builds correctly with all sections
- [x] Test summarizers with sample data

---

## Dependencies

### Blocking
- Story 14.3 (delete_memory tool) - Tool must exist before summarizer needed

### Non-Blocking
- Story 14.1 (store_memory schema update) - Schema changes inform summarizer updates
- Story 14.2 (store_memory handler update) - Handler changes inform response format

---

## Test Cases

### Unit Tests

1. **test_memory_management_section_content**
   - Verify MEMORY_MANAGEMENT_SECTION contains required guidance
   - Check for store_memory, delete_memory, retrieve_memories mentions

2. **test_tool_usage_instructions_content**
   - Verify TOOL_USAGE_INSTRUCTIONS includes delete_memory
   - Check for user_id placeholder

3. **test_build_system_prompt_includes_memory_section**
   - Call build_system_prompt() with user_id
   - Verify output contains MEMORY_MANAGEMENT_SECTION content

4. **test_summarize_store_memory_success**
   - Input: `{"status": "success", "memory_id": "abc123...", "message": "ok", "storage": {...}}`
   - Expected: "Memory saved (abc123...)"

5. **test_summarize_store_memory_error**
   - Input: `{"status": "error", "message": "Validation failed"}`
   - Expected: "Validation failed"

6. **test_summarize_delete_memory_success**
   - Input: `{"status": "success", "deleted": true, "memory_id": "xyz", "message": "ok"}`
   - Expected: "Memory deleted"

7. **test_summarize_delete_memory_not_found**
   - Input: `{"status": "error", "deleted": false, "memory_id": "xyz", "message": "Memory not found"}`
   - Expected: "Delete failed: Memory not found"

8. **test_summarize_delete_memory_unauthorized**
   - Input: `{"status": "error", "deleted": false, "memory_id": "xyz", "message": "Unauthorized"}`
   - Expected: "Delete failed: Unauthorized"

---

## Acceptance Criteria Traceability

| AC ID | Task | Test Case |
|-------|------|-----------|
| AC #1 | Task 1 | test_memory_management_section_content |
| AC #2 | Task 2 | test_tool_usage_instructions_content |
| AC #3 | Task 3 | test_build_system_prompt_includes_memory_section |
| AC #4 | Task 4, 5 | test_summarize_* tests |

---

## Dev Notes

### Token Impact
- MEMORY_MANAGEMENT_SECTION: ~300 tokens (fixed, always present)
- Acceptable trade-off for improved memory tool usage

### Placement in System Prompt
The memory management section should be placed after the proactive capabilities section but before user-specific context (profile, portfolio, triggers). This ensures the LLM understands memory tool usage before seeing user data.

**Order:**
1. BASE_SYSTEM_PROMPT
2. PROACTIVE_CAPABILITIES_SECTION
3. MEMORY_MANAGEMENT_SECTION (NEW)
4. User ID
5. USER PROFILE
6. USER PORTFOLIO
7. ACTIVE TRIGGERS
8. Datetime
9. Platform formatting
10. TOOL_USAGE_INSTRUCTIONS

### Summarizer Consistency
The summarizers should follow the existing pattern:
- Concise output (<50 chars when possible)
- Handle error cases with message extraction
- Truncate long messages at 500 chars

---

## References

- Epic: `docs/epics/epic-14-direct-memory-storage.md`
- Tech Spec: `.bmad-ephemeral/stories/tech-spec-epic-14.md`
- Existing prompts: `backend/api/prompts.py`
- Existing summarizers: `backend/api/status_summarizers.py`
