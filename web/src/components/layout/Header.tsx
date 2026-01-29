import { Menu, X, Sun, Moon, Monitor } from 'lucide-react';
import { useAppStore, useSidebarOpen } from '@/lib/stores/appStore';
import { useIsMobile, usePrefersReducedMotion } from '@/hooks/useMediaQuery';
import { useDarkModeToggle } from '@/hooks/useDarkMode';
import { useHealth } from '@/lib/hooks/useHealth';
import { Button } from '@/components/ui/button';
import { HealthIndicator, LLMIndicator } from '@/components/status';
import { TooltipProvider } from '@/components/ui/tooltip';
import { cn } from '@/lib/utils';

/**
 * Header component with logo, health indicators, and LLM indicator
 *
 * Layout:
 * - Left: Hamburger menu (mobile only) + Annie logo/name
 * - Center: Health status indicators (Story 20.3)
 * - Right: LLM indicator (Story 20.3) + Dark mode toggle
 */
export function Header() {
  const isMobile = useIsMobile();
  const prefersReducedMotion = usePrefersReducedMotion();
  const sidebarOpen = useSidebarOpen();
  const toggleSidebar = useAppStore((state) => state.toggleSidebar);
  const { darkMode, toggle: toggleDarkMode } = useDarkModeToggle();

  // Health status from useHealth hook
  const {
    health,
    healthState,
    loading: healthLoading,
    error: healthError,
    lastCheck,
    hasDegradedServices,
  } = useHealth();

  // Extract active LLM from health response (use llm_api status for now)
  // In production, this would come from a config endpoint or the health response
  const activeLLM = health?.components?.llm_api === 'ok' ? 'gemini-3-pro-preview' : null;

  const transitionClasses = prefersReducedMotion
    ? ''
    : 'transition-colors duration-200';

  return (
    <TooltipProvider delayDuration={300}>
      <header
        className={cn(
          'sticky top-0 z-50 flex h-14 items-center justify-between border-b border-border bg-background/95 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/60',
          transitionClasses
        )}
        role="banner"
      >
        {/* Left section: Hamburger + Logo */}
        <div className="flex items-center gap-2">
          {/* Hamburger menu - mobile only */}
          {isMobile && (
            <Button
              variant="ghost"
              size="icon"
              onClick={toggleSidebar}
              className="h-9 w-9"
              aria-label={sidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
              aria-expanded={sidebarOpen}
              aria-controls="sidebar-navigation"
            >
              {sidebarOpen ? (
                <X className="h-5 w-5" aria-hidden="true" />
              ) : (
                <Menu className="h-5 w-5" aria-hidden="true" />
              )}
            </Button>
          )}

          {/* Annie Logo and Name */}
          <div className="flex items-center gap-2">
            <div
              className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-primary-foreground"
              aria-hidden="true"
            >
              <span className="text-lg font-bold">A</span>
            </div>
            <span className="text-lg font-semibold text-foreground">Annie</span>
          </div>
        </div>

        {/* Center section: Health status indicators (Story 20.3) */}
        <div className="hidden items-center gap-2 md:flex">
          <HealthIndicator
            healthState={healthState}
            loading={healthLoading}
            error={healthError}
            lastCheck={lastCheck}
            hasDegradedServices={hasDegradedServices}
          />
        </div>

        {/* Right section: LLM indicator + Dark mode toggle */}
        <div className="flex items-center gap-2">
          {/* LLM indicator (Story 20.3) */}
          <div className="hidden sm:block">
            <LLMIndicator
              activeLLM={activeLLM}
              llmStatus={healthState.llm}
              loading={healthLoading}
            />
          </div>

          {/* Dark mode toggle */}
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleDarkMode}
            className="h-9 w-9"
            aria-label={`Switch to ${darkMode === 'system' ? 'light' : darkMode === 'light' ? 'dark' : 'system'} mode. Currently: ${darkMode} mode`}
          >
            {darkMode === 'light' && <Sun className="h-5 w-5" aria-hidden="true" />}
            {darkMode === 'dark' && <Moon className="h-5 w-5" aria-hidden="true" />}
            {darkMode === 'system' && <Monitor className="h-5 w-5" aria-hidden="true" />}
          </Button>
        </div>
      </header>
    </TooltipProvider>
  );
}

export default Header;
