"""
Shared utility functions for the Annie backend API.
"""

from typing import Any, Dict, Optional
import logging


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
