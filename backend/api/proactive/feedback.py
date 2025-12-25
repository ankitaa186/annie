"""
Feedback Handler Module

Implements closed-loop learning by detecting and processing user feedback
on proactive messages. Enables Annie to adapt trigger behavior based on
user reactions within a 2-hour feedback window.

Story: 13.10 - Feedback Handler (Closed Loop Learning)
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import redis.asyncio as redis

from api.logging import get_logger
from api.proactive.intents_client import IntentsClient

logger = get_logger(__name__)


async def get_proactive_context(
    user_id: str,
    redis_client: redis.Redis
) -> Optional[Dict[str, Any]]:
    """
    Check if user is responding to a recent proactive message.

    This function checks Redis for a recently sent proactive message
    (within 2-hour feedback window) and returns the full context needed
    for the LLM to understand and process feedback.

    Redis Key: proactive_message:{user_id}:last

    Args:
        user_id: User identifier
        redis_client: Redis client instance

    Returns:
        Proactive context dict with trigger details, or None if no recent message

        Context structure:
        {
            "trigger_id": str,
            "message_id": str,
            "sent_at": str (ISO timestamp),
            "trigger_details": dict (full trigger from agentic-memories)
        }

    Raises:
        Does not raise - returns None on any error (graceful degradation)
    """
    try:
        # Check Redis for recent proactive message
        key = f"proactive_message:{user_id}:last"
        data_str = await redis_client.get(key)

        if not data_str:
            # No recent proactive message
            return None

        # Parse stored data
        try:
            data = json.loads(data_str)
        except json.JSONDecodeError as e:
            logger.warning(
                "Failed to parse proactive message data from Redis",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "data": data_str[:100]  # Log first 100 chars for debugging
                }
            )
            return None

        # Validate required fields
        trigger_id = data.get("trigger_id")
        message_id = data.get("message_id")
        sent_at = data.get("sent_at")

        if not trigger_id or not message_id or not sent_at:
            logger.warning(
                "Proactive message data missing required fields",
                extra={
                    "user_id": user_id,
                    "has_trigger_id": bool(trigger_id),
                    "has_message_id": bool(message_id),
                    "has_sent_at": bool(sent_at)
                }
            )
            return None

        # Verify message is within 2-hour feedback window
        try:
            # Handle different timestamp formats
            if isinstance(sent_at, (int, float)):
                # Unix timestamp - convert to datetime
                sent_dt = datetime.fromtimestamp(sent_at, tz=timezone.utc)
            elif isinstance(sent_at, str):
                # ISO string - parse it
                sent_dt = datetime.fromisoformat(sent_at.replace('Z', '+00:00'))
            else:
                logger.warning(
                    "Unexpected sent_at type",
                    extra={"user_id": user_id, "sent_at_type": type(sent_at).__name__}
                )
                return None

            now = datetime.now(timezone.utc)
            time_diff = (now - sent_dt).total_seconds()

            # 2 hours = 7200 seconds
            if time_diff > 7200:
                logger.debug(
                    "Proactive message outside feedback window",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "sent_at": sent_at,
                        "time_diff_seconds": time_diff
                    }
                )
                return None

        except (ValueError, TypeError, AttributeError) as e:
            logger.warning(
                "Failed to parse sent_at timestamp",
                extra={
                    "user_id": user_id,
                    "sent_at": sent_at,
                    "sent_at_type": type(sent_at).__name__,
                    "error": str(e)
                }
            )
            return None

        # Fetch full trigger details from agentic-memories
        try:
            client = IntentsClient()
            trigger = await client.get_trigger(trigger_id)

            if not trigger:
                logger.warning(
                    "Trigger not found in agentic-memories",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id
                    }
                )
                return None

        except Exception as e:
            logger.error(
                "Failed to fetch trigger details from agentic-memories",
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )
            # Return partial context without trigger details
            # LLM can still acknowledge feedback even without full details
            trigger = {"id": trigger_id, "intent_name": "Unknown"}

        # Build proactive context
        context = {
            "trigger_id": trigger_id,
            "message_id": message_id,
            "sent_at": sent_at,
            "trigger_details": trigger,
            "time_since_message_seconds": time_diff
        }

        logger.info(
            "Proactive feedback context detected",
            extra={
                "user_id": user_id,
                "trigger_id": trigger_id,
                "intent_name": trigger.get("intent_name", "Unknown"),
                "time_since_message_seconds": time_diff
            }
        )

        return context

    except Exception as e:
        # Graceful degradation - log error but don't fail chat flow
        logger.error(
            "Unexpected error in get_proactive_context, continuing without feedback detection",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return None
