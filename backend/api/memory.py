"""
Memory Manager Module

Orchestrates conversation storage operations with agentic-memories service.
Provides graceful degradation with Redis fallback queue and retry logic.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import redis.asyncio as redis

from api.config import get_config
from api.logging import get_logger
from api.memory_client import MemoryClient, MemoryNetworkError, MemoryAPIError
from api.state import StateManager
from api.status import emit_status

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

    async def retry_queued_memories(self):
        """
        Background worker to retry queued memories (runs every 5 minutes).

        Scans all memory_queue:* keys and attempts to store queued conversations.
        """
        start_time = time.time()

        logger.info("Starting retry worker for queued memories")

        try:
            async with StateManager() as state_manager:
                queue_pattern = "memory_queue:*"
                cursor = 0
                total_retried = 0
                total_success = 0

                # Scan for all memory queue keys
                while True:
                    cursor, keys = await state_manager.redis_client.scan(
                        cursor=cursor,
                        match=queue_pattern,
                        count=100
                    )

                    for queue_key in keys:
                        user_id = queue_key.decode('utf-8').replace("memory_queue:", "")
                        queue_length = await state_manager.redis_client.llen(queue_key)

                        logger.debug(
                            f"Processing queue: {queue_key.decode('utf-8')} ({queue_length} items)"
                        )

                        # Process each queued memory
                        for _ in range(queue_length):
                            # Pop from left (FIFO)
                            queue_item_json = await state_manager.redis_client.lpop(queue_key)
                            if not queue_item_json:
                                break

                            try:
                                queue_item = json.loads(queue_item_json)
                                total_retried += 1

                                # Extract data
                                user_id = queue_item["user_id"]
                                conversation_id = queue_item["conversation_id"]
                                history = queue_item["history"]
                                platform = queue_item.get("platform", "telegram")

                                # Build metadata
                                metadata = {
                                    "platform": platform,
                                    "conversation_id": conversation_id
                                }

                                # Attempt to store
                                async with MemoryClient() as memory_client:
                                    result = await memory_client.store_memory(user_id, history, metadata)

                                total_success += 1
                                logger.info(
                                    "Queued conversation stored successfully on retry",
                                    extra={
                                        "user_id": user_id,
                                        "conversation_id": conversation_id,
                                        "memories_created": result.get("memories_created", 0)
                                    }
                                )

                            except (MemoryNetworkError, MemoryAPIError) as e:
                                logger.warning(
                                    f"Retry failed for queued conversation: {str(e)}",
                                    extra={
                                        "user_id": queue_item.get("user_id"),
                                        "conversation_id": queue_item.get("conversation_id")
                                    }
                                )
                                # Push back to end of queue (right push)
                                await state_manager.redis_client.rpush(queue_key, queue_item_json)

                            except Exception as e:
                                logger.error(
                                    f"Unexpected error processing queued conversation: {str(e)}",
                                    extra={
                                        "user_id": queue_item.get("user_id"),
                                        "conversation_id": queue_item.get("conversation_id")
                                    },
                                    exc_info=True
                                )
                                # Push back to queue to avoid losing data
                                await state_manager.redis_client.rpush(queue_key, queue_item_json)

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
        """
        logger.info(
            f"Starting memory retry worker (interval: {self.RETRY_INTERVAL}s)"
        )

        while True:
            try:
                await asyncio.sleep(self.RETRY_INTERVAL)
                await self.retry_queued_memories()
            except Exception as e:
                logger.error(
                    f"Error in retry worker loop: {str(e)}",
                    exc_info=True
                )
                # Continue running even if one iteration fails
                await asyncio.sleep(self.RETRY_INTERVAL)

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
                "Circuit breaker is open, skipping orchestrator stream",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role
                }
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
                f"Failed to stream message through orchestrator: {str(e)}",
                extra={
                    "user_id": user_id,
                    "conversation_id": conversation_id,
                    "role": role,
                    "error_type": type(e).__name__,
                    "duration_ms": duration_ms
                }
            )

            # Graceful degradation - return None instead of raising
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
                    except:
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
