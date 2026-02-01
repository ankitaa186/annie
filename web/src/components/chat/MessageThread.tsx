import { memo, useRef, forwardRef } from 'react';
import { Virtuoso, VirtuosoHandle } from 'react-virtuoso';
import { Bot } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UserMessage } from './UserMessage';
import { AnnieMessage } from './AnnieMessage';
import { MessageContent } from './MessageContent';
import { ToolCallCard } from './ToolCallCard';
import type { Message } from '@/types';
import type { AnnieState, ActiveToolCall } from '@/lib/stores/appStore';

interface MessageThreadProps {
  messages: Message[];
  streamingMessage: string | null;
  isLoading: boolean;
  isStreaming: boolean;
  annieState?: AnnieState;
  activeTool?: ActiveToolCall | null;
  className?: string;
}

/**
 * Loading skeleton for message history
 */
const LoadingSkeleton = memo(function LoadingSkeleton() {
  return (
    <div
      className="flex flex-col gap-4 p-4"
      aria-label="Loading conversation history"
      aria-busy="true"
    >
      {/* Simulate user message */}
      <div className="flex justify-end">
        <div className="h-16 w-48 animate-pulse rounded-2xl rounded-br-sm bg-primary/20" />
      </div>
      {/* Simulate Annie message */}
      <div className="flex gap-3">
        <div className="h-8 w-8 animate-pulse rounded-full bg-muted" />
        <div className="h-24 w-64 animate-pulse rounded-2xl rounded-bl-sm bg-muted" />
      </div>
      {/* Simulate user message */}
      <div className="flex justify-end">
        <div className="h-12 w-40 animate-pulse rounded-2xl rounded-br-sm bg-primary/20" />
      </div>
      {/* Simulate Annie message */}
      <div className="flex gap-3">
        <div className="h-8 w-8 animate-pulse rounded-full bg-muted" />
        <div className="h-32 w-72 animate-pulse rounded-2xl rounded-bl-sm bg-muted" />
      </div>
    </div>
  );
});

/**
 * Empty state when no conversation is active
 */
const EmptyState = memo(function EmptyState() {
  return (
    <div
      className={cn(
        'flex h-full flex-col items-center justify-center',
        'text-muted-foreground'
      )}
      aria-label="No messages yet"
    >
      <div
        className={cn(
          'flex h-16 w-16 items-center justify-center',
          'mb-4 rounded-full bg-muted'
        )}
      >
        <Bot className="h-8 w-8 opacity-50" aria-hidden="true" />
      </div>
      <h2 className="mb-2 text-xl font-semibold text-foreground">
        Start a conversation
      </h2>
      <p className="max-w-sm text-center text-sm">
        Send a message to Annie and get help with decisions, advice, or just
        chat about anything on your mind.
      </p>
    </div>
  );
});

/**
 * Typing indicator while Annie is responding
 */
const TypingIndicator = memo(function TypingIndicator() {
  return (
    <div
      className="flex gap-3 px-4"
      role="status"
      aria-label="Annie is typing"
    >
      <div
        className={cn(
          'flex h-8 w-8 flex-shrink-0 items-center justify-center',
          'rounded-full bg-annie-purple text-white',
          'shadow-sm'
        )}
        aria-hidden="true"
      >
        <Bot className="h-5 w-5" />
      </div>
      <div
        className={cn(
          'flex items-center gap-1 rounded-2xl rounded-bl-sm px-4 py-3',
          'bg-muted shadow-sm'
        )}
      >
        <span
          className="inline-block h-2 w-2 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '0ms' }}
        />
        <span
          className="inline-block h-2 w-2 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '150ms' }}
        />
        <span
          className="inline-block h-2 w-2 animate-bounce rounded-full bg-muted-foreground"
          style={{ animationDelay: '300ms' }}
        />
      </div>
    </div>
  );
});

/**
 * Streaming message display (shows Annie's response as it's being generated)
 */
const StreamingMessage = memo(function StreamingMessage({
  content,
}: {
  content: string;
}) {
  return (
    <div className="flex gap-3 px-4" role="status" aria-live="polite">
      <div
        className={cn(
          'flex h-8 w-8 flex-shrink-0 items-center justify-center',
          'rounded-full bg-annie-purple text-white',
          'shadow-sm'
        )}
        aria-hidden="true"
      >
        <Bot className="h-5 w-5" />
      </div>
      <div className="flex max-w-[80%] flex-col gap-1">
        <div
          className={cn(
            'rounded-2xl rounded-bl-sm px-4 py-2',
            'bg-muted shadow-sm'
          )}
        >
          <MessageContent content={content} />
          {/* Blinking cursor */}
          <span className="inline-block h-4 w-0.5 animate-pulse bg-foreground" />
        </div>
      </div>
    </div>
  );
});

/**
 * Individual message row component for virtual list
 */
const MessageRow = forwardRef<HTMLDivElement, { message: Message }>(
  function MessageRow({ message }, ref) {
    if (message.role === 'user') {
      return (
        <div ref={ref} className="py-2">
          <UserMessage message={message} />
        </div>
      );
    }

    return (
      <div ref={ref} className="py-2">
        <AnnieMessage message={message} />
      </div>
    );
  }
);

/**
 * MessageThread - Main chat message display component
 *
 * Features:
 * - Virtual scrolling for performance with 100+ messages (react-virtuoso)
 * - Auto-scroll to bottom on new messages
 * - Starts at bottom of conversation
 * - Loading skeleton while fetching history
 * - Empty state for new conversations
 * - Typing indicator while streaming
 * - Streaming message display
 */
export const MessageThread = memo(function MessageThread({
  messages,
  streamingMessage,
  isLoading,
  isStreaming,
  annieState: _annieState,
  activeTool,
  className,
}: MessageThreadProps) {
  const virtuosoRef = useRef<VirtuosoHandle>(null);

  // Show loading state
  if (isLoading) {
    return (
      <div className={cn('flex h-full flex-col overflow-hidden', className)}>
        <LoadingSkeleton />
      </div>
    );
  }

  // Show empty state
  if (messages.length === 0 && !streamingMessage && !isStreaming) {
    return (
      <div className={cn('flex h-full flex-col', className)}>
        <EmptyState />
      </div>
    );
  }

  // Render streaming content (typing indicator, tool card, or streaming message)
  const renderStreamingContent = () => {
    if (activeTool) {
      return (
        <div className="px-4 py-2">
          <div className="ml-11 max-w-[80%]">
            <ToolCallCard tool={activeTool} />
          </div>
        </div>
      );
    }

    if (streamingMessage) {
      return (
        <div className="py-2">
          <StreamingMessage content={streamingMessage} />
        </div>
      );
    }

    if (isStreaming) {
      return (
        <div className="py-2">
          <TypingIndicator />
        </div>
      );
    }

    return null;
  };

  return (
    <div
      className={cn('flex h-full flex-col overflow-hidden', className)}
      role="log"
      aria-label="Conversation messages"
      aria-live="polite"
    >
      <Virtuoso
        ref={virtuosoRef}
        data={messages}
        initialTopMostItemIndex={messages.length - 1}
        followOutput="auto"
        alignToBottom
        itemContent={(_index, message) => <MessageRow message={message} />}
        components={{
          Footer: () => renderStreamingContent(),
        }}
        className="h-full"
      />
    </div>
  );
});

export default MessageThread;
