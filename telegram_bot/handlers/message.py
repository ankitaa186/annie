"""
Message Handler with Authorization

This module handles incoming Telegram messages with authorization checks.
"""

import asyncio
import html
import re
import time
from telegram import Update, Message as TelegramMessage
from telegram.ext import ContextTypes, MessageHandler, filters
from telegram.error import RetryAfter, TelegramError
from telegram.constants import ParseMode

from telegram_bot.auth import AuthenticationModule
from telegram_bot.backend_client import get_backend_client
from telegram_bot.config import get_config
from telegram_bot.logger import get_logger

logger = get_logger(__name__)


def markdown_to_telegram_html(text: str) -> str:
    """
    Convert markdown from LLM output to Telegram-safe HTML.

    Handles common markdown patterns:
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

# Telegram message length limit (use 4000 for safety, actual limit is 4096)
MAX_MESSAGE_LENGTH = 4000

# Update frequency for streaming (milliseconds) - AC #2 specifies 100-500ms
# Using 200ms as a good balance between responsiveness and rate limiting
MIN_UPDATE_INTERVAL_MS = 500  # Update every 500ms (2x per second) to avoid Telegram rate limits


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
    typing_task: asyncio.Task
):
    """
    Stream LLM response to Telegram with time-based updates and message splitting.

    Enforces first-token timeout (AC #7) by wrapping the initial streaming call.

    Args:
        backend_client: Backend client instance
        conversation_id: Conversation ID from backend
        user_id: Telegram user ID
        message: Original Telegram message to reply to
        typing_task: Typing indicator task to cancel when first message is sent

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
    is_first_chunk = True

    # Get the stream generator
    stream = backend_client.stream_response(conversation_id, user_id)

    # Enforce first-token timeout by wrapping first iteration with wait_for
    first_token_timeout = backend_client.first_token_timeout
    try:
        # Wait for first chunk with timeout
        first_chunk = await asyncio.wait_for(
            stream.__anext__(),
            timeout=first_token_timeout
        )

        # Process first chunk
        response_buffer.append(first_chunk)
        chunk_count += 1
        current_text = "".join(response_buffer)
        current_time_ms = time.time() * 1000

        # Send first message immediately (with HTML formatting)
        html_text = markdown_to_telegram_html(current_text)
        sent_messages.append(await message.reply_text(html_text, parse_mode=ParseMode.HTML))
        last_update_time = current_time_ms
        is_first_chunk = False

        # Cancel typing indicator once first message is sent
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        logger.debug(
            "Typing indicator stopped (first message sent)",
            extra={
                "user_id": user_id,
                "chat_id": message.chat_id,
                "event": "typing_indicator_stopped"
            }
        )

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
        # This can happen if backend sends "done" event before any "token" events
        logger.warning(
            "Stream completed with no tokens (empty LLM response)",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "event": "empty_stream_response"
            }
        )

        # Cancel typing indicator
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

        # Return 0 - no response sent (graceful handling, no error to user)
        return 0

    # Continue streaming remaining chunks
    async for chunk in stream:
        response_buffer.append(chunk)
        chunk_count += 1
        current_text = "".join(response_buffer)
        current_time_ms = time.time() * 1000  # Current time in milliseconds

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
                await sent_messages[-1].edit_text(html_part, parse_mode=ParseMode.HTML)
            except Exception:
                pass  # Ignore edit failures on split

            # Start new message with remainder
            remaining_text = current_text[split_point:]
            html_remaining = markdown_to_telegram_html(remaining_text)
            new_message = await message.reply_text(html_remaining, parse_mode=ParseMode.HTML)
            sent_messages.append(new_message)

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

        # Time-based update logic (AC #2: updates every 100-500ms)
        # Update if MIN_UPDATE_INTERVAL_MS has passed since last update
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
                await sent_messages[-1].edit_text(html_text, parse_mode=ParseMode.HTML)
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
                await asyncio.wait_for(
                    sent_messages[-1].edit_text(final_html, parse_mode=ParseMode.HTML),
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

    # Calculate total response length across all messages
    total_length = sum(len(msg.text or "") for msg in sent_messages)
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
                typing_task
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

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

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
                typing_task
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

    except Exception as e:
        # Cancel typing indicator on error
        typing_task.cancel()
        try:
            await typing_task
        except asyncio.CancelledError:
            pass

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
