"""
Chat Route Handler

Handles incoming chat requests and initiates LLM streaming responses.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.logging import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["chat"])

# Temporary message storage (will use Redis in Story 2.5)
from api.routes.stream import conversation_messages_store


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    user_id: str = Field(..., description="Unique user identifier")
    platform: str = Field(..., description="Platform identifier (e.g., 'telegram')")
    message: str = Field(..., min_length=1, description="User message content")
    context: Optional[dict] = Field(default={}, description="Additional context metadata")


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    status: str = Field(..., description="Conversation status (e.g., 'streaming')")
    stream_url: str = Field(..., description="URL to connect for SSE streaming")
    timestamp: str = Field(..., description="Response timestamp (ISO 8601)")


@router.post("/chat", response_model=ChatResponse)
async def create_chat(request: ChatRequest):
    """
    Process incoming chat message and initiate streaming response.

    This endpoint receives a chat message, generates a conversation ID,
    and returns the streaming URL where the client can connect to receive
    the LLM response in real-time via Server-Sent Events (SSE).

    Args:
        request: Chat request with user_id, platform, message, and optional context

    Returns:
        ChatResponse with conversation_id, status, and stream_url

    Raises:
        HTTPException: 400 for invalid input
        HTTPException: 503 if service is unavailable

    Flow:
        1. Validate request
        2. Generate conversation_id
        3. TODO (Story 2.5): Store conversation state in Redis
        4. Return stream URL for client to connect

    Example:
        POST /api/chat
        {
            "user_id": "123456",
            "platform": "telegram",
            "message": "What should I invest in?",
            "context": {}
        }

        Response:
        {
            "conversation_id": "conv_abc123",
            "status": "streaming",
            "stream_url": "/api/stream/conv_abc123",
            "timestamp": "2025-11-11T10:00:00Z"
        }
    """
    logger.info(
        "Chat request received",
        extra={
            "user_id": request.user_id,
            "platform": request.platform,
            "message_length": len(request.message)
        }
    )

    # Generate unique conversation ID
    conversation_id = f"conv_{uuid.uuid4().hex[:16]}"

    # TODO (Story 2.5): Load conversation history from Redis
    # TODO (Story 2.5): Store new message in conversation state
    # For now, store message temporarily in memory
    conversation_messages_store[conversation_id] = [
        {"role": "user", "content": request.message}
    ]
    logger.debug(
        "Stored conversation message",
        extra={"conversation_id": conversation_id, "message": request.message[:100]}
    )

    # Build stream URL
    stream_url = f"/api/stream/{conversation_id}"

    logger.info(
        "Chat conversation initiated",
        extra={
            "conversation_id": conversation_id,
            "user_id": request.user_id,
            "stream_url": stream_url
        }
    )

    return ChatResponse(
        conversation_id=conversation_id,
        status="streaming",
        stream_url=stream_url,
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
