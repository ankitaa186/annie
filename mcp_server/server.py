"""
MCP Server Main Module

Implements MCP (Model Context Protocol) server with HTTP transport
and JSON-RPC 2.0 protocol support.
"""

import asyncio
import inspect
import json
import os
import time
from datetime import datetime
import pytz

_PACIFIC_TZ = pytz.timezone("America/Los_Angeles")
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

from mcp_server.config import get_config
from mcp_server.logging import get_logger, log_performance
from mcp_server.tools import (
    ToolRegistry,
    health_check_tool,
    store_memory_tool,
    delete_memory_tool,
    retrieve_memories_tool,
    compact_memories_tool,
    get_user_profile_tool,
    update_user_profile_tool,  # Story 15.4
    get_portfolio_tool,
    add_holding_tool,
    update_holding_tool,
    remove_holding_tool,
    clear_portfolio_tool,
    get_stock_data_tool,
    get_stock_history_tool,
    get_financials_tool,  # Financial statements + earnings
    get_sec_filings_tool,  # SEC EDGAR filings (10-K, 10-Q, 8-K)
    create_trigger_tool,
    list_triggers_tool,
    update_trigger_tool,
    delete_trigger_tool,
    web_search_tool,
    reddit_search_tool,
    web_crawl_tool,
    home_assistant_query_tool,  # Epic 16 - Story 16.1
    home_assistant_control_tool,  # Epic 16 - Story 16.2
    send_voice_message_to_smart_home_tool,  # Epic 16 - Story 16.6
    browser_action_tool,  # Browser Automation
)

logger = get_logger(__name__)
config = get_config()


def setup_debugger():
    """Initialize remote debugger automatically in dev environment."""
    environment = os.getenv("ENVIRONMENT", "dev")
    
    # Only enable debugging in dev environment
    if environment.lower() == "dev":
        try:
            import debugpy
            debug_port = int(os.getenv("DEBUGGER_PORT", "5679"))
            debugpy.listen(("0.0.0.0", debug_port))
            logger.info(f"🔧 Remote debugger listening on port {debug_port} (dev mode)")
        except ImportError:
            logger.debug("debugpy not available - remote debugging disabled")
        except Exception as e:
            logger.warning(f"Failed to setup debugger: {e}")


# Initialize debugger before creating app (dev only)
setup_debugger()


class MCPServer:
    """MCP Server implementation with HTTP transport."""

    def __init__(self):
        """Initialize MCP server."""
        self.tool_registry = ToolRegistry()
        self.register_default_tools()
        logger.info("MCP Server initialized")

    def register_default_tools(self):
        """Register default tools."""
        self.tool_registry.register(health_check_tool)
        self.tool_registry.register(store_memory_tool)
        self.tool_registry.register(delete_memory_tool)
        self.tool_registry.register(retrieve_memories_tool)
        self.tool_registry.register(compact_memories_tool)
        self.tool_registry.register(get_user_profile_tool)
        # Profile update tool (Epic 15 - Story 15.4)
        self.tool_registry.register(update_user_profile_tool)
        # Portfolio management tools (Epic 10)
        self.tool_registry.register(get_portfolio_tool)
        self.tool_registry.register(add_holding_tool)
        self.tool_registry.register(update_holding_tool)
        self.tool_registry.register(remove_holding_tool)
        self.tool_registry.register(clear_portfolio_tool)
        # Stock market analysis tools (Epic 10 - Story 10.6)
        self.tool_registry.register(get_stock_data_tool)
        self.tool_registry.register(get_stock_history_tool)
        # Financial data tools (financial statements, earnings, SEC filings)
        self.tool_registry.register(get_financials_tool)
        self.tool_registry.register(get_sec_filings_tool)
        # Proactive AI: Trigger management tools (Epic 13 - Story 13.2)
        self.tool_registry.register(create_trigger_tool)
        self.tool_registry.register(list_triggers_tool)
        self.tool_registry.register(update_trigger_tool)
        self.tool_registry.register(delete_trigger_tool)
        # Web search tool (Epic 15 - Story 15.1)
        self.tool_registry.register(web_search_tool)
        # Reddit search tool (Epic 15 - Story 15.3) - DISABLED: Reddit OAuth not configured
        self.tool_registry.register(reddit_search_tool)
        # Web crawl tool (Epic 15 - Story 15.2)
        self.tool_registry.register(web_crawl_tool)
        # Home Assistant tools (Epic 16 - Stories 16.1, 16.2, 16.6)
        self.tool_registry.register(home_assistant_query_tool)
        self.tool_registry.register(home_assistant_control_tool)
        self.tool_registry.register(send_voice_message_to_smart_home_tool)
        # Browser automation tool
        self.tool_registry.register(browser_action_tool)
        logger.info(f"Registered {len(self.tool_registry.tools)} tools")

    async def handle_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
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
                return await self.handle_tool_call(request_id, params)
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
    async def handle_tool_call(self, request_id: Optional[Any], params: Dict[str, Any]) -> Dict[str, Any]:
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

            # Check if handler is async and await if needed
            if inspect.iscoroutinefunction(tool_handler):
                result = await tool_handler(**arguments)
            else:
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


# Create FastAPI app
app = FastAPI(
    title="Annie MCP Server",
    description="MCP (Model Context Protocol) Server for Annie",
    version="1.0.0"
)

# Initialize MCP server instance
mcp_server = MCPServer()


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(content={
        "status": "ok",
        "timestamp": datetime.now(_PACIFIC_TZ).isoformat(),
        "tools_registered": len(mcp_server.tool_registry.tools)
    })


@app.get("/tools/list")
async def list_tools():
    """
    List all available MCP tools.

    Returns JSON-RPC 2.0 response with tools list.
    """
    request_data = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": "http-list"
    }

    response = await mcp_server.handle_request(request_data)
    return JSONResponse(content=response)


@app.post("/tools/call")
async def call_tool(request: Request):
    """
    Call an MCP tool via JSON-RPC 2.0.

    Expects JSON-RPC 2.0 request body:
    {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "tool_name",
            "arguments": {...}
        },
        "id": 1
    }
    """
    try:
        request_data = await request.json()

        # Validate JSON-RPC 2.0 format
        if request_data.get("jsonrpc") != "2.0":
            return JSONResponse(
                status_code=400,
                content={
                    "jsonrpc": "2.0",
                    "error": {
                        "code": -32600,
                        "message": "Invalid Request: jsonrpc version must be '2.0'"
                    },
                    "id": request_data.get("id")
                }
            )

        response = await mcp_server.handle_request(request_data)
        return JSONResponse(content=response)

    except json.JSONDecodeError as e:
        return JSONResponse(
            status_code=400,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32700,
                    "message": f"Parse error: {str(e)}"
                },
                "id": None
            }
        )
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "jsonrpc": "2.0",
                "error": {
                    "code": -32603,
                    "message": f"Internal error: {str(e)}"
                },
                "id": None
            }
        )


@app.get("/")
async def root():
    """Root endpoint with server info."""
    return JSONResponse(content={
        "name": "Annie MCP Server",
        "version": "1.0.0",
        "status": "running",
        "transport": "http",
        "endpoints": {
            "health": "/health",
            "list_tools": "/tools/list",
            "call_tool": "/tools/call (POST)"
        }
    })


if __name__ == "__main__":
    import uvicorn

    port = config.get("MCP_SERVER_PORT", 8002)

    logger.info(f"Starting MCP server on port {port}...")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        log_level=config.get("LOG_LEVEL", "info").lower()
    )
