# Story 20.3: Health Status & System Indicators

Status: drafted

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

- [ ] Task 1: Create health status hook (AC: 5, 9, 10)
  - [ ] 1.1 Create `web/src/lib/hooks/useHealth.ts`
  - [ ] 1.2 Implement polling with 30-second interval
  - [ ] 1.3 Parse `/health/full` response
  - [ ] 1.4 Handle network errors gracefully
  - [ ] 1.5 Add loading state for initial fetch

- [ ] Task 2: Build HealthIndicator component (AC: 1, 2, 3, 7)
  - [ ] 2.1 Create `web/src/components/status/HealthIndicator.tsx`
  - [ ] 2.2 Display colored dots for each service
  - [ ] 2.3 Map status to colors (ok→green, degraded→yellow, unavailable→red)
  - [ ] 2.4 Add subtle warning indicator when degraded

- [ ] Task 3: Build LLMIndicator component (AC: 4)
  - [ ] 3.1 Create `web/src/components/status/LLMIndicator.tsx`
  - [ ] 3.2 Display active LLM provider name
  - [ ] 3.3 Extract LLM info from health response or config

- [ ] Task 4: Implement tooltips (AC: 6)
  - [ ] 4.1 Add Radix UI Tooltip component
  - [ ] 4.2 Show detailed status on health dot hover
  - [ ] 4.3 Include component name and status text
  - [ ] 4.4 Show timestamp of last check

- [ ] Task 5: Add smooth transitions (AC: 8)
  - [ ] 5.1 Animate color changes
  - [ ] 5.2 Prevent layout shift on status change
  - [ ] 5.3 Add fade transitions

- [ ] Task 6: Integrate with Header
  - [ ] 6.1 Add HealthIndicator to Header component
  - [ ] 6.2 Add LLMIndicator to Header component
  - [ ] 6.3 Position appropriately in header layout

- [ ] Task 7: Update Zustand store
  - [ ] 7.1 Add health state to appStore
  - [ ] 7.2 Add activeLLM state
  - [ ] 7.3 Create updateHealth action

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

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
