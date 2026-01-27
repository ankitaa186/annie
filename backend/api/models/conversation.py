"""
Conversation Models for Web UI API

Pydantic models for conversation management endpoints.
Supports list, create, update, delete, and message retrieval operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Conversation(BaseModel):
    """
    Conversation summary model for list operations.

    Used in conversation list responses to show overview without full messages.
    """

    id: str = Field(..., description="Unique conversation identifier")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")
    message_count: int = Field(default=0, description="Total number of messages")
    last_message_preview: Optional[str] = Field(
        default=None,
        description="Preview of the last message (truncated to 100 chars)"
    )


class ConversationListResponse(BaseModel):
    """Response model for listing conversations."""

    conversations: List[Conversation] = Field(
        ...,
        description="List of conversations sorted by updated_at (most recent first)"
    )
    total: int = Field(..., description="Total number of conversations for user")


class CreateConversationRequest(BaseModel):
    """Request model for creating a new conversation."""

    title: Optional[str] = Field(
        default=None,
        description="Optional conversation title. Auto-generated if not provided."
    )


class CreateConversationResponse(BaseModel):
    """Response model for conversation creation."""

    id: str = Field(..., description="Unique conversation identifier")
    title: str = Field(..., description="Conversation title")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")


class UpdateConversationRequest(BaseModel):
    """Request model for updating conversation title."""

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="New conversation title"
    )


class UpdateConversationResponse(BaseModel):
    """Response model for conversation update."""

    id: str = Field(..., description="Conversation identifier")
    title: str = Field(..., description="Updated conversation title")
    updated_at: datetime = Field(..., description="Update timestamp (UTC)")


class DeleteConversationResponse(BaseModel):
    """Response model for conversation deletion."""

    status: str = Field(default="deleted", description="Deletion status")


class Message(BaseModel):
    """Message model for conversation history."""

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    timestamp: Optional[datetime] = Field(
        default=None,
        description="Message timestamp (UTC)"
    )
    tool_calls: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Tool calls made during this message (assistant only)"
    )


class PaginationInfo(BaseModel):
    """Pagination metadata."""

    page: int = Field(..., description="Current page number (1-indexed)")
    limit: int = Field(..., description="Items per page")
    total: int = Field(..., description="Total number of items")
    has_more: bool = Field(..., description="Whether more pages exist")


class ConversationDetailResponse(BaseModel):
    """
    Response model for getting a single conversation with messages.

    Includes full message history with pagination.
    """

    id: str = Field(..., description="Conversation identifier")
    title: str = Field(..., description="Conversation title")
    messages: List[Message] = Field(..., description="Paginated messages")
    created_at: datetime = Field(..., description="Creation timestamp (UTC)")
    updated_at: datetime = Field(..., description="Last update timestamp (UTC)")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")


class MessageListResponse(BaseModel):
    """Response model for paginated message history."""

    messages: List[Message] = Field(..., description="Paginated messages")
    pagination: PaginationInfo = Field(..., description="Pagination metadata")


# Export all models for __init__.py
__all__ = [
    "Conversation",
    "ConversationListResponse",
    "CreateConversationRequest",
    "CreateConversationResponse",
    "UpdateConversationRequest",
    "UpdateConversationResponse",
    "DeleteConversationResponse",
    "Message",
    "PaginationInfo",
    "ConversationDetailResponse",
    "MessageListResponse",
]
