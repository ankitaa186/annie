import { renderHook, act, waitFor } from '@testing-library/react';
import { useHealth } from '../useHealth';
import type { HealthResponse } from '../useHealth';

// Mock fetch
const mockFetch = jest.fn();
global.fetch = mockFetch;

// Mock health response
const mockHealthResponse: HealthResponse = {
  status: 'ok',
  components: {
    mcp_server: 'ok',
    redis: 'ok',
    llm_api: 'ok',
    agentic_memories: {
      status: 'ok',
      checks: { chroma: { ok: true }, timescale: { ok: true } },
    },
    proactive_worker: {
      status: 'ok',
      alive: true,
    },
    langfuse: {
      enabled: true,
      client_available: true,
    },
    cloud_logging: {
      enabled: false,
    },
  },
  timestamp: '2026-01-26T10:00:00Z',
};

describe('useHealth', () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockFetch.mockClear();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it('should start with loading state', () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves

    const { result } = renderHook(() => useHealth());

    expect(result.current.loading).toBe(true);
    expect(result.current.health).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('should fetch health on mount', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthResponse,
    });

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockFetch).toHaveBeenCalledWith('/api/health/full', {
      method: 'GET',
      headers: { Accept: 'application/json' },
    });
    expect(result.current.health).toEqual(mockHealthResponse);
    expect(result.current.error).toBeNull();
  });

  it('should parse health state correctly', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthResponse,
    });

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.healthState).toEqual({
      backend: 'ok',
      mcp: 'ok',
      redis: 'ok',
      memories: 'ok',
      llm: 'ok',
    });
    expect(result.current.hasDegradedServices).toBe(false);
  });

  it('should detect degraded services', async () => {
    const degradedResponse: HealthResponse = {
      ...mockHealthResponse,
      status: 'degraded',
      components: {
        ...mockHealthResponse.components,
        mcp_server: 'unavailable',
        agentic_memories: {
          status: 'degraded',
          error: 'Partial failure',
        },
      },
    };

    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => degradedResponse,
    });

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.healthState.mcp).toBe('unavailable');
    expect(result.current.healthState.memories).toBe('degraded');
    expect(result.current.hasDegradedServices).toBe(true);
  });

  it('should handle network errors gracefully', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network error'));

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Network error');
    expect(result.current.health).toBeNull();
  });

  it('should handle non-ok response', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      statusText: 'Internal Server Error',
    });

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.error).toBe('Health check failed: 500 Internal Server Error');
  });

  it('should poll every 30 seconds', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockHealthResponse,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockHealthResponse, status: 'degraded' }),
      });

    const { result } = renderHook(() => useHealth());

    // Wait for initial fetch
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Advance timer by 30 seconds
    act(() => {
      jest.advanceTimersByTime(30000);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });
  });

  it('should cleanup interval on unmount', async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: async () => mockHealthResponse,
    });

    const { result, unmount } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(mockFetch).toHaveBeenCalledTimes(1);

    // Unmount the hook
    unmount();

    // Advance timer - should not call fetch again
    act(() => {
      jest.advanceTimersByTime(30000);
    });

    // Still only 1 call (no new calls after unmount)
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('should update lastCheck timestamp on success', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => mockHealthResponse,
    });

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.lastCheck).toBeInstanceOf(Date);
  });

  it('should keep last known state on subsequent errors', async () => {
    // First call succeeds
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockHealthResponse,
      })
      // Second call fails
      .mockRejectedValueOnce(new Error('Temporary network issue'));

    const { result } = renderHook(() => useHealth());

    // Wait for initial fetch
    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.health).toEqual(mockHealthResponse);
    expect(result.current.error).toBeNull();

    // Advance timer to trigger second fetch
    act(() => {
      jest.advanceTimersByTime(30000);
    });

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2);
    });

    // Should have error but still show last known health
    expect(result.current.error).toBe('Temporary network issue');
    expect(result.current.health).toEqual(mockHealthResponse);
  });

  it('should provide manual refresh function', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => mockHealthResponse,
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ ...mockHealthResponse, status: 'degraded' }),
      });

    const { result } = renderHook(() => useHealth());

    await waitFor(() => {
      expect(result.current.loading).toBe(false);
    });

    expect(result.current.health?.status).toBe('ok');

    // Manually refresh
    await act(async () => {
      await result.current.refresh();
    });

    expect(result.current.health?.status).toBe('degraded');
    expect(mockFetch).toHaveBeenCalledTimes(2);
  });

  it('should return default health state when no data', () => {
    mockFetch.mockImplementation(() => new Promise(() => {})); // Never resolves

    const { result } = renderHook(() => useHealth());

    expect(result.current.healthState).toEqual({
      backend: 'unavailable',
      mcp: 'unavailable',
      redis: 'unavailable',
      memories: 'unavailable',
      llm: 'unavailable',
    });
    expect(result.current.hasDegradedServices).toBe(true);
  });
});
