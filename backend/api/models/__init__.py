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

__all__ = [
    "FileAttachment",
    "FileCategory",
    "SUPPORTED_MIME_TYPES",
    "FILE_SIZE_LIMITS",
    "MAX_FILES_PER_REQUEST",
    "validate_files",
    "get_files_metadata",
]
