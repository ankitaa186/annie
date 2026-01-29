/**
 * ConversationList - Displays grouped conversation history in sidebar
 *
 * Features:
 * - Groups conversations by date (Today, Yesterday, Previous 7 Days, Older)
 * - Loading skeleton during fetch
 * - Empty state for new users
 * - Integrates with ConversationItem for individual entries
 */

import { useMemo, useState } from 'react';
import { startOfDay, subDays, isAfter, isEqual } from 'date-fns';
import { MessageSquare, AlertCircle } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';
import { ConversationItem } from './ConversationItem';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { cn } from '@/lib/utils';
import type { Conversation, GroupedConversations } from '@/types';

interface ConversationListProps {
  conversations: Conversation[];
  activeConversationId: string | null;
  isLoading: boolean;
  error: string | null;
  isCollapsed: boolean;
  onSelect: (id: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onDelete: (id: string) => void;
}

/**
 * Group conversations by date categories
 */
function groupConversationsByDate(conversations: Conversation[]): GroupedConversations {
  const now = new Date();
  const today = startOfDay(now);
  const yesterday = startOfDay(subDays(now, 1));
  const weekAgo = startOfDay(subDays(now, 7));

  const groups: GroupedConversations = {
    today: [],
    yesterday: [],
    previousWeek: [],
    older: [],
  };

  // Sort conversations by updatedAt descending first
  const sorted = [...conversations].sort(
    (a, b) => new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
  );

  for (const conv of sorted) {
    const convDate = startOfDay(new Date(conv.updatedAt));

    if (isEqual(convDate, today) || isAfter(convDate, today)) {
      groups.today.push(conv);
    } else if (isEqual(convDate, yesterday)) {
      groups.yesterday.push(conv);
    } else if (isAfter(convDate, weekAgo) || isEqual(convDate, weekAgo)) {
      groups.previousWeek.push(conv);
    } else {
      groups.older.push(conv);
    }
  }

  return groups;
}

/**
 * Loading skeleton component
 */
function ConversationSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="space-y-2 p-2">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="space-y-2 p-3">
          <div className="flex items-start justify-between gap-2">
            <Skeleton className="h-4 w-32" />
            <Skeleton className="h-3 w-12" />
          </div>
          <Skeleton className="h-3 w-48" />
        </div>
      ))}
    </div>
  );
}

/**
 * Empty state component
 */
function EmptyState({ isCollapsed }: { isCollapsed: boolean }) {
  if (isCollapsed) {
    return (
      <div className="flex flex-col items-center py-4">
        <MessageSquare className="h-5 w-5 text-muted-foreground opacity-50" />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <MessageSquare
        className="h-12 w-12 text-muted-foreground opacity-50 mb-3"
        aria-hidden="true"
      />
      <p className="text-sm font-medium text-muted-foreground">No conversations yet</p>
      <p className="text-xs text-muted-foreground mt-1">
        Start a new chat to begin
      </p>
    </div>
  );
}

/**
 * Error state component
 */
function ErrorState({ error, isCollapsed }: { error: string; isCollapsed: boolean }) {
  if (isCollapsed) {
    return (
      <div className="flex flex-col items-center py-4">
        <AlertCircle className="h-5 w-5 text-destructive opacity-70" />
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <AlertCircle
        className="h-10 w-10 text-destructive opacity-70 mb-3"
        aria-hidden="true"
      />
      <p className="text-sm font-medium text-destructive">Failed to load conversations</p>
      <p className="text-xs text-muted-foreground mt-1">{error}</p>
    </div>
  );
}

/**
 * Conversation group section header
 */
function GroupHeader({ title, isCollapsed }: { title: string; isCollapsed: boolean }) {
  if (isCollapsed) return null;

  return (
    <div className="px-3 py-2">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        {title}
      </h3>
    </div>
  );
}

export function ConversationList({
  conversations,
  activeConversationId,
  isLoading,
  error,
  isCollapsed,
  onSelect,
  onRename,
  onDelete,
}: ConversationListProps) {
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);

  // Group conversations by date
  const grouped = useMemo(
    () => groupConversationsByDate(conversations),
    [conversations]
  );

  // Handle delete confirmation
  const handleDeleteRequest = (id: string) => {
    const conversation = conversations.find((c) => c.id === id);
    if (conversation) {
      setDeleteTarget(conversation);
    }
  };

  const handleDeleteConfirm = () => {
    if (deleteTarget) {
      onDelete(deleteTarget.id);
      setDeleteTarget(null);
    }
  };

  const handleDeleteCancel = () => {
    setDeleteTarget(null);
  };

  // Show loading state
  if (isLoading) {
    return <ConversationSkeleton count={isCollapsed ? 5 : 3} />;
  }

  // Show error state
  if (error) {
    return <ErrorState error={error} isCollapsed={isCollapsed} />;
  }

  // Show empty state
  if (conversations.length === 0) {
    return <EmptyState isCollapsed={isCollapsed} />;
  }

  // Render a group of conversations
  const renderGroup = (title: string, items: Conversation[]) => {
    if (items.length === 0) return null;

    return (
      <div key={title} className="space-y-1">
        <GroupHeader title={title} isCollapsed={isCollapsed} />
        <div className={cn('space-y-1', isCollapsed && 'flex flex-col items-center')}>
          {items.map((conversation) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              isActive={conversation.id === activeConversationId}
              isCollapsed={isCollapsed}
              onSelect={onSelect}
              onRename={onRename}
              onDelete={handleDeleteRequest}
            />
          ))}
        </div>
      </div>
    );
  };

  return (
    <>
      <div className="space-y-4 py-2">
        {renderGroup('Today', grouped.today)}
        {renderGroup('Yesterday', grouped.yesterday)}
        {renderGroup('Previous 7 Days', grouped.previousWeek)}
        {renderGroup('Older', grouped.older)}
      </div>

      {/* Delete Confirmation Dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && handleDeleteCancel()}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete conversation?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete "{deleteTarget?.title}". This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteConfirm}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

export default ConversationList;
