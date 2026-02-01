# Epic: Annie Web UI

> **Epic ID**: 20
> **Status**: Draft
> **Priority**: High
> **Estimated Effort**: 10-14 days
> **Dependencies**: Backend API (complete), File Context Sharing (Epic 18)

---

## 1. Overview

### 1.1 Problem Statement

Annie currently operates exclusively through Telegram, which creates several limitations:

- **Platform Lock-in**: Users must have Telegram installed and configured
- **Limited Rich Interactions**: Telegram's UI constraints limit how Annie can present information
- **No Voice Input**: Users can only type, not speak to Annie
- **No Visual Presence**: Annie has no visual identity - she's just text
- **Limited Transparency**: Users can't see system health, which LLM is active, or Annie's thinking state
- **No Memory Browsing**: Users can't explore what Annie remembers about them
- **Mobile Web Gap**: No responsive web option for quick access without app installation

### 1.2 Solution

Build a **responsive web application** that provides a richer Annie experience:

1. **Gemini-Inspired Layout**: Clean, proven two-column design (conversations + chat)
2. **Visual Identity**: Animated anime avatar that shows Annie's state (thinking, speaking, empathetic)
3. **Multimodal I/O**: Text, voice input, file upload; voice AND text output
4. **Transparency Layer**: Health status indicators, active LLM display, thinking states
5. **Extended Features**: Memory browser, tool calling visibility

### 1.3 Success Criteria

Annie is a thinking machine - performance targets are relaxed in favor of quality and functionality.

| Metric | Target | Rationale |
|--------|--------|-----------|
| First Contentful Paint | <3s | Acceptable for companion app |
| Time to Interactive | <5s | Users expect some load time |
| Mobile Lighthouse Score | >70 | Functional over perfect |
| Voice input accuracy | >90% | Browser API dependent |
| Concurrent users | 10+ | Personal companion, not SaaS |
| Session persistence | Survives refresh | Core requirement |
| First response token | No target | Annie thinks as long as she needs |

---

## 2. Architecture

### 2.1 Technology Stack

**Design Principle:** Boring technology that works. Annie's backend already handles LLM/tools/memory - the web UI just needs to present it beautifully.

| Layer | Technology | Rationale |
|-------|------------|-----------|
| **Framework** | Vite + React 18 | Simple, fast builds, no SSR complexity needed for SPA |
| **UI Components** | shadcn/ui + Tailwind CSS | Full control, copy-paste components, unique Annie identity |
| **State Management** | Zustand | Lightweight, simple mental model |
| **Real-time** | Custom SSE hook | Annie's `/api/stream/{id}` format, no adapter needed |
| **Voice Input** | Web Speech API | Native browser support, no external service |
| **Voice Output** | Web Audio API + TTS | Web-based voice (complements Home Assistant) |
| **Authentication** | Cloudflare Access | Already configured at annie.memoryforge.io with Google Auth |
| **Deployment** | Docker + existing compose | Fits existing infrastructure |

**Why NOT Next.js:** Annie's web UI is a single-page chat application. No SEO needed, no content pages, no server-side rendering benefits. Vite + React is 60% less complexity.

**Why NOT assistant-ui:** Annie has her own backend API with custom SSE format. assistant-ui's value is its provider integrations (OpenAI, Anthropic) which we don't need. Building custom with shadcn/ui gives Annie a unique identity, not a generic chat feel.

### 2.2 Component Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           ANNIE WEB UI                                   │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────┐   │
│  │ HEADER                                                           │   │
│  │ ┌─────────────┐  ┌──────────────────────┐  ┌─────────────────┐  │   │
│  │ │ Annie Logo  │  │ Health: 🟢🟢🟢        │  │ LLM: Gemini 2.0 │  │   │
│  │ └─────────────┘  └──────────────────────┘  └─────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌──────────────────┐  ┌────────────────────────────────────────────┐  │
│  │ SIDEBAR          │  │ CHAT AREA                                   │  │
│  │                  │  │                                             │  │
│  │ Conversations    │  │  ┌─────────────────────────────────────┐   │  │
│  │ ┌──────────────┐ │  │  │ MESSAGE THREAD                      │   │  │
│  │ │ Today        │ │  │  │                                     │   │  │
│  │ │ • Chat 1     │ │  │  │ [User Message]                      │   │  │
│  │ │ • Chat 2     │ │  │  │                                     │   │  │
│  │ ├──────────────┤ │  │  │ ┌─────────────────────────────────┐ │   │  │
│  │ │ Yesterday    │ │  │  │ │ 🎭 Annie Avatar (animated)      │ │   │  │
│  │ │ • Chat 3     │ │  │  │ │ [Annie Response]                │ │   │  │
│  │ └──────────────┘ │  │  │ │ 🔊 [Play Voice]                 │ │   │  │
│  │                  │  │  │ └─────────────────────────────────┘ │   │  │
│  │ ┌──────────────┐ │  │  │                                     │   │  │
│  │ │ Memory       │ │  │  │ [Thinking indicator: "Searching..."]│   │  │
│  │ │ Browser 🧠   │ │  │  └─────────────────────────────────────┘   │  │
│  │ └──────────────┘ │  │                                             │  │
│  │                  │  │  ┌─────────────────────────────────────┐   │  │
│  │ ┌──────────────┐ │  │  │ INPUT AREA                          │   │  │
│  │ │ Tools 🔧     │ │  │  │ ┌─────────────────────────────────┐ │   │  │
│  │ └──────────────┘ │  │  │ │ [Text Input]        [🎤] [📎] [➤]│ │   │  │
│  │                  │  │  │ └─────────────────────────────────┘ │   │  │
│  └──────────────────┘  │  └─────────────────────────────────────┘   │  │
│                        └────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 2.3 Data Flow

```
User Input (text/voice/file)
         │
         ▼
    ┌─────────────┐
    │ Web UI      │
    │ (Next.js)   │
    └─────────────┘
         │
         ▼ POST /api/chat + files
    ┌─────────────┐
    │ Backend API │
    │ (FastAPI)   │
    └─────────────┘
         │
         ▼ SSE /api/stream/{id}
    ┌─────────────┐
    │ LLM + Tools │
    └─────────────┘
         │
         ▼ Streaming response
    ┌─────────────┐
    │ Web UI      │──→ Display text + trigger TTS
    └─────────────┘
```

### 2.4 Authentication Flow

Authentication is handled entirely by Cloudflare Access before requests reach Annie.

```
User visits annie.memoryforge.io
              │
              ▼
    ┌─────────────────────┐
    │ Cloudflare Access   │
    │ (Google Auth)       │
    └─────────────────────┘
              │
     ┌────────┴────────┐
     │                 │
     ▼                 ▼
[Authenticated]   [Not Auth'd]
     │                 │
     ▼                 ▼
[Add CF Headers]  [Google Login]
     │                 │
     ▼                 └──→ [Back to start]
[Forward to App]
     │
     ▼
┌─────────────────────┐
│ Annie Web UI        │
│ (No auth logic)     │
└─────────────────────┘
     │
     ▼
┌─────────────────────┐
│ Backend Middleware  │
│ → user_id: 1169...  │
└─────────────────────┘
```

**Key Points:**
- No login page in Annie Web UI
- No auth state management in frontend
- Backend extracts email from CF JWT, maps to Telegram user_id
- `user@example.com` → `YOUR_USER_ID`
- Same identity as Telegram bot (shared conversations, memories)
- Future users: add email→user_id mapping

---

## 3. Stories

### Story 20.1: Project Setup & Infrastructure

**Priority**: P0
**Estimate**: 1 day

Set up Vite + React project with core dependencies and Docker integration.

**Files**:
- `web/` (new directory)
- `web/package.json`
- `web/vite.config.ts`
- `web/Dockerfile`
- `docker-compose.yaml` (update)

**Acceptance Criteria**:

- [ ] Vite + React 18 project
- [ ] TypeScript configuration
- [ ] Tailwind CSS + shadcn/ui setup
- [ ] ESLint + Prettier configuration
- [ ] Dockerfile for containerized deployment
- [ ] Docker Compose service definition
- [ ] Environment variables configuration (VITE_API_URL, etc.)
- [ ] Development server runs on port 3000
- [ ] Production build completes successfully
- [ ] Nginx config for SPA routing (fallback to index.html)

**Package.json Dependencies**:
```json
{
  "dependencies": {
    "react": "^18.0.0",
    "react-dom": "^18.0.0",
    "react-router-dom": "^6.0.0",
    "zustand": "^4.0.0",
    "@radix-ui/react-*": "latest",
    "clsx": "latest",
    "tailwind-merge": "latest",
    "lucide-react": "latest"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.0.0",
    "tailwindcss": "^3.0.0",
    "typescript": "^5.0.0"
  }
}
```

---

### Story 20.2: Layout & Navigation Shell

**Priority**: P0
**Estimate**: 1.5 days

Implement the core responsive layout with header, sidebar, and main content area.

**Files**:
- `web/src/App.tsx`
- `web/src/pages/ChatPage.tsx`
- `web/src/components/layout/Header.tsx`
- `web/src/components/layout/Sidebar.tsx`
- `web/src/components/layout/MainContent.tsx`
- `web/src/components/layout/Layout.tsx`

**Acceptance Criteria**:

- [ ] Responsive two-column layout (sidebar + main)
- [ ] Sidebar collapses to hamburger on mobile (<768px)
- [ ] Header with:
  - Annie logo/name
  - Health status indicators (green dots)
  - Current LLM indicator
- [ ] Sidebar with:
  - Conversation list (grouped by date)
  - New conversation button
  - Memory Browser link (V2 placeholder)
  - Tools link (V3 placeholder)
- [ ] Main content area for chat
- [ ] Dark mode support (system preference)
- [ ] Smooth transitions and animations
- [ ] Accessibility: proper ARIA labels, keyboard navigation

**Responsive Breakpoints**:
| Breakpoint | Layout |
|------------|--------|
| <768px | Single column, hamburger menu |
| 768-1024px | Collapsed sidebar (icons only) |
| >1024px | Full two-column layout |

---

### Story 20.3: Health Status & System Indicators

**Priority**: P0
**Estimate**: 0.5 days

Implement real-time health status display and LLM indicator.

**Files**:
- `web/components/status/HealthIndicator.tsx`
- `web/components/status/LLMIndicator.tsx`
- `web/lib/hooks/useHealth.ts`

**Acceptance Criteria**:

- [ ] Health status component showing:
  - Backend API status (green/yellow/red dot)
  - MCP Server status
  - Redis status
  - agentic-memories status
- [ ] LLM indicator showing active provider (e.g., "Gemini 2.0")
- [ ] Poll `/health/full` endpoint every 30 seconds
- [ ] Tooltip on hover showing detailed status
- [ ] Visual indication of degraded service
- [ ] No jarring UI changes on status update

---

### Story 20.4: Conversation List & Management

**Priority**: P0
**Estimate**: 1 day

Implement conversation history sidebar with CRUD operations.

**Files**:
- `web/components/conversations/ConversationList.tsx`
- `web/components/conversations/ConversationItem.tsx`
- `web/lib/hooks/useConversations.ts`
- `web/lib/stores/conversationStore.ts`

**Acceptance Criteria**:

- [ ] List conversations grouped by date (Today, Yesterday, Previous 7 Days, Older)
- [ ] Each conversation shows:
  - Title (auto-generated from first message or "New conversation")
  - Last message timestamp
  - Truncated preview
- [ ] Click to switch conversations
- [ ] New conversation button (+ icon)
- [ ] Delete conversation (with confirmation)
- [ ] Rename conversation (inline edit)
- [ ] Conversations persist in backend (Redis/PostgreSQL)
- [ ] Loading skeleton while fetching
- [ ] Empty state for new users

**API Integration**:
- `GET /api/conversations` - List user's conversations
- `POST /api/conversations` - Create new conversation
- `DELETE /api/conversations/{id}` - Delete conversation
- `PATCH /api/conversations/{id}` - Update title

---

### Story 20.5: Chat Interface - Message Display

**Priority**: P0
**Estimate**: 1.5 days

Implement the message thread display with proper formatting and styling.

**Files**:
- `web/components/chat/MessageThread.tsx`
- `web/components/chat/UserMessage.tsx`
- `web/components/chat/AnnieMessage.tsx`
- `web/components/chat/MessageContent.tsx`

**Acceptance Criteria**:

- [ ] Message thread with auto-scroll to bottom
- [ ] User messages: right-aligned, distinct styling
- [ ] Annie messages: left-aligned with avatar placeholder
- [ ] Markdown rendering in messages:
  - Headers, bold, italic
  - Code blocks with syntax highlighting
  - Lists (ordered, unordered)
  - Links (open in new tab)
  - Tables
- [ ] File attachments display (images inline, documents as cards)
- [ ] Timestamp on hover
- [ ] Copy message button
- [ ] Smooth scroll behavior
- [ ] Virtualized list for performance (100+ messages)

---

### Story 20.6: Chat Interface - Input & Sending

**Priority**: P0
**Estimate**: 1 day

Implement the message input area with text, file upload, and send functionality.

**Files**:
- `web/components/chat/InputArea.tsx`
- `web/components/chat/FileUpload.tsx`
- `web/lib/hooks/useChat.ts`

**Acceptance Criteria**:

- [ ] Auto-expanding textarea (max 6 lines, then scroll)
- [ ] Send button (enabled when input not empty)
- [ ] Send on Enter, Shift+Enter for newline
- [ ] File upload button with drag-and-drop support
- [ ] File preview before sending
- [ ] Multiple file support (up to 10)
- [ ] File type validation (images, PDFs, docs, spreadsheets)
- [ ] File size validation with user-friendly errors
- [ ] Loading state while sending
- [ ] Disable input while Annie is responding

**Integration**:
- POST to `/api/chat` with message + files (multipart/form-data)
- Handle streaming response via SSE

---

### Story 20.7: SSE Streaming Integration

**Priority**: P0
**Estimate**: 1.5 days

Implement real-time streaming of Annie's responses via Server-Sent Events.

**Files**:
- `web/lib/hooks/useStream.ts`
- `web/lib/api/streamClient.ts`
- `web/components/chat/StreamingMessage.tsx`

**Acceptance Criteria**:

- [ ] Connect to `/api/stream/{conversation_id}` SSE endpoint
- [ ] Display tokens as they arrive (character-by-character or chunk)
- [ ] Handle different SSE event types:
  - `message` - Text content
  - `tool_call` - Tool being invoked
  - `tool_result` - Tool execution result
  - `done` - Stream complete
  - `error` - Error occurred
- [ ] Typing indicator while waiting for first token
- [ ] Graceful reconnection on disconnect
- [ ] Cancel ongoing stream (abort controller)
- [ ] Error handling with user-friendly messages

---

### Story 20.8: Thinking & Tool Call Display

**Priority**: P0
**Estimate**: 0.5 day

Display Annie's thinking state and tool calls from existing SSE stream.

**Context**: Annie's backend already streams `tool_call` and `tool_result` events via SSE. This story is purely UI rendering - no new backend work.

**Files**:
- `web/src/components/chat/ThinkingIndicator.tsx`
- `web/src/components/chat/ToolCallCard.tsx`

**SSE Events to Handle**:
| Event | UI Response |
|-------|-------------|
| `tool_call` | Show "Annie is [action]..." + tool card |
| `tool_result` | Update tool card with result indicator |
| `message` | Render text (handled by Story 20.7) |
| `done` | Clear thinking state |
| `error` | Show error toast |

**Acceptance Criteria**:

- [ ] Map `tool_call` events to user-friendly display:
  | Tool | Display |
  |------|---------|
  | `web_search` | "Searching the web..." |
  | `retrieve_memories` | "Remembering..." |
  | `get_portfolio` | "Checking portfolio..." |
  | `home_assistant_query` | "Checking smart home..." |
  | (default) | "Working on it..." |
- [ ] Tool call card with:
  - Tool name (friendly)
  - Expandable parameters (optional, for debugging)
  - Success/failure indicator from `tool_result`
- [ ] Animated spinner/dots while tool is running
- [ ] Tool cards appear inline in conversation flow
- [ ] Smooth transitions between states

---

### Story 20.9: Voice Input (Speech-to-Text)

**Priority**: P1
**Estimate**: 1 day

Implement voice input using the Web Speech API.

**Files**:
- `web/components/chat/VoiceInput.tsx`
- `web/lib/hooks/useSpeechRecognition.ts`

**Acceptance Criteria**:

- [ ] Microphone button in input area
- [ ] Click to start/stop recording
- [ ] Visual feedback while recording (pulsing icon, waveform)
- [ ] Real-time transcription display
- [ ] Auto-stop after silence (3 seconds)
- [ ] Manual stop and send
- [ ] Browser compatibility check (Chrome, Edge, Safari)
- [ ] Graceful fallback for unsupported browsers
- [ ] Permission handling for microphone access
- [ ] Error handling (permission denied, no microphone)

**Browser Support**:
| Browser | Support |
|---------|---------|
| Chrome | Full |
| Edge | Full |
| Safari | Full |
| Firefox | Limited (needs polyfill) |

---

### Story 20.10: Voice Output (Text-to-Speech)

**Priority**: P1
**Estimate**: 1 day

Implement voice output for Annie's responses using Web Speech API or cloud TTS.

**Files**:
- `web/components/chat/VoiceOutput.tsx`
- `web/lib/hooks/useTextToSpeech.ts`

**Acceptance Criteria**:

- [ ] Play button on each Annie message
- [ ] Global auto-play toggle (off by default)
- [ ] Voice selection (browser voices)
- [ ] Speed control (0.5x - 2x)
- [ ] Pause/resume playback
- [ ] Visual indicator during playback
- [ ] Stop playback when new message arrives
- [ ] Keyboard shortcut for play/pause (Space when focused)
- [ ] Remember voice preferences (localStorage)

**Note**: This complements Home Assistant voice (Epic 16) for when user is at the computer vs. away from it.

---

### Story 20.11: Animated Annie Avatar

**Priority**: P1
**Estimate**: 2 days

Implement Annie's animated anime avatar with state-based animations.

**Files**:
- `web/components/avatar/AnnieAvatar.tsx`
- `web/components/avatar/AvatarStates.tsx`
- `web/public/avatar/` (avatar assets)

**Acceptance Criteria**:

- [ ] Anime-style avatar design (placeholder or commissioned)
- [ ] Avatar states with transitions:
  - **Idle**: Gentle breathing/blinking animation
  - **Thinking**: Eyes looking up/around, thinking pose
  - **Speaking**: Mouth animation synced to TTS or simple loop
  - **Happy**: Smile, sparkles for good news
  - **Empathetic**: Soft expression for emotional support
  - **Surprised**: Wide eyes for unexpected input
- [ ] Smooth transitions between states
- [ ] Avatar appears next to Annie's messages
- [ ] Mini avatar in header (optional)
- [ ] Configurable size (small for messages, large for sidebar)
- [ ] Fallback to static image if animations fail

**Technical Options**:
- Lottie animations (JSON-based, lightweight)
- CSS animations with sprite sheets
- Canvas/WebGL for complex animations

---

### Story 20.12: Mobile Responsiveness & PWA

**Priority**: P1
**Estimate**: 1 day

Ensure full mobile responsiveness and Progressive Web App capabilities.

**Files**:
- `web/app/manifest.json`
- `web/components/mobile/*`
- Various responsive adjustments

**Acceptance Criteria**:

- [ ] Full functionality on mobile devices
- [ ] Touch-friendly UI (48px minimum touch targets)
- [ ] Swipe gestures for sidebar
- [ ] PWA manifest for "Add to Home Screen"
- [ ] Service worker for offline shell
- [ ] Splash screen on mobile
- [ ] iOS Safari viewport handling
- [ ] Android Chrome install prompt
- [ ] Landscape orientation support
- [ ] Responsive images and assets

---

### Story 20.13: Cloudflare Access Integration

**Priority**: P1
**Estimate**: 0.25 day (2 hours)

Integrate with existing Cloudflare Access authentication.

**Context**:
- Domain `annie.memoryforge.io` is protected by Cloudflare Access with Google Auth
- All authenticated requests route to user_id `YOUR_USER_ID` (Ankit's Telegram ID)
- This enables seamless identity across Telegram bot and Web UI

**Files**:
- `backend/api/middleware/cloudflare_auth.py` (new)
- `backend/api/main.py` (update - add middleware)

**Acceptance Criteria**:

- [ ] Backend middleware extracts email from CF-Access-JWT-Assertion header
- [ ] Email-to-user_id mapping: `user@example.com` → `YOUR_USER_ID`
- [ ] Same user identity as Telegram bot (shared conversations, memories)
- [ ] Unknown emails rejected with 401
- [ ] Requests without CF headers rejected (defense in depth)
- [ ] Access logged for audit trail (email, user_id, timestamp)

**Implementation**:
```python
# backend/api/middleware/cloudflare_auth.py
import jwt

# Email to Telegram user_id mapping
USER_MAPPING = {
    "user@example.com": "YOUR_USER_ID",
    # Future users can be added here
}

async def cloudflare_auth_middleware(request: Request, call_next):
    # Skip auth for health checks
    if request.url.path.startswith("/health"):
        return await call_next(request)

    # Extract email from Cloudflare Access JWT
    cf_jwt = request.headers.get("CF-Access-JWT-Assertion")
    if cf_jwt:
        payload = jwt.decode(cf_jwt, options={"verify_signature": False})
        email = payload.get("email")
        user_id = USER_MAPPING.get(email)
        if user_id:
            request.state.user_id = user_id
            return await call_next(request)

    # Reject unauthorized access
    return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
```

**No frontend auth required** - Cloudflare handles login before requests reach the app.

**Future expansion**: Move USER_MAPPING to database or config file for dynamic user management.

---

### Story 20.14: Backend API Extensions

**Priority**: P0
**Estimate**: 1.5 days

Extend backend API to support web UI features.

**Files**:
- `backend/api/routes/conversations.py` (new)
- `backend/api/routes/chat.py` (update)
- `backend/api/routes/stream.py` (update)
- `backend/api/models/conversation.py` (new)

**Acceptance Criteria**:

- [ ] `GET /api/conversations` - List conversations for user
- [ ] `POST /api/conversations` - Create conversation
- [ ] `GET /api/conversations/{id}` - Get conversation with messages
- [ ] `DELETE /api/conversations/{id}` - Delete conversation
- [ ] `PATCH /api/conversations/{id}` - Update conversation title
- [ ] `GET /api/conversations/{id}/messages` - Paginated message history
- [ ] Conversation persistence in Redis (with PostgreSQL option for future)
- [ ] User authentication validation
- [ ] CORS configuration for web UI domain
- [ ] Rate limiting per user

---

### Story 20.15: Integration Testing & Polish

**Priority**: P1
**Estimate**: 1 day

End-to-end testing and UI polish.

**Files**:
- `web/tests/e2e/*`
- Various component refinements

**Acceptance Criteria**:

- [ ] E2E tests with Playwright:
  - Login flow
  - Send message and receive response
  - File upload
  - Voice input (mocked)
  - Conversation switching
- [ ] Cross-browser testing (Chrome, Firefox, Safari, Edge)
- [ ] Mobile device testing (iOS Safari, Android Chrome)
- [ ] Performance audit (Lighthouse >90)
- [ ] Accessibility audit (WCAG 2.1 AA)
- [ ] Error boundary implementation
- [ ] 404 and error pages
- [ ] Loading states and skeletons

---

## 4. V2 Features (Future Stories)

### Story 20.16: Memory Browser (V2 - Debug/Admin)

**Priority**: P3
**Estimate**: 2 days

**Purpose**: Debug/admin tool to inspect Annie's memory state. Not a primary user feature.

**Features**:
- Browse memories by category
- Search memories
- View memory details and source
- Delete specific memories
- "Forget this" functionality

**Access**: Hidden behind admin flag or debug mode.

---

### Story 20.17: Tool Calling UI (V2 - Debug/Admin)

**Priority**: P3
**Estimate**: 2 days

**Purpose**: Debug/admin tool to test tools directly. Not for regular use - Annie decides when to use tools.

**Features**:
- Tool palette in sidebar
- Search tools
- Manual tool invocation with parameters
- Tool execution history

**Access**: Hidden behind admin flag or debug mode.

---

### Story 20.18: Proactive Trigger Notifications (V2)

**Priority**: P2
**Estimate**: 1.5 days

**Purpose**: How Epic 13 (Proactive AI) triggers manifest in the web UI. Not replacing Epic 13, but the display layer.

**Scenarios**:
| User State | Trigger Display |
|------------|-----------------|
| On page, active | Toast notification + avatar animation |
| Tab in background | Browser push notification (if permitted) |
| Tab closed | Queue for next visit, or rely on Telegram/Home Assistant |

**Features**:
- Notification permission request flow
- Toast/alert component for incoming triggers
- Notification badge on browser tab
- "Annie wants to talk" indicator
- Notification history panel
- Sound toggle (optional alert sound)

**Depends on**: Epic 13 (Proactive AI) trigger infrastructure

---

## 5. Technical Considerations

### 5.1 State Management

```typescript
// Zustand store structure
interface AppState {
  // Conversations
  conversations: Conversation[]
  activeConversationId: string | null

  // Messages
  messages: Record<string, Message[]>
  streamingMessage: string | null

  // UI State
  sidebarOpen: boolean
  annieState: 'idle' | 'thinking' | 'speaking' | 'tool_calling'
  activeTool: string | null

  // Settings
  voiceEnabled: boolean
  autoPlayVoice: boolean
  darkMode: 'system' | 'light' | 'dark'
}
```

### 5.2 API Response Types

```typescript
interface ChatResponse {
  conversation_id: string
  message_id: string
  status: 'streaming' | 'complete' | 'error'
}

interface StreamEvent {
  type: 'message' | 'tool_call' | 'tool_result' | 'done' | 'error'
  data: any
}

interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
  last_message_preview: string
}
```

### 5.3 Performance Targets

Annie is a thinking machine - relaxed targets focused on functionality over optimization.

| Metric | Target | Notes |
|--------|--------|-------|
| First Contentful Paint | <3s | Acceptable for companion app |
| Time to Interactive | <5s | Users expect some load time |
| Cumulative Layout Shift | <0.25 | Relaxed, animations may shift |
| Bundle size (initial) | No strict limit | Functionality over bytes |

---

## 6. Dependencies

### 6.1 External Services

| Service | Required | Purpose |
|---------|----------|---------|
| Backend API | Yes | Chat, streaming, conversations |
| Redis | Yes | Session storage, conversations |
| Browser Speech API | Optional | Voice input/output |

### 6.2 Internal Dependencies

| Epic | Required | Purpose |
|------|----------|---------|
| Epic 18 (File Context) | Yes | File upload support |
| Epic 19 (Adaptive Context) | Optional | Persona-aware responses |
| Backend API | Yes | All functionality |

---

## 7. Risks & Mitigations

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Browser Speech API inconsistency | Medium | Medium | Feature detection, graceful fallback |
| SSE connection drops | Medium | Low | Auto-reconnect with exponential backoff |
| Avatar animation performance | Low | Medium | Use Lottie, lazy load, reduced motion support |
| Mobile viewport issues | Medium | Medium | Thorough testing, viewport meta tags |
| Telegram + Web sync lag | Low | Medium | V1: Manual refresh. V2: WebSocket sync |

### 7.1 Cross-Client Behavior

**Design Decision:** Conversations are shared between Telegram and Web.

| Aspect | Behavior |
|--------|----------|
| Conversation visibility | All conversations visible in both clients |
| Continue conversation | Start on Telegram, continue on Web (or vice versa) |
| Same user identity | Email→user_id mapping ensures same identity across clients |
| Real-time sync (V1) | Manual refresh to see messages from other client |
| Real-time sync (V2) | WebSocket for live updates |

**Why this works:** Both clients hit the same backend with the same user_id. Conversations are stored by conversation_id in Redis, not by client type.

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| User adoption | 50% shift from Telegram | Analytics |
| Session duration | >5 minutes average | Analytics |
| Voice input usage | >20% of messages | Logs |
| Mobile vs Desktop | Track ratio | Analytics |
| Error rate | <1% | Logs |
| User satisfaction | Qualitative | Feedback |

---

## 9. Design References

### 9.1 Inspiration

- **Gemini UI**: Clean layout, integrated voice, multimodal
- **Claude UI**: Minimalist, conversation-focused
- **ChatGPT**: Canvas feature, conversation sidebar
- **assistant-ui library**: shadcn/ui patterns, streaming

### 9.2 Color Palette (Draft)

| Element | Light Mode | Dark Mode |
|---------|------------|-----------|
| Background | #FFFFFF | #0F0F0F |
| Sidebar | #F5F5F5 | #1A1A1A |
| User Message | #E3F2FD | #1E3A5F |
| Annie Message | #F5F5F5 | #2D2D2D |
| Accent | #7C3AED | #A78BFA |
| Success | #10B981 | #34D399 |
| Error | #EF4444 | #F87171 |

---

## 10. Future Considerations

- **Telegram OAuth**: Allow Telegram users to log in seamlessly
- **Desktop App**: Electron wrapper for native experience
- **Browser Extension**: Quick access to Annie
- **Widgets**: Embeddable Annie for other sites
- **Collaborative Conversations**: Share conversations with others
- **Voice Cloning**: Custom Annie voice using ElevenLabs/similar
- **AR/VR**: Annie as spatial companion
