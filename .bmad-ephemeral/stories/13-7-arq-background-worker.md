# Story 13.7: Arq Background Worker

**Epic:** 13 - Proactive AI Worker
**Story ID:** 13.7
**Status:** complete
**Estimated Effort:** 1 day

---

## User Story

**As a** system,
**I want** a background worker that polls and processes triggers,
**So that** proactive messages are sent at the right times.

---

## Acceptance Criteria

### AC #1: Scheduled Trigger Polling
**Given** worker running,
**When** poll interval reached (30s),
**Then:**
- Calls `IntentsClient.get_pending(trigger_type="scheduled")`
- For each due trigger:
  1. Claims trigger via `IntentsClient.claim_intent(id)`
  2. If 409 Conflict → Skip (already claimed by another worker)
  3. If claimed → Pass to processing pipeline

### AC #2: Condition Trigger Polling
**Given** worker running,
**When** poll interval reached (60s),
**Then:**
- Calls `IntentsClient.get_pending(trigger_type="condition")`
- For each trigger:
  1. Skip if `in_cooldown` flag is true
  2. Claims trigger via `IntentsClient.claim_intent(id)`
  3. If 409 Conflict → Skip (already claimed by another worker)
  4. Evaluates condition via evaluators (fast, no LLM)
  5. If condition met → Pass to processing pipeline
  6. If not met → Call `fire_intent()` with status="condition_not_met" (clears claim, updates next_check)

### AC #3: Processing Pipeline
**Given** claimed trigger to process,
**Then** executes in order:
1. Subconscious gate check
2. Wake-up agent execution
3. Telegram delivery (if not skipped)
4. Fire report to agentic-memories (clears claim)

### AC #4: Fire Reporting
**Given** trigger processed,
**When** reporting to agentic-memories,
**Then:**
- Calls `IntentsClient.fire_intent()` with `IntentFireRequest`:
  - `status`: `success` | `failed` | `gate_blocked` | `condition_not_met`
  - `message_id`: Telegram message ID (if sent)
  - `message_preview`: First 100 chars of message
  - `trigger_data`: Runtime data (price at fire time, etc.)
  - `gate_result`: Subconscious gate details (if blocked)
  - `evaluation_ms`: Condition evaluation time
  - `generation_ms`: LLM generation time
  - `delivery_ms`: Telegram delivery time
  - `error_message`: Error details (if failed)

### AC #5: Error Resilience
**Given** worker failure,
**When** exception occurs,
**Then:**
- Worker continues running (doesn't crash)
- Failed trigger logged
- Will retry on next poll cycle
- Error logged to Langfuse

### AC #6: Worker Configuration
**Given** Arq worker,
**Then** configuration includes:
- Cron job: scheduled polling every 30s
- Cron job: condition polling every 60s
- Redis connection from environment
- Max concurrent jobs: 10
- Job timeout: 60s

---

## Tasks

### Task 1: Set up Arq worker structure
- [x] Create `backend/api/proactive/worker.py`
- [x] Add `arq>=0.25.0` to requirements.txt (already present)
- [x] Configure Redis settings from environment
- [x] Create `WorkerSettings` class

### Task 2: Implement trigger polling
- [x] Create `poll_triggers` async function
- [x] Call `get_pending()` to get all due intents
- [x] Categorize by trigger_type:
  - Time-based: `cron`, `interval`, `once` → process directly
  - Condition-based: `price`, `silence`, `portfolio` → evaluate first
- [x] For each trigger: claim → process → fire
- [x] Handle 409 Conflict (skip - already claimed)
- [x] Register as cron job (every minute)

### Task 3: Implement condition evaluation
- [x] For condition triggers, check `in_cooldown` flag in metadata first
- [x] If not in cooldown, evaluate condition via evaluators
- [x] If condition met → proceed to processing pipeline
- [x] If condition not met → fire with status="condition_not_met" (updates next_check)

### Task 4: Implement processing pipeline
- [x] Create `process_trigger` async function
- [x] Call subconscious gate check
- [x] Call wake-up agent if gate passes
- [x] Call telegram delivery if not skipped
- [x] Call fire_intent with full report

### Task 5: Add error handling
- [x] Wrap all processing in try/except
- [x] Log errors with trigger context
- [x] Ensure worker never crashes
- [x] Add Langfuse error tracing

### Task 6: Create worker Dockerfile/entrypoint
- [ ] Create entrypoint for running Arq worker (deferred to Story 13.11)
- [ ] Configure in docker-compose (deferred to Story 13.11)
- [x] Document how to run worker locally (via module execution)

---

## Dev Notes

### Technical Notes
- See Design Doc Section 8.3 for worker architecture
- New dependency: `arq>=0.25.0`
- Runs as separate process/container
- Uses same Redis as main backend

### Files to Create/Modify
- `backend/api/proactive/worker.py` (new)
- `backend/api/proactive/__init__.py` (export worker)
- `backend/requirements.txt` (add arq)
- `docker-compose.yml` (optional worker service)

### Arq Cron Job Configuration
```python
cron_jobs = [
    cron(poll_scheduled_triggers, second={0, 30}),  # Every 30 seconds
    cron(poll_condition_triggers, minute={0, 1, 2, ...}),  # Every minute
]
```

### Fire Report Fields
- status: success | skipped | gate_blocked | condition_not_met | error
- message_id: Telegram message ID (if sent)
- message_preview: First 100 chars of message
- skip_reason: Why skipped (if applicable)
- tools_called: List of tools used
- execution_time_ms: Total processing time

---

## Dev Agent Record

### Context Reference
- Story Context: `.bmad-ephemeral/stories/13-7-arq-background-worker.context.xml`
- Design Document: `docs/design/proactive-ai-architecture.md` (Section 8.3 - Worker Architecture)

### Implementation Notes
- Created unified `poll_triggers` function that runs every minute (instead of separate scheduled/condition polling)
- Simplified approach: Single cron job polls all pending intents, then categorizes by trigger_type
- Condition triggers check `in_cooldown` flag in metadata before claiming
- Full processing pipeline implemented with 4 phases: gate → agent → delivery → fire
- Comprehensive error handling at 3 levels:
  1. Individual trigger errors (logged, continue processing other triggers)
  2. Poll cycle errors (logged, retry next cycle)
  3. Fire reporting errors (logged but never crashes worker)
- Langfuse tracing on all major functions (@observe decorators)
- Worker can be run via: `python -m arq api.proactive.worker.WorkerSettings`
- Direct test execution: `python -m api.proactive.worker`
- Docker integration deferred to Story 13.11 (Integration Testing)

### Implementation Details

**Key Functions:**
- `poll_triggers(ctx)`: Main cron job, runs every minute
- `process_trigger(trigger, clients...)`: Full pipeline execution
- `handle_condition_trigger(trigger, client)`: Evaluate condition, fire if not met
- `fire_trigger_report(client, trigger_id, ...)`: Build and send fire report

**Error Handling:**
- Per-trigger try/except: Logs error, continues processing other triggers
- Poll cycle try/except: Logs error, worker retries next minute
- Fire reporting try/except: Logs error but never crashes
- Network errors gracefully handled (IntentsNetworkError)

**Observability:**
- Langfuse traces: `poll_triggers` (trace), `process_trigger` (trace), `handle_condition_trigger` (span), `fire_trigger_report` (span)
- Structured logging with context (trigger_id, user_id, timing, status)
- Poll statistics logged: pending_count, claimed, processed, conflicts, skipped_cooldown, condition_not_met

**Claims-Based Multi-Worker Safety:**
- `claim_intent()` returns `{"conflict": True}` for 409 responses
- Worker skips already-claimed triggers without error
- Safe to run multiple workers for HA/scale

### Verification
- [x] Worker polls all pending triggers every minute (unified polling)
- [x] Claims prevent duplicate processing (409 Conflict → skip)
- [x] Condition triggers check in_cooldown flag before claiming
- [x] Condition evaluation fires condition_not_met if not met
- [x] Pipeline executes gate → agent → delivery → report
- [x] Worker survives errors and continues running
- [x] Fire reports include all required fields (status, timing, message_id, etc.)
- [x] Langfuse tracing enabled on all major functions
- [x] Structured logging with trigger context
- [ ] Integration testing with real agentic-memories (Story 13.11)
- [ ] Docker deployment (Story 13.11)
