/**
 * ConversationItem - Individual conversation entry in the sidebar list
 *
 * Features:
 * - Displays title, timestamp, and message preview
 * - Active state highlighting
 * - Click to select conversation
 * - Double-click to rename (inline edit)
 * - Context menu for delete/rename actions
 * - Keyboard accessible
 */

import { useState, useRef, useEffect, useCallback } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Input } from '@/components/ui/input';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Button } from '@/components/ui/button';
import type { Conversation } from '@/types';

interface ConversationItemProps {
  conversation: Conversation;
  isActive: boolean;
  isCollapsed: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onDelete: (id: string) => void;
}

/**
 * Format timestamp to relative time (e.g., "2 hours ago")
 */
function formatTimestamp(isoString: string): string {
  try {
    return formatDistanceToNow(new Date(isoString), { addSuffix: true });
  } catch {
    return '';
  }
}

/**
 * Truncate text with ellipsis
 */
function truncateText(text: string | null | undefined, maxLength: number): string {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength).trim() + '...';
}

export function ConversationItem({
  conversation,
  isActive,
  isCollapsed,
  onSelect,
  onRename,
  onDelete,
}: ConversationItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState(conversation.title);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const itemRef = useRef<HTMLDivElement>(null);

  // Focus input when entering edit mode
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  // Reset edit title when conversation changes
  useEffect(() => {
    setEditTitle(conversation.title);
  }, [conversation.title]);

  /**
   * Handle click to select conversation
   */
  const handleClick = useCallback(() => {
    if (!isEditing) {
      onSelect(conversation.id);
    }
  }, [isEditing, onSelect, conversation.id]);

  /**
   * Handle double-click to enter edit mode
   */
  const handleDoubleClick = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsEditing(true);
  }, []);

  /**
   * Handle keyboard navigation
   */
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' && !isEditing) {
        onSelect(conversation.id);
      } else if (e.key === 'F2' || (e.key === 'r' && e.ctrlKey)) {
        e.preventDefault();
        setIsEditing(true);
      } else if (e.key === 'Delete') {
        e.preventDefault();
        onDelete(conversation.id);
      }
    },
    [isEditing, onSelect, onDelete, conversation.id]
  );

  /**
   * Save the edited title
   */
  const handleSave = useCallback(() => {
    const trimmedTitle = editTitle.trim();
    if (trimmedTitle && trimmedTitle !== conversation.title) {
      onRename(conversation.id, trimmedTitle);
    } else {
      setEditTitle(conversation.title);
    }
    setIsEditing(false);
  }, [editTitle, conversation.id, conversation.title, onRename]);

  /**
   * Cancel editing
   */
  const handleCancel = useCallback(() => {
    setEditTitle(conversation.title);
    setIsEditing(false);
  }, [conversation.title]);

  /**
   * Handle input key events
   */
  const handleInputKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        handleSave();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        handleCancel();
      }
    },
    [handleSave, handleCancel]
  );

  /**
   * Handle context menu actions
   */
  const handleRenameClick = useCallback(() => {
    setIsMenuOpen(false);
    // Small delay to allow menu to close
    setTimeout(() => setIsEditing(true), 100);
  }, []);

  const handleDeleteClick = useCallback(() => {
    setIsMenuOpen(false);
    onDelete(conversation.id);
  }, [onDelete, conversation.id]);

  // For collapsed sidebar, show only icon
  if (isCollapsed) {
    return (
      <div
        ref={itemRef}
        role="button"
        tabIndex={0}
        onClick={handleClick}
        onKeyDown={handleKeyDown}
        className={cn(
          'flex h-10 w-10 items-center justify-center rounded-lg cursor-pointer transition-colors',
          isActive
            ? 'bg-accent text-accent-foreground'
            : 'hover:bg-accent/50 text-muted-foreground hover:text-foreground'
        )}
        aria-label={`Conversation: ${conversation.title}`}
        aria-current={isActive ? 'true' : undefined}
      >
        <div className="h-2 w-2 rounded-full bg-current opacity-60" />
      </div>
    );
  }

  return (
    <div
      ref={itemRef}
      role="button"
      tabIndex={0}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onKeyDown={handleKeyDown}
      className={cn(
        'group relative rounded-lg cursor-pointer transition-colors p-3',
        isActive
          ? 'bg-accent text-accent-foreground'
          : 'hover:bg-accent/50 text-foreground',
        isEditing && 'bg-accent'
      )}
      aria-label={`Conversation: ${conversation.title}`}
      aria-current={isActive ? 'true' : undefined}
    >
      {/* Title Row */}
      <div className="flex items-start justify-between gap-2">
        {isEditing ? (
          <Input
            ref={inputRef}
            value={editTitle}
            onChange={(e) => setEditTitle(e.target.value)}
            onBlur={handleSave}
            onKeyDown={handleInputKeyDown}
            className="h-7 px-2 py-1 text-sm font-medium"
            aria-label="Edit conversation title"
          />
        ) : (
          <>
            <span className="font-medium text-sm truncate flex-1">
              {truncateText(conversation.title, 25)}
            </span>
            <span className="text-xs text-muted-foreground whitespace-nowrap">
              {formatTimestamp(conversation.updatedAt)}
            </span>
          </>
        )}
      </div>

      {/* Preview Row */}
      {!isEditing && conversation.lastMessagePreview && (
        <p className="mt-1 text-xs text-muted-foreground truncate">
          {truncateText(conversation.lastMessagePreview, 60)}
        </p>
      )}

      {/* Message count indicator (optional) */}
      {!isEditing && conversation.messageCount > 0 && (
        <p className="mt-1 text-xs text-muted-foreground opacity-60">
          {conversation.messageCount} message{conversation.messageCount !== 1 ? 's' : ''}
        </p>
      )}

      {/* Context Menu Button - appears on hover */}
      {!isEditing && (
        <DropdownMenu open={isMenuOpen} onOpenChange={setIsMenuOpen}>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className={cn(
                'absolute right-1 top-1 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity',
                isMenuOpen && 'opacity-100'
              )}
              onClick={(e) => e.stopPropagation()}
              aria-label="Conversation options"
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-40">
            <DropdownMenuItem onClick={handleRenameClick}>
              <Pencil className="mr-2 h-4 w-4" />
              Rename
            </DropdownMenuItem>
            <DropdownMenuItem
              onClick={handleDeleteClick}
              className="text-destructive focus:text-destructive"
            >
              <Trash2 className="mr-2 h-4 w-4" />
              Delete
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </div>
  );
}

export default ConversationItem;
