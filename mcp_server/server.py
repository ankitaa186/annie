"""
MCP Server Main Module

Implements MCP (Model Context Protocol) server with stdio transport
and JSON-RPC 2.0 protocol support.
"""

import json
import sys
import time
from datetime import datetime
from typing import Any, Dict, Optional

from mcp_server.logging import get_logger, log_performance
from mcp_server.tools import ToolRegistry, health_check_tool

logger = get_logger(__name__)


class MCPServer:
    """MCP Server implementation with stdio transport."""
    
    def __init__(self):
        """Initialize MCP server."""
        self.tool_registry = ToolRegistry()
        self.register_default_tools()
        logger.info("MCP Server initialized")
    
    def register_default_tools(self):
        """Register default tools."""
        self.tool_registry.register(health_check_tool)
        logger.info(f"Registered {len(self.tool_registry.tools)} tools")
    
    def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle JSON-RPC 2.0 request.
        
        Args:
            request: JSON-RPC 2.0 request dictionary
        
        Returns:
            JSON-RPC 2.0 response dictionary
        """
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})
        
        logger.debug(
            f"Received request: method={method}, id={request_id}",
            extra={"request_id": str(request_id), "method": method}
        )
        
        try:
            if method == "tools/list":
                return self.handle_tools_list(request_id)
            elif method == "tools/call":
                return self.handle_tool_call(request_id, params)
            else:
                return self.create_error_response(
                    request_id,
                    -32601,
                    f"Method not found: {method}"
                )
        except Exception as e:
            logger.error(
                f"Error handling request: {str(e)}",
                exc_info=True,
                extra={"request_id": str(request_id), "error_code": "REQUEST_HANDLING_ERROR"}
            )
            return self.create_error_response(
                request_id,
                -32603,
                f"Internal error: {str(e)}"
            )
    
    def handle_tools_list(self, request_id: Optional[Any]) -> Dict[str, Any]:
        """
        Handle tools/list request.
        
        Args:
            request_id: Request ID
        
        Returns:
            JSON-RPC response with list of available tools
        """
        tools = []
        for tool_name, tool_info in self.tool_registry.tools.items():
            tools.append({
                "name": tool_name,
                "description": tool_info.get("description", ""),
                "inputSchema": tool_info.get("inputSchema", {})
            })
        
        logger.info(f"Listed {len(tools)} tools", extra={"request_id": str(request_id)})
        
        return {
            "jsonrpc": "2.0",
            "result": {"tools": tools},
            "id": request_id
        }
    
    @log_performance("tool_call")
    def handle_tool_call(self, request_id: Optional[Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle tools/call request.
        
        Args:
            request_id: Request ID
            params: Tool call parameters (name, arguments)
        
        Returns:
            JSON-RPC response with tool result
        """
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        
        if not tool_name:
            return self.create_error_response(
                request_id,
                -32602,
                "Invalid params: 'name' is required"
            )
        
        start_time = time.time()
        
        logger.info(
            f"Tool call: {tool_name}",
            extra={
                "request_id": str(request_id),
                "tool_name": tool_name,
                "parameters": arguments
            }
        )
        
        # Get tool handler
        tool_info = self.tool_registry.get_tool(tool_name)
        if not tool_info:
            return self.create_error_response(
                request_id,
                -32601,
                f"Tool not found: {tool_name}"
            )
        
        # Execute tool
        try:
            tool_handler = tool_info["handler"]
            result = tool_handler(**arguments)
            duration_ms = int((time.time() - start_time) * 1000)
            
            logger.info(
                f"Tool call completed: {tool_name}",
                extra={
                    "request_id": str(request_id),
                    "tool_name": tool_name,
                    "duration_ms": duration_ms,
                    "result": result
                }
            )
            
            return {
                "jsonrpc": "2.0",
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result)
                        }
                    ]
                },
                "id": request_id
            }
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Tool call failed: {tool_name}",
                exc_info=True,
                extra={
                    "request_id": str(request_id),
                    "tool_name": tool_name,
                    "duration_ms": duration_ms,
                    "error_code": "TOOL_EXECUTION_ERROR"
                }
            )
            return self.create_error_response(
                request_id,
                -32603,
                f"Tool execution error: {str(e)}"
            )
    
    def create_error_response(
        self,
        request_id: Optional[Any],
        code: int,
        message: str
    ) -> Dict[str, Any]:
        """
        Create JSON-RPC error response.
        
        Args:
            request_id: Request ID
            code: Error code
            message: Error message
        
        Returns:
            JSON-RPC error response
        """
        logger.warning(
            f"Error response: code={code}, message={message}",
            extra={"request_id": str(request_id), "error_code": code}
        )
        
        return {
            "jsonrpc": "2.0",
            "error": {
                "code": code,
                "message": message
            },
            "id": request_id
        }
    
    def run(self):
        """Run MCP server with stdio transport."""
        logger.info("Starting MCP server with stdio transport...")
        
        try:
            while True:
                # Read JSON-RPC message from stdin
                line = sys.stdin.readline()
                if not line:
                    # EOF reached - log and wait briefly before continuing
                    # This handles cases where stdin temporarily closes
                    logger.debug("EOF on stdin, waiting for input...")
                    time.sleep(0.1)
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                try:
                    request = json.loads(line)
                    response = self.handle_request(request)
                    
                    # Write response to stdout
                    print(json.dumps(response), flush=True)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON: {str(e)}", exc_info=True)
                    error_response = self.create_error_response(
                        None,
                        -32700,
                        f"Parse error: {str(e)}"
                    )
                    print(json.dumps(error_response), flush=True)
        except KeyboardInterrupt:
            logger.info("MCP server shutting down...")
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}", exc_info=True)
            sys.exit(1)


def main():
    """Main entry point for MCP server."""
    server = MCPServer()
    server.run()


if __name__ == "__main__":
    main()
