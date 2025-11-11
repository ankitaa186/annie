"""
MCP Client Module

HTTP client for communicating with MCP server via JSON-RPC 2.0 protocol.
"""

import httpx
from typing import Any, Dict, List, Optional
from api.config import get_config
from api.logging import get_logger

logger = get_logger(__name__)


class MCPClient:
    """
    HTTP client for MCP server communication.

    Handles JSON-RPC 2.0 requests to MCP server tools.
    """

    def __init__(self, mcp_server_url: Optional[str] = None):
        """
        Initialize MCP client.

        Args:
            mcp_server_url: MCP server URL (default: from config)
        """
        if mcp_server_url:
            self.mcp_server_url = mcp_server_url
        else:
            # Only load config if URL not provided
            try:
                config = get_config()
                self.mcp_server_url = config.get("MCP_SERVER_URL", "http://mcp-server:8002")
            except Exception as e:
                # Fallback to default if config fails
                logger.warning(f"Failed to load config, using default MCP server URL: {str(e)}")
                self.mcp_server_url = "http://mcp-server:8002"

        self.client = httpx.Client(timeout=30.0)
        logger.info(f"MCP Client initialized with server URL: {self.mcp_server_url}")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close HTTP client."""
        self.close()

    def close(self):
        """Close HTTP client connection."""
        if self.client:
            self.client.close()

    def health_check(self) -> Dict[str, Any]:
        """
        Check MCP server health.

        Returns:
            Health status dictionary

        Raises:
            MCPClientError: If health check fails
        """
        try:
            response = self.client.get(f"{self.mcp_server_url}/health")
            response.raise_for_status()

            health_data = response.json()
            logger.info("MCP server health check passed", extra={"health": health_data})

            return health_data
        except httpx.HTTPError as e:
            logger.error(f"MCP server health check failed: {str(e)}", exc_info=True)
            raise MCPClientError(f"Health check failed: {str(e)}") from e

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List available MCP tools.

        Returns:
            List of tool definitions with name, description, and inputSchema

        Raises:
            MCPClientError: If request fails
        """
        try:
            response = self.client.get(f"{self.mcp_server_url}/tools/list")
            response.raise_for_status()

            json_rpc_response = response.json()

            # Check for JSON-RPC error
            if "error" in json_rpc_response:
                error = json_rpc_response["error"]
                raise MCPClientError(f"JSON-RPC error {error['code']}: {error['message']}")

            # Extract tools from result
            result = json_rpc_response.get("result", {})
            tools = result.get("tools", [])

            logger.info(f"Listed {len(tools)} MCP tools")

            return tools
        except httpx.HTTPError as e:
            logger.error(f"Failed to list MCP tools: {str(e)}", exc_info=True)
            raise MCPClientError(f"Failed to list tools: {str(e)}") from e

    def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Call an MCP tool.

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments dictionary

        Returns:
            Tool execution result

        Raises:
            MCPClientError: If tool call fails
        """
        arguments = arguments or {}

        # Build JSON-RPC 2.0 request
        json_rpc_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": f"call-{tool_name}"
        }

        logger.info(
            f"Calling MCP tool: {tool_name}",
            extra={
                "tool_name": tool_name,
                "arguments": arguments
            }
        )

        try:
            response = self.client.post(
                f"{self.mcp_server_url}/tools/call",
                json=json_rpc_request,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()

            json_rpc_response = response.json()

            # Check for JSON-RPC error
            if "error" in json_rpc_response:
                error = json_rpc_response["error"]
                error_msg = f"JSON-RPC error {error['code']}: {error['message']}"
                logger.error(
                    f"MCP tool call failed: {tool_name}",
                    extra={
                        "tool_name": tool_name,
                        "error_code": error["code"],
                        "error_message": error["message"]
                    }
                )
                raise MCPClientError(error_msg)

            # Extract result
            result = json_rpc_response.get("result", {})

            logger.info(
                f"MCP tool call completed: {tool_name}",
                extra={
                    "tool_name": tool_name,
                    "result": result
                }
            )

            return result
        except httpx.HTTPError as e:
            logger.error(
                f"HTTP error calling MCP tool: {tool_name}",
                exc_info=True,
                extra={"tool_name": tool_name}
            )
            raise MCPClientError(f"Failed to call tool {tool_name}: {str(e)}") from e


class MCPClientError(Exception):
    """Exception raised for MCP client errors."""
    pass


# Convenience function for one-off tool calls
def call_mcp_tool(tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Call an MCP tool (convenience function).

    Args:
        tool_name: Name of the tool to call
        arguments: Tool arguments dictionary

    Returns:
        Tool execution result

    Raises:
        MCPClientError: If tool call fails
    """
    with MCPClient() as client:
        return client.call_tool(tool_name, arguments)
