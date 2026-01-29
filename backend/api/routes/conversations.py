"""
Conversations Route Handler

Handles conversation management for the web UI.
Provides endpoints for listing, creating, updating, and deleting conversations.

Authentication:
- Web UI: Uses Cloudflare Access middleware (request.state.user_id)
- Telegram bot: Uses request body user_id (fallback for compatibility)

All endpoints require authentication and validate user ownership.
"""

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from api.logging import get_logger
from api.models.conversation import (
    Conversation,
    ConversationDetailResponse,
    ConversationListResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    DeleteConversationResponse,
    Message,
    MessageListResponse,
    PaginationInfo,
    UpdateConversationRequest,
    UpdateConversationResponse,
)
from api.state import StateManager, StateError

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/conversations", tags=["conversations"])


def get_user_id(request: Request) -> str:
    """
    Get user_id from Cloudflare auth middleware or raise 401.

    For web UI requests, user_id is extracted from Cloudflare Access JWT
    and attached to request.state by cloudflare_auth_middleware.

    Args:
        request: FastAPI Request object

    Returns:
        user_id string

    Raises:
        HTTPException: 401 if not authenticated
    """
    # Priority 1: CF auth middleware (web flow)
    if hasattr(request.state, "user_id") and request.state.user_id:
        return request.state.user_id

    # No authentication found - reject
    logger.warning(
        "Authentication required but not provided",
        extra={
            "path": request.url.path,
            "method": request.method,
            "event": "conversations_auth_failed"
        }
    )
    raise HTTPException(
        status_code=401,
        detail="Authentication required"
    )


async def verify_conversation_ownership(
    state: StateManager,
    conversation_id: str,
    user_id: str
) -> bool:
    """
    Verify that a conversation belongs to the specified user.

    Args:
        state: StateManager instance
        conversation_id: Conversation to verify
        user_id: Expected owner user_id

    Returns:
        True if user owns the conversation

    Raises:
        HTTPException: 404 if conversation not found
        HTTPException: 403 if user doesn't own conversation
    """
    detail = await state.get_conversation_detail(conversation_id)

    if not detail:
        raise HTTPException(
            status_code=404,
            detail=f"Conversation {conversation_id} not found"
        )

    if detail.get("user_id") != user_id:
        logger.warning(
            "Unauthorized conversation access attempt",
            extra={
                "conversation_id": conversation_id,
                "requesting_user": user_id,
                "owner_user": detail.get("user_id"),
                "event": "conversations_unauthorized_access"
            }
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not own this conversation"
        )

    return True


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    request: Request,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    limit: int = Query(default=50, ge=1, le=100, description="Items per page")
):
    """
    List conversations for the authenticated user.

    Conversations are sorted by updated_at (most recent first).

    Args:
        request: FastAPI Request object
        page: Page number (default: 1)
        limit: Items per page (default: 50, max: 100)

    Returns:
        ConversationListResponse with list of conversations and total count

    Example:
        GET /api/conversations?page=1&limit=20

        Response:
        {
            "conversations": [
                {
                    "id": "conv_abc123",
                    "title": "Portfolio Discussion",
                    "created_at": "2026-01-26T10:00:00Z",
                    "updated_at": "2026-01-26T12:30:00Z",
                    "message_count": 15,
                    "last_message_preview": "Thanks for the advice..."
                }
            ],
            "total": 5
        }
    """
    user_id = get_user_id(request)
    start_time = time.time()

    logger.info(
        "List conversations request",
        extra={
            "user_id": user_id,
            "page": page,
            "limit": limit,
            "event": "conversations_list_request"
        }
    )

    try:
        async with StateManager() as state:
            # Calculate offset
            offset = (page - 1) * limit

            # Get conversations
            conversations_data = await state.list_conversations(
                user_id=user_id,
                limit=limit,
                offset=offset
            )

            # Get total count
            total = await state.get_conversations_count(user_id)

            # Convert to response models
            conversations = []
            for conv in conversations_data:
                try:
                    conversations.append(Conversation(
                        id=conv["id"],
                        title=conv.get("title", "Untitled"),
                        created_at=datetime.fromisoformat(
                            conv["created_at"].replace("Z", "+00:00")
                        ) if conv.get("created_at") else datetime.now(timezone.utc),
                        updated_at=datetime.fromisoformat(
                            conv["updated_at"].replace("Z", "+00:00")
                        ) if conv.get("updated_at") else datetime.now(timezone.utc),
                        message_count=conv.get("message_count", 0),
                        last_message_preview=conv.get("last_message_preview")
                    ))
                except Exception as e:
                    logger.warning(
                        f"Failed to parse conversation: {e}",
                        extra={"conv_id": conv.get("id")}
                    )
                    continue

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversations listed successfully",
                extra={
                    "user_id": user_id,
                    "count": len(conversations),
                    "total": total,
                    "page": page,
                    "duration_ms": duration_ms,
                    "event": "conversations_list_success"
                }
            )

            return ConversationListResponse(
                conversations=conversations,
                total=total
            )

    except StateError as e:
        logger.error(
            "State management error in list conversations",
            extra={
                "user_id": user_id,
                "error": str(e),
                "event": "conversations_list_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to list conversations. Please try again."
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Unexpected error in list conversations",
            extra={
                "user_id": user_id,
                "error_type": type(e).__name__,
                "error": str(e),
                "event": "conversations_list_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


@router.post("", response_model=CreateConversationResponse)
async def create_conversation(
    request: Request,
    body: Optional[CreateConversationRequest] = None
):
    """
    Create a new conversation.

    Args:
        request: FastAPI Request object
        body: Optional request body with title

    Returns:
        CreateConversationResponse with new conversation details

    Example:
        POST /api/conversations
        {"title": "Investment Discussion"}

        Response:
        {
            "id": "conv_abc123",
            "title": "Investment Discussion",
            "created_at": "2026-01-26T10:00:00Z"
        }
    """
    user_id = get_user_id(request)
    title = body.title if body else None
    start_time = time.time()

    logger.info(
        "Create conversation request",
        extra={
            "user_id": user_id,
            "has_title": title is not None,
            "event": "conversations_create_request"
        }
    )

    try:
        async with StateManager() as state:
            result = await state.create_conversation(
                user_id=user_id,
                platform="web",
                title=title
            )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation created successfully",
                extra={
                    "user_id": user_id,
                    "conversation_id": result["conversation_id"],
                    "title": result["title"],
                    "duration_ms": duration_ms,
                    "event": "conversations_create_success"
                }
            )

            return CreateConversationResponse(
                id=result["conversation_id"],
                title=result["title"],
                created_at=datetime.fromisoformat(
                    result["created_at"].replace("Z", "+00:00")
                )
            )

    except StateError as e:
        logger.error(
            "State management error in create conversation",
            extra={
                "user_id": user_id,
                "error": str(e),
                "event": "conversations_create_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to create conversation. Please try again."
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Unexpected error in create conversation",
            extra={
                "user_id": user_id,
                "error_type": type(e).__name__,
                "error": str(e),
                "event": "conversations_create_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    request: Request,
    conversation_id: str,
    page: int = Query(default=1, ge=1, description="Page number for messages"),
    limit: int = Query(default=50, ge=1, le=100, description="Messages per page")
):
    """
    Get a conversation with paginated messages.

    Args:
        request: FastAPI Request object
        conversation_id: Conversation identifier
        page: Page number for messages (default: 1)
        limit: Messages per page (default: 50, max: 100)

    Returns:
        ConversationDetailResponse with conversation details and messages

    Raises:
        404: Conversation not found
        403: User doesn't own conversation

    Example:
        GET /api/conversations/conv_abc123?page=1&limit=50

        Response:
        {
            "id": "conv_abc123",
            "title": "Portfolio Discussion",
            "messages": [...],
            "created_at": "2026-01-26T10:00:00Z",
            "updated_at": "2026-01-26T12:30:00Z",
            "pagination": {
                "page": 1,
                "limit": 50,
                "total": 15,
                "has_more": false
            }
        }
    """
    user_id = get_user_id(request)
    start_time = time.time()

    logger.info(
        "Get conversation request",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "page": page,
            "limit": limit,
            "event": "conversations_get_request"
        }
    )

    try:
        async with StateManager() as state:
            # Verify ownership
            await verify_conversation_ownership(state, conversation_id, user_id)

            # Get conversation detail
            detail = await state.get_conversation_detail(conversation_id)

            # Get paginated messages
            messages_data = await state.get_paginated_messages(
                conversation_id=conversation_id,
                page=page,
                limit=limit
            )

            # Convert messages to response model
            messages = []
            for msg in messages_data.get("messages", []):
                try:
                    timestamp = None
                    if msg.get("timestamp"):
                        try:
                            timestamp = datetime.fromisoformat(
                                msg["timestamp"].replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    messages.append(Message(
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        timestamp=timestamp,
                        tool_calls=msg.get("tool_calls")
                    ))
                except Exception as e:
                    logger.warning(
                        f"Failed to parse message: {e}",
                        extra={"conversation_id": conversation_id}
                    )
                    continue

            pagination = messages_data.get("pagination", {})

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation retrieved successfully",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_count": len(messages),
                    "duration_ms": duration_ms,
                    "event": "conversations_get_success"
                }
            )

            return ConversationDetailResponse(
                id=conversation_id,
                title=detail.get("title", "Untitled"),
                messages=messages,
                created_at=datetime.fromisoformat(
                    detail["created_at"].replace("Z", "+00:00")
                ) if detail.get("created_at") else datetime.now(timezone.utc),
                updated_at=datetime.fromisoformat(
                    detail["updated_at"].replace("Z", "+00:00")
                ) if detail.get("updated_at") else datetime.now(timezone.utc),
                pagination=PaginationInfo(
                    page=pagination.get("page", page),
                    limit=pagination.get("limit", limit),
                    total=pagination.get("total", 0),
                    has_more=pagination.get("has_more", False)
                )
            )

    except StateError as e:
        logger.error(
            "State management error in get conversation",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error": str(e),
                "event": "conversations_get_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversation. Please try again."
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Unexpected error in get conversation",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error_type": type(e).__name__,
                "error": str(e),
                "event": "conversations_get_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


@router.delete("/{conversation_id}", response_model=DeleteConversationResponse)
async def delete_conversation(
    request: Request,
    conversation_id: str
):
    """
    Delete a conversation and all its messages.

    Args:
        request: FastAPI Request object
        conversation_id: Conversation identifier

    Returns:
        DeleteConversationResponse with status

    Raises:
        404: Conversation not found
        403: User doesn't own conversation

    Example:
        DELETE /api/conversations/conv_abc123

        Response:
        {"status": "deleted"}
    """
    user_id = get_user_id(request)
    start_time = time.time()

    logger.info(
        "Delete conversation request",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "event": "conversations_delete_request"
        }
    )

    try:
        async with StateManager() as state:
            # Verify ownership
            await verify_conversation_ownership(state, conversation_id, user_id)

            # Delete conversation
            deleted = await state.delete_conversation(conversation_id)

            if not deleted:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to delete conversation"
                )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation deleted successfully",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "duration_ms": duration_ms,
                    "event": "conversations_delete_success"
                }
            )

            return DeleteConversationResponse(status="deleted")

    except StateError as e:
        logger.error(
            "State management error in delete conversation",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error": str(e),
                "event": "conversations_delete_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to delete conversation. Please try again."
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Unexpected error in delete conversation",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error_type": type(e).__name__,
                "error": str(e),
                "event": "conversations_delete_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


@router.patch("/{conversation_id}", response_model=UpdateConversationResponse)
async def update_conversation(
    request: Request,
    conversation_id: str,
    body: UpdateConversationRequest
):
    """
    Update conversation title.

    Args:
        request: FastAPI Request object
        conversation_id: Conversation identifier
        body: Request body with new title

    Returns:
        UpdateConversationResponse with updated details

    Raises:
        404: Conversation not found
        403: User doesn't own conversation

    Example:
        PATCH /api/conversations/conv_abc123
        {"title": "New Title"}

        Response:
        {
            "id": "conv_abc123",
            "title": "New Title",
            "updated_at": "2026-01-26T14:00:00Z"
        }
    """
    user_id = get_user_id(request)
    start_time = time.time()

    logger.info(
        "Update conversation request",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "new_title": body.title,
            "event": "conversations_update_request"
        }
    )

    try:
        async with StateManager() as state:
            # Verify ownership
            await verify_conversation_ownership(state, conversation_id, user_id)

            # Update title
            result = await state.update_conversation_title(
                conversation_id=conversation_id,
                title=body.title
            )

            if not result:
                raise HTTPException(
                    status_code=500,
                    detail="Failed to update conversation"
                )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation updated successfully",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "new_title": body.title,
                    "duration_ms": duration_ms,
                    "event": "conversations_update_success"
                }
            )

            return UpdateConversationResponse(
                id=result["id"],
                title=result["title"],
                updated_at=datetime.fromisoformat(
                    result["updated_at"].replace("Z", "+00:00")
                )
            )

    except StateError as e:
        logger.error(
            "State management error in update conversation",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error": str(e),
                "event": "conversations_update_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update conversation. Please try again."
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Unexpected error in update conversation",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error_type": type(e).__name__,
                "error": str(e),
                "event": "conversations_update_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    request: Request,
    conversation_id: str,
    page: int = Query(default=1, ge=1, description="Page number"),
    limit: int = Query(default=50, ge=1, le=100, description="Messages per page")
):
    """
    Get paginated messages for a conversation.

    Separate endpoint for message-only retrieval (lighter payload).

    Args:
        request: FastAPI Request object
        conversation_id: Conversation identifier
        page: Page number (default: 1)
        limit: Messages per page (default: 50, max: 100)

    Returns:
        MessageListResponse with messages and pagination

    Raises:
        404: Conversation not found
        403: User doesn't own conversation

    Example:
        GET /api/conversations/conv_abc123/messages?page=2&limit=20

        Response:
        {
            "messages": [...],
            "pagination": {
                "page": 2,
                "limit": 20,
                "total": 50,
                "has_more": true
            }
        }
    """
    user_id = get_user_id(request)
    start_time = time.time()

    logger.info(
        "Get conversation messages request",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "page": page,
            "limit": limit,
            "event": "conversations_messages_request"
        }
    )

    try:
        async with StateManager() as state:
            # Verify ownership
            await verify_conversation_ownership(state, conversation_id, user_id)

            # Get paginated messages
            messages_data = await state.get_paginated_messages(
                conversation_id=conversation_id,
                page=page,
                limit=limit
            )

            # Convert messages to response model
            messages = []
            for msg in messages_data.get("messages", []):
                try:
                    timestamp = None
                    if msg.get("timestamp"):
                        try:
                            timestamp = datetime.fromisoformat(
                                msg["timestamp"].replace("Z", "+00:00")
                            )
                        except (ValueError, TypeError):
                            pass

                    messages.append(Message(
                        role=msg.get("role", "user"),
                        content=msg.get("content", ""),
                        timestamp=timestamp,
                        tool_calls=msg.get("tool_calls")
                    ))
                except Exception as e:
                    logger.warning(
                        f"Failed to parse message: {e}",
                        extra={"conversation_id": conversation_id}
                    )
                    continue

            pagination = messages_data.get("pagination", {})

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation messages retrieved successfully",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "message_count": len(messages),
                    "page": page,
                    "duration_ms": duration_ms,
                    "event": "conversations_messages_success"
                }
            )

            return MessageListResponse(
                messages=messages,
                pagination=PaginationInfo(
                    page=pagination.get("page", page),
                    limit=pagination.get("limit", limit),
                    total=pagination.get("total", 0),
                    has_more=pagination.get("has_more", False)
                )
            )

    except StateError as e:
        logger.error(
            "State management error in get conversation messages",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error": str(e),
                "event": "conversations_messages_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve messages. Please try again."
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(
            "Unexpected error in get conversation messages",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "error_type": type(e).__name__,
                "error": str(e),
                "event": "conversations_messages_error"
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )
