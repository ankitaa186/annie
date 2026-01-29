/**
 * ToolCallCard component - Displays active tool calls during Annie's response
 *
 * Features:
 * - User-friendly tool name mapping
 * - Animated spinner while running
 * - Success/error indicator on completion
 * - Expandable parameters view
 * - Smooth transitions
 *
 * Story 20.8: Thinking & Tool Call Display
 */

import { memo, useState } from 'react';
import {
  Search,
  Brain,
  TrendingUp,
  Home,
  Globe,
  MessageSquare,
  Volume2,
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
  XCircle,
  Wrench,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import type { ActiveToolCall } from '@/lib/stores/appStore';

interface ToolCallCardProps {
  /** Tool call information */
  tool: ActiveToolCall;
  /** Additional CSS classes */
  className?: string;
}

/** Tool display configuration */
interface ToolConfig {
  icon: LucideIcon;
  label: string;
  description: string;
  color: string;
}

/** Map tool names to friendly display */
const TOOL_CONFIGS: Record<string, ToolConfig> = {
  web_search: {
    icon: Search,
    label: 'Searching the web',
    description: 'Finding relevant information online',
    color: 'text-blue-500',
  },
  retrieve_memories: {
    icon: Brain,
    label: 'Remembering',
    description: 'Searching through memories',
    color: 'text-purple-500',
  },
  store_memory: {
    icon: Brain,
    label: 'Storing memory',
    description: 'Saving important information',
    color: 'text-purple-500',
  },
  get_stock_data: {
    icon: TrendingUp,
    label: 'Checking stocks',
    description: 'Fetching market data',
    color: 'text-green-500',
  },
  get_portfolio_summary: {
    icon: TrendingUp,
    label: 'Checking portfolio',
    description: 'Analyzing investment holdings',
    color: 'text-green-500',
  },
  home_assistant_query: {
    icon: Home,
    label: 'Checking smart home',
    description: 'Querying device states',
    color: 'text-orange-500',
  },
  home_assistant_control: {
    icon: Home,
    label: 'Controlling smart home',
    description: 'Adjusting devices',
    color: 'text-orange-500',
  },
  send_voice_message_to_smart_home: {
    icon: Volume2,
    label: 'Sending voice message',
    description: 'Speaking through smart speaker',
    color: 'text-orange-500',
  },
  web_crawl: {
    icon: Globe,
    label: 'Reading webpage',
    description: 'Extracting page content',
    color: 'text-blue-500',
  },
  reddit_search: {
    icon: MessageSquare,
    label: 'Searching Reddit',
    description: 'Finding community discussions',
    color: 'text-orange-600',
  },
  update_user_profile: {
    icon: Brain,
    label: 'Updating profile',
    description: 'Saving user preferences',
    color: 'text-purple-500',
  },
};

/** Default config for unknown tools */
const DEFAULT_TOOL_CONFIG: ToolConfig = {
  icon: Wrench,
  label: 'Working on it',
  description: 'Processing request',
  color: 'text-muted-foreground',
};

/**
 * Get tool configuration, with fallback to default
 */
function getToolConfig(toolName: string): ToolConfig {
  return TOOL_CONFIGS[toolName] || {
    ...DEFAULT_TOOL_CONFIG,
    label: `Using ${toolName.replace(/_/g, ' ')}`,
  };
}

/**
 * Format tool arguments for display
 */
function formatArgs(args: Record<string, unknown>): string {
  return JSON.stringify(args, null, 2);
}

/**
 * Format tool result for display
 */
function formatResult(result: unknown): string {
  if (typeof result === 'string') {
    return result.length > 100 ? result.slice(0, 100) + '...' : result;
  }
  return 'Completed';
}

/**
 * ToolCallCard - Displays a tool call with status
 */
export const ToolCallCard = memo(function ToolCallCard({
  tool,
  className,
}: ToolCallCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const config = getToolConfig(tool.name);
  const Icon = config.icon;

  const isRunning = tool.status === 'running' || tool.status === 'pending';
  const isCompleted = tool.status === 'completed';
  const isError = tool.status === 'error';

  return (
    <div
      className={cn(
        'rounded-lg border bg-muted/50 p-3 transition-all duration-200',
        isRunning && 'border-primary/50 bg-primary/5',
        isCompleted && 'border-green-500/30 bg-green-500/5',
        isError && 'border-destructive/30 bg-destructive/5',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center gap-3">
        {/* Status icon */}
        <div
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-full',
            'bg-background shadow-sm'
          )}
        >
          {isRunning ? (
            <Loader2 className={cn('h-4 w-4 animate-spin', config.color)} />
          ) : isCompleted ? (
            <CheckCircle2 className="h-4 w-4 text-green-500" />
          ) : isError ? (
            <XCircle className="h-4 w-4 text-destructive" />
          ) : (
            <Icon className={cn('h-4 w-4', config.color)} />
          )}
        </div>

        {/* Tool info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium">
            {config.label}
            {isRunning && '...'}
          </p>
          <p className="text-xs text-muted-foreground truncate">
            {config.description}
          </p>
        </div>

        {/* Expand button (only if has args) */}
        {Object.keys(tool.args).length > 0 && (
          <Button
            variant="ghost"
            size="sm"
            className="h-6 w-6 p-0"
            onClick={() => setIsExpanded(!isExpanded)}
            aria-label={isExpanded ? 'Hide details' : 'Show details'}
            aria-expanded={isExpanded}
          >
            {isExpanded ? (
              <ChevronDown className="h-4 w-4" />
            ) : (
              <ChevronRight className="h-4 w-4" />
            )}
          </Button>
        )}
      </div>

      {/* Expanded args view */}
      {isExpanded && Object.keys(tool.args).length > 0 && (
        <div className="mt-3 rounded-md bg-background p-2 overflow-x-auto">
          <pre className="text-xs text-muted-foreground whitespace-pre-wrap break-all">
            {formatArgs(tool.args)}
          </pre>
        </div>
      )}

      {/* Result summary (if completed with result) */}
      {isCompleted && tool.result !== undefined && (
        <div className="mt-2 text-xs text-muted-foreground">
          <span className="font-medium">Result: </span>
          <span>{formatResult(tool.result)}</span>
        </div>
      )}
    </div>
  );
});

export default ToolCallCard;
