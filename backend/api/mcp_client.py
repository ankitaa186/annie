"""
MCP Client Module

Async HTTP client for communicating with MCP server via JSON-RPC 2.0 protocol.
Provides tool schema fetching and tool execution with error handling and caching.
"""

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx

from api.config import get_config
from api.logging import get_logger

try:
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    # Graceful degradation if langfuse not installed
    LANGFUSE_AVAILABLE = False
    def observe(**kwargs):
        """No-op decorator when Langfuse not available"""
        def decorator(func):
            return func
        return decorator
    class langfuse_context:
        @staticmethod
        def update_current_observation(**kwargs):
            pass

logger = get_logger(__name__)


class MCPClientError(Exception):
    """Base exception for MCP client errors."""
    pass


class MCPNetworkError(MCPClientError):
    """Exception raised when MCP server is unreachable."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class MCPToolError(MCPClientError):
    """Exception raised when tool execution fails."""
    def __init__(self, tool_name: str, message: str, error_code: Optional[int] = None):
        self.tool_name = tool_name
        self.message = message
        self.error_code = error_code
        super().__init__(f"Tool '{tool_name}' failed: {message}")


class MCPClient:
    """
    Async HTTP client for MCP server communication.

    Features:
    - JSON-RPC 2.0 protocol support
    - Tool schema fetching with caching (tools/list)
    - Tool execution (tools/call)
    - Timeout handling (5 second default for p95 requirement)
    - Structured error logging
    - Connection pooling with httpx.AsyncClient
    """

    # Default configuration
    DEFAULT_MCP_URL = "http://mcp-server:8002"
    DEFAULT_TIMEOUT = 60.0  # 60 seconds (generous timeout for memory operations which can take 7+ seconds)
    CACHE_TTL = 300  # 5 minutes for tool schema cache

    def __init__(self, mcp_server_url: Optional[str] = None, timeout: Optional[float] = None):
        """
        Initialize MCP client.

        Args:
            mcp_server_url: MCP server URL (default: from config or http://mcp-server:8002)
            timeout: Request timeout in seconds (default: 60.0)
        """
        if mcp_server_url:
            self.mcp_server_url = mcp_server_url
        else:
            # Load from config
            try:
                config = get_config()
                self.mcp_server_url = config.get("MCP_SERVER_URL", self.DEFAULT_MCP_URL)
            except Exception as e:
                logger.warning(
                    "Failed to load config, using default MCP server URL",
                    extra={"error": str(e)}
                )
                self.mcp_server_url = self.DEFAULT_MCP_URL

        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Initialize async HTTP client with timeout
        self.client = httpx.AsyncClient(timeout=self.timeout)

        # Cache for tool schemas
        self._tool_cache: Optional[List[Dict[str, Any]]] = None
        self._cache_timestamp: Optional[float] = None

        logger.info(
            "MCP Client initialized",
            extra={
                "mcp_server_url": self.mcp_server_url,
                "timeout": self.timeout
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close HTTP client."""
        await self.close()

    async def close(self):
        """Close HTTP client connection."""
        if self.client:
            await self.client.aclose()

    async def list_tools(self, use_cache: bool = True) -> List[Dict[str, Any]]:
        """
        Fetch available tools from MCP server.

        Args:
            use_cache: Use cached tool schemas if available (default: True)

        Returns:
            List of tool dictionaries with 'name', 'description', and 'inputSchema'

        Raises:
            MCPNetworkError: If MCP server is unreachable
            MCPClientError: If request fails
        """
        # Check cache
        if use_cache and self._tool_cache is not None:
            cache_age = time.time() - (self._cache_timestamp or 0)
            if cache_age < self.CACHE_TTL:
                logger.debug(
                    "Using cached tool schemas",
                    extra={"tool_count": len(self._tool_cache), "cache_age_seconds": int(cache_age)}
                )
                return self._tool_cache

        start_time = time.time()
        url = f"{self.mcp_server_url}/tools/list"

        try:
            logger.debug("Fetching tool schemas from MCP server", extra={"url": url})

            response = await self.client.get(url)

            # Check for errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception:
                    pass

                raise MCPClientError(f"Failed to list tools: {error_msg}")

            # Parse JSON-RPC response
            result = response.json()

            # Extract tools from result
            tools = result.get("result", {}).get("tools", [])

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Tool schemas fetched successfully",
                extra={
                    "tool_count": len(tools),
                    "duration_ms": duration_ms
                }
            )

            # Update cache
            self._tool_cache = tools
            self._cache_timestamp = time.time()

            return tools

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "MCP server timeout",
                extra={
                    "url": url,
                    "duration_ms": duration_ms,
                    "timeout": self.timeout
                }
            )
            raise MCPNetworkError("MCP server timeout", e)

        except httpx.NetworkError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "MCP server unreachable",
                extra={
                    "url": url,
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            raise MCPNetworkError("MCP server unreachable", e)

        except MCPClientError:
            # Re-raise MCP client errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected error fetching tools",
                extra={
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise MCPClientError(f"Unexpected error: {type(e).__name__}")

    @observe(name="mcp_tool_call", as_type="span")
    async def call_tool(self, tool_name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute an MCP tool via JSON-RPC 2.0.

        Langfuse automatically traces this method with:
        - Input: tool_name, arguments (truncated to 500 chars)
        - Output: tool_result (truncated to 500 chars)
        - Duration, errors, and metadata

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments dictionary

        Returns:
            Tool result dictionary

        Raises:
            MCPNetworkError: If MCP server is unreachable
            MCPToolError: If tool execution fails
            MCPClientError: If request fails
        """
        arguments = arguments or {}
        start_time = time.time()

        # Generate unique request ID
        request_id = f"call-{uuid.uuid4().hex[:8]}"

        try:
            # Build JSON-RPC 2.0 request
            json_rpc_request = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                },
                "id": request_id
            }

            # Make request to tools/call endpoint
            url = f"{self.mcp_server_url}/tools/call"

            logger.info(
                "Calling MCP tool",
                extra={
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "parameters": arguments
                }
            )

            # Update Langfuse observation with metadata (decorator creates span automatically)
            if LANGFUSE_AVAILABLE:
                try:
                    langfuse_context.update_current_observation(
                        metadata={
                            "tool_name": tool_name,
                            "request_id": request_id,
                            "arguments": str(arguments)[:500]  # Truncate to 500 chars
                        }
                    )
                except Exception:
                    pass  # Fire-and-forget

            response = await self.client.post(
                url,
                json=json_rpc_request,
                headers={"Content-Type": "application/json"}
            )

            # Parse JSON-RPC response
            json_rpc_response = response.json()

            # Check for JSON-RPC error
            if "error" in json_rpc_response:
                error_info = json_rpc_response["error"]
                error_code = error_info.get("code", -32603)
                error_message = error_info.get("message", "Unknown error")

                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Tool execution failed",
                    extra={
                        "tool_name": tool_name,
                        "request_id": request_id,
                        "duration_ms": duration_ms,
                        "error_code": error_code,
                        "error_message": error_message
                    }
                )

                raise MCPToolError(tool_name, error_message, error_code)

            # Check for HTTP error
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                duration_ms = int((time.time() - start_time) * 1000)
                logger.error(
                    "Tool call HTTP error",
                    extra={
                        "tool_name": tool_name,
                        "request_id": request_id,
                        "duration_ms": duration_ms,
                        "status_code": response.status_code
                    }
                )
                raise MCPToolError(tool_name, error_msg)

            # Extract result from JSON-RPC response
            result = json_rpc_response.get("result", {})

            # Parse tool result from content array
            # MCP server returns: {"content": [{"type": "text", "text": "json_string"}]}
            content = result.get("content", [])
            if content and len(content) > 0:
                text_content = content[0].get("text", "{}")
                try:
                    tool_result = json.loads(text_content)
                except json.JSONDecodeError:
                    # If not JSON, return as plain text
                    tool_result = {"result": text_content}
            else:
                tool_result = result

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Tool execution completed",
                extra={
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                    "success": True
                }
            )

            # Update Langfuse observation with output (decorator captures return automatically)
            if LANGFUSE_AVAILABLE:
                try:
                    langfuse_context.update_current_observation(
                        output={
                            "tool_result": str(tool_result)[:500],  # Truncate to 500 chars
                            "duration_ms": duration_ms,
                            "result_size": len(str(tool_result))
                        }
                    )
                    logger.info(
                        f"[LANGFUSE] Updated MCP tool call span: {tool_name}",
                        extra={
                            "tool_name": tool_name,
                            "duration_ms": duration_ms
                        }
                    )
                except Exception as e:
                    logger.debug(f"[LANGFUSE] Failed to update tool span: {e}")

            # @observe() decorator automatically captures return value
            return tool_result

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Tool execution timeout",
                extra={
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                    "timeout": self.timeout
                }
            )
            # @observe() decorator automatically captures and logs the exception
            raise MCPNetworkError(f"Tool '{tool_name}' timed out", e)

        except httpx.NetworkError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Tool execution network error",
                extra={
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            # @observe() decorator automatically captures and logs the exception
            raise MCPNetworkError(f"MCP server unreachable for tool '{tool_name}'", e)

        except (MCPClientError, MCPToolError):
            # @observe() decorator automatically captures and logs the exception
            # Re-raise MCP errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected tool execution error",
                extra={
                    "tool_name": tool_name,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            # @observe() decorator automatically captures and logs the exception
            raise MCPClientError(f"Unexpected error calling tool '{tool_name}': {type(e).__name__}")
