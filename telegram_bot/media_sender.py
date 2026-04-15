"""
Media Sender Module for Telegram Bot

This module handles sending photos, videos, and media groups to Telegram users.
Follows OpenClaw's pattern of supporting URLs, file paths, bytes, and file IDs.

Supports:
- Single photos with optional caption
- Single videos with optional caption
- Media groups (albums of photos/videos)
- Voice notes
- Animations (GIFs)
"""

import asyncio
import base64
from dataclasses import dataclass
from enum import Enum
from io import BytesIO
from typing import List, Optional, Union
from urllib.parse import urlparse

import aiohttp
from telegram import InputMediaPhoto, InputMediaVideo, Message
from telegram.constants import ParseMode
from telegram.error import BadRequest, RetryAfter, TelegramError
from telegram.ext import ContextTypes

from telegram_bot.logger import get_logger

logger = get_logger(__name__)


class MediaType(Enum):
    """Supported media types for sending."""
    PHOTO = "photo"
    VIDEO = "video"
    ANIMATION = "animation"  # GIFs
    VOICE = "voice"


class MediaSourceType(Enum):
    """Source type for media content."""
    URL = "url"
    FILE_PATH = "file_path"
    BYTES = "bytes"
    BASE64 = "base64"
    FILE_ID = "file_id"  # Telegram file_id for reuse


@dataclass
class MediaItem:
    """
    Represents a media item to be sent.

    Attributes:
        media_type: Type of media (photo, video, etc.)
        source: The media source (URL, path, bytes, base64, or file_id)
        source_type: Type of the source
        caption: Optional caption text (supports HTML/Markdown)
        filename: Optional filename for the media
        width: Optional width in pixels (for photos/videos)
        height: Optional height in pixels (for photos/videos)
        duration: Optional duration in seconds (for videos/voice)
    """
    media_type: MediaType
    source: Union[str, bytes]
    source_type: MediaSourceType
    caption: Optional[str] = None
    filename: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    duration: Optional[int] = None

    @classmethod
    def from_url(
        cls,
        url: str,
        media_type: MediaType = MediaType.PHOTO,
        caption: Optional[str] = None,
        **kwargs
    ) -> "MediaItem":
        """Create MediaItem from URL."""
        return cls(
            media_type=media_type,
            source=url,
            source_type=MediaSourceType.URL,
            caption=caption,
            **kwargs
        )

    @classmethod
    def from_bytes(
        cls,
        data: bytes,
        media_type: MediaType = MediaType.PHOTO,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs
    ) -> "MediaItem":
        """Create MediaItem from bytes."""
        return cls(
            media_type=media_type,
            source=data,
            source_type=MediaSourceType.BYTES,
            caption=caption,
            filename=filename or f"media.{media_type.value}",
            **kwargs
        )

    @classmethod
    def from_base64(
        cls,
        data_base64: str,
        media_type: MediaType = MediaType.PHOTO,
        caption: Optional[str] = None,
        filename: Optional[str] = None,
        **kwargs
    ) -> "MediaItem":
        """Create MediaItem from base64 encoded string."""
        return cls(
            media_type=media_type,
            source=data_base64,
            source_type=MediaSourceType.BASE64,
            caption=caption,
            filename=filename or f"media.{media_type.value}",
            **kwargs
        )

    @classmethod
    def from_file_id(
        cls,
        file_id: str,
        media_type: MediaType = MediaType.PHOTO,
        caption: Optional[str] = None,
        **kwargs
    ) -> "MediaItem":
        """Create MediaItem from Telegram file_id (for reusing previously uploaded media)."""
        return cls(
            media_type=media_type,
            source=file_id,
            source_type=MediaSourceType.FILE_ID,
            caption=caption,
            **kwargs
        )


@dataclass
class MediaSendResult:
    """Result of a media send operation."""
    success: bool
    message: Optional[Message] = None
    messages: Optional[List[Message]] = None  # For media groups
    error: Optional[str] = None
    file_id: Optional[str] = None  # Returned file_id for reuse

    @property
    def file_ids(self) -> List[str]:
        """Get all file_ids from sent messages (useful for media groups)."""
        ids = []
        if self.message:
            if self.message.photo:
                ids.append(self.message.photo[-1].file_id)
            elif self.message.video:
                ids.append(self.message.video.file_id)
            elif self.message.animation:
                ids.append(self.message.animation.file_id)
        if self.messages:
            for msg in self.messages:
                if msg.photo:
                    ids.append(msg.photo[-1].file_id)
                elif msg.video:
                    ids.append(msg.video.file_id)
        return ids


# Configuration
MEDIA_SIZE_LIMITS = {
    MediaType.PHOTO: 10 * 1024 * 1024,      # 10MB for photos
    MediaType.VIDEO: 50 * 1024 * 1024,      # 50MB for videos
    MediaType.ANIMATION: 50 * 1024 * 1024,  # 50MB for GIFs
    MediaType.VOICE: 50 * 1024 * 1024,      # 50MB for voice
}

MEDIA_DOWNLOAD_TIMEOUT = 30.0  # seconds
MAX_RETRIES = 3
RETRY_DELAY = 1.0  # seconds

# Maximum items in a media group
MAX_MEDIA_GROUP_SIZE = 10


async def fetch_media_from_url(
    url: str,
    timeout: float = MEDIA_DOWNLOAD_TIMEOUT,
    max_size: int = 50 * 1024 * 1024,
    session: Optional[aiohttp.ClientSession] = None
) -> bytes:
    """
    Fetch media content from URL.

    Args:
        url: URL to fetch media from
        timeout: Download timeout in seconds
        max_size: Maximum allowed file size in bytes
        session: Optional aiohttp session to reuse (avoids creating one per call)

    Returns:
        Media content as bytes

    Raises:
        ValueError: If URL is invalid or file too large
        Exception: If download fails
    """
    # Validate URL
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid URL: {url}")

    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported URL scheme: {parsed.scheme}")

    logger.info(
        "Fetching media from URL",
        extra={
            "url": url[:100],
            "timeout": timeout,
            "event": "media_fetch_start"
        }
    )

    async def _fetch(s: aiohttp.ClientSession) -> bytes:
        async with s.get(
            url,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            response.raise_for_status()

            # Check content length if available
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > max_size:
                raise ValueError(
                    f"File too large: {int(content_length)} bytes "
                    f"(max: {max_size} bytes)"
                )

            # Read content with size limit
            content = await response.read()

            if len(content) > max_size:
                raise ValueError(
                    f"File too large: {len(content)} bytes "
                    f"(max: {max_size} bytes)"
                )

            logger.info(
                "Media fetched successfully",
                extra={
                    "url": url[:100],
                    "size_bytes": len(content),
                    "content_type": response.headers.get("Content-Type"),
                    "event": "media_fetch_success"
                }
            )

            return content

    try:
        if session and not session.closed:
            return await _fetch(session)
        else:
            async with aiohttp.ClientSession() as new_session:
                return await _fetch(new_session)

    except aiohttp.ClientError as e:
        logger.error(
            "Media fetch failed",
            extra={
                "url": url[:100],
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "media_fetch_failed"
            }
        )
        raise Exception(f"Failed to fetch media from URL: {e}")


def decode_base64_media(data_base64: str) -> bytes:
    """
    Decode base64 encoded media.

    Args:
        data_base64: Base64 encoded string

    Returns:
        Decoded bytes

    Raises:
        ValueError: If decoding fails
    """
    try:
        return base64.b64decode(data_base64)
    except Exception as e:
        raise ValueError(f"Failed to decode base64 media: {e}")


async def prepare_media_input(
    item: MediaItem,
    max_size: Optional[int] = None
) -> Union[str, BytesIO]:
    """
    Prepare media input for Telegram API.

    Args:
        item: MediaItem to prepare
        max_size: Optional max size override

    Returns:
        Either a string (URL or file_id) or BytesIO for upload
    """
    size_limit = max_size or MEDIA_SIZE_LIMITS.get(item.media_type, 50 * 1024 * 1024)

    if item.source_type == MediaSourceType.URL:
        # Fetch from URL
        content = await fetch_media_from_url(item.source, max_size=size_limit)
        buffer = BytesIO(content)
        if item.filename:
            buffer.name = item.filename
        return buffer

    elif item.source_type == MediaSourceType.FILE_ID:
        # Return file_id directly - Telegram will handle it
        return item.source

    elif item.source_type == MediaSourceType.BYTES:
        if len(item.source) > size_limit:
            raise ValueError(
                f"Media too large: {len(item.source)} bytes "
                f"(max: {size_limit} bytes)"
            )
        buffer = BytesIO(item.source)
        if item.filename:
            buffer.name = item.filename
        return buffer

    elif item.source_type == MediaSourceType.BASE64:
        content = decode_base64_media(item.source)
        if len(content) > size_limit:
            raise ValueError(
                f"Media too large: {len(content)} bytes "
                f"(max: {size_limit} bytes)"
            )
        buffer = BytesIO(content)
        if item.filename:
            buffer.name = item.filename
        return buffer

    elif item.source_type == MediaSourceType.FILE_PATH:
        # Read from file path
        with open(item.source, "rb") as f:
            content = f.read()
        if len(content) > size_limit:
            raise ValueError(
                f"Media too large: {len(content)} bytes "
                f"(max: {size_limit} bytes)"
            )
        buffer = BytesIO(content)
        buffer.name = item.filename or item.source.split("/")[-1]
        return buffer

    raise ValueError(f"Unsupported source type: {item.source_type}")


def _reset_media_input(media_input: Union[str, BytesIO]) -> None:
    """Reset BytesIO read position for retry. No-op for strings (file_id)."""
    if isinstance(media_input, BytesIO):
        media_input.seek(0)


async def send_photo(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    item: MediaItem,
    reply_to_message_id: Optional[int] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    max_retries: int = MAX_RETRIES
) -> MediaSendResult:
    """
    Send a single photo to a chat.

    Args:
        context: Telegram bot context
        chat_id: Target chat ID
        item: MediaItem containing the photo
        reply_to_message_id: Optional message to reply to
        parse_mode: Parse mode for caption
        max_retries: Maximum retry attempts

    Returns:
        MediaSendResult with success status and message info
    """
    logger.info(
        "Sending photo",
        extra={
            "chat_id": chat_id,
            "source_type": item.source_type.value,
            "has_caption": bool(item.caption),
            "event": "send_photo_start"
        }
    )

    # Prepare media ONCE before retry loop (avoids re-downloading URLs)
    media_input = await prepare_media_input(item)
    last_error = None

    for attempt in range(max_retries):
        try:
            _reset_media_input(media_input)

            # Send the photo
            message = await context.bot.send_photo(
                chat_id=chat_id,
                photo=media_input,
                caption=item.caption,
                parse_mode=parse_mode if item.caption else None,
                reply_to_message_id=reply_to_message_id
            )

            file_id = message.photo[-1].file_id if message.photo else None

            logger.info(
                "Photo sent successfully",
                extra={
                    "chat_id": chat_id,
                    "message_id": message.message_id,
                    "file_id": file_id[:20] + "..." if file_id else None,
                    "event": "send_photo_success"
                }
            )

            return MediaSendResult(
                success=True,
                message=message,
                file_id=file_id
            )

        except RetryAfter as e:
            logger.warning(
                "Rate limited when sending photo",
                extra={
                    "chat_id": chat_id,
                    "retry_after": e.retry_after,
                    "attempt": attempt + 1,
                    "event": "send_photo_rate_limited"
                }
            )
            await asyncio.sleep(e.retry_after)
            last_error = str(e)

        except BadRequest as e:
            # Caption parsing error - retry without parse_mode
            if "can't parse" in str(e).lower():
                logger.warning(
                    "Caption parse error, retrying as plain text",
                    extra={
                        "chat_id": chat_id,
                        "error": str(e),
                        "event": "send_photo_caption_parse_error"
                    }
                )
                try:
                    _reset_media_input(media_input)
                    message = await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=media_input,
                        caption=item.caption,
                        reply_to_message_id=reply_to_message_id
                    )
                    file_id = message.photo[-1].file_id if message.photo else None
                    return MediaSendResult(
                        success=True,
                        message=message,
                        file_id=file_id
                    )
                except Exception as retry_e:
                    last_error = str(retry_e)
            else:
                last_error = str(e)
                logger.error(
                    "Bad request when sending photo",
                    extra={
                        "chat_id": chat_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "event": "send_photo_bad_request"
                    }
                )

        except TelegramError as e:
            last_error = str(e)
            logger.error(
                f"Telegram error when sending photo: {type(e).__name__}: {e}",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_photo_telegram_error"
                },
                exc_info=True,
            )

        except Exception as e:
            last_error = str(e)
            logger.error(
                "Error sending photo",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_photo_error"
                }
            )

        # Wait before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return MediaSendResult(
        success=False,
        error=f"Failed to send photo after {max_retries} attempts: {last_error}"
    )


async def send_video(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    item: MediaItem,
    reply_to_message_id: Optional[int] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    max_retries: int = MAX_RETRIES,
    supports_streaming: bool = True
) -> MediaSendResult:
    """
    Send a single video to a chat.

    Args:
        context: Telegram bot context
        chat_id: Target chat ID
        item: MediaItem containing the video
        reply_to_message_id: Optional message to reply to
        parse_mode: Parse mode for caption
        max_retries: Maximum retry attempts
        supports_streaming: Whether video supports streaming playback

    Returns:
        MediaSendResult with success status and message info
    """
    logger.info(
        "Sending video",
        extra={
            "chat_id": chat_id,
            "source_type": item.source_type.value,
            "has_caption": bool(item.caption),
            "duration": item.duration,
            "event": "send_video_start"
        }
    )

    # Prepare media ONCE before retry loop (avoids re-downloading URLs)
    media_input = await prepare_media_input(item)
    last_error = None

    for attempt in range(max_retries):
        try:
            _reset_media_input(media_input)

            # Send the video
            message = await context.bot.send_video(
                chat_id=chat_id,
                video=media_input,
                caption=item.caption,
                parse_mode=parse_mode if item.caption else None,
                reply_to_message_id=reply_to_message_id,
                width=item.width,
                height=item.height,
                duration=item.duration,
                supports_streaming=supports_streaming
            )

            file_id = message.video.file_id if message.video else None

            logger.info(
                "Video sent successfully",
                extra={
                    "chat_id": chat_id,
                    "message_id": message.message_id,
                    "file_id": file_id[:20] + "..." if file_id else None,
                    "event": "send_video_success"
                }
            )

            return MediaSendResult(
                success=True,
                message=message,
                file_id=file_id
            )

        except RetryAfter as e:
            logger.warning(
                "Rate limited when sending video",
                extra={
                    "chat_id": chat_id,
                    "retry_after": e.retry_after,
                    "attempt": attempt + 1,
                    "event": "send_video_rate_limited"
                }
            )
            await asyncio.sleep(e.retry_after)
            last_error = str(e)

        except BadRequest as e:
            # Caption parsing error - retry without parse_mode
            if "can't parse" in str(e).lower():
                logger.warning(
                    "Caption parse error, retrying as plain text",
                    extra={
                        "chat_id": chat_id,
                        "error": str(e),
                        "event": "send_video_caption_parse_error"
                    }
                )
                try:
                    _reset_media_input(media_input)
                    message = await context.bot.send_video(
                        chat_id=chat_id,
                        video=media_input,
                        caption=item.caption,
                        reply_to_message_id=reply_to_message_id,
                        width=item.width,
                        height=item.height,
                        duration=item.duration,
                        supports_streaming=supports_streaming
                    )
                    file_id = message.video.file_id if message.video else None
                    return MediaSendResult(
                        success=True,
                        message=message,
                        file_id=file_id
                    )
                except Exception as retry_e:
                    last_error = str(retry_e)
            else:
                last_error = str(e)
                logger.error(
                    "Bad request when sending video",
                    extra={
                        "chat_id": chat_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "event": "send_video_bad_request"
                    }
                )

        except TelegramError as e:
            last_error = str(e)
            logger.error(
                "Telegram error when sending video",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_video_telegram_error"
                }
            )

        except Exception as e:
            last_error = str(e)
            logger.error(
                "Error sending video",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_video_error"
                }
            )

        # Wait before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return MediaSendResult(
        success=False,
        error=f"Failed to send video after {max_retries} attempts: {last_error}"
    )


async def send_animation(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    item: MediaItem,
    reply_to_message_id: Optional[int] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    max_retries: int = MAX_RETRIES
) -> MediaSendResult:
    """
    Send an animation (GIF) to a chat.

    Args:
        context: Telegram bot context
        chat_id: Target chat ID
        item: MediaItem containing the animation
        reply_to_message_id: Optional message to reply to
        parse_mode: Parse mode for caption
        max_retries: Maximum retry attempts

    Returns:
        MediaSendResult with success status and message info
    """
    logger.info(
        "Sending animation",
        extra={
            "chat_id": chat_id,
            "source_type": item.source_type.value,
            "has_caption": bool(item.caption),
            "event": "send_animation_start"
        }
    )

    # Prepare media ONCE before retry loop (avoids re-downloading URLs)
    media_input = await prepare_media_input(item)
    last_error = None

    for attempt in range(max_retries):
        try:
            _reset_media_input(media_input)

            message = await context.bot.send_animation(
                chat_id=chat_id,
                animation=media_input,
                caption=item.caption,
                parse_mode=parse_mode if item.caption else None,
                reply_to_message_id=reply_to_message_id,
                width=item.width,
                height=item.height,
                duration=item.duration
            )

            file_id = message.animation.file_id if message.animation else None

            logger.info(
                "Animation sent successfully",
                extra={
                    "chat_id": chat_id,
                    "message_id": message.message_id,
                    "file_id": file_id[:20] + "..." if file_id else None,
                    "event": "send_animation_success"
                }
            )

            return MediaSendResult(
                success=True,
                message=message,
                file_id=file_id
            )

        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            last_error = str(e)

        except Exception as e:
            last_error = str(e)
            logger.error(
                "Error sending animation",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_animation_error"
                }
            )

        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return MediaSendResult(
        success=False,
        error=f"Failed to send animation after {max_retries} attempts: {last_error}"
    )


async def send_voice(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    item: MediaItem,
    reply_to_message_id: Optional[int] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    max_retries: int = MAX_RETRIES
) -> MediaSendResult:
    """
    Send a voice message to a chat.

    Args:
        context: Telegram bot context
        chat_id: Target chat ID
        item: MediaItem containing the voice message
        reply_to_message_id: Optional message to reply to
        parse_mode: Parse mode for caption
        max_retries: Maximum retry attempts

    Returns:
        MediaSendResult with success status and message info
    """
    logger.info(
        "Sending voice message",
        extra={
            "chat_id": chat_id,
            "source_type": item.source_type.value,
            "duration": item.duration,
            "event": "send_voice_start"
        }
    )

    # Prepare media ONCE before retry loop (avoids re-downloading URLs)
    media_input = await prepare_media_input(item)
    last_error = None

    for attempt in range(max_retries):
        try:
            _reset_media_input(media_input)

            message = await context.bot.send_voice(
                chat_id=chat_id,
                voice=media_input,
                caption=item.caption,
                parse_mode=parse_mode if item.caption else None,
                reply_to_message_id=reply_to_message_id,
                duration=item.duration
            )

            file_id = message.voice.file_id if message.voice else None

            logger.info(
                "Voice message sent successfully",
                extra={
                    "chat_id": chat_id,
                    "message_id": message.message_id,
                    "file_id": file_id[:20] + "..." if file_id else None,
                    "event": "send_voice_success"
                }
            )

            return MediaSendResult(
                success=True,
                message=message,
                file_id=file_id
            )

        except RetryAfter as e:
            await asyncio.sleep(e.retry_after)
            last_error = str(e)

        except Exception as e:
            last_error = str(e)
            logger.error(
                "Error sending voice",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_voice_error"
                }
            )

        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return MediaSendResult(
        success=False,
        error=f"Failed to send voice after {max_retries} attempts: {last_error}"
    )


async def send_media_group(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    items: List[MediaItem],
    reply_to_message_id: Optional[int] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    max_retries: int = MAX_RETRIES
) -> MediaSendResult:
    """
    Send a media group (album) of photos and/or videos.

    Args:
        context: Telegram bot context
        chat_id: Target chat ID
        items: List of MediaItems (photos and videos only)
        reply_to_message_id: Optional message to reply to
        parse_mode: Parse mode for captions
        max_retries: Maximum retry attempts

    Returns:
        MediaSendResult with success status and messages info

    Notes:
        - Maximum 10 items per media group
        - Only photos and videos are supported in media groups
        - Only the first item's caption will be shown (Telegram limitation)
    """
    if not items:
        return MediaSendResult(
            success=False,
            error="No media items provided"
        )

    if len(items) > MAX_MEDIA_GROUP_SIZE:
        logger.warning(
            "Media group too large, truncating",
            extra={
                "requested_count": len(items),
                "max_count": MAX_MEDIA_GROUP_SIZE,
                "event": "media_group_truncated"
            }
        )
        items = items[:MAX_MEDIA_GROUP_SIZE]

    # Validate media types
    for item in items:
        if item.media_type not in (MediaType.PHOTO, MediaType.VIDEO):
            return MediaSendResult(
                success=False,
                error=f"Media groups only support photos and videos, got: {item.media_type.value}"
            )

    logger.info(
        "Sending media group",
        extra={
            "chat_id": chat_id,
            "item_count": len(items),
            "types": [item.media_type.value for item in items],
            "event": "send_media_group_start"
        }
    )

    # Prepare all media ONCE before retry loop (avoids re-downloading URLs)
    prepared_inputs = []
    for item in items:
        media_input = await prepare_media_input(item)
        prepared_inputs.append(media_input)

    def _build_media_list(use_parse_mode: bool = True) -> list:
        """Build InputMedia list from prepared inputs, resetting BytesIO positions."""
        media_list = []
        for i, (item, media_input) in enumerate(zip(items, prepared_inputs)):
            _reset_media_input(media_input)

            # Only first item gets the caption
            caption = item.caption if i == 0 else None
            caption_parse_mode = (parse_mode if caption and use_parse_mode else None)

            if item.media_type == MediaType.PHOTO:
                media_list.append(InputMediaPhoto(
                    media=media_input,
                    caption=caption,
                    parse_mode=caption_parse_mode
                ))
            elif item.media_type == MediaType.VIDEO:
                media_list.append(InputMediaVideo(
                    media=media_input,
                    caption=caption,
                    parse_mode=caption_parse_mode,
                    width=item.width,
                    height=item.height,
                    duration=item.duration,
                    supports_streaming=True
                ))
        return media_list

    last_error = None

    for attempt in range(max_retries):
        try:
            media_list = _build_media_list(use_parse_mode=True)

            # Send the media group
            messages = await context.bot.send_media_group(
                chat_id=chat_id,
                media=media_list,
                reply_to_message_id=reply_to_message_id
            )

            logger.info(
                "Media group sent successfully",
                extra={
                    "chat_id": chat_id,
                    "message_count": len(messages),
                    "message_ids": [m.message_id for m in messages],
                    "event": "send_media_group_success"
                }
            )

            return MediaSendResult(
                success=True,
                messages=list(messages)
            )

        except RetryAfter as e:
            logger.warning(
                "Rate limited when sending media group",
                extra={
                    "chat_id": chat_id,
                    "retry_after": e.retry_after,
                    "attempt": attempt + 1,
                    "event": "send_media_group_rate_limited"
                }
            )
            await asyncio.sleep(e.retry_after)
            last_error = str(e)

        except BadRequest as e:
            # Caption parsing error - retry without parse_mode
            if "can't parse" in str(e).lower():
                logger.warning(
                    "Caption parse error in media group, retrying as plain text",
                    extra={
                        "chat_id": chat_id,
                        "error": str(e),
                        "event": "send_media_group_caption_parse_error"
                    }
                )
                try:
                    media_list = _build_media_list(use_parse_mode=False)
                    messages = await context.bot.send_media_group(
                        chat_id=chat_id,
                        media=media_list,
                        reply_to_message_id=reply_to_message_id
                    )
                    return MediaSendResult(
                        success=True,
                        messages=list(messages)
                    )
                except Exception as retry_e:
                    last_error = str(retry_e)
            else:
                last_error = str(e)
                logger.error(
                    "Bad request when sending media group",
                    extra={
                        "chat_id": chat_id,
                        "error": str(e),
                        "attempt": attempt + 1,
                        "event": "send_media_group_bad_request"
                    }
                )

        except TelegramError as e:
            last_error = str(e)
            logger.error(
                "Telegram error when sending media group",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_media_group_telegram_error"
                }
            )

        except Exception as e:
            last_error = str(e)
            logger.error(
                "Error sending media group",
                extra={
                    "chat_id": chat_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "attempt": attempt + 1,
                    "event": "send_media_group_error"
                }
            )

        # Wait before retry
        if attempt < max_retries - 1:
            await asyncio.sleep(RETRY_DELAY * (attempt + 1))

    return MediaSendResult(
        success=False,
        error=f"Failed to send media group after {max_retries} attempts: {last_error}"
    )


async def send_media(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    item: MediaItem,
    reply_to_message_id: Optional[int] = None,
    parse_mode: ParseMode = ParseMode.HTML,
    max_retries: int = MAX_RETRIES
) -> MediaSendResult:
    """
    Send any type of media to a chat (dispatcher function).

    Args:
        context: Telegram bot context
        chat_id: Target chat ID
        item: MediaItem to send
        reply_to_message_id: Optional message to reply to
        parse_mode: Parse mode for caption
        max_retries: Maximum retry attempts

    Returns:
        MediaSendResult with success status and message info
    """
    if item.media_type == MediaType.PHOTO:
        return await send_photo(
            context, chat_id, item, reply_to_message_id, parse_mode, max_retries
        )
    elif item.media_type == MediaType.VIDEO:
        return await send_video(
            context, chat_id, item, reply_to_message_id, parse_mode, max_retries
        )
    elif item.media_type == MediaType.ANIMATION:
        return await send_animation(
            context, chat_id, item, reply_to_message_id, parse_mode, max_retries
        )
    elif item.media_type == MediaType.VOICE:
        return await send_voice(
            context, chat_id, item, reply_to_message_id, parse_mode, max_retries
        )
    else:
        return MediaSendResult(
            success=False,
            error=f"Unsupported media type: {item.media_type.value}"
        )


# Convenience functions for common use cases

async def send_photo_from_url(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    url: str,
    caption: Optional[str] = None,
    reply_to_message_id: Optional[int] = None
) -> MediaSendResult:
    """Convenience function to send a photo from URL."""
    item = MediaItem.from_url(url, MediaType.PHOTO, caption)
    return await send_photo(context, chat_id, item, reply_to_message_id)


async def send_video_from_url(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    url: str,
    caption: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    duration: Optional[int] = None
) -> MediaSendResult:
    """Convenience function to send a video from URL."""
    item = MediaItem.from_url(url, MediaType.VIDEO, caption, duration=duration)
    return await send_video(context, chat_id, item, reply_to_message_id)


async def send_photo_from_base64(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    data_base64: str,
    caption: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    filename: str = "photo.jpg"
) -> MediaSendResult:
    """Convenience function to send a photo from base64 data."""
    item = MediaItem.from_base64(data_base64, MediaType.PHOTO, caption, filename)
    return await send_photo(context, chat_id, item, reply_to_message_id)


async def send_video_from_base64(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    data_base64: str,
    caption: Optional[str] = None,
    reply_to_message_id: Optional[int] = None,
    filename: str = "video.mp4",
    duration: Optional[int] = None
) -> MediaSendResult:
    """Convenience function to send a video from base64 data."""
    item = MediaItem.from_base64(data_base64, MediaType.VIDEO, caption, filename, duration=duration)
    return await send_video(context, chat_id, item, reply_to_message_id)
