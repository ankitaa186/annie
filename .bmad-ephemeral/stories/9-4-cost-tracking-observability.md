# Story 9.4: Cost Tracking and Observability

**Story ID:** 9.4
**Epic:** Epic 9 - Multi-LLM Provider Support - Gemini 3.0 Pro
**Status:** drafted
**Points:** 2
**Assignee:** TBD
**Sprint:** TBD

---

## User Story

**As a** platform operator
**I want** accurate cost calculation and Langfuse tracing for Gemini 3.0 Pro
**So that** I can monitor and optimize LLM costs across all providers (Grok, ChatGPT, Gemini) and make data-driven decisions about provider selection based on cost and performance

---

## Acceptance Criteria

### AC#1: Token Count Accuracy
- [ ] Langfuse traces show accurate token counts for Gemini requests:
  - Input tokens (prompt + context)
  - Output tokens (generated text)
  - Cached tokens (if Gemini supports context caching)
  - Total tokens (input + output)
- [ ] Token counts match Gemini API response metadata exactly
- [ ] Token counting includes tool call overhead (function definitions, results)

### AC#2: Cost Calculation with Tiered Pricing
- [ ] Cost per request calculated correctly based on Gemini 3 Pro tiered pricing:
  - Input tokens ≤200k: $2.00 per 1M tokens
  - Input tokens >200k: $4.00 per 1M tokens (for tokens beyond 200k)
  - Output tokens ≤200k: $12.00 per 1M tokens
  - Output tokens >200k: $18.00 per 1M tokens (for tokens beyond 200k)
  - Cached tokens ≤200k: $0.20 per 1M tokens
  - Cached tokens >200k: $0.40 per 1M tokens (for tokens beyond 200k)
  - Total cost: Tiered calculation (first 200k at low rate, excess at high rate)
- [ ] Cost calculation method: `GeminiProvider.calculate_cost(input_tokens, output_tokens, cached_tokens)`
- [ ] Cost displayed in USD with 6 decimal precision (e.g., `$0.004200`)
- [ ] Tier information included in cost metadata ("low" or "high")

### AC#3: Langfuse Trace Integration
- [ ] Gemini LLM calls create proper Langfuse generations:
  - Model: `gemini-3-pro-preview`
  - Trace hierarchy: `chat_request` → `stream_request` → `gemini_llm_call` → `tool_calls`
  - Input: Full prompt with messages
  - Output: Generated response text
  - Metadata: Provider name, streaming mode, tools used
- [ ] Session linking works: All traces for same conversation_id grouped under session
- [ ] User ID captured: Telegram user ID for per-user cost tracking

### AC#4: Cost Metadata Capture
- [ ] Each Langfuse generation includes cost metadata:
  ```python
  {
      "model": "gemini-3-pro-preview",
      "input_tokens": 1250,
      "output_tokens": 450,
      "cached_tokens": 0,
      "total_tokens": 1700,
      "input_cost_usd": 0.002500,  # 1250 * $2.00 / 1M (low tier)
      "output_cost_usd": 0.005400,  # 450 * $12.00 / 1M (low tier)
      "cached_cost_usd": 0.000000,
      "total_cost_usd": 0.007900,
      "tier": "low",  # All tokens ≤200k threshold
      "provider": "gemini",
      "tools_used": ["internet_search", "store_memory"]
  }
  ```
- [ ] Cost metadata survives async fire-and-forget pattern (contextvars)

### AC#5: Cost Alerts
- [ ] Cost alerts work for Gemini provider:
  - Configurable threshold: `GEMINI_COST_ALERT_THRESHOLD` env var (default $500/month)
  - Alert logged when monthly spend exceeds threshold
  - Alert includes: current spend, threshold, top conversations by cost
- [ ] Cost aggregation by:
  - Per conversation (session_id)
  - Per user (user_id)
  - Per day/week/month
  - Per provider (for comparison)

### AC#6: Multi-Provider Cost Dashboard
- [ ] Cost comparison view shows all providers:
  - Grok-4 costs (including Live Search costs)
  - ChatGPT-5 costs
  - Gemini 3.0 Pro costs
- [ ] Metrics displayed:
  - Total requests per provider
  - Average cost per request
  - Total monthly spend per provider
  - Cost per token comparison
  - ROI analysis (quality vs cost)

---

## Tasks

### Task 1: Implement Gemini Cost Calculation Method
**File:** `backend/api/providers/gemini_provider.py`

**Subtasks:**
- [ ] **1.1** Add Gemini tiered pricing constants to config:
  ```python
  # backend/api/config.py
  # Gemini 3 Pro tiered pricing (as of Dec 2024)
  GEMINI_INPUT_COST_LOW = 0.00200   # $2.00 per 1M tokens (≤200k tokens)
  GEMINI_INPUT_COST_HIGH = 0.00400  # $4.00 per 1M tokens (>200k tokens)
  GEMINI_OUTPUT_COST_LOW = 0.01200  # $12.00 per 1M tokens (≤200k tokens)
  GEMINI_OUTPUT_COST_HIGH = 0.01800  # $18.00 per 1M tokens (>200k tokens)
  GEMINI_CACHED_COST_LOW = 0.00020  # $0.20 per 1M tokens (≤200k cached)
  GEMINI_CACHED_COST_HIGH = 0.00040  # $0.40 per 1M tokens (>200k cached)
  GEMINI_STORAGE_COST = 0.00450  # $4.50 per 1M tokens/hour (context caching storage)
  ```
- [ ] **1.2** Implement `calculate_cost()` method in `GeminiProvider` with tiered pricing:
  ```python
  def calculate_cost(
      self,
      input_tokens: int,
      output_tokens: int,
      cached_tokens: int = 0
  ) -> dict:
      """Calculate cost for Gemini API call with tiered pricing."""
      # Tiered pricing threshold
      TIER_THRESHOLD = 200_000  # 200k tokens

      # Calculate input cost (tiered)
      if input_tokens <= TIER_THRESHOLD:
          input_cost = (input_tokens * GEMINI_INPUT_COST_LOW) / 1_000_000
      else:
          # First 200k at low rate, rest at high rate
          low_tier = TIER_THRESHOLD * GEMINI_INPUT_COST_LOW / 1_000_000
          high_tier = (input_tokens - TIER_THRESHOLD) * GEMINI_INPUT_COST_HIGH / 1_000_000
          input_cost = low_tier + high_tier

      # Calculate output cost (tiered)
      if output_tokens <= TIER_THRESHOLD:
          output_cost = (output_tokens * GEMINI_OUTPUT_COST_LOW) / 1_000_000
      else:
          low_tier = TIER_THRESHOLD * GEMINI_OUTPUT_COST_LOW / 1_000_000
          high_tier = (output_tokens - TIER_THRESHOLD) * GEMINI_OUTPUT_COST_HIGH / 1_000_000
          output_cost = low_tier + high_tier

      # Calculate cached cost (tiered)
      if cached_tokens <= TIER_THRESHOLD:
          cached_cost = (cached_tokens * GEMINI_CACHED_COST_LOW) / 1_000_000
      else:
          low_tier = TIER_THRESHOLD * GEMINI_CACHED_COST_LOW / 1_000_000
          high_tier = (cached_tokens - TIER_THRESHOLD) * GEMINI_CACHED_COST_HIGH / 1_000_000
          cached_cost = low_tier + high_tier

      return {
          "input_cost_usd": round(input_cost, 6),
          "output_cost_usd": round(output_cost, 6),
          "cached_cost_usd": round(cached_cost, 6),
          "total_cost_usd": round(input_cost + output_cost + cached_cost, 6),
          "tier": "low" if (input_tokens + output_tokens + cached_tokens) <= TIER_THRESHOLD else "high"
      }
  ```
- [ ] **1.3** Extract token counts from Gemini API response:
  - Access `response.usage_metadata.prompt_token_count`
  - Access `response.usage_metadata.candidates_token_count`
  - Access `response.usage_metadata.cached_content_token_count` (if available)
- [ ] **1.4** Handle missing token metadata gracefully (fallback to estimates)

### Task 2: Integrate Langfuse Tracing for Gemini
**File:** `backend/api/providers/gemini_provider.py`

**Subtasks:**
- [ ] **2.1** Import Langfuse tracing utilities:
  ```python
  from backend.api.observability.tracing import observe, get_current_trace
  ```
- [ ] **2.2** Decorate `stream_chat_completion()` with `@observe()`:
  ```python
  @observe(name="gemini_llm_streaming", as_type="generation")
  async def stream_chat_completion(self, messages, **kwargs):
      # Existing streaming logic
  ```
- [ ] **2.3** Update trace with input metadata at start:
  ```python
  trace = get_current_trace()
  if trace:
      trace.update(
          model="gemini-3.0-pro",
          metadata={
              "provider": "gemini",
              "message_count": len(messages),
              "tools_available": bool(kwargs.get("tools"))
          }
      )
  ```
- [ ] **2.4** Capture streaming chunks and accumulate output
- [ ] **2.5** Update trace with final results after streaming completes:
  ```python
  if trace:
      cost_data = self.calculate_cost(input_tokens, output_tokens, cached_tokens)
      trace.update(
          output=full_response_text,
          usage={
              "input": input_tokens,
              "output": output_tokens,
              "total": input_tokens + output_tokens,
              "cached": cached_tokens,
              "unit": "TOKENS"
          },
          metadata={
              **cost_data,
              "streaming": True,
              "finish_reason": finish_reason
          }
      )
  ```
- [ ] **2.6** Handle errors and update trace with error metadata

### Task 3: Add Session and User Linking
**File:** `backend/api/routes/stream.py`

**Subtasks:**
- [ ] **3.1** Set session_id for Langfuse trace (already implemented in Story 8.2):
  ```python
  @observe(name="stream_request", as_type="trace")
  async def stream_endpoint(conversation_id: str):
      trace = get_current_trace()
      if trace:
          trace.update(session_id=conversation_id)
  ```
- [ ] **3.2** Set user_id from conversation metadata:
  ```python
  user_id = await state_manager.get_user_id(conversation_id)
  if trace and user_id:
      trace.update(user_id=str(user_id))
  ```
- [ ] **3.3** Verify session grouping in Langfuse dashboard
- [ ] **3.4** Test per-user cost aggregation queries

### Task 4: Implement Cost Aggregation Logic
**File:** `backend/api/observability/cost_tracker.py` (new file)

**Subtasks:**
- [ ] **4.1** Create `CostTracker` class for aggregating Langfuse data:
  ```python
  class CostTracker:
      def __init__(self, langfuse_client):
          self.client = langfuse_client

      async def get_daily_costs(self, date: str) -> dict:
          """Get costs for specific date, grouped by provider."""
          # Query Langfuse traces for date
          # Aggregate costs by provider
          return {
              "grok-4": 12.45,
              "chatgpt-5": 8.32,
              "gemini-3-pro": 5.67
          }

      async def get_user_costs(self, user_id: str, days: int = 30) -> dict:
          """Get costs for specific user over time period."""
          pass

      async def get_conversation_cost(self, conversation_id: str) -> dict:
          """Get total cost for specific conversation."""
          pass
  ```
- [ ] **4.2** Implement daily cost aggregation (group by date and provider)
- [ ] **4.3** Implement user cost aggregation (group by user_id)
- [ ] **4.4** Implement conversation cost calculation (sum all traces with session_id)
- [ ] **4.5** Add caching layer (Redis) for aggregated costs (1 hour TTL)

### Task 5: Cost Alert System
**File:** `backend/api/observability/cost_alerts.py` (new file)

**Subtasks:**
- [ ] **5.1** Create `CostAlertManager` class:
  ```python
  class CostAlertManager:
      def __init__(self, cost_tracker, alert_threshold: float):
          self.tracker = cost_tracker
          self.threshold = alert_threshold

      async def check_monthly_spend(self, provider: str) -> dict:
          """Check if monthly spend exceeds threshold."""
          monthly_cost = await self.tracker.get_monthly_costs(provider)
          if monthly_cost > self.threshold:
              await self._send_alert(provider, monthly_cost)
          return {"provider": provider, "cost": monthly_cost, "threshold": self.threshold}
  ```
- [ ] **5.2** Implement alert logging (structured logs with `event="cost_alert"`)
- [ ] **5.3** Add environment variable: `GEMINI_COST_ALERT_THRESHOLD` (default $500)
- [ ] **5.4** Integrate into background task (check daily at midnight UTC)
- [ ] **5.5** Test alert triggering with mock data

### Task 6: Add Cost Dashboard Endpoint
**File:** `backend/api/routes/observability.py` (new file)

**Subtasks:**
- [ ] **6.1** Create `/api/observability/costs` endpoint:
  ```python
  @router.get("/costs")
  async def get_cost_dashboard(
      days: int = 30,
      user_id: str | None = None
  ):
      """Get cost dashboard data."""
      tracker = CostTracker(langfuse_client)

      costs = await tracker.get_daily_costs_range(days)
      by_provider = await tracker.get_costs_by_provider(days)
      top_users = await tracker.get_top_users_by_cost(days, limit=10)

      return {
          "period_days": days,
          "total_cost": sum(costs.values()),
          "by_provider": by_provider,
          "by_date": costs,
          "top_users": top_users if not user_id else None,
          "user_cost": await tracker.get_user_costs(user_id, days) if user_id else None
      }
  ```
- [ ] **6.2** Add authentication for observability endpoints (admin only)
- [ ] **6.3** Test endpoint with sample data

### Task 7: Update Cost Calculation Tests
**File:** `tests/unit/test_gemini_cost_tracking.py` (new file)

**Subtasks:**
- [ ] **7.1** Test `calculate_cost()` method:
  ```python
  def test_gemini_cost_calculation():
      provider = GeminiProvider()
      cost = provider.calculate_cost(
          input_tokens=10000,
          output_tokens=2000,
          cached_tokens=0
      )
      # With example pricing: $2.50 input, $10.00 output per 1M tokens
      assert cost["input_cost_usd"] == 0.025000  # 10k * $2.50 / 1M
      assert cost["output_cost_usd"] == 0.020000  # 2k * $10.00 / 1M
      assert cost["total_cost_usd"] == 0.045000
  ```
- [ ] **7.2** Test cost calculation with cached tokens
- [ ] **7.3** Test zero token edge case
- [ ] **7.4** Test large token counts (>1M tokens)
- [ ] **7.5** Test rounding behavior (6 decimal places)

### Task 8: Integration Test for Langfuse Cost Tracking
**File:** `tests/integration/test_gemini_langfuse_tracing.py` (new file)

**Subtasks:**
- [ ] **8.1** Test full request with Langfuse tracing:
  ```python
  async def test_gemini_cost_tracking_end_to_end():
      # Make chat request with Gemini provider
      response = await client.post("/api/chat", json={
          "message": "Hello!",
          "conversation_id": "test-123"
      })

      # Wait for Langfuse flush
      await asyncio.sleep(2)

      # Query Langfuse for trace
      traces = langfuse_client.get_traces(session_id="test-123")
      assert len(traces) > 0

      generation = traces[0].get_generation("gemini_llm_streaming")
      assert generation.model == "gemini-3-pro-preview"
      assert generation.usage.input > 0
      assert generation.usage.output > 0
      assert "total_cost_usd" in generation.metadata
      assert generation.metadata["provider"] == "gemini"
  ```
- [ ] **8.2** Test session linking (multiple requests same conversation_id)
- [ ] **8.3** Test user_id capture
- [ ] **8.4** Test cost metadata accuracy

---

## Dev Notes

### Gemini 3 Pro Pricing (as of Dec 2024)
**Source:** https://ai.google.dev/pricing (verified Dec 2024)

**Tiered Pricing Structure:**

| Token Count | Input Cost | Output Cost | Cached Input Cost |
|-------------|------------|-------------|-------------------|
| ≤200k tokens | $2.00 per 1M | $12.00 per 1M | $0.20 per 1M |
| >200k tokens | $4.00 per 1M | $18.00 per 1M | $0.40 per 1M |

**Context Caching Storage:** $4.50 per 1M tokens/hour

**Key Points:**
- Tiered pricing activates at 200k token threshold
- Context caching reduces input costs by 10x (first 200k: $2.00 → $0.20)
- **Gemini 3 is PAID ONLY** - no free tier available
- Batch API available with 50% discount

**Comparison with competitors:**
- **Grok-4:** FREE during promotional period (until Nov 21, 2025), then TBD
- **ChatGPT-5:** $X per 1M input, $Y per 1M output (check latest)
- **Gemini 3 Pro:** Premium flagship model, 1M context, multimodal, tiered pricing

### Langfuse Cost Tracking Pattern (from Story 8.5)

```python
# backend/api/llm_client.py (preserve this pattern)
@observe(name="llm_streaming", as_type="generation")
async def stream_chat_completion(self, messages, **kwargs):
    trace = get_current_trace()

    # Set model at start
    if trace:
        trace.update(model=self.provider.get_model_name())

    # Stream chunks and accumulate
    full_response = ""
    async for chunk in self.provider.stream_chat_completion(messages, **kwargs):
        full_response += chunk.get("content", "")
        yield chunk

    # Calculate cost after streaming
    usage = self.provider.get_usage_metadata()
    cost = self.provider.calculate_cost(
        input_tokens=usage["input"],
        output_tokens=usage["output"],
        cached_tokens=usage.get("cached", 0)
    )

    # Update trace with final data
    if trace:
        trace.update(
            output=full_response,
            usage={
                "input": usage["input"],
                "output": usage["output"],
                "total": usage["input"] + usage["output"],
                "unit": "TOKENS"
            },
            metadata={
                **cost,
                "provider": self.provider.get_provider_name()
            }
        )
```

### Token Counting for Tool Calls

When tools are used, token counts include:
- **Input:** Prompt + tool definitions (schemas) + previous tool results
- **Output:** Generated text + tool call arguments
- **Example:**
  - Prompt: 500 tokens
  - Tool definitions: 300 tokens (for 3 tools)
  - Tool result in context: 200 tokens
  - Total input: 1000 tokens

### Cost Aggregation Query (Langfuse API)

```python
# Example: Get total costs for last 30 days
from datetime import datetime, timedelta

start_date = datetime.now() - timedelta(days=30)
traces = langfuse_client.get_traces(
    from_timestamp=start_date,
    metadata_filter={"provider": "gemini"}
)

total_cost = sum(
    trace.metadata.get("total_cost_usd", 0)
    for trace in traces
)
```

### Testing Strategy

**Unit Tests (4 hours estimated):**
- Cost calculation accuracy (various token counts)
- Pricing constant correctness
- Rounding behavior
- Edge cases (zero tokens, very large counts)

**Integration Tests (6 hours estimated):**
- End-to-end Langfuse tracing with cost metadata
- Session and user linking
- Cost aggregation queries
- Alert triggering

**Manual Testing:**
- Langfuse dashboard verification (traces visible with costs)
- Cost comparison across providers
- Alert threshold testing

### Key Constraints

1. **Accuracy:** Cost calculations must be precise (financial data)
2. **Performance:** Cost tracking should not add >50ms latency
3. **Fire-and-Forget:** Langfuse failures must not block requests
4. **Privacy:** User cost data must be secured (admin-only access)
5. **Pricing Updates:** Easy to update pricing constants without code changes (consider env vars)

### Dependencies

- **Story 8.1:** Core Langfuse integration (client, decorators)
- **Story 8.2:** Chat endpoint tracing (session linking pattern)
- **Story 8.5:** Cost tracking implementation for Grok/ChatGPT (baseline)
- **Story 9.2:** GeminiProvider streaming (must extract token metadata)

### Definition of Done

- [ ] All 6 acceptance criteria met and validated
- [ ] All 8 tasks completed with subtasks
- [ ] Unit tests: 100% coverage for cost calculation logic
- [ ] Integration tests: Langfuse cost tracking verified end-to-end
- [ ] Gemini costs visible in Langfuse dashboard
- [ ] Cost alerts working with configurable threshold
- [ ] Cost comparison dashboard shows all providers
- [ ] Code reviewed and approved
- [ ] Pricing constants documented with source (Google pricing page)
- [ ] Manual testing completed: Langfuse dashboard, cost accuracy

---

## Technical Context

### Langfuse Documentation
- Generations and cost tracking: https://langfuse.com/docs/tracing/generations
- Usage metadata: https://langfuse.com/docs/tracing/usage
- Custom metadata: https://langfuse.com/docs/tracing/metadata

### Gemini API Usage Metadata
- `response.usage_metadata.prompt_token_count` - Input tokens
- `response.usage_metadata.candidates_token_count` - Output tokens
- `response.usage_metadata.cached_content_token_count` - Cached tokens (if applicable)
- `response.usage_metadata.total_token_count` - Total tokens

### Related Stories
- **Story 8.1:** Core Langfuse Integration (baseline patterns)
- **Story 8.2:** Chat Endpoint Tracing (session linking)
- **Story 8.5:** Cost Tracking & Analytics (Grok/ChatGPT implementation)
- **Story 9.2:** Implement Gemini Provider (token extraction)

---

## Notes

Created: 2025-12-11
Last Updated: 2025-12-11
Created By: BMad Master (via sprint planning workflow)
