"""
Backend API Client for Telegram Bot

This module handles communication with the Backend API service,
including message forwarding and streaming response handling.
"""

import asyncio
import json
from typing import AsyncGenerator, Optional
import aiohttp

from telegram_bot.config import get_config
from telegram_bot.logger import get_logger

logger = get_logger(__name__)


class BackendClient:
    """Client for communicating with Backend API service."""

    def __init__(self, backend_url: Optional[str] = None, timeout: int = 30):
        """
        Initialize Backend API client.

        Args:
            backend_url: Backend API base URL (defaults to env var)
            timeout: Request timeout in seconds (default: 30)
        """
        config = get_config()
        self.backend_url = backend_url or config.get("BACKEND_URL", "http://backend:8000")
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.session: Optional[aiohttp.ClientSession] = None

        logger.info(
            "Backend client initialized",
            extra={
                "backend_url": self.backend_url,
                "timeout_seconds": timeout,
                "event": "backend_client_initialized"
            }
        )

    async def _ensure_session(self):
        """Ensure aiohttp session is created."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self.timeout)
            logger.debug(
                "HTTP session created",
                extra={"event": "session_created"}
            )

    async def close(self):
        """Close HTTP session."""
        if self.session and not self.session.closed:
            await self.session.close()
            logger.debug(
                "HTTP session closed",
                extra={"event": "session_closed"}
            )

    async def send_message(
        self,
        user_id: int,
        message: str,
        message_type: str = "text",
        max_retries: int = 3
    ) -> dict:
        """
        Send a message to the backend API for processing.

        Args:
            user_id: Telegram user ID
            message: Message content
            message_type: Type of message ("text" or "voice")
            max_retries: Maximum number of retry attempts

        Returns:
            API response with conversation_id and streaming info

        Raises:
            Exception: If all retry attempts fail
        """
        await self._ensure_session()

        payload = {
            "user_id": str(user_id),
            "platform": "telegram",
            "message": message,
            "context": {
                "message_type": message_type
            }
        }

        endpoint = f"{self.backend_url}/api/chat"

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Sending message to backend",
                    extra={
                        "user_id": user_id,
                        "message_type": message_type,
                        "message_length": len(message),
                        "attempt": attempt,
                        "endpoint": endpoint,
                        "event": "backend_request"
                    }
                )

                async with self.session.post(endpoint, json=payload) as response:
                    response.raise_for_status()
                    result = await response.json()

                    logger.info(
                        "Backend response received",
                        extra={
                            "user_id": user_id,
                            "conversation_id": result.get("conversation_id"),
                            "status_code": response.status,
                            "event": "backend_response"
                        }
                    )

                    return result

            except aiohttp.ClientError as e:
                wait_time = 2 ** (attempt - 1)  # Exponential backoff

                logger.error(
                    "Backend request failed",
                    extra={
                        "user_id": user_id,
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "retry_after_seconds": wait_time if attempt < max_retries else None,
                        "event": "backend_request_failed"
                    },
                    exc_info=True
                )

                if attempt < max_retries:
                    logger.info(
                        f"Retrying backend request in {wait_time} seconds...",
                        extra={
                            "wait_time_seconds": wait_time,
                            "event": "retry_scheduled"
                        }
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        "Backend request failed after all retries",
                        extra={
                            "user_id": user_id,
                            "total_attempts": max_retries,
                            "event": "backend_request_exhausted"
                        }
                    )
                    raise

    async def stream_response(
        self,
        conversation_id: str,
        user_id: int
    ) -> AsyncGenerator[str, None]:
        """
        Stream LLM response from backend using Server-Sent Events (SSE).

        Args:
            conversation_id: Conversation ID from chat endpoint
            user_id: Telegram user ID (for logging)

        Yields:
            Response chunks as they arrive

        Raises:
            Exception: If streaming fails
        """
        await self._ensure_session()

        endpoint = f"{self.backend_url}/api/stream/{conversation_id}"

        logger.info(
            "Starting response stream",
            extra={
                "user_id": user_id,
                "conversation_id": conversation_id,
                "endpoint": endpoint,
                "event": "stream_started"
            }
        )

        try:
            async with self.session.get(endpoint) as response:
                response.raise_for_status()

                chunk_count = 0
                async for line in response.content:
                    decoded_line = line.decode("utf-8").strip()

                    # Skip empty lines and SSE comments
                    if not decoded_line or decoded_line.startswith(":"):
                        continue

                    # Parse SSE data field
                    if decoded_line.startswith("data: "):
                        data = decoded_line[6:]  # Remove "data: " prefix

                        # Check for stream end marker
                        if data == "[DONE]":
                            logger.info(
                                "Response stream completed",
                                extra={
                                    "user_id": user_id,
                                    "conversation_id": conversation_id,
                                    "total_chunks": chunk_count,
                                    "event": "stream_completed"
                                }
                            )
                            break

                        # Parse JSON and extract text content
                        try:
                            chunk_data = json.loads(data)
                            chunk_type = chunk_data.get("type")

                            # Only yield text tokens, skip metadata
                            if chunk_type == "token":
                                content = chunk_data.get("content", "")
                                if content:
                                    chunk_count += 1
                                    yield content

                                    logger.debug(
                                        "Stream chunk received",
                                        extra={
                                            "user_id": user_id,
                                            "conversation_id": conversation_id,
                                            "chunk_number": chunk_count,
                                            "chunk_length": len(content),
                                            "event": "stream_chunk"
                                        }
                                    )
                            elif chunk_type == "done":
                                # Stream completed with metadata
                                tokens_used = chunk_data.get("tokens_used", {})
                                logger.info(
                                    "Response stream completed with tokens",
                                    extra={
                                        "user_id": user_id,
                                        "conversation_id": conversation_id,
                                        "total_chunks": chunk_count,
                                        "tokens_used": tokens_used,
                                        "event": "stream_completed"
                                    }
                                )
                                break

                        except json.JSONDecodeError as e:
                            logger.warning(
                                f"Failed to parse stream chunk JSON: {data[:100]}",
                                extra={
                                    "user_id": user_id,
                                    "conversation_id": conversation_id,
                                    "error": str(e),
                                    "event": "stream_parse_error"
                                }
                            )
                            # Skip malformed chunks
                            continue

        except aiohttp.ClientError as e:
            logger.error(
                "Response stream failed",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "event": "stream_failed"
                },
                exc_info=True
            )
            raise

    async def upload_voice_file(
        self,
        user_id: int,
        file_bytes: bytes,
        duration: int,
        max_retries: int = 3
    ) -> dict:
        """
        Upload a voice file to the backend for transcription.

        Args:
            user_id: Telegram user ID
            file_bytes: Voice file bytes
            duration: Voice message duration in seconds
            max_retries: Maximum number of retry attempts

        Returns:
            API response with transcribed text and conversation_id

        Raises:
            Exception: If all retry attempts fail
        """
        await self._ensure_session()

        endpoint = f"{self.backend_url}/api/voice"

        # Prepare multipart form data
        form = aiohttp.FormData()
        form.add_field("user_id", str(user_id))
        form.add_field("duration", str(duration))
        form.add_field(
            "voice_file",
            file_bytes,
            filename="voice.ogg",
            content_type="audio/ogg"
        )

        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Uploading voice file to backend",
                    extra={
                        "user_id": user_id,
                        "file_size": len(file_bytes),
                        "duration": duration,
                        "attempt": attempt,
                        "endpoint": endpoint,
                        "event": "voice_upload_request"
                    }
                )

                async with self.session.post(endpoint, data=form) as response:
                    response.raise_for_status()
                    result = await response.json()

                    logger.info(
                        "Voice file uploaded successfully",
                        extra={
                            "user_id": user_id,
                            "conversation_id": result.get("conversation_id"),
                            "transcription_length": len(result.get("transcription", "")),
                            "status_code": response.status,
                            "event": "voice_upload_success"
                        }
                    )

                    return result

            except aiohttp.ClientError as e:
                wait_time = 2 ** (attempt - 1)  # Exponential backoff

                logger.error(
                    "Voice upload failed",
                    extra={
                        "user_id": user_id,
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "error": str(e),
                        "error_type": type(e).__name__,
                        "retry_after_seconds": wait_time if attempt < max_retries else None,
                        "event": "voice_upload_failed"
                    },
                    exc_info=True
                )

                if attempt < max_retries:
                    logger.info(
                        f"Retrying voice upload in {wait_time} seconds...",
                        extra={
                            "wait_time_seconds": wait_time,
                            "event": "retry_scheduled"
                        }
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        "Voice upload failed after all retries",
                        extra={
                            "user_id": user_id,
                            "total_attempts": max_retries,
                            "event": "voice_upload_exhausted"
                        }
                    )
                    raise


# Global backend client instance (initialized once, reused)
_backend_client: Optional[BackendClient] = None


def get_backend_client() -> BackendClient:
    """
    Get singleton backend client instance.

    Returns:
        BackendClient instance
    """
    global _backend_client

    if _backend_client is None:
        _backend_client = BackendClient()
        logger.info(
            "Backend client singleton created",
            extra={"event": "backend_client_singleton_created"}
        )

    return _backend_client


async def close_backend_client():
    """Close global backend client session."""
    global _backend_client

    if _backend_client is not None:
        await _backend_client.close()
        _backend_client = None
        logger.info(
            "Backend client singleton closed",
            extra={"event": "backend_client_singleton_closed"}
        )
