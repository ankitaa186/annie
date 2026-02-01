# Story 20.7: SSE Streaming Integration

Status: review

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

- [x] Task 1: Create SSE stream client (AC: 1, 10)
  - [x] 1.1 Create `web/src/lib/api/streamClient.ts`
  - [x] 1.2 Implement EventSource connection
  - [x] 1.3 Add auto-reconnect with exponential backoff
  - [x] 1.4 Handle connection errors

- [x] Task 2: Create useStream hook (AC: 1, 2, 7, 8, 10, 11)
  - [x] 2.1 Create `web/src/lib/hooks/useStream.ts`
  - [x] 2.2 Manage EventSource lifecycle
  - [x] 2.3 Parse incoming SSE events
  - [x] 2.4 Update streaming message state
  - [x] 2.5 Handle done event - finalize message
  - [x] 2.6 Handle error event
  - [x] 2.7 Implement abort functionality

- [x] Task 3: Create StreamingMessage component (AC: 2, 9)
  - [x] 3.1 Create `web/src/components/chat/StreamingMessage.tsx`
  - [x] 3.2 Display streaming content with cursor
  - [x] 3.3 Show typing indicator before first token
  - [x] 3.4 Animate cursor while streaming

- [x] Task 4: Handle event types (AC: 3, 4, 5, 6)
  - [x] 4.1 Parse `message` events → append to content
  - [x] 4.2 Parse `status` events → update Annie state
  - [x] 4.3 Parse `tool_call` events → delegate to tool display
  - [x] 4.4 Parse `tool_result` events → delegate to tool display

- [x] Task 5: Implement cancel functionality (AC: 11)
  - [x] 5.1 Add cancel button to streaming UI
  - [x] 5.2 Implement disconnect for SSE
  - [x] 5.3 Finalize partial message on cancel

- [x] Task 6: Implement error handling (AC: 8, 12)
  - [x] 6.1 Show error toast for stream errors
  - [x] 6.2 Add retry button
  - [x] 6.3 Handle specific error codes

- [x] Task 7: Update Zustand store
  - [x] 7.1 Add streamingMessage state
  - [x] 7.2 Add annieState ('idle', 'thinking', 'speaking', 'tool_calling')
  - [x] 7.3 Create setStreamingMessage action
  - [x] 7.4 Create setAnnieState action

- [x] Task 8: Integrate with ChatPage
  - [x] 8.1 Connect useStream to message send flow
  - [x] 8.2 Show StreamingMessage in thread
  - [x] 8.3 Finalize message when done

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

- .bmad-ephemeral/stories/20-7-sse-streaming-integration.context.xml

### Agent Model Used

### Debug Log References

**Implementation Plan (2026-01-26):**
1. Task 1: Create SSE stream client with EventSource connection and auto-reconnect
2. Task 2: Create useStream hook for managing SSE lifecycle and event parsing
3. Task 3: Enhance StreamingMessage component (already exists in MessageThread.tsx)
4. Task 4: Handle all event types (status, token, tool_call, tool_result, done, error)
5. Task 5: Implement cancel functionality with AbortController
6. Task 6: Add error handling with retry option
7. Task 7: Update Zustand store with annieState
8. Task 8: Integrate with ChatPage and useChat hook

**Key Observations:**
- appStore.ts already has: streamingMessage, setStreamingMessage, appendToStreamingMessage, finalizeStreamingMessage, isStreaming
- chatStore.ts already has: annieState, setAnnieState, streamUrl, setStreamUrl
- MessageThread.tsx already has: StreamingMessage component and TypingIndicator
- useChat.ts needs to integrate with useStream hook after getting stream_url
- Backend SSE format: {"event": "message", "data": JSON.stringify({type, ...})}

**Decision:** Use chatStore.ts for streaming state since it has annieState. Will consolidate streaming functionality there.

### Completion Notes List

### File List
