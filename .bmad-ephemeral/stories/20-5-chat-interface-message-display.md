# Story 20.5: Chat Interface - Message Display

Status: ready-for-dev

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

- [ ] Task 1: Create MessageThread component (AC: 1, 10, 11, 12)
  - [ ] 1.1 Create `web/src/components/chat/MessageThread.tsx`
  - [ ] 1.2 Implement auto-scroll to bottom
  - [ ] 1.3 Add smooth scroll behavior
  - [ ] 1.4 Implement virtual scrolling for performance
  - [ ] 1.5 Add loading skeleton for history fetch

- [ ] Task 2: Create UserMessage component (AC: 2)
  - [ ] 2.1 Create `web/src/components/chat/UserMessage.tsx`
  - [ ] 2.2 Right-align with user-specific styling
  - [ ] 2.3 Apply distinct background color

- [ ] Task 3: Create AnnieMessage component (AC: 3)
  - [ ] 3.1 Create `web/src/components/chat/AnnieMessage.tsx`
  - [ ] 3.2 Left-align with Annie styling
  - [ ] 3.3 Add avatar placeholder (for Story 20.11)

- [ ] Task 4: Create MessageContent component (AC: 4, 5, 6)
  - [ ] 4.1 Create `web/src/components/chat/MessageContent.tsx`
  - [ ] 4.2 Integrate react-markdown for rendering
  - [ ] 4.3 Configure code block syntax highlighting
  - [ ] 4.4 Configure links to open in new tab
  - [ ] 4.5 Style tables with borders
  - [ ] 4.6 Style lists properly

- [ ] Task 5: Create FileAttachment component (AC: 7)
  - [ ] 5.1 Create `web/src/components/chat/FileAttachment.tsx`
  - [ ] 5.2 Display images inline with click-to-expand
  - [ ] 5.3 Display documents as file cards
  - [ ] 5.4 Show filename, size, type icon

- [ ] Task 6: Add message interactions (AC: 8, 9)
  - [ ] 6.1 Show timestamp on hover
  - [ ] 6.2 Add copy button on hover
  - [ ] 6.3 Implement copy to clipboard
  - [ ] 6.4 Show brief "Copied!" feedback

- [ ] Task 7: Integrate with ChatPage
  - [ ] 7.1 Replace MainContent placeholder with MessageThread
  - [ ] 7.2 Connect to messages from Zustand store
  - [ ] 7.3 Load history for active conversation

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

### Debug Log References

### Completion Notes List

### File List
