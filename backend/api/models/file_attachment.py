"""
File Attachment Models for Multimodal LLM Processing

Defines the FileAttachment model shared between Telegram Bot and Backend API.
Supports Gemini native multimodal and ChatGPT vision/text extraction fallback.
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FileCategory(str, Enum):
    """File category enumeration."""
    IMAGE = "image"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"


# Supported MIME types and their metadata
SUPPORTED_MIME_TYPES: Dict[str, Dict] = {
    # Images (Gemini & ChatGPT native support)
    "image/jpeg": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},
    "image/png": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},
    "image/gif": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},
    "image/webp": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},

    # Documents (Gemini native, ChatGPT needs text extraction)
    "application/pdf": {"category": FileCategory.DOCUMENT, "gemini": True, "chatgpt": False},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "category": FileCategory.DOCUMENT, "gemini": True, "chatgpt": False
    },
    "text/plain": {"category": FileCategory.DOCUMENT, "gemini": True, "chatgpt": True},

    # Spreadsheets (Gemini native, ChatGPT needs text extraction)
    "text/csv": {"category": FileCategory.SPREADSHEET, "gemini": True, "chatgpt": True},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "category": FileCategory.SPREADSHEET, "gemini": True, "chatgpt": False
    },
}

# File size limits by category (in bytes)
FILE_SIZE_LIMITS = {
    FileCategory.IMAGE: 10 * 1024 * 1024,      # 10MB
    FileCategory.DOCUMENT: 20 * 1024 * 1024,   # 20MB
    FileCategory.SPREADSHEET: 20 * 1024 * 1024, # 20MB
}

# Maximum files per request
MAX_FILES_PER_REQUEST = 10


class FileAttachment(BaseModel):
    """
    Represents a file attachment for LLM processing.

    This model is used to transport files from Telegram Bot to Backend API.
    Files are base64 encoded for JSON transport.
    """
    filename: str = Field(..., description="Original filename")
    mime_type: str = Field(..., description="MIME type of the file")
    size_bytes: int = Field(..., ge=0, description="File size in bytes")
    data_base64: str = Field(..., description="Base64-encoded file content")

    @field_validator('mime_type')
    @classmethod
    def validate_mime_type(cls, v: str) -> str:
        """Validate that MIME type is supported."""
        if v not in SUPPORTED_MIME_TYPES:
            raise ValueError(f"Unsupported MIME type: {v}")
        return v

    @field_validator('size_bytes')
    @classmethod
    def validate_size(cls, v: int, info) -> int:
        """Validate file size against limits."""
        if v == 0:
            raise ValueError("File is empty")
        return v

    def get_category(self) -> Optional[FileCategory]:
        """Get file category from MIME type."""
        type_info = SUPPORTED_MIME_TYPES.get(self.mime_type)
        if type_info:
            return type_info["category"]
        return None

    def is_supported_by_gemini(self) -> bool:
        """Check if file type is natively supported by Gemini."""
        type_info = SUPPORTED_MIME_TYPES.get(self.mime_type)
        return type_info.get("gemini", False) if type_info else False

    def is_supported_by_chatgpt(self) -> bool:
        """Check if file type is natively supported by ChatGPT (images only)."""
        type_info = SUPPORTED_MIME_TYPES.get(self.mime_type)
        return type_info.get("chatgpt", False) if type_info else False

    def is_image(self) -> bool:
        """Check if file is an image."""
        return self.get_category() == FileCategory.IMAGE

    def is_document(self) -> bool:
        """Check if file is a document (PDF, DOCX, TXT)."""
        return self.get_category() == FileCategory.DOCUMENT

    def is_spreadsheet(self) -> bool:
        """Check if file is a spreadsheet (XLSX, CSV)."""
        return self.get_category() == FileCategory.SPREADSHEET


def validate_files(files: List[FileAttachment]) -> List[str]:
    """
    Validate a list of file attachments.

    Args:
        files: List of FileAttachment objects

    Returns:
        List of validation error messages (empty if all valid)
    """
    errors = []

    # Check max files limit
    if len(files) > MAX_FILES_PER_REQUEST:
        errors.append(f"Too many files. Maximum {MAX_FILES_PER_REQUEST} files per request.")

    # Validate each file
    for i, file in enumerate(files):
        # Check size against category limit
        category = file.get_category()
        if category:
            limit = FILE_SIZE_LIMITS.get(category, 0)
            if file.size_bytes > limit:
                limit_mb = limit / (1024 * 1024)
                size_mb = file.size_bytes / (1024 * 1024)
                errors.append(
                    f"File '{file.filename}' is too large ({size_mb:.1f}MB). "
                    f"Maximum for {category.value}s: {limit_mb:.0f}MB"
                )

    return errors


def get_files_metadata(files: List[FileAttachment]) -> Dict:
    """
    Get metadata for logging about a list of files.

    Args:
        files: List of FileAttachment objects

    Returns:
        Metadata dictionary for logging (no file content)
    """
    return {
        "file_count": len(files),
        "total_size_bytes": sum(f.size_bytes for f in files),
        "mime_types": list(set(f.mime_type for f in files)),
        "filenames": [f.filename for f in files],
        "categories": list(set(f.get_category().value for f in files if f.get_category())),
    }
