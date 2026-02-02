"""
Tests for the media_sender module.

Tests:
- MediaItem creation from different sources
- Media preparation logic
- Photo/video sending with mocked bot
- Media group sending
- Error handling and retries
"""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from telegram_bot.media_sender import (
    MediaItem,
    MediaType,
    MediaSourceType,
    MediaSendResult,
    decode_base64_media,
    prepare_media_input,
    send_photo,
    send_video,
    send_animation,
    send_voice,
    send_media_group,
    send_media,
    send_photo_from_url,
    send_video_from_url,
    send_photo_from_base64,
    send_video_from_base64,
    fetch_media_from_url,
    MEDIA_SIZE_LIMITS,
    MAX_MEDIA_GROUP_SIZE,
)


# =============================================================================
# MediaItem Tests
# =============================================================================

class TestMediaItem:
    """Tests for MediaItem class."""

    def test_from_url_photo(self):
        """Test creating MediaItem from URL for photo."""
        item = MediaItem.from_url(
            url="https://example.com/photo.jpg",
            media_type=MediaType.PHOTO,
            caption="Test caption"
        )
        assert item.media_type == MediaType.PHOTO
        assert item.source == "https://example.com/photo.jpg"
        assert item.source_type == MediaSourceType.URL
        assert item.caption == "Test caption"

    def test_from_url_video(self):
        """Test creating MediaItem from URL for video."""
        item = MediaItem.from_url(
            url="https://example.com/video.mp4",
            media_type=MediaType.VIDEO,
            caption="Video caption",
            duration=120
        )
        assert item.media_type == MediaType.VIDEO
        assert item.source == "https://example.com/video.mp4"
        assert item.source_type == MediaSourceType.URL
        assert item.caption == "Video caption"
        assert item.duration == 120

    def test_from_bytes(self):
        """Test creating MediaItem from bytes."""
        data = b"fake image data"
        item = MediaItem.from_bytes(
            data=data,
            media_type=MediaType.PHOTO,
            caption="Bytes caption",
            filename="test.jpg"
        )
        assert item.media_type == MediaType.PHOTO
        assert item.source == data
        assert item.source_type == MediaSourceType.BYTES
        assert item.filename == "test.jpg"

    def test_from_base64(self):
        """Test creating MediaItem from base64."""
        data = base64.b64encode(b"fake image data").decode()
        item = MediaItem.from_base64(
            data_base64=data,
            media_type=MediaType.PHOTO,
            caption="Base64 caption",
            filename="test.jpg"
        )
        assert item.media_type == MediaType.PHOTO
        assert item.source == data
        assert item.source_type == MediaSourceType.BASE64
        assert item.filename == "test.jpg"

    def test_from_file_id(self):
        """Test creating MediaItem from Telegram file_id."""
        file_id = "AgACAgIAAxkBAAIBZWN..."
        item = MediaItem.from_file_id(
            file_id=file_id,
            media_type=MediaType.PHOTO,
            caption="File ID caption"
        )
        assert item.media_type == MediaType.PHOTO
        assert item.source == file_id
        assert item.source_type == MediaSourceType.FILE_ID
        assert item.caption == "File ID caption"


# =============================================================================
# MediaSendResult Tests
# =============================================================================

class TestMediaSendResult:
    """Tests for MediaSendResult class."""

    def test_success_result(self):
        """Test successful result."""
        mock_message = MagicMock()
        mock_message.photo = [MagicMock(file_id="test_file_id")]

        result = MediaSendResult(
            success=True,
            message=mock_message,
            file_id="test_file_id"
        )

        assert result.success
        assert result.message == mock_message
        assert result.file_id == "test_file_id"
        assert result.error is None

    def test_failure_result(self):
        """Test failure result."""
        result = MediaSendResult(
            success=False,
            error="Failed to send media"
        )

        assert not result.success
        assert result.message is None
        assert result.error == "Failed to send media"

    def test_file_ids_property_single_photo(self):
        """Test file_ids property with single photo."""
        mock_message = MagicMock()
        mock_message.photo = [MagicMock(file_id="photo_file_id")]
        mock_message.video = None
        mock_message.animation = None

        result = MediaSendResult(success=True, message=mock_message)
        assert result.file_ids == ["photo_file_id"]

    def test_file_ids_property_single_video(self):
        """Test file_ids property with single video."""
        mock_message = MagicMock()
        mock_message.photo = None
        mock_message.video = MagicMock(file_id="video_file_id")
        mock_message.animation = None

        result = MediaSendResult(success=True, message=mock_message)
        assert result.file_ids == ["video_file_id"]

    def test_file_ids_property_media_group(self):
        """Test file_ids property with media group."""
        mock_messages = [
            MagicMock(photo=[MagicMock(file_id="photo1")], video=None),
            MagicMock(photo=[MagicMock(file_id="photo2")], video=None),
        ]

        result = MediaSendResult(success=True, messages=mock_messages)
        assert "photo1" in result.file_ids
        assert "photo2" in result.file_ids


# =============================================================================
# Helper Function Tests
# =============================================================================

class TestHelperFunctions:
    """Tests for helper functions."""

    def test_decode_base64_media_valid(self):
        """Test decoding valid base64 data."""
        original_data = b"test image data"
        encoded = base64.b64encode(original_data).decode()

        decoded = decode_base64_media(encoded)
        assert decoded == original_data

    def test_decode_base64_media_invalid(self):
        """Test decoding invalid base64 data."""
        with pytest.raises(ValueError, match="Failed to decode base64"):
            decode_base64_media("not valid base64!!!")

    @pytest.mark.asyncio
    async def test_prepare_media_input_file_id(self):
        """Test prepare_media_input with file_id (returns string directly)."""
        item = MediaItem.from_file_id("AgACAgIAAxkBAAIBZWN...", MediaType.PHOTO)
        result = await prepare_media_input(item)
        assert result == "AgACAgIAAxkBAAIBZWN..."

    @pytest.mark.asyncio
    async def test_prepare_media_input_bytes(self):
        """Test prepare_media_input with bytes."""
        data = b"test image data"
        item = MediaItem.from_bytes(data, MediaType.PHOTO, filename="test.jpg")

        result = await prepare_media_input(item)

        assert isinstance(result, BytesIO)
        assert result.read() == data
        assert result.name == "test.jpg"

    @pytest.mark.asyncio
    async def test_prepare_media_input_base64(self):
        """Test prepare_media_input with base64."""
        original_data = b"test image data"
        encoded = base64.b64encode(original_data).decode()
        item = MediaItem.from_base64(encoded, MediaType.PHOTO, filename="test.jpg")

        result = await prepare_media_input(item)

        assert isinstance(result, BytesIO)
        assert result.read() == original_data

    @pytest.mark.asyncio
    async def test_prepare_media_input_bytes_too_large(self):
        """Test prepare_media_input rejects files that are too large."""
        # Create data larger than photo limit (10MB)
        large_data = b"x" * (11 * 1024 * 1024)
        item = MediaItem.from_bytes(large_data, MediaType.PHOTO)

        with pytest.raises(ValueError, match="too large"):
            await prepare_media_input(item)


# =============================================================================
# Send Function Tests (with mocked bot)
# =============================================================================

class TestSendPhoto:
    """Tests for send_photo function."""

    @pytest.mark.asyncio
    async def test_send_photo_success(self, mock_telegram_context):
        """Test successful photo sending."""
        # Setup mock
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.photo = [MagicMock(file_id="test_file_id")]
        mock_telegram_context.bot.send_photo = AsyncMock(return_value=mock_message)

        # Create item and send
        item = MediaItem.from_file_id("existing_file_id", MediaType.PHOTO, "Test caption")

        result = await send_photo(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        assert result.message == mock_message
        assert result.file_id == "test_file_id"
        mock_telegram_context.bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_photo_with_caption(self, mock_telegram_context):
        """Test photo sending with caption."""
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.photo = [MagicMock(file_id="test_file_id")]
        mock_telegram_context.bot.send_photo = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("file_id", MediaType.PHOTO, "My <b>bold</b> caption")

        result = await send_photo(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        call_kwargs = mock_telegram_context.bot.send_photo.call_args.kwargs
        assert call_kwargs["caption"] == "My <b>bold</b> caption"

    @pytest.mark.asyncio
    async def test_send_photo_failure(self, mock_telegram_context):
        """Test photo sending failure."""
        from telegram.error import TelegramError
        mock_telegram_context.bot.send_photo = AsyncMock(
            side_effect=TelegramError("Network error")
        )

        item = MediaItem.from_file_id("file_id", MediaType.PHOTO)

        result = await send_photo(
            context=mock_telegram_context,
            chat_id=12345,
            item=item,
            max_retries=1
        )

        assert not result.success
        assert "Network error" in result.error


class TestSendVideo:
    """Tests for send_video function."""

    @pytest.mark.asyncio
    async def test_send_video_success(self, mock_telegram_context):
        """Test successful video sending."""
        mock_message = MagicMock()
        mock_message.message_id = 124
        mock_message.video = MagicMock(file_id="video_file_id")
        mock_telegram_context.bot.send_video = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("video_id", MediaType.VIDEO, duration=60)

        result = await send_video(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        assert result.file_id == "video_file_id"

    @pytest.mark.asyncio
    async def test_send_video_with_dimensions(self, mock_telegram_context):
        """Test video sending with dimensions."""
        mock_message = MagicMock()
        mock_message.message_id = 124
        mock_message.video = MagicMock(file_id="video_file_id")
        mock_telegram_context.bot.send_video = AsyncMock(return_value=mock_message)

        item = MediaItem(
            media_type=MediaType.VIDEO,
            source="video_id",
            source_type=MediaSourceType.FILE_ID,
            width=1920,
            height=1080,
            duration=120
        )

        result = await send_video(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        call_kwargs = mock_telegram_context.bot.send_video.call_args.kwargs
        assert call_kwargs["width"] == 1920
        assert call_kwargs["height"] == 1080
        assert call_kwargs["duration"] == 120


class TestSendMediaGroup:
    """Tests for send_media_group function."""

    @pytest.mark.asyncio
    async def test_send_media_group_success(self, mock_telegram_context):
        """Test successful media group sending."""
        mock_messages = [
            MagicMock(message_id=1, photo=[MagicMock(file_id="photo1")]),
            MagicMock(message_id=2, photo=[MagicMock(file_id="photo2")]),
        ]
        mock_telegram_context.bot.send_media_group = AsyncMock(return_value=mock_messages)

        items = [
            MediaItem.from_file_id("file1", MediaType.PHOTO, "Album caption"),
            MediaItem.from_file_id("file2", MediaType.PHOTO),
        ]

        result = await send_media_group(
            context=mock_telegram_context,
            chat_id=12345,
            items=items
        )

        assert result.success
        assert len(result.messages) == 2
        mock_telegram_context.bot.send_media_group.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_group_empty_items(self, mock_telegram_context):
        """Test media group with no items."""
        result = await send_media_group(
            context=mock_telegram_context,
            chat_id=12345,
            items=[]
        )

        assert not result.success
        assert "No media items" in result.error

    @pytest.mark.asyncio
    async def test_send_media_group_truncates_large_groups(self, mock_telegram_context):
        """Test that large media groups are truncated."""
        mock_messages = [MagicMock(message_id=i, photo=[MagicMock(file_id=f"photo{i}")])
                        for i in range(MAX_MEDIA_GROUP_SIZE)]
        mock_telegram_context.bot.send_media_group = AsyncMock(return_value=mock_messages)

        # Create more items than allowed
        items = [MediaItem.from_file_id(f"file{i}", MediaType.PHOTO)
                for i in range(15)]  # 15 items > MAX_MEDIA_GROUP_SIZE (10)

        result = await send_media_group(
            context=mock_telegram_context,
            chat_id=12345,
            items=items
        )

        # Should succeed with truncated items
        assert result.success
        # The call should only have MAX_MEDIA_GROUP_SIZE items
        call_args = mock_telegram_context.bot.send_media_group.call_args
        assert len(call_args.kwargs["media"]) == MAX_MEDIA_GROUP_SIZE

    @pytest.mark.asyncio
    async def test_send_media_group_rejects_non_photo_video(self, mock_telegram_context):
        """Test that media groups reject non-photo/video items."""
        items = [
            MediaItem.from_file_id("file1", MediaType.ANIMATION),
        ]

        result = await send_media_group(
            context=mock_telegram_context,
            chat_id=12345,
            items=items
        )

        assert not result.success
        assert "only support photos and videos" in result.error


class TestSendMedia:
    """Tests for send_media dispatcher function."""

    @pytest.mark.asyncio
    async def test_send_media_photo(self, mock_telegram_context):
        """Test send_media dispatches to send_photo."""
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.photo = [MagicMock(file_id="test_file_id")]
        mock_telegram_context.bot.send_photo = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("file_id", MediaType.PHOTO)

        result = await send_media(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        mock_telegram_context.bot.send_photo.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_video(self, mock_telegram_context):
        """Test send_media dispatches to send_video."""
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.video = MagicMock(file_id="test_file_id")
        mock_telegram_context.bot.send_video = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("file_id", MediaType.VIDEO)

        result = await send_media(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        mock_telegram_context.bot.send_video.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_media_animation(self, mock_telegram_context):
        """Test send_media dispatches to send_animation."""
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.animation = MagicMock(file_id="test_file_id")
        mock_telegram_context.bot.send_animation = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("file_id", MediaType.ANIMATION)

        result = await send_media(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        mock_telegram_context.bot.send_animation.assert_called_once()


# =============================================================================
# Convenience Function Tests
# =============================================================================

class TestConvenienceFunctions:
    """Tests for convenience functions."""

    @pytest.mark.asyncio
    async def test_send_photo_from_base64(self, mock_telegram_context):
        """Test send_photo_from_base64 convenience function."""
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.photo = [MagicMock(file_id="test_file_id")]
        mock_telegram_context.bot.send_photo = AsyncMock(return_value=mock_message)

        data = base64.b64encode(b"fake image data").decode()

        result = await send_photo_from_base64(
            context=mock_telegram_context,
            chat_id=12345,
            data_base64=data,
            caption="Test caption"
        )

        assert result.success

    @pytest.mark.asyncio
    async def test_send_video_from_base64(self, mock_telegram_context):
        """Test send_video_from_base64 convenience function."""
        mock_message = MagicMock()
        mock_message.message_id = 123
        mock_message.video = MagicMock(file_id="test_file_id")
        mock_telegram_context.bot.send_video = AsyncMock(return_value=mock_message)

        data = base64.b64encode(b"fake video data").decode()

        result = await send_video_from_base64(
            context=mock_telegram_context,
            chat_id=12345,
            data_base64=data,
            caption="Test caption",
            duration=60
        )

        assert result.success


# =============================================================================
# Size Limits Tests
# =============================================================================

class TestSendVoice:
    """Tests for send_voice function."""

    @pytest.mark.asyncio
    async def test_send_voice_success(self, mock_telegram_context):
        """Test successful voice sending."""
        mock_message = MagicMock()
        mock_message.message_id = 125
        mock_message.voice = MagicMock(file_id="voice_file_id")
        mock_telegram_context.bot.send_voice = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("voice_id", MediaType.VOICE)

        result = await send_voice(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        assert result.file_id == "voice_file_id"

    @pytest.mark.asyncio
    async def test_send_voice_with_caption_uses_parse_mode(self, mock_telegram_context):
        """Test voice sending passes parse_mode for captions."""
        from telegram.constants import ParseMode

        mock_message = MagicMock()
        mock_message.message_id = 125
        mock_message.voice = MagicMock(file_id="voice_file_id")
        mock_telegram_context.bot.send_voice = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("voice_id", MediaType.VOICE, caption="<b>Bold</b> caption")

        result = await send_voice(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        call_kwargs = mock_telegram_context.bot.send_voice.call_args.kwargs
        assert call_kwargs["parse_mode"] == ParseMode.HTML

    @pytest.mark.asyncio
    async def test_send_voice_no_caption_no_parse_mode(self, mock_telegram_context):
        """Test voice sending without caption does not set parse_mode."""
        mock_message = MagicMock()
        mock_message.message_id = 125
        mock_message.voice = MagicMock(file_id="voice_file_id")
        mock_telegram_context.bot.send_voice = AsyncMock(return_value=mock_message)

        item = MediaItem.from_file_id("voice_id", MediaType.VOICE)

        result = await send_voice(
            context=mock_telegram_context,
            chat_id=12345,
            item=item
        )

        assert result.success
        call_kwargs = mock_telegram_context.bot.send_voice.call_args.kwargs
        assert call_kwargs["parse_mode"] is None


# =============================================================================
# Fetch Media From URL Tests
# =============================================================================

class TestFetchMediaFromUrl:
    """Tests for fetch_media_from_url function."""

    @pytest.mark.asyncio
    async def test_invalid_url_raises(self):
        """Test that invalid URLs raise ValueError."""
        with pytest.raises(ValueError, match="Invalid URL"):
            await fetch_media_from_url("not-a-url")

    @pytest.mark.asyncio
    async def test_unsupported_scheme_raises(self):
        """Test that non-http(s) schemes raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported URL scheme"):
            await fetch_media_from_url("ftp://example.com/file.jpg")

    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        """Test successful URL fetch returns bytes."""
        test_content = b"fake image bytes"

        with patch("telegram_bot.media_sender.aiohttp.ClientSession") as MockSession:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.read = AsyncMock(return_value=test_content)
            mock_response.headers = {"Content-Type": "image/jpeg"}
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session.get = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            MockSession.return_value = mock_session

            result = await fetch_media_from_url("https://example.com/photo.jpg")
            assert result == test_content

    @pytest.mark.asyncio
    async def test_content_too_large_by_header(self):
        """Test that oversized Content-Length header raises ValueError."""
        with patch("telegram_bot.media_sender.aiohttp.ClientSession") as MockSession:
            mock_response = AsyncMock()
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {"Content-Length": str(100 * 1024 * 1024)}
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)

            mock_session = AsyncMock()
            mock_session.get = MagicMock(return_value=mock_response)
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)

            MockSession.return_value = mock_session

            with pytest.raises(ValueError, match="File too large"):
                await fetch_media_from_url(
                    "https://example.com/huge.jpg",
                    max_size=10 * 1024 * 1024
                )

    @pytest.mark.asyncio
    async def test_reuses_provided_session(self):
        """Test that a provided session is reused instead of creating a new one."""
        test_content = b"fake image bytes"

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.read = AsyncMock(return_value=test_content)
        mock_response.headers = {"Content-Type": "image/jpeg"}
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.closed = False
        mock_session.get = MagicMock(return_value=mock_response)

        result = await fetch_media_from_url(
            "https://example.com/photo.jpg",
            session=mock_session
        )
        assert result == test_content
        mock_session.get.assert_called_once()


# =============================================================================
# Reset Media Input Tests
# =============================================================================

class TestResetMediaInput:
    """Tests for _reset_media_input helper."""

    def test_resets_bytesio_position(self):
        """Test that BytesIO position is reset to 0."""
        from telegram_bot.media_sender import _reset_media_input

        buf = BytesIO(b"test data")
        buf.read()  # Move position to end
        assert buf.tell() > 0

        _reset_media_input(buf)
        assert buf.tell() == 0

    def test_noop_for_string(self):
        """Test that string input (file_id) is not modified."""
        from telegram_bot.media_sender import _reset_media_input

        # Should not raise
        _reset_media_input("AgACAgIAAxkBAAIBZWN...")


# =============================================================================
# Size Limits Tests
# =============================================================================

class TestSizeLimits:
    """Tests for media size limits."""

    def test_photo_size_limit(self):
        """Test photo size limit is 10MB."""
        assert MEDIA_SIZE_LIMITS[MediaType.PHOTO] == 10 * 1024 * 1024

    def test_video_size_limit(self):
        """Test video size limit is 50MB."""
        assert MEDIA_SIZE_LIMITS[MediaType.VIDEO] == 50 * 1024 * 1024

    def test_max_media_group_size(self):
        """Test max media group size is 10."""
        assert MAX_MEDIA_GROUP_SIZE == 10


# =============================================================================
# Resolve Redis Ref Tests
# =============================================================================

class TestResolveRedisRef:
    """Tests for resolve_redis_ref helper in message handler."""

    @pytest.mark.asyncio
    async def test_resolve_redis_ref_success(self):
        """Test successful fetch: GET returns data, DELETE is called."""
        from telegram_bot.handlers.message import resolve_redis_ref

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=b"iVBORw0KGgoAAAANSUhEUg==")
        mock_redis.delete = AsyncMock()

        result = await resolve_redis_ref(mock_redis, "media:conv:uuid1", "conv")

        assert result == "iVBORw0KGgoAAAANSUhEUg=="
        mock_redis.get.assert_called_once_with("media:conv:uuid1")
        mock_redis.delete.assert_called_once_with("media:conv:uuid1")

    @pytest.mark.asyncio
    async def test_resolve_redis_ref_returns_str(self):
        """Test that a string value from Redis is returned directly."""
        from telegram_bot.handlers.message import resolve_redis_ref

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="already_a_string")
        mock_redis.delete = AsyncMock()

        result = await resolve_redis_ref(mock_redis, "media:conv:uuid2", "conv")

        assert result == "already_a_string"

    @pytest.mark.asyncio
    async def test_resolve_redis_ref_missing(self):
        """Test that a missing key returns None."""
        from telegram_bot.handlers.message import resolve_redis_ref

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

        result = await resolve_redis_ref(mock_redis, "media:conv:gone", "conv")

        assert result is None
        mock_redis.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_resolve_redis_ref_error(self):
        """Test that a Redis exception returns None gracefully."""
        from telegram_bot.handlers.message import resolve_redis_ref

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(side_effect=Exception("Connection refused"))

        result = await resolve_redis_ref(mock_redis, "media:conv:err", "conv")

        assert result is None
