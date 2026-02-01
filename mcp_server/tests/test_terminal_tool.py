"""
Tests for Terminal Command Execution Tool

Tests cover:
- Admin authorization check
- Handler function with user_id parameter
- Successful command execution via proxy
- Error handling (timeout, connection, general errors)
- Tool schema validation (user_id required)
"""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import httpx

from mcp_server.tools.terminal import (
    execute_command_tool_handler,
    execute_command_tool,
    HOST_TERMINAL_URL,
)
from mcp_server.config import is_admin


class TestIsAdminFunction:
    """Tests for is_admin function in config."""

    def test_is_admin_with_admin_user(self):
        """Admin user returns True."""
        with patch("mcp_server.config.ADMIN_USER_IDS", {"123", "456"}):
            # Need to reimport to get patched value
            from mcp_server import config
            config.ADMIN_USER_IDS = {"123", "456"}
            assert config.is_admin("123") is True
            assert config.is_admin("456") is True

    def test_is_admin_with_non_admin_user(self):
        """Non-admin user returns False."""
        with patch("mcp_server.config.ADMIN_USER_IDS", {"123"}):
            from mcp_server import config
            config.ADMIN_USER_IDS = {"123"}
            assert config.is_admin("999") is False

    def test_is_admin_with_empty_user_id(self):
        """Empty user_id returns False."""
        assert is_admin("") is False
        assert is_admin(None) is False

    def test_is_admin_with_empty_admin_list(self):
        """Empty admin list means no one is admin."""
        with patch("mcp_server.config.ADMIN_USER_IDS", set()):
            from mcp_server import config
            config.ADMIN_USER_IDS = set()
            assert config.is_admin("123") is False

    def test_is_admin_strips_whitespace(self):
        """User ID with whitespace is handled correctly."""
        with patch("mcp_server.config.ADMIN_USER_IDS", {"123"}):
            from mcp_server import config
            config.ADMIN_USER_IDS = {"123"}
            assert config.is_admin(" 123 ") is True


class TestAdminAuthorization:
    """Tests for admin authorization check."""

    @pytest.mark.asyncio
    async def test_non_admin_user_rejected(self):
        """Non-admin user receives UNAUTHORIZED error."""
        with patch("mcp_server.tools.terminal.is_admin", return_value=False):
            result = await execute_command_tool_handler(
                command="ls",
                user_id="non_admin_user",
            )

            assert result["status"] == "error"
            assert result["error_code"] == "UNAUTHORIZED"
            assert "admin users only" in result["error"]

    @pytest.mark.asyncio
    async def test_admin_user_allowed(self):
        """Admin user can execute commands."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success", "stdout": "output"}
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await execute_command_tool_handler(
                command="ls",
                user_id="admin_user",
            )

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_empty_user_id_rejected(self):
        """Empty user_id is rejected."""
        with patch("mcp_server.tools.terminal.is_admin", return_value=False):
            result = await execute_command_tool_handler(
                command="ls",
                user_id="",
            )

            assert result["status"] == "error"
            assert result["error_code"] == "UNAUTHORIZED"

    @pytest.mark.asyncio
    async def test_unauthorized_attempt_logged(self):
        """Unauthorized access attempts are logged."""
        with patch("mcp_server.tools.terminal.is_admin", return_value=False), \
             patch("mcp_server.tools.terminal.logger") as mock_logger:
            await execute_command_tool_handler(
                command="rm -rf /",
                user_id="hacker_123",
            )

            mock_logger.warning.assert_called_once()
            call_args = mock_logger.warning.call_args
            assert "Unauthorized" in call_args.args[0]
            extra = call_args.kwargs.get("extra", {})
            assert extra["user_id"] == "hacker_123"
            assert extra["command"] == "rm -rf /"


class TestExecuteCommandHandler:
    """Tests for execute_command_tool_handler function."""

    @pytest.mark.asyncio
    async def test_successful_command_execution(self):
        """Successful command returns response from host-terminal-mcp."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "stdout": "Hello, World!\n",
            "stderr": "",
            "exit_code": 0,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await execute_command_tool_handler(
                command="echo 'Hello, World!'",
                user_id="YOUR_USER_ID",
            )

            assert result["status"] == "success"
            assert result["stdout"] == "Hello, World!\n"
            assert result["exit_code"] == 0
            mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_with_working_directory(self):
        """Command with working_directory passes it to the server."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "status": "success",
            "stdout": "/home/user\n",
            "stderr": "",
            "exit_code": 0,
        }
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            result = await execute_command_tool_handler(
                command="pwd",
                user_id="YOUR_USER_ID",
                working_directory="/home/user",
            )

            assert result["status"] == "success"
            # Verify working_directory was included in payload
            call_args = mock_client.post.call_args
            json_payload = call_args.kwargs.get("json", {})
            assert json_payload["command"] == "pwd"
            assert json_payload["working_directory"] == "/home/user"

    @pytest.mark.asyncio
    async def test_user_id_logged(self):
        """User ID is included in log messages."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "success"}
        mock_response.raise_for_status = MagicMock()

        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class, \
             patch("mcp_server.tools.terminal.logger") as mock_logger:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.return_value = mock_response
            mock_client_class.return_value = mock_client

            await execute_command_tool_handler(
                command="ls",
                user_id="test_user_123",
            )

            # Verify logger.info was called with user_id in extra
            mock_logger.info.assert_called_once()
            call_args = mock_logger.info.call_args
            extra = call_args.kwargs.get("extra", {})
            assert extra["user_id"] == "test_user_123"


class TestErrorHandling:
    """Tests for error handling in execute_command_tool_handler."""

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        """Timeout returns appropriate error message."""
        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.TimeoutException("Request timed out")
            mock_client_class.return_value = mock_client

            result = await execute_command_tool_handler(
                command="sleep 999",
                user_id="YOUR_USER_ID",
            )

            assert result["status"] == "error"
            assert "timed out" in result["error"]

    @pytest.mark.asyncio
    async def test_connection_error(self):
        """Connection error returns helpful message."""
        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = httpx.ConnectError("Connection refused")
            mock_client_class.return_value = mock_client

            result = await execute_command_tool_handler(
                command="ls",
                user_id="YOUR_USER_ID",
            )

            assert result["status"] == "error"
            assert "Cannot reach terminal server" in result["error"]
            assert "host-terminal-mcp" in result["error"]

    @pytest.mark.asyncio
    async def test_general_exception(self):
        """General exception returns error string."""
        with patch("mcp_server.tools.terminal.is_admin", return_value=True), \
             patch("httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.post.side_effect = Exception("Unexpected error")
            mock_client_class.return_value = mock_client

            result = await execute_command_tool_handler(
                command="ls",
                user_id="YOUR_USER_ID",
            )

            assert result["status"] == "error"
            assert "Unexpected error" in result["error"]


class TestToolSchema:
    """Tests for tool schema definition."""

    def test_tool_name(self):
        """Tool has correct name."""
        assert execute_command_tool["name"] == "execute_command"

    def test_tool_has_description(self):
        """Tool has description mentioning key capabilities."""
        desc = execute_command_tool["description"]
        assert "terminal command" in desc.lower() or "command" in desc.lower()
        assert "host" in desc.lower()

    def test_tool_has_admin_restriction(self):
        """Tool description mentions admin restriction."""
        desc = execute_command_tool["description"]
        assert "admin" in desc.lower()
        assert "ADMIN_USER_IDS" in desc

    def test_tool_has_input_schema(self):
        """Tool has inputSchema with correct structure."""
        schema = execute_command_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "command" in schema["properties"]
        assert "user_id" in schema["properties"]
        assert "working_directory" in schema["properties"]

    def test_command_is_required(self):
        """command field is required."""
        required = execute_command_tool["inputSchema"]["required"]
        assert "command" in required

    def test_user_id_is_required(self):
        """user_id field is required."""
        required = execute_command_tool["inputSchema"]["required"]
        assert "user_id" in required

    def test_working_directory_is_optional(self):
        """working_directory field is NOT required."""
        required = execute_command_tool["inputSchema"]["required"]
        assert "working_directory" not in required

    def test_user_id_property_definition(self):
        """user_id property has correct type and description."""
        user_id_prop = execute_command_tool["inputSchema"]["properties"]["user_id"]
        assert user_id_prop["type"] == "string"
        assert "user" in user_id_prop["description"].lower()

    def test_tool_has_handler(self):
        """Tool has handler function."""
        assert execute_command_tool["handler"] == execute_command_tool_handler


class TestHostTerminalUrl:
    """Tests for HOST_TERMINAL_URL configuration."""

    def test_default_url_uses_docker_internal(self):
        """Default URL uses host.docker.internal."""
        # The default is set at module load time, so we just verify its structure
        assert "host.docker.internal" in HOST_TERMINAL_URL or "localhost" in HOST_TERMINAL_URL
        assert "8099" in HOST_TERMINAL_URL
