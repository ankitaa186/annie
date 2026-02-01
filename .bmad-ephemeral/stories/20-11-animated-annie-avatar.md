# Story 20.11: Animated Annie Avatar

Status: drafted

## Story

As a user,
I want to see an animated anime avatar of Annie that reflects her current state,
so that Annie feels like a companion with presence rather than just text on a screen.

## Acceptance Criteria

1. Anime-style avatar design (placeholder or commissioned art)
2. Avatar displays next to Annie's messages
3. Idle state with gentle breathing/blinking animation
4. Thinking state with eyes looking up/around
5. Speaking state with mouth animation (simple loop)
6. Happy state with smile and sparkles for good news
7. Empathetic state with soft expression for emotional support
8. Surprised state with wide eyes for unexpected input
9. Smooth transitions between states
10. Mini avatar option in header
11. Configurable size (small for messages, large for sidebar)
12. Fallback to static image if animations fail
13. Reduced motion support for accessibility

## Tasks / Subtasks

- [ ] Task 1: Source or create avatar assets
  - [ ] 1.1 Design or commission anime avatar
  - [ ] 1.2 Create sprite sheets or Lottie animations
  - [ ] 1.3 Create assets for each state
  - [ ] 1.4 Optimize file sizes

- [ ] Task 2: Create AnnieAvatar component (AC: 2, 11)
  - [ ] 2.1 Create `web/src/components/avatar/AnnieAvatar.tsx`
  - [ ] 2.2 Support different sizes (sm, md, lg)
  - [ ] 2.3 Accept state prop for animation
  - [ ] 2.4 Render appropriate animation/image

- [ ] Task 3: Implement Lottie animations (AC: 3-8, 9)
  - [ ] 3.1 Install lottie-react
  - [ ] 3.2 Create animation wrapper component
  - [ ] 3.3 Implement idle animation
  - [ ] 3.4 Implement thinking animation
  - [ ] 3.5 Implement speaking animation
  - [ ] 3.6 Implement happy animation
  - [ ] 3.7 Implement empathetic animation
  - [ ] 3.8 Implement surprised animation
  - [ ] 3.9 Add transition logic between states

- [ ] Task 4: Create AvatarStates controller (AC: 9)
  - [ ] 4.1 Create `web/src/components/avatar/AvatarStates.tsx`
  - [ ] 4.2 Map annieState from Zustand to avatar state
  - [ ] 4.3 Handle state transitions smoothly

- [ ] Task 5: Integrate with messages (AC: 2)
  - [ ] 5.1 Add avatar to AnnieMessage component
  - [ ] 5.2 Connect to current Annie state
  - [ ] 5.3 Size appropriately for message context

- [ ] Task 6: Add header mini avatar (AC: 10)
  - [ ] 6.1 Add small avatar to header
  - [ ] 6.2 Reflect current state
  - [ ] 6.3 Make clickable (future: open settings)

- [ ] Task 7: Handle fallbacks (AC: 12, 13)
  - [ ] 7.1 Create static fallback images
  - [ ] 7.2 Detect animation failures
  - [ ] 7.3 Respect prefers-reduced-motion
  - [ ] 7.4 Show static image if reduced motion

## Dev Notes

### Avatar States

| State | Trigger | Animation |
|-------|---------|-----------|
| Idle | Default, no activity | Gentle breathing, occasional blink |
| Thinking | SSE `status` event | Eyes looking up/around, thinking pose |
| Speaking | SSE `token` events | Mouth movement loop |
| Happy | Positive response detected | Smile, sparkle effects |
| Empathetic | Emotional support context | Soft, caring expression |
| Surprised | Unexpected input | Wide eyes, raised eyebrows |

### Lottie Implementation

```typescript
import Lottie from 'lottie-react';
import idleAnimation from '../assets/avatar/idle.json';
import thinkingAnimation from '../assets/avatar/thinking.json';
// ... other animations

const ANIMATIONS = {
  idle: idleAnimation,
  thinking: thinkingAnimation,
  speaking: speakingAnimation,
  happy: happyAnimation,
  empathetic: empatheticAnimation,
  surprised: surprisedAnimation,
};

interface AnnieAvatarProps {
  state: keyof typeof ANIMATIONS;
  size?: 'sm' | 'md' | 'lg';
}

export function AnnieAvatar({ state, size = 'md' }: AnnieAvatarProps) {
  const prefersReducedMotion = useMediaQuery('(prefers-reduced-motion: reduce)');

  const sizeClasses = {
    sm: 'w-8 h-8',
    md: 'w-12 h-12',
    lg: 'w-24 h-24',
  };

  if (prefersReducedMotion) {
    return (
      <img
        src={`/avatar/static-${state}.png`}
        alt="Annie"
        className={cn('rounded-full', sizeClasses[size])}
      />
    );
  }

  return (
    <div className={cn('rounded-full overflow-hidden', sizeClasses[size])}>
      <Lottie
        animationData={ANIMATIONS[state]}
        loop={state !== 'surprised'}
        autoplay
      />
    </div>
  );
}
```

### State Mapping from Zustand

```typescript
// Map annieState to avatar state
function getAvatarState(annieState: string, messageContext?: string): AvatarState {
  switch (annieState) {
    case 'thinking':
      return 'thinking';
    case 'speaking':
      return 'speaking';
    case 'tool_calling':
      return 'thinking';
    default:
      // Could analyze message content for emotional states
      return 'idle';
  }
}
```

### CSS Transitions

```css
.avatar-container {
  transition: opacity 0.3s ease-in-out;
}

.avatar-transition-enter {
  opacity: 0;
}

.avatar-transition-enter-active {
  opacity: 1;
}

.avatar-transition-exit {
  opacity: 1;
}

.avatar-transition-exit-active {
  opacity: 0;
}
```

### Asset Requirements

For each state, need:
1. **Lottie JSON** - Primary animated version
2. **Static PNG** - Fallback for reduced motion
3. **Optimized size** - Keep animations under 100KB each

### Technical Options

| Option | Pros | Cons |
|--------|------|------|
| Lottie | Smooth, scalable, small files | Requires After Effects workflow |
| CSS Sprites | Simple, no dependencies | Less smooth, larger files |
| Canvas/WebGL | Most control | Complex, performance concerns |

**Recommendation**: Start with Lottie for quality, with static PNG fallbacks.

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.11]
- [Lottie Web](https://airbnb.io/lottie/#/web)
- [Source: docs/brainstorming-web-ui-2026-01-25.md#Annie-Perspective]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
