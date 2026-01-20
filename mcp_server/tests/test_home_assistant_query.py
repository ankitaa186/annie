"""
Tests for Home Assistant Query Tool (Epic 16 - Story 16.1)

Tests cover:
- AC #1: Query specific entities by ID
- AC #2: Query all entities by domain
- AC #3: Handle entity not found (404)
- AC #4: Handle invalid token (401)
- AC #5: Request timeout handling
- AC #6: Structured logging
- AC #7: Handle missing configuration
- AC #8: Unit tests with mocked HA responses
"""

import os
from unittest.mock import AsyncMock, patch, MagicMock
import pytest
import httpx


class TestHomeAssistantClient:
    """Tests for HomeAssistantClient class."""

    @pytest.fixture
    def mock_entity_response(self):
        """Sample HA entity state response."""
        return {
            "entity_id": "light.living_room",
            "state": "on",
            "attributes": {
                "brightness": 255,
                "friendly_name": "Living Room Light",
                "color_mode": "brightness"
            },
            "last_changed": "2025-01-10T10:30:00.000000+00:00",
            "last_updated": "2025-01-10T10:30:00.000000+00:00"
        }

    @pytest.fixture
    def mock_all_states_response(self):
        """Sample HA all states response."""
        return [
            {
                "entity_id": "light.living_room",
                "state": "on",
                "attributes": {"brightness": 255, "friendly_name": "Living Room"},
                "last_changed": "2025-01-10T10:30:00Z"
            },
            {
                "entity_id": "light.bedroom",
                "state": "off",
                "attributes": {"friendly_name": "Bedroom Light"},
                "last_changed": "2025-01-10T09:00:00Z"
            },
            {
                "entity_id": "sensor.temperature",
                "state": "72.5",
                "attributes": {"unit_of_measurement": "°F", "friendly_name": "Temperature"},
                "last_changed": "2025-01-10T10:35:00Z"
            },
            {
                "entity_id": "switch.fan",
                "state": "off",
                "attributes": {"friendly_name": "Fan"},
                "last_changed": "2025-01-10T08:00:00Z"
            }
        ]

    @pytest.mark.asyncio
    async def test_query_single_entity_success(self, mock_entity_response):
        """AC #1: Query single entity by ID returns complete data."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_entity_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entity_state("light.living_room")

        assert result["status"] == "success"
        assert result["provider"] == "home_assistant"
        assert result["query_count"] == 1
        assert len(result["entities"]) == 1

        entity = result["entities"][0]
        assert entity["entity_id"] == "light.living_room"
        assert entity["state"] == "on"
        assert entity["attributes"]["brightness"] == 255
        assert "last_changed" in entity

    @pytest.mark.asyncio
    async def test_query_multiple_entities_success(self, mock_entity_response):
        """AC #1: Query multiple entities returns all with complete data."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        responses = [
            {"entity_id": "light.living_room", "state": "on", "attributes": {}, "last_changed": "2025-01-10T10:30:00Z"},
            {"entity_id": "sensor.temperature", "state": "72", "attributes": {"unit": "F"}, "last_changed": "2025-01-10T10:35:00Z"}
        ]

        call_count = [0]  # Use list to allow modification in nested function

        async def mock_get(url, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = responses[call_count[0]]
            mock_resp.raise_for_status = MagicMock()
            call_count[0] += 1
            return mock_resp

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = mock_get

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_ids(["light.living_room", "sensor.temperature"])

        assert result["status"] == "success"
        assert result["query_count"] == 2
        assert len(result["entities"]) == 2
        assert result["entities"][0]["entity_id"] == "light.living_room"
        assert result["entities"][1]["entity_id"] == "sensor.temperature"

    @pytest.mark.asyncio
    async def test_query_by_domain_light(self, mock_all_states_response):
        """AC #2: Query by domain returns all entities in that domain."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_all_states_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_domain("light")

        assert result["status"] == "success"
        assert result["domain"] == "light"
        assert result["query_count"] == 2  # Only light.* entities
        assert all(e["entity_id"].startswith("light.") for e in result["entities"])

    @pytest.mark.asyncio
    async def test_query_by_domain_all(self, mock_all_states_response):
        """AC #2: Query with domain='all' returns all entities."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_all_states_response
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_domain("all")

        assert result["status"] == "success"
        assert result["domain"] == "all"
        assert result["query_count"] == 4  # All entities

    @pytest.mark.asyncio
    async def test_query_entity_not_found(self):
        """AC #3: Handle 404 not found with graceful error."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entity_state("light.nonexistent")

        assert result["status"] == "error"
        assert result["error_code"] == "NOT_FOUND"
        assert "not found" in result["error_message"].lower()
        assert result["entity_id"] == "light.nonexistent"

    @pytest.mark.asyncio
    async def test_query_unauthorized(self):
        """AC #4: Handle 401 unauthorized with clear error message."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 401

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="invalid-token"
            )
            result = await client.get_entity_state("light.living_room")

        assert result["status"] == "error"
        assert result["error_code"] == "UNAUTHORIZED"
        assert "token" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_query_timeout(self):
        """AC #5: Handle timeout with proper error code."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = httpx.TimeoutException("Request timed out")

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token",
                timeout=5
            )
            result = await client.get_entity_state("light.living_room")

        assert result["status"] == "error"
        assert result["error_code"] == "TIMEOUT"
        assert "timed out" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_query_network_error(self):
        """AC #8 additional: Handle network/connection errors."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = httpx.ConnectError("Connection refused")

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entity_state("light.living_room")

        assert result["status"] == "error"
        assert result["error_code"] == "NETWORK_ERROR"
        assert "connect" in result["error_message"].lower()


class TestHomeAssistantConfigErrors:
    """Tests for configuration error handling (AC #7)."""

    @pytest.mark.asyncio
    async def test_config_error_missing_url(self):
        """AC #7: Missing HA_URL returns CONFIG_ERROR."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        # Patch module-level config to simulate missing URL
        with patch("mcp_server.tools.home_assistant.HA_URL", ""):
            client = HomeAssistantClient(
                base_url="",  # Empty URL
                access_token="valid-token"
            )
            result = await client.get_entity_state("light.living_room")

        assert result["status"] == "error"
        assert result["error_code"] == "CONFIG_ERROR"
        assert "HA_URL" in result["error_message"]

    @pytest.mark.asyncio
    async def test_config_error_missing_token(self):
        """AC #7: Missing HA_ACCESS_TOKEN returns CONFIG_ERROR."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        # Patch module-level config to simulate missing token
        with patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", ""):
            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token=""  # Empty token
            )
            result = await client.get_entity_state("light.living_room")

        assert result["status"] == "error"
        assert result["error_code"] == "CONFIG_ERROR"
        assert "HA_ACCESS_TOKEN" in result["error_message"]

    @pytest.mark.asyncio
    async def test_config_error_both_missing(self):
        """AC #7: Both missing returns CONFIG_ERROR for URL first."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        # Patch module-level config to simulate both missing
        with patch("mcp_server.tools.home_assistant.HA_URL", ""):
            with patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", ""):
                client = HomeAssistantClient(
                    base_url="",
                    access_token=""
                )
                result = await client.get_entity_state("light.living_room")

        assert result["status"] == "error"
        assert result["error_code"] == "CONFIG_ERROR"
        # URL is checked first
        assert "HA_URL" in result["error_message"]


class TestHomeAssistantQueryToolHandler:
    """Tests for the MCP tool handler function."""

    @pytest.fixture
    def mock_client_success(self):
        """Mock HomeAssistantClient with successful response."""
        with patch("mcp_server.tools.home_assistant.HomeAssistantClient") as mock:
            instance = mock.return_value
            instance.get_entities_by_ids = AsyncMock(return_value={
                "status": "success",
                "provider": "home_assistant",
                "entities": [
                    {"entity_id": "light.test", "state": "on", "attributes": {}, "last_changed": "2025-01-10T10:00:00Z"}
                ],
                "query_count": 1
            })
            instance.get_entities_by_domain = AsyncMock(return_value={
                "status": "success",
                "provider": "home_assistant",
                "entities": [
                    {"entity_id": "light.a", "state": "on", "attributes": {}, "last_changed": "2025-01-10T10:00:00Z"},
                    {"entity_id": "light.b", "state": "off", "attributes": {}, "last_changed": "2025-01-10T09:00:00Z"}
                ],
                "query_count": 2,
                "domain": "light"
            })
            yield mock

    @pytest.mark.asyncio
    async def test_handler_with_entity_ids(self, mock_client_success):
        """Tool handler calls get_entities_by_ids when entity_ids provided."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler(entity_ids=["light.test"])

        assert result["status"] == "success"
        mock_client_success.return_value.get_entities_by_ids.assert_called_once_with(["light.test"])

    @pytest.mark.asyncio
    async def test_handler_with_domain(self, mock_client_success):
        """Tool handler calls get_entities_by_domain when domain provided."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler(domain="light")

        assert result["status"] == "success"
        assert result["query_count"] == 2
        mock_client_success.return_value.get_entities_by_domain.assert_called_once_with("light")

    @pytest.mark.asyncio
    async def test_handler_invalid_both_params(self):
        """Tool handler returns error when both entity_ids and domain provided."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler(
            entity_ids=["light.test"],
            domain="light"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"
        assert "not both" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_handler_invalid_no_params(self):
        """Tool handler returns error when neither parameter provided."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        result = await home_assistant_query_handler()

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_handler_logs_operation(self, mock_client_success):
        """AC #6: Tool handler logs with required fields."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        with patch("mcp_server.tools.home_assistant.logger") as mock_logger:
            await home_assistant_query_handler(entity_ids=["light.test"])

            mock_logger.info.assert_called()
            call_args = mock_logger.info.call_args
            extra = call_args.kwargs.get("extra", {})

            assert extra.get("tool_name") == "home_assistant_query"
            assert "status" in extra
            assert "entity_count" in extra
            assert "duration_ms" in extra


class TestHomeAssistantQueryToolSchema:
    """Tests for tool schema structure."""

    def test_tool_schema_structure(self):
        """Verify tool schema has required fields."""
        from mcp_server.tools.home_assistant import home_assistant_query_tool

        assert "name" in home_assistant_query_tool
        assert home_assistant_query_tool["name"] == "home_assistant_query"
        assert "description" in home_assistant_query_tool
        assert "inputSchema" in home_assistant_query_tool
        assert "handler" in home_assistant_query_tool
        assert callable(home_assistant_query_tool["handler"])

    def test_input_schema_properties(self):
        """Verify inputSchema has entity_ids and domain properties."""
        from mcp_server.tools.home_assistant import home_assistant_query_tool

        schema = home_assistant_query_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "entity_ids" in schema["properties"]
        assert "domain" in schema["properties"]

        # entity_ids is array of strings
        assert schema["properties"]["entity_ids"]["type"] == "array"
        assert schema["properties"]["entity_ids"]["items"]["type"] == "string"

        # domain is string with enum
        assert schema["properties"]["domain"]["type"] == "string"
        assert "enum" in schema["properties"]["domain"]

    def test_input_schema_mutual_exclusion_documented(self):
        """Verify mutual exclusion of entity_ids/domain is documented in descriptions."""
        from mcp_server.tools.home_assistant import home_assistant_query_tool

        schema = home_assistant_query_tool["inputSchema"]
        # Note: oneOf not used due to Gemini compatibility; mutual exclusion enforced in handler
        # Verify descriptions document the constraint
        entity_ids_desc = schema["properties"]["entity_ids"]["description"].lower()
        domain_desc = schema["properties"]["domain"]["description"].lower()

        # Both descriptions should mention the mutual exclusion
        assert "not both" in entity_ids_desc or "either" in entity_ids_desc
        assert "not both" in domain_desc or "either" in domain_desc


class TestHomeAssistantPartialErrors:
    """Tests for partial error handling with multiple entities."""

    @pytest.mark.asyncio
    async def test_partial_errors_some_entities_fail(self):
        """When some entities fail, return success with partial_errors."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        call_count = [0]

        async def mock_get(url, **kwargs):
            mock_resp = MagicMock()

            if call_count[0] == 0:
                # First entity succeeds
                mock_resp.status_code = 200
                mock_resp.json.return_value = {
                    "entity_id": "light.good",
                    "state": "on",
                    "attributes": {},
                    "last_changed": "2025-01-10T10:00:00Z"
                }
                mock_resp.raise_for_status = MagicMock()
            else:
                # Second entity fails (not found)
                mock_resp.status_code = 404

            call_count[0] += 1
            return mock_resp

        mock_client_instance = AsyncMock()
        mock_client_instance.get.side_effect = mock_get

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_ids(["light.good", "light.bad"])

        assert result["status"] == "success"
        assert result["query_count"] == 1
        assert "partial_errors" in result
        assert len(result["partial_errors"]) == 1
        assert result["partial_errors"][0]["entity_id"] == "light.bad"
        assert result["partial_errors"][0]["error_code"] == "NOT_FOUND"

    @pytest.mark.asyncio
    async def test_all_entities_fail(self):
        """When all entities fail, return error with ALL_FAILED code."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 404

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_ids(["light.bad1", "light.bad2"])

        assert result["status"] == "error"
        assert result["error_code"] == "ALL_FAILED"
        assert "errors" in result
        assert len(result["errors"]) == 2

    @pytest.mark.asyncio
    async def test_empty_entity_ids_list(self):
        """Empty entity_ids list returns INVALID_INPUT error."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        client = HomeAssistantClient(
            base_url="http://ha.local:8123",
            access_token="valid-token"
        )
        result = await client.get_entities_by_ids([])

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"


class TestHomeAssistantDomainQueries:
    """Additional tests for domain query variations."""

    @pytest.fixture
    def mock_states(self):
        """Extended mock states for domain filtering."""
        return [
            {"entity_id": "light.a", "state": "on", "attributes": {}, "last_changed": ""},
            {"entity_id": "light.b", "state": "off", "attributes": {}, "last_changed": ""},
            {"entity_id": "switch.c", "state": "on", "attributes": {}, "last_changed": ""},
            {"entity_id": "sensor.d", "state": "72", "attributes": {}, "last_changed": ""},
            {"entity_id": "climate.e", "state": "heat", "attributes": {}, "last_changed": ""},
            {"entity_id": "binary_sensor.f", "state": "on", "attributes": {}, "last_changed": ""},
        ]

    @pytest.mark.asyncio
    async def test_query_domain_sensor(self, mock_states):
        """Query sensor domain returns only sensor entities."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_domain("sensor")

        assert result["status"] == "success"
        assert result["query_count"] == 1
        assert result["entities"][0]["entity_id"] == "sensor.d"

    @pytest.mark.asyncio
    async def test_query_domain_binary_sensor(self, mock_states):
        """Query binary_sensor domain (with underscore)."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_domain("binary_sensor")

        assert result["status"] == "success"
        assert result["query_count"] == 1
        assert result["entities"][0]["entity_id"] == "binary_sensor.f"

    @pytest.mark.asyncio
    async def test_query_domain_empty_result(self, mock_states):
        """Query domain with no matching entities returns empty list."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_domain("cover")  # No cover entities in mock

        assert result["status"] == "success"
        assert result["query_count"] == 0
        assert result["entities"] == []

    @pytest.mark.asyncio
    async def test_query_domain_case_insensitive(self, mock_states):
        """Domain matching is case-insensitive."""
        from mcp_server.tools.home_assistant import HomeAssistantClient

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance

            client = HomeAssistantClient(
                base_url="http://ha.local:8123",
                access_token="valid-token"
            )
            result = await client.get_entities_by_domain("LIGHT")

        assert result["status"] == "success"
        assert result["query_count"] == 2


class TestExcludeDisabledEntities:
    """Tests for exclude_disabled parameter filtering."""

    @pytest.fixture
    def mock_states_with_disabled(self):
        """Mock states including disabled/orphaned entities."""
        return [
            {
                "entity_id": "light.active",
                "state": "on",
                "attributes": {"friendly_name": "Active Light"},
                "last_changed": "2025-01-10T10:00:00Z"
            },
            {
                "entity_id": "light.disabled_orphan",
                "state": "unavailable",
                "attributes": {"restored": True, "friendly_name": "Orphaned Light"},
                "last_changed": "2025-01-10T10:00:00Z"
            },
            {
                "entity_id": "light.another_active",
                "state": "off",
                "attributes": {"friendly_name": "Another Active"},
                "last_changed": "2025-01-10T10:00:00Z"
            },
            {
                "entity_id": "light.also_disabled",
                "state": "unavailable",
                "attributes": {"restored": True, "friendly_name": "Also Disabled"},
                "last_changed": "2025-01-10T10:00:00Z"
            },
        ]

    @pytest.mark.asyncio
    async def test_exclude_disabled_default_true(self, mock_states_with_disabled):
        """By default, disabled entities are filtered out."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states_with_disabled
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.HA_URL", "http://ha.local:8123"):
            with patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test-token"):
                with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
                    mock_client.return_value.__aenter__.return_value = mock_client_instance

                    result = await home_assistant_query_handler(domain="light")

        assert result["status"] == "success"
        assert result["query_count"] == 2  # Only active entities
        assert result["filtered_disabled"] == 2  # 2 disabled filtered out

        entity_ids = [e["entity_id"] for e in result["entities"]]
        assert "light.active" in entity_ids
        assert "light.another_active" in entity_ids
        assert "light.disabled_orphan" not in entity_ids
        assert "light.also_disabled" not in entity_ids

    @pytest.mark.asyncio
    async def test_exclude_disabled_false_includes_all(self, mock_states_with_disabled):
        """When exclude_disabled=False, all entities are returned."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states_with_disabled
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.HA_URL", "http://ha.local:8123"):
            with patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test-token"):
                with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
                    mock_client.return_value.__aenter__.return_value = mock_client_instance

                    result = await home_assistant_query_handler(domain="light", exclude_disabled=False)

        assert result["status"] == "success"
        assert result["query_count"] == 4  # All entities
        assert "filtered_disabled" not in result  # No filtering happened

        entity_ids = [e["entity_id"] for e in result["entities"]]
        assert "light.disabled_orphan" in entity_ids
        assert "light.also_disabled" in entity_ids

    @pytest.mark.asyncio
    async def test_exclude_disabled_no_disabled_entities(self):
        """When no disabled entities, no filtering metadata added."""
        from mcp_server.tools.home_assistant import home_assistant_query_handler

        mock_states = [
            {"entity_id": "light.a", "state": "on", "attributes": {}, "last_changed": ""},
            {"entity_id": "light.b", "state": "off", "attributes": {}, "last_changed": ""},
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_states
        mock_response.raise_for_status = MagicMock()

        mock_client_instance = AsyncMock()
        mock_client_instance.get.return_value = mock_response

        with patch("mcp_server.tools.home_assistant.HA_URL", "http://ha.local:8123"):
            with patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test-token"):
                with patch("mcp_server.tools.home_assistant.httpx.AsyncClient") as mock_client:
                    mock_client.return_value.__aenter__.return_value = mock_client_instance

                    result = await home_assistant_query_handler(domain="light")

        assert result["status"] == "success"
        assert result["query_count"] == 2
        assert "filtered_disabled" not in result  # No disabled to filter

    @pytest.mark.asyncio
    async def test_is_disabled_entity_function(self):
        """Test _is_disabled_entity helper function."""
        from mcp_server.tools.home_assistant import _is_disabled_entity

        # Entity with restored=True is disabled
        disabled = {"attributes": {"restored": True}}
        assert _is_disabled_entity(disabled) is True

        # Entity with restored=False is not disabled
        not_disabled = {"attributes": {"restored": False}}
        assert _is_disabled_entity(not_disabled) is False

        # Entity without restored attribute is not disabled
        normal = {"attributes": {"brightness": 255}}
        assert _is_disabled_entity(normal) is False

        # Entity without attributes is not disabled
        empty = {}
        assert _is_disabled_entity(empty) is False

    def test_schema_includes_exclude_disabled(self):
        """Tool schema includes exclude_disabled parameter."""
        from mcp_server.tools.home_assistant import home_assistant_query_tool

        schema = home_assistant_query_tool["inputSchema"]
        assert "exclude_disabled" in schema["properties"]
        assert schema["properties"]["exclude_disabled"]["type"] == "boolean"
        assert schema["properties"]["exclude_disabled"]["default"] is True
