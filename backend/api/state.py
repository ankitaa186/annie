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
            title = f"New Chat"

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
