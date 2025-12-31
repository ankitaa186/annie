"""
User Profile Tools

Provides tools for retrieving and updating user profiles
via the agentic-memories service.
"""

import asyncio
import time
from typing import Any, Dict

import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Get User Profile Tool
# =============================================================================

async def get_user_profile_tool_handler(
    user_id: str
) -> Dict[str, Any]:
    """
    Retrieve user profile from agentic-memories service.

    The profile includes 21 fields across 5 categories (basics, preferences, goals,
    interests, background) that are automatically extracted from conversations.

    Args:
        user_id: User identifier

    Returns:
        dict: Profile object with all fields and completeness percentage
    """
    start_time = time.time()

    config = get_config()
    memories_url = config["AGENTIC_MEMORIES_URL"]

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        logger.error(
            "Invalid user_id for profile retrieval",
            extra={"user_id": user_id, "error": "user_id must be non-empty string"}
        )
        return {
            "status": "error",
            "error": "Invalid user_id: must be non-empty string",
            "user_id": user_id
        }

    try:
        url = f"{memories_url}/v1/profile"
        params = {"user_id": user_id}

        logger.info(
            "Retrieving user profile from agentic-memories",
            extra={
                "user_id": user_id,
                "url": url,
                "params": params
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, params=params)

            if response.status_code != 200:
                error_msg = f"Profile retrieval failed with status {response.status_code}"
                logger.error(
                    error_msg,
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "response_text": response.text[:200]
                    }
                )
                return {
                    "status": "error",
                    "error": error_msg,
                    "user_id": user_id,
                    "status_code": response.status_code
                }

            profile_data = response.json()
            duration_ms = int((time.time() - start_time) * 1000)

            completeness = int(profile_data.get("completeness_pct", 0))
            profile = profile_data.get("profile", {})

            logger.info(
                "Profile retrieved successfully",
                extra={
                    "user_id": user_id,
                    "completeness": completeness,
                    "duration_ms": duration_ms,
                    "populated_fields": profile_data.get("populated_fields", 0),
                    "total_fields": profile_data.get("total_fields", 21)
                }
            )

            return {
                "status": "success",
                "user_id": user_id,
                "completeness": completeness,
                "basics": profile.get("basics", {}),
                "preferences": profile.get("preferences", {}),
                "goals": profile.get("goals", {}),
                "interests": profile.get("interests", {}),
                "background": profile.get("background", {})
            }

    except httpx.TimeoutException as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Profile retrieval timed out after {duration_ms}ms"
        logger.error(
            error_msg,
            extra={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error": str(e)
            }
        )
        return {
            "status": "error",
            "error": error_msg,
            "user_id": user_id
        }

    except httpx.RequestError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Network error during profile retrieval: {str(e)}"
        logger.error(
            error_msg,
            extra={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error": str(e),
                "error_type": type(e).__name__
            }
        )
        return {
            "status": "error",
            "error": error_msg,
            "user_id": user_id
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Unexpected error during profile retrieval: {str(e)}"
        logger.error(
            error_msg,
            extra={
                "user_id": user_id,
                "duration_ms": duration_ms,
                "error": str(e),
                "error_type": type(e).__name__
            },
            exc_info=True
        )
        return {
            "status": "error",
            "error": error_msg,
            "user_id": user_id
        }


get_user_profile_tool = {
    "name": "get_user_profile",
    "description": (
        "Retrieve user profile with structured data automatically extracted from conversations. "
        "Returns 21 fields across 5 categories: "
        "(1) Basics - name, age, location, occupation, timezone; "
        "(2) Preferences - communication style, topics of interest, language; "
        "(3) Goals - short-term goals, long-term goals, values; "
        "(4) Interests - hobbies, expertise areas; "
        "(5) Background - education, work history, life events. "
        "Includes a completeness percentage (0-100) indicating how much is known. "
        "Use this to personalize responses, understand user context, tailor recommendations, "
        "or reference what you know about them. Fields may be null if not yet learned. Profile extraction happens automatically during conversation storage, you can nudge the user to give you more information if the profile is incomplete."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            }
        },
        "required": ["user_id"]
    },
    "handler": get_user_profile_tool_handler
}


# =============================================================================
# Update User Profile Tool
# =============================================================================

# Allowed categories for profile updates
ALLOWED_PROFILE_CATEGORIES = {"basics", "preferences", "goals", "interests", "background"}


async def update_user_profile_tool_handler(
    user_id: str,
    category: str,
    field_name: str,
    value: Any,
    reason: str = None
) -> Dict[str, Any]:
    """
    Update a specific field in the user's profile in agentic-memories.

    This tool makes a PUT request to the agentic-memories profile API to update
    a specific field. Use when the user explicitly shares new information about
    themselves that should be persisted.

    Args:
        user_id: User identifier
        category: Profile category (basics, preferences, goals, interests, background)
        field_name: Field name within the category
        value: New value (string, number, boolean, or array)
        reason: Optional reason for the update (for audit trail)

    Returns:
        dict: Result with status, updated value, previous value, and metadata
    """
    start_time = time.time()

    # Validate category against allowed list
    if category not in ALLOWED_PROFILE_CATEGORIES:
        logger.warning(
            "Invalid category for profile update",
            extra={
                "user_id": user_id,
                "category": category,
                "field_name": field_name,
                "error": "VALIDATION_ERROR"
            }
        )
        return {
            "status": "error",
            "error_message": f"Invalid category '{category}'. Allowed: {', '.join(sorted(ALLOWED_PROFILE_CATEGORIES))}",
            "error_code": "VALIDATION_ERROR"
        }

    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    payload = {
        "user_id": user_id,
        "value": value,
        "source": "llm_explicit"
    }

    if reason:
        payload["reason"] = reason

    max_retries = 3
    retry_delays = [1, 2, 4]

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(max_retries):
            try:
                logger.info(
                    "Updating user profile field",
                    extra={
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "attempt": attempt + 1,
                        "has_reason": reason is not None
                    }
                )

                response = await client.put(
                    f"{memories_url}/v1/profile/{category}/{field_name}",
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )

                duration_ms = int((time.time() - start_time) * 1000)

                if response.status_code in (200, 201):
                    result = response.json()

                    logger.info(
                        "Profile field updated successfully",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "duration_ms": duration_ms,
                            "attempts": attempt + 1
                        }
                    )

                    return {
                        "status": "success",
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "value": result.get("value"),
                        "previous_value": result.get("previous_value"),
                        "confidence": 100.0,
                        "last_updated": result.get("last_updated")
                    }

                elif response.status_code == 404:
                    logger.warning(
                        "Profile field not found",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "error_message": f"Profile field not found: {category}/{field_name}",
                        "error_code": "NOT_FOUND"
                    }

                elif response.status_code == 400:
                    error_msg = "Invalid request"
                    try:
                        error_data = response.json()
                        error_msg = error_data.get("message", error_msg)
                    except Exception:
                        error_msg = response.text or error_msg

                    logger.warning(
                        "Profile update validation error",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "error": error_msg,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "error_message": error_msg,
                        "error_code": "VALIDATION_ERROR"
                    }

                elif response.status_code >= 500:
                    logger.warning(
                        "Profile update server error, will retry",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "duration_ms": duration_ms
                        }
                    )

                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delays[attempt])
                        continue

                    return {
                        "status": "error",
                        "error_message": f"Server error after {max_retries} attempts",
                        "error_code": "SERVER_ERROR"
                    }

                else:
                    logger.error(
                        "Profile update failed with unexpected status",
                        extra={
                            "user_id": user_id,
                            "category": category,
                            "field_name": field_name,
                            "status_code": response.status_code,
                            "duration_ms": duration_ms
                        }
                    )
                    return {
                        "status": "error",
                        "error_message": f"HTTP {response.status_code}",
                        "error_code": response.status_code
                    }

            except httpx.TimeoutException:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.warning(
                    "Profile update timeout, will retry",
                    extra={
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "attempt": attempt + 1,
                        "duration_ms": duration_ms
                    }
                )

                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delays[attempt])
                    continue

                return {
                    "status": "error",
                    "error_message": f"Timeout after {max_retries} attempts",
                    "error_code": "TIMEOUT_ERROR"
                }

            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Unexpected error updating profile",
                    extra={
                        "user_id": user_id,
                        "category": category,
                        "field_name": field_name,
                        "error": str(e),
                        "duration_ms": duration_ms
                    },
                    exc_info=True
                )
                return {
                    "status": "error",
                    "error_message": str(e),
                    "error_code": "INTERNAL_ERROR"
                }

    return {
        "status": "error",
        "error_message": "Unknown error occurred",
        "error_code": "UNKNOWN"
    }


update_user_profile_tool = {
    "name": "update_user_profile",
    "description": """Update a specific field in the user's profile.

Use this tool when the user:
1. Explicitly tells you new information about themselves ("I just moved to Seattle")
2. Corrects previously known information ("Actually, I prefer formal communication")
3. Expresses a preference or goal change ("I'm now focusing on retirement planning")

Categories and common fields:
- basics: name, age, location, occupation, timezone
- preferences: communication_style, topics_of_interest, response_length
- goals: short_term, long_term, current_focus
- interests: hobbies, favorite_topics, dislikes
- background: education, work_history, family

Do NOT use for:
- Information already in their profile (check first with get_user_profile)
- Temporary moods or states ("I'm feeling tired today")
- Speculative information ("You seem like someone who...")""",
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "category": {
                "type": "string",
                "enum": ["basics", "preferences", "goals", "interests", "background"],
                "description": "Profile category to update"
            },
            "field_name": {
                "type": "string",
                "description": "Field name within the category (e.g., 'location', 'communication_style')"
            },
            "value": {
                "description": "New value (string, number, boolean, or array)"
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for the update (for audit trail)"
            }
        },
        "required": ["user_id", "category", "field_name", "value"]
    },
    "handler": update_user_profile_tool_handler
}
