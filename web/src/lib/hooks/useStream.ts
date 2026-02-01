/**
 * useStream hook - Manages SSE streaming for Annie's responses
 *
 * Handles:
 * - EventSource lifecycle management
 * - Parsing incoming SSE events
 * - Updating store state (streaming message, Annie state)
 * - Auto-reconnect with exponential backoff
 * - Abort/cancel functionality
 *
 * Story 20.7: SSE Streaming Integration
 */

import { useCallback, useRef, useEffect, useState } from 'react';
import { useAppStore } from '@/lib/stores/appStore';
import type { Message } from '@/types';
import {
  StreamClient,
  createStreamClient,
  type ConnectionState,
  type StreamClientHandlers,
} from '@/lib/api/streamClient';

/** Tool call information for display */
export interface ActiveToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'pending' | 'running' | 'completed' | 'error';
  result?: unknown;
}

/** useStream hook return type */
export interface UseStreamReturn {
  /** Current connection state */
  connectionState: ConnectionState;
  /** Whether currently streaming */
  isStreaming: boolean;
  /** Any stream error message */
  error: string | null;
  /** Error code from backend */
  errorCode: string | null;
  /** Active tool call information */
  activeTool: ActiveToolCall | null;
  /** Connect to stream for given conversation */
  connect: (conversationId: string) => void;
  /** Cancel/abort the current stream */
  cancel: () => void;
  /** Retry the last failed connection */
  retry: () => void;
  /** Clear error state */
  clearError: () => void;
}

/**
 * useStream - Hook for managing SSE streaming
 *
 * Usage:
 * ```tsx
 * function ChatComponent() {
 *   const { connect, cancel, isStreaming, error } = useStream();
 *
 *   const handleSendMessage = async (message: string) => {
 *     const response = await sendChatMessage(message);
 *     connect(response.conversation_id);
 *   };
 *
 *   return (
 *     <>
 *       {isStreaming && <CancelButton onClick={cancel} />}
 *       {error && <ErrorMessage message={error} />}
 *     </>
 *   );
 * }
 * ```
 */
export function useStream(): UseStreamReturn {
  // Local state
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [activeTool, setActiveTool] = useState<ActiveToolCall | null>(null);

  // Refs for stable references
  const streamClientRef = useRef<StreamClient | null>(null);
  const lastConversationIdRef = useRef<string | null>(null);
  const streamContentRef = useRef<string>('');

  // Store actions
  const setStreamingMessage = useAppStore((state) => state.setStreamingMessage);
  const setStreamingConversationId = useAppStore((state) => state.setStreamingConversationId);
  const appendToStreamingMessage = useAppStore((state) => state.appendToStreamingMessage);
  const setAnnieState = useAppStore((state) => state.setAnnieState);
  const addMessage = useAppStore((state) => state.addMessage);
  const setIsStreaming = useAppStore((state) => state.setIsStreaming);
  const activeConversationId = useAppStore((state) => state.activeConversationId);

  /**
   * Create stream client handlers
   */
  const createHandlers = useCallback(
    (conversationId: string): StreamClientHandlers => {
      console.log('[useStream] createHandlers called for conversation:', conversationId);
      return {
      onStatus: (message) => {
        // Status event - Annie is thinking/working
        console.log('[useStream] onStatus handler called:', message);
        setAnnieState('thinking');
      },

      onToken: (content) => {
        // Token event - append to streaming message
        console.log('[useStream] onToken handler called, content length:', content.length);
        streamContentRef.current += content;
        appendToStreamingMessage(content);
        setAnnieState('speaking');
      },

      onToolCall: (name, args) => {
        // Tool call event - delegate to tool display (Story 20.8)
        console.log('[useStream] onToolCall handler called:', name);
        setAnnieState('tool_calling');
        setActiveTool({
          name,
          args,
          status: 'running',
        });
      },

      onToolResult: (name, result) => {
        // Tool result event - update tool display
        setActiveTool((prev) =>
          prev && prev.name === name
            ? { ...prev, status: 'completed', result }
            : prev
        );
        console.debug('[SSE] Tool result:', name, result);
      },

      onDone: (tokensUsed) => {
        // Stream complete - finalize message
        const content = streamContentRef.current;
        // Use the conversation ID from the ref (set when connect was called)
        // This ensures we use the correct ID even if the closure is stale
        const targetConversationId = lastConversationIdRef.current || conversationId;
        console.debug('[SSE] Done, adding message to:', targetConversationId, 'content length:', content.length);

        if (content) {
          const assistantMessage: Message = {
            id: crypto.randomUUID(),
            role: 'assistant',
            content,
            timestamp: new Date().toISOString(),
          };
          addMessage(targetConversationId, assistantMessage);
          console.debug('[SSE] Message added:', assistantMessage.id);
        }

        // Reset state - IMPORTANT: clear streaming message AFTER adding the real message
        streamContentRef.current = '';
        setStreamingMessage(null);
        setStreamingConversationId(null);
        setIsStreaming(false);
        setAnnieState('idle');
        setActiveTool(null);
        setConnectionState('closed');

        console.debug('[SSE] Done, tokens used:', tokensUsed);
      },

      onError: (message, code) => {
        // Error from server
        setError(message);
        setErrorCode(code || null);
        setStreamingConversationId(null);
        setIsStreaming(false);
        setAnnieState('idle');
        setActiveTool(null);
        setConnectionState('error');

        console.error('[SSE] Error:', message, code);
      },

      onConnectionStateChange: (state) => {
        setConnectionState(state);
      },
    };
    },
    [addMessage, appendToStreamingMessage, setAnnieState, setStreamingMessage, setStreamingConversationId, setIsStreaming]
  );

  /**
   * Connect to SSE stream for a conversation
   */
  const connect = useCallback(
    (conversationId: string) => {
      // Clear any previous errors
      setError(null);
      setErrorCode(null);

      // Reset streaming content
      streamContentRef.current = '';
      setStreamingMessage(null);

      // Store conversation ID for retry and for display filtering
      console.log('[useStream] connect() setting streamingConversationId to:', conversationId);
      lastConversationIdRef.current = conversationId;
      setStreamingConversationId(conversationId);

      // Create or reset stream client
      if (streamClientRef.current) {
        streamClientRef.current.reset(conversationId);
      } else {
        streamClientRef.current = createStreamClient(
          conversationId,
          createHandlers(conversationId)
        );
      }

      // Update handlers for new conversation
      streamClientRef.current = createStreamClient(
        conversationId,
        createHandlers(conversationId)
      );

      // Start connection
      setAnnieState('thinking');
      console.log('[useStream] Connecting to SSE for conversation:', conversationId);
      streamClientRef.current.connect();
    },
    [createHandlers, setAnnieState, setStreamingMessage, setStreamingConversationId]
  );

  /**
   * Cancel the current stream
   */
  const cancel = useCallback(() => {
    if (streamClientRef.current) {
      streamClientRef.current.disconnect();
    }

    // Finalize partial message if any content was received
    const content = streamContentRef.current;
    const conversationId = lastConversationIdRef.current || activeConversationId;

    if (content && conversationId) {
      addMessage(conversationId, {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: content + '\n\n*[Response cancelled]*',
        timestamp: new Date().toISOString(),
      });
    }

    // Reset state
    setStreamingMessage(null);
    setStreamingConversationId(null);
    streamContentRef.current = '';
    setAnnieState('idle');
    setActiveTool(null);
    setConnectionState('closed');
  }, [activeConversationId, addMessage, setAnnieState, setStreamingMessage, setStreamingConversationId]);

  /**
   * Retry the last failed connection
   */
  const retry = useCallback(() => {
    const conversationId = lastConversationIdRef.current;
    if (conversationId) {
      connect(conversationId);
    }
  }, [connect]);

  /**
   * Clear error state
   */
  const clearError = useCallback(() => {
    setError(null);
    setErrorCode(null);
  }, []);

  /**
   * Cleanup on unmount
   */
  useEffect(() => {
    return () => {
      if (streamClientRef.current) {
        streamClientRef.current.disconnect();
      }
    };
  }, []);

  // Compute derived state
  const isStreaming =
    connectionState === 'connecting' || connectionState === 'connected';

  return {
    connectionState,
    isStreaming,
    error,
    errorCode,
    activeTool,
    connect,
    cancel,
    retry,
    clearError,
  };
}

export default useStream;
