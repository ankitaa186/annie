import { useParams, useNavigate } from 'react-router-dom';
import { useEffect, useCallback, useRef } from 'react';
import { cn } from '@/lib/utils';
import { MessageThread, InputArea } from '@/components/chat';
import { useChat } from '@/lib/hooks/useChat';
import { useStream } from '@/lib/hooks/useStream';
import { useConversations } from '@/lib/hooks/useConversations';
import {
  useAppStore,
  useActiveConversationId,
  useMessages,
  useStreamingMessage,
  useStreamingConversationId,
  useIsLoadingHistory,
  useIsStreaming,
  useAnnieState,
} from '@/lib/stores/appStore';

/**
 * ChatPage - Main chat interface page
 *
 * Displays the message thread for the active conversation.
 * Connects to Zustand store for message state.
 * Route: /chat/:conversationId
 */
export function ChatPage() {
  const { conversationId } = useParams<{ conversationId?: string }>();
  console.log('[ChatPage] Rendering, conversationId:', conversationId);
  const navigate = useNavigate();
  const prevConversationIdRef = useRef<string | null>(null);

  // Chat hook for sending messages
  const { sendMessage: sendChatMessage, isSending } = useChat();

  // Stream hook for SSE connection
  const { connect: connectStream, isStreaming: streamIsActive, activeTool } = useStream();

  // Conversations hook for fetching messages
  const { fetchMessages } = useConversations();

  // Wrap sendMessage to connect to stream after sending
  const sendMessage = useCallback(
    async (message: string, files?: File[]) => {
      console.log('[ChatPage] sendMessage called, URL conversationId:', conversationId);
      const newConversationId = await sendChatMessage(message, files);
      console.log('[ChatPage] sendChatMessage returned:', newConversationId);
      // Navigate to the conversation URL so the useEffect sync doesn't reset
      navigate(`/chat/${newConversationId}`, { replace: true });
      // Connect to SSE stream to receive Annie's response
      console.log('[ChatPage] Connecting stream to:', newConversationId);
      connectStream(newConversationId);
      return newConversationId;
    },
    [sendChatMessage, connectStream, navigate, conversationId]
  );

  // Store state
  const activeConversationId = useActiveConversationId();
  const messages = useMessages(activeConversationId);
  const streamingMessage = useStreamingMessage();
  const streamingConversationId = useStreamingConversationId();
  const isLoadingHistory = useIsLoadingHistory();
  const isStreaming = useIsStreaming();

  // Only show streaming indicators if the streaming belongs to THIS conversation
  const isStreamingForThisConversation = isStreaming && streamingConversationId === activeConversationId;
  const streamingMessageForThisConversation = streamingConversationId === activeConversationId ? streamingMessage : null;

  // What activeTool is actually being passed to MessageThread
  const activeToolForThisConversation = isStreamingForThisConversation ? activeTool : null;

  console.log('[ChatPage] Streaming state check:', {
    urlConversationId: conversationId,
    activeConversationId,
    streamingConversationId,
    isStreaming,
    isStreamingForThisConversation,
    streamingMessageLength: streamingMessage?.length || 0,
    streamingMessageForThisLength: streamingMessageForThisConversation?.length || 0,
    idsMatch: streamingConversationId === activeConversationId,
    activeTool: activeTool ? activeTool.name : null,
    activeToolForThis: activeToolForThisConversation ? activeToolForThisConversation.name : null,
  });
  const annieState = useAnnieState();

  // Store actions
  const setActiveConversation = useAppStore(
    (state) => state.setActiveConversation
  );

  // Sync URL parameter with store
  useEffect(() => {
    if (conversationId !== activeConversationId) {
      setActiveConversation(conversationId || null);
    }
  }, [conversationId, activeConversationId, setActiveConversation]);

  // Fetch messages when switching to a different conversation
  useEffect(() => {
    // Only fetch if we have a conversation ID and it changed
    if (conversationId && conversationId !== prevConversationIdRef.current) {
      prevConversationIdRef.current = conversationId;
      // Fetch messages for this conversation (the hook checks if already loaded)
      fetchMessages(conversationId);
    }
  }, [conversationId, fetchMessages]);

  // Disable input while sending or streaming response (for this conversation)
  const inputDisabled = isSending || isStreamingForThisConversation || streamIsActive;

  // Dynamic placeholder based on state
  const placeholder = isStreamingForThisConversation
    ? 'Annie is responding...'
    : 'Type a message...';

  return (
    <div
      className={cn('flex h-full min-h-0 flex-col overflow-hidden')}
      aria-label="Chat conversation"
    >
      <MessageThread
        messages={messages}
        streamingMessage={streamingMessageForThisConversation}
        isLoading={isLoadingHistory}
        isStreaming={isStreamingForThisConversation}
        annieState={annieState}
        activeTool={activeToolForThisConversation}
        className="flex-1"
      />

      {/* Message input */}
      <InputArea
        onSend={sendMessage}
        disabled={inputDisabled}
        placeholder={placeholder}
      />
    </div>
  );
}

export default ChatPage;
