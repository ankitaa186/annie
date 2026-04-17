"""
Unit tests for mcp_server/tools/daily_context.py (Epic 22 - Story 22.2
+ 22.2.1 + 22.2.2).

Covers:
- Tool schema shape (22.2.2: free-form keys with a validator, no enum).
- Key validator (regex, length, types).
- Per-day key-count cap (KEY_LIMIT_EXCEEDED).
- Validation on bad inputs (missing user_id, invalid key, oversized value).
- Redis write round-trip (append to dict + expireat, insertion order).
- 30-day fixed-horizon TTL via `eviction_epoch_for_pacific_date`.
- Graceful error path when Redis is unavailable.
- `get_daily_context` historical fetch tool: validation, hit, miss,
  corrupt payload, Redis failure, mutual exclusion, range checks.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytz

from mcp_server.tools.daily_context import (
    DAILY_CONTEXT_TTL_DAYS,
    MAX_KEYS_PER_DAY,
    MAX_VALUE_CHARS,
    MAX_SLOT_CHARS,  # back-compat alias
    _key,
    _key_for_date,
    _validate_key,
    eviction_epoch_for_pacific_date,
    get_daily_context_tool,
    get_daily_context_tool_handler,
    update_daily_context_tool,
    update_daily_context_tool_handler,
)


class TestToolSchema:
    def test_tool_has_required_fields(self):
        assert update_daily_context_tool["name"] == "update_daily_context"
        assert "description" in update_daily_context_tool
        assert "inputSchema" in update_daily_context_tool
        assert callable(update_daily_context_tool["handler"])
        assert update_daily_context_tool["handler"] is update_daily_context_tool_handler

    def test_schema_requires_user_id_key_value(self):
        schema = update_daily_context_tool["inputSchema"]
        assert set(schema["required"]) == {"user_id", "key", "value"}

    def test_schema_uses_pattern_not_enum(self):
        """22.2.2: keys are free-form, validated by regex — no enum."""
        schema = update_daily_context_tool["inputSchema"]
        key_prop = schema["properties"]["key"]
        assert "pattern" in key_prop
        # Regex must be snake_case-ish, start with letter.
        assert key_prop["pattern"] == r"^[a-z][a-z0-9_]{0,31}$"
        assert key_prop["maxLength"] == 32
        # Old enum field must be gone.
        assert "enum" not in key_prop

    def test_description_references_scratchpad_vs_store_memory(self):
        desc = update_daily_context_tool["description"]
        assert "CURRENT_DAY_CONTEXT" in desc
        assert "store_memory" in desc  # decision tree must contrast the two

    def test_description_advertises_free_form_keys(self):
        """22.2.2: description must advertise a common-examples list WITHOUT
        presenting it as exhaustive. Also must mention the key-count cap."""
        desc = update_daily_context_tool["description"]
        assert "meals" in desc
        assert "house_hunting" in desc or "trip_plans" in desc or "debugging" in desc
        # Cap must be mentioned so the LLM knows why KEY_LIMIT_EXCEEDED fires.
        assert str(MAX_KEYS_PER_DAY) in desc

    def test_max_slot_chars_back_compat_alias(self):
        """22.2.2: `MAX_SLOT_CHARS` kept as alias of `MAX_VALUE_CHARS` for
        any callers / tests that import the old name. Guard the alias."""
        assert MAX_SLOT_CHARS == MAX_VALUE_CHARS


class TestKeyValidator:
    @pytest.mark.parametrize("key", [
        "meals",
        "schedule",
        "workout",
        "house_hunting",
        "trip_plans",
        "debugging",
        "pet_medication",
        "open_loops",
        "decisions_today",
        "a",           # single-char allowed (must start with letter)
        "topic_123",   # digits allowed after first char
        "x" * 32,      # max length
    ])
    def test_accepts_valid_keys(self, key):
        assert _validate_key(key) is None

    @pytest.mark.parametrize("key", [
        "",                      # empty
        "Meals",                 # uppercase
        "HOUSE_HUNTING",         # all-uppercase
        "house-hunting",         # hyphen not allowed (snake_case only)
        "house hunting",         # space
        " meals",                # leading whitespace
        "meals ",                # trailing whitespace
        "1meal",                 # leading digit
        "_meals",                # leading underscore
        "meals.breakfast",       # dot
        "meals:breakfast",       # colon (would collide with redis key)
        "meals/lunch",           # slash
        "meals\n",               # newline
        "😀_happy",              # emoji
        "x" * 33,                # too long
    ])
    def test_rejects_invalid_keys(self, key):
        err = _validate_key(key)
        assert err is not None
        assert isinstance(err, str)

    def test_rejects_non_string_keys(self):
        assert _validate_key(None) is not None
        assert _validate_key(123) is not None
        assert _validate_key(["meals"]) is not None


class TestValidation:
    @pytest.mark.asyncio
    async def test_rejects_missing_user_id(self):
        result = await update_daily_context_tool_handler("", "meals", "eggs")
        assert result["status"] == "error"
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_rejects_invalid_key_format(self):
        result = await update_daily_context_tool_handler("user_1", "House Hunting!", "x")
        assert result["status"] == "error"
        assert result["error_code"] == "VALIDATION_ERROR"
        # Error message should explain the format so the LLM learns.
        assert "lowercase" in result["message"].lower() or "snake_case" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_rejects_uppercase_key(self):
        """Uppercase is rejected, not silently lowercased — prevents Meals vs
        meals drift between turns that could otherwise land in the same dict
        as two distinct keys."""
        result = await update_daily_context_tool_handler("user_1", "Meals", "eggs")
        assert result["status"] == "error"
        assert result["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_oversized_value_is_truncated_not_rejected(self):
        """We truncate rather than reject so a slightly-too-long value still
        lands in the scratchpad (partial > nothing)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        huge = "x" * (MAX_VALUE_CHARS + 500)
        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler("user_1", "meals", huge)

        assert result["status"] == "success"
        stored_json = fake_pipe.set.call_args.args[1]
        stored = json.loads(stored_json)
        assert len(stored["meals"]) == MAX_VALUE_CHARS


class TestRedisRoundTrip:
    @pytest.mark.asyncio
    async def test_writes_new_key_to_empty_scratchpad(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler(
                "user_42", "meals", "eggs + toast"
            )

        assert result["status"] == "success"
        assert result["key"] == "meals"
        assert result["keys_currently_set"] == ["meals"]

        # Verify the set payload is a dict with the key.
        set_call = fake_pipe.set.call_args
        stored_key = set_call.args[0]
        assert stored_key.startswith("daily_context:user_42:")
        stored = json.loads(set_call.args[1])
        assert stored == {"meals": "eggs + toast"}

        # 22.2.1: expireat should land at today's-Pacific-midnight + 30 days
        # (fixed horizon, computed from the date in the key — not rolling).
        expire_call = fake_pipe.expireat.call_args
        assert expire_call.args[0] == stored_key
        epoch = expire_call.args[1]
        assert epoch > 0
        date_in_key = stored_key.rsplit(":", 1)[-1]
        assert epoch == eviction_epoch_for_pacific_date(date_in_key)
        _PAC = pytz.timezone("America/Los_Angeles")
        evict_dt = datetime.fromtimestamp(epoch, tz=_PAC)
        y, m, d = [int(x) for x in date_in_key.split("-")]
        expected = _PAC.localize(datetime(y, m, d)) + timedelta(days=DAILY_CONTEXT_TTL_DAYS)
        assert evict_dt == expected

    @pytest.mark.asyncio
    async def test_preserves_other_keys_when_updating_one(self):
        existing = json.dumps({"meals": "eggs", "schedule": "dentist 3pm"})
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=existing)

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler(
                "user_42", "workout", "5k run, felt great"
            )

        assert result["status"] == "success"
        stored = json.loads(fake_pipe.set.call_args.args[1])
        assert stored == {
            "meals": "eggs",
            "schedule": "dentist 3pm",
            "workout": "5k run, felt great",
        }
        assert set(result["keys_currently_set"]) == {"meals", "schedule", "workout"}

    @pytest.mark.asyncio
    async def test_accepts_free_form_key_outside_old_enum(self):
        """22.2.2: `house_hunting` was never in the old slot enum — must work."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler(
                "user_42", "house_hunting", "apt B wins for natural light; apt C has garage"
            )

        assert result["status"] == "success"
        stored = json.loads(fake_pipe.set.call_args.args[1])
        assert stored == {"house_hunting": "apt B wins for natural light; apt C has garage"}

    @pytest.mark.asyncio
    async def test_corrupt_existing_value_is_reset(self):
        """If the stored JSON is corrupt, we start fresh rather than crash."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="{not json")

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler("user_42", "mood", "fine")

        assert result["status"] == "success"
        stored = json.loads(fake_pipe.set.call_args.args[1])
        assert stored == {"mood": "fine"}

    @pytest.mark.asyncio
    async def test_empty_value_clears_key_from_prompt(self):
        """22.2.2: writing empty string is the documented CLEAR mechanism.
        The handler still writes the key with "" value — `format_for_prompt`
        (backend-side) then strips it from the rendered block."""
        existing = json.dumps({"meals": "eggs", "schedule": "dentist 3pm"})
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=existing)

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler("user_42", "schedule", "")

        assert result["status"] == "success"
        stored = json.loads(fake_pipe.set.call_args.args[1])
        # Key is kept at "" — render-side hides it; write-side doesn't delete.
        assert stored == {"meals": "eggs", "schedule": ""}


class TestKeyCountCap:
    @pytest.mark.asyncio
    async def test_rejects_new_key_once_at_cap(self):
        """22.2.2: per-day cap of MAX_KEYS_PER_DAY keys. When full, a NEW
        key is rejected with KEY_LIMIT_EXCEEDED and guidance to consolidate."""
        full = {f"topic_{i}": f"v{i}" for i in range(MAX_KEYS_PER_DAY)}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(full))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler(
                "user_42", "another_topic", "this should be rejected"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "KEY_LIMIT_EXCEEDED"
        # Tell the LLM what keys exist so it can pick one to reuse.
        assert result["keys_currently_set"] == sorted(full.keys())
        assert "consolidate" in result["message"].lower() or "reuse" in result["message"].lower()

    @pytest.mark.asyncio
    async def test_updates_to_existing_key_always_allowed_even_at_cap(self):
        """Updating a key that already exists does NOT create a new slot —
        the cap only gates brand-new keys. Otherwise the LLM couldn't keep
        updating `meals` on a full-day."""
        full = {f"topic_{i}": f"v{i}" for i in range(MAX_KEYS_PER_DAY)}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(full))

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler(
                "user_42", "topic_3", "updated value for topic_3"
            )

        assert result["status"] == "success"
        stored = json.loads(fake_pipe.set.call_args.args[1])
        assert stored["topic_3"] == "updated value for topic_3"
        # Still MAX_KEYS_PER_DAY keys — no growth.
        assert len(stored) == MAX_KEYS_PER_DAY

    @pytest.mark.asyncio
    async def test_writes_up_to_cap_succeed(self):
        """Exactly at cap, another NEW key is blocked; the one AT-cap write
        itself (the MAX_KEYS_PER_DAY-th key) still succeeds."""
        just_under = {f"topic_{i}": f"v{i}" for i in range(MAX_KEYS_PER_DAY - 1)}
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(just_under))

        fake_pipe = MagicMock()
        fake_pipe.set = MagicMock(return_value=fake_pipe)
        fake_pipe.expireat = MagicMock(return_value=fake_pipe)
        fake_pipe.execute = AsyncMock(return_value=[True, True])
        mock_redis.pipeline = MagicMock(return_value=fake_pipe)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler(
                "user_42", "final_topic", "this is the MAX-th key, should land"
            )

        assert result["status"] == "success"
        stored = json.loads(fake_pipe.set.call_args.args[1])
        assert len(stored) == MAX_KEYS_PER_DAY
        assert stored["final_topic"] == "this is the MAX-th key, should land"


class TestFailureModes:
    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_error_code(self):
        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=None):
            result = await update_daily_context_tool_handler("user_1", "meals", "x")
        assert result["status"] == "error"
        assert result["error_code"] == "REDIS_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_redis_exception_returns_internal_error(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("conn reset"))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            result = await update_daily_context_tool_handler("user_1", "meals", "x")
        assert result["status"] == "error"
        assert result["error_code"] == "INTERNAL_ERROR"


class TestKeyFormat:
    def test_key_uses_pacific_date(self):
        noon_pac = pytz.timezone("America/Los_Angeles").localize(
            datetime(2026, 4, 15, 12, 0, 0)
        )
        assert _key("user_9", noon_pac) == "daily_context:user_9:2026-04-15"

    def test_key_for_date_composes_directly(self):
        assert _key_for_date("user_9", "2026-03-01") == "daily_context:user_9:2026-03-01"


class TestEvictionEpochFixedHorizon:
    """22.2.1: TTL is a deterministic function of the date-in-key, not the
    current time. Backfill writes don't extend the horizon."""

    def test_horizon_is_exactly_30_days_past_date_midnight_pacific(self):
        epoch = eviction_epoch_for_pacific_date("2026-04-16")
        _PAC = pytz.timezone("America/Los_Angeles")
        dt = datetime.fromtimestamp(epoch, tz=_PAC)
        assert dt == _PAC.localize(datetime(2026, 5, 16, 0, 0, 0))

    def test_horizon_crosses_dst_spring_forward(self):
        # Pacific DST spring-forward 2026: Mar 8. A Feb 20 key + 30 days =
        # Mar 22 — crosses the transition. Midnight Pacific must still be
        # midnight Pacific (PDT post-transition).
        epoch = eviction_epoch_for_pacific_date("2026-02-20")
        _PAC = pytz.timezone("America/Los_Angeles")
        dt = datetime.fromtimestamp(epoch, tz=_PAC)
        assert dt == _PAC.localize(datetime(2026, 3, 22, 0, 0, 0))
        assert dt.hour == 0 and dt.minute == 0  # true midnight in local PT

    def test_horizon_crosses_dst_fall_back(self):
        # Pacific fall-back 2026: Nov 1. An Oct 15 key + 30 days = Nov 14.
        epoch = eviction_epoch_for_pacific_date("2026-10-15")
        _PAC = pytz.timezone("America/Los_Angeles")
        dt = datetime.fromtimestamp(epoch, tz=_PAC)
        assert dt == _PAC.localize(datetime(2026, 11, 14, 0, 0, 0))

    def test_horizon_is_deterministic_across_multiple_calls(self):
        a = eviction_epoch_for_pacific_date("2026-04-16")
        b = eviction_epoch_for_pacific_date("2026-04-16")
        assert a == b  # no dependence on wall clock


class TestGetDailyContextSchema:
    def test_tool_has_required_fields(self):
        assert get_daily_context_tool["name"] == "get_daily_context"
        assert "description" in get_daily_context_tool
        assert "inputSchema" in get_daily_context_tool
        assert callable(get_daily_context_tool["handler"])
        assert get_daily_context_tool["handler"] is get_daily_context_tool_handler

    def test_schema_requires_only_user_id(self):
        # date vs. days_ago is enforced in the handler, not the schema,
        # because JSONSchema oneOf is awkward. Schema requires user_id only.
        schema = get_daily_context_tool["inputSchema"]
        assert schema["required"] == ["user_id"]
        assert "date" in schema["properties"]
        assert "days_ago" in schema["properties"]

    def test_days_ago_bounds_match_ttl_horizon(self):
        prop = get_daily_context_tool["inputSchema"]["properties"]["days_ago"]
        assert prop["minimum"] == 0
        assert prop["maximum"] == DAILY_CONTEXT_TTL_DAYS

    def test_description_warns_against_hallucination(self):
        desc = get_daily_context_tool["description"]
        # Must tell the LLM what to do on miss.
        assert "found: false" in desc or "found:false" in desc.replace(" ", "")
        assert "hallucinate" in desc.lower() or "do not hallucinate" in desc.lower()


class TestGetDailyContextValidation:
    @pytest.mark.asyncio
    async def test_rejects_missing_user_id(self):
        r = await get_daily_context_tool_handler("", days_ago=1)
        assert r["status"] == "error"
        assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_rejects_neither_date_nor_days_ago(self):
        r = await get_daily_context_tool_handler("user_1")
        assert r["status"] == "error"
        assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_rejects_both_date_and_days_ago(self):
        r = await get_daily_context_tool_handler("user_1", date="2026-04-15", days_ago=1)
        assert r["status"] == "error"
        assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_rejects_days_ago_out_of_range(self):
        for bad in (-1, DAILY_CONTEXT_TTL_DAYS + 1, 365):
            r = await get_daily_context_tool_handler("user_1", days_ago=bad)
            assert r["status"] == "error"
            assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_rejects_malformed_date(self):
        for bad in ("yesterday", "2026/04/15", "04-15-2026", "not a date", ""):
            r = await get_daily_context_tool_handler("user_1", date=bad)
            assert r["status"] == "error"
            assert r["error_code"] == "VALIDATION_ERROR"

    @pytest.mark.asyncio
    async def test_rejects_future_date(self):
        # 10 years from now — guaranteed to be in the future regardless of
        # when the test runs.
        future = (datetime.now(pytz.timezone("America/Los_Angeles")).date()
                  + timedelta(days=3650)).strftime("%Y-%m-%d")
        r = await get_daily_context_tool_handler("user_1", date=future)
        assert r["status"] == "error"
        assert r["error_code"] == "VALIDATION_ERROR"


class TestGetDailyContextFetch:
    @pytest.mark.asyncio
    async def test_hit_returns_scratchpad_dict(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({"meals": "eggs", "workout": "5k"}))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", days_ago=1)

        assert r["status"] == "success"
        assert r["found"] is True
        assert r["scratchpad"] == {"meals": "eggs", "workout": "5k"}
        # Key used should be yesterday's Pacific date.
        yesterday_pac = (datetime.now(pytz.timezone("America/Los_Angeles")).date()
                         - timedelta(days=1)).strftime("%Y-%m-%d")
        assert r["date"] == yesterday_pac
        mock_redis.get.assert_awaited_once_with(f"daily_context:user_42:{yesterday_pac}")

    @pytest.mark.asyncio
    async def test_hit_returns_free_form_keys(self):
        """22.2.2: historical days may contain keys outside the old enum —
        the fetch tool must return them as-is."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "house_hunting": "apt B",
            "meals": "eggs",
            "debugging": "flaky test fixed",
        }))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", days_ago=3)

        assert r["status"] == "success"
        assert r["found"] is True
        assert r["scratchpad"] == {
            "house_hunting": "apt B",
            "meals": "eggs",
            "debugging": "flaky test fixed",
        }

    @pytest.mark.asyncio
    async def test_miss_returns_found_false_not_error(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", days_ago=5)

        assert r["status"] == "success"
        assert r["found"] is False
        assert r["scratchpad"] is None

    @pytest.mark.asyncio
    async def test_corrupt_json_treated_as_miss(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="{not json")
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", days_ago=3)

        assert r["status"] == "success"
        assert r["found"] is False
        assert r["scratchpad"] is None

    @pytest.mark.asyncio
    async def test_non_dict_payload_treated_as_miss(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(["a", "b"]))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", days_ago=3)

        assert r["status"] == "success"
        assert r["found"] is False

    @pytest.mark.asyncio
    async def test_redis_unavailable_returns_error(self):
        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=None):
            r = await get_daily_context_tool_handler("user_1", days_ago=1)
        assert r["status"] == "error"
        assert r["error_code"] == "REDIS_UNAVAILABLE"

    @pytest.mark.asyncio
    async def test_redis_exception_returns_internal_error(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("boom"))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_1", days_ago=1)

        assert r["status"] == "error"
        assert r["error_code"] == "INTERNAL_ERROR"

    @pytest.mark.asyncio
    async def test_days_ago_zero_equals_today(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({"meals": "now"}))
        mock_redis.aclose = AsyncMock()

        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", days_ago=0)

        today_pac = datetime.now(pytz.timezone("America/Los_Angeles")).strftime("%Y-%m-%d")
        assert r["status"] == "success"
        assert r["date"] == today_pac
        assert r["found"] is True

    @pytest.mark.asyncio
    async def test_explicit_date_is_used_as_is(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps({"schedule": "dentist"}))
        mock_redis.aclose = AsyncMock()

        # Use a date known to be in the past.
        past = (datetime.now(pytz.timezone("America/Los_Angeles")).date()
                - timedelta(days=7)).strftime("%Y-%m-%d")
        with patch("mcp_server.tools.daily_context._get_redis_client", return_value=mock_redis):
            r = await get_daily_context_tool_handler("user_42", date=past)

        assert r["status"] == "success"
        assert r["date"] == past
        mock_redis.get.assert_awaited_once_with(f"daily_context:user_42:{past}")
