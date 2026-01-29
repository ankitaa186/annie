import { useEffect, type ReactNode } from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { MainContent } from './MainContent';
import { useAppStore, useSidebarOpen } from '@/lib/stores/appStore';
import { useIsMobile, useIsTablet, usePrefersReducedMotion } from '@/hooks/useMediaQuery';
import { useDarkModeEffect } from '@/hooks/useDarkMode';
import { cn } from '@/lib/utils';

interface LayoutProps {
  children: ReactNode;
}

/**
 * Main layout component providing responsive two-column structure
 *
 * Breakpoints:
 * - Mobile (<768px): Single column, sidebar hidden (hamburger menu)
 * - Tablet (768-1024px): Two column, sidebar collapsed (icons only)
 * - Desktop (>1024px): Two column, full sidebar
 */
export function Layout({ children }: LayoutProps) {
  const isMobile = useIsMobile();
  const isTablet = useIsTablet();
  const prefersReducedMotion = usePrefersReducedMotion();

  const sidebarOpen = useSidebarOpen();
  const setSidebarOpen = useAppStore((state) => state.setSidebarOpen);
  const setSidebarCollapsed = useAppStore((state) => state.setSidebarCollapsed);

  // Apply dark mode effect
  useDarkModeEffect();

  // Handle responsive sidebar behavior
  useEffect(() => {
    if (isMobile) {
      // On mobile, sidebar is overlay and closed by default
      setSidebarOpen(false);
      setSidebarCollapsed(false);
    } else if (isTablet) {
      // On tablet, sidebar is collapsed (icons only)
      setSidebarOpen(true);
      setSidebarCollapsed(true);
    } else {
      // On desktop, full sidebar
      setSidebarOpen(true);
      setSidebarCollapsed(false);
    }
  }, [isMobile, isTablet, setSidebarOpen, setSidebarCollapsed]);

  // Transition classes based on reduced motion preference
  const transitionClasses = prefersReducedMotion
    ? ''
    : 'transition-all duration-300 ease-in-out';

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Header - Fixed at top */}
      <Header />

      {/* Main layout area - fills remaining height, no outer scroll */}
      <div className="flex flex-1 min-h-0">
        {/* Sidebar overlay backdrop for mobile */}
        {isMobile && sidebarOpen && (
          <div
            className={cn(
              'fixed inset-0 z-40 bg-black/50',
              prefersReducedMotion ? '' : 'animate-in fade-in duration-200'
            )}
            onClick={() => setSidebarOpen(false)}
            onKeyDown={(e) => {
              if (e.key === 'Escape') {
                setSidebarOpen(false);
              }
            }}
            role="button"
            tabIndex={0}
            aria-label="Close sidebar"
          />
        )}

        {/* Sidebar */}
        <aside
          className={cn(
            'z-50 flex-shrink-0 overflow-hidden bg-muted/50',
            transitionClasses,
            // Mobile: overlay, slide from left
            isMobile && [
              'fixed inset-y-0 left-0 top-14',
              sidebarOpen
                ? 'translate-x-0'
                : '-translate-x-full',
              'w-64',
            ],
            // Tablet: collapsed (icons only)
            isTablet && 'w-16',
            // Desktop: full width
            !isMobile && !isTablet && 'w-64',
            // Border
            'border-r border-border'
          )}
          aria-label="Sidebar navigation"
        >
          <Sidebar />
        </aside>

        {/* Main content area */}
        <main
          className={cn(
            'flex-1 min-h-0 overflow-hidden',
            transitionClasses
          )}
        >
          <MainContent>{children}</MainContent>
        </main>
      </div>
    </div>
  );
}

export default Layout;
