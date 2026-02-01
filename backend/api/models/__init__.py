"""
Backend API Models

Pydantic models for request/response validation.
"""

from api.models.file_attachment import (
    FileAttachment,
    FileCategory,
    SUPPORTED_MIME_TYPES,
    FILE_SIZE_LIMITS,
    MAX_FILES_PER_REQUEST,
    validate_files,
    get_files_metadata,
)
from api.models.conversation import (
    Conversation,
    ConversationListResponse,
    CreateConversationRequest,
    CreateConversationResponse,
    UpdateConversationRequest,
    UpdateConversationResponse,
    DeleteConversationResponse,
    Message,
    PaginationInfo,
    ConversationDetailResponse,
    MessageListResponse,
)

__all__ = [
    # File attachment models
    "FileAttachment",
    "FileCategory",
    "SUPPORTED_MIME_TYPES",
    "FILE_SIZE_LIMITS",
    "MAX_FILES_PER_REQUEST",
    "validate_files",
    "get_files_metadata",
    # Conversation models
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
