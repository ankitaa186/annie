import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface MainContentProps {
  children: ReactNode;
  className?: string;
}

/**
 * Main content area component
 * Provides proper scrolling container for chat and other content
 */
export function MainContent({ children, className }: MainContentProps) {
  return (
    <div
      className={cn(
        'flex h-full min-h-0 flex-col overflow-hidden',
        className
      )}
      role="main"
      aria-label="Main content area"
    >
      {children}
    </div>
  );
}

export default MainContent;
