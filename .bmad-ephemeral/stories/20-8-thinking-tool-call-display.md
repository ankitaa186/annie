# Story 20.8: Thinking & Tool Call Display

Status: ready-for-dev

## Story

As a user,
I want to see what Annie is doing when she's thinking or using tools,
so that I understand her process and have transparency into her actions.

## Acceptance Criteria

1. Thinking indicator shows during `status` SSE events
2. Status message displayed (e.g., "Annie is searching the web...")
3. Tool calls mapped to user-friendly display names
4. Tool call card shows tool name and expandable parameters
5. Tool result indicated with success/failure state
6. Animated spinner/dots while tool is running
7. Tool cards appear inline in conversation flow
8. Smooth transitions between states
9. Multiple sequential tool calls displayed properly
10. Error state for failed tool calls

## Tasks / Subtasks

- [ ] Task 1: Create ThinkingIndicator component (AC: 1, 2, 6)
  - [ ] 1.1 Create `web/src/components/chat/ThinkingIndicator.tsx`
  - [ ] 1.2 Display status message from SSE
  - [ ] 1.3 Add animated spinner/dots
  - [ ] 1.4 Support different status types

- [ ] Task 2: Create ToolCallCard component (AC: 3, 4, 5, 10)
  - [ ] 2.1 Create `web/src/components/chat/ToolCallCard.tsx`
  - [ ] 2.2 Map tool names to friendly labels
  - [ ] 2.3 Show tool icon based on type
  - [ ] 2.4 Add expandable parameters section
  - [ ] 2.5 Show success/failure indicator
  - [ ] 2.6 Show error message for failures

- [ ] Task 3: Create tool display name mapping (AC: 3)
  - [ ] 3.1 Create tool name → display name map
  - [ ] 3.2 Create tool name → icon map
  - [ ] 3.3 Handle unknown tools gracefully

- [ ] Task 4: Handle tool call events (AC: 7, 9)
  - [ ] 4.1 Parse tool_call SSE events
  - [ ] 4.2 Add tool card to message thread
  - [ ] 4.3 Parse tool_result events
  - [ ] 4.4 Update tool card with result

- [ ] Task 5: Add animations (AC: 6, 8)
  - [ ] 5.1 Spinning animation for in-progress tools
  - [ ] 5.2 Fade-in for tool cards
  - [ ] 5.3 State transition animations

- [ ] Task 6: Integrate with streaming
  - [ ] 6.1 Connect to useStream hook events
  - [ ] 6.2 Update Zustand store with tool state
  - [ ] 6.3 Clear tool state on stream complete

## Dev Notes

### Tool Display Name Mapping

```typescript
const TOOL_DISPLAY_MAP: Record<string, { label: string; icon: string; color: string }> = {
  'web_search': {
    label: 'Searching the web...',
    icon: '🔍',
    color: 'blue'
  },
  'web_crawl': {
    label: 'Reading webpage...',
    icon: '📄',
    color: 'green'
  },
  'retrieve_memories': {
    label: 'Remembering...',
    icon: '🧠',
    color: 'purple'
  },
  'store_memory': {
    label: 'Saving to memory...',
    icon: '💾',
    color: 'purple'
  },
  'get_portfolio': {
    label: 'Checking portfolio...',
    icon: '📊',
    color: 'emerald'
  },
  'get_portfolio_summary': {
    label: 'Analyzing portfolio...',
    icon: '📈',
    color: 'emerald'
  },
  'home_assistant_query': {
    label: 'Checking smart home...',
    icon: '🏠',
    color: 'orange'
  },
  'home_assistant_control': {
    label: 'Controlling device...',
    icon: '🎮',
    color: 'orange'
  },
  'reddit_search': {
    label: 'Searching Reddit...',
    icon: '🔴',
    color: 'red'
  },
  'get_user_profile': {
    label: 'Loading your profile...',
    icon: '👤',
    color: 'cyan'
  },
  'update_user_profile': {
    label: 'Updating profile...',
    icon: '✏️',
    color: 'cyan'
  },
};

function getToolDisplay(toolName: string) {
  return TOOL_DISPLAY_MAP[toolName] || {
    label: 'Working on it...',
    icon: '⚙️',
    color: 'gray'
  };
}
```

### ThinkingIndicator Component

```tsx
interface ThinkingIndicatorProps {
  message: string;
}

export function ThinkingIndicator({ message }: ThinkingIndicatorProps) {
  return (
    <div className="flex items-center gap-2 text-gray-500 py-2">
      <div className="flex gap-1">
        <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce" />
        <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce delay-100" />
        <span className="w-2 h-2 bg-purple-500 rounded-full animate-bounce delay-200" />
      </div>
      <span className="text-sm">{message}</span>
    </div>
  );
}
```

### ToolCallCard Component

```tsx
interface ToolCallCardProps {
  toolName: string;
  args: Record<string, any>;
  status: 'running' | 'success' | 'error';
  result?: any;
  error?: string;
}

export function ToolCallCard({ toolName, args, status, result, error }: ToolCallCardProps) {
  const [expanded, setExpanded] = useState(false);
  const display = getToolDisplay(toolName);

  return (
    <div className={cn(
      "border rounded-lg p-3 my-2",
      `border-${display.color}-200 bg-${display.color}-50 dark:bg-${display.color}-950`
    )}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span>{display.icon}</span>
          <span className="font-medium">{display.label}</span>
          {status === 'running' && (
            <Loader2 className="w-4 h-4 animate-spin" />
          )}
          {status === 'success' && (
            <CheckCircle className="w-4 h-4 text-green-500" />
          )}
          {status === 'error' && (
            <XCircle className="w-4 h-4 text-red-500" />
          )}
        </div>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-gray-500 hover:text-gray-700"
        >
          {expanded ? <ChevronUp /> : <ChevronDown />}
        </button>
      </div>

      {expanded && (
        <div className="mt-2 text-sm">
          <div className="font-mono bg-gray-100 dark:bg-gray-800 p-2 rounded">
            <pre>{JSON.stringify(args, null, 2)}</pre>
          </div>
          {error && (
            <div className="mt-2 text-red-500">{error}</div>
          )}
        </div>
      )}
    </div>
  );
}
```

### Integration with useStream

```typescript
// In useStream hook
case 'tool_call':
  setAnnieState('tool_calling');
  addToolCall({
    id: data.id || crypto.randomUUID(),
    name: data.name,
    args: data.args,
    status: 'running',
  });
  break;

case 'tool_result':
  updateToolCall(data.tool_call_id, {
    status: data.error ? 'error' : 'success',
    result: data.result,
    error: data.error,
  });
  break;
```

### Zustand Store Updates

```typescript
interface ToolState {
  activeTools: Array<{
    id: string;
    name: string;
    args: Record<string, any>;
    status: 'running' | 'success' | 'error';
    result?: any;
    error?: string;
  }>;

  addToolCall: (tool: ToolState['activeTools'][0]) => void;
  updateToolCall: (id: string, updates: Partial<ToolState['activeTools'][0]>) => void;
  clearTools: () => void;
}
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.8]
- [Source: backend/api/routes/stream.py - tool_call events]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-3.3]

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/20-8-thinking-tool-call-display.context.xml

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
