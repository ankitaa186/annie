# Story 20.14: Backend API Extensions

Status: review

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

- [x] Task 1: Create conversation model and schema (AC: 1, 2, 3)
  - [x] 1.1 Create `backend/api/models/conversation.py`
  - [x] 1.2 Define Conversation Pydantic model (id, title, created_at, updated_at, message_count, last_message_preview)
  - [x] 1.3 Define ConversationListResponse model
  - [x] 1.4 Define CreateConversationRequest/Response models
  - [x] 1.5 Define ConversationDetailResponse model (with messages)

- [x] Task 2: Create conversations router (AC: 1, 2, 3, 4, 5)
  - [x] 2.1 Create `backend/api/routes/conversations.py`
  - [x] 2.2 Implement GET /api/conversations (list)
  - [x] 2.3 Implement POST /api/conversations (create)
  - [x] 2.4 Implement GET /api/conversations/{id} (detail)
  - [x] 2.5 Implement DELETE /api/conversations/{id} (delete)
  - [x] 2.6 Implement PATCH /api/conversations/{id} (update title)
  - [x] 2.7 Implement GET /api/conversations/{id}/messages (paginated)

- [x] Task 3: Implement Redis storage layer (AC: 7)
  - [x] 3.1 Design Redis key structure for conversations
  - [x] 3.2 Implement conversation CRUD operations in StateManager
  - [x] 3.3 Add conversation list by user_id (sorted by updated_at)
  - [x] 3.4 Add conversation metadata storage
  - [x] 3.5 Ensure backward compatibility with existing session/conversation data

- [x] Task 4: Implement user authentication for routes (AC: 8)
  - [x] 4.1 Get user_id from request.state (CF auth middleware)
  - [x] 4.2 Fallback to request body user_id (Telegram compatibility)
  - [x] 4.3 Validate user owns conversation before operations
  - [x] 4.4 Return 403 for unauthorized conversation access

- [x] Task 5: Configure CORS (AC: 9)
  - [x] 5.1 Update CORS middleware for annie.memoryforge.io
  - [x] 5.2 Allow credentials for authenticated requests
  - [x] 5.3 Configure allowed methods (GET, POST, PATCH, DELETE, OPTIONS)

- [x] Task 6: Implement rate limiting (AC: 10)
  - [x] 6.1 Add rate limiter middleware or decorator
  - [x] 6.2 Configure limits per user (e.g., 60 req/min)
  - [x] 6.3 Return 429 with Retry-After header when exceeded

- [x] Task 7: Register router and update main.py
  - [x] 7.1 Import conversations router
  - [x] 7.2 Include router with /api prefix
  - [x] 7.3 Verify OpenAPI docs include new endpoints

- [x] Task 8: Write unit and integration tests (AC: 11)
  - [x] 8.1 Test list conversations returns user's conversations only
  - [x] 8.2 Test create conversation returns valid response
  - [x] 8.3 Test get conversation with pagination
  - [x] 8.4 Test delete conversation removes data
  - [x] 8.5 Test update title works correctly
  - [x] 8.6 Test 404 for non-existent conversation
  - [x] 8.7 Test 403 for unauthorized access

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

- .bmad-ephemeral/stories/20-14-backend-api-extensions.context.xml

### Agent Model Used

claude-opus-4-5-20251101

### Debug Log References

Implementation followed the story's Dev Notes architecture closely, including:
- Redis key structure as specified (sorted sets for user conversations, hashes for metadata)
- API endpoints matching the documented design
- Authentication flow using CF auth middleware
- Rate limiting with sliding window algorithm

### Completion Notes List

1. **Conversation Models (Task 1)**: Created comprehensive Pydantic models in `conversation.py`:
   - `Conversation`, `ConversationListResponse`, `CreateConversationRequest/Response`
   - `UpdateConversationRequest/Response`, `DeleteConversationResponse`
   - `Message`, `PaginationInfo`, `ConversationDetailResponse`, `MessageListResponse`

2. **Redis Storage Layer (Task 3)**: Extended `StateManager` with 8 new methods:
   - `list_conversations()` - Sorted set + hash retrieval
   - `get_conversations_count()` - ZCARD for total count
   - `create_conversation()` - Pipeline for atomic creation
   - `get_conversation_detail()` - Hash retrieval
   - `update_conversation_title()` - Hash update + sorted set score update
   - `delete_conversation()` - Pipeline for atomic deletion
   - `get_paginated_messages()` - LRANGE with offset/limit
   - `touch_conversation()` - Update timestamp on message add

3. **Conversations Router (Task 2)**: Implemented all 6 endpoints:
   - GET /api/conversations - List with pagination
   - POST /api/conversations - Create with optional title
   - GET /api/conversations/{id} - Detail with paginated messages
   - DELETE /api/conversations/{id} - Delete with ownership check
   - PATCH /api/conversations/{id} - Update title
   - GET /api/conversations/{id}/messages - Paginated messages only

4. **Authentication (Task 4)**: Implemented `get_user_id()` and `verify_conversation_ownership()`:
   - Extracts user_id from request.state (set by CF auth middleware)
   - Returns 401 if no authentication
   - Returns 403 if user doesn't own conversation
   - Returns 404 if conversation not found

5. **CORS Configuration (Task 5)**: Updated `main.py`:
   - Production: https://annie.memoryforge.io
   - Development: localhost:3000, localhost:5173, 127.0.0.1 variants
   - Credentials enabled, specific methods allowed

6. **Rate Limiting (Task 6)**: Created `rate_limiter.py`:
   - Sliding window algorithm using Redis sorted sets
   - 60 requests/minute per user
   - Returns 429 with Retry-After header
   - X-RateLimit-* headers on all responses
   - Fails open on Redis errors

7. **Router Registration (Task 7)**: Updated `main.py`:
   - Imported and included conversations router
   - Added rate limit middleware
   - Updated root endpoint with new endpoints documentation

8. **Tests (Task 8)**: Created comprehensive test suite:
   - Model validation tests
   - StateManager method tests
   - Router authentication tests
   - Rate limiter tests
   - CORS configuration tests
   - Integration tests for auth requirements

### File List

**New Files:**
- backend/api/models/conversation.py
- backend/api/routes/conversations.py
- backend/api/middleware/rate_limiter.py
- backend/tests/test_conversations.py

**Modified Files:**
- backend/api/models/__init__.py (added conversation exports)
- backend/api/routes/__init__.py (added conversations export)
- backend/api/middleware/__init__.py (added rate_limiter exports)
- backend/api/state.py (added 8 conversation management methods)
- backend/api/main.py (CORS config, router registration, rate limit middleware)

## Change Log

- 2026-01-26: Story 20.14 Backend API Extensions - Implemented conversation management APIs (Claude Opus 4.5)

