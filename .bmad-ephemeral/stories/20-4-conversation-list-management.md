# Story 20.4: Conversation List & Management

Status: drafted

## Story

As a user,
I want to see my conversation history in a sidebar and manage conversations,
so that I can easily switch between, create, rename, and delete conversations.

## Acceptance Criteria

1. Conversations listed in sidebar, grouped by date (Today, Yesterday, Previous 7 Days, Older)
2. Each conversation item shows title, last message timestamp, and truncated preview
3. Click on conversation switches to that conversation
4. Active conversation visually highlighted
5. "New Conversation" button creates empty chat
6. Delete conversation available via context menu or swipe (with confirmation)
7. Rename conversation via inline edit (double-click or edit icon)
8. Conversations fetched from backend API on load
9. Loading skeleton shown while fetching
10. Empty state for new users with no conversations
11. Conversations persist across sessions (backed by Redis)
12. Real-time update when new message sent (optimistic UI)

## Tasks / Subtasks

- [ ] Task 1: Create useConversations hook (AC: 8, 11)
  - [ ] 1.1 Create `web/src/lib/hooks/useConversations.ts`
  - [ ] 1.2 Fetch conversations from `GET /api/conversations`
  - [ ] 1.3 Implement create conversation via `POST /api/conversations`
  - [ ] 1.4 Implement delete via `DELETE /api/conversations/{id}`
  - [ ] 1.5 Implement rename via `PATCH /api/conversations/{id}`
  - [ ] 1.6 Handle loading and error states

- [ ] Task 2: Build ConversationList component (AC: 1, 2, 9, 10)
  - [ ] 2.1 Create `web/src/components/conversations/ConversationList.tsx`
  - [ ] 2.2 Group conversations by date
  - [ ] 2.3 Render ConversationItem for each
  - [ ] 2.4 Show loading skeleton
  - [ ] 2.5 Show empty state with friendly message

- [ ] Task 3: Build ConversationItem component (AC: 2, 3, 4)
  - [ ] 3.1 Create `web/src/components/conversations/ConversationItem.tsx`
  - [ ] 3.2 Display title, timestamp, preview
  - [ ] 3.3 Handle click to switch conversation
  - [ ] 3.4 Highlight active conversation

- [ ] Task 4: Implement new conversation (AC: 5)
  - [ ] 4.1 Wire up "New Conversation" button
  - [ ] 4.2 Call create API
  - [ ] 4.3 Switch to new conversation
  - [ ] 4.4 Show optimistic UI update

- [ ] Task 5: Implement delete conversation (AC: 6)
  - [ ] 5.1 Add context menu with delete option
  - [ ] 5.2 Show confirmation dialog
  - [ ] 5.3 Call delete API
  - [ ] 5.4 Remove from list with animation
  - [ ] 5.5 Switch to another conversation if active was deleted

- [ ] Task 6: Implement rename conversation (AC: 7)
  - [ ] 6.1 Add edit mode to ConversationItem
  - [ ] 6.2 Double-click or edit icon triggers edit
  - [ ] 6.3 Inline text input for new title
  - [ ] 6.4 Save on Enter or blur
  - [ ] 6.5 Cancel on Escape

- [ ] Task 7: Integrate with Sidebar (AC: 1)
  - [ ] 7.1 Replace placeholder in Sidebar with ConversationList
  - [ ] 7.2 Ensure proper scrolling
  - [ ] 7.3 Test responsive behavior

- [ ] Task 8: Update Zustand store (AC: 12)
  - [ ] 8.1 Add conversations state
  - [ ] 8.2 Add activeConversationId state
  - [ ] 8.3 Create setActiveConversation action
  - [ ] 8.4 Create addConversation, removeConversation actions

## Dev Notes

### Date Grouping Logic

```typescript
function groupByDate(conversations: Conversation[]) {
  const now = new Date();
  const today = startOfDay(now);
  const yesterday = subDays(today, 1);
  const weekAgo = subDays(today, 7);

  return {
    today: conversations.filter(c => new Date(c.updated_at) >= today),
    yesterday: conversations.filter(c => {
      const date = new Date(c.updated_at);
      return date >= yesterday && date < today;
    }),
    previousWeek: conversations.filter(c => {
      const date = new Date(c.updated_at);
      return date >= weekAgo && date < yesterday;
    }),
    older: conversations.filter(c => new Date(c.updated_at) < weekAgo),
  };
}
```

### API Integration

```typescript
// useConversations.ts
const fetchConversations = async () => {
  const response = await fetch('/api/conversations');
  return response.json();
};

const createConversation = async () => {
  const response = await fetch('/api/conversations', { method: 'POST' });
  return response.json();
};

const deleteConversation = async (id: string) => {
  await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
};

const renameConversation = async (id: string, title: string) => {
  const response = await fetch(`/api/conversations/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  return response.json();
};
```

### Component Structure

```
Sidebar
└── ConversationList
    ├── NewConversationButton
    ├── ConversationGroup (Today)
    │   └── ConversationItem[]
    ├── ConversationGroup (Yesterday)
    │   └── ConversationItem[]
    └── ConversationGroup (Older)
        └── ConversationItem[]
```

### ConversationItem Design

```tsx
<div className={cn(
  "p-3 rounded-lg cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800",
  isActive && "bg-gray-100 dark:bg-gray-800"
)}>
  <div className="flex justify-between items-start">
    <span className="font-medium truncate">{title}</span>
    <span className="text-xs text-gray-500">{formatTime(updated_at)}</span>
  </div>
  <p className="text-sm text-gray-500 truncate mt-1">{preview}</p>
</div>
```

### Empty State

```tsx
<div className="flex flex-col items-center justify-center h-40 text-gray-500">
  <MessageSquare className="w-12 h-12 mb-2" />
  <p>No conversations yet</p>
  <p className="text-sm">Start chatting with Annie!</p>
</div>
```

### Dependencies

- **Depends on Story 20.14**: Backend API must provide `/api/conversations` endpoints
- **Integrates with Story 20.2**: Replaces placeholder in Sidebar component

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.4]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-2.2.2]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
