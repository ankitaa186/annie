"""
Chat Route Handler

Handles incoming chat requests and initiates LLM streaming responses.
Integrates with StateManager for session and conversation management.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.logging import get_logger
from api.state import StateManager, StateError

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api", tags=["chat"])


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

    This endpoint receives a chat message, manages session state with Redis,
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
        2. Get or create session in Redis
        3. Store user message in conversation history
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

    try:
        async with StateManager() as state:
            # Get or create session
            session = await state.get_session(request.user_id)

            if not session:
                # Create new session
                session = await state.create_session(request.user_id, request.platform)
                logger.info(
                    "New session created",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": session["conversation_id"]
                    }
                )
            else:
                # Update existing session activity
                await state.update_session_activity(request.user_id)
                logger.info(
                    "Existing session updated",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": session["conversation_id"]
                    }
                )

            conversation_id = session["conversation_id"]

            # Store user message in conversation history
            user_message = {
                "role": "user",
                "content": request.message
            }
            await state.add_message(conversation_id, user_message)

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

    except StateError as e:
        logger.error(
            "State management error",
            extra={
                "user_id": request.user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to manage conversation state. Please try again."
        )

    except Exception as e:
        logger.error(
            "Unexpected error in chat endpoint",
            extra={
                "user_id": request.user_id,
                "error_type": type(e).__name__,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


class ConversationHistoryResponse(BaseModel):
    """Response model for conversation history endpoint."""
    user_id: str = Field(..., description="User identifier")
    conversation_id: str = Field(..., description="Conversation identifier")
    messages: List[Dict[str, Any]] = Field(..., description="List of messages")
    pagination: Dict[str, Any] = Field(..., description="Pagination metadata")


@router.get("/conversations/{user_id}", response_model=ConversationHistoryResponse)
async def get_conversation_history(
    user_id: str,
    page: int = 1,
    limit: int = 50
):
    """
    Retrieve conversation history for a user with pagination.

    Args:
        user_id: Unique user identifier
        page: Page number (default: 1)
        limit: Messages per page (default: 50, max: 50)

    Returns:
        ConversationHistoryResponse with messages and pagination info

    Raises:
        HTTPException: 404 if no session found for user
        HTTPException: 422 if invalid pagination parameters
        HTTPException: 500 for state management errors

    Example:
        GET /api/conversations/123456?page=1&limit=50

        Response:
        {
            "user_id": "123456",
            "conversation_id": "conv_abc123",
            "messages": [...],
            "pagination": {
                "page": 1,
                "limit": 50,
                "total": 100,
                "has_more": true
            }
        }
    """
    # Validate pagination parameters
    if page < 1:
        raise HTTPException(
            status_code=422,
            detail="Page number must be >= 1"
        )

    if limit < 1 or limit > 50:
        raise HTTPException(
            status_code=422,
            detail="Limit must be between 1 and 50"
        )

    logger.info(
        "Conversation history request received",
        extra={
            "user_id": user_id,
            "page": page,
            "limit": limit
        }
    )

    try:
        async with StateManager() as state:
            # Get session to find conversation_id
            session = await state.get_session(user_id)

            if not session:
                logger.warning(
                    "No session found for user",
                    extra={"user_id": user_id}
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"No active session found for user {user_id}"
                )

            conversation_id = session["conversation_id"]

            # Get conversation metadata for total count
            metadata = await state.get_conversation_metadata(conversation_id)
            total_messages = metadata.get("total_messages", 0)

            # Calculate offset
            offset = (page - 1) * limit

            if offset >= total_messages and total_messages > 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"Page {page} exceeds available messages"
                )

            # Get all messages (Redis LRANGE doesn't support offset well, so we get all and slice)
            all_messages = await state.get_conversation_history(
                conversation_id,
                limit=total_messages  # Get all messages
            )

            # Apply pagination in Python
            paginated_messages = all_messages[offset:offset + limit]

            # Build pagination metadata
            has_more = (offset + limit) < total_messages
            pagination = {
                "page": page,
                "limit": limit,
                "total": total_messages,
                "has_more": has_more
            }

            logger.info(
                "Conversation history retrieved",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "total_messages": total_messages,
                    "returned_messages": len(paginated_messages),
                    "page": page
                }
            )

            return ConversationHistoryResponse(
                user_id=user_id,
                conversation_id=conversation_id,
                messages=paginated_messages,
                pagination=pagination
            )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise

    except StateError as e:
        logger.error(
            "State management error in conversation history",
            extra={
                "user_id": user_id,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversation history. Please try again."
        )

    except Exception as e:
        logger.error(
            "Unexpected error in conversation history endpoint",
            extra={
                "user_id": user_id,
                "error_type": type(e).__name__,
                "error": str(e)
            }
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )
