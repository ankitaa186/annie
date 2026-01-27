import { useEffect } from 'react';
import { useAppStore, useDarkMode } from '@/lib/stores/appStore';
import { usePrefersDarkMode } from './useMediaQuery';

/**
 * Hook to manage dark mode based on user preference or system setting
 * Applies the 'dark' class to documentElement and syncs with system preference
 */
export function useDarkModeEffect(): void {
  const darkMode = useDarkMode();
  const systemPrefersDark = usePrefersDarkMode();

  useEffect(() => {
    const root = document.documentElement;

    // Determine if dark mode should be applied
    const shouldBeDark =
      darkMode === 'dark' || (darkMode === 'system' && systemPrefersDark);

    if (shouldBeDark) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [darkMode, systemPrefersDark]);
}

/**
 * Hook that returns whether dark mode is currently active (resolved)
 */
export function useIsDarkMode(): boolean {
  const darkMode = useDarkMode();
  const systemPrefersDark = usePrefersDarkMode();

  return darkMode === 'dark' || (darkMode === 'system' && systemPrefersDark);
}

/**
 * Hook to cycle through dark mode options
 */
export function useDarkModeToggle(): {
  darkMode: ReturnType<typeof useDarkMode>;
  isDark: boolean;
  toggle: () => void;
  setMode: (mode: 'system' | 'light' | 'dark') => void;
} {
  const darkMode = useDarkMode();
  const isDark = useIsDarkMode();
  const setDarkMode = useAppStore((state) => state.setDarkMode);

  const toggle = () => {
    // Cycle: system -> light -> dark -> system
    const nextMode =
      darkMode === 'system' ? 'light' : darkMode === 'light' ? 'dark' : 'system';
    setDarkMode(nextMode);
  };

  return {
    darkMode,
    isDark,
    toggle,
    setMode: setDarkMode,
  };
}
