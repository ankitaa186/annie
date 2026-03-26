"""
Memory Manager Module

Orchestrates conversation storage operations with agentic-memories service.
Provides graceful degradation with Redis fallback queue and retry logic.
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


from api.config import get_config
from api.logging import get_logger
from api.memory_client import MemoryClient, MemoryNetworkError, MemoryAPIError
from api.state import StateManager

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


class MemoryManager:
    """
    Memory Manager for conversation storage.

    Features:
    - Direct conversation history storage (agentic-memories handles extraction)
    - Graceful degradation with Redis fallback queue
    - Background retry worker for failed storage operations
    - Circuit breaker pattern for repeated failures
    """

    # Configuration constants
    MAX_MESSAGES_FOR_STORAGE = 50  # Limit conversation history size
    FALLBACK_QUEUE_TTL = 86400  # 24 hours
    RETRY_INTERVAL = 300  # 5 minutes
    CIRCUIT_BREAKER_THRESHOLD = 5  # Failures before circuit opens
    CIRCUIT_BREAKER_TIMEOUT = 900  # 15 minutes

    # Flush worker constants (Story 12-5)
    FLUSH_CHECK_INTERVAL = 300   # 5 minutes between flush checks
    INACTIVE_THRESHOLD = 600     # 10 minutes of inactivity before flush
    FLUSH_MARKER_TTL = 3600      # 1 hour TTL for "already flushed" marker

    # Distributed lock constants (for multi-worker environments)
    RETRY_WORKER_LOCK_KEY = "worker_lock:retry_memories"
    FLUSH_WORKER_LOCK_KEY = "worker_lock:flush_sessions"
    WORKER_LOCK_TTL = 120        # 2 minutes max lock duration

    def __init__(self):
        """Initialize Memory Manager."""
        self.config = get_config()
        self._circuit_breaker_failures = 0
        self._circuit_breaker_opened_at = None

        logger.info("Memory Manager initialized")

    @observe(name="memory_storage", as_type="trace")
    async def store_conversation_memory(
        self,
        user_id: str,
        conversation_id: str,
        conversation_history: List[Dict[str, str]],
        platform: str = "telegram"
    ) -> bool:
        """
        Store conversation turn in agentic-memories service.

        Note: Runs as background task (separate trace). Link to conversation via metadata.

        Typically receives only the most recent turn (2 messages: user + assistant)
        for incremental memory storage. The service will automatically extract
        memories from the conversation turn.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            conversation_history: List of message dicts with role, content (typically 2 messages)
            platform: Platform identifier (default: telegram)

        Returns:
            bool: True if stored successfully, False if queued for retry
        """
        start_time = time.time()

        # Limit conversation history size (safety check, usually only 2 messages)
        if len(conversation_history) > self.MAX_MESSAGES_FOR_STORAGE:
            logger.warning(
                f"Conversation history too long ({len(conversation_history)} messages), "
                f"truncating to last {self.MAX_MESSAGES_FOR_STORAGE}"
            )
            conversation_history = conversation_history[-self.MAX_MESSAGES_FOR_STORAGE:]

        # Check circuit breaker
        if self._is_circuit_breaker_open():
            logger.warning(
                "Circuit breaker is open, queueing memory for retry",
                extra={"user_id": user_id, "conversation_id": conversation_id}
            )
            await self._queue_memory_for_retry(user_id, conversation_id, conversation_history, platform)
            return False

        try:
            # Build metadata
            metadata = {
                "platform": platform,
                "conversation_id": conversation_id
            }

            # Attempt to store in agentic-memories
            async with MemoryClient() as memory_client:
                result = await memory_client.store_memory(user_id, conversation_history, metadata)

            duration_ms = int((time.time() - start_time) * 1000)

            # Success - reset circuit breaker
            self._circuit_breaker_failures = 0
            self._circuit_breaker_opened_at = None

            logger.info(
                "Conversation memory stored successfully (fire-and-forget response logged)",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "memories_created": result.get("memories_created", 0),
                    "memory_ids": result.get("memory_ids", []),
                    "duration_ms": duration_ms,
                    "full_response": result  # Log complete response for debugging
                }
            )
            return True

        except (MemoryNetworkError, MemoryAPIError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # Increment circuit breaker failures
            self._circuit_breaker_failures += 1
            if self._circuit_breaker_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
                self._circuit_breaker_opened_at = time.time()
                logger.error(
                    f"Circuit breaker opened after {self._circuit_breaker_failures} failures",
                    extra={"user_id": user_id, "conversation_id": conversation_id}
                )

            logger.error(
                f"Failed to store conversation memory, queueing for retry: {str(e)}",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms
                }
            )

            # Queue for retry
            await self._queue_memory_for_retry(user_id, conversation_id, conversation_history, platform)
            return False

    def _is_circuit_breaker_open(self) -> bool:
        """
        Check if circuit breaker is currently open.

        Returns:
            bool: True if circuit breaker is open, False otherwise
        """
        if self._circuit_breaker_opened_at is None:
            return False

        elapsed = time.time() - self._circuit_breaker_opened_at

        if elapsed >= self.CIRCUIT_BREAKER_TIMEOUT:
            # Timeout elapsed, close circuit breaker
            logger.info("Circuit breaker timeout elapsed, closing circuit breaker")
            self._circuit_breaker_failures = 0
            self._circuit_breaker_opened_at = None
            return False

        return True

    async def _queue_memory_for_retry(
        self,
        user_id: str,
        conversation_id: str,
        conversation_history: List[Dict[str, str]],
        platform: str
    ):
        """
        Queue conversation for retry in Redis fallback queue.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            conversation_history: List of message dicts
            platform: Platform identifier
        """
        queue_key = f"memory_queue:{user_id}"

        # Build queue payload
        queue_payload = {
            "user_id": user_id,
            "conversation_id": conversation_id,
            "history": conversation_history,
            "platform": platform,
            "queued_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            async with StateManager() as state_manager:
                # Push to Redis list (right push)
                await state_manager.redis_client.rpush(queue_key, json.dumps(queue_payload))

                # Set TTL on queue
                await state_manager.redis_client.expire(queue_key, self.FALLBACK_QUEUE_TTL)

            logger.info(
                "Conversation queued for retry",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "queue_key": queue_key
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to queue conversation for retry: {str(e)}",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id
                }
            )

    async def _queue_message_for_retry(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        flush: bool = False
    ):
        """
        Queue a single message for retry in Redis fallback queue.

        Used when orchestrator streaming fails. Messages are retried by the
        retry worker which calls stream_message() again.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            role: Message role
            content: Message content
            message_id: Optional message ID
            flush: Whether to flush on retry
        """
        queue_key = f"message_queue:{user_id}"

        # Build queue payload
        queue_payload = {
            "type": "orchestrator_message",  # Distinguish from old format
            "user_id": user_id,
            "conversation_id": conversation_id,
            "role": role,
            "content": content,
            "message_id": message_id,
            "flush": flush,
            "queued_at": datetime.now(timezone.utc).isoformat()
        }

        try:
            async with StateManager() as state_manager:
                # Push to Redis list (right push)
                await state_manager.redis_client.rpush(queue_key, json.dumps(queue_payload))

                # Set TTL on queue
                await state_manager.redis_client.expire(queue_key, self.FALLBACK_QUEUE_TTL)

            logger.info(
                "Message queued for retry",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "queue_key": queue_key
                }
            )

        except Exception as e:
            logger.error(
                f"Failed to queue message for retry: {str(e)}",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role
                }
            )

    async def retry_queued_memories(self):
        """
        Background worker to retry queued messages (runs every 5 minutes).

        Scans message_queue:* keys and attempts to stream queued messages
        through the orchestrator.
        """
        start_time = time.time()

        logger.info("Starting retry worker for queued messages")

        try:
            async with StateManager() as state_manager:
                cursor = 0
                total_retried = 0
                total_success = 0

                # Scan for message queues (orchestrator messages)
                while True:
                    cursor, keys = await state_manager.redis_client.scan(
                        cursor=cursor,
                        match="message_queue:*",
                        count=100
                    )

                    for queue_key in keys:
                        # Handle bytes or string keys
                        if isinstance(queue_key, bytes):
                            queue_key_str = queue_key.decode('utf-8')
                        else:
                            queue_key_str = queue_key

                        queue_length = await state_manager.redis_client.llen(queue_key)

                        logger.debug(
                            f"Processing queue: {queue_key_str} ({queue_length} items)"
                        )

                        # Process each queued message
                        for _ in range(queue_length):
                            # Pop from left (FIFO)
                            queue_item_json = await state_manager.redis_client.lpop(queue_key)
                            if not queue_item_json:
                                break

                            # Handle bytes
                            if isinstance(queue_item_json, bytes):
                                queue_item_json = queue_item_json.decode('utf-8')

                            try:
                                queue_item = json.loads(queue_item_json)
                                total_retried += 1

                                # Extract data for orchestrator message
                                user_id = queue_item["user_id"]
                                conversation_id = queue_item["conversation_id"]
                                role = queue_item["role"]
                                content = queue_item["content"]
                                message_id = queue_item.get("message_id")
                                flush = queue_item.get("flush", False)

                                # Attempt to stream through orchestrator
                                async with MemoryClient() as memory_client:
                                    result = await memory_client.stream_message(
                                        conversation_id=conversation_id,
                                        role=role,
                                        content=content,
                                        user_id=user_id,
                                        message_id=message_id,
                                        flush=flush,
                                    )

                                total_success += 1
                                logger.info(
                                    "Queued message streamed successfully on retry",
                                    extra={
                                        "user_id": user_id,
                                        "conversation_id": conversation_id,
                                        "role": role,
                                        "injections": len(result.get("injections", []))
                                    }
                                )

                            except (MemoryNetworkError, MemoryAPIError) as e:
                                logger.warning(
                                    f"Retry failed for queued message: {str(e)}",
                                    extra={
                                        "user_id": queue_item.get("user_id"),
                                        "conversation_id": queue_item.get("conversation_id"),
                                        "role": queue_item.get("role")
                                    }
                                )
                                # Push back to end of queue (right push)
                                await state_manager.redis_client.rpush(
                                    queue_key,
                                    queue_item_json if isinstance(queue_item_json, bytes) else queue_item_json.encode()
                                )

                            except Exception as e:
                                logger.error(
                                    f"Unexpected error processing queued message: {str(e)}",
                                    extra={
                                        "user_id": queue_item.get("user_id"),
                                        "conversation_id": queue_item.get("conversation_id"),
                                        "role": queue_item.get("role")
                                    },
                                    exc_info=True
                                )
                                # Push back to queue to avoid losing data
                                await state_manager.redis_client.rpush(
                                    queue_key,
                                    queue_item_json if isinstance(queue_item_json, bytes) else queue_item_json.encode()
                                )

                    if cursor == 0:
                        break

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Retry worker completed",
                extra={
                    "total_retried": total_retried,
                    "total_success": total_success,
                    "duration_ms": duration_ms
                }
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Retry worker failed: {str(e)}",
                extra={"duration_ms": duration_ms},
                exc_info=True
            )

    async def start_retry_worker(self):
        """
        Start background retry worker task.

        Runs indefinitely, processing queued memories every RETRY_INTERVAL seconds.
        Uses Redis Lock object for safe distributed locking with atomic release.
        """
        worker_id = f"worker-{os.getpid()}"
        logger.info(
            f"Starting memory retry worker (interval: {self.RETRY_INTERVAL}s, id: {worker_id})"
        )

        while True:
            try:
                await asyncio.sleep(self.RETRY_INTERVAL)

                # Use Redis Lock object for safe distributed locking
                # - blocking=False: Don't wait if lock is held
                # - timeout: Lock auto-expires if holder crashes
                # - Lock.release() uses Lua script to atomically verify ownership
                async with StateManager() as state_manager:
                    lock = state_manager.redis_client.lock(
                        self.RETRY_WORKER_LOCK_KEY,
                        timeout=self.WORKER_LOCK_TTL,
                        blocking=False
                    )

                    acquired = await lock.acquire()
                    if not acquired:
                        logger.debug(
                            "Retry worker skipped: another worker holds lock",
                            extra={"worker_id": worker_id}
                        )
                        continue

                    logger.debug(
                        "Retry worker lock acquired",
                        extra={"worker_id": worker_id}
                    )

                    try:
                        await self.retry_queued_memories()
                    finally:
                        try:
                            await lock.release()
                            logger.debug(
                                "Retry worker lock released",
                                extra={"worker_id": worker_id}
                            )
                        except Exception as release_err:
                            # Lock may have expired - that's OK, just log it
                            logger.debug(
                                "Retry worker lock release skipped (may have expired)",
                                extra={"worker_id": worker_id, "error": str(release_err)}
                            )

            except Exception as e:
                logger.error(
                    f"Error in retry worker loop: {str(e)}",
                    exc_info=True
                )
                # Continue running even if one iteration fails
                await asyncio.sleep(self.RETRY_INTERVAL)

    async def flush_stale_sessions(self):
        """
        Background worker to flush orchestrator buffers for inactive sessions.

        Scans all session:* keys and triggers flush for sessions inactive > 10 minutes.
        This ensures single-message conversations or final messages are not lost.

        Story 12-5: Flush Orchestrator Buffer on Session End
        """
        start_time = time.time()
        logger.info("Starting stale session flush check")

        try:
            async with StateManager() as state_manager:
                cursor = 0
                total_checked = 0
                total_flushed = 0

                while True:
                    cursor, keys = await state_manager.redis_client.scan(
                        cursor=cursor,
                        match="session:*",
                        count=100
                    )

                    for session_key in keys:
                        # Handle bytes or string keys
                        if isinstance(session_key, bytes):
                            session_key_str = session_key.decode('utf-8')
                        else:
                            session_key_str = session_key
                        user_id = session_key_str.replace("session:", "")

                        # Get session data
                        session_json = await state_manager.redis_client.get(session_key)
                        if not session_json:
                            continue

                        # Parse session
                        if isinstance(session_json, bytes):
                            session_json = session_json.decode('utf-8')
                        session = json.loads(session_json)
                        conversation_id = session.get("conversation_id")
                        last_activity = session.get("last_activity")

                        if not conversation_id or not last_activity:
                            continue

                        total_checked += 1

                        # Check if already flushed
                        flush_marker_key = f"flushed:{conversation_id}"
                        already_flushed = await state_manager.redis_client.exists(flush_marker_key)
                        if already_flushed:
                            continue

                        # Calculate inactivity
                        try:
                            last_activity_dt = datetime.fromisoformat(
                                last_activity.replace('Z', '+00:00')
                            )
                        except ValueError:
                            logger.warning(
                                f"Invalid last_activity timestamp: {last_activity}",
                                extra={"user_id": user_id, "conversation_id": conversation_id}
                            )
                            continue

                        now = datetime.now(timezone.utc)
                        inactive_seconds = (now - last_activity_dt).total_seconds()

                        if inactive_seconds >= self.INACTIVE_THRESHOLD:
                            # Trigger flush
                            logger.info(
                                "Flushing stale session",
                                extra={
                                    "user_id": user_id,
                                    "conversation_id": conversation_id,
                                    "inactive_seconds": int(inactive_seconds)
                                }
                            )

                            try:
                                # Call stream_conversation_message with flush=True
                                # Empty content is fine - we just want to trigger the flush
                                await self.stream_conversation_message(
                                    user_id=user_id,
                                    conversation_id=conversation_id,
                                    role="system",
                                    content="",
                                    flush=True
                                )

                                # Generate summary and echo to agentic-memories before expiry
                                try:
                                    conversation_history = await state_manager.get_conversation_history(
                                        conversation_id, limit=state_manager.MAX_MESSAGES
                                    )
                                    # Count only user messages (not tool calls/results)
                                    user_message_count = sum(
                                        1 for msg in conversation_history if msg.get("role") == "user"
                                    )
                                    if user_message_count >= 3:  # Skip single-question conversations
                                        summary_text = await state_manager.get_or_create_summary(
                                            conversation_id,
                                            conversation_history,
                                            len(conversation_history)
                                        )
                                        if summary_text:
                                            logger.info(
                                                "Summary generated on session flush",
                                                extra={
                                                    "conversation_id": conversation_id,
                                                    "user_id": user_id,
                                                    "user_message_count": user_message_count,
                                                    "total_messages": len(conversation_history),
                                                    "summary_length": len(summary_text)
                                                }
                                            )
                                            # Queue summary notification for Telegram delivery
                                            # The proactive-worker drains this outbox each poll cycle
                                            try:
                                                from zoneinfo import ZoneInfo
                                                pst_now = datetime.now(ZoneInfo("America/Los_Angeles"))
                                                outbox_payload = json.dumps({
                                                    "user_id": user_id,
                                                    "message": "<i>Session summarized and saved to memory.</i>\n",
                                                    "trigger_id": f"session_flush:{conversation_id}",
                                                    "is_html": True,
                                                    "metadata": {
                                                        "conversation_id": conversation_id,
                                                        "user_id": user_id,
                                                        "timestamp": pst_now.strftime("%Y-%m-%d %I:%M:%S %p %Z"),
                                                    },
                                                })
                                                await state_manager.redis_client.rpush("telegram:outbox", outbox_payload)
                                                logger.info(
                                                    "Queued summary notification for Telegram delivery",
                                                    extra={"conversation_id": conversation_id, "user_id": user_id}
                                                )
                                            except Exception as notify_err:
                                                logger.warning(
                                                    "Failed to queue summary notification (non-blocking)",
                                                    extra={
                                                        "conversation_id": conversation_id,
                                                        "error": str(notify_err)
                                                    }
                                                )
                                except Exception as e:
                                    logger.warning(
                                        "Failed to generate summary on session flush (non-blocking)",
                                        extra={
                                            "conversation_id": conversation_id,
                                            "error": str(e)
                                        }
                                    )

                                # Mark as flushed to avoid double-flush
                                await state_manager.redis_client.setex(
                                    flush_marker_key,
                                    self.FLUSH_MARKER_TTL,
                                    "1"
                                )
                                total_flushed += 1

                            except Exception as e:
                                logger.warning(
                                    f"Failed to flush stale session: {str(e)}",
                                    extra={
                                        "user_id": user_id,
                                        "conversation_id": conversation_id
                                    }
                                )

                    if cursor == 0:
                        break

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "Stale session flush check completed",
                extra={
                    "total_checked": total_checked,
                    "total_flushed": total_flushed,
                    "duration_ms": duration_ms
                }
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                f"Stale session flush check failed: {str(e)}",
                extra={"duration_ms": duration_ms},
                exc_info=True
            )

    async def start_flush_worker(self):
        """
        Start background flush worker task.

        Runs indefinitely, flushing stale sessions every FLUSH_CHECK_INTERVAL seconds.
        Uses Redis Lock object for safe distributed locking with atomic release.
        This is a FALLBACK mechanism - most conversations have 2+ messages and batch normally.

        Story 12-5: Flush Orchestrator Buffer on Session End
        """
        worker_id = f"worker-{os.getpid()}"
        logger.info(
            f"Starting stale session flush worker (interval: {self.FLUSH_CHECK_INTERVAL}s, "
            f"threshold: {self.INACTIVE_THRESHOLD}s, id: {worker_id})"
        )

        while True:
            try:
                await asyncio.sleep(self.FLUSH_CHECK_INTERVAL)

                # Use Redis Lock object for safe distributed locking
                # - blocking=False: Don't wait if lock is held
                # - timeout: Lock auto-expires if holder crashes
                # - Lock.release() uses Lua script to atomically verify ownership
                async with StateManager() as state_manager:
                    lock = state_manager.redis_client.lock(
                        self.FLUSH_WORKER_LOCK_KEY,
                        timeout=self.WORKER_LOCK_TTL,
                        blocking=False
                    )

                    acquired = await lock.acquire()
                    if not acquired:
                        logger.debug(
                            "Flush worker skipped: another worker holds lock",
                            extra={"worker_id": worker_id}
                        )
                        continue

                    logger.debug(
                        "Flush worker lock acquired",
                        extra={"worker_id": worker_id}
                    )

                    try:
                        await self.flush_stale_sessions()
                    finally:
                        try:
                            await lock.release()
                            logger.debug(
                                "Flush worker lock released",
                                extra={"worker_id": worker_id}
                            )
                        except Exception as release_err:
                            # Lock may have expired - that's OK, just log it
                            logger.debug(
                                "Flush worker lock release skipped (may have expired)",
                                extra={"worker_id": worker_id, "error": str(release_err)}
                            )

            except Exception as e:
                logger.error(
                    f"Error in flush worker loop: {str(e)}",
                    exc_info=True
                )
                # Continue running even if one iteration fails
                await asyncio.sleep(self.FLUSH_CHECK_INTERVAL)

    @observe(name="stream_conversation_message", as_type="span")
    async def stream_conversation_message(
        self,
        user_id: str,
        conversation_id: str,
        role: str,
        content: str,
        message_id: Optional[str] = None,
        flush: bool = False,
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Stream a single message through the orchestrator for batched storage.

        The orchestrator batches messages (2-8) before LLM extraction, providing
        ~70% cost savings compared to direct /v1/store calls. Returns any relevant
        memories that should be injected into context.

        Args:
            user_id: User identifier
            conversation_id: Conversation identifier
            role: Message role ("user", "assistant", "system", "tool")
            content: Message content
            message_id: Optional message ID for tracking
            flush: Force immediate flush of batched messages (default: False)

        Returns:
            List of memory injections if successful, None on failure (graceful degradation)
        """
        start_time = time.time()

        # Check circuit breaker
        if self._is_circuit_breaker_open():
            logger.warning(
                "Circuit breaker is open, queueing message for retry",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role
                }
            )
            # Queue for retry instead of dropping
            await self._queue_message_for_retry(
                user_id=user_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                message_id=message_id,
                flush=flush
            )
            return None

        try:
            async with MemoryClient() as memory_client:
                result = await memory_client.stream_message(
                    conversation_id=conversation_id,
                    role=role,
                    content=content,
                    user_id=user_id,
                    message_id=message_id,
                    flush=flush,
                )

            duration_ms = int((time.time() - start_time) * 1000)

            # Success - reset circuit breaker
            self._circuit_breaker_failures = 0
            self._circuit_breaker_opened_at = None

            injections = result.get("injections", [])

            logger.info(
                "Message streamed through orchestrator",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "injections_count": len(injections),
                    "duration_ms": duration_ms,
                    "flush": flush
                }
            )

            return injections

        except (MemoryNetworkError, MemoryAPIError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            # Increment circuit breaker failures
            self._circuit_breaker_failures += 1
            if self._circuit_breaker_failures >= self.CIRCUIT_BREAKER_THRESHOLD:
                self._circuit_breaker_opened_at = time.time()
                logger.error(
                    f"Circuit breaker opened after {self._circuit_breaker_failures} failures",
                    extra={"user_id": user_id, "conversation_id": conversation_id}
                )

            logger.warning(
                f"Failed to stream message through orchestrator, queueing for retry: {str(e)}",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms
                }
            )

            # Queue for retry instead of losing the message
            await self._queue_message_for_retry(
                user_id=user_id,
                conversation_id=conversation_id,
                role=role,
                content=content,
                message_id=message_id,
                flush=flush
            )

            return None

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                f"Unexpected error streaming message through orchestrator: {str(e)}",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "duration_ms": duration_ms
                },
                exc_info=True
            )

            # Graceful degradation
            return None

    @observe(name="format_memories", as_type="span")
    async def format_memories_for_llm(self, memories: List[Dict[str, Any]]) -> str:
        """
        Format retrieved memories into LLM-friendly context string.

        Langfuse @observe() decorator automatically traces:
        - Input: memory count
        - Output: formatted context length, token estimate
        - Duration

        This method transforms memory objects from agentic-memories into a readable
        context string that can be injected into the LLM system prompt. The format
        emphasizes decisions, preferences, outcomes, and temporal context.

        Args:
            memories: List of memory objects from retrieve_memories, each containing:
                - conversation_summary: Brief summary of the conversation
                - decisions: List of decisions made
                - preferences: User preferences (risk_tolerance, priorities, constraints)
                - topics: List of relevant topics
                - timestamp: When the conversation occurred
                - relevance_score: Semantic similarity score (0.0-1.0)

        Returns:
            str: Formatted context string for LLM prompt injection
                 Returns message indicating no history if memories is empty

        Example output:
            ```
            Here is the user's past decision history (ordered by relevance):

            1. User asked for stock investment advice for AAPL...
               Decisions made:
               - Buy 10 shares of AAPL
                 Outcome: Gained 15% in 2 weeks
               Risk tolerance: moderate
               Priorities: long-term growth, dividend income
               (From conversation on 2025-11-10)

            Use this history to personalize your recommendations and reference past decisions when relevant.
            ```
        """
        from api.prompts import MEMORY_CONTEXT_HEADER, MEMORY_CONTEXT_FOOTER, NO_MEMORY_CONTEXT

        if not memories:
            return NO_MEMORY_CONTEXT

        context_parts = [MEMORY_CONTEXT_HEADER]

        for i, memory in enumerate(memories, 1):
            # Get metadata
            metadata = memory.get('metadata', {})

            # Add memory content (agentic-memories uses "content" field)
            content = memory.get('content', memory.get('conversation_summary', memory.get('summary', '')))
            if content:
                context_parts.append(f"\n{i}. {content}")
            else:
                context_parts.append(f"\n{i}. [No content available]")

            # Add memory layer and type info
            layer = memory.get('layer', '')
            mem_type = memory.get('type', '')
            if layer or mem_type:
                context_parts.append(f"   Type: {mem_type or 'unknown'} ({layer or 'unknown'} term)")

            # Add decisions (if available in old format)
            decisions = memory.get('decisions', metadata.get('decisions', []))
            if decisions:
                context_parts.append("   Decisions made:")
                for decision in decisions:
                    if isinstance(decision, dict):
                        decision_text = decision.get('decision', '')
                        if decision_text:
                            context_parts.append(f"   - {decision_text}")

                            # Add outcome if available
                            outcome = decision.get('outcome', '')
                            if outcome:
                                context_parts.append(f"     Outcome: {outcome}")

                            # Add reasoning if available
                            reasoning = decision.get('reasoning', '')
                            if reasoning:
                                context_parts.append(f"     Reasoning: {reasoning}")
                    elif isinstance(decision, str):
                        # Handle simple string decisions
                        context_parts.append(f"   - {decision}")

            # Add preferences (if available in old format)
            preferences = memory.get('preferences', metadata.get('preferences', {}))
            if preferences:
                # Risk tolerance
                risk_tolerance = preferences.get('risk_tolerance', '')
                if risk_tolerance:
                    context_parts.append(f"   Risk tolerance: {risk_tolerance}")

                # Priorities
                priorities = preferences.get('priorities', [])
                if priorities:
                    if isinstance(priorities, list):
                        context_parts.append(f"   Priorities: {', '.join(priorities)}")
                    else:
                        context_parts.append(f"   Priorities: {priorities}")

                # Constraints
                constraints = preferences.get('constraints', [])
                if constraints:
                    if isinstance(constraints, list):
                        context_parts.append(f"   Constraints: {', '.join(constraints)}")
                    else:
                        context_parts.append(f"   Constraints: {constraints}")

            # Add tags (from metadata)
            tags = metadata.get('tags', memory.get('topics', []))
            if tags:
                # Tags might be JSON string, parse it
                if isinstance(tags, str):
                    try:
                        import json
                        tags = json.loads(tags)
                    except (ValueError, TypeError):
                        pass
                if isinstance(tags, list):
                    context_parts.append(f"   Tags: {', '.join(tags)}")
                else:
                    context_parts.append(f"   Tags: {tags}")

            # Add relevance score (agentic-memories uses "score" field)
            relevance_score = memory.get('score', memory.get('relevance_score', 0.0))
            if relevance_score > 0:
                # Convert to percentage for readability
                relevance_pct = int(relevance_score * 100)
                context_parts.append(f"   Relevance: {relevance_pct}%")

            # Add timestamp for temporal context (check metadata too)
            timestamp = metadata.get('timestamp', memory.get('timestamp', ''))
            if timestamp:
                # Try to format timestamp nicely
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    formatted_date = dt.strftime("%Y-%m-%d")
                    context_parts.append(f"   (From conversation on {formatted_date})")
                except Exception:
                    # Fallback to raw timestamp
                    context_parts.append(f"   (From conversation on {timestamp})")

        # Add instruction for LLM to use this context
        context_parts.append(f"\n{MEMORY_CONTEXT_FOOTER}")

        formatted_context = "\n".join(context_parts)

        # Log token estimate (rough approximation: 1 token ≈ 4 characters)
        estimated_tokens = len(formatted_context) // 4
        logger.debug(
            "Formatted memories for LLM",
            extra={
                "memory_count": len(memories),
                "estimated_tokens": estimated_tokens,
                "exceeds_limit": estimated_tokens > 2000
            }
        )

        if estimated_tokens > 2000:
            logger.warning(
                f"Formatted memory context exceeds 2000 token target ({estimated_tokens} tokens)",
                extra={"memory_count": len(memories), "estimated_tokens": estimated_tokens}
            )

        return formatted_context
