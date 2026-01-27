/**
 * useSession hook - Manages user session lifecycle
 *
 * Handles:
 * - Creating/resuming session on app load
 * - Updating current conversation when user switches
 * - Session state in Zustand store
 */

import { useCallback, useEffect, useRef } from 'react';
import { useAppStore } from '@/lib/stores/appStore';
import { apiUrl } from '@/lib/config';

/** Session state from backend */
interface SessionResponse {
  user_id: string;
  platform: string;
  conversation_id: string | null;
  created_at: string;
  last_activity: string;
}

/** useSession hook return type */
interface UseSessionReturn {
  /** Whether session is being initialized */
  isInitializing: boolean;
  /** Current session's conversation ID */
  currentConversationId: string | null;
  /** Switch to a different conversation */
  switchConversation: (conversationId: string | null) => Promise<void>;
  /** Initialize or resume session */
  initSession: (conversationId?: string) => Promise<void>;
}

// Track if session has been initialized globally
let sessionInitialized = false;

/**
 * useSession - Hook for session management
 */
export function useSession(): UseSessionReturn {
  const isInitializingRef = useRef(false);

  const activeConversationId = useAppStore((state) => state.activeConversationId);
  const setActiveConversation = useAppStore((state) => state.setActiveConversation);

  /**
   * Initialize or resume session on app load
   */
  const initSession = useCallback(async (conversationId?: string): Promise<void> => {
    if (isInitializingRef.current) return;
    isInitializingRef.current = true;

    try {
      const response = await fetch(apiUrl('/session'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform: 'web',
          ...(conversationId ? { conversation_id: conversationId } : {}),
        }),
      });

      if (!response.ok) {
        console.warn('Session init failed:', response.status);
        return;
      }

      const data: SessionResponse = await response.json();

      // Update store with session's current conversation
      if (data.conversation_id) {
        setActiveConversation(data.conversation_id);
      }

      sessionInitialized = true;
    } catch (err) {
      console.warn('Failed to initialize session:', err);
    } finally {
      isInitializingRef.current = false;
    }
  }, [setActiveConversation]);

  /**
   * Switch to a different conversation
   */
  const switchConversation = useCallback(async (conversationId: string | null): Promise<void> => {
    try {
      const response = await fetch(apiUrl('/session'), {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          conversation_id: conversationId,
        }),
      });

      if (!response.ok) {
        console.warn('Failed to switch conversation:', response.status);
        return;
      }

      const data: SessionResponse = await response.json();

      console.log('[switchConversation] Requested:', conversationId, 'Backend returned:', data.conversation_id);

      // Update store
      if (data.conversation_id) {
        setActiveConversation(data.conversation_id);
      } else {
        setActiveConversation(null);
      }
    } catch (err) {
      console.warn('Failed to switch conversation:', err);
    }
  }, [setActiveConversation]);

  // Initialize session on first mount
  useEffect(() => {
    if (!sessionInitialized) {
      initSession();
    }
  }, [initSession]);

  return {
    isInitializing: isInitializingRef.current,
    currentConversationId: activeConversationId,
    switchConversation,
    initSession,
  };
}

export default useSession;
