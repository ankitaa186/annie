"""
Daily Context Scratchpad Tool (Epic 22 - Story 22.2 + 22.2.1 + 22.2.2)

MCP tool `update_daily_context(user_id, key, value)` — write side of the
per-user day-scoped scratchpad. Read side lives at
`backend/api/daily_context.py` and renders only TODAY's scratchpad as the
`[CURRENT_DAY_CONTEXT]` block in every system prompt. Historical days are
fetched explicitly via the `get_daily_context` tool in this module.

Storage (30-day rolling)
------------------------
- Redis key:  `daily_context:{user_id}:{YYYY-MM-DD Pacific}`  (one per day)
- Value:      JSON dict keyed by LLM-chosen key names, string values.
- TTL:        `expireat` = (Pacific midnight of the date in the key) + 30 days.
              Fixed horizon (not rolling-on-write), so an older day's key
              expires on a deterministic date regardless of when it was
              last touched. DST-safe via pytz localize.

Prompt-injection (today-only)
-----------------------------
The system prompt only ever renders TODAY's scratchpad as
`[CURRENT_DAY_CONTEXT]`. 30 days of keys would bloat every turn. Historical
days are accessed on-demand by the LLM calling `get_daily_context(date=...)`
or `get_daily_context(days_ago=N)`.

Key contract (22.2.2 — free-form)
---------------------------------
The LLM picks semantic key names for each fact it wants to remember today.
Keys must match ``^[a-z][a-z0-9_]{0,31}$`` — lowercase snake_case, up to 32
chars. Common examples (NOT enforced — just conventions):
  - meals, schedule, workout, mood, open_loops, decisions_today
  - house_hunting, trip_plans, debugging, pet_medication
Pre-22.2.2 the set was enforced as an enum; now it's advisory. The regex
exists to (a) keep rendering / logging predictable, (b) prevent drift
between `Meals` / `meals` / `meals ` across turns, (c) keep keys safe for
JSON and prompt embedding.

Caps
----
- Per-key value length: ``MAX_VALUE_CHARS`` (truncate, don't reject).
- Per-day key count:    ``MAX_KEYS_PER_DAY`` (reject the ADDITION of a new
                         key once the cap is hit; updates to an existing
                         key are always allowed). Stops chatter-key bloat
                         (snack_1 / snack_2 / snack_3 …) — the LLM is told
                         to reuse / consolidate into an existing key.

Last-writer-wins per key: each call overwrites the value for that key.
To APPEND, pass the concatenated value (read current from
`[CURRENT_DAY_CONTEXT]` for today, or `get_daily_context` for past days).
To CLEAR a key for today, write an empty string — `format_for_prompt`
strips blank-valued keys from the rendered block. The key still counts
toward the per-day cap after a clear (it's a used slot with empty value).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pytz
import redis.asyncio as redis

from mcp_server.logging import get_logger

logger = get_logger(__name__)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

_PACIFIC = pytz.timezone("America/Los_Angeles")

# Key validation: snake_case, leading letter, up to 32 chars. Applied to the
# JSON-dict keys the LLM picks — NOT to the Redis key structure.
_KEY_REGEX = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_KEY_REGEX_PATTERN = r"^[a-z][a-z0-9_]{0,31}$"

# Hard cap on per-key value size. The prompt renders every key in every
# turn, so a bloated value quickly burns tokens. 2 KB per key is plenty for
# "today's schedule" or "meals so far".
MAX_VALUE_CHARS = 2000

# Back-compat alias — some tests / callers may still reference the old name.
MAX_SLOT_CHARS = MAX_VALUE_CHARS

# Hard cap on distinct keys per day. At 20 keys x 2000 chars = ~40 KB of
# scratchpad max in the prompt; enough for a rich day, not enough for
# chatter-key bloat.
MAX_KEYS_PER_DAY = 20


def _pacific_date_str(now: Optional[datetime] = None) -> str:
    if now is None:
        now = datetime.now(_PACIFIC)
    elif now.tzinfo is None:
        now = _PACIFIC.localize(now)
    else:
        now = now.astimezone(_PACIFIC)
    return now.strftime("%Y-%m-%d")


# TTL horizon: each day's scratchpad survives this many days past its own
# Pacific midnight before Redis evicts it. Fixed per-key horizon (not rolling
# on write) so a backfill to day D-20 still evicts at D+30, not at write+30.
DAILY_CONTEXT_TTL_DAYS = 30


def eviction_epoch_for_pacific_date(date_str: str) -> int:
    """
    Given a YYYY-MM-DD Pacific date, return the Unix epoch second at which
    that day's scratchpad should expire: Pacific midnight of that date plus
    `DAILY_CONTEXT_TTL_DAYS`. DST-safe via pytz localize.

    Determinism is the point: for key `daily_context:{u}:2026-04-16`, every
    write sets the same `expireat` (2026-05-16 00:00 Pacific). A backfill
    write to yesterday's slot does not extend the horizon.
    """
    year, month, day = [int(x) for x in date_str.split("-")]
    target_date = datetime(year, month, day).date() + timedelta(days=DAILY_CONTEXT_TTL_DAYS)
    naive_midnight = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0)
    midnight_pac = _PACIFIC.localize(naive_midnight)
    return int(midnight_pac.timestamp())


def _key(user_id: str, now: Optional[datetime] = None) -> str:
    """Compose today's Redis key. For historical dates use `_key_for_date`."""
    return f"daily_context:{user_id}:{_pacific_date_str(now)}"


def _key_for_date(user_id: str, date_str: str) -> str:
    """Compose the Redis key for a specific Pacific date (YYYY-MM-DD)."""
    return f"daily_context:{user_id}:{date_str}"


def _get_redis_client() -> Optional[redis.Redis]:
    try:
        return redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    except Exception as e:
        logger.warning(f"Failed to create Redis client for daily_context: {e}")
        return None


def _validate_key(key: str) -> Optional[str]:
    """
    Return an error message string if `key` is invalid, else None.

    Validator is intentionally strict — the LLM should use a consistent
    snake_case vocabulary rather than have surprising silent normalization
    applied to its inputs.
    """
    if not isinstance(key, str):
        return "key must be a string"
    if not key:
        return "key must not be empty"
    if not _KEY_REGEX.fullmatch(key):
        return (
            f"key must match {_KEY_REGEX_PATTERN} — lowercase snake_case, "
            "start with a letter, <= 32 chars (e.g., `meals`, `schedule`, "
            "`house_hunting`)"
        )
    return None


async def update_daily_context_tool_handler(
    user_id: str, key: str, value: str
) -> Dict[str, Any]:
    """
    Write (overwrite) a key in today's scratchpad for `user_id`.

    Args:
        user_id: Telegram user ID (string, numeric).
        key: LLM-chosen semantic key (see validator for format).
        value: Free-text value for the key (<= MAX_VALUE_CHARS).

    Returns:
        {"status": "success", ...} on write,
        {"status": "error", "error_code": ..., "message": ...} on failure.
    """
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "user_id is required",
        }
    key_error = _validate_key(key)
    if key_error:
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": key_error,
        }
    if value is None:
        value = ""
    if not isinstance(value, str):
        value = str(value)
    if len(value) > MAX_VALUE_CHARS:
        value = value[:MAX_VALUE_CHARS]

    redis_client = _get_redis_client()
    if redis_client is None:
        return {
            "status": "error",
            "error_code": "REDIS_UNAVAILABLE",
            "message": "Redis client could not be created",
        }

    today_str = _pacific_date_str()
    redis_key = _key_for_date(user_id, today_str)
    try:
        raw = await redis_client.get(redis_key)
        if raw:
            try:
                data = json.loads(raw)
                if not isinstance(data, dict):
                    data = {}
            except (json.JSONDecodeError, TypeError):
                data = {}
        else:
            data = {}

        # Per-day key-count cap. Updates to EXISTING keys are always allowed
        # (no new slot created); only the addition of a brand-new key when
        # already at the cap is blocked.
        if key not in data and len(data) >= MAX_KEYS_PER_DAY:
            return {
                "status": "error",
                "error_code": "KEY_LIMIT_EXCEEDED",
                "message": (
                    f"Already {len(data)} keys in today's scratchpad "
                    f"(cap {MAX_KEYS_PER_DAY}). Reuse or consolidate an "
                    f"existing key instead of creating a new one. "
                    f"Currently-set keys: {sorted(data.keys())}"
                ),
                "keys_currently_set": sorted(data.keys()),
            }

        data[key] = value

        pipe = redis_client.pipeline()
        pipe.set(redis_key, json.dumps(data))
        # 30-day rolling TTL, fixed per-key horizon (see helper docstring).
        pipe.expireat(redis_key, eviction_epoch_for_pacific_date(today_str))
        await pipe.execute()

        logger.info(
            "daily_context.key_updated",
            extra={
                "user_id": user_id,
                "daily_key": key,
                "value_chars": len(value),
                "redis_key": redis_key,
                "key_count_after": len(data),
            },
        )

        return {
            "status": "success",
            "key": key,
            "message": f"Updated {key}.",
            "keys_currently_set": list(data.keys()),
        }
    except Exception as e:
        logger.error(
            "daily_context.update_failed",
            extra={"user_id": user_id, "daily_key": key, "error": str(e)},
        )
        return {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"Failed to update daily_context: {e}",
        }
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


update_daily_context_tool = {
    "name": "update_daily_context",
    "description": f"""Write or overwrite a key in the user's day-scoped scratchpad.

This writes to TODAY's scratchpad (Pacific time). Today's scratchpad is the
one that appears in your system prompt as [CURRENT_DAY_CONTEXT] at the top
of every turn — so anything you write here is visible to you on the next
turn. Storage is 30-day rolling: each day's keys survive for 30 days past
that day's Pacific midnight, then evict automatically. Past days are NOT
in the prompt; fetch them explicitly via `get_daily_context`.

Use this tool for facts that are meaningful TODAY but shouldn't clutter
permanent memory: what the user ate, today's workout, today's schedule,
current mood, decisions made today, house-hunting options being weighed,
a debugging investigation in flight, a trip itinerary being planned, a
pet's medication schedule, etc.

When to use this tool (vs. store_memory):
- Day-scoped fact (today's state) -> update_daily_context (this tool)
- Permanent preference / biographical fact -> store_memory

Key naming (free-form — YOU choose)
-----------------------------------
Pick a clear, lowercase snake_case name that describes WHAT the fact is
about. Keys must match `{_KEY_REGEX_PATTERN}` (lowercase letters, digits,
underscore, start with a letter, up to 32 chars).

Common examples (not a fixed list):
  meals, schedule, workout, mood, open_loops, decisions_today,
  house_hunting, trip_plans, debugging, pet_medication

Conventions:
- Reuse the same key across the day. If you already have `meals` with
  "eggs + toast", the afternoon update is `meals` = "eggs + toast; chicken
  salad at noon" — not a new key `lunch`.
- Check [CURRENT_DAY_CONTEXT] first and reuse the key that's there.
- There's a {MAX_KEYS_PER_DAY}-key cap per day to prevent bloat. If you hit
  it you'll get a KEY_LIMIT_EXCEEDED error telling you to consolidate.

Last-writer-wins per key: to APPEND, pass the concatenated value yourself.
To CLEAR a key for today, pass an empty string `""` — it stops rendering
in the prompt.
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Exact user ID from the system message (numeric Telegram user ID). NEVER use placeholders like 'default', 'user', 'anonymous', or 'me'.",
            },
            "key": {
                "type": "string",
                "description": f"Lowercase snake_case key naming the fact (e.g., `meals`, `schedule`, `house_hunting`). Must match {_KEY_REGEX_PATTERN}. Reuse an existing key from [CURRENT_DAY_CONTEXT] when the fact fits it — don't create siblings like `breakfast`+`lunch` when `meals` already exists.",
                "pattern": _KEY_REGEX_PATTERN,
                "maxLength": 32,
            },
            "value": {
                "type": "string",
                "description": f"New value for the key (replaces any existing value). Pass empty string to clear. Max {MAX_VALUE_CHARS} chars (longer values are truncated).",
                "maxLength": MAX_VALUE_CHARS,
            },
        },
        "required": ["user_id", "key", "value"],
    },
    "handler": update_daily_context_tool_handler,
}


# --------------------------------------------------------------------------- #
# get_daily_context — historical day fetch                                    #
# --------------------------------------------------------------------------- #


def _date_str_for_days_ago(days_ago: int, now: Optional[datetime] = None) -> str:
    """Return Pacific YYYY-MM-DD for (today - days_ago)."""
    if now is None:
        now_pac = datetime.now(_PACIFIC)
    elif now.tzinfo is None:
        now_pac = _PACIFIC.localize(now)
    else:
        now_pac = now.astimezone(_PACIFIC)
    target = now_pac.date() - timedelta(days=days_ago)
    return target.strftime("%Y-%m-%d")


def _is_valid_date_str(date_str: str) -> bool:
    """Validate YYYY-MM-DD. Returns False on malformed input (incl. 'today')."""
    if not isinstance(date_str, str):
        return False
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except (ValueError, TypeError):
        return False


async def get_daily_context_tool_handler(
    user_id: str,
    date: Optional[str] = None,
    days_ago: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Read a past (or today's) scratchpad for `user_id`.

    Exactly one of `date` (YYYY-MM-DD Pacific) or `days_ago` (0..30) must be
    provided. Returns:
        {"status": "success", "date": "...", "scratchpad": {...}, "found": True}
        {"status": "success", "date": "...", "scratchpad": None, "found": False}
        {"status": "error", ...} on validation / Redis failure.

    A missing day is a SUCCESS with `found=False` — the caller should tell
    the user they don't have a scratchpad for that day, not hallucinate.
    """
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "user_id is required",
        }

    # Mutual exclusion: exactly one of date or days_ago.
    if date is None and days_ago is None:
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Provide exactly one of: date (YYYY-MM-DD) or days_ago (0-30).",
        }
    if date is not None and days_ago is not None:
        return {
            "status": "error",
            "error_code": "VALIDATION_ERROR",
            "message": "Provide only one of date or days_ago, not both.",
        }

    if days_ago is not None:
        if not isinstance(days_ago, int) or isinstance(days_ago, bool):
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "days_ago must be an integer 0-30.",
            }
        if days_ago < 0 or days_ago > DAILY_CONTEXT_TTL_DAYS:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": f"days_ago must be 0-{DAILY_CONTEXT_TTL_DAYS} (scratchpad horizon).",
            }
        date_str = _date_str_for_days_ago(days_ago)
    else:
        if not _is_valid_date_str(date):
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": "date must be YYYY-MM-DD (Pacific).",
            }
        date_str = date
        # Reject future dates — they can't exist.
        today_str = _pacific_date_str()
        if date_str > today_str:
            return {
                "status": "error",
                "error_code": "VALIDATION_ERROR",
                "message": f"date must not be in the future (today Pacific is {today_str}).",
            }

    redis_client = _get_redis_client()
    if redis_client is None:
        return {
            "status": "error",
            "error_code": "REDIS_UNAVAILABLE",
            "message": "Redis client could not be created",
        }

    key = _key_for_date(user_id, date_str)
    try:
        raw = await redis_client.get(key)
        if not raw:
            return {
                "status": "success",
                "date": date_str,
                "scratchpad": None,
                "found": False,
            }
        try:
            data = json.loads(raw)
            if not isinstance(data, dict):
                # Corrupt payload — treat as miss (same behavior as read-side).
                return {
                    "status": "success",
                    "date": date_str,
                    "scratchpad": None,
                    "found": False,
                }
        except (json.JSONDecodeError, TypeError):
            return {
                "status": "success",
                "date": date_str,
                "scratchpad": None,
                "found": False,
            }

        logger.info(
            "daily_context.history_fetched",
            extra={
                "user_id": user_id,
                "date": date_str,
                "key_count": len(data),
                "redis_key": key,
            },
        )
        return {
            "status": "success",
            "date": date_str,
            "scratchpad": data,
            "found": True,
        }
    except Exception as e:
        logger.error(
            "daily_context.history_fetch_failed",
            extra={"user_id": user_id, "date": date_str, "error": str(e)},
        )
        return {
            "status": "error",
            "error_code": "INTERNAL_ERROR",
            "message": f"Failed to fetch daily_context for {date_str}: {e}",
        }
    finally:
        try:
            await redis_client.aclose()
        except Exception:
            pass


get_daily_context_tool = {
    "name": "get_daily_context",
    "description": f"""Read the user's scratchpad for a past (or today's) day.

Today's scratchpad is already in your system prompt as [CURRENT_DAY_CONTEXT]
— you only need this tool for PAST days. Storage is 30-day rolling, so
valid range is today through {DAILY_CONTEXT_TTL_DAYS} days ago.

Use this when the user references something from an earlier day:
- "What did I eat yesterday?"          -> get_daily_context(days_ago=1)
- "What was my workout last Monday?"   -> get_daily_context(date="2026-04-13")
- "How did I feel three days ago?"     -> get_daily_context(days_ago=3)

IMPORTANT: if the response is `found: false`, TELL THE USER you don't have
a scratchpad entry for that day. Do NOT hallucinate what they ate, did, or
felt. Missing days are missing — that's a valid answer.

Do NOT use this tool speculatively or for every turn. Only call it when the
user asks about a specific past day. 30 days of scratchpad in the prompt
would be token bloat.

Parameters: provide exactly ONE of `date` or `days_ago`.
- date:     YYYY-MM-DD Pacific (e.g., "2026-04-13")
- days_ago: integer 0-{DAILY_CONTEXT_TTL_DAYS} (0 = today, 1 = yesterday)

Returns a dict of key -> value (keys are LLM-chosen, varying day to day —
may include `meals`, `schedule`, `workout`, or anything the LLM captured
for that day), or found=false.
""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Exact user ID from the system message (numeric Telegram user ID). NEVER use placeholders like 'default', 'user', 'anonymous', or 'me'.",
            },
            "date": {
                "type": "string",
                "description": "Pacific date YYYY-MM-DD. Mutually exclusive with days_ago.",
                "pattern": r"^\d{4}-\d{2}-\d{2}$",
            },
            "days_ago": {
                "type": "integer",
                "description": f"0 = today, 1 = yesterday, up to {DAILY_CONTEXT_TTL_DAYS}. Mutually exclusive with date.",
                "minimum": 0,
                "maximum": DAILY_CONTEXT_TTL_DAYS,
            },
        },
        "required": ["user_id"],
    },
    "handler": get_daily_context_tool_handler,
}
