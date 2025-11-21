# Epic 8: Langfuse Integration for LLM Observability

**Status:** Planned
**Priority:** Medium
**Estimated Effort:** 2-3 days
**Based on:** agentic-memories implementation (October 2025)

---

## Overview

Integrate Langfuse Cloud for end-to-end LLM observability and tracing across all Annie components. This enables comprehensive monitoring of LLM interactions, tool calls, memory operations, and profile management with minimal performance overhead.

---

## Business Value

1. **Cost Monitoring**: Track LLM API costs across Grok-4 and ChatGPT-5
2. **Performance Optimization**: Identify slow LLM calls and optimize prompts
3. **Debugging**: Trace complete conversation flows with tool calls
4. **Quality Assurance**: Monitor response quality and user satisfaction
5. **Analytics**: Understand usage patterns and feature adoption

---

## Technical Architecture

### Langfuse Setup
- **Hosted Solution**: Langfuse Cloud (https://us.cloud.langfuse.com)
- **SDK Version**: `langfuse==2.36.0` (from agentic-memories)
- **Integration Pattern**: Singleton client + request-scoped tracing
- **Performance**: Fire-and-forget (batch_size=10, flush_interval=1s)

### Key Components (from agentic-memories pattern)
1. **Singleton Client** (`backend/api/observability/langfuse_client.py`)
   - Lazy initialization
   - Background flushing
   - Graceful degradation

2. **Tracing Utilities** (`backend/api/observability/tracing.py`)
   - Request-scoped context using `contextvars`
   - `start_trace()`, `start_span()`, `end_span()`
   - Async-safe context management

3. **Configuration** (`backend/api/config.py`)
   - `get_langfuse_public_key()`
   - `get_langfuse_secret_key()`
   - `get_langfuse_host()`
   - `is_langfuse_enabled()`

### Trace Hierarchy
```
Request Trace (API endpoint: /api/chat)
├── Span: chat_processing
│   ├── Generation: llm_call (Grok-4/ChatGPT-5)
│   │   ├── Input: system prompt + user message
│   │   ├── Output: assistant response
│   │   └── Metadata: model, tokens, cost
│   ├── Span: tool_execution
│   │   ├── Span: internet_search
│   │   ├── Span: store_memory
│   │   └── Span: retrieve_memories
│   └── Span: profile_management
│       ├── Span: load_profile
│       └── Span: refresh_profile (background)
```

---

## Environment Configuration

### Required Variables (add to `.env` and `env.example`)
```bash
# Langfuse Tracing (optional - disabled if not configured)
LANGFUSE_PUBLIC_KEY=pk-lf-...  # Get from Langfuse Cloud dashboard
LANGFUSE_SECRET_KEY=sk-lf-...  # Get from Langfuse Cloud dashboard
LANGFUSE_HOST=https://us.cloud.langfuse.com  # Default for Langfuse Cloud

# Project Configuration
LANGFUSE_PROJECT_NAME=Annie  # Project name in Langfuse dashboard
LANGFUSE_ENVIRONMENT=development  # development, staging, production
```

### docker-compose.yml Updates
```yaml
backend:
  environment:
    - LANGFUSE_PUBLIC_KEY=${LANGFUSE_PUBLIC_KEY:-}
    - LANGFUSE_SECRET_KEY=${LANGFUSE_SECRET_KEY:-}
    - LANGFUSE_HOST=${LANGFUSE_HOST:-https://us.cloud.langfuse.com}
```

---

## Stories Breakdown

### **Story 8.1: Core Langfuse Integration** (1 day)

**Goal**: Set up Langfuse client and configuration infrastructure

**Tasks**:
1. Add `langfuse==2.36.0` to `backend/requirements.txt`
2. Create `backend/api/observability/` directory
3. Implement `backend/api/observability/langfuse_client.py`:
   - Singleton pattern (replicate from agentic-memories)
   - Lazy initialization
   - Background flushing (batch_size=10, flush_interval=1s)
   - `atexit` handler for graceful shutdown
   - `ping_langfuse()` health check
4. Implement `backend/api/observability/tracing.py`:
   - `contextvars` for async-safe context
   - `start_trace(name, user_id, metadata)`
   - `get_current_trace()`
   - `start_span(name, metadata, input)`
   - `end_span(output, level)`
   - `trace_error(exception, metadata)`
5. Add Langfuse config to `backend/api/config.py`:
   - `get_langfuse_public_key()` with `@lru_cache`
   - `get_langfuse_secret_key()` with `@lru_cache`
   - `get_langfuse_host()` with `@lru_cache`
   - `is_langfuse_enabled()` (checks both keys exist)
6. Update `.env` and `env.example` with Langfuse variables
7. Update `docker-compose.yml` with Langfuse env vars

**Acceptance Criteria**:
- [ ] Langfuse client initializes when keys are configured
- [ ] Gracefully degrades when keys are missing (no crashes)
- [ ] Health check (`ping_langfuse()`) returns correct status
- [ ] Context management works across async operations
- [ ] Zero crashes if Langfuse is unavailable

---

### **Story 8.2: Chat Endpoint Tracing** (0.5 days)

**Goal**: Trace all chat requests and LLM calls

**Tasks**:
1. Instrument `/api/chat` endpoint:
   - Start trace with user_id, conversation_id
   - Capture request metadata (platform, message_length)
   - Update trace with response status
2. Instrument `/api/stream` endpoint:
   - Inherit trace from chat request
   - Create span for LLM streaming
   - Capture chunk counts and timing
3. Instrument `backend/api/llm_client.py`:
   - Wrap LLM calls with `generation` tracking
   - Capture prompts (truncated to 1000 chars)
   - Capture completions (truncated to 1000 chars)
   - Track token usage (prompt_tokens, completion_tokens, total_tokens)
   - Calculate cost per request
   - Record model name and provider (grok-4/chatgpt-5)

**Acceptance Criteria**:
- [ ] Every chat request creates a trace in Langfuse
- [ ] LLM calls visible as generations with:
  - Input prompt
  - Output completion
  - Token counts
  - Model name
  - Cost calculation
- [ ] Traces linked by conversation_id
- [ ] User_id filterable in Langfuse UI

---

### **Story 8.3: Tool Execution Tracing** (0.5 days)

**Goal**: Trace all MCP tool calls

**Tasks**:
1. Instrument `backend/api/mcp_client.py`:
   - Create span for each tool call
   - Capture tool name, parameters
   - Record execution duration
   - Track success/failure status
   - Log errors with context
2. Instrument specific tools:
   - `internet_search` (Grok-4 Live Search)
   - `store_memory` (agentic-memories)
   - `retrieve_memories` (agentic-memories)
   - `get_user_profile` (MCP profile tool)

**Acceptance Criteria**:
- [ ] All tool calls traced as spans
- [ ] Tool parameters captured (sanitized for sensitive data)
- [ ] Tool results summarized (not full response)
- [ ] Failed tools logged with error details
- [ ] Tool spans nested under parent LLM generation

---

### **Story 8.4: Memory & Profile Tracing** (0.5 days)

**Goal**: Trace memory and profile operations

**Tasks**:
1. Instrument `backend/api/memory.py`:
   - Span for `store_conversation_memory()`
   - Span for `format_memories_for_llm()`
   - Track memory storage success/failure
   - Track queue operations (fallback)
2. Instrument `backend/api/profile.py`:
   - Span for `load_profile_from_cache()`
   - Span for `refresh_profile_background()`
   - Track cache hits/misses
   - Track refresh triggers (message count, time-based)
   - Capture profile completeness metrics

**Acceptance Criteria**:
- [ ] Memory operations traced with:
  - Message count
  - Storage status (stored/queued)
  - Duration
- [ ] Profile operations traced with:
  - Cache hit/miss
  - Completeness score
  - Refresh trigger type
- [ ] Background operations properly linked to parent trace

---

### **Story 8.5: Cost Tracking & Analytics** (0.5 days)

**Goal**: Calculate and track LLM costs

**Tasks**:
1. Implement cost calculation in `backend/api/llm_client.py`:
   - Grok-4 costs (including Live Search: $0.025/source)
   - ChatGPT-5 costs (based on token pricing)
2. Add cost metadata to generations:
   - `input_cost`
   - `output_cost`
   - `total_cost`
   - `live_search_cost` (if applicable)
3. Create Langfuse dashboards:
   - Daily/weekly/monthly cost summaries
   - Cost breakdown by user, feature, model
   - Token usage trends
4. Set up cost alerts in Langfuse (optional)

**Acceptance Criteria**:
- [ ] Costs calculated accurately for Grok-4 and ChatGPT-5
- [ ] Live Search costs tracked separately
- [ ] Cost metadata visible in Langfuse traces
- [ ] Dashboard shows cost trends over time

---

### **Story 8.6: Health Check & Documentation** (0.5 days)

**Goal**: Add health check and comprehensive documentation

**Tasks**:
1. Add Langfuse check to `/health` endpoint:
   - Status: enabled/disabled
   - Client availability
   - Last successful flush
2. Update `CLAUDE.md` with Langfuse section:
   - How to get Langfuse Cloud credentials
   - How to create "Annie" project in Langfuse
   - How to access traces
   - Cost monitoring guide
   - Troubleshooting common issues
3. Create `docs/LANGFUSE_IMPLEMENTATION.md`:
   - Architecture overview
   - Trace hierarchy
   - Integration points
   - Success metrics
   - Replicates agentic-memories doc structure

**Acceptance Criteria**:
- [ ] Health endpoint shows Langfuse status
- [ ] CLAUDE.md has Langfuse setup instructions
- [ ] Implementation doc matches agentic-memories format
- [ ] Example traces documented

---

## Implementation Notes (from agentic-memories)

### Performance Characteristics
- **Async background logging**: Fire-and-forget pattern
- **Batching**: Traces batched (10 at a time)
- **Flush interval**: 1 second
- **Graceful degradation**: App continues if Langfuse unavailable
- **Expected overhead**: < 10ms p95 latency

### Data Truncation (for privacy/performance)
- Prompts: 1000 characters
- Completions: 1000 characters
- Tool parameters: 500 characters
- No PII beyond user_id

### Context Management
- Uses Python `contextvars` for async-safe trace context
- Each request gets isolated trace
- Spans automatically nested under current trace
- No manual context passing required

---

## Success Metrics

- [ ] 100% of LLM requests traced
- [ ] 100% of tool calls traced
- [ ] End-to-end latency visible in traces
- [ ] Cost tracking accurate within 1%
- [ ] Zero performance degradation (<10ms overhead)
- [ ] Team can debug issues 3x faster using traces

---

## Rollout Strategy

### Phase 1: Development (Current)
- Integration implemented but disabled by default
- Can be enabled in dev environment by setting keys

### Phase 2: Dev Environment Testing
- Set Langfuse credentials in dev `.env`
- Monitor for issues
- Validate trace quality
- Measure latency impact

### Phase 3: Production
- Enable in production after dev validation
- Monitor p95 latency
- Set up cost alerts
- Create team dashboards

---

## Dependencies

**Prerequisites**:
- Langfuse Cloud account (free tier available)
- Python 3.12+
- Docker Compose environment

**No blocking dependencies on other epics**

---

## Future Enhancements

1. Add more granular spans:
   - Redis operations
   - State management operations
   - Session creation/retrieval
2. Add custom metrics:
   - User satisfaction scores
   - Response quality ratings
   - Feature usage analytics
3. Langfuse prompts management (prompt versioning)
4. A/B testing via Langfuse experiments
5. User feedback collection

---

## References

- **agentic-memories implementation**: `/Users/Ankit/dev/agentic-memories/`
  - `LANGFUSE_IMPLEMENTATION.md`: Complete implementation guide
  - `src/dependencies/langfuse_client.py`: Singleton client pattern
  - `src/services/tracing.py`: Request-scoped tracing utilities
  - `src/config.py`: Configuration functions
- **Langfuse Docs**: https://langfuse.com/docs
- **Langfuse Python SDK**: https://github.com/langfuse/langfuse-python
