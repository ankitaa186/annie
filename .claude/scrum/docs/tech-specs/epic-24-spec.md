# Epic 23 — Story 23.2: `google.generativeai` → `google.genai` SDK migration

**Author:** Parminder
**Date:** 2026-04-25
**Status:** draft (pending Disha refinement, David/Murat sign-off on parallel research)
**Depends on:** Story 23.1 merged to remote first (rationale below)

---

## 1. Impact analysis

**Files that change:**

- `backend/api/providers/gemini_provider.py` — full rewrite of SDK call sites (~80 LOC of the 1500-line file). Logic flow stays identical; only the SDK shape changes.
- `backend/requirements.txt` — drop `google-generativeai>=0.3.0`, add `google-genai>=1.0` (latest stable).
- `backend/tests/unit/test_gemini_provider.py` — 14 patch sites (all `genai.configure` / `genai.GenerativeModel`).
- `backend/tests/unit/test_overflow_recovery.py` — 2 patch sites on `provider.model.start_chat`.
- `backend/tests/unit/test_story_23_1_token_counting.py` — 9 patch sites on `genai.configure` / `GenerativeModel` / `start_chat`. **This is the load-bearing one** — Story 23.1's invariants must survive.

**Files that DO NOT change:**

- `backend/api/providers/gemini_tool_adapter.py` — pure dict↔dict format conversion, no SDK imports. Untouched.
- `backend/api/observability/cost.py` — Annie's own cost table keyed by model-name string. SDK-independent.
- `backend/api/constants.py` — model name strings (`gemini-3.1-pro-preview`) are SDK-independent.
- All `chatgpt_provider.py` / `grok_provider.py` paths.
- The MCP tool side (`mcp_server/tools.py`) — Gemini's function-calling shape change is internal to the provider; the OpenAI-format dict that crosses the MCP boundary is unchanged.

**Breaking surfaces (zero):** the provider's external contract (`stream_chat_completion` async generator + event dict shape) does not change. No upstream consumer needs touching.

**Total LOC budget:** ~150 LOC changed across prod + tests. Net new code likely <50 LOC; the rest is replacements.

---

## 2. API surface diff (the five that matter for Annie)

| # | Concern | Old (`google.generativeai`) | New (`google.genai`) |
|---|---------|------------------------------|----------------------|
| 1 | **Import + client** | `import google.generativeai as genai`<br>`genai.configure(api_key=...)`<br>`model = genai.GenerativeModel(name, generation_config=..., safety_settings=...)` | `from google import genai`<br>`from google.genai import types`<br>`client = genai.Client(api_key=...)` — generation config / safety_settings move to **per-call** `config=types.GenerateContentConfig(...)` |
| 2 | **Streaming + chat** | `chat = model.start_chat(history=...)`<br>`response = chat.send_message(msg, stream=True, tools=tools_config)` → iterable of chunks | `chat = client.chats.create(model=..., history=..., config=...)`<br>`response = chat.send_message_stream(message=msg)` (or async via `client.aio.chats.create(...)`) — async iter of chunks. Tools live in `config`, not per-message. |
| 3 | **Function calling shape** | `chunk.candidates[0].content.parts[i].function_call.name` + `.args` (proto map → Annie's `convert_proto_to_dict` recursion) | Same path: `chunk.candidates[0].content.parts[i].function_call.name` + `.args` — but `args` is now a **plain `dict`** (pydantic-backed, not proto). The 60-line `convert_proto_to_dict` helper goes away. |
| 4 | **Function response (sending tool results back)** | `from google.ai import generativelanguage as glm`<br>`glm.Part(function_response=glm.FunctionResponse(name=, response=))` | `from google.genai import types`<br>`types.Part.from_function_response(name=..., response={...})` — and the GA-class import (`from google.ai import generativelanguage`) goes away entirely. |
| 5 | **Safety + usage_metadata** | `from google.generativeai.types import HarmCategory, HarmBlockThreshold`; safety as dict `{HarmCategory.X: HarmBlockThreshold.Y}`; `chunk.usage_metadata.prompt_token_count` / `.candidates_token_count` | Enums move to `types.HarmCategory` / `types.HarmBlockThreshold`; safety as `list[types.SafetySetting(category=..., threshold=...)]` inside `GenerateContentConfig`. Streaming `usage_metadata` field path is unchanged (final chunk carries it). |

**Other notes (not load-bearing for Annie but worth knowing):**
- `inline_data` dict shape (`{"mime_type": ..., "data": base64}`) is still accepted in the contents list — multimodal stays the way Annie writes it today.
- `count_tokens` moves to `client.models.count_tokens(model=, contents=)`. Annie deleted these in 23.1, so informational only.
- `automatic_function_calling` is **on by default** in the new SDK. Annie MUST set `automatic_function_calling={'disable': True}` in the config or the SDK will try to execute Python callables itself, bypassing Annie's MCP layer entirely. **This is a silent footgun — explicit disable is required.**
- Async path: `client.aio.chats.create(...)` exists. Worth using since `stream_chat_completion` is already `async`.

---

## 3. The thing that worries me — the function-call args type change

The old SDK delivered `part.function_call.args` as a `proto.marshal.collections.MapComposite` (or `RepeatedComposite` for arrays). Annie's `convert_proto_to_dict` (lines 666–705 of `gemini_provider.py`) is a 60-line recursive walker that special-cases proto types. **In the new SDK `args` is already a Python `dict`** — that whole helper deletes.

The risk isn't the deletion. It's that the helper currently coerces unknown proto wrappers via `str()` as a last resort. If the new SDK ever delivers a non-trivial nested type the dict-cast doesn't handle, we'd get a silent serialization failure at the `json.dumps(fc["args"])` boundary in the persistence event. The mitigation is a unit test that feeds a deeply nested function-call args (object containing array containing object) end-to-end and asserts the persisted JSON round-trips cleanly. Murat's test plan should pick this up.

---

## 4. Migration strategy — recommendation: **HARD CUT**

Two options were considered:

**Option A — Hard cut (one PR replaces both packages).**
- Pros: simpler, no env-var gating, no two-codepath test matrix, no second cleanup PR. Annie is single-tenant (Ankit), so blast radius is one user.
- Cons: if the new SDK has unexpected behavior, rollback = git revert + `make rebuild`. Acceptable for a personal-use system.

**Option B — Side-by-side (env-gated `GEMINI_SDK=legacy|new`).**
- Pros: instant rollback via env var, can validate in prod for a week before deleting legacy.
- Cons: doubles the test surface, doubles the maintenance burden until the legacy path is removed, and the new SDK's default `automatic_function_calling=True` makes the two paths semantically different in subtle ways (you'd be testing a hybrid you'll never ship). The "validate in prod for a week" benefit is illusory for a single-user system — Ankit IS the prod traffic; he can validate the same way with hard cut by just using the bot for a day.

**Pick A (hard cut).** Ankit is solo dev, single user, the deprecation warning is benign so there's no urgency forcing a rushed migration, and a clean PR is easier to review than a feature flag. If we hit a snag, `git revert` is one command. Don't over-engineer the safety net.

---

## 5. Top 5 risk areas

| # | Risk | Likelihood | Mitigation |
|---|------|-----------|------------|
| 1 | **`automatic_function_calling` default flip** — new SDK auto-executes Python callables when `tools=[fn]`. If we forget to set `disable=True`, the SDK will try to execute Annie's tool stubs locally, bypassing the MCP layer silently. Tests would still pass (no callable provided) but production would break the moment a real flow runs. | Medium | Explicit `automatic_function_calling={'disable': True}` in `GenerateContentConfig`; unit test that asserts an MCP tool call still routes through `mcp_client.call_tool(...)` (not auto-executed). |
| 2 | **Function-response shape regression** — the `glm.FunctionResponse` → `types.Part.from_function_response` swap is on the multi-turn path. If the new shape sends `response={...}` differently than the old (e.g., the old expected `response` to be a dict with arbitrary keys; the new might expect `{"result": ...}` wrapping), the LLM may receive a malformed tool result and emit `MALFORMED_FUNCTION_CALL`. Story 9.3's MALFORMED retry logic would mask this as a flaky test. | Medium | Integration-shaped test that runs a 2-turn conversation (tool call → tool response → final text), assert the second turn produces a `STOP` finish_reason, NOT `MALFORMED_FUNCTION_CALL` (value=10). |
| 3 | **Story 23.1 token-counting tests must continue to pass with the same invariants** — the 11 tests in `test_story_23_1_token_counting.py` patch `genai.configure` / `genai.GenerativeModel` / `model.start_chat`. After migration these patch sites move to `client.aio.chats.create` (or wherever the new SDK lives). Test rewrites must preserve **observable behavior**: `usage_metadata` extracted, `count_tokens` never called, `level=ERROR` generation on failure, `usage_metadata_missing` warning fired when SDK omits it. AC10's prod watchdog at +24h post-Story-23.1-merge must remain valid. | High (mechanical) | Murat owns this. The new fakes (`_FakeChat`) need a `send_message_stream` returning an async iterator instead of `send_message` returning a sync iterator. The chunk shapes (`chunk.candidates[0].content.parts[i].function_call.args` as dict) need updating. |
| 4 | **Langfuse cost calc** — Annie computes cost via `calculate_llm_cost(provider=cost_model_id, ...)` keyed by the model-name string (`gemini-3.1-pro-preview`). This is SDK-independent (Annie's own table, not Langfuse's model registry). **Low risk** — included here for explicit clearing. | Very low | Smoke check: post-migration, assert `calculate_cost({...})` returns the same dollar figures for the same token counts. One-line test. |
| 5 | **Deprecation warning origin** — the warning fires at **import time** of `google.generativeai` (it's a `DeprecationWarning` raised in the package's `__init__`). It is NOT urgent (no functionality removal yet). Rough urgency: months, not days. This frames the migration as a planned story, not a hotfix. | n/a (informational) | None — but it justifies hard-cut over env-gate; we have time to do it cleanly. |

**Risks I considered and dropped:**
- *Pricing changes* — model-name strings are unchanged, billing rides on the model name; SDK swap doesn't move pricing.
- *Multimodal regression* — the `inline_data` dict shape is still accepted in the new SDK; the converter (`_convert_messages_to_gemini_format`) builds plain dicts, so it ports as-is.
- *Safety filter behavior change* — the enum strings are the same (`HARM_CATEGORY_HARASSMENT`, `BLOCK_NONE`); only the import path and config-shape change.

---

## 6. Proposed acceptance criteria

(Disha's starter list refined; ~10 ACs total. She'll sharpen wording.)

- [ ] **AC1** — `backend/requirements.txt`: `google-generativeai` removed, `google-genai>=1.0` (or whatever stable is current at story-pickup time) added. `make rebuild` succeeds.
- [ ] **AC2** — All `import google.generativeai` / `from google.generativeai.types ...` / `from google.ai import generativelanguage` references replaced. `grep -rn "google.generativeai\|google.ai.generativelanguage" backend/` returns zero matches.
- [ ] **AC3** — `gemini_provider.py` rewritten against `google.genai`: client uses `genai.Client(api_key=...)`; streaming uses `client.aio.chats.create(...)` + `chat.send_message_stream(...)`; safety settings as `types.SafetySetting` list inside `types.GenerateContentConfig`; tool config explicitly sets `automatic_function_calling={'disable': True}`.
- [ ] **AC4** — Function-response build site uses `types.Part.from_function_response(name=, response=)` (no `glm` import).
- [ ] **AC5** — `convert_proto_to_dict` helper deleted; `function_call.args` consumed as a plain dict. New unit test: deeply-nested args (object→array→object) round-trip cleanly through `json.dumps(fc["args"])`.
- [ ] **AC6** — All Story 23.1 invariants preserved (tests `test_gemini_provider_uses_usage_metadata`, `test_gemini_provider_omits_usage_when_metadata_absent`, `test_gemini_provider_no_count_tokens_call`, `test_gemini_error_path_traces_generation`, `test_gemini_mid_stream_429_records_real_prompt_tokens` all pass after re-fixturing for the new SDK shape).
- [ ] **AC7** — Two-turn function-calling integration test: tool call emitted → tool result formatted via `types.Part.from_function_response` → second turn produces `STOP` (NOT `MALFORMED_FUNCTION_CALL`). Asserts the function-response wire shape is right.
- [ ] **AC8** — Multimodal smoke: an `inline_data` image attached to a user message still reaches the model (assert `client.aio.chats.create` receives the part in the contents). Re-uses existing multimodal test scaffolding.
- [ ] **AC9** — Cost-calc parity smoke: `provider.calculate_cost({"prompt_tokens": 1000, "completion_tokens": 500, "cached_tokens": 0})` returns the same dollar figure pre- and post-migration.
- [ ] **AC10** — Deprecation warning gone: `make logs SERVICE=backend` post-merge contains zero matches for `"google.generativeai package has ended"`.
- [ ] **AC11** — Test counts non-decreasing: backend ≥708, mcp ≥542 (Story 23.1 baseline). New tests added (AC5, AC7) increment, not replace.
- [ ] **AC12** *(optional, deferred to follow-up)* — Migrate to `client.aio.*` async path end-to-end. Annie's `stream_chat_completion` is `async` already; the sync `for chunk in response` becomes `async for chunk in ...`. Cleaner, but not required for the deprecation fix. Can defer to epic-23 follow-up.

---

## 7. Per-story breakdown (1 story is enough)

I'd recommend Disha draft this as a **single story (23.2)**, not multiple. The work is one provider rewrite — splitting it would create more PR-coordination overhead than it saves.

**Story 23.2** — Migrate Gemini provider from `google.generativeai` to `google.genai`.

**Sub-tasks:**
1. Update `requirements.txt` + `make rebuild`.
2. Rewrite `gemini_provider.__init__`: client construction + per-call config.
3. Rewrite `stream_chat_completion`: `client.chats.create` + `send_message_stream`, port the chunk-iteration loop (debug capture, safety check, function-call extraction, finish-reason logic).
4. Replace `glm.Part(function_response=...)` build site with `types.Part.from_function_response(...)`.
5. Delete `convert_proto_to_dict` helper, simplify `args` consumption.
6. Update tests in `test_gemini_provider.py`, `test_overflow_recovery.py`, `test_story_23_1_token_counting.py` — patch sites + chunk fakes.
7. Add new tests for AC5 (nested args round-trip), AC7 (two-turn function calling), AC9 (cost parity).
8. Run full suite, verify deprecation warning gone, verify Story 23.1 watchdog still green.

**Edge cases the implementation must handle:**
- `chunk.candidates[0].content.parts` may be empty on intermediate chunks (text-only deltas). Current code already guards.
- `automatic_function_calling=disable` must be set; a unit test that asserts MCP path is taken (not local execution) prevents regression.
- The `client.aio.chats.create()` async iter: the old SDK's `for chunk in response` becomes `async for chunk in response`. Be careful not to mix them up in the rewrite.
- Multi-turn loop: after sending tool responses, the SDK may or may not preserve thought_signatures the way `start_chat()` did. The new SDK's `chats.create` is the supported equivalent and the docs say it preserves history including function_response parts. **Verify in implementation, not in spec** — David will see immediately if it breaks.

**Test strategy:**
- Reuse the `_FakeChat` / `_FakeChunk` patterns from Story 23.1 — adapted to the new SDK's chunk shape (function_call.args as dict, not proto map).
- Keep the same five Story 23.1 invariants. Murat's watchdog calendar (+24h, +7d, +30d) carries forward unchanged.
- Add the two-turn integration test (AC7) to surface the function-response shape regression early.

---

## 8. Architectural decisions

**Decision 1: hard cut over env-gating.** Single-user system, low blast radius, simpler PR. Recorded in `architecture.md` (will seed if not present).

**Decision 2: keep `gemini_tool_adapter.py` unchanged.** It's a pure dict↔dict converter with no SDK coupling. Resist the urge to "modernize while we're in there" — out-of-scope for this story.

**Decision 3: use `client.aio.chats.create` (async) over `client.chats.create` (sync).** Annie's `stream_chat_completion` is already `async`; pairing it with the async client is the natural fit. No `asyncio.to_thread` wrappers needed.

**Decision 4: explicitly disable `automatic_function_calling`.** The new SDK's default is to auto-execute Python callables. Annie's MCP architecture demands explicit routing. This is non-negotiable; the disable flag goes in.

**Anti-pattern to avoid:** do NOT introduce a `_call_sdk` abstraction layer "in case we migrate again." YAGNI. The provider has one SDK; another migration is unlikely within Annie's lifetime.

---

## 9. Verification strategy

**Pre-merge (automated):**
1. `make rebuild` succeeds (new package installs cleanly).
2. Full backend test suite (≥708) + mcp suite (≥542).
3. New AC5/AC7/AC9 tests pass.
4. Manual `make logs SERVICE=backend` after a smoke chat round-trip — no deprecation warning, no proto-related errors.

**Post-merge (Murat's watchdog calendar — Story 23.1 carries forward):**
- **+24h**: `usage_metadata_missing` rate <1% in Loki — same query as Story 23.1 AC10.
- **+7d**: AC6-style Langfuse query (any `usage.input < 50 AND output_chars > 200` placeholder rows) returns zero. Plus first cost-recon dry-run.
- **+30d**: cost-recon variance <10% target.

The new check unique to Story 23.2:
- **+24h**: zero log entries matching `"google.generativeai"` or `"deprecat"` — proves the warning is gone and the legacy package isn't being import-pulled by some transitive dep we missed.

---

## 10. Dependency on Story 23.1 merge

**YES — Story 23.1 must merge to remote before 23.2 picks up.** Three reasons:

1. **Merge conflicts.** Story 23.1 rewrote `_extract_usage_metadata`, the success-STOP and ended-without-STOP token-counting blocks, and the `_trace_error_generation` helper. Story 23.2 rewrites the surrounding chunk-iteration loop and the `__init__`. These are spatially adjacent in `gemini_provider.py` (same file, overlapping ranges). Doing 23.2 against a tree where 23.1 isn't merged would force David into a manual three-way merge later.

2. **Shared test file.** `test_story_23_1_token_counting.py` is THE regression-prevention battery for token counting. Story 23.2's AC6 explicitly preserves these tests. If 23.1 isn't merged, the test file isn't on `develop`, and 23.2 would be re-implementing both at once.

3. **Watchdog calendar continuity.** Murat's +24h/+7d/+30d post-23.1 watchdog is in flight (first checkpoint 2026-04-26 16:00 PT). Stacking 23.2 on top of an unmerged 23.1 would make it impossible to attribute regressions to one or the other if something fires.

**Sequencing:** Ankit pushes 23.1 → 23.1 lands on remote → Disha drafts 23.2 → I review and move to `ready` → David picks up.

**Story 23.2 itself blocks no other work.** Provider contract is stable; cross-cutting changes are zero.

---

## 11. Size + LOC budget

**Size: M** (medium — single provider rewrite + test re-fixturing). Rough budget:

| Surface | LOC delta |
|---------|-----------|
| `gemini_provider.py` | ~80 lines changed, ~60 lines deleted (`convert_proto_to_dict`), ~30 lines added (config builders, async iter) → **net ~+50 LOC, with ~110 churn** |
| `requirements.txt` | 1 line replaced |
| `test_gemini_provider.py` | ~30 lines changed (patch sites + fake chunks) |
| `test_overflow_recovery.py` | ~10 lines changed |
| `test_story_23_1_token_counting.py` | ~50 lines changed (`_FakeChat` adapted, chunk shape) |
| New tests (AC5, AC7, AC9) | ~120 LOC added |
| **Total** | **~340 LOC churn, ~+170 net** |

A solid M. Not S (the test re-fixturing alone is non-trivial), not L (no architectural change, no cross-service work). One-day implementation, one-day testing pass.

---

## Open questions for Disha

1. Do you want AC12 (full `client.aio.*` async path) in scope, or deferred to a follow-up? My take: include it — Annie's stream is async anyway, and the sync-iter wrapping (`for chunk in response`) will look ugly once the rest is async. Calling it now avoids a future small-cleanup PR.
2. Should we open a "deprecation-warning watchdog" alongside Story 23.1's `usage_metadata_missing` watchdog? My take: yes, but folded into AC10 — one Loki query for both at the +24h checkpoint.
