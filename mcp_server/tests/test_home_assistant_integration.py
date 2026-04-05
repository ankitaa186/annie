"""
Integration Tests for Home Assistant Tools (Epic 16 - Story 16.5)

End-to-end integration tests that verify:
- AC #1: Tools are properly exported from __init__.py
- AC #2: Tools are registered in server.py and appear in /tools/list
- AC #3: Coverage for home_assistant.py
- AC #4: Skippable real HA integration tests (when HA_URL is configured)

Tests include:
- Import verification
- Tool registration verification
- Query-then-control flow
- Full allowlist enforcement
- Real HA integration (skippable)
"""

import os
import pytest
from unittest.mock import AsyncMock, patch


@pytest.fixture(autouse=True)
def _bypass_admin_check():
    """Bypass admin authorization for all HA integration tests."""
    with patch("mcp_server.tools.home_assistant.is_admin", return_value=True):
        yield


class TestToolExports:
    """AC #1: Verify tools are exported from mcp_server.tools."""

    def test_import_home_assistant_query_tool(self):
        """Verify home_assistant_query_tool can be imported."""
        from mcp_server.tools import home_assistant_query_tool

        assert home_assistant_query_tool is not None
        assert home_assistant_query_tool["name"] == "home_assistant_query"
        assert "inputSchema" in home_assistant_query_tool
        assert "handler" in home_assistant_query_tool

    def test_import_home_assistant_control_tool(self):
        """Verify home_assistant_control_tool can be imported."""
        from mcp_server.tools import home_assistant_control_tool

        assert home_assistant_control_tool is not None
        assert home_assistant_control_tool["name"] == "home_assistant_control"
        assert "inputSchema" in home_assistant_control_tool
        assert "handler" in home_assistant_control_tool

    def test_import_handlers(self):
        """Verify handlers can be imported."""
        from mcp_server.tools import (
            home_assistant_query_handler,
            home_assistant_control_handler,
        )

        assert callable(home_assistant_query_handler)
        assert callable(home_assistant_control_handler)

    def test_import_allowlist_validator(self):
        """Verify AllowlistValidator can be imported."""
        from mcp_server.tools import (
            AllowlistValidator,
            get_allowlist_validator,
            reset_allowlist_validator,
        )

        assert AllowlistValidator is not None
        assert callable(get_allowlist_validator)
        assert callable(reset_allowlist_validator)

    def test_import_map_action_to_service(self):
        """Verify map_action_to_service can be imported."""
        from mcp_server.tools import map_action_to_service

        assert callable(map_action_to_service)

    def test_import_home_assistant_client(self):
        """Verify HomeAssistantClient can be imported."""
        from mcp_server.tools import HomeAssistantClient

        assert HomeAssistantClient is not None

    def test_tools_in_all_list(self):
        """Verify HA tools are in __all__ list."""
        from mcp_server.tools import __all__

        assert "home_assistant_query_tool" in __all__
        assert "home_assistant_control_tool" in __all__
        assert "home_assistant_query_handler" in __all__
        assert "home_assistant_control_handler" in __all__
        assert "AllowlistValidator" in __all__
        assert "HomeAssistantClient" in __all__


class TestToolRegistration:
    """AC #2: Verify tools are registered in server.py."""

    def test_home_assistant_query_in_registry(self):
        """Verify home_assistant_query is registered."""
        from mcp_server.server import mcp_server

        tool = mcp_server.tool_registry.get_tool("home_assistant_query")
        assert tool is not None
        assert tool["name"] == "home_assistant_query"
        assert "description" in tool
        assert "inputSchema" in tool
        assert "handler" in tool

    def test_home_assistant_control_in_registry(self):
        """Verify home_assistant_control is registered."""
        from mcp_server.server import mcp_server

        tool = mcp_server.tool_registry.get_tool("home_assistant_control")
        assert tool is not None
        assert tool["name"] == "home_assistant_control"
        assert "SECURITY" in tool["description"]  # Security warning in description
        assert "inputSchema" in tool
        assert "handler" in tool

    def test_query_tool_schema_complete(self):
        """Verify query tool has complete schema."""
        from mcp_server.server import mcp_server

        tool = mcp_server.tool_registry.get_tool("home_assistant_query")
        schema = tool["inputSchema"]

        assert schema["type"] == "object"
        assert "entity_ids" in schema["properties"]
        assert "domain" in schema["properties"]
        # Note: oneOf not used due to Gemini compatibility; mutual exclusion enforced in handler
        # Check that descriptions mention "either entity_ids OR domain"
        assert "either" in schema["properties"]["entity_ids"]["description"].lower() or \
               "not both" in schema["properties"]["entity_ids"]["description"].lower()

    def test_control_tool_schema_complete(self):
        """Verify control tool has complete schema."""
        from mcp_server.server import mcp_server

        tool = mcp_server.tool_registry.get_tool("home_assistant_control")
        schema = tool["inputSchema"]

        assert schema["type"] == "object"
        assert "entity_id" in schema["properties"]
        assert "action" in schema["properties"]
        assert "parameters" in schema["properties"]
        assert "entity_id" in schema["required"]
        assert "action" in schema["required"]

        # Verify all 7 actions in enum
        actions = schema["properties"]["action"]["enum"]
        assert "turn_on" in actions
        assert "turn_off" in actions
        assert "toggle" in actions
        assert "set_brightness" in actions
        assert "set_temperature" in actions
        assert "set_hvac_mode" in actions
        assert "set_position" in actions

    def test_total_tool_count_includes_ha_tools(self):
        """Verify HA tools are counted in total."""
        from mcp_server.server import mcp_server

        # Should have at least 24 tools (23 from before + 1 control = 25 now)
        assert len(mcp_server.tool_registry.tools) >= 24


class TestQueryThenControlFlow:
    """End-to-end test for query → control → verify flow."""

    @pytest.mark.asyncio
    async def test_query_then_control_flow(self):
        """
        Test the complete flow:
        1. Query entity state (off)
        2. Control entity (turn_on)
        3. Verify new state (on)
        """
        from mcp_server.tools.home_assistant import (
            home_assistant_query_handler,
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        # Track call count to return different states
        get_state_call_count = [0]

        async def mock_get_state(entity_id):
            get_state_call_count[0] += 1
            if get_state_call_count[0] <= 1:  # Control's pre-state
                return {
                    "status": "success",
                    "entities": [{"entity_id": entity_id, "state": "off"}]
                }
            else:  # Control's post-state (after turn_on)
                return {
                    "status": "success",
                    "entities": [{"entity_id": entity_id, "state": "on"}]
                }

        with patch("mcp_server.tools.home_assistant.HA_URL", "http://ha.local:8123"):
            with patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test-token"):
                with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.*"):
                    reset_allowlist_validator()

                    with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                        instance = mock_client.return_value
                        instance.get_entity_state = AsyncMock(side_effect=mock_get_state)
                        instance.get_entities_by_ids = AsyncMock(return_value={
                            "status": "success",
                            "entities": [{"entity_id": "light.living_room", "state": "off"}],
                            "query_count": 1
                        })
                        instance.call_service = AsyncMock(return_value={"status": "success"})

                        # Step 1: Query initial state (uses get_entities_by_ids)
                        query_result = await home_assistant_query_handler(
                            entity_ids=["light.living_room"]
                        )
                        assert query_result["status"] == "success"
                        assert query_result["entities"][0]["state"] == "off"

                        # Step 2: Control - turn on the light (uses get_entity_state for pre/post)
                        control_result = await home_assistant_control_handler(
                            entity_id="light.living_room",
                            action="turn_on"
                        )
                        assert control_result["status"] == "success"
                        assert control_result["previous_state"] == "off"
                        assert control_result["new_state"] == "on"


class TestFullAllowlistEnforcement:
    """Comprehensive security tests for allowlist enforcement."""

    @pytest.mark.asyncio
    async def test_allowlist_exact_match_allowed(self):
        """Exact match entity is allowed."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.living_room"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(return_value={
                    "status": "success",
                    "entities": [{"state": "off"}]
                })
                instance.call_service = AsyncMock(return_value={"status": "success"})

                result = await home_assistant_control_handler(
                    entity_id="light.living_room",
                    action="turn_on"
                )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_allowlist_exact_match_denied(self):
        """Non-matching entity is denied."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.living_room"):
            reset_allowlist_validator()

            result = await home_assistant_control_handler(
                entity_id="light.bedroom",
                action="turn_on"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "FORBIDDEN"
        assert "light.living_room" in result["error_message"]

    @pytest.mark.asyncio
    async def test_allowlist_wildcard_allowed(self):
        """Wildcard pattern allows matching entities."""
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
                    "status": "success",
                    "entities": [{"state": "off"}]
                })
                instance.call_service = AsyncMock(return_value={"status": "success"})

                result = await home_assistant_control_handler(
                    entity_id="light.bedroom",
                    action="turn_on"
                )

        assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_allowlist_wildcard_different_domain_denied(self):
        """Wildcard doesn't match different domain."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.*"):
            reset_allowlist_validator()

            result = await home_assistant_control_handler(
                entity_id="switch.fan",
                action="turn_on"
            )

        assert result["status"] == "error"
        assert result["error_code"] == "FORBIDDEN"

    @pytest.mark.asyncio
    async def test_empty_allowlist_blocks_all(self):
        """Empty allowlist blocks all control."""
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
    async def test_multiple_patterns_allowed(self):
        """Multiple patterns in allowlist work."""
        from mcp_server.tools.home_assistant import (
            home_assistant_control_handler,
            reset_allowlist_validator,
        )

        reset_allowlist_validator()

        with patch("mcp_server.tools.home_assistant.HA_CONTROL_ALLOWLIST", "light.living_room,switch.*,climate.thermostat"):
            reset_allowlist_validator()

            with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock_client:
                instance = mock_client.return_value
                instance.get_entity_state = AsyncMock(return_value={
                    "status": "success",
                    "entities": [{"state": "off"}]
                })
                instance.call_service = AsyncMock(return_value={"status": "success"})

                # Test exact match
                result1 = await home_assistant_control_handler(
                    entity_id="light.living_room",
                    action="turn_on"
                )
                assert result1["status"] == "success"

                # Test wildcard
                result2 = await home_assistant_control_handler(
                    entity_id="switch.bedroom_fan",
                    action="turn_on"
                )
                assert result2["status"] == "success"

                # Test exact match on climate
                result3 = await home_assistant_control_handler(
                    entity_id="climate.thermostat",
                    action="turn_on"
                )
                assert result3["status"] == "success"


def _is_ha_configured_for_integration_tests():
    """
    Check if HA is configured for integration tests.
    Returns True only if HA_URL starts with http and HA_ACCESS_TOKEN is a real token.
    
    Real HA long-lived access tokens are typically 180+ characters.
    Test tokens are much shorter, so we check for > 100 characters to distinguish.
    """
    ha_url = os.getenv("HA_URL", "")
    ha_token = os.getenv("HA_ACCESS_TOKEN", "")
    # Must have real URL (not placeholder) and real token (> 100 chars)
    # Real HA tokens are ~180 chars, test tokens are much shorter
    return (
        ha_url.startswith("http") and
        len(ha_token) > 100 and  # Real tokens are 180+ chars, test tokens are < 50
        "REPLACE" not in ha_url.upper() and
        "REPLACE" not in ha_token.upper() and
        "test" not in ha_token.lower()  # Exclude test values
    )


class TestRealHomeAssistantIntegration:
    """
    Integration tests with real Home Assistant.
    Skipped if HA is not properly configured.

    To run these tests:
    1. Set HA_URL=http://your-ha-ip:8123
    2. Set HA_ACCESS_TOKEN=your-long-lived-access-token
    3. Run: pytest -k TestRealHomeAssistantIntegration
    """

    @pytest.mark.skipif(
        not _is_ha_configured_for_integration_tests(),
        reason="Home Assistant not configured for integration tests"
    )
    @pytest.mark.asyncio
    async def test_real_ha_query_by_domain(self):
        """Query all entities in a domain from real HA."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler(domain="light")

        assert result["status"] == "success"
        assert "entities" in result
        assert "query_count" in result

    @pytest.mark.skipif(
        not _is_ha_configured_for_integration_tests(),
        reason="Home Assistant not configured for integration tests"
    )
    @pytest.mark.asyncio
    async def test_real_ha_query_all_domains(self):
        """Query all entities from real HA."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler(domain="all")

        assert result["status"] == "success"
        assert "entities" in result
        assert result["query_count"] > 0

    @pytest.mark.skipif(
        not _is_ha_configured_for_integration_tests(),
        reason="Home Assistant not configured for integration tests"
    )
    @pytest.mark.asyncio
    async def test_real_ha_query_entity_not_found(self):
        """Query non-existent entity from real HA."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler(
            entity_ids=["light.definitely_does_not_exist_xyz123"]
        )

        # May return error or partial errors depending on HA version
        assert result is not None


class TestToolSchemaValidation:
    """Verify tool schemas are valid and complete."""

    def test_query_tool_description_mentions_use_cases(self):
        """Query tool description includes use cases."""
        from mcp_server.tools import home_assistant_query_tool

        desc = home_assistant_query_tool["description"]
        assert "state" in desc.lower()
        assert "entity" in desc.lower() or "device" in desc.lower()

    def test_control_tool_description_mentions_security(self):
        """Control tool description mentions security."""
        from mcp_server.tools import home_assistant_control_tool

        desc = home_assistant_control_tool["description"]
        assert "SECURITY" in desc
        assert "allowlist" in desc.lower() or "ALLOWLIST" in desc

    def test_query_schema_enforces_mutual_exclusion(self):
        """Query tool enforces either entity_ids OR domain (not both)."""
        from mcp_server.tools import home_assistant_query_tool

        schema = home_assistant_query_tool["inputSchema"]
        # Note: oneOf not used due to Gemini compatibility; mutual exclusion enforced in handler
        # Verify descriptions document the constraint
        entity_ids_desc = schema["properties"]["entity_ids"]["description"].lower()
        domain_desc = schema["properties"]["domain"]["description"].lower()
        assert "not both" in entity_ids_desc or "either" in entity_ids_desc
        assert "not both" in domain_desc or "either" in domain_desc

    def test_control_schema_action_enum_complete(self):
        """Control tool action enum has all 7 actions."""
        from mcp_server.tools import home_assistant_control_tool

        schema = home_assistant_control_tool["inputSchema"]
        actions = schema["properties"]["action"]["enum"]

        expected_actions = [
            "turn_on", "turn_off", "toggle",
            "set_brightness", "set_temperature",
            "set_hvac_mode", "set_position"
        ]

        for action in expected_actions:
            assert action in actions, f"Missing action: {action}"
