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
from telegram.error import RetryAfter, BadRequest, TelegramError


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
            await self.redis_client.aclose()

    @observe(name="send_proactive_message", as_type="span")
    async def send_proactive_message(
        self,
        user_id: str,
        message: str,
        trigger_id: str,
        parse_mode: str = "HTML",
        max_retries: Optional[int] = None
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

            # Convert markdown to Telegram-safe HTML
            # LLM output uses markdown (e.g., **bold**, ###) but Telegram expects HTML
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

                    # Send message via Telegram API (using HTML-converted message)
                    message_obj = await self.bot.send_message(
                        chat_id=chat_id,
                        text=html_message,
                        parse_mode=parse_mode
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
                            "event": "proactive_delivery_success"
                        }
                    )

                    # Record message for feedback detection (Story 13.10)
                    try:
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
            error_msg = f"Invalid Telegram request: {str(e)}"
            delivery_ms = int((time.time() - start_time) * 1000)
            logger.error(
                error_msg,
                extra={
                    "user_id": user_id,
                    "trigger_id": trigger_id,
                    "error": str(e),
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
