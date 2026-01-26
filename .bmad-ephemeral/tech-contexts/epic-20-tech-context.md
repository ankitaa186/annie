# Epic 20: Annie Web UI - Technical Context

> **Epic ID**: 20
> **Status**: Contexted
> **Generated**: 2026-01-26
> **PRD**: docs/epics/epic-20-web-ui.md
> **Architecture**: CLAUDE.md + Brainstorming Session

---

## 1. Overview

### 1.1 Epic Objectives

Build a responsive web application for Annie that overcomes Telegram limitations and provides a richer experience:

| Objective | Description |
|-----------|-------------|
| **Multi-platform access** | Web/mobile accessibility without Telegram dependency |
| **Rich interactions** | Animated avatar, thinking indicators, tool call visibility |
| **Multimodal I/O** | Text, voice input, file upload; voice AND text output |
| **Transparency** | Health status indicators, active LLM display, thinking states |
| **Shared identity** | Same user across Telegram and Web via Cloudflare Access auth |

### 1.2 Scope Boundaries

**In Scope (V1)**:
- Core chat interface (messages, streaming, input)
- Health status and LLM indicators
- Conversation management (list, switch, delete)
- SSE streaming integration
- Thinking/tool call display
- Cloudflare Access authentication
- Backend API extensions for conversations
- Docker deployment

**Out of Scope (V2/V3)**:
- Voice input/output (Stories 20.9-20.10)
- Animated Annie avatar (Story 20.11)
- Mobile PWA (Story 20.12)
- Memory browser (Story 20.16)
- Tool calling UI (Story 20.17)
- Proactive trigger notifications (Story 20.18)

---

## 2. Architecture Alignment

### 2.1 Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Framework** | Vite + React 18 | Simple, fast builds, no SSR complexity needed for SPA |
| **UI Components** | shadcn/ui + Tailwind CSS | Full control, copy-paste components, unique Annie identity |
| **State Management** | Zustand | Lightweight, simple mental model |
| **Real-time** | Custom SSE hook | Annie's `/api/stream/{id}` format, no adapter needed |
| **Authentication** | Cloudflare Access | Already configured at annie.memoryforge.io with Google Auth |
| **Deployment** | Docker + Nginx | Fits existing infrastructure |

### 2.2 Integration Points

#### 2.2.1 Backend API (Existing)

```
POST /api/chat
├── Request: { user_id, platform, message, files? }
└── Response: { conversation_id, status, stream_url, timestamp }

GET /api/stream/{conversation_id}
├── SSE Events:
│   ├── { type: "status", message: "Annie is thinking..." }
│   ├── { type: "token", content: "..." }
│   ├── { type: "tool_call", name: "...", args: {...} }
│   ├── { type: "tool_result", ... }
│   ├── { type: "done", tokens_used: {...} }
│   └── { type: "error", message: "...", code: "..." }
└── Headers: Cache-Control: no-cache, X-Accel-Buffering: no

GET /health/full
└── Response: { status, components: { mcp_server, redis, llm_api, ... } }
```

#### 2.2.2 Backend API (New - Story 20.14)

```
GET /api/conversations
├── Response: [{ id, title, created_at, updated_at, last_message_preview }]
└── Auth: Cloudflare Access JWT → user_id mapping

POST /api/conversations
├── Request: (empty - creates new conversation)
└── Response: { id, title, created_at }

GET /api/conversations/{id}
├── Response: { id, title, messages: [...], created_at, updated_at }
└── Pagination: ?page=1&limit=50

DELETE /api/conversations/{id}
└── Response: { status: "deleted" }

PATCH /api/conversations/{id}
├── Request: { title: "New Title" }
└── Response: { id, title, updated_at }
```

#### 2.2.3 Authentication Flow

```
User → annie.memoryforge.io
         │
         ▼
┌─────────────────────────┐
│ Cloudflare Access       │
│ (Google OAuth)          │
└─────────────────────────┘
         │
         ▼ CF-Access-JWT-Assertion header
┌─────────────────────────┐
│ Backend Middleware      │
│ Extract email from JWT  │
│ Map: email → user_id    │
└─────────────────────────┘
         │
         ▼
user@example.com → YOUR_USER_ID
```

### 2.3 Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      WEB CLIENT                              │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ Zustand     │    │ useStream   │    │ useHealth   │     │
│  │ Store       │    │ Hook        │    │ Hook        │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │              │
│         │    POST /api/chat │                  │              │
│         │◄─────────────────►│                  │              │
│         │                  │    GET /health   │              │
│         │    GET /api/stream│◄────────────────►│              │
│         │◄─────────────────►│                  │              │
└─────────────────────────────────────────────────────────────┘
                             │
                             ▼ HTTP/SSE
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND API                               │
├─────────────────────────────────────────────────────────────┤
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐     │
│  │ chat.py     │    │ stream.py   │    │ main.py     │     │
│  │ /api/chat   │    │ /api/stream │    │ /health     │     │
│  └─────────────┘    └─────────────┘    └─────────────┘     │
│         │                  │                  │              │
│         ▼                  ▼                  │              │
│  ┌─────────────┐    ┌─────────────┐          │              │
│  │ Redis       │    │ LLM Client  │          │              │
│  │ (Sessions)  │    │ (Gemini)    │          │              │
│  └─────────────┘    └─────────────┘          │              │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Design

### 3.1 Directory Structure

```
annie/
├── web/                           # NEW - Epic 20
│   ├── src/
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── Sidebar.tsx
│   │   │   │   ├── MainContent.tsx
│   │   │   │   └── Layout.tsx
│   │   │   ├── chat/
│   │   │   │   ├── MessageThread.tsx
│   │   │   │   ├── UserMessage.tsx
│   │   │   │   ├── AnnieMessage.tsx
│   │   │   │   ├── InputArea.tsx
│   │   │   │   ├── FileUpload.tsx
│   │   │   │   ├── StreamingMessage.tsx
│   │   │   │   ├── ThinkingIndicator.tsx
│   │   │   │   └── ToolCallCard.tsx
│   │   │   ├── conversations/
│   │   │   │   ├── ConversationList.tsx
│   │   │   │   └── ConversationItem.tsx
│   │   │   └── status/
│   │   │       ├── HealthIndicator.tsx
│   │   │       └── LLMIndicator.tsx
│   │   ├── lib/
│   │   │   ├── api/
│   │   │   │   ├── client.ts          # HTTP client with CF headers
│   │   │   │   └── streamClient.ts    # SSE client
│   │   │   ├── hooks/
│   │   │   │   ├── useChat.ts
│   │   │   │   ├── useStream.ts
│   │   │   │   ├── useConversations.ts
│   │   │   │   └── useHealth.ts
│   │   │   └── stores/
│   │   │       └── appStore.ts        # Zustand store
│   │   ├── pages/
│   │   │   └── ChatPage.tsx
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css                  # Tailwind imports
│   ├── public/
│   │   └── favicon.ico
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   ├── tsconfig.json
│   ├── Dockerfile
│   └── nginx.conf                     # SPA routing
├── backend/
│   └── api/
│       ├── middleware/
│       │   └── cloudflare_auth.py     # NEW - Story 20.13
│       └── routes/
│           └── conversations.py       # NEW - Story 20.14
└── docker-compose.yml                 # UPDATE - add web service
```

### 3.2 Key Components

#### 3.2.1 Zustand Store (`appStore.ts`)

```typescript
interface AppState {
  // Conversations
  conversations: Conversation[];
  activeConversationId: string | null;

  // Messages
  messages: Record<string, Message[]>;
  streamingMessage: string | null;

  // UI State
  sidebarOpen: boolean;
  annieState: 'idle' | 'thinking' | 'speaking' | 'tool_calling';
  activeTool: string | null;

  // Health
  health: {
    backend: 'ok' | 'degraded' | 'unavailable';
    mcp: 'ok' | 'degraded' | 'unavailable';
    redis: 'ok' | 'degraded' | 'unavailable';
    memories: 'ok' | 'degraded' | 'unavailable';
  };
  activeLLM: string;

  // Actions
  setActiveConversation: (id: string | null) => void;
  addMessage: (conversationId: string, message: Message) => void;
  setStreamingMessage: (content: string | null) => void;
  setAnnieState: (state: AppState['annieState']) => void;
  updateHealth: (health: AppState['health']) => void;
}
```

#### 3.2.2 SSE Stream Hook (`useStream.ts`)

```typescript
export function useStream(conversationId: string | null) {
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const eventSourceRef = useRef<EventSource | null>(null);
  const { addMessage, setStreamingMessage, setAnnieState } = useAppStore();

  useEffect(() => {
    if (!conversationId) return;

    const eventSource = new EventSource(`/api/stream/${conversationId}`);
    eventSourceRef.current = eventSource;

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);

      switch (data.type) {
        case 'status':
          // Update thinking indicator
          setAnnieState('thinking');
          break;
        case 'token':
          // Append to streaming message
          setStreamingMessage(prev => (prev || '') + data.content);
          setAnnieState('speaking');
          break;
        case 'tool_call':
          // Show tool call card
          setAnnieState('tool_calling');
          break;
        case 'done':
          // Finalize message
          setAnnieState('idle');
          setStreamingMessage(null);
          break;
        case 'error':
          setError(data.message);
          setAnnieState('idle');
          break;
      }
    };

    eventSource.onerror = () => {
      setIsConnected(false);
      // Auto-reconnect with exponential backoff
    };

    return () => {
      eventSource.close();
    };
  }, [conversationId]);

  return { isConnected, error };
}
```

#### 3.2.3 Cloudflare Auth Middleware (`cloudflare_auth.py`)

```python
"""
Cloudflare Access Authentication Middleware

Extracts user identity from Cloudflare Access JWT and maps to Annie user_id.
No frontend auth logic needed - Cloudflare handles login before requests reach Annie.
"""

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from api.logging import get_logger

logger = get_logger(__name__)

# Email to Telegram user_id mapping
# Future: Move to database or config file for dynamic management
USER_MAPPING = {
    "user@example.com": "YOUR_USER_ID",
}


async def cloudflare_auth_middleware(request: Request, call_next):
    """
    Extract user identity from Cloudflare Access JWT.

    Headers provided by Cloudflare Access:
    - CF-Access-JWT-Assertion: Contains signed JWT with user email
    - CF-Access-Authenticated-User-Email: Direct email header (backup)

    Maps email to internal user_id for consistent identity across
    Telegram bot and Web UI.
    """
    # Skip auth for health checks and static assets
    if request.url.path.startswith("/health"):
        return await call_next(request)
    if request.url.path.startswith("/assets"):
        return await call_next(request)

    # Extract Cloudflare Access JWT
    cf_jwt = request.headers.get("CF-Access-JWT-Assertion")

    if cf_jwt:
        try:
            # Decode JWT (signature verification optional - CF already verified)
            # Note: In production, verify signature with Cloudflare's public key
            payload = jwt.decode(cf_jwt, options={"verify_signature": False})
            email = payload.get("email")

            if email:
                user_id = USER_MAPPING.get(email)

                if user_id:
                    # Attach user_id to request state for route handlers
                    request.state.user_id = user_id
                    request.state.email = email

                    logger.info(
                        "Cloudflare auth successful",
                        extra={
                            "email": email,
                            "user_id": user_id,
                            "path": request.url.path
                        }
                    )

                    return await call_next(request)
                else:
                    logger.warning(
                        "Unknown email - not in USER_MAPPING",
                        extra={"email": email, "path": request.url.path}
                    )
        except jwt.DecodeError as e:
            logger.warning(
                "Failed to decode CF JWT",
                extra={"error": str(e), "path": request.url.path}
            )

    # Fallback: Check direct email header
    cf_email = request.headers.get("CF-Access-Authenticated-User-Email")
    if cf_email:
        user_id = USER_MAPPING.get(cf_email)
        if user_id:
            request.state.user_id = user_id
            request.state.email = cf_email
            return await call_next(request)

    # No valid authentication
    logger.warning(
        "Unauthorized request - no valid CF headers",
        extra={"path": request.url.path}
    )

    return JSONResponse(
        status_code=401,
        content={"detail": "Unauthorized - Cloudflare Access required"}
    )
```

### 3.3 SSE Event Handling

The web UI must handle the same SSE event types already produced by the backend:

| Event Type | Backend Source | Web UI Handler |
|------------|----------------|----------------|
| `status` | `emit_status()` calls in stream.py | Update `ThinkingIndicator` with message |
| `token` | `stream_chat_completion()` yields | Append to `StreamingMessage` |
| `tool_call` | Tool execution in stream_generator | Show `ToolCallCard` with tool name |
| `tool_result` | After `mcp_client.call_tool()` | Update `ToolCallCard` with result |
| `done` | Stream completion | Finalize message, clear streaming state |
| `error` | Exception handlers | Show error toast, allow retry |

### 3.4 Tool Call Display Mapping

```typescript
const TOOL_DISPLAY_NAMES: Record<string, { label: string; icon: string }> = {
  'web_search': { label: 'Searching the web...', icon: '🔍' },
  'web_crawl': { label: 'Reading webpage...', icon: '📄' },
  'retrieve_memories': { label: 'Remembering...', icon: '🧠' },
  'store_memory': { label: 'Saving to memory...', icon: '💾' },
  'get_portfolio': { label: 'Checking portfolio...', icon: '📊' },
  'get_portfolio_summary': { label: 'Analyzing portfolio...', icon: '📈' },
  'home_assistant_query': { label: 'Checking smart home...', icon: '🏠' },
  'home_assistant_control': { label: 'Controlling device...', icon: '🎮' },
  'reddit_search': { label: 'Searching Reddit...', icon: '🔴' },
  'get_user_profile': { label: 'Loading your profile...', icon: '👤' },
  'update_user_profile': { label: 'Updating profile...', icon: '✏️' },
};
```

---

## 4. Non-Functional Requirements

### 4.1 Performance (Relaxed Targets)

Annie is a thinking machine - performance targets prioritize quality over speed:

| Metric | Target | Measurement |
|--------|--------|-------------|
| First Contentful Paint | <3s | Lighthouse audit |
| Time to Interactive | <5s | Lighthouse audit |
| Bundle Size (initial) | <500KB | Build output |
| SSE Connection Time | <1s | Network timing |
| Health Poll Interval | 30s | Config constant |

### 4.2 Browser Support

| Browser | Version | Status |
|---------|---------|--------|
| Chrome | 90+ | Full support |
| Firefox | 90+ | Full support |
| Safari | 14+ | Full support |
| Edge | 90+ | Full support |
| Mobile Safari | iOS 14+ | Full support |
| Mobile Chrome | Android 10+ | Full support |

### 4.3 Accessibility

- WCAG 2.1 Level AA compliance
- Proper ARIA labels on interactive elements
- Keyboard navigation support
- Reduced motion support (`prefers-reduced-motion`)
- Screen reader compatibility

---

## 5. Dependencies

### 5.1 NPM Packages (web/)

```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "zustand": "^4.4.0",
    "@radix-ui/react-dialog": "^1.0.0",
    "@radix-ui/react-dropdown-menu": "^2.0.0",
    "@radix-ui/react-scroll-area": "^1.0.0",
    "@radix-ui/react-tooltip": "^1.0.0",
    "clsx": "^2.0.0",
    "tailwind-merge": "^2.0.0",
    "lucide-react": "^0.294.0",
    "react-markdown": "^9.0.0",
    "react-syntax-highlighter": "^15.5.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "tailwindcss": "^3.3.0",
    "autoprefixer": "^10.4.0",
    "postcss": "^8.4.0",
    "@types/react": "^18.2.0",
    "@types/react-dom": "^18.2.0",
    "eslint": "^8.55.0",
    "prettier": "^3.1.0"
  }
}
```

### 5.2 Python Packages (backend/)

```
# Story 20.13 - Cloudflare Auth
pyjwt>=2.8.0
```

### 5.3 External Dependencies

| Service | Required | Purpose |
|---------|----------|---------|
| Cloudflare Access | Yes | Authentication (already configured) |
| Backend API | Yes | Chat, streaming, conversations |
| Redis | Yes | Session storage |

---

## 6. Acceptance Criteria

### 6.1 Story-Level Criteria

#### Story 20.1: Project Setup
- [ ] `npm run dev` starts development server on port 3000
- [ ] `npm run build` produces production bundle
- [ ] Tailwind CSS classes work correctly
- [ ] shadcn/ui components render correctly
- [ ] Docker build succeeds
- [ ] Docker Compose integration works

#### Story 20.2: Layout & Navigation
- [ ] Two-column layout (sidebar + main) on desktop
- [ ] Sidebar collapses to hamburger on mobile (<768px)
- [ ] Header shows Annie logo, health dots, LLM indicator
- [ ] Dark mode follows system preference
- [ ] Smooth transitions between layouts

#### Story 20.3: Health Status
- [ ] Health dots update every 30 seconds
- [ ] Tooltip shows component status on hover
- [ ] LLM indicator shows active provider name
- [ ] Degraded services show yellow/red indicators

#### Story 20.4: Conversation Management
- [ ] Conversations grouped by date
- [ ] Click switches active conversation
- [ ] New conversation button creates empty chat
- [ ] Delete shows confirmation dialog
- [ ] Rename via inline edit

#### Story 20.5: Message Display
- [ ] User messages right-aligned, distinct style
- [ ] Annie messages left-aligned with avatar placeholder
- [ ] Markdown rendering (headers, code, lists, links)
- [ ] File attachments displayed appropriately
- [ ] Auto-scroll to bottom on new message

#### Story 20.6: Input & Sending
- [ ] Auto-expanding textarea (max 6 lines)
- [ ] Send on Enter, Shift+Enter for newline
- [ ] File upload with drag-and-drop
- [ ] File type/size validation
- [ ] Loading state during send

#### Story 20.7: SSE Streaming
- [ ] Connect to `/api/stream/{id}` SSE endpoint
- [ ] Display tokens as they arrive
- [ ] Handle all event types (status, token, tool_call, tool_result, done, error)
- [ ] Auto-reconnect on disconnect
- [ ] Cancel button for ongoing stream

#### Story 20.8: Thinking & Tool Calls
- [ ] Thinking indicator shows during status events
- [ ] Tool call cards show friendly names
- [ ] Tool cards show success/failure state
- [ ] Smooth transitions between states

#### Story 20.13: Cloudflare Auth
- [ ] Middleware extracts email from CF JWT
- [ ] Email maps to user_id correctly
- [ ] Unknown emails rejected with 401
- [ ] Health endpoints bypass auth
- [ ] Audit log on successful auth

#### Story 20.14: Backend API Extensions
- [ ] GET /api/conversations returns user's conversations
- [ ] POST /api/conversations creates new conversation
- [ ] DELETE /api/conversations/{id} deletes conversation
- [ ] PATCH /api/conversations/{id} updates title
- [ ] CORS configured for web domain

#### Story 20.15: Integration & Polish
- [ ] E2E tests pass (Playwright)
- [ ] Cross-browser testing complete
- [ ] Lighthouse score >70
- [ ] Error boundaries implemented
- [ ] Loading states for all async operations

---

## 7. Traceability Matrix

| PRD Requirement | Story | Files | Test Coverage |
|-----------------|-------|-------|---------------|
| Platform access | 20.1 | web/Dockerfile, docker-compose.yml | E2E |
| Health indicators | 20.3 | HealthIndicator.tsx, useHealth.ts | Unit + E2E |
| LLM indicator | 20.3 | LLMIndicator.tsx | Unit |
| Conversation sidebar | 20.2, 20.4 | Sidebar.tsx, ConversationList.tsx | Unit + E2E |
| Message display | 20.5 | MessageThread.tsx, AnnieMessage.tsx | Unit |
| Message input | 20.6 | InputArea.tsx, FileUpload.tsx | Unit + E2E |
| SSE streaming | 20.7 | useStream.ts, streamClient.ts | Unit + Integration |
| Thinking indicator | 20.8 | ThinkingIndicator.tsx | Unit |
| Tool call display | 20.8 | ToolCallCard.tsx | Unit |
| Authentication | 20.13 | cloudflare_auth.py | Unit + Integration |
| Conversation API | 20.14 | conversations.py | Unit + Integration |
| File upload | 20.6 | FileUpload.tsx, backend files | E2E |
| Cross-client sync | 20.14 | conversations.py, Redis | Integration |

---

## 8. Risks and Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| SSE connection drops | Medium | Low | Auto-reconnect with exponential backoff, persist partial messages |
| Cloudflare JWT decoding issues | High | Low | Fallback to email header, comprehensive logging |
| Large conversation lists | Low | Medium | Virtual scrolling, pagination |
| Cross-client message sync | Medium | Medium | V1: Manual refresh. V2: WebSocket for live sync |
| Mobile viewport issues | Medium | Medium | Thorough testing, viewport meta tags |
| Bundle size growth | Low | Medium | Code splitting, lazy loading |

---

## 9. Test Strategy

### 9.1 Unit Tests

- **Components**: Jest + React Testing Library
- **Hooks**: Jest with mock EventSource
- **Stores**: Zustand testing patterns
- **Backend Middleware**: pytest with mock JWT

### 9.2 Integration Tests

- **SSE Streaming**: Real EventSource connection to test backend
- **Conversations API**: pytest with test Redis
- **Auth Flow**: Mock Cloudflare headers

### 9.3 E2E Tests

- **Framework**: Playwright
- **Scenarios**:
  - Send message and receive streamed response
  - File upload flow
  - Conversation switching
  - New conversation creation
  - Error handling and recovery

---

## 10. Story Sequence

### Phase 1: Foundation (Stories 20.1, 20.13, 20.14)
1. **20.1** Project Setup & Infrastructure
2. **20.13** Cloudflare Access Integration
3. **20.14** Backend API Extensions

### Phase 2: Core UI (Stories 20.2, 20.3, 20.4, 20.5, 20.6)
4. **20.2** Layout & Navigation Shell
5. **20.3** Health Status & System Indicators
6. **20.4** Conversation List & Management
7. **20.5** Chat Interface - Message Display
8. **20.6** Chat Interface - Input & Sending

### Phase 3: Streaming (Stories 20.7, 20.8, 20.15)
9. **20.7** SSE Streaming Integration
10. **20.8** Thinking & Tool Call Display
11. **20.15** Integration Testing & Polish

### V2 (Future)
- **20.9** Voice Input
- **20.10** Voice Output
- **20.11** Animated Avatar
- **20.12** Mobile PWA
- **20.16-20.18** Debug/Admin Tools
