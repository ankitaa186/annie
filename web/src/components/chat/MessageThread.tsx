import {
  memo,
  useRef,
  useEffect,
  useCallback,
  forwardRef,
} from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
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
 * - Virtual scrolling for performance with 100+ messages
 * - Auto-scroll to bottom on new messages
 * - Smooth scroll behavior
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
  annieState: _annieState, // Reserved for future use
  activeTool,
  className,
}: MessageThreadProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const prevMessageCountRef = useRef(messages.length);
  const shouldScrollRef = useRef(true);

  // Virtual scrolling setup
  const virtualizer = useVirtualizer({
    count: messages.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 100, // Estimated message height
    overscan: 5, // Render 5 extra items outside viewport
    getItemKey: (index) => messages[index]?.id ?? `msg-${index}`,
  });

  const virtualItems = virtualizer.getVirtualItems();

  // Check if user is near the bottom (within 150px)
  const checkIfNearBottom = useCallback(() => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return true;

    const { scrollTop, scrollHeight, clientHeight } = scrollElement;
    return scrollHeight - scrollTop - clientHeight < 150;
  }, []);

  // Scroll to bottom with smooth behavior
  const scrollToBottom = useCallback((smooth = true) => {
    const scrollElement = scrollRef.current;
    if (!scrollElement) return;

    scrollElement.scrollTo({
      top: scrollElement.scrollHeight,
      behavior: smooth ? 'smooth' : 'auto',
    });
  }, []);

  // Track scroll position to determine if we should auto-scroll
  const handleScroll = useCallback(() => {
    shouldScrollRef.current = checkIfNearBottom();
  }, [checkIfNearBottom]);

  // Auto-scroll when new messages arrive (only if user is near bottom)
  useEffect(() => {
    if (messages.length > prevMessageCountRef.current) {
      if (shouldScrollRef.current) {
        // Use requestAnimationFrame to ensure DOM has updated
        requestAnimationFrame(() => {
          scrollToBottom(true);
        });
      }
    }
    prevMessageCountRef.current = messages.length;
  }, [messages.length, scrollToBottom]);

  // Auto-scroll when streaming starts/updates
  useEffect(() => {
    if (streamingMessage && shouldScrollRef.current) {
      requestAnimationFrame(() => {
        scrollToBottom(false);
      });
    }
  }, [streamingMessage, scrollToBottom]);

  // Initial scroll to bottom when messages first load
  useEffect(() => {
    if (!isLoading && messages.length > 0) {
      // Instant scroll on initial load
      scrollToBottom(false);
    }
  }, [isLoading, messages.length, scrollToBottom]);

  // Calculate total height for virtual list
  const totalSize = virtualizer.getTotalSize();

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

  return (
    <div
      ref={scrollRef}
      className={cn(
        'flex h-full flex-col overflow-y-auto scroll-smooth',
        className
      )}
      onScroll={handleScroll}
      role="log"
      aria-label="Conversation messages"
      aria-live="polite"
    >
      {/* Virtual list container */}
      <div
        style={{
          height: `${totalSize}px`,
          width: '100%',
          position: 'relative',
        }}
      >
        {virtualItems.map((virtualRow) => {
          const message = messages[virtualRow.index];
          if (!message) return null;
          return (
            <div
              key={virtualRow.key}
              data-index={virtualRow.index}
              ref={virtualizer.measureElement}
              style={{
                position: 'absolute',
                top: 0,
                left: 0,
                width: '100%',
                transform: `translateY(${virtualRow.start}px)`,
              }}
            >
              <MessageRow message={message} />
            </div>
          );
        })}
      </div>

      {/* Tool call card (shown when Annie is using a tool) */}
      {activeTool && (
        <div className="px-4 py-2">
          <div className="ml-11 max-w-[80%]">
            <ToolCallCard tool={activeTool} />
          </div>
        </div>
      )}

      {/* Streaming message (outside virtual list, always at bottom) */}
      {streamingMessage && (
        <div className="py-2">
          <StreamingMessage content={streamingMessage} />
        </div>
      )}

      {/* Typing indicator when streaming but no content yet */}
      {isStreaming && !streamingMessage && !activeTool && (
        <div className="py-2">
          <TypingIndicator />
        </div>
      )}

      {/* Bottom padding for comfortable reading */}
      <div className="h-4 flex-shrink-0" aria-hidden="true" />
    </div>
  );
});

export default MessageThread;
