/**
 * SSE Stream Client for Annie Web UI
 *
 * Handles Server-Sent Events connection to the backend streaming endpoint.
 * Features:
 * - EventSource connection management
 * - Auto-reconnect with exponential backoff
 * - Connection state tracking
 * - Error handling and recovery
 *
 * Story 20.7: SSE Streaming Integration
 */

import { apiUrl } from '@/lib/config';

/** Backoff configuration for reconnection */
const INITIAL_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30000;
const BACKOFF_MULTIPLIER = 2;

/** Maximum reconnection attempts before giving up */
const MAX_RECONNECT_ATTEMPTS = 5;

/** Connection state */
export type ConnectionState =
  | 'disconnected'
  | 'connecting'
  | 'connected'
  | 'error'
  | 'closed';

/** SSE event types from backend */
export type SSEEventType =
  | 'status'
  | 'token'
  | 'tool_call'
  | 'tool_call_started'
  | 'tool_call_completed'
  | 'tool_result'
  | 'done'
  | 'error';

/** Parsed SSE event data */
export interface SSEEventData {
  type: SSEEventType;
  message?: string;
  content?: string;
  name?: string;
  args?: Record<string, unknown>;
  result?: unknown;
  code?: string;
  tokens_used?: {
    prompt: number;
    completion: number;
  };
  // Fields for tool_call_started/completed events
  tool?: string;
  arguments?: Record<string, unknown>;
  result_summary?: string;
}

/** Stream client event handlers */
export interface StreamClientHandlers {
  onStatus?: (message: string) => void;
  onToken?: (content: string) => void;
  onToolCall?: (name: string, args: Record<string, unknown>) => void;
  onToolResult?: (name: string, result: unknown) => void;
  onDone?: (tokensUsed?: { prompt: number; completion: number }) => void;
  onError?: (message: string, code?: string) => void;
  onConnectionStateChange?: (state: ConnectionState) => void;
}

/**
 * StreamClient - SSE connection manager for streaming LLM responses
 *
 * Usage:
 * ```ts
 * const client = new StreamClient(conversationId, {
 *   onToken: (content) => appendToMessage(content),
 *   onDone: () => finalizeMessage(),
 *   onError: (message) => showError(message),
 * });
 *
 * client.connect();
 * // Later:
 * client.disconnect();
 * ```
 */
export class StreamClient {
  private eventSource: EventSource | null = null;
  private conversationId: string;
  private handlers: StreamClientHandlers;
  private connectionState: ConnectionState = 'disconnected';
  private backoffMs: number = INITIAL_BACKOFF_MS;
  private reconnectAttempts: number = 0;
  private reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private shouldReconnect: boolean = true;
  private isManualClose: boolean = false;

  constructor(conversationId: string, handlers: StreamClientHandlers = {}) {
    this.conversationId = conversationId;
    this.handlers = handlers;
  }

  /**
   * Get current connection state
   */
  get state(): ConnectionState {
    return this.connectionState;
  }

  /**
   * Check if connected
   */
  get isConnected(): boolean {
    return this.connectionState === 'connected';
  }

  /**
   * Update connection state and notify handler
   */
  private setConnectionState(state: ConnectionState): void {
    this.connectionState = state;
    this.handlers.onConnectionStateChange?.(state);
  }

  /**
   * Connect to the SSE stream
   */
  connect(): void {
    // Don't connect if already connected or connecting
    if (this.eventSource && this.connectionState !== 'error') {
      return;
    }

    this.isManualClose = false;
    this.shouldReconnect = true;
    this.setConnectionState('connecting');

    const url = apiUrl(`/stream/${this.conversationId}`);
    console.log('[StreamClient] Creating EventSource for URL:', url);

    try {
      this.eventSource = new EventSource(url);

      this.eventSource.onopen = () => {
        console.log('[StreamClient] EventSource connected');
        // Reset backoff on successful connection
        this.backoffMs = INITIAL_BACKOFF_MS;
        this.reconnectAttempts = 0;
        this.setConnectionState('connected');
      };

      this.eventSource.onmessage = (event: MessageEvent) => {
        console.log('[StreamClient] Message received:', event.data.substring(0, 100));
        this.handleMessage(event);
      };

      this.eventSource.onerror = (event) => {
        console.error('[StreamClient] EventSource error:', event);
        // EventSource error - could be connection lost or server error
        if (!this.isManualClose) {
          this.setConnectionState('error');
          this.handleReconnect();
        }
      };
    } catch (err) {
      this.setConnectionState('error');
      this.handlers.onError?.(
        err instanceof Error ? err.message : 'Failed to connect to stream'
      );
    }
  }

  /**
   * Disconnect from the SSE stream
   */
  disconnect(): void {
    this.isManualClose = true;
    this.shouldReconnect = false;
    this.cancelReconnect();

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    this.setConnectionState('closed');
  }

  /**
   * Handle incoming SSE message
   */
  private handleMessage(event: MessageEvent): void {
    try {
      const data: SSEEventData = JSON.parse(event.data);

      switch (data.type) {
        case 'status':
          if (data.message) {
            this.handlers.onStatus?.(data.message);
          }
          break;

        case 'token':
          if (data.content !== undefined) {
            this.handlers.onToken?.(data.content);
          }
          break;

        case 'tool_call':
          if (data.name && data.args) {
            this.handlers.onToolCall?.(data.name, data.args);
          }
          break;

        case 'tool_call_started':
          // Backend sends tool_call_started with tool and arguments fields
          if (data.tool && data.arguments) {
            this.handlers.onToolCall?.(data.tool, data.arguments);
          }
          break;

        case 'tool_result':
          if (data.name) {
            this.handlers.onToolResult?.(data.name, data.result);
          }
          break;

        case 'tool_call_completed':
          // Backend sends tool_call_completed with tool and result_summary fields
          if (data.tool) {
            this.handlers.onToolResult?.(data.tool, data.result_summary);
          }
          break;

        case 'done':
          this.handlers.onDone?.(data.tokens_used);
          // Close connection after done event - stream is complete
          this.disconnect();
          break;

        case 'error':
          this.handlers.onError?.(
            data.message || 'Unknown error',
            data.code
          );
          // Don't auto-reconnect on explicit error from server
          this.shouldReconnect = false;
          this.disconnect();
          break;

        default:
          // Unknown event type - log but don't crash
          console.warn('Unknown SSE event type:', data);
      }
    } catch (err) {
      // JSON parse error - log but don't crash
      console.error('Failed to parse SSE message:', event.data, err);
    }
  }

  /**
   * Handle reconnection with exponential backoff
   */
  private handleReconnect(): void {
    // Don't reconnect if manually closed or max attempts reached
    if (!this.shouldReconnect) {
      return;
    }

    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.handlers.onError?.(
        'Connection lost. Maximum reconnection attempts reached.',
        'MAX_RECONNECT'
      );
      this.shouldReconnect = false;
      return;
    }

    this.reconnectAttempts++;

    // Cancel any pending reconnect
    this.cancelReconnect();

    // Schedule reconnect with backoff
    this.reconnectTimeoutId = setTimeout(() => {
      if (this.shouldReconnect) {
        this.connect();
        // Increase backoff for next attempt
        this.backoffMs = Math.min(
          this.backoffMs * BACKOFF_MULTIPLIER,
          MAX_BACKOFF_MS
        );
      }
    }, this.backoffMs);
  }

  /**
   * Cancel any pending reconnection attempt
   */
  private cancelReconnect(): void {
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
  }

  /**
   * Reset the client for a new stream
   * Call this when starting a new conversation or retrying
   */
  reset(conversationId?: string): void {
    this.disconnect();
    if (conversationId) {
      this.conversationId = conversationId;
    }
    this.backoffMs = INITIAL_BACKOFF_MS;
    this.reconnectAttempts = 0;
    this.setConnectionState('disconnected');
  }
}

/**
 * Create a new StreamClient instance
 */
export function createStreamClient(
  conversationId: string,
  handlers: StreamClientHandlers = {}
): StreamClient {
  return new StreamClient(conversationId, handlers);
}

export default StreamClient;
