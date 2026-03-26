"""
File Handler Module for Telegram Bot

This module handles file reception, validation, and processing for files
shared via Telegram. Supports images, documents, and spreadsheets.

Follows the process-and-discard model - files are processed in memory
and never persisted to disk or database.
"""

import asyncio
import base64
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple

from telegram import Document, Message, PhotoSize, Video
from telegram.ext import ContextTypes

from telegram_bot.logger import get_logger

logger = get_logger(__name__)


class FileCategory(Enum):
    """File category enumeration."""
    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"
    SPREADSHEET = "spreadsheet"


class FileErrorType(Enum):
    """File processing error types."""
    UNSUPPORTED_FORMAT = "unsupported_format"
    SIZE_EXCEEDED = "size_exceeded"
    DOWNLOAD_FAILED = "download_failed"
    CORRUPTED = "corrupted"
    EMPTY_FILE = "empty_file"
    PASSWORD_PROTECTED = "password_protected"
    TIMEOUT = "timeout"
    PROCESSING_FAILED = "processing_failed"


@dataclass
class FileAttachment:
    """
    Represents a file attachment for LLM processing.

    This model is shared between Telegram Bot and Backend API.
    Files are converted to base64 for JSON transport.
    """
    filename: str
    mime_type: str
    size_bytes: int
    data_base64: str

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "filename": self.filename,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "data_base64": self.data_base64
        }


@dataclass
class FileError:
    """Represents a file processing error."""
    filename: str
    error_type: FileErrorType
    message: str

    def to_dict(self) -> dict:
        """Convert to dictionary for logging/serialization."""
        return {
            "filename": self.filename,
            "error_type": self.error_type.value,
            "message": self.message
        }


@dataclass
class FileProcessingResult:
    """Result of processing one or more files."""
    successful: List[FileAttachment] = field(default_factory=list)
    failed: List[FileError] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Check if any files failed to process."""
        return len(self.failed) > 0

    @property
    def has_successful(self) -> bool:
        """Check if any files were processed successfully."""
        return len(self.successful) > 0

    @property
    def all_failed(self) -> bool:
        """Check if all files failed to process."""
        return len(self.failed) > 0 and len(self.successful) == 0


# Supported MIME types and their metadata
SUPPORTED_MIME_TYPES = {
    # Images (Gemini & ChatGPT native support)
    "image/jpeg": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},
    "image/png": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},
    "image/gif": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},
    "image/webp": {"category": FileCategory.IMAGE, "gemini": True, "chatgpt": True},

    # Videos (Gemini native support)
    "video/mp4": {"category": FileCategory.VIDEO, "gemini": True, "chatgpt": False},
    "video/mpeg": {"category": FileCategory.VIDEO, "gemini": True, "chatgpt": False},
    "video/quicktime": {"category": FileCategory.VIDEO, "gemini": True, "chatgpt": False},
    "video/webm": {"category": FileCategory.VIDEO, "gemini": True, "chatgpt": False},
    "video/x-msvideo": {"category": FileCategory.VIDEO, "gemini": True, "chatgpt": False},
    "video/3gpp": {"category": FileCategory.VIDEO, "gemini": True, "chatgpt": False},

    # Documents (Gemini native, ChatGPT needs extraction)
    "application/pdf": {"category": FileCategory.DOCUMENT, "gemini": True, "chatgpt": False},
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {
        "category": FileCategory.DOCUMENT, "gemini": True, "chatgpt": False
    },
    "text/plain": {"category": FileCategory.DOCUMENT, "gemini": True, "chatgpt": True},

    # Spreadsheets (Gemini native, ChatGPT needs extraction)
    "text/csv": {"category": FileCategory.SPREADSHEET, "gemini": True, "chatgpt": True},
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": {
        "category": FileCategory.SPREADSHEET, "gemini": True, "chatgpt": False
    },
}

# File size limits by category (in bytes)
FILE_SIZE_LIMITS = {
    FileCategory.IMAGE: 10 * 1024 * 1024,      # 10MB
    FileCategory.VIDEO: 50 * 1024 * 1024,      # 50MB (Telegram bot limit)
    FileCategory.DOCUMENT: 20 * 1024 * 1024,   # 20MB
    FileCategory.SPREADSHEET: 20 * 1024 * 1024, # 20MB
}

# Maximum number of files per message
MAX_FILES_PER_MESSAGE = 10

# Timeouts (in seconds)
FILE_DOWNLOAD_TIMEOUT = 30.0
FILE_DOWNLOAD_RETRY_DELAY = 2.0
FILE_DOWNLOAD_MAX_RETRIES = 1

# File type icons for acknowledgment messages
FILE_TYPE_ICONS = {
    FileCategory.IMAGE: "📷",
    FileCategory.VIDEO: "🎬",
    FileCategory.DOCUMENT: "📄",
    FileCategory.SPREADSHEET: "📊",
}

# Multi-file header icon
MULTI_FILE_ICON = "📎"


def get_file_category(mime_type: str) -> Optional[FileCategory]:
    """
    Get file category from MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        FileCategory or None if unsupported
    """
    type_info = SUPPORTED_MIME_TYPES.get(mime_type)
    if type_info:
        return type_info["category"]
    return None


def is_mime_type_supported(mime_type: str) -> bool:
    """
    Check if MIME type is supported.

    Args:
        mime_type: MIME type string

    Returns:
        True if supported, False otherwise
    """
    return mime_type in SUPPORTED_MIME_TYPES


def get_size_limit(mime_type: str) -> int:
    """
    Get size limit for a MIME type.

    Args:
        mime_type: MIME type string

    Returns:
        Size limit in bytes, or 0 if unsupported
    """
    category = get_file_category(mime_type)
    if category:
        return FILE_SIZE_LIMITS.get(category, 0)
    return 0


def validate_file_size(mime_type: str, size_bytes: int) -> Tuple[bool, Optional[str]]:
    """
    Validate file size against limits.

    Args:
        mime_type: MIME type string
        size_bytes: File size in bytes

    Returns:
        Tuple of (is_valid, error_message)
    """
    if size_bytes == 0:
        return False, "File is empty"

    limit = get_size_limit(mime_type)
    if limit == 0:
        return False, "Unsupported file type"

    if size_bytes > limit:
        limit_mb = limit / (1024 * 1024)
        size_mb = size_bytes / (1024 * 1024)
        return False, f"File too large ({size_mb:.1f}MB). Maximum: {limit_mb:.0f}MB"

    return True, None


def normalize_mime_type(mime_type: Optional[str], filename: str) -> str:
    """
    Normalize and validate MIME type, inferring from filename if needed.

    Args:
        mime_type: MIME type from Telegram (may be None)
        filename: Original filename

    Returns:
        Normalized MIME type string
    """
    # Extension to MIME type mapping for common types
    extension_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".mpeg": "video/mpeg",
        ".mpg": "video/mpeg",
        ".mov": "video/quicktime",
        ".webm": "video/webm",
        ".avi": "video/x-msvideo",
        ".3gp": "video/3gpp",
        ".pdf": "application/pdf",
        ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ".txt": "text/plain",
        ".csv": "text/csv",
        ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    }

    # If MIME type is provided and valid, use it
    if mime_type and mime_type in SUPPORTED_MIME_TYPES:
        return mime_type

    # Try to infer from filename extension
    filename_lower = filename.lower()
    for ext, inferred_mime in extension_map.items():
        if filename_lower.endswith(ext):
            return inferred_mime

    # Return original or default
    return mime_type or "application/octet-stream"


def get_file_icon(mime_type: str) -> str:
    """
    Get display icon for file type.

    Args:
        mime_type: MIME type string

    Returns:
        Emoji icon string
    """
    category = get_file_category(mime_type)
    if category:
        return FILE_TYPE_ICONS.get(category, "📎")
    return "📎"


async def download_file_with_retry(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    max_retries: int = FILE_DOWNLOAD_MAX_RETRIES,
    timeout: float = FILE_DOWNLOAD_TIMEOUT,
    retry_delay: float = FILE_DOWNLOAD_RETRY_DELAY
) -> bytes:
    """
    Download file from Telegram with retry logic.

    Args:
        context: Telegram bot context
        file_id: Telegram file ID
        max_retries: Maximum retry attempts (default: 1)
        timeout: Download timeout in seconds (default: 30)
        retry_delay: Delay between retries in seconds (default: 2)

    Returns:
        File bytes

    Raises:
        Exception: If download fails after all retries
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            # Get file info with timeout
            file = await asyncio.wait_for(
                context.bot.get_file(file_id),
                timeout=timeout
            )

            # Download file content with timeout
            file_bytes = await asyncio.wait_for(
                file.download_as_bytearray(),
                timeout=timeout
            )

            logger.info(
                "File downloaded successfully",
                extra={
                    "file_id": file_id[:20] + "..." if len(file_id) > 20 else file_id,
                    "size_bytes": len(file_bytes),
                    "attempt": attempt + 1,
                    "event": "file_download_success"
                }
            )

            return bytes(file_bytes)

        except asyncio.TimeoutError as e:
            last_error = e
            logger.warning(
                "File download timeout",
                extra={
                    "file_id": file_id[:20] + "..." if len(file_id) > 20 else file_id,
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "timeout_seconds": timeout,
                    "event": "file_download_timeout"
                }
            )

        except Exception as e:
            last_error = e
            logger.warning(
                "File download failed",
                extra={
                    "file_id": file_id[:20] + "..." if len(file_id) > 20 else file_id,
                    "attempt": attempt + 1,
                    "max_retries": max_retries,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "event": "file_download_failed"
                }
            )

        # Retry if not last attempt
        if attempt < max_retries:
            logger.info(
                f"Retrying file download in {retry_delay}s",
                extra={
                    "file_id": file_id[:20] + "..." if len(file_id) > 20 else file_id,
                    "attempt": attempt + 1,
                    "retry_delay": retry_delay,
                    "event": "file_download_retry"
                }
            )
            await asyncio.sleep(retry_delay)

    # All retries exhausted
    raise Exception(f"File download failed after {max_retries + 1} attempts: {last_error}")


def encode_file_to_base64(file_bytes: bytes) -> str:
    """
    Encode file bytes to base64 string.

    Args:
        file_bytes: Raw file bytes

    Returns:
        Base64 encoded string
    """
    return base64.b64encode(file_bytes).decode("utf-8")


async def process_photo(
    photo: PhotoSize,
    context: ContextTypes.DEFAULT_TYPE
) -> Tuple[Optional[FileAttachment], Optional[FileError]]:
    """
    Process a photo attachment from Telegram.

    Args:
        photo: Telegram PhotoSize object (largest size)
        context: Bot context

    Returns:
        Tuple of (FileAttachment or None, FileError or None)
    """
    # Photos are always JPEG
    mime_type = "image/jpeg"
    filename = f"photo_{photo.file_unique_id}.jpg"
    size_bytes = photo.file_size or 0

    # Validate size
    is_valid, error_msg = validate_file_size(mime_type, size_bytes)
    if not is_valid:
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.SIZE_EXCEEDED if "too large" in (error_msg or "") else FileErrorType.EMPTY_FILE,
            message=error_msg or "Invalid file"
        )

    try:
        # Download file
        file_bytes = await download_file_with_retry(context, photo.file_id)

        # Validate downloaded content
        if len(file_bytes) == 0:
            return None, FileError(
                filename=filename,
                error_type=FileErrorType.EMPTY_FILE,
                message="Downloaded file is empty"
            )

        # Encode to base64
        data_base64 = encode_file_to_base64(file_bytes)

        return FileAttachment(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            data_base64=data_base64
        ), None

    except asyncio.TimeoutError:
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.TIMEOUT,
            message="Download timed out. Please try again."
        )
    except Exception as e:
        logger.error(
            "Photo processing failed",
            extra={
                "file_name": filename,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "photo_processing_failed"
            }
        )
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.DOWNLOAD_FAILED,
            message="Failed to download photo. Please try again."
        )


async def process_document(
    document: Document,
    context: ContextTypes.DEFAULT_TYPE
) -> Tuple[Optional[FileAttachment], Optional[FileError]]:
    """
    Process a document attachment from Telegram.

    Args:
        document: Telegram Document object
        context: Bot context

    Returns:
        Tuple of (FileAttachment or None, FileError or None)
    """
    filename = document.file_name or f"document_{document.file_unique_id}"
    mime_type = normalize_mime_type(document.mime_type, filename)
    size_bytes = document.file_size or 0

    # Check if MIME type is supported
    if not is_mime_type_supported(mime_type):
        supported_types = ", ".join([
            "JPEG, PNG, GIF, WEBP (images)",
            "MP4, MPEG, MOV, WEBM, AVI, 3GP (videos)",
            "PDF, DOCX, TXT (documents)",
            "XLSX, CSV (spreadsheets)"
        ])
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.UNSUPPORTED_FORMAT,
            message=f"Unsupported file type. I support: {supported_types}"
        )

    # Validate size
    is_valid, error_msg = validate_file_size(mime_type, size_bytes)
    if not is_valid:
        error_type = FileErrorType.EMPTY_FILE if size_bytes == 0 else FileErrorType.SIZE_EXCEEDED
        return None, FileError(
            filename=filename,
            error_type=error_type,
            message=error_msg or "Invalid file"
        )

    try:
        # Download file
        file_bytes = await download_file_with_retry(context, document.file_id)

        # Validate downloaded content
        if len(file_bytes) == 0:
            return None, FileError(
                filename=filename,
                error_type=FileErrorType.EMPTY_FILE,
                message="Downloaded file is empty"
            )

        # Encode to base64
        data_base64 = encode_file_to_base64(file_bytes)

        logger.info(
            "Document processed successfully",
            extra={
                "file_name": filename,
                "mime_type": mime_type,
                "size_bytes": len(file_bytes),
                "event": "document_processed"
            }
        )

        return FileAttachment(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            data_base64=data_base64
        ), None

    except asyncio.TimeoutError:
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.TIMEOUT,
            message="Download timed out. Please try again."
        )
    except Exception as e:
        logger.error(
            "Document processing failed",
            extra={
                "file_name": filename,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "document_processing_failed"
            }
        )
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.DOWNLOAD_FAILED,
            message="Failed to download file. Please try again."
        )


async def process_video(
    video: Video,
    context: ContextTypes.DEFAULT_TYPE
) -> Tuple[Optional[FileAttachment], Optional[FileError]]:
    """
    Process a video attachment from Telegram.

    Args:
        video: Telegram Video object
        context: Bot context

    Returns:
        Tuple of (FileAttachment or None, FileError or None)
    """
    # Videos are typically MP4
    mime_type = video.mime_type or "video/mp4"
    filename = video.file_name or f"video_{video.file_unique_id}.mp4"
    size_bytes = video.file_size or 0

    # Normalize mime type
    mime_type = normalize_mime_type(mime_type, filename)

    # Check if MIME type is supported
    if not is_mime_type_supported(mime_type):
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.UNSUPPORTED_FORMAT,
            message=f"Unsupported video format: {mime_type}"
        )

    # Validate size
    is_valid, error_msg = validate_file_size(mime_type, size_bytes)
    if not is_valid:
        error_type = FileErrorType.EMPTY_FILE if size_bytes == 0 else FileErrorType.SIZE_EXCEEDED
        return None, FileError(
            filename=filename,
            error_type=error_type,
            message=error_msg or "Invalid video"
        )

    try:
        # Download file
        file_bytes = await download_file_with_retry(context, video.file_id)

        # Validate downloaded content
        if len(file_bytes) == 0:
            return None, FileError(
                filename=filename,
                error_type=FileErrorType.EMPTY_FILE,
                message="Downloaded video is empty"
            )

        # Encode to base64
        data_base64 = encode_file_to_base64(file_bytes)

        logger.info(
            "Video processed successfully",
            extra={
                "file_name": filename,
                "mime_type": mime_type,
                "size_bytes": len(file_bytes),
                "duration": video.duration,
                "width": video.width,
                "height": video.height,
                "event": "video_processed"
            }
        )

        return FileAttachment(
            filename=filename,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            data_base64=data_base64
        ), None

    except asyncio.TimeoutError:
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.TIMEOUT,
            message="Video download timed out. Please try a smaller video."
        )
    except Exception as e:
        logger.error(
            "Video processing failed",
            extra={
                "file_name": filename,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "video_processing_failed"
            }
        )
        return None, FileError(
            filename=filename,
            error_type=FileErrorType.DOWNLOAD_FAILED,
            message="Failed to download video. Please try again."
        )


async def process_message_files(
    message: Message,
    context: ContextTypes.DEFAULT_TYPE
) -> FileProcessingResult:
    """
    Process all files in a Telegram message.

    Handles:
    - Single photos
    - Photo albums (media groups)
    - Videos
    - Document attachments

    Args:
        message: Telegram Message object
        context: Bot context

    Returns:
        FileProcessingResult with successful and failed files
    """
    result = FileProcessingResult()

    # Check for photos (including media groups)
    if message.photo:
        # Get the largest photo size
        largest_photo = message.photo[-1]
        attachment, error = await process_photo(largest_photo, context)
        if attachment:
            result.successful.append(attachment)
        if error:
            result.failed.append(error)

    # Check for video
    if message.video:
        attachment, error = await process_video(message.video, context)
        if attachment:
            result.successful.append(attachment)
        if error:
            result.failed.append(error)

    # Check for document
    if message.document:
        attachment, error = await process_document(message.document, context)
        if attachment:
            result.successful.append(attachment)
        if error:
            result.failed.append(error)

    # Log processing result
    if result.successful or result.failed:
        logger.info(
            "Message files processed",
            extra={
                "successful_count": len(result.successful),
                "failed_count": len(result.failed),
                "total_size_bytes": sum(f.size_bytes for f in result.successful),
                "event": "message_files_processed"
            }
        )

    return result


def has_processable_files(message: Message) -> bool:
    """
    Check if message contains files that can be processed.

    Args:
        message: Telegram Message object

    Returns:
        True if message has photos, videos, or documents
    """
    return bool(message.photo) or bool(message.video) or bool(message.document)


def format_file_acknowledgment(files: List[FileAttachment]) -> str:
    """
    Format acknowledgment message for received files.

    Args:
        files: List of successfully processed FileAttachment objects

    Returns:
        Formatted acknowledgment message string
    """
    if not files:
        return ""

    if len(files) == 1:
        icon = get_file_icon(files[0].mime_type)
        return f"{icon} File received, analyzing..."

    # Multiple files
    return f"📎 {len(files)} files received, analyzing..."


def format_file_error(error: FileError) -> str:
    """
    Format user-friendly error message for file processing failure.

    Args:
        error: FileError object

    Returns:
        User-friendly error message
    """
    error_messages = {
        FileErrorType.UNSUPPORTED_FORMAT: (
            f"Sorry, I can't process {error.filename}.\n\n"
            "I support:\n"
            "• Images: JPEG, PNG, GIF, WEBP\n"
            "• Videos: MP4, MPEG, MOV, WEBM, AVI, 3GP\n"
            "• Documents: PDF, DOCX, TXT\n"
            "• Spreadsheets: XLSX, CSV\n\n"
            "Could you send the file in one of these formats?"
        ),
        FileErrorType.SIZE_EXCEEDED: (
            f"That file is too large ({error.filename}).\n\n"
            "Please send:\n"
            "• Images under 10MB\n"
            "• Videos under 50MB\n"
            "• Documents under 20MB"
        ),
        FileErrorType.DOWNLOAD_FAILED: (
            f"I couldn't download {error.filename}.\n"
            "Could you try sending it again?"
        ),
        FileErrorType.CORRUPTED: (
            f"That file ({error.filename}) appears to be corrupted.\n"
            "Could you try sending it again?"
        ),
        FileErrorType.EMPTY_FILE: (
            f"That file ({error.filename}) appears to be empty."
        ),
        FileErrorType.PASSWORD_PROTECTED: (
            f"This PDF ({error.filename}) appears to be password-protected.\n"
            "Could you send an unlocked version?"
        ),
        FileErrorType.TIMEOUT: (
            f"Processing {error.filename} took too long.\n"
            "Could you try a smaller file?"
        ),
        FileErrorType.PROCESSING_FAILED: (
            f"I received {error.filename} but had trouble reading it.\n"
            "Could you:\n"
            "• Try sending it again\n"
            "• Or describe what's in it\n\n"
            "I'll do my best to help either way!"
        ),
    }

    return error_messages.get(
        error.error_type,
        f"I had trouble processing {error.filename}. Please try again."
    )


def format_partial_success_acknowledgment(result: FileProcessingResult) -> str:
    """
    Format acknowledgment for partial success (some files succeeded, some failed).

    Args:
        result: FileProcessingResult with both successful and failed files

    Returns:
        Formatted acknowledgment with status for each file
    """
    if not result.has_errors:
        # No errors - use regular acknowledgment
        return format_file_acknowledgment(result.successful)

    if result.all_failed:
        # All failed - show first error
        return format_file_error(result.failed[0])

    # Partial success
    total_files = len(result.successful) + len(result.failed)
    lines = [f"{MULTI_FILE_ICON} I received {total_files} files but couldn't process some:"]

    # Add successful files
    for file in result.successful:
        get_file_icon(file.mime_type)
        lines.append(f"• ✅ {file.filename} - ready")

    # Add failed files
    for error in result.failed:
        # Short error reason
        reason = {
            FileErrorType.UNSUPPORTED_FORMAT: "unsupported format",
            FileErrorType.SIZE_EXCEEDED: "too large",
            FileErrorType.DOWNLOAD_FAILED: "download failed",
            FileErrorType.CORRUPTED: "corrupted",
            FileErrorType.EMPTY_FILE: "empty file",
            FileErrorType.PASSWORD_PROTECTED: "password protected",
            FileErrorType.TIMEOUT: "timed out",
            FileErrorType.PROCESSING_FAILED: "processing failed",
        }.get(error.error_type, "error")
        lines.append(f"• ❌ {error.filename} - {reason}")

    lines.append("")
    lines.append("I'll analyze the files I can read. Let me take a look...")

    return "\n".join(lines)
