"""
State Management Module

Redis-based conversation state management for Annie chatbot.
Handles session creation, conversation history storage, and context building for LLM.

Redis Key Patterns:
- session:{user_id} -> Session data (JSON, TTL: 1 hour)
- conversation:{conversation_id} -> Message list (JSON array, TTL: 30 min)
"""

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from api.config import get_config
from api.logging import get_logger

logger = get_logger(__name__)


class StateError(Exception):
    """Base exception for state management errors."""
    pass


class RedisConnectionError(StateError):
    """Exception raised when Redis is unreachable."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class StateValidationError(StateError):
    """Exception raised when state data is invalid."""
    def __init__(self, message: str, field: Optional[str] = None):
        self.message = message
        self.field = field
        super().__init__(message)


class StateManager:
    """
    Async Redis-based state manager for conversation state.

    Features:
    - Session creation and management with TTL (1 hour)
    - Conversation history storage with Redis Lists (TTL: 30 min)
    - Context building for LLM with token limits (20 messages or 20k tokens)
    - Graceful degradation when Redis unavailable
    - Performance monitoring with duration tracking
    - Connection pooling with redis.asyncio

    Usage:
        async with StateManager() as state:
            session = await state.get_session(user_id)
            if not session:
                session = await state.create_session(user_id, "telegram")
    """

    # Configuration
    SESSION_TTL = 3600  # 1 hour in seconds
    CONVERSATION_TTL = 1800  # 30 minutes in seconds
    MAX_MESSAGES = 20  # Max messages for LLM context
    MAX_TOKENS = 20000  # Max tokens for LLM context (~4 chars per token)
    CHARS_PER_TOKEN = 4  # Simple token estimation heuristic

    def __init__(self, redis_client: Optional[redis.Redis] = None):
        """
        Initialize StateManager.

        Args:
            redis_client: Optional Redis client (for testing). If not provided,
                         creates new client from configuration.
        """
        if redis_client:
            self.redis_client = redis_client
            self._should_close = False  # Don't close if client was provided
        else:
            # Load configuration
            try:
                config = get_config()
                redis_host = config.get("REDIS_HOST", "redis")
                redis_port = int(config.get("REDIS_PORT", 6379))
            except Exception as e:
                logger.warning(
                    "Failed to load config, using default Redis settings",
                    extra={"error": str(e)}
                )
                redis_host = "redis"
                redis_port = 6379

            # Create Redis client
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=0,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self._should_close = True

        self._is_healthy = True

        logger.info(
            "StateManager initialized",
            extra={
                "redis_host": getattr(self.redis_client.connection_pool.connection_kwargs, 'host', 'unknown'),
                "redis_port": getattr(self.redis_client.connection_pool.connection_kwargs, 'port', 'unknown')
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        # Test connection
        try:
            await self.check_health()
        except RedisConnectionError:
            # Log but don't fail - graceful degradation
            logger.warning("Redis connection unavailable, operating in degraded mode")
            self._is_healthy = False

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._should_close and self.redis_client:
            await self.redis_client.close()
            logger.info("StateManager closed")

    async def check_health(self) -> bool:
        """
        Check Redis connection health.

        Returns:
            True if Redis is available, False otherwise

        Raises:
            RedisConnectionError: If Redis connection fails
        """
        start_time = time.time()

        try:
            await self.redis_client.ping()
            duration_ms = int((time.time() - start_time) * 1000)

            logger.debug(
                "Redis health check successful",
                extra={"duration_ms": duration_ms}
            )

            self._is_healthy = True
            return True

        except redis.exceptions.ConnectionError as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Redis connection failed",
                extra={
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            raise RedisConnectionError(
                "Redis server is unreachable",
                original_error=e
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Redis health check failed with unexpected error",
                extra={
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            raise RedisConnectionError(
                f"Redis health check failed: {str(e)}",
                original_error=e
            )

    async def create_session(self, user_id: str, platform: str) -> Dict[str, Any]:
        """
        Create new session for user.

        Args:
            user_id: Unique user identifier
            platform: Platform identifier (e.g., "telegram")

        Returns:
            Session dictionary with conversation_id, timestamps, etc.

        Raises:
            StateValidationError: If user_id or platform is invalid
            RedisConnectionError: If Redis operation fails (gracefully degraded)
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        if not platform or not platform.strip():
            raise StateValidationError("platform cannot be empty", field="platform")

        start_time = time.time()

        # Generate unique conversation ID
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        # Create session structure
        session = {
            "user_id": user_id,
            "platform": platform,
            "conversation_id": conversation_id,
            "created_at": now,
            "last_activity": now,
            "message_count": 0
        }

        # Store in Redis
        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, session not persisted (degraded mode)",
                extra={"user_id": user_id, "conversation_id": conversation_id}
            )
            return session

        try:
            key = f"session:{user_id}"
            await self.redis_client.setex(
                key,
                self.SESSION_TTL,
                json.dumps(session)
            )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Session created",
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "conversation_id": conversation_id,
                    "ttl": self.SESSION_TTL,
                    "duration_ms": duration_ms
                }
            )

            return session

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to create session in Redis, operating in degraded mode",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            # Graceful degradation: return session without persisting
            self._is_healthy = False
            return session

    async def get_session(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session for user.

        Args:
            user_id: Unique user identifier

        Returns:
            Session dictionary if exists and not expired, None otherwise
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot retrieve session (degraded mode)",
                extra={"user_id": user_id}
            )
            return None

        try:
            key = f"session:{user_id}"
            session_json = await self.redis_client.get(key)

            duration_ms = int((time.time() - start_time) * 1000)

            if not session_json:
                logger.debug(
                    "Session not found",
                    extra={"user_id": user_id, "duration_ms": duration_ms}
                )
                return None

            # Parse session
            session = json.loads(session_json)

            logger.debug(
                "Session retrieved",
                extra={
                    "user_id": user_id,
                    "conversation_id": session.get("conversation_id"),
                    "duration_ms": duration_ms
                }
            )

            return session

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to retrieve session from Redis",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            return None

        except json.JSONDecodeError as e:
            logger.error(
                "Failed to parse session JSON",
                extra={
                    "user_id": user_id,
                    "error": str(e)
                }
            )
            return None

    async def update_session_activity(self, user_id: str) -> None:
        """
        Update session last_activity timestamp and reset TTL.

        Args:
            user_id: Unique user identifier
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot update session (degraded mode)",
                extra={"user_id": user_id}
            )
            return

        try:
            # Get current session
            session = await self.get_session(user_id)
            if not session:
                logger.warning(
                    "Cannot update session activity: session not found",
                    extra={"user_id": user_id}
                )
                return

            # Update timestamps and message count
            session["last_activity"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            session["message_count"] = session.get("message_count", 0) + 1

            # Store updated session with reset TTL
            key = f"session:{user_id}"
            await self.redis_client.setex(
                key,
                self.SESSION_TTL,
                json.dumps(session)
            )

            duration_ms = int((time.time() - start_time) * 1000)

            logger.debug(
                "Session activity updated",
                extra={
                    "user_id": user_id,
                    "conversation_id": session.get("conversation_id"),
                    "message_count": session["message_count"],
                    "duration_ms": duration_ms
                }
            )

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to update session activity",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False

    async def add_message(
        self,
        conversation_id: str,
        message: Dict[str, Any]
    ) -> None:
        """
        Add message to conversation history.

        Args:
            conversation_id: Unique conversation identifier
            message: Message dictionary with role, content, timestamp, etc.
                     Expected fields: role, content
                     Optional fields: timestamp, tool_calls

        Raises:
            StateValidationError: If message format is invalid
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if not message.get("role"):
            raise StateValidationError("message must have 'role' field", field="role")

        if "content" not in message:
            raise StateValidationError("message must have 'content' field", field="content")

        start_time = time.time()

        # Add timestamp if not present
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, message not persisted (degraded mode)",
                extra={"conversation_id": conversation_id, "role": message["role"]}
            )
            return

        try:
            key = f"conversation:{conversation_id}"

            # Append message to list
            await self.redis_client.rpush(key, json.dumps(message))

            # Set TTL (only if key is new, won't override existing TTL)
            await self.redis_client.expire(key, self.CONVERSATION_TTL)

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Message added to conversation",
                extra={
                    "conversation_id": conversation_id,
                    "role": message["role"],
                    "content_length": len(message.get("content", "")),
                    "duration_ms": duration_ms
                }
            )

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to add message to conversation",
                extra={
                    "conversation_id": conversation_id,
                    "role": message["role"],
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False

    async def get_conversation_history(
        self,
        conversation_id: str,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Retrieve conversation history.

        Args:
            conversation_id: Unique conversation identifier
            limit: Maximum number of messages to retrieve (default: 20)

        Returns:
            List of messages in chronological order (oldest first)
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot retrieve conversation history (degraded mode)",
                extra={"conversation_id": conversation_id}
            )
            return []

        try:
            key = f"conversation:{conversation_id}"

            # Get last N messages using LRANGE with negative indices
            # LRANGE -limit -1 gets last 'limit' items
            messages_json = await self.redis_client.lrange(key, -limit, -1)

            duration_ms = int((time.time() - start_time) * 1000)

            if not messages_json:
                logger.debug(
                    "No conversation history found",
                    extra={"conversation_id": conversation_id, "duration_ms": duration_ms}
                )
                return []

            # Parse messages
            messages = []
            for msg_json in messages_json:
                try:
                    messages.append(json.loads(msg_json))
                except json.JSONDecodeError as e:
                    logger.error(
                        "Failed to parse message JSON",
                        extra={
                            "conversation_id": conversation_id,
                            "error": str(e)
                        }
                    )
                    continue

            logger.debug(
                "Conversation history retrieved",
                extra={
                    "conversation_id": conversation_id,
                    "message_count": len(messages),
                    "duration_ms": duration_ms
                }
            )

            return messages

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to retrieve conversation history",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            return []

    async def build_llm_context(
        self,
        conversation_id: str,
        system_message: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Build LLM context with token limits (20 messages or 20k tokens).

        Retrieves conversation history and applies limits:
        - Max 20 messages
        - Max 20,000 tokens (estimated at ~4 chars per token)
        - Truncates from beginning if needed (keeps most recent)
        - Always preserves system message if provided

        Args:
            conversation_id: Unique conversation identifier
            system_message: Optional system prompt to prepend

        Returns:
            List of messages for LLM (ready for chat_completion)
        """
        start_time = time.time()

        # Retrieve last 20 messages
        messages = await self.get_conversation_history(conversation_id, limit=self.MAX_MESSAGES)

        # Estimate token count
        def estimate_tokens(text: str) -> int:
            """Estimate tokens using simple heuristic (~4 chars per token)."""
            return len(text) // self.CHARS_PER_TOKEN

        # Calculate total tokens
        total_tokens = sum(estimate_tokens(msg.get("content", "")) for msg in messages)

        # Add system message if provided
        context_messages = []
        if system_message:
            context_messages.append({
                "role": "system",
                "content": system_message
            })
            total_tokens += estimate_tokens(system_message)

        # Truncate from beginning if exceeds token limit
        if total_tokens > self.MAX_TOKENS:
            logger.info(
                "Context exceeds token limit, truncating from beginning",
                extra={
                    "conversation_id": conversation_id,
                    "original_messages": len(messages),
                    "original_tokens": total_tokens,
                    "max_tokens": self.MAX_TOKENS
                }
            )

            # Keep removing oldest messages until under limit
            while total_tokens > self.MAX_TOKENS and messages:
                removed_msg = messages.pop(0)  # Remove from beginning
                total_tokens -= estimate_tokens(removed_msg.get("content", ""))

        # Add conversation messages
        context_messages.extend(messages)

        duration_ms = int((time.time() - start_time) * 1000)

        logger.info(
            "LLM context built",
            extra={
                "conversation_id": conversation_id,
                "message_count": len(context_messages),
                "estimated_tokens": total_tokens,
                "has_system_message": system_message is not None,
                "duration_ms": duration_ms
            }
        )

        return context_messages

    async def get_conversation_metadata(
        self,
        conversation_id: str
    ) -> Dict[str, Any]:
        """
        Get conversation metadata (message count, etc.).

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Dictionary with conversation metadata
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if not self._is_healthy:
            return {
                "conversation_id": conversation_id,
                "total_messages": 0,
                "status": "degraded"
            }

        try:
            key = f"conversation:{conversation_id}"
            total_messages = await self.redis_client.llen(key)

            return {
                "conversation_id": conversation_id,
                "total_messages": total_messages,
                "status": "active"
            }

        except (redis.exceptions.ConnectionError, redis.exceptions.TimeoutError) as e:
            logger.error(
                "Failed to get conversation metadata",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e)
                }
            )

            self._is_healthy = False
            return {
                "conversation_id": conversation_id,
                "total_messages": 0,
                "status": "degraded"
            }
