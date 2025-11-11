"""
Streaming Route Handler

Handles SSE (Server-Sent Events) streaming for real-time LLM responses.
"""

import asyncio
import json
import time
from typing import AsyncGenerator, Dict, Any
from datetime import datetime, timezone

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from api.llm_client import LLMClient, LLMClientError
from api.logging import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["streaming"])

# Track active streams (in-memory for now, will use Redis in Story 2.5)
active_streams: Dict[str, float] = {}  # conversation_id -> timestamp
MAX_CONCURRENT_STREAMS = 100


async def stream_generator(
    conversation_id: str,
    messages: list,
    request: Request
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Generate SSE events from LLM streaming response.

    Args:
        conversation_id: Unique conversation identifier
        messages: List of chat messages to send to LLM
        request: FastAPI request object for disconnection detection

    Yields:
        SSE event dictionaries with type, data, and optional event fields
    """
    start_time = time.time()
    first_token_sent = False

    try:
        # Create LLM client
        async with LLMClient() as client:
            logger.info(
                "Starting SSE stream",
                extra={
                    "conversation_id": conversation_id,
                    "message_count": len(messages)
                }
            )

            # Stream tokens from LLM
            async for event in client.chat_completion_stream(messages):
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

                # Yield SSE event
                yield {
                    "event": "message",
                    "data": json.dumps(event)
                }

                # If error event, stop streaming
                if event.get("type") == "error":
                    logger.error(
                        "Error during streaming",
                        extra={
                            "conversation_id": conversation_id,
                            "error_code": event.get("code"),
                            "error_message": event.get("message")
                        }
                    )
                    break

                # If completion event, log and stop
                if event.get("type") == "done":
                    duration_ms = int((time.time() - start_time) * 1000)
                    tokens_used = event.get("tokens_used", {})
                    logger.info(
                        "Stream completed successfully",
                        extra={
                            "conversation_id": conversation_id,
                            "duration_ms": duration_ms,
                            "tokens": tokens_used
                        }
                    )
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
