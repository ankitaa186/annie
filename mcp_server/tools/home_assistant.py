"""
Home Assistant Tools (Epic 16)

Story 16.1: Query Tool - Entity state querying from Home Assistant via REST API.
Story 16.2: Control Tool - Entity control with allowlist enforcement.
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
                    "Examples: ['light.living_room', 'sensor.outdoor_temperature', 'binary_sensor.garage_door']"
                )
            },
            "domain": {
                "type": "string",
                "enum": ["light", "switch", "sensor", "climate", "binary_sensor", "cover", "fan", "lock", "media_player", "all"],
                "description": (
                    "Query all entities in a domain. Use 'all' to get complete state dump. "
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
        },
        "oneOf": [
            {"required": ["entity_ids"]},
            {"required": ["domain"]}
        ]
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
