"""
Intents Client Module

Async HTTP client for communicating with agentic-memories Intents API.
Provides CRUD operations, polling for due intents, claiming intents for
exclusive processing, and reporting execution results.
"""

import time
from typing import Any, Dict, List, Optional

import httpx

from api.config import get_config
from api.logging import get_logger

logger = get_logger(__name__)


class IntentsClientError(Exception):
    """Base exception for intents client errors."""
    pass


class IntentsNetworkError(IntentsClientError):
    """Exception raised when agentic-memories service is unreachable."""
    def __init__(self, message: str, original_error: Optional[Exception] = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)


class IntentsAPIError(IntentsClientError):
    """Exception raised when agentic-memories API returns an error."""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[Dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(f"Intents API error ({status_code}): {message}")


class IntentsClient:
    """
    Async HTTP client for agentic-memories Intents API communication.

    Features:
    - CRUD operations for intents
    - Polling for pending (due) intents
    - Claiming intents for exclusive processing
    - Reporting execution results
    - Health check endpoint
    - Timeout handling (30 second default)
    - Structured error logging
    - Connection pooling with httpx.AsyncClient
    """

    # Default configuration
    DEFAULT_INTENTS_URL = "http://host.docker.internal:8080"
    DEFAULT_TIMEOUT = 30.0  # 30 seconds for intent operations

    def __init__(self, intents_url: Optional[str] = None, timeout: Optional[float] = None):
        """
        Initialize Intents client.

        Args:
            intents_url: agentic-memories service URL (default: from config or http://host.docker.internal:8080)
            timeout: Request timeout in seconds (default: 30.0)
        """
        if intents_url:
            self.intents_url = intents_url
        else:
            # Load from config
            try:
                config = get_config()
                self.intents_url = config.get("AGENTIC_MEMORIES_URL", self.DEFAULT_INTENTS_URL)
            except Exception as e:
                logger.warning(
                    "Failed to load config, using default agentic-memories URL",
                    extra={"error": str(e)}
                )
                self.intents_url = self.DEFAULT_INTENTS_URL

        self.timeout = timeout or self.DEFAULT_TIMEOUT

        # Initialize async HTTP client with timeout
        self.client = httpx.AsyncClient(
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )

        logger.info(
            "Intents Client initialized",
            extra={
                "intents_url": self.intents_url,
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

    async def create_intent(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create a new intent in agentic-memories.

        Args:
            data: Intent creation payload with fields:
                - user_id: User identifier
                - intent_name: Human-readable intent name
                - description: Intent description
                - trigger_type: "cron", "interval", "once", "price", "silence", "portfolio"
                - trigger_schedule: Schedule configuration dict
                - trigger_condition: Condition configuration dict (optional)
                - action_type: "notify", "check_in", "briefing", "analysis", "reminder"
                - action_context: Rich context dict for LLM
                - action_priority: "low", "normal", "high", "urgent"
                - expires_at: Expiration datetime (optional)
                - max_executions: Max execution count (optional)
                - metadata: Additional metadata dict (optional)

        Returns:
            dict: Created intent object with id, next_check, created_at, etc.

        Raises:
            IntentsNetworkError: If agentic-memories service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents"

        try:
            logger.debug(
                "Creating intent in agentic-memories",
                extra={
                    "user_id": data.get("user_id"),
                    "intent_name": data.get("intent_name"),
                    "trigger_type": data.get("trigger_type"),
                    "url": url
                }
            )

            # Send POST request
            response = await self.client.post(url, json=data)

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
                    "Intent creation failed",
                    extra={
                        "user_id": data.get("user_id"),
                        "intent_name": data.get("intent_name"),
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            response_data = response.json()

            logger.info(
                "Intent created successfully",
                extra={
                    "user_id": data.get("user_id"),
                    "intent_id": response_data.get("id"),
                    "intent_name": data.get("intent_name"),
                    "trigger_type": data.get("trigger_type"),
                    "duration_ms": duration_ms
                }
            )

            return response_data

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent creation timed out",
                extra={
                    "user_id": data.get("user_id"),
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "user_id": data.get("user_id"),
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent creation",
                extra={
                    "user_id": data.get("user_id"),
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def list_intents(
        self,
        user_id: str,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        List intents for a user with optional filters.

        Args:
            user_id: User identifier (required)
            filters: Optional filter dict with fields:
                - trigger_type: Filter by trigger type
                - enabled: Filter by enabled status (bool)

        Returns:
            List of intent objects (summary format)

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents"

        try:
            # Build query parameters
            params: Dict[str, Any] = {"user_id": user_id}
            if filters:
                params.update(filters)

            logger.debug(
                "Listing intents from agentic-memories",
                extra={
                    "user_id": user_id,
                    "filters": filters,
                    "url": url
                }
            )

            # Send GET request
            response = await self.client.get(url, params=params)

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
                    "Intent listing failed",
                    extra={
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            intents = response.json()

            logger.info(
                "Intents listed successfully",
                extra={
                    "user_id": user_id,
                    "intent_count": len(intents),
                    "duration_ms": duration_ms
                }
            )

            return intents

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent listing timed out",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
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
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent listing",
                extra={
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def get_intent(self, intent_id: str) -> Dict[str, Any]:
        """
        Get full intent details by ID.

        Args:
            intent_id: Intent identifier

        Returns:
            dict: Full intent object

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/{intent_id}"

        try:
            logger.debug(
                "Retrieving intent from agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url
                }
            )

            # Send GET request
            response = await self.client.get(url)

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
                    "Intent retrieval failed",
                    extra={
                        "intent_id": intent_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            intent = response.json()

            logger.info(
                "Intent retrieved successfully",
                extra={
                    "intent_id": intent_id,
                    "user_id": intent.get("user_id"),
                    "duration_ms": duration_ms
                }
            )

            return intent

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent retrieval timed out",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent retrieval",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def update_intent(
        self,
        intent_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Update an existing intent.

        Args:
            intent_id: Intent identifier
            data: Partial update payload (any fields from create)

        Returns:
            dict: Updated intent object

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/{intent_id}"

        try:
            logger.debug(
                "Updating intent in agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url
                }
            )

            # Send PUT request
            response = await self.client.put(url, json=data)

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
                    "Intent update failed",
                    extra={
                        "intent_id": intent_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            intent = response.json()

            logger.info(
                "Intent updated successfully",
                extra={
                    "intent_id": intent_id,
                    "user_id": intent.get("user_id"),
                    "duration_ms": duration_ms
                }
            )

            return intent

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent update timed out",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent update",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def delete_intent(self, intent_id: str) -> bool:
        """
        Delete an intent.

        Args:
            intent_id: Intent identifier

        Returns:
            bool: True if successful

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/{intent_id}"

        try:
            logger.debug(
                "Deleting intent from agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url
                }
            )

            # Send DELETE request
            response = await self.client.delete(url)

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
                    "Intent deletion failed",
                    extra={
                        "intent_id": intent_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            logger.info(
                "Intent deleted successfully",
                extra={
                    "intent_id": intent_id,
                    "duration_ms": duration_ms
                }
            )

            return True

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent deletion timed out",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent deletion",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def get_pending(
        self,
        trigger_type: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get pending (due) intents for processing.

        Returns intents that are due for evaluation, excluding already-claimed intents.
        For condition triggers, includes in_cooldown flag in metadata.

        Args:
            trigger_type: Optional filter by trigger type
            user_id: Optional filter by user ID

        Returns:
            List of pending intent objects

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/pending"

        try:
            # Build query parameters
            params: Dict[str, Any] = {}
            if trigger_type:
                params["trigger_type"] = trigger_type
            if user_id:
                params["user_id"] = user_id

            logger.debug(
                "Retrieving pending intents from agentic-memories",
                extra={
                    "trigger_type": trigger_type,
                    "user_id": user_id,
                    "url": url
                }
            )

            # Send GET request
            response = await self.client.get(url, params=params)

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
                    "Pending intents retrieval failed",
                    extra={
                        "trigger_type": trigger_type,
                        "user_id": user_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            pending_intents = response.json()

            logger.info(
                "Pending intents retrieved successfully",
                extra={
                    "trigger_type": trigger_type,
                    "user_id": user_id,
                    "pending_count": len(pending_intents),
                    "duration_ms": duration_ms
                }
            )

            return pending_intents

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Pending intents retrieval timed out",
                extra={
                    "trigger_type": trigger_type,
                    "user_id": user_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "trigger_type": trigger_type,
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during pending intents retrieval",
                extra={
                    "trigger_type": trigger_type,
                    "user_id": user_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def claim_intent(self, intent_id: str) -> Dict[str, Any]:
        """
        Claim an intent for exclusive processing.

        Uses FOR UPDATE SKIP LOCKED for multi-worker safety.
        Returns 409 Conflict if already claimed within 5 minutes (expected behavior, not an error).

        Args:
            intent_id: Intent identifier

        Returns:
            dict: Claim response with "intent" and "claimed_at" fields

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error (excluding 409 Conflict)

        Note:
            409 Conflict is returned as a dict with {"conflict": True, "message": "..."}
            instead of raising an exception, as this is expected worker behavior.
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/{intent_id}/claim"

        try:
            logger.debug(
                "Claiming intent in agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url
                }
            )

            # Send POST request
            response = await self.client.post(url, json={})

            duration_ms = int((time.time() - start_time) * 1000)

            # Special handling for 409 Conflict (expected behavior)
            if response.status_code == 409:
                try:
                    error_data = response.json()
                    conflict_msg = error_data.get("detail", error_data.get("message", "Intent already claimed"))
                except Exception:
                    conflict_msg = "Intent already claimed"

                logger.debug(
                    "Intent already claimed (409 Conflict - expected)",
                    extra={
                        "intent_id": intent_id,
                        "conflict_detail": conflict_msg,
                        "duration_ms": duration_ms
                    }
                )

                # Return conflict result instead of raising exception
                return {
                    "conflict": True,
                    "message": conflict_msg,
                    "intent_id": intent_id
                }

            # Check for other errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_data.get("message", error_msg))
                except Exception:
                    error_msg = response.text or error_msg

                logger.error(
                    "Intent claim failed",
                    extra={
                        "intent_id": intent_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            claim_result = response.json()

            logger.info(
                "Intent claimed successfully",
                extra={
                    "intent_id": intent_id,
                    "claimed_at": claim_result.get("claimed_at"),
                    "duration_ms": duration_ms
                }
            )

            return claim_result

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent claim timed out",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent claim",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def fire_intent(
        self,
        intent_id: str,
        report: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Report intent execution result.

        Clears claimed_at, updates execution counters, and returns cooldown info
        for condition triggers.

        Args:
            intent_id: Intent identifier
            report: Execution report with fields:
                - status: "success", "failed", "gate_blocked", "condition_not_met"
                - message_id: Telegram message ID (optional)
                - message_preview: Message preview (optional)
                - trigger_data: Trigger evaluation data (optional)
                - gate_result: Gate evaluation result (optional)
                - evaluation_ms: Evaluation duration (optional)
                - generation_ms: Generation duration (optional)
                - delivery_ms: Delivery duration (optional)
                - error_message: Error details if failed (optional)

        Returns:
            dict: Fire response with fields:
                - success: bool
                - cooldown_active: bool (for condition triggers)
                - cooldown_remaining_hours: float (for condition triggers)
                - last_condition_fire: datetime (for condition triggers)

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/{intent_id}/fire"

        try:
            logger.debug(
                "Reporting intent execution to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "status": report.get("status"),
                    "url": url
                }
            )

            # Send POST request
            response = await self.client.post(url, json=report)

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
                    "Intent fire reporting failed",
                    extra={
                        "intent_id": intent_id,
                        "status": report.get("status"),
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            fire_result = response.json()

            logger.info(
                "Intent execution reported successfully",
                extra={
                    "intent_id": intent_id,
                    "status": report.get("status"),
                    "cooldown_active": fire_result.get("cooldown_active"),
                    "duration_ms": duration_ms
                }
            )

            return fire_result

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent fire reporting timed out",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent fire reporting",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def get_history(
        self,
        intent_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get execution history for an intent.

        Returns audit trail ordered by executed_at DESC.

        Args:
            intent_id: Intent identifier
            limit: Maximum number of records to return (default: 50)
            offset: Number of records to skip (default: 0)

        Returns:
            List of execution history records with fields:
                - id: History record ID
                - intent_id: Intent ID
                - status: Execution status
                - executed_at: Execution timestamp
                - evaluation_ms: Evaluation duration
                - generation_ms: Generation duration
                - delivery_ms: Delivery duration
                - message_id: Telegram message ID
                - error_message: Error details if failed

        Raises:
            IntentsNetworkError: If service is unreachable
            IntentsAPIError: If API returns an error
        """
        start_time = time.time()
        url = f"{self.intents_url}/v1/intents/{intent_id}/history"

        try:
            # Build query parameters
            params = {
                "limit": limit,
                "offset": offset
            }

            logger.debug(
                "Retrieving intent execution history from agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "limit": limit,
                    "offset": offset,
                    "url": url
                }
            )

            # Send GET request
            response = await self.client.get(url, params=params)

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
                    "Intent history retrieval failed",
                    extra={
                        "intent_id": intent_id,
                        "status_code": response.status_code,
                        "error": error_msg,
                        "duration_ms": duration_ms
                    }
                )
                raise IntentsAPIError(
                    message=error_msg,
                    status_code=response.status_code,
                    response_data=error_data if 'error_data' in locals() else None
                )

            # Parse successful response
            history = response.json()

            logger.info(
                "Intent history retrieved successfully",
                extra={
                    "intent_id": intent_id,
                    "record_count": len(history),
                    "duration_ms": duration_ms
                }
            )

            return history

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Intent history retrieval timed out",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "timeout": self.timeout,
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Request timed out after {self.timeout}s",
                original_error=e
            )

        except (httpx.NetworkError, httpx.ConnectError) as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Failed to connect to agentic-memories",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"Failed to connect to agentic-memories: {str(e)}",
                original_error=e
            )

        except httpx.HTTPError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "HTTP error during intent history retrieval",
                extra={
                    "intent_id": intent_id,
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            raise IntentsNetworkError(
                f"HTTP error: {str(e)}",
                original_error=e
            )

    async def health_check(self) -> bool:
        """
        Check if agentic-memories Intents API is available.

        Returns:
            bool: True if service is healthy, False otherwise
        """
        start_time = time.time()
        url = f"{self.intents_url}/health"

        try:
            logger.debug("Checking agentic-memories health", extra={"url": url})

            response = await self.client.get(url)
            duration_ms = int((time.time() - start_time) * 1000)

            is_healthy = response.status_code == 200

            logger.info(
                "Intents API health check completed",
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
                "Intents API health check failed",
                extra={
                    "url": url,
                    "error": str(e),
                    "duration_ms": duration_ms
                }
            )
            return False
