/**
 * Simple toast hook for displaying notifications
 *
 * Uses a global state to manage toast messages.
 * Components can use the useToast hook to display toasts.
 */

import { create } from 'zustand';

export type ToastType = 'default' | 'success' | 'error' | 'warning';

export interface Toast {
  id: string;
  message: string;
  type: ToastType;
  duration?: number;
}

interface ToastState {
  toasts: Toast[];
  addToast: (message: string, type?: ToastType, duration?: number) => string;
  removeToast: (id: string) => void;
  clearToasts: () => void;
}

export const useToastStore = create<ToastState>((set, get) => ({
  toasts: [],

  addToast: (message: string, type: ToastType = 'default', duration = 5000): string => {
    const id = crypto.randomUUID();
    const toast: Toast = { id, message, type, duration };

    set((state) => ({
      toasts: [...state.toasts, toast],
    }));

    // Auto-remove after duration
    if (duration > 0) {
      setTimeout(() => {
        get().removeToast(id);
      }, duration);
    }

    return id;
  },

  removeToast: (id: string) => {
    set((state) => ({
      toasts: state.toasts.filter((t) => t.id !== id),
    }));
  },

  clearToasts: () => {
    set({ toasts: [] });
  },
}));

/**
 * Hook for displaying toast notifications
 */
export function useToast() {
  const addToast = useToastStore((state) => state.addToast);
  const removeToast = useToastStore((state) => state.removeToast);

  return {
    toast: (message: string, type?: ToastType, duration?: number) =>
      addToast(message, type, duration),
    success: (message: string, duration?: number) => addToast(message, 'success', duration),
    error: (message: string, duration?: number) => addToast(message, 'error', duration ?? 7000),
    warning: (message: string, duration?: number) => addToast(message, 'warning', duration),
    dismiss: removeToast,
  };
}

/**
 * Hook for accessing all toasts (for ToastContainer)
 */
export function useToasts() {
  return useToastStore((state) => state.toasts);
}
