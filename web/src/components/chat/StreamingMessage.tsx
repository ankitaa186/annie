/**
 * StreamingMessage component - Displays Annie's response as it streams
 *
 * Features:
 * - Real-time content display with blinking cursor
 * - Cancel button during streaming
 * - Typing indicator before first token
 * - Accessible with ARIA live regions
 *
 * Story 20.7: SSE Streaming Integration
 */

import { memo } from 'react';
import { Bot, X, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { MessageContent } from './MessageContent';
import type { AnnieState } from '@/lib/stores/appStore';

interface StreamingMessageProps {
  /** Current streaming content */
  content: string | null;
  /** Annie's current state */
  annieState: AnnieState;
  /** Callback to cancel the stream */
  onCancel?: () => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Typing indicator - shown while waiting for first token
 */
const TypingIndicator = memo(function TypingIndicator() {
  return (
    <div className="flex gap-1" aria-hidden="true">
      <span
        className={cn(
          'inline-block h-2 w-2 rounded-full bg-muted-foreground',
          'animate-bounce'
        )}
        style={{ animationDelay: '0ms' }}
      />
      <span
        className={cn(
          'inline-block h-2 w-2 rounded-full bg-muted-foreground',
          'animate-bounce'
        )}
        style={{ animationDelay: '150ms' }}
      />
      <span
        className={cn(
          'inline-block h-2 w-2 rounded-full bg-muted-foreground',
          'animate-bounce'
        )}
        style={{ animationDelay: '300ms' }}
      />
    </div>
  );
});

/**
 * Blinking cursor - shown while streaming
 */
const BlinkingCursor = memo(function BlinkingCursor() {
  return (
    <span
      className={cn(
        'inline-block h-4 w-0.5 ml-0.5',
        'bg-foreground animate-pulse'
      )}
      aria-hidden="true"
    />
  );
});

/**
 * Status indicator - shows what Annie is doing
 */
const StatusIndicator = memo(function StatusIndicator({
  state,
}: {
  state: AnnieState;
}) {
  const statusText = {
    idle: '',
    thinking: 'Annie is thinking...',
    speaking: 'Annie is responding...',
    tool_calling: 'Annie is using a tool...',
  };

  if (state === 'idle') return null;

  return (
    <span className="sr-only">{statusText[state]}</span>
  );
});

/**
 * StreamingMessage - Shows Annie's streaming response
 */
export const StreamingMessage = memo(function StreamingMessage({
  content,
  annieState,
  onCancel,
  className,
}: StreamingMessageProps) {
  const isThinking = annieState === 'thinking' && !content;
  const isStreaming = annieState !== 'idle';
  const showContent = content && content.length > 0;
  const showCancelButton = isStreaming && onCancel;

  // Don't render if idle and no content
  if (!isStreaming && !showContent) {
    return null;
  }

  return (
    <div
      className={cn('flex gap-3 px-4', className)}
      role="status"
      aria-live="polite"
      aria-busy={isStreaming}
      aria-label={isThinking ? 'Annie is thinking' : 'Annie is responding'}
    >
      {/* Annie avatar */}
      <div
        className={cn(
          'flex h-8 w-8 flex-shrink-0 items-center justify-center',
          'rounded-full bg-annie-purple text-white',
          'shadow-sm'
        )}
        aria-hidden="true"
      >
        {annieState === 'tool_calling' ? (
          <Loader2 className="h-5 w-5 animate-spin" />
        ) : (
          <Bot className="h-5 w-5" />
        )}
      </div>

      {/* Message content */}
      <div className="flex max-w-[80%] flex-col gap-1">
        <div
          className={cn(
            'rounded-2xl rounded-bl-sm px-4 py-2',
            'bg-muted shadow-sm'
          )}
        >
          {/* Status for screen readers */}
          <StatusIndicator state={annieState} />

          {/* Typing indicator (before first token) */}
          {isThinking && <TypingIndicator />}

          {/* Streaming content */}
          {showContent && (
            <>
              <MessageContent content={content} />
              {/* Blinking cursor while streaming */}
              {isStreaming && <BlinkingCursor />}
            </>
          )}
        </div>

        {/* Cancel button */}
        {showCancelButton && (
          <Button
            variant="ghost"
            size="sm"
            onClick={onCancel}
            className={cn(
              'self-start h-7 px-2 text-xs',
              'text-muted-foreground hover:text-foreground'
            )}
            aria-label="Cancel response"
          >
            <X className="h-3 w-3 mr-1" />
            Cancel
          </Button>
        )}
      </div>
    </div>
  );
});

/**
 * TypingIndicatorMessage - Standalone typing indicator for use in MessageThread
 */
export const TypingIndicatorMessage = memo(function TypingIndicatorMessage({
  className,
}: {
  className?: string;
}) {
  return (
    <div
      className={cn('flex gap-3 px-4', className)}
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
        <TypingIndicator />
      </div>
    </div>
  );
});

export default StreamingMessage;
