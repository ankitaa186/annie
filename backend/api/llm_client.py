"""
LLM Client Module

Unified client for LLM providers (Grok-4 and ChatGPT-5) with automatic failover,
error handling, rate limiting support, and streaming capabilities.
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from api.config import get_config
from api.logging import get_logger

logger = get_logger(__name__)


class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


class ProviderError(LLMClientError):
    """Exception raised when a provider fails."""
    def __init__(self, provider: str, message: str, original_error: Optional[Exception] = None):
        self.provider = provider
        self.message = message
        self.original_error = original_error
        super().__init__(f"{provider}: {message}")


class RateLimitError(LLMClientError):
    """Exception raised when rate limit is hit."""
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.provider = provider
        self.retry_after = retry_after
        message = f"{provider} rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(message)


class LLMClient:
    """
    Unified LLM client supporting multiple providers with automatic failover.

    Supports:
    - Grok-4 (XAI API) - Primary provider
    - ChatGPT-5 (OpenAI API) - Fallback provider

    Features:
    - Automatic provider failover within 2 seconds
    - Rate limiting detection and handling
    - Structured error logging
    - Environment-based configuration
    """

    # Provider configuration
    GROK4_BASE_URL = "https://api.x.ai/v1"
    CHATGPT5_BASE_URL = "https://api.openai.com/v1"

    # Timeouts (in seconds)
    REQUEST_TIMEOUT = 30.0  # Total timeout for request
    FAILOVER_TIMEOUT = 2.0  # Max time before failing over to backup provider

    def __init__(self):
        """
        Initialize LLM client with provider configuration from environment.

        Raises:
            ValueError: If required configuration is missing or invalid
        """
        config = get_config()

        # Get primary provider
        self.primary_provider = config.get("LLM_PROVIDER", "grok-4")

        # Get API keys
        self.grok_api_key = config.get("GROK_API_KEY")
        self.chatgpt_api_key = config.get("CHATGPT_API_KEY")

        # Validate provider configuration
        if self.primary_provider not in ["grok-4", "chatgpt-5"]:
            logger.warning(
                f"Invalid LLM_PROVIDER '{self.primary_provider}'. Defaulting to 'grok-4'.",
                extra={"provider": self.primary_provider}
            )
            self.primary_provider = "grok-4"

        # Initialize HTTP client with timeout
        self.client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)

        # Track which providers are available
        self.providers_available = {
            "grok-4": bool(self.grok_api_key and self.grok_api_key != "REPLACE_ME"),
            "chatgpt-5": bool(self.chatgpt_api_key and self.chatgpt_api_key != "REPLACE_ME")
        }

        logger.info(
            "LLM Client initialized",
            extra={
                "primary_provider": self.primary_provider,
                "grok4_available": self.providers_available["grok-4"],
                "chatgpt5_available": self.providers_available["chatgpt-5"]
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

    def _get_provider_config(self, provider: str) -> Dict[str, str]:
        """
        Get configuration for a specific provider.

        Args:
            provider: Provider name ("grok-4" or "chatgpt-5")

        Returns:
            Dictionary with base_url and api_key

        Raises:
            ProviderError: If provider is not configured
        """
        if provider == "grok-4":
            if not self.providers_available["grok-4"]:
                raise ProviderError("grok-4", "Grok-4 API key not configured")
            return {
                "base_url": self.GROK4_BASE_URL,
                "api_key": self.grok_api_key
            }
        elif provider == "chatgpt-5":
            if not self.providers_available["chatgpt-5"]:
                raise ProviderError("chatgpt-5", "ChatGPT-5 API key not configured")
            return {
                "base_url": self.CHATGPT5_BASE_URL,
                "api_key": self.chatgpt_api_key
            }
        else:
            raise ProviderError(provider, f"Unknown provider: {provider}")

    def _get_fallback_provider(self, failed_provider: str) -> Optional[str]:
        """
        Get fallback provider for a failed provider.

        Args:
            failed_provider: Provider that failed

        Returns:
            Fallback provider name, or None if no fallback available
        """
        if failed_provider == "grok-4" and self.providers_available["chatgpt-5"]:
            return "chatgpt-5"
        elif failed_provider == "chatgpt-5" and self.providers_available["grok-4"]:
            return "grok-4"
        return None

    async def _call_provider(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Call a specific LLM provider.

        Args:
            provider: Provider name ("grok-4" or "chatgpt-5")
            messages: List of message dictionaries with 'role' and 'content'
            timeout: Optional timeout override for this request

        Returns:
            Response dictionary from provider

        Raises:
            ProviderError: If provider call fails
            RateLimitError: If rate limit is hit
        """
        start_time = time.time()

        try:
            # Get provider configuration
            config = self._get_provider_config(provider)

            # Build request
            url = f"{config['base_url']}/chat/completions"
            headers = {
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "grok-4-0709" if provider == "grok-4" else "gpt-4",
                "messages": messages
            }

            # Make request with timeout
            request_timeout = timeout if timeout is not None else self.FAILOVER_TIMEOUT
            response = await self.client.post(
                url,
                headers=headers,
                json=payload,
                timeout=request_timeout
            )

            # Check for rate limiting
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                retry_after_seconds = int(retry_after) if retry_after else None

                logger.warning(
                    "Rate limit hit",
                    extra={
                        "provider": provider,
                        "retry_after": retry_after_seconds
                    }
                )

                raise RateLimitError(provider, retry_after_seconds)

            # Check for other errors
            if response.status_code != 200:
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", error_msg)
                except Exception:
                    pass

                raise ProviderError(provider, error_msg)

            # Parse response
            result = response.json()

            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(
                "LLM request successful",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "model": payload["model"]
                }
            )

            return result

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Provider timeout",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "timeout": request_timeout
                }
            )
            raise ProviderError(provider, "Request timeout", e)

        except httpx.NetworkError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Network error",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            raise ProviderError(provider, "Network error", e)

        except RateLimitError:
            # Re-raise rate limit errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected provider error",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise ProviderError(provider, f"Unexpected error: {type(e).__name__}", e)

    async def chat_completion(self, messages: List[Dict[str, str]]) -> Dict[str, Any]:
        """
        Send chat completion request with automatic provider failover.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
                     Example: [{"role": "user", "content": "Hello"}]

        Returns:
            Response dictionary with 'choices', 'usage', etc.

        Raises:
            LLMClientError: If all providers fail
        """
        # Determine provider order (primary first, then fallback)
        provider = self.primary_provider
        fallback = self._get_fallback_provider(provider)

        logger.info(
            "Starting chat completion",
            extra={
                "primary_provider": provider,
                "fallback_provider": fallback,
                "message_count": len(messages)
            }
        )

        # Try primary provider
        try:
            result = await self._call_provider(provider, messages, timeout=self.FAILOVER_TIMEOUT)
            return result

        except RateLimitError as e:
            # Log rate limit and try fallback
            logger.warning(
                "Rate limit on primary provider, attempting fallback",
                extra={
                    "failed_provider": provider,
                    "fallback_provider": fallback,
                    "retry_after": e.retry_after
                }
            )

            # If no fallback, return user-friendly error
            if not fallback:
                logger.error(
                    "No fallback provider available for rate limit",
                    extra={"failed_provider": provider}
                )
                raise LLMClientError(
                    "I'm experiencing technical difficulties. Please try again in a moment."
                )

        except ProviderError as e:
            # Log provider failure and try fallback
            logger.warning(
                "Primary provider failed, attempting fallback",
                extra={
                    "failed_provider": provider,
                    "fallback_provider": fallback,
                    "error": e.message,
                    "retry_attempt": "failover"
                }
            )

            # If no fallback, return user-friendly error
            if not fallback:
                logger.error(
                    "No fallback provider available",
                    extra={"failed_provider": provider}
                )
                raise LLMClientError(
                    "I'm experiencing technical difficulties. Please try again in a moment."
                )

        # Try fallback provider
        try:
            logger.info(
                "Attempting fallback provider",
                extra={"fallback_provider": fallback}
            )
            result = await self._call_provider(fallback, messages, timeout=self.FAILOVER_TIMEOUT)

            logger.info(
                "Fallback successful",
                extra={
                    "failed_provider": provider,
                    "successful_provider": fallback
                }
            )

            return result

        except (ProviderError, RateLimitError) as e:
            # Both providers failed
            logger.error(
                "All providers failed",
                extra={
                    "primary_provider": provider,
                    "fallback_provider": fallback,
                    "error": str(e)
                }
            )

            # Return user-friendly error message
            raise LLMClientError(
                "I'm experiencing technical difficulties. Please try again in a moment."
            )

    async def _call_provider_stream(
        self,
        provider: str,
        messages: List[Dict[str, str]],
        timeout: Optional[float] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Call a specific LLM provider with streaming enabled.

        Args:
            provider: Provider name ("grok-4" or "chatgpt-5")
            messages: List of message dictionaries with 'role' and 'content'
            timeout: Optional timeout override for this request

        Yields:
            Stream event dictionaries in SSE format

        Raises:
            ProviderError: If provider call fails
            RateLimitError: If rate limit is hit
        """
        start_time = time.time()

        try:
            # Get provider configuration
            config = self._get_provider_config(provider)

            # Build request
            url = f"{config['base_url']}/chat/completions"
            headers = {
                "Authorization": f"Bearer {config['api_key']}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "grok-4-0709" if provider == "grok-4" else "gpt-4",
                "messages": messages,
                "stream": True  # Enable streaming
            }

            # Make streaming request
            request_timeout = timeout if timeout is not None else self.REQUEST_TIMEOUT

            logger.info(
                "Starting streaming request",
                extra={
                    "provider": provider,
                    "model": payload["model"],
                    "message_count": len(messages)
                }
            )

            async with self.client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=request_timeout
            ) as response:
                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    retry_after_seconds = int(retry_after) if retry_after else None

                    logger.warning(
                        "Rate limit hit during streaming",
                        extra={
                            "provider": provider,
                            "retry_after": retry_after_seconds
                        }
                    )

                    raise RateLimitError(provider, retry_after_seconds)

                # Check for other errors
                if response.status_code != 200:
                    error_msg = f"HTTP {response.status_code}"
                    try:
                        error_text = await response.aread()
                        error_data = json.loads(error_text)
                        error_msg = error_data.get("error", {}).get("message", error_msg)
                    except Exception:
                        pass

                    raise ProviderError(provider, error_msg)

                # Track metrics
                first_token = True
                first_token_time = None
                token_count = 0

                # Parse SSE stream
                async for line in response.aiter_lines():
                    # Skip empty lines
                    if not line.strip():
                        continue

                    # SSE format: "data: {json}"
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix

                        # Check for stream end marker
                        if data_str.strip() == "[DONE]":
                            break

                        try:
                            # Parse JSON chunk
                            chunk = json.loads(data_str)

                            # Extract token from chunk
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content")

                                if content:
                                    # Track first token latency
                                    if first_token:
                                        first_token_time = time.time()
                                        first_token_latency_ms = int((first_token_time - start_time) * 1000)
                                        logger.info(
                                            "First token received",
                                            extra={
                                                "provider": provider,
                                                "latency_ms": first_token_latency_ms
                                            }
                                        )
                                        first_token = False

                                    token_count += 1

                                    # Yield token in SSE format
                                    yield {
                                        "type": "token",
                                        "content": content
                                    }

                                # Check for finish reason (completion)
                                finish_reason = chunk["choices"][0].get("finish_reason")
                                if finish_reason:
                                    # Extract token usage if available
                                    usage = chunk.get("usage", {})

                                    duration_ms = int((time.time() - start_time) * 1000)
                                    logger.info(
                                        "Streaming completed",
                                        extra={
                                            "provider": provider,
                                            "duration_ms": duration_ms,
                                            "token_count": token_count,
                                            "finish_reason": finish_reason
                                        }
                                    )

                                    # Yield completion event
                                    yield {
                                        "type": "done",
                                        "tokens_used": {
                                            "prompt": usage.get("prompt_tokens", 0),
                                            "completion": usage.get("completion_tokens", token_count)
                                        }
                                    }

                        except json.JSONDecodeError as e:
                            logger.warning(
                                "Failed to parse streaming chunk",
                                extra={
                                    "provider": provider,
                                    "line": data_str[:100],  # Log first 100 chars
                                    "error": str(e)
                                }
                            )
                            continue

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Streaming timeout",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "timeout": request_timeout
                }
            )
            raise ProviderError(provider, "Streaming timeout", e)

        except httpx.NetworkError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Streaming network error",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            raise ProviderError(provider, "Network error during streaming", e)

        except RateLimitError:
            # Re-raise rate limit errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected streaming error",
                extra={
                    "provider": provider,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise ProviderError(provider, f"Unexpected streaming error: {type(e).__name__}", e)

    async def chat_completion_stream(
        self,
        messages: List[Dict[str, str]]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send streaming chat completion request with automatic provider failover.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
                     Example: [{"role": "user", "content": "Hello"}]

        Yields:
            Stream event dictionaries:
            - Token event: {"type": "token", "content": "text chunk"}
            - Completion event: {"type": "done", "tokens_used": {"prompt": N, "completion": M}}
            - Error event: {"type": "error", "message": "error message", "code": "ERROR_CODE"}

        Raises:
            LLMClientError: If all providers fail before streaming starts
        """
        # Determine provider order (primary first, then fallback)
        provider = self.primary_provider
        fallback = self._get_fallback_provider(provider)

        logger.info(
            "Starting streaming chat completion",
            extra={
                "primary_provider": provider,
                "fallback_provider": fallback,
                "message_count": len(messages)
            }
        )

        # Try primary provider
        try:
            async for event in self._call_provider_stream(provider, messages, timeout=self.FAILOVER_TIMEOUT):
                yield event
            return  # Successfully completed streaming

        except RateLimitError as e:
            # Log rate limit and try fallback
            logger.warning(
                "Rate limit on primary provider during streaming, attempting fallback",
                extra={
                    "failed_provider": provider,
                    "fallback_provider": fallback,
                    "retry_after": e.retry_after
                }
            )

            # If no fallback, yield error event
            if not fallback:
                logger.error(
                    "No fallback provider available for streaming rate limit",
                    extra={"failed_provider": provider}
                )
                yield {
                    "type": "error",
                    "message": "I'm experiencing technical difficulties. Please try again in a moment.",
                    "code": "RATE_LIMIT_ERROR"
                }
                return

        except ProviderError as e:
            # Log provider failure and try fallback
            logger.warning(
                "Primary provider failed during streaming, attempting fallback",
                extra={
                    "failed_provider": provider,
                    "fallback_provider": fallback,
                    "error": e.message
                }
            )

            # If no fallback, yield error event
            if not fallback:
                logger.error(
                    "No fallback provider available for streaming",
                    extra={"failed_provider": provider}
                )
                yield {
                    "type": "error",
                    "message": "I'm experiencing technical difficulties. Please try again in a moment.",
                    "code": "PROVIDER_ERROR"
                }
                return

        # Try fallback provider
        try:
            logger.info(
                "Attempting fallback provider for streaming",
                extra={"fallback_provider": fallback}
            )

            async for event in self._call_provider_stream(fallback, messages, timeout=self.FAILOVER_TIMEOUT):
                yield event

            logger.info(
                "Streaming fallback successful",
                extra={
                    "failed_provider": provider,
                    "successful_provider": fallback
                }
            )

        except (ProviderError, RateLimitError) as e:
            # Both providers failed
            logger.error(
                "All providers failed during streaming",
                extra={
                    "primary_provider": provider,
                    "fallback_provider": fallback,
                    "error": str(e)
                }
            )

            # Yield error event
            yield {
                "type": "error",
                "message": "I'm experiencing technical difficulties. Please try again in a moment.",
                "code": "ALL_PROVIDERS_FAILED"
            }

    def health_check(self) -> str:
        """
        Check primary provider availability.

        Returns:
            "ok" if primary provider is available
            "degraded" if only fallback provider is available
            "unavailable" if no providers are available
        """
        primary_available = self.providers_available.get(self.primary_provider, False)
        fallback = self._get_fallback_provider(self.primary_provider)
        fallback_available = self.providers_available.get(fallback, False) if fallback else False

        if primary_available:
            status = "ok"
        elif fallback_available:
            status = "degraded"
        else:
            status = "unavailable"

        logger.debug(
            "Health check completed",
            extra={
                "status": status,
                "primary_provider": self.primary_provider,
                "primary_available": primary_available,
                "fallback_available": fallback_available
            }
        )

        return status
