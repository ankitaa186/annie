"""
Streaming Route Handler

Handles SSE (Server-Sent Events) streaming for real-time LLM responses
with function calling, tool orchestration, and Redis-based conversation state.
"""

import asyncio
import json
import time
import uuid
from typing import AsyncGenerator, Dict, Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.llm_client import LLMClient, LLMClientError
from api.constants import MODELS_WITH_INTERNAL_TOOL_HANDLING
from api.mcp_client import MCPClient, MCPClientError, MCPToolError, MCPNetworkError
from api.models.file_attachment import FileAttachment, get_files_metadata
from api.state import StateManager, StateError
from api.status import StatusContext, emit_status
from api.logging import get_logger
from api.utils import (
    inject_user_id,
    invalidate_profile_cache_if_needed,
    strip_base64_from_tool_result,
)

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


def format_media_frame(
    media_type: str,
    source: str,
    source_type: str = "url",
    caption: Optional[str] = None,
    filename: Optional[str] = None,
    duration: Optional[int] = None,
    width: Optional[int] = None,
    height: Optional[int] = None
) -> Dict[str, Any]:
    """
    Format media as SSE event for sending to Telegram client.

    Creates a media frame that will be processed by the Telegram bot's
    media_sender module to send photos, videos, or other media to users.

    Args:
        media_type: Type of media ("photo", "video", "animation", "voice", "video_note")
        source: Media source (URL, base64 data, or Telegram file_id)
        source_type: Type of source ("url", "base64", "file_id")
        caption: Optional caption for the media (supports HTML formatting)
        filename: Optional filename for the media
        duration: Optional duration in seconds (for video/voice)
        width: Optional width in pixels (for video)
        height: Optional height in pixels (for video)

    Returns:
        SSE event dictionary with type "media"

    Example:
        >>> format_media_frame("photo", "https://example.com/image.jpg", caption="A beautiful sunset")
        {"event": "message", "data": '{"type":"media","media_type":"photo","source":"...","source_type":"url","caption":"..."}'}
    """
    frame = {
        "type": "media",
        "media_type": media_type,
        "source": source,
        "source_type": source_type
    }

    # Add optional fields if provided
    if caption:
        frame["caption"] = caption
    if filename:
        frame["filename"] = filename
    if duration is not None:
        frame["duration"] = duration
    if width is not None:
        frame["width"] = width
    if height is not None:
        frame["height"] = height

    return {
        "event": "message",
        "data": json.dumps(frame)
    }


def format_media_group_frame(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Format media group (album) as SSE event for sending to Telegram client.

    Creates a media_group frame that will be processed by the Telegram bot's
    media_sender module to send albums (multiple photos/videos) to users.
    Albums can contain 2-10 items and support only photos and videos.

    Args:
        items: List of media items, each with:
            - media_type: "photo" or "video"
            - source: Media source (URL, base64, or file_id)
            - source_type: Type of source ("url", "base64", "file_id")
            - caption: Optional caption (only first item's caption is shown)

    Returns:
        SSE event dictionary with type "media_group"

    Example:
        >>> items = [
        ...     {"media_type": "photo", "source": "https://example.com/1.jpg", "source_type": "url"},
        ...     {"media_type": "photo", "source": "https://example.com/2.jpg", "source_type": "url", "caption": "Photos from today"}
        ... ]
        >>> format_media_group_frame(items)
        {"event": "message", "data": '{"type":"media_group","items":[...]}'}
    """
    return {
        "event": "message",
        "data": json.dumps({
            "type": "media_group",
            "items": items
        })
    }


def extract_media_from_tool_result(tool_result: Any, tool_name: str) -> Optional[Dict[str, Any]]:
    """
    Extract media data from a tool result if it contains media to send.

    Checks if a tool result contains media that should be sent to the user
    (e.g., generated images, fetched photos, etc.). Returns media frame data
    if found, None otherwise.

    Tool results should include media in one of these formats:
    1. Direct media object: {"media": {"type": "photo", "url": "...", "caption": "..."}}
    2. Image generation result: {"image_url": "...", "prompt": "..."} (for image gen tools)
    3. Media list: {"media_items": [{"type": "photo", "url": "..."}, ...]}
    4. Browser screenshot: {"results": [{"action": "screenshot", "data": {"base64": "..."}}]}

    Args:
        tool_result: The result returned by the tool
        tool_name: Name of the tool that returned the result

    Returns:
        Dict with media frame data, or None if no media found
    """
    if not isinstance(tool_result, dict):
        return None

    # Format 1: Direct media object
    if "media" in tool_result:
        media = tool_result["media"]
        if isinstance(media, dict) and "type" in media:
            return {
                "single": True,
                "media_type": media.get("type", "photo"),
                "source": media.get("url") or media.get("source") or media.get("data"),
                "source_type": media.get("source_type", "url"),
                "caption": media.get("caption"),
                "filename": media.get("filename"),
                "duration": media.get("duration"),
                "width": media.get("width"),
                "height": media.get("height")
            }

    # Format 2: Image generation result (common pattern for DALL-E, Stable Diffusion, etc.)
    if tool_name in ["generate_image", "create_image", "dalle", "stable_diffusion", "image_generation"]:
        if "image_url" in tool_result:
            return {
                "single": True,
                "media_type": "photo",
                "source": tool_result["image_url"],
                "source_type": "url",
                "caption": tool_result.get("prompt") or tool_result.get("caption")
            }
        if "image_data" in tool_result or "base64" in tool_result:
            return {
                "single": True,
                "media_type": "photo",
                "source": tool_result.get("image_data") or tool_result.get("base64"),
                "source_type": "base64",
                "caption": tool_result.get("prompt") or tool_result.get("caption")
            }
        if "images" in tool_result and isinstance(tool_result["images"], list):
            # Multiple images generated
            items = []
            for i, img in enumerate(tool_result["images"]):
                if isinstance(img, dict):
                    items.append({
                        "media_type": "photo",
                        "source": img.get("url") or img.get("data"),
                        "source_type": "base64" if img.get("data") else "url",
                        "caption": tool_result.get("prompt") if i == 0 else None
                    })
                elif isinstance(img, str):
                    # Assume URL if string
                    items.append({
                        "media_type": "photo",
                        "source": img,
                        "source_type": "url",
                        "caption": tool_result.get("prompt") if i == 0 else None
                    })
            if items:
                return {"single": False, "items": items}

    # Format 3: Media list (for tools that return multiple media items)
    if "media_items" in tool_result:
        items = []
        for item in tool_result["media_items"]:
            if isinstance(item, dict):
                items.append({
                    "media_type": item.get("type", "photo"),
                    "source": item.get("url") or item.get("source") or item.get("data"),
                    "source_type": item.get("source_type", "url"),
                    "caption": item.get("caption")
                })
        if items:
            if len(items) == 1:
                return {"single": True, **items[0]}
            return {"single": False, "items": items}

    # Format 4: Browser screenshot results
    # browser_action returns {"results": [{"action": "screenshot", "data": {"base64": "...", "width": .., "height": ..}}]}
    if tool_name == "browser_action" and isinstance(tool_result.get("results"), list):
        screenshots = []
        for r in tool_result["results"]:
            if (
                isinstance(r, dict)
                and r.get("action") == "screenshot"
                and r.get("status") == "success"
                and isinstance(r.get("data"), dict)
                and r["data"].get("base64")
            ):
                screenshots.append({
                    "media_type": "photo",
                    "source": r["data"]["base64"],
                    "source_type": "base64",
                    "width": r["data"].get("width"),
                    "height": r["data"].get("height"),
                })
        if len(screenshots) == 1:
            return {"single": True, **screenshots[0]}
        elif screenshots:
            return {"single": False, "items": screenshots}

    return None


# ---------------------------------------------------------------------------
# Redis offloading for large base64 media
# ---------------------------------------------------------------------------
MEDIA_OFFLOAD_THRESHOLD = 64 * 1024   # 64 KB
MEDIA_OFFLOAD_TTL = 300               # 5 minutes


async def offload_base64_to_redis(
    media_data: Dict[str, Any],
    redis_client,
    conversation_id: str
) -> Dict[str, Any]:
    """
    Replace large base64 sources with Redis key references.

    If a media item's source_type is "base64" and the payload exceeds
    MEDIA_OFFLOAD_THRESHOLD, the base64 string is stored in Redis under
    a unique key and the media_data dict is mutated to carry a small
    ``redis_ref`` source instead of the full blob.  This keeps SSE frames
    small and avoids aiohttp chunk-size errors.

    On Redis failure the original media_data is returned unchanged so that
    the existing 2 MB read_bufsize safety net can handle it.

    Args:
        media_data: Dict from extract_media_from_tool_result
        redis_client: An async Redis client (e.g. ``state_manager.redis_client``)
        conversation_id: Used as part of the Redis key namespace

    Returns:
        The (possibly mutated) media_data dict.
    """
    async def _offload_item(item: Dict[str, Any]) -> None:
        """Offload a single item dict in-place if it qualifies."""
        if item.get("source_type") != "base64":
            return
        source = item.get("source", "")
        if len(source) <= MEDIA_OFFLOAD_THRESHOLD:
            return
        redis_key = f"media:{conversation_id}:{uuid.uuid4()}"
        try:
            await redis_client.set(redis_key, source, ex=MEDIA_OFFLOAD_TTL)
            item["source"] = redis_key
            item["source_type"] = "redis_ref"
            logger.info(
                "Large base64 media offloaded to Redis",
                extra={
                    "conversation_id": conversation_id,
                    "redis_key": redis_key,
                    "original_size": len(source),
                    "event": "media_offloaded"
                }
            )
        except Exception as exc:
            logger.warning(
                "Failed to offload media to Redis, leaving inline",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "event": "media_offload_failed"
                }
            )

    try:
        if media_data.get("single", True):
            await _offload_item(media_data)
        else:
            for item in media_data.get("items", []):
                await _offload_item(item)
    except Exception as exc:
        logger.warning(
            "Unexpected error during media offload, leaving inline",
            extra={
                "conversation_id": conversation_id,
                "error": str(exc),
                "event": "media_offload_unexpected_error"
            }
        )

    return media_data


def build_media_sse_frames(
    media_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Build SSE frame(s) from extracted media data.

    Converts the output of extract_media_from_tool_result into one or more
    SSE event dicts ready to yield to the client.

    Args:
        media_data: Dict from extract_media_from_tool_result (must not be None)

    Returns:
        List of SSE event dicts (typically 1 element, or 1 media_group frame)
    """
    if media_data.get("single", True):
        return [format_media_frame(
            media_type=media_data.get("media_type", "photo"),
            source=media_data.get("source"),
            source_type=media_data.get("source_type", "url"),
            caption=media_data.get("caption"),
            filename=media_data.get("filename"),
            duration=media_data.get("duration"),
            width=media_data.get("width"),
            height=media_data.get("height")
        )]
    else:
        return [format_media_group_frame(media_data.get("items", []))]


@observe(name="llm_streaming", as_type="span")
async def stream_generator(
    conversation_id: str,
    messages: List[Dict[str, Any]],
    request: Request,
    state_manager: Optional[StateManager] = None,
    files: Optional[List[FileAttachment]] = None,
    user_id: Optional[str] = None
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
    - Multimodal file processing (images, documents, spreadsheets)

    Args:
        conversation_id: Unique conversation identifier
        messages: List of chat messages to send to LLM
        request: FastAPI request object for disconnection detection
        state_manager: Optional StateManager for storing assistant response
        files: Optional list of file attachments for multimodal processing
        user_id: Optional user ID to inject into tool calls (prevents LLM from using wrong IDs)

    Yields:
        SSE event dictionaries with event="message" and data containing:
        - Status frame: {"type": "status", "message": "..."}
        - Token frame: {"type": "token", "content": "..."}
        - Done frame: {"type": "done", "tokens_used": {...}}
        - Error frame: {"type": "error", "message": "...", "code": "..."}
    """
    start_time = time.time()
    first_token_sent = False
    max_tool_iterations = 20
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
            if llm_client.primary_provider_name in MODELS_WITH_INTERNAL_TOOL_HANDLING:
                # Gemini: Stream directly with mcp_client - tools are handled automatically
                logger.info(
                    "Using Gemini streaming (internal tool handling)",
                    extra={
                        "conversation_id": conversation_id,
                        "provider": llm_client.primary_provider_name
                    }
                )

                # Emit status: Starting LLM composition
                if files:
                    emit_status("Analyzing your files...", icon="📎")
                else:
                    emit_status("Composing response...", icon="🧠")

                async for event in llm_client.stream_chat_completion(
                    conversation_messages,
                    tools=tools,
                    mcp_client=mcp_client,
                    files=files,
                    user_id=user_id,
                    conversation_id=conversation_id,
                    state_manager=state_manager
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

                    # Persist Gemini tool calls to Redis (intercept-only, not forwarded to client)
                    if event.get("type") == "tool_persist_calls" and state_manager:
                        try:
                            await state_manager.add_message(conversation_id, {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": tc["id"],
                                        "type": "function",
                                        "function": {
                                            "name": tc["name"],
                                            "arguments": tc.get("arguments", "{}")
                                        }
                                    }
                                    for tc in event.get("tool_calls", [])
                                ],
                                "is_tool_call": True
                            })
                            tool_names = [tc["name"] for tc in event.get("tool_calls", [])]
                            logger.info(
                                "Gemini tool calls persisted to Redis",
                                extra={
                                    "conversation_id": conversation_id,
                                    "tool_names": tool_names,
                                    "tool_count": len(tool_names)
                                }
                            )
                        except Exception as e:
                            logger.warning(
                                "Failed to persist Gemini tool calls to Redis",
                                extra={
                                    "conversation_id": conversation_id,
                                    "error": str(e)
                                }
                            )
                        continue  # Don't forward persistence events to SSE client

                    if event.get("type") == "tool_persist_result":
                        tool_name = event.get("tool_name", "")
                        result_content = event.get("result_content", "")

                        if state_manager:
                            try:
                                await state_manager.add_message(conversation_id, {
                                    "role": "tool",
                                    "content": result_content,
                                    "tool_call_id": event.get("tool_call_id", ""),
                                    "tool_name": tool_name,
                                    "is_tool_result": True
                                })
                                logger.info(
                                    "Gemini tool result persisted to Redis",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "tool_name": tool_name
                                    }
                                )
                            except Exception as e:
                                logger.warning(
                                    "Failed to persist Gemini tool result to Redis",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "tool_name": tool_name,
                                        "error": str(e)
                                    }
                                )

                        # Check if tool result contains media to send to user
                        try:
                            tool_result = json.loads(result_content) if isinstance(result_content, str) else result_content
                        except (json.JSONDecodeError, TypeError):
                            tool_result = None

                        # Invalidate profile cache after successful update_user_profile
                        # (no-op for other tools; defensive against Redis failures)
                        if state_manager and isinstance(tool_result, dict):
                            await invalidate_profile_cache_if_needed(
                                tool_name,
                                tool_result,
                                user_id,
                                state_manager.redis_client,
                                logger,
                            )

                        if isinstance(tool_result, dict):
                            media_data = extract_media_from_tool_result(tool_result, tool_name)
                            if media_data:
                                if state_manager:
                                    media_data = await offload_base64_to_redis(
                                        media_data, state_manager.redis_client, conversation_id
                                    )
                                logger.info(
                                    "Tool returned media to send",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "tool_name": tool_name,
                                        "is_single": media_data.get("single", True),
                                        "media_type": media_data.get("media_type", "unknown"),
                                        "event": "tool_media_emit"
                                    }
                                )
                                for frame in build_media_sse_frames(media_data):
                                    yield frame

                        continue  # Don't forward persistence events to SSE client

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
                    if files:
                        emit_status("Analyzing your files...", icon="📎")
                    else:
                        emit_status("Composing response...", icon="🧠")

                    # Stream tokens from LLM
                    async for event in llm_client.stream_chat_completion(
                        conversation_messages,
                        tools=tools,
                        mcp_client=mcp_client,
                        files=files,
                        user_id=user_id,
                        conversation_id=conversation_id,
                        state_manager=state_manager
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

                # Persist tool call message to Redis for context continuity
                if state_manager:
                    try:
                        tool_call_message = {
                            "role": "assistant",
                            "content": message.get("content", "") or "",
                            "tool_calls": [
                                {
                                    "id": tc.get("id", ""),
                                    "type": "function",
                                    "function": {
                                        "name": tc.get("function", {}).get("name", ""),
                                        "arguments": tc.get("function", {}).get("arguments", "{}")
                                    }
                                }
                                for tc in tool_calls
                            ],
                            "is_tool_call": True
                        }
                        await state_manager.add_message(conversation_id, tool_call_message)
                    except Exception as e:
                        logger.warning(
                            "Failed to persist tool call message to Redis",
                            extra={
                                "conversation_id": conversation_id,
                                "error": str(e),
                                "tool_count": len(tool_calls)
                            }
                        )

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

                    # Inject correct user_id to override LLM-inferred value
                    inject_user_id(
                        arguments, user_id, logger,
                        {"conversation_id": conversation_id, "tool_name": function_name}
                    )

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

                            # Drain status queue immediately so user sees status before tool executes
                            while not status_queue.empty():
                                try:
                                    status_msg = status_queue.get_nowait()
                                    yield format_status_frame(status_msg)
                                except asyncio.QueueEmpty:
                                    break

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

                            # Drain status queue immediately so user sees completion status
                            while not status_queue.empty():
                                try:
                                    status_msg = status_queue.get_nowait()
                                    yield format_status_frame(status_msg)
                                except asyncio.QueueEmpty:
                                    break

                            # Check if tool result contains media to send to user
                            media_data = extract_media_from_tool_result(tool_result, function_name)
                            if media_data:
                                if state_manager:
                                    media_data = await offload_base64_to_redis(
                                        media_data, state_manager.redis_client, conversation_id
                                    )
                                logger.info(
                                    "Tool returned media to send",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "tool_name": function_name,
                                        "tool_call_id": tool_call_id,
                                        "is_single": media_data.get("single", True),
                                        "media_type": media_data.get("media_type", "unknown"),
                                        "event": "tool_media_emit"
                                    }
                                )
                                for frame in build_media_sse_frames(media_data):
                                    yield frame

                        # Add tool result to conversation (strip base64 so LLM won't echo it)
                        tool_content = json.dumps(strip_base64_from_tool_result(tool_result))
                        conversation_messages.append({
                            "role": "tool",
                            "content": tool_content,
                            "tool_call_id": tool_call_id
                        })

                        # Persist tool result to Redis for context continuity
                        if state_manager:
                            try:
                                await state_manager.add_message(conversation_id, {
                                    "role": "tool",
                                    "content": tool_content,
                                    "tool_call_id": tool_call_id,
                                    "tool_name": function_name,
                                    "is_tool_result": True
                                })
                            except Exception as e:
                                logger.warning(
                                    "Failed to persist tool result to Redis",
                                    extra={
                                        "conversation_id": conversation_id,
                                        "tool_name": function_name,
                                        "tool_call_id": tool_call_id,
                                        "error": str(e)
                                    }
                                )

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

                        # Check if tool returned a business logic error
                        tool_success = True
                        if isinstance(tool_result, dict) and tool_result.get("status") == "error":
                            tool_success = False

                        # Invalidate profile cache after successful update_user_profile
                        # (no-op for other tools; defensive against Redis failures)
                        if state_manager:
                            await invalidate_profile_cache_if_needed(
                                function_name,
                                tool_result,
                                user_id,
                                state_manager.redis_client,
                                logger,
                            )

                        if tool_success:
                            logger.info(
                                "Tool execution successful",
                                extra={
                                    "conversation_id": conversation_id,
                                    "tool_name": function_name,
                                    "tool_call_id": tool_call_id
                                }
                            )
                        else:
                            logger.warning(
                                "Tool returned error",
                                extra={
                                    "conversation_id": conversation_id,
                                    "tool_name": function_name,
                                    "tool_call_id": tool_call_id,
                                    "error_message": tool_result.get("message", "Unknown error")
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
                    if files:
                        emit_status("Analyzing your files...", icon="📎")
                    else:
                        emit_status("Composing response...", icon="🧠")

                    # Stream final response anyway
                    async for event in llm_client.stream_chat_completion(conversation_messages, tools=tools, mcp_client=mcp_client, files=files, user_id=user_id, conversation_id=conversation_id, state_manager=state_manager):
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

        # Verify conversation ownership if request has authenticated user
        auth_user_id = getattr(request.state, "user_id", None)
        if auth_user_id and user_id and auth_user_id != user_id:
            logger.error(
                "Stream access denied: authenticated user does not own conversation",
                extra={
                    "conversation_id": conversation_id,
                    "auth_user_id": auth_user_id,
                    "conversation_owner": user_id,
                }
            )
            raise HTTPException(status_code=403, detail="Access denied")

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

        # Load files from Redis cache (set by chat endpoint for multimodal processing)
        files = None
        try:
            files_key = f"files:{conversation_id}"
            files_data = await state_manager.redis_client.get(files_key)
            if files_data:
                import json
                files_list = json.loads(files_data)
                files = [FileAttachment(**f) for f in files_list]

                # Log file metadata (not content)
                files_meta = get_files_metadata(files)
                logger.info(
                    "Files loaded for multimodal processing",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "file_count": files_meta["file_count"],
                        "total_size_bytes": files_meta["total_size_bytes"],
                        "mime_types": files_meta["mime_types"],
                        "event": "files_loaded"
                    }
                )

                # Delete files from Redis after loading (process-and-discard model)
                await state_manager.redis_client.delete(files_key)

        except Exception as e:
            logger.warning(
                f"Failed to load files for multimodal processing, continuing without: {str(e)}",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "error_type": type(e).__name__
                }
            )

        # Return SSE response with state manager and files passed to generator
        return EventSourceResponse(
            stream_generator(conversation_id, messages, request, state_manager, files, user_id),
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
