# Story 9.5: Testing and Validation

**Story ID:** 9.5
**Epic:** Epic 9 - Multi-LLM Provider Support - Gemini 3.0 Pro
**Status:** drafted
**Points:** 2
**Assignee:** TBD
**Sprint:** TBD

---

## User Story

**As a** quality engineer
**I want** comprehensive test coverage ensuring provider parity and performance
**So that** users get consistent, high-quality experience regardless of which LLM provider is active (Grok, ChatGPT, or Gemini), and we can confidently deploy Gemini to production

---

## Acceptance Criteria

### AC#1: Code Coverage
- [ ] 80%+ code coverage for all Gemini provider code:
  - `backend/api/providers/gemini_provider.py` - Core provider implementation
  - `backend/api/providers/gemini_tool_adapter.py` - Tool calling adapter
  - `backend/api/observability/cost_tracker.py` - Cost tracking logic
  - `backend/api/observability/cost_alerts.py` - Alert system
- [ ] Coverage report generated and stored in CI artifacts
- [ ] Critical paths (streaming, tool calling, error handling) have 100% coverage

### AC#2: Provider Parity Tests
- [ ] Same prompt produces comparable quality across all providers:
  - Test prompt: "Explain quantum computing in simple terms"
  - Assert: All providers return coherent, relevant responses
  - Assert: Response length within 20% variance
  - Assert: Key concepts mentioned in all responses (qubits, superposition, entanglement)
- [ ] Parity test suite includes:
  - Basic chat completion (simple question/answer)
  - Multi-turn conversation (context preservation)
  - Streaming responses (chunk delivery)
  - Tool calling (internet search, memory, profile)
  - Error handling (API failures, timeouts)
- [ ] Parity tests run against all 3 providers concurrently

### AC#3: Performance Benchmarks
- [ ] Gemini latency within 20% of Grok-4 baseline:
  - **First token latency:** <500ms (p95) - from Story 2.3 requirement
  - **Total completion time:** <5s for 500-token response
  - **Tool call overhead:** <5s per tool - from Story 2.4 requirement
- [ ] Performance metrics collected:
  - Time to first token (TTFT)
  - Tokens per second (TPS) during streaming
  - End-to-end request latency
  - Tool call latency breakdown (MCP call + LLM processing)
- [ ] Benchmark results stored in CI artifacts for trend analysis

### AC#4: Comprehensive Test Suite
- [ ] **Unit tests** cover:
  - GeminiProvider streaming logic (message conversion, chunk formatting)
  - GeminiToolAdapter schema conversion (all parameter types)
  - Cost calculation accuracy (various token counts, pricing tiers)
  - Error handling (API errors, safety filters, quota limits)
  - Edge cases (empty messages, very long prompts, special characters)
- [ ] **Integration tests** cover:
  - End-to-end chat flow (user message → LLM response → Telegram)
  - Tool calling with real MCP server
  - Langfuse tracing and cost tracking
  - Session and user linking
  - Multi-turn conversations with context
- [ ] **Regression tests** ensure:
  - Grok-4 functionality unchanged after provider refactoring
  - ChatGPT-5 functionality unchanged
  - All existing tests pass (Epic 1-8 test suites)

### AC#5: Documentation Complete
- [ ] `CLAUDE.md` updated with Gemini configuration:
  - How to get Gemini API key (link to Google AI Studio)
  - How to configure `LLM_PROVIDER=gemini-3-pro`
  - Environment variables: `GEMINI_API_KEY`, `GEMINI_MODEL`, etc.
  - Troubleshooting guide for common Gemini errors:
    - Safety filter blocking ("Response blocked by safety filter" → adjust prompt)
    - Quota exceeded (429 error → check API quota in console)
    - Invalid API key (401 error → regenerate key)
  - Cost comparison table (Grok vs ChatGPT vs Gemini)
- [ ] `env.example` includes Gemini variables with helpful comments
- [ ] Code comments explain Gemini-specific logic (safety filters, message format)

### AC#6: Production Readiness
- [ ] All Epic 9 stories (9.1-9.5) complete and DoD met
- [ ] No P0/P1 bugs in Gemini provider code
- [ ] Security review passed:
  - API keys properly masked in logs
  - No secrets in error messages
  - GEMINI_API_KEY validated on startup
- [ ] Performance review passed (latency within SLA)
- [ ] Observability verified (Langfuse traces, cost tracking, alerts)
- [ ] Deployment checklist created

---

## Tasks

### Task 1: Unit Tests for GeminiProvider Streaming
**File:** `tests/unit/test_gemini_provider.py` (new file)

**Subtasks:**
- [ ] **1.1** Test basic streaming:
  ```python
  @pytest.mark.asyncio
  async def test_gemini_streaming_basic():
      provider = GeminiProvider()
      messages = [{"role": "user", "content": "Hello!"}]

      chunks = []
      async for chunk in provider.stream_chat_completion(messages):
          chunks.append(chunk)

      assert len(chunks) > 0
      assert chunks[0]["type"] == "content"
      assert "content" in chunks[0]
      assert chunks[-1]["type"] == "done"
  ```
- [ ] **1.2** Test message format conversion (OpenAI → Gemini):
  ```python
  def test_convert_messages_to_gemini():
      messages = [
          {"role": "system", "content": "You are helpful."},
          {"role": "user", "content": "Hello!"},
          {"role": "assistant", "content": "Hi there!"},
          {"role": "user", "content": "How are you?"}
      ]
      gemini_messages = GeminiProvider._convert_messages(messages)
      assert gemini_messages[0]["role"] == "user"
      assert gemini_messages[0]["parts"][0]["text"] == "You are helpful.\n\nHello!"
      # System message merged with first user message in Gemini
  ```
- [ ] **1.3** Test chunk format conversion (Gemini → OpenAI SSE):
  ```python
  def test_convert_gemini_chunk_to_sse():
      gemini_chunk = Mock()
      gemini_chunk.candidates[0].content.parts[0].text = "Hello"

      sse_chunk = GeminiProvider._convert_chunk(gemini_chunk)
      assert sse_chunk["type"] == "content"
      assert sse_chunk["content"] == "Hello"
  ```
- [ ] **1.4** Test empty response handling
- [ ] **1.5** Test very long prompt (>100k tokens) - ensure no truncation errors
- [ ] **1.6** Test special characters in prompt (emojis, unicode, code blocks)

### Task 2: Unit Tests for Safety Filter Handling
**File:** `tests/unit/test_gemini_safety_filters.py` (new file)

**Subtasks:**
- [ ] **2.1** Test safety filter blocking:
  ```python
  @pytest.mark.asyncio
  async def test_safety_filter_blocked():
      provider = GeminiProvider()
      # Mock Gemini API to return safety filter block
      with patch.object(provider.client, 'generate_content') as mock:
          mock.return_value.candidates[0].finish_reason = "SAFETY"

          chunks = []
          async for chunk in provider.stream_chat_completion([...]):
              chunks.append(chunk)

          assert any("safety filter" in str(c).lower() for c in chunks)
  ```
- [ ] **2.2** Test different block categories (HARM_CATEGORY_HARASSMENT, HATE_SPEECH, etc.)
- [ ] **2.3** Test user-friendly error message format
- [ ] **2.4** Test Langfuse trace captures safety filter metadata

### Task 3: Unit Tests for Quota and Rate Limit Handling
**File:** `tests/unit/test_gemini_quota_handling.py` (new file)

**Subtasks:**
- [ ] **3.1** Test quota exceeded (429 error):
  ```python
  @pytest.mark.asyncio
  async def test_quota_exceeded_handling():
      provider = GeminiProvider()
      with patch.object(provider.client, 'generate_content') as mock:
          mock.side_effect = Exception("429 Resource Exhausted: Quota exceeded")

          with pytest.raises(QuotaExceededError) as exc:
              async for _ in provider.stream_chat_completion([...]):
                  pass

          assert "quota" in str(exc.value).lower()
          assert "check your quota" in str(exc.value).lower()
  ```
- [ ] **3.2** Test per-minute quota limit (RPM)
- [ ] **3.3** Test daily quota limit
- [ ] **3.4** Test retry logic with exponential backoff

### Task 4: Unit Tests for Tool Adapter
**File:** `tests/unit/test_gemini_tool_adapter.py` (already created in Story 9.3, expand here)

**Subtasks:**
- [ ] **4.1** Expand schema conversion tests for all parameter types:
  - String, integer, boolean, number, object, array
  - Nested objects (e.g., `{location: {city: string, country: string}}`)
  - Enum constraints (e.g., `{mode: enum["on", "off", "auto"]}`)
  - Optional vs required parameters
- [ ] **4.2** Test tool call conversion edge cases:
  - Empty arguments `{}`
  - Very large arguments (10KB+ JSON)
  - Special characters in arguments
- [ ] **4.3** Test tool result formatting:
  - Normal result (<1KB)
  - Large result (>10KB, should truncate)
  - Error result (tool execution failed)

### Task 5: Integration Tests for Provider Parity
**File:** `tests/integration/test_provider_parity.py` (new file)

**Subtasks:**
- [ ] **5.1** Test basic chat parity:
  ```python
  @pytest.mark.asyncio
  async def test_basic_chat_parity():
      prompt = "Explain quantum computing in simple terms"
      messages = [{"role": "user", "content": prompt}]

      # Test all 3 providers
      grok_response = await test_with_provider("grok-4", messages)
      chatgpt_response = await test_with_provider("chatgpt-5", messages)
      gemini_response = await test_with_provider("gemini-3-pro", messages)

      # All should mention key concepts
      key_terms = ["qubit", "superposition", "entanglement"]
      for response in [grok_response, chatgpt_response, gemini_response]:
          assert any(term in response.lower() for term in key_terms)

      # Length variance within 20%
      lengths = [len(r) for r in [grok_response, chatgpt_response, gemini_response]]
      avg_length = sum(lengths) / len(lengths)
      for length in lengths:
          variance = abs(length - avg_length) / avg_length
          assert variance < 0.20  # Within 20%
  ```
- [ ] **5.2** Test multi-turn conversation parity (context preservation)
- [ ] **5.3** Test streaming parity (chunk delivery timing)
- [ ] **5.4** Test tool calling parity (all providers call same tools correctly)
- [ ] **5.5** Test error handling parity (graceful failures)

### Task 6: Performance Benchmarks
**File:** `tests/performance/benchmark_providers.py` (new file)

**Subtasks:**
- [ ] **6.1** Benchmark first token latency (TTFT):
  ```python
  import time

  async def benchmark_first_token_latency(provider_name: str):
      provider = create_provider(provider_name)
      messages = [{"role": "user", "content": "Write a haiku about coding"}]

      start = time.perf_counter()
      first_chunk_time = None

      async for chunk in provider.stream_chat_completion(messages):
          if chunk["type"] == "content" and first_chunk_time is None:
              first_chunk_time = time.perf_counter() - start
              break

      return first_chunk_time * 1000  # Convert to ms

  # Run benchmark
  grok_ttft = await benchmark_first_token_latency("grok-4")
  gemini_ttft = await benchmark_first_token_latency("gemini-3-pro")

  assert gemini_ttft < 500  # p95 requirement
  assert gemini_ttft < grok_ttft * 1.20  # Within 20% of Grok
  ```
- [ ] **6.2** Benchmark tokens per second (TPS) during streaming
- [ ] **6.3** Benchmark end-to-end latency (request → response complete)
- [ ] **6.4** Benchmark tool call overhead (with/without tools)
- [ ] **6.5** Store benchmark results in JSON for trend analysis:
  ```json
  {
    "timestamp": "2025-12-11T12:00:00Z",
    "provider": "gemini-3-pro",
    "ttft_ms": 320,
    "tps": 45.2,
    "end_to_end_ms": 2150,
    "tool_call_overhead_ms": 4200
  }
  ```
- [ ] **6.6** Generate performance comparison report (markdown table)

### Task 7: Regression Tests for Existing Functionality
**File:** `tests/regression/test_epic_9_regression.py` (new file)

**Subtasks:**
- [ ] **7.1** Run all existing test suites after Epic 9 refactoring:
  - Epic 1 tests (Foundation & Infrastructure)
  - Epic 2 tests (Core Chat & LLM Integration)
  - Epic 3 tests (Memory & Persistence)
  - Epic 4 tests (Decision Support Tools)
  - Epic 5 tests (Telegram Bot Interface)
  - Epic 8 tests (Langfuse Integration)
- [ ] **7.2** Assert 100% pass rate (no regressions introduced)
- [ ] **7.3** Test Grok-4 specific features still work:
  - Grok-4 Live Search (Story 4.1)
  - Live search cost tracking
  - Search activation logging
- [ ] **7.4** Test ChatGPT-5 fallback still works (if Grok fails)
- [ ] **7.5** Test backward compatibility:
  - Old config (`LLM_PROVIDER=grok-4`) still works
  - No breaking changes to existing API endpoints
  - Session state management unchanged

### Task 8: Update Documentation
**File:** `CLAUDE.md`

**Subtasks:**
- [ ] **8.1** Add Gemini provider section:
  ```markdown
  ### Gemini 3.0 Pro Provider

  Annie supports Google's Gemini 3.0 Pro as a third LLM provider option.

  **Getting Started:**
  1. Get API key from [Google AI Studio](https://makersuite.google.com/app/apikey)
  2. Set environment variables:
     ```bash
     LLM_PROVIDER=gemini-3-pro
     GEMINI_API_KEY=your_key_here
     GEMINI_MODEL=gemini-3.0-pro  # Optional, defaults to gemini-3.0-pro
     GEMINI_MAX_TOKENS=8192       # Optional, defaults to 8192
     ```
  3. Restart services: `make restart`

  **Features:**
  - ✅ Streaming responses
  - ✅ Tool calling (internet search, memory, profile)
  - ✅ Cost tracking via Langfuse
  - ✅ Safety filter handling
  - ✅ Quota management

  **Cost Comparison:**
  | Provider | Input (per 1M tokens) | Output (per 1M tokens) |
  |----------|------------------------|-------------------------|
  | Grok-4 | FREE (until Nov 21 2025) | FREE |
  | ChatGPT-5 | $X.XX | $Y.YY |
  | Gemini 3.0 Pro | $2.50 | $10.00 |
  ```
- [ ] **8.2** Add troubleshooting section:
  ```markdown
  **Common Gemini Errors:**

  1. **Safety Filter Blocking**
     - Error: "Response blocked by safety filter"
     - Cause: Prompt triggered content policy (hate speech, violence, etc.)
     - Fix: Rephrase prompt to avoid policy violations

  2. **Quota Exceeded**
     - Error: "429 Resource Exhausted: Quota exceeded"
     - Cause: API quota limit reached (per-minute or daily)
     - Fix: Check quota in [Google Cloud Console](https://console.cloud.google.com/apis/api/generativelanguage.googleapis.com/quotas)

  3. **Invalid API Key**
     - Error: "401 Unauthorized: Invalid API key"
     - Cause: API key expired or incorrect
     - Fix: Regenerate key in Google AI Studio
  ```
- [ ] **8.3** Update provider selection guide with decision matrix:
  ```markdown
  **Which Provider Should I Use?**

  - **Grok-4:** Best for cost-sensitive use cases (FREE until Nov 21 2025), Live Search for real-time data
  - **ChatGPT-5:** Best for complex reasoning, function calling reliability
  - **Gemini 3.0 Pro:** Best for multimodal future (images, audio), Google ecosystem integration
  ```
- [ ] **8.4** Update environment variables section with Gemini vars
- [ ] **8.5** Add performance benchmarks to docs

**File:** `env.example`

**Subtasks:**
- [ ] **8.6** Add Gemini environment variables:
  ```bash
  # LLM Provider Configuration (grok-4, chatgpt-5, gemini-3-pro)
  LLM_PROVIDER=grok-4

  # ... existing vars ...

  # Gemini 3.0 Pro Configuration
  GEMINI_API_KEY=REPLACE_ME  # Get from https://makersuite.google.com/app/apikey
  GEMINI_MODEL=gemini-3.0-pro  # Optional: Gemini model version
  GEMINI_MAX_TOKENS=8192       # Optional: Max output tokens (default 8192)
  GEMINI_TEMPERATURE=0.7       # Optional: Temperature 0.0-1.0 (default 0.7)
  GEMINI_COST_ALERT_THRESHOLD=500  # Optional: Monthly cost alert in USD (default $500)
  GEMINI_MAX_TOOL_ITERATIONS=5     # Optional: Max tool call iterations (default 5)
  ```
- [ ] **8.7** Add helpful comments explaining each variable

### Task 9: Create Deployment Checklist
**File:** `docs/05-deployment/GEMINI_DEPLOYMENT_CHECKLIST.md` (new file)

**Subtasks:**
- [ ] **9.1** Pre-deployment checklist:
  - [ ] All Epic 9 stories complete (9.1-9.5)
  - [ ] Test suite passing (unit, integration, parity, performance)
  - [ ] Code coverage ≥80%
  - [ ] Security review passed
  - [ ] Documentation updated (CLAUDE.md, env.example)
  - [ ] Langfuse tracing verified in staging
  - [ ] Cost tracking accuracy validated
  - [ ] Performance benchmarks meet SLA
- [ ] **9.2** Deployment steps:
  1. Update production `.env` with Gemini credentials
  2. Set `LLM_PROVIDER=gemini-3-pro`
  3. Deploy new version: `make rebuild && make start`
  4. Verify health: `curl http://localhost:8000/health/detailed`
  5. Test basic chat: Send test message via Telegram
  6. Monitor Langfuse: Check traces appearing
  7. Monitor costs: Verify cost tracking working
- [ ] **9.3** Rollback plan:
  - Revert `LLM_PROVIDER` to `grok-4` or `chatgpt-5`
  - Restart services: `make restart`
  - Verify old provider working
- [ ] **9.4** Monitoring checklist:
  - [ ] Langfuse dashboard shows Gemini traces
  - [ ] Cost alerts configured (threshold set)
  - [ ] Error logs monitored for safety filter / quota issues
  - [ ] Performance metrics within SLA (TTFT <500ms, tool calls <5s)

---

## Dev Notes

### Test Data Fixtures

Create reusable test fixtures for common scenarios:

```python
# tests/fixtures/provider_fixtures.py
import pytest

@pytest.fixture
def sample_messages():
    return [
        {"role": "system", "content": "You are a helpful AI assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there! How can I help you?"},
        {"role": "user", "content": "Tell me about quantum computing."}
    ]

@pytest.fixture
def sample_tool_schema():
    return {
        "type": "function",
        "function": {
            "name": "internet_search",
            "description": "Search the internet",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"}
                },
                "required": ["query"]
            }
        }
    }

@pytest.fixture
async def mock_gemini_client():
    """Mock Gemini API client for unit tests."""
    with patch('google.generativeai.GenerativeModel') as mock:
        yield mock
```

### Performance Baseline (from existing stories)

- **Story 2.3 (SSE Streaming):** First token latency <500ms (p95)
- **Story 2.4 (Function Calling):** Tool call overhead <5s
- **Story 3.1 (Memory Storage):** Memory operations <500ms (p95)

Gemini must meet or beat these baselines.

### Test Coverage Tools

```bash
# Generate coverage report
pytest tests/ --cov=backend/api/providers --cov-report=html

# View coverage report
open htmlcov/index.html

# Check coverage threshold (fail if <80%)
pytest tests/ --cov=backend/api/providers --cov-fail-under=80
```

### CI/CD Integration

Add to GitHub Actions / CI pipeline:

```yaml
# .github/workflows/test.yml
- name: Run Epic 9 Test Suite
  run: |
    pytest tests/unit/test_gemini_*.py -v
    pytest tests/integration/test_provider_parity.py -v
    pytest tests/performance/benchmark_providers.py -v
    pytest tests/regression/test_epic_9_regression.py -v

- name: Generate Coverage Report
  run: pytest --cov=backend/api/providers --cov-report=xml

- name: Upload Coverage to Codecov
  uses: codecov/codecov-action@v3

- name: Performance Regression Check
  run: python scripts/check_performance_regression.py
```

### Manual Testing Checklist

Before marking story complete, manually verify:

1. **Basic Chat:**
   - Send "Hello!" via Telegram with Gemini provider
   - Verify response received and formatted correctly
   - Check Langfuse trace appears

2. **Tool Calling:**
   - Send "What's the weather in London?" (triggers internet_search)
   - Verify tool called and result incorporated
   - Check tool call events streamed to Telegram

3. **Multi-Turn Conversation:**
   - Have 5-turn conversation about a topic
   - Verify context preserved (Gemini remembers earlier messages)
   - Check session linking in Langfuse

4. **Error Scenarios:**
   - Test with invalid API key → Verify user-friendly error
   - Test prompt that triggers safety filter → Verify graceful handling
   - Test during quota exceeded → Verify helpful error message

5. **Cost Tracking:**
   - Make several requests with Gemini
   - Check Langfuse traces show accurate token counts and costs
   - Verify cost aggregation endpoint returns correct totals

### Key Constraints

1. **No Regressions:** All existing tests must pass (Epics 1-8)
2. **Performance:** Gemini latency within 20% of Grok-4 baseline
3. **Parity:** Same prompts produce comparable quality across all providers
4. **Coverage:** 80%+ code coverage for all new Gemini code
5. **Documentation:** Complete guide for switching to Gemini

### Dependencies

- **Stories 9.1-9.4:** All previous Epic 9 stories must be complete
- **All Epics 1-8:** Existing functionality to preserve in regression tests

### Definition of Done

- [ ] All 6 acceptance criteria met and validated
- [ ] All 9 tasks completed with subtasks
- [ ] Test coverage ≥80% for Gemini provider code
- [ ] Provider parity tests pass (all 3 providers produce comparable results)
- [ ] Performance benchmarks meet SLA (TTFT <500ms, within 20% of Grok)
- [ ] Regression tests pass (no breaking changes to existing functionality)
- [ ] Documentation complete (CLAUDE.md, env.example, deployment checklist)
- [ ] Code reviewed and approved
- [ ] Security review passed (API key masking, no secrets in logs)
- [ ] Manual testing checklist complete (basic chat, tools, errors, cost tracking)
- [ ] Epic 9 retrospective scheduled

---

## Technical Context

### Test Pyramid

```
        E2E Tests (5%)
       /              \
    Integration (25%)
   /                    \
Unit Tests (70%)
```

**Unit Tests (70%):** Fast, isolated, mock external dependencies
- GeminiProvider methods
- Tool adapter conversions
- Cost calculation logic
- Error handling

**Integration Tests (25%):** Test component interactions, use test environment
- Provider → MCP Server → Tools
- Langfuse tracing end-to-end
- Session/user linking
- Multi-turn conversations

**E2E Tests (5%):** Full system tests, use staging environment (optional for Epic 9)
- Telegram → Backend → Gemini → Response
- Real user scenarios

### Related Documentation
- pytest documentation: https://docs.pytest.org/
- pytest-asyncio: https://pytest-asyncio.readthedocs.io/
- Coverage.py: https://coverage.readthedocs.io/
- Gemini API testing guide: https://ai.google.dev/gemini-api/docs/testing

### Related Stories
- **All Epic 9 Stories (9.1-9.4):** Must be complete before this story
- **Story 2.3:** SSE Streaming (performance baseline)
- **Story 2.4:** Function Calling (tool call baseline)
- **Story 6.2:** Unit & Integration Testing (testing patterns)

---

## Notes

Created: 2025-12-11
Last Updated: 2025-12-11
Created By: BMad Master (via sprint planning workflow)

**Important:** This is the final story in Epic 9. Upon completion, the epic is DONE and ready for retrospective.
