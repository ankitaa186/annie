"""
Session Management Routes

Provides endpoints for session lifecycle:
- POST /api/session - Create or resume session on app load
- PATCH /api/session - Update current conversation
- GET /api/session - Get current session state

Session tracks:
- user_id: Authenticated user
- platform: "web" or "telegram"
- current_conversation_id: Active conversation (nullable)
- last_activity: Timestamp for TTL refresh
"""

import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.logging import get_logger
from api.state import StateManager, StateError

logger = get_logger(__name__)

router = APIRouter(prefix="/api/session", tags=["session"])


# Request/Response Models

class CreateSessionRequest(BaseModel):
    """Request to create or resume a session."""
    platform: str = Field(default="web", description="Platform identifier")
    conversation_id: Optional[str] = Field(
        default=None,
        description="Optional conversation to resume"
    )


class UpdateSessionRequest(BaseModel):
    """Request to update session's current conversation."""
    conversation_id: Optional[str] = Field(
        default=None,
        description="Conversation ID to switch to (null to clear)"
    )


class SessionResponse(BaseModel):
    """Session state response."""
    user_id: str
    platform: str
    conversation_id: Optional[str] = Field(
        default=None,
        description="Current active conversation (null if none)"
    )
    created_at: str
    last_activity: str


def get_user_id(request: Request) -> str:
    """
    Extract user_id from authenticated request.

    The Cloudflare auth middleware attaches user_id to request.state.
    In dev mode, this is auto-populated with the default dev user.

    Raises:
        HTTPException: If user not authenticated
    """
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )
    return user_id


@router.post("", response_model=SessionResponse)
async def create_or_resume_session(
    request: Request,
    body: Optional[CreateSessionRequest] = None
):
    """
    Create or resume a session.

    Called when app loads. Returns existing session if valid,
    or creates a new one.

    If conversation_id is provided, validates ownership and sets
    as current conversation.

    Args:
        request: FastAPI Request with authenticated user
        body: Optional session configuration

    Returns:
        SessionResponse with current session state
    """
    user_id = get_user_id(request)
    platform = body.platform if body else "web"
    requested_conversation_id = body.conversation_id if body else None
    start_time = time.time()

    logger.info(
        "Session request",
        extra={
            "user_id": user_id,
            "platform": platform,
            "requested_conversation_id": requested_conversation_id,
            "event": "session_create_request"
        }
    )

    try:
        async with StateManager() as state:
            # Check for existing session
            session = await state.get_session(user_id)

            if session:
                # Session exists - update activity and optionally switch conversation
                if requested_conversation_id:
                    # User wants to resume specific conversation
                    resumed = await state.resume_conversation(
                        user_id=user_id,
                        conversation_id=requested_conversation_id,
                        platform=platform
                    )
                    if resumed:
                        session = resumed
                    else:
                        logger.warning(
                            "Could not resume requested conversation",
                            extra={
                                "user_id": user_id,
                                "conversation_id": requested_conversation_id
                            }
                        )
                else:
                    # Just refresh activity
                    await state.update_session_activity(user_id)

                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "Existing session resumed",
                    extra={
                        "user_id": user_id,
                        "conversation_id": session.get("conversation_id"),
                        "duration_ms": duration_ms,
                        "event": "session_resumed"
                    }
                )
            else:
                # No session - create new one
                if requested_conversation_id:
                    # Try to resume specific conversation
                    session = await state.resume_conversation(
                        user_id=user_id,
                        conversation_id=requested_conversation_id,
                        platform=platform
                    )

                if not session:
                    # Create fresh session without conversation
                    session = await state.create_session_only(
                        user_id=user_id,
                        platform=platform
                    )

                duration_ms = int((time.time() - start_time) * 1000)
                logger.info(
                    "New session created",
                    extra={
                        "user_id": user_id,
                        "conversation_id": session.get("conversation_id"),
                        "duration_ms": duration_ms,
                        "event": "session_created"
                    }
                )

            return SessionResponse(
                user_id=user_id,
                platform=session.get("platform", platform),
                conversation_id=session.get("conversation_id"),
                created_at=session.get("created_at", datetime.now(timezone.utc).isoformat()),
                last_activity=session.get("last_activity", datetime.now(timezone.utc).isoformat())
            )

    except StateError as e:
        logger.error(
            "Session creation failed",
            extra={
                "user_id": user_id,
                "error": str(e),
                "event": "session_create_error"
            }
        )
        raise HTTPException(status_code=500, detail="Failed to create session")


@router.patch("", response_model=SessionResponse)
async def update_session(
    request: Request,
    body: UpdateSessionRequest
):
    """
    Update session's current conversation.

    Called when user clicks a conversation in sidebar.
    Validates ownership before switching.

    Args:
        request: FastAPI Request with authenticated user
        body: UpdateSessionRequest with new conversation_id

    Returns:
        SessionResponse with updated session state
    """
    user_id = get_user_id(request)
    conversation_id = body.conversation_id
    start_time = time.time()

    logger.info(
        "Session update request",
        extra={
            "user_id": user_id,
            "conversation_id": conversation_id,
            "event": "session_update_request"
        }
    )

    try:
        async with StateManager() as state:
            if conversation_id:
                # Switch to specific conversation
                session = await state.resume_conversation(
                    user_id=user_id,
                    conversation_id=conversation_id,
                    platform="web"
                )
                if not session:
                    raise HTTPException(
                        status_code=404,
                        detail="Conversation not found or access denied"
                    )
            else:
                # Clear current conversation (user starting fresh)
                session = await state.clear_current_conversation(user_id)
                if not session:
                    raise HTTPException(
                        status_code=404,
                        detail="No active session"
                    )

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Session updated",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "duration_ms": duration_ms,
                    "event": "session_updated"
                }
            )

            return SessionResponse(
                user_id=user_id,
                platform=session.get("platform", "web"),
                conversation_id=session.get("conversation_id"),
                created_at=session.get("created_at", ""),
                last_activity=session.get("last_activity", "")
            )

    except HTTPException:
        raise
    except StateError as e:
        logger.error(
            "Session update failed",
            extra={
                "user_id": user_id,
                "error": str(e),
                "event": "session_update_error"
            }
        )
        raise HTTPException(status_code=500, detail="Failed to update session")


@router.get("", response_model=SessionResponse)
async def get_session(request: Request):
    """
    Get current session state.

    Returns:
        SessionResponse with current session or 404 if no session
    """
    user_id = get_user_id(request)

    try:
        async with StateManager() as state:
            session = await state.get_session(user_id)

            if not session:
                raise HTTPException(
                    status_code=404,
                    detail="No active session"
                )

            return SessionResponse(
                user_id=user_id,
                platform=session.get("platform", "web"),
                conversation_id=session.get("conversation_id"),
                created_at=session.get("created_at", ""),
                last_activity=session.get("last_activity", "")
            )

    except HTTPException:
        raise
    except StateError as e:
        logger.error(
            "Get session failed",
            extra={
                "user_id": user_id,
                "error": str(e),
                "event": "session_get_error"
            }
        )
        raise HTTPException(status_code=500, detail="Failed to get session")
