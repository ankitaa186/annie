"""
MCP Server Tool Registry and Tool Implementations

This module provides tool registration and basic tool implementations.
"""

from typing import Any, Callable, Dict, Optional

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


def health_check_tool_handler() -> Dict[str, Any]:
    """
    Health check tool handler.
    
    Returns:
        Health status dictionary
    """
    from datetime import datetime
    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


# Health check tool definition
health_check_tool = {
    "name": "health_check",
    "description": "Check MCP server health status",
    "inputSchema": {
        "type": "object",
        "properties": {},
        "required": []
    },
    "handler": health_check_tool_handler
}
