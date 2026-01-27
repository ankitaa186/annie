"""
Chat Route Handler

Handles incoming chat requests and initiates LLM streaming responses.
Integrates with StateManager for session and conversation management.
Integrates with MemoryManager for conversation memory storage.
"""

import asyncio
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field

from api.logging import get_logger
from api.memory import MemoryManager
from api.mcp_client import MCPClient, MCPClientError, MCPNetworkError, MCPToolError
from api.models.file_attachment import (
    FileAttachment,
    MAX_FILES_PER_REQUEST,
    validate_files,
    get_files_metadata,
)
from api.proactive.activity_tracker import ActivityTracker
from api.profile import ProfileManager
from api.state import StateManager, StateError
from api.status import emit_status

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
        def update_current_trace(**kwargs):
            pass

logger = get_logger(__name__)

# Decision support keywords for memory retrieval
DECISION_SUPPORT_KEYWORDS = {
    "should i", "recommend", "advice", "help me decide", "what do you think",
    "is it good", "is it a good idea", "what's better", "which is better",
    "help me choose", "what should", "should we", "would you recommend"
}

# Create router
router = APIRouter(prefix="/api", tags=["chat"])


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
    conversation_id: str,
    message_content: str,
    role: str = "user"
):
    """
    Background task to stream message through orchestrator for batched memory storage.

    This runs asynchronously and doesn't block the chat response.
    Uses the orchestrator's intelligent batching (2-8 messages before LLM extraction)
    for ~70% cost savings compared to direct /v1/store calls.

    Args:
        user_id: User identifier
        conversation_id: Conversation identifier
        message_content: The message content to stream
        role: Message role ("user" or "assistant")
    """
    try:
        logger.info(
            "Starting background orchestrator stream",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "role": role,
                "content_length": len(message_content)
            }
        )

        # Stream message through orchestrator (batches 2-8 messages before extraction)
        memory_manager = MemoryManager()
        injections = await memory_manager.stream_conversation_message(
            user_id=user_id,
            conversation_id=conversation_id,
            role=role,
            content=message_content
        )

        if injections is not None:
            logger.info(
                "Message streamed to orchestrator successfully (fire-and-forget)",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "injections_count": len(injections),
                    "status": "streamed"
                }
            )
        else:
            logger.warning(
                "Orchestrator stream failed (graceful degradation)",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "status": "degraded"
                }
            )

    except Exception as e:
        logger.error(
            f"Error in background orchestrator stream: {str(e)}",
            exc_info=True,
            extra={"user_id": user_id, "conversation_id": conversation_id}
        )


async def refresh_profile_background(user_id: str):
    """
    Background task to refresh user profile.

    This runs asynchronously and doesn't block the chat response.

    Args:
        user_id: User identifier
    """
    try:
        logger.info(
            "Starting background profile refresh",
            extra={"user_id": user_id}
        )

        # Create ProfileManager and refresh profile
        async with StateManager() as state:
            profile_manager = ProfileManager(redis_client=state.redis_client)
            await profile_manager.refresh_profile_background(user_id)

        logger.info(
            "Profile refresh completed in background",
            extra={"user_id": user_id}
        )

    except Exception as e:
        logger.error(
            f"Error in background profile refresh: {str(e)}",
            exc_info=True,
            extra={"user_id": user_id}
        )


class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    user_id: str = Field(..., description="Unique user identifier")
    platform: str = Field(..., description="Platform identifier (e.g., 'telegram')")
    message: str = Field(..., min_length=1, description="User message content")
    context: Optional[dict] = Field(default={}, description="Additional context metadata")
    files: Optional[List[FileAttachment]] = Field(
        default=None,
        description="Optional list of file attachments for multimodal processing",
        max_length=MAX_FILES_PER_REQUEST
    )


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    conversation_id: str = Field(..., description="Unique conversation identifier")
    status: str = Field(..., description="Conversation status (e.g., 'streaming')")
    stream_url: str = Field(..., description="URL to connect for SSE streaming")
    timestamp: str = Field(..., description="Response timestamp (ISO 8601)")


@router.post("/chat", response_model=ChatResponse)
@observe(name="chat_request", as_type="trace")
async def create_chat(
    request: ChatRequest,
    background_tasks: BackgroundTasks,
    http_request: Request
):
    """
    Process incoming chat message and initiate streaming response.

    Langfuse @observe() decorator automatically traces:
    - Input: request (user_id, platform, message, context)
    - Output: ChatResponse (conversation_id, stream_url)
    - Duration, errors, and session linking
    - Nested spans for memory retrieval

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
    # Override user_id from auth middleware if available (web UI flow)
    # This ensures the authenticated user_id is used instead of client-provided one
    if hasattr(http_request.state, 'user_id') and http_request.state.user_id:
        if request.user_id != http_request.state.user_id:
            logger.info(
                "Overriding client user_id with authenticated user_id",
                extra={
                    "client_user_id": request.user_id,
                    "auth_user_id": http_request.state.user_id,
                    "event": "user_id_override"
                }
            )
        # Create a new request object with the correct user_id
        request = ChatRequest(
            user_id=http_request.state.user_id,
            platform=request.platform,
            message=request.message,
            context=request.context,
            files=request.files
        )

    # Detect decision support request for memory retrieval
    needs_decision_support = is_decision_support_request(request.message)

    # Log file metadata if present (never log file content)
    files_metadata = None
    if request.files:
        files_metadata = get_files_metadata(request.files)

        # Validate files
        validation_errors = validate_files(request.files)
        if validation_errors:
            raise HTTPException(
                status_code=400,
                detail=f"File validation failed: {'; '.join(validation_errors)}"
            )

    logger.info(
        "Chat request received",
        extra={
            "user_id": request.user_id,
            "platform": request.platform,
            "message_length": len(request.message),
            "needs_decision_support": needs_decision_support,
            "has_files": request.files is not None,
            "files_metadata": files_metadata,
            "event": "multimodal_request" if request.files else "text_request"
        }
    )

    # Update trace metadata (decorator handles trace creation)
    if LANGFUSE_AVAILABLE:
        try:
            langfuse_context.update_current_trace(
                user_id=request.user_id,
                metadata={
                    "platform": request.platform,
                    "message_length": len(request.message),
                    "needs_decision_support": needs_decision_support,
                    "message": request.message[:100]  # First 100 chars for context
                }
            )
        except Exception:
            pass  # Fire-and-forget

    try:
        async with StateManager() as state:
            # Get or create session
            session = await state.get_session(request.user_id)

            if not session:
                # Create new session
                session = await state.create_session(request.user_id, request.platform)

                # Also create conversation metadata so it appears in conversation list (Epic 20 Web UI)
                # This ensures the conversation is tracked in conversations:{user_id} sorted set
                conversation_title = request.message[:50] + ("..." if len(request.message) > 50 else "")
                conversation_id = session["conversation_id"]

                now = datetime.now(timezone.utc)
                now_iso = now.isoformat().replace("+00:00", "Z")
                now_timestamp = now.timestamp()

                # Store conversation metadata using session's conversation_id
                meta_key = f"conversation:{conversation_id}:meta"
                conversations_key = f"conversations:{request.user_id}"

                pipe = state.redis_client.pipeline()
                pipe.hset(meta_key, mapping={
                    "user_id": request.user_id,
                    "title": conversation_title,
                    "created_at": now_iso,
                    "updated_at": now_iso
                })
                pipe.expire(meta_key, state.CONVERSATION_META_TTL)
                pipe.zadd(conversations_key, {conversation_id: now_timestamp})
                pipe.expire(conversations_key, state.CONVERSATION_META_TTL)
                await pipe.execute()

                logger.info(
                    "New session created with conversation metadata",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": conversation_id,
                        "title": conversation_title
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

            # Update trace with session_id to link with stream trace (decorator handles trace management)
            if LANGFUSE_AVAILABLE:
                try:
                    langfuse_context.update_current_trace(session_id=conversation_id)
                    logger.info(
                        f"[LANGFUSE] Updated chat trace with session_id: {conversation_id}",
                        extra={"conversation_id": conversation_id}
                    )
                except Exception:
                    pass  # Fire-and-forget: ignore tracing failures

            # Store user message in conversation history
            user_message = {
                "role": "user",
                "content": request.message
            }
            await state.add_message(conversation_id, user_message)

            # Update user activity timestamp (non-blocking, fire-and-forget)
            try:
                tracker = ActivityTracker(redis_client=state.redis_client)
                await tracker.record_activity(request.user_id)
            except Exception as e:
                # Fire-and-forget: log error but don't fail chat flow
                logger.warning(
                    f"Failed to update user activity: {str(e)}",
                    extra={
                        "user_id": request.user_id,
                        "error_type": type(e).__name__
                    }
                )

            # Check for proactive feedback context (Story 13.10)
            # If user is responding to a recent proactive message, store context for streaming endpoint
            try:
                from api.proactive.feedback import get_proactive_context

                proactive_context = await get_proactive_context(
                    request.user_id,
                    state.redis_client
                )

                if proactive_context:
                    # Store proactive context in Redis for streaming endpoint
                    # Similar to memory_context and profile_cache patterns
                    proactive_context_key = f"proactive_context:{conversation_id}"
                    await state.redis_client.setex(
                        proactive_context_key,
                        300,  # 5 minutes TTL (same as other context caches)
                        json.dumps(proactive_context)
                    )

                    logger.info(
                        "Proactive feedback context detected and stored",
                        extra={
                            "user_id": request.user_id,
                            "conversation_id": conversation_id,
                            "trigger_id": proactive_context.get("trigger_id"),
                            "intent_name": proactive_context.get("trigger_details", {}).get("intent_name", "Unknown"),
                            "time_since_message_seconds": proactive_context.get("time_since_message_seconds")
                        }
                    )

            except Exception as e:
                # Fire-and-forget: log error but don't fail chat flow
                # Graceful degradation - feedback detection is optional
                logger.warning(
                    f"Failed to detect proactive feedback context: {str(e)}",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": conversation_id,
                        "error_type": type(e).__name__
                    }
                )

            # Load and manage user profile (non-blocking)
            try:
                profile_manager = ProfileManager(redis_client=state.redis_client)

                # Load profile from cache (fast, <10ms)
                profile = await profile_manager.load_profile_from_cache(request.user_id)

                # Increment message count for trigger tracking
                message_count = await profile_manager.increment_message_count(request.user_id)

                # Check if profile refresh should be triggered
                # Pass message_count to avoid race condition from re-reading Redis
                should_refresh = await profile_manager.check_refresh_triggers(
                    request.user_id,
                    message_count=message_count
                )

                logger.info(
                    "Profile loaded",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": conversation_id,
                        "cached": profile.get("cached", False),
                        "completeness": profile.get("completeness", 0),
                        "message_count": message_count,
                        "refresh_triggered": should_refresh
                    }
                )

                # Trigger background refresh if needed
                if should_refresh:
                    background_tasks.add_task(
                        refresh_profile_background,
                        request.user_id
                    )
                    logger.info(
                        "Profile refresh queued",
                        extra={
                            "user_id": request.user_id,
                            "message_count": message_count
                        }
                    )

                # Store profile in Redis for streaming endpoint (TTL: 5 minutes)
                # Only store if profile has data (completeness > 0)
                if profile.get("completeness", 0) > 0:
                    profile_key = f"profile_cache:{conversation_id}"
                    await state.redis_client.setex(
                        profile_key,
                        300,  # 5 minutes TTL
                        json.dumps(profile)
                    )
                    logger.info(
                        "Profile cached for streaming endpoint",
                        extra={
                            "user_id": request.user_id,
                            "conversation_id": conversation_id,
                            "completeness": profile.get("completeness", 0)
                        }
                    )

            except Exception as e:
                # Graceful degradation: log error but continue without profile
                logger.error(
                    f"Profile loading failed, continuing without profile: {str(e)}",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": conversation_id,
                        "error_type": type(e).__name__
                    },
                    exc_info=True
                )

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

                    # Emit status: Starting memory retrieval
                    emit_status("Retrieving your memories...", icon="🔍")

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

                    # Emit status: Memory retrieval complete
                    if memory_count > 0:
                        emit_status(f"Found {memory_count} relevant memories", icon="✅")
                    else:
                        emit_status("No relevant memories found", icon="✅")

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

            # Store files in Redis for stream endpoint access (if present)
            # Files are stored temporarily and discarded after LLM response completes
            if request.files:
                files_key = f"files:{conversation_id}"
                # Convert FileAttachment objects to dicts for JSON serialization
                files_data = [f.model_dump() for f in request.files]
                await state.redis_client.setex(
                    files_key,
                    300,  # 5 minutes TTL (same as other context caches)
                    json.dumps(files_data)
                )
                logger.info(
                    "Files stored for stream endpoint",
                    extra={
                        "user_id": request.user_id,
                        "conversation_id": conversation_id,
                        "file_count": len(request.files),
                        "total_size_bytes": sum(f.size_bytes for f in request.files),
                        "event": "files_stored"
                    }
                )

            # Trigger background memory storage on EVERY message (fire-and-forget)
            # This ensures comprehensive memory coverage for personalization
            logger.info(
                "Triggering automatic memory storage",
                extra={
                    "user_id": request.user_id,
                    "conversation_id": conversation_id
                }
            )

            # Add background task (runs after response is sent)
            # Streams user message through orchestrator for batched memory storage
            background_tasks.add_task(
                store_conversation_memory_background,
                request.user_id,
                conversation_id,
                request.message,  # Pass message content for orchestrator
                "user"  # Role is always "user" for incoming chat messages
            )

            logger.info(
                "Chat conversation initiated",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": request.user_id,
                    "stream_url": stream_url,
                    "memory_storage_queued": True  # Now queued for every message
                }
            )

            # Update trace with success status (decorator handles output automatically)
            if LANGFUSE_AVAILABLE:
                try:
                    langfuse_context.update_current_trace(
                        metadata={
                            "response_status": "success",
                            "conversation_id": conversation_id
                        }
                    )
                except Exception:
                    pass  # Fire-and-forget: ignore tracing failures

            return ChatResponse(
                conversation_id=conversation_id,
                status="streaming",
                stream_url=stream_url,
                timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            )

    except StateError as e:
        # Decorator automatically captures exceptions, just log it
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
        # Decorator automatically captures exceptions, just log it
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
