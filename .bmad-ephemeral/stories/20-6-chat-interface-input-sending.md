# Story 20.6: Chat Interface - Input & Sending

Status: review

## Story

As a user,
I want to type messages and upload files in a comfortable input area,
so that I can communicate with Annie through text and share documents/images for analysis.

## Acceptance Criteria

1. Auto-expanding textarea that grows with content (max 6 lines, then scroll)
2. Send button enabled only when input is not empty
3. Send on Enter key, Shift+Enter for newline
4. File upload button with click and drag-and-drop support
5. File preview shown before sending
6. Multiple file support (up to 10 files per message)
7. File type validation (images, PDFs, docs, spreadsheets)
8. File size validation with user-friendly error messages
9. Loading/sending state with disabled input
10. Input disabled while Annie is responding
11. Character count indicator for long messages (optional)
12. Paste image from clipboard support

## Tasks / Subtasks

- [x] Task 1: Create InputArea component (AC: 1, 2, 3, 9, 10)
  - [x] 1.1 Create `web/src/components/chat/InputArea.tsx`
  - [x] 1.2 Implement auto-expanding textarea
  - [x] 1.3 Add send button with enabled/disabled state
  - [x] 1.4 Handle Enter/Shift+Enter key events
  - [x] 1.5 Show loading state during send
  - [x] 1.6 Disable input while Annie responds

- [x] Task 2: Create FileUpload component (AC: 4, 5, 6)
  - [x] 2.1 Create `web/src/components/chat/FileUpload.tsx` (integrated into InputArea)
  - [x] 2.2 Add file input with hidden trigger
  - [x] 2.3 Implement drag-and-drop zone
  - [x] 2.4 Show file previews (thumbnails for images)
  - [x] 2.5 Allow removing files before send
  - [x] 2.6 Limit to 10 files max

- [x] Task 3: Implement file validation (AC: 7, 8)
  - [x] 3.1 Create file validation utilities
  - [x] 3.2 Validate MIME types against allowed list
  - [x] 3.3 Validate file sizes (10MB images, 20MB documents)
  - [x] 3.4 Show user-friendly error toasts

- [x] Task 4: Create useChat hook (AC: 9)
  - [x] 4.1 Create `web/src/lib/hooks/useChat.ts`
  - [x] 4.2 Implement sendMessage function
  - [x] 4.3 Handle POST to /api/chat with files
  - [x] 4.4 Update Zustand store with sent message
  - [x] 4.5 Trigger SSE stream connection (placeholder for Story 20.7)

- [x] Task 5: Implement clipboard paste (AC: 12)
  - [x] 5.1 Listen for paste events
  - [x] 5.2 Extract images from clipboard
  - [x] 5.3 Add to file list for upload

- [x] Task 6: Add character count (AC: 11)
  - [x] 6.1 Display character count for messages >500 chars
  - [x] 6.2 Show warning at 4000 chars
  - [x] 6.3 Prevent send at 8000 chars (optional limit)

- [x] Task 7: Integrate with ChatPage
  - [x] 7.1 Add InputArea below MessageThread
  - [x] 7.2 Connect to useChat hook
  - [x] 7.3 Wire up to Zustand store

## Dev Notes

### InputArea Layout

```
┌─────────────────────────────────────────────────────────────┐
│ [File previews row - if files attached]                      │
├─────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Type a message...                              [📎] [➤] │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Auto-expanding Textarea

```typescript
const textareaRef = useRef<HTMLTextAreaElement>(null);

const adjustHeight = () => {
  const textarea = textareaRef.current;
  if (textarea) {
    textarea.style.height = 'auto';
    const maxHeight = 6 * 24; // 6 lines * line height
    textarea.style.height = Math.min(textarea.scrollHeight, maxHeight) + 'px';
  }
};

useEffect(() => {
  adjustHeight();
}, [message]);
```

### File Validation

```typescript
const ALLOWED_MIME_TYPES = {
  // Images
  'image/jpeg': { maxSize: 10 * 1024 * 1024, label: 'JPEG' },
  'image/png': { maxSize: 10 * 1024 * 1024, label: 'PNG' },
  'image/gif': { maxSize: 10 * 1024 * 1024, label: 'GIF' },
  'image/webp': { maxSize: 10 * 1024 * 1024, label: 'WebP' },
  // Documents
  'application/pdf': { maxSize: 20 * 1024 * 1024, label: 'PDF' },
  'text/plain': { maxSize: 20 * 1024 * 1024, label: 'Text' },
  // Spreadsheets
  'text/csv': { maxSize: 20 * 1024 * 1024, label: 'CSV' },
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
    { maxSize: 20 * 1024 * 1024, label: 'Excel' },
  // Word
  'application/vnd.openxmlformats-officedocument.wordprocessingml.document':
    { maxSize: 20 * 1024 * 1024, label: 'Word' },
};

function validateFile(file: File): string | null {
  const config = ALLOWED_MIME_TYPES[file.type];
  if (!config) {
    return `File type not supported: ${file.type}`;
  }
  if (file.size > config.maxSize) {
    return `File too large: ${formatBytes(file.size)} (max ${formatBytes(config.maxSize)})`;
  }
  return null;
}
```

### Drag and Drop

```typescript
const [isDragging, setIsDragging] = useState(false);

const handleDragOver = (e: DragEvent) => {
  e.preventDefault();
  setIsDragging(true);
};

const handleDragLeave = () => {
  setIsDragging(false);
};

const handleDrop = (e: DragEvent) => {
  e.preventDefault();
  setIsDragging(false);
  const files = Array.from(e.dataTransfer.files);
  addFiles(files);
};
```

### Send Message Flow

```typescript
const sendMessage = async () => {
  if (!message.trim() && files.length === 0) return;

  setIsSending(true);

  // Optimistically add user message to thread
  const userMessage = {
    id: crypto.randomUUID(),
    role: 'user',
    content: message,
    files: files.map(f => ({ filename: f.name, mime_type: f.type })),
    timestamp: new Date().toISOString(),
  };
  addMessage(activeConversationId, userMessage);

  // Prepare form data
  const formData = new FormData();
  formData.append('message', message);
  formData.append('user_id', userId);
  formData.append('platform', 'web');
  files.forEach(f => formData.append('files', f));

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      body: formData,
    });
    const { conversation_id, stream_url } = await response.json();

    // Start SSE stream (Story 20.7)
    connectToStream(stream_url);
  } catch (error) {
    // Handle error
  }

  setMessage('');
  setFiles([]);
  setIsSending(false);
};
```

### File Preview Component

```tsx
<div className="flex gap-2 flex-wrap p-2 border-t">
  {files.map((file, index) => (
    <div key={index} className="relative group">
      {file.type.startsWith('image/') ? (
        <img
          src={URL.createObjectURL(file)}
          className="w-16 h-16 object-cover rounded"
        />
      ) : (
        <div className="w-16 h-16 flex items-center justify-center bg-gray-100 rounded">
          <FileIcon className="w-8 h-8" />
        </div>
      )}
      <button
        onClick={() => removeFile(index)}
        className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full p-1"
      >
        <X className="w-3 h-3" />
      </button>
    </div>
  ))}
</div>
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.6]
- [Source: docs/epics/epic-18-file-context-sharing.md#Supported-Formats]
- [Source: backend/api/models/file_attachment.py]

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/20-6-chat-interface-input-sending.context.xml

### Agent Model Used

Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

Implementation plan:
1. Task 1-2: InputArea component with integrated file upload (no separate FileUpload component - cleaner architecture)
2. Task 3: File validation utilities mirroring backend rules
3. Task 4: useChat hook using appStore for state management
4. Task 5: Clipboard paste integrated into InputArea
5. Task 6: Character count integrated into InputArea
6. Task 7: ChatPage integration connecting all pieces

Key decisions:
- Integrated file upload into InputArea rather than separate component (simpler, better UX)
- Created useToast hook + ToastContainer for error notifications
- Updated useChat to use appStore instead of separate chatStore (consistency)
- SSE streaming placeholder - actual implementation in Story 20.7

### Completion Notes List

- All 7 tasks completed successfully
- InputArea provides full-featured message input with file upload
- File validation mirrors backend rules (10MB images, 20MB docs, max 10 files)
- Toast notifications for validation errors
- Character count appears at 500+ chars, warning at 4000, blocks at 8000
- Clipboard paste supports images (Ctrl/Cmd+V)
- Drag-and-drop zone with visual feedback
- useChat hook ready for SSE integration in Story 20.7

### File List

**New Files:**
- web/src/lib/utils/fileValidation.ts - File validation utilities (MIME types, size limits, base64 conversion)
- web/src/lib/hooks/useToast.ts - Toast notification hook and Zustand store
- web/src/components/ui/toast.tsx - ToastContainer component for rendering notifications
- web/src/components/chat/FilePreview.tsx - File preview with thumbnails and remove buttons
- web/src/components/chat/InputArea.tsx - Main chat input component with all features

**Modified Files:**
- web/src/lib/hooks/useChat.ts - Updated to use appStore, added file attachment handling
- web/src/lib/hooks/index.ts - Export useChat, useToast hooks
- web/src/pages/ChatPage.tsx - Integrated InputArea component
- web/src/App.tsx - Added ToastContainer

**Deleted Files:**
- web/src/lib/stores/chatStore.ts - Removed duplicate store (using appStore instead)

### Change Log

- 2026-01-26: Story 20.6 implementation complete - Chat input with file upload, validation, and sending
