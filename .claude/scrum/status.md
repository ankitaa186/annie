# Sprint Status
Last Updated: 2026-04-16 (session, 22.2.2 wave) by Fenny-as-proxy

## Project
- Name: Annie (Personal AI Companion)
- Tech Stack: Python 3.12+ / FastAPI / Redis / Docker Compose / React+Vite (web) / Grok-4+ChatGPT-5+Gemini
- Test Command: make test
- Build Command: make start

## Implementation Status Overview

### Completed Epics
- Epic 1: Foundation & Infrastructure (Stories 1.1-1.6) - DONE
- Epic 2: Core Chat & LLM Integration (Stories 2.1-2.7) - DONE
- Epic 3: Memory & Persistence (Stories 3.1-3.2) - DONE
- Epic 4: Decision Support Tools - Story 4.1 (Grok Live Search) - DONE
- Epic 5: Telegram Bot Interface (Stories 5.1-5.3) - DONE
- Epic 7: User Profile & Personalization (Stories 7.1-7.2) - DONE
- Epic 8: Langfuse Integration - DONE
- Epic 9: Gemini Provider - DONE
- Epic 13: Proactive AI - DONE
- Epic 14: Direct Memory Storage - DONE
- Epic 15: Extended MCP Tools - DONE
- Epic 16: Home Assistant Integration - DONE
- Epic 17: Cloud Logging (Loki) - DONE
- Epic 18: File Context Sharing - DONE

### Remaining / Draft Epics
- Epic 6: Integration & Quality (Testing, E2E, Docs) - NOT STARTED
- Epic 10: Portfolio Management - DRAFT
- Epic 11: Real-time Status Updates - DRAFT
- Epic 12: Memory Storage Enhancements - DRAFT
- Epic 19: Adaptive Context & Persona Modulation - DRAFT (High Priority)
- Epic 20: Web UI - PARTIAL (scaffolded, needs completion)
- Epic 21: WhatsApp Integration - DRAFT
- Epic 22: Session Context Continuity - IN PROGRESS (P0) — 22.1/22.2/22.3 done; 22.2.1 follow-on (30-day TTL + history fetch) this wave; 22.4 reshaped (structured-aggregation only); 22.5 deferred
- Story 4.2: Stock Trader Tool - Market Analysis - NOT STARTED
- Story 4.3: Stock Trader Tool - Personalized Recommendations - NOT STARTED

## Epic 22: Session Context Continuity

- Status: 22.1/22.2/22.3 done; 22.4/22.5 deferred
- Priority: P0
- Created: 2026-04-16
- Owner: Disha (product), Parminder (tech), David (impl), Harpreet (review), Murat (test)
- Doc: docs/epics/epic-22-session-context-continuity.md

### Story 22.1: Always-inject cached rolling summary
- Status: done (awaiting Ankit's review/merge)
- Assigned: David/Harpreet/Murat (Fenny-as-proxy this session)
- Priority: P0
- Size: S (~40 LOC)
- Dependencies: none
- Review Cycles: 0
- Acceptance Criteria:
  - [ ] `build_llm_context` injects cached `conversation:{id}:summary` as a system message regardless of token budget, when present
  - [ ] Injection framed as `[Earlier conversation summary]` (matches existing overflow path string)
  - [ ] No double-injection when overflow path also fires
  - [ ] Existing overflow/summary-refresh logic still works
  - [ ] Unit test covers: (a) summary present + short context injects once; (b) no summary cached → no injection; (c) overflow path still injects without duplication
- Notes: Already-maintained `conversation:{id}:summary` cache; current code injects only on >20k-token overflow. Pruning keeps context small so injection almost never fires — load-bearing gap.

### Story 22.2: Daily scratchpad `[CURRENT_DAY_CONTEXT]`
- Status: done (awaiting Ankit's review/merge); superseded by 22.2.1 (TTL+history) and 22.2.2 (free-form keys).
- Assigned: David/Harpreet/Murat (Fenny-as-proxy this session)
- Priority: P0
- Size: M (~200 LOC)
- Dependencies: none
- Review Cycles: 0
- Acceptance Criteria (as shipped post-22.2.2):
  - [ ] Redis key `daily_context:{user_id}:{YYYY-MM-DD Pacific}` with 30-day-rolling TTL (22.2.1)
  - [ ] Free-form keys validated by `^[a-z][a-z0-9_]{0,31}$`; per-day 20-key cap; per-key 2000-char cap (22.2.2)
  - [ ] New MCP tool `update_daily_context(user_id, key, value)` in `mcp_server/tools/` registered via `server.py`
  - [ ] New helper in `backend/api/daily_context.py` (sibling module) to read+format scratchpad for prompt
  - [ ] `build_system_prompt` renders `[CURRENT_DAY_CONTEXT]` section when scratchpad non-empty
  - [ ] `routes/stream.py` loads scratchpad and passes to `build_system_prompt`
  - [ ] Unit test covers: write → read round-trip; free-form key accepted (e.g., `house_hunting`); empty scratchpad gives no prompt section; blank value clears a key from prompt
- Notes: Original slot design (6 enum values) was generalized in 22.2.2 to accept any LLM-chosen semantic key. The previous names remain valid and are suggested as common examples.

### Story 22.2.1: 30-day rolling TTL + historical fetch tool + language sweep
- Status: done (awaiting Ankit's review/merge)
- Assigned: David/Harpreet/Murat (Fenny-as-proxy this session)
- Priority: P0
- Size: S (~150 LOC)
- Dependencies: 22.2
- Review Cycles: 0
- Acceptance Criteria:
  - [ ] TTL extended from "next Pacific midnight" to 30 days past the Pacific midnight of the date in the key (fixed per-key horizon, not rolling-on-write). Helper: `eviction_epoch_for_pacific_date(date_str)`.
  - [ ] New MCP tool `get_daily_context(user_id, date?, days_ago?)` registered via `server.py` — exactly one of `date` (YYYY-MM-DD) or `days_ago` (0-30) required. Returns `{status:success, scratchpad, found}` on hit, `{status:success, scratchpad:null, found:false}` on miss.
  - [ ] Prompt-injection behavior unchanged: `[CURRENT_DAY_CONTEXT]` still shows TODAY only. Past days accessible via the new tool only.
  - [ ] Prompt guidance updated: decision-tree references `get_daily_context` for past-day questions; explicit "say you don't have the scratchpad, don't hallucinate" when `found:false`.
  - [ ] Language sweep: "session-scoped" replaced with "day-scoped" / "today-only" (prompt) and "30-day rolling" (storage) across `daily_context.py` (mcp + backend), `prompts.py`, epic doc, and tests. "session-scoped" is gone from the codebase (except Epic 19's unrelated 2-hour TTL).
  - [ ] Unit tests cover: TTL computation for a given date (incl. DST boundaries), new tool validation (mutual exclusion, range, malformed date, future date), history fetch with hit / miss / corrupt JSON / Redis error, days_ago=0 equals today.
  - [ ] All previously-passing tests still green (459 backend + 478 mcp).
- Notes: 22.4 was considered for subsumption but **reshaped instead**: 22.4 remains P1 deferred and now scopes to structured-aggregation entries (workout counts, sleep averages, weight trend) — free-text daily state is wholly owned by the scratchpad post-22.2.1. Epic doc updated.

### Story 22.3: Rewrite `store_memory` prompt guidance
- Status: done (awaiting Ankit's review/merge)
- Assigned: David/Harpreet/Murat (Fenny-as-proxy this session)
- Priority: P0
- Size: S (prompt-only, ~50 LOC of prompt text)
- Dependencies: 22.2 (references scratchpad by name)
- Review Cycles: 0
- Acceptance Criteria:
  - [ ] `backend/api/prompts.py:271-320` `MEMORY_MANAGEMENT_SECTION` rewritten
  - [ ] Remove "background extraction handles this" framing
  - [ ] Replace with decision tree: day-scoped → scratchpad; permanent → store_memory; never "I don't know" without consulting `[CURRENT_DAY_CONTEXT]` then `[Earlier conversation summary]` (and `get_daily_context` for past-day questions, added in 22.2.1)
  - [ ] Existing unit tests in `backend/tests/unit/test_prompts.py` still pass (update assertions that probe the old text)
- Notes: Sequenced after 22.2 write (both touch prompts.py); 22.3 rewrites a bounded region so conflict risk is low.

### Story 22.2.2: Generalize scratchpad — drop slot enum, free-form keys
- Status: done (awaiting Ankit's review/merge)
- Assigned: David/Harpreet/Murat (Fenny-as-proxy this session)
- Priority: P0
- Size: S (~80 LOC)
- Dependencies: 22.2, 22.2.1
- Review Cycles: 0
- Acceptance Criteria:
  - [ ] `ALLOWED_SLOTS` enum and `DAILY_CONTEXT_SLOTS` tuple removed from prod code. MCP tool schema uses `pattern`/`maxLength` on `key`, not `enum`.
  - [ ] Parameter renamed `slot` → `key` in handler, schema, description.
  - [ ] Key validator `^[a-z][a-z0-9_]{0,31}$`. Rejects uppercase/whitespace/punctuation/emoji/leading-digit with a clear error message.
  - [ ] Per-day key-count cap (20 keys). NEW keys rejected at cap with `KEY_LIMIT_EXCEEDED` and list of currently-set keys for the LLM to consolidate into. Updates to existing keys always allowed.
  - [ ] `format_for_prompt` renders dict in insertion order; blank/empty/whitespace values stripped (serves as the CLEAR mechanism).
  - [ ] Prompt guidance in `MEMORY_MANAGEMENT_SECTION` updated: free-form snake_case, reuse-don't-proliferate, non-enum examples (house_hunting, trip_plans, debugging, pet_medication), clear via empty string.
  - [ ] Epic doc §22.2 rewritten to document 22.2.2 follow-on scope.
  - [ ] All pre-existing tests pass; new tests cover arbitrary keys, invalid key rejection, 20-key cap, insertion-order rendering, clear mechanism.
- Notes: No schema migration — prior keys (meals / schedule / etc.) all pass the new validator. 22.4 rationale unchanged (numeric aggregation is still 22.4's job, scratchpad is still prose).

### Story 22.4: update_daily_log tool — DEFERRED + RESHAPED (not this wave)
- Status: draft (reshape landed 2026-04-16; see epic doc §22.4)
- Scope narrowed: structured entries only (workout/weight/sleep/meal_macros/mood_score). Free-text daily state removed — owned by scratchpad post-22.2.1.
- Priority: P1. Unblocks when Ankit starts serious recomp aggregation queries.
### Story 22.5: Pre-generation memory RAG prefetch — DEFERRED (not this wave; 22.5 revised finding on bus re: memory_client.stream_message)

## Backlog
Epic 22 in flight (22.1/22.2/22.3). 22.4/22.5 deferred to a later wave.

## Session Note
Agent tool unavailable this session (confirmed via ToolSearch — same constraint as bus 14:25). Fenny is running waves 1-4 as Fenny-as-proxy with clearly labeled role hats per change.
