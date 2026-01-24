"""
Unit tests for ChatGPT Provider multimodal support (Story 18.3).

Tests text extraction fallback for documents when using ChatGPT instead of Gemini.
"""

import base64
import pytest
from unittest.mock import MagicMock, patch
from api.providers.chatgpt_provider import ChatGPTProvider


class MockFileAttachment:
    """Mock FileAttachment for testing."""

    def __init__(self, filename: str, mime_type: str, size_bytes: int, data_base64: str):
        self.filename = filename
        self.mime_type = mime_type
        self.size_bytes = size_bytes
        self.data_base64 = data_base64


@pytest.fixture
def provider():
    """Create ChatGPT provider with mocked config."""
    with patch("api.providers.chatgpt_provider.get_config") as mock_config:
        mock_config.return_value = {
            "CHATGPT_API_KEY": "test-api-key",
            "LLM_REQUEST_TIMEOUT": "300.0",
            "LLM_STREAMING_TIMEOUT": "300.0",
        }
        return ChatGPTProvider()


class TestBuildMultimodalMessages:
    """Tests for _build_multimodal_messages method."""

    def test_no_files_returns_original_messages(self, provider):
        """When no files, messages should pass through unchanged."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "Hello!"},
        ]

        result = provider._build_multimodal_messages(messages, files=None)

        assert result == messages

    def test_image_creates_image_url_content(self, provider):
        """Image files should use native image_url format."""
        messages = [{"role": "user", "content": "What's in this image?"}]
        image_data = base64.b64encode(b"fake image data").decode()
        files = [
            MockFileAttachment(
                filename="test.png",
                mime_type="image/png",
                size_bytes=100,
                data_base64=image_data,
            )
        ]

        result = provider._build_multimodal_messages(messages, files)

        assert len(result) == 1
        assert result[0]["role"] == "user"
        assert isinstance(result[0]["content"], list)
        assert len(result[0]["content"]) == 2

        # First part: text
        assert result[0]["content"][0]["type"] == "text"
        assert result[0]["content"][0]["text"] == "What's in this image?"

        # Second part: image_url
        assert result[0]["content"][1]["type"] == "image_url"
        assert "data:image/png;base64," in result[0]["content"][1]["image_url"]["url"]

    def test_text_file_direct_inclusion(self, provider):
        """Text files should be included directly."""
        messages = [{"role": "user", "content": "Read this file"}]
        text_content = "Hello, this is a test file."
        files = [
            MockFileAttachment(
                filename="test.txt",
                mime_type="text/plain",
                size_bytes=len(text_content),
                data_base64=base64.b64encode(text_content.encode()).decode(),
            )
        ]

        result = provider._build_multimodal_messages(messages, files)

        assert len(result[0]["content"]) == 2
        assert result[0]["content"][1]["type"] == "text"
        assert "[Content from test.txt]" in result[0]["content"][1]["text"]
        assert text_content in result[0]["content"][1]["text"]

    def test_csv_file_direct_inclusion(self, provider):
        """CSV files should be included directly."""
        messages = [{"role": "user", "content": "Analyze this data"}]
        csv_content = "name,age\nAlice,30\nBob,25"
        files = [
            MockFileAttachment(
                filename="data.csv",
                mime_type="text/csv",
                size_bytes=len(csv_content),
                data_base64=base64.b64encode(csv_content.encode()).decode(),
            )
        ]

        result = provider._build_multimodal_messages(messages, files)

        assert "[CSV data from data.csv]" in result[0]["content"][1]["text"]
        assert csv_content in result[0]["content"][1]["text"]

    def test_files_attached_only_to_last_user_message(self, provider):
        """Files should only be attached to the last user message (current message)."""
        messages = [
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "First message"},
            {"role": "assistant", "content": "Response"},
            {"role": "user", "content": "Second message"},
        ]
        image_data = base64.b64encode(b"fake image data").decode()
        files = [
            MockFileAttachment(
                filename="test.png",
                mime_type="image/png",
                size_bytes=100,
                data_base64=image_data,
            )
        ]

        result = provider._build_multimodal_messages(messages, files)

        # System message unchanged
        assert result[0]["content"] == "You are helpful."

        # First user message unchanged (no files - they go to last)
        assert result[1]["content"] == "First message"

        # Assistant message unchanged
        assert result[2]["content"] == "Response"

        # Last user message has content array with file
        assert isinstance(result[3]["content"], list)
        assert len(result[3]["content"]) == 2

    def test_multiple_files_in_single_message(self, provider):
        """Multiple files should all be included in first user message."""
        messages = [{"role": "user", "content": "Compare these"}]
        image_data = base64.b64encode(b"fake image").decode()
        text_data = base64.b64encode(b"sample text").decode()
        files = [
            MockFileAttachment("img.png", "image/png", 100, image_data),
            MockFileAttachment("doc.txt", "text/plain", 50, text_data),
        ]

        result = provider._build_multimodal_messages(messages, files)

        # Original text + 2 files = 3 content parts
        assert len(result[0]["content"]) == 3

    def test_unsupported_format_returns_error_message(self, provider):
        """Unsupported formats should return error text."""
        messages = [{"role": "user", "content": "Process this"}]
        files = [
            MockFileAttachment(
                filename="archive.zip",
                mime_type="application/zip",
                size_bytes=1000,
                data_base64=base64.b64encode(b"PK").decode(),
            )
        ]

        result = provider._build_multimodal_messages(messages, files)

        assert "Unable to process archive.zip" in result[0]["content"][1]["text"]


class TestPdfTextExtraction:
    """Tests for _extract_pdf_text method."""

    def test_extract_pdf_text_success(self, provider):
        """Should extract text from valid PDF."""
        # Create a minimal valid PDF
        from io import BytesIO

        try:
            from pypdf import PdfWriter

            writer = PdfWriter()
            page = writer.add_blank_page(width=72, height=72)
            # Note: Adding actual text to a blank page requires reportlab or similar

            buffer = BytesIO()
            writer.write(buffer)
            pdf_bytes = buffer.getvalue()

            file = MockFileAttachment(
                filename="test.pdf",
                mime_type="application/pdf",
                size_bytes=len(pdf_bytes),
                data_base64=base64.b64encode(pdf_bytes).decode(),
            )

            result = provider._extract_pdf_text(file)

            # Empty PDF returns message about no extractable text
            assert result is not None
            assert "no extractable text" in result.lower() or "page" in result.lower()

        except ImportError:
            pytest.skip("pypdf not installed")

    def test_extract_pdf_invalid_data(self, provider):
        """Should handle invalid PDF data gracefully."""
        file = MockFileAttachment(
            filename="corrupt.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            data_base64=base64.b64encode(b"not a pdf").decode(),
        )

        result = provider._extract_pdf_text(file)

        assert result is None


class TestDocxTextExtraction:
    """Tests for _extract_docx_text method."""

    def test_extract_docx_invalid_data(self, provider):
        """Should handle invalid DOCX data gracefully."""
        file = MockFileAttachment(
            filename="corrupt.docx",
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            size_bytes=10,
            data_base64=base64.b64encode(b"not a docx").decode(),
        )

        result = provider._extract_docx_text(file)

        assert result is None


class TestXlsxTextExtraction:
    """Tests for _extract_xlsx_text method."""

    def test_extract_xlsx_invalid_data(self, provider):
        """Should handle invalid XLSX data gracefully."""
        file = MockFileAttachment(
            filename="corrupt.xlsx",
            mime_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            size_bytes=10,
            data_base64=base64.b64encode(b"not an xlsx").decode(),
        )

        result = provider._extract_xlsx_text(file)

        assert result is None


class TestProcessFileForChatgpt:
    """Tests for _process_file_for_chatgpt method."""

    def test_jpeg_image(self, provider):
        """JPEG images should use image_url format."""
        image_data = base64.b64encode(b"fake jpeg").decode()
        file = MockFileAttachment("photo.jpg", "image/jpeg", 100, image_data)

        result = provider._process_file_for_chatgpt(file)

        assert result["type"] == "image_url"
        assert "data:image/jpeg;base64," in result["image_url"]["url"]

    def test_gif_image(self, provider):
        """GIF images should use image_url format."""
        image_data = base64.b64encode(b"GIF89a").decode()
        file = MockFileAttachment("animation.gif", "image/gif", 100, image_data)

        result = provider._process_file_for_chatgpt(file)

        assert result["type"] == "image_url"
        assert "data:image/gif;base64," in result["image_url"]["url"]

    def test_webp_image(self, provider):
        """WEBP images should use image_url format."""
        image_data = base64.b64encode(b"RIFF").decode()
        file = MockFileAttachment("image.webp", "image/webp", 100, image_data)

        result = provider._process_file_for_chatgpt(file)

        assert result["type"] == "image_url"
        assert "data:image/webp;base64," in result["image_url"]["url"]
