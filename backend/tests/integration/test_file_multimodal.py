"""
Integration tests for File Context Sharing (Epic 18).

Tests the end-to-end flow of file upload from chat request through to LLM providers.
"""

import base64
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


@pytest.fixture
def test_client():
    """Create a test client for the FastAPI app."""
    os.environ["SKIP_ENV_VALIDATION"] = "true"

    from api.main import app
    client = TestClient(app)
    yield client

    del os.environ["SKIP_ENV_VALIDATION"]


@pytest.fixture
def sample_image_base64():
    """Generate a small valid PNG image in base64."""
    # Minimal 1x1 transparent PNG
    png_bytes = bytes([
        0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,  # PNG signature
        0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,  # IHDR chunk
        0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,  # 1x1 pixels
        0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,  # RGBA
        0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,  # IDAT chunk
        0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,  # compressed data
        0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,  #
        0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,  # IEND chunk
        0x42, 0x60, 0x82
    ])
    return base64.b64encode(png_bytes).decode()


@pytest.fixture
def sample_text_base64():
    """Generate sample text file content in base64."""
    text = "This is a sample document for testing.\nIt has multiple lines."
    return base64.b64encode(text.encode()).decode()


class TestChatRequestWithFiles:
    """Test chat endpoint accepts files correctly."""

    def test_chat_request_accepts_files_array(self, test_client, sample_image_base64):
        """Chat endpoint should accept files array in request body."""
        with patch("api.routes.chat.StateManager") as mock_state_class:
            # Mock redis client
            mock_redis = MagicMock()
            mock_redis.setex = AsyncMock()
            mock_redis.get = AsyncMock(return_value=None)

            # Mock StateManager context manager
            mock_state = MagicMock()
            mock_state.__aenter__ = AsyncMock(return_value=mock_state)
            mock_state.__aexit__ = AsyncMock(return_value=None)
            mock_state.redis_client = mock_redis
            mock_state.get_profile_context = AsyncMock(return_value="")
            mock_state.get_memory_context = AsyncMock(return_value="")
            mock_state.load_conversation = AsyncMock(return_value=[])
            mock_state.append_message = AsyncMock()
            mock_state.add_message = AsyncMock()
            mock_state.store_files = AsyncMock()
            mock_state.get_session = AsyncMock(return_value={
                "message_count": 0,
                "conversation_id": "test-conv-123"
            })
            mock_state.update_session_activity = AsyncMock()
            mock_state_class.return_value = mock_state

            response = test_client.post(
                "/api/chat",
                json={
                    "user_id": "test_user_123",
                    "platform": "telegram",
                    "message": "What's in this image?",
                    "files": [
                        {
                            "filename": "test.png",
                            "mime_type": "image/png",
                            "size_bytes": 100,
                            "data_base64": sample_image_base64
                        }
                    ]
                }
            )

            assert response.status_code == 200
            data = response.json()
            assert "conversation_id" in data
            assert "stream_url" in data

    def test_chat_request_validates_file_mime_type(self, test_client):
        """Chat endpoint should reject unsupported MIME types."""
        response = test_client.post(
            "/api/chat",
            json={
                "user_id": "test_user_123",
                "platform": "telegram",
                "message": "Process this file",
                "files": [
                    {
                        "filename": "archive.zip",
                        "mime_type": "application/zip",
                        "size_bytes": 1000,
                        "data_base64": base64.b64encode(b"PK").decode()
                    }
                ]
            }
        )

        # Pydantic validates MIME type first, returns 422
        assert response.status_code == 422
        # Error is in Pydantic validation details
        error_detail = response.json()
        assert "error" in error_detail or "detail" in error_detail

    def test_chat_request_validates_file_size(self, test_client, sample_image_base64):
        """Chat endpoint should reject oversized files."""
        response = test_client.post(
            "/api/chat",
            json={
                "user_id": "test_user_123",
                "platform": "telegram",
                "message": "Process this file",
                "files": [
                    {
                        "filename": "huge.png",
                        "mime_type": "image/png",
                        "size_bytes": 50 * 1024 * 1024,  # 50MB (over 10MB limit)
                        "data_base64": sample_image_base64
                    }
                ]
            }
        )

        assert response.status_code == 400
        # Error message says "too large" and includes "MB"
        assert "large" in response.json()["detail"].lower()

    def test_chat_request_validates_max_files(self, test_client, sample_image_base64):
        """Chat endpoint should reject too many files."""
        files = [
            {
                "filename": f"image_{i}.png",
                "mime_type": "image/png",
                "size_bytes": 100,
                "data_base64": sample_image_base64
            }
            for i in range(15)  # More than MAX_FILES_PER_REQUEST (10)
        ]

        response = test_client.post(
            "/api/chat",
            json={
                "user_id": "test_user_123",
                "platform": "telegram",
                "message": "Process these files",
                "files": files
            }
        )

        assert response.status_code == 422  # Pydantic validation error


class TestFileAttachmentModel:
    """Test FileAttachment Pydantic model validation."""

    def test_file_attachment_valid(self, sample_image_base64):
        """Valid FileAttachment should be accepted."""
        from api.models.file_attachment import FileAttachment

        file = FileAttachment(
            filename="test.png",
            mime_type="image/png",
            size_bytes=100,
            data_base64=sample_image_base64
        )

        assert file.filename == "test.png"
        assert file.mime_type == "image/png"

    def test_file_attachment_requires_all_fields(self):
        """FileAttachment should require all fields."""
        from api.models.file_attachment import FileAttachment

        with pytest.raises(ValueError):
            FileAttachment(
                filename="test.png",
                mime_type="image/png"
                # Missing size_bytes and data_base64
            )


class TestSupportedMimeTypes:
    """Test MIME type constants and validation."""

    def test_image_mime_types_supported(self):
        """All common image types should be supported."""
        from api.models.file_attachment import SUPPORTED_MIME_TYPES

        assert "image/jpeg" in SUPPORTED_MIME_TYPES
        assert "image/png" in SUPPORTED_MIME_TYPES
        assert "image/gif" in SUPPORTED_MIME_TYPES
        assert "image/webp" in SUPPORTED_MIME_TYPES

    def test_document_mime_types_supported(self):
        """Document types should be supported."""
        from api.models.file_attachment import SUPPORTED_MIME_TYPES

        assert "application/pdf" in SUPPORTED_MIME_TYPES
        assert "text/plain" in SUPPORTED_MIME_TYPES

    def test_spreadsheet_mime_types_supported(self):
        """Spreadsheet types should be supported."""
        from api.models.file_attachment import SUPPORTED_MIME_TYPES

        assert "text/csv" in SUPPORTED_MIME_TYPES

    def test_validate_files_function(self, sample_image_base64):
        """validate_files should check MIME types and sizes."""
        from api.models.file_attachment import FileAttachment, validate_files

        valid_files = [
            FileAttachment(
                filename="photo.png",
                mime_type="image/png",
                size_bytes=1000,
                data_base64=sample_image_base64
            )
        ]

        # Should not raise for valid files
        validate_files(valid_files)

    def test_validate_files_rejects_unsupported_type(self, sample_image_base64):
        """FileAttachment should reject unsupported MIME types via Pydantic validator."""
        from api.models.file_attachment import FileAttachment
        from pydantic import ValidationError

        # Pydantic validates MIME type at model creation
        with pytest.raises(ValidationError) as exc_info:
            FileAttachment(
                filename="archive.zip",
                mime_type="application/zip",
                size_bytes=1000,
                data_base64=sample_image_base64
            )
        assert "unsupported" in str(exc_info.value).lower()


class TestFileSizeLimits:
    """Test file size limit constants."""

    def test_image_size_limit(self):
        """Image size limit should be 10MB."""
        from api.models.file_attachment import FILE_SIZE_LIMITS, FileCategory

        assert FILE_SIZE_LIMITS[FileCategory.IMAGE] == 10 * 1024 * 1024

    def test_document_size_limit(self):
        """Document size limit should be 20MB."""
        from api.models.file_attachment import FILE_SIZE_LIMITS, FileCategory

        assert FILE_SIZE_LIMITS[FileCategory.DOCUMENT] == 20 * 1024 * 1024

    def test_spreadsheet_size_limit(self):
        """Spreadsheet size limit should be 20MB."""
        from api.models.file_attachment import FILE_SIZE_LIMITS, FileCategory

        assert FILE_SIZE_LIMITS[FileCategory.SPREADSHEET] == 20 * 1024 * 1024


class TestGetFilesMetadata:
    """Test get_files_metadata utility function."""

    def test_get_files_metadata_returns_safe_info(self, sample_image_base64):
        """get_files_metadata should return aggregated metadata without base64 content."""
        from api.models.file_attachment import FileAttachment, get_files_metadata

        files = [
            FileAttachment(
                filename="photo.png",
                mime_type="image/png",
                size_bytes=1000,
                data_base64=sample_image_base64
            )
        ]

        metadata = get_files_metadata(files)

        # Check aggregated metadata format
        assert metadata["file_count"] == 1
        assert metadata["total_size_bytes"] == 1000
        assert "image/png" in metadata["mime_types"]
        assert "photo.png" in metadata["filenames"]
        assert "image" in metadata["categories"]
        # data_base64 should NOT be in metadata (sensitive)
        assert "data_base64" not in metadata


class TestGeminiMultimodalIntegration:
    """Test Gemini provider multimodal message building."""

    def test_gemini_builds_inline_data_for_images(self, sample_image_base64):
        """Gemini provider should build inline_data parts for images."""
        from api.models.file_attachment import FileAttachment

        with patch("api.providers.gemini_provider.get_config") as mock_config:
            mock_config.return_value = {
                "GOOGLE_API_KEY": "test-key",
                "GEMINI_MODEL": "gemini-3.1-pro-preview",
                "GEMINI_MAX_OUTPUT_TOKENS": "16384",
                "GEMINI_TEMPERATURE": "1.0",
                "GEMINI_CONTEXT_CACHE_TTL": "300",
                "GEMINI_SAFETY_SETTING": "BLOCK_NONE",
                "GEMINI_MAX_TOOL_ITERATIONS": "20"
            }

            with patch("api.providers.gemini_provider.genai"):
                from api.providers.gemini_provider import GeminiProvider
                provider = GeminiProvider()

                messages = [{"role": "user", "content": "What's in this image?"}]
                files = [
                    FileAttachment(
                        filename="test.png",
                        mime_type="image/png",
                        size_bytes=100,
                        data_base64=sample_image_base64
                    )
                ]

                system_instruction, gemini_messages = provider._convert_messages_to_gemini_format(
                    messages, files
                )

                # Check that file was attached as inline_data
                assert len(gemini_messages) == 1
                parts = gemini_messages[0]["parts"]
                assert len(parts) == 2  # text + image

                # First part: text
                assert "text" in parts[0]

                # Second part: inline_data
                assert "inline_data" in parts[1]
                assert parts[1]["inline_data"]["mime_type"] == "image/png"


class TestChatGPTMultimodalIntegration:
    """Test ChatGPT provider multimodal message building."""

    def test_chatgpt_builds_image_url_for_images(self, sample_image_base64):
        """ChatGPT provider should build image_url content for images."""
        from api.models.file_attachment import FileAttachment

        with patch("api.providers.chatgpt_provider.get_config") as mock_config:
            mock_config.return_value = {
                "OPENAI_API_KEY": "test-key",
                "LLM_REQUEST_TIMEOUT": "300.0",
                "LLM_STREAMING_TIMEOUT": "300.0"
            }

            from api.providers.chatgpt_provider import ChatGPTProvider
            provider = ChatGPTProvider()

            messages = [{"role": "user", "content": "What's in this image?"}]
            files = [
                FileAttachment(
                    filename="test.png",
                    mime_type="image/png",
                    size_bytes=100,
                    data_base64=sample_image_base64
                )
            ]

            result = provider._build_multimodal_messages(messages, files)

            assert len(result) == 1
            content = result[0]["content"]
            assert isinstance(content, list)
            assert len(content) == 2

            # First part: text
            assert content[0]["type"] == "text"

            # Second part: image_url
            assert content[1]["type"] == "image_url"
            assert "data:image/png;base64," in content[1]["image_url"]["url"]

    def test_chatgpt_extracts_text_from_csv(self):
        """ChatGPT provider should include CSV content as text."""
        csv_content = "name,value\nAlice,100\nBob,200"
        csv_base64 = base64.b64encode(csv_content.encode()).decode()

        from api.models.file_attachment import FileAttachment

        with patch("api.providers.chatgpt_provider.get_config") as mock_config:
            mock_config.return_value = {
                "OPENAI_API_KEY": "test-key",
                "LLM_REQUEST_TIMEOUT": "300.0",
                "LLM_STREAMING_TIMEOUT": "300.0"
            }

            from api.providers.chatgpt_provider import ChatGPTProvider
            provider = ChatGPTProvider()

            messages = [{"role": "user", "content": "Analyze this data"}]
            files = [
                FileAttachment(
                    filename="data.csv",
                    mime_type="text/csv",
                    size_bytes=len(csv_content),
                    data_base64=csv_base64
                )
            ]

            result = provider._build_multimodal_messages(messages, files)

            # CSV should be included as text content
            content = result[0]["content"]
            assert content[1]["type"] == "text"
            assert "CSV data from data.csv" in content[1]["text"]
            assert "Alice,100" in content[1]["text"]
