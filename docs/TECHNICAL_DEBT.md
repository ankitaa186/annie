# Technical Debt Tracking

This document tracks technical debt items identified during development that should be addressed in future iterations.

## Priority Levels

- **HIGH**: Should be addressed before production deployment
- **MEDIUM**: Should be addressed soon, but not blocking
- **LOW**: Nice to have, address when time permits

---

## Current Technical Debt Items

### 1. Missing Automated Tests for Backend API

**Priority:** MEDIUM
**Identified In:** Story 2.1 Code Review (2025-11-11)
**Component:** Backend API (`backend/`)

**Description:**
No automated test suite exists for the backend API. Story 2.1 implemented FastAPI endpoints, middleware, and health checks, but no pytest tests were created to validate functionality.

**Impact:**
- No automated validation of endpoints, middleware, or health checks
- Risk of regressions when making changes
- Difficult to verify behavior without manual testing
- Reduces confidence in refactoring efforts

**Recommended Solution:**
Add pytest test suite covering:
- Health check endpoints (`/health`, `/health/detailed`)
- Request logging middleware
- CORS middleware configuration
- Component health check functions
- Error scenarios (component failures, network errors)
- Response format validation
- Timestamp format validation (ISO 8601)

**Proposed Action:**
- Create `backend/tests/` directory structure
- Add pytest configuration and fixtures
- Write test cases for all Story 2.1 features
- Integrate with CI/CD pipeline (when available)

**Affected Stories:** Story 2.1 (and potentially all future Epic 2 stories)

**Estimated Effort:** 2-3 points

---

### 2. CORS Configuration Not Production-Ready

**Priority:** MEDIUM (HIGH before production deployment)
**Identified In:** Story 2.1 Code Review (2025-11-11)
**Component:** Backend API (`backend/api/main.py`)

**Description:**
CORS middleware is currently configured with `allow_origins=["*"]`, which allows any origin to make requests to the API. This is acceptable for development but poses a security risk in production.

**Impact:**
- Security vulnerability: Any website can make requests to the API
- Potential for CSRF attacks in production
- Does not meet production security standards
- Could expose API to unauthorized access

**Current Implementation:**
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ Security risk in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Recommended Solution:**
Add environment-specific CORS configuration:
```python
# In backend/api/config.py
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")

# In backend/api/main.py
config = get_config()
origins = config.get("ALLOWED_ORIGINS", ["*"]) if config["ENVIRONMENT"] == "dev" else config.get("ALLOWED_ORIGINS", []).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

**Proposed Action:**
- Add `ALLOWED_ORIGINS` environment variable
- Update `backend/api/main.py` to use environment-specific CORS
- Document production CORS configuration in deployment guide
- Test with restricted origins in staging environment

**Affected Stories:** Story 2.1

**When to Address:** Before Story 6.4 (Documentation & Deployment Readiness)

**Estimated Effort:** 1 point

---

### 3. Placeholder Health Checks for Redis, LLM, Agentic-Memories

**Priority:** LOW (by design, not true debt)
**Identified In:** Story 2.1 Code Review (2025-11-11)
**Component:** Backend API (`backend/api/main.py`)

**Description:**
Health check functions for Redis, LLM API, and agentic-memories currently return hardcoded `"ok"` status. These are placeholders with TODO comments indicating they will be implemented in future stories.

**Impact:**
- Cannot detect actual failures of these components yet
- `/health/detailed` may report "ok" when components are actually down
- Limited observability of system health

**Current Implementation:**
```python
def check_redis_health() -> str:
    # TODO: Implement actual Redis health check in Story 2.5
    return "ok"

def check_llm_api_health() -> str:
    # TODO: Implement actual LLM API health check in Story 2.2
    return "ok"

def check_agentic_memories_health() -> str:
    # TODO: Implement actual agentic-memories health check in Story 3.1
    return "ok"
```

**Planned Resolution:**
- **Story 2.2**: Implement actual LLM API health check
- **Story 2.5**: Implement actual Redis health check (connection test)
- **Story 3.1**: Implement actual agentic-memories health check

**Status:** Tracked in respective stories, no additional action needed

---

## Resolved Technical Debt

### ✅ 1. Backend Config Validation Too Strict (RESOLVED: 2025-11-11)

**Issue:** Backend config validation required LLM API keys for Story 2.1, even though LLM functionality wasn't needed until Story 2.2. This blocked service startup.

**Resolution:** Modified `backend/api/config.py` to convert LLM API key validation from errors to warnings. Keys are now optional for Story 2.1 and will be required when LLM client is implemented in Story 2.2.

**Resolved In:** Story 2.1 Implementation

---

## Notes

- Technical debt items should be reviewed before each epic retrospective
- Medium and High priority items should be addressed within the same epic or sprint
- Low priority items can be deferred to future epics
- All technical debt should be cleared before production deployment (Epic 6)
