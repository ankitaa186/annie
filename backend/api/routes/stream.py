"""
Streaming Route Handler

Handles SSE (Server-Sent Events) streaming for real-time LLM responses
with function calling and tool orchestration support.
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Dict, Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.llm_client import LLMClient, LLMClientError
from api.mcp_client import MCPClient, MCPClientError, MCPToolError, MCPNetworkError
from api.logging import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["streaming"])

# Track active streams (in-memory for now, will use Redis in Story 2.5)
active_streams: Dict[str, float] = {}  # conversation_id -> timestamp
MAX_CONCURRENT_STREAMS = 100


async def stream_generator(
    conversation_id: str,
    messages: List[Dict[str, Any]],
    request: Request
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generate SSE events from LLM streaming response with tool orchestration.

    Handles:
    - Tool schema fetching from MCP server
    - Function calling with LLM
    - Tool execution via MCP client
    - Multi-step tool calling (max 5 iterations)
    - Error handling for tool failures

    Args:
        conversation_id: Unique conversation identifier
        messages: List of chat messages to send to LLM
        request: FastAPI request object for disconnection detection

    Yields:
        SSE event dictionaries with type, data, and optional event fields
    """
    start_time = time.time()
    first_token_sent = False
    max_tool_iterations = 5

    try:
        # Create clients
        async with LLMClient() as llm_client, MCPClient() as mcp_client:
            logger.info(
                "Starting SSE stream with tool orchestration",
                extra={
                    "conversation_id": conversation_id,
                    "message_count": len(messages)
                }
            )

            # Fetch tool schemas from MCP server
            tools = None
            try:
                mcp_tools = await mcp_client.list_tools()
                if mcp_tools:
                    # Convert MCP tools to OpenAI function calling format
                    tools = llm_client.convert_mcp_tools_to_functions(mcp_tools)
                    logger.info(
                        "Tools registered for function calling",
                        extra={
                            "conversation_id": conversation_id,
                            "tool_count": len(tools)
                        }
                    )
            except (MCPClientError, MCPNetworkError) as e:
                # Log warning but continue without tools
                logger.warning(
                    "Failed to fetch tools from MCP server, continuing without tools",
                    extra={
                        "conversation_id": conversation_id,
                        "error": str(e)
                    }
                )

            # Tool orchestration loop
            tool_call_count = 0
            conversation_messages = messages.copy()

            for iteration in range(max_tool_iterations):
                # Check for client disconnection
                if await request.is_disconnected():
                    logger.info(
                        "Client disconnected during stream",
                        extra={
                            "conversation_id": conversation_id,
                            "iteration": iteration,
                            "reason": "client_disconnect"
                        }
                    )
                    break

                # Call LLM (non-streaming first to check for function calls)
                try:
                    response = await llm_client.chat_completion(
                        conversation_messages,
                        tools=tools
                    )
                except LLMClientError as e:
                    # LLM error - yield error event and stop
                    logger.error(
                        "LLM error during tool orchestration",
                        extra={
                            "conversation_id": conversation_id,
                            "iteration": iteration,
                            "error": str(e)
                        }
                    )
                    yield {
                        "event": "message",
                        "data": json.dumps({
                            "type": "error",
                            "message": str(e),
                            "code": "LLM_CLIENT_ERROR"
                        })
                    }
                    break

                # Check if LLM wants to call a function
                message = response.get("choices", [{}])[0].get("message", {})
                tool_calls = message.get("tool_calls", [])

                if not tool_calls:
                    # No tool calls - LLM returned final content
                    # Now stream the final response
                    logger.info(
                        "No tool calls, streaming final response",
                        extra={
                            "conversation_id": conversation_id,
                            "tool_calls_made": tool_call_count
                        }
                    )

                    # Stream tokens from LLM
                    async for event in llm_client.chat_completion_stream(
                        conversation_messages,
                        tools=tools
                    ):
                        # Check for client disconnection
                        if await request.is_disconnected():
                            logger.info(
                                "Client disconnected during final stream",
                                extra={
                                    "conversation_id": conversation_id,
                                    "reason": "client_disconnect"
                                }
                            )
                            break

                        # Track first token latency
                        if not first_token_sent and event.get("type") == "token":
                            first_token_latency_ms = int((time.time() - start_time) * 1000)
                            logger.info(
                                "First token sent to client",
                                extra={
                                    "conversation_id": conversation_id,
                                    "latency_ms": first_token_latency_ms
                                }
                            )
                            first_token_sent = True

                        # Yield SSE event
                        yield {
                            "event": "message",
                            "data": json.dumps(event)
                        }

                        # If error or completion, stop streaming
                        if event.get("type") in ["error", "done"]:
                            if event.get("type") == "done":
                                duration_ms = int((time.time() - start_time) * 1000)
                                logger.info(
                                    "Stream completed successfully",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "duration_ms": duration_ms,
                                        "tool_calls": tool_call_count,
                                        "tokens": event.get("tokens_used", {})
                                    }
                                )
                            break

                    # Exit tool orchestration loop
                    break

                # Process tool calls
                tool_call_count += len(tool_calls)
                logger.info(
                    "Processing tool calls",
                    extra={
                        "conversation_id": conversation_id,
                        "iteration": iteration,
                        "tool_call_count": len(tool_calls),
                        "total_tool_calls": tool_call_count
                    }
                )

                # Add assistant message with tool calls to conversation
                conversation_messages.append(message)

                # Execute each tool call
                for tool_call in tool_calls:
                    function_name = tool_call.get("function", {}).get("name", "")
                    arguments_str = tool_call.get("function", {}).get("arguments", "{}")
                    tool_call_id = tool_call.get("id", "")

                    # Parse arguments
                    try:
                        arguments = json.loads(arguments_str)
                    except json.JSONDecodeError:
                        arguments = {}

                    logger.info(
                        "Executing tool",
                        extra={
                            "conversation_id": conversation_id,
                            "tool_name": function_name,
                            "tool_call_id": tool_call_id,
                            "arguments": arguments
                        }
                    )

                    # Execute tool via MCP client
                    try:
                        tool_result = await mcp_client.call_tool(function_name, arguments)

                        # Add tool result to conversation
                        conversation_messages.append({
                            "role": "tool",
                            "content": json.dumps(tool_result),
                            "tool_call_id": tool_call_id
                        })

                        logger.info(
                            "Tool execution successful",
                            extra={
                                "conversation_id": conversation_id,
                                "tool_name": function_name,
                                "tool_call_id": tool_call_id
                            }
                        )

                    except (MCPToolError, MCPNetworkError) as e:
                        # Tool execution failed - add error to conversation
                        error_result = {
                            "error": str(e),
                            "status": "failed"
                        }

                        conversation_messages.append({
                            "role": "tool",
                            "content": json.dumps(error_result),
                            "tool_call_id": tool_call_id
                        })

                        logger.error(
                            "Tool execution failed",
                            extra={
                                "conversation_id": conversation_id,
                                "tool_name": function_name,
                                "tool_call_id": tool_call_id,
                                "error": str(e)
                            }
                        )

                # Check if we've exceeded max iterations
                if iteration >= max_tool_iterations - 1:
                    logger.warning(
                        "Max tool iterations reached",
                        extra={
                            "conversation_id": conversation_id,
                            "iterations": iteration + 1,
                            "tool_calls": tool_call_count
                        }
                    )
                    # Stream final response anyway
                    async for event in llm_client.chat_completion_stream(conversation_messages, tools=tools):
                        if await request.is_disconnected():
                            break
                        yield {
                            "event": "message",
                            "data": json.dumps(event)
                        }
                        if event.get("type") in ["error", "done"]:
                            break
                    break

    except LLMClientError as e:
        # LLM client error - send error event
        logger.error(
            "LLM client error during streaming",
            extra={
                "conversation_id": conversation_id,
                "error": str(e)
            }
        )

        yield {
            "event": "message",
            "data": json.dumps({
                "type": "error",
                "message": str(e),
                "code": "LLM_CLIENT_ERROR"
            })
        }

    except Exception as e:
        # Unexpected error - send error event
        logger.error(
            "Unexpected error during streaming",
            extra={
                "conversation_id": conversation_id,
                "error_type": type(e).__name__,
                "error": str(e)
            }
        )

        yield {
            "event": "message",
            "data": json.dumps({
                "type": "error",
                "message": "An unexpected error occurred during streaming",
                "code": "INTERNAL_ERROR"
            })
        }

    finally:
        # Cleanup: Remove from active streams
        if conversation_id in active_streams:
            del active_streams[conversation_id]
            logger.info(
                "Stream cleanup completed",
                extra={
                    "conversation_id": conversation_id,
                    "active_streams": len(active_streams)
                }
            )


@router.get("/stream/health")
async def stream_health():
    """
    Check streaming service health.

    Returns:
        JSON response with active stream count and capacity
    """
    return JSONResponse(content={
        "status": "ok",
        "active_streams": len(active_streams),
        "max_concurrent_streams": MAX_CONCURRENT_STREAMS,
        "capacity_remaining": MAX_CONCURRENT_STREAMS - len(active_streams),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    })


@router.get("/stream/{conversation_id}")
async def stream_response(conversation_id: str, request: Request):
    """
    Stream LLM response via Server-Sent Events (SSE).

    This endpoint establishes an SSE connection and streams tokens from the LLM
    in real-time. The stream continues until completion, error, or client disconnection.

    Args:
        conversation_id: Unique conversation identifier
        request: FastAPI request object

    Returns:
        EventSourceResponse: SSE stream with token events

    Raises:
        HTTPException: 503 if concurrent stream limit exceeded
        HTTPException: 404 if conversation not found (future: when using Redis)

    SSE Event Format:
        Token event: {"type":"token","content":"text chunk"}
        Completion event: {"type":"done","tokens_used":{"prompt":N,"completion":M}}
        Error event: {"type":"error","message":"error message","code":"ERROR_CODE"}
    """
    # Check concurrent stream limit
    if len(active_streams) >= MAX_CONCURRENT_STREAMS:
        logger.warning(
            "Concurrent stream limit exceeded",
            extra={
                "conversation_id": conversation_id,
                "active_streams": len(active_streams),
                "limit": MAX_CONCURRENT_STREAMS
            }
        )

        raise HTTPException(
            status_code=503,
            detail="Service temporarily unavailable. Too many concurrent streams. Please try again in a moment."
        )

    # Register active stream
    active_streams[conversation_id] = time.time()

    logger.info(
        "SSE connection established",
        extra={
            "conversation_id": conversation_id,
            "client_ip": request.client.host if request.client else "unknown",
            "active_streams": len(active_streams)
        }
    )

    # TODO (Story 2.5): Load conversation state from Redis
    # For now, use a test message
    messages = [
        {"role": "user", "content": "Hello, how are you?"}
    ]

    # Return SSE response
    return EventSourceResponse(
        stream_generator(conversation_id, messages, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )
