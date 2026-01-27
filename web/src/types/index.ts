/**
 * Frontend type definitions for Annie Web UI
 */

/**
 * File attachment for display in messages
 * Matches backend FileAttachment model structure
 */
export interface FileAttachment {
  filename: string;
  mime_type: string;
  size_bytes: number;
  /** URL for displayable content (images) - may be data URL or object URL */
  url?: string;
  /** Base64-encoded data (only present during upload, not for display) */
  data_base64?: string;
}

/**
 * File category derived from MIME type
 */
export type FileCategory = 'image' | 'document' | 'spreadsheet';

/**
 * Chat message structure
 */
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  files?: FileAttachment[];
}

/**
 * Conversation metadata
 * Matches the backend API contract from Story 20.14.
 */
export interface Conversation {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
  messageCount: number;
  /** Preview of the last message (truncated), null if no messages */
  lastMessagePreview: string | null;
}

/**
 * API response for fetching conversations list
 */
export interface ConversationsListResponse {
  conversations: Conversation[];
  total: number;
}

/**
 * API response for creating a new conversation
 */
export interface CreateConversationResponse {
  id: string;
  title: string;
  createdAt: string;
}

/**
 * API response for renaming a conversation
 */
export interface RenameConversationResponse {
  id: string;
  title: string;
  updatedAt: string;
}

/**
 * API response for deleting a conversation
 */
export interface DeleteConversationResponse {
  status: 'deleted';
}

/**
 * Groups conversations by date category
 */
export interface GroupedConversations {
  today: Conversation[];
  yesterday: Conversation[];
  previousWeek: Conversation[];
  older: Conversation[];
}

/**
 * SSE Event types from backend stream
 */
export type SSEEventType =
  | 'status'
  | 'token'
  | 'tool_call'
  | 'tool_result'
  | 'done'
  | 'error';

export interface SSEEvent {
  type: SSEEventType;
  message?: string;
  content?: string;
  name?: string;
  args?: Record<string, unknown>;
  code?: string;
}

/**
 * Helper function to get file category from MIME type
 */
export function getFileCategory(mimeType: string): FileCategory | null {
  if (mimeType.startsWith('image/')) {
    return 'image';
  }
  if (
    mimeType === 'application/pdf' ||
    mimeType === 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' ||
    mimeType === 'text/plain'
  ) {
    return 'document';
  }
  if (
    mimeType === 'text/csv' ||
    mimeType === 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
  ) {
    return 'spreadsheet';
  }
  return null;
}

/**
 * Helper to check if file is an image
 */
export function isImageFile(mimeType: string): boolean {
  return mimeType.startsWith('image/');
}

/**
 * Helper to format file size for display
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

/**
 * Helper to format timestamp for display
 */
export function formatTimestamp(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  if (isToday) {
    return date.toLocaleTimeString(undefined, {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true
    });
  }

  return date.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true,
  });
}
