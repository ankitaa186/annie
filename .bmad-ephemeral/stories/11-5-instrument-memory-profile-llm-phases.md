# Story 11.5: Instrument Memory, Profile, and LLM Phases

Status: done

## Story

As a user,
I want to see when Annie is checking my memories and composing a response,
so that I understand the full processing pipeline.

## Acceptance Criteria

1. **AC #1: Memory Operations**
   - Retrieval: "🔍 Retrieving your memories..."
   - Retrieval complete: "✅ Found 3 relevant memories" (or "No relevant memories found")
   - Storage: "💾 Saving conversation to memory..."
   - Storage complete: "✅ Memory saved"
   - Background operations should be silent (no status for background refresh)

2. **AC #2: Profile Operations**
   - Load: "👤 Loading your profile..."
   - Load complete: "✅ Profile loaded (67% complete)"
   - Background refresh: Silent (no status emission)
   - Cache hit: Silent (no status - too fast to show)

3. **AC #3: LLM Phases**
   - Just before streaming: "🧠 Composing response..."
   - Emitted after all tool calls complete, before first token
   - Marks transition from "gathering info" to "generating answer"

4. **AC #4: Grok Live Search (if applicable)**
   - Search triggered: "🌐 Searching the web..."
   - Search complete: "✅ Found {n} sources"
   - Only emit if Grok Live Search is actually invoked

## Tasks / Subtasks

- [ ] Task 1: Instrument memory retrieval (AC: #1)
  - [ ] Add emit_status() before retrieve_memories call
  - [ ] Add emit_status() after with result count
  - [ ] Handle "no memories found" case

- [ ] Task 2: Instrument memory storage (AC: #1)
  - [ ] Add emit_status() before store_memory call
  - [ ] Add emit_status() after successful storage
  - [ ] Note: Storage often happens in background - decide if visible

- [ ] Task 3: Instrument profile loading (AC: #2)
  - [ ] Add emit_status() before profile load (if cache miss)
  - [ ] Add emit_status() after profile loaded with completeness
  - [ ] Skip status for cache hits (too fast)
  - [ ] Skip status for background refresh

- [ ] Task 4: Instrument LLM composition phase (AC: #3)
  - [ ] Add emit_status() just before LLM streaming begins
  - [ ] Place after all tool calls are complete
  - [ ] Use icon "🧠" to indicate thinking/composing

- [ ] Task 5: Instrument Grok Live Search (AC: #4)
  - [ ] Detect when Live Search is triggered
  - [ ] Emit status for search start and completion
  - [ ] Include source count in completion status

- [ ] Task 6: Write unit tests
  - [ ] Test memory retrieval status emission
  - [ ] Test memory storage status emission
  - [ ] Test profile load status (cache miss)
  - [ ] Test LLM phase status timing

## Dev Notes

### Implementation Locations

```python
# backend/api/memory.py - Memory operations
async def retrieve_relevant_memories(user_id: str, query: str):
    emit_status("Retrieving your memories...", icon="🔍")
    memories = await memory_client.retrieve(user_id, query)
    count = len(memories)
    if count > 0:
        emit_status(f"Found {count} relevant memories", icon="✅")
    else:
        emit_status("No relevant memories found", icon="✅")
    return memories

async def store_conversation_memory(user_id: str, conversation: dict):
    emit_status("Saving conversation to memory...", icon="💾")
    await memory_client.store(user_id, conversation)
    emit_status("Memory saved", icon="✅")
```

```python
# backend/api/profile.py - Profile operations
async def get_profile_for_request(user_id: str):
    cached = await redis.get(f"profile:{user_id}")
    if cached:
        # Cache hit - silent, too fast to show
        return json.loads(cached)

    emit_status("Loading your profile...", icon="👤")
    profile = await profile_client.get(user_id)
    completeness = profile.get("completeness", 0)
    emit_status(f"Profile loaded ({completeness}% complete)", icon="✅")
    await cache_profile(user_id, profile)
    return profile
```

```python
# backend/api/routes/stream.py - LLM phase
async def stream_llm_response(conversation_id: str):
    # ... tool calls happen here ...

    # Just before LLM streaming
    emit_status("Composing response...", icon="🧠")

    async for token in llm_client.stream():
        yield token
```

### Silent Operations

The following should NOT emit status:
- Profile cache hits (instant, no value in showing)
- Profile background refresh (happens async, would confuse user)
- Memory retry from Redis queue (background worker)

### Grok Live Search Detection

Grok Live Search is invoked by the LLM automatically. Detection options:

1. **Response metadata**: Check `live_search_sources_used` in response
2. **Streaming chunks**: Grok may indicate search in chunk metadata
3. **Log parsing**: Detect from structured logs (not ideal)

If detection is complex, defer to future story.

### Project Structure Notes

- Modify: `backend/api/memory.py`
- Modify: `backend/api/profile.py`
- Modify: `backend/api/routes/stream.py`
- Import: `emit_status` from `backend/api/status.py`

### Dependencies

- **Story 11.1**: Status emitter infrastructure must be complete

### Timing Considerations

Status emissions should feel natural:
- Memory retrieval: ~200-500ms - worth showing
- Profile cache miss: ~100-300ms - worth showing
- Profile cache hit: <10ms - too fast, skip
- LLM composition: Signals transition, important to show

### References

- [Source: docs/epics/epic-11-realtime-status-updates.md#Story-11.5]
- [Source: backend/api/memory.py] - Memory manager
- [Source: backend/api/profile.py] - Profile manager
- [Source: backend/api/routes/stream.py] - Streaming endpoint

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2025-12-16 | Story drafted from Epic 11 brainstorm | SM (Bob) |

## Dev Agent Record

### Context Reference

**Story Context XML:** `/home/ankit/dev/annie/.bmad-ephemeral/stories/11-5-instrument-memory-profile-llm-phases-context.xml`

This context file contains:
- Detailed technical analysis of memory.py, profile.py, and stream.py modules
- Specific code locations for status emission instrumentation
- Timing considerations for each operation type
- Implementation notes for silent vs. visible operations
- Search queries to find memory retrieval and profile loading call sites

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

### Completion Notes List

1. **Memory Retrieval Status (AC #1)**:
   - Added status emissions in `backend/api/routes/stream.py` for `retrieve_memories` MCP tool calls
   - Emits "🔍 Retrieving your memories..." before tool execution
   - Emits "✅ Found N relevant memories" or "✅ No relevant memories found" after completion
   - Status also added in `backend/api/routes/chat.py` for upfront memory retrieval (graceful no-op if no StatusContext)

2. **Memory Storage Status (AC #1)**:
   - SKIPPED: All memory storage operations run as background tasks (fire-and-forget or BackgroundTasks)
   - Per story spec: "Background operations should be silent"
   - No status emissions added for storage to avoid confusing users with async operations

3. **Profile Loading Status (AC #2)**:
   - Added status emissions in `backend/api/routes/stream.py` for `get_user_profile` MCP tool calls
   - Emits "👤 Loading your profile..." before tool execution
   - Emits "✅ Profile loaded (X% complete)" after completion with completeness percentage
   - Cache hits and background refresh remain silent per spec

4. **LLM Composition Phase (AC #3)**:
   - Added "🧠 Composing response..." status in three locations in `backend/api/routes/stream.py`:
     - Line ~203: Before Gemini streaming starts
     - Line ~389: Before OpenAI/Grok final streaming (no tool calls path)
     - Line ~668: Before max iterations fallback streaming
   - Signals transition from "gathering info" to "generating answer"

5. **Grok Live Search (AC #4)**:
   - Modified `backend/api/providers/grok_provider.py` to include `sources_used` in done event
   - Added status emission in stream.py (3 locations) when `sources_used > 0`
   - Emits "✅ Found N sources" after streaming completes
   - Includes immediate queue drain to ensure status is yielded before done event
   - No "Searching the web..." start status (API limitation - search detection only available at end)

6. **Testing**:
   - Created comprehensive test suite: `backend/tests/unit/test_story_11_5_status_phases.py`
   - 7 test cases covering all acceptance criteria
   - All tests passing (100% pass rate)
   - Tests verify status emission timing, message content, and integration scenarios

7. **Implementation Notes**:
   - Status emissions only work within StatusContext (active in stream.py)
   - emit_status() calls in chat.py are graceful no-ops (no active StatusContext)
   - Status queue draining critical for Grok Live Search status to appear before done event
   - Architecture insight: Memory/profile operations happen via MCP tool calls during streaming, not during chat endpoint processing

### File List

**Modified Files:**
- `backend/api/routes/stream.py` - Added status emissions for memory, profile, LLM composition, and Grok Live Search
- `backend/api/routes/chat.py` - Added status emissions for memory retrieval (graceful no-op fallback)
- `backend/api/providers/grok_provider.py` - Added sources_used to done event for Live Search detection
- `backend/api/memory.py` - Added import for emit_status (not used, for future non-background operations)

**Created Files:**
- `backend/tests/unit/test_story_11_5_status_phases.py` - Comprehensive test suite (7 tests, all passing)
