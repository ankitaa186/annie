# Epic: Session Context Continuity

> **Epic ID**: 22
> **Status**: Draft
> **Priority**: High (P0)
> **Estimated Effort**: 4-6 days
> **Dependencies**: None blocking. Coordinates with Epic 19 (Adaptive Context) but does not depend on it.
> **Created**: 2026-04-16
> **Owner**: Disha

---

## 1. Overview

### 1.1 Problem Statement

Annie — the running product — self-reported a "Context Horizon Gap" that her own team then validated empirically in the codebase. From Annie's own diagnosis (verbatim):

> "Middle-ground amnesia — knows deep past (long-term memory) + last few messages, but things said 2 hours ago in same session fall into a void."

> "No working scratchpad. Annie asked Ankit 'what is your schedule?' and 'what did you eat earlier?' even though they'd been talking about his day for hours. Treats a long conversation as isolated mini-chats."

The symptom is embarrassing re-asks: after hours of discussing his day, Annie prompts "what did you eat today?" as if the session had just begun. For a sole-user product where the user is doing an 8-week body recomposition and tracks meals, workouts, and schedule intra-day, this is load-bearing amnesia, not a cosmetic annoyance.

### 1.2 Empirical Root Causes (Confirmed in Code)

The team reproduced the gap by reading the code, not by inference:

1. **`_prune_tool_results` destroys older tool outputs.** In `backend/api/state.py` (~line 1025), tool outputs from turns older than ~2 user turns are replaced with stubs like `[Returned 5 results]`. Memory-retrieval payloads, web-search results, and portfolio snapshots from earlier in the same session become unreadable. **This is the heart of the amnesia** — the LLM's own prior tool outputs get shredded.

2. **Rolling summary infrastructure exists but is rarely used.** `conversation:{id}:summary` is maintained and refreshed every 10 messages. However, `build_llm_context` only injects it into the prompt when total tokens exceed ~20k — an overflow path that rarely fires because pruning (root cause #1) keeps the context small. The cached summary sits unused on normal turns, which is exactly when it would prevent amnesia.

3. **No session scratchpad.** `build_system_prompt` in `backend/api/prompts.py:1188` assembles the user profile, portfolio, triggers, and Pacific time — but zero "today's running state." There is no slot for "what the user said earlier this session."

4. **Prompt guidance actively discourages storing routine daily facts.** `backend/api/prompts.py:271-320` tells the LLM not to call `store_memory` for routine daily facts because "background extraction handles them." But the agentic-memories extraction orchestrator batches 2-8 messages before firing — so recent facts are not yet retrievable via `retrieve_memories` when the LLM needs them. The prompt trusts a pipeline whose latency it doesn't reckon with.

5. **No pre-LLM memory prefetch.** `retrieve_memories` is reactive — the LLM has to choose to call it. When it doesn't, and extraction hasn't yet ingested the fact, Annie hallucinates or re-asks.

### 1.3 Relationship to Epic 19 (Peer, Not Subsumer)

Epic 19 (Adaptive Context & Persona Modulation) is frequently invoked as "the context epic," but a close read of `docs/epics/epic-19-adaptive-context.md` shows it targets a different gap:

- **Epic 19 is about persona switching and narrative injection at session boundaries.** It fetches synthesized user narratives from agentic-memories, classifies topics (finance / emotional / maker / intimate / etc.), swaps persona (strategist / sage / beloved / builder / buddy), and rewires retrieval weights and tool priorities.
- **Epic 22 is about in-session state retention — what the user said 90 minutes ago in this same conversation.**

They are **peers**. Epic 19 solves "who is Annie being right now and which of Ankit's lifetime of memories is relevant." Epic 22 solves "what did Ankit say to Annie already today, in this very session." Shipping one does not fix the other; shipping both compounds. Epic 22 is currently the higher-leverage fix because the symptoms (re-asks, daily-log gaps) are acute and the surface area is smaller.

### 1.4 Ankit-Specific Context

This epic is explicitly scoped for a sole-user product with a specific user:

- **Ankit is 41, Intuit engineer, building Annie as his personal AI.** No multi-tenant considerations.
- **Active 8-week body recomposition.** Intra-day meal logging, workout tracking, weight, sleep, mood are load-bearing — this is the daily use case, not an edge case.
- **Latency tolerance is high (15-20s LLM turns are fine).** We can afford pre-LLM prefetch and always-injected summaries.
- **"Solve for me specifically" > "solve generically."** Daily-log slots can be concrete (meals, workout, weight, sleep, mood) rather than abstract.
- **Momentum over ceremony.** Ship the 40-LOC fix (22.1) immediately; don't gate it on the larger pieces.

### 1.5 Goals

- Eliminate in-session amnesia: facts stated earlier in the session are available for the rest of the session without requiring `retrieve_memories`.
- Provide a structured "today" view the LLM can read and write cheaply, with a natural midnight reset.
- Close the store_memory vs. background-extraction prompt contradiction that causes the LLM to trust a pipeline it shouldn't.
- Cleanly separate session-scoped state (today's scratchpad) from cross-day state (daily log) from permanent memory (agentic-memories).

### 1.6 Non-Goals

- Persona modulation. That is Epic 19's scope.
- Narrative synthesis or cross-memory summarization. That is agentic-memories' job.
- Changing the base memory architecture (Chroma / Timescale / Neo4j). Scratchpad and daily log are Annie-side Redis artifacts that complement, not replace, agentic-memories.
- Multi-user session isolation beyond what already exists (`user_id` in Redis keys).

### 1.7 Success Criteria

| Signal | Target |
|--------|--------|
| Re-ask incidents ("what did you eat?" / "what's your schedule?" after the answer was given earlier in session) | 0 in a 7-day Langfuse sample |
| Langfuse trace of a 20+ message conversation shows `[Earlier conversation summary]` injected as a system block regardless of token count | 100% of traces |
| Langfuse trace shows `[CURRENT_DAY_CONTEXT]` populated and present in the system prompt after the first intra-day fact is captured | 100% of traces post-capture |
| Cross-day queries ("how many times did I hit the gym this week?") answerable from `get_daily_log` without agentic-memories round-trip | >80% |
| No increase in p95 turn latency beyond 1s over baseline | Hold the line |

---

## 2. Story Slate

Stories are listed in ROI order. **Sequencing is deliberate** — 22.1 is a same-day ship that immediately reduces the symptom; 22.2 and 22.4 are the architectural backbone; 22.3 and 22.5 tighten the loop.

### Story 22.1 — Always-inject cached rolling summary

**Priority**: P0
**Estimated Size**: S (~40 LOC)
**Problem**: The `conversation:{id}:summary` cache is already maintained (refreshes every 10 messages) but `build_llm_context` only injects it when total tokens exceed ~20k. Because `_prune_tool_results` keeps context small, the overflow path almost never fires. The summary sits unused on exactly the turns where it would prevent amnesia.
**Scope**: In `backend/api/state.py:build_llm_context`, always inject the cached summary as a system message (e.g., framed as `[Earlier conversation summary]`) when it exists, independent of token budget. Keep the existing overflow-triggered refresh logic.
**Acceptance signal**: Langfuse trace of any 20+ message conversation shows `[Earlier conversation summary]` as an injected system block even when total tokens are well under 20k.
**Why first**: 40 lines, no new infrastructure, immediate symptom reduction. Ships regardless of the fix-#4 interpretation question below.

---

### Story 22.2 — Daily scratchpad `[CURRENT_DAY_CONTEXT]`

**Priority**: P0
**Estimated Size**: M (~200 LOC)
**Problem**: There is no "today's running state" anywhere in the prompt. The LLM has the user profile (lifetime), recent message history (last few turns), and sometimes a rolling summary — but nothing structured for "here is what we established today."
**Scope**:
- New Redis key `daily_context:{user_id}:{YYYY-MM-DD Pacific}` with TTL through next midnight Pacific.
- Structured slots: `schedule`, `meals`, `workout`, `mood`, `open_loops`, `decisions_today`.
- New MCP tool `update_daily_context(slot, value)` — LLM-callable, writes to the scratchpad.
- Read-side injection: `build_system_prompt` renders the scratchpad as a `[CURRENT_DAY_CONTEXT]` section when non-empty.
- Natural midnight reset (TTL handles this; no cron needed).
**Acceptance signal**: After "I had eggs for breakfast" and "dentist at 3pm" in the morning, asking "what did I eat?" or "what's my schedule today?" 90 minutes later answers correctly without invoking `retrieve_memories`.
**Why second**: This is the architectural backbone for "session-aware today." Every subsequent fix references it.

---

### Story 22.3 — Rewrite `store_memory` prompt guidance

**Priority**: P0
**Estimated Size**: S (prompt-only, ~50 LOC of prompt text)
**Problem**: `backend/api/prompts.py:271-320` tells the LLM not to `store_memory` for routine daily facts because "background extraction handles them." In practice, the agentic-memories extraction orchestrator batches 2-8 messages before firing, so facts stated in the last few minutes are not yet retrievable. The prompt trusts a pipeline whose latency it doesn't match, so the LLM trusts it too and then hallucinates or re-asks.
**Scope**:
- Audit the memory-guidance section of `prompts.py`.
- Remove "background extraction handles this" framing.
- Replace with a decision tree:
  - **Session-scoped fact** (today's meals, today's workout, today's schedule, today's mood) → `update_daily_context`.
  - **Permanent fact** (new preference, new goal, new biographical info) → `store_memory`.
  - **Never say "I don't know"** for something the user said earlier this session without first consulting the scratchpad (`[CURRENT_DAY_CONTEXT]`) and, failing that, the rolling summary (`[Earlier conversation summary]`).
**Acceptance signal**: Prompt no longer tells the LLM to defer to background extraction. In manual replay of the "what did you eat today?" regression, the LLM consults the scratchpad first.
**Why third**: Without this, 22.2's scratchpad gets underused because the prompt still discourages writing to it. This is the policy layer that activates the mechanism.

---

### Story 22.4 — `update_daily_log` tool

**Priority**: P1
**Estimated Size**: M (~250 LOC)
**Problem**: The scratchpad (22.2) resets at midnight. For an 8-week recomposition, Ankit needs cross-day queries: "how many times did I hit the gym this week?", "what's my average sleep this month?", "did I hit my protein target Monday through Thursday?" Today, Annie has to guess or round-trip through agentic-memories, where these facts are extracted prose and hard to aggregate.
**Scope**:
- Structured MCP tool `update_daily_log` for meal / workout / weight / sleep / mood entries.
- Redis for 30-day hot storage (fast aggregation queries).
- agentic-memories write for permanence (so >30-day history survives).
- Companion tool `get_daily_log(date_range, category)` for the LLM to answer "this week I worked out 4 times" style questions directly.
- Schema aligned with body-recomp use case (meals: timestamp + description + macros if given; workout: timestamp + type + duration; weight: timestamp + value; sleep: hours + quality; mood: scale + note).
**Acceptance signal**: Ankit asks "how many gym sessions this week?" and Annie answers from `get_daily_log` without an agentic-memories retrieval. Entries logged today also appear in the scratchpad from 22.2.
**Why fourth**: Complements 22.2 — scratchpad is "today-aware prompting," daily log is "cross-day trend analysis." Separable because 22.2 alone already solves the re-ask regression; 22.4 is what makes the recomp workflow tractable.

---

### Story 22.5 — Pre-generation memory RAG prefetch

**Priority**: P1
**Estimated Size**: M (~150 LOC, pending prereq check)
**Problem**: `retrieve_memories` is reactive — the LLM has to choose to call it. When the LLM skips the call and the fact isn't in the scratchpad (because extraction hasn't ingested it yet), Annie re-asks or hallucinates.
**Prereq check (in progress)**: Parminder is verifying whether agentic-memories' `memory_client.stream_message` already returns memory injections wired into the prompt. If yes → 22.5 collapses to a config/exposure story (surface and document what's already there). If no → build the classifier-and-prefetch path below.
**Scope (if build is needed)**:
- Pre-LLM keyword classifier over the incoming user message: keywords like `schedule`, `ate` / `eat` / `food`, `workout` / `gym`, `portfolio` / `stocks`, `meeting`, `mood`, etc.
- Classifier triggers a targeted `retrieve_memories` call before the LLM runs.
- Top 3 results injected as a `[PREFETCHED MEMORIES]` section in the prompt.
- Budget: add no more than ~2s to turn latency (we have headroom given 15-20s tolerance).
**Acceptance signal**: For a message like "what did I tell you about the Intuit offsite?" the prompt contains `[PREFETCHED MEMORIES]` with the relevant memory even if the LLM never calls `retrieve_memories` itself.
**Why fifth**: Highest-complexity, lowest-certainty — hence last. Its value also partially overlaps with 22.2+22.4 (if today's facts are already in the scratchpad, prefetch matters less). Parminder's prereq check may shrink this further.

---

## 3. Sequencing Rationale

- **22.1 ships today.** 40 LOC, no infrastructure, immediate symptom reduction. Independent of everything else. The risk of sitting on it is another week of "what did you eat today?" re-asks.
- **22.2 is the backbone.** It introduces the scratchpad that 22.3, 22.4, and 22.5 all reference. Must land before 22.3 (prompt rewrite) can point the LLM at it.
- **22.3 activates 22.2.** Without the prompt rewrite, the scratchpad exists but is underused. Sequenced right after 22.2 so the mechanism and the policy land together.
- **22.4 is parallel-safe to 22.3** once 22.2 is in. Could be picked up in parallel if David has bandwidth. Separated because its value is cross-day analytics (8-week recomp), not re-ask prevention.
- **22.5 is gated on Parminder's prereq check.** If `stream_message` already handles prefetch, this collapses to a config story. If not, full build. Either way it's last because 22.1+22.2+22.3 already kill the primary symptom.

---

## 4. Open Questions

### 4.1 What did Annie mean by "Dynamic Context Window Summarization" (fix #4)?

Annie's self-critique truncated fix #4. Both Disha and Parminder independently inferred it means "always-inject the cached rolling summary" — which is exactly what Story 22.1 does. Parminder wanted to surface this to Ankit for confirmation before shipping; the product decision (Disha) is that 22.1 ships regardless of the answer because the empirical code evidence (summary cache exists, is maintained, is almost never injected) is sufficient on its own. If Ankit later clarifies fix #4 as something different (e.g., tiered summarization, per-topic summaries), we'll file a follow-up story — but 22.1 doesn't block on it.

**Action**: Note and monitor. Do not block 22.1.

### 4.2 Prereq check for 22.5

Does agentic-memories' `memory_client.stream_message` already return memory injections that Annie wires into the prompt? Parminder is investigating in parallel. If yes, 22.5 is a config/exposure story. If no, 22.5 is a full build.

**Action**: Parminder to post findings to the bus; Disha to resize 22.5 once the answer is in.

---

## 5. Out of Scope

- **Epic 19 (persona modulation).** Topic detection, persona switching, narrative fetching, retrieval-weight rewiring. These are Epic 19's responsibilities and remain Epic 19's responsibilities.
- **Changes to the agentic-memories extraction pipeline itself.** Epic 22 works around extraction latency by providing a session-scoped scratchpad; it does not try to make extraction faster.
- **Rewriting `_prune_tool_results`.** The pruning function is doing what it was designed to do (keep context small). Epic 22 compensates for its information loss via summary injection (22.1) and scratchpad (22.2), rather than changing pruning behavior. A future story could revisit pruning if summary+scratchpad prove insufficient.
- **Multi-user session isolation.** Not needed — Annie is sole-user.

---

## 6. Dependencies

| Dependency | Required | Notes |
|------------|----------|-------|
| Redis | Yes | Scratchpad and daily-log hot storage; already in stack |
| agentic-memories | Yes (for 22.4 permanence, 22.5 prefetch) | Already in stack |
| MCP tool registry | Yes | 22.2 and 22.4 add new tools |
| Langfuse | Yes | Acceptance signals rely on trace inspection |
| Epic 19 | **No** | Peer epic — parallel safe |
