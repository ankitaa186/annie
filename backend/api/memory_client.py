"""
Memory Client Module

Async HTTP client for communicating with agentic-memories service.
Provides memory storage operations with error handling and structured logging.
"""

import json
import time
from typing import Any, Dict, Optional

import httpx

from api.config import get_config
from api.logging import get_logger

logger = get_logger(__name__)


class MemoryClientError(Exception):
    """Base exception for memory client errors."""
    pass


class MemoryNetworkError(MemoryClientError):
    """Exception raised when agentic-memories service is unreachable."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class MemoryAPIError(MemoryClientError):
    """Exception raised when agentic-memories API returns an error."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(f"Memory API error ({status_code}): {message}")


class MemoryClient:
    """
    Async HTTP client for agentic-memories service communication.

    Features:
    - Memory storage via HTTP API
    - Health check endpoint
    - Timeout handling (240 second default for long-running LLM extraction)
    - Structured error logging
    - Connection pooling with httpx.AsyncClient
    """

    # Default configuration
    DEFAULT_MEMORIES_URL = "http://host.docker.internal:8080"
    DEFAULT_TIMEOUT = 240.0  # 4 minutes (long-running LLM extraction process)

    def __init__(self, memories_url: Optional[str] = None, timeout: Optional[float] = None):
        """
        Initialize Memory client.

        Args:
            memories_url: agentic-memories service URL (default: from config or http://host.docker.internal:8080)
            timeout: Request timeout in seconds (default: 240.0 for long-running LLM extraction)
        """
        if memories_url:
            self.memories_url = memories_url
        else:
            # Load from config
            try:
                config = get_config()
                self.memories_url = config.get("AGENTIC_MEMORIES_URL", self.DEFAULT_MEMORIES_URL)
            except Exception as e:
                logger.warning(
                    "Failed to load config, using default agentic-memories URL",
                    extra={"error": str(e)}
                )
                self.memories_url = self.DEFAULT_MEMORIES_URL

        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Initialize async HTTP client with timeout
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )

        logger.info(
            "Memory Client initialized",
            extra={
                "memories_url": self.memories_url,
                "timeout": self.timeout
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close HTTP client."""
        await self.close()

    async def close(self):
        """Close HTTP client connection."""
        if self.client:
            await self.client.aclose()

    async def store_memory(
        self,
        user_id: str,
        history: list[Dict[str, str]],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store conversation transcript in agentic-memories service.

        The service will automatically extract memories from the conversation history.

        Args:
            user_id: User identifier
            history: List of conversation messages with structure:
                [
                    {"role": "user"|"assistant"|"system", "content": str},
                    ...
                ]
            metadata: Optional metadata dict (e.g., {"platform": "telegram", "conversation_id": "..."})

        Returns:
            dict: Response from agentic-memories service:
                {
                    "memories_created": int,
                    "ids": List[str],
                    "summary": str,
                    "memories": List[Dict],
                    ...
                }

        Raises:
            MemoryNetworkError: If agentic-memories service is unreachable
            MemoryAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.memories_url}/v1/store"

        try:
            logger.debug(
                "Storing conversation transcript in agentic-memories",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "message_count": len(history)
                }
            )

            # Build request payload
            payload = {
                "user_id": user_id,
                "history": history
            }
            if metadata:
                payload["metadata"] = metadata

            # Send POST request
            response = await self.client.post(url, json=payload)

            duration_ms = int((time.time() - start_time) * 1000)

            # Check for errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Memory storage failed",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise MemoryAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            response_data = response.json()

            logger.info(
                "Conversation transcript stored successfully",
                extra={
                    "user_id": user_id,
                    "memories_created": response_data.get("memories_created", 0),
                    "duration_ms": duration_ms,
                    "message_count": len(history)
                }
            )

            return response_data

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Memory storage timed out",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise MemoryNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise MemoryNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during memory storage",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise MemoryNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def retrieve_memories(
        self,
        user_id: str,
        query: str,
        limit: int = 5,
        persona: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        """
        Retrieve relevant memories from agentic-memories service.

        Args:
            user_id: User identifier
            query: Search query for semantic matching
            limit: Maximum number of memories to retrieve (default: 5)
            persona: Optional persona filter (e.g., "stock_trader", "career_advisor")

        Returns:
            List of memory objects sorted by relevance score (highest first)
            Returns empty list on failure (graceful degradation)

        Raises:
            MemoryNetworkError: If service is unreachable
            MemoryAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.memories_url}/v1/retrieve"

        try:
            # Build query parameters
            params = {
                "user_id": user_id,
                "query": query,
                "limit": limit
            }
            if persona:
                params["persona"] = persona

            logger.debug(
                "Retrieving memories from agentic-memories",
                extra={
                    "user_id": user_id,
                    "query": query,
                    "limit": limit,
                    "persona": persona,
                    "url": url
                }
            )

            # Send GET request with 300ms timeout for retrieval (performance target)
            # Override default 5s timeout for faster retrieval
            response = await self.client.get(
                url,
                params=params,
                timeout=0.3  # 300ms target
            )

            duration_ms = int((time.time() - start_time) * 1000)

            # Check for errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message", error_msg)
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Memory retrieval failed",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise MemoryAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            response_data = response.json()
            # agentic-memories API returns "results" field (not "memories")
            memories = response_data.get("results", [])

            # Log performance warning if exceeded target
            if duration_ms > 300:
                logger.warning(
                    "Memory retrieval exceeded 300ms target",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "duration_ms": duration_ms,
                        "memory_count": len(memories),
                        "exceeded_target": True
                    }
                )
            else:
                logger.info(
                    "Memories retrieved successfully",
                    extra={
                        "user_id": user_id,
                        "query": query,
                        "memory_count": len(memories),
                        "duration_ms": duration_ms
                    }
                )

            return memories

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Memory retrieval timed out, returning empty list (graceful degradation)",
                extra={
                    "user_id": user_id,
                    "query": query,
                    "timeout": 0.3,
                    "duration_ms": duration_ms
                }
            )
            # Graceful degradation: return empty list on timeout
            return []

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Failed to connect to agentic-memories for retrieval, returning empty list (graceful degradation)",
                extra={
                    "user_id": user_id,
                    "query": query,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            # Graceful degradation: return empty list on network error
            return []

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "HTTP error during memory retrieval, returning empty list (graceful degradation)",
                extra={
                    "user_id": user_id,
                    "query": query,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            # Graceful degradation: return empty list on HTTP error
            return []

    async def store_direct(
        self,
        user_id: str,
        content: str,
        layer: str = "long-term",
        memory_type: str = "explicit",
        tags: Optional[list[str]] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Store a memory directly in agentic-memories without LLM extraction.

        Content is stored as-is — no fragmentation or processing.
        Use this for pre-processed content like conversation summaries.

        Args:
            user_id: User identifier
            content: Memory content text (max 5000 chars)
            layer: Memory layer: 'short-term', 'semantic', 'long-term' (default: 'long-term')
            memory_type: Memory type: 'explicit' or 'implicit' (default: 'explicit')
            tags: Optional list of tags for categorization
            metadata: Optional metadata dict

        Returns:
            dict: Response from agentic-memories with memory ID

        Raises:
            MemoryNetworkError: If service is unreachable
            MemoryAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.memories_url}/v1/memories/direct"

        try:
            payload: Dict[str, Any] = {
                "user_id": user_id,
                "content": content,
                "layer": layer,
                "type": memory_type,
            }
            if tags:
                payload["tags"] = tags
            if metadata:
                payload["metadata"] = metadata

            logger.debug(
                "Storing direct memory in agentic-memories",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "content_length": len(content),
                    "layer": layer
                }
            )

            response = await self.client.post(url, json=payload)
            duration_ms = int((time.time() - start_time) * 1000)

            if response.status_code not in (200, 201):
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_data.get("message", error_msg))
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Direct memory storage failed",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise MemoryAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            response_data = response.json()

            logger.info(
                "Direct memory stored successfully",
                extra={
                    "user_id": user_id,
                    "memory_id": response_data.get("id"),
                    "layer": layer,
                    "content_length": len(content),
                    "duration_ms": duration_ms
                }
            )

            return response_data

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Direct memory storage timed out",
                extra={"user_id": user_id, "url": url, "duration_ms": duration_ms}
            )
            raise MemoryNetworkError(f"Request timed out after {self.timeout}s", original_error=e)

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories for direct storage",
                extra={"user_id": user_id, "url": url, "error": str(e), "duration_ms": duration_ms}
            )
            raise MemoryNetworkError(f"Failed to connect: {str(e)}", original_error=e)

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during direct memory storage",
                extra={"user_id": user_id, "url": url, "error": str(e), "duration_ms": duration_ms}
            )
            raise MemoryNetworkError(f"HTTP error: {str(e)}", original_error=e)

    async def stream_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        user_id: str,
        message_id: Optional[str] = None,
        flush: bool = False,
    ) -> Dict[str, Any]:
        """
        Stream a single message through the orchestrator for batched storage.

        The orchestrator batches messages (2-8) before triggering LLM extraction,
        providing ~70% cost savings compared to direct /v1/store calls.

        Args:
            conversation_id: Conversation identifier
            role: Message role ("user", "assistant", "system", "tool")
            content: Message content
            user_id: User ID (passed in metadata for storage)
            message_id: Optional message ID for tracking
            flush: Force immediate flush of batched messages (default: False)

        Returns:
            dict: Response with "injections" list of relevant memories
                {
                    "injections": [
                        {
                            "memory_id": str,
                            "content": str,
                            "source": str,
                            "channel": str,
                            "score": float,
                            "metadata": dict
                        }
                    ]
                }

        Raises:
            MemoryNetworkError: If agentic-memories service is unreachable
            MemoryAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.memories_url}/v1/orchestrator/message"

        try:
            logger.debug(
                "Streaming message to orchestrator",
                extra={
                    "conversation_id": conversation_id,
                    "role": role,
                    "user_id": user_id,
                    "url": url,
                    "flush": flush
                }
            )

            # Build request payload matching orchestrator schema
            payload: Dict[str, Any] = {
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "metadata": {"user_id": user_id},
                "flush": flush
            }
            if message_id:
                payload["message_id"] = message_id

            # Send POST request
            response = await self.client.post(url, json=payload)

            duration_ms = int((time.time() - start_time) * 1000)

            # Check for errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_data.get("message", error_msg))
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Orchestrator stream_message failed",
                    extra={
                        "conversation_id": conversation_id,
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise MemoryAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            response_data = response.json()
            injections = response_data.get("injections", [])

            logger.info(
                "Message streamed to orchestrator successfully",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "role": role,
                    "injections_count": len(injections),
                    "duration_ms": duration_ms,
                    "flush": flush
                }
            )

            return response_data

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Orchestrator stream_message timed out",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise MemoryNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to orchestrator",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise MemoryNetworkError(
                f"Failed to connect to orchestrator: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during orchestrator stream_message",
                extra={
                    "conversation_id": conversation_id,
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise MemoryNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def health_check(self) -> bool:
        """
        Check if agentic-memories service is available.

        Returns:
            bool: True if service is healthy, False otherwise
        """
        start_time = time.time()
        url = f"{self.memories_url}/health"

        try:
            logger.debug("Checking agentic-memories health", extra={"url": url})

            response = await self.client.get(url)
            duration_ms = int((time.time() - start_time) * 1000)

            is_healthy = response.status_code == 200

            logger.info(
                "Health check completed",
                extra={
                    "url": url,
                    "status_code": response.status_code,
                    "healthy": is_healthy,
                    "duration_ms": duration_ms
                }
            )

            return is_healthy

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Health check failed",
                extra={
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            return False
