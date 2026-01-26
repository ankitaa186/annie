# Story 20.7: SSE Streaming Integration

Status: drafted

## Story

As a user,
I want to see Annie's response stream in real-time as she generates it,
so that I get immediate feedback and can follow her thinking process.

## Acceptance Criteria

1. Connect to `/api/stream/{conversation_id}` SSE endpoint after sending message
2. Display tokens as they arrive (character-by-character streaming)
3. Handle `message` event type - text content tokens
4. Handle `status` event type - thinking/working indicator
5. Handle `tool_call` event type - tool being invoked (delegate to Story 20.8)
6. Handle `tool_result` event type - tool execution result (delegate to Story 20.8)
7. Handle `done` event type - stream complete, finalize message
8. Handle `error` event type - show error with user-friendly message
9. Typing indicator shown while waiting for first token
10. Graceful reconnection on disconnect with exponential backoff
11. Cancel button to abort ongoing stream
12. Error handling with retry option

## Tasks / Subtasks

- [ ] Task 1: Create SSE stream client (AC: 1, 10)
  - [ ] 1.1 Create `web/src/lib/api/streamClient.ts`
  - [ ] 1.2 Implement EventSource connection
  - [ ] 1.3 Add auto-reconnect with exponential backoff
  - [ ] 1.4 Handle connection errors

- [ ] Task 2: Create useStream hook (AC: 1, 2, 7, 8, 10, 11)
  - [ ] 2.1 Create `web/src/lib/hooks/useStream.ts`
  - [ ] 2.2 Manage EventSource lifecycle
  - [ ] 2.3 Parse incoming SSE events
  - [ ] 2.4 Update streaming message state
  - [ ] 2.5 Handle done event - finalize message
  - [ ] 2.6 Handle error event
  - [ ] 2.7 Implement abort functionality

- [ ] Task 3: Create StreamingMessage component (AC: 2, 9)
  - [ ] 3.1 Create `web/src/components/chat/StreamingMessage.tsx`
  - [ ] 3.2 Display streaming content with cursor
  - [ ] 3.3 Show typing indicator before first token
  - [ ] 3.4 Animate cursor while streaming

- [ ] Task 4: Handle event types (AC: 3, 4, 5, 6)
  - [ ] 4.1 Parse `message` events → append to content
  - [ ] 4.2 Parse `status` events → update Annie state
  - [ ] 4.3 Parse `tool_call` events → delegate to tool display
  - [ ] 4.4 Parse `tool_result` events → delegate to tool display

- [ ] Task 5: Implement cancel functionality (AC: 11)
  - [ ] 5.1 Add cancel button to streaming UI
  - [ ] 5.2 Implement AbortController for SSE
  - [ ] 5.3 Finalize partial message on cancel

- [ ] Task 6: Implement error handling (AC: 8, 12)
  - [ ] 6.1 Show error toast for stream errors
  - [ ] 6.2 Add retry button
  - [ ] 6.3 Handle specific error codes

- [ ] Task 7: Update Zustand store
  - [ ] 7.1 Add streamingMessage state
  - [ ] 7.2 Add annieState ('idle', 'thinking', 'speaking', 'tool_calling')
  - [ ] 7.3 Create setStreamingMessage action
  - [ ] 7.4 Create setAnnieState action

- [ ] Task 8: Integrate with ChatPage
  - [ ] 8.1 Connect useStream to message send flow
  - [ ] 8.2 Show StreamingMessage in thread
  - [ ] 8.3 Finalize message when done

## Dev Notes

### SSE Event Format (from backend)

```typescript
// Events received from /api/stream/{conversation_id}
type SSEEvent =
  | { type: 'status'; message: string }           // "🔄 Annie is thinking..."
  | { type: 'token'; content: string }            // Text chunk
  | { type: 'tool_call'; name: string; args: object }
  | { type: 'tool_result'; name: string; result: object }
  | { type: 'done'; tokens_used: { prompt: number; completion: number } }
  | { type: 'error'; message: string; code: string };
```

### useStream Hook Implementation

```typescript
export function useStream(conversationId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const { addMessage, setStreamingMessage, setAnnieState } = useAppStore();
  const streamContentRef = useRef('');

  const connect = useCallback(() => {
    if (!conversationId) return;

    const eventSource = new EventSource(`/api/stream/${conversationId}`);
    eventSourceRef.current = eventSource;
    streamContentRef.current = '';

    eventSource.onopen = () => {
      setIsConnected(true);
      setError(null);
    };

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'status':
          setAnnieState('thinking');
          break;

        case 'token':
          streamContentRef.current += data.content;
          setStreamingMessage(streamContentRef.current);
          setAnnieState('speaking');
          break;

        case 'tool_call':
          setAnnieState('tool_calling');
          // Delegate to tool display (Story 20.8)
          break;

        case 'done':
          // Finalize message
          addMessage(conversationId, {
            role: 'assistant',
            content: streamContentRef.current,
            timestamp: new Date().toISOString(),
          });
          setStreamingMessage(null);
          setAnnieState('idle');
          eventSource.close();
          break;

        case 'error':
          setError(data.message);
          setAnnieState('idle');
          eventSource.close();
          break;
      }
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      // Implement reconnection with backoff
    };

    return () => {
      eventSource.close();
    };
  }, [conversationId]);

  const cancel = useCallback(() => {
    eventSourceRef.current?.close();
    setStreamingMessage(null);
    setAnnieState('idle');
  }, []);

  return { isConnected, error, connect, cancel };
}
```

### StreamingMessage Component

```tsx
export function StreamingMessage({ content }: { content: string }) {
  return (
    <div className="flex gap-3 mb-4">
      <Avatar className="w-8 h-8" />
      <div className="max-w-[80%] bg-gray-100 dark:bg-gray-800 rounded-2xl px-4 py-2">
        <MessageContent content={content} />
        <span className="inline-block w-2 h-4 bg-purple-500 animate-pulse ml-1" />
      </div>
    </div>
  );
}
```

### Typing Indicator

```tsx
export function TypingIndicator() {
  return (
    <div className="flex gap-3 mb-4">
      <Avatar className="w-8 h-8" />
      <div className="bg-gray-100 dark:bg-gray-800 rounded-2xl px-4 py-3">
        <div className="flex gap-1">
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </div>
      </div>
    </div>
  );
}
```

### Reconnection with Backoff

```typescript
const INITIAL_BACKOFF = 1000;
const MAX_BACKOFF = 30000;

let backoff = INITIAL_BACKOFF;

const reconnect = () => {
  setTimeout(() => {
    connect();
    backoff = Math.min(backoff * 2, MAX_BACKOFF);
  }, backoff);
};

// Reset backoff on successful connection
eventSource.onopen = () => {
  backoff = INITIAL_BACKOFF;
};
```

### Zustand Store Updates

```typescript
interface StreamState {
  streamingMessage: string | null;
  annieState: 'idle' | 'thinking' | 'speaking' | 'tool_calling';
  activeTool: { name: string; args: object } | null;

  setStreamingMessage: (content: string | null) => void;
  setAnnieState: (state: StreamState['annieState']) => void;
  setActiveTool: (tool: StreamState['activeTool']) => void;
}
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.7]
- [Source: backend/api/routes/stream.py - SSE event format]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-3.3]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
