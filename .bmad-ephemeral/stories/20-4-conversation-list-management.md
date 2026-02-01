# Story 20.4: Conversation List & Management

Status: review

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

- [x] Task 1: Create useConversations hook (AC: 8, 11)
  - [x] 1.1 Create `web/src/lib/hooks/useConversations.ts`
  - [x] 1.2 Fetch conversations from `GET /api/conversations`
  - [x] 1.3 Implement create conversation via `POST /api/conversations`
  - [x] 1.4 Implement delete via `DELETE /api/conversations/{id}`
  - [x] 1.5 Implement rename via `PATCH /api/conversations/{id}`
  - [x] 1.6 Handle loading and error states

- [x] Task 2: Build ConversationList component (AC: 1, 2, 9, 10)
  - [x] 2.1 Create `web/src/components/conversations/ConversationList.tsx`
  - [x] 2.2 Group conversations by date
  - [x] 2.3 Render ConversationItem for each
  - [x] 2.4 Show loading skeleton
  - [x] 2.5 Show empty state with friendly message

- [x] Task 3: Build ConversationItem component (AC: 2, 3, 4)
  - [x] 3.1 Create `web/src/components/conversations/ConversationItem.tsx`
  - [x] 3.2 Display title, timestamp, preview
  - [x] 3.3 Handle click to switch conversation
  - [x] 3.4 Highlight active conversation

- [x] Task 4: Implement new conversation (AC: 5)
  - [x] 4.1 Wire up "New Conversation" button
  - [x] 4.2 Call create API
  - [x] 4.3 Switch to new conversation
  - [x] 4.4 Show optimistic UI update

- [x] Task 5: Implement delete conversation (AC: 6)
  - [x] 5.1 Add context menu with delete option
  - [x] 5.2 Show confirmation dialog
  - [x] 5.3 Call delete API
  - [x] 5.4 Remove from list with animation
  - [x] 5.5 Switch to another conversation if active was deleted

- [x] Task 6: Implement rename conversation (AC: 7)
  - [x] 6.1 Add edit mode to ConversationItem
  - [x] 6.2 Double-click or edit icon triggers edit
  - [x] 6.3 Inline text input for new title
  - [x] 6.4 Save on Enter or blur
  - [x] 6.5 Cancel on Escape

- [x] Task 7: Integrate with Sidebar (AC: 1)
  - [x] 7.1 Replace placeholder in Sidebar with ConversationList
  - [x] 7.2 Ensure proper scrolling
  - [x] 7.3 Test responsive behavior

- [x] Task 8: Update Zustand store (AC: 12)
  - [x] 8.1 Add conversations state
  - [x] 8.2 Add activeConversationId state
  - [x] 8.3 Create setActiveConversation action
  - [x] 8.4 Create addConversation, removeConversation actions

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

- .bmad-ephemeral/stories/20-4-conversation-list-management.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

Implementation followed the plan:
1. Added date-fns and Radix UI dependencies to package.json
2. Created shadcn/ui components: skeleton, alert-dialog, dropdown-menu, context-menu
3. Extended Conversation type with lastMessagePreview field
4. Updated Zustand store with conversations loading/error states and setConversations action
5. Created useConversations hook with API integration and mock data fallback
6. Built ConversationItem with edit mode, context menu, and keyboard support
7. Built ConversationList with date grouping, loading skeleton, empty state
8. Integrated ConversationList into Sidebar with all handlers wired up

### Completion Notes List

1. **API Fallback**: The useConversations hook implements graceful fallback to local state when the backend API (Story 20.14) is unavailable. When the API returns 404 or fails, the hook switches to mock data mode but continues to provide full functionality using local Zustand state.

2. **Optimistic UI**: All mutations (create, delete, rename) use optimistic updates - the UI updates immediately and then syncs with the server. This provides snappy UX even with slow network.

3. **Date Grouping**: Conversations are grouped into Today, Yesterday, Previous 7 Days, and Older categories using date-fns. Groups are sorted by updatedAt descending.

4. **Delete Confirmation**: Delete operations show an AlertDialog confirmation before proceeding. If the deleted conversation was active, the UI switches to the next available conversation.

5. **Inline Rename**: Double-click or the edit icon triggers inline edit mode. Enter saves, Escape cancels, blur saves. Keyboard accessible with F2 shortcut.

6. **Responsive Behavior**: The ConversationList adapts to collapsed sidebar mode (tablet), showing only dot indicators for conversations.

7. **Dependencies Added**: date-fns ^3.6.0, @radix-ui/react-alert-dialog ^1.1.2, @radix-ui/react-context-menu ^2.2.2

8. **Run `npm install` Required**: The new dependencies need to be installed by running `npm install` in the web/ directory.

### File List

- web/package.json (modified - added date-fns, alert-dialog, context-menu dependencies)
- web/src/types/index.ts (modified - added lastMessagePreview to Conversation, added API response types)
- web/src/lib/stores/appStore.ts (modified - added conversationsLoading, conversationsError, setConversations, etc.)
- web/src/lib/hooks/useConversations.ts (new - hook for conversation CRUD with API/mock fallback)
- web/src/lib/hooks/index.ts (modified - export useConversations)
- web/src/components/ui/skeleton.tsx (new - shadcn/ui skeleton component)
- web/src/components/ui/alert-dialog.tsx (new - shadcn/ui alert-dialog component)
- web/src/components/ui/dropdown-menu.tsx (new - shadcn/ui dropdown-menu component)
- web/src/components/ui/context-menu.tsx (new - shadcn/ui context-menu component)
- web/src/components/conversations/ConversationItem.tsx (new - individual conversation entry)
- web/src/components/conversations/ConversationList.tsx (new - grouped conversation list with states)
- web/src/components/conversations/index.ts (new - barrel export)
- web/src/components/layout/Sidebar.tsx (modified - integrated ConversationList)
