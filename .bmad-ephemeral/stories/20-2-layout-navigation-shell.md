# Story 20.2: Layout & Navigation Shell

Status: review

## Story

As a user,
I want a responsive two-column layout with header, sidebar, and main content area,
so that I can navigate Annie's interface intuitively across desktop and mobile devices.

## Acceptance Criteria

1. Responsive two-column layout (sidebar + main content) on desktop (>1024px)
2. Sidebar collapses to hamburger menu on mobile (<768px)
3. Collapsed sidebar shows icons only on tablet (768-1024px)
4. Header displays Annie logo/name on the left
5. Header shows health status indicators (placeholder for Story 20.3)
6. Header shows current LLM indicator (placeholder for Story 20.3)
7. Sidebar contains conversation list area (placeholder for Story 20.4)
8. Sidebar has "New Conversation" button with + icon
9. Sidebar has Memory Browser link (V2 placeholder, disabled)
10. Sidebar has Tools link (V3 placeholder, disabled)
11. Main content area renders chat interface (placeholder for Story 20.5)
12. Dark mode support following system preference
13. Smooth transitions and animations between layout states
14. Proper ARIA labels for accessibility
15. Keyboard navigation support (Tab, Enter, Escape)

## Tasks / Subtasks

- [x] Task 1: Create Layout component structure (AC: 1, 2, 3)
  - [x] 1.1 Create `web/src/components/layout/Layout.tsx`
  - [x] 1.2 Implement responsive grid/flex layout
  - [x] 1.3 Add breakpoint-based layout switching
  - [x] 1.4 Create layout context for sidebar state

- [x] Task 2: Build Header component (AC: 4, 5, 6)
  - [x] 2.1 Create `web/src/components/layout/Header.tsx`
  - [x] 2.2 Add Annie logo/name with styling
  - [x] 2.3 Add placeholder slots for health indicators
  - [x] 2.4 Add placeholder slot for LLM indicator
  - [x] 2.5 Add hamburger menu button for mobile

- [x] Task 3: Build Sidebar component (AC: 7, 8, 9, 10)
  - [x] 3.1 Create `web/src/components/layout/Sidebar.tsx`
  - [x] 3.2 Add conversation list container area
  - [x] 3.3 Implement "New Conversation" button
  - [x] 3.4 Add Memory Browser link (disabled, V2 badge)
  - [x] 3.5 Add Tools link (disabled, V3 badge)
  - [x] 3.6 Implement collapse/expand animation

- [x] Task 4: Build MainContent component (AC: 11)
  - [x] 4.1 Create `web/src/components/layout/MainContent.tsx`
  - [x] 4.2 Add chat area placeholder
  - [x] 4.3 Ensure proper scrolling behavior

- [x] Task 5: Implement dark mode (AC: 12)
  - [x] 5.1 Configure Tailwind dark mode (class strategy)
  - [x] 5.2 Add system preference detection
  - [x] 5.3 Apply dark mode styles to all components
  - [x] 5.4 Store preference in localStorage

- [x] Task 6: Add animations and transitions (AC: 13)
  - [x] 6.1 Sidebar slide animation
  - [x] 6.2 Layout transition on breakpoint change
  - [x] 6.3 Button hover/active states
  - [x] 6.4 Respect `prefers-reduced-motion`

- [x] Task 7: Implement accessibility (AC: 14, 15)
  - [x] 7.1 Add ARIA labels to navigation elements
  - [x] 7.2 Implement keyboard navigation
  - [x] 7.3 Add focus indicators
  - [x] 7.4 Test with screen reader

- [x] Task 8: Create ChatPage and routing
  - [x] 8.1 Create `web/src/pages/ChatPage.tsx`
  - [x] 8.2 Set up React Router
  - [x] 8.3 Configure default route to ChatPage

## Dev Notes

### Layout Structure

```
┌─────────────────────────────────────────────────────────────────────────┐
│ HEADER                                                                   │
│ ┌─────────────┐  ┌──────────────────────┐  ┌─────────────────┐          │
│ │ Annie Logo  │  │ Health: 🟢🟢🟢        │  │ LLM: Gemini 2.0 │          │
│ └─────────────┘  └──────────────────────┘  └─────────────────┘          │
├─────────────────────────────────────────────────────────────────────────┤
│ ┌──────────────────┐  ┌────────────────────────────────────────────┐    │
│ │ SIDEBAR          │  │ MAIN CONTENT                                │    │
│ │                  │  │                                             │    │
│ │ [+ New Chat]     │  │  (Chat interface placeholder)               │    │
│ │                  │  │                                             │    │
│ │ Conversations    │  │                                             │    │
│ │ ├─ Today         │  │                                             │    │
│ │ │  └─ Chat 1     │  │                                             │    │
│ │ └─ Yesterday     │  │                                             │    │
│ │                  │  │                                             │    │
│ │ ─────────────    │  │                                             │    │
│ │ 🧠 Memory (V2)   │  │                                             │    │
│ │ 🔧 Tools (V3)    │  │                                             │    │
│ └──────────────────┘  └────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────┘
```

### Responsive Breakpoints

| Breakpoint | Width | Layout |
|------------|-------|--------|
| Mobile | <768px | Single column, hamburger menu |
| Tablet | 768-1024px | Collapsed sidebar (icons only) |
| Desktop | >1024px | Full two-column layout |

### Component Hierarchy

```
App.tsx
└── Layout.tsx
    ├── Header.tsx
    │   ├── Logo
    │   ├── HealthIndicator (placeholder)
    │   └── LLMIndicator (placeholder)
    ├── Sidebar.tsx
    │   ├── NewConversationButton
    │   ├── ConversationList (placeholder)
    │   └── NavLinks (Memory, Tools)
    └── MainContent.tsx
        └── ChatPage.tsx (via React Router)
```

### Zustand Store Updates

```typescript
// Add to appStore.ts
interface LayoutState {
  sidebarOpen: boolean;
  sidebarCollapsed: boolean; // For tablet view
  darkMode: 'system' | 'light' | 'dark';

  toggleSidebar: () => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  setDarkMode: (mode: 'system' | 'light' | 'dark') => void;
}
```

### Dark Mode Implementation

```typescript
// Tailwind config
module.exports = {
  darkMode: 'class',
  // ...
}

// System preference detection
useEffect(() => {
  const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
  const handleChange = () => {
    if (darkMode === 'system') {
      document.documentElement.classList.toggle('dark', mediaQuery.matches);
    }
  };
  mediaQuery.addEventListener('change', handleChange);
  return () => mediaQuery.removeEventListener('change', handleChange);
}, [darkMode]);
```

### Color Palette (from Epic)

| Element | Light Mode | Dark Mode |
|---------|------------|-----------|
| Background | #FFFFFF | #0F0F0F |
| Sidebar | #F5F5F5 | #1A1A1A |
| Accent | #7C3AED | #A78BFA |

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.2]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-3.2]
- [Source: docs/epics/epic-20-web-ui.md#Section-9.2-Color-Palette]

## Dev Agent Record

### Context Reference

- .bmad-ephemeral/stories/20-2-layout-navigation-shell.context.xml

### Agent Model Used

- Claude Opus 4.5 (claude-opus-4-5-20251101)

### Debug Log References

- Implementation started with Zustand store for layout state management
- Created responsive breakpoint hooks (useMediaQuery, useIsMobile, useIsTablet, useIsDesktop)
- Implemented dark mode with system preference detection and localStorage persistence
- Built Layout, Header, Sidebar, MainContent components with responsive behavior
- Added ARIA labels, keyboard navigation (Escape to close sidebar), focus indicators
- Tailwind animations with prefers-reduced-motion support

### Completion Notes List

- All 8 tasks completed successfully
- Responsive layout works at three breakpoints: mobile (<768px), tablet (768-1024px), desktop (>1024px)
- Mobile: hamburger menu toggles sidebar overlay
- Tablet: sidebar shows icons only with tooltips
- Desktop: full sidebar visible
- Dark mode: cycles through system/light/dark with header toggle button
- Animations respect prefers-reduced-motion media query
- Accessibility: comprehensive ARIA labels, role attributes, keyboard support

### File List

**New Files:**
- web/src/components/layout/Layout.tsx
- web/src/components/layout/Header.tsx
- web/src/components/layout/Sidebar.tsx
- web/src/components/layout/MainContent.tsx
- web/src/components/layout/index.ts
- web/src/components/ui/scroll-area.tsx
- web/src/components/ui/tooltip.tsx
- web/src/lib/stores/appStore.ts
- web/src/hooks/useMediaQuery.ts
- web/src/hooks/useDarkMode.ts
- web/src/hooks/index.ts
- web/src/pages/ChatPage.tsx
- web/src/types/index.ts

**Modified Files:**
- web/src/App.tsx (updated to use Layout and routing)
- web/src/index.css (added reduced motion styles, scroll utilities)
- web/tailwind.config.js (added slide animations)

### Change Log

- 2026-01-26: Story 20-2 implementation complete - Layout & Navigation Shell with responsive design, dark mode, and accessibility features
