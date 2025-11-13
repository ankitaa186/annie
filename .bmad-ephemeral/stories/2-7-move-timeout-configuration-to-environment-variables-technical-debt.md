# Story 2.7: Move Timeout Configuration to Environment Variables (Technical Debt)

Status: done

## Story

As a **developer/operator**,
I want **timeout values configurable via environment variables instead of hardcoded**,
so that **I can adjust timeouts for different environments without code changes**.

## Acceptance Criteria

**AC #1:** Given `env.example`, when I check timeout configuration, then it includes environment variables:
  - `LLM_REQUEST_TIMEOUT` (default: 180)
  - `LLM_FAILOVER_TIMEOUT` (default: 180)
  - `LLM_STREAMING_TIMEOUT` (default: 180)
  - `BACKEND_CONNECT_TIMEOUT` (default: 10)
  - `BACKEND_SOCK_READ_TIMEOUT` (default: 180)
  - `TELEGRAM_FIRST_TOKEN_TIMEOUT` (default: 120)

**AC #2:** Given `backend/api/llm_client.py`, when I check the LLMClient class, then hardcoded timeout class variables are replaced with instance variables loaded from environment config with sensible defaults

**AC #3:** Given `telegram_bot/backend_client.py`, when I check the BackendClient class, then hardcoded timeout values are replaced with environment variable loading with fallback defaults

**AC #4:** Given environment variables are not set, when services start, then they use documented default values without errors

**AC #5:** Given timeout environment variables are set, when I restart services, then new timeout values are applied and logged at startup

**AC #6:** Given timeout configuration changes, when I update `.env` file and restart, then no code changes are required to adjust timeout behavior

**AC #7:** Given the implementation, when I check logging, then timeout values are logged at service initialization showing which values are being used (env vs defaults)

## Tasks / Subtasks

- [x] Task 1: Update environment variable documentation (AC: #1)
  - [x] Add timeout variables to `env.example` with documentation
  - [x] Include default values and descriptions for each timeout
  - [x] Group by service (LLM, Backend, Telegram)

- [x] Task 2: Refactor LLMClient timeout configuration (AC: #2, #4, #5, #7)
  - [x] Load `backend/api/llm_client.py`
  - [x] Convert class variables (REQUEST_TIMEOUT, FAILOVER_TIMEOUT, STREAMING_TIMEOUT) to instance variables
  - [x] Load timeout values from config with `float()` conversion
  - [x] Apply fallback defaults if env vars not set
  - [x] Update all references from `self.FAILOVER_TIMEOUT` to `self.failover_timeout`
  - [x] Add startup logging showing loaded timeout values

- [x] Task 3: Refactor BackendClient timeout configuration (AC: #3, #4, #5, #7)
  - [x] Load `telegram_bot/backend_client.py`
  - [x] Update `__init__` to load timeouts from config
  - [x] Load BACKEND_CONNECT_TIMEOUT and BACKEND_SOCK_READ_TIMEOUT
  - [x] Apply to `aiohttp.ClientTimeout` configuration
  - [x] Add startup logging showing loaded timeout values

- [x] Task 4: Verify backward compatibility (AC: #4, #6)
  - [x] Test services start without any timeout env vars set
  - [x] Verify default values are applied correctly
  - [x] Confirm no breaking changes to existing behavior

- [x] Task 5: Test configuration changes (AC: #5, #6)
  - [x] Set timeout env vars in `.env`
  - [x] Restart services
  - [x] Verify new values are applied from logs
  - [x] Confirm no code changes required

## Dev Notes

### Architecture Context

**Configuration Pattern** (from ARCHITECTURE_PLAN.md):
- Environment variables loaded via `api.config.get_config()` in backend
- Environment variables loaded via `telegram_bot.config.get_config()` in telegram bot
- All configuration centralized in `.env` file
- Sensible defaults required for all optional configuration

**Affected Services**:
1. **Backend API** (`backend/api/llm_client.py`)
   - Current: Class variables `REQUEST_TIMEOUT = 180.0`, `FAILOVER_TIMEOUT = 180.0`, `STREAMING_TIMEOUT = 180.0`
   - Change: Instance variables loaded from config in `__init__`

2. **Telegram Bot** (`telegram_bot/backend_client.py`)
   - Current: Hardcoded timeouts in `__init__` (connect=10, sock_read=180, first_token_timeout=120)
   - Change: Load from config with defaults

### Implementation Strategy

**Backend LLMClient Refactor**:
```python
def __init__(self):
    config = get_config()

    # Load timeouts from environment with sensible defaults
    self.request_timeout = float(config.get("LLM_REQUEST_TIMEOUT", "180.0"))
    self.failover_timeout = float(config.get("LLM_FAILOVER_TIMEOUT", "180.0"))
    self.streaming_timeout = float(config.get("LLM_STREAMING_TIMEOUT", "180.0"))

    # Initialize HTTP client with timeout
    self.client = httpx.AsyncClient(timeout=self.request_timeout)

    # Log loaded values
    logger.info(
        "LLM client timeouts configured",
        extra={
            "request_timeout": self.request_timeout,
            "failover_timeout": self.failover_timeout,
            "streaming_timeout": self.streaming_timeout
        }
    )
```

**Telegram BackendClient Refactor**:
```python
def __init__(self, backend_url: Optional[str] = None, first_token_timeout: int = None):
    config = get_config()

    # Load timeouts from env or use defaults
    self.first_token_timeout = first_token_timeout or int(
        config.get("TELEGRAM_FIRST_TOKEN_TIMEOUT", "120")
    )
    connect_timeout = int(config.get("BACKEND_CONNECT_TIMEOUT", "10"))
    sock_read_timeout = int(config.get("BACKEND_SOCK_READ_TIMEOUT", "180"))

    self.timeout = aiohttp.ClientTimeout(
        total=None,
        connect=connect_timeout,
        sock_read=sock_read_timeout
    )

    logger.info(
        "Backend client initialized",
        extra={
            "first_token_timeout": self.first_token_timeout,
            "connect_timeout": connect_timeout,
            "sock_read_timeout": sock_read_timeout
        }
    )
```

### Testing Approach

1. **Default Behavior Test**: Start services without timeout env vars, verify defaults apply
2. **Custom Configuration Test**: Set env vars, restart, verify new values from logs
3. **Backward Compatibility**: Ensure existing deployments work without changes

### Technical Debt Context

This story addresses hardcoded timeout values that currently require code changes to adjust. After implementation:
- Operators can tune timeouts for different environments (dev/staging/prod)
- Troubleshooting timeout issues won't require code deployment
- Configuration is self-documenting via `env.example`

### Project Structure Notes

**Files to Modify**:
- `env.example` - Add timeout variable documentation
- `backend/api/llm_client.py` - Refactor timeout loading (lines 62-65, __init__)
- `telegram_bot/backend_client.py` - Refactor timeout loading (lines 22-41, __init__)

**No New Files Created** - Pure refactoring story

### References

- [Source: docs/epics-and-stories.md#Story-2.7]
- [Source: docs/02-architecture/ARCHITECTURE_PLAN.md#Configuration-Management]
- [Source: backend/api/llm_client.py:62-65] - Current hardcoded timeouts
- [Source: telegram_bot/backend_client.py:22-41] - Current timeout configuration

## Dev Agent Record

### Context Reference

- `.bmad-ephemeral/stories/2-7-move-timeout-configuration-to-environment-variables-technical-debt.context.xml`

### Agent Model Used

Claude Sonnet 4.5 (claude-sonnet-4-5-20250929)

### Debug Log References

**Implementation Plan:**
1. Added all 6 timeout environment variables to env.example with comprehensive documentation
2. Refactored LLMClient.__init__() to load timeout values from config (lines 78-82)
3. Updated all LLMClient timeout references from class variables to instance variables (6 locations)
4. Refactored BackendClient.__init__() to load timeout values from config (lines 33-39)
5. Added startup logging for all timeout values in both services
6. Verified services start successfully without env vars (backward compatibility)
7. Tested configuration changes work without code modifications

### Completion Notes List

**Completed:** 2025-11-12
**Definition of Done:** All acceptance criteria met, code reviewed, tests passing

✅ All acceptance criteria met:
- AC #1: env.example updated with all 6 timeout variables with defaults and descriptions
- AC #2: LLMClient timeout class variables converted to instance variables loaded from config
- AC #3: BackendClient timeout values loaded from environment variables with fallback defaults
- AC #4: Services start successfully without timeout env vars using documented defaults
- AC #5: Timeout environment variables applied and logged at startup
- AC #6: Configuration changes work via .env without code changes
- AC #7: Timeout values logged at service initialization

**Key Implementation Details:**
- Maintained backward compatibility: All existing deployments work without .env updates
- Used float() conversion for LLM timeouts, int() for Backend/Telegram timeouts
- Preserved first_token_timeout parameter override capability in BackendClient
- Added comprehensive logging showing actual timeout values being used
- Followed existing configuration patterns from config modules

### File List

**MODIFIED:**
- `env.example` - Added timeout configuration section with 6 timeout variables
- `backend/api/llm_client.py` - Refactored timeout configuration (removed class variables, added instance variables from config, updated all references)
- `telegram_bot/backend_client.py` - Refactored timeout configuration (load from config with defaults)
