"""
Home Assistant Tools (Epic 16)

Story 16.1: Query Tool - Entity state querying from Home Assistant via REST API.
Story 16.2: Control Tool - Entity control with allowlist enforcement.
Story 16.6: Voice Message Tool - Send voice messages to Alexa via notify.alexa_media.
"""

from typing import Any, Dict, List, Optional, Tuple
import asyncio
import time
import httpx

from mcp_server.config import (
    HA_URL,
    HA_ACCESS_TOKEN,
    HA_CONTROL_ALLOWLIST,
    HA_TIMEOUT,
    is_ha_configured,
)
from mcp_server.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# AllowlistValidator (Story 16.2)
# =============================================================================

class AllowlistValidator:
    """
    Validates entity IDs against the HA_CONTROL_ALLOWLIST.

    Supports:
    - Exact match: "light.living_room" matches "light.living_room"
    - Domain wildcard: "light.*" matches any "light.xxx" entity
    - Partial wildcard: "light.living*" matches "light.living_room", "light.living_lamp"
    - Empty allowlist blocks all control
    """

    def __init__(self, allowlist_str: Optional[str] = None):
        """
        Initialize with allowlist string.

        Args:
            allowlist_str: Comma-separated entity patterns (defaults to HA_CONTROL_ALLOWLIST)
        """
        raw = allowlist_str if allowlist_str is not None else HA_CONTROL_ALLOWLIST
        # Parse comma-separated, strip whitespace, filter empty
        self.patterns = [
            p.strip() for p in raw.split(",")
            if p.strip()
        ]

    def is_allowed(self, entity_id: str) -> bool:
        """
        Check if an entity ID is allowed for control.

        Args:
            entity_id: Entity ID to check (e.g., "light.living_room")

        Returns:
            True if allowed, False if blocked
        """
        import fnmatch

        if not self.patterns:
            return False

        for pattern in self.patterns:
            # Use fnmatch for glob-style matching (supports *, ?, [seq], [!seq])
            # This handles: "light.*", "light.living*", "light.living_room", etc.
            if fnmatch.fnmatch(entity_id, pattern):
                return True

        return False

    def get_allowed_list(self) -> List[str]:
        """
        Get list of allowed entity patterns.

        Returns:
            List of pattern strings (may include wildcards)
        """
        return self.patterns.copy()


# Global allowlist validator instance
_allowlist_validator: Optional[AllowlistValidator] = None


def get_allowlist_validator() -> AllowlistValidator:
    """Get or create the allowlist validator singleton."""
    global _allowlist_validator
    if _allowlist_validator is None:
        _allowlist_validator = AllowlistValidator()
    return _allowlist_validator


def reset_allowlist_validator():
    """Reset the allowlist validator (for testing)."""
    global _allowlist_validator
    _allowlist_validator = None


class HomeAssistantClient:
    """
    Async HTTP client for Home Assistant REST API.

    Handles authentication, timeout, and error responses.
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        access_token: Optional[str] = None,
        timeout: Optional[int] = None
    ):
        """
        Initialize Home Assistant client.

        Args:
            base_url: HA base URL (defaults to HA_URL from config)
            access_token: Long-lived access token (defaults to HA_ACCESS_TOKEN)
            timeout: Request timeout in seconds (defaults to HA_TIMEOUT)
        """
        self.base_url = (base_url or HA_URL).rstrip("/")
        self.access_token = access_token or HA_ACCESS_TOKEN
        self.timeout = timeout or HA_TIMEOUT

    def _check_config(self) -> Optional[Dict[str, Any]]:
        """
        Check if HA is configured. Returns error dict if not.
        """
        if not self.base_url:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "CONFIG_ERROR",
                "error_message": "HA_URL not configured. Set HA_URL environment variable."
            }
        if not self.access_token:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "CONFIG_ERROR",
                "error_message": "HA_ACCESS_TOKEN not configured. Generate a long-lived access token in Home Assistant."
            }
        return None

    def _get_headers(self) -> Dict[str, str]:
        """Get authorization headers for HA API."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    def _parse_entity_state(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse HA entity state response into standard format.

        Args:
            data: Raw HA API response for an entity

        Returns:
            Standardized entity dict with entity_id, state, attributes, last_changed
        """
        return {
            "entity_id": data.get("entity_id", ""),
            "state": data.get("state", "unknown"),
            "attributes": data.get("attributes", {}),
            "last_changed": data.get("last_changed", "")
        }

    async def get_entity_state(self, entity_id: str) -> Dict[str, Any]:
        """
        Get state of a single entity.

        Args:
            entity_id: Entity ID (e.g., "light.living_room")

        Returns:
            Dict with status and entity data or error info
        """
        config_error = self._check_config()
        if config_error:
            return config_error

        url = f"{self.base_url}/api/states/{entity_id}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers())

                if response.status_code == 401:
                    return {
                        "status": "error",
                        "provider": "home_assistant",
                        "error_code": "UNAUTHORIZED",
                        "error_message": "Invalid or expired access token. Generate a new long-lived access token.",
                        "entity_id": entity_id
                    }

                if response.status_code == 404:
                    return {
                        "status": "error",
                        "provider": "home_assistant",
                        "error_code": "NOT_FOUND",
                        "error_message": f"Entity '{entity_id}' not found in Home Assistant.",
                        "entity_id": entity_id
                    }

                response.raise_for_status()
                data = response.json()

                return {
                    "status": "success",
                    "provider": "home_assistant",
                    "entities": [self._parse_entity_state(data)],
                    "query_count": 1
                }

        except httpx.TimeoutException:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "TIMEOUT",
                "error_message": f"Request timed out after {self.timeout}s. Home Assistant may be slow or unreachable.",
                "entity_id": entity_id
            }
        except httpx.ConnectError:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "NETWORK_ERROR",
                "error_message": f"Failed to connect to Home Assistant at {self.base_url}. Check network connectivity.",
                "entity_id": entity_id
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "HTTP_ERROR",
                "error_message": f"HTTP error {e.response.status_code}: {str(e)}",
                "entity_id": entity_id
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "UNKNOWN",
                "error_message": str(e),
                "entity_id": entity_id
            }

    async def get_entities_by_ids(self, entity_ids: List[str]) -> Dict[str, Any]:
        """
        Get states of multiple entities by ID.

        Args:
            entity_ids: List of entity IDs to query

        Returns:
            Dict with status and list of entity data or error info
        """
        config_error = self._check_config()
        if config_error:
            return config_error

        if not entity_ids:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "INVALID_INPUT",
                "error_message": "No entity IDs provided."
            }

        results = []
        errors = []

        for entity_id in entity_ids:
            result = await self.get_entity_state(entity_id)

            if result["status"] == "success":
                results.extend(result["entities"])
            else:
                # For individual entity errors, include in errors list but continue
                errors.append({
                    "entity_id": entity_id,
                    "error_code": result.get("error_code"),
                    "error_message": result.get("error_message")
                })

        # If all queries failed, return error
        if not results and errors:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "ALL_FAILED",
                "error_message": f"All {len(entity_ids)} entity queries failed.",
                "errors": errors
            }

        response = {
            "status": "success",
            "provider": "home_assistant",
            "entities": results,
            "query_count": len(results)
        }

        # Include partial errors if some succeeded
        if errors:
            response["partial_errors"] = errors

        return response

    async def get_entities_by_domain(self, domain: str) -> Dict[str, Any]:
        """
        Get all entities in a domain.

        Args:
            domain: Domain name (e.g., "light", "sensor", "all")

        Returns:
            Dict with status and list of entity data or error info
        """
        config_error = self._check_config()
        if config_error:
            return config_error

        url = f"{self.base_url}/api/states"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self._get_headers())

                if response.status_code == 401:
                    return {
                        "status": "error",
                        "provider": "home_assistant",
                        "error_code": "UNAUTHORIZED",
                        "error_message": "Invalid or expired access token. Generate a new long-lived access token."
                    }

                response.raise_for_status()
                all_states = response.json()

                # Filter by domain if not "all"
                if domain.lower() == "all":
                    filtered = all_states
                else:
                    domain_prefix = f"{domain.lower()}."
                    filtered = [
                        s for s in all_states
                        if s.get("entity_id", "").startswith(domain_prefix)
                    ]

                entities = [self._parse_entity_state(s) for s in filtered]

                return {
                    "status": "success",
                    "provider": "home_assistant",
                    "entities": entities,
                    "query_count": len(entities),
                    "domain": domain
                }

        except httpx.TimeoutException:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "TIMEOUT",
                "error_message": f"Request timed out after {self.timeout}s. Home Assistant may be slow or unreachable."
            }
        except httpx.ConnectError:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "NETWORK_ERROR",
                "error_message": f"Failed to connect to Home Assistant at {self.base_url}. Check network connectivity."
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "HTTP_ERROR",
                "error_message": f"HTTP error {e.response.status_code}: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "UNKNOWN",
                "error_message": str(e)
            }

    # =========================================================================
    # Control Methods (Story 16.2)
    # =========================================================================

    @staticmethod
    def get_domain_from_entity(entity_id: str) -> str:
        """
        Extract domain from entity ID.

        Args:
            entity_id: Entity ID (e.g., "light.living_room")

        Returns:
            Domain string (e.g., "light")
        """
        if "." in entity_id:
            return entity_id.split(".")[0]
        return ""

    async def call_service(
        self,
        domain: str,
        service: str,
        entity_id: str,
        data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Call a Home Assistant service.

        Args:
            domain: Service domain (e.g., "light", "climate")
            service: Service name (e.g., "turn_on", "set_temperature")
            entity_id: Target entity ID
            data: Additional service data (e.g., {"brightness": 255})

        Returns:
            Dict with status and result or error info
        """
        config_error = self._check_config()
        if config_error:
            return config_error

        url = f"{self.base_url}/api/services/{domain}/{service}"

        # Build request body
        body = {"entity_id": entity_id}
        if data:
            body.update(data)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    url,
                    headers=self._get_headers(),
                    json=body
                )

                if response.status_code == 401:
                    return {
                        "status": "error",
                        "provider": "home_assistant",
                        "error_code": "UNAUTHORIZED",
                        "error_message": "Invalid or expired access token.",
                        "entity_id": entity_id
                    }

                if response.status_code == 404:
                    return {
                        "status": "error",
                        "provider": "home_assistant",
                        "error_code": "SERVICE_NOT_FOUND",
                        "error_message": f"Service '{domain}.{service}' not found.",
                        "entity_id": entity_id
                    }

                response.raise_for_status()

                return {
                    "status": "success",
                    "provider": "home_assistant",
                    "entity_id": entity_id,
                    "service_called": f"{domain}.{service}"
                }

        except httpx.TimeoutException:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "TIMEOUT",
                "error_message": f"Request timed out after {self.timeout}s.",
                "entity_id": entity_id
            }
        except httpx.ConnectError:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "NETWORK_ERROR",
                "error_message": f"Failed to connect to Home Assistant at {self.base_url}.",
                "entity_id": entity_id
            }
        except httpx.HTTPStatusError as e:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "HTTP_ERROR",
                "error_message": f"HTTP error {e.response.status_code}: {str(e)}",
                "entity_id": entity_id
            }
        except Exception as e:
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "UNKNOWN",
                "error_message": str(e),
                "entity_id": entity_id
            }


# =============================================================================
# Action Mapping (Story 16.2)
# =============================================================================

def map_action_to_service(
    action: str,
    entity_id: str,
    parameters: Optional[Dict[str, Any]] = None
) -> Tuple[str, str, Dict[str, Any]]:
    """
    Map a control action to Home Assistant service call.

    Args:
        action: Action name (turn_on, turn_off, toggle, set_brightness, etc.)
        entity_id: Target entity ID
        parameters: Action parameters (brightness, temperature, etc.)

    Returns:
        Tuple of (domain, service_name, service_data)

    Raises:
        ValueError: If action is unknown
    """
    domain = HomeAssistantClient.get_domain_from_entity(entity_id)
    params = parameters or {}

    if action == "turn_on":
        return (domain, "turn_on", {})

    elif action == "turn_off":
        return (domain, "turn_off", {})

    elif action == "toggle":
        return (domain, "toggle", {})

    elif action == "set_brightness":
        brightness = params.get("brightness")
        if brightness is None:
            raise ValueError("set_brightness requires 'brightness' parameter (0-255)")
        return ("light", "turn_on", {"brightness": int(brightness)})

    elif action == "set_temperature":
        temperature = params.get("temperature")
        if temperature is None:
            raise ValueError("set_temperature requires 'temperature' parameter")
        return ("climate", "set_temperature", {"temperature": float(temperature)})

    elif action == "set_hvac_mode":
        hvac_mode = params.get("hvac_mode")
        if hvac_mode is None:
            raise ValueError("set_hvac_mode requires 'hvac_mode' parameter")
        return ("climate", "set_hvac_mode", {"hvac_mode": hvac_mode})

    elif action == "set_position":
        position = params.get("position")
        if position is None:
            raise ValueError("set_position requires 'position' parameter (0-100)")
        return ("cover", "set_cover_position", {"position": int(position)})

    else:
        raise ValueError(f"Unknown action: {action}")


def _is_disabled_entity(entity: Dict[str, Any]) -> bool:
    """
    Check if an entity is disabled/orphaned.

    Entities with 'restored: true' attribute are orphaned entries
    that HA couldn't reconnect to their integration.
    """
    attributes = entity.get("attributes", {})
    return attributes.get("restored", False) is True


async def home_assistant_query_handler(
    entity_ids: Optional[List[str]] = None,
    domain: Optional[str] = None,
    exclude_disabled: bool = True
) -> Dict[str, Any]:
    """
    Query Home Assistant entity states.

    Use either entity_ids OR domain parameter (not both).

    Args:
        entity_ids: List of specific entity IDs to query
        domain: Domain name to query all entities (light, sensor, climate, etc.)
        exclude_disabled: Filter out disabled/orphaned entities (default: True)

    Returns:
        Dict with status, provider, entities list, and query_count
    """
    start_time = time.time()

    # Validate input - must have exactly one of entity_ids or domain
    if entity_ids and domain:
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_INPUT",
            "error_message": "Provide either entity_ids OR domain, not both."
        }

    if not entity_ids and not domain:
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_INPUT",
            "error_message": "Provide either entity_ids or domain parameter."
        }

    client = HomeAssistantClient()

    if entity_ids:
        result = await client.get_entities_by_ids(entity_ids)
    else:
        result = await client.get_entities_by_domain(domain)

    # Filter out disabled entities if requested
    if result.get("status") == "success" and exclude_disabled:
        original_count = len(result.get("entities", []))
        result["entities"] = [
            e for e in result.get("entities", [])
            if not _is_disabled_entity(e)
        ]
        filtered_count = original_count - len(result["entities"])
        result["query_count"] = len(result["entities"])
        if filtered_count > 0:
            result["filtered_disabled"] = filtered_count

    duration_ms = int((time.time() - start_time) * 1000)

    # Log the operation
    logger.info(
        "home_assistant_query.completed",
        extra={
            "tool_name": "home_assistant_query",
            "status": result.get("status"),
            "entity_count": result.get("query_count", 0),
            "duration_ms": duration_ms,
            "query_type": "entity_ids" if entity_ids else "domain",
            "domain": domain if domain else None,
            "exclude_disabled": exclude_disabled,
            "filtered_disabled": result.get("filtered_disabled", 0)
        }
    )

    return result


# Home Assistant Query Tool Definition
home_assistant_query_tool = {
    "name": "home_assistant_query",
    "description": (
        "Query entity states from Home Assistant smart home system. "
        "Returns current state, attributes, and last_changed timestamp for entities. "
        "Use for checking device status (lights, switches), sensor readings (temperature, humidity), "
        "or any home automation state. Provide either specific entity_ids OR a domain to query."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "entity_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "List of specific entity IDs to query. "
                    "Provide either entity_ids OR domain (not both). "
                    "Examples: ['light.living_room', 'sensor.outdoor_temperature', 'binary_sensor.garage_door']"
                )
            },
            "domain": {
                "type": "string",
                "enum": ["light", "switch", "sensor", "climate", "binary_sensor", "cover", "fan", "lock", "media_player", "all"],
                "description": (
                    "Query all entities in a domain. Use 'all' to get complete state dump. "
                    "Provide either entity_ids OR domain (not both). "
                    "Common domains: light, switch, sensor, climate, binary_sensor, cover, fan, lock"
                )
            },
            "exclude_disabled": {
                "type": "boolean",
                "default": True,
                "description": (
                    "Filter out disabled/orphaned entities (those with restored=true attribute). "
                    "Default: true. Set to false to include all entities."
                )
            }
        }
    },
    "handler": home_assistant_query_handler
}


# =============================================================================
# Home Assistant Control Tool (Story 16.2)
# =============================================================================

async def home_assistant_control_handler(
    entity_id: str,
    action: str,
    parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Control a Home Assistant entity.

    SECURITY: Only entities in HA_CONTROL_ALLOWLIST can be controlled.
    Attempting to control non-allowlisted entities returns FORBIDDEN error.

    Args:
        entity_id: Entity ID to control (e.g., "light.living_room")
        action: Action to perform (turn_on, turn_off, toggle, set_brightness, etc.)
        parameters: Optional parameters for the action (e.g., {"brightness": 200})

    Returns:
        Dict with status, previous_state, new_state, or error info
    """
    start_time = time.time()

    # STEP 1: Check allowlist FIRST (CRITICAL - never bypass)
    validator = get_allowlist_validator()
    allowed = validator.is_allowed(entity_id)

    if not allowed:
        duration_ms = int((time.time() - start_time) * 1000)

        # Prepare forbidden response with allowed list
        allowed_list = validator.get_allowed_list()
        if allowed_list:
            message = f"Entity '{entity_id}' not in allowlist. Allowed: {', '.join(allowed_list)}"
        else:
            message = "All control is disabled. HA_CONTROL_ALLOWLIST is empty."

        # Audit log for denied request
        logger.warning(
            "home_assistant_control.denied",
            extra={
                "tool_name": "home_assistant_control",
                "entity_id": entity_id,
                "action": action,
                "allowed": False,
                "duration_ms": duration_ms
            }
        )

        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "FORBIDDEN",
            "error_message": message,
            "entity_id": entity_id
        }

    # STEP 2: Map action to service call
    try:
        domain, service, service_data = map_action_to_service(action, entity_id, parameters)
    except ValueError as e:
        duration_ms = int((time.time() - start_time) * 1000)

        logger.error(
            "home_assistant_control.invalid_action",
            extra={
                "tool_name": "home_assistant_control",
                "entity_id": entity_id,
                "action": action,
                "error": str(e),
                "duration_ms": duration_ms
            }
        )

        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_ACTION",
            "error_message": str(e),
            "entity_id": entity_id
        }

    client = HomeAssistantClient()

    # STEP 3: Get current state (for previous_state)
    prev_result = await client.get_entity_state(entity_id)
    previous_state = None
    if prev_result.get("status") == "success" and prev_result.get("entities"):
        previous_state = prev_result["entities"][0].get("state")

    # STEP 4: Call the service
    result = await client.call_service(domain, service, entity_id, service_data)

    if result.get("status") != "success":
        duration_ms = int((time.time() - start_time) * 1000)

        logger.error(
            "home_assistant_control.service_failed",
            extra={
                "tool_name": "home_assistant_control",
                "entity_id": entity_id,
                "action": action,
                "error_code": result.get("error_code"),
                "allowed": True,
                "duration_ms": duration_ms
            }
        )

        return result

    # STEP 5: Get new state (for new_state)
    # Small delay to allow HA to process the state change
    await asyncio.sleep(0.2)

    new_result = await client.get_entity_state(entity_id)
    new_state = None
    if new_result.get("status") == "success" and new_result.get("entities"):
        new_state = new_result["entities"][0].get("state")

    duration_ms = int((time.time() - start_time) * 1000)

    # Audit log for successful request
    logger.info(
        "home_assistant_control.completed",
        extra={
            "tool_name": "home_assistant_control",
            "entity_id": entity_id,
            "action": action,
            "parameters": parameters,
            "previous_state": previous_state,
            "new_state": new_state,
            "allowed": True,
            "duration_ms": duration_ms
        }
    )

    return {
        "status": "success",
        "provider": "home_assistant",
        "entity_id": entity_id,
        "action": action,
        "parameters": parameters or {},
        "previous_state": previous_state,
        "new_state": new_state
    }


# Home Assistant Control Tool Definition
home_assistant_control_tool = {
    "name": "home_assistant_control",
    "description": (
        "Control Home Assistant entities (lights, switches, climate, covers). "
        "SECURITY: Only entities in HA_CONTROL_ALLOWLIST can be controlled. "
        "Attempting to control non-allowlisted entities returns FORBIDDEN error. "
        "Use for actions like turning on/off lights, setting thermostat temperature, "
        "or adjusting cover positions."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "entity_id": {
                "type": "string",
                "description": (
                    "Entity ID to control (e.g., 'light.living_room', 'climate.thermostat')"
                )
            },
            "action": {
                "type": "string",
                "enum": [
                    "turn_on",
                    "turn_off",
                    "toggle",
                    "set_brightness",
                    "set_temperature",
                    "set_hvac_mode",
                    "set_position"
                ],
                "description": (
                    "Action to perform. "
                    "turn_on/turn_off/toggle: Basic on/off control. "
                    "set_brightness: Set light brightness (0-255). "
                    "set_temperature: Set thermostat target temp. "
                    "set_hvac_mode: Set HVAC mode (heat, cool, auto, off). "
                    "set_position: Set cover position (0-100)."
                )
            },
            "parameters": {
                "type": "object",
                "description": (
                    "Action parameters. Examples: "
                    "{\"brightness\": 200} for set_brightness, "
                    "{\"temperature\": 72} for set_temperature, "
                    "{\"hvac_mode\": \"heat\"} for set_hvac_mode, "
                    "{\"position\": 50} for set_position."
                ),
                "additionalProperties": True
            }
        },
        "required": ["entity_id", "action"]
    },
    "handler": home_assistant_control_handler
}


# =============================================================================
# Voice Message Tool (Story 16.6)
# =============================================================================

# Voice type to SSML mapping for Alexa emotional voice
VOICE_TYPES: Dict[str, Dict[str, Any]] = {
    # Basic delivery methods
    "say": {"method": "tts", "ssml": None},
    "announce": {"method": "announce", "ssml": None},

    # Effects (SSML wrapped)
    "whisper": {
        "method": "tts",
        "ssml": '<amazon:effect name="whispered">{message}</amazon:effect>'
    },

    # Emotions (SSML wrapped)
    "excited": {
        "method": "tts",
        "ssml": '<amazon:emotion name="excited" intensity="medium">{message}</amazon:emotion>'
    },
    "disappointed": {
        "method": "tts",
        "ssml": '<amazon:emotion name="disappointed" intensity="medium">{message}</amazon:emotion>'
    },

    # Speaking Styles (SSML wrapped)
    "conversational": {
        "method": "tts",
        "ssml": '<amazon:domain name="conversational">{message}</amazon:domain>'
    },
    "news": {
        "method": "tts",
        "ssml": '<amazon:domain name="news">{message}</amazon:domain>'
    },
    "fun": {
        "method": "tts",
        "ssml": '<amazon:domain name="fun">{message}</amazon:domain>'
    },
}

# Cooldown state for voice messages (module-level)
_last_voice_message_time: Optional[float] = None
VOICE_MESSAGE_COOLDOWN_SECONDS = 60


def reset_voice_message_cooldown():
    """Reset the voice message cooldown (for testing)."""
    global _last_voice_message_time
    _last_voice_message_time = None


def _check_voice_cooldown() -> Optional[Dict[str, Any]]:
    """
    Check if voice message is on cooldown.

    Returns:
        None if not on cooldown, error dict if on cooldown
    """
    global _last_voice_message_time
    if _last_voice_message_time:
        elapsed = time.time() - _last_voice_message_time
        if elapsed < VOICE_MESSAGE_COOLDOWN_SECONDS:
            remaining = int(VOICE_MESSAGE_COOLDOWN_SECONDS - elapsed)
            return {
                "status": "error",
                "provider": "home_assistant",
                "error_code": "COOLDOWN",
                "error_message": f"Voice message on cooldown. Try again in {remaining} seconds.",
                "seconds_remaining": remaining
            }
    return None


def build_ssml_message(message: str, voice_type: str) -> str:
    """
    Build SSML-wrapped message based on voice type.

    Args:
        message: The message to speak
        voice_type: One of the VOICE_TYPES keys

    Returns:
        SSML-wrapped message or plain message if no SSML needed
    """
    if voice_type not in VOICE_TYPES:
        return message

    voice_config = VOICE_TYPES[voice_type]
    ssml_template = voice_config.get("ssml")

    if ssml_template:
        return ssml_template.format(message=message)
    return message


def get_voice_delivery_method(voice_type: str) -> str:
    """
    Get the delivery method (tts or announce) for a voice type.

    Args:
        voice_type: One of the VOICE_TYPES keys

    Returns:
        "tts" or "announce"
    """
    if voice_type in VOICE_TYPES:
        return VOICE_TYPES[voice_type].get("method", "tts")
    return "tts"


async def send_voice_message_to_smart_home_handler(
    message: str,
    devices: List[str],
    voice_type: str = "say"
) -> Dict[str, Any]:
    """
    Send a voice message to smart home speakers (Alexa) via Home Assistant.

    This tool calls the notify.alexa_media service with SSML-wrapped messages
    for emotional voice expression.

    CONSTRAINTS:
    - Only effective when user is physically at home
    - This is a COMPLEMENT to text responses, not replacement
    - 60-second cooldown between successful sends
    - Cooldown NOT consumed on errors

    Args:
        message: The message for Annie to speak aloud
        devices: List of target device entity IDs (e.g., ["media_player.kitchen_echo"])
        voice_type: How to deliver the message (say, announce, whisper, excited, etc.)

    Returns:
        Dict with status, devices, message, voice_type, or error info
    """
    global _last_voice_message_time
    start_time = time.time()

    # STEP 1: Check cooldown (fail fast)
    cooldown_error = _check_voice_cooldown()
    if cooldown_error:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.info(
            "send_voice_message.cooldown_blocked",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "devices": devices,
                "voice_type": voice_type,
                "cooldown_active": True,
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return cooldown_error

    # STEP 2: Validate inputs
    if not message or not message.strip():
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning(
            "send_voice_message.invalid_input",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error": "empty_message",
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_INPUT",
            "error_message": "Message cannot be empty."
        }

    if not devices or len(devices) == 0:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning(
            "send_voice_message.invalid_input",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error": "empty_devices",
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_INPUT",
            "error_message": "At least one device must be specified."
        }

    if voice_type not in VOICE_TYPES:
        duration_ms = int((time.time() - start_time) * 1000)
        valid_types = list(VOICE_TYPES.keys())
        logger.warning(
            "send_voice_message.invalid_voice_type",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "voice_type": voice_type,
                "valid_types": valid_types,
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_INPUT",
            "error_message": f"Invalid voice_type '{voice_type}'. Valid types: {', '.join(valid_types)}"
        }

    # STEP 3: Query HA for valid media_player entities (device validation)
    query_result = await home_assistant_query_handler(domain="media_player")

    if query_result.get("status") != "success":
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "send_voice_message.ha_query_failed",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error_code": query_result.get("error_code"),
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        # Pass through HA errors (CONFIG_ERROR, NETWORK_ERROR, etc.)
        return query_result

    # Extract valid entity IDs from query result
    valid_entities = query_result.get("entities", [])
    valid_device_ids = [e.get("entity_id") for e in valid_entities if e.get("entity_id")]

    # STEP 4: Validate ALL requested devices exist (fail-all on any invalid)
    invalid_devices = [d for d in devices if d not in valid_device_ids]

    if invalid_devices:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.warning(
            "send_voice_message.invalid_devices",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "invalid_devices": invalid_devices,
                "valid_devices": valid_device_ids,
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "INVALID_DEVICE",
            "error_message": f"Unknown device(s): {invalid_devices}",
            "invalid_devices": invalid_devices,
            "valid_devices": valid_device_ids
        }

    # STEP 5: Build SSML-wrapped message
    ssml_message = build_ssml_message(message.strip(), voice_type)
    delivery_method = get_voice_delivery_method(voice_type)

    # STEP 6: Call notify.alexa_media service
    client = HomeAssistantClient()

    config_error = client._check_config()
    if config_error:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "send_voice_message.config_error",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error_code": "CONFIG_ERROR",
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return config_error

    # Build notify service payload (different from standard service call)
    # notify.alexa_media uses 'target' array, not 'entity_id'
    url = f"{client.base_url}/api/services/notify/alexa_media"
    payload = {
        "message": ssml_message,
        "target": devices,
        "data": {"type": delivery_method}
    }

    try:
        async with httpx.AsyncClient(timeout=client.timeout) as http_client:
            response = await http_client.post(
                url,
                headers=client._get_headers(),
                json=payload
            )

            if response.status_code == 401:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "send_voice_message.unauthorized",
                    extra={
                        "tool_name": "send_voice_message_to_smart_home",
                        "error_code": "UNAUTHORIZED",
                        "duration_ms": duration_ms,
                        "status": "error"
                    }
                )
                return {
                    "status": "error",
                    "provider": "home_assistant",
                    "error_code": "UNAUTHORIZED",
                    "error_message": "Invalid or expired access token."
                }

            if response.status_code == 404:
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "send_voice_message.service_not_found",
                    extra={
                        "tool_name": "send_voice_message_to_smart_home",
                        "error_code": "SERVICE_NOT_FOUND",
                        "duration_ms": duration_ms,
                        "status": "error"
                    }
                )
                return {
                    "status": "error",
                    "provider": "home_assistant",
                    "error_code": "SERVICE_NOT_FOUND",
                    "error_message": "notify.alexa_media service not found. Ensure Alexa Media Player integration is installed."
                }

            response.raise_for_status()

            # STEP 7: On success, update cooldown timestamp
            _last_voice_message_time = time.time()

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "send_voice_message.completed",
                extra={
                    "tool_name": "send_voice_message_to_smart_home",
                    "devices": devices,
                    "voice_type": voice_type,
                    "delivery_method": delivery_method,
                    "cooldown_active": False,
                    "duration_ms": duration_ms,
                    "status": "success"
                }
            )

            return {
                "status": "success",
                "provider": "home_assistant",
                "devices": devices,
                "message": message.strip(),
                "voice_type": voice_type,
                "cooldown_seconds": VOICE_MESSAGE_COOLDOWN_SECONDS
            }

    except httpx.TimeoutException:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "send_voice_message.timeout",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error_code": "TIMEOUT",
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "TIMEOUT",
            "error_message": f"Request timed out after {client.timeout}s."
        }

    except httpx.ConnectError:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "send_voice_message.network_error",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error_code": "NETWORK_ERROR",
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "NETWORK_ERROR",
            "error_message": f"Failed to connect to Home Assistant at {client.base_url}."
        }

    except httpx.HTTPStatusError as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "send_voice_message.http_error",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error_code": "HTTP_ERROR",
                "http_status": e.response.status_code,
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "HTTP_ERROR",
            "error_message": f"HTTP error {e.response.status_code}: {str(e)}"
        }

    except Exception as e:
        duration_ms = int((time.time() - start_time) * 1000)
        logger.error(
            "send_voice_message.unknown_error",
            extra={
                "tool_name": "send_voice_message_to_smart_home",
                "error_code": "UNKNOWN",
                "error": str(e),
                "duration_ms": duration_ms,
                "status": "error"
            }
        )
        return {
            "status": "error",
            "provider": "home_assistant",
            "error_code": "UNKNOWN",
            "error_message": str(e)
        }


# Voice Message Tool Definition
send_voice_message_to_smart_home_tool = {
    "name": "send_voice_message_to_smart_home",
    "description": (
        "Send a voice message to smart home speakers (Alexa devices) via Home Assistant. "
        "USE WITH DISCRETION - CONSTRAINTS: "
        "1) Only effective when user is physically at home - do NOT use if user is away. "
        "2) This is a COMPLEMENT to text responses, not a replacement - always send text too. "
        "3) 60-second cooldown between messages to prevent annoyance. "
        "VOICE TYPES - choose based on emotional context: "
        "'say' (default): Neutral delivery. "
        "'announce': Attention tone first - for urgent matters. "
        "'whisper': Soft, intimate - for gentle reminders, private moments. "
        "'excited': Happy, enthusiastic - for celebrations, good news. "
        "'disappointed': Empathetic, sympathetic - for comfort, bad news. "
        "'conversational': Casual, friendly - like chatting with a friend. "
        "'news': Formal delivery - for factual information. "
        "'fun': Animated, playful - for greetings, lighthearted moments. "
        "AVOID: routine responses, sensitive info, late night (unless urgent)."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "message": {
                "type": "string",
                "description": "The message for Annie to speak aloud"
            },
            "devices": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Target device entity IDs. Examples: "
                    "['media_player.kitchen_echo', 'media_player.bedroom_echo']"
                )
            },
            "voice_type": {
                "type": "string",
                "enum": ["say", "announce", "whisper", "excited", "disappointed", "conversational", "news", "fun"],
                "default": "say",
                "description": (
                    "How to deliver the message. "
                    "'say': Neutral (default). "
                    "'announce': Attention tone first. "
                    "'whisper': Soft, intimate. "
                    "'excited': Happy, enthusiastic. "
                    "'disappointed': Empathetic, sympathetic. "
                    "'conversational': Casual, friendly. "
                    "'news': Formal, factual. "
                    "'fun': Animated, playful."
                )
            }
        },
        "required": ["message", "devices"]
    },
    "handler": send_voice_message_to_smart_home_handler
}
