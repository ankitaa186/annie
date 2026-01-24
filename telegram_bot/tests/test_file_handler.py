"""
Tests for File Handler Module

Tests for file validation, processing, and acknowledgment formatting.
"""

import base64
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from telegram_bot.file_handler import (
    FileAttachment,
    FileCategory,
    FileError,
    FileErrorType,
    FileProcessingResult,
    SUPPORTED_MIME_TYPES,
    FILE_SIZE_LIMITS,
    get_file_category,
    is_mime_type_supported,
    get_size_limit,
    validate_file_size,
    normalize_mime_type,
    get_file_icon,
    encode_file_to_base64,
    download_file_with_retry,
    process_photo,
    process_document,
    process_message_files,
    has_processable_files,
    format_file_acknowledgment,
    format_file_error,
    format_partial_success_acknowledgment,
)


class TestFileCategory:
    """Tests for file category determination."""

    def test_get_file_category_image(self):
        """Test image MIME types return IMAGE category."""
        assert get_file_category("image/jpeg") == FileCategory.IMAGE
        assert get_file_category("image/png") == FileCategory.IMAGE
        assert get_file_category("image/gif") == FileCategory.IMAGE
        assert get_file_category("image/webp") == FileCategory.IMAGE

    def test_get_file_category_document(self):
        """Test document MIME types return DOCUMENT category."""
        assert get_file_category("application/pdf") == FileCategory.DOCUMENT
        assert get_file_category("text/plain") == FileCategory.DOCUMENT
        assert get_file_category(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ) == FileCategory.DOCUMENT

    def test_get_file_category_spreadsheet(self):
        """Test spreadsheet MIME types return SPREADSHEET category."""
        assert get_file_category("text/csv") == FileCategory.SPREADSHEET
        assert get_file_category(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ) == FileCategory.SPREADSHEET

    def test_get_file_category_unsupported(self):
        """Test unsupported MIME types return None."""
        assert get_file_category("application/zip") is None
        assert get_file_category("video/mp4") is None
        assert get_file_category("audio/mp3") is None
        assert get_file_category("unknown/type") is None


class TestMimeTypeValidation:
    """Tests for MIME type validation."""

    def test_is_mime_type_supported_valid(self):
        """Test supported MIME types return True."""
        for mime_type in SUPPORTED_MIME_TYPES.keys():
            assert is_mime_type_supported(mime_type) is True

    def test_is_mime_type_supported_invalid(self):
        """Test unsupported MIME types return False."""
        assert is_mime_type_supported("application/zip") is False
        assert is_mime_type_supported("video/mp4") is False
        assert is_mime_type_supported("") is False

    def test_normalize_mime_type_known(self):
        """Test MIME type normalization for known types."""
        assert normalize_mime_type("image/jpeg", "photo.jpg") == "image/jpeg"
        assert normalize_mime_type("application/pdf", "doc.pdf") == "application/pdf"

    def test_normalize_mime_type_from_extension(self):
        """Test MIME type inference from file extension."""
        assert normalize_mime_type(None, "photo.jpg") == "image/jpeg"
        assert normalize_mime_type(None, "photo.jpeg") == "image/jpeg"
        assert normalize_mime_type(None, "image.png") == "image/png"
        assert normalize_mime_type(None, "doc.pdf") == "application/pdf"
        assert normalize_mime_type(None, "data.csv") == "text/csv"
        assert normalize_mime_type(None, "sheet.xlsx") == (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    def test_normalize_mime_type_case_insensitive(self):
        """Test file extension matching is case insensitive."""
        assert normalize_mime_type(None, "PHOTO.JPG") == "image/jpeg"
        assert normalize_mime_type(None, "Doc.PDF") == "application/pdf"


class TestFileSizeValidation:
    """Tests for file size validation."""

    def test_get_size_limit_images(self):
        """Test size limits for image types (10MB)."""
        assert get_size_limit("image/jpeg") == 10 * 1024 * 1024
        assert get_size_limit("image/png") == 10 * 1024 * 1024

    def test_get_size_limit_documents(self):
        """Test size limits for document types (20MB)."""
        assert get_size_limit("application/pdf") == 20 * 1024 * 1024
        assert get_size_limit("text/plain") == 20 * 1024 * 1024

    def test_get_size_limit_spreadsheets(self):
        """Test size limits for spreadsheet types (20MB)."""
        assert get_size_limit("text/csv") == 20 * 1024 * 1024

    def test_get_size_limit_unsupported(self):
        """Test size limit for unsupported types returns 0."""
        assert get_size_limit("application/zip") == 0

    def test_validate_file_size_valid(self):
        """Test valid file sizes pass validation."""
        # Small image (1MB)
        is_valid, error = validate_file_size("image/jpeg", 1024 * 1024)
        assert is_valid is True
        assert error is None

        # At limit (10MB image)
        is_valid, error = validate_file_size("image/png", 10 * 1024 * 1024)
        assert is_valid is True
        assert error is None

    def test_validate_file_size_too_large(self):
        """Test oversized files fail validation."""
        # Image over 10MB
        is_valid, error = validate_file_size("image/jpeg", 11 * 1024 * 1024)
        assert is_valid is False
        assert "too large" in error.lower()

        # Document over 20MB
        is_valid, error = validate_file_size("application/pdf", 21 * 1024 * 1024)
        assert is_valid is False
        assert "too large" in error.lower()

    def test_validate_file_size_empty(self):
        """Test empty files fail validation."""
        is_valid, error = validate_file_size("image/jpeg", 0)
        assert is_valid is False
        assert "empty" in error.lower()

    def test_validate_file_size_unsupported(self):
        """Test unsupported types fail validation."""
        is_valid, error = validate_file_size("application/zip", 1024)
        assert is_valid is False
        assert "unsupported" in error.lower()


class TestFileIcons:
    """Tests for file icon mapping."""

    def test_get_file_icon_images(self):
        """Test image types get camera icon."""
        assert get_file_icon("image/jpeg") == "📷"
        assert get_file_icon("image/png") == "📷"

    def test_get_file_icon_documents(self):
        """Test document types get document icon."""
        assert get_file_icon("application/pdf") == "📄"
        assert get_file_icon("text/plain") == "📄"

    def test_get_file_icon_spreadsheets(self):
        """Test spreadsheet types get chart icon."""
        assert get_file_icon("text/csv") == "📊"

    def test_get_file_icon_unknown(self):
        """Test unknown types get default icon."""
        assert get_file_icon("application/zip") == "📎"


class TestBase64Encoding:
    """Tests for base64 encoding."""

    def test_encode_file_to_base64(self):
        """Test file encoding to base64."""
        test_bytes = b"Hello, World!"
        encoded = encode_file_to_base64(test_bytes)

        # Verify it's valid base64
        decoded = base64.b64decode(encoded)
        assert decoded == test_bytes

    def test_encode_empty_file(self):
        """Test encoding empty file."""
        encoded = encode_file_to_base64(b"")
        assert encoded == ""

    def test_encode_binary_file(self):
        """Test encoding binary content."""
        test_bytes = bytes(range(256))  # All byte values
        encoded = encode_file_to_base64(test_bytes)

        decoded = base64.b64decode(encoded)
        assert decoded == test_bytes


class TestFileAttachment:
    """Tests for FileAttachment dataclass."""

    def test_file_attachment_creation(self):
        """Test creating a FileAttachment."""
        attachment = FileAttachment(
            filename="test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            data_base64="SGVsbG8="
        )

        assert attachment.filename == "test.pdf"
        assert attachment.mime_type == "application/pdf"
        assert attachment.size_bytes == 1024
        assert attachment.data_base64 == "SGVsbG8="

    def test_file_attachment_to_dict(self):
        """Test FileAttachment serialization."""
        attachment = FileAttachment(
            filename="test.pdf",
            mime_type="application/pdf",
            size_bytes=1024,
            data_base64="SGVsbG8="
        )

        as_dict = attachment.to_dict()
        assert as_dict["filename"] == "test.pdf"
        assert as_dict["mime_type"] == "application/pdf"
        assert as_dict["size_bytes"] == 1024
        assert as_dict["data_base64"] == "SGVsbG8="


class TestFileError:
    """Tests for FileError dataclass."""

    def test_file_error_creation(self):
        """Test creating a FileError."""
        error = FileError(
            filename="test.zip",
            error_type=FileErrorType.UNSUPPORTED_FORMAT,
            message="ZIP files not supported"
        )

        assert error.filename == "test.zip"
        assert error.error_type == FileErrorType.UNSUPPORTED_FORMAT
        assert error.message == "ZIP files not supported"

    def test_file_error_to_dict(self):
        """Test FileError serialization."""
        error = FileError(
            filename="test.zip",
            error_type=FileErrorType.UNSUPPORTED_FORMAT,
            message="ZIP files not supported"
        )

        as_dict = error.to_dict()
        assert as_dict["filename"] == "test.zip"
        assert as_dict["error_type"] == "unsupported_format"
        assert as_dict["message"] == "ZIP files not supported"


class TestFileProcessingResult:
    """Tests for FileProcessingResult dataclass."""

    def test_empty_result(self):
        """Test empty result properties."""
        result = FileProcessingResult()
        assert result.has_errors is False
        assert result.has_successful is False
        assert result.all_failed is False

    def test_successful_only(self):
        """Test result with only successful files."""
        result = FileProcessingResult(
            successful=[
                FileAttachment("a.jpg", "image/jpeg", 100, "abc")
            ]
        )
        assert result.has_errors is False
        assert result.has_successful is True
        assert result.all_failed is False

    def test_failed_only(self):
        """Test result with only failed files."""
        result = FileProcessingResult(
            failed=[
                FileError("a.zip", FileErrorType.UNSUPPORTED_FORMAT, "Not supported")
            ]
        )
        assert result.has_errors is True
        assert result.has_successful is False
        assert result.all_failed is True

    def test_partial_success(self):
        """Test result with both successful and failed files."""
        result = FileProcessingResult(
            successful=[
                FileAttachment("a.jpg", "image/jpeg", 100, "abc")
            ],
            failed=[
                FileError("b.zip", FileErrorType.UNSUPPORTED_FORMAT, "Not supported")
            ]
        )
        assert result.has_errors is True
        assert result.has_successful is True
        assert result.all_failed is False


class TestDownloadFileWithRetry:
    """Tests for file download with retry logic."""

    @pytest.mark.asyncio
    async def test_download_success_first_attempt(self):
        """Test successful download on first attempt."""
        mock_context = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"test content")
        mock_context.bot.get_file = AsyncMock(return_value=mock_file)

        result = await download_file_with_retry(
            mock_context, "test_file_id", max_retries=1, timeout=5.0
        )

        assert result == b"test content"
        mock_context.bot.get_file.assert_called_once_with("test_file_id")

    @pytest.mark.asyncio
    async def test_download_success_on_retry(self):
        """Test successful download on retry after first failure."""
        mock_context = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"test content")

        # First call fails, second succeeds
        mock_context.bot.get_file = AsyncMock(
            side_effect=[Exception("Network error"), mock_file]
        )

        result = await download_file_with_retry(
            mock_context, "test_file_id", max_retries=1, timeout=5.0, retry_delay=0.1
        )

        assert result == b"test content"
        assert mock_context.bot.get_file.call_count == 2

    @pytest.mark.asyncio
    async def test_download_all_retries_exhausted(self):
        """Test failure after all retries exhausted."""
        mock_context = MagicMock()
        mock_context.bot.get_file = AsyncMock(
            side_effect=Exception("Persistent error")
        )

        with pytest.raises(Exception) as exc_info:
            await download_file_with_retry(
                mock_context, "test_file_id", max_retries=1, timeout=5.0, retry_delay=0.1
            )

        assert "failed after" in str(exc_info.value).lower()
        assert mock_context.bot.get_file.call_count == 2


class TestProcessPhoto:
    """Tests for photo processing."""

    @pytest.mark.asyncio
    async def test_process_photo_success(self):
        """Test successful photo processing."""
        mock_photo = MagicMock()
        mock_photo.file_id = "photo_123"
        mock_photo.file_unique_id = "unique_123"
        mock_photo.file_size = 1024

        mock_context = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"jpeg content")
        mock_context.bot.get_file = AsyncMock(return_value=mock_file)

        attachment, error = await process_photo(mock_photo, mock_context)

        assert attachment is not None
        assert error is None
        assert attachment.mime_type == "image/jpeg"
        assert attachment.filename == "photo_unique_123.jpg"
        assert attachment.size_bytes == len(b"jpeg content")

    @pytest.mark.asyncio
    async def test_process_photo_too_large(self):
        """Test photo rejection when too large."""
        mock_photo = MagicMock()
        mock_photo.file_id = "photo_123"
        mock_photo.file_unique_id = "unique_123"
        mock_photo.file_size = 15 * 1024 * 1024  # 15MB

        mock_context = MagicMock()

        attachment, error = await process_photo(mock_photo, mock_context)

        assert attachment is None
        assert error is not None
        assert error.error_type == FileErrorType.SIZE_EXCEEDED


class TestProcessDocument:
    """Tests for document processing."""

    @pytest.mark.asyncio
    async def test_process_document_success(self):
        """Test successful document processing."""
        mock_doc = MagicMock()
        mock_doc.file_id = "doc_123"
        mock_doc.file_unique_id = "unique_doc_123"
        mock_doc.file_name = "report.pdf"
        mock_doc.mime_type = "application/pdf"
        mock_doc.file_size = 5000

        mock_context = MagicMock()
        mock_file = AsyncMock()
        mock_file.download_as_bytearray.return_value = bytearray(b"pdf content")
        mock_context.bot.get_file = AsyncMock(return_value=mock_file)

        attachment, error = await process_document(mock_doc, mock_context)

        assert attachment is not None
        assert error is None
        assert attachment.filename == "report.pdf"
        assert attachment.mime_type == "application/pdf"

    @pytest.mark.asyncio
    async def test_process_document_unsupported(self):
        """Test document rejection for unsupported type."""
        mock_doc = MagicMock()
        mock_doc.file_id = "doc_123"
        mock_doc.file_unique_id = "unique_doc_123"
        mock_doc.file_name = "archive.zip"
        mock_doc.mime_type = "application/zip"
        mock_doc.file_size = 1000

        mock_context = MagicMock()

        attachment, error = await process_document(mock_doc, mock_context)

        assert attachment is None
        assert error is not None
        assert error.error_type == FileErrorType.UNSUPPORTED_FORMAT


class TestHasProcessableFiles:
    """Tests for checking if message has processable files."""

    def test_has_photo(self):
        """Test message with photo."""
        mock_message = MagicMock()
        mock_message.photo = [MagicMock()]
        mock_message.document = None

        assert has_processable_files(mock_message) is True

    def test_has_document(self):
        """Test message with document."""
        mock_message = MagicMock()
        mock_message.photo = None
        mock_message.document = MagicMock()

        assert has_processable_files(mock_message) is True

    def test_no_files(self):
        """Test message without files."""
        mock_message = MagicMock()
        mock_message.photo = None
        mock_message.document = None

        assert has_processable_files(mock_message) is False


class TestAcknowledgmentFormatting:
    """Tests for acknowledgment message formatting."""

    def test_format_single_image(self):
        """Test acknowledgment for single image."""
        files = [
            FileAttachment("screenshot.png", "image/png", 1024, "abc")
        ]

        ack = format_file_acknowledgment(files)

        # Uses image icon and simple message (no filename per user feedback)
        assert "📸" in ack or "📷" in ack  # Image icon
        assert "File received" in ack
        assert "analyzing" in ack

    def test_format_single_document(self):
        """Test acknowledgment for single document."""
        files = [
            FileAttachment("report.pdf", "application/pdf", 5000, "abc")
        ]

        ack = format_file_acknowledgment(files)

        assert "📄" in ack  # Document icon
        assert "File received" in ack
        assert "analyzing" in ack

    def test_format_multiple_files(self):
        """Test acknowledgment for multiple files."""
        files = [
            FileAttachment("photo.jpg", "image/jpeg", 1024, "abc"),
            FileAttachment("doc.pdf", "application/pdf", 5000, "def"),
            FileAttachment("data.csv", "text/csv", 500, "ghi"),
        ]

        ack = format_file_acknowledgment(files)

        assert "📎" in ack
        assert "3 files" in ack
        assert "analyzing" in ack

    def test_format_empty_files(self):
        """Test acknowledgment for empty file list."""
        ack = format_file_acknowledgment([])
        assert ack == ""


class TestErrorFormatting:
    """Tests for error message formatting."""

    def test_format_unsupported_format_error(self):
        """Test error message for unsupported format."""
        error = FileError(
            filename="archive.zip",
            error_type=FileErrorType.UNSUPPORTED_FORMAT,
            message="Not supported"
        )

        msg = format_file_error(error)

        assert "archive.zip" in msg
        assert "JPEG" in msg or "PDF" in msg  # Lists supported formats

    def test_format_size_exceeded_error(self):
        """Test error message for size exceeded."""
        error = FileError(
            filename="huge.pdf",
            error_type=FileErrorType.SIZE_EXCEEDED,
            message="Too large"
        )

        msg = format_file_error(error)

        assert "huge.pdf" in msg or "too large" in msg.lower()

    def test_format_download_failed_error(self):
        """Test error message for download failure."""
        error = FileError(
            filename="doc.pdf",
            error_type=FileErrorType.DOWNLOAD_FAILED,
            message="Network error"
        )

        msg = format_file_error(error)

        assert "doc.pdf" in msg
        assert "try" in msg.lower()  # Suggests retry


class TestPartialSuccessFormatting:
    """Tests for partial success acknowledgment formatting."""

    def test_partial_success(self):
        """Test acknowledgment with some successes and failures."""
        result = FileProcessingResult(
            successful=[
                FileAttachment("photo.jpg", "image/jpeg", 1024, "abc")
            ],
            failed=[
                FileError("archive.zip", FileErrorType.UNSUPPORTED_FORMAT, "Not supported")
            ]
        )

        ack = format_partial_success_acknowledgment(result)

        assert "2 files" in ack
        assert "✅" in ack
        assert "❌" in ack
        assert "photo.jpg" in ack
        assert "archive.zip" in ack

    def test_all_success_uses_regular_format(self):
        """Test that all-success uses regular formatting."""
        result = FileProcessingResult(
            successful=[
                FileAttachment("photo.jpg", "image/jpeg", 1024, "abc")
            ]
        )

        ack = format_partial_success_acknowledgment(result)

        # Should use regular acknowledgment format (no filenames, just icon + "analyzing")
        assert "File received" in ack
        assert "analyzing" in ack
        assert "❌" not in ack

    def test_all_failed_shows_error(self):
        """Test that all-failed shows error message."""
        result = FileProcessingResult(
            failed=[
                FileError("archive.zip", FileErrorType.UNSUPPORTED_FORMAT, "Not supported")
            ]
        )

        ack = format_partial_success_acknowledgment(result)

        # Should show error message
        assert "archive.zip" in ack
