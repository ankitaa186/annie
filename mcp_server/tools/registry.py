"""
MCP Tool Registry

Provides the ToolRegistry class for managing tool registration.
"""

from typing import Any, Dict, Optional

from mcp_server.logging import get_logger

logger = get_logger(__name__)


class ToolRegistry:
    """Registry for MCP tools."""

    def __init__(self):
        """Initialize tool registry."""
        self.tools: Dict[str, Dict[str, Any]] = {}

    def register(self, tool_info: Dict[str, Any]):
        """
        Register a tool.

        Args:
            tool_info: Tool information dictionary with:
                - name: Tool name
                - description: Tool description
                - inputSchema: JSON schema for input parameters
                - handler: Tool handler function
        """
        tool_name = tool_info["name"]
        self.tools[tool_name] = tool_info
        logger.debug(f"Registered tool: {tool_name}")

    def get_tool(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get tool information by name.

        Args:
            tool_name: Tool name

        Returns:
            Tool information dictionary or None if not found
        """
        return self.tools.get(tool_name)
