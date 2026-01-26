# Story 20.14: Backend API Extensions

Status: drafted

## Story

As a web UI developer,
I want conversation management API endpoints,
so that users can list, create, switch, delete, and rename conversations in the web interface.

## Acceptance Criteria

1. `GET /api/conversations` returns list of conversations for authenticated user
2. `POST /api/conversations` creates new conversation and returns details
3. `GET /api/conversations/{id}` returns conversation with messages (paginated)
4. `DELETE /api/conversations/{id}` deletes conversation (with confirmation requirement)
5. `PATCH /api/conversations/{id}` updates conversation title
6. `GET /api/conversations/{id}/messages` returns paginated message history
7. Conversations persist in Redis (with PostgreSQL migration path for future)
8. User authentication validated for all endpoints (via CF auth or request body)
9. CORS configuration allows web UI domain
10. Rate limiting per user implemented
11. Unit tests cover all endpoints with various scenarios
12. OpenAPI documentation auto-generated for all endpoints

## Tasks / Subtasks

- [ ] Task 1: Create conversation model and schema (AC: 1, 2, 3)
  - [ ] 1.1 Create `backend/api/models/conversation.py`
  - [ ] 1.2 Define Conversation Pydantic model (id, title, created_at, updated_at, message_count, last_message_preview)
  - [ ] 1.3 Define ConversationListResponse model
  - [ ] 1.4 Define CreateConversationRequest/Response models
  - [ ] 1.5 Define ConversationDetailResponse model (with messages)

- [ ] Task 2: Create conversations router (AC: 1, 2, 3, 4, 5)
  - [ ] 2.1 Create `backend/api/routes/conversations.py`
  - [ ] 2.2 Implement GET /api/conversations (list)
  - [ ] 2.3 Implement POST /api/conversations (create)
  - [ ] 2.4 Implement GET /api/conversations/{id} (detail)
  - [ ] 2.5 Implement DELETE /api/conversations/{id} (delete)
  - [ ] 2.6 Implement PATCH /api/conversations/{id} (update title)
  - [ ] 2.7 Implement GET /api/conversations/{id}/messages (paginated)

- [ ] Task 3: Implement Redis storage layer (AC: 7)
  - [ ] 3.1 Design Redis key structure for conversations
  - [ ] 3.2 Implement conversation CRUD operations in StateManager
  - [ ] 3.3 Add conversation list by user_id (sorted by updated_at)
  - [ ] 3.4 Add conversation metadata storage
  - [ ] 3.5 Ensure backward compatibility with existing session/conversation data

- [ ] Task 4: Implement user authentication for routes (AC: 8)
  - [ ] 4.1 Get user_id from request.state (CF auth middleware)
  - [ ] 4.2 Fallback to request body user_id (Telegram compatibility)
  - [ ] 4.3 Validate user owns conversation before operations
  - [ ] 4.4 Return 403 for unauthorized conversation access

- [ ] Task 5: Configure CORS (AC: 9)
  - [ ] 5.1 Update CORS middleware for annie.memoryforge.io
  - [ ] 5.2 Allow credentials for authenticated requests
  - [ ] 5.3 Configure allowed methods (GET, POST, PATCH, DELETE, OPTIONS)

- [ ] Task 6: Implement rate limiting (AC: 10)
  - [ ] 6.1 Add rate limiter middleware or decorator
  - [ ] 6.2 Configure limits per user (e.g., 60 req/min)
  - [ ] 6.3 Return 429 with Retry-After header when exceeded

- [ ] Task 7: Register router and update main.py
  - [ ] 7.1 Import conversations router
  - [ ] 7.2 Include router with /api prefix
  - [ ] 7.3 Verify OpenAPI docs include new endpoints

- [ ] Task 8: Write unit and integration tests (AC: 11)
  - [ ] 8.1 Test list conversations returns user's conversations only
  - [ ] 8.2 Test create conversation returns valid response
  - [ ] 8.3 Test get conversation with pagination
  - [ ] 8.4 Test delete conversation removes data
  - [ ] 8.5 Test update title works correctly
  - [ ] 8.6 Test 404 for non-existent conversation
  - [ ] 8.7 Test 403 for unauthorized access

## Dev Notes

### Architecture Context

**API Design** (from tech context):
```
GET /api/conversations
├── Response: [{ id, title, created_at, updated_at, last_message_preview }]
└── Auth: Cloudflare Access JWT → user_id mapping

POST /api/conversations
├── Request: (empty or { title?: string })
└── Response: { id, title, created_at }

GET /api/conversations/{id}
├── Response: { id, title, messages: [...], created_at, updated_at }
└── Pagination: ?page=1&limit=50

DELETE /api/conversations/{id}
└── Response: { status: "deleted" }

PATCH /api/conversations/{id}
├── Request: { title: "New Title" }
└── Response: { id, title, updated_at }

GET /api/conversations/{id}/messages
├── Response: { messages: [...], pagination: {...} }
└── Pagination: ?page=1&limit=50
```

### Redis Key Structure

```
# User's conversation list (sorted set, score = updated_at timestamp)
conversations:{user_id}  →  [conv_id1, conv_id2, ...]

# Conversation metadata (hash)
conversation:{conv_id}:meta  →  {
    "user_id": "YOUR_USER_ID",
    "title": "Portfolio Discussion",
    "created_at": "2026-01-26T10:00:00Z",
    "updated_at": "2026-01-26T12:30:00Z"
}

# Conversation messages (existing - list)
conversation:{conv_id}:messages  →  [msg1, msg2, ...]

# Backward compatibility: session → conversation mapping (existing)
session:{user_id}  →  { "conversation_id": "conv_abc123", ... }
```

### Integration with Existing Code

**Current Flow** (from chat.py and stream.py):
- `/api/chat` creates/gets session with `StateManager.get_session()` / `create_session()`
- Session contains `conversation_id`
- Messages stored in Redis list

**New Flow** (this story):
- Add `conversations` router for CRUD operations
- Extend `StateManager` with conversation-specific methods
- Keep backward compatibility with existing session management

### User ID Resolution

```python
def get_user_id(request: Request) -> str:
    """Get user_id from CF auth middleware or request body."""
    # Priority 1: CF auth middleware (web flow)
    if hasattr(request.state, 'user_id'):
        return request.state.user_id

    # Priority 2: Request body (Telegram flow - for chat endpoint)
    # Note: For conversation endpoints, we require auth
    raise HTTPException(status_code=401, detail="Authentication required")
```

### Response Models

```python
# backend/api/models/conversation.py
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

class Conversation(BaseModel):
    id: str = Field(..., description="Unique conversation identifier")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    message_count: int = Field(0, description="Number of messages")
    last_message_preview: Optional[str] = Field(None, description="Preview of last message")

class ConversationListResponse(BaseModel):
    conversations: List[Conversation]
    total: int

class CreateConversationResponse(BaseModel):
    id: str
    title: str
    created_at: datetime

class ConversationDetailResponse(BaseModel):
    id: str
    title: str
    messages: List[dict]
    created_at: datetime
    updated_at: datetime
    pagination: dict
```

### Project Structure Notes

```
backend/
├── api/
│   ├── models/
│   │   ├── __init__.py
│   │   ├── file_attachment.py    # Existing
│   │   └── conversation.py       # NEW - this story
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── chat.py               # Existing
│   │   ├── stream.py             # Existing
│   │   └── conversations.py      # NEW - this story
│   ├── state.py                  # MODIFY - add conversation methods
│   └── main.py                   # MODIFY - add router
└── tests/
    └── test_conversations.py     # NEW - unit tests
```

### CORS Configuration Update

```python
# In main.py - update existing CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://annie.memoryforge.io",
        "http://localhost:3000",  # Dev
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
```

### Dependencies with Other Stories

- **Depends on Story 20.13**: Cloudflare auth middleware must be in place for user_id resolution
- **Enables Story 20.4**: Conversation List UI component will consume these APIs

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.14]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-2.2.2]
- [Source: backend/api/routes/chat.py - existing patterns]
- [Source: backend/api/state.py - existing StateManager]

## Dev Agent Record

### Context Reference

<!-- Path(s) to story context XML will be added here by context workflow -->

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

