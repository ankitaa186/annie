# Epic 9: Multi-LLM Provider Support - Add Gemini 3 Pro

**Status:** In Progress
**Priority:** Business Critical (User Priority Override)
**Estimated Effort:** 30-40 hours (5-7 days)
**Sprint:** Current Sprint (Immediate Priority)

---

## Overview

Enable Annie to support multiple LLM providers (Grok-4, ChatGPT-5, Gemini 3 Pro) with seamless switching via environment configuration, maintaining feature parity and cost transparency. This enhances vendor flexibility, cost optimization, and access to Gemini's 1M token context window, advanced reasoning with thinking, and multimodal capabilities.

---

## Business Value

1. **Vendor Diversification**: Reduce dependency on single LLM provider
2. **Cost Optimization**: Choose best price/performance provider per use case
3. **Future-Proofing**: Access to Gemini's multimodal features (vision, audio) for future epics
4. **Flexibility**: Switch providers without code changes (just `.env` update)
5. **Competitive Positioning**: Leverage Google's flagship model alongside Grok-4 and ChatGPT-5

**Strategic Driver**: Preparation for post-Grok-4-free-period (after Nov 21, 2025) and access to Google's ecosystem.

---

## Goals

**Epic-Level Success Criteria:**
1. ✅ Users can switch providers via `.env` without code changes
2. ✅ All core features work identically across providers (chat, streaming, memory, MCP tools)
3. ✅ Cost tracking accurate per provider in Langfuse
4. ✅ Existing Grok-4 functionality unchanged (zero regression)
5. ✅ Graceful error handling for provider-specific failures (safety filters, quotas)

**Non-Goals (Out of Scope):**
- Multi-provider load balancing
- Automatic failover between providers
- Provider-specific feature optimization (e.g., Gemini's vision capabilities)

---

## Technical Architecture

### Provider Abstraction Layer

```
┌─────────────────────────────────────────────┐
│         Backend API (FastAPI)               │
│  ┌───────────────────────────────────────┐  │
│  │   LLMClient (Abstraction Layer)       │  │
│  │   - detect_provider()                 │  │
│  │   - stream_chat_completion()          │  │
│  │   - calculate_cost()                  │  │
│  └────────────┬──────────────────────────┘  │
│               │                              │
│      ┌────────┴────────┬────────────┐       │
│      ▼                 ▼            ▼       │
│  ┌────────┐      ┌──────────┐  ┌─────────┐ │
│  │ Grok   │      │ ChatGPT  │  │ Gemini  │ │
│  │Provider│      │ Provider │  │Provider │ │
│  └────────┘      └──────────┘  └─────────┘ │
└─────────────────────────────────────────────┘
```

### Key Design Decisions

**1. Provider Detection Strategy:**
- Runtime detection based on `LLM_PROVIDER` env var
- Factory pattern returns appropriate provider instance
- No code changes required for switching

**2. Backward Compatibility Guarantees:**
- Existing Grok/ChatGPT code paths unchanged
- New Gemini code in isolated provider class
- Shared interface ensures feature parity

**3. Tool Calling Adapter:**
- MCP tools maintain OpenAI-compatible schema
- Provider-specific adapters translate to native format
- `GeminiToolAdapter` converts OpenAI → Gemini function declarations

**4. Error Handling Strategy:**
- Provider-agnostic error codes
- Gemini safety filters mapped to standard error responses
- Quota/rate limit handling per provider

---

## Environment Configuration

### Required Variables (add to `.env` and `env.example`)
```bash
# LLM Provider Configuration
# Options: grok-4 | chatgpt-5 | gemini-3-pro-preview
LLM_PROVIDER=grok-4  # Default provider

# Gemini 3 Pro Configuration
GEMINI_API_KEY=REPLACE_ME                      # Get from: https://aistudio.google.com/app/apikey
GEMINI_MODEL=gemini-3-pro-preview              # Model name (gemini-3-pro-preview)
GEMINI_MAX_OUTPUT_TOKENS=8192                  # Max output tokens (default: 8192, max: 65536)
GEMINI_TEMPERATURE=1.0                         # Temperature (default: 1.0, avoid lowering - causes looping)
GEMINI_SAFETY_SETTING=BLOCK_NONE               # Safety: BLOCK_NONE (minimal), BLOCK_ONLY_HIGH
GEMINI_CONTEXT_CACHE_TTL=300                   # Context cache TTL in seconds (default: 300)
```

### docker-compose.yml Updates
```yaml
backend:
  environment:
    - GEMINI_API_KEY=${GEMINI_API_KEY:-}
    - GEMINI_MODEL=${GEMINI_MODEL:-gemini-3-pro-preview}
    - GEMINI_TEMPERATURE=${GEMINI_TEMPERATURE:-1.0}
    - GEMINI_SAFETY_SETTING=${GEMINI_SAFETY_SETTING:-BLOCK_NONE}
```

---

## Stories Breakdown

### **Story 9.1: Refactor LLM Client into Provider Abstraction**
**Goal:** Extract existing Grok/ChatGPT logic into provider pattern without breaking current functionality

**Tasks:**
- Task 1: Create provider abstraction interface (backend/api/providers/base.py)
- Task 2: Refactor existing LLMClient to GrokProvider class
- Task 3: Extract ChatGPT logic into ChatGPTProvider class
- Task 7: Update LLMClient factory pattern
- Task 20: Regression test for Grok-4

**Acceptance Criteria:**
- ✅ Grok-4 and ChatGPT-5 work identically to before refactor
- ✅ Zero API changes to existing code calling LLMClient
- ✅ All existing tests pass
- ✅ Provider selection via `LLM_PROVIDER` env var works
- ✅ Factory pattern instantiates correct provider class

**Estimated Effort:** 6-8 hours (1 day)

**Files Changed:**
- `backend/api/providers/base.py` (new)
- `backend/api/providers/grok_provider.py` (new)
- `backend/api/providers/chatgpt_provider.py` (new)
- `backend/api/llm_client.py` (refactored)

---

### **Story 9.2: Implement Gemini 3 Pro Provider**
**Goal:** Add Gemini as a third provider option with streaming chat completion

**Tasks:**
- Task 4: Add Gemini environment variables to config.py and env.example
- Task 5: Implement GeminiProvider class with streaming
- Task 8: Add google-generativeai to backend/requirements.txt
- Task 11: Gemini safety filter error handling
- Task 12: Gemini quota/rate limit handling

**Acceptance Criteria:**
- ✅ User can set `LLM_PROVIDER=gemini-3-pro-preview` in .env
- ✅ Basic chat completion works with streaming
- ✅ Streaming format compatible with existing SSE implementation
- ✅ Safety filter blocks handled gracefully (user-friendly errors)
- ✅ Quota errors return meaningful messages
- ✅ Environment validation ensures GEMINI_API_KEY is set when provider is gemini-3-pro

**Estimated Effort:** 8-10 hours (1.5 days)

**Files Changed:**
- `backend/api/providers/gemini_provider.py` (new)
- `backend/api/config.py` (updated)
- `backend/requirements.txt` (updated)
- `env.example` (updated)

**Technical Notes:**
- Use `google.generativeai` SDK
- Streaming response format: `candidates[0].content.parts[0].text`
- Handle safety ratings per chunk
- Map finish reasons: STOP, SAFETY, MAX_TOKENS

---

### **Story 9.3: Gemini Tool Calling Integration**
**Goal:** Enable MCP tools to work with Gemini's function calling format

**Tasks:**
- Task 6: Build Gemini tool calling adapter
- Task 14: Integration tests for Gemini + MCP tools

**Acceptance Criteria:**
- ✅ All MCP tools (internet_search, store_memory, get_user_profile, etc.) work with Gemini
- ✅ Tool adapter converts OpenAI schema → Gemini function_declarations format
- ✅ Tool responses properly formatted for streaming to Telegram
- ✅ Tool call failures handled gracefully
- ✅ Multiple tool calls in sequence work correctly
- ✅ Tool results incorporated into LLM context properly

**Estimated Effort:** 6-8 hours (1 day)

**Files Changed:**
- `backend/api/providers/gemini_tool_adapter.py` (new)
- `backend/api/providers/gemini_provider.py` (updated)
- `tests/integration/test_gemini_mcp.py` (new)

**Technical Notes:**
- OpenAI format: `{"type": "function", "function": {...}}`
- Gemini format: `{"function_declarations": [{...}]}`
- Handle tool call responses in streaming context

---

### **Story 9.4: Cost Tracking and Observability**
**Goal:** Accurate cost calculation and Langfuse tracing for Gemini

**Tasks:**
- Task 9: Implement Gemini cost calculation (input/output/cached tokens)
- Task 10: Update Langfuse tracing for Gemini
- Task 16: Validate cost tracking accuracy

**Acceptance Criteria:**
- ✅ Langfuse shows accurate token counts for Gemini requests
- ✅ Cost per request calculated correctly with tiered pricing:
  - Input tokens ≤200k: $2.00 per 1M tokens | >200k: $4.00 per 1M
  - Output tokens ≤200k: $12.00 per 1M tokens | >200k: $18.00 per 1M
  - Cached tokens ≤200k: $0.20 per 1M | >200k: $0.40 per 1M
- ✅ Session traces link Gemini calls properly
- ✅ Model metadata captured (gemini-3-pro-preview)
- ✅ Cost alerts work for Gemini (configurable threshold)
- ✅ Cost comparison dashboard shows Grok vs ChatGPT vs Gemini

**Estimated Effort:** 4-6 hours (0.75 days)

**Files Changed:**
- `backend/api/providers/gemini_provider.py` (updated)
- `backend/api/llm_client.py` (updated for cost tracking)

**Technical Notes:**
- Gemini 3 Pro tiered pricing ($2-4 input, $12-18 output, $0.20-0.40 cached per 1M tokens)
- Langfuse generation tracking with cost metadata
- Token counting via Gemini's tokenizer

---

### **Story 9.5: Testing and Validation**
**Goal:** Comprehensive test coverage ensuring provider parity

**Tasks:**
- Task 13: Unit tests for GeminiProvider streaming
- Task 15: Provider parity tests (same prompt across all providers)
- Task 17: Performance benchmarks (Grok vs Gemini latency)
- Task 18: Update CLAUDE.md documentation
- Task 19: Update env.example with Gemini variables

**Acceptance Criteria:**
- ✅ 80%+ code coverage for Gemini provider
- ✅ Same prompt produces comparable quality across all providers
- ✅ Gemini latency within 20% of Grok-4
- ✅ Provider parity test suite includes:
  - Basic chat completion
  - Streaming responses
  - Tool calling (internet search, memory, etc.)
  - Error handling (API failures, timeouts)
- ✅ Documentation complete for switching providers
- ✅ CLAUDE.md includes:
  - How to get Gemini API key
  - How to configure Gemini provider
  - Troubleshooting Gemini-specific errors (safety filters, quota)
  - Cost comparison guide

**Estimated Effort:** 6-8 hours (1 day)

**Files Changed:**
- `tests/unit/test_gemini_provider.py` (new)
- `tests/integration/test_provider_parity.py` (new)
- `tests/performance/benchmark_providers.py` (new)
- `CLAUDE.md` (updated)
- `env.example` (updated)

**Technical Notes:**
- Provider parity: Use identical prompt, compare response quality
- Performance: Measure first token latency, total completion time
- Documentation: Gemini-specific troubleshooting (safety filters, quota exceeded)

---

## Total Epic Estimate

**Total Effort:** 30-40 hours (~5-7 days)

**Story Breakdown:**
- Story 9.1: 6-8 hours (Refactor to provider abstraction)
- Story 9.2: 8-10 hours (Implement Gemini provider)
- Story 9.3: 6-8 hours (Tool calling adapter)
- Story 9.4: 4-6 hours (Cost tracking & observability)
- Story 9.5: 6-8 hours (Testing & documentation)

---

## Sprint Allocation Options

### **Option A: Dedicated Sprint (Recommended)**
- Sprint focus: Multi-LLM support epic
- Duration: 1 sprint (1 week with focused effort)
- Team: Amelia (dev), Murat (testing), Paige (docs)
- Advantages: Focused delivery, clean testing, complete documentation

### **Option B: Incremental Integration**
- Stories 9.1-9.2 in Sprint N (foundation + Gemini basics)
- Stories 9.3-9.5 in Sprint N+1 (tool integration + testing)
- Allows parallel work on other epics
- Advantages: Flexibility, doesn't block other work

---

## Dependencies

**Prerequisites:**
- None - can start immediately
- Does NOT block other V1.0 MVP work

**No blocking dependencies on other epics**

---

## Risks & Mitigations

### 🟡 Medium Risks

**Risk 1: Gemini API changes**
- **Mitigation:** Provider abstraction isolates changes, update only GeminiProvider class
- **Contingency:** Maintain Grok-4/ChatGPT-5 as primary, Gemini as optional

**Risk 2: Tool calling format incompatibilities**
- **Mitigation:** Thorough testing with all MCP tools, build robust adapter
- **Contingency:** Document incompatible tools, disable Gemini for those use cases

**Risk 3: Gemini safety filters too aggressive**
- **Mitigation:** Configurable safety threshold, graceful error handling
- **Contingency:** Fallback to Grok-4/ChatGPT-5 for blocked content

### 🟢 Low Risks

**Risk 4: Cost tracking accuracy**
- **Mitigation:** Langfuse supports Gemini natively, validate against Google billing
- **Impact:** Low - cost tracking is observability, not critical path

---

## Success Metrics

### Functional Metrics
- [ ] 100% of MCP tools work with Gemini
- [ ] Zero regression in Grok-4/ChatGPT-5 functionality
- [ ] Provider switching works without code changes (just `.env` update)

### Performance Metrics
- [ ] Gemini first token latency < 500ms (p95)
- [ ] Gemini total response time comparable to Grok-4 (±20%)
- [ ] Zero performance degradation when adding Gemini provider

### Quality Metrics
- [ ] 80%+ code coverage for Gemini provider
- [ ] All integration tests pass for Gemini
- [ ] Provider parity tests show comparable quality across providers

### Observability Metrics
- [ ] Cost tracking accurate within 1% (validated against Google billing)
- [ ] Langfuse traces show Gemini calls with metadata
- [ ] Team can debug Gemini issues using traces

---

## Rollout Strategy

### Phase 1: Development
- Epic 9 stories implemented
- Gemini provider available but disabled by default
- Can be enabled in dev by setting `LLM_PROVIDER=gemini-3-pro-preview`

### Phase 2: Dev Environment Testing
- Enable Gemini in dev `.env`
- Run provider parity tests
- Validate cost tracking accuracy
- Measure latency and performance

### Phase 3: Production (Optional)
- Enable Gemini in production after validation
- Monitor for safety filter issues
- Track cost vs Grok-4/ChatGPT-5
- Collect user feedback on response quality

---

## Future Enhancements

**Post-Epic 9 (Out of Scope):**
1. **Multimodal Support**: Use Gemini for image/video analysis
2. **Long Context**: Leverage Gemini's 2M token context for full conversation history
3. **Automatic Provider Selection**: Choose best provider based on task type
4. **Failover**: Automatic fallback to alternative provider on failure
5. **A/B Testing**: Compare response quality across providers

---

## References

- **Gemini 3 Pro Docs**: https://ai.google.dev/gemini-api/docs/gemini-3
- **Google AI Studio**: https://aistudio.google.com
- **Gemini Pricing**: https://ai.google.dev/pricing
- **Langfuse Gemini Support**: https://langfuse.com/docs/integrations/google-gemini
- **Annie Architecture**: `docs/02-architecture/ARCHITECTURE_PLAN.md`
- **Current LLM Client**: `backend/api/llm_client.py`

---

## Task Checklist (20 Tasks)

**Story 9.1: Provider Abstraction (6 tasks)**
- [ ] Task 1: Create provider abstraction interface (backend/api/providers/base.py)
- [ ] Task 2: Refactor LLMClient to GrokProvider class
- [ ] Task 3: Extract ChatGPT logic into ChatGPTProvider class
- [ ] Task 7: Update LLMClient factory pattern
- [ ] Task 20: Regression test for Grok-4
- [ ] Task 21: Update existing code to use factory pattern

**Story 9.2: Gemini Provider (5 tasks)**
- [ ] Task 4: Add Gemini environment variables
- [ ] Task 5: Implement GeminiProvider class with streaming
- [ ] Task 8: Add google-generativeai dependency
- [ ] Task 11: Gemini safety filter error handling
- [ ] Task 12: Gemini quota/rate limit handling

**Story 9.3: Tool Calling (2 tasks)**
- [ ] Task 6: Build Gemini tool calling adapter
- [ ] Task 14: Integration tests for Gemini + MCP

**Story 9.4: Cost Tracking (3 tasks)**
- [ ] Task 9: Implement Gemini cost calculation
- [ ] Task 10: Update Langfuse tracing for Gemini
- [ ] Task 16: Validate cost tracking accuracy

**Story 9.5: Testing & Docs (4 tasks)**
- [ ] Task 13: Unit tests for GeminiProvider
- [ ] Task 15: Provider parity tests
- [ ] Task 17: Performance benchmarks
- [ ] Task 18: Update CLAUDE.md
- [ ] Task 19: Update env.example

---

_This epic enables Annie to support multiple LLM providers with full backward compatibility, cost transparency, and graceful error handling. Gemini 3 Pro provides strategic optionality for post-Grok-4-free-period and access to Google's 1M context window, advanced reasoning with thinking, and multimodal capabilities._
