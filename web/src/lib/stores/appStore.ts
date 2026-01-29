import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Message, Conversation } from '@/types';
import type { HealthState } from '@/lib/hooks/useHealth';

export type DarkMode = 'system' | 'light' | 'dark';

/** Annie's current state during conversation */
export type AnnieState = 'idle' | 'thinking' | 'speaking' | 'tool_calling';

/** Active tool call information */
export interface ActiveToolCall {
  name: string;
  args: Record<string, unknown>;
  status: 'pending' | 'running' | 'completed' | 'error';
  result?: unknown;
}

/**
 * Default health state when not yet loaded
 */
const DEFAULT_HEALTH_STATE: HealthState = {
  backend: 'unavailable',
  mcp: 'unavailable',
  redis: 'unavailable',
  memories: 'unavailable',
  llm: 'unavailable',
};

interface AppState {
  // Sidebar state
  sidebarOpen: boolean;
  sidebarCollapsed: boolean; // For tablet view (icons only)

  // Dark mode
  darkMode: DarkMode;

  // Health state (Story 20.3)
  health: HealthState;
  activeLLM: string | null;
  healthLoading: boolean;
  healthError: string | null;
  lastHealthCheck: Date | null;

  // Chat state
  activeConversationId: string | null;
  conversations: Conversation[];
  conversationsLoading: boolean; // Story 20.4: Loading state for conversations list
  conversationsError: string | null; // Story 20.4: Error state for conversations list
  messages: Record<string, Message[]>; // Keyed by conversationId
  streamingMessage: string | null; // Current streaming response content
  streamingConversationId: string | null; // Which conversation the streaming belongs to
  isLoadingHistory: boolean;
  isStreaming: boolean;

  // Streaming state (Story 20.7)
  annieState: AnnieState;
  activeTool: ActiveToolCall | null;
  streamError: string | null;
  streamErrorCode: string | null;

  // Layout actions
  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setDarkMode: (mode: DarkMode) => void;

  // Health actions (Story 20.3)
  updateHealth: (health: HealthState) => void;
  setActiveLLM: (llm: string | null) => void;
  setHealthLoading: (loading: boolean) => void;
  setHealthError: (error: string | null) => void;
  setLastHealthCheck: (date: Date | null) => void;

  // Chat actions
  setActiveConversation: (conversationId: string | null) => void;
  setConversations: (conversations: Conversation[]) => void; // Story 20.4: Bulk set conversations
  setConversationsLoading: (loading: boolean) => void; // Story 20.4
  setConversationsError: (error: string | null) => void; // Story 20.4
  addConversation: (conversation: Conversation) => void;
  updateConversation: (conversationId: string, updates: Partial<Conversation>) => void;
  removeConversation: (conversationId: string) => void;
  addMessage: (conversationId: string, message: Message) => void;
  setMessages: (conversationId: string, messages: Message[]) => void;
  updateMessage: (conversationId: string, messageId: string, updates: Partial<Message>) => void;
  setStreamingMessage: (content: string | null) => void;
  setStreamingConversationId: (conversationId: string | null) => void;
  appendToStreamingMessage: (content: string) => void;
  finalizeStreamingMessage: (conversationId: string, messageId: string) => void;
  setIsLoadingHistory: (loading: boolean) => void;
  setIsStreaming: (streaming: boolean) => void;
  clearConversation: (conversationId: string) => void;

  // Streaming actions (Story 20.7)
  setAnnieState: (state: AnnieState) => void;
  setActiveTool: (tool: ActiveToolCall | null) => void;
  updateActiveTool: (updates: Partial<ActiveToolCall>) => void;
  setStreamError: (message: string | null, code?: string | null) => void;
  clearStreamError: () => void;
}

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      // Initial layout state
      sidebarOpen: true,
      sidebarCollapsed: false,
      darkMode: 'system',

      // Initial health state (Story 20.3)
      health: DEFAULT_HEALTH_STATE,
      activeLLM: null,
      healthLoading: true,
      healthError: null,
      lastHealthCheck: null,

      // Initial chat state
      activeConversationId: null,
      conversations: [],
      conversationsLoading: false,
      conversationsError: null,
      messages: {},
      streamingMessage: null,
      streamingConversationId: null,
      isLoadingHistory: false,
      isStreaming: false,

      // Initial streaming state (Story 20.7)
      annieState: 'idle',
      activeTool: null,
      streamError: null,
      streamErrorCode: null,

      // Layout actions
      toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
      setSidebarOpen: (open) => set({ sidebarOpen: open }),
      setSidebarCollapsed: (collapsed) => set({ sidebarCollapsed: collapsed }),
      setDarkMode: (mode) => set({ darkMode: mode }),

      // Health actions (Story 20.3)
      updateHealth: (health) => set({ health }),
      setActiveLLM: (llm) => set({ activeLLM: llm }),
      setHealthLoading: (loading) => set({ healthLoading: loading }),
      setHealthError: (error) => set({ healthError: error }),
      setLastHealthCheck: (date) => set({ lastHealthCheck: date }),

      // Chat actions
      setActiveConversation: (conversationId) => {
        console.log('[Store] setActiveConversation called:', conversationId);
        set({ activeConversationId: conversationId });
      },

      setConversations: (conversations) => set({ conversations }),

      setConversationsLoading: (loading) => set({ conversationsLoading: loading }),

      setConversationsError: (error) => set({ conversationsError: error }),

      addConversation: (conversation) =>
        set((state) => ({
          conversations: [conversation, ...state.conversations],
        })),

      updateConversation: (conversationId, updates) =>
        set((state) => ({
          conversations: state.conversations.map((conv) =>
            conv.id === conversationId ? { ...conv, ...updates } : conv
          ),
        })),

      removeConversation: (conversationId) =>
        set((state) => ({
          conversations: state.conversations.filter((conv) => conv.id !== conversationId),
          messages: Object.fromEntries(
            Object.entries(state.messages).filter(([id]) => id !== conversationId)
          ),
          activeConversationId:
            state.activeConversationId === conversationId
              ? null
              : state.activeConversationId,
        })),

      addMessage: (conversationId, message) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: [...(state.messages[conversationId] || []), message],
          },
        })),

      setMessages: (conversationId, messages) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: messages,
          },
        })),

      updateMessage: (conversationId, messageId, updates) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: (state.messages[conversationId] || []).map((msg) =>
              msg.id === messageId ? { ...msg, ...updates } : msg
            ),
          },
        })),

      setStreamingMessage: (content) => set({ streamingMessage: content }),

      setStreamingConversationId: (conversationId) => {
        console.log('[Store] setStreamingConversationId called:', conversationId);
        set({ streamingConversationId: conversationId });
      },

      appendToStreamingMessage: (content) => {
        console.log('[Store] appendToStreamingMessage called, content length:', content.length);
        set((state) => {
          const newMessage = (state.streamingMessage || '') + content;
          console.log('[Store] streamingMessage updated, total length:', newMessage.length);
          return { streamingMessage: newMessage };
        });
      },

      finalizeStreamingMessage: (conversationId, messageId) => {
        const { streamingMessage, messages } = get();
        if (streamingMessage) {
          const newMessage: Message = {
            id: messageId,
            role: 'assistant',
            content: streamingMessage,
            timestamp: new Date().toISOString(),
          };
          set({
            messages: {
              ...messages,
              [conversationId]: [...(messages[conversationId] || []), newMessage],
            },
            streamingMessage: null,
            isStreaming: false,
          });
        }
      },

      setIsLoadingHistory: (loading) => set({ isLoadingHistory: loading }),

      setIsStreaming: (streaming) => {
        console.log('[Store] setIsStreaming called:', streaming);
        set({ isStreaming: streaming });
      },

      clearConversation: (conversationId) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [conversationId]: [],
          },
        })),

      // Streaming actions (Story 20.7)
      setAnnieState: (annieState) => set({ annieState }),

      setActiveTool: (tool) => set({ activeTool: tool }),

      updateActiveTool: (updates) =>
        set((state) => ({
          activeTool: state.activeTool
            ? { ...state.activeTool, ...updates }
            : null,
        })),

      setStreamError: (message, code = null) =>
        set({ streamError: message, streamErrorCode: code }),

      clearStreamError: () =>
        set({ streamError: null, streamErrorCode: null }),
    }),
    {
      name: 'annie-app-store',
      partialize: (state) => ({
        darkMode: state.darkMode,
        // Persist conversations list but not messages (they'll be fetched from server)
        conversations: state.conversations,
        activeConversationId: state.activeConversationId,
      }),
    }
  )
);

// Selector hooks for better performance
export const useSidebarOpen = () => useAppStore((state) => state.sidebarOpen);
export const useSidebarCollapsed = () => useAppStore((state) => state.sidebarCollapsed);
export const useDarkMode = () => useAppStore((state) => state.darkMode);

// Chat selector hooks
export const useActiveConversationId = () => useAppStore((state) => state.activeConversationId);
export const useConversationsList = () => useAppStore((state) => state.conversations);
export const useConversationsLoading = () => useAppStore((state) => state.conversationsLoading);
export const useConversationsError = () => useAppStore((state) => state.conversationsError);
export const useMessages = (conversationId: string | null) =>
  useAppStore((state) => (conversationId ? state.messages[conversationId] || [] : []));
export const useStreamingMessage = () => useAppStore((state) => state.streamingMessage);
export const useStreamingConversationId = () => useAppStore((state) => state.streamingConversationId);
export const useIsLoadingHistory = () => useAppStore((state) => state.isLoadingHistory);
export const useIsStreaming = () => useAppStore((state) => state.isStreaming);

// Health selector hooks (Story 20.3)
export const useHealth = () => useAppStore((state) => state.health);
export const useActiveLLM = () => useAppStore((state) => state.activeLLM);
export const useHealthLoading = () => useAppStore((state) => state.healthLoading);
export const useHealthError = () => useAppStore((state) => state.healthError);
export const useLastHealthCheck = () => useAppStore((state) => state.lastHealthCheck);
export const useHasDegradedServices = () =>
  useAppStore((state) =>
    Object.values(state.health).some((status) => status !== 'ok')
  );

// Streaming selector hooks (Story 20.7)
export const useAnnieState = () => useAppStore((state) => state.annieState);
export const useActiveTool = () => useAppStore((state) => state.activeTool);
export const useStreamError = () => useAppStore((state) => state.streamError);
export const useStreamErrorCode = () => useAppStore((state) => state.streamErrorCode);
