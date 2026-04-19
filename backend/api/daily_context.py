"""
Daily Context Scratchpad — read side (Epic 22 - Story 22.2 + 22.2.1 + 22.2.2)

Provides the read-side helpers for the per-user day-scoped scratchpad. The
write side and the historical-day read side both live in the MCP server
(`mcp_server/tools/daily_context.py` — `update_daily_context` and
`get_daily_context` tools). This module is used by the chat pipeline to
inject TODAY's scratchpad into every system prompt as
`[CURRENT_DAY_CONTEXT]`.

Design
------
- Key:   `daily_context:{user_id}:{YYYY-MM-DD Pacific}`  (one per day)
- Value: JSON dict keyed by LLM-chosen key names (free-form snake_case),
         each holding a string.
- TTL:   30-day rolling, fixed-horizon per key. The MCP write side sets
         `expireat` = (Pacific midnight of the date in the key) + 30 days,
         so each day's scratchpad vanishes on a deterministic date. DST-safe
         via pytz localize.
- Keys:  Free-form (22.2.2). Pre-22.2.2 the set was a fixed enum
         (schedule / meals / workout / mood / open_loops / decisions_today);
         now the LLM picks semantic names per fact. Validation lives in the
         MCP tool — this read side accepts whatever is in Redis and renders
         in insertion order.

Prompt-injection semantics: TODAY ONLY
--------------------------------------
This module only reads today's scratchpad for the prompt. Past days live in
Redis for 30 days but are fetched on-demand by the LLM calling
`get_daily_context(date=..., days_ago=...)` — NOT dumped into every prompt.
30 days of keys would bloat every turn.

Why a Pacific-local key and not a UTC one?
------------------------------------------
Ankit is the sole user, on Pacific time, tracking an 8-week body
recomposition. "Today" means today for him, not today in UTC. The key
includes the Pacific date so a single conversation spanning midnight UTC
but not midnight Pacific keeps accumulating into the same scratchpad.

Graceful degradation
--------------------
All reads return `None` on Redis failure. The consumer (stream.py) treats
`None` as "no scratchpad this turn" and renders nothing. We never block a
chat turn on scratchpad problems.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pytz

from api.logging import get_logger

logger = get_logger(__name__)

_PACIFIC = pytz.timezone("America/Los_Angeles")


def pacific_date_str(now: Optional[datetime] = None) -> str:
    """Return the current Pacific-local date as YYYY-MM-DD."""
    if now is None:
        now = datetime.now(_PACIFIC)
    elif now.tzinfo is None:
        now = _PACIFIC.localize(now)
    else:
        now = now.astimezone(_PACIFIC)
    return now.strftime("%Y-%m-%d")


def next_midnight_pacific_epoch(now: Optional[datetime] = None) -> int:
    """
    Return the unix epoch second of the next Pacific midnight.

    DST-safe: builds a naive datetime at (tomorrow, 00:00) and localizes via
    pytz so the transition days round correctly. Retained for back-compat
    with pre-22.2.1 tests; production TTL now uses
    `mcp_server.tools.daily_context.eviction_epoch_for_pacific_date` for a
    fixed 30-day horizon instead of this next-midnight value.
    """
    if now is None:
        now_pac = datetime.now(_PACIFIC)
    elif now.tzinfo is None:
        now_pac = _PACIFIC.localize(now)
    else:
        now_pac = now.astimezone(_PACIFIC)

    tomorrow = now_pac.date() + timedelta(days=1)
    naive_midnight = datetime(tomorrow.year, tomorrow.month, tomorrow.day, 0, 0, 0)
    midnight_pac = _PACIFIC.localize(naive_midnight)
    return int(midnight_pac.timestamp())


def daily_context_key(user_id: str, now: Optional[datetime] = None) -> str:
    """Compose the Redis key for a user's scratchpad on today's Pacific date."""
    return f"daily_context:{user_id}:{pacific_date_str(now)}"


def format_for_prompt(scratchpad: Optional[Dict[str, Any]]) -> str:
    """
    Render the scratchpad dict as the `[CURRENT_DAY_CONTEXT]` prompt block.

    Iterates keys in INSERTION ORDER (Python dict ordering, preserved across
    `json.dumps` / `json.loads` in Redis). That is: the order the LLM first
    wrote each key today. Feels like a journal.

    Returns empty string when the scratchpad is empty or every value is
    blank. Callers should skip appending when the return value is falsy.
    Blank / whitespace-only / None values are treated as absent — that is
    the CLEAR mechanism (writing empty string clears a key from the prompt).
    """
    if not scratchpad or not isinstance(scratchpad, dict):
        return ""

    lines = []
    for key, value in scratchpad.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if not value:
                continue
        else:
            value = str(value)
        lines.append(f"- {key}: {value}")

    if not lines:
        return ""

    header = (
        "[CURRENT_DAY_CONTEXT]\n"
        "Today's scratchpad (Pacific) — what the user has told you in "
        "conversation so far today. Use as recent context; still call tools "
        "for anything external, fresh, or high-stakes. Update with "
        "`update_daily_context(key, value)` — snake_case keys, reuse "
        "existing keys across the day rather than creating siblings."
    )
    return header + "\n" + "\n".join(lines)


class DailyContextManager:
    """Backend read-side helper around the scratchpad Redis key."""

    def __init__(self, redis_client):
        self.redis_client = redis_client

    async def get_scratchpad(
        self, user_id: str, now: Optional[datetime] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Read today's scratchpad for `user_id`. Returns None when unset or on
        Redis error (graceful degradation — never raises to the caller).
        """
        if not user_id:
            return None
        key = daily_context_key(user_id, now)
        try:
            raw = await self.redis_client.get(key)
        except Exception as e:
            logger.warning(
                "Failed to read daily_context scratchpad",
                extra={"user_id": user_id, "key": key, "error": str(e)},
            )
            return None
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(
                "Corrupt daily_context payload, ignoring",
                extra={"user_id": user_id, "key": key, "error": str(e)},
            )
            return None
        if not isinstance(data, dict):
            return None
        return data

    async def get_scratchpad_prompt_block(
        self, user_id: str, now: Optional[datetime] = None
    ) -> str:
        """Convenience: read and format in one call."""
        scratchpad = await self.get_scratchpad(user_id, now)
        return format_for_prompt(scratchpad)
