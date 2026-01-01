"""
Proactive AI: Trigger Management Tools (Epic 13)

Provides tools for creating, listing, updating, and deleting proactive triggers
(intents) that allow Annie to initiate contact with users based on schedules
or conditions.
"""

import json
import time
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx

from mcp_server.config import get_config
from mcp_server.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Create Trigger Tool
# =============================================================================


async def create_trigger_tool_handler(
    user_id: str,
    intent_name: str,
    trigger_type: str,
    action_context: dict = None,
    schedule: dict = None,
    condition: dict = None,
    enabled: bool = True,
    expires_at: str = None
) -> Dict[str, Any]:
    """
    Create a new proactive trigger (called "intent" in backend).

    This tool allows the LLM to set up triggers that will cause Annie to
    initiate contact with the user based on schedules or conditions.

    Args:
        user_id: User identifier
        intent_name: Short descriptive name (e.g., 'Morning portfolio brief')
        trigger_type: 'scheduled' or 'condition'
        action_context: Comprehensive briefing for wake-up LLM (see architecture doc)
        schedule: Schedule configuration for 'scheduled' type
        condition: Condition configuration for 'condition' type
        enabled: Whether trigger is active (default: True)
        expires_at: Optional ISO datetime when trigger auto-deletes

    Returns:
        dict: Created trigger with ID and next_check time
    """
    start_time = time.time()

    # Validate action_context (required parameter)
    if not action_context:
        return {
            "status": "error",
            "message": "Missing required parameter 'action_context'. You must provide a comprehensive briefing object for the wake-up LLM that includes: research_topic/briefing_request, user_preferences, delivery_instructions, and any relevant context."
        }

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Validate trigger_type
    if trigger_type not in ["scheduled", "condition"]:
        return {
            "status": "error",
            "message": f"Invalid trigger_type: '{trigger_type}'. Must be 'scheduled' or 'condition'."
        }

    # Validate type-specific configuration
    if trigger_type == "scheduled" and not schedule:
        return {
            "status": "error",
            "message": "Schedule configuration required for 'scheduled' trigger type"
        }

    if trigger_type == "condition" and not condition:
        return {
            "status": "error",
            "message": "Condition configuration required for 'condition' trigger type"
        }

    # Build request payload
    # action_context must be a JSON string, not a dict
    action_context_str = action_context
    if isinstance(action_context, dict):
        action_context_str = json.dumps(action_context)
    elif not isinstance(action_context, str):
        # If it's not a dict or string, convert to string
        action_context_str = json.dumps(action_context)

    # Map trigger_type from MCP tool format to agentic-memories API format
    # MCP tool uses: "scheduled" or "condition"
    # API expects: "cron" | "interval" | "once" | "price" | "silence" | "portfolio"
    api_trigger_type = trigger_type
    api_schedule = None
    api_condition = None

    if trigger_type == "scheduled" and schedule:
        # Map scheduled trigger to API format
        # Default timezone to America/Los_Angeles (PST) if not provided
        default_timezone = "America/Los_Angeles"
        schedule_mode = schedule.get("mode", "cron")
        if schedule_mode == "once":
            api_trigger_type = "once"
            # Get the datetime and timezone
            dt_str = schedule.get("datetime")
            tz_str = schedule.get("timezone", default_timezone)

            # If datetime doesn't have timezone offset, add it
            # This ensures the API interprets the time correctly
            if dt_str and "+" not in dt_str and "-" not in dt_str[-6:]:
                try:
                    # Parse the naive datetime and localize it
                    naive_dt = datetime.fromisoformat(dt_str.replace("Z", ""))
                    tz = ZoneInfo(tz_str)
                    localized_dt = naive_dt.replace(tzinfo=tz)
                    dt_str = localized_dt.isoformat()
                    logger.debug(
                        f"Added timezone offset to datetime: {schedule.get('datetime')} -> {dt_str}",
                        extra={"original": schedule.get("datetime"), "localized": dt_str, "timezone": tz_str}
                    )
                except Exception as e:
                    logger.warning(f"Failed to localize datetime: {e}")

            api_schedule = {
                "trigger_at": dt_str,
                "timezone": tz_str
            }
        elif schedule_mode == "cron":
            api_trigger_type = "cron"
            api_schedule = {
                "cron": schedule.get("cron_expression") or schedule.get("cron"),
                "timezone": schedule.get("timezone", default_timezone)
            }
        else:
            # Default to cron if mode not specified
            api_trigger_type = "cron"
            api_schedule = schedule
    elif trigger_type == "condition" and condition:
        # Map condition trigger to API format
        condition_type = condition.get("condition_type", "price")
        api_trigger_type = condition_type  # "price", "silence", or "portfolio"

        # Set default check_interval_minutes based on condition type
        # Price: every 2 hours (120 min) - balances responsiveness with API limits
        # Portfolio: every 24 hours (1440 min) - daily check is sufficient
        # Silence: every 60 min - checking user inactivity hourly is sufficient
        default_check_intervals = {
            "price": 120,
            "portfolio": 1440,
            "silence": 60
        }
        check_interval = condition.get(
            "check_interval_minutes",
            default_check_intervals.get(condition_type, 120)
        )

        api_condition = {
            "expression": condition.get("expression"),
            "check_interval_minutes": check_interval,
            "cooldown_hours": condition.get("cooldown_hours", 1),
            "fire_mode": condition.get("fire_mode", "recurring")
        }

    payload = {
        "user_id": user_id,
        "intent_name": intent_name,
        "trigger_type": api_trigger_type,
        "action_context": action_context_str,
        "enabled": enabled
    }

    if api_schedule:
        payload["trigger_schedule"] = api_schedule
    if api_condition:
        payload["trigger_condition"] = api_condition
    if expires_at:
        payload["expires_at"] = expires_at

    try:
        # Log the full request payload
        payload_json_str = json.dumps(payload, indent=2, default=str)
        logger.info(
            f"Creating proactive trigger via MCP tool - URL: {memories_url}/v1/intents\n"
            f"Payload:\n{payload_json_str}",
            extra={
                "user_id": user_id,
                "intent_name": intent_name,
                "trigger_type": trigger_type,
                "api_trigger_type": api_trigger_type,
                "payload": payload
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{memories_url}/v1/intents",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code in (200, 201):
                result = response.json()

                logger.info(
                    "Trigger created successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "intent_name": intent_name,
                        "trigger_id": result.get("id"),
                        "next_check": result.get("next_check"),
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "trigger": {
                        "id": result.get("id"),
                        "intent_name": result.get("intent_name"),
                        "description": result.get("description"),
                        "trigger_type": result.get("trigger_type"),
                        "trigger_schedule": result.get("trigger_schedule"),
                        "trigger_condition": result.get("trigger_condition"),
                        "enabled": result.get("enabled"),
                        "next_check": result.get("next_check"),
                        "execution_count": result.get("execution_count", 0),
                        "created_at": result.get("created_at"),
                        "updated_at": result.get("updated_at")
                    },
                    "message": f"Created trigger '{intent_name}'. Next fire: {result.get('next_check', 'TBD')}"
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                error_data = None
                try:
                    error_data = response.json()
                    # Handle different error response formats
                    if "errors" in error_data and isinstance(error_data["errors"], list):
                        # agentic-memories returns {"errors": ["error1", "error2"]}
                        error_msg = "; ".join(error_data["errors"])
                    elif "detail" in error_data:
                        error_msg = error_data["detail"]
                        if isinstance(error_msg, dict) and "errors" in error_msg:
                            # Handle nested errors format
                            error_msg = "; ".join(error_msg["errors"]) if isinstance(error_msg["errors"], list) else str(error_msg["errors"])
                    elif "message" in error_data:
                        error_msg = error_data["message"]
                    else:
                        error_msg = str(error_data) if error_data else error_msg
                except Exception:
                    error_msg = response.text or error_msg

                # Log full error details
                error_data_str = json.dumps(error_data, indent=2, default=str) if error_data else str(error_data)
                payload_json_str = json.dumps(payload, indent=2, default=str)

                logger.error(
                    f"Create trigger failed via MCP tool - Status: {response.status_code}\n"
                    f"Error: {error_msg}\n"
                    f"Error Data: {error_data_str}\n"
                    f"Response Text: {response.text}\n"
                    f"Request Payload:\n{payload_json_str}",
                    extra={
                        "user_id": user_id,
                        "intent_name": intent_name,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "error_data": error_data,
                        "response_text": response.text,
                        "request_payload": payload,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to create trigger: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Create trigger timed out", extra={"user_id": user_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error creating trigger", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error creating trigger", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Create trigger tool definition
create_trigger_tool = {
    "name": "create_trigger",
    "description": """
Create a proactive trigger that will cause Annie to initiate contact with the user.

USE THIS WHEN USER WANTS:
- Reminders: "Remind me to...", "Every morning tell me...", "On Friday..."
- Alerts: "Let me know when NVDA drops below $130", "Alert me if any stock moves 5%"
- Check-ins: "If I don't message you for 2 days, check in", "Ping me if I'm silent"
- Scheduled updates: "Every weekday, give me a portfolio summary"

CRON EXPRESSIONS (for scheduled triggers):
- "every morning at 9am" -> "0 9 * * *"
- "every weekday at 8:30" -> "30 8 * * 1-5"
- "every Friday at 5pm" -> "0 17 * * 5"
- "twice a day (9am and 5pm)" -> "0 9,17 * * *"

Cron format: [minute] [hour] [day-of-month] [month] [day-of-week]
Examples: "0 9 * * *" = 9am daily, "30 8 * * 1-5" = 8:30am weekdays

ACTION_CONTEXT GUIDANCE:
Write a COMPREHENSIVE briefing for the wake-up AI. This is its ONLY context - be thorough!

REQUIRED SECTIONS:
1. original_request: User's exact words
2. intent_summary: What this trigger should accomplish and WHY it matters
3. user_context: Name, timezone, communication style (NOT dynamic data like holdings/prices)
4. execution_instructions: Step-by-step guide including:
   - Which tools to call to gather fresh data
   - How to analyze and interpret the data
   - Decision criteria for when to skip vs send
5. message_guidance: How to compose the message:
   - If user wants brief: respect that preference
   - Otherwise: default to rich, informative messages with insights and context
   - Include voice examples showing personality
   - Explain WHY data matters, not just WHAT the numbers are
6. available_tools: Which tools are relevant and how to use them
7. edge_cases: How to handle errors, missing data, unusual situations

CRITICAL RULES:
- PRE-FLIGHT CHECK: Before calling this tool, you MUST call list_triggers first to check
  if a similar trigger already exists. If a similar intent exists (e.g., user wants to change
  the time of an existing alert), use update_trigger instead. Only use create_trigger for
  brand new intents. DO NOT create duplicate triggers!
- If in doubt whether to create a new trigger or update an existing one, ASK THE USER to confirm
  before proceeding. Example: "I see you already have a '9am portfolio update' - should I update
  that one to 1pm, or create a separate trigger?"
- NEVER put dynamic data (holdings, prices) in action_context - fetch fresh via tools
- Wake-up AI should use tools liberally to gather current information
- action_context preferences take precedence - if user wants brief, respect it
- Be thorough - this briefing is EVERYTHING the wake-up AI knows
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "intent_name": {
                "type": "string",
                "description": "Short descriptive name (e.g., 'Morning portfolio brief')"
            },
            "trigger_type": {
                "type": "string",
                "enum": ["scheduled", "condition"],
                "description": "Wake-up mechanism: 'scheduled' for time-based, 'condition' for event-based"
            },
            "action_context": {
                "type": "object",
                "description": "Comprehensive briefing for wake-up LLM with all execution guidance"
            },
            "schedule": {
                "type": "object",
                "description": "Schedule configuration for 'scheduled' type triggers",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["cron", "once"],
                        "description": "'cron' for recurring, 'once' for one-time"
                    },
                    "cron_expression": {
                        "type": "string",
                        "description": "Cron expression for recurring (e.g., '0 9 * * 1-5')"
                    },
                    "datetime": {
                        "type": "string",
                        "description": "ISO datetime for one-time triggers. IMPORTANT: Use the CURRENT DATE from system prompt (Pacific time). Format: 'YYYY-MM-DDTHH:MM:SS'. Example: if system shows '2025-12-31T19:30' Pacific and you want '2 min from now', use '2025-12-31T19:32:00' (NOT Jan 1st)"
                    },
                    "timezone": {
                        "type": "string",
                        "description": "IANA timezone. Default: 'America/Los_Angeles' (PST/PDT) - omit unless user specifies different timezone"
                    }
                }
            },
            "condition": {
                "type": "object",
                "description": "Condition configuration for 'condition' type triggers",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["price", "portfolio", "silence"],
                        "description": "Condition type"
                    },
                    "expression": {
                        "type": "string",
                        "description": "Condition expression (e.g., 'NVDA < 130', 'inactive_hours > 48')"
                    },
                    "check_interval_minutes": {
                        "type": "integer",
                        "description": "How often to evaluate in minutes (default: 120 for price, 1440 for portfolio, 60 for silence)"
                    },
                    "cooldown_hours": {
                        "type": "integer",
                        "description": "Minimum hours between fires (default: 24)"
                    }
                }
            },
            "enabled": {
                "type": "boolean",
                "description": "Whether trigger is active (default: true)",
                "default": True
            },
            "expires_at": {
                "type": "string",
                "description": "Optional: ISO datetime when trigger auto-deletes"
            }
        },
        "required": ["user_id", "intent_name", "trigger_type", "action_context"]
    },
    "handler": create_trigger_tool_handler
}


# =============================================================================
# List Triggers Tool
# =============================================================================


async def list_triggers_tool_handler(
    user_id: str,
    trigger_type: str = "all",
    include_disabled: bool = False
) -> Dict[str, Any]:
    """
    List user's proactive triggers.

    Args:
        user_id: User identifier
        trigger_type: Filter by type: 'scheduled', 'condition', or 'all' (default: 'all')
        include_disabled: Include paused triggers (default: False)

    Returns:
        dict: Array of triggers with id, name, schedule/condition, status, etc.
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    # Build query parameters
    params = {"user_id": user_id}
    if trigger_type != "all":
        params["trigger_type"] = trigger_type
    if include_disabled:
        params["include_disabled"] = "true"

    try:
        logger.info(
            "Listing triggers via MCP tool",
            extra={
                "user_id": user_id,
                "trigger_type": trigger_type,
                "include_disabled": include_disabled
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{memories_url}/v1/intents",
                params=params
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()
                # API returns a list directly, not wrapped in an object
                if isinstance(result, list):
                    triggers = result
                else:
                    triggers = result.get("intents", [])

                logger.info(
                    "Triggers listed successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_count": len(triggers),
                        "duration_ms": duration_ms
                    }
                )

                # Format triggers for LLM consumption
                formatted_triggers = []
                for trigger in triggers:
                    formatted = {
                        "id": trigger.get("id"),
                        "intent_name": trigger.get("intent_name"),
                        "description": trigger.get("description"),
                        "trigger_type": trigger.get("trigger_type"),
                        "trigger_schedule": trigger.get("trigger_schedule"),
                        "trigger_condition": trigger.get("trigger_condition"),
                        "enabled": trigger.get("enabled"),
                        "next_check": trigger.get("next_check"),
                        "last_checked": trigger.get("last_checked"),
                        "last_executed": trigger.get("last_executed"),
                        "execution_count": trigger.get("execution_count", 0),
                        "last_execution_status": trigger.get("last_execution_status"),
                        "created_at": trigger.get("created_at"),
                        "updated_at": trigger.get("updated_at")
                    }

                    formatted_triggers.append(formatted)

                return {
                    "status": "success",
                    "trigger_count": len(formatted_triggers),
                    "triggers": formatted_triggers,
                    "message": f"Found {len(formatted_triggers)} trigger{'s' if len(formatted_triggers) != 1 else ''}."
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "List triggers failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to list triggers: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("List triggers timed out", extra={"user_id": user_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error listing triggers", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error listing triggers", extra={"user_id": user_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# List triggers tool definition
list_triggers_tool = {
    "name": "list_triggers",
    "description": """
List all proactive triggers for the current user.

USE WHEN USER ASKS:
- "What reminders do I have?"
- "Show my alerts"
- "What notifications are set up?"
- "List my triggers"
- "What's scheduled?"

Returns array of triggers with:
- id: Unique identifier
- intent_name: Display name
- trigger_type: 'scheduled' or 'condition'
- schedule/condition: Configuration details
- enabled: Active status (true/false)
- next_check: When it will next evaluate
- fire_count: Number of times it has fired
- last_fired: When it last fired (or null if never)

Use this before updating or deleting triggers to show user what exists.
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "trigger_type": {
                "type": "string",
                "enum": ["scheduled", "condition", "all"],
                "description": "Filter by type (default: 'all')",
                "default": "all"
            },
            "include_disabled": {
                "type": "boolean",
                "description": "Include paused triggers (default: false)",
                "default": False
            }
        },
        "required": ["user_id"]
    },
    "handler": list_triggers_tool_handler
}


# =============================================================================
# Update Trigger Tool
# =============================================================================


async def update_trigger_tool_handler(
    user_id: str,
    trigger_id: str,
    intent_name: str = None,
    schedule: dict = None,
    condition: dict = None,
    action_context: dict = None,
    enabled: bool = None
) -> Dict[str, Any]:
    """
    Update an existing proactive trigger.

    Supports partial updates - only provided fields are modified.

    Args:
        user_id: User identifier
        trigger_id: ID from list_triggers
        intent_name: New display name
        schedule: New schedule configuration
        condition: New condition configuration
        action_context: Updated briefing (merges with existing)
        enabled: Enable (True) or pause (False)

    Returns:
        dict: Updated trigger details
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id and trigger_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    if not trigger_id or not isinstance(trigger_id, str):
        return {
            "status": "error",
            "message": "Invalid trigger_id: must be non-empty string"
        }

    # Build request payload (only include provided fields)
    payload = {"user_id": user_id}
    if intent_name is not None:
        payload["intent_name"] = intent_name
    if schedule is not None:
        # Convert schedule from MCP tool format to API format
        # MCP format: {"mode": "cron", "cron_expression": "0 9 * * *", "timezone": "America/Los_Angeles"}
        # API format: {"cron": "0 9 * * *", "timezone": "America/Los_Angeles"}
        # Note: Only include timezone if provided, to preserve existing timezone on updates
        schedule_mode = schedule.get("mode", "cron")
        if schedule_mode == "once":
            trigger_schedule = {
                "trigger_at": schedule.get("datetime")
            }
            if schedule.get("timezone"):
                trigger_schedule["timezone"] = schedule["timezone"]
            payload["trigger_schedule"] = trigger_schedule
        elif schedule_mode == "cron":
            trigger_schedule = {
                "cron": schedule.get("cron_expression") or schedule.get("cron")
            }
            if schedule.get("timezone"):
                trigger_schedule["timezone"] = schedule["timezone"]
            payload["trigger_schedule"] = trigger_schedule
        else:
            # Pass through as-is for other modes
            payload["trigger_schedule"] = schedule
    if condition is not None:
        payload["trigger_condition"] = condition
    if action_context is not None:
        # action_context must be a JSON string
        if isinstance(action_context, dict):
            payload["action_context"] = json.dumps(action_context)
        else:
            payload["action_context"] = action_context
    if enabled is not None:
        payload["enabled"] = enabled

    try:
        logger.info(
            "Updating trigger via MCP tool",
            extra={
                "user_id": user_id,
                "trigger_id": trigger_id,
                "updates": {k: v for k, v in payload.items() if k != "user_id"}
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.put(
                f"{memories_url}/v1/intents/{trigger_id}",
                json=payload,
                headers={"Content-Type": "application/json"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                result = response.json()

                logger.info(
                    "Trigger updated successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "trigger": {
                        "id": result.get("id"),
                        "intent_name": result.get("intent_name"),
                        "description": result.get("description"),
                        "trigger_type": result.get("trigger_type"),
                        "trigger_schedule": result.get("trigger_schedule"),
                        "trigger_condition": result.get("trigger_condition"),
                        "enabled": result.get("enabled"),
                        "next_check": result.get("next_check"),
                        "execution_count": result.get("execution_count", 0),
                        "created_at": result.get("created_at"),
                        "updated_at": result.get("updated_at")
                    },
                    "message": f"Updated trigger '{result.get('intent_name')}'"
                }

            elif response.status_code == 404:
                logger.info(
                    "Trigger not found for update",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Trigger not found with ID '{trigger_id}'",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Update trigger failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to update trigger: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Update trigger timed out", extra={"user_id": user_id, "trigger_id": trigger_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error updating trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error updating trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Update trigger tool definition
update_trigger_tool = {
    "name": "update_trigger",
    "description": """
Update an existing proactive trigger's configuration.

USE WHEN USER WANTS TO:
- Change schedule: "Make it 8am instead of 9am"
- Modify condition: "Change to alert at $125 instead of $130"
- Update preferences: "Make the messages shorter"
- Pause: "Stop the morning updates for now" -> set enabled=false
- Resume: "Turn my alerts back on" -> set enabled=true

PROCESS:
1. Call list_triggers to find the trigger ID
2. Call update_trigger with the changes
3. Confirm the update with user

PAUSING VS DELETING:
- Use enabled=false to pause (can resume later)
- Use delete_trigger to permanently remove

Only include fields you want to change. Omitted fields keep current values.
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "trigger_id": {
                "type": "string",
                "description": "ID from list_triggers"
            },
            "intent_name": {
                "type": "string",
                "description": "New display name"
            },
            "schedule": {
                "type": "object",
                "description": "New schedule configuration"
            },
            "condition": {
                "type": "object",
                "description": "New condition configuration"
            },
            "action_context": {
                "type": "object",
                "description": "Updated briefing (merges with existing)"
            },
            "enabled": {
                "type": "boolean",
                "description": "Enable (true) or pause (false)"
            }
        },
        "required": ["user_id", "trigger_id"]
    },
    "handler": update_trigger_tool_handler
}


# =============================================================================
# Delete Trigger Tool
# =============================================================================


async def delete_trigger_tool_handler(
    user_id: str,
    trigger_id: str,
    confirm: bool = False
) -> Dict[str, Any]:
    """
    Permanently delete a proactive trigger.

    Args:
        user_id: User identifier
        trigger_id: ID from list_triggers
        confirm: Must be True to confirm deletion

    Returns:
        dict: Confirmation of deletion
    """
    start_time = time.time()

    # Get agentic-memories URL from config
    try:
        config = get_config()
        memories_url = config.get("AGENTIC_MEMORIES_URL", "http://host.docker.internal:8080")
    except Exception as e:
        logger.warning(f"Failed to load config, using default: {e}")
        memories_url = "http://host.docker.internal:8080"

    # Validate user_id and trigger_id
    if not user_id or not isinstance(user_id, str):
        return {
            "status": "error",
            "message": "Invalid user_id: must be non-empty string"
        }

    if not trigger_id or not isinstance(trigger_id, str):
        return {
            "status": "error",
            "message": "Invalid trigger_id: must be non-empty string"
        }

    # Validate confirmation
    if not confirm:
        logger.warning(
            "Delete trigger called without confirmation",
            extra={"user_id": user_id, "trigger_id": trigger_id}
        )
        return {
            "status": "error",
            "message": "Confirmation required. This permanently deletes the trigger. Set confirm=true to proceed.",
            "error_code": "CONFIRMATION_REQUIRED"
        }

    try:
        logger.info(
            "Deleting trigger via MCP tool",
            extra={
                "user_id": user_id,
                "trigger_id": trigger_id
            }
        )

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.delete(
                f"{memories_url}/v1/intents/{trigger_id}",
                params={"user_id": user_id, "confirm": "true"}
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # 200 = OK with response body, 204 = No Content (success with no body)
            if response.status_code in (200, 204):
                # Try to get response body if available (200), otherwise use trigger_id
                intent_name = trigger_id
                if response.status_code == 200:
                    try:
                        result = response.json()
                        intent_name = result.get('intent_name', trigger_id)
                    except Exception:
                        pass

                logger.info(
                    "Trigger deleted successfully via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "trigger_id": trigger_id,
                    "message": f"Deleted trigger '{intent_name}'"
                }

            elif response.status_code == 404:
                logger.info(
                    "Trigger not found for deletion",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "duration_ms": duration_ms
                    }
                )
                return {
                    "status": "error",
                    "message": f"Trigger not found with ID '{trigger_id}'",
                    "error_code": 404
                }

            else:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Delete trigger failed via MCP tool",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )

                return {
                    "status": "error",
                    "message": f"Failed to delete trigger: {error_msg}",
                    "error_code": response.status_code
                }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Delete trigger timed out", extra={"user_id": user_id, "trigger_id": trigger_id, "duration_ms": duration_ms})
        return {"status": "error", "message": "Service timed out. Please try again.", "error_code": "TIMEOUT"}

    except (httpx.NetworkError, httpx.ConnectError) as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Network error deleting trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms})
        return {"status": "error", "message": "Service unavailable. Please try again later.", "error_code": "NETWORK_ERROR"}

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error("Unexpected error deleting trigger", extra={"user_id": user_id, "trigger_id": trigger_id, "error": str(e), "duration_ms": duration_ms}, exc_info=True)
        return {"status": "error", "message": f"Unexpected error: {str(e)}", "error_code": "INTERNAL_ERROR"}


# Delete trigger tool definition
delete_trigger_tool = {
    "name": "delete_trigger",
    "description": """
Permanently delete a proactive trigger.

USE WHEN USER WANTS TO:
- "Stop the morning reminders" (permanently)
- "Cancel the NVDA alert"
- "Remove that trigger"
- "I don't need that anymore"

IMPORTANT:
- ALWAYS confirm with user before deleting
- This is permanent - cannot be undone
- For temporary stop, use update_trigger with enabled=false instead

PROCESS:
1. Call list_triggers to show user what exists
2. Confirm which trigger to delete
3. Call delete_trigger with confirm=true
4. Confirm deletion to user

Example:
User: "Stop my morning updates"
You: "I see you have 'Morning portfolio brief' set for 8:30am weekdays. Do you want to pause it temporarily or delete it permanently?"
User: "Delete it"
You: [Call delete_trigger with confirm=true]
    """,
    "inputSchema": {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "User identifier"
            },
            "trigger_id": {
                "type": "string",
                "description": "ID from list_triggers"
            },
            "confirm": {
                "type": "boolean",
                "description": "Must be true to confirm deletion"
            }
        },
        "required": ["user_id", "trigger_id", "confirm"]
    },
    "handler": delete_trigger_tool_handler
}
