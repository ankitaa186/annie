import { useState, useEffect, useCallback, useRef } from 'react';
import { config } from '@/lib/config';

/**
 * Component status values returned by the backend health API
 */
export type ComponentStatus = 'ok' | 'degraded' | 'unavailable';

/**
 * Agentic memories component health status
 */
export interface AgenticMemoriesStatus {
  status: ComponentStatus;
  checks?: Record<string, { ok: boolean }>;
  error?: string;
}

/**
 * Proactive worker health status
 */
export interface WorkerStatus {
  status: ComponentStatus;
  alive?: boolean;
  error?: string;
}

/**
 * Langfuse health status
 */
export interface LangfuseStatus {
  enabled: boolean;
  client_available?: boolean;
  last_flush?: string | null;
}

/**
 * Cloud logging health status
 */
export interface CloudLoggingStatus {
  enabled: boolean;
  driver?: string;
}

/**
 * Full health response from /health/full endpoint
 */
export interface HealthResponse {
  status: 'ok' | 'degraded';
  components: {
    mcp_server: ComponentStatus;
    redis: ComponentStatus;
    llm_api: ComponentStatus;
    agentic_memories: AgenticMemoriesStatus;
    proactive_worker: WorkerStatus;
    langfuse: LangfuseStatus;
    cloud_logging: CloudLoggingStatus;
  };
  timestamp: string;
}

/**
 * Simplified health state for UI display
 */
export interface HealthState {
  backend: ComponentStatus;
  mcp: ComponentStatus;
  redis: ComponentStatus;
  memories: ComponentStatus;
  llm: ComponentStatus;
}

/**
 * Return type for useHealth hook
 */
export interface UseHealthReturn {
  /** Current health data from API */
  health: HealthResponse | null;
  /** Simplified health state for UI */
  healthState: HealthState;
  /** Whether initial fetch is in progress */
  loading: boolean;
  /** Error message if health check failed */
  error: string | null;
  /** Timestamp of last successful check */
  lastCheck: Date | null;
  /** Whether any service is degraded or unavailable */
  hasDegradedServices: boolean;
  /** Manually trigger a health check */
  refresh: () => Promise<void>;
}

/**
 * Default health state when loading or error
 */
const DEFAULT_HEALTH_STATE: HealthState = {
  backend: 'unavailable',
  mcp: 'unavailable',
  redis: 'unavailable',
  memories: 'unavailable',
  llm: 'unavailable',
};

/**
 * Polling interval in milliseconds (30 seconds)
 */
const POLLING_INTERVAL = 30000;

/**
 * Hook to fetch and poll health status from the backend
 *
 * Features:
 * - Polls /health/full every 30 seconds
 * - Handles network errors gracefully
 * - Provides loading state for initial fetch
 * - Exposes simplified health state for UI components
 *
 * @returns Health status, loading state, and error information
 */
export function useHealth(): UseHealthReturn {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastCheck, setLastCheck] = useState<Date | null>(null);

  // Track if component is mounted to avoid state updates after unmount
  const mountedRef = useRef(true);
  // Track the interval ID for cleanup
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  /**
   * Fetch health status from the backend API
   */
  const fetchHealth = useCallback(async () => {
    try {
      const response = await fetch(`${config.apiUrl}/health/full`, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
        },
      });

      if (!mountedRef.current) return;

      if (!response.ok) {
        throw new Error(`Health check failed: ${response.status} ${response.statusText}`);
      }

      const data: HealthResponse = await response.json();

      if (!mountedRef.current) return;

      setHealth(data);
      setError(null);
      setLastCheck(new Date());
    } catch (e) {
      if (!mountedRef.current) return;

      const errorMessage = e instanceof Error ? e.message : 'Unable to check system health';
      setError(errorMessage);
      // Don't clear existing health data on error - keep showing last known state
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, []);

  /**
   * Manual refresh function exposed to consumers
   */
  const refresh = useCallback(async () => {
    await fetchHealth();
  }, [fetchHealth]);

  // Initial fetch and polling setup
  useEffect(() => {
    mountedRef.current = true;

    // Initial fetch
    fetchHealth();

    // Set up polling interval
    intervalRef.current = setInterval(fetchHealth, POLLING_INTERVAL);

    // Cleanup on unmount
    return () => {
      mountedRef.current = false;
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [fetchHealth]);

  /**
   * Convert API response to simplified health state for UI
   */
  const healthState: HealthState = health
    ? {
        // Backend is "ok" if we got a response
        backend: health.status === 'ok' ? 'ok' : 'degraded',
        mcp: health.components.mcp_server,
        redis: health.components.redis,
        memories:
          typeof health.components.agentic_memories === 'object'
            ? health.components.agentic_memories.status
            : 'unavailable',
        llm: health.components.llm_api,
      }
    : DEFAULT_HEALTH_STATE;

  /**
   * Check if any service is not "ok"
   */
  const hasDegradedServices = Object.values(healthState).some(
    (status) => status !== 'ok'
  );

  return {
    health,
    healthState,
    loading,
    error,
    lastCheck,
    hasDegradedServices,
    refresh,
  };
}

export default useHealth;
