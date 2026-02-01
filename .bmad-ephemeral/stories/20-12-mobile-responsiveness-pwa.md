# Story 20.12: Mobile Responsiveness & PWA

Status: drafted

## Story

As a mobile user,
I want Annie's web UI to work perfectly on my phone and be installable as an app,
so that I can access Annie on mobile without the Telegram app.

## Acceptance Criteria

1. Full functionality on mobile devices
2. Touch-friendly UI (48px minimum touch targets)
3. Swipe gestures for sidebar open/close
4. PWA manifest for "Add to Home Screen"
5. Service worker for offline shell caching
6. Splash screen on mobile app launch
7. iOS Safari viewport handling (notch, keyboard)
8. Android Chrome install prompt support
9. Landscape orientation support
10. Responsive images and assets
11. No horizontal scroll on any screen size
12. Performance optimized for mobile networks

## Tasks / Subtasks

- [ ] Task 1: Audit and fix responsive issues (AC: 1, 11)
  - [ ] 1.1 Test all pages on mobile viewports
  - [ ] 1.2 Fix any overflow/scroll issues
  - [ ] 1.3 Ensure all content accessible on mobile
  - [ ] 1.4 Test on actual devices

- [ ] Task 2: Implement touch targets (AC: 2)
  - [ ] 2.1 Audit all interactive elements
  - [ ] 2.2 Ensure 48px minimum size
  - [ ] 2.3 Add adequate spacing between targets
  - [ ] 2.4 Test touch accuracy

- [ ] Task 3: Add swipe gestures (AC: 3)
  - [ ] 3.1 Implement swipe-to-open sidebar
  - [ ] 3.2 Implement swipe-to-close sidebar
  - [ ] 3.3 Add gesture hints for new users

- [ ] Task 4: Create PWA manifest (AC: 4, 6)
  - [ ] 4.1 Create `manifest.json`
  - [ ] 4.2 Add app icons (multiple sizes)
  - [ ] 4.3 Configure theme colors
  - [ ] 4.4 Configure display mode (standalone)
  - [ ] 4.5 Add splash screen configuration

- [ ] Task 5: Implement service worker (AC: 5)
  - [ ] 5.1 Create service worker
  - [ ] 5.2 Cache app shell (HTML, CSS, JS)
  - [ ] 5.3 Implement offline fallback page
  - [ ] 5.4 Configure cache strategies

- [ ] Task 6: Handle iOS Safari (AC: 7)
  - [ ] 6.1 Add viewport meta tags
  - [ ] 6.2 Handle safe area insets (notch)
  - [ ] 6.3 Handle keyboard viewport resize
  - [ ] 6.4 Test on iOS Safari

- [ ] Task 7: Handle Android Chrome (AC: 8)
  - [ ] 7.1 Implement beforeinstallprompt handler
  - [ ] 7.2 Add install button/prompt UI
  - [ ] 7.3 Test install flow

- [ ] Task 8: Handle landscape (AC: 9)
  - [ ] 8.1 Test landscape orientation
  - [ ] 8.2 Adjust layout for landscape
  - [ ] 8.3 Ensure chat is usable in landscape

- [ ] Task 9: Optimize assets (AC: 10, 12)
  - [ ] 9.1 Implement responsive images (srcset)
  - [ ] 9.2 Compress images
  - [ ] 9.3 Lazy load non-critical images
  - [ ] 9.4 Minimize initial bundle size

## Dev Notes

### PWA Manifest

```json
// public/manifest.json
{
  "name": "Annie - AI Companion",
  "short_name": "Annie",
  "description": "Your personal AI companion",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#0F0F0F",
  "theme_color": "#7C3AED",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png"
    },
    {
      "src": "/icons/icon-maskable.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ]
}
```

### Viewport Meta Tags

```html
<!-- index.html -->
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
```

### Safe Area Handling

```css
/* Handle notch and home indicator */
.layout {
  padding-top: env(safe-area-inset-top);
  padding-bottom: env(safe-area-inset-bottom);
  padding-left: env(safe-area-inset-left);
  padding-right: env(safe-area-inset-right);
}

.input-area {
  padding-bottom: calc(env(safe-area-inset-bottom) + 8px);
}
```

### Service Worker

```typescript
// public/sw.js
const CACHE_NAME = 'annie-v1';
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/assets/index.js',
  '/assets/index.css',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
});

self.addEventListener('fetch', (event) => {
  // Network-first for API calls
  if (event.request.url.includes('/api/')) {
    return;
  }

  // Cache-first for static assets
  event.respondWith(
    caches.match(event.request).then((response) => {
      return response || fetch(event.request);
    })
  );
});
```

### Swipe Gesture Hook

```typescript
const useSwipeGesture = (onSwipeLeft: () => void, onSwipeRight: () => void) => {
  const touchStart = useRef<number | null>(null);

  const handleTouchStart = (e: TouchEvent) => {
    touchStart.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e: TouchEvent) => {
    if (touchStart.current === null) return;

    const touchEnd = e.changedTouches[0].clientX;
    const diff = touchStart.current - touchEnd;

    if (Math.abs(diff) > 50) {
      if (diff > 0) {
        onSwipeLeft();
      } else {
        onSwipeRight();
      }
    }

    touchStart.current = null;
  };

  return { handleTouchStart, handleTouchEnd };
};
```

### Android Install Prompt

```typescript
const [deferredPrompt, setDeferredPrompt] = useState<any>(null);

useEffect(() => {
  const handler = (e: Event) => {
    e.preventDefault();
    setDeferredPrompt(e);
  };

  window.addEventListener('beforeinstallprompt', handler);
  return () => window.removeEventListener('beforeinstallprompt', handler);
}, []);

const handleInstall = async () => {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  if (outcome === 'accepted') {
    setDeferredPrompt(null);
  }
};
```

### Touch Target Guidelines

```css
/* Minimum touch targets */
.touch-target {
  min-width: 48px;
  min-height: 48px;
  padding: 12px;
}

/* Adequate spacing */
.button-group {
  gap: 8px; /* Minimum 8px between targets */
}
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.12]
- [PWA Documentation](https://web.dev/progressive-web-apps/)
- [iOS Safari Viewport](https://webkit.org/blog/7929/designing-websites-for-iphone-x/)

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
