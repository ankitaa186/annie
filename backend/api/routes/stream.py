"""
Streaming Route Handler

Handles SSE (Server-Sent Events) streaming for real-time LLM responses
with function calling, tool orchestration, and Redis-based conversation state.
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.llm_client import LLMClient, LLMClientError
from api.mcp_client import MCPClient, MCPClientError, MCPToolError, MCPNetworkError
from api.state import StateManager, StateError
from api.status import StatusContext, emit_status
from api.logging import get_logger

try:
    from langfuse.decorators import observe, langfuse_context
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    def observe(**kwargs):
        def decorator(func):
            return func
        return decorator
    class langfuse_context:
        @staticmethod
        def update_current_observation(**kwargs):
            pass

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["streaming"])

# Track active streams (streaming-specific, separate from session state)
active_streams: Dict[str, float] = {}  # conversation_id -> timestamp
MAX_CONCURRENT_STREAMS = 100


def format_status_frame(message: str) -> Dict[str, Any]:
    """
    Format status message as SSE event.

    Creates a status frame that will be interleaved with token/done/error frames
    during streaming. Status frames follow the same SSE format as existing frames.

    Args:
        message: Formatted status message (typically with icon prefix)

    Returns:
        SSE event dictionary with type "status"

    Example:
        >>> format_status_frame("🔄 Annie is thinking...")
        {"event": "message", "data": '{"type":"status","message":"🔄 Annie is thinking..."}'}
    """
    return {
        "event": "message",
        "data": json.dumps({"type": "status", "message": message})
    }


@observe(name="llm_streaming", as_type="span")
async def stream_generator(
    conversation_id: str,
    messages: List[Dict[str, Any]],
    request: Request,
    state_manager: Optional[StateManager] = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generate SSE events from LLM streaming response with tool orchestration.

    Langfuse @observe() decorator automatically traces:
    - Input: conversation_id, messages (truncated), request metadata
    - Output: chunk_count, duration, completion_status
    - Duration and errors

    Handles:
    - Tool schema fetching from MCP server
    - Function calling with LLM
    - Tool execution via MCP client
    - Multi-step tool calling (max 5 iterations)
    - Error handling for tool failures
    - Storing assistant response in Redis after completion
    - Status emission via StatusContext (e.g., "Annie is thinking...")

    Args:
        conversation_id: Unique conversation identifier
        messages: List of chat messages to send to LLM
        request: FastAPI request object for disconnection detection
        state_manager: Optional StateManager for storing assistant response

    Yields:
        SSE event dictionaries with event="message" and data containing:
        - Status frame: {"type": "status", "message": "..."}
        - Token frame: {"type": "token", "content": "..."}
        - Done frame: {"type": "done", "tokens_used": {...}}
        - Error frame: {"type": "error", "message": "...", "code": "..."}
    """
    start_time = time.time()
    first_token_sent = False
    max_tool_iterations = 10
    assistant_response_content = []  # Accumulate assistant response for storage
    chunk_count = 0  # Track number of chunks streamed

    # Update observation metadata (decorator handles all tracing)
    if LANGFUSE_AVAILABLE:
        try:
            langfuse_context.update_current_observation(
                metadata={
                    "conversation_id": conversation_id,
                    "message_count": len(messages)
                }
            )
        except Exception:
            pass  # Fire-and-forget

    # Create async queue for status messages
    # StatusContext will write to this queue, and we'll drain it before each event
    status_queue: asyncio.Queue[str] = asyncio.Queue()

    def status_callback(message: str) -> None:
        """Callback for StatusContext to queue status messages for SSE emission."""
        try:
            status_queue.put_nowait(message)
        except asyncio.QueueFull:
            # Queue should never fill (we drain before each event), but handle gracefully
            logger.warning(
                "Status queue full, dropping message",
                extra={
                    "conversation_id": conversation_id,
                    "message": message
                }
            )

    try:
        # Create clients and initialize status context
        async with (
            LLMClient() as llm_client,
            MCPClient() as mcp_client,
            StatusContext(conversation_id, status_callback)
        ):
            # NOTE: Initial "thinking" status is already sent by telegram_bot
            # before connecting to SSE stream. Emitting here causes duplicate
            # which Telegram rejects with "Message is not modified" error.
            # emit_status("Annie is thinking...")

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

            # IMPORTANT: Gemini handles tool execution internally during streaming
            # Skip the OpenAI-style tool orchestration loop for Gemini providers
            if llm_client.primary_provider_name == "gemini-3-pro-preview":
                # Gemini: Stream directly with mcp_client - tools are handled automatically
                logger.info(
                    "Using Gemini streaming (internal tool handling)",
                    extra={
                        "conversation_id": conversation_id,
                        "provider": "gemini-3-pro-preview"
                    }
                )

                # Emit status: Starting LLM composition
                emit_status("Composing response...", icon="🧠")

                async for event in llm_client.stream_chat_completion(
                    conversation_messages,
                    tools=tools,
                    mcp_client=mcp_client
                ):
                    # Check for client disconnection
                    if await request.is_disconnected():
                        logger.info(
                            "Client disconnected during stream",
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

                    # Accumulate assistant response content and track chunks
                    if event.get("type") == "token":
                        assistant_response_content.append(event.get("content", ""))
                        chunk_count += 1

                    # Handle Redis save BEFORE yielding done event
                    if event.get("type") == "done":
                        duration_ms = int((time.time() - start_time) * 1000)

                        # Emit status for Grok Live Search if used
                        sources_used = event.get("sources_used", 0)
                        if sources_used > 0:
                            emit_status(f"Found {sources_used} sources", icon="✅")
                            # Drain status queue immediately to capture Live Search status
                            while not status_queue.empty():
                                try:
                                    status_msg = status_queue.get_nowait()
                                    yield format_status_frame(status_msg)
                                except asyncio.QueueEmpty:
                                    break

                        logger.info(
                            "Stream completed successfully",
                            extra={
                                "conversation_id": conversation_id,
                                "duration_ms": duration_ms,
                                "tool_calls": event.get("tool_calls_made", 0),
                                "tokens": event.get("tokens_used", {})
                            }
                        )

                        # Store assistant response in Redis BEFORE yielding done event
                        if state_manager and assistant_response_content:
                            if await request.is_disconnected():
                                logger.info(
                                    "Client disconnected, skipping Redis save",
                                    extra={"conversation_id": conversation_id}
                                )
                            else:
                                full_response = "".join(assistant_response_content)
                                assistant_message = {
                                    "role": "assistant",
                                    "content": full_response
                                }
                                try:
                                    await state_manager.add_message(conversation_id, assistant_message)
                                    logger.info(
                                        "Assistant response stored in Redis",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "response_length": len(full_response)
                                        }
                                    )
                                except asyncio.CancelledError:
                                    logger.warning(
                                        "Redis save cancelled (unexpected - should not occur)",
                                        extra={"conversation_id": conversation_id}
                                    )
                                    raise
                                except StateError as e:
                                    logger.error(
                                        "Failed to store assistant response",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "error": str(e)
                                        },
                                        exc_info=True
                                    )

                    # Drain status queue before yielding event (ensures status frames are interleaved)
                    while not status_queue.empty():
                        try:
                            status_msg = status_queue.get_nowait()
                            yield format_status_frame(status_msg)
                        except asyncio.QueueEmpty:
                            break

                    # Yield SSE event
                    yield {
                        "event": "message",
                        "data": json.dumps(event)
                    }

                    # If error or completion, stop streaming
                    if event.get("type") in ["error", "done"]:
                        break

                # Gemini streaming complete - exit generator
                return

            # OpenAI/Grok: Use traditional tool orchestration loop
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
                        },
                        exc_info=True
                    )

                    # Drain status queue before yielding error event
                    while not status_queue.empty():
                        try:
                            status_msg = status_queue.get_nowait()
                            yield format_status_frame(status_msg)
                        except asyncio.QueueEmpty:
                            break

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

                # Debug: Log the full response to understand why tool wasn't called
                logger.debug(
                    "LLM response analysis",
                    extra={
                        "conversation_id": conversation_id,
                        "has_tool_calls": bool(tool_calls),
                        "tool_calls_count": len(tool_calls) if tool_calls else 0,
                        "message_content": message.get("content", "")[:200] if message.get("content") else None,
                        "finish_reason": response.get("choices", [{}])[0].get("finish_reason"),
                        "tools_provided": len(tools) if tools else 0
                    }
                )

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

                    # Emit status: Starting LLM composition
                    emit_status("Composing response...", icon="🧠")

                    # Stream tokens from LLM
                    async for event in llm_client.stream_chat_completion(
                        conversation_messages,
                        tools=tools,
                        mcp_client=mcp_client
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

                        # Accumulate assistant response content and track chunks
                        if event.get("type") == "token":
                            assistant_response_content.append(event.get("content", ""))
                            chunk_count += 1

                        # If error or completion, handle Redis save BEFORE yielding done event
                        # This prevents SSE framework cleanup from cancelling the Redis operation
                        if event.get("type") == "done":
                            duration_ms = int((time.time() - start_time) * 1000)

                            # Emit status for Grok Live Search if used
                            sources_used = event.get("sources_used", 0)
                            if sources_used > 0:
                                emit_status(f"Found {sources_used} sources", icon="✅")
                                # Drain status queue immediately to capture Live Search status
                                while not status_queue.empty():
                                    try:
                                        status_msg = status_queue.get_nowait()
                                        yield format_status_frame(status_msg)
                                    except asyncio.QueueEmpty:
                                        break

                            logger.info(
                                "Stream completed successfully",
                                extra={
                                    "conversation_id": conversation_id,
                                    "duration_ms": duration_ms,
                                    "tool_calls": tool_call_count,
                                    "tokens": event.get("tokens_used", {})
                                }
                            )

                            # Store assistant response in Redis BEFORE yielding done event
                            # This prevents cancellation by SSE framework's cancel_on_finish task
                            if state_manager and assistant_response_content:
                                # Check if client disconnected before saving
                                if await request.is_disconnected():
                                    logger.info(
                                        "Client disconnected, skipping Redis save",
                                        extra={"conversation_id": conversation_id}
                                    )
                                else:
                                    full_response = "".join(assistant_response_content)
                                    assistant_message = {
                                        "role": "assistant",
                                        "content": full_response
                                    }
                                    try:
                                        await state_manager.add_message(conversation_id, assistant_message)
                                        logger.info(
                                            "Assistant response stored in Redis",
                                            extra={
                                                "conversation_id": conversation_id,
                                                "response_length": len(full_response)
                                            }
                                        )
                                    except asyncio.CancelledError:
                                        # Shouldn't happen now since we save before yielding, but handle gracefully
                                        logger.warning(
                                            "Redis save cancelled (unexpected - should not occur)",
                                            extra={"conversation_id": conversation_id}
                                        )
                                        raise  # Re-raise to allow proper cancellation
                                    except StateError as e:
                                        logger.error(
                                            "Failed to store assistant response",
                                            extra={
                                                "conversation_id": conversation_id,
                                                "error": str(e)
                                            },
                                            exc_info=True
                                        )

                        # Drain status queue before yielding event (ensures status frames are interleaved)
                        while not status_queue.empty():
                            try:
                                status_msg = status_queue.get_nowait()
                                yield format_status_frame(status_msg)
                            except asyncio.QueueEmpty:
                                break

                        # Yield SSE event (after Redis save for done events)
                        yield {
                            "event": "message",
                            "data": json.dumps(event)
                        }

                        # If error or completion, stop streaming after yielding
                        if event.get("type") in ["error", "done"]:
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
                        # Fire-and-forget for store_memory (non-blocking)
                        if function_name == "store_memory":
                            # Create background task with exception handling
                            async def _store_memory_background():
                                try:
                                    await mcp_client.call_tool(function_name, arguments)
                                    logger.info(
                                        "Background memory storage completed successfully",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "tool_name": function_name,
                                            "tool_call_id": tool_call_id
                                        }
                                    )
                                except Exception as e:
                                    logger.error(
                                        "Background memory storage failed (will retry via queue)",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "tool_name": function_name,
                                            "tool_call_id": tool_call_id,
                                            "error": str(e),
                                            "error_type": type(e).__name__
                                        },
                                        exc_info=True
                                    )

                            # Launch background task
                            asyncio.create_task(_store_memory_background())

                            # Return immediate success response
                            tool_result = {
                                "status": "queued",
                                "message": "Memory storage initiated in background"
                            }

                            logger.info(
                                "Memory storage queued (fire-and-forget)",
                                extra={
                                    "conversation_id": conversation_id,
                                    "tool_name": function_name,
                                    "tool_call_id": tool_call_id
                                }
                            )
                        else:
                            # All other tools: await completion
                            # Emit status for memory and profile operations
                            if function_name == "retrieve_memories":
                                emit_status("Retrieving your memories...", icon="🔍")
                            elif function_name == "get_user_profile":
                                emit_status("Loading your profile...", icon="👤")

                            tool_result = await mcp_client.call_tool(function_name, arguments)

                            # Emit completion status for memory and profile operations
                            if function_name == "retrieve_memories":
                                memory_count = tool_result.get("memory_count", 0)
                                if memory_count > 0:
                                    emit_status(f"Found {memory_count} relevant memories", icon="✅")
                                else:
                                    emit_status("No relevant memories found", icon="✅")
                            elif function_name == "get_user_profile":
                                completeness = tool_result.get("completeness", 0)
                                emit_status(f"Profile loaded ({completeness}% complete)", icon="✅")

                        # Add tool result to conversation
                        tool_content = json.dumps(tool_result)
                        conversation_messages.append({
                            "role": "tool",
                            "content": tool_content,
                            "tool_call_id": tool_call_id
                        })

                        # DEBUG: Log tool result content (first 500 chars)
                        logger.debug(
                            f"Tool result added to conversation (content preview): {tool_content[:500]}",
                            extra={
                                "conversation_id": conversation_id,
                                "tool_name": function_name,
                                "tool_call_id": tool_call_id,
                                "result_length": len(tool_content)
                            }
                        )

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
                            },
                            exc_info=True
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
                    # Emit status: Starting LLM composition (max iterations)
                    emit_status("Composing response...", icon="🧠")

                    # Stream final response anyway
                    async for event in llm_client.stream_chat_completion(conversation_messages, tools=tools, mcp_client=mcp_client):
                        if await request.is_disconnected():
                            break

                        # Accumulate assistant response content and track chunks
                        if event.get("type") == "token":
                            assistant_response_content.append(event.get("content", ""))
                            chunk_count += 1

                        # Handle Redis save BEFORE yielding done event (prevents cancellation)
                        if event.get("type") == "done":
                            # Emit status for Grok Live Search if used
                            sources_used = event.get("sources_used", 0)
                            if sources_used > 0:
                                emit_status(f"Found {sources_used} sources", icon="✅")
                                # Drain status queue immediately to capture Live Search status
                                while not status_queue.empty():
                                    try:
                                        status_msg = status_queue.get_nowait()
                                        yield format_status_frame(status_msg)
                                    except asyncio.QueueEmpty:
                                        break

                            # Store assistant response in Redis before yielding
                            if state_manager and assistant_response_content:
                                full_response = "".join(assistant_response_content)
                                assistant_message = {
                                    "role": "assistant",
                                    "content": full_response
                                }
                                try:
                                    await state_manager.add_message(conversation_id, assistant_message)
                                    logger.info(
                                        "Assistant response stored in Redis (max iterations)",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "response_length": len(full_response)
                                        }
                                    )
                                except asyncio.CancelledError:
                                    # Shouldn't happen now since we save before yielding
                                    logger.warning(
                                        "Redis save cancelled (unexpected - max iterations)",
                                        extra={"conversation_id": conversation_id}
                                    )
                                    raise
                                except StateError as e:
                                    logger.error(
                                        "Failed to store assistant response (max iterations)",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "error": str(e)
                                        },
                                        exc_info=True
                                    )

                        # Drain status queue before yielding event (max iterations path)
                        while not status_queue.empty():
                            try:
                                status_msg = status_queue.get_nowait()
                                yield format_status_frame(status_msg)
                            except asyncio.QueueEmpty:
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
            },
            exc_info=True
        )

        # Drain status queue before yielding error event (exception handler)
        while not status_queue.empty():
            try:
                status_msg = status_queue.get_nowait()
                yield format_status_frame(status_msg)
            except asyncio.QueueEmpty:
                break

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
            },
            exc_info=True
        )

        # Drain status queue before yielding error event (generic exception handler)
        while not status_queue.empty():
            try:
                status_msg = status_queue.get_nowait()
                yield format_status_frame(status_msg)
            except asyncio.QueueEmpty:
                break

        yield {
            "event": "message",
            "data": json.dumps({
                "type": "error",
                "message": "An unexpected error occurred during streaming",
                "code": "INTERNAL_ERROR"
            })
        }

    finally:
        # Update observation output (decorator handles span end automatically)
        if LANGFUSE_AVAILABLE:
            try:
                duration_ms = int((time.time() - start_time) * 1000)
                langfuse_context.update_current_observation(
                    output={
                        "chunk_count": chunk_count,
                        "duration_ms": duration_ms,
                        "completion_status": "completed" if chunk_count > 0 else "failed"
                    }
                )
            except Exception:
                pass  # Fire-and-forget

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
@observe(name="stream_request", as_type="trace")
async def stream_response(conversation_id: str, request: Request):
    """
    Stream LLM response via Server-Sent Events (SSE).

    Langfuse @observe() decorator automatically traces:
    - Input: conversation_id, request metadata
    - Output: EventSourceResponse (SSE stream)
    - Duration, errors, and nested spans
    - Session linking via conversation_id

    This endpoint establishes an SSE connection, loads conversation context from Redis,
    and streams tokens from the LLM in real-time. After streaming completes, stores
    the assistant's response in conversation history.

    Args:
        conversation_id: Unique conversation identifier
        request: FastAPI request object

    Returns:
        EventSourceResponse: SSE stream with token events

    Raises:
        HTTPException: 503 if concurrent stream limit exceeded
        HTTPException: 500 if state management fails

    SSE Event Format:
        Status event: {"type":"status","message":"🔄 Annie is thinking..."}
        Token event: {"type":"token","content":"text chunk"}
        Completion event: {"type":"done","tokens_used":{"prompt":N,"completion":M}}
        Error event: {"type":"error","message":"error message","code":"ERROR_CODE"}
    """
    # Update trace with session_id to link to chat_request trace (decorator handles trace creation)
    if LANGFUSE_AVAILABLE:
        try:
            langfuse_context.update_current_trace(
                session_id=conversation_id,
                user_id="system",  # Will update with actual user_id once loaded from state
                metadata={"endpoint": "/stream"}
            )
        except Exception:
            pass  # Fire-and-forget

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

    try:
        # Create StateManager to load conversation context
        state_manager = StateManager()

        # Get user_id for this conversation (needed for memory tool calls)
        user_id = await state_manager.get_user_id_for_conversation(conversation_id)

        # Update trace with actual user_id (decorator handles trace management)
        if LANGFUSE_AVAILABLE and user_id:
            try:
                langfuse_context.update_current_trace(user_id=user_id)
                logger.info(
                    f"[LANGFUSE] Updated stream trace with user_id: {user_id}",
                    extra={"conversation_id": conversation_id, "user_id": user_id}
                )
            except Exception:
                pass  # Fire-and-forget

        # Get platform from session if available (for platform-specific formatting)
        platform = "api"  # Default platform
        if user_id:
            session = await state_manager.get_session(user_id)
            if session:
                platform = session.get("platform", "api")

        # Load user profile from Redis cache (set by chat endpoint)
        profile = None
        if user_id:
            try:
                profile_key = f"profile_cache:{conversation_id}"
                profile_data = await state_manager.redis_client.get(profile_key)
                if profile_data:
                    import json
                    profile = json.loads(profile_data)
                    logger.info(
                        "Profile loaded for system prompt",
                        extra={
                            "conversation_id": conversation_id,
                            "user_id": user_id,
                            "completeness": profile.get("completeness", 0)
                        }
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to load profile for system prompt, continuing without: {str(e)}",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id
                    }
                )

        # Load user portfolio from cache or refresh (Story 10.3)
        portfolio = None
        if user_id:
            try:
                from api.portfolio_context import PortfolioManager
                portfolio_manager = PortfolioManager(redis_client=state_manager.redis_client)
                portfolio = await portfolio_manager.get_portfolio(user_id, refresh_if_empty=True)
                if portfolio and portfolio.get("total_holdings", 0) > 0:
                    logger.info(
                        "Portfolio loaded for system prompt",
                        extra={
                            "conversation_id": conversation_id,
                            "user_id": user_id,
                            "holdings_count": portfolio.get("total_holdings", 0),
                            "cached": portfolio.get("cached", False)
                        }
                    )
            except Exception as e:
                logger.warning(
                    f"Failed to load portfolio for system prompt, continuing without: {str(e)}",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id
                    }
                )

        # Load proactive context from Redis cache (Story 13.10 - Feedback Handler)
        # If user is responding to a recent proactive message, include context in system prompt
        proactive_context = None
        if user_id:
            try:
                proactive_context_key = f"proactive_context:{conversation_id}"
                proactive_context_data = await state_manager.redis_client.get(proactive_context_key)
                if proactive_context_data:
                    import json
                    proactive_context = json.loads(proactive_context_data)
                    logger.info(
                        "Proactive context loaded for feedback handling",
                        extra={
                            "conversation_id": conversation_id,
                            "user_id": user_id,
                            "trigger_id": proactive_context.get("trigger_id"),
                            "intent_name": proactive_context.get("trigger_details", {}).get("intent_name", "Unknown")
                        }
                    )

                    # Clear context after loading (one-time use)
                    await state_manager.redis_client.delete(proactive_context_key)

            except Exception as e:
                logger.warning(
                    f"Failed to load proactive context, continuing without: {str(e)}",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "error_type": type(e).__name__
                    }
                )

        # Build system message with user_id, profile, portfolio, proactive_context, and platform-specific formatting
        from api.prompts import build_system_prompt

        system_message = build_system_prompt(
            user_id=user_id,
            platform=platform,
            include_tool_instructions=True,
            profile=profile,
            portfolio=portfolio,
            proactive_context=proactive_context
        ) if user_id else None

        logger.debug(
            "System message built",
            extra={
                "conversation_id": conversation_id,
                "user_id": user_id,
                "platform": platform,
                "has_system_message": system_message is not None
            }
        )

        # Load conversation history from Redis with system message
        messages = await state_manager.build_llm_context(conversation_id, system_message)

        if not messages:
            # No conversation history found - this might be a new conversation
            # or the first message hasn't been added yet
            logger.warning(
                "No conversation history found, starting with empty context",
                extra={"conversation_id": conversation_id}
            )
            messages = []

        logger.info(
            "Loaded conversation context from Redis",
            extra={
                "conversation_id": conversation_id,
                "message_count": len(messages),
                "has_user_id": user_id is not None
            }
        )

        # Return SSE response with state manager passed to generator
        return EventSourceResponse(
            stream_generator(conversation_id, messages, request, state_manager),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )

    except StateError as e:
        # Decorator automatically captures exceptions, just log it
        logger.error(
            "State management error in stream endpoint",
            extra={
                "conversation_id": conversation_id,
                "error": str(e)
            },
            exc_info=True
        )

        # Graceful degradation: continue with empty messages
        logger.warning(
            "Continuing with empty context due to state error (degraded mode)",
            extra={"conversation_id": conversation_id}
        )

        return EventSourceResponse(
            stream_generator(conversation_id, [], request, None),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"
            }
        )
