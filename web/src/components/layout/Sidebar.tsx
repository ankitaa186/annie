import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Brain, Wrench } from 'lucide-react';
import { useSidebarCollapsed, useAppStore, useActiveConversationId } from '@/lib/stores/appStore';
import { useIsMobile, usePrefersReducedMotion } from '@/hooks/useMediaQuery';
import { useConversations } from '@/lib/hooks/useConversations';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { ConversationList } from '@/components/conversations';
import { cn } from '@/lib/utils';

/**
 * Sidebar component with conversation list and navigation links
 *
 * Sections:
 * - New Conversation button
 * - Conversation list (Story 20.4)
 * - Memory Browser link (V2 - disabled)
 * - Tools link (V3 - disabled)
 */
export function Sidebar() {
  const navigate = useNavigate();
  const isMobile = useIsMobile();
  const isCollapsed = useSidebarCollapsed();
  const prefersReducedMotion = usePrefersReducedMotion();
  const activeConversationId = useActiveConversationId();
  const setActiveConversation = useAppStore((state) => state.setActiveConversation);
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);

  // Use conversations hook for data management
  const {
    conversations,
    isLoading,
    error,
    createConversation,
    deleteConversation,
    renameConversation,
  } = useConversations();

  // Show full content on mobile (overlay) or desktop, collapsed on tablet
  const showFullContent = isMobile || !isCollapsed;

  const transitionClasses = prefersReducedMotion
    ? ''
    : 'transition-all duration-200';

  /**
   * Handle creating a new conversation
   */
  const handleNewChat = useCallback(async () => {
    try {
      const newConversation = await createConversation();
      setActiveConversation(newConversation.id);

      // Close sidebar on mobile after creating conversation
      if (isMobile) {
        setSidebarOpen(false);
      }
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }
  }, [createConversation, setActiveConversation, isMobile, setSidebarOpen]);

  /**
   * Handle selecting a conversation
   */
  const handleSelectConversation = useCallback(
    (id: string) => {
      // Navigate to the conversation URL
      navigate(`/chat/${id}`);
      setActiveConversation(id);

      // Close sidebar on mobile after selecting conversation
      if (isMobile) {
        setSidebarOpen(false);
      }
    },
    [navigate, setActiveConversation, isMobile, setSidebarOpen]
  );

  /**
   * Handle renaming a conversation
   */
  const handleRenameConversation = useCallback(
    (id: string, newTitle: string) => {
      renameConversation(id, newTitle);
    },
    [renameConversation]
  );

  /**
   * Handle deleting a conversation
   */
  const handleDeleteConversation = useCallback(
    (id: string) => {
      deleteConversation(id);
    },
    [deleteConversation]
  );

  return (
    <TooltipProvider delayDuration={0}>
      <nav
        id="sidebar-navigation"
        className="flex h-full flex-col"
        aria-label="Main navigation"
      >
        {/* New Conversation Button */}
        <div className={cn('p-3', !showFullContent && 'flex justify-center')}>
          {showFullContent ? (
            <Button
              className={cn(
                'w-full justify-start gap-2',
                transitionClasses
              )}
              onClick={handleNewChat}
              aria-label="Start a new conversation"
            >
              <Plus className="h-4 w-4" aria-hidden="true" />
              <span>New Chat</span>
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  size="icon"
                  className={cn('h-10 w-10', transitionClasses)}
                  onClick={handleNewChat}
                  aria-label="Start a new conversation"
                >
                  <Plus className="h-5 w-5" aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p>New Chat</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>

        {/* Conversation List Area (Story 20.4) */}
        <ScrollArea className="flex-1 px-3">
          <ConversationList
            conversations={conversations}
            activeConversationId={activeConversationId}
            isLoading={isLoading}
            error={error}
            isCollapsed={!showFullContent}
            onSelect={handleSelectConversation}
            onRename={handleRenameConversation}
            onDelete={handleDeleteConversation}
          />
        </ScrollArea>

        {/* Separator */}
        <div
          className={cn(
            'mx-3 border-t border-border',
            !showFullContent && 'mx-2'
          )}
        />

        {/* Navigation Links */}
        <div
          className={cn(
            'space-y-1 p-3',
            !showFullContent && 'flex flex-col items-center'
          )}
        >
          {/* Memory Browser - V2 (disabled) */}
          {showFullContent ? (
            <Button
              variant="ghost"
              className={cn(
                'w-full justify-start gap-2 text-muted-foreground',
                transitionClasses
              )}
              disabled
              aria-label="Memory Browser - Coming in version 2"
            >
              <Brain className="h-4 w-4" aria-hidden="true" />
              <span>Memory</span>
              <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                V2
              </span>
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-10 w-10 text-muted-foreground"
                  disabled
                  aria-label="Memory Browser - Coming in version 2"
                >
                  <Brain className="h-5 w-5" aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p>Memory (V2)</p>
              </TooltipContent>
            </Tooltip>
          )}

          {/* Tools - V3 (disabled) */}
          {showFullContent ? (
            <Button
              variant="ghost"
              className={cn(
                'w-full justify-start gap-2 text-muted-foreground',
                transitionClasses
              )}
              disabled
              aria-label="Tools - Coming in version 3"
            >
              <Wrench className="h-4 w-4" aria-hidden="true" />
              <span>Tools</span>
              <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-medium">
                V3
              </span>
            </Button>
          ) : (
            <Tooltip>
              <TooltipTrigger asChild>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-10 w-10 text-muted-foreground"
                  disabled
                  aria-label="Tools - Coming in version 3"
                >
                  <Wrench className="h-5 w-5" aria-hidden="true" />
                </Button>
              </TooltipTrigger>
              <TooltipContent side="right">
                <p>Tools (V3)</p>
              </TooltipContent>
            </Tooltip>
          )}
        </div>
      </nav>
    </TooltipProvider>
  );
}

export default Sidebar;
