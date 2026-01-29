/**
 * Toast notification component
 *
 * Displays temporary notifications at the bottom of the screen.
 * Supports different types: default, success, error, warning.
 */

import { X, CheckCircle, AlertCircle, AlertTriangle, Info } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useToasts, useToastStore, type Toast } from '@/lib/hooks/useToast';

const toastVariants: Record<Toast['type'], string> = {
  default: 'bg-popover text-popover-foreground border-border',
  success: 'bg-emerald-500/10 text-emerald-500 border-emerald-500/20',
  error: 'bg-destructive/10 text-destructive border-destructive/20',
  warning: 'bg-amber-500/10 text-amber-500 border-amber-500/20',
};

const toastIcons: Record<Toast['type'], typeof Info> = {
  default: Info,
  success: CheckCircle,
  error: AlertCircle,
  warning: AlertTriangle,
};

interface ToastItemProps {
  toast: Toast;
  onDismiss: (id: string) => void;
}

function ToastItem({ toast, onDismiss }: ToastItemProps) {
  const Icon = toastIcons[toast.type];

  return (
    <div
      className={cn(
        'flex items-start gap-3 rounded-lg border p-4 shadow-lg',
        'animate-in slide-in-from-bottom-5 fade-in duration-200',
        toastVariants[toast.type]
      )}
      role="alert"
      aria-live="assertive"
    >
      <Icon className="h-5 w-5 flex-shrink-0 mt-0.5" aria-hidden="true" />
      <p className="flex-1 text-sm leading-relaxed">{toast.message}</p>
      <button
        onClick={() => onDismiss(toast.id)}
        className={cn(
          'flex-shrink-0 rounded-full p-1',
          'hover:bg-foreground/10 transition-colors',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2'
        )}
        aria-label="Dismiss notification"
      >
        <X className="h-4 w-4" />
      </button>
    </div>
  );
}

/**
 * Toast container - renders all active toasts
 *
 * Place this component at the root of your app (in Layout or App.tsx)
 */
export function ToastContainer() {
  const toasts = useToasts();
  const removeToast = useToastStore((state) => state.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div
      className={cn(
        'fixed bottom-4 right-4 z-[100]',
        'flex flex-col gap-2',
        'max-w-md w-full pointer-events-none'
      )}
      aria-label="Notifications"
    >
      {toasts.map((toast) => (
        <div key={toast.id} className="pointer-events-auto">
          <ToastItem toast={toast} onDismiss={removeToast} />
        </div>
      ))}
    </div>
  );
}

export default ToastContainer;
