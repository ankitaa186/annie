# Story 20.18: Proactive Trigger Notifications

Status: drafted

## Story

As a user,
I want to be notified when Annie has something to tell me proactively,
so that I don't miss important insights or reminders even when I'm not actively chatting.

## Acceptance Criteria

1. Toast notification when proactive trigger fires (user on page)
2. Avatar animation when Annie wants to talk
3. Browser push notification when tab is in background (if permitted)
4. Notification permission request flow
5. Notification badge on browser tab
6. "Annie wants to talk" indicator in UI
7. Notification history panel
8. Sound toggle for alert sound (optional, off by default)
9. Queue notifications when tab closed (show on next visit)
10. Integration with Epic 13 trigger infrastructure

## Tasks / Subtasks

- [ ] Task 1: Create notification service
  - [ ] 1.1 Create `web/src/lib/notifications/notificationService.ts`
  - [ ] 1.2 Handle toast notifications
  - [ ] 1.3 Handle browser push notifications
  - [ ] 1.4 Handle notification permissions

- [ ] Task 2: Implement permission request flow
  - [ ] 2.1 Create permission request UI
  - [ ] 2.2 Handle permission states
  - [ ] 2.3 Remember user preference

- [ ] Task 3: Create ProactiveNotification component
  - [ ] 3.1 Create toast for in-page notifications
  - [ ] 3.2 Trigger avatar animation
  - [ ] 3.3 Add "Annie wants to talk" badge

- [ ] Task 4: Implement browser notifications
  - [ ] 4.1 Request Notification permission
  - [ ] 4.2 Send push notification when tab hidden
  - [ ] 4.3 Handle notification click (focus tab)

- [ ] Task 5: Add tab badge
  - [ ] 5.1 Update document.title with badge
  - [ ] 5.2 Use favicon with badge indicator

- [ ] Task 6: Create notification history
  - [ ] 6.1 Create NotificationHistory component
  - [ ] 6.2 Store recent notifications
  - [ ] 6.3 Show unread count

- [ ] Task 7: Add sound option
  - [ ] 7.1 Add notification sound asset
  - [ ] 7.2 Sound toggle in settings
  - [ ] 7.3 Play on notification (if enabled)

- [ ] Task 8: Queue for offline
  - [ ] 8.1 Store pending notifications in localStorage
  - [ ] 8.2 Show on next visit
  - [ ] 8.3 Clear after shown

- [ ] Task 9: Connect to Epic 13 triggers
  - [ ] 9.1 Implement WebSocket/SSE for trigger events
  - [ ] 9.2 Parse trigger payload
  - [ ] 9.3 Display appropriate notification

## Dev Notes

### Epic 13 Integration

This story is the **web UI display layer** for Epic 13 (Proactive AI Worker). The trigger infrastructure already exists:
- Triggers stored in Redis by proactive worker
- Delivered via Telegram currently
- This story adds web delivery channel

### Notification Flow

```
Epic 13 Worker
     │
     ▼ Fires trigger
Redis (trigger queue)
     │
     ▼ Poll or WebSocket
Web UI
     │
     ├─► User Active on Page → Toast + Avatar animation
     ├─► Tab in Background → Browser Push Notification
     └─► Tab Closed → Queue for next visit
```

### Toast Notification

```tsx
import { toast } from 'sonner';

function showProactiveNotification(trigger: ProactiveTrigger) {
  toast.custom((t) => (
    <div className="flex items-center gap-3 bg-purple-50 dark:bg-purple-950 p-4 rounded-lg shadow-lg">
      <AnnieAvatar state="happy" size="sm" />
      <div>
        <p className="font-medium">Annie has something for you</p>
        <p className="text-sm text-gray-600">{trigger.preview}</p>
      </div>
      <button onClick={() => {
        toast.dismiss(t);
        handleTriggerClick(trigger);
      }}>
        View
      </button>
    </div>
  ));
}
```

### Browser Push Notification

```typescript
const requestNotificationPermission = async () => {
  if (!('Notification' in window)) {
    return 'unsupported';
  }

  if (Notification.permission === 'granted') {
    return 'granted';
  }

  if (Notification.permission !== 'denied') {
    const permission = await Notification.requestPermission();
    return permission;
  }

  return 'denied';
};

const sendPushNotification = (trigger: ProactiveTrigger) => {
  if (Notification.permission !== 'granted') return;

  new Notification('Annie', {
    body: trigger.preview,
    icon: '/icons/annie-notification.png',
    badge: '/icons/annie-badge.png',
    tag: trigger.id, // Prevents duplicates
  });
};
```

### Tab Badge

```typescript
// Update page title with notification count
const updateTitleBadge = (count: number) => {
  const baseTitle = 'Annie';
  document.title = count > 0 ? `(${count}) ${baseTitle}` : baseTitle;
};

// Favicon with badge
const updateFaviconBadge = (hasNotification: boolean) => {
  const favicon = document.querySelector('link[rel="icon"]');
  favicon.href = hasNotification
    ? '/icons/favicon-badge.png'
    : '/icons/favicon.png';
};
```

### "Annie Wants to Talk" UI

```tsx
function AnnieWantsToTalk({ trigger }: { trigger: ProactiveTrigger }) {
  return (
    <div className="fixed bottom-4 right-4 bg-white dark:bg-gray-900 rounded-lg shadow-xl p-4 max-w-sm animate-bounce-subtle">
      <div className="flex items-center gap-3">
        <AnnieAvatar state="happy" size="md" />
        <div>
          <p className="font-medium">Annie wants to talk! 💬</p>
          <p className="text-sm text-gray-600">{trigger.preview}</p>
        </div>
      </div>
      <div className="flex gap-2 mt-3">
        <button
          onClick={() => openConversation(trigger)}
          className="px-3 py-1 bg-purple-500 text-white rounded"
        >
          Chat Now
        </button>
        <button
          onClick={() => dismissTrigger(trigger)}
          className="px-3 py-1 text-gray-500"
        >
          Later
        </button>
      </div>
    </div>
  );
}
```

### Notification History

```tsx
function NotificationHistory() {
  const [notifications, setNotifications] = useState<ProactiveTrigger[]>([]);

  return (
    <div className="p-4">
      <h3 className="font-medium mb-4">Recent Notifications</h3>
      {notifications.length === 0 ? (
        <p className="text-gray-500">No recent notifications</p>
      ) : (
        <ul className="space-y-2">
          {notifications.map((n) => (
            <li key={n.id} className="p-2 bg-gray-50 rounded">
              <p className="text-sm">{n.preview}</p>
              <p className="text-xs text-gray-400">{formatTime(n.timestamp)}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

### Sound Notification

```typescript
const notificationSound = new Audio('/sounds/notification.mp3');

const playNotificationSound = () => {
  const soundEnabled = localStorage.getItem('annie-notification-sound') === 'true';
  if (soundEnabled) {
    notificationSound.play().catch(() => {
      // Autoplay blocked - user hasn't interacted yet
    });
  }
};
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.18]
- [Source: docs/design/proactive-ai-architecture.md]
- [Source: backend/api/proactive/telegram_delivery.py - Existing delivery]

## Dev Agent Record

### Context Reference

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
