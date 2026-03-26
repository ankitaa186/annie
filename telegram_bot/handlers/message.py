"""
Message Handler with Authorization

This module handles incoming Telegram messages with authorization checks.
"""

import asyncio
import html
import re
import time
from typing import Optional
from telegram import Update, Message as TelegramMessage
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.error import RetryAfter, TelegramError, BadRequest
from telegram.constants import ParseMode
import redis.asyncio as redis

from telegram_bot.auth import AuthenticationModule
from telegram_bot.backend_client import get_backend_client
from telegram_bot.config import get_config
from telegram_bot.file_handler import (
    FileProcessingResult,
    process_message_files,
    format_file_acknowledgment,
    format_partial_success_acknowledgment,
)
from telegram_bot.logger import get_logger
from telegram_bot.media_sender import (
    MediaItem,
    MediaType,
    MediaSourceType,
    send_media,
    send_media_group,
)

logger = get_logger(__name__)


# SSE frame type mappings (used by stream_response_to_telegram for media/media_group frames)
# Maps string types from backend SSE events to MediaType/MediaSourceType enums
MEDIA_TYPE_MAP = {
    "photo": MediaType.PHOTO,
    "video": MediaType.VIDEO,
    "animation": MediaType.ANIMATION,
    "voice": MediaType.VOICE,
}

# Source types that can arrive over SSE (JSON-serializable only).
# Note: "bytes" and "file_path" are NOT valid over SSE/JSON but included
# for forward-compatibility with local-only use cases.
SOURCE_TYPE_MAP = {
    "url": MediaSourceType.URL,
    "base64": MediaSourceType.BASE64,
    "file_id": MediaSourceType.FILE_ID,
    "file_path": MediaSourceType.FILE_PATH,
}

# Subset of media types valid in Telegram media groups (albums)
MEDIA_GROUP_TYPE_MAP = {
    "photo": MediaType.PHOTO,
    "video": MediaType.VIDEO,
}

async def resolve_redis_ref(redis_client, redis_key: str, conversation_id: str = "") -> Optional[str]:
    """
    Fetch a base64 blob that was offloaded to Redis by the backend.

    The key is deleted after a successful read (one-time use).

    Args:
        redis_client: An async Redis client.
        redis_key: The ``media:<conv_id>:<uuid>`` key.
        conversation_id: For logging context only.

    Returns:
        The base64 string, or ``None`` if the key is missing or an error occurs.
    """
    try:
        data = await redis_client.get(redis_key)
        if data is None:
            logger.warning(
                "Redis media key not found (expired or already consumed)",
                extra={
                    "conversation_id": conversation_id,
                    "redis_key": redis_key,
                    "event": "media_redis_key_missing"
                }
            )
            return None
        # Delete after successful read (one-time use)
        await redis_client.delete(redis_key)
        logger.info(
            "Resolved media from Redis",
            extra={
                "conversation_id": conversation_id,
                "redis_key": redis_key,
                "size": len(data) if isinstance(data, (str, bytes)) else 0,
                "event": "media_redis_fetch_success"
            }
        )
        return data if isinstance(data, str) else data.decode("utf-8")
    except Exception as exc:
        logger.error(
            "Failed to resolve media from Redis",
            extra={
                "conversation_id": conversation_id,
                "redis_key": redis_key,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "event": "media_redis_fetch_error"
            }
        )
        return None


# Conversation state storage (per user) - for tracking status messages and pending messages
conversation_states: dict[int, dict] = {}

# Media group buffering for multiple files sent at once
# Structure: {media_group_id: {"messages": [Message], "caption": str, "user_id": int, "chat_id": int, "task": asyncio.Task}}
media_group_buffers: dict[str, dict] = {}
MEDIA_GROUP_WAIT_SECONDS = 1.0  # Wait time for additional files in media group


def get_conversation_state(user_id: int) -> dict:
    """
    Get or create conversation state for user.

    Args:
        user_id: Telegram user ID

    Returns:
        Conversation state dictionary
    """
    if user_id not in conversation_states:
        conversation_states[user_id] = {
            "status_message_id": None,
            "is_processing": False,
            "pending_messages": [],
            "pending_indicator_message_id": None
        }
    return conversation_states[user_id]


def clear_conversation_state(user_id: int):
    """
    Clear conversation state after processing completes.

    Args:
        user_id: Telegram user ID
    """
    if user_id in conversation_states:
        conversation_states[user_id] = {
            "status_message_id": None,
            "is_processing": False,
            "pending_messages": [],
            "pending_indicator_message_id": None
        }


def markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown from LLM output to Telegram-safe HTML.

    Handles common markdown patterns:
    - ***bold italic*** → <b><i>bold italic</i></b>
    - **bold** or __bold__ → <b>bold</b>
    - *italic* or _italic_ → <i>italic</i>
    - `code` → <code>code</code>
    - ```code blocks``` → <pre>code</pre>
    - [link](url) → <a href="url">link</a>
    - ### headers → <b>header</b>
    - Numbered lists: 1. item → 1. item (plain)

    Args:
        text: Raw markdown text from LLM

    Returns:
        HTML-formatted text safe for Telegram
    """
    if not text:
        return text

    # First, escape HTML special characters to prevent injection
    # But we need to do this carefully to not break our own tags
    text = html.escape(text)

    # Code blocks (``` ... ```) - must be done before inline code
    # Handle multi-line code blocks
    text = re.sub(
        r'```(?:\w+)?\n?(.*?)```',
        r'<pre>\1</pre>',
        text,
        flags=re.DOTALL
    )

    # Inline code (`code`)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)

    # Bold+Italic combined: ***text*** → <b><i>text</i></b>
    # Must be done BEFORE separate bold/italic to avoid conflicts
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'___([^_]+)___', r'<b><i>\1</i></b>', text)

    # Bold: **text** or __text__
    text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)

    # Italic: *text* or _text_ (but not inside words like file_name)
    # Use word boundaries to avoid matching underscores in identifiers
    text = re.sub(r'(?<!\w)\*([^*]+)\*(?!\w)', r'<i>\1</i>', text)
    text = re.sub(r'(?<!\w)_([^_]+)_(?!\w)', r'<i>\1</i>', text)

    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Headers: ### Header → bold (Telegram doesn't support headers)
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Strikethrough: ~~text~~ → <s>text</s>
    text = re.sub(r'~~([^~]+)~~', r'<s>\1</s>', text)

    # Clean up escaped characters that markdown uses
    # (html.escape already handled &, <, > so we just need backslash escapes)
    text = text.replace(r'\*', '*')
    text = text.replace(r'\_', '_')
    text = text.replace(r'\`', '`')
    text = text.replace(r'\#', '#')
    text = text.replace(r'\.', '.')
    text = text.replace(r'\-', '-')
    text = text.replace(r'\!', '!')
    text = text.replace(r'\[', '[')
    text = text.replace(r'\]', ']')
    text = text.replace(r'\(', '(')
    text = text.replace(r'\)', ')')

    return text

# Global auth module (initialized once)
auth_module = None

# Global Redis client (initialized once)
redis_client = None

# Telegram message length limit (use 4000 for safety, actual limit is 4096)
MAX_MESSAGE_LENGTH = 4000

# Update frequency for streaming (milliseconds) - AC #2 specifies 100-500ms
# Using 200ms as a good balance between responsiveness and rate limiting
MIN_UPDATE_INTERVAL_MS = 500  # Update every 500ms (2x per second) to avoid Telegram rate limits


def get_redis_client() -> redis.Redis:
    """
    Get or initialize Redis client.

    Returns:
        Redis client instance
    """
    global redis_client

    if redis_client is None:
        config = get_config()
        redis_host = config.get("REDIS_HOST", "redis")
        redis_port = int(config.get("REDIS_PORT", "6379"))

        redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=0,
            decode_responses=True,
            socket_timeout=5,
            socket_connect_timeout=5
        )

        logger.info(
            "Redis client initialized",
            extra={
                "redis_host": redis_host,
                "redis_port": redis_port,
                "event": "redis_client_initialized"
            }
        )

    return redis_client


async def append_pending_message(redis_client: redis.Redis, user_id: str, message: str) -> None:
    """
    Append a message to the pending message slot for a user.

    Args:
        redis_client: Redis client instance
        user_id: User ID as string
        message: Message text to append
    """
    key = f"pending_message:{user_id}"

    try:
        # Get existing pending messages
        existing = await redis_client.get(key)

        if existing:
            # Append with newline separator
            combined = f"{existing}\n{message}"
        else:
            combined = message

        # Enforce max size (4000 chars) - keep most recent messages
        if len(combined) > 4000:
            combined = combined[-4000:]

        # Store with 5 minute TTL
        await redis_client.set(key, combined, ex=300)

        logger.debug(
            "Pending message appended",
            extra={
                "user_id": user_id,
                "message_length": len(message),
                "total_pending_length": len(combined),
                "event": "pending_message_appended"
            }
        )
    except Exception as e:
        logger.error(
            "Failed to append pending message",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "pending_append_failed"
            }
        )


async def count_pending_messages(redis_client: redis.Redis, user_id: str) -> int:
    """
    Count the number of pending messages for a user.

    Args:
        redis_client: Redis client instance
        user_id: User ID as string

    Returns:
        Number of pending messages (split by newline)
    """
    key = f"pending_message:{user_id}"

    try:
        pending = await redis_client.get(key)
        if not pending:
            return 0

        return len(pending.split("\n"))
    except Exception as e:
        logger.error(
            "Failed to count pending messages",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "pending_count_failed"
            }
        )
        return 0


async def get_and_clear_pending(redis_client: redis.Redis, user_id: str) -> Optional[str]:
    """
    Atomically get and clear pending messages for a user.

    Args:
        redis_client: Redis client instance
        user_id: User ID as string

    Returns:
        Pending message text (or None if no pending messages)
    """
    key = f"pending_message:{user_id}"

    try:
        # Use pipeline for atomic GET and DELETE
        pipe = redis_client.pipeline()
        pipe.get(key)
        pipe.delete(key)
        results = await pipe.execute()

        pending = results[0]  # The GET result

        if pending:
            logger.info(
                "Pending messages retrieved and cleared",
                extra={
                    "user_id": user_id,
                    "pending_length": len(pending),
                    "event": "pending_retrieved"
                }
            )

        return pending
    except Exception as e:
        logger.error(
            "Failed to get and clear pending messages",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "pending_get_clear_failed"
            }
        )
        return None


async def keep_typing_indicator(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    """
    Keep sending typing indicator every 4 seconds until cancelled.

    Args:
        context: Bot context
        chat_id: Chat ID to send typing indicator to
    """
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(4)  # Send every 4 seconds (indicator lasts ~5 seconds)
    except asyncio.CancelledError:
        # Task was cancelled, stop sending typing indicator
        logger.debug(
            "Typing indicator task cancelled",
            extra={"chat_id": chat_id, "event": "typing_indicator_cancelled"}
        )
        raise


async def stream_response_to_telegram(
    backend_client,
    conversation_id: str,
    user_id: int,
    message: TelegramMessage,
    typing_task: asyncio.Task,
    context: ContextTypes.DEFAULT_TYPE,
    state: dict
):
    """
    Stream LLM response to Telegram with status updates and message editing.

    Handles status frames from SSE stream by editing the status message.
    When first token arrives, transitions to streaming response in same message.

    Args:
        backend_client: Backend client instance
        conversation_id: Conversation ID from backend
        user_id: Telegram user ID
        message: Original Telegram message to reply to
        typing_task: Typing indicator task to cancel when first message is sent
        context: Bot context for edit_message_text()
        state: Conversation state dict with status_message_id

    Returns:
        Total length of response sent

    Raises:
        asyncio.TimeoutError: If first token not received within timeout
    """
    response_buffer = []
    sent_messages = []  # Track all messages (for multi-message responses)
    chunk_count = 0
    last_update_time = 0  # Track time of last message update (milliseconds)
    rate_limit_until = 0  # Timestamp (ms) when Telegram rate limit expires
    is_first_token = True

    # Get status_message_id from state (AC #1)
    status_message_id = state.get("status_message_id")
    chat_id = message.chat_id

    # Get the stream generator
    stream = backend_client.stream_response(conversation_id, user_id)

    # Enforce first-token timeout by wrapping first iteration with wait_for
    first_token_timeout = backend_client.first_token_timeout
    try:
        # Process stream frames (status and tokens)
        async for chunk_data in stream:
            chunk_type = chunk_data.get("type")
            current_time_ms = time.time() * 1000

            # Handle status frames (AC #2)
            # Only process status frames BEFORE first token arrives
            # After response streaming starts, ignore status updates to prevent message corruption
            if chunk_type == "status":
                if not is_first_token:
                    # Already streaming response - ignore late status updates
                    logger.debug(
                        "Ignoring status frame after response started",
                        extra={"user_id": user_id, "status": chunk_data.get("message", "")[:50]}
                    )
                    continue
                if not status_message_id:
                    continue
                status_text = chunk_data.get("message", "")
                time_since_last_update = current_time_ms - last_update_time
                is_rate_limited = current_time_ms < rate_limit_until

                # Apply debouncing (reuse MIN_UPDATE_INTERVAL_MS)
                if time_since_last_update >= MIN_UPDATE_INTERVAL_MS and not is_rate_limited:
                    try:
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_message_id,
                            text=status_text
                        )
                        last_update_time = current_time_ms

                        logger.debug(
                            "Status message updated",
                            extra={
                                "user_id": user_id,
                                "status": status_text,
                                "event": "status_updated"
                            }
                        )
                    except RetryAfter as retry_error:
                        rate_limit_until = current_time_ms + (retry_error.retry_after * 1000)
                        logger.debug(
                            "Status edit rate limited",
                            extra={
                                "user_id": user_id,
                                "retry_after": retry_error.retry_after,
                                "event": "status_rate_limited"
                            }
                        )
                    except Exception as e:
                        # Include error in message since extra fields may not display
                        logger.debug(
                            f"Status edit failed: {str(e)[:80]}",
                            extra={"user_id": user_id, "error": str(e), "error_type": type(e).__name__}
                        )
                continue

            # Handle token frames (AC #3: transition from status to response)
            if chunk_type == "token":
                content = chunk_data.get("content", "")
                if not content:
                    continue

                response_buffer.append(content)
                chunk_count += 1
                current_text = "".join(response_buffer)

                # First token - transition from status to response (AC #3)
                if is_first_token:
                    is_first_token = False

                    # Edit status message with first token (seamless transition)
                    try:
                        html_text = markdown_to_telegram_html(current_text)
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=status_message_id,
                            text=html_text,
                            parse_mode=ParseMode.HTML
                        )
                        sent_messages.append(status_message_id)  # Track for later edits
                        last_update_time = current_time_ms

                        # Keep typing indicator running during streaming
                        # It will show between rate-limited message edits
                        # Cancel happens when stream completes (done frame)

                        logger.info(
                            "Transitioned to response streaming",
                            extra={
                                "user_id": user_id,
                                "event": "status_to_response_transition"
                            }
                        )
                    except Exception as e:
                        logger.error(
                            "Failed to transition status to response",
                            extra={"user_id": user_id, "error": str(e)}
                        )
                        # Fallback: send new message if edit fails
                        html_text = markdown_to_telegram_html(current_text)
                        sent_messages.append(await message.reply_text(html_text, parse_mode=ParseMode.HTML))
                        last_update_time = current_time_ms
                    continue

                # Check if we need to split into a new message
                if len(current_text) > MAX_MESSAGE_LENGTH and len(sent_messages) > 0:
                    # Current message is getting too long, split it
                    # Find a good break point (end of sentence near the limit)
                    split_point = MAX_MESSAGE_LENGTH
                    for i in range(MAX_MESSAGE_LENGTH - 200, min(MAX_MESSAGE_LENGTH, len(current_text))):
                        if current_text[i] in '.!?\n':
                            split_point = i + 1
                            break

                    # Send current message part as final edit
                    current_part = current_text[:split_point]
                    try:
                        html_part = markdown_to_telegram_html(current_part)
                        # Edit using message_id from sent_messages
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=sent_messages[-1] if isinstance(sent_messages[-1], int) else sent_messages[-1].message_id,
                            text=html_part,
                            parse_mode=ParseMode.HTML
                        )
                    except Exception:
                        pass  # Ignore edit failures on split

                    # Start new message with remainder
                    remaining_text = current_text[split_point:]
                    html_remaining = markdown_to_telegram_html(remaining_text)
                    new_message = await message.reply_text(html_remaining, parse_mode=ParseMode.HTML)
                    sent_messages.append(new_message.message_id)

                    # Reset buffer to only contain the new message's text
                    response_buffer = [remaining_text]

                    # Reset update timer for new message
                    last_update_time = current_time_ms

                    logger.info(
                        "Split response into new message",
                        extra={
                            "user_id": user_id,
                            "message_number": len(sent_messages),
                            "split_at": split_point,
                            "event": "message_split"
                        }
                    )
                    continue

                # Time-based update logic for subsequent tokens
                time_since_last_update = current_time_ms - last_update_time
                should_update = time_since_last_update >= MIN_UPDATE_INTERVAL_MS

                # Check if we're still rate-limited by Telegram
                is_rate_limited = current_time_ms < rate_limit_until

                if is_rate_limited and should_update:
                    # Skip this edit - we're still rate-limited
                    logger.debug(
                        "Skipping edit (rate-limited)",
                        extra={
                            "user_id": user_id,
                            "wait_remaining_ms": int(rate_limit_until - current_time_ms),
                            "event": "edit_skipped_rate_limit"
                        }
                    )

                if should_update and not is_rate_limited:
                    # Edit last message (time-throttled) with HTML formatting
                    try:
                        html_text = markdown_to_telegram_html(current_text)
                        msg_id = sent_messages[-1] if isinstance(sent_messages[-1], int) else sent_messages[-1].message_id
                        await context.bot.edit_message_text(
                            chat_id=chat_id,
                            message_id=msg_id,
                            text=html_text,
                            parse_mode=ParseMode.HTML
                        )
                        last_update_time = current_time_ms

                        logger.debug(
                            "Message updated (time-throttled)",
                            extra={
                                "user_id": user_id,
                                "time_since_last_update_ms": int(time_since_last_update),
                                "event": "message_updated"
                            }
                        )
                    except RetryAfter as retry_error:
                        # Telegram rate limit - calculate when we can edit again
                        rate_limit_until = current_time_ms + (retry_error.retry_after * 1000)

                        logger.warning(
                            "Message edit rate limited by Telegram",
                            extra={
                                "user_id": user_id,
                                "retry_after_seconds": retry_error.retry_after,
                                "paused_until": rate_limit_until,
                                "event": "telegram_rate_limited"
                            }
                        )
                        # Don't update last_update_time - we'll retry after rate limit expires
                    except TelegramError as tg_error:
                        # Other Telegram API errors (e.g., message too old to edit)
                        logger.debug(
                            "Message edit failed (Telegram API error)",
                            extra={
                                "user_id": user_id,
                                "error": str(tg_error)[:100],
                                "error_type": type(tg_error).__name__,
                                "event": "telegram_edit_failed"
                            }
                        )
                    except Exception as edit_error:
                        # Unexpected errors
                        logger.warning(
                            "Message edit failed (unexpected error)",
                            extra={
                                "user_id": user_id,
                                "error": str(edit_error)[:100],
                                "error_type": type(edit_error).__name__,
                                "event": "message_edit_error"
                            }
                        )

            # Handle media frames (send photos/videos to user)
            elif chunk_type == "media":
                # Media send request from backend
                media_type_str = chunk_data.get("media_type", "photo")
                source_type_str = chunk_data.get("source_type", "url")
                source = chunk_data.get("source")
                caption = chunk_data.get("caption")
                filename = chunk_data.get("filename")
                duration = chunk_data.get("duration")
                width = chunk_data.get("width")
                height = chunk_data.get("height")

                # Resolve Redis-offloaded base64 media
                if source_type_str == "redis_ref" and source:
                    resolved = await resolve_redis_ref(
                        get_redis_client(), source, conversation_id
                    )
                    if resolved:
                        source = resolved
                        source_type_str = "base64"
                    else:
                        logger.warning(
                            "Skipping media frame: redis_ref could not be resolved",
                            extra={"user_id": user_id, "event": "media_redis_ref_unresolved"}
                        )
                        continue

                if not source:
                    logger.warning(
                        "Media frame received without source",
                        extra={"user_id": user_id, "event": "media_no_source"}
                    )
                    continue

                media_type = MEDIA_TYPE_MAP.get(media_type_str, MediaType.PHOTO)
                source_type = SOURCE_TYPE_MAP.get(source_type_str, MediaSourceType.URL)

                # Create MediaItem
                media_item = MediaItem(
                    media_type=media_type,
                    source=source,
                    source_type=source_type,
                    caption=caption,
                    filename=filename,
                    duration=duration,
                    width=width,
                    height=height
                )

                # Send the media
                try:
                    result = await send_media(
                        context=context,
                        chat_id=chat_id,
                        item=media_item,
                        reply_to_message_id=message.message_id
                    )

                    if result.success:
                        logger.info(
                            "Media sent successfully",
                            extra={
                                "user_id": user_id,
                                "media_type": media_type_str,
                                "file_id": result.file_id[:20] + "..." if result.file_id else None,
                                "event": "media_sent"
                            }
                        )
                    else:
                        logger.error(
                            "Media send failed",
                            extra={
                                "user_id": user_id,
                                "media_type": media_type_str,
                                "error": result.error,
                                "event": "media_send_failed"
                            }
                        )
                except Exception as media_error:
                    logger.error(
                        "Exception while sending media",
                        extra={
                            "user_id": user_id,
                            "media_type": media_type_str,
                            "error": str(media_error),
                            "error_type": type(media_error).__name__,
                            "event": "media_send_exception"
                        }
                    )
                continue

            # Handle media_group frames (send albums to user)
            elif chunk_type == "media_group":
                items_data = chunk_data.get("items", [])
                if not items_data:
                    logger.warning(
                        "Media group frame received without items",
                        extra={"user_id": user_id, "event": "media_group_no_items"}
                    )
                    continue

                # Create MediaItems
                media_items = []
                for item_data in items_data:
                    media_type_str = item_data.get("media_type", "photo")
                    source_type_str = item_data.get("source_type", "url")
                    item_source = item_data.get("source")

                    # Resolve Redis-offloaded base64 media per item
                    if source_type_str == "redis_ref" and item_source:
                        resolved = await resolve_redis_ref(
                            get_redis_client(), item_source, conversation_id
                        )
                        if resolved:
                            item_source = resolved
                            source_type_str = "base64"
                        else:
                            continue  # skip unresolvable item

                    # Only photos and videos are supported in media groups
                    if media_type_str not in MEDIA_GROUP_TYPE_MAP:
                        continue

                    media_items.append(MediaItem(
                        media_type=MEDIA_GROUP_TYPE_MAP.get(media_type_str, MediaType.PHOTO),
                        source=item_source,
                        source_type=SOURCE_TYPE_MAP.get(source_type_str, MediaSourceType.URL),
                        caption=item_data.get("caption"),
                        filename=item_data.get("filename"),
                        duration=item_data.get("duration"),
                        width=item_data.get("width"),
                        height=item_data.get("height")
                    ))

                if not media_items:
                    logger.warning(
                        "No valid items in media group",
                        extra={"user_id": user_id, "event": "media_group_no_valid_items"}
                    )
                    continue

                # Send the media group
                try:
                    result = await send_media_group(
                        context=context,
                        chat_id=chat_id,
                        items=media_items,
                        reply_to_message_id=message.message_id
                    )

                    if result.success:
                        logger.info(
                            "Media group sent successfully",
                            extra={
                                "user_id": user_id,
                                "item_count": len(media_items),
                                "message_count": len(result.messages) if result.messages else 0,
                                "event": "media_group_sent"
                            }
                        )
                    else:
                        logger.error(
                            "Media group send failed",
                            extra={
                                "user_id": user_id,
                                "item_count": len(media_items),
                                "error": result.error,
                                "event": "media_group_send_failed"
                            }
                        )
                except Exception as media_error:
                    logger.error(
                        "Exception while sending media group",
                        extra={
                            "user_id": user_id,
                            "item_count": len(media_items),
                            "error": str(media_error),
                            "error_type": type(media_error).__name__,
                            "event": "media_group_send_exception"
                        }
                    )
                continue

            # Handle done and error frames
            elif chunk_type in ["done", "error"]:
                # Cancel typing indicator now that stream is complete
                if typing_task and not typing_task.done():
                    typing_task.cancel()
                    try:
                        await typing_task
                    except asyncio.CancelledError:
                        pass

                # Handle error frames - display error message to user
                if chunk_type == "error":
                    error_message = chunk_data.get("message", "An error occurred while processing your request.")
                    error_code = chunk_data.get("code", "UNKNOWN")

                    logger.warning(
                        "Error frame received from backend",
                        extra={
                            "user_id": user_id,
                            "error_code": error_code,
                            "error_message": error_message,
                            "event": "stream_error"
                        }
                    )

                    # Add error message to response buffer so it gets displayed
                    # Prefix with emoji to indicate it's an error
                    response_buffer.append(f"⚠️ {error_message}")

                logger.info(
                    f"Stream {chunk_type} frame received",
                    extra={
                        "user_id": user_id,
                        "chunk_type": chunk_type,
                        "event": f"stream_{chunk_type}"
                    }
                )
                break

    except asyncio.TimeoutError:
        logger.error(
            f"First token timeout after {first_token_timeout}s",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "timeout_seconds": first_token_timeout,
                "event": "first_token_timeout"
            }
        )
        raise  # Re-raise to be handled by caller

    except StopAsyncIteration:
        # Stream completed without yielding any tokens (empty response)
        logger.warning(
            "Stream completed with no tokens (empty LLM response)",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "event": "empty_stream_response"
            }
        )

        # Cancel typing indicator
        if typing_task:
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

        # Return 0 - no response sent (graceful handling, no error to user)
        return 0

    except Exception as e:
        logger.error(
            "Stream processing failed",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "stream_processing_failed"
            },
            exc_info=True
        )
        raise

    # Final update with complete response (with rate limit retry)
    final_text = "".join(response_buffer)
    if len(sent_messages) > 0 and final_text:
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # If we're rate-limited, wait before retrying (with max 60s cap)
                current_time_ms = time.time() * 1000
                if current_time_ms < rate_limit_until:
                    wait_ms = min(rate_limit_until - current_time_ms, 60000)  # Cap at 60 seconds
                    wait_seconds = wait_ms / 1000
                    logger.info(
                        f"Waiting {wait_seconds:.1f}s for rate limit before final edit (attempt {attempt + 1})",
                        extra={
                            "user_id": user_id,
                            "wait_seconds": wait_seconds,
                            "attempt": attempt + 1,
                            "event": "final_edit_waiting"
                        }
                    )
                    await asyncio.sleep(wait_seconds)

                # Try final edit with 30s timeout to prevent indefinite hang
                logger.debug(
                    f"Attempting final edit (attempt {attempt + 1}, length {len(final_text)})",
                    extra={"user_id": user_id, "final_length": len(final_text)}
                )
                final_html = markdown_to_telegram_html(final_text)
                msg_id = sent_messages[-1] if isinstance(sent_messages[-1], int) else sent_messages[-1].message_id
                await asyncio.wait_for(
                    context.bot.edit_message_text(
                        chat_id=chat_id,
                        message_id=msg_id,
                        text=final_html,
                        parse_mode=ParseMode.HTML
                    ),
                    timeout=30.0
                )
                logger.info(
                    "Final message update successful",
                    extra={
                        "user_id": user_id,
                        "total_messages": len(sent_messages),
                        "final_length": len(final_text),
                        "attempt": attempt + 1,
                        "event": "final_edit_success"
                    }
                )
                break  # Success - exit retry loop

            except asyncio.TimeoutError:
                logger.error(
                    f"Final edit timed out after 30s (attempt {attempt + 1})",
                    extra={
                        "user_id": user_id,
                        "final_length": len(final_text),
                        "attempt": attempt + 1,
                        "event": "final_edit_timeout"
                    }
                )
                break  # Don't retry on timeout

            except RetryAfter as retry_error:
                # Update rate limit and retry
                rate_limit_until = time.time() * 1000 + (retry_error.retry_after * 1000)
                logger.warning(
                    f"Final edit rate-limited (wait {retry_error.retry_after}s), attempt {attempt + 1}/{max_retries}",
                    extra={
                        "user_id": user_id,
                        "retry_after_seconds": retry_error.retry_after,
                        "attempt": attempt + 1,
                        "event": "final_edit_rate_limited"
                    }
                )
                if attempt == max_retries - 1:
                    logger.error(
                        "Final edit failed after all retries (rate limit)",
                        extra={
                            "user_id": user_id,
                            "final_length": len(final_text),
                            "event": "final_edit_exhausted"
                        }
                    )

            except BadRequest as e:
                error_msg = str(e).lower()
                # "Message is not modified" is expected when final text matches last update
                if "not modified" in error_msg:
                    logger.debug(
                        "Final edit skipped (message unchanged)",
                        extra={
                            "user_id": user_id,
                            "final_length": len(final_text),
                            "event": "final_edit_unchanged"
                        }
                    )
                    break
                # HTML parsing error - retry with plain text
                elif "parse entities" in error_msg or "can't parse" in error_msg:
                    logger.warning(
                        f"HTML parsing failed, retrying with plain text: {str(e)[:80]}",
                        extra={
                            "user_id": user_id,
                            "error": str(e)[:100],
                            "event": "final_edit_html_fallback"
                        }
                    )
                    try:
                        # Fallback: send as plain text without HTML formatting
                        await asyncio.wait_for(
                            context.bot.edit_message_text(
                                chat_id=chat_id,
                                message_id=msg_id,
                                text=final_text  # Raw markdown, no parse_mode
                            ),
                            timeout=30.0
                        )
                        logger.info(
                            "Final edit succeeded with plain text fallback",
                            extra={"user_id": user_id, "final_length": len(final_text)}
                        )
                    except Exception as fallback_error:
                        logger.warning(
                            f"Plain text fallback also failed: {str(fallback_error)[:50]}",
                            extra={"user_id": user_id}
                        )
                    break
                else:
                    logger.warning(
                        f"Final edit failed (BadRequest): {str(e)[:100]}",
                        extra={
                            "user_id": user_id,
                            "error": str(e)[:100],
                            "attempt": attempt + 1,
                            "event": "final_edit_bad_request"
                        }
                    )
                    break  # Don't retry on other BadRequest errors

            except Exception as e:
                logger.warning(
                    "Final edit failed",
                    extra={
                        "user_id": user_id,
                        "error": str(e)[:100],
                        "error_type": type(e).__name__,
                        "attempt": attempt + 1,
                        "event": "final_edit_failed"
                    }
                )
                break  # Don't retry on non-rate-limit errors

    # Handle error-only response (no tokens received, just error frame)
    # In this case, edit the status message with the error
    elif len(sent_messages) == 0 and final_text and status_message_id:
        logger.info(
            "Displaying error message via status message edit",
            extra={
                "user_id": user_id,
                "error_text": final_text[:100],
                "event": "error_via_status_edit"
            }
        )
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=status_message_id,
                text=final_text
            )
        except Exception as e:
            logger.warning(
                "Failed to display error via status edit",
                extra={
                    "user_id": user_id,
                    "error": str(e)[:100],
                    "event": "error_status_edit_failed"
                }
            )

    # Calculate total response length
    total_length = len(final_text) if final_text else 0
    return total_length


def setup_message_handlers(application):
    """
    Setup message handlers with authorization.

    Args:
        application: Telegram Application instance
    """
    global auth_module

    # Initialize authentication module
    config = get_config()
    auth_module = AuthenticationModule(config["AUTHORIZED_USER_IDS"])

    logger.info(
        "Message handlers initialized",
        extra={
            "authorized_users_count": auth_module.get_authorized_count(),
            "event": "handlers_setup"
        }
    )

    # Register text message handler
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    logger.info(
        "Text message handler registered",
        extra={"event": "handler_registered", "handler_type": "text"}
    )

    # Register voice message handler
    application.add_handler(
        MessageHandler(filters.VOICE, handle_voice_message)
    )

    logger.info(
        "Voice message handler registered",
        extra={"event": "handler_registered", "handler_type": "voice"}
    )

    # Register photo message handler (for images with or without captions)
    application.add_handler(
        MessageHandler(filters.PHOTO, handle_file_message)
    )

    logger.info(
        "Photo message handler registered",
        extra={"event": "handler_registered", "handler_type": "photo"}
    )

    # Register document message handler (for PDFs, DOCX, XLSX, etc.)
    application.add_handler(
        MessageHandler(filters.Document.ALL, handle_file_message)
    )

    logger.info(
        "Document message handler registered",
        extra={"event": "handler_registered", "handler_type": "document"}
    )


async def handle_pending_messages(
    user_id: int,
    chat_id: int,
    pending_text: str,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Process pending messages recursively after a request completes.

    Args:
        user_id: Telegram user ID
        chat_id: Chat ID
        pending_text: Pending message text (possibly multi-line)
        context: Bot context
    """
    redis = get_redis_client()
    user_id_str = str(user_id)

    # Set processing flag for pending message handling
    processing_key = f"processing:{user_id_str}"

    try:
        # Try to set processing flag (should succeed since previous processing just completed)
        flag_set = await redis.set(processing_key, "1", ex=180, nx=True)

        if not flag_set:
            # Unlikely case: another message arrived and started processing
            # Append this pending to the new pending slot
            logger.warning(
                "Processing flag already set while handling pending - re-queueing",
                extra={
                    "user_id": user_id,
                    "event": "pending_requeued"
                }
            )
            await append_pending_message(redis, user_id_str, pending_text)
            return

        # Get or create conversation state for pending message
        state = get_conversation_state(user_id)

        # Send status message
        status_msg = await context.bot.send_message(
            chat_id=chat_id,
            text="🔄 Annie is thinking..."
        )

        # Store status message ID in state
        state["status_message_id"] = status_msg.message_id

        logger.info(
            "Processing pending messages",
            extra={
                "user_id": user_id,
                "pending_length": len(pending_text),
                "event": "pending_processing_started"
            }
        )

        # Get backend client
        backend_client = get_backend_client()

        # Send pending message to backend
        response = await backend_client.send_message(
            user_id=user_id,
            message=pending_text,
            message_type="text"
        )

        conversation_id = response.get("conversation_id")

        # Create a dummy typing task (already showing status message)
        typing_task = asyncio.create_task(asyncio.sleep(0))

        # Stream response (reuse existing streaming function)
        try:
            # Create a mock message object for stream_response_to_telegram
            class MockMessage:
                def __init__(self, msg_id, c_id):
                    self.message_id = msg_id
                    self.chat_id = c_id

                async def reply_text(self, text, **kwargs):
                    # Send new message (shouldn't happen with status message approach)
                    return await context.bot.send_message(
                        chat_id=self.chat_id,
                        text=text,
                        **kwargs
                    )

            mock_message = MockMessage(status_msg.message_id, chat_id)

            response_length = await stream_response_to_telegram(
                backend_client,
                conversation_id,
                user_id,
                mock_message,
                typing_task,
                context,
                state
            )

            logger.info(
                "Pending message processing complete",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "response_length": response_length,
                    "event": "pending_processed"
                }
            )

        except asyncio.TimeoutError:
            logger.error(
                "First token timeout on pending message",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "event": "pending_first_token_timeout"
                }
            )

            await status_msg.edit_text(
                "Sorry, the response is taking longer than expected. "
                "Please try again or rephrase your question."
            )

    except Exception as e:
        logger.error(
            "Failed to process pending messages",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "pending_processing_failed"
            },
            exc_info=True
        )

        # Send error message
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text="Sorry, I had trouble processing your follow-up message. Please try again."
            )
        except Exception:
            pass

    finally:
        # Clear processing flag
        try:
            await redis.delete(processing_key)
        except Exception:
            pass

        # Check for MORE pending messages (recursive handling)
        try:
            more_pending = await get_and_clear_pending(redis, user_id_str)
            if more_pending:
                logger.info(
                    "More pending messages detected - recursive handling",
                    extra={
                        "user_id": user_id,
                        "event": "pending_recursive"
                    }
                )
                # Recursively process
                await handle_pending_messages(user_id, chat_id, more_pending, context)
        except Exception as e:
            logger.error(
                "Failed to check for more pending messages",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "event": "pending_recursive_check_failed"
                }
            )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming text messages with authorization.

    Args:
        update: Telegram update object
        context: Bot context
    """
    global auth_module

    # Extract message data
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    message_text = message.text
    message_id = message.message_id
    timestamp = message.date
    username = message.from_user.username

    # Log message receipt (without content for privacy)
    logger.info(
        "Message received",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "message_length": len(message_text),
            "timestamp": timestamp.isoformat(),
            "username": username,
            "event": "message_received"
        }
    )

    # Authorization check (fail-fast pattern)
    if not auth_module.is_authorized(user_id):
        logger.warning(
            f"UNAUTHORIZED ACCESS ATTEMPT - User ID: {user_id}, Username: @{username or 'unknown'}",
            extra={
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "message_id": message_id,
                "event": "message_blocked"
            }
        )

        # Send rejection message
        await message.reply_text(auth_module.get_rejection_message())

        logger.info(
            "Rejection message sent to unauthorized user",
            extra={
                "user_id": user_id,
                "event": "rejection_sent"
            }
        )
        return

    # User is authorized - proceed with processing
    logger.info(
        "Message authorized - processing",
        extra={
            "user_id": user_id,
            "message_id": message_id,
            "authorized": True,
            "event": "message_authorized"
        }
    )

    # Check if already processing another message
    redis = get_redis_client()
    user_id_str = str(user_id)
    processing_key = f"processing:{user_id_str}"

    try:
        is_processing = await redis.get(processing_key)

        if is_processing:
            # Already processing - add to pending message slot
            logger.info(
                "User has active request - adding to pending",
                extra={
                    "user_id": user_id,
                    "message_id": message_id,
                    "event": "message_queued_pending"
                }
            )

            # Append to pending messages
            await append_pending_message(redis, user_id_str, message_text)

            # Count pending messages to show appropriate status
            count = await count_pending_messages(redis, user_id_str)

            if count == 1:
                # First pending message
                await message.reply_text("📝 Got it - will handle after current request...")
            else:
                # Multiple pending messages
                await message.reply_text(f"📝 Added to pending ({count} follow-up messages)...")

            logger.info(
                "Pending status message sent",
                extra={
                    "user_id": user_id,
                    "pending_count": count,
                    "event": "pending_status_sent"
                }
            )
            return

    except Exception as e:
        # Redis error - log but continue processing (graceful degradation)
        logger.error(
            "Failed to check processing flag - proceeding with message",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "processing_check_failed"
            }
        )

    # Set processing flag (atomic with NX flag)
    try:
        flag_set = await redis.set(processing_key, "1", ex=180, nx=True)

        if not flag_set:
            # Race condition: flag was set between check and set
            # Treat as pending
            logger.warning(
                "Processing flag race condition - adding to pending",
                extra={
                    "user_id": user_id,
                    "event": "processing_flag_race"
                }
            )
            await append_pending_message(redis, user_id_str, message_text)
            await message.reply_text("📝 Got it - will handle after current request...")
            return

        logger.debug(
            "Processing flag set",
            extra={
                "user_id": user_id,
                "ttl_seconds": 180,
                "event": "processing_flag_set"
            }
        )
    except Exception as e:
        # Redis error - log but continue (graceful degradation)
        logger.error(
            "Failed to set processing flag - continuing anyway",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "processing_flag_set_failed"
            }
        )

    # Get or create conversation state
    state = get_conversation_state(user_id)

    # Send immediate status message (AC #1: <100ms target)
    status_msg = await message.reply_text("🔄 Annie is thinking...")
    state["status_message_id"] = status_msg.message_id

    logger.info(
        "Status message sent",
        extra={
            "user_id": user_id,
            "status_message_id": state["status_message_id"],
            "event": "status_message_sent"
        }
    )

    # Start typing indicator task (optional - status message provides feedback)
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    logger.debug(
        "Typing indicator task started",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "event": "typing_indicator_started"
        }
    )

    # Forward message to backend and handle streaming response
    try:
        # Get backend client
        backend_client = get_backend_client()

        # Send message to backend
        response = await backend_client.send_message(
            user_id=user_id,
            message=message_text,
            message_type="text"
        )

        conversation_id = response.get("conversation_id")

        logger.info(
            "Message forwarded to backend successfully",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "event": "backend_forward_success"
            }
        )

        # Stream response back to user (with first-token timeout enforcement)
        try:
            response_length = await stream_response_to_telegram(
                backend_client,
                conversation_id,
                user_id,
                message,
                typing_task,
                context,
                state
            )
        except asyncio.TimeoutError:
            # First token timeout - cancel typing and inform user
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

            logger.error(
                "First token timeout exceeded",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "event": "first_token_timeout"
                }
            )

            await message.reply_text(
                "Sorry, the response is taking longer than expected. "
                "Please try again or rephrase your question."
            )
            return

        logger.info(
            "Message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "response_length": response_length,
                "event": "message_processed"
            }
        )

        # Clear processing flag and check for pending messages
        try:
            await redis.delete(processing_key)
            logger.debug(
                "Processing flag cleared",
                extra={
                    "user_id": user_id,
                    "event": "processing_flag_cleared"
                }
            )
        except Exception as e:
            logger.error(
                "Failed to clear processing flag",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "event": "processing_flag_clear_failed"
                }
            )

        # Check for pending messages and process them
        try:
            pending = await get_and_clear_pending(redis, user_id_str)
            if pending:
                logger.info(
                    "Pending messages detected - starting auto-pickup",
                    extra={
                        "user_id": user_id,
                        "pending_length": len(pending),
                        "event": "pending_auto_pickup"
                    }
                )
                # Process pending messages recursively
                await handle_pending_messages(user_id, chat_id, pending, context)
        except Exception as e:
            logger.error(
                "Failed to check/process pending messages",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "event": "pending_check_failed"
                }
            )

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        # Clear processing flag on error
        try:
            await redis.delete(processing_key)
            logger.debug(
                "Processing flag cleared (error path)",
                extra={
                    "user_id": user_id,
                    "event": "processing_flag_cleared_error"
                }
            )
        except Exception:
            pass  # Ignore errors during cleanup

        # Backend error - send user-friendly error message
        logger.error(
            "Failed to process message via backend",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "message_processing_failed"
            },
            exc_info=True
        )

        # Send error message to user
        await message.reply_text(
            "Sorry, I'm having trouble processing your message right now. "
            "Please try again in a moment."
        )

        logger.info(
            "Error message sent to user",
            extra={
                "user_id": user_id,
                "event": "error_message_sent"
            }
        )

        # Still check for pending messages even after error
        try:
            pending = await get_and_clear_pending(redis, user_id_str)
            if pending:
                logger.info(
                    "Pending messages found after error - processing",
                    extra={
                        "user_id": user_id,
                        "event": "pending_after_error"
                    }
                )
                await handle_pending_messages(user_id, chat_id, pending, context)
        except Exception:
            pass  # Ignore errors in pending check after error


async def handle_voice_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming voice messages with authorization.

    Args:
        update: Telegram update object
        context: Bot context
    """
    global auth_module

    # Extract message data
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    message_id = message.message_id
    timestamp = message.date
    username = message.from_user.username
    voice = message.voice

    # Log voice message receipt
    logger.info(
        "Voice message received",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "voice_duration": voice.duration,
            "voice_file_size": voice.file_size,
            "timestamp": timestamp.isoformat(),
            "username": username,
            "event": "voice_message_received"
        }
    )

    # Authorization check (fail-fast pattern)
    if not auth_module.is_authorized(user_id):
        logger.warning(
            f"UNAUTHORIZED VOICE MESSAGE - User ID: {user_id}, Username: @{username or 'unknown'}",
            extra={
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "message_id": message_id,
                "event": "voice_message_blocked"
            }
        )

        # Send rejection message
        await message.reply_text(auth_module.get_rejection_message())

        logger.info(
            "Rejection message sent to unauthorized user",
            extra={
                "user_id": user_id,
                "event": "rejection_sent"
            }
        )
        return

    # User is authorized - proceed with processing
    logger.info(
        "Voice message authorized - processing",
        extra={
            "user_id": user_id,
            "message_id": message_id,
            "authorized": True,
            "event": "voice_message_authorized"
        }
    )

    # Check if already processing another message
    redis = get_redis_client()
    user_id_str = str(user_id)
    processing_key = f"processing:{user_id_str}"

    try:
        is_processing = await redis.get(processing_key)

        if is_processing:
            # Already processing - inform user that voice messages can't be queued
            logger.info(
                "User has active request - cannot queue voice message",
                extra={
                    "user_id": user_id,
                    "message_id": message_id,
                    "event": "voice_message_rejected_busy"
                }
            )

            await message.reply_text(
                "📝 I'm currently processing your previous message. "
                "Voice messages can't be queued - please wait a moment and try again."
            )
            return

    except Exception as e:
        # Redis error - log but continue processing (graceful degradation)
        logger.error(
            "Failed to check processing flag for voice - proceeding",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "voice_processing_check_failed"
            }
        )

    # Set processing flag (atomic with NX flag)
    try:
        flag_set = await redis.set(processing_key, "1", ex=180, nx=True)

        if not flag_set:
            # Race condition: flag was set between check and set
            logger.warning(
                "Processing flag race condition for voice message",
                extra={
                    "user_id": user_id,
                    "event": "voice_processing_flag_race"
                }
            )
            await message.reply_text(
                "📝 I'm currently processing another message. "
                "Please wait a moment and try again."
            )
            return

        logger.debug(
            "Processing flag set for voice message",
            extra={
                "user_id": user_id,
                "ttl_seconds": 180,
                "event": "voice_processing_flag_set"
            }
        )
    except Exception as e:
        # Redis error - log but continue (graceful degradation)
        logger.error(
            "Failed to set processing flag for voice - continuing anyway",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "voice_processing_flag_set_failed"
            }
        )

    # Get or create conversation state
    state = get_conversation_state(user_id)

    # Send immediate status message (AC #1: <100ms target)
    status_msg = await message.reply_text("🔄 Annie is thinking...")
    state["status_message_id"] = status_msg.message_id

    logger.info(
        "Status message sent for voice",
        extra={
            "user_id": user_id,
            "status_message_id": state["status_message_id"],
            "event": "voice_status_message_sent"
        }
    )

    # Start typing indicator task (keeps showing until response arrives)
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    logger.debug(
        "Typing indicator task started",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "event": "typing_indicator_started"
        }
    )

    # Download and forward voice file to backend
    try:
        # Get backend client
        backend_client = get_backend_client()

        # Download voice file from Telegram
        logger.info(
            "Downloading voice file from Telegram",
            extra={
                "user_id": user_id,
                "file_id": voice.file_id,
                "file_size": voice.file_size,
                "event": "voice_download_start"
            }
        )

        voice_file = await context.bot.get_file(voice.file_id)
        voice_bytes = await voice_file.download_as_bytearray()

        logger.info(
            "Voice file downloaded successfully",
            extra={
                "user_id": user_id,
                "file_id": voice.file_id,
                "downloaded_size": len(voice_bytes),
                "event": "voice_download_success"
            }
        )

        # Upload to backend for transcription and processing
        response = await backend_client.upload_voice_file(
            user_id=user_id,
            file_bytes=bytes(voice_bytes),
            duration=voice.duration
        )

        conversation_id = response.get("conversation_id")
        transcription = response.get("transcription", "")

        logger.info(
            "Voice file uploaded to backend successfully",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "transcription_length": len(transcription),
                "event": "voice_upload_success"
            }
        )

        # Stream response back to user (with first-token timeout enforcement)
        try:
            response_length = await stream_response_to_telegram(
                backend_client,
                conversation_id,
                user_id,
                message,
                typing_task,
                context,
                state
            )
        except asyncio.TimeoutError:
            # First token timeout - cancel typing and inform user
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

            logger.error(
                "First token timeout exceeded",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "event": "first_token_timeout"
                }
            )

            await message.reply_text(
                "Sorry, the response is taking longer than expected. "
                "Please try again or rephrase your question."
            )
            return

        logger.info(
            "Voice message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "voice_duration": voice.duration,
                "response_length": response_length,
                "event": "voice_message_processed"
            }
        )

        # Clear processing flag and check for pending messages
        try:
            await redis.delete(processing_key)
            logger.debug(
                "Processing flag cleared after voice message",
                extra={
                    "user_id": user_id,
                    "event": "voice_processing_flag_cleared"
                }
            )
        except Exception as e:
            logger.error(
                "Failed to clear processing flag after voice",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "event": "voice_processing_flag_clear_failed"
                }
            )

        # Check for pending text messages and process them
        try:
            pending = await get_and_clear_pending(redis, user_id_str)
            if pending:
                logger.info(
                    "Pending messages detected after voice - starting auto-pickup",
                    extra={
                        "user_id": user_id,
                        "pending_length": len(pending),
                        "event": "voice_pending_auto_pickup"
                    }
                )
                # Process pending messages recursively
                await handle_pending_messages(user_id, chat_id, pending, context)
        except Exception as e:
            logger.error(
                "Failed to check/process pending after voice",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "event": "voice_pending_check_failed"
                }
            )

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        # Clear processing flag on error
        try:
            await redis.delete(processing_key)
            logger.debug(
                "Processing flag cleared for voice (error path)",
                extra={
                    "user_id": user_id,
                    "event": "voice_processing_flag_cleared_error"
                }
            )
        except Exception:
            pass  # Ignore errors during cleanup

        # Backend error - send user-friendly error message
        logger.error(
            "Failed to process voice message via backend",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "voice_processing_failed"
            },
            exc_info=True
        )

        # Send error message to user
        await message.reply_text(
            "Sorry, I'm having trouble processing your voice message right now. "
            "Please try again in a moment."
        )

        logger.info(
            "Error message sent to user",
            extra={
                "user_id": user_id,
                "event": "error_message_sent"
            }
        )

        # Still check for pending messages even after error
        try:
            pending = await get_and_clear_pending(redis, user_id_str)
            if pending:
                logger.info(
                    "Pending messages found after voice error - processing",
                    extra={
                        "user_id": user_id,
                        "event": "voice_pending_after_error"
                    }
                )
                await handle_pending_messages(user_id, chat_id, pending, context)
        except Exception:
            pass  # Ignore errors in pending check after error


async def _buffer_media_group_message(
    media_group_id: str,
    message: TelegramMessage,
    caption: str,
    user_id: int,
    chat_id: int,
    context: ContextTypes.DEFAULT_TYPE
):
    """
    Buffer a message that's part of a media group (multiple files sent at once).

    When users send multiple files at once in Telegram, they arrive as separate
    messages with the same media_group_id. We buffer them and process together
    after a short delay to ensure all files are collected.

    Args:
        media_group_id: Telegram's media group identifier
        message: The Telegram message containing the file
        caption: Caption from the message (usually only on first message)
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        context: Bot context
    """
    global media_group_buffers

    if media_group_id not in media_group_buffers:
        # First message in this media group - create buffer
        media_group_buffers[media_group_id] = {
            "messages": [message],
            "caption": caption,  # Caption is usually only on first message
            "user_id": user_id,
            "chat_id": chat_id,
            "context": context,
            "task": None
        }

        logger.info(
            "Media group buffer created",
            extra={
                "media_group_id": media_group_id,
                "user_id": user_id,
                "has_caption": bool(caption),
                "event": "media_group_buffer_created"
            }
        )

        # Schedule processing after delay
        async def process_after_delay():
            await asyncio.sleep(MEDIA_GROUP_WAIT_SECONDS)
            await _process_media_group(media_group_id)

        task = asyncio.create_task(process_after_delay())
        media_group_buffers[media_group_id]["task"] = task

    else:
        # Additional message in existing media group - add to buffer
        buffer = media_group_buffers[media_group_id]
        buffer["messages"].append(message)

        # Update caption if this message has one (first message with caption wins)
        if caption and not buffer["caption"]:
            buffer["caption"] = caption

        logger.debug(
            "Message added to media group buffer",
            extra={
                "media_group_id": media_group_id,
                "message_count": len(buffer["messages"]),
                "has_caption": bool(buffer["caption"]),
                "event": "media_group_message_added"
            }
        )


async def _process_media_group(media_group_id: str):
    """
    Process all buffered files from a media group together.

    Called after the buffer delay expires. Collects all files,
    uses the caption from the first message, and sends to backend.

    Args:
        media_group_id: The media group to process
    """
    global media_group_buffers, auth_module

    if media_group_id not in media_group_buffers:
        logger.warning(
            "Media group buffer not found for processing",
            extra={"media_group_id": media_group_id, "event": "media_group_buffer_missing"}
        )
        return

    buffer = media_group_buffers.pop(media_group_id)
    messages = buffer["messages"]
    caption = buffer["caption"]
    user_id = buffer["user_id"]
    chat_id = buffer["chat_id"]
    context = buffer["context"]

    logger.info(
        "Processing media group",
        extra={
            "media_group_id": media_group_id,
            "user_id": user_id,
            "message_count": len(messages),
            "has_caption": bool(caption),
            "event": "media_group_processing_start"
        }
    )

    # Authorization check
    if not auth_module.is_authorized(user_id):
        logger.warning(
            f"UNAUTHORIZED MEDIA GROUP - User ID: {user_id}",
            extra={
                "user_id": user_id,
                "media_group_id": media_group_id,
                "event": "media_group_blocked"
            }
        )
        # Reply to first message
        await messages[0].reply_text(auth_module.get_rejection_message())
        return

    # Process files from all messages in the group
    from telegram_bot.file_handler import (
        FileProcessingResult,
        process_message_files,
        format_partial_success_acknowledgment,
    )

    all_successful = []
    all_failed = []

    for msg in messages:
        result = await process_message_files(msg, context)
        all_successful.extend(result.successful)
        all_failed.extend(result.failed)

    # Create combined result
    combined_result = FileProcessingResult(successful=all_successful, failed=all_failed)

    logger.info(
        "Media group files processed",
        extra={
            "media_group_id": media_group_id,
            "successful_count": len(all_successful),
            "failed_count": len(all_failed),
            "event": "media_group_files_processed"
        }
    )

    # Handle case where all files failed
    if combined_result.all_failed:
        error_msg = format_partial_success_acknowledgment(combined_result)
        await messages[0].reply_text(error_msg)
        return

    # Send acknowledgment for successful files and capture message ID for streaming
    status_message_id = None
    if combined_result.has_successful:
        ack_msg = format_file_acknowledgment(combined_result.successful)
        if ack_msg:
            ack_sent = await messages[0].reply_text(ack_msg)
            status_message_id = ack_sent.message_id

    # Set the status message ID in conversation state for streaming updates
    state = get_conversation_state(user_id)
    state["status_message_id"] = status_message_id

    logger.debug(
        "Media group status message set",
        extra={
            "user_id": user_id,
            "status_message_id": status_message_id,
            "event": "media_group_status_set"
        }
    )

    # Forward to backend with combined files
    await _forward_media_group_to_backend(
        messages[0], context, user_id, chat_id, caption, combined_result
    )


async def _forward_media_group_to_backend(
    reply_message: TelegramMessage,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    caption: str,
    file_result: "FileProcessingResult"
):
    """
    Forward processed media group files to the backend.

    Args:
        reply_message: Message to reply to (first in group)
        context: Bot context
        user_id: Telegram user ID
        chat_id: Telegram chat ID
        caption: User's caption (or empty string)
        file_result: Combined file processing result
    """
    redis = get_redis_client()
    user_id_str = str(user_id)
    processing_key = f"processing:{user_id_str}"

    # Check/set processing flag
    try:
        is_processing = await redis.get(processing_key)
        if is_processing:
            await reply_message.reply_text(
                "📝 I'm currently processing your previous message. "
                "Please wait a moment and try again."
            )
            return

        await redis.set(processing_key, "1", ex=180, nx=True)
    except Exception as e:
        logger.error(
            "Redis error in media group processing",
            extra={"user_id": user_id, "error": str(e)}
        )

    # Start typing indicator
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    # Build message text (use caption or default prompt)
    message_text = caption if caption else "What do you see in these files? Please analyze them."

    try:
        backend_client = get_backend_client()
        files_data = [f.to_dict() for f in file_result.successful]

        response = await backend_client.send_message(
            user_id=user_id,
            message=message_text,
            message_type="file",
            files=files_data
        )

        conversation_id = response.get("conversation_id")

        logger.info(
            "Media group forwarded to backend",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "files_count": len(files_data),
                "has_caption": bool(caption),
                "event": "media_group_backend_forward"
            }
        )

        # Stream response
        state = get_conversation_state(user_id)
        response_length = await stream_response_to_telegram(
            backend_client,
            conversation_id,
            user_id,
            reply_message,
            typing_task,
            context,
            state
        )

        logger.info(
            "Media group response streamed",
            extra={
                "user_id": user_id,
                "response_length": response_length,
                "event": "media_group_response_complete"
            }
        )

    except Exception as e:
        typing_task.cancel()
        logger.error(
            "Error processing media group",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "media_group_error"
            },
            exc_info=True
        )
        await reply_message.reply_text(
            "Sorry, I encountered an error processing your files. Please try again."
        )

    finally:
        # Clear processing flag
        try:
            await redis.delete(processing_key)
        except Exception:
            pass


async def handle_file_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handle incoming file messages (photos, documents) with authorization.

    Processes files, sends acknowledgment, and forwards to backend for
    multimodal LLM processing (Gemini native or ChatGPT fallback).

    Args:
        update: Telegram update object
        context: Bot context
    """
    global auth_module

    # Extract message data
    message = update.message
    user_id = message.from_user.id
    chat_id = message.chat_id
    message_id = message.message_id
    timestamp = message.date
    username = message.from_user.username

    # Get caption if any (user's message along with the file)
    caption = message.caption or ""

    # Determine file type for logging
    file_type = "photo" if message.photo else "document"

    # Check for media group (multiple files sent at once)
    media_group_id = message.media_group_id

    # Log file message receipt
    logger.info(
        "File message received",
        extra={
            "user_id": user_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "file_type": file_type,
            "has_caption": bool(caption),
            "caption_length": len(caption) if caption else 0,
            "media_group_id": media_group_id,
            "timestamp": timestamp.isoformat(),
            "username": username,
            "event": "file_message_received"
        }
    )

    # Handle media groups (multiple files sent at once)
    if media_group_id:
        await _buffer_media_group_message(
            media_group_id, message, caption, user_id, chat_id, context
        )
        return  # Processing will happen when buffer is flushed

    # Authorization check (fail-fast pattern)
    if not auth_module.is_authorized(user_id):
        logger.warning(
            f"UNAUTHORIZED FILE MESSAGE - User ID: {user_id}, Username: @{username or 'unknown'}",
            extra={
                "user_id": user_id,
                "username": username,
                "chat_id": chat_id,
                "message_id": message_id,
                "file_type": file_type,
                "event": "file_message_blocked"
            }
        )

        # Send rejection message
        await message.reply_text(auth_module.get_rejection_message())

        logger.info(
            "Rejection message sent to unauthorized user",
            extra={
                "user_id": user_id,
                "event": "rejection_sent"
            }
        )
        return

    # User is authorized - proceed with processing
    logger.info(
        "File message authorized - processing",
        extra={
            "user_id": user_id,
            "message_id": message_id,
            "file_type": file_type,
            "authorized": True,
            "event": "file_message_authorized"
        }
    )

    # Check if already processing another message
    redis = get_redis_client()
    user_id_str = str(user_id)
    processing_key = f"processing:{user_id_str}"

    try:
        is_processing = await redis.get(processing_key)

        if is_processing:
            # Already processing - inform user that file messages can't be queued
            logger.info(
                "User has active request - cannot queue file message",
                extra={
                    "user_id": user_id,
                    "message_id": message_id,
                    "file_type": file_type,
                    "event": "file_message_rejected_busy"
                }
            )

            await message.reply_text(
                "📝 I'm currently processing your previous message. "
                "Files can't be queued - please wait a moment and try again."
            )
            return

    except Exception as e:
        # Redis error - log but continue processing (graceful degradation)
        logger.error(
            "Failed to check processing flag for file - proceeding",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "file_processing_check_failed"
            }
        )

    # Set processing flag (atomic with NX flag)
    try:
        flag_set = await redis.set(processing_key, "1", ex=180, nx=True)

        if not flag_set:
            # Race condition: flag was set between check and set
            logger.warning(
                "Processing flag race condition for file message",
                extra={
                    "user_id": user_id,
                    "event": "file_processing_flag_race"
                }
            )
            await message.reply_text(
                "📝 I'm currently processing another message. "
                "Please wait a moment and try again."
            )
            return

        logger.debug(
            "Processing flag set for file message",
            extra={
                "user_id": user_id,
                "ttl_seconds": 180,
                "event": "file_processing_flag_set"
            }
        )
    except Exception as e:
        # Redis error - log but continue (graceful degradation)
        logger.error(
            "Failed to set processing flag for file - continuing anyway",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "file_processing_flag_set_failed"
            }
        )

    # Process files from message
    file_result = await process_message_files(message, context)

    # Handle case where all files failed
    if file_result.all_failed:
        # Clear processing flag
        try:
            await redis.delete(processing_key)
        except Exception:
            pass

        # Send error message for first failure
        error_msg = format_partial_success_acknowledgment(file_result)
        await message.reply_text(error_msg)

        logger.warning(
            "All files failed to process",
            extra={
                "user_id": user_id,
                "failed_count": len(file_result.failed),
                "errors": [e.to_dict() for e in file_result.failed],
                "event": "all_files_failed"
            }
        )

        # If there's a caption, process it as a text message without files
        if caption:
            logger.info(
                "Processing caption as text-only message after file failures",
                extra={
                    "user_id": user_id,
                    "caption_length": len(caption),
                    "event": "caption_fallback"
                }
            )
            # Graceful degradation: send caption as text-only
            # Reset processing flag was already cleared, continue with text
            await _process_text_with_files(
                message, context, user_id, chat_id, caption, None, redis, processing_key
            )
        return

    # Files processed (at least some successful)
    # Send acknowledgment message
    ack_message = format_partial_success_acknowledgment(file_result)
    status_msg = await message.reply_text(ack_message)

    logger.info(
        "File acknowledgment sent",
        extra={
            "user_id": user_id,
            "successful_count": len(file_result.successful),
            "failed_count": len(file_result.failed),
            "total_size_bytes": sum(f.size_bytes for f in file_result.successful),
            "event": "file_acknowledgment_sent"
        }
    )

    # Get or create conversation state
    state = get_conversation_state(user_id)
    state["status_message_id"] = status_msg.message_id

    # Start typing indicator
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    # Build message content (use caption or default prompt)
    message_text = caption if caption else "What do you see in this file? Please analyze it."

    # Forward message to backend with files
    try:
        # Get backend client
        backend_client = get_backend_client()

        # Convert FileAttachments to dicts for JSON transport
        files_data = [f.to_dict() for f in file_result.successful]

        # Send message to backend with files
        response = await backend_client.send_message(
            user_id=user_id,
            message=message_text,
            message_type="file",
            files=files_data
        )

        conversation_id = response.get("conversation_id")

        logger.info(
            "File message forwarded to backend successfully",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "files_count": len(files_data),
                "total_size_bytes": sum(f.size_bytes for f in file_result.successful),
                "event": "file_backend_forward_success"
            }
        )

        # Stream response back to user (with first-token timeout enforcement)
        try:
            response_length = await stream_response_to_telegram(
                backend_client,
                conversation_id,
                user_id,
                message,
                typing_task,
                context,
                state
            )
        except asyncio.TimeoutError:
            # First token timeout - cancel typing and inform user
            typing_task.cancel()
            try:
                await typing_task
            except asyncio.CancelledError:
                pass

            logger.error(
                "First token timeout exceeded for file message",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "event": "file_first_token_timeout"
                }
            )

            await message.reply_text(
                "Sorry, the response is taking longer than expected. "
                "Please try again or rephrase your question."
            )
            return

        logger.info(
            "File message processing complete",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "conversation_id": conversation_id,
                "file_type": file_type,
                "files_count": len(file_result.successful),
                "response_length": response_length,
                "event": "file_message_processed"
            }
        )

        # Clear processing flag and check for pending messages
        try:
            await redis.delete(processing_key)
            logger.debug(
                "Processing flag cleared after file message",
                extra={
                    "user_id": user_id,
                    "event": "file_processing_flag_cleared"
                }
            )
        except Exception as e:
            logger.error(
                "Failed to clear processing flag after file",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "event": "file_processing_flag_clear_failed"
                }
            )

        # Check for pending text messages and process them
        try:
            pending = await get_and_clear_pending(redis, user_id_str)
            if pending:
                logger.info(
                    "Pending messages detected after file - starting auto-pickup",
                    extra={
                        "user_id": user_id,
                        "pending_length": len(pending),
                        "event": "file_pending_auto_pickup"
                    }
                )
                # Process pending messages recursively
                await handle_pending_messages(user_id, chat_id, pending, context)
        except Exception as e:
            logger.error(
                "Failed to check/process pending after file",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "event": "file_pending_check_failed"
                }
            )

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        # Clear processing flag on error
        try:
            await redis.delete(processing_key)
            logger.debug(
                "Processing flag cleared for file (error path)",
                extra={
                    "user_id": user_id,
                    "event": "file_processing_flag_cleared_error"
                }
            )
        except Exception:
            pass  # Ignore errors during cleanup

        # Backend error - send user-friendly error message
        logger.error(
            "Failed to process file message via backend",
            extra={
                "user_id": user_id,
                "message_id": message_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "file_processing_failed"
            },
            exc_info=True
        )

        # Send error message to user
        await message.reply_text(
            "Sorry, I'm having trouble processing your file right now. "
            "Please try again in a moment."
        )

        logger.info(
            "Error message sent to user",
            extra={
                "user_id": user_id,
                "event": "error_message_sent"
            }
        )

        # Still check for pending messages even after error
        try:
            pending = await get_and_clear_pending(redis, user_id_str)
            if pending:
                logger.info(
                    "Pending messages found after file error - processing",
                    extra={
                        "user_id": user_id,
                        "event": "file_pending_after_error"
                    }
                )
                await handle_pending_messages(user_id, chat_id, pending, context)
        except Exception:
            pass  # Ignore errors in pending check after error


async def _process_text_with_files(
    message: TelegramMessage,
    context: ContextTypes.DEFAULT_TYPE,
    user_id: int,
    chat_id: int,
    message_text: str,
    files_data: Optional[list],
    redis,
    processing_key: str
):
    """
    Internal helper to process a text message with optional file attachments.

    This is used for graceful degradation when files fail but caption is present.

    Args:
        message: Telegram message object
        context: Bot context
        user_id: User ID
        chat_id: Chat ID
        message_text: Message text content
        files_data: Optional list of file dicts (or None for text-only)
        redis: Redis client
        processing_key: Redis key for processing flag
    """
    # Set processing flag
    try:
        await redis.set(processing_key, "1", ex=180, nx=True)
    except Exception:
        pass

    # Get or create conversation state
    state = get_conversation_state(user_id)

    # Send status message
    status_msg = await message.reply_text("🔄 Annie is thinking...")
    state["status_message_id"] = status_msg.message_id

    # Start typing indicator
    typing_task = asyncio.create_task(keep_typing_indicator(context, chat_id))

    try:
        # Get backend client
        backend_client = get_backend_client()

        # Send message to backend (with or without files)
        response = await backend_client.send_message(
            user_id=user_id,
            message=message_text,
            message_type="text" if not files_data else "file",
            files=files_data
        )

        conversation_id = response.get("conversation_id")

        # Stream response
        response_length = await stream_response_to_telegram(
            backend_client,
            conversation_id,
            user_id,
            message,
            typing_task,
            context,
            state
        )

        logger.info(
            "Text-with-files message processed",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "response_length": response_length,
                "had_files": bool(files_data),
                "event": "text_with_files_processed"
            }
        )

    except Exception as e:
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        logger.error(
            "Failed to process text-with-files message",
            extra={
                "user_id": user_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "event": "text_with_files_failed"
            }
        )

        await message.reply_text(
            "Sorry, I'm having trouble processing your message right now. "
            "Please try again in a moment."
        )

    finally:
        # Clear processing flag
        try:
            await redis.delete(processing_key)
        except Exception:
            pass
