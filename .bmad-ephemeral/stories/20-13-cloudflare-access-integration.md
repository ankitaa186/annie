# Story 20.13: Cloudflare Access Integration

Status: ready-for-dev

## Story

As a web user,
I want to authenticate via Cloudflare Access with Google OAuth,
so that I can access Annie's web UI with the same identity as my Telegram account.

## Acceptance Criteria

1. Backend middleware extracts email from CF-Access-JWT-Assertion header
2. Email-to-user_id mapping implemented (`user@example.com` → `YOUR_USER_ID`)
3. Same user identity as Telegram bot (shared conversations, memories)
4. Unknown emails rejected with 401 Unauthorized response
5. Requests without CF headers rejected (defense in depth)
6. Health endpoints bypass authentication
7. Static asset endpoints bypass authentication
8. Access logged for audit trail (email, user_id, timestamp, path)
9. Middleware integrated into FastAPI application startup
10. Unit tests cover all authentication scenarios

## Tasks / Subtasks

- [ ] Task 1: Create Cloudflare auth middleware (AC: 1, 2, 3)
  - [ ] 1.1 Create `backend/api/middleware/cloudflare_auth.py`
  - [ ] 1.2 Implement JWT decoding from CF-Access-JWT-Assertion header
  - [ ] 1.3 Create USER_MAPPING dictionary with email → user_id
  - [ ] 1.4 Extract email from JWT payload
  - [ ] 1.5 Attach user_id to request.state for route handlers

- [ ] Task 2: Implement fallback and error handling (AC: 4, 5)
  - [ ] 2.1 Add fallback to CF-Access-Authenticated-User-Email header
  - [ ] 2.2 Return 401 for unknown emails with clear message
  - [ ] 2.3 Return 401 for missing CF headers
  - [ ] 2.4 Handle JWT decode errors gracefully

- [ ] Task 3: Configure bypass paths (AC: 6, 7)
  - [ ] 3.1 Bypass auth for `/health` and `/health/full` endpoints
  - [ ] 3.2 Bypass auth for `/assets/*` static files
  - [ ] 3.3 Bypass auth for root `/` endpoint

- [ ] Task 4: Add audit logging (AC: 8)
  - [ ] 4.1 Log successful auth with email, user_id, path
  - [ ] 4.2 Log failed auth attempts with reason
  - [ ] 4.3 Log unknown email attempts for security monitoring

- [ ] Task 5: Integrate middleware into FastAPI (AC: 9)
  - [ ] 5.1 Update `backend/api/main.py` to add middleware
  - [ ] 5.2 Ensure middleware runs before route handlers
  - [ ] 5.3 Verify middleware doesn't break existing Telegram flow

- [ ] Task 6: Add dependencies (AC: 1)
  - [ ] 6.1 Add `pyjwt>=2.8.0` to backend requirements.txt
  - [ ] 6.2 Rebuild backend container to include new dependency

- [ ] Task 7: Write unit tests (AC: 10)
  - [ ] 7.1 Test valid CF JWT → successful auth
  - [ ] 7.2 Test valid email header fallback → successful auth
  - [ ] 7.3 Test unknown email → 401 response
  - [ ] 7.4 Test missing headers → 401 response
  - [ ] 7.5 Test malformed JWT → 401 response
  - [ ] 7.6 Test health endpoint bypass → 200 without auth
  - [ ] 7.7 Test static asset bypass → passes through

## Dev Notes

### Architecture Context

**Authentication Flow** (from epic):
```
User → annie.memoryforge.io
         │
         ▼
┌─────────────────────────┐
│ Cloudflare Access       │
│ (Google OAuth)          │
└─────────────────────────┘
         │ CF-Access-JWT-Assertion header
         ▼
┌─────────────────────────┐
│ Backend Middleware      │
│ Extract email from JWT  │
│ Map: email → user_id    │
└─────────────────────────┘
         │
         ▼
user@example.com → YOUR_USER_ID
```

**Key Design Decisions**:
- No JWT signature verification (Cloudflare already verified)
- USER_MAPPING is a simple dict for now (future: database/config file)
- Telegram flow unchanged (middleware only applies to requests with CF headers)
- Same user_id ensures shared conversations across Telegram and Web

### Middleware Implementation

```python
# backend/api/middleware/cloudflare_auth.py
import jwt
from fastapi import Request
from fastapi.responses import JSONResponse
from api.logging import get_logger

logger = get_logger(__name__)

# Email to Telegram user_id mapping
USER_MAPPING = {
    "user@example.com": "YOUR_USER_ID",
}

# Paths that bypass authentication
BYPASS_PATHS = ["/health", "/assets", "/"]

async def cloudflare_auth_middleware(request: Request, call_next):
    # Check bypass paths
    path = request.url.path
    if any(path.startswith(bp) for bp in BYPASS_PATHS):
        return await call_next(request)

    # Extract CF JWT
    cf_jwt = request.headers.get("CF-Access-JWT-Assertion")
    if cf_jwt:
        try:
            payload = jwt.decode(cf_jwt, options={"verify_signature": False})
            email = payload.get("email")
            if email:
                user_id = USER_MAPPING.get(email)
                if user_id:
                    request.state.user_id = user_id
                    request.state.email = email
                    logger.info("CF auth success", extra={"email": email, "user_id": user_id})
                    return await call_next(request)
        except jwt.DecodeError:
            pass

    # Fallback to email header
    cf_email = request.headers.get("CF-Access-Authenticated-User-Email")
    if cf_email:
        user_id = USER_MAPPING.get(cf_email)
        if user_id:
            request.state.user_id = user_id
            request.state.email = cf_email
            return await call_next(request)

    return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
```

### Integration with Existing Code

The middleware must NOT break existing Telegram bot flow:
- Telegram bot calls `/api/chat` directly without CF headers
- Middleware should only enforce auth when CF headers are present
- OR: Add Telegram-specific path bypass (`/api/chat` from internal network)

**Important**: The current `/api/chat` endpoint accepts `user_id` in request body (Telegram flow). For web flow, we'll use `request.state.user_id` from middleware. Routes need to check both sources.

### Project Structure Notes

```
backend/
├── api/
│   ├── middleware/
│   │   ├── __init__.py           # NEW
│   │   └── cloudflare_auth.py    # NEW - this story
│   ├── main.py                   # MODIFY - add middleware
│   └── ...
├── requirements.txt              # MODIFY - add pyjwt
└── tests/
    └── test_cloudflare_auth.py   # NEW - unit tests
```

### Testing Strategy

```python
# tests/test_cloudflare_auth.py
import pytest
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

def test_valid_jwt_auth():
    """Test successful auth with valid CF JWT"""
    # Create mock JWT with email
    headers = {"CF-Access-JWT-Assertion": encode_test_jwt("user@example.com")}
    response = client.get("/api/health/full", headers=headers)
    # Health should work (but this tests the flow)

def test_unknown_email_rejected():
    """Test 401 for unknown email"""
    headers = {"CF-Access-JWT-Assertion": encode_test_jwt("unknown@example.com")}
    response = client.get("/api/conversations", headers=headers)
    assert response.status_code == 401
```

### References

- [Source: docs/epics/epic-20-web-ui.md#Story-20.13]
- [Source: .bmad-ephemeral/tech-contexts/epic-20-tech-context.md#Section-3.2.3]
- [Source: docs/brainstorming-web-ui-2026-01-25.md#Auth]

## Dev Agent Record

### Context Reference

- `.bmad-ephemeral/stories/20-13-cloudflare-access-integration.context.xml`

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

