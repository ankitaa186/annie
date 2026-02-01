import { AlertCircle, Loader2 } from 'lucide-react';
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';
import type { ComponentStatus, HealthState, UseHealthReturn } from '@/lib/hooks/useHealth';

/**
 * Service configuration for health indicator dots
 */
interface ServiceConfig {
  key: keyof HealthState;
  label: string;
  description: string;
}

/**
 * Services to display in health indicator
 */
const SERVICES: ServiceConfig[] = [
  { key: 'backend', label: 'Backend API', description: 'Core API service' },
  { key: 'mcp', label: 'MCP Server', description: 'Tool execution service' },
  { key: 'redis', label: 'Redis', description: 'State and caching' },
  { key: 'memories', label: 'Memories', description: 'Conversation memory service' },
];

/**
 * Color classes for each status
 */
const STATUS_COLORS: Record<ComponentStatus | 'unknown', string> = {
  ok: 'bg-green-500',
  degraded: 'bg-yellow-500',
  unavailable: 'bg-red-500',
  unknown: 'bg-gray-400',
};

/**
 * Status display text
 */
const STATUS_TEXT: Record<ComponentStatus | 'unknown', string> = {
  ok: 'Healthy',
  degraded: 'Degraded',
  unavailable: 'Unavailable',
  unknown: 'Unknown',
};

/**
 * Props for HealthIndicator component
 */
interface HealthIndicatorProps {
  /** Health state from useHealth hook */
  healthState: HealthState;
  /** Whether initial load is in progress */
  loading: boolean;
  /** Error message if health check failed */
  error: string | null;
  /** Timestamp of last successful check */
  lastCheck: Date | null;
  /** Whether any service is degraded */
  hasDegradedServices: boolean;
  /** Optional className for container */
  className?: string;
}

/**
 * Single status dot with tooltip
 */
function StatusDot({
  status,
  label,
  description,
  lastCheck,
}: {
  status: ComponentStatus | 'unknown';
  label: string;
  description: string;
  lastCheck: Date | null;
}) {
  const colorClass = STATUS_COLORS[status] || STATUS_COLORS.unknown;
  const statusText = STATUS_TEXT[status] || STATUS_TEXT.unknown;

  const lastCheckText = lastCheck
    ? `Last checked: ${lastCheck.toLocaleTimeString()}`
    : 'Not checked yet';

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          className={cn(
            'h-2.5 w-2.5 rounded-full transition-colors duration-300',
            colorClass
          )}
          aria-label={`${label}: ${statusText}`}
        />
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <div className="space-y-1">
          <div className="font-medium">{label}</div>
          <div className="text-xs opacity-90">{description}</div>
          <div className="flex items-center gap-1.5 text-xs">
            <span
              className={cn('h-1.5 w-1.5 rounded-full', colorClass)}
              aria-hidden="true"
            />
            <span>{statusText}</span>
          </div>
          <div className="text-xs opacity-70">{lastCheckText}</div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * Loading skeleton for health indicator
 */
function HealthIndicatorSkeleton() {
  return (
    <div
      className="flex items-center gap-1.5"
      role="status"
      aria-label="Loading health status"
    >
      {SERVICES.map((service) => (
        <div
          key={service.key}
          className="h-2.5 w-2.5 rounded-full bg-muted-foreground/30 animate-pulse"
          aria-hidden="true"
        />
      ))}
      <Loader2
        className="ml-1 h-3 w-3 animate-spin text-muted-foreground"
        aria-hidden="true"
      />
      <span className="sr-only">Loading health status...</span>
    </div>
  );
}

/**
 * Error state for health indicator
 */
function HealthIndicatorError({ error }: { error: string }) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div
          className="flex items-center gap-1.5 text-destructive"
          role="alert"
          aria-label="Health check failed"
        >
          <AlertCircle className="h-4 w-4" aria-hidden="true" />
          <span className="text-xs hidden sm:inline">Offline</span>
        </div>
      </TooltipTrigger>
      <TooltipContent side="bottom" className="max-w-xs">
        <div className="space-y-1">
          <div className="font-medium text-destructive">Connection Error</div>
          <div className="text-xs">{error}</div>
          <div className="text-xs opacity-70">
            Unable to check system health. The backend may be unreachable.
          </div>
        </div>
      </TooltipContent>
    </Tooltip>
  );
}

/**
 * HealthIndicator component displays colored status dots for each service
 *
 * Features:
 * - Color-coded dots: green (ok), yellow (degraded), red (unavailable)
 * - Tooltip on hover with detailed status
 * - Loading skeleton during initial fetch
 * - Error state when health check fails
 * - Warning indicator when any service is degraded
 * - Smooth color transitions
 *
 * @example
 * ```tsx
 * const { healthState, loading, error, lastCheck, hasDegradedServices } = useHealth();
 *
 * <HealthIndicator
 *   healthState={healthState}
 *   loading={loading}
 *   error={error}
 *   lastCheck={lastCheck}
 *   hasDegradedServices={hasDegradedServices}
 * />
 * ```
 */
export function HealthIndicator({
  healthState,
  loading,
  error,
  lastCheck,
  hasDegradedServices,
  className,
}: HealthIndicatorProps) {
  // Show skeleton during initial load
  if (loading) {
    return <HealthIndicatorSkeleton />;
  }

  // Show error state if we have an error and no previous health data
  if (error && !lastCheck) {
    return <HealthIndicatorError error={error} />;
  }

  return (
    <div
      className={cn('flex items-center gap-1.5', className)}
      role="status"
      aria-label="System health indicators"
    >
      {SERVICES.map((service) => (
        <StatusDot
          key={service.key}
          status={healthState[service.key]}
          label={service.label}
          description={service.description}
          lastCheck={lastCheck}
        />
      ))}

      {/* Warning indicator when any service is degraded */}
      {hasDegradedServices && (
        <Tooltip>
          <TooltipTrigger asChild>
            <AlertCircle
              className="ml-0.5 h-3.5 w-3.5 text-yellow-500 transition-opacity duration-300"
              aria-hidden="true"
            />
          </TooltipTrigger>
          <TooltipContent side="bottom">
            <div className="text-xs">Some services are not fully operational</div>
          </TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

/**
 * Standalone HealthIndicator that manages its own state
 *
 * Use this when you don't need access to health data elsewhere.
 * For shared state, use useHealth hook and pass props to HealthIndicator.
 */
export function HealthIndicatorWithState({
  className,
}: {
  className?: string;
}) {
  // Import dynamically to avoid circular deps
  const { useHealth } = require('@/lib/hooks/useHealth');
  const { healthState, loading, error, lastCheck, hasDegradedServices } =
    useHealth() as UseHealthReturn;

  return (
    <HealthIndicator
      healthState={healthState}
      loading={loading}
      error={error}
      lastCheck={lastCheck}
      hasDegradedServices={hasDegradedServices}
      {...(className ? { className } : {})}
    />
  );
}

export default HealthIndicator;
