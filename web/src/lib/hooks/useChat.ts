/**
 * useChat hook - Manages chat message sending and state
 *
 * Handles:
 * - Sending messages to the backend API
 * - Converting files to base64 attachments
 * - Optimistically adding user messages to store
 * - Triggering SSE stream connection (Story 20.7)
 */

import { useState, useCallback } from 'react';
import { useAppStore } from '@/lib/stores/appStore';
import { apiUrl } from '@/lib/config';
import { filesToAttachments, type FileAttachment } from '@/lib/utils/fileValidation';
import type { Message, Conversation } from '@/types';

/** Chat API request body */
interface ChatRequest {
  user_id: string;
  platform: 'web';
  message: string;
  // Note: conversation_id is managed by session on backend
  // No need to pass it - backend uses session's current conversation
  context?: Record<string, unknown>;
  files?: FileAttachment[];
}

/** Chat API response */
interface ChatResponse {
  conversation_id: string;
  status: 'streaming';
  stream_url: string;
  timestamp: string;
}

/** useChat hook return type */
interface UseChatReturn {
  /** Send a message and return the conversation ID for SSE streaming */
  sendMessage: (message: string, files?: File[]) => Promise<string>;
  /** Whether a message is currently being sent */
  isSending: boolean;
  /** Any error that occurred */
  error: string | null;
  /** Clear the current error */
  clearError: () => void;
}

/**
 * Get or generate user ID for the session
 * In production, this would come from auth (Cloudflare Access)
 */
function getUserId(): string {
  // Check for existing ID in session storage
  let userId = sessionStorage.getItem('annie-user-id');

  if (!userId) {
    // Generate a new ID for anonymous users
    // Format: web_<timestamp>_<random>
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    userId = `web_${timestamp}_${random}`;
    sessionStorage.setItem('annie-user-id', userId);
  }

  return userId;
}

/**
 * useChat - Hook for sending chat messages
 */
export function useChat(): UseChatReturn {
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Use appStore (the main store used by the app)
  const activeConversationId = useAppStore((state) => state.activeConversationId);
  const addMessage = useAppStore((state) => state.addMessage);
  const addConversation = useAppStore((state) => state.addConversation);
  const setActiveConversation = useAppStore((state) => state.setActiveConversation);
  const setIsStreaming = useAppStore((state) => state.setIsStreaming);
  const setStreamingConversationId = useAppStore((state) => state.setStreamingConversationId);

  /**
   * Send a message to Annie
   */
  const sendMessage = useCallback(
    async (message: string, files: File[] = []) => {
      // Clear previous error
      setError(null);

      // Validate input
      const trimmedMessage = message.trim();
      if (!trimmedMessage && files.length === 0) {
        throw new Error('Message or files required');
      }

      setIsSending(true);
      console.log('[useChat] Before setIsStreaming - activeConversationId:', activeConversationId);
      // Set streaming state AND streaming conversation ID together
      // This ensures isStreamingForThisConversation is true immediately
      setIsStreaming(true);
      if (activeConversationId) {
        setStreamingConversationId(activeConversationId);
      }
      console.log('[useChat] setIsStreaming(true) and setStreamingConversationId called, activeConversationId:', activeConversationId);

      try {
        // Convert files to base64 attachments for API
        const fileAttachments = files.length > 0 ? await filesToAttachments(files) : undefined;

        // Prepare API request
        // Note: No conversation_id needed - session on backend tracks current conversation
        const request: ChatRequest = {
          user_id: getUserId(),
          platform: 'web',
          message: trimmedMessage,
          ...(fileAttachments ? { files: fileAttachments } : {}),
        };

        // Send to backend FIRST to get the canonical conversation ID
        const response = await fetch(apiUrl('/chat'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(request),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `Request failed: ${response.status}`);
        }

        const data: ChatResponse = await response.json();
        const conversationId = data.conversation_id;

        // Now add user message and conversation using the backend's ID
        const displayFiles = fileAttachments
          ? fileAttachments.map((f) => ({
              filename: f.filename,
              mime_type: f.mime_type,
              size_bytes: f.size_bytes,
            }))
          : undefined;

        const userMessage: Message = {
          id: crypto.randomUUID(),
          role: 'user',
          content: trimmedMessage,
          timestamp: new Date().toISOString(),
          ...(displayFiles ? { files: displayFiles } : {}),
        };

        // Create conversation if it doesn't exist
        const state = useAppStore.getState();
        if (!state.conversations.find((c: Conversation) => c.id === conversationId)) {
          addConversation({
            id: conversationId,
            title: trimmedMessage.slice(0, 50) + (trimmedMessage.length > 50 ? '...' : ''),
            createdAt: new Date().toISOString(),
            updatedAt: new Date().toISOString(),
            messageCount: 0,
            lastMessagePreview: trimmedMessage.slice(0, 100),
          });
        }

        // Set active conversation and add user message
        setActiveConversation(conversationId);
        addMessage(conversationId, userMessage);

        // Return the conversation ID for SSE streaming
        return conversationId;

      } catch (err) {
        const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
        setError(errorMessage);
        setIsStreaming(false);
        throw err; // Re-throw so InputArea can handle restoration
      } finally {
        setIsSending(false);
        // Note: setIsStreaming(false) is now handled by useStream hook when SSE completes
      }
    },
    [activeConversationId, addMessage, addConversation, setActiveConversation, setIsStreaming, setStreamingConversationId]
  );

  /**
   * Clear the current error
   */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    sendMessage,
    isSending,
    error,
    clearError,
  };
}

export default useChat;
