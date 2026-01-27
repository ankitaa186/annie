/**
 * Runtime configuration for Annie Web UI
 *
 * Environment variables are injected at build time by Vite.
 * All VITE_* prefixed environment variables are exposed to the client.
 */

export const config = {
  /**
   * Base URL for API requests.
   * Defaults to '/api' which is proxied in development and nginx in production.
   */
  apiUrl: import.meta.env.VITE_API_URL || '/api',

  /**
   * Current environment mode.
   */
  mode: import.meta.env.MODE,

  /**
   * Whether the app is running in development mode.
   */
  isDev: import.meta.env.DEV,

  /**
   * Whether the app is running in production mode.
   */
  isProd: import.meta.env.PROD,
} as const;

/**
 * Build API endpoint URL.
 *
 * @param path - API path (e.g., '/chat' or 'chat')
 * @returns Full API URL
 */
export function apiUrl(path: string): string {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${config.apiUrl}${cleanPath}`;
}
