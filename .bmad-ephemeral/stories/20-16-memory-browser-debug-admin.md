# Story 20.16: Memory Browser (Debug/Admin)

Status: drafted

## Story

As an admin/developer,
I want to browse and manage Annie's memories about me,
so that I can debug memory-related issues and have control over what Annie remembers.

## Acceptance Criteria

1. Memory browser accessible from sidebar (admin mode)
2. List all memories by category/topic
3. Search memories by keyword
4. View memory details (content, source, timestamp)
5. Delete specific memories
6. "Forget this" functionality from memory detail
7. Pagination for large memory sets
8. Hidden behind admin flag or debug mode
9. Confirmation before destructive actions
10. Visual indication of memory recency

## Tasks / Subtasks

- [ ] Task 1: Create memory API client
  - [ ] 1.1 Create `web/src/lib/api/memoryClient.ts`
  - [ ] 1.2 Implement list memories endpoint
  - [ ] 1.3 Implement search memories
  - [ ] 1.4 Implement delete memory

- [ ] Task 2: Create MemoryBrowser page
  - [ ] 2.1 Create `web/src/pages/MemoryBrowserPage.tsx`
  - [ ] 2.2 Layout with search and list
  - [ ] 2.3 Memory detail panel/modal

- [ ] Task 3: Create MemoryList component
  - [ ] 3.1 Create `web/src/components/memory/MemoryList.tsx`
  - [ ] 3.2 Group by category
  - [ ] 3.3 Show timestamp and preview
  - [ ] 3.4 Pagination controls

- [ ] Task 4: Create MemoryDetail component
  - [ ] 4.1 Create `web/src/components/memory/MemoryDetail.tsx`
  - [ ] 4.2 Show full content
  - [ ] 4.3 Show source/timestamp
  - [ ] 4.4 Delete button with confirmation

- [ ] Task 5: Implement search
  - [ ] 5.1 Search input with debounce
  - [ ] 5.2 Call search API
  - [ ] 5.3 Display results

- [ ] Task 6: Add admin mode guard
  - [ ] 6.1 Check admin flag
  - [ ] 6.2 Hide from regular users
  - [ ] 6.3 Show "V2" badge in sidebar

- [ ] Task 7: Backend API (if not exists)
  - [ ] 7.1 GET /api/memories - List memories
  - [ ] 7.2 GET /api/memories/search - Search
  - [ ] 7.3 DELETE /api/memories/{id} - Delete

## Dev Notes

### Purpose

This is a **debug/admin tool**, not a primary user feature. It helps:
- Developers debug memory retrieval issues
- Admin (Ankit) manage what Annie remembers
- Understand how memories are categorized

### Memory API (agentic-memories)

```typescript
// API calls to agentic-memories service
const listMemories = async (userId: string, page: number = 1) => {
  const response = await fetch(
    `${MEMORIES_URL}/v1/memories/${userId}?page=${page}&limit=20`
  );
  return response.json();
};

const searchMemories = async (userId: string, query: string) => {
  const response = await fetch(
    `${MEMORIES_URL}/v1/memories/${userId}/search?q=${encodeURIComponent(query)}`
  );
  return response.json();
};

const deleteMemory = async (userId: string, memoryId: string) => {
  await fetch(`${MEMORIES_URL}/v1/memories/${userId}/${memoryId}`, {
    method: 'DELETE',
  });
};
```

### UI Layout

```
┌─────────────────────────────────────────────────┐
│ Memory Browser                          [Search]│
├─────────────────────────────────────────────────┤
│ ┌─────────────────┐  ┌────────────────────────┐ │
│ │ Categories      │  │ Memory Detail          │ │
│ │ ├─ Decisions    │  │                        │ │
│ │ ├─ Preferences  │  │ Content:               │ │
│ │ ├─ Facts        │  │ User prefers morning   │ │
│ │ └─ Topics       │  │ meetings before 9am... │ │
│ │                 │  │                        │ │
│ │ Recent Memories │  │ Source: conversation   │ │
│ │ ├─ Jan 25       │  │ Created: Jan 25, 2026  │ │
│ │ ├─ Jan 24       │  │                        │ │
│ │ └─ Jan 23       │  │ [Delete Memory]        │ │
│ └─────────────────┘  └────────────────────────┘ │
├─────────────────────────────────────────────────┤
│                    [1] [2] [3] ... [10]         │
└─────────────────────────────────────────────────┘
```

### Admin Mode Check

```typescript
// Check if admin mode enabled
const isAdminMode = () => {
  // Option 1: URL parameter
  if (new URLSearchParams(window.location.search).has('admin')) {
    return true;
  }

  // Option 2: Local storage flag
  if (localStorage.getItem('annie-admin-mode') === 'true') {
    return true;
  }

  // Option 3: Specific user
  const userId = useAppStore.getState().userId;
  return userId === 'YOUR_USER_ID'; // Ankit's ID
};
```

### Confirmation Dialog

```tsx
<AlertDialog>
  <AlertDialogTrigger asChild>
    <Button variant="destructive">Delete Memory</Button>
  </AlertDialogTrigger>
  <AlertDialogContent>
    <AlertDialogHeader>
      <AlertDialogTitle>Delete this memory?</AlertDialogTitle>
      <AlertDialogDescription>
        Annie will forget this information. This cannot be undone.
      </AlertDialogDescription>
    </AlertDialogHeader>
    <AlertDialogFooter>
      <AlertDialogCancel>Cancel</AlertDialogCancel>
      <AlertDialogAction onClick={handleDelete}>
        Delete
      </AlertDialogAction>
    </AlertDialogFooter>
  </AlertDialogContent>
</AlertDialog>
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.16]
- [Source: docs/brainstorming-web-ui-2026-01-25.md#Memory-Browser]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
