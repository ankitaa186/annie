"""
Chat Route Handler

Handles incoming chat requests and initiates LLM streaming responses.
Integrates with StateManager for session and conversation management.
Integrates with MemoryManager for conversation memory storage.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel, Field

from api.logging import get_logger
from api.memory import MemoryManager
from api.mcp_client import MCPClient, MCPClientError, MCPNetworkError, MCPToolError
from api.state import StateManager, StateError

logger = get_logger(__name__)

# Farewell keywords for conversation end detection
FAREWELL_KEYWORDS = {
    "thanks", "thank you", "thanks!", "thank you!", "thx", "ty",
    "bye", "goodbye", "bye!", "goodbye!", "see you", "cya",
    "that's all", "thats all", "done", "i'm done", "im done"
}

# Decision support keywords for memory retrieval
DECISION_SUPPORT_KEYWORDS = {
    "should i", "recommend", "advice", "help me decide", "what do you think",
    "is it good", "is it a good idea", "what's better", "which is better",
    "help me choose", "what should", "should we", "would you recommend"
}

# Create router
router = APIRouter(prefix="/api", tags=["chat"])


def is_conversation_ending(message: str) -> bool:
    """
    Detect if user message indicates conversation is ending.

    Args:
        message: User message content

    Returns:
        bool: True if message contains farewell keywords
    """
    message_lower = message.lower().strip()

    # Check for exact match or keyword at end of message
    for keyword in FAREWELL_KEYWORDS:
        if message_lower == keyword or message_lower.endswith(keyword):
            return True

    return False


def is_decision_support_request(message: str) -> bool:
    """
    Detect if user message requests decision support or advice.

    This triggers memory retrieval to provide personalized recommendations
    based on past decisions and preferences.

    Args:
        message: User message content

    Returns:
        bool: True if message contains decision support keywords
    """
    message_lower = message.lower().strip()

    # Check for decision support keywords
    for keyword in DECISION_SUPPORT_KEYWORDS:
        if keyword in message_lower:
            return True

    return False


def extract_decision_query(message: str) -> str:
    """
    Extract query from user message for memory retrieval.

    Removes common question words and formats the message into a query
    suitable for semantic search.

    Args:
        message: User message content

    Returns:
        str: Extracted query for memory search
    """
    # Remove common question words and decision keywords
    query = message.lower()

    # Remove decision support keywords
    for keyword in DECISION_SUPPORT_KEYWORDS:
        query = query.replace(keyword, "")

    # Remove question marks and punctuation
    query = query.replace("?", "").replace("!", "").strip()

    # If query is empty or too short, use original message
    if len(query) < 5:
        query = message

    return query.strip()


async def store_conversation_memory_background(
    user_id: str,
    conversation_id: str
):
    """
    Background task to store conversation memory.

    This runs asynchronously and doesn't block the chat response.

    Args:
        user_id: User identifier
        conversation_id: Conversation identifier
    """
    try:
        logger.info(
            "Starting background memory storage",
            extra={"user_id": user_id, "conversation_id": conversation_id}
        )

        # Get conversation history
        async with StateManager() as state:
            # Get up to 50 messages for storage
            conversation_history = await state.get_conversation_history(
                conversation_id,
                limit=50
            )

        if not conversation_history or len(conversation_history) < 2:
            logger.info(
                "Conversation too short for memory storage, skipping",
                extra={"user_id": user_id, "message_count": len(conversation_history)}
            )
            return

        # Store conversation memory (agentic-memories handles extraction)
        memory_manager = MemoryManager()
        success = await memory_manager.store_conversation_memory(
            user_id=user_id,
            conversation_id=conversation_id,
            conversation_history=conversation_history,
            platform="telegram"
        )

        if success:
            logger.info(
                "Conversation memory stored successfully in background",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "memory_id": memory_data.get("memory_id")
                }
            )
        else:
            logger.warning(
                "Conversation memory queued for retry",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id
                }
            )

    except Exception as e:
        logger.error(
            f"Error in background memory storage: {str(e)}",
            exc_info=True,
            extra={"user_id": user_id, "conversation_id": conversation_id}
        )


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
async def create_chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """
    Process incoming chat message and initiate streaming response.

    This endpoint receives a chat message, manages session state with Redis,
    and returns the streaming URL where the client can connect to receive
    the LLM response in real-time via Server-Sent Events (SSE).

    Also detects conversation ending (farewell keywords) and triggers
    background memory storage for long-term retention.

    Args:
        request: Chat request with user_id, platform, message, and optional context
        background_tasks: FastAPI background tasks for non-blocking operations

    Returns:
        ChatResponse with conversation_id, status, and stream_url

    Raises:
        HTTPException: 400 for invalid input
        HTTPException: 503 if service is unavailable

    Flow:
        1. Validate request
        2. Get or create session in Redis
        3. Store user message in conversation history
        4. Detect conversation end and trigger memory storage (background)
        5. Return stream URL for client to connect

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
    # Detect conversation ending and decision support request
    conversation_is_ending = is_conversation_ending(request.message)
    needs_decision_support = is_decision_support_request(request.message)

    logger.info(
        "Chat request received",
        extra={
            "user_id": request.user_id,
            "platform": request.platform,
            "message_length": len(request.message),
            "conversation_ending": conversation_is_ending,
            "needs_decision_support": needs_decision_support
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

            # Retrieve and format memory context if decision support is needed
            memory_context = None
            if needs_decision_support:
                try:
                    # Extract query from user message
                    query = extract_decision_query(request.message)

                    logger.info(
                        "Decision support detected, retrieving memories",
                        extra={
                            "user_id": request.user_id,
                            "conversation_id": conversation_id,
                            "query": query
                        }
                    )

                    # Call retrieve_memories MCP tool
                    async with MCPClient() as mcp_client:
                        retrieval_result = await mcp_client.call_tool(
                            "retrieve_memories",
                            {
                                "user_id": request.user_id,
                                "query": query,
                                "limit": 5
                            }
                        )

                    # Check if memories were retrieved
                    memories = retrieval_result.get("memories", [])
                    memory_count = retrieval_result.get("memory_count", 0)

                    logger.info(
                        "Memory retrieval completed",
                        extra={
                            "user_id": request.user_id,
                            "conversation_id": conversation_id,
                            "memory_count": memory_count
                        }
                    )

                    # Format memories for LLM if any were found
                    if memories and memory_count > 0:
                        memory_manager = MemoryManager()
                        memory_context = await memory_manager.format_memories_for_llm(memories)

                        # Store memory context in Redis for streaming endpoint (TTL: 5 minutes)
                        memory_context_key = f"memory_context:{conversation_id}"
                        await state.redis_client.setex(
                            memory_context_key,
                            300,  # 5 minutes TTL
                            memory_context
                        )

                        logger.info(
                            "Memory context formatted and stored",
                            extra={
                                "user_id": request.user_id,
                                "conversation_id": conversation_id,
                                "context_length": len(memory_context),
                                "memory_count": memory_count
                            }
                        )
                    else:
                        logger.info(
                            "No relevant memories found for decision support",
                            extra={
                                "user_id": request.user_id,
                                "conversation_id": conversation_id,
                                "query": query
                            }
                        )

                except (MCPClientError, MCPNetworkError, MCPToolError) as e:
                    # Graceful degradation: log error but continue without memory context
                    logger.warning(
                        f"Memory retrieval failed, continuing without memory context: {str(e)}",
                        extra={
                            "user_id": request.user_id,
                            "conversation_id": conversation_id,
                            "error_type": type(e).__name__
                        }
                    )

                except Exception as e:
                    # Graceful degradation: log error but continue without memory context
                    logger.error(
                        f"Unexpected error during memory retrieval, continuing without memory context: {str(e)}",
                        extra={
                            "user_id": request.user_id,
                            "conversation_id": conversation_id,
                            "error_type": type(e).__name__
                        },
                        exc_info=True
                    )

            # Build stream URL
            stream_url = f"/api/stream/{conversation_id}"

            # Trigger background memory storage if conversation is ending
            if conversation_is_ending:
                logger.info(
                    "Conversation ending detected, triggering memory storage",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": conversation_id
                    }
                )
                # Add background task (runs after response is sent)
                background_tasks.add_task(
                    store_conversation_memory_background,
                    request.user_id,
                    conversation_id
                )

            logger.info(
                "Chat conversation initiated",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": request.user_id,
                    "stream_url": stream_url,
                    "memory_storage_queued": conversation_is_ending
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
            },
            exc_info=True
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
            },
            exc_info=True
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
            },
            exc_info=True
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
            },
            exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again."
        )
