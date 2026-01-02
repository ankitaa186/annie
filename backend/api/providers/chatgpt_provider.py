"""
ChatGPT-5 Provider

Implementation of ChatGPT-5 (OpenAI API) provider with streaming support,
function calling, and Langfuse tracing integration.
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


class ChatGPTProvider(BaseProvider):
    """
    ChatGPT-5 (OpenAI API) provider implementation.

    Features:
    - Streaming chat completion with function calling
    - OpenAI-compatible function calling format
    - Rate limit handling and error recovery
    - Cost calculation based on OpenAI pricing
    - Langfuse tracing integration (fire-and-forget)
    """

    # ChatGPT-5 API configuration
    BASE_URL = "https://api.openai.com/v1"
    MODEL_NAME = "gpt-5.2"  # Latest flagship model (Dec 2025) - 400k context, 128k output

    def __init__(self):
        """
        Initialize ChatGPT-5 provider with configuration from environment.

        Raises:
            ValueError: If CHATGPT_API_KEY is not configured
        """
        config = get_config()

        # Get API key
        self.api_key = config.get("CHATGPT_API_KEY")
        if not self.api_key or self.api_key == "REPLACE_ME":
            raise ValueError("CHATGPT_API_KEY not configured")

        # Load timeout configuration from environment
        self.request_timeout = float(config.get("LLM_REQUEST_TIMEOUT", "180.0"))
        self.streaming_timeout = float(config.get("LLM_STREAMING_TIMEOUT", "180.0"))

        # Initialize HTTP client
        self.client = httpx.AsyncClient(timeout=self.request_timeout)

        logger.info(
            "ChatGPT-5 provider initialized",
            extra={
                "provider": "chatgpt-5",
                "model": self.MODEL_NAME,
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
        return "chatgpt-5"

    def calculate_cost(self, usage: Dict[str, int]) -> Dict[str, float]:
        """
        Calculate cost for ChatGPT-5 usage.

        Args:
            usage: Token usage with keys:
                - prompt_tokens: Input tokens
                - completion_tokens: Output tokens

        Returns:
            Cost details dictionary
        """
        return calculate_llm_cost(
            provider="chatgpt-5",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            sources_used=0  # ChatGPT-5 doesn't have Live Search
        )

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        mcp_client: Optional[Any] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from ChatGPT-5 with tool calling support.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tools in OpenAI format
            mcp_client: Optional MCP client for executing tool calls
            **kwargs: Additional parameters (unused, for interface compatibility)

        Yields:
            Stream event dictionaries:
            - {"type": "token", "content": "..."}
            - {"type": "tool_call_started", "tool": "name", "arguments": {...}}
            - {"type": "tool_call_completed", "tool": "name", "result_summary": "..."}
            - {"type": "tool_call_failed", "tool": "name", "error": "..."}
            - {"type": "done", "tokens_used": {...}}

        Raises:
            ProviderError: If provider call fails
            RateLimitError: If rate limit is hit
        """
        # Track conversation for multi-turn tool calling
        conversation_messages = list(messages)
        max_tool_iterations = 10
        iteration = 0

        while iteration < max_tool_iterations:
            iteration += 1

            async for event in self._stream_single_completion(
                conversation_messages, tools, mcp_client
            ):
                if event.get("type") == "tool_calls_pending":
                    # Tool calls need to be executed, then continue loop
                    tool_calls = event.get("tool_calls", [])
                    tool_results = event.get("tool_results", [])

                    # Add assistant message with tool calls
                    conversation_messages.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": tool_calls
                    })

                    # Add tool results
                    for result in tool_results:
                        conversation_messages.append({
                            "role": "tool",
                            "tool_call_id": result["tool_call_id"],
                            "content": result["content"]
                        })

                    # Continue to next iteration for follow-up response
                    break
                elif event.get("type") == "done":
                    # Final completion, exit loop
                    yield event
                    return
                else:
                    # Pass through other events (tokens, tool_call_started, etc.)
                    yield event
            else:
                # Loop completed without break (no pending tool calls)
                return

        # Max iterations reached
        logger.warning(
            "ChatGPT-5 max tool iterations reached",
            extra={"provider": "chatgpt-5", "max_iterations": max_tool_iterations}
        )

    async def _stream_single_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        mcp_client: Optional[Any] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream a single completion (may result in tool calls or final response).
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
                "stream_options": {"include_usage": True}  # Get usage in stream
            }

            # Add tools if provided
            if tools:
                payload["tools"] = tools
                logger.debug(
                    "Function calling enabled for ChatGPT-5 streaming",
                    extra={"provider": "chatgpt-5", "tool_count": len(tools)}
                )

            logger.info(
                "Starting ChatGPT-5 streaming request",
                extra={
                    "provider": "chatgpt-5",
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
                        "ChatGPT-5 rate limit hit during streaming",
                        extra={
                            "provider": "chatgpt-5",
                            "retry_after": retry_after_seconds
                        }
                    )

                    raise RateLimitError("chatgpt-5", retry_after_seconds)

                # Check for other errors
                if response.status_code != 200:
                    error_msg = f"HTTP {response.status_code}"
                    try:
                        error_text = await response.aread()
                        error_data = json.loads(error_text)
                        error_msg = error_data.get("error", {}).get("message", error_msg)
                    except Exception:
                        pass

                    raise ProviderError("chatgpt-5", error_msg)

                # Track metrics
                first_token = True
                first_token_time = None
                token_count = 0
                accumulated_content = []

                # Track streaming tool calls (OpenAI sends them in chunks)
                streaming_tool_calls: Dict[int, Dict[str, Any]] = {}
                final_usage = {}

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

                            # Check for usage in final chunk (with stream_options)
                            if "usage" in chunk and chunk["usage"]:
                                final_usage = chunk["usage"]

                            # Extract token from chunk
                            if "choices" in chunk and len(chunk["choices"]) > 0:
                                delta = chunk["choices"][0].get("delta", {})
                                content = delta.get("content")
                                tool_calls_delta = delta.get("tool_calls")

                                # Handle content tokens
                                if content:
                                    # Track first token latency
                                    if first_token:
                                        first_token_time = time.time()
                                        first_token_latency_ms = int((first_token_time - start_time) * 1000)
                                        logger.info(
                                            "ChatGPT-5 first token received",
                                            extra={
                                                "provider": "chatgpt-5",
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

                                # Handle streaming tool calls
                                if tool_calls_delta:
                                    for tc in tool_calls_delta:
                                        idx = tc.get("index", 0)
                                        if idx not in streaming_tool_calls:
                                            # New tool call
                                            streaming_tool_calls[idx] = {
                                                "id": tc.get("id", ""),
                                                "type": "function",
                                                "function": {
                                                    "name": tc.get("function", {}).get("name", ""),
                                                    "arguments": ""
                                                }
                                            }
                                        else:
                                            # Append to existing tool call
                                            if tc.get("id"):
                                                streaming_tool_calls[idx]["id"] = tc["id"]
                                            if tc.get("function", {}).get("name"):
                                                streaming_tool_calls[idx]["function"]["name"] = tc["function"]["name"]

                                        # Accumulate arguments
                                        if tc.get("function", {}).get("arguments"):
                                            streaming_tool_calls[idx]["function"]["arguments"] += tc["function"]["arguments"]

                                # Check for finish reason (completion)
                                finish_reason = chunk["choices"][0].get("finish_reason")
                                if finish_reason:
                                    duration_ms = int((time.time() - start_time) * 1000)
                                    # Handle null usage from OpenAI (can be null in streaming)
                                    usage = final_usage or chunk.get("usage") or {}

                                    logger.info(
                                        "ChatGPT-5 streaming completed",
                                        extra={
                                            "provider": "chatgpt-5",
                                            "duration_ms": duration_ms,
                                            "token_count": token_count,
                                            "finish_reason": finish_reason,
                                            "tool_calls_count": len(streaming_tool_calls)
                                        }
                                    )

                                    # Handle tool calls
                                    if finish_reason == "tool_calls" and streaming_tool_calls:
                                        # Convert streaming tool calls to list
                                        tool_calls_list = [streaming_tool_calls[i] for i in sorted(streaming_tool_calls.keys())]
                                        tool_results = []

                                        for tc in tool_calls_list:
                                            tool_name = tc["function"]["name"]
                                            tool_call_id = tc["id"]

                                            try:
                                                args = json.loads(tc["function"]["arguments"]) if tc["function"]["arguments"] else {}
                                            except json.JSONDecodeError:
                                                args = {}

                                            # Emit tool_call_started
                                            yield {
                                                "type": "tool_call_started",
                                                "tool": tool_name,
                                                "arguments": args
                                            }

                                            # Execute tool if MCP client available
                                            if mcp_client:
                                                try:
                                                    result = await mcp_client.call_tool(tool_name, args)
                                                    result_str = json.dumps(result) if isinstance(result, (dict, list)) else str(result)

                                                    # Emit tool_call_completed
                                                    yield {
                                                        "type": "tool_call_completed",
                                                        "tool": tool_name,
                                                        "result_summary": result_str[:200] + "..." if len(result_str) > 200 else result_str
                                                    }

                                                    tool_results.append({
                                                        "tool_call_id": tool_call_id,
                                                        "content": result_str
                                                    })
                                                except Exception as e:
                                                    error_msg = str(e)
                                                    logger.error(
                                                        "ChatGPT-5 tool execution failed",
                                                        extra={
                                                            "provider": "chatgpt-5",
                                                            "tool": tool_name,
                                                            "error": error_msg
                                                        }
                                                    )

                                                    # Emit tool_call_failed
                                                    yield {
                                                        "type": "tool_call_failed",
                                                        "tool": tool_name,
                                                        "error": error_msg
                                                    }

                                                    tool_results.append({
                                                        "tool_call_id": tool_call_id,
                                                        "content": f"Error: {error_msg}"
                                                    })
                                            else:
                                                # No MCP client, return error
                                                yield {
                                                    "type": "tool_call_failed",
                                                    "tool": tool_name,
                                                    "error": "MCP client not available"
                                                }
                                                tool_results.append({
                                                    "tool_call_id": tool_call_id,
                                                    "content": "Error: Tool execution not available"
                                                })

                                        # Yield pending tool calls for conversation continuation
                                        yield {
                                            "type": "tool_calls_pending",
                                            "tool_calls": tool_calls_list,
                                            "tool_results": tool_results
                                        }
                                        return

                                    # Track LLM generation in Langfuse (fire-and-forget)
                                    if trace:
                                        try:
                                            # Extract token usage
                                            prompt_tokens = usage.get("prompt_tokens", 0)
                                            completion_tokens = usage.get("completion_tokens", token_count)
                                            total_tokens = prompt_tokens + completion_tokens

                                            # Calculate costs
                                            cost_info = calculate_llm_cost(
                                                provider="chatgpt-5",
                                                prompt_tokens=prompt_tokens,
                                                completion_tokens=completion_tokens,
                                                sources_used=0
                                            )

                                            # Prepare prompt and completion (truncated)
                                            prompt_text = json.dumps([m for m in messages if m.get("role") != "tool"])
                                            truncated_prompt = self._truncate_text(prompt_text, 1000)
                                            full_completion = "".join(accumulated_content)
                                            truncated_completion = self._truncate_text(full_completion, 1000)

                                            # Create Langfuse generation and end it with usage including costs
                                            generation = trace.generation(
                                                name="llm_call_chatgpt-5_streaming",
                                                input=truncated_prompt,
                                                model=self.MODEL_NAME,
                                                metadata={
                                                    "provider": "chatgpt-5",
                                                    "streaming": True
                                                }
                                            )

                                            generation.end(
                                                output=truncated_completion,
                                                usage={
                                                    "input": prompt_tokens,
                                                    "output": completion_tokens,
                                                    "total": total_tokens,
                                                    "input_cost": cost_info.get("input_cost", 0),
                                                    "output_cost": cost_info.get("output_cost", 0),
                                                    "total_cost": cost_info.get("total_cost", 0)
                                                },
                                                metadata={
                                                    "duration_ms": duration_ms
                                                }
                                            )

                                            logger.info(
                                                "Langfuse generation tracked successfully",
                                                extra={
                                                    "provider": "chatgpt-5",
                                                    "prompt_tokens": prompt_tokens,
                                                    "completion_tokens": completion_tokens,
                                                    "cost_usd": cost_info.get("total_cost", 0)
                                                }
                                            )
                                        except Exception as e:
                                            # Fire-and-forget: log but don't fail stream
                                            logger.warning(
                                                f"Failed to track ChatGPT-5 streaming generation in Langfuse: {str(e)}",
                                                extra={"provider": "chatgpt-5", "error": str(e)}
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
                                "Failed to parse ChatGPT-5 streaming chunk",
                                extra={
                                    "provider": "chatgpt-5",
                                    "line": data_str[:100],
                                    "error": str(e)
                                }
                            )
                            continue

        except httpx.TimeoutException as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "ChatGPT-5 streaming timeout",
                extra={
                    "provider": "chatgpt-5",
                    "duration_ms": duration_ms,
                    "timeout": self.streaming_timeout
                }
            )
            raise ProviderError("chatgpt-5", "Streaming timeout", e)

        except httpx.NetworkError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.warning(
                "ChatGPT-5 streaming network error",
                extra={
                    "provider": "chatgpt-5",
                    "duration_ms": duration_ms,
                    "error": str(e)
                }
            )
            raise ProviderError("chatgpt-5", "Network error during streaming", e)

        except RateLimitError:
            # Re-raise rate limit errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected ChatGPT-5 streaming error",
                extra={
                    "provider": "chatgpt-5",
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise ProviderError("chatgpt-5", f"Unexpected streaming error: {type(e).__name__}", e)

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to max_length, adding ellipsis if truncated."""
        if len(text) <= max_length:
            return text
        return text[:max_length - 3] + "..."
