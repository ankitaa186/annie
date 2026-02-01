# Story 20.3: Health Status & System Indicators

Status: review

## Story

As a user,
I want to see real-time health status and active LLM indicator in the header,
so that I have transparency into Annie's system state and know which AI is responding.

## Acceptance Criteria

1. Health status component shows colored dots for each service
2. Services monitored: Backend API, MCP Server, Redis, agentic-memories
3. Color coding: green (ok), yellow (degraded), red (unavailable)
4. LLM indicator shows active provider name (e.g., "Gemini 2.0", "Grok-4")
5. Health endpoint polled every 30 seconds
6. Tooltip on hover shows detailed status per component
7. Visual indication when any service is degraded (subtle warning)
8. No jarring UI changes on status updates (smooth transitions)
9. Initial loading state while first health check completes
10. Error handling if health endpoint unreachable

## Tasks / Subtasks

- [x] Task 1: Create health status hook (AC: 5, 9, 10)
  - [x] 1.1 Create `web/src/lib/hooks/useHealth.ts`
  - [x] 1.2 Implement polling with 30-second interval
  - [x] 1.3 Parse `/health/full` response
  - [x] 1.4 Handle network errors gracefully
  - [x] 1.5 Add loading state for initial fetch

- [x] Task 2: Build HealthIndicator component (AC: 1, 2, 3, 7)
  - [x] 2.1 Create `web/src/components/status/HealthIndicator.tsx`
  - [x] 2.2 Display colored dots for each service
  - [x] 2.3 Map status to colors (ok->green, degraded->yellow, unavailable->red)
  - [x] 2.4 Add subtle warning indicator when degraded

- [x] Task 3: Build LLMIndicator component (AC: 4)
  - [x] 3.1 Create `web/src/components/status/LLMIndicator.tsx`
  - [x] 3.2 Display active LLM provider name
  - [x] 3.3 Extract LLM info from health response or config

- [x] Task 4: Implement tooltips (AC: 6)
  - [x] 4.1 Add Radix UI Tooltip component
  - [x] 4.2 Show detailed status on health dot hover
  - [x] 4.3 Include component name and status text
  - [x] 4.4 Show timestamp of last check

- [x] Task 5: Add smooth transitions (AC: 8)
  - [x] 5.1 Animate color changes
  - [x] 5.2 Prevent layout shift on status change
  - [x] 5.3 Add fade transitions

- [x] Task 6: Integrate with Header
  - [x] 6.1 Add HealthIndicator to Header component
  - [x] 6.2 Add LLMIndicator to Header component
  - [x] 6.3 Position appropriately in header layout

- [x] Task 7: Update Zustand store
  - [x] 7.1 Add health state to appStore
  - [x] 7.2 Add activeLLM state
  - [x] 7.3 Create updateHealth action

## Dev Notes

### Health API Response Structure

```json
// GET /health/full
{
  "status": "ok",
  "components": {
    "mcp_server": "ok",
    "redis": "ok",
    "llm_api": "ok",
    "agentic_memories": {
      "status": "ok",
      "checks": { "chroma": {"ok": true}, ... }
    },
    "proactive_worker": { "status": "ok", "alive": true },
    "langfuse": { "enabled": true, "client_available": true }
  },
  "timestamp": "2026-01-26T10:00:00Z"
}
```

### Component Design

```tsx
// HealthIndicator.tsx
<div className="flex items-center gap-1.5">
  <Tooltip content="Backend API: OK">
    <div className="w-2 h-2 rounded-full bg-green-500" />
  </Tooltip>
  <Tooltip content="MCP Server: OK">
    <div className="w-2 h-2 rounded-full bg-green-500" />
  </Tooltip>
  <Tooltip content="Redis: OK">
    <div className="w-2 h-2 rounded-full bg-green-500" />
  </Tooltip>
  <Tooltip content="Memories: Degraded">
    <div className="w-2 h-2 rounded-full bg-yellow-500" />
  </Tooltip>
</div>
```

### useHealth Hook

```typescript
// web/src/lib/hooks/useHealth.ts
export function useHealth() {
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchHealth = async () => {
      try {
        const response = await fetch('/api/health/full');
        const data = await response.json();
        setHealth(data);
        setError(null);
      } catch (e) {
        setError('Unable to check system health');
      } finally {
        setLoading(false);
      }
    };

    fetchHealth();
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  return { health, loading, error };
}
```

### Status Color Mapping

```typescript
const STATUS_COLORS = {
  ok: 'bg-green-500',
  degraded: 'bg-yellow-500',
  unavailable: 'bg-red-500',
  unknown: 'bg-gray-400',
};
```

### LLM Provider Names

```typescript
const LLM_DISPLAY_NAMES: Record<string, string> = {
  'gemini-3-pro-preview': 'Gemini 3 Pro',
  'grok-4': 'Grok-4',
  'chatgpt-5': 'ChatGPT-5',
};
```

### Project Structure

```
web/src/
├── components/
│   └── status/
│       ├── HealthIndicator.tsx    # NEW
│       └── LLMIndicator.tsx       # NEW
└── lib/
    └── hooks/
        └── useHealth.ts           # NEW
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.3]
- [Source: backend/api/main.py#full_health_check]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md]

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/20-3-health-status-system-indicators.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

**2026-01-26 - Implementation Plan:**
1. Task 1: Create useHealth hook with polling, error handling, loading states
2. Task 2: Build HealthIndicator with colored dots and warning states
3. Task 3: Build LLMIndicator to display active provider
4. Task 4: Implement tooltips using existing Radix UI Tooltip
5. Task 5: Add CSS transitions for smooth status changes
6. Task 6: Integrate components into Header
7. Task 7: Update Zustand store with health state

**Approach:**
- Use existing Radix Tooltip from web/src/components/ui/tooltip.tsx
- TypeScript types for health response matching backend /health/full
- 30-second polling interval with cleanup on unmount
- Graceful error handling with "unknown" state fallback

### Completion Notes List

- Implemented useHealth hook with 30-second polling, comprehensive TypeScript types, and graceful error handling
- Created HealthIndicator component with colored status dots for Backend, MCP, Redis, and Memories services
- Built LLMIndicator with friendly display names for Gemini, Grok, and ChatGPT providers
- Used existing Radix UI Tooltip for accessible hover information with last check timestamp
- Added smooth CSS transitions (transition-colors duration-300) for non-jarring status changes
- Integrated both components into Header, replacing placeholder elements from Story 20.2
- Extended Zustand appStore with health state, activeLLM, and related actions/selectors
- Created comprehensive test files for useHealth hook, HealthIndicator, and LLMIndicator components

### File List

**New Files:**
- web/src/lib/hooks/useHealth.ts - Health polling hook with TypeScript types
- web/src/lib/hooks/index.ts - Barrel export for lib hooks
- web/src/components/status/HealthIndicator.tsx - Status dots component
- web/src/components/status/LLMIndicator.tsx - LLM provider badge
- web/src/components/status/index.ts - Barrel export for status components
- web/src/lib/hooks/__tests__/useHealth.test.ts - Unit tests for useHealth
- web/src/components/status/__tests__/HealthIndicator.test.tsx - Unit tests for HealthIndicator
- web/src/components/status/__tests__/LLMIndicator.test.tsx - Unit tests for LLMIndicator

**Modified Files:**
- web/src/lib/stores/appStore.ts - Added health state, activeLLM, and related actions
- web/src/components/layout/Header.tsx - Replaced placeholders with actual components

### Change Log

- 2026-01-26: Implemented Story 20.3 - Health Status & System Indicators (All 7 tasks complete)
