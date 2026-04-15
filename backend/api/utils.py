"""
Shared utility functions for the Annie backend API.
"""

import re
from typing import Any, Dict, Optional
import logging

# Threshold for considering a string "large base64" (matches stream.py MEDIA_OFFLOAD_THRESHOLD)
_BASE64_STRIP_THRESHOLD = 64 * 1024  # 64 KB
_BASE64_PATTERN = re.compile(r'^[A-Za-z0-9+/\n]+=*$')


def strip_base64_from_tool_result(
    result: Any,
    threshold: int = _BASE64_STRIP_THRESHOLD,
) -> Any:
    """
    Recursively replace large base64 strings in a tool result with a placeholder.

    This prevents LLMs from seeing raw base64 in conversation context and
    echoing it back as inline ``data:`` URIs in their text responses.
    Only strings that exceed *threshold* **and** consist solely of base64
    characters are replaced.

    Args:
        result: Tool result (dict, list, or primitive).
        threshold: Minimum string length to consider for stripping.

    Returns:
        A shallow copy of *result* with large base64 values replaced by
        ``"[image data removed - sent to user as media]"``.
    """
    if isinstance(result, dict):
        return {k: strip_base64_from_tool_result(v, threshold) for k, v in result.items()}
    if isinstance(result, list):
        return [strip_base64_from_tool_result(item, threshold) for item in result]
    if isinstance(result, str) and len(result) > threshold:
        # Quick check: base64 has no spaces; sample the head to avoid scanning the whole string
        sample = result[:256]
        if _BASE64_PATTERN.match(sample):
            return "[image data removed - sent to user as media]"
    return result


def inject_user_id(
    tool_args: Dict[str, Any],
    user_id: Optional[str],
    logger: logging.Logger,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """
    Inject the correct user_id into tool arguments, overriding any LLM-provided value.

    This prevents LLMs from using incorrect user_ids (e.g., inferring "ankit" from
    profile name instead of using the system-provided Telegram user ID).

    Args:
        tool_args: Tool arguments dictionary (modified in place)
        user_id: Correct user_id to inject
        logger: Logger instance for warning messages
        context: Additional context for log messages (e.g., conversation_id, tool_name)
    """
    if not user_id:
        return

    # Always inject user_id — whether LLM included it or not.
    # Tools that don't accept user_id are protected by the MCP server's
    # parameter filtering (inspect.signature).
    original_user_id = tool_args.get("user_id")
    if original_user_id is not None and original_user_id != user_id:
        log_extra = context.copy() if context else {}
        log_extra.update({
            "original_user_id": original_user_id,
            "correct_user_id": user_id
        })
        logger.warning(
            "Overriding LLM-provided user_id with correct value",
            extra=log_extra
        )
    tool_args["user_id"] = user_id


async def invalidate_profile_cache_if_needed(
    tool_name: str,
    tool_result: Any,
    user_id: Optional[str],
    redis_client: Any,
    logger: logging.Logger,
) -> None:
    """
    Invalidate the profile cache (``profile:{user_id}``) when the
    ``update_user_profile`` MCP tool has completed successfully.

    This ensures the LLM sees fresh profile data on the next
    ``get_user_profile`` call within the same conversation, rather than
    stale data from the 15-minute TTL cache.

    Called from the backend tool-execution boundary. The MCP tool itself
    remains generic and stateless; cache management is a backend concern.

    The function is intentionally defensive — any Redis failure is caught
    and logged so cache-invalidation issues never block conversation flow.

    Args:
        tool_name: The name of the MCP tool that was executed.
        tool_result: The result dict returned by the MCP tool.
        user_id: The user ID whose cache should be invalidated.
        redis_client: Async Redis client (may be ``None``).
        logger: Logger instance for structured logging.
    """
    if tool_name != "update_user_profile":
        return

    if not isinstance(tool_result, dict) or tool_result.get("status") != "success":
        return

    if not redis_client or not user_id:
        logger.debug(
            "Skipping profile cache invalidation (missing redis_client or user_id)",
            extra={
                "tool_name": tool_name,
                "user_id": user_id,
                "has_redis_client": bool(redis_client),
            },
        )
        return

    cache_key = f"profile:{user_id}"
    try:
        await redis_client.delete(cache_key)
        logger.info(
            "Profile cache invalidated after successful update_user_profile",
            extra={
                "tool_name": tool_name,
                "user_id": user_id,
                "cache_key": cache_key,
                "event": "profile_cache_invalidated",
            },
        )
    except Exception as e:  # noqa: BLE001 - defensive: never block conversation
        logger.warning(
            "Failed to invalidate profile cache (non-fatal)",
            extra={
                "tool_name": tool_name,
                "user_id": user_id,
                "cache_key": cache_key,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
