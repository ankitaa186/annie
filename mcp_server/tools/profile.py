"""
User Profile Tools

Provides tools for retrieving and updating user profiles
via the agentic-memories service.
"""

import asyncio
import json
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

            # Pass through every category agentic-memories returns. Categories
            # that aren't dicts are dropped (defensive — should never happen).
            categories = {
                cat: fields
                for cat, fields in profile.items()
                if isinstance(fields, dict)
            }
            return {
                "status": "success",
                "user_id": user_id,
                "completeness": completeness,
                **categories,
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
        "Retrieve user profile automatically extracted from past conversations. "
        "Returns 8 categories: "
        "(1) Basics - name, age, birthday, location, occupation, family_status, children, spouse; "
        "(2) Preferences - communication_style, risk_tolerance, dietary_restrictions, gift_preferences; "
        "(3) Goals - short_term, long_term, financial_goals, career_goals, bucket_list; "
        "(4) Interests - hobbies, sports, favorite_topics, travel_destinations; "
        "(5) Background - skills, work_history, education_history, vehicle; "
        "(6) Health - allergies, dietary_needs, health_conditions, clothing_sizes; "
        "(7) Personality - personality_type, strengths, fears, stress_response; "
        "(8) Values - life_values, philanthropy, spiritual_alignment, dealbreakers. "
        "Includes completeness percentage (0-100). Fields may be null if not yet learned."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Must be the exact user ID from the system message (a numeric Telegram user ID). NEVER use placeholders like 'default', 'user', 'anonymous', or 'me'."
            }
        },
        "required": ["user_id"]
    },
    "handler": get_user_profile_tool_handler
}


# =============================================================================
# Update User Profile Tool
# =============================================================================

# Allowed categories for profile updates (must match agentic-memories extraction)
ALLOWED_PROFILE_CATEGORIES = {
    "basics", "preferences", "goals", "interests",
    "background", "health", "personality", "values"
}

# Canonical field names per category. Union of the curated seed vocabulary and
# every field the agentic-memories extractor has actually written across users.
# Phase 1 floor — Phase 2 adds per-user dynamic discovery on top of this.
# Last synced from `profile_fields` table on 2026-04-14.
CANONICAL_FIELDS = {
    "basics": {
        # curated seed
        "name", "nicknames", "age", "birthday", "location", "pronouns",
        "occupation", "education", "family_status", "children", "spouse",
        "pets", "siblings", "languages", "important_dates",
        # extractor-observed additions
        "spouse_name",
    },
    "preferences": {
        # curated seed
        "communication_style", "love_language", "risk_tolerance", "investing_style",
        "dietary_restrictions", "food_preferences", "beverage_preferences",
        "music_preferences", "movie_preferences", "book_preferences",
        "color_preferences", "gift_ideas", "gift_preferences", "pet_peeves",
        "travel_preferences", "sleep_schedule", "work_schedule", "brokerage_platforms",
        # extractor-observed additions
        "advice_sources", "advice_style", "favorites", "hiking_time_preference",
        "investing_approach_preference", "investing_beliefs", "investing_criteria",
        "investing_philosophy", "investing_principles", "investing_strategy",
        "investing_strategy_preference", "investment_beliefs", "investment_criteria",
        "investment_focus", "investment_outlook_bullish", "investment_philosophy",
        "investment_preference", "investment_risk_belief", "investment_risk_preference",
        "investment_role_model", "investment_strategy", "investment_strategy_preference",
        "investment_thesis", "investment_time_horizon", "learning_schedule", "likes",
        "market_views", "news_sources", "preferred_investing_strategy",
        "stock_preferences", "travel_preference", "ui_theme", "work_style",
    },
    "goals": {
        # curated seed
        "short_term", "long_term", "financial_goals", "career_goals",
        "aspirations", "bucket_list",
        # extractor-observed additions
        "current_focus", "portfolio_sector_targets",
    },
    "interests": {
        # curated seed
        "hobbies", "sports", "music", "books", "movies_tv", "learning_areas",
        "favorite_topics", "activities", "travel_destinations", "collections",
        # extractor-observed additions
        "dining_preferences", "favorite_whiskey", "music_taste", "passions",
        "topics", "whiskey_preferences",
    },
    "background": {
        # curated seed
        "skills", "achievements", "education_history", "work_history",
        "current_employer", "specialization", "family_background",
        "cultural_background", "vehicle", "investing_experience", "how_we_met",
        # extractor-observed additions
        "current_projects", "experiences", "family", "father_occupation",
        "history", "hometown", "industry", "origin",
        "stock_holdings", "stocks_held", "stocks_owned", "work_routine",
    },
    "health": {
        "allergies", "dietary_needs", "health_conditions", "medications",
        "clothing_sizes", "sensory_preferences", "vision_correction",
    },
    "personality": {
        "personality_type", "strengths", "fears", "stress_response",
        "conflict_style", "social_battery", "nostalgia_triggers", "communication_quirks",
    },
    "values": {
        "life_values", "philanthropy", "spiritual_alignment", "dealbreakers",
    },
}

# Field name aliases - map common variants to canonical names
# (matches agentic-memories ProfileExtractor.FIELD_NAME_ALIASES)
FIELD_NAME_ALIASES = {
    # Date variants
    "birthdate": "birthday",
    "birth_date": "birthday",
    "dob": "birthday",
    # Singular → plural
    "brokerage_platform": "brokerage_platforms",
    "hobby": "hobbies",
    "skill": "skills",
    "language": "languages",
    "nickname": "nicknames",
    # Goal duplicates
    "retirement_goal": "long_term",
    "retirement_goals": "long_term",
    "targets": "long_term",
    "plans": "short_term",
    # Occupation variants
    "job": "occupation",
    "work": "occupation",
    # Location variants
    "city": "location",
    "country": "location",
    # Family consolidation
    "spouse_occupation": "spouse",
    "spouse_employer": "spouse",
    "wife": "spouse",
    "husband": "spouse",
    "daughter_age": "children",
    "son_age": "children",
    # Skills consolidation
    "programming_languages": "skills",
    "technical_skills": "skills",
}


async def _fetch_user_profile_fields(
    user_id: str, memories_url: str
) -> Dict[str, set]:
    """Return {category: {field_name, ...}} for fields the extractor has already
    written for this user. On any error returns {} so the caller falls back to
    the static CANONICAL_FIELDS whitelist alone."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{memories_url}/v1/profile",
                params={"user_id": user_id},
            )
            if response.status_code != 200:
                logger.warning(
                    "Could not fetch user field universe for write validation",
                    extra={"user_id": user_id, "status_code": response.status_code},
                )
                return {}
            profile = response.json().get("profile", {})
            return {
                cat: set(fields.keys())
                for cat, fields in profile.items()
                if isinstance(fields, dict)
            }
    except Exception as e:
        logger.warning(
            "Error fetching user field universe (degrading to static whitelist)",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
            },
        )
        return {}


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
        category: Profile category (basics, preferences, goals, interests, background,
                  health, personality, values)
        field_name: Field name within the category (must be a canonical field name)
        value: New value (string, number, boolean, or array)
        reason: Optional reason for the update (for audit trail)

    Returns:
        dict: Result with status, updated value, previous value, and metadata
    """
    start_time = time.time()

    # Parse JSON strings into Python objects if needed
    # (Gemini sends value as string per schema, may contain JSON arrays/objects)
    parsed_value = value
    if isinstance(value, str):
        stripped = value.strip()
        # Try to parse JSON if it looks like an array or object
        if (stripped.startswith('[') and stripped.endswith(']')) or \
           (stripped.startswith('{') and stripped.endswith('}')):
            try:
                parsed_value = json.loads(stripped)
                logger.debug(
                    "Parsed JSON value for profile update",
                    extra={"original": value[:100], "parsed_type": type(parsed_value).__name__}
                )
            except json.JSONDecodeError:
                # Keep as string if parsing fails
                pass
    value = parsed_value

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

    # Apply field name alias normalization (matches agentic-memories extraction)
    original_field_name = field_name
    if field_name in FIELD_NAME_ALIASES:
        field_name = FIELD_NAME_ALIASES[field_name]
        logger.info(
            "Normalized field name alias",
            extra={
                "user_id": user_id,
                "original": original_field_name,
                "canonical": field_name
            }
        )

    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate field name against the union of:
    #   1. CANONICAL_FIELDS — static seed vocabulary, used as a floor for new users
    #   2. The user's existing profile fields — whatever the extractor has
    #      written. Lets the LLM update fields the extractor invented even if
    #      they aren't in the static whitelist.
    # Net-new field invention is rejected and redirected to store_memory.
    canonical_fields = CANONICAL_FIELDS.get(category, set())
    user_fields_by_category = await _fetch_user_profile_fields(user_id, memories_url)
    allowed_fields = canonical_fields | user_fields_by_category.get(category, set())

    if field_name not in allowed_fields:
        logger.warning(
            "Unknown field name for profile update",
            extra={
                "user_id": user_id,
                "category": category,
                "field_name": field_name,
                "canonical_count": len(canonical_fields),
                "user_field_count": len(user_fields_by_category.get(category, set())),
                "error": "UNKNOWN_FIELD",
            }
        )
        return {
            "status": "error",
            "error_message": (
                f"Field '{field_name}' does not exist in category '{category}' for this user. "
                f"Profile is for stable identity facts only. For novel facts about the user, "
                f"use the store_memory tool instead."
            ),
            "error_code": "UNKNOWN_FIELD",
            "suggestion": "store_memory",
        }

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
    "description": (
        "Update an EXISTING field in the user's profile when they explicitly share persistent identity info. "
        "USE FOR: (1) identity changes ('I moved to Seattle'); (2) corrections ('my name is spelled...'); "
        "(3) preference/goal updates ('I'm focusing on retirement'). "
        "DO NOT USE FOR: task instructions, temporary states, transient data (watchlists, cash), or speculation. "
        "FIELD VOCABULARY: You can update any field that already exists for this user (call get_user_profile first to see them) "
        "or any field in the curated canonical set (basics: name/age/birthday/location/occupation/family_status/children/spouse/pets/pronouns; "
        "preferences: communication_style/risk_tolerance/dietary_restrictions/gift_preferences/investing_style; "
        "goals: short_term/long_term/financial_goals/career_goals/bucket_list/aspirations; "
        "interests: hobbies/sports/favorite_topics/travel_destinations/collections; "
        "background: skills/work_history/education_history/vehicle/investing_experience; "
        "health: allergies/dietary_needs/health_conditions/medications; "
        "personality: personality_type/strengths/fears/stress_response; "
        "values: life_values/philanthropy/dealbreakers). "
        "DO NOT INVENT NEW FIELD NAMES. If the user shares a novel fact that doesn't fit any existing or canonical field, "
        "use the store_memory tool instead — that's what it's for. "
        "Use arrays for lists, objects for structured data. Common aliases auto-normalize (birthdate→birthday)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "Must be the exact user ID from the system message (a numeric Telegram user ID). NEVER use placeholders like 'default', 'user', 'anonymous', or 'me'."
            },
            "category": {
                "type": "string",
                "enum": ["basics", "preferences", "goals", "interests", "background",
                         "health", "personality", "values"],
                "description": "Profile category to update"
            },
            "field_name": {
                "type": "string",
                "description": (
                    "Canonical field name within the category. Must be one of the "
                    "exact field names listed above. Common aliases (birthdate→birthday, "
                    "job→occupation) are auto-normalized."
                )
            },
            "value": {
                "type": "string",
                "description": (
                    "New value as a JSON string. For simple values use the value directly "
                    "(e.g., 'vegetarian'). For arrays use JSON array format "
                    "(e.g., '[\"hiking\", \"reading\"]'). For objects use JSON object format "
                    "(e.g., '{\"name\": \"Jane\", \"occupation\": \"engineer\"}')"
                )
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
