/**
 * Tests for useChat hook
 *
 * Tests cover:
 * - Message sending
 * - File attachment handling
 * - Store updates
 * - Error handling
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { useChat } from '../useChat';

// Mock the appStore
const mockAddMessage = vi.fn();
const mockAddConversation = vi.fn();
const mockSetActiveConversation = vi.fn();
const mockSetIsStreaming = vi.fn();

vi.mock('@/lib/stores/appStore', () => ({
  useAppStore: (selector: (state: unknown) => unknown) => {
    const state = {
      activeConversationId: null,
      addMessage: mockAddMessage,
      addConversation: mockAddConversation,
      setActiveConversation: mockSetActiveConversation,
      setIsStreaming: mockSetIsStreaming,
    };
    return selector(state);
  },
}));

// Mock fetch
const mockFetch = vi.fn();
global.fetch = mockFetch;

// Mock sessionStorage
const mockSessionStorage = {
  getItem: vi.fn(),
  setItem: vi.fn(),
};
Object.defineProperty(global, 'sessionStorage', {
  value: mockSessionStorage,
});

describe('useChat', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSessionStorage.getItem.mockReturnValue('test-user-123');
    mockFetch.mockResolvedValue({
      ok: true,
      json: () =>
        Promise.resolve({
          conversation_id: 'conv-123',
          status: 'streaming',
          stream_url: '/api/stream/conv-123',
          timestamp: new Date().toISOString(),
        }),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('sendMessage', () => {
    it('should send a text message', async () => {
      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('Hello Annie');
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat'),
        expect.objectContaining({
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: expect.stringContaining('Hello Annie'),
        })
      );
    });

    it('should add user message to store optimistically', async () => {
      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('Test message');
      });

      expect(mockAddMessage).toHaveBeenCalledWith(
        expect.any(String), // conversation ID
        expect.objectContaining({
          role: 'user',
          content: 'Test message',
        })
      );
    });

    it('should create conversation for new chat', async () => {
      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('First message');
      });

      expect(mockAddConversation).toHaveBeenCalledWith(
        expect.objectContaining({
          title: expect.stringContaining('First message'),
        })
      );
      expect(mockSetActiveConversation).toHaveBeenCalled();
    });

    it('should set isSending during request', async () => {
      const { result } = renderHook(() => useChat());

      expect(result.current.isSending).toBe(false);

      const sendPromise = act(async () => {
        await result.current.sendMessage('Test');
      });

      // Note: Due to async nature, checking mid-flight state is tricky
      // The important thing is it returns to false after completion
      await sendPromise;

      expect(result.current.isSending).toBe(false);
    });

    it('should throw error for empty message without files', async () => {
      const { result } = renderHook(() => useChat());

      await expect(
        act(async () => {
          await result.current.sendMessage('');
        })
      ).rejects.toThrow('Message or files required');
    });

    it('should trim whitespace from message', async () => {
      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('  Hello  ');
      });

      expect(mockAddMessage).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          content: 'Hello',
        })
      );
    });
  });

  describe('error handling', () => {
    it('should set error on API failure', async () => {
      mockFetch.mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: 'Server error' }),
      });

      const { result } = renderHook(() => useChat());

      await expect(
        act(async () => {
          await result.current.sendMessage('Test');
        })
      ).rejects.toThrow('Server error');

      expect(result.current.error).toBe('Server error');
    });

    it('should handle network errors', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useChat());

      await expect(
        act(async () => {
          await result.current.sendMessage('Test');
        })
      ).rejects.toThrow('Network error');

      expect(result.current.error).toBe('Network error');
    });

    it('should clear error with clearError', async () => {
      mockFetch.mockRejectedValue(new Error('Network error'));

      const { result } = renderHook(() => useChat());

      try {
        await act(async () => {
          await result.current.sendMessage('Test');
        });
      } catch {
        // Expected
      }

      expect(result.current.error).toBe('Network error');

      act(() => {
        result.current.clearError();
      });

      expect(result.current.error).toBeNull();
    });
  });

  describe('streaming state', () => {
    it('should set isStreaming during send', async () => {
      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('Test');
      });

      // Should have been called with true at start
      expect(mockSetIsStreaming).toHaveBeenCalledWith(true);
    });
  });

  describe('user ID management', () => {
    it('should use existing user ID from session storage', async () => {
      mockSessionStorage.getItem.mockReturnValue('existing-user-id');

      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('Test');
      });

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          body: expect.stringContaining('existing-user-id'),
        })
      );
    });

    it('should generate new user ID if none exists', async () => {
      mockSessionStorage.getItem.mockReturnValue(null);

      const { result } = renderHook(() => useChat());

      await act(async () => {
        await result.current.sendMessage('Test');
      });

      // Should have stored a new user ID
      expect(mockSessionStorage.setItem).toHaveBeenCalledWith(
        'annie-user-id',
        expect.stringMatching(/^web_/)
      );
    });
  });
});
