# Sprint Status
Last Updated: 2026-04-25 (Story 23.1 testing approved by Murat — done, awaiting Ankit's merge/push)

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
- Epic 23: Cost & Observability Hardening - IN PROGRESS (P0) — 23.1 drafted (provider token counting fix); kicked off after 30-day Gemini reconciliation found ~88% undercount
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

## Epic 23: Cost & Observability Hardening

- Status: IN PROGRESS (23.1 drafted)
- Priority: P0
- Created: 2026-04-25
- Owner: Disha (product), Parminder (tech), David (impl), Harpreet (review), Murat (test)
- Theme: Make Annie's spend numbers trustworthy enough to base budget alarms / soft caps / auto-shutoff on. Reconciliation 2026-03-26→04-25 found Annie recorded $12.19 vs Google billed ~$100 (-88%). Cost tracking is the load-bearing input for any future cost-safety machinery; right now it would fail silently long before any guardrail fires. This epic absorbs follow-ons: budget alerts, soft-cap throttling, monthly reconciliation tooling, and per-user cost attribution.

### Story 23.1: Fix provider token counting in streaming providers
- Status: done (Murat approved 2026-04-25 — awaiting Ankit's merge/push; +24h/+7d/+30d watchdog plan in bus)
- Assigned: David (implementation)
- Priority: P0
- Size: M (~250-400 LOC across 3 prod files + 1 reconciliation script + tests)
- Dependencies: none (independent of David's Class C cross-provider history bug; can land in either order — see Notes for sequencing guidance)
- Review Cycles: 0
- User Problem: Annie's recorded Gemini spend is ~88% lower than Google's actual bill ($12.19 vs ~$100 over 30 days). Output tokens are recorded as the **stream-chunk count** (a 1,031-char real reply was logged as `completionTokens: 16`, ~50x undercount). Error/429 paths short-circuit tracing entirely (last 3 days have ZERO Gemini observations despite the cap-trip burst that pushed Google to $100). This makes cost data unusable as the basis for budget alarms, soft caps, or any future auto-shutoff. Without trustworthy cost numbers, Ankit cannot safely scale Annie's usage or extend access to others.

- Acceptance Criteria:
  - [ ] **AC1 — Gemini token source corrected.** In `backend/api/providers/gemini_provider.py`, both Langfuse-tracking blocks (lines ~685-740 streaming-text path; lines ~1034-1086 function-call path) read `prompt_tokens` and `completion_tokens` from the final stream chunk's `usage_metadata` (`prompt_token_count`, `candidates_token_count`). Lines 641 and 1037 (`token_count += 1` per chunk) are removed or repurposed for non-cost telemetry only. Verify: a unit test feeding a mock stream where the final chunk has `usage_metadata(prompt_token_count=1234, candidates_token_count=567)` must produce a Langfuse generation with `usage.input=1234, usage.output=567`, regardless of how many chunks were emitted.
  - [ ] **AC2 — Pre-stream `count_tokens()` round-trip removed.** The separate `client.count_tokens()` call at `gemini_provider.py:~689` is deleted. Input tokens come exclusively from the final chunk's `usage_metadata.prompt_token_count`. Verify: grep for `count_tokens` in `gemini_provider.py` returns zero matches in the streaming code path; existing tests still pass.
  - [ ] **AC3 — Gemini fallback when `usage_metadata` absent.** If the final stream chunk lacks `usage_metadata` (defensive — SDK contract change, malformed response, mid-stream abort), the generation is still emitted to Langfuse with `usage=None` and a structured log line `event="usage_metadata_missing"` at WARNING level including conversation_id, model, and chunk_count. We do NOT fall back to chunk-counting for cost. Verify: unit test with a stream that never emits `usage_metadata` produces (a) a Langfuse generation with null usage, (b) a single WARNING log with `event="usage_metadata_missing"`, (c) no exception raised to caller.
  - [ ] **AC4 — ChatGPT `stream_options.include_usage=true` enabled.** In `backend/api/providers/chatgpt_provider.py` (the streaming completion call site, currently around line 543's usage block), the OpenAI streaming request sets `stream_options={"include_usage": True}`. The final chunk's `usage` block is read for `prompt_tokens` and `completion_tokens`. The chunk-count fallback at line 543 (`usage.get("completion_tokens", token_count)`) is replaced with the same null-and-warn behavior as AC3. Verify: unit test with mock OpenAI stream emitting a final chunk with `usage={prompt_tokens:1000, completion_tokens:500}` produces a generation recorded with those exact values; mock stream WITHOUT `usage` produces null-usage generation + WARNING `event="usage_metadata_missing"`.
  - [ ] **AC5 — Error-path tracing for 4xx/5xx.** When the provider raises (rate limit / quota / network / 5xx), Langfuse still receives a `generation.end()` call before the exception propagates. The generation has: `level="ERROR"`, `status_message=<exception class + truncated message>`, `usage` populated from `usage_metadata` if the SDK delivered it before the failure (Gemini's 429 sometimes does after prompt-processing), else null. The orchestrator's existing exception handling is unchanged — this is a `try/finally` around `generation.end()`, not a swallowing catch. Verify: integration test mocks Gemini raising `ResourceExhausted("quota exceeded")` after one chunk; assert one Langfuse generation exists with `level="ERROR"` and the model name set. Same test for ChatGPT 429.
  - [ ] **AC6 — The Apr-04-shaped placeholder traces eliminated.** Parminder identified a separate broken path: 17 traces on Apr 4 (and similar on Apr 6) with `in=10, out=5-28` for every call — likely a placeholder-record path or a silent `count_tokens()` failure landing in the `except: pass` branch around line 1034. Inspect both Langfuse-tracking blocks; ensure no code path records hardcoded or default-zero token counts as if they were real. If the path is identified, fix it; if it's already covered by AC1/AC2/AC5, document why in the PR description. Verify: search the next 7 days of `release=annie-prod` Langfuse traces for any generation with `usage.input < 50 AND output_chars > 200` — should return zero hits. Manual spot-check, not CI.
  - [ ] **AC7 — Reconciliation tooling exists.** A new script at `scripts/cost_reconciliation.py` (Python, runnable inside any Annie service container or standalone) takes a date range and produces a per-day report comparing: Annie's Langfuse-recorded cost (REST API: `GET /api/public/observations` filtered by `type=GENERATION` and date range, summed by `cost.total_cost`), per-model token breakdown, and a column for "Google billed (manual entry)" that the operator fills from the Google Cloud Console billing detail. Output: markdown table writeable to stdout or `reports/cost_YYYY-MM-DD_to_YYYY-MM-DD.md`. The script does NOT need to integrate with Google Cloud Billing API in this story — that's a separate followup. Verify: running `python scripts/cost_reconciliation.py --start 2026-04-01 --end 2026-04-25 --output stdout` returns a markdown table; manual smoke test by Parminder.
  - [ ] **AC8 — Manual reconciliation checkpoint scheduled.** Once 23.1 is merged, Disha posts a calendar reminder for +7 days, +14 days, and +30 days post-merge to run the script and compare to Google's billing detail. Target variance at +30 days: <10% (Parminder's original AC5). At +7 and +14, variance is informational — we expect the gap to be noticeably narrower than 88% even at +7 days. If variance stays above 25% at +30 days, open a follow-up story (Story 23.2) to dig into remaining gap sources (untraced retries, count_tokens billing, etc.). This AC is satisfied by the calendar reminder being set; the reconciliation itself is done in followup work.
  - [ ] **AC9 — All existing provider tests still pass.** `backend/tests/unit/providers/` and `backend/tests/integration/` green. New tests added per ACs above.
  - [ ] **AC10 — No log-spam regression.** New WARNING-level `event="usage_metadata_missing"` does not fire for >1% of requests in the first 24h post-merge under normal traffic. If it does, that means SDK behavior is different than assumed — escalate before relying on cost data. Verify: spot-check Loki / docker logs at +24h, count of `event="usage_metadata_missing"` divided by total chat requests.

- Edge Cases:
  - Stream aborted client-side mid-response (Telegram disconnect): final chunk never arrives → AC3 fallback fires (null usage + WARNING). Acceptable — partial costs untracked but not bogus.
  - Gemini SDK retries internally and our code only sees the final result: `usage_metadata` will reflect the successful attempt's tokens, not the retried-and-failed attempts. Google bills us for ALL attempts. This is a known residual gap that the reconciliation script (AC7) will surface; not in scope for this story to eliminate.
  - Gemini 429 returns `usage_metadata` with `prompt_token_count > 0` but `candidates_token_count == 0` (prompt processed, generation refused). AC5 should record this faithfully — this is real billed prompt-processing.
  - ChatGPT-5 + tools: when the response is a tool call, the `completion_tokens` includes the tool-call JSON tokens. AC4 should still capture this correctly via `usage.completion_tokens`.
  - `release=annie-dev` vs `release=annie-prod`: tooling AC7 should accept a `--release` filter so dev traffic doesn't pollute prod reconciliation.

- Notes:
  - **Sequencing vs David's Class C story (cross-provider history corruption).** Independent — different files, different test surfaces. This story touches `gemini_provider.py:~640-740, ~1034-1086`, `chatgpt_provider.py:~540-560`, plus a new script. David's story touches `chatgpt_provider.py` message-building (different region) and likely `state.py` persistence shape. Low merge-conflict risk. Parminder's call on which lands first; my recommendation is **23.1 first** because (a) accurate cost data is a prerequisite for any future budget guardrail and (b) it's lower-risk (instrumentation only, no conversation-correctness changes).
  - **Why this is M not S.** AC1/AC2/AC4 are surgical (~30 LOC). AC5 (error-path tracing) requires `try/finally` discipline around generation.end() at multiple call sites and careful coordination with existing exception handling — easy to break. AC6 requires investigation. AC7 is a new ~150-LOC script. Tests are ~100-150 LOC. Total budget: ~250-400 LOC including the script.
  - **Why a new epic, not Story 8.X.** Epic 8 was about wiring up Langfuse infrastructure (one-time setup, DONE). This kicks off a budget-safety theme: the next stories under Epic 23 will be soft-cap alerts (e.g., warn at $50/month), per-user cost attribution, the Google Cloud Billing API integration that AC7 stops short of, and possibly an auto-shutoff. Grouping them under their own epic keeps the cost-safety thread coherent.
  - **Numbers to keep in mind.** Recorded $12.19 ≈ input cost only. Adjusted estimate with proper output counting ≈ $22. Remaining $78 gap is hypothesized (per Parminder) to come from untraced SDK-internal retries, count_tokens billing, and the cap-trip burst that backoff suppressed from tracing. AC1-AC5 should close most of this; AC7+AC8 quantifies the residual.
  - **Open question for Parminder — RESOLVED 2026-04-25.** Gemini `count_tokens()` is **likely free** (Google docs indicate count_tokens is a metadata endpoint that doesn't run the model — no input or output token billing). However, the codebase makes a SEPARATE network round-trip per stream success path (line 689) and per "ended without STOP" path (line 1040) to call `model.count_tokens(gemini_messages)` — that's a real RPC even if not metered against inference. AC2 (delete the round-trip) is the correct call regardless: (a) we're already going to have `prompt_token_count` on the final chunk's `usage_metadata` for free, (b) eliminates a latency hit and a failure mode (the `except: pass` at line 1041 silently swallows count_tokens errors, which is hypothesis #2 for the Apr-04 placeholder traces), (c) any non-zero possibility of metering goes away. So AC2 stays as written, AC8 still verifies the residual at +30. Net: don't block David on this; the architecture is right.

  - **Implementation note from Parminder for David (AC5 shape).** Wrap `generation.end()` in a `try/finally` at the call site for now — do NOT extract a context manager in this story. Rationale: the streaming path is already a deeply-nested generator (`async for chunk in stream` inside `while tool_iteration < max`), and threading a context manager through that without changing yield semantics is a refactor wider than 23.1's scope. A localized `try: ... finally: generation.end(...)` around each of the four affected blocks (gemini success, gemini ended-without-stop, gemini error, chatgpt success+error) keeps the diff bounded and reviewable. If we find ourselves writing the same finally three times, Harpreet flags it in review and we extract in a 23.1.1 follow-up. **For AC3/AC4 null-fallback shape: use `usage=None` (i.e., omit the usage dict entirely from `generation.end()`) — Langfuse v2 accepts a missing usage and renders the generation with no token/cost data, which is exactly the signal we want ("we don't know"). Do NOT pass `usage={"input":None, "output":None}` — the SDK will likely coerce to 0 and re-introduce false-zero cost rows downstream.**

## Backlog
Epic 22 in flight (22.1/22.2/22.3). 22.4/22.5 deferred to a later wave. Epic 23 kicked off 2026-04-25 — Story 23.1 ready for David (Parminder approved 2026-04-25).

## Session Note
Agent tool unavailable this session (confirmed via ToolSearch — same constraint as bus 14:25). Fenny is running waves 1-4 as Fenny-as-proxy with clearly labeled role hats per change.
