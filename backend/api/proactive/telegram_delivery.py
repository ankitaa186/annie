"""
Telegram Delivery Module for Proactive AI

This module handles sending proactive messages to users via Telegram Bot API.
It includes rate limit handling, retry logic, and feedback tracking for Story 13.10.

Key Features:
- Direct Telegram Bot API integration using python-telegram-bot
- Rate limit handling with exponential backoff (up to 3 retries)
- Redis-based message tracking for feedback detection
- Langfuse tracing for observability
- Graceful error handling (never crashes worker)

Redis Keys:
- proactive_message:{user_id}:last -> JSON with trigger_id, message_id, sent_at (TTL: 2h)
"""

import asyncio
import html
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import redis.asyncio as redis
from telegram import Bot
from telegram.constants import ChatAction
from telegram.error import RetryAfter, BadRequest, TelegramError


def strip_html_tags(text: str) -> str:
    """Remove all HTML tags from text, used as fallback when HTML parsing fails."""
    return re.sub(r'<[^>]+>', '', text)


def validate_html_tags(text: str) -> bool:
    """
    Check if HTML tags are properly balanced.
    Returns True if all tags are balanced, False otherwise.
    """
    # Simple tag matching for Telegram-supported tags
    tag_pattern = re.compile(r'<(/?)([a-z]+)(?:\s[^>]*)?>')
    stack = []

    for match in tag_pattern.finditer(text):
        is_closing = match.group(1) == '/'
        tag_name = match.group(2)

        if is_closing:
            if not stack or stack[-1] != tag_name:
                return False
            stack.pop()
        else:
            stack.append(tag_name)

    return len(stack) == 0


def convert_markdown_table_to_text(text: str) -> str:
    """
    Convert markdown tables to readable text format.

    Markdown tables like:
        | Col1 | Col2 | Col3 |
        |------|------|------|
        | A    | B    | C    |

    Are converted to:
        Col1: A
        Col2: B
        Col3: C
        ───────────

    Args:
        text: Text potentially containing markdown tables

    Returns:
        Text with tables converted to readable format
    """
    lines = text.split('\n')
    result = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Check if this line looks like a table row (starts with |)
        if line.strip().startswith('|') and '|' in line[1:]:
            # Found potential table start - collect all table lines
            table_lines = []

            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1

            # Need at least header + separator + 1 data row
            if len(table_lines) >= 3:
                # Parse header row
                header_line = table_lines[0]
                headers = [h.strip() for h in header_line.strip('|').split('|')]
                headers = [h for h in headers if h]  # Remove empty strings

                # Check if second line is separator (contains dashes)
                separator_line = table_lines[1].strip()
                if re.match(r'^[\|\s\-:]+$', separator_line):
                    # Valid table - convert data rows
                    data_rows = table_lines[2:]

                    for row_line in data_rows:
                        cells = [c.strip() for c in row_line.strip('|').split('|')]
                        cells = [c for c in cells if c or len(cells) > len(headers)]

                        # Build readable format: Header: Value
                        for j, header in enumerate(headers):
                            if j < len(cells):
                                value = cells[j].strip()
                                if value:  # Only add non-empty values
                                    result.append(f"  {header}: {value}")

                        # Add separator between rows
                        result.append("  ───────────")

                    # Remove trailing separator
                    if result and result[-1] == "  ───────────":
                        result.pop()
                    result.append("")  # Blank line after table
                else:
                    # Not a valid table (no separator), keep original lines
                    result.extend(table_lines)
            else:
                # Not enough lines for a table, keep original
                result.extend(table_lines)
        else:
            result.append(line)
            i += 1

    return '\n'.join(result)


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
    - | tables | → readable key-value format

    Args:
        text: Raw markdown text from LLM

    Returns:
        HTML-formatted text safe for Telegram
    """
    if not text:
        return text

    # Convert markdown tables to readable text BEFORE escaping HTML
    text = convert_markdown_table_to_text(text)

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

    # Inline code (`code`) - non-greedy to avoid spanning multiple code spans
    text = re.sub(r'`([^`]+?)`', r'<code>\1</code>', text)

    # Bold+Italic combined: ***text*** → <b><i>text</i></b>
    # Must be done BEFORE separate bold/italic to avoid conflicts
    # Use non-greedy matching
    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'<b><i>\1</i></b>', text)
    text = re.sub(r'___(.+?)___', r'<b><i>\1</i></b>', text)

    # Bold: **text** or __text__ - non-greedy
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'__(.+?)__', r'<b>\1</b>', text)

    # Italic with asterisks: *text* - non-greedy, with word boundary checks
    # Must not be preceded or followed by word chars to avoid matching mid-word
    text = re.sub(r'(?<!\w)\*(.+?)\*(?!\w)', r'<i>\1</i>', text)

    # Skip underscore italic - it's too error-prone with technical text
    # containing variable_names, file_paths, etc.
    # text = re.sub(r'(?<!\w)_(.+?)_(?!\w)', r'<i>\1</i>', text)

    # Links: [text](url)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)

    # Headers: ### Header → bold (Telegram doesn't support headers)
    text = re.sub(r'^#{1,6}\s*(.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)

    # Strikethrough: ~~text~~ → <s>text</s>
    text = re.sub(r'~~(.+?)~~', r'<s>\1</s>', text)

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

    # Validate that HTML tags are balanced
    if not validate_html_tags(text):
        # If tags are unbalanced, strip all HTML and return escaped text
        # This is safer than sending malformed HTML to Telegram
        return html.escape(strip_html_tags(text))

    return text


# Telegram message length limit (use 4000 for safety, actual limit is 4096)
MAX_MESSAGE_LENGTH = 4000


def split_long_message(text: str, max_length: int = MAX_MESSAGE_LENGTH) -> list[str]:
    """
    Split a long message into chunks that fit within Telegram's limit.

    Tries to split at natural breakpoints (double newline, single newline, space).

    Args:
        text: The message text to split
        max_length: Maximum length per chunk (default 4000)

    Returns:
        List of message chunks
    """
    if len(text) <= max_length:
        return [text]

    chunks = []
    remaining = text

    while len(remaining) > max_length:
        # Find best split point
        split_point = max_length

        # Try to split at double newline (paragraph break) first
        for i in range(max_length - 1, max(0, max_length - 500), -1):
            if remaining[i:i+2] == '\n\n':
                split_point = i + 2
                break
        else:
            # Try single newline
            for i in range(max_length - 1, max(0, max_length - 300), -1):
                if remaining[i] == '\n':
                    split_point = i + 1
                    break
            else:
                # Try space
                for i in range(max_length - 1, max(0, max_length - 100), -1):
                    if remaining[i] == ' ':
                        split_point = i + 1
                        break

        chunks.append(remaining[:split_point].rstrip())
        remaining = remaining[split_point:].lstrip()

    if remaining:
        chunks.append(remaining)

    return chunks


from api.config import get_config
from api.logging import get_logger

try:
    from langfuse.decorators import observe
    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False
    def observe(**kwargs):
        def decorator(func):
            return func
        return decorator

logger = get_logger(__name__)


@dataclass
class DeliveryResult:
    """Result of a proactive message delivery attempt.

    Attributes:
        success: Whether the message was delivered successfully
        message_id: Telegram message ID if successful (None if failed)
        error: Error message if delivery failed (None if successful)
        delivery_ms: Delivery time in milliseconds
    """
    success: bool
    message_id: Optional[str]
    error: Optional[str]
    delivery_ms: int


class TelegramDelivery:
    """Telegram message delivery handler for proactive AI system.

    This class provides the core delivery mechanism for sending proactive messages
    to users via Telegram. It handles rate limits, retries, and records messages
    for feedback tracking.

    Usage:
        delivery = TelegramDelivery()
        result = await delivery.send_proactive_message(
            user_id="123456789",
            message="Your stocks are up 5% today!",
            trigger_id="price_alert_AAPL_123"
        )

        if result.success:
            print(f"Message sent: {result.message_id}")
        else:
            print(f"Delivery failed: {result.error}")
    """

    # Configuration
    MAX_RETRIES = 3
    FEEDBACK_WINDOW_SECONDS = 7200  # 2 hours

    def __init__(self, bot_token: Optional[str] = None, redis_client: Optional[redis.Redis] = None):
        """Initialize Telegram delivery handler.

        Args:
            bot_token: Telegram bot token (defaults to TELEGRAM_BOT_TOKEN from env)
            redis_client: Redis client for message tracking (defaults to new client)
        """
        # Get bot token from config if not provided
        if bot_token is None:
            config = get_config()
            bot_token = config.get("TELEGRAM_BOT_TOKEN")
            if not bot_token or bot_token == "REPLACE_ME":
                raise ValueError(
                    "TELEGRAM_BOT_TOKEN is required for proactive message delivery. "
                    "Please set it in your .env file."
                )

        self.bot = Bot(token=bot_token)

        # Set up Redis client for message tracking
        if redis_client:
            self.redis_client = redis_client
            self._should_close_redis = False
        else:
            config = get_config()
            redis_host = config.get("REDIS_HOST", "redis")
            redis_port = int(config.get("REDIS_PORT", "6379"))
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                decode_responses=True
            )
            self._should_close_redis = True

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - cleanup resources."""
        if self._should_close_redis and self.redis_client:
            await self.redis_client.close()

    @observe(name="send_proactive_message", as_type="span")
    async def send_proactive_message(
        self,
        user_id: str,
        message: str,
        trigger_id: str,
        parse_mode: str = "HTML",
        max_retries: Optional[int] = None,
        is_html: bool = False,
    ) -> DeliveryResult:
        """Send proactive message to user via Telegram.

        This method handles:
        1. Input validation
        2. Message delivery via Telegram Bot API
        3. Rate limit handling with exponential backoff
        4. Message tracking for feedback detection (Story 13.10)
        5. Performance timing and observability

        Args:
            user_id: User identifier (Telegram chat_id as string)
            message: Message text to send
            trigger_id: Trigger ID for tracking and feedback
            parse_mode: Telegram parse mode (HTML or Markdown)
            max_retries: Maximum retry attempts for rate limits (default: 3)
            is_html: If True, message is already Telegram-safe HTML; skip
                     markdown-to-HTML conversion (default: False)

        Returns:
            DeliveryResult with success status, message_id, error, and timing
        """
        start_time = time.time()
        max_retries = max_retries or self.MAX_RETRIES

        # Input validation
        if not user_id or not user_id.strip():
            error_msg = "user_id cannot be empty"
            logger.error(
                error_msg,
                extra={
                    "trigger_id": trigger_id,
                    "event": "proactive_delivery_validation_failed"
                }
            )
            delivery_ms = int((time.time() - start_time) * 1000)
            return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

        if not message or not message.strip():
            error_msg = "message cannot be empty"
            logger.error(
                error_msg,
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger_id,
                    "event": "proactive_delivery_validation_failed"
                }
            )
            delivery_ms = int((time.time() - start_time) * 1000)
            return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

        if not trigger_id or not trigger_id.strip():
            error_msg = "trigger_id cannot be empty"
            logger.error(
                error_msg,
                extra={
                    "user_id": user_id,
                    "event": "proactive_delivery_validation_failed"
                }
            )
            delivery_ms = int((time.time() - start_time) * 1000)
            return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

        try:
            # Convert user_id (string) to chat_id (int)
            # In our system, user_id IS the Telegram chat_id
            try:
                chat_id = int(user_id)
            except ValueError:
                error_msg = f"Invalid user_id format (must be numeric): {user_id}"
                logger.error(
                    error_msg,
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "event": "proactive_delivery_validation_failed"
                    }
                )
                delivery_ms = int((time.time() - start_time) * 1000)
                return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

            # Convert markdown to Telegram-safe HTML (skip if already HTML)
            if is_html:
                html_message = message
            else:
                html_message = markdown_to_telegram_html(message)
                logger.debug(
                    "Converted markdown to HTML for Telegram",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "original_length": len(message),
                        "html_length": len(html_message),
                        "event": "markdown_to_html_conversion"
                    }
                )

            # Retry loop for rate limiting
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        "Attempting to deliver proactive message",
                        extra={
                            "user_id": user_id,
                            "chat_id": chat_id,
                            "trigger_id": trigger_id,
                            "message_length": len(message),
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "event": "proactive_delivery_attempt"
                        }
                    )

                    # Split long messages into chunks
                    message_chunks = split_long_message(html_message)
                    total_chunks = len(message_chunks)

                    if total_chunks > 1:
                        logger.info(
                            "Splitting long message into chunks",
                            extra={
                                "user_id": user_id,
                                "trigger_id": trigger_id,
                                "total_chunks": total_chunks,
                                "original_length": len(html_message),
                                "event": "proactive_message_split"
                            }
                        )

                    # Send typing indicator to show user we're about to send
                    await self.bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.TYPING
                    )

                    # Send each chunk
                    message_obj = None
                    for chunk_idx, chunk in enumerate(message_chunks):
                        message_obj = await self.bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            parse_mode=parse_mode
                        )
                        # Small delay between chunks to avoid rate limiting
                        if chunk_idx < total_chunks - 1:
                            await asyncio.sleep(0.5)
                            # Show typing indicator for next chunk
                            await self.bot.send_chat_action(
                                chat_id=chat_id,
                                action=ChatAction.TYPING
                            )

                    delivery_ms = int((time.time() - start_time) * 1000)

                    logger.info(
                        "Proactive message delivered successfully",
                        extra={
                            "user_id": user_id,
                            "chat_id": chat_id,
                            "trigger_id": trigger_id,
                            "message_id": message_obj.message_id,
                            "attempt": attempt,
                            "delivery_ms": delivery_ms,
                            "total_chunks": total_chunks,
                            "event": "proactive_delivery_success"
                        }
                    )

                    # Record last message for feedback detection (Story 13.10)
                    # Skip recording for non-intent trigger_ids (e.g. session_flush:*)
                    # as they are not real intents and cause 422 errors on feedback lookup
                    try:
                        if ":" not in trigger_id:
                            await record_proactive_message(
                                self.redis_client,
                                user_id,
                                trigger_id,
                                str(message_obj.message_id)
                            )
                    except Exception as e:
                        # Don't fail delivery if recording fails
                        logger.warning(
                            "Failed to record proactive message for feedback tracking",
                            extra={
                                "user_id": user_id,
                                "trigger_id": trigger_id,
                                "message_id": message_obj.message_id,
                                "error": str(e),
                                "error_type": type(e).__name__,
                                "event": "proactive_recording_failed"
                            },
                            exc_info=True
                        )

                    return DeliveryResult(
                        success=True,
                        message_id=str(message_obj.message_id),
                        error=None,
                        delivery_ms=delivery_ms
                    )

                except RetryAfter as e:
                    wait_time = e.retry_after
                    logger.warning(
                        f"Rate limited by Telegram, retry_after={wait_time}s",
                        extra={
                            "user_id": user_id,
                            "chat_id": chat_id,
                            "trigger_id": trigger_id,
                            "retry_after": wait_time,
                            "attempt": attempt,
                            "max_retries": max_retries,
                            "event": "proactive_delivery_rate_limited"
                        }
                    )

                    if attempt < max_retries:
                        await asyncio.sleep(wait_time)
                    else:
                        error_msg = f"Rate limited after {max_retries} retries"
                        delivery_ms = int((time.time() - start_time) * 1000)
                        logger.error(
                            error_msg,
                            extra={
                                "user_id": user_id,
                                "chat_id": chat_id,
                                "trigger_id": trigger_id,
                                "delivery_ms": delivery_ms,
                                "event": "proactive_delivery_failed_rate_limit"
                            }
                        )
                        return DeliveryResult(
                            success=False,
                            message_id=None,
                            error=error_msg,
                            delivery_ms=delivery_ms
                        )

        except BadRequest as e:
            error_str = str(e)
            # Check if it's a parsing error - retry with plain text
            if "parse entities" in error_str.lower() or "can't find end tag" in error_str.lower():
                logger.warning(
                    "HTML parsing failed, retrying with plain text",
                    extra={
                        "user_id": user_id,
                        "trigger_id": trigger_id,
                        "error": error_str,
                        "event": "proactive_delivery_html_fallback"
                    }
                )
                try:
                    # Strip all HTML and send as plain text
                    plain_message = html.escape(strip_html_tags(message))
                    message_chunks = split_long_message(plain_message)

                    # Send typing indicator
                    await self.bot.send_chat_action(
                        chat_id=chat_id,
                        action=ChatAction.TYPING
                    )

                    message_obj = None
                    for chunk_idx, chunk in enumerate(message_chunks):
                        message_obj = await self.bot.send_message(
                            chat_id=chat_id,
                            text=chunk,
                            parse_mode=None  # No parsing, plain text
                        )
                        if chunk_idx < len(message_chunks) - 1:
                            await asyncio.sleep(0.5)

                    delivery_ms = int((time.time() - start_time) * 1000)
                    logger.info(
                        "Proactive message delivered as plain text (fallback)",
                        extra={
                            "user_id": user_id,
                            "trigger_id": trigger_id,
                            "message_id": message_obj.message_id,
                            "delivery_ms": delivery_ms,
                            "event": "proactive_delivery_success_plaintext"
                        }
                    )

                    # Record for feedback tracking
                    try:
                        await record_proactive_message(
                            self.redis_client, user_id, trigger_id, str(message_obj.message_id)
                        )
                    except Exception:
                        pass  # Don't fail on recording error

                    return DeliveryResult(
                        success=True,
                        message_id=str(message_obj.message_id),
                        error=None,
                        delivery_ms=delivery_ms
                    )
                except Exception as fallback_error:
                    error_msg = f"Plain text fallback also failed: {str(fallback_error)}"
                    delivery_ms = int((time.time() - start_time) * 1000)
                    logger.error(error_msg, extra={"user_id": user_id, "trigger_id": trigger_id})
                    return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

            error_msg = f"Invalid Telegram request: {error_str}"
            delivery_ms = int((time.time() - start_time) * 1000)
            logger.error(
                error_msg,
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger_id,
                    "error": error_str,
                    "error_type": "BadRequest",
                    "delivery_ms": delivery_ms,
                    "event": "proactive_delivery_failed_bad_request"
                },
                exc_info=True
            )
            return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

        except TelegramError as e:
            error_msg = f"Telegram API error: {str(e)}"
            delivery_ms = int((time.time() - start_time) * 1000)
            logger.error(
                error_msg,
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "delivery_ms": delivery_ms,
                    "event": "proactive_delivery_failed_telegram_error"
                },
                exc_info=True
            )
            return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)

        except Exception as e:
            error_msg = f"Unexpected error during delivery: {str(e)}"
            delivery_ms = int((time.time() - start_time) * 1000)
            logger.error(
                error_msg,
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "delivery_ms": delivery_ms,
                    "event": "proactive_delivery_failed_unexpected"
                },
                exc_info=True
            )
            return DeliveryResult(success=False, message_id=None, error=error_msg, delivery_ms=delivery_ms)


@observe(name="record_proactive_message", as_type="span")
async def record_proactive_message(
    redis_client: redis.Redis,
    user_id: str,
    trigger_id: str,
    message_id: str
) -> None:
    """Record proactive message for feedback detection (Story 13.10).

    This function stores the most recent proactive message sent to a user
    so that the feedback handler can detect if the user's next message is
    a response to the proactive message.

    Redis Key: proactive_message:{user_id}:last
    TTL: 2 hours (feedback window)
    Value: JSON with trigger_id, message_id, sent_at

    Args:
        redis_client: Redis client instance
        user_id: User identifier
        trigger_id: Trigger ID that generated the message
        message_id: Telegram message ID

    Raises:
        Exception: If Redis operation fails (caller should handle gracefully)
    """
    key = f"proactive_message:{user_id}:last"
    value = json.dumps({
        "trigger_id": trigger_id,
        "message_id": message_id,
        "sent_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    })

    # Store with 2-hour TTL (feedback window)
    await redis_client.setex(
        key,
        TelegramDelivery.FEEDBACK_WINDOW_SECONDS,
        value
    )

    logger.info(
        "Recorded proactive message for feedback tracking",
        extra={
            "user_id": user_id,
            "trigger_id": trigger_id,
            "message_id": message_id,
            "ttl_seconds": TelegramDelivery.FEEDBACK_WINDOW_SECONDS,
            "event": "proactive_message_recorded"
        }
    )
