"""
Tests for Home Assistant Control Tool (Epic 16 - Story 16.2)

Tests cover:
- AC #1: Allowlist parsing
- AC #2: Exact match allowlist
- AC #3: Wildcard allowlist support
- AC #4: Empty allowlist blocks all control
- AC #5: FORBIDDEN error includes allowed entities
- AC #6: Action to service mapping
- AC #7: Previous and new state in response
- AC #8: Audit logging for all attempts
- AC #9: Unit tests with >90% coverage
"""

from unittest.mock import AsyncMock, patch, MagicMock
import pytest


@pytest.fixture(autouse=True)
def _bypass_admin_check():
    """Bypass admin authorization for all HA control tests."""
    with patch("mcp_server.tools.home_assistant.is_admin", return_value=True):
        yield


class TestAllowlistValidator:
    """Tests for AllowlistValidator class (AC #1, #2, #3, #4)."""

    def test_parsing_comma_separated(self):
        """AC #1: Parse comma-separated allowlist."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.living_room,switch.fan")
        assert len(validator.patterns) == 2
        assert "light.living_room" in validator.patterns
        assert "switch.fan" in validator.patterns

    def test_parsing_with_whitespace(self):
        """AC #1: Handle whitespace in allowlist."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.a , switch.b , climate.c ")
        assert len(validator.patterns) == 3
        assert "light.a" in validator.patterns
        assert "switch.b" in validator.patterns
        assert "climate.c" in validator.patterns

    def test_parsing_empty_string(self):
        """AC #1: Empty string results in empty patterns."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("")
        assert len(validator.patterns) == 0

    def test_parsing_only_commas(self):
        """AC #1: Only commas results in empty patterns."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator(",,,")
        assert len(validator.patterns) == 0

    def test_exact_match_allowed(self):
        """AC #2: Exact match entity is allowed."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.living_room,switch.fan")
        assert validator.is_allowed("light.living_room") is True
        assert validator.is_allowed("switch.fan") is True

    def test_exact_match_denied(self):
        """AC #2: Non-matching entity is denied."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.living_room,switch.fan")
        assert validator.is_allowed("light.bedroom") is False
        assert validator.is_allowed("climate.thermostat") is False

    def test_wildcard_matches_domain(self):
        """AC #3: Wildcard pattern matches any entity in domain."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.*,climate.thermostat")
        assert validator.is_allowed("light.bedroom") is True
        assert validator.is_allowed("light.kitchen") is True
        assert validator.is_allowed("light.any_room_name") is True
        assert validator.is_allowed("climate.thermostat") is True

    def test_wildcard_does_not_match_other_domains(self):
        """AC #3: Wildcard only matches its own domain."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.*")
        assert validator.is_allowed("switch.fan") is False
        assert validator.is_allowed("climate.thermostat") is False
        assert validator.is_allowed("cover.garage") is False

    def test_partial_wildcard_matches(self):
        """Partial wildcard like light.living* matches light.living_room."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.living*")
        assert validator.is_allowed("light.living_room") is True
        assert validator.is_allowed("light.living_lamp") is True
        assert validator.is_allowed("light.living") is True
        # Does not match other lights
        assert validator.is_allowed("light.bedroom") is False
        assert validator.is_allowed("light.kitchen") is False
        # Does not match other domains
        assert validator.is_allowed("switch.living_room") is False

    def test_empty_allowlist_blocks_all(self):
        """AC #4: Empty allowlist blocks all entities."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("")
        assert validator.is_allowed("light.living_room") is False
        assert validator.is_allowed("switch.fan") is False
        assert validator.is_allowed("climate.thermostat") is False

    def test_get_allowed_list(self):
        """Get the list of allowed patterns."""
        from mcp_server.tools.home_assistant import AllowlistValidator

        validator = AllowlistValidator("light.*,switch.fan")
        allowed = validator.get_allowed_list()
        assert allowed == ["light.*", "switch.fan"]
        # Verify it's a copy, not the original
        allowed.append("test")
        assert "test" not in validator.patterns


class TestActionMapping:
    """Tests for action to service mapping (AC #6)."""

    def test_turn_on_mapping(self):
        """AC #6: turn_on maps to {domain}.turn_on."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service("turn_on", "light.living_room")
        assert domain == "light"
        assert service == "turn_on"
        assert data == {}

    def test_turn_off_mapping(self):
        """AC #6: turn_off maps to {domain}.turn_off."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service("turn_off", "switch.fan")
        assert domain == "switch"
        assert service == "turn_off"
        assert data == {}

    def test_toggle_mapping(self):
        """AC #6: toggle maps to {domain}.toggle."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service("toggle", "light.bedroom")
        assert domain == "light"
        assert service == "toggle"
        assert data == {}

    def test_set_brightness_mapping(self):
        """AC #6: set_brightness maps to light.turn_on with brightness."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service(
            "set_brightness", "light.living_room", {"brightness": 200}
        )
        assert domain == "light"
        assert service == "turn_on"
        assert data == {"brightness": 200}

    def test_set_brightness_missing_param(self):
        """AC #6: set_brightness without brightness param raises ValueError."""
        from mcp_server.tools.home_assistant import map_action_to_service

        with pytest.raises(ValueError, match="brightness"):
            map_action_to_service("set_brightness", "light.living_room")

    def test_set_temperature_mapping(self):
        """AC #6: set_temperature maps to climate.set_temperature."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service(
            "set_temperature", "climate.thermostat", {"temperature": 72}
        )
        assert domain == "climate"
        assert service == "set_temperature"
        assert data == {"temperature": 72.0}

    def test_set_temperature_missing_param(self):
        """AC #6: set_temperature without temperature param raises ValueError."""
        from mcp_server.tools.home_assistant import map_action_to_service

        with pytest.raises(ValueError, match="temperature"):
            map_action_to_service("set_temperature", "climate.thermostat")

    def test_set_hvac_mode_mapping(self):
        """AC #6: set_hvac_mode maps to climate.set_hvac_mode."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service(
            "set_hvac_mode", "climate.thermostat", {"hvac_mode": "heat"}
        )
        assert domain == "climate"
        assert service == "set_hvac_mode"
        assert data == {"hvac_mode": "heat"}

    def test_set_hvac_mode_missing_param(self):
        """AC #6: set_hvac_mode without hvac_mode param raises ValueError."""
        from mcp_server.tools.home_assistant import map_action_to_service

        with pytest.raises(ValueError, match="hvac_mode"):
            map_action_to_service("set_hvac_mode", "climate.thermostat")

    def test_set_position_mapping(self):
        """AC #6: set_position maps to cover.set_cover_position."""
        from mcp_server.tools.home_assistant import map_action_to_service

        domain, service, data = map_action_to_service(
            "set_position", "cover.garage", {"position": 50}
        )
        assert domain == "cover"
        assert service == "set_cover_position"
        assert data == {"position": 50}

    def test_set_position_missing_param(self):
        """AC #6: set_position without position param raises ValueError."""
        from mcp_server.tools.home_assistant import map_action_to_service

        with pytest.raises(ValueError, match="position"):
            map_action_to_service("set_position", "cover.garage")

    def test_unknown_action_raises(self):
        """AC #6: Unknown action raises ValueError."""
        from mcp_server.tools.home_assistant import map_action_to_service

        with pytest.raises(ValueError, match="Unknown action"):
            map_action_to_service("unknown_action", "light.living_room")


class TestHomeAssistantControlHandler:
    """Tests for the control handler function (AC #5, #7, #8)."""

    @pytest.fixture
    def mock_entity_state(self):
        """Sample entity state response."""
        return {
            "status": "success",
            "provider": "home_assistant",
            "entities": [{
                "entity_id": "light.living_room",
                "state": "off",
                "attributes": {"brightness": 0},
                "last_changed": "2025-01-10T10:00:00Z"
            }],
            "query_count": 1
        }

    @pytest.fixture
    def mock_service_success(self):
        """Mock successful service call response."""
        return {
            "status": "success",
            "provider": "home_assistant",
            "entity_id": "light.living_room",
            "service_called": "light.turn_on"
        }

    @pytest.mark.asyncio
    async def test_control_allowed_entity_success(self):
        """AC #2: Control allowed entity returns success."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        mock_state_before = {
            "status": "success",
            "entities": [{"entity_id": "light.living_room", "state": "off"}],
        }
        mock_state_after = {
            "status": "success",
            "entities": [{"entity_id": "light.living_room", "state": "on"}],
        }
        mock_service = {"status": "success"}

        call_count = [0]

        async def mock_get_state(entity_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_state_before
            return mock_state_after

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.*"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(side_effect=mock_get_state)
                instance.call_service = AsyncMock(return_value=mock_service)

                result = await home_assistant_control_handler(
                    entity_id="light.living_room",
                    action="turn_on"
                )

        assert result["status"] == "success"
        assert result["entity_id"] == "light.living_room"
        assert result["action"] == "turn_on"
        assert result["previous_state"] == "off"
        assert result["new_state"] == "on"

    @pytest.mark.asyncio
    async def test_control_forbidden_entity(self):
        """AC #5: Control forbidden entity returns FORBIDDEN with allowed list."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.living_room,switch.fan"):
            reset_allowlist_validator()

            result = await home_assistant_control_handler(
                entity_id="light.bedroom",
                action="turn_on"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "FORBIDDEN"
        assert "light.bedroom" in result["error_message"]
        assert "light.living_room" in result["error_message"]
        assert "switch.fan" in result["error_message"]

    @pytest.mark.asyncio
    async def test_control_empty_allowlist_forbidden(self):
        """AC #4: Empty allowlist returns FORBIDDEN with explanation."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", ""):
            reset_allowlist_validator()

            result = await home_assistant_control_handler(
                entity_id="light.living_room",
                action="turn_on"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "FORBIDDEN"
        assert "All control is disabled" in result["error_message"]

    @pytest.mark.asyncio
    async def test_control_returns_previous_and_new_state(self):
        """AC #7: Success response includes previous_state and new_state."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        call_count = [0]

        async def mock_get_state(entity_id):
            call_count[0] += 1
            if call_count[0] == 1:
                return {"status": "success", "entities": [{"state": "off"}]}
            return {"status": "success", "entities": [{"state": "on"}]}

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.*"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(side_effect=mock_get_state)
                instance.call_service = AsyncMock(return_value={"status": "success"})

                result = await home_assistant_control_handler(
                    entity_id="light.living_room",
                    action="turn_on"
                )

        assert result["status"] == "success"
        assert "previous_state" in result
        assert "new_state" in result
        assert result["previous_state"] == "off"
        assert result["new_state"] == "on"

    @pytest.mark.asyncio
    async def test_audit_log_allowed_request(self):
        """AC #8: Allowed request logs with allowed=true."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.*"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(return_value={
                    "status": "success", "entities": [{"state": "on"}]
                })
                instance.call_service = AsyncMock(return_value={"status": "success"})

                with patch("mcp_server.tools.home_assistant.logger") as mock_logger:
                    await home_assistant_control_handler(
                        entity_id="light.living_room",
                        action="turn_on"
                    )

                    # Check that info was called (for successful request)
                    mock_logger.info.assert_called()
                    call_args = mock_logger.info.call_args
                    extra = call_args.kwargs.get("extra", {})

                    assert extra.get("tool_name") == "home_assistant_control"
                    assert extra.get("entity_id") == "light.living_room"
                    assert extra.get("action") == "turn_on"
                    assert extra.get("allowed") is True
                    assert "duration_ms" in extra

    @pytest.mark.asyncio
    async def test_audit_log_denied_request(self):
        """AC #8: Denied request logs with allowed=false."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "switch.fan"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.logger") as mock_logger:
                await home_assistant_control_handler(
                    entity_id="light.bedroom",
                    action="turn_on"
                )

                # Check that warning was called (for denied request)
                mock_logger.warning.assert_called()
                call_args = mock_logger.warning.call_args
                extra = call_args.kwargs.get("extra", {})

                assert extra.get("tool_name") == "home_assistant_control"
                assert extra.get("entity_id") == "light.bedroom"
                assert extra.get("action") == "turn_on"
                assert extra.get("allowed") is False
                assert "duration_ms" in extra


class TestHomeAssistantControlToolSchema:
    """Tests for control tool schema structure."""

    def test_tool_schema_structure(self):
        """Verify tool schema has required fields."""
        from mcp_server.tools.home_assistant import home_assistant_control_tool

        assert "name" in home_assistant_control_tool
        assert home_assistant_control_tool["name"] == "home_assistant_control"
        assert "description" in home_assistant_control_tool
        assert "SECURITY" in home_assistant_control_tool["description"]
        assert "inputSchema" in home_assistant_control_tool
        assert "handler" in home_assistant_control_tool
        assert callable(home_assistant_control_tool["handler"])

    def test_input_schema_properties(self):
        """Verify inputSchema has entity_id, action, parameters."""
        from mcp_server.tools.home_assistant import home_assistant_control_tool

        schema = home_assistant_control_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "entity_id" in schema["properties"]
        assert "action" in schema["properties"]
        assert "parameters" in schema["properties"]

        # action has enum
        assert "enum" in schema["properties"]["action"]
        actions = schema["properties"]["action"]["enum"]
        assert "turn_on" in actions
        assert "turn_off" in actions
        assert "toggle" in actions
        assert "set_brightness" in actions
        assert "set_temperature" in actions
        assert "set_hvac_mode" in actions
        assert "set_position" in actions

    def test_required_fields(self):
        """Verify required fields."""
        from mcp_server.tools.home_assistant import home_assistant_control_tool

        schema = home_assistant_control_tool["inputSchema"]
        assert "required" in schema
        assert "entity_id" in schema["required"]
        assert "action" in schema["required"]
        assert "parameters" not in schema["required"]


class TestHomeAssistantClientControl:
    """Tests for HomeAssistantClient.call_service method."""

    @pytest.mark.asyncio
    async def test_call_service_success(self):
        """Service call success returns expected response."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.call_service(
                "light", "turn_on", "light.living_room", {"brightness": 255}
            )

        assert result["status"] == "success"
        assert result["entity_id"] == "light.living_room"
        assert result["service_called"] == "light.turn_on"

    @pytest.mark.asyncio
    async def test_call_service_unauthorized(self):
        """Service call with 401 returns UNAUTHORIZED."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="invalid-token"
            )
            result = await client.call_service(
                "light", "turn_on", "light.living_room"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_call_service_not_found(self):
        """Service call with 404 returns SERVICE_NOT_FOUND."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client_instance = AsyncMock()
        mock_client_instance.post.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.call_service(
                "invalid", "service", "light.living_room"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "SERVICE_NOT_FOUND"

    def test_get_domain_from_entity(self):
        """Test domain extraction from entity ID."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        assert HomeAssistantClient.get_domain_from_entity("light.living_room") == "light"
        assert HomeAssistantClient.get_domain_from_entity("climate.thermostat") == "climate"
        assert HomeAssistantClient.get_domain_from_entity("cover.garage_door") == "cover"
        assert HomeAssistantClient.get_domain_from_entity("switch.fan") == "switch"
        assert HomeAssistantClient.get_domain_from_entity("invalid") == ""


class TestControlWithParameters:
    """Tests for control actions with parameters."""

    @pytest.mark.asyncio
    async def test_set_brightness_with_params(self):
        """Set brightness passes brightness to service call."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.*"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(return_value={
                    "status": "success", "entities": [{"state": "on"}]
                })
                instance.call_service = AsyncMock(return_value={"status": "success"})

                result = await home_assistant_control_handler(
                    entity_id="light.living_room",
                    action="set_brightness",
                    parameters={"brightness": 128}
                )

                # Verify call_service was called with brightness in data
                instance.call_service.assert_called_once()
                call_args = instance.call_service.call_args
                assert call_args[0][0] == "light"  # domain
                assert call_args[0][1] == "turn_on"  # service
                assert call_args[0][2] == "light.living_room"  # entity_id
                assert call_args[0][3] == {"brightness": 128}  # data

        assert result["status"] == "success"
        assert result["parameters"] == {"brightness": 128}

    @pytest.mark.asyncio
    async def test_set_temperature_with_params(self):
        """Set temperature passes temperature to service call."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "climate.*"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(return_value={
                    "status": "success", "entities": [{"state": "heat"}]
                })
                instance.call_service = AsyncMock(return_value={"status": "success"})

                result = await home_assistant_control_handler(
                    entity_id="climate.thermostat",
                    action="set_temperature",
                    parameters={"temperature": 72}
                )

                # Verify call_service was called with temperature in data
                instance.call_service.assert_called_once()
                call_args = instance.call_service.call_args
                assert call_args[0][0] == "climate"
                assert call_args[0][1] == "set_temperature"
                assert call_args[0][3] == {"temperature": 72.0}

        assert result["status"] == "success"
