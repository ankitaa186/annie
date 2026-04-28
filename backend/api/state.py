"""
State Management Module

Redis-based conversation state management for Annie chatbot.
Handles conversation creation, history storage, and context building for LLM.

Redis Key Patterns:
- session:{user_id} -> Active session data (JSON, TTL: configurable, default 2 hours)
- conversations:{user_id} -> Sorted set of conversation IDs (score = updated_at timestamp)
- conversation:{conversation_id}:meta -> Conversation metadata hash (user_id, title, timestamps)
- conversation:{conversation_id} -> Message list (JSON array)
- conversation_mapping:{conversation_id} -> user_id (String) - Reverse lookup for memory tools

All keys share the same TTL (default 2 hours) and are refreshed on activity.
"""

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis
from redis import exceptions as redis_exceptions

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
    - Unified conversation management for Telegram and Web UI
    - Configurable TTL (default 2 hours, set via CONVERSATION_TTL_HOURS env var)
    - Conversation history storage with Redis Lists
    - Context building for LLM with token limits (40 messages or 20k tokens)
    - Graceful degradation when Redis unavailable
    - Performance monitoring with duration tracking
    - Connection pooling with redis.asyncio

    Usage:
        async with StateManager() as state:
            # Create or resume conversation
            conv = await state.create_conversation(user_id, platform="telegram")

            # Or resume latest conversation
            conv = await state.create_conversation(user_id, resume_latest=True)
    """

    # Configuration - TTL in seconds (default 2 hours, configurable via env)
    DEFAULT_TTL_HOURS = 2
    TTL_SECONDS = int(os.environ.get("CONVERSATION_TTL_HOURS", DEFAULT_TTL_HOURS)) * 3600

    # Legacy aliases for backward compatibility
    SESSION_TTL = TTL_SECONDS
    CONVERSATION_TTL = TTL_SECONDS
    CONVERSATION_META_TTL = TTL_SECONDS  # Unified - no longer 7 days

    MAX_MESSAGES = 40  # Max messages for LLM context
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
            try:
                await asyncio.wait_for(self.redis_client.aclose(), timeout=3.0)
            except (asyncio.TimeoutError, Exception) as e:
                logger.debug(f"Redis close: {e}")
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

        except redis_exceptions.ConnectionError as e:
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

    @observe(name="create_conversation", as_type="span")
    async def create_conversation(
        self,
        user_id: str,
        platform: str = "web",
        title: Optional[str] = None,
        resume_latest: bool = False
    ) -> Dict[str, Any]:
        """
        Create or resume a conversation for a user.

        This is the unified method for both Telegram and Web UI conversation management.
        It creates all necessary Redis structures:
        - Session data (session:{user_id})
        - Conversation metadata (conversation:{id}:meta)
        - Sorted set entry (conversations:{user_id})
        - Reverse mapping (conversation_mapping:{id})

        Args:
            user_id: Unique user identifier
            platform: Platform identifier ("telegram" or "web", default "web")
            title: Optional conversation title (auto-generated from first message if None)
            resume_latest: If True, resume the most recent conversation instead of creating new

        Returns:
            Session/conversation dictionary with conversation_id, timestamps, etc.

        Raises:
            StateValidationError: If user_id is invalid
            RedisConnectionError: If Redis operation fails (gracefully degraded)
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        start_time = time.time()

        # If resume_latest, try to find existing conversation
        if resume_latest and self._is_healthy:
            existing = await self._get_latest_conversation(user_id)
            if existing:
                # Update session to point to this conversation
                await self._update_session_conversation(user_id, existing, platform)
                logger.info(
                    "Resumed existing conversation",
                    extra={
                        "user_id": user_id,
                        "conversation_id": existing["conversation_id"],
                        "platform": platform
                    }
                )
                return existing

        # Generate unique conversation ID
        conversation_id = f"conv_{uuid.uuid4().hex[:16]}"
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat().replace("+00:00", "Z")
        now_timestamp = now.timestamp()

        # Auto-generate title if not provided
        if not title:
            title = "New Chat"

        # Create unified session/conversation structure
        session = {
            "user_id": user_id,
            "platform": platform,
            "conversation_id": conversation_id,
            "title": title,
            "created_at": now_iso,
            "updated_at": now_iso,
            "last_activity": now_iso,
            "message_count": 0
        }

        # Store in Redis
        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, conversation not persisted (degraded mode)",
                extra={"user_id": user_id, "conversation_id": conversation_id}
            )
            return session

        try:
            pipe = self.redis_client.pipeline()

            # 1. Session data (for active session tracking)
            session_key = f"session:{user_id}"
            pipe.setex(session_key, self.TTL_SECONDS, json.dumps(session))

            # 2. Conversation metadata hash
            meta_key = f"conversation:{conversation_id}:meta"
            pipe.hset(meta_key, mapping={
                "user_id": user_id,
                "title": title,
                "created_at": now_iso,
                "updated_at": now_iso
            })
            pipe.expire(meta_key, self.TTL_SECONDS)

            # 3. Add to user's conversation sorted set (for listing)
            conversations_key = f"conversations:{user_id}"
            pipe.zadd(conversations_key, {conversation_id: now_timestamp})
            pipe.expire(conversations_key, self.TTL_SECONDS)

            # 4. Reverse mapping for user_id lookup
            mapping_key = f"conversation_mapping:{conversation_id}"
            pipe.setex(mapping_key, self.TTL_SECONDS, user_id)

            await pipe.execute()

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation created",
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "conversation_id": conversation_id,
                    "title": title,
                    "ttl_hours": self.TTL_SECONDS // 3600,
                    "duration_ms": duration_ms
                }
            )

            return session

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to create conversation in Redis, operating in degraded mode",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            # Graceful degradation: return session without persisting
            self._is_healthy = False
            return session

    async def _get_latest_conversation(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get the most recent conversation for a user."""
        try:
            conversations_key = f"conversations:{user_id}"
            # Get the highest-scored (most recent) conversation
            result = await self.redis_client.zrevrange(conversations_key, 0, 0)
            if not result:
                return None

            conv_id = result[0]
            if isinstance(conv_id, bytes):
                conv_id = conv_id.decode("utf-8")

            # Get session data
            session = await self.get_session(user_id)
            if session and session.get("conversation_id") == conv_id:
                return session

            # Build session from metadata
            meta_key = f"conversation:{conv_id}:meta"
            meta = await self.redis_client.hgetall(meta_key)
            if not meta:
                return None

            # Handle bytes
            meta_dict = {}
            for k, v in meta.items():
                if isinstance(k, bytes):
                    k = k.decode("utf-8")
                if isinstance(v, bytes):
                    v = v.decode("utf-8")
                meta_dict[k] = v

            return {
                "user_id": user_id,
                "conversation_id": conv_id,
                "title": meta_dict.get("title", "Untitled"),
                "created_at": meta_dict.get("created_at"),
                "updated_at": meta_dict.get("updated_at"),
                "last_activity": meta_dict.get("updated_at"),
                "message_count": 0
            }

        except Exception as e:
            logger.warning(f"Failed to get latest conversation: {e}")
            return None

    async def _update_session_conversation(
        self,
        user_id: str,
        conversation: Dict[str, Any],
        platform: str
    ) -> None:
        """Update session to point to an existing conversation."""
        try:
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            session = {
                **conversation,
                "platform": platform,
                "last_activity": now_iso
            }
            session_key = f"session:{user_id}"
            await self.redis_client.setex(
                session_key,
                self.TTL_SECONDS,
                json.dumps(session)
            )
        except Exception as e:
            logger.warning(f"Failed to update session: {e}")

    async def create_session(self, user_id: str, platform: str) -> Dict[str, Any]:
        """
        Create new session for user.

        DEPRECATED: Use create_conversation() instead. This method is kept for
        backward compatibility and simply delegates to create_conversation().

        Args:
            user_id: Unique user identifier
            platform: Platform identifier (e.g., "telegram")

        Returns:
            Session dictionary with conversation_id, timestamps, etc.
        """
        return await self.create_conversation(user_id=user_id, platform=platform)

    async def resume_conversation(
        self,
        user_id: str,
        conversation_id: str,
        platform: str = "web"
    ) -> Optional[Dict[str, Any]]:
        """
        Resume a specific conversation by ID.

        Validates the user owns the conversation, then updates the session
        to point to it. Used when Web UI user clicks on an old conversation.

        Args:
            user_id: Unique user identifier
            conversation_id: Conversation ID to resume
            platform: Platform identifier (default "web")

        Returns:
            Session dictionary if successful, None if conversation not found or not owned

        Raises:
            StateValidationError: If user_id or conversation_id is invalid
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot resume conversation (degraded mode)",
                extra={"user_id": user_id, "conversation_id": conversation_id}
            )
            return None

        try:
            # Verify conversation exists and belongs to user
            meta_key = f"conversation:{conversation_id}:meta"
            meta = await self.redis_client.hgetall(meta_key)

            if not meta:
                logger.warning(
                    "Conversation not found for resume",
                    extra={"conversation_id": conversation_id, "user_id": user_id}
                )
                return None

            # Handle bytes
            owner_id = meta.get("user_id") or meta.get(b"user_id")
            if isinstance(owner_id, bytes):
                owner_id = owner_id.decode("utf-8")

            if owner_id != user_id:
                logger.warning(
                    "User does not own conversation",
                    extra={
                        "conversation_id": conversation_id,
                        "requesting_user": user_id,
                        "owner_user": owner_id
                    }
                )
                return None

            # Build session from metadata
            title = meta.get("title") or meta.get(b"title", b"Untitled")
            if isinstance(title, bytes):
                title = title.decode("utf-8")

            created_at = meta.get("created_at") or meta.get(b"created_at")
            if isinstance(created_at, bytes):
                created_at = created_at.decode("utf-8")

            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            session = {
                "user_id": user_id,
                "platform": platform,
                "conversation_id": conversation_id,
                "title": title,
                "created_at": created_at,
                "updated_at": now_iso,
                "last_activity": now_iso,
                "message_count": 0
            }

            # Update session to point to this conversation
            session_key = f"session:{user_id}"
            await self.redis_client.setex(
                session_key,
                self.TTL_SECONDS,
                json.dumps(session)
            )

            # Touch conversation to update its position in sorted set
            await self.touch_conversation(conversation_id)

            logger.info(
                "Conversation resumed",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "platform": platform
                }
            )

            return session

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            logger.error(
                "Failed to resume conversation",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "error": str(e)
                }
            )
            self._is_healthy = False
            return None

    async def create_session_only(
        self,
        user_id: str,
        platform: str = "web"
    ) -> Dict[str, Any]:
        """
        Create a session without a conversation.

        Used when user opens the app but hasn't started chatting yet.
        Session's conversation_id will be None until user sends first message
        or selects a conversation.

        Args:
            user_id: Unique user identifier
            platform: Platform identifier ("web" or "telegram")

        Returns:
            Session dictionary with conversation_id=None
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        session = {
            "user_id": user_id,
            "platform": platform,
            "conversation_id": None,  # No conversation yet
            "created_at": now_iso,
            "last_activity": now_iso,
            "message_count": 0
        }

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, session not persisted (degraded mode)",
                extra={"user_id": user_id}
            )
            return session

        try:
            session_key = f"session:{user_id}"
            await self.redis_client.setex(
                session_key,
                self.TTL_SECONDS,
                json.dumps(session)
            )

            logger.info(
                "Session created (no conversation)",
                extra={
                    "user_id": user_id,
                    "platform": platform,
                    "ttl_hours": self.TTL_SECONDS // 3600
                }
            )

            return session

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            logger.error(
                "Failed to create session",
                extra={"user_id": user_id, "error": str(e)}
            )
            self._is_healthy = False
            return session

    async def clear_current_conversation(
        self,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Clear the session's current conversation.

        Used when user wants to start fresh without selecting
        an existing conversation.

        Args:
            user_id: Unique user identifier

        Returns:
            Updated session dictionary or None if no session
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        if not self._is_healthy:
            return None

        try:
            # Get existing session
            session = await self.get_session(user_id)
            if not session:
                return None

            # Clear conversation_id
            now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            session["conversation_id"] = None
            session["last_activity"] = now_iso

            # Update in Redis
            session_key = f"session:{user_id}"
            await self.redis_client.setex(
                session_key,
                self.TTL_SECONDS,
                json.dumps(session)
            )

            logger.info(
                "Session conversation cleared",
                extra={"user_id": user_id}
            )

            return session

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            logger.error(
                "Failed to clear conversation",
                extra={"user_id": user_id, "error": str(e)}
            )
            self._is_healthy = False
            return None

    @observe(name="get_session", as_type="span")
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

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
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

            # Refresh conversation_mapping TTL
            conversation_id = session.get("conversation_id")
            if conversation_id:
                mapping_key = f"conversation_mapping:{conversation_id}"
                await self.redis_client.setex(
                    mapping_key,
                    self.CONVERSATION_TTL,
                    user_id
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

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
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

    @observe(name="add_message", as_type="span")
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

            # Refresh TTL on activity (resets TTL to full duration)
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

        except asyncio.CancelledError:
            # Client disconnected - this is normal, just re-raise to allow proper cancellation
            raise
        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to add message to conversation",
                extra={
                    "conversation_id": conversation_id,
                    "role": message["role"],
                    "error": str(e),
                    "error_type": type(e).__name__,
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
                    msg = json.loads(msg_json)
                    # Normalize tool_calls: ensure "type": "function" is present
                    # (older persisted messages may lack this field)
                    if msg.get("tool_calls"):
                        for tc in msg["tool_calls"]:
                            if "type" not in tc:
                                tc["type"] = "function"
                    messages.append(msg)
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

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
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

    # =========================================================================
    # Context Compaction Methods
    # =========================================================================

    @staticmethod
    def _create_tool_result_summary(content: str, tool_name: str = "") -> str:
        """
        Create a compact deterministic summary of a tool result (no LLM call).

        Parses JSON content and returns a short description. Falls back to
        a length-based summary if JSON parsing fails.

        Args:
            content: The tool result content string
            tool_name: Optional tool name for context

        Returns:
            Compact summary string
        """
        try:
            data = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            # Not JSON — summarize by length
            length = len(content) if content else 0
            return f"[Tool result: {length} chars]"

        # Handle error results
        if isinstance(data, dict):
            if data.get("status") == "error" or data.get("status") == "failed":
                error_msg = data.get("error", data.get("message", "unknown error"))
                return f"[Error: {str(error_msg)[:80]}]"

            if data.get("status") == "queued":
                return "[Queued for background processing]"

            # Handle common tool result patterns
            # Web search results
            if "results" in data and isinstance(data["results"], list):
                count = len(data["results"])
                return f"[Returned {count} results]"

            # Memory retrieval
            if "memories" in data and isinstance(data["memories"], list):
                count = len(data["memories"])
                return f"[Retrieved {count} memories]"

            if "memory_count" in data:
                return f"[Retrieved {data['memory_count']} memories]"

            # Profile data
            if "completeness" in data:
                return f"[Profile loaded ({data['completeness']}% complete)]"

            # Portfolio data
            if "holdings" in data and isinstance(data["holdings"], list):
                count = len(data["holdings"])
                return f"[Portfolio: {count} holdings]"

            # Home Assistant
            if "entities" in data and isinstance(data["entities"], list):
                count = len(data["entities"])
                return f"[{count} entities returned]"

            # Generic success with status
            if data.get("status") == "success":
                msg = data.get("message", "")
                if msg:
                    return f"[Success: {str(msg)[:80]}]"
                return "[Success]"

        # Fallback: describe by size
        content_len = len(content) if content else 0
        if tool_name:
            return f"[{tool_name} result: {content_len} chars]"
        return f"[Tool result: {content_len} chars]"

    @staticmethod
    def _drop_orphan_tool_results(
        messages: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Drop role=tool messages whose tool_call_id has no matching
        preceding assistant.tool_calls entry. Required when truncation
        cuts mid-pair: OpenAI rejects orphan tool results.
        """
        seen_tool_call_ids: set = set()
        out: List[Dict[str, Any]] = []
        for msg in messages:
            role = msg.get("role")
            if role == "assistant":
                for tc in msg.get("tool_calls") or []:
                    tcid = tc.get("id")
                    if tcid:
                        seen_tool_call_ids.add(tcid)
                out.append(msg)
            elif role == "tool":
                if msg.get("tool_call_id") in seen_tool_call_ids:
                    out.append(msg)
                # else: orphan — drop silently
            else:
                out.append(msg)
        return out

    @staticmethod
    def _prune_tool_results(
        messages: List[Dict[str, Any]],
        keep_recent_turns: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Replace verbose tool result content in older turns with compact summaries.

        Walks messages backwards, identifies turn boundaries (each role="user"
        message starts a new turn), and replaces tool result content in turns
        older than keep_recent_turns with compact summaries.

        Args:
            messages: List of conversation messages
            keep_recent_turns: Number of recent user turns to preserve fully

        Returns:
            New list of messages with older tool results pruned
        """
        if not messages:
            return messages

        # Identify turn boundaries by finding user messages (walking backwards)
        user_indices = []
        for i in range(len(messages) - 1, -1, -1):
            if messages[i].get("role") == "user":
                user_indices.append(i)

        # If fewer turns than threshold, nothing to prune
        if len(user_indices) <= keep_recent_turns:
            return messages

        # The cutoff index: messages before this index are in "old" turns
        # user_indices is in reverse order, so user_indices[keep_recent_turns - 1]
        # is the start of the oldest "recent" turn
        cutoff_index = user_indices[keep_recent_turns - 1]

        # Build pruned message list
        pruned = []
        for i, msg in enumerate(messages):
            if i < cutoff_index and msg.get("role") == "tool":
                # This is a tool result in an older turn — prune it
                tool_name = msg.get("tool_name", "")
                original_content = msg.get("content", "")
                summary = StateManager._create_tool_result_summary(
                    original_content, tool_name
                )
                pruned_msg = {
                    **msg,
                    "content": summary,
                    "_pruned": True
                }
                pruned.append(pruned_msg)
            elif i < cutoff_index and msg.get("is_tool_call"):
                # Tool call assistant message in older turn — keep but strip large arguments
                pruned_msg = dict(msg)
                if "tool_calls" in pruned_msg:
                    compact_calls = []
                    for tc in pruned_msg["tool_calls"]:
                        compact_calls.append({
                            "id": tc.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc.get("function", {}).get("name", ""),
                                "arguments": "{}"
                            }
                        })
                    pruned_msg["tool_calls"] = compact_calls
                    pruned_msg["_pruned"] = True
                pruned.append(pruned_msg)
            else:
                pruned.append(msg)

        return pruned

    # Summary staleness threshold: regenerate if this many new messages arrived
    SUMMARY_STALENESS_THRESHOLD = 5

    @staticmethod
    def _format_messages_for_summary(messages: List[Dict[str, Any]]) -> str:
        """
        Format messages into a readable transcript for the summarizer LLM.

        Truncates long messages and labels tool results with tool name.

        Args:
            messages: List of conversation messages to format

        Returns:
            Formatted transcript string
        """
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "tool":
                tool_name = msg.get("tool_name", "unknown_tool")
                # Truncate long tool results
                if len(content) > 10000:
                    content = content[:10000] + "... [truncated]"
                lines.append(f"[Tool: {tool_name}] {content}")
            elif role == "assistant" and msg.get("is_tool_call"):
                tool_calls = msg.get("tool_calls", [])
                tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
                lines.append(f"Assistant called tools: {', '.join(tool_names)}")
            elif role == "system":
                # Skip system messages from summary transcript
                continue
            else:
                # User or assistant text
                if role == "assistant" and len(content) > 20000:
                    content = content[:20000] + "... [truncated]"
                label = role.capitalize()
                lines.append(f"{label}: {content}")

        return "\n".join(lines)

    async def _generate_summary(
        self,
        messages: List[Dict[str, Any]],
        conversation_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a summary of messages using an LLM call.

        Uses SUMMARY_LLM_PROVIDER if configured, otherwise the default provider.
        Injects user profile into the prompt for personalized summaries.

        Args:
            messages: Messages to summarize
            conversation_id: Optional conversation ID for profile lookup

        Returns:
            Summary text string, or None on failure
        """
        try:
            from api.prompts import SUMMARY_SYSTEM_PROMPT, format_profile_for_prompt
            from api.llm_client import LLMClient
            from api.mcp_client import MCPClient
            from api.profile import ProfileManager

            config = get_config()
            provider_override = config.get("SUMMARY_LLM_MODEL")

            transcript = self._format_messages_for_summary(messages)
            if not transcript.strip():
                return None

            # Load user profile for context
            profile_section = ""
            if conversation_id:
                try:
                    user_id = await self.get_user_id_for_conversation(conversation_id)
                    if user_id:
                        profile_mgr = ProfileManager(redis_client=self.redis_client)
                        profile = await profile_mgr.fetch_profile(user_id)
                        if profile and profile.get("completeness", profile.get("completeness_pct", 0)) > 0:
                            profile_text = format_profile_for_prompt(profile)
                            if profile_text:
                                profile_section = f"\n\n## User Profile\n{profile_text}\n"
                except Exception as e:
                    logger.debug(
                        "Could not load profile for summary (continuing without)",
                        extra={"conversation_id": conversation_id, "error": str(e)}
                    )

            system_prompt = SUMMARY_SYSTEM_PROMPT
            if profile_section:
                system_prompt += profile_section

            llm_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Summarize this conversation:\n\n{transcript}"}
            ]

            async with LLMClient(provider_override=provider_override) as client, MCPClient() as mcp_client:
                # Load tools so the summarizer can call them if needed
                tools = None
                try:
                    mcp_tools = await mcp_client.list_tools()
                    if mcp_tools:
                        tools = client.convert_mcp_tools_to_functions(mcp_tools)
                except Exception as e:
                    logger.debug(
                        "Could not load tools for summary (continuing without)",
                        extra={"error": str(e)}
                    )

                response = await client.chat_completion(llm_messages, tools=tools, mcp_client=mcp_client)

            # Extract content from response
            choices = response.get("choices", [])
            if choices:
                summary = choices[0].get("message", {}).get("content", "")
                if summary:
                    logger.info(
                        "Summary generated",
                        extra={
                            "input_messages": len(messages),
                            "summary_length": len(summary)
                        }
                    )
                    return summary

            return None

        except Exception as e:
            logger.warning(
                "Failed to generate summary, will fall back to truncation",
                extra={"error": str(e), "error_type": type(e).__name__}
            )
            return None

    async def get_or_create_summary(
        self,
        conversation_id: str,
        messages_to_summarize: List[Dict[str, Any]],
        current_message_count: int
    ) -> Optional[str]:
        """
        Get cached summary or generate a new one.

        Checks Redis for a cached summary. If it exists and is fresh
        (within SUMMARY_STALENESS_THRESHOLD messages), returns it.
        Otherwise generates a new summary and caches it.

        Args:
            conversation_id: Conversation identifier
            messages_to_summarize: Messages that would be dropped by truncation
            current_message_count: Current total message count in conversation

        Returns:
            Summary text, or None if generation fails
        """
        summary_key = f"conversation:{conversation_id}:summary"

        # Check for cached summary
        if self._is_healthy:
            try:
                cached = await self.redis_client.get(summary_key)
                if cached:
                    cached_data = json.loads(cached)
                    msg_count_at_gen = cached_data.get("message_count_at_generation", 0)
                    # If the cached summary is still fresh enough, use it
                    if (current_message_count - msg_count_at_gen) < self.SUMMARY_STALENESS_THRESHOLD:
                        logger.debug(
                            "Using cached summary",
                            extra={
                                "conversation_id": conversation_id,
                                "generated_at_count": msg_count_at_gen,
                                "current_count": current_message_count
                            }
                        )
                        return cached_data.get("text")
            except Exception as e:
                logger.warning(
                    "Failed to read cached summary",
                    extra={"conversation_id": conversation_id, "error": str(e)}
                )

        # Generate new summary
        summary_text = await self._generate_summary(messages_to_summarize, conversation_id)
        if not summary_text:
            return None

        # Cache the summary
        if self._is_healthy:
            try:
                summary_data = json.dumps({
                    "text": summary_text,
                    "message_count_at_generation": current_message_count,
                    "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
                })
                await self.redis_client.setex(
                    summary_key,
                    self.TTL_SECONDS,  # Same TTL as conversation
                    summary_data
                )
            except Exception as e:
                logger.warning(
                    "Failed to cache summary (returning summary anyway)",
                    extra={"conversation_id": conversation_id, "error": str(e)}
                )

        # Fire-and-forget: echo summary to agentic-memories
        asyncio.ensure_future(
            self._echo_summary_to_memories(conversation_id, summary_text, messages_to_summarize)
        )

        return summary_text

    @staticmethod
    def _extract_long_term_content(summary_text: str) -> Optional[str]:
        """
        Extract content worth persisting to long-term memory from a summary.

        Extracts the "What was on their mind" (emotional context) and
        "What matters going forward" (decisions, preferences, action items)
        sections. Skips casual conversations with nothing noteworthy.

        Args:
            summary_text: Full summary text with structured sections

        Returns:
            Combined sections text, or None if nothing worth persisting
        """
        if not summary_text:
            return None

        sections_to_keep = ["## What was on their mind", "## What matters going forward"]
        extracted = []

        for header in sections_to_keep:
            start = summary_text.find(header)
            if start == -1:
                continue
            content_after = summary_text[start:]
            next_section = content_after.find("\n## ", len(header))
            section_text = (content_after[:next_section] if next_section != -1 else content_after).strip()

            body = section_text[len(header):].strip()
            if body and "nothing specific" not in body.lower() and "casual conversation" not in body.lower():
                extracted.append(section_text)

        if not extracted:
            return None

        return "\n\n".join(extracted)

    @staticmethod
    def _parse_summary_metadata(
        summary_text: str,
        conversation_id: str,
        user_id: str,
        user_name: Optional[str],
        message_count: int
    ) -> Dict[str, Any]:
        """
        Parse LLM-generated metadata from summary and merge with system fields.

        Extracts the JSON block from the ## Metadata section produced by the
        summarizer LLM, then merges with known system fields (user_id, user_name,
        conversation_id, timestamp, message_count).

        Args:
            summary_text: Full summary text containing ## Metadata section
            conversation_id: Conversation identifier
            user_id: User identifier
            user_name: User's display name (from profile), or None
            message_count: Number of messages in the conversation

        Returns:
            Merged metadata dictionary with system + LLM-generated fields
        """
        from zoneinfo import ZoneInfo
        pst_now = datetime.now(ZoneInfo("America/Los_Angeles"))
        metadata: Dict[str, Any] = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "source": "session_summary",
            "timestamp": pst_now.isoformat(),
            "message_count": message_count,
        }
        if user_name:
            metadata["user_name"] = user_name

        # Parse the JSON block from ## Metadata section
        try:
            meta_start = summary_text.find("## Metadata")
            if meta_start != -1:
                json_start = summary_text.find("```json", meta_start)
                json_end = summary_text.find("```", json_start + 7) if json_start != -1 else -1
                if json_start != -1 and json_end != -1:
                    json_str = summary_text[json_start + 7:json_end].strip()
                    llm_metadata = json.loads(json_str)
                    # Merge LLM-generated fields (ensure lists stay as lists)
                    for key in ("mood", "category", "has_unresolved"):
                        if key in llm_metadata:
                            metadata[key] = llm_metadata[key]
                    # List fields — defensive: parse if LLM returned a string
                    for key in ("topics", "people_mentioned"):
                        val = llm_metadata.get(key)
                        if val is None:
                            continue
                        if isinstance(val, str):
                            try:
                                val = json.loads(val)
                            except (json.JSONDecodeError, ValueError):
                                val = [val]
                        if isinstance(val, list):
                            metadata[key] = val
        except (json.JSONDecodeError, Exception) as e:
            logger.debug(
                "Could not parse LLM metadata (continuing without)",
                extra={"error": str(e)}
            )

        return metadata

    # Importance by category — decisions/planning are more valuable than casual chat
    _IMPORTANCE_BY_CATEGORY: Dict[str, float] = {
        "decision-making": 0.95,
        "planning": 0.9,
        "advice": 0.85,
        "troubleshooting": 0.85,
        "research": 0.8,
        "venting": 0.7,
        "casual": 0.5,
    }

    # Valence by mood — rough mapping for emotional memory routing
    _VALENCE_BY_MOOD: Dict[str, float] = {
        "excited": 0.8,
        "happy": 0.7,
        "curious": 0.5,
        "neutral": 0.0,
        "stressed": -0.4,
        "frustrated": -0.6,
        "anxious": -0.5,
        "sad": -0.7,
        "angry": -0.8,
    }

    async def _echo_summary_to_memories(
        self,
        conversation_id: str,
        summary_text: str,
        messages: Optional[List[Dict[str, Any]]] = None
    ) -> None:
        """
        Fire-and-forget: send episodic memory to agentic-memories for recall.

        Extracts the "What was on their mind" and "What matters going forward"
        sections for persistence, along with LLM-generated metadata (topics,
        mood, category) and system fields (user_id, user_name, conversation_id).

        Uses the full DirectMemoryRequest schema:
        - layer=episodic (conversations are events, not static facts)
        - persona_tags for filterable tags
        - event_timestamp to route into episodic_memories table
        - emotional_state/valence from mood for emotional_memories table
        - participants from people_mentioned
        - importance scaled by category

        Args:
            conversation_id: Conversation identifier
            summary_text: The full structured summary text
            messages: Optional list of conversation messages (for message_count)
        """
        try:
            from api.memory_client import MemoryClient

            # Look up user_id for this conversation
            user_id = await self.get_user_id_for_conversation(conversation_id)
            if not user_id:
                logger.debug(
                    "No user_id for conversation, skipping memory echo",
                    extra={"conversation_id": conversation_id}
                )
                return

            # Extract long-term content (mind + forward sections)
            content = self._extract_long_term_content(summary_text)
            if not content:
                logger.debug(
                    "No long-term content to persist (casual conversation)",
                    extra={"conversation_id": conversation_id}
                )
                return

            # Load user_name from profile cache (non-blocking)
            user_name = None
            try:
                from api.profile import ProfileManager
                profile_mgr = ProfileManager(redis_client=self.redis_client)
                profile = await profile_mgr.load_profile_from_cache(user_id)
                if profile:
                    user_name = profile.get("basics", {}).get("name")
            except Exception:
                pass  # non-blocking

            # Build metadata with LLM-generated + system fields
            metadata = self._parse_summary_metadata(
                summary_text, conversation_id, user_id, user_name, len(messages or [])
            )

            # Build deduplicated persona_tags from metadata
            tag_set: dict[str, None] = {}  # ordered set via dict keys
            tag_set["conversation_summary"] = None
            if metadata.get("has_unresolved"):
                tag_set["has_unresolved"] = None
            if metadata.get("category"):
                tag_set[metadata["category"]] = None
            for topic in metadata.get("topics", []):
                tag_set[topic] = None
            persona_tags = list(tag_set)[:10]  # API max is 10

            # Dynamic importance based on category
            category = metadata.get("category", "casual")
            importance = self._IMPORTANCE_BY_CATEGORY.get(category, 0.7)
            if metadata.get("has_unresolved"):
                importance = min(importance + 0.1, 1.0)

            # Emotional fields from mood
            mood = metadata.get("mood")
            emotional_state = mood if mood and mood != "neutral" else None
            valence = self._VALENCE_BY_MOOD.get(mood, None) if mood else None

            # Participants from people_mentioned
            people = metadata.get("people_mentioned", [])
            participants = people if people else None

            # Event timestamp (ISO8601) — routes to episodic_memories table
            event_timestamp = metadata.get("timestamp")

            # Store via direct API with full typed fields
            async with MemoryClient() as memory_client:
                result = await memory_client.store_direct(
                    user_id=user_id,
                    content=content,
                    layer="episodic",
                    memory_type="explicit",
                    persona_tags=persona_tags,
                    metadata=metadata,
                    importance=importance,
                    confidence=0.9,
                    event_timestamp=event_timestamp,
                    participants=participants,
                    event_type="conversation",
                    emotional_state=emotional_state,
                    valence=valence,
                )
            logger.info(
                "Summary persisted to agentic-memories",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "memory_id": result.get("memory_id") or result.get("id"),
                    "content_length": len(content),
                    "full_summary_length": len(summary_text),
                    "layer": "episodic",
                    "persona_tags": persona_tags,
                    "importance": importance,
                    "emotional_state": emotional_state,
                }
            )
        except Exception as e:
            logger.warning(
                "Failed to echo summary to agentic-memories (non-blocking)",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                    "error_type": type(e).__name__
                }
            )

    @observe(name="build_llm_context", as_type="span")
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

        # Retrieve conversation history
        messages = await self.get_conversation_history(conversation_id, limit=self.MAX_MESSAGES)

        # Prune verbose tool results in older turns to save tokens
        messages = self._prune_tool_results(messages)

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

        # Story 22.1: Always-inject cached rolling summary.
        # The `conversation:{id}:summary` cache is maintained by the refresh
        # logic above and by the overflow path below, but before 22.1 it was
        # ONLY rendered into the prompt on overflow — a rare path, because
        # `_prune_tool_results` keeps total_tokens well under MAX_TOKENS most
        # turns. That meant on normal turns the summary sat unused in Redis
        # while the LLM kept re-asking about things from earlier in the
        # session. Inject it eagerly as a 2nd system message whenever present
        # and we're NOT going to take the overflow branch (which injects its
        # own copy and would double-render).
        summary_already_injected = False
        if self._is_healthy and total_tokens <= self.MAX_TOKENS:
            try:
                summary_key = f"conversation:{conversation_id}:summary"
                cached = await self.redis_client.get(summary_key)
                if cached:
                    try:
                        summary_text = json.loads(cached).get("text")
                    except (json.JSONDecodeError, TypeError):
                        summary_text = None
                    if summary_text:
                        summary_msg = {
                            "role": "system",
                            "content": f"[Earlier conversation summary]\n{summary_text}",
                        }
                        context_messages.append(summary_msg)
                        total_tokens += estimate_tokens(summary_msg["content"])
                        summary_already_injected = True
                        logger.debug(
                            "Cached rolling summary injected (always-inject path)",
                            extra={
                                "conversation_id": conversation_id,
                                "summary_chars": len(summary_text),
                            },
                        )
            except Exception as e:
                logger.warning(
                    "Always-inject summary read failed (non-blocking)",
                    extra={
                        "conversation_id": conversation_id,
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        # Truncate from beginning if exceeds token limit
        if total_tokens > self.MAX_TOKENS:
            logger.info(
                "Context exceeds token limit, attempting summarization",
                extra={
                    "conversation_id": conversation_id,
                    "original_messages": len(messages),
                    "original_tokens": total_tokens,
                    "max_tokens": self.MAX_TOKENS
                }
            )

            # Identify which messages would be dropped
            messages_to_drop = []
            temp_tokens = total_tokens
            temp_messages = list(messages)
            while temp_tokens > self.MAX_TOKENS and temp_messages:
                removed = temp_messages.pop(0)
                temp_tokens -= estimate_tokens(removed.get("content", ""))
                messages_to_drop.append(removed)

            # Try to summarize the dropped messages
            summary_text = None
            if messages_to_drop:
                try:
                    summary_text = await self.get_or_create_summary(
                        conversation_id,
                        messages_to_drop,
                        len(messages)
                    )
                except Exception as e:
                    logger.warning(
                        "Summary generation failed, falling back to truncation",
                        extra={
                            "conversation_id": conversation_id,
                            "error": str(e)
                        }
                    )

            if summary_text:
                # Insert summary as system message after the main system message.
                # Story 22.1: the always-inject path above may have already
                # appended a copy from the Redis cache. If so, replace it with
                # this fresh one (which may be regenerated here) rather than
                # stacking a second `[Earlier conversation summary]` block.
                summary_msg = {
                    "role": "system",
                    "content": f"[Earlier conversation summary]\n{summary_text}"
                }
                if summary_already_injected:
                    # Find the existing injected summary_msg (system message
                    # whose content starts with the summary marker) and
                    # overwrite it in place.
                    for i in range(len(context_messages) - 1, -1, -1):
                        m = context_messages[i]
                        if (
                            m.get("role") == "system"
                            and isinstance(m.get("content"), str)
                            and m["content"].startswith("[Earlier conversation summary]")
                        ):
                            context_messages[i] = summary_msg
                            break
                    else:
                        context_messages.append(summary_msg)
                else:
                    context_messages.append(summary_msg)
                total_tokens = (
                    estimate_tokens(system_message or "")
                    + estimate_tokens(summary_msg["content"])
                    + sum(estimate_tokens(m.get("content", "")) for m in temp_messages)
                )
                messages = temp_messages
            else:
                # Fallback: plain truncation (drop oldest)
                while total_tokens > self.MAX_TOKENS and messages:
                    removed_msg = messages.pop(0)
                    total_tokens -= estimate_tokens(removed_msg.get("content", ""))

        # Drop any role=tool messages whose matching assistant.tool_calls was
        # truncated away. OpenAI rejects orphan tool results with:
        # "messages with role 'tool' must be a response to a preceeding
        # message with 'tool_calls'." Assistant tool_call messages have tiny
        # content tokens, so the truncator above can drop the assistant turn
        # but stop on the next message — leaving an orphan tool at the head.
        messages = self._drop_orphan_tool_results(messages)

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

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
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

    async def get_user_id_for_conversation(
        self,
        conversation_id: str
    ) -> Optional[str]:
        """
        Get user_id associated with a conversation.

        This uses the reverse mapping stored in Redis to look up
        which user owns a conversation. Used by the stream endpoint
        to inject user_id into system message for tool calls.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            user_id string if found, None otherwise
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot retrieve user_id (degraded mode)",
                extra={"conversation_id": conversation_id}
            )
            return None

        try:
            mapping_key = f"conversation_mapping:{conversation_id}"
            user_id = await self.redis_client.get(mapping_key)

            if user_id:
                # Redis returns bytes, decode to string
                user_id = user_id.decode("utf-8") if isinstance(user_id, bytes) else user_id

                logger.debug(
                    "User ID retrieved for conversation",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id
                    }
                )
                return user_id
            else:
                logger.warning(
                    "No user_id mapping found for conversation",
                    extra={"conversation_id": conversation_id}
                )
                return None

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            logger.error(
                "Failed to retrieve user_id mapping",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e)
                }
            )

            self._is_healthy = False
            return None

    # =========================================================================
    # Conversation Management Methods (Epic 20, Story 20.14)
    # =========================================================================
    #
    # Redis Key Patterns for conversations:
    # - conversations:{user_id}  -> Sorted set (score = updated_at timestamp)
    # - conversation:{conv_id}:meta  -> Hash (user_id, title, created_at, updated_at)
    # - conversation:{conv_id}  -> List (messages, existing pattern)
    # - conversation_mapping:{conv_id}  -> String (user_id, existing pattern)

    # Conversation metadata TTL (7 days) - longer than session TTL for persistence
    CONVERSATION_META_TTL = 7 * 24 * 3600  # 7 days in seconds

    async def list_conversations(
        self,
        user_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        List conversations for a user, sorted by updated_at (most recent first).

        Args:
            user_id: Unique user identifier
            limit: Maximum number of conversations to return (default: 50)
            offset: Number of conversations to skip (default: 0)

        Returns:
            List of conversation metadata dictionaries

        Redis Keys Used:
            - conversations:{user_id} (sorted set, score = updated_at timestamp)
            - conversation:{conv_id}:meta (hash for each conversation)
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot list conversations (degraded mode)",
                extra={"user_id": user_id}
            )
            return []

        try:
            # Get conversation IDs from sorted set (reverse order = most recent first)
            conversations_key = f"conversations:{user_id}"
            conv_ids = await self.redis_client.zrevrange(
                conversations_key,
                offset,
                offset + limit - 1
            )

            if not conv_ids:
                logger.debug(
                    "No conversations found for user",
                    extra={"user_id": user_id}
                )
                return []

            # Fetch metadata for each conversation
            conversations = []
            for conv_id in conv_ids:
                # Handle bytes if needed
                if isinstance(conv_id, bytes):
                    conv_id = conv_id.decode("utf-8")

                meta_key = f"conversation:{conv_id}:meta"
                meta = await self.redis_client.hgetall(meta_key)

                if meta:
                    # Get message count and last message preview
                    messages_key = f"conversation:{conv_id}"
                    message_count = await self.redis_client.llen(messages_key)

                    # Get last message for preview
                    last_message_preview = None
                    if message_count > 0:
                        last_msg_json = await self.redis_client.lindex(messages_key, -1)
                        if last_msg_json:
                            try:
                                if isinstance(last_msg_json, bytes):
                                    last_msg_json = last_msg_json.decode("utf-8")
                                last_msg = json.loads(last_msg_json)
                                content = last_msg.get("content", "")
                                # Truncate to 100 chars
                                last_message_preview = content[:100] + "..." if len(content) > 100 else content
                            except (json.JSONDecodeError, TypeError):
                                pass

                    # Handle bytes in meta dict
                    meta_dict = {}
                    for k, v in meta.items():
                        if isinstance(k, bytes):
                            k = k.decode("utf-8")
                        if isinstance(v, bytes):
                            v = v.decode("utf-8")
                        meta_dict[k] = v

                    conversations.append({
                        "id": conv_id,
                        "title": meta_dict.get("title", "Untitled"),
                        "created_at": meta_dict.get("created_at"),
                        "updated_at": meta_dict.get("updated_at"),
                        "message_count": message_count,
                        "last_message_preview": last_message_preview
                    })

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversations listed",
                extra={
                    "user_id": user_id,
                    "count": len(conversations),
                    "limit": limit,
                    "offset": offset,
                    "duration_ms": duration_ms
                }
            )

            return conversations

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to list conversations",
                extra={
                    "user_id": user_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            return []

    async def get_conversations_count(self, user_id: str) -> int:
        """
        Get total number of conversations for a user.

        Args:
            user_id: Unique user identifier

        Returns:
            Total conversation count
        """
        if not user_id or not user_id.strip():
            raise StateValidationError("user_id cannot be empty", field="user_id")

        if not self._is_healthy:
            return 0

        try:
            conversations_key = f"conversations:{user_id}"
            count = await self.redis_client.zcard(conversations_key)
            return count or 0

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            logger.error(
                "Failed to get conversations count",
                extra={"user_id": user_id, "error": str(e)}
            )
            self._is_healthy = False
            return 0

    async def get_conversation_detail(
        self,
        conversation_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        Get detailed conversation metadata.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Conversation metadata dictionary or None if not found
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot get conversation detail (degraded mode)",
                extra={"conversation_id": conversation_id}
            )
            return None

        try:
            meta_key = f"conversation:{conversation_id}:meta"
            meta = await self.redis_client.hgetall(meta_key)

            if not meta:
                logger.debug(
                    "Conversation not found",
                    extra={"conversation_id": conversation_id}
                )
                return None

            # Handle bytes in meta dict
            meta_dict = {}
            for k, v in meta.items():
                if isinstance(k, bytes):
                    k = k.decode("utf-8")
                if isinstance(v, bytes):
                    v = v.decode("utf-8")
                meta_dict[k] = v

            return {
                "id": conversation_id,
                "title": meta_dict.get("title", "Untitled"),
                "user_id": meta_dict.get("user_id"),
                "created_at": meta_dict.get("created_at"),
                "updated_at": meta_dict.get("updated_at")
            }

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            logger.error(
                "Failed to get conversation detail",
                extra={"conversation_id": conversation_id, "error": str(e)}
            )
            self._is_healthy = False
            return None

    async def update_conversation_title(
        self,
        conversation_id: str,
        title: str
    ) -> Optional[Dict[str, Any]]:
        """
        Update conversation title.

        Args:
            conversation_id: Unique conversation identifier
            title: New title for the conversation

        Returns:
            Updated conversation metadata or None if not found
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if not title or not title.strip():
            raise StateValidationError("title cannot be empty", field="title")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot update conversation (degraded mode)",
                extra={"conversation_id": conversation_id}
            )
            return None

        try:
            meta_key = f"conversation:{conversation_id}:meta"

            # Check if conversation exists
            exists = await self.redis_client.exists(meta_key)
            if not exists:
                logger.debug(
                    "Conversation not found for update",
                    extra={"conversation_id": conversation_id}
                )
                return None

            # Update title and updated_at
            now = datetime.now(timezone.utc)
            now_iso = now.isoformat().replace("+00:00", "Z")
            now_timestamp = now.timestamp()

            pipe = self.redis_client.pipeline()
            pipe.hset(meta_key, mapping={"title": title, "updated_at": now_iso})
            pipe.expire(meta_key, self.CONVERSATION_META_TTL)

            # Get user_id to update sorted set score
            user_id = await self.redis_client.hget(meta_key, "user_id")
            if user_id:
                if isinstance(user_id, bytes):
                    user_id = user_id.decode("utf-8")
                conversations_key = f"conversations:{user_id}"
                pipe.zadd(conversations_key, {conversation_id: now_timestamp})

            await pipe.execute()

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation title updated",
                extra={
                    "conversation_id": conversation_id,
                    "title": title,
                    "duration_ms": duration_ms
                }
            )

            return {
                "id": conversation_id,
                "title": title,
                "updated_at": now_iso
            }

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to update conversation title",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            return None

    async def delete_conversation(
        self,
        conversation_id: str
    ) -> bool:
        """
        Delete a conversation and all its data.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            True if deleted successfully, False if not found or error
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot delete conversation (degraded mode)",
                extra={"conversation_id": conversation_id}
            )
            return False

        try:
            # Get user_id from metadata to remove from sorted set
            meta_key = f"conversation:{conversation_id}:meta"
            user_id = await self.redis_client.hget(meta_key, "user_id")

            if not user_id:
                logger.debug(
                    "Conversation not found for deletion",
                    extra={"conversation_id": conversation_id}
                )
                return False

            if isinstance(user_id, bytes):
                user_id = user_id.decode("utf-8")

            # Delete all conversation data
            pipe = self.redis_client.pipeline()

            # Remove from user's conversation list
            conversations_key = f"conversations:{user_id}"
            pipe.zrem(conversations_key, conversation_id)

            # Delete metadata
            pipe.delete(meta_key)

            # Delete messages
            messages_key = f"conversation:{conversation_id}"
            pipe.delete(messages_key)

            # Delete reverse mapping
            mapping_key = f"conversation_mapping:{conversation_id}"
            pipe.delete(mapping_key)

            await pipe.execute()

            duration_ms = int((time.time() - start_time) * 1000)

            logger.info(
                "Conversation deleted",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "duration_ms": duration_ms
                }
            )

            return True

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to delete conversation",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            return False

    async def get_paginated_messages(
        self,
        conversation_id: str,
        page: int = 1,
        limit: int = 50
    ) -> Dict[str, Any]:
        """
        Get paginated messages for a conversation.

        Args:
            conversation_id: Unique conversation identifier
            page: Page number (1-indexed)
            limit: Messages per page (default: 50)

        Returns:
            Dictionary with messages list and pagination info
        """
        if not conversation_id or not conversation_id.strip():
            raise StateValidationError("conversation_id cannot be empty", field="conversation_id")

        if page < 1:
            raise StateValidationError("page must be >= 1", field="page")

        if limit < 1 or limit > 100:
            raise StateValidationError("limit must be between 1 and 100", field="limit")

        start_time = time.time()

        if not self._is_healthy:
            logger.warning(
                "Redis unavailable, cannot get paginated messages (degraded mode)",
                extra={"conversation_id": conversation_id}
            )
            return {
                "messages": [],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": 0,
                    "has_more": False
                }
            }

        try:
            messages_key = f"conversation:{conversation_id}"

            # Get total count
            total = await self.redis_client.llen(messages_key)

            # Calculate offset
            offset = (page - 1) * limit

            # Get messages (LRANGE is 0-indexed)
            messages_json = await self.redis_client.lrange(
                messages_key,
                offset,
                offset + limit - 1
            )

            # Parse messages
            messages = []
            for msg_json in messages_json:
                try:
                    if isinstance(msg_json, bytes):
                        msg_json = msg_json.decode("utf-8")
                    messages.append(json.loads(msg_json))
                except (json.JSONDecodeError, TypeError) as e:
                    logger.error(
                        "Failed to parse message JSON",
                        extra={
                            "conversation_id": conversation_id,
                            "error": str(e)
                        }
                    )
                    continue

            has_more = (offset + limit) < total

            duration_ms = int((time.time() - start_time) * 1000)

            logger.debug(
                "Paginated messages retrieved",
                extra={
                    "conversation_id": conversation_id,
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "returned": len(messages),
                    "duration_ms": duration_ms
                }
            )

            return {
                "messages": messages,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "has_more": has_more
                }
            }

        except (redis_exceptions.ConnectionError, redis_exceptions.TimeoutError) as e:
            duration_ms = int((time.time() - start_time) * 1000)

            logger.error(
                "Failed to get paginated messages",
                extra={
                    "conversation_id": conversation_id,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )

            self._is_healthy = False
            return {
                "messages": [],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": 0,
                    "has_more": False
                }
            }

    async def touch_conversation(self, conversation_id: str) -> None:
        """
        Update conversation's updated_at timestamp (touch).

        Called when messages are added to update the sort order.

        Args:
            conversation_id: Unique conversation identifier
        """
        if not conversation_id or not conversation_id.strip():
            return

        if not self._is_healthy:
            return

        try:
            meta_key = f"conversation:{conversation_id}:meta"

            # Check if this is a managed conversation (has metadata)
            exists = await self.redis_client.exists(meta_key)
            if not exists:
                # This is likely a legacy conversation without metadata
                return

            now = datetime.now(timezone.utc)
            now_iso = now.isoformat().replace("+00:00", "Z")
            now_timestamp = now.timestamp()

            # Get user_id
            user_id = await self.redis_client.hget(meta_key, "user_id")
            if not user_id:
                return

            if isinstance(user_id, bytes):
                user_id = user_id.decode("utf-8")

            # Update metadata and sorted set
            pipe = self.redis_client.pipeline()
            pipe.hset(meta_key, "updated_at", now_iso)

            conversations_key = f"conversations:{user_id}"
            pipe.zadd(conversations_key, {conversation_id: now_timestamp})

            await pipe.execute()

            logger.debug(
                "Conversation touched",
                extra={"conversation_id": conversation_id}
            )

        except Exception as e:
            # Silent failure - touching is non-critical
            logger.warning(
                "Failed to touch conversation",
                extra={"conversation_id": conversation_id, "error": str(e)}
            )
