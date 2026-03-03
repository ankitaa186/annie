import { Sparkles } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { ComponentStatus } from '@/lib/hooks/useHealth';
import {
  MODEL_DISPLAY_NAMES as LLM_DISPLAY_NAMES,
  getLLMDisplayName,
} from '@/lib/constants/llm';

// Re-export for backward compatibility
export { LLM_DISPLAY_NAMES, getLLMDisplayName };

/**
 * Status color for LLM indicator dot
 */
const STATUS_COLORS: Record<ComponentStatus | 'unknown', string> = {
  ok: 'bg-green-500',
  degraded: 'bg-yellow-500',
  unavailable: 'bg-red-500',
  unknown: 'bg-gray-400',
};

/**
 * Props for LLMIndicator component
 */
interface LLMIndicatorProps {
  /** Active LLM provider ID (e.g., 'gemini-3.1-pro-preview') */
  activeLLM: string | null;
  /** LLM API health status */
  llmStatus: ComponentStatus;
  /** Whether health data is still loading */
  loading?: boolean;
  /** Optional className for container */
  className?: string;
}

/**
 * Loading skeleton for LLM indicator
 */
function LLMIndicatorSkeleton() {
  return (
    <div
      className="flex items-center gap-1.5 rounded-md bg-muted px-2 py-1"
      role="status"
      aria-label="Loading LLM indicator"
    >
      <div className="h-2 w-2 rounded-full bg-muted-foreground/30 animate-pulse" />
      <div className="h-3 w-16 rounded bg-muted-foreground/30 animate-pulse" />
    </div>
  );
}

/**
 * LLMIndicator displays the active LLM provider with status
 *
 * Features:
 * - Shows friendly provider name (e.g., "Gemini 3 Pro" instead of "gemini-3.1-pro-preview")
 * - Status dot indicates LLM API health
 * - Tooltip shows full provider details
 * - Loading skeleton during initial fetch
 * - Smooth transitions on status changes
 *
 * @example
 * ```tsx
 * <LLMIndicator
 *   activeLLM="gemini-3.1-pro-preview"
 *   llmStatus="ok"
 * />
 * ```
 */
export function LLMIndicator({
  activeLLM,
  llmStatus,
  loading = false,
  className,
}: LLMIndicatorProps) {
  // Show skeleton during initial load
  if (loading) {
    return <LLMIndicatorSkeleton />;
  }

  const displayName = getLLMDisplayName(activeLLM);
  const statusColor = STATUS_COLORS[llmStatus] || STATUS_COLORS.unknown;

  const statusText =
    llmStatus === 'ok'
      ? 'Connected'
      : llmStatus === 'degraded'
        ? 'Degraded'
        : llmStatus === 'unavailable'
          ? 'Unavailable'
          : 'Unknown';

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className={cn(
            'flex items-center gap-1.5 rounded-md bg-muted px-2 py-1 text-sm text-muted-foreground transition-colors duration-300',
            className
          )}
          role="status"
          aria-label={`Active LLM: ${displayName}, Status: ${statusText}`}
        >
          {/* Status dot */}
          <span
            className={cn(
              'h-2 w-2 rounded-full transition-colors duration-300',
              statusColor
            )}
            aria-hidden="true"
          />
          {/* Provider name */}
          <span className="font-medium">{displayName}</span>
          {/* Sparkles icon for AI indicator */}
          <Sparkles className="h-3 w-3 opacity-60" aria-hidden="true" />
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-primary" aria-hidden="true" />
            <span className="font-medium">Active AI Provider</span>
          </div>
          <div className="text-xs space-y-1">
            <div>
              <span className="opacity-70">Model: </span>
              <span>{displayName}</span>
            </div>
            {activeLLM && activeLLM !== displayName && (
              <div>
                <span className="opacity-70">ID: </span>
                <span className="font-mono text-[10px]">{activeLLM}</span>
              </div>
            )}
            <div className="flex items-center gap-1.5">
              <span className="opacity-70">Status: </span>
              <span
                className={cn('h-1.5 w-1.5 rounded-full', statusColor)}
                aria-hidden="true"
              />
              <span>{statusText}</span>
            </div>
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

export default LLMIndicator;
