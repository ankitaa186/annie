"""
Tests for Voice Message Tool (Epic 16 - Story 16.6)

Tests cover:
- AC #4: Voice type support (8 types with SSML wrapping)
- AC #5: 60-second cooldown enforcement
- AC #6: Cooldown NOT consumed on errors
- AC #7: Device validation via HA query
- AC #8: Fail-all on invalid device
- AC #9: Clear error codes
- AC #12-14: Unit tests for cooldown, validation, SSML
"""

import os
import time
from unittest.mock import AsyncMock, patch, MagicMock
import pytest

# Import the module under test
from mcp_server.tools.home_assistant import (
    VOICE_TYPES,
    VOICE_MESSAGE_COOLDOWN_SECONDS,
    reset_voice_message_cooldown,
    _check_voice_cooldown,
    build_ssml_message,
    get_voice_delivery_method,
    send_voice_message_to_smart_home_handler,
    send_voice_message_to_smart_home_tool,
)


class TestVoiceTypes:
    """Tests for VOICE_TYPES configuration."""

    def test_voice_types_has_8_entries(self):
        """Verify VOICE_TYPES contains all 8 voice types."""
        expected_types = ["say", "announce", "whisper", "excited", "disappointed", "conversational", "news", "fun"]
        assert len(VOICE_TYPES) == 8
        for voice_type in expected_types:
            assert voice_type in VOICE_TYPES

    def test_voice_type_say_no_ssml(self):
        """AC #4: say voice type has no SSML wrapping."""
        assert VOICE_TYPES["say"]["method"] == "tts"
        assert VOICE_TYPES["say"]["ssml"] is None

    def test_voice_type_announce_no_ssml(self):
        """AC #4: announce voice type has no SSML wrapping."""
        assert VOICE_TYPES["announce"]["method"] == "announce"
        assert VOICE_TYPES["announce"]["ssml"] is None

    def test_voice_type_whisper_ssml(self):
        """AC #4: whisper has amazon:effect SSML tag."""
        assert VOICE_TYPES["whisper"]["method"] == "tts"
        assert 'amazon:effect name="whispered"' in VOICE_TYPES["whisper"]["ssml"]

    def test_voice_type_excited_ssml(self):
        """AC #4: excited has amazon:emotion SSML tag."""
        assert VOICE_TYPES["excited"]["method"] == "tts"
        assert 'amazon:emotion name="excited"' in VOICE_TYPES["excited"]["ssml"]

    def test_voice_type_disappointed_ssml(self):
        """AC #4: disappointed has amazon:emotion SSML tag."""
        assert VOICE_TYPES["disappointed"]["method"] == "tts"
        assert 'amazon:emotion name="disappointed"' in VOICE_TYPES["disappointed"]["ssml"]

    def test_voice_type_conversational_ssml(self):
        """AC #4: conversational has amazon:domain SSML tag."""
        assert VOICE_TYPES["conversational"]["method"] == "tts"
        assert 'amazon:domain name="conversational"' in VOICE_TYPES["conversational"]["ssml"]

    def test_voice_type_news_ssml(self):
        """AC #4: news has amazon:domain SSML tag."""
        assert VOICE_TYPES["news"]["method"] == "tts"
        assert 'amazon:domain name="news"' in VOICE_TYPES["news"]["ssml"]

    def test_voice_type_fun_ssml(self):
        """AC #4: fun has amazon:domain SSML tag."""
        assert VOICE_TYPES["fun"]["method"] == "tts"
        assert 'amazon:domain name="fun"' in VOICE_TYPES["fun"]["ssml"]


class TestBuildSsmlMessage:
    """Tests for build_ssml_message function."""

    def test_build_ssml_say_no_wrapping(self):
        """AC #4: say returns plain message."""
        result = build_ssml_message("Hello world", "say")
        assert result == "Hello world"

    def test_build_ssml_announce_no_wrapping(self):
        """AC #4: announce returns plain message."""
        result = build_ssml_message("Hello world", "announce")
        assert result == "Hello world"

    def test_build_ssml_whisper(self):
        """AC #4: whisper wraps in amazon:effect tag."""
        result = build_ssml_message("Hello", "whisper")
        assert result == '<amazon:effect name="whispered">Hello</amazon:effect>'

    def test_build_ssml_excited(self):
        """AC #4: excited wraps in amazon:emotion tag."""
        result = build_ssml_message("Great news!", "excited")
        assert result == '<amazon:emotion name="excited" intensity="medium">Great news!</amazon:emotion>'

    def test_build_ssml_disappointed(self):
        """AC #4: disappointed wraps in amazon:emotion tag."""
        result = build_ssml_message("Sorry about that", "disappointed")
        assert result == '<amazon:emotion name="disappointed" intensity="medium">Sorry about that</amazon:emotion>'

    def test_build_ssml_conversational(self):
        """AC #4: conversational wraps in amazon:domain tag."""
        result = build_ssml_message("Hey there!", "conversational")
        assert result == '<amazon:domain name="conversational">Hey there!</amazon:domain>'

    def test_build_ssml_news(self):
        """AC #4: news wraps in amazon:domain tag."""
        result = build_ssml_message("Breaking news", "news")
        assert result == '<amazon:domain name="news">Breaking news</amazon:domain>'

    def test_build_ssml_fun(self):
        """AC #4: fun wraps in amazon:domain tag."""
        result = build_ssml_message("Yay!", "fun")
        assert result == '<amazon:domain name="fun">Yay!</amazon:domain>'

    def test_build_ssml_unknown_type_returns_plain(self):
        """Unknown voice type returns plain message."""
        result = build_ssml_message("Hello", "unknown_type")
        assert result == "Hello"


class TestGetVoiceDeliveryMethod:
    """Tests for get_voice_delivery_method function."""

    def test_say_returns_tts(self):
        """say voice type uses tts method."""
        assert get_voice_delivery_method("say") == "tts"

    def test_announce_returns_announce(self):
        """announce voice type uses announce method."""
        assert get_voice_delivery_method("announce") == "announce"

    def test_whisper_returns_tts(self):
        """whisper voice type uses tts method."""
        assert get_voice_delivery_method("whisper") == "tts"

    def test_excited_returns_tts(self):
        """excited voice type uses tts method."""
        assert get_voice_delivery_method("excited") == "tts"

    def test_unknown_returns_tts_default(self):
        """Unknown voice type defaults to tts."""
        assert get_voice_delivery_method("unknown") == "tts"


class TestCooldownMechanism:
    """Tests for cooldown mechanism (AC #5, #6)."""

    def setup_method(self):
        """Reset cooldown before each test."""
        reset_voice_message_cooldown()

    def test_cooldown_constant_is_60_seconds(self):
        """Verify cooldown is 60 seconds."""
        assert VOICE_MESSAGE_COOLDOWN_SECONDS == 60

    def test_no_cooldown_initially(self):
        """AC #5: No cooldown when never sent."""
        result = _check_voice_cooldown()
        assert result is None

    def test_cooldown_check_after_reset(self):
        """Reset clears cooldown state."""
        reset_voice_message_cooldown()
        result = _check_voice_cooldown()
        assert result is None

    @patch("mcp_server.tools.home_assistant._last_voice_message_time", time.time())
    def test_cooldown_blocks_rapid_sends(self):
        """AC #5: Cooldown blocks sends within 60s."""
        # Patch the module-level variable
        import mcp_server.tools.home_assistant as ha_module
        ha_module._last_voice_message_time = time.time()

        result = _check_voice_cooldown()

        assert result is not None
        assert result["status"] == "error"
        assert result["error_code"] == "COOLDOWN"
        assert "seconds_remaining" in result
        assert result["seconds_remaining"] > 0
        assert result["seconds_remaining"] <= 60

    @patch("mcp_server.tools.home_assistant._last_voice_message_time", time.time() - 65)
    def test_cooldown_allows_after_60s(self):
        """AC #5: Cooldown allows sends after 60s."""
        import mcp_server.tools.home_assistant as ha_module
        ha_module._last_voice_message_time = time.time() - 65  # 65 seconds ago

        result = _check_voice_cooldown()

        assert result is None  # No cooldown error


class TestDeviceValidation:
    """Tests for device validation (AC #7, #8)."""

    @pytest.fixture
    def mock_ha_query_success(self):
        """Mock successful HA query response."""
        return {
            "status": "success",
            "provider": "home_assistant",
            "entities": [
                {"entity_id": "media_player.kitchen_echo", "state": "idle"},
                {"entity_id": "media_player.bedroom_echo", "state": "playing"},
                {"entity_id": "media_player.living_room", "state": "idle"},
            ],
            "query_count": 3
        }

    @pytest.fixture
    def mock_ha_config(self):
        """Mock HA configuration."""
        return {
            "HA_URL": "http://localhost:8123",
            "HA_ACCESS_TOKEN": "test_token"
        }

    @pytest.mark.asyncio
    async def test_valid_devices_pass(self, mock_ha_query_success, mock_ha_config):
        """AC #7: Valid devices pass validation."""
        reset_voice_message_cooldown()

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query, \
             patch("mcp_server.tools.home_assistant.HA_URL", mock_ha_config["HA_URL"]), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", mock_ha_config["HA_ACCESS_TOKEN"]), \
             patch("httpx.AsyncClient") as mock_client_class:

            mock_query.return_value = mock_ha_query_success

            # Mock successful HTTP response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.kitchen_echo"],
                voice_type="say"
            )

            assert result["status"] == "success"
            mock_query.assert_called_once_with(domain="media_player")

    @pytest.mark.asyncio
    async def test_invalid_device_returns_valid_list(self, mock_ha_query_success):
        """AC #8: Invalid device returns error with valid_devices list."""
        reset_voice_message_cooldown()

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_ha_query_success

            result = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.fake_device"],
                voice_type="say"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "INVALID_DEVICE"
            assert "invalid_devices" in result
            assert "media_player.fake_device" in result["invalid_devices"]
            assert "valid_devices" in result
            assert "media_player.kitchen_echo" in result["valid_devices"]

    @pytest.mark.asyncio
    async def test_mixed_devices_fail_all(self, mock_ha_query_success):
        """AC #8: Mix of valid and invalid devices fails entire request."""
        reset_voice_message_cooldown()

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_ha_query_success

            result = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.kitchen_echo", "media_player.fake_device"],
                voice_type="say"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "INVALID_DEVICE"
            assert "media_player.fake_device" in result["invalid_devices"]


class TestCooldownNotConsumedOnError:
    """Tests for AC #6: Cooldown NOT consumed on errors."""

    def setup_method(self):
        """Reset cooldown before each test."""
        reset_voice_message_cooldown()

    @pytest.mark.asyncio
    async def test_cooldown_not_consumed_on_invalid_device(self):
        """AC #6: Invalid device error doesn't consume cooldown."""
        mock_ha_query = {
            "status": "success",
            "entities": [{"entity_id": "media_player.kitchen_echo", "state": "idle"}],
            "query_count": 1
        }

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query, \
             patch("mcp_server.tools.home_assistant.HA_URL", "http://localhost:8123"), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test_token"), \
             patch("httpx.AsyncClient") as mock_client_class:

            mock_query.return_value = mock_ha_query

            # Mock successful HTTP response for the second (valid) call
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            # First call: invalid device (should NOT consume cooldown)
            result1 = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.fake_device"],
                voice_type="say"
            )
            assert result1["status"] == "error"
            assert result1["error_code"] == "INVALID_DEVICE"

            # Second call: valid device (should succeed, not blocked by cooldown)
            result2 = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.kitchen_echo"],
                voice_type="say"
            )
            assert result2["status"] == "success"

    @pytest.mark.asyncio
    async def test_cooldown_not_consumed_on_empty_message(self):
        """AC #6: Empty message error doesn't consume cooldown."""
        with patch("mcp_server.tools.home_assistant.HA_URL", "http://localhost:8123"), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test_token"):

            # First call: empty message
            result1 = await send_voice_message_to_smart_home_handler(
                message="",
                devices=["media_player.kitchen_echo"],
                voice_type="say"
            )
            assert result1["status"] == "error"
            assert result1["error_code"] == "INVALID_INPUT"

            # Verify no cooldown was set
            cooldown_check = _check_voice_cooldown()
            assert cooldown_check is None


class TestErrorCodes:
    """Tests for AC #9: Clear error codes."""

    def setup_method(self):
        """Reset cooldown before each test."""
        reset_voice_message_cooldown()

    @pytest.mark.asyncio
    async def test_error_code_cooldown(self):
        """AC #9: COOLDOWN error code."""
        import mcp_server.tools.home_assistant as ha_module
        ha_module._last_voice_message_time = time.time()

        result = await send_voice_message_to_smart_home_handler(
            message="Hello",
            devices=["media_player.kitchen_echo"],
            voice_type="say"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "COOLDOWN"

    @pytest.mark.asyncio
    async def test_error_code_invalid_device(self):
        """AC #9: INVALID_DEVICE error code."""
        reset_voice_message_cooldown()

        mock_ha_query = {
            "status": "success",
            "entities": [{"entity_id": "media_player.kitchen_echo", "state": "idle"}],
            "query_count": 1
        }

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query:
            mock_query.return_value = mock_ha_query

            result = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.fake_device"],
                voice_type="say"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "INVALID_DEVICE"

    @pytest.mark.asyncio
    async def test_error_code_invalid_input_empty_message(self):
        """AC #9: INVALID_INPUT error code for empty message."""
        result = await send_voice_message_to_smart_home_handler(
            message="",
            devices=["media_player.kitchen_echo"],
            voice_type="say"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_error_code_invalid_input_empty_devices(self):
        """AC #9: INVALID_INPUT error code for empty devices."""
        result = await send_voice_message_to_smart_home_handler(
            message="Hello",
            devices=[],
            voice_type="say"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_error_code_invalid_voice_type(self):
        """AC #9: INVALID_INPUT error code for invalid voice type."""
        result = await send_voice_message_to_smart_home_handler(
            message="Hello",
            devices=["media_player.kitchen_echo"],
            voice_type="invalid_type"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "INVALID_INPUT"

    @pytest.mark.asyncio
    async def test_error_code_config_error(self):
        """AC #9: CONFIG_ERROR when HA not configured."""
        reset_voice_message_cooldown()

        mock_ha_query = {
            "status": "success",
            "entities": [{"entity_id": "media_player.kitchen_echo", "state": "idle"}],
            "query_count": 1
        }

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query, \
             patch("mcp_server.tools.home_assistant.HA_URL", ""), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", ""):

            mock_query.return_value = mock_ha_query

            result = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.kitchen_echo"],
                voice_type="say"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "CONFIG_ERROR"


class TestToolSchema:
    """Tests for tool schema definition (AC #1, #10)."""

    def test_tool_name(self):
        """AC #1: Tool has correct name."""
        assert send_voice_message_to_smart_home_tool["name"] == "send_voice_message_to_smart_home"

    def test_tool_has_description(self):
        """AC #10: Tool has LLM-guiding description."""
        desc = send_voice_message_to_smart_home_tool["description"]
        assert "home" in desc.lower()
        assert "complement" in desc.lower() or "COMPLEMENT" in desc
        assert "cooldown" in desc.lower() or "60-second" in desc
        assert "voice type" in desc.lower() or "VOICE TYPES" in desc

    def test_tool_description_includes_constraints(self):
        """AC #10: Description includes all constraints."""
        desc = send_voice_message_to_smart_home_tool["description"]
        assert "physically at home" in desc or "home" in desc.lower()
        assert "replacement" in desc.lower() or "COMPLEMENT" in desc
        assert "60" in desc  # 60-second cooldown

    def test_tool_has_input_schema(self):
        """AC #1: Tool has inputSchema."""
        schema = send_voice_message_to_smart_home_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "message" in schema["properties"]
        assert "devices" in schema["properties"]
        assert "voice_type" in schema["properties"]

    def test_tool_required_fields(self):
        """AC #1: message and devices are required."""
        required = send_voice_message_to_smart_home_tool["inputSchema"]["required"]
        assert "message" in required
        assert "devices" in required

    def test_tool_voice_type_enum(self):
        """AC #4: voice_type has all 8 options in enum."""
        voice_type_prop = send_voice_message_to_smart_home_tool["inputSchema"]["properties"]["voice_type"]
        enum_values = voice_type_prop["enum"]

        expected = ["say", "announce", "whisper", "excited", "disappointed", "conversational", "news", "fun"]
        assert len(enum_values) == 8
        for voice_type in expected:
            assert voice_type in enum_values

    def test_tool_voice_type_default(self):
        """AC #4: voice_type defaults to 'say'."""
        voice_type_prop = send_voice_message_to_smart_home_tool["inputSchema"]["properties"]["voice_type"]
        assert voice_type_prop["default"] == "say"

    def test_tool_has_handler(self):
        """AC #1: Tool has handler function."""
        assert send_voice_message_to_smart_home_tool["handler"] == send_voice_message_to_smart_home_handler


class TestNotifyAlexaMediaCall:
    """Tests for notify.alexa_media service call (AC #2, #3)."""

    def setup_method(self):
        """Reset cooldown before each test."""
        reset_voice_message_cooldown()

    @pytest.mark.asyncio
    async def test_multi_device_in_target_array(self):
        """AC #3: Multiple devices are passed to target array."""
        mock_ha_query = {
            "status": "success",
            "entities": [
                {"entity_id": "media_player.kitchen_echo", "state": "idle"},
                {"entity_id": "media_player.bedroom_echo", "state": "idle"},
            ],
            "query_count": 2
        }

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query, \
             patch("mcp_server.tools.home_assistant.HA_URL", "http://localhost:8123"), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test_token"), \
             patch("httpx.AsyncClient") as mock_client_class:

            mock_query.return_value = mock_ha_query

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await send_voice_message_to_smart_home_handler(
                message="Dinner is ready!",
                devices=["media_player.kitchen_echo", "media_player.bedroom_echo"],
                voice_type="announce"
            )

            assert result["status"] == "success"
            assert result["devices"] == ["media_player.kitchen_echo", "media_player.bedroom_echo"]

            # Verify the call was made with both devices
            call_args = mock_client.post.call_args
            json_payload = call_args.kwargs.get("json", {})
            assert json_payload["target"] == ["media_player.kitchen_echo", "media_player.bedroom_echo"]

    @pytest.mark.asyncio
    async def test_notify_alexa_media_endpoint(self):
        """AC #2: Calls correct endpoint."""
        mock_ha_query = {
            "status": "success",
            "entities": [{"entity_id": "media_player.kitchen_echo", "state": "idle"}],
            "query_count": 1
        }

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query, \
             patch("mcp_server.tools.home_assistant.HA_URL", "http://localhost:8123"), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test_token"), \
             patch("httpx.AsyncClient") as mock_client_class:

            mock_query.return_value = mock_ha_query

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await send_voice_message_to_smart_home_handler(
                message="Hello",
                devices=["media_player.kitchen_echo"],
                voice_type="say"
            )

            # Verify endpoint
            call_args = mock_client.post.call_args
            url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
            assert "api/services/notify/alexa_media" in url

    @pytest.mark.asyncio
    async def test_ssml_wrapped_message_in_payload(self):
        """AC #2: SSML-wrapped message is sent in payload."""
        mock_ha_query = {
            "status": "success",
            "entities": [{"entity_id": "media_player.kitchen_echo", "state": "idle"}],
            "query_count": 1
        }

        with patch("mcp_server.tools.home_assistant.home_assistant_query_handler", new_callable=AsyncMock) as mock_query, \
             patch("mcp_server.tools.home_assistant.HA_URL", "http://localhost:8123"), \
             patch("mcp_server.tools.home_assistant.HA_ACCESS_TOKEN", "test_token"), \
             patch("httpx.AsyncClient") as mock_client_class:

            mock_query.return_value = mock_ha_query

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.raise_for_status = MagicMock()

            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await send_voice_message_to_smart_home_handler(
                message="Great news!",
                devices=["media_player.kitchen_echo"],
                voice_type="excited"
            )

            # Verify SSML in payload
            call_args = mock_client.post.call_args
            json_payload = call_args.kwargs.get("json", {})
            assert 'amazon:emotion name="excited"' in json_payload["message"]
            assert "Great news!" in json_payload["message"]
