# Story 20.5: Chat Interface - Message Display

Status: review

## Story

As a user,
I want to see my conversation with Annie in a beautifully formatted message thread,
so that I can read our exchanges with proper styling, markdown rendering, and file attachments.

## Acceptance Criteria

1. Message thread with auto-scroll to bottom on new messages
2. User messages right-aligned with distinct styling
3. Annie messages left-aligned with avatar placeholder
4. Markdown rendering in messages (headers, bold, italic, code, lists, links, tables)
5. Code blocks with syntax highlighting
6. Links open in new tab
7. File attachments displayed appropriately (images inline, documents as cards)
8. Timestamp shown on message hover
9. Copy message button on hover
10. Smooth scroll behavior
11. Virtualized list for performance with 100+ messages
12. Loading state when fetching conversation history

## Tasks / Subtasks

- [x] Task 1: Create MessageThread component (AC: 1, 10, 11, 12)
  - [x] 1.1 Create `web/src/components/chat/MessageThread.tsx`
  - [x] 1.2 Implement auto-scroll to bottom
  - [x] 1.3 Add smooth scroll behavior
  - [x] 1.4 Implement virtual scrolling for performance
  - [x] 1.5 Add loading skeleton for history fetch

- [x] Task 2: Create UserMessage component (AC: 2)
  - [x] 2.1 Create `web/src/components/chat/UserMessage.tsx`
  - [x] 2.2 Right-align with user-specific styling
  - [x] 2.3 Apply distinct background color

- [x] Task 3: Create AnnieMessage component (AC: 3)
  - [x] 3.1 Create `web/src/components/chat/AnnieMessage.tsx`
  - [x] 3.2 Left-align with Annie styling
  - [x] 3.3 Add avatar placeholder (for Story 20.11)

- [x] Task 4: Create MessageContent component (AC: 4, 5, 6)
  - [x] 4.1 Create `web/src/components/chat/MessageContent.tsx`
  - [x] 4.2 Integrate react-markdown for rendering
  - [x] 4.3 Configure code block syntax highlighting
  - [x] 4.4 Configure links to open in new tab
  - [x] 4.5 Style tables with borders
  - [x] 4.6 Style lists properly

- [x] Task 5: Create FileAttachment component (AC: 7)
  - [x] 5.1 Create `web/src/components/chat/FileAttachment.tsx`
  - [x] 5.2 Display images inline with click-to-expand
  - [x] 5.3 Display documents as file cards
  - [x] 5.4 Show filename, size, type icon

- [x] Task 6: Add message interactions (AC: 8, 9)
  - [x] 6.1 Show timestamp on hover
  - [x] 6.2 Add copy button on hover
  - [x] 6.3 Implement copy to clipboard
  - [x] 6.4 Show brief "Copied!" feedback

- [x] Task 7: Integrate with ChatPage
  - [x] 7.1 Replace MainContent placeholder with MessageThread
  - [x] 7.2 Connect to messages from Zustand store
  - [x] 7.3 Load history for active conversation

## Dev Notes

### Message Structure

```typescript
interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  files?: FileAttachment[];
}

interface FileAttachment {
  filename: string;
  mime_type: string;
  size_bytes: number;
  url?: string; // For images that can be displayed
}
```

### Component Layout

```
MessageThread
├── LoadingSkeleton (when loading)
├── Message[] (virtualized)
│   ├── UserMessage
│   │   └── MessageContent
│   └── AnnieMessage
│       ├── Avatar (placeholder)
│       └── MessageContent
│           └── FileAttachment[]
└── ScrollAnchor (for auto-scroll)
```

### Markdown Configuration

```typescript
// Using react-markdown with plugins
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';

<ReactMarkdown
  remarkPlugins={[remarkGfm]}
  components={{
    code({ node, inline, className, children, ...props }) {
      const match = /language-(\w+)/.exec(className || '');
      return !inline && match ? (
        <SyntaxHighlighter
          style={oneDark}
          language={match[1]}
          PreTag="div"
          {...props}
        >
          {String(children).replace(/\n$/, '')}
        </SyntaxHighlighter>
      ) : (
        <code className={className} {...props}>
          {children}
        </code>
      );
    },
    a({ href, children }) {
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    },
  }}
>
  {content}
</ReactMarkdown>
```

### Virtual Scrolling

```typescript
// Using @tanstack/react-virtual for performance
import { useVirtualizer } from '@tanstack/react-virtual';

const virtualizer = useVirtualizer({
  count: messages.length,
  getScrollElement: () => scrollRef.current,
  estimateSize: () => 100, // Estimated message height
  overscan: 5,
});
```

### Styling

```typescript
// User message
<div className="flex justify-end mb-4">
  <div className="max-w-[80%] bg-blue-100 dark:bg-blue-900 rounded-2xl rounded-br-sm px-4 py-2">
    <MessageContent content={message.content} />
  </div>
</div>

// Annie message
<div className="flex gap-3 mb-4">
  <Avatar className="w-8 h-8" />
  <div className="max-w-[80%] bg-gray-100 dark:bg-gray-800 rounded-2xl rounded-bl-sm px-4 py-2">
    <MessageContent content={message.content} />
  </div>
</div>
```

### Auto-scroll Logic

```typescript
const scrollToBottom = useCallback(() => {
  messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
}, []);

// Scroll on new message
useEffect(() => {
  if (messages.length > prevLength) {
    scrollToBottom();
  }
}, [messages.length]);
```

### Dependencies

- `react-markdown` - Markdown rendering
- `remark-gfm` - GitHub Flavored Markdown
- `react-syntax-highlighter` - Code syntax highlighting
- `@tanstack/react-virtual` - Virtual scrolling

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.5]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md]

## Dev Agent Record

### Context Reference
- .bmad-ephemeral/stories/20-5-chat-interface-message-display.context.xml

### Agent Model Used
Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References
Implementation plan:
1. Added dependencies to package.json (react-markdown, remark-gfm, react-syntax-highlighter, @tanstack/react-virtual)
2. Created types for Message and FileAttachment in web/src/types/index.ts
3. Updated Zustand store with message state (messages, streamingMessage, isLoadingHistory, isStreaming)
4. Created MessageContent component with markdown rendering and syntax highlighting
5. Created FileAttachment component with image preview and document cards
6. Created UserMessage component with right-alignment and hover interactions
7. Created AnnieMessage component with avatar placeholder and left-alignment
8. Created MessageThread component with virtual scrolling and auto-scroll
9. Updated ChatPage to integrate MessageThread and connect to store
10. Added CSS utilities for prose styling and smooth scroll

### Completion Notes List
- Implemented all 7 tasks covering 12 acceptance criteria
- MessageThread uses @tanstack/react-virtual for performance with 100+ messages
- Auto-scroll only triggers when user is near bottom (within 150px)
- Streaming message shown with blinking cursor indicator
- Empty state shown when no messages in conversation
- Loading skeleton shown during history fetch
- Copy functionality with 2-second "Copied!" feedback
- All links open in new tab with rel="noopener noreferrer" for security
- Full markdown support: headers, bold, italic, code, lists, tables, blockquotes
- Syntax highlighting uses oneDark theme from react-syntax-highlighter
- Avatar uses Bot icon as placeholder for Story 20.11
- Dark mode fully supported via Tailwind CSS classes
- WCAG 2.1 AA accessibility with ARIA labels and keyboard navigation

### File List
- web/package.json (modified - added dependencies)
- web/src/types/index.ts (created - Message, FileAttachment, Conversation types)
- web/src/lib/stores/appStore.ts (modified - added message state and actions)
- web/src/components/chat/MessageContent.tsx (created)
- web/src/components/chat/FileAttachment.tsx (created)
- web/src/components/chat/UserMessage.tsx (created)
- web/src/components/chat/AnnieMessage.tsx (created)
- web/src/components/chat/MessageThread.tsx (created)
- web/src/components/chat/index.ts (created)
- web/src/pages/ChatPage.tsx (modified - integrated MessageThread)
- web/src/index.css (modified - added prose styling)

### Change Log
- 2026-01-26: Story 20-5 implementation complete - all acceptance criteria met
