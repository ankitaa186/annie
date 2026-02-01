import { memo, useState, useCallback } from 'react';
import { Copy, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { MessageContent } from './MessageContent';
import { FileAttachment } from './FileAttachment';
import type { Message } from '@/types';
import { formatTimestamp } from '@/types';

interface UserMessageProps {
  message: Message;
  className?: string;
}

/**
 * UserMessage - Displays a user message bubble
 *
 * Features:
 * - Right-aligned with distinct blue styling
 * - Shows timestamp on hover
 * - Copy button on hover
 * - File attachments support
 */
export const UserMessage = memo(function UserMessage({
  message,
  className,
}: UserMessageProps) {
  const [isHovered, setIsHovered] = useState(false);
  const [isCopied, setIsCopied] = useState(false);

  const handleMouseEnter = useCallback(() => {
    setIsHovered(true);
  }, []);

  const handleMouseLeave = useCallback(() => {
    setIsHovered(false);
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(message.content);
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy message:', err);
    }
  }, [message.content]);

  return (
    <div
      className={cn('group flex justify-end px-4', className)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      role="listitem"
      aria-label={`Your message sent at ${formatTimestamp(message.timestamp)}`}
    >
      <div className="flex max-w-[80%] flex-col items-end gap-1">
        {/* Message bubble */}
        <div className="relative">
          <div
            className={cn(
              'rounded-2xl rounded-br-sm px-4 py-2',
              'bg-primary text-primary-foreground',
              'shadow-sm'
            )}
          >
            <MessageContent content={message.content} className="text-inherit" />

            {/* File attachments */}
            {message.files && message.files.length > 0 && (
              <div className="mt-2 space-y-2">
                {message.files.map((file, index) => (
                  <FileAttachment
                    key={`${file.filename}-${index}`}
                    file={file}
                    className="bg-primary-foreground/10"
                  />
                ))}
              </div>
            )}
          </div>

          {/* Hover actions */}
          <div
            className={cn(
              'absolute -left-10 top-1/2 -translate-y-1/2',
              'transition-opacity duration-150',
              isHovered ? 'opacity-100' : 'opacity-0'
            )}
          >
            <Button
              variant="ghost"
              size="sm"
              className="h-8 w-8 p-0"
              onClick={handleCopy}
              aria-label={isCopied ? 'Copied!' : 'Copy message'}
            >
              {isCopied ? (
                <Check className="h-4 w-4 text-green-500" />
              ) : (
                <Copy className="h-4 w-4" />
              )}
            </Button>
          </div>
        </div>

        {/* Timestamp on hover */}
        <div
          className={cn(
            'text-xs text-muted-foreground transition-opacity duration-150',
            isHovered ? 'opacity-100' : 'opacity-0'
          )}
        >
          {formatTimestamp(message.timestamp)}
        </div>
      </div>
    </div>
  );
});

export default UserMessage;
