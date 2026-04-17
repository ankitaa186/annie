"""
Unit tests for backend/api/daily_context.py (Epic 22 - Story 22.2 + 22.2.2).

Covers:
- Pacific-date key math and DST-safe next-midnight-Pacific epoch (retained
  helper for back-compat; prod TTL path is in the MCP write side).
- DailyContextManager round-trip with a mocked Redis.
- format_for_prompt rendering rules:
    * free-form keys (22.2.2) — any dict keys render, no slot enum
    * insertion order preserved (dict ordering across json round-trip)
    * blank / None values stripped (the "clear a key" mechanism)
"""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock

import pytest
import pytz

from api.daily_context import (
    DailyContextManager,
    daily_context_key,
    format_for_prompt,
    next_midnight_pacific_epoch,
    pacific_date_str,
)


_PACIFIC = pytz.timezone("America/Los_Angeles")


class TestPacificDateMath:
    def test_key_uses_pacific_date(self):
        noon_pacific = _PACIFIC.localize(datetime(2026, 4, 15, 12, 0, 0))
        assert daily_context_key("user_1", noon_pacific) == "daily_context:user_1:2026-04-15"

    def test_pacific_date_handles_naive_datetime_as_pacific(self):
        # Convention in our helpers: naive datetimes are LOCALIZED to Pacific,
        # not interpreted as UTC. Ensures test runs are stable regardless of
        # the host's tz.
        assert pacific_date_str(datetime(2026, 4, 15, 12, 0, 0)) == "2026-04-15"

    def test_next_midnight_pacific_normal_day(self):
        noon = _PACIFIC.localize(datetime(2026, 4, 15, 12, 0, 0))
        midnight = datetime.fromtimestamp(next_midnight_pacific_epoch(noon), tz=_PACIFIC)
        assert midnight.year == 2026
        assert midnight.month == 4
        assert midnight.day == 16
        assert midnight.hour == 0
        assert midnight.minute == 0

    def test_next_midnight_pacific_spring_forward(self):
        """DST: 2026 spring-forward is 2026-03-08. Midnight on 2026-03-07 still
        resolves to 2026-03-08 00:00 Pacific (the 23-hour day)."""
        before_dst = _PACIFIC.localize(datetime(2026, 3, 7, 23, 30, 0))
        midnight = datetime.fromtimestamp(next_midnight_pacific_epoch(before_dst), tz=_PACIFIC)
        assert midnight.year == 2026
        assert midnight.month == 3
        assert midnight.day == 8
        assert midnight.hour == 0

    def test_next_midnight_pacific_fall_back(self):
        """DST: 2026 fall-back is 2026-11-01. Midnight on 2026-10-31 resolves
        to 2026-11-01 00:00 Pacific (the 25-hour day)."""
        before_dst = _PACIFIC.localize(datetime(2026, 10, 31, 23, 30, 0))
        midnight = datetime.fromtimestamp(next_midnight_pacific_epoch(before_dst), tz=_PACIFIC)
        assert midnight.year == 2026
        assert midnight.month == 11
        assert midnight.day == 1
        assert midnight.hour == 0


class TestFormatForPrompt:
    def test_empty_scratchpad_returns_empty_string(self):
        assert format_for_prompt(None) == ""
        assert format_for_prompt({}) == ""

    def test_non_dict_scratchpad_returns_empty_string(self):
        # Defensive: if upstream somehow passes a list/string, don't crash.
        assert format_for_prompt(["not", "a", "dict"]) == ""
        assert format_for_prompt("not a dict") == ""

    def test_all_blank_values_returns_empty_string(self):
        # Whitespace-only and None values must be treated as absent — this
        # is the CLEAR-a-key mechanism (write empty string -> key disappears
        # from the rendered block).
        assert format_for_prompt({
            "schedule": "   ",
            "meals": None,
            "workout": "",
        }) == ""

    def test_renders_keys_in_insertion_order(self):
        """22.2.2: insertion order (LLM-chosen) is the render order. No
        canonical slot sequence anymore — feels like a journal."""
        scratchpad = {
            "meals": "eggs + toast",
            "schedule": "dentist 3pm",
        }
        rendered = format_for_prompt(scratchpad)
        assert "[CURRENT_DAY_CONTEXT]" in rendered
        meals_pos = rendered.find("- meals:")
        sched_pos = rendered.find("- schedule:")
        # meals was inserted first -> renders first.
        assert 0 < meals_pos < sched_pos
        assert "dentist 3pm" in rendered
        assert "eggs + toast" in rendered

    def test_renders_arbitrary_llm_chosen_keys(self):
        """22.2.2: keys like `house_hunting`, `debugging`, `trip_plans` that
        weren't in the old enum must render normally."""
        scratchpad = {
            "house_hunting": "3 options in Redmond under review",
            "debugging": "flaky redis test in test_memory_queue",
            "pet_medication": "cat: 1 dose at 8am, 1 at 8pm",
        }
        rendered = format_for_prompt(scratchpad)
        assert "- house_hunting: 3 options in Redmond under review" in rendered
        assert "- debugging: flaky redis test in test_memory_queue" in rendered
        assert "- pet_medication: cat: 1 dose at 8am, 1 at 8pm" in rendered

    def test_mixed_old_and_new_keys_both_render(self):
        """22.2.2: a scratchpad that mixes pre-22.2.2 enum keys (meals) with
        free-form keys (house_hunting) must render fully. No special casing."""
        scratchpad = {
            "meals": "eggs",
            "house_hunting": "apt B wins for light",
            "workout": "5k",
        }
        rendered = format_for_prompt(scratchpad)
        assert "- meals: eggs" in rendered
        assert "- house_hunting: apt B wins for light" in rendered
        assert "- workout: 5k" in rendered

    def test_renders_twenty_keys_without_truncation(self):
        """Per-day cap is 20 keys — verify the render handles a full day."""
        scratchpad = {f"topic_{i}": f"value-{i}" for i in range(20)}
        rendered = format_for_prompt(scratchpad)
        for i in range(20):
            assert f"- topic_{i}: value-{i}" in rendered

    def test_blank_value_for_one_key_removes_only_that_key(self):
        scratchpad = {
            "meals": "eggs",
            "schedule": "",  # cleared
            "workout": "5k",
        }
        rendered = format_for_prompt(scratchpad)
        assert "- meals: eggs" in rendered
        assert "- workout: 5k" in rendered
        assert "- schedule:" not in rendered

    def test_non_string_values_coerced(self):
        rendered = format_for_prompt({"open_loops": ["call plumber", "email mom"]})
        assert "- open_loops:" in rendered
        assert "call plumber" in rendered


class TestDailyContextManagerRoundTrip:
    @pytest.mark.asyncio
    async def test_get_scratchpad_returns_dict_on_success(self):
        payload = json.dumps({"meals": "eggs", "schedule": "dentist 3pm"})
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=payload)

        mgr = DailyContextManager(mock_redis)
        result = await mgr.get_scratchpad("user_42")

        assert result == {"meals": "eggs", "schedule": "dentist 3pm"}

    @pytest.mark.asyncio
    async def test_get_scratchpad_preserves_insertion_order_through_json_roundtrip(self):
        """22.2.2: the order the LLM wrote keys is preserved by json.loads,
        so the prompt render matches the journal order. Don't regress this."""
        payload = json.dumps({"zeta_topic": "first", "alpha_topic": "second", "mu_topic": "third"})
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=payload)

        mgr = DailyContextManager(mock_redis)
        result = await mgr.get_scratchpad("user_42")

        assert list(result.keys()) == ["zeta_topic", "alpha_topic", "mu_topic"]

    @pytest.mark.asyncio
    async def test_get_scratchpad_none_on_missing_key(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        mgr = DailyContextManager(mock_redis)
        result = await mgr.get_scratchpad("user_42")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_scratchpad_none_on_corrupt_json(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="{not json")

        mgr = DailyContextManager(mock_redis)
        result = await mgr.get_scratchpad("user_42")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_scratchpad_none_on_non_dict_json(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=json.dumps(["not", "a", "dict"]))

        mgr = DailyContextManager(mock_redis)
        result = await mgr.get_scratchpad("user_42")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_scratchpad_none_on_redis_error(self):
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=RuntimeError("boom"))

        mgr = DailyContextManager(mock_redis)
        # Must not raise — graceful degradation is part of the contract.
        result = await mgr.get_scratchpad("user_42")

        assert result is None

    @pytest.mark.asyncio
    async def test_prompt_block_renders_or_empty(self):
        mock_redis = AsyncMock()

        payload = json.dumps({"meals": "eggs"})
        mock_redis.get = AsyncMock(return_value=payload)
        mgr = DailyContextManager(mock_redis)
        block = await mgr.get_scratchpad_prompt_block("user_42")
        assert "[CURRENT_DAY_CONTEXT]" in block
        assert "eggs" in block

        mock_redis.get = AsyncMock(return_value=None)
        mgr = DailyContextManager(mock_redis)
        block = await mgr.get_scratchpad_prompt_block("user_42")
        assert block == ""

    @pytest.mark.asyncio
    async def test_empty_user_id_returns_none(self):
        mock_redis = AsyncMock()
        mgr = DailyContextManager(mock_redis)
        assert await mgr.get_scratchpad("") is None
