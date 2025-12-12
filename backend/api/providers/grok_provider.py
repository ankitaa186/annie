"""
Grok-4 Provider

Implementation of Grok-4 (XAI API) provider with streaming support,
Grok-4 Live Search, function calling, and Langfuse tracing integration.
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from api.config import get_config
from api.logging import get_logger
from api.providers.base import BaseProvider
from api.observability.tracing import get_current_trace
from api.observability.cost import calculate_llm_cost

logger = get_logger(__name__)


class ProviderError(Exception):
    """Exception raised when a provider fails."""
    def __init__(self, provider: str, message: str, original_error: Optional[Exception] = None):
        self.provider = provider
        self.message = message
        self.original_error = original_error
        super().__init__(f"{provider}: {message}")


class RateLimitError(Exception):
    """Exception raised when rate limit is hit."""
    def __init__(self, provider: str, retry_after: Optional[int] = None):
        self.provider = provider
        self.retry_after = retry_after
        message = f"{provider} rate limit exceeded"
        if retry_after:
            message += f". Retry after {retry_after} seconds"
        super().__init__(message)


class GrokProvider(BaseProvider):
    """
    Grok-4 (XAI API) provider implementation.

    Features:
    - Streaming chat completion with function calling
    - Grok-4 Live Search support (auto/on/off modes)
    - Rate limit handling and error recovery
    - Cost calculation including Live Search costs
    - Langfuse tracing integration (fire-and-forget)
    """

    # Grok-4 API configuration
    BASE_URL = "https://api.x.ai/v1"
    MODEL_NAME = "grok-4-fast"

    def __init__(self):
        """
        Initialize Grok-4 provider with configuration from environment.

        Raises:
            ValueError: If GROK_API_KEY is not configured
        """
        config = get_config()

        # Get API key
        self.api_key = config.get("GROK_API_KEY")
        if not self.api_key or self.api_key == "REPLACE_ME":
            raise ValueError("GROK_API_KEY not configured")

        # Load timeout configuration from environment
        self.request_timeout = float(config.get("LLM_REQUEST_TIMEOUT", "180.0"))
        self.streaming_timeout = float(config.get("LLM_STREAMING_TIMEOUT", "180.0"))

        # Load Grok-4 Live Search configuration
        self.live_search_mode = config.get("GROK_LIVE_SEARCH_MODE", "auto")
        self.live_search_max_results = int(config.get("GROK_LIVE_SEARCH_MAX_RESULTS", "10"))
        self.live_search_cost_alert = int(config.get("GROK_LIVE_SEARCH_COST_ALERT_THRESHOLD", "800"))

        # Initialize HTTP client
        self.client = httpx.AsyncClient(timeout=self.request_timeout)

        logger.info(
            "Grok-4 provider initialized",
            extra={
                "provider": "grok-4",
                "model": self.MODEL_NAME,
                "live_search_mode": self.live_search_mode,
                "live_search_max_results": self.live_search_max_results,
                "request_timeout": self.request_timeout
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

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "grok-4"

    def calculate_cost(self, usage: Dict[str, int]) -> Dict[str, float]:
        """
        Calculate cost for Grok-4 usage.

        Args:
            usage: Token usage with keys:
                - prompt_tokens: Input tokens
                - completion_tokens: Output tokens
                - sources_used: Number of Live Search sources accessed

        Returns:
            Cost details dictionary
        """
        return calculate_llm_cost(
            provider="grok-4",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            sources_used=usage.get("sources_used", 0)
        )

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from Grok-4.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tools in OpenAI format
            **kwargs: Additional parameters (unused, for interface compatibility)

        Yields:
            Stream event dictionaries

        Raises:
            ProviderError: If provider call fails
            RateLimitError: If rate limit is hit
        """
        start_time = time.time()

        try:
            # Build request
            url = f"{self.BASE_URL}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.MODEL_NAME,
                "messages": messages,
                "stream": True,
                "search_parameters": {
                    "mode": self.live_search_mode,
                    "return_citations": True
                }
            }

            # Add tools if provided
            if tools:
                payload["tools"] = tools
                logger.debug(
                    "Function calling enabled for Grok-4 streaming",
                    extra={"provider": "grok-4", "tool_count": len(tools)}
                )

            logger.info(
                "Starting Grok-4 streaming request",
                extra={
                    "provider": "grok-4",
                    "model": self.MODEL_NAME,
                    "message_count": len(messages),
                    "timeout_seconds": self.streaming_timeout,
                    "tool_count": len(tools) if tools else 0
                }
            )

            # Make streaming request
            async with self.client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=self.streaming_timeout
            ) as response:
                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = response.headers.get("retry-after")
                    retry_after_seconds = int(retry_after) if retry_after else None

                    logger.warning(
                        "Grok-4 rate limit hit during streaming",
                        extra={
                            "provider": "grok-4",
                            "retry_after": retry_after_seconds
                        }
                    )

                    raise RateLimitError("grok-4", retry_after_seconds)

                # Check for other errors
                if response.status_code != 200:
                    error_msg = f"HTTP {response.status_code}"
                    try:
                        error_text = await response.aread()
                        error_data = json.loads(error_text)
                        error_msg = error_data.get("error", {}).get("message", error_msg)
                    except Exception:
                        pass

                    raise ProviderError("grok-4", error_msg)

                # Track metrics
                first_token = True
                first_token_time = None
                token_count = 0
                accumulated_content = []

                # Get current trace for Langfuse
                trace = get_current_trace()

                # Parse SSE stream
                async for line in response.aiter_lines():
                    # Skip empty lines
                    if not line.strip():
                        continue

                    # SSE format: "data: {json}"
                    if line.startswith("data: "):
                        data_str = line[6:]

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
                                            "Grok-4 first token received",
                                            extra={
                                                "provider": "grok-4",
                                                "latency_ms": first_token_latency_ms
                                            }
                                        )
                                        first_token = False

                                    token_count += 1
                                    accumulated_content.append(content)

                                    # Yield token in SSE format
                                    yield {
                                        "type": "token",
                                        "content": content
                                    }

                                # Check for finish reason (completion)
                                finish_reason = chunk["choices"][0].get("finish_reason")
                                if finish_reason:
                                    # Extract token usage
                                    usage = chunk.get("usage", {})

                                    duration_ms = int((time.time() - start_time) * 1000)

                                    # Log Grok-4 Live Search usage if search was activated
                                    sources_used = usage.get("num_sources_used", 0)

                                    if sources_used > 0:
                                        citations = chunk.get("citations", [])
                                        cost_estimate = sources_used * 0.025

                                        logger.info(
                                            "Grok-4 Live Search activated (streaming)",
                                            extra={
                                                "provider": "grok-4",
                                                "search_activated": True,
                                                "sources_accessed": sources_used,
                                                "citations_count": len(citations),
                                                "citations": citations[:5] if len(citations) > 5 else citations,
                                                "cost_estimate_usd": round(cost_estimate, 4),
                                                "duration_ms": duration_ms,
                                                "event": "live_search_used"
                                            }
                                        )

                                    logger.info(
                                        "Grok-4 streaming completed",
                                        extra={
                                            "provider": "grok-4",
                                            "duration_ms": duration_ms,
                                            "token_count": token_count,
                                            "finish_reason": finish_reason
                                        }
                                    )

                                    # Track LLM generation in Langfuse (fire-and-forget)
                                    if trace:
                                        try:
                                            # Extract token usage
                                            prompt_tokens = usage.get("prompt_tokens", 0)
                                            completion_tokens = usage.get("completion_tokens", token_count)
                                            total_tokens = prompt_tokens + completion_tokens

                                            # Calculate costs
                                            cost_details = calculate_llm_cost(
                                                provider="grok-4",
                                                prompt_tokens=prompt_tokens,
                                                completion_tokens=completion_tokens,
                                                sources_used=sources_used
                                            )

                                            # Prepare prompt and completion (truncated)
                                            prompt_text = json.dumps([m for m in messages if m.get("role") != "tool"])
                                            truncated_prompt = self._truncate_text(prompt_text, 1000)
                                            full_completion = "".join(accumulated_content)
                                            truncated_completion = self._truncate_text(full_completion, 1000)

                                            # Create Langfuse generation with cost details
                                            trace.generation(
                                                name="llm_call_grok-4_streaming",
                                                input=truncated_prompt,
                                                output=truncated_completion,
                                                model=self.MODEL_NAME,
                                                metadata={
                                                    "provider": "grok-4",
                                                    "duration_ms": duration_ms,
                                                    "sources_used": sources_used,
                                                    "streaming": True
                                                },
                                                usage={
                                                    "input": prompt_tokens,
                                                    "output": completion_tokens,
                                                    "total": total_tokens,
                                                    "unit": "TOKENS"
                                                },
                                                usage_details=cost_details
                                            )
                                        except Exception as e:
                                            # Fire-and-forget: log but don't fail stream
                                            logger.warning(
                                                f"Failed to track Grok-4 streaming generation in Langfuse: {str(e)}",
                                                extra={"provider": "grok-4"}
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
                                "Failed to parse Grok-4 streaming chunk",
                                extra={
                                    "provider": "grok-4",
                                    "line": data_str[:100],
                                    "error": str(e)
                                }
                            )
                            continue

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Grok-4 streaming timeout",
                extra={
                    "provider": "grok-4",
                    "duration_ms": duration_ms,
                    "timeout": self.streaming_timeout
                }
            )
            raise ProviderError("grok-4", "Streaming timeout", e)

        except httpx.NetworkError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "Grok-4 streaming network error",
                extra={
                    "provider": "grok-4",
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            raise ProviderError("grok-4", "Network error during streaming", e)

        except RateLimitError:
            # Re-raise rate limit errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected Grok-4 streaming error",
                extra={
                    "provider": "grok-4",
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise ProviderError("grok-4", f"Unexpected streaming error: {type(e).__name__}", e)
