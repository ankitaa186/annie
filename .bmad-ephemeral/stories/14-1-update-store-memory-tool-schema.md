# Story 14.1: Update store_memory Tool Schema

Status: completed

## Story

**As a** developer,
**I want** the store_memory tool to accept pre-formatted memory content with optional typed fields,
**So that** the LLM can directly store critical memories without the 60-100 second extraction pipeline delay.

**Epic:** Epic 14 - Direct Memory Storage Enhancement
**Prerequisites:** agentic-memories `/v1/memories/direct` endpoint available
**Estimated Effort:** 2 hours

## Acceptance Criteria

### AC #1: Schema accepts `content` field instead of `history`
**Given** the store_memory tool is called
**When** the LLM provides memory content
**Then** the tool accepts a `content` field (string, required) instead of the old `history` array

**Mapped to Tasks:** Task 1

---

### AC #2: Schema includes optional episodic fields
**Given** the store_memory tool schema is defined
**When** storing an episodic memory (event with time/place/people)
**Then** the schema includes optional fields:
- `event_timestamp` (datetime) - When the event occurred
- `location` (string) - Where it happened
- `participants` (array of strings) - Who was involved

**Mapped to Tasks:** Task 1

---

### AC #3: Schema includes optional emotional fields
**Given** the store_memory tool schema is defined
**When** storing a memory with emotional context
**Then** the schema includes optional fields:
- `emotional_state` (string) - e.g., "happy", "anxious"
- `valence` (float) - -1.0 to 1.0 (negative to positive)
- `arousal` (float) - 0.0 to 1.0 (calm to excited)

**Mapped to Tasks:** Task 1

---

### AC #4: Schema includes optional procedural fields
**Given** the store_memory tool schema is defined
**When** storing a skill or procedure memory
**Then** the schema includes optional fields:
- `skill_name` (string) - Name of the skill/procedure
- `proficiency_level` (string) - e.g., "beginner", "intermediate", "expert"

**Mapped to Tasks:** Task 1

---

### AC #5: Default values work correctly
**Given** the store_memory tool is called with minimal required fields
**When** optional fields are not provided
**Then** the tool uses sensible defaults:
- `importance`: 0.8 (high importance for explicit storage)
- `layer`: "semantic" (persistent memory layer)
- `persona_tags`: [] (empty array)

**Mapped to Tasks:** Task 1

---

### AC #6: LLM-readable descriptions guide proper tool usage
**Given** the store_memory tool schema
**When** the LLM reads the tool description
**Then** the descriptions clearly explain:
- When to use the tool (critical, explicit memories only)
- What each field means
- That background extraction handles routine info

**Mapped to Tasks:** Task 1

---

## Tasks / Subtasks

### Task 1: Update store_memory Tool Schema
**Status:** DONE
**Acceptance Criteria:** AC #1, AC #2, AC #3, AC #4, AC #5, AC #6

**Implementation Details:**

Update the `store_memory_tool` definition in `mcp_server/tools.py` (lines 263-310) to use the new schema.

**Current Schema (to be replaced):**
```python
store_memory_tool = {
    "name": "store_memory",
    "description": "Store conversation transcript in agentic-memories service...",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {"type": "string", ...},
            "history": {"type": "array", ...},  # REMOVE
            "metadata": {"type": "object", ...}
        },
        "required": ["user_id", "history"]  # CHANGE to ["user_id", "content"]
    }
}
```

**New Schema:**
```python
store_memory_tool = {
    "name": "store_memory",
    "description": """Store a critical memory directly in agentic-memories service.

IMPORTANT: Only use this tool for CRITICAL information that:
1. User explicitly asks you to remember ("Remember that I...", "Don't forget...")
2. Is a permanent preference/constraint ("I'm allergic to...", "Never recommend...")
3. Is a life-changing decision with lasting impact
4. Would be dangerous to forget (medical conditions, safety constraints)

DO NOT use for routine information - background extraction handles that automatically.

Examples of good uses:
- "User is severely allergic to shellfish - carries EpiPen"
- "User's risk tolerance is conservative - never recommend high-risk investments"
- "User's mother passed away in March 2024 - sensitive topic"

Examples of bad uses (handled by background extraction):
- Daily activities or routine conversations
- Temporary preferences or moods
- Information already in their profile
- Topics just discussed""",
    "inputSchema": {
        "type": "object",
        "properties": {
            # Required fields
            "user_id": {
                "type": "string",
                "description": "User identifier for memory storage"
            },
            "content": {
                "type": "string",
                "description": "Pre-formatted memory content to store. Should be a clear, complete statement of what to remember.",
                "maxLength": 5000
            },

            # General fields (always stored in ChromaDB)
            "importance": {
                "type": "number",
                "description": "Importance level from 0.0 to 1.0. Higher values = more critical. Default: 0.8",
                "minimum": 0.0,
                "maximum": 1.0,
                "default": 0.8
            },
            "layer": {
                "type": "string",
                "description": "Memory layer for storage. Default: 'semantic' (persistent).",
                "enum": ["short-term", "semantic", "long-term"],
                "default": "semantic"
            },
            "persona_tags": {
                "type": "array",
                "description": "Tags for memory categorization. Max 10 tags.",
                "items": {"type": "string"},
                "maxItems": 10,
                "default": []
            },
            "metadata": {
                "type": "object",
                "description": "Optional metadata (source, conversation_id, trigger)",
                "properties": {
                    "source": {"type": "string"},
                    "conversation_id": {"type": "string"},
                    "trigger": {"type": "string"}
                }
            },

            # Optional episodic fields -> triggers episodic_memories write
            "event_timestamp": {
                "type": "string",
                "format": "date-time",
                "description": "When the event occurred (ISO 8601). Include for episodic memories (events with time/place)."
            },
            "location": {
                "type": "string",
                "description": "Where the event happened. Used with event_timestamp for episodic memories."
            },
            "participants": {
                "type": "array",
                "description": "Who was involved in the event. Used with event_timestamp for episodic memories.",
                "items": {"type": "string"}
            },

            # Optional emotional fields -> triggers emotional_memories write
            "emotional_state": {
                "type": "string",
                "description": "Primary emotional state (e.g., 'happy', 'anxious', 'excited'). Include for emotionally significant memories."
            },
            "valence": {
                "type": "number",
                "description": "Emotional valence from -1.0 (negative) to 1.0 (positive). Used with emotional_state.",
                "minimum": -1.0,
                "maximum": 1.0
            },
            "arousal": {
                "type": "number",
                "description": "Emotional arousal from 0.0 (calm) to 1.0 (excited). Used with emotional_state.",
                "minimum": 0.0,
                "maximum": 1.0
            },

            # Optional procedural fields -> triggers procedural_memories write
            "skill_name": {
                "type": "string",
                "description": "Name of skill or procedure being learned. Include for how-to or skill memories."
            },
            "proficiency_level": {
                "type": "string",
                "description": "User's proficiency level. Used with skill_name.",
                "enum": ["beginner", "intermediate", "advanced", "expert"]
            }
        },
        "required": ["user_id", "content"]
    },
    "handler": store_memory_tool_handler
}
```

**Technical Notes:**
- The handler function (`store_memory_tool_handler`) will be updated in Story 14.2 to call the new `/v1/memories/direct` endpoint
- This story only updates the schema - the handler changes come in Story 14.2
- The `history` field is replaced entirely by `content` - no backward compatibility needed since the old endpoint was too slow to be usable
- Default values (`importance=0.8`, `layer="semantic"`) must be applied in the handler when fields are not provided

**Storage Routing (handled by agentic-memories):**
- ChromaDB (always) - includes stored_in_* flags for deletion tracking
- episodic_memories (if event_timestamp provided)
- emotional_memories (if emotional_state provided)
- procedural_memories (if skill_name provided)

**Subtasks:**
- [x] Remove `history` field from schema
- [x] Add `content` field (required, string, max 5000 chars)
- [x] Add `importance` field with default 0.8
- [x] Add `layer` field with default "semantic"
- [x] Add `persona_tags` field with default []
- [x] Add episodic fields: event_timestamp, location, participants
- [x] Add emotional fields: emotional_state, valence, arousal
- [x] Add procedural fields: skill_name, proficiency_level
- [x] Update tool description with usage guidance
- [x] Update required fields to ["user_id", "content"]
- [x] Verify schema is valid JSON Schema

---

## Definition of Done

- [x] Task 1 completed
- [x] All 6 acceptance criteria validated with evidence
- [x] `store_memory` tool schema updated in `mcp_server/tools.py`
- [x] `history` field removed from schema
- [x] `content` field added as required
- [x] Optional episodic fields added (event_timestamp, location, participants)
- [x] Optional emotional fields added (emotional_state, valence, arousal)
- [x] Optional procedural fields added (skill_name, proficiency_level)
- [x] Default values documented (importance=0.8, layer="semantic")
- [x] Tool description includes usage guidance for LLM
- [x] Schema validates correctly
- [x] No regressions in other MCP tools

---

## Dev Notes

### Architecture Context

**Component Overview:**
- **store_memory tool** (`mcp_server/tools.py`): MCP tool for storing memories
- **agentic-memories service** (External): Persistent memory storage
- **New endpoint**: `POST /v1/memories/direct` (bypasses LangGraph extraction)

**Current Flow (Slow - 60-100s):**
```
LLM -> store_memory tool -> /v1/store -> LangGraph Pipeline -> Storage
```

**New Flow (Fast - 1-2s):**
```
LLM -> store_memory tool -> /v1/memories/direct -> Direct Storage
```

**Schema Changes Summary:**

| Field | Current | New | Notes |
|-------|---------|-----|-------|
| user_id | Required | Required | No change |
| history | Required (array) | REMOVED | Replaced by content |
| content | N/A | Required (string) | New field |
| importance | N/A | Optional (default: 0.8) | New field |
| layer | N/A | Optional (default: "semantic") | New field |
| persona_tags | N/A | Optional (default: []) | New field |
| metadata | Optional | Optional | Unchanged |
| event_timestamp | N/A | Optional | Episodic trigger |
| location | N/A | Optional | Episodic |
| participants | N/A | Optional | Episodic |
| emotional_state | N/A | Optional | Emotional trigger |
| valence | N/A | Optional | Emotional |
| arousal | N/A | Optional | Emotional |
| skill_name | N/A | Optional | Procedural trigger |
| proficiency_level | N/A | Optional | Procedural |

### Technical Constraints

1. **Schema Validation:**
   - JSON Schema draft-07 compatible
   - `maxLength` for content: 5000 characters
   - `maxItems` for persona_tags: 10
   - Numeric ranges enforced (importance 0-1, valence -1 to 1, arousal 0-1)

2. **Backward Compatibility:**
   - None required - old endpoint was unusably slow (60-100s)
   - Clean break to new schema

3. **Handler Compatibility:**
   - This story updates schema only
   - Handler changes in Story 14.2 to call new endpoint
   - Handler must apply defaults when fields not provided

### Dependencies

**Blocking:**
- None for schema update (handler update in Story 14.2)

**Non-Blocking:**
- agentic-memories `/v1/memories/direct` endpoint (needed for Story 14.2)

### Key Files to Modify

**Files to Modify:**
- `mcp_server/tools.py` (lines 263-310) - Update store_memory_tool schema

**Reference Files:**
- `.bmad-ephemeral/stories/tech-spec-epic-14.md` - Epic 14 technical specification
- `docs/epics/epic-14-direct-memory-storage.md` - Epic overview and story details

### Testing Strategy

**Unit Tests:**
- Validate schema structure
- Validate field types and constraints
- Validate required vs optional fields
- Validate enum values (layer, proficiency_level)
- Validate numeric ranges

**Integration Tests:**
- Verify schema appears correctly in `tools/list` MCP response
- Verify LLM can read and understand the schema

### Success Metrics

- Schema updated with all new fields
- Tool description clearly guides LLM usage
- Schema validates as proper JSON Schema
- `tools/list` returns updated schema

---

## References

1. **Epic 14 Technical Specification** (`.bmad-ephemeral/stories/tech-spec-epic-14.md`)
   - Lines 70-99: store_memory Input Schema (Updated)
   - Lines 311-316: AC-14.1 acceptance criteria

2. **Epic 14 Overview** (`docs/epics/epic-14-direct-memory-storage.md`)
   - Lines 82-143: Story 14.1 details
   - Lines 100-127: New schema specification

3. **Current Implementation** (`mcp_server/tools.py`)
   - Lines 263-310: Current store_memory_tool definition

---

**Created:** 2025-12-29
**Epic:** Epic 14 - Direct Memory Storage Enhancement
**Story:** 14.1 - Update store_memory Tool Schema
**Status:** drafted

---

## Dev Agent Record

### Context Reference

**Story Context XML:** `.bmad-ephemeral/stories/14-1-update-store-memory-tool-schema.context.xml`

Generated: N/A (not needed - direct implementation)
Generated by: N/A
Contains: N/A

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

N/A

### Completion Notes List

1. **Schema Update Completed** (2025-12-29): Updated `store_memory_tool` schema in `mcp_server/tools.py`:
   - Removed `history` array field (old conversation-based approach)
   - Added `content` field as required string (max 5000 chars) for pre-formatted memory
   - Added general fields: `importance` (default 0.8), `layer` (default "semantic"), `persona_tags` (default [])
   - Added episodic fields: `event_timestamp`, `location`, `participants`
   - Added emotional fields: `emotional_state`, `valence`, `arousal`
   - Added procedural fields: `skill_name`, `proficiency_level`
   - Updated tool description with clear LLM guidance for when to use the tool

2. **Handler Signature Updated** (2025-12-29): Updated `store_memory_tool_handler` function signature to accept new parameters with defaults. Handler still calls `/v1/store` endpoint (endpoint change deferred to Story 14.2).

3. **Tests Updated** (2025-12-29): Completely rewrote `mcp_server/tests/test_store_memory_tool.py`:
   - Added tests for new content-based schema
   - Added tests for all episodic, emotional, and procedural fields
   - Added tests for default values (importance=0.8, layer="semantic", persona_tags=[])
   - Added comprehensive schema validation tests
   - All 27 handler tests and 14 schema tests cover the acceptance criteria

### File List

**Modified Files:**
- `/Users/ankit/dev/annie/mcp_server/tools.py` - Updated store_memory_tool schema and handler
- `/Users/ankit/dev/annie/mcp_server/tests/test_store_memory_tool.py` - Updated tests for new schema
- `/Users/ankit/dev/annie/.bmad-ephemeral/stories/14-1-update-store-memory-tool-schema.md` - This story file
