/**
 * useConversations hook - Manages conversation list operations
 *
 * Handles:
 * - Fetching conversations list from backend API
 * - Fetching messages for a conversation
 * - Creating new conversations
 * - Deleting conversations
 * - Renaming conversations
 * - Optimistic UI updates
 *
 * Note: When Story 20.14 (Backend API Extensions) is not available,
 * falls back to local state management with mock data.
 */

import { useCallback, useEffect } from 'react';
import { useAppStore } from '@/lib/stores/appStore';
import { apiUrl } from '@/lib/config';
import type {
  Conversation,
  ConversationsListResponse,
  CreateConversationResponse,
  RenameConversationResponse,
  Message,
} from '@/types';

/** API response for fetching messages */
interface MessagesResponse {
  messages: Array<{
    role: 'user' | 'assistant';
    content: string;
    timestamp?: string;
    tool_calls?: unknown[];
  }>;
  pagination: {
    page: number;
    limit: number;
    total: number;
    has_more: boolean;
  };
}

/** Mock data for development when backend API is unavailable */
const MOCK_CONVERSATIONS: Conversation[] = [];

/** Check if we're using mock data (backend unavailable) */
let useMockData = false;

/**
 * Generate a new conversation with default values
 */
function createNewConversation(): Conversation {
  const now = new Date().toISOString();
  return {
    id: crypto.randomUUID(),
    title: 'New Chat',
    createdAt: now,
    updatedAt: now,
    messageCount: 0,
    lastMessagePreview: null,
  };
}

/**
 * Get user ID for API requests
 */
function getUserId(): string {
  let userId = sessionStorage.getItem('annie-user-id');
  if (!userId) {
    const timestamp = Date.now().toString(36);
    const random = Math.random().toString(36).substring(2, 8);
    userId = `web_${timestamp}_${random}`;
    sessionStorage.setItem('annie-user-id', userId);
  }
  return userId;
}

// Global flag to track if initial fetch has been triggered (prevents double fetch from multiple hook instances)
let initialFetchTriggered = false;

/**
 * useConversations - Hook for managing conversations list
 */
export function useConversations() {
  const {
    conversations,
    conversationsLoading,
    conversationsError,
    activeConversationId,
    messages: storeMessages,
    setConversations,
    setConversationsLoading,
    setConversationsError,
    setActiveConversation,
    setMessages,
    setIsLoadingHistory,
    addConversation,
    removeConversation,
    updateConversation,
  } = useAppStore();

  /**
   * Fetch conversations from the backend API
   */
  const fetchConversations = useCallback(async (): Promise<void> => {
    setConversationsLoading(true);
    setConversationsError(null);

    try {
      const response = await fetch(apiUrl(`/conversations?user_id=${getUserId()}`), {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        if (response.status === 404) {
          // API not implemented yet, use mock data
          useMockData = true;
          setConversations(MOCK_CONVERSATIONS);
          return;
        }
        throw new Error(`Failed to fetch conversations: ${response.status}`);
      }

      const data: ConversationsListResponse = await response.json();

      // Transform snake_case from API to camelCase for frontend
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const transformedConversations: Conversation[] = (data.conversations as any[]).map((conv) => ({
        id: conv.id as string,
        title: conv.title as string,
        createdAt: (conv.created_at || conv.createdAt) as string,
        updatedAt: (conv.updated_at || conv.updatedAt) as string,
        messageCount: (conv.message_count || conv.messageCount || 0) as number,
        lastMessagePreview: (conv.last_message_preview || conv.lastMessagePreview || null) as string | null,
      }));

      setConversations(transformedConversations);
      useMockData = false;
    } catch (err) {
      // On network error, fall back to mock data
      console.warn('Conversations API unavailable, using local state:', err);
      useMockData = true;
      setConversations(MOCK_CONVERSATIONS);
    } finally {
      setConversationsLoading(false);
    }
  }, [setConversations, setConversationsLoading, setConversationsError]);

  /**
   * Fetch messages for a conversation from the backend API
   */
  const fetchMessages = useCallback(async (conversationId: string): Promise<Message[]> => {
    // Skip if we already have messages for this conversation
    const existingMessages = storeMessages[conversationId];
    if (existingMessages && existingMessages.length > 0) {
      return existingMessages;
    }

    setIsLoadingHistory(true);

    try {
      const response = await fetch(apiUrl(`/conversations/${conversationId}/messages`), {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        if (response.status === 404) {
          // API not implemented or conversation not found
          console.warn('Messages API unavailable or conversation not found');
          setIsLoadingHistory(false);
          return [];
        }
        throw new Error(`Failed to fetch messages: ${response.status}`);
      }

      const data: MessagesResponse = await response.json();

      // Transform messages and generate IDs
      const transformedMessages: Message[] = data.messages.map((msg, index) => ({
        id: `msg-${conversationId}-${index}-${Date.now()}`,
        role: msg.role,
        content: msg.content,
        timestamp: msg.timestamp || new Date().toISOString(),
      }));

      // Store in state
      setMessages(conversationId, transformedMessages);

      return transformedMessages;
    } catch (err) {
      console.warn('Failed to fetch messages:', err);
      return [];
    } finally {
      setIsLoadingHistory(false);
    }
  }, [storeMessages, setMessages, setIsLoadingHistory]);

  /**
   * Create a new conversation
   */
  const createConversation = useCallback(async (): Promise<Conversation> => {
    const newConversation = createNewConversation();

    // Optimistic update - add immediately
    addConversation(newConversation);

    if (!useMockData) {
      try {
        const response = await fetch(apiUrl('/conversations'), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_id: getUserId(),
          }),
        });

        if (response.ok) {
          const data: CreateConversationResponse = await response.json();

          // Update with server-generated data
          updateConversation(newConversation.id, {
            id: data.id,
            title: data.title,
            createdAt: data.createdAt,
          });

          return {
            ...newConversation,
            id: data.id,
            title: data.title,
            createdAt: data.createdAt,
          };
        }
      } catch (err) {
        // API unavailable, keep optimistic update
        console.warn('Failed to sync conversation creation:', err);
      }
    }

    return newConversation;
  }, [addConversation, updateConversation]);

  /**
   * Delete a conversation
   */
  const deleteConversation = useCallback(
    async (id: string): Promise<void> => {
      // Get current state for potential rollback
      const conversationToDelete = conversations.find((c) => c.id === id);
      const wasActive = activeConversationId === id;

      // Optimistic update - remove immediately
      removeConversation(id);

      // If deleted conversation was active, switch to another
      if (wasActive && conversations.length > 1) {
        const remainingConversations = conversations.filter((c) => c.id !== id);
        const firstRemaining = remainingConversations[0];
        if (firstRemaining) {
          setActiveConversation(firstRemaining.id);
        }
      }

      if (!useMockData) {
        try {
          const response = await fetch(apiUrl(`/conversations/${id}?user_id=${getUserId()}`), {
            method: 'DELETE',
          });

          if (!response.ok && response.status !== 404) {
            // Rollback on failure
            if (conversationToDelete) {
              addConversation(conversationToDelete);
              if (wasActive) {
                setActiveConversation(id);
              }
            }
            throw new Error(`Failed to delete conversation: ${response.status}`);
          }
        } catch (err) {
          console.warn('Failed to sync conversation deletion:', err);
          // Keep optimistic update even on API error for better UX
        }
      }
    },
    [conversations, activeConversationId, removeConversation, addConversation, setActiveConversation]
  );

  /**
   * Rename a conversation
   */
  const renameConversation = useCallback(
    async (id: string, newTitle: string): Promise<void> => {
      const trimmedTitle = newTitle.trim();
      if (!trimmedTitle) {
        throw new Error('Title cannot be empty');
      }

      // Get current title for potential rollback
      const conversation = conversations.find((c) => c.id === id);
      const oldTitle = conversation?.title;

      // Optimistic update
      updateConversation(id, {
        title: trimmedTitle,
        updatedAt: new Date().toISOString(),
      });

      if (!useMockData) {
        try {
          const response = await fetch(apiUrl(`/conversations/${id}`), {
            method: 'PATCH',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              user_id: getUserId(),
              title: trimmedTitle,
            }),
          });

          if (response.ok) {
            const data: RenameConversationResponse = await response.json();
            updateConversation(id, {
              title: data.title,
              updatedAt: data.updatedAt,
            });
          } else if (response.status !== 404) {
            // Rollback on failure (except 404 which means API not implemented)
            if (oldTitle !== undefined) {
              updateConversation(id, { title: oldTitle });
            }
            throw new Error(`Failed to rename conversation: ${response.status}`);
          }
        } catch (err) {
          console.warn('Failed to sync conversation rename:', err);
          // Keep optimistic update even on API error
        }
      }
    },
    [conversations, updateConversation]
  );

  // Fetch conversations on mount (only once across all hook instances)
  useEffect(() => {
    if (!initialFetchTriggered && !conversationsLoading) {
      initialFetchTriggered = true;
      fetchConversations();
    }
  }, [fetchConversations, conversationsLoading]);

  return {
    conversations,
    isLoading: conversationsLoading,
    error: conversationsError,
    fetchConversations,
    fetchMessages,
    createConversation,
    deleteConversation,
    renameConversation,
  };
}

export default useConversations;
