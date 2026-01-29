/**
 * InputArea component - Chat message input with file upload
 *
 * Features:
 * - Auto-expanding textarea (max 6 lines, then scroll)
 * - Send button (disabled when empty)
 * - Enter to send, Shift+Enter for newline
 * - File upload with drag-and-drop
 * - File preview before sending
 * - Clipboard paste for images
 * - Character count indicator
 * - Loading state during send
 */

import {
  useRef,
  useState,
  useCallback,
  useEffect,
  type ChangeEvent,
  type KeyboardEvent,
  type DragEvent,
  type ClipboardEvent,
} from 'react';
import { Send, Paperclip, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { FilePreview } from './FilePreview';
import { useToast } from '@/lib/hooks/useToast';
import {
  validateFiles,
  getAcceptAttribute,
  isImageFile,
  MAX_FILES_PER_MESSAGE,
  CHAR_COUNT_VISIBLE_THRESHOLD,
  CHAR_COUNT_WARNING_THRESHOLD,
  CHAR_COUNT_MAX_THRESHOLD,
} from '@/lib/utils/fileValidation';

interface InputAreaProps {
  onSend: (message: string, files?: File[]) => Promise<unknown>;
  disabled?: boolean;
  placeholder?: string;
}

/** Line height for textarea calculations */
const LINE_HEIGHT = 24; // px
const MAX_LINES = 6;
const MAX_HEIGHT = LINE_HEIGHT * MAX_LINES;

/**
 * InputArea - Main chat input component
 */
export function InputArea({
  onSend,
  disabled = false,
  placeholder = 'Type a message...',
}: InputAreaProps) {
  const [message, setMessage] = useState('');
  const [files, setFiles] = useState<File[]>([]);
  const [isSending, setIsSending] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const dragCountRef = useRef(0);
  const messageRef = useRef(''); // Track current message synchronously

  const { error: showError } = useToast();

  // Determine if input should be disabled
  const isDisabled = disabled || isSending;
  const hasContent = message.trim().length > 0 || files.length > 0;
  const canSend = hasContent && !isDisabled;

  // Character count state
  const charCount = message.length;
  const showCharCount = charCount >= CHAR_COUNT_VISIBLE_THRESHOLD;
  const isWarning = charCount >= CHAR_COUNT_WARNING_THRESHOLD;
  const isOverLimit = charCount >= CHAR_COUNT_MAX_THRESHOLD;

  /**
   * Adjust textarea height based on content
   */
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    // Reset height to auto to get actual scroll height
    textarea.style.height = 'auto';

    // Calculate new height (capped at max)
    const newHeight = Math.min(textarea.scrollHeight, MAX_HEIGHT);
    textarea.style.height = `${newHeight}px`;

    // Show scrollbar if content exceeds max height
    textarea.style.overflowY = textarea.scrollHeight > MAX_HEIGHT ? 'auto' : 'hidden';
  }, []);

  // Adjust height when message changes
  useEffect(() => {
    adjustHeight();
  }, [message, adjustHeight]);

  /**
   * Handle message input change
   */
  const handleMessageChange = useCallback((e: ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value;
    messageRef.current = value; // Update ref synchronously
    setMessage(value);
  }, []);

  /**
   * Add validated files to the list
   */
  const addFiles = useCallback(
    (newFiles: File[]) => {
      const { valid, errors } = validateFiles(newFiles, files.length);

      // Show errors
      errors.forEach((err) => showError(err));

      // Add valid files
      if (valid.length > 0) {
        setFiles((prev) => [...prev, ...valid]);
      }
    },
    [files.length, showError]
  );

  /**
   * Remove a file by index
   */
  const removeFile = useCallback((index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /**
   * Handle file input change
   */
  const handleFileInputChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (fileList && fileList.length > 0) {
        addFiles(Array.from(fileList));
      }
      // Reset input to allow selecting the same file again
      e.target.value = '';
    },
    [addFiles]
  );

  /**
   * Open file picker
   */
  const openFilePicker = useCallback(() => {
    if (!isDisabled) {
      fileInputRef.current?.click();
    }
  }, [isDisabled]);

  /**
   * Handle send
   */
  const handleSend = useCallback(async () => {
    // Read from ref for the most up-to-date value (avoids stale closure issues)
    const currentMessage = messageRef.current.trim();
    const hasContent = currentMessage.length > 0 || files.length > 0;

    if (!hasContent || isDisabled || isOverLimit) return;

    const messageToSend = currentMessage;
    const filesToSend = [...files];

    // Clear input immediately for responsive feel
    messageRef.current = '';
    setMessage('');
    setFiles([]);
    setIsSending(true);

    try {
      await onSend(messageToSend, filesToSend);
    } catch (err) {
      // Restore message on error
      messageRef.current = messageToSend;
      setMessage(messageToSend);
      setFiles(filesToSend);
      const errorMessage = err instanceof Error ? err.message : 'Failed to send message';
      showError(errorMessage);
    } finally {
      setIsSending(false);
      // Focus textarea after send
      textareaRef.current?.focus();
    }
  }, [files, isDisabled, isOverLimit, onSend, showError]);

  /**
   * Handle keyboard events (Enter to send, Shift+Enter for newline)
   */
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        // handleSend checks the ref directly for the current message
        handleSend();
      }
    },
    [handleSend]
  );

  /**
   * Handle drag events
   */
  const handleDragEnter = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCountRef.current++;
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragCountRef.current--;
    if (dragCountRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e: DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      e.stopPropagation();
      dragCountRef.current = 0;
      setIsDragging(false);

      if (isDisabled) return;

      const droppedFiles = Array.from(e.dataTransfer.files);
      if (droppedFiles.length > 0) {
        addFiles(droppedFiles);
      }
    },
    [isDisabled, addFiles]
  );

  /**
   * Handle paste events (for images from clipboard)
   */
  const handlePaste = useCallback(
    (e: ClipboardEvent<HTMLTextAreaElement>) => {
      const items = e.clipboardData?.items;
      if (!items) return;

      const imageFiles: File[] = [];

      for (const item of items) {
        if (item.kind === 'file' && isImageFile(item.getAsFile()!)) {
          const file = item.getAsFile();
          if (file) {
            // Create a new file with a better name
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const extension = file.type.split('/')[1] || 'png';
            const namedFile = new File(
              [file],
              `pasted-image-${timestamp}.${extension}`,
              { type: file.type }
            );
            imageFiles.push(namedFile);
          }
        }
      }

      if (imageFiles.length > 0) {
        e.preventDefault(); // Prevent pasting image as text
        addFiles(imageFiles);
      }
    },
    [addFiles]
  );

  return (
    <div
      className={cn(
        'relative border-t border-border bg-background',
        isDragging && 'ring-2 ring-primary ring-inset'
      )}
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {/* Drag overlay */}
      {isDragging && (
        <div
          className={cn(
            'absolute inset-0 z-10',
            'flex items-center justify-center',
            'bg-primary/10 border-2 border-dashed border-primary',
            'pointer-events-none'
          )}
        >
          <p className="text-sm font-medium text-primary">Drop files here</p>
        </div>
      )}

      {/* File previews */}
      <FilePreview files={files} onRemove={removeFile} disabled={isDisabled} />

      {/* Input row */}
      <div className="flex items-end gap-2 p-3">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          className="hidden"
          multiple
          accept={getAcceptAttribute()}
          onChange={handleFileInputChange}
          disabled={isDisabled}
          aria-label="Upload files"
        />

        {/* File upload button */}
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={openFilePicker}
          disabled={isDisabled || files.length >= MAX_FILES_PER_MESSAGE}
          className="flex-shrink-0 h-10 w-10"
          aria-label="Attach files"
          title={
            files.length >= MAX_FILES_PER_MESSAGE
              ? `Maximum ${MAX_FILES_PER_MESSAGE} files`
              : 'Attach files'
          }
        >
          <Paperclip className="h-5 w-5" />
        </Button>

        {/* Textarea container */}
        <div className="relative flex-1">
          <textarea
            ref={textareaRef}
            value={message}
            onChange={handleMessageChange}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={isDisabled}
            placeholder={placeholder}
            rows={1}
            className={cn(
              'w-full resize-none rounded-lg border border-input bg-background px-3 py-2.5',
              'text-sm leading-6 placeholder:text-muted-foreground',
              'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2',
              'disabled:cursor-not-allowed disabled:opacity-50',
              isOverLimit && 'border-destructive focus:ring-destructive'
            )}
            style={{
              minHeight: `${LINE_HEIGHT + 20}px`, // Single line + padding
              maxHeight: `${MAX_HEIGHT}px`,
            }}
            aria-label="Message input"
            aria-describedby={showCharCount ? 'char-count' : undefined}
          />

          {/* Character count */}
          {showCharCount && (
            <div
              id="char-count"
              className={cn(
                'absolute right-2 bottom-1 text-xs',
                isOverLimit
                  ? 'text-destructive font-medium'
                  : isWarning
                    ? 'text-amber-500'
                    : 'text-muted-foreground'
              )}
              aria-live="polite"
            >
              {charCount.toLocaleString()}
              {isOverLimit && ` / ${CHAR_COUNT_MAX_THRESHOLD.toLocaleString()}`}
            </div>
          )}
        </div>

        {/* Send button */}
        <Button
          type="button"
          size="icon"
          onClick={handleSend}
          disabled={!canSend || isOverLimit}
          className="flex-shrink-0 h-10 w-10"
          aria-label={isSending ? 'Sending...' : 'Send message'}
        >
          {isSending ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Send className="h-5 w-5" />
          )}
        </Button>
      </div>

      {/* Over limit warning */}
      {isOverLimit && (
        <p className="px-3 pb-2 text-xs text-destructive">
          Message is too long. Maximum {CHAR_COUNT_MAX_THRESHOLD.toLocaleString()} characters.
        </p>
      )}
    </div>
  );
}

export default InputArea;
