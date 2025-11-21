# Bug Fixes: Bare Except Clause and Unit Test Compatibility

**Date**: 2025-11-20
**Severity**: Medium
**Impact**: Better error handling and test reliability

---

## Problem Description

### Bug 1: Bare except clause catches all exceptions silently

**Symptoms:**
- Timezone conversion errors in profile formatting were silently swallowed
- Could catch KeyboardInterrupt and SystemExit, preventing proper program termination
- Debugging difficult due to silent failure without logging

**Root Cause:**
The `format_profile_for_prompt()` function in `backend/api/prompts.py` used a bare `except:` clause when converting user timezone to local time:

```python
try:
    user_tz = pytz.timezone(basics['timezone'])
    user_time = datetime.now(user_tz).strftime("%I:%M %p")
    basics_lines.append(f"Timezone: {basics['timezone']} (current time: {user_time})")
except:  # ❌ BARE EXCEPT - catches everything!
    basics_lines.append(f"Timezone: {basics['timezone']}")
```

**Why This is Bad:**
- Catches ALL exceptions, including system signals (KeyboardInterrupt, SystemExit)
- No logging, making legitimate errors invisible
- Invalid timezone strings fail silently
- Debugging nearly impossible

---

### Bug 2: Unit tests incompatible with Redis Hash implementation

**Symptoms:**
- Unit tests for ProfileManager would fail after Redis Hash migration
- Tests mocked wrong Redis methods (get/setex instead of hgetall/hget/hincrby/hset/expire)
- Test assertions checking for JSON string data instead of Hash dict data

**Root Cause:**
The implementation was changed from JSON string storage to Redis Hash storage (for atomic updates), but tests still mocked the old methods:

**Implementation uses:**
- `hgetall()` / `hget()` - Read from Hash
- `hincrby()` - Atomic increment
- `hset()` - Atomic field update
- `expire()` - Set TTL

**Tests were mocking:**
- `get()` - Returns JSON string
- `setex()` - Writes JSON string with TTL

**Specific Incompatibilities:**
1. `test_check_refresh_triggers_*` - Mocked `get()` returning JSON, but code calls `hgetall()` expecting dict
2. `test_increment_message_count_*` - Mocked `get()`/`setex()`, but code calls `hincrby()`/`expire()`
3. `test_refresh_profile_background_*` - Expected 2 `setex()` calls, but code only calls 1 (profile) + `hset()`/`expire()` for metadata

---

## Solution

### Fix 1: Replace bare except with specific exceptions and logging

**File:** `backend/api/prompts.py` (lines 115-129)

**BEFORE:**
```python
try:
    user_tz = pytz.timezone(basics['timezone'])
    user_time = datetime.now(user_tz).strftime("%I:%M %p")
    basics_lines.append(f"Timezone: {basics['timezone']} (current time: {user_time})")
except:
    basics_lines.append(f"Timezone: {basics['timezone']}")
```

**AFTER:**
```python
try:
    user_tz = pytz.timezone(basics['timezone'])
    user_time = datetime.now(user_tz).strftime("%I:%M %p")
    basics_lines.append(f"Timezone: {basics['timezone']} (current time: {user_time})")
except (pytz.exceptions.UnknownTimeZoneError, ValueError, KeyError) as e:
    # Log timezone conversion errors for debugging
    from api.logging import get_logger
    logger = get_logger(__name__)
    logger.warning(
        f"Failed to convert timezone: {basics.get('timezone')}",
        extra={"error": str(e), "error_type": type(e).__name__}
    )
    basics_lines.append(f"Timezone: {basics['timezone']}")
```

**Benefits:**
- ✅ Only catches expected timezone-related exceptions
- ✅ System signals (KeyboardInterrupt, SystemExit) not caught
- ✅ Errors logged for debugging
- ✅ Invalid timezones visible in logs with error context

---

### Fix 2: Update unit tests to match Redis Hash implementation

**File:** `backend/tests/unit/test_profile_manager.py`

#### Change 1: Updated redis_mock fixture (lines 15-30)

**BEFORE:**
```python
@pytest.fixture
async def redis_mock():
    """Mock Redis client."""
    mock = AsyncMock()
    mock.get = AsyncMock()
    mock.setex = AsyncMock()
    mock.close = AsyncMock()
    return mock
```

**AFTER:**
```python
@pytest.fixture
async def redis_mock():
    """Mock Redis client."""
    mock = AsyncMock()
    # Old JSON string methods (still used for profile cache)
    mock.get = AsyncMock()
    mock.setex = AsyncMock()
    # New Redis Hash methods (used for profile metadata)
    mock.hgetall = AsyncMock()
    mock.hget = AsyncMock()
    mock.hincrby = AsyncMock()
    mock.hset = AsyncMock()
    mock.expire = AsyncMock()
    mock.exists = AsyncMock()
    mock.close = AsyncMock()
    return mock
```

#### Change 2: Updated check_refresh_triggers tests

**BEFORE:**
```python
# Mock Redis get to return None (no metadata)
redis_mock.get.return_value = None

result = await profile_manager.check_refresh_triggers(user_id)

redis_mock.get.assert_called_once_with(f"profile_meta:{user_id}")
```

**AFTER:**
```python
# Mock Redis hgetall to return empty dict (no metadata)
redis_mock.hgetall.return_value = {}

result = await profile_manager.check_refresh_triggers(user_id)

redis_mock.hgetall.assert_called_once_with(f"profile_meta:{user_id}")
```

**For message count tests:**
```python
# Redis Hash returns dict with STRING values (not int!)
metadata = {
    "message_count": str(count),  # String, not int
    "last_refresh": datetime.now(timezone.utc).isoformat()
}
redis_mock.hgetall.return_value = metadata
```

#### Change 3: Updated increment_message_count tests

**BEFORE:**
```python
# Mock Redis get to return None (new user)
redis_mock.get.return_value = None

count = await profile_manager.increment_message_count(user_id)

assert count == 1
redis_mock.setex.assert_called_once()
```

**AFTER:**
```python
# Mock Redis hincrby to return 1 (first increment)
redis_mock.hincrby.return_value = 1

count = await profile_manager.increment_message_count(user_id)

assert count == 1

# Verify HINCRBY was called correctly
redis_mock.hincrby.assert_called_once_with(f"profile_meta:{user_id}", "message_count", 1)

# Verify EXPIRE was called to set TTL
redis_mock.expire.assert_called_once_with(f"profile_meta:{user_id}", 86400)
```

#### Change 4: Updated refresh_profile_background test

**BEFORE:**
```python
# Verify Redis setex was called with correct data
assert redis_mock.setex.call_count == 2  # profile + metadata
```

**AFTER:**
```python
# Verify profile was cached using SETEX (still uses JSON for profile cache)
assert redis_mock.setex.call_count == 1  # profile only

# Verify _update_last_refresh was called (uses HSET + EXPIRE for metadata)
redis_mock.hset.assert_called_once()
hset_call = redis_mock.hset.call_args[0]
assert hset_call[0] == f"profile_meta:{user_id}"
assert hset_call[1] == "last_refresh"

# Verify EXPIRE was called to set TTL on metadata
redis_mock.expire.assert_called_once_with(f"profile_meta:{user_id}", 86400)
```

---

## Verification

### Bug 1: Bare Except Fix

**Test Invalid Timezone:**
```python
profile = {
    "completeness": 50,
    "basics": {"timezone": "Invalid/Timezone"}
}

formatted = format_profile_for_prompt(profile)
# Should log warning but not crash
# Logs: WARNING: Failed to convert timezone: Invalid/Timezone
```

### Bug 2: Unit Test Compatibility

**Run Tests:**
```bash
docker compose exec -T backend python -m pytest tests/unit/test_profile_manager.py -v
```

**Results:**
```
============================= test session starts ==============================
collected 12 items

tests/unit/test_profile_manager.py::test_load_profile_from_cache_hit PASSED [  8%]
tests/unit/test_profile_manager.py::test_load_profile_from_cache_miss PASSED [ 16%]
tests/unit/test_profile_manager.py::test_load_profile_redis_error_graceful_degradation PASSED [ 25%]
tests/unit/test_profile_manager.py::test_refresh_profile_background_success PASSED [ 33%]
tests/unit/test_profile_manager.py::test_refresh_profile_background_mcp_failure PASSED [ 41%]
tests/unit/test_profile_manager.py::test_check_refresh_triggers_first_time PASSED [ 50%]
tests/unit/test_profile_manager.py::test_check_refresh_triggers_message_count PASSED [ 58%]
tests/unit/test_profile_manager.py::test_check_refresh_triggers_time_based PASSED [ 66%]
tests/unit/test_profile_manager.py::test_increment_message_count_new_user PASSED [ 75%]
tests/unit/test_profile_manager.py::test_increment_message_count_existing_user PASSED [ 83%]
tests/unit/test_profile_manager.py::test_profile_manager_close PASSED    [ 91%]
tests/unit/test_profile_manager.py::test_profile_manager_close_owned_redis PASSED [100%]

============================== 12 passed in 1.63s =============================
```

✅ All 12 tests passed!

---

## Impact Assessment

### Before Fixes
- ❌ **Bug 1**: Timezone errors silently swallowed, no logging, KeyboardInterrupt could be caught
- ❌ **Bug 2**: Unit tests would fail after Redis Hash migration, no test coverage for Hash methods

### After Fixes
- ✅ **Bug 1**: Specific exception handling, errors logged with context, system signals not caught
- ✅ **Bug 2**: Tests compatible with Redis Hash implementation, all 12 tests passing
- ✅ No behavioral changes in production code
- ✅ Better debugging and error visibility
- ✅ Reliable test coverage for profile management

---

## Related Files

**Bug 1:**
- `backend/api/prompts.py` - Fixed bare except clause (lines 115-129)

**Bug 2:**
- `backend/tests/unit/test_profile_manager.py` - Updated all tests to use Hash methods
  - Updated fixture (lines 15-30)
  - Updated 6 test functions to use hgetall/hget/hincrby/hset/expire

---

## Lessons Learned

1. **Never use bare except clauses** - Always catch specific exceptions and log errors
2. **Update tests with implementation changes** - When refactoring data structures, update tests to match
3. **Redis Hash methods return strings** - Remember that HGETALL returns string values, not native types
4. **Test mocks must match actual API** - Mock the methods that are actually called, not legacy methods
5. **Atomic operations need different test patterns** - HINCRBY/HSET don't need pre-read mocks

---

## Rollout

- **Status**: Fixed ✅
- **Deployed**: Backend restarted
- **Tests**: All 12 ProfileManager unit tests passing
- **Monitoring**: Watch for timezone conversion warnings in logs

---

## Additional Notes

### Why Redis Hash for Metadata but JSON for Profile Cache?

**Metadata (Hash):**
- Needs atomic field updates (message_count, last_refresh updated independently)
- Prevents race conditions between concurrent updates
- Perfect for Redis Hash (HINCRBY, HSET are atomic)

**Profile Cache (JSON String):**
- Entire profile replaced atomically on refresh
- No partial updates needed
- JSON string simpler for complete object storage

This hybrid approach optimizes for each use case!
