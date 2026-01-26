# Story 20.15: Integration Testing & Polish

Status: drafted

## Story

As a developer,
I want comprehensive end-to-end tests and UI polish,
so that the web UI is reliable, accessible, and production-ready.

## Acceptance Criteria

1. E2E tests with Playwright covering all major flows
2. Test: Login flow (Cloudflare Access simulation)
3. Test: Send message and receive streamed response
4. Test: File upload flow
5. Test: Conversation switching
6. Test: New conversation creation
7. Cross-browser testing (Chrome, Firefox, Safari, Edge)
8. Mobile device testing (iOS Safari, Android Chrome)
9. Lighthouse score >70 for performance
10. WCAG 2.1 AA accessibility compliance
11. Error boundary implementation for graceful failures
12. 404 and error pages designed
13. Loading states and skeletons for all async operations
14. Polish: Consistent spacing, typography, and colors

## Tasks / Subtasks

- [ ] Task 1: Set up Playwright (AC: 1)
  - [ ] 1.1 Install Playwright and configure
  - [ ] 1.2 Create test fixtures and helpers
  - [ ] 1.3 Set up CI integration for tests

- [ ] Task 2: Write E2E tests (AC: 2, 3, 4, 5, 6)
  - [ ] 2.1 Test login simulation
  - [ ] 2.2 Test send message flow
  - [ ] 2.3 Test SSE streaming reception
  - [ ] 2.4 Test file upload with preview
  - [ ] 2.5 Test conversation list interactions
  - [ ] 2.6 Test new conversation creation
  - [ ] 2.7 Test conversation deletion

- [ ] Task 3: Cross-browser testing (AC: 7)
  - [ ] 3.1 Configure Playwright for multiple browsers
  - [ ] 3.2 Run tests on Chrome
  - [ ] 3.3 Run tests on Firefox
  - [ ] 3.4 Run tests on Safari (WebKit)
  - [ ] 3.5 Run tests on Edge
  - [ ] 3.6 Fix browser-specific issues

- [ ] Task 4: Mobile testing (AC: 8)
  - [ ] 4.1 Configure mobile viewports in Playwright
  - [ ] 4.2 Test iOS Safari emulation
  - [ ] 4.3 Test Android Chrome emulation
  - [ ] 4.4 Test responsive layout transitions
  - [ ] 4.5 Test touch interactions

- [ ] Task 5: Performance audit (AC: 9)
  - [ ] 5.1 Run Lighthouse audit
  - [ ] 5.2 Optimize bundle size if needed
  - [ ] 5.3 Add lazy loading for heavy components
  - [ ] 5.4 Optimize images and assets

- [ ] Task 6: Accessibility audit (AC: 10)
  - [ ] 6.1 Run axe accessibility scanner
  - [ ] 6.2 Fix ARIA label issues
  - [ ] 6.3 Ensure keyboard navigation works
  - [ ] 6.4 Test with screen reader
  - [ ] 6.5 Verify color contrast ratios

- [ ] Task 7: Implement error boundaries (AC: 11)
  - [ ] 7.1 Create ErrorBoundary component
  - [ ] 7.2 Wrap major sections with boundaries
  - [ ] 7.3 Show user-friendly error UI
  - [ ] 7.4 Add error reporting/logging

- [ ] Task 8: Create error pages (AC: 12)
  - [ ] 8.1 Design 404 Not Found page
  - [ ] 8.2 Design generic error page
  - [ ] 8.3 Add route for 404 fallback

- [ ] Task 9: Ensure loading states (AC: 13)
  - [ ] 9.1 Audit all async operations
  - [ ] 9.2 Add skeletons where missing
  - [ ] 9.3 Add loading spinners where appropriate
  - [ ] 9.4 Ensure no flash of unstyled content

- [ ] Task 10: UI polish (AC: 14)
  - [ ] 10.1 Review spacing consistency
  - [ ] 10.2 Review typography hierarchy
  - [ ] 10.3 Review color consistency
  - [ ] 10.4 Review dark mode appearance
  - [ ] 10.5 Fix any visual inconsistencies

## Dev Notes

### Playwright Configuration

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: 'html',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
    { name: 'webkit', use: { ...devices['Desktop Safari'] } },
    { name: 'Mobile Chrome', use: { ...devices['Pixel 5'] } },
    { name: 'Mobile Safari', use: { ...devices['iPhone 12'] } },
  ],
  webServer: {
    command: 'npm run dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

### Sample E2E Tests

```typescript
// tests/e2e/chat.spec.ts
import { test, expect } from '@playwright/test';

test.describe('Chat Flow', () => {
  test('should send message and receive response', async ({ page }) => {
    await page.goto('/');

    // Type message
    const input = page.getByRole('textbox', { name: /message/i });
    await input.fill('Hello Annie!');

    // Send message
    await page.getByRole('button', { name: /send/i }).click();

    // Wait for user message to appear
    await expect(page.getByText('Hello Annie!')).toBeVisible();

    // Wait for Annie's response (streaming)
    await expect(page.locator('.annie-message')).toBeVisible({ timeout: 30000 });
  });

  test('should upload file', async ({ page }) => {
    await page.goto('/');

    // Upload file
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles('./tests/fixtures/test-image.png');

    // Verify preview
    await expect(page.getByAltText('File preview')).toBeVisible();

    // Send with file
    await page.getByRole('button', { name: /send/i }).click();
  });
});
```

### Error Boundary Component

```tsx
import { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error caught by boundary:', error, errorInfo);
    // Could send to error reporting service
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="p-8 text-center">
          <h2 className="text-xl font-bold mb-2">Something went wrong</h2>
          <p className="text-gray-500 mb-4">Please try refreshing the page</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 bg-purple-500 text-white rounded"
          >
            Refresh
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}
```

### 404 Page

```tsx
export function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-6xl font-bold text-gray-300">404</h1>
      <p className="text-xl text-gray-500 mt-4">Page not found</p>
      <Link
        to="/"
        className="mt-8 px-4 py-2 bg-purple-500 text-white rounded"
      >
        Go back home
      </Link>
    </div>
  );
}
```

### Loading Skeleton Examples

```tsx
// Conversation list skeleton
export function ConversationListSkeleton() {
  return (
    <div className="space-y-2 p-4">
      {[...Array(5)].map((_, i) => (
        <div key={i} className="animate-pulse">
          <div className="h-4 bg-gray-200 rounded w-3/4 mb-2" />
          <div className="h-3 bg-gray-200 rounded w-1/2" />
        </div>
      ))}
    </div>
  );
}

// Message skeleton
export function MessageSkeleton() {
  return (
    <div className="animate-pulse flex gap-3 mb-4">
      <div className="w-8 h-8 bg-gray-200 rounded-full" />
      <div className="flex-1">
        <div className="h-4 bg-gray-200 rounded w-1/4 mb-2" />
        <div className="h-4 bg-gray-200 rounded w-3/4" />
      </div>
    </div>
  );
}
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.15]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-4]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
