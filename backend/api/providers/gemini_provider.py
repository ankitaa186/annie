"""
Gemini 3 Pro Provider

Implementation of Gemini 3 Pro (Google AI API) provider with streaming support,
safety filter handling, function calling, and Langfuse tracing integration.
"""

import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from api.config import get_config
from api.logging import get_logger
from api.providers.base import BaseProvider
from api.providers.gemini_tool_adapter import GeminiToolAdapter
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


class GeminiProvider(BaseProvider):
    """
    Gemini 3 Pro (Google AI API) provider implementation.

    Features:
    - Streaming chat completion with function calling
    - Message format conversion (OpenAI → Gemini)
    - Safety filter handling (4 harm categories)
    - Quota and rate limit handling
    - Cost calculation with tiered pricing
    - Langfuse tracing integration (fire-and-forget)
    """

    # Gemini 3 Pro API configuration
    MODEL_NAME = "gemini-3-pro-preview"

    # Safety filter user-friendly messages
    SAFETY_MESSAGES = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: "I cannot respond due to content policy. Please rephrase.",
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: "I cannot respond due to content policy. Please rephrase.",
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: "I cannot respond due to content policy. Please rephrase.",
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: "I cannot respond due to content policy. Please rephrase.",
    }

    def __init__(self):
        """
        Initialize Gemini 3 Pro provider with configuration from environment.

        Raises:
            ValueError: If GEMINI_API_KEY is not configured
        """
        config = get_config()

        # Get API key
        self.api_key = config.get("GEMINI_API_KEY")
        if not self.api_key or self.api_key == "REPLACE_ME":
            raise ValueError("GEMINI_API_KEY not configured")

        # Load configuration from environment
        self.model_name = config.get("GEMINI_MODEL", self.MODEL_NAME)
        self.max_output_tokens = int(config.get("GEMINI_MAX_OUTPUT_TOKENS", "8192"))
        self.temperature = float(config.get("GEMINI_TEMPERATURE", "1.0"))
        self.context_cache_ttl = int(config.get("GEMINI_CONTEXT_CACHE_TTL", "300"))

        # Load safety setting (default: BLOCK_NONE for minimal filtering)
        safety_setting_str = config.get("GEMINI_SAFETY_SETTING", "BLOCK_NONE")
        self.safety_setting = self._parse_safety_setting(safety_setting_str)

        # Configure Gemini API
        genai.configure(api_key=self.api_key)

        # Create model instance
        self.model = genai.GenerativeModel(
            model_name=self.model_name,
            generation_config={
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
            },
            safety_settings=self._get_safety_settings()
        )

        # Initialize tool adapter for function calling (Story 9.3)
        self.tool_adapter = GeminiToolAdapter()

        # Load max tool iterations from config (prevent infinite loops)
        self.max_tool_iterations = int(config.get("GEMINI_MAX_TOOL_ITERATIONS", "5"))

        logger.info(
            "Gemini 3 Pro provider initialized",
            extra={
                "provider": "gemini-3-pro-preview",
                "model": self.model_name,
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
                "safety_setting": safety_setting_str,
                "max_tool_iterations": self.max_tool_iterations
            }
        )

    def _parse_safety_setting(self, setting_str: str) -> HarmBlockThreshold:
        """
        Parse safety setting string to HarmBlockThreshold enum.

        Args:
            setting_str: Safety setting string

        Returns:
            HarmBlockThreshold enum value
        """
        setting_map = {
            "BLOCK_NONE": HarmBlockThreshold.BLOCK_NONE,
            "BLOCK_ONLY_HIGH": HarmBlockThreshold.BLOCK_ONLY_HIGH,
            "BLOCK_MEDIUM_AND_ABOVE": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            "BLOCK_LOW_AND_ABOVE": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        }
        return setting_map.get(setting_str, HarmBlockThreshold.BLOCK_NONE)

    def _get_safety_settings(self) -> Dict[HarmCategory, HarmBlockThreshold]:
        """
        Get safety settings for all harm categories.

        Returns:
            Dictionary mapping harm categories to thresholds
        """
        return {
            HarmCategory.HARM_CATEGORY_HARASSMENT: self.safety_setting,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: self.safety_setting,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: self.safety_setting,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: self.safety_setting,
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        # Gemini SDK doesn't require explicit cleanup
        pass

    async def close(self):
        """Close provider resources (no-op for Gemini)."""
        # Gemini SDK handles cleanup internally
        pass

    def get_provider_name(self) -> str:
        """Return provider name."""
        return "gemini-3-pro-preview"

    def calculate_cost(self, usage: Dict[str, int]) -> Dict[str, float]:
        """
        Calculate cost for Gemini 3 Pro usage.

        Args:
            usage: Token usage with keys:
                - prompt_tokens: Input tokens
                - completion_tokens: Output tokens
                - cached_tokens: Cached input tokens (optional)

        Returns:
            Cost details dictionary
        """
        return calculate_llm_cost(
            provider="gemini-3-pro-preview",
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            sources_used=0,  # Gemini doesn't have live search
            cached_tokens=usage.get("cached_tokens", 0)
        )

    def _convert_messages_to_gemini_format(
        self, messages: List[Dict[str, Any]]
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """
        Convert OpenAI-format messages to Gemini format.

        OpenAI format: [{"role": "user", "content": "..."}]
        Gemini format: [{"role": "user", "parts": [{"text": "..."}]}]

        Role mapping:
        - user → user
        - assistant → model
        - system → prepended to first user message (Gemini has no native system role)

        Args:
            messages: List of OpenAI-format messages

        Returns:
            Tuple of (system_instruction, converted_messages)
        """
        system_instruction = None
        converted_messages = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                # Gemini doesn't have native system role - extract for system_instruction
                system_instruction = content
            elif role == "user":
                converted_messages.append({
                    "role": "user",
                    "parts": [{"text": content}]
                })
            elif role == "assistant":
                # Map assistant → model for Gemini
                converted_messages.append({
                    "role": "model",
                    "parts": [{"text": content}]
                })
            elif role == "tool":
                # Tool results (function calling)
                converted_messages.append({
                    "role": "user",
                    "parts": [{"text": f"Tool result: {content}"}]
                })

        return system_instruction, converted_messages

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from Gemini 3 Pro with tool calling support.

        Implements multi-turn function calling with thought_signature preservation (Story 9.3).

        Args:
            messages: List of message dictionaries (OpenAI format)
            tools: Optional list of tools in OpenAI format for function calling
            **kwargs: Additional parameters:
                - mcp_client: MCP client for tool execution (required if tools provided)

        Yields:
            Stream event dictionaries (OpenAI-compatible format):
            - {"type": "token", "content": "text"}
            - {"type": "tool_call_started", "tool": "name", "arguments": {...}}
            - {"type": "tool_call_completed", "tool": "name", "result_summary": "..."}
            - {"type": "tool_call_failed", "tool": "name", "error": "..."}
            - {"type": "done", "tokens_used": {"prompt": N, "completion": M}}

        Raises:
            ProviderError: If provider call fails
            RateLimitError: If rate limit is hit
        """
        start_time = time.time()

        try:
            # Convert messages to Gemini format
            system_instruction, gemini_messages = self._convert_messages_to_gemini_format(messages)

            # Convert tools to Gemini format if provided (Story 9.3)
            gemini_tools = None
            mcp_client = kwargs.get("mcp_client")

            if tools:
                gemini_tools = self.tool_adapter.convert_openai_to_gemini_schema(tools)
                logger.info(
                    "Converted MCP tools to Gemini format",
                    extra={
                        "provider": "gemini-3-pro-preview",
                        "tool_count": len(gemini_tools)
                    }
                )

            # Log request
            logger.info(
                "Starting Gemini 3 Pro streaming request",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "model": self.model_name,
                    "message_count": len(messages),
                    "has_system_instruction": system_instruction is not None,
                    "tool_count": len(gemini_tools) if gemini_tools else 0
                }
            )

            # Track metrics
            first_token = True
            first_token_time = None
            token_count = 0
            accumulated_content = []

            # Get current trace for Langfuse
            trace = get_current_trace()

            # Multi-turn tool calling loop (Story 9.3)
            # Use ChatSession API for automatic thought_signature handling
            tool_iteration = 0

            # Initialize ChatSession with history (all messages except the last user message)
            # The last user message will be sent via send_message()
            history = gemini_messages[:-1] if len(gemini_messages) > 1 else []
            last_user_message = gemini_messages[-1]["parts"][0]["text"] if gemini_messages else ""

            # CRITICAL: Prepend system_instruction to history if provided
            # Gemini doesn't have native system role, so we inject it into first user message
            if system_instruction and history:
                # Find first user message in history and prepend system instruction
                for msg in history:
                    if msg.get("role") == "user" and msg.get("parts"):
                        msg["parts"][0]["text"] = f"{system_instruction}\n\n{msg['parts'][0]['text']}"
                        logger.debug(
                            "Prepended system instruction to first user message in history",
                            extra={"provider": "gemini-3-pro-preview"}
                        )
                        break
            elif system_instruction and not history:
                # No history, prepend to last_user_message instead
                last_user_message = f"{system_instruction}\n\n{last_user_message}"
                logger.debug(
                    "Prepended system instruction to first user message",
                    extra={"provider": "gemini-3-pro-preview"}
                )

            # Build tool configuration
            tools_config = None
            if gemini_tools:
                tools_config = [{"function_declarations": gemini_tools}]

            # Start chat session with history
            chat = self.model.start_chat(history=history)

            logger.debug(
                "Initialized ChatSession for automatic thought_signature handling",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "history_length": len(history),
                    "has_tools": tools_config is not None
                }
            )

            while tool_iteration < self.max_tool_iterations:
                # Generate streaming response using ChatSession
                try:
                    # Build generation config
                    generation_config = {}

                    # Send message with streaming
                    # Note: system_instruction is handled at model initialization, not per-message
                    # On first iteration: send user message (string)
                    # On subsequent iterations: send function response (dict with parts)
                    response = chat.send_message(
                        last_user_message,
                        stream=True,
                        tools=tools_config
                    )

                    # Track if we found a function call in this iteration
                    function_call_detected = False
                    function_call_name = None
                    function_call_args = None

                    # Process chunks
                    # Note: thought_signatures are handled automatically by ChatSession (Story 9.3)
                    for chunk in response:

                        # Check for safety blocks
                        if hasattr(chunk, 'prompt_feedback') and chunk.prompt_feedback.block_reason:
                            # Safety filter blocked the prompt
                            block_reason = chunk.prompt_feedback.block_reason
                            logger.warning(
                                "Gemini safety filter blocked prompt",
                                extra={
                                    "provider": "gemini-3-pro-preview",
                                    "block_reason": str(block_reason)
                                }
                            )
                            yield {
                                "type": "error",
                                "message": "I cannot respond due to content policy. Please rephrase your question.",
                                "code": "SAFETY_FILTER_BLOCKED"
                            }
                            return

                        # Extract content from chunk
                        if chunk.candidates and len(chunk.candidates) > 0:
                            candidate = chunk.candidates[0]

                            # Check for safety block in candidate
                            if candidate.finish_reason and "SAFETY" in str(candidate.finish_reason):
                                # Get harm category if available
                                harm_category = None
                                if hasattr(candidate, 'safety_ratings') and candidate.safety_ratings:
                                    for rating in candidate.safety_ratings:
                                        if rating.blocked:
                                            harm_category = rating.category
                                            break

                                safety_msg = self.SAFETY_MESSAGES.get(
                                    harm_category,
                                    "I cannot respond due to content policy. Please rephrase."
                                )

                                logger.warning(
                                    "Gemini safety filter blocked response",
                                    extra={
                                        "provider": "gemini-3-pro-preview",
                                        "finish_reason": str(candidate.finish_reason),
                                        "harm_category": str(harm_category) if harm_category else None
                                    }
                                )

                                yield {
                                    "type": "error",
                                    "message": safety_msg,
                                    "code": "SAFETY_FILTER_BLOCKED"
                                }
                                return

                            # Extract content (text or function_call)
                            if candidate.content and candidate.content.parts:
                                for part in candidate.content.parts:
                                    # Check for function call (Story 9.3)
                                    if hasattr(part, 'function_call') and part.function_call:
                                        function_call_detected = True
                                        function_call_name = part.function_call.name
                                        # Convert args to JSON-serializable format
                                        # dict() alone doesn't handle nested RepeatedComposite objects
                                        function_call_args = json.loads(json.dumps(dict(part.function_call.args), default=str))

                                        # ChatSession handles thought_signatures automatically
                                        logger.info(
                                            "Gemini function call detected",
                                            extra={
                                                "provider": "gemini-3-pro-preview",
                                                "tool_name": function_call_name,
                                                "iteration": tool_iteration
                                            }
                                        )

                                        # Emit tool_call_started event
                                        yield {
                                            "type": "tool_call_started",
                                            "tool": function_call_name,
                                            "arguments": function_call_args
                                        }

                                    # Extract text content (can co-exist with function_call)
                                    if hasattr(part, 'text') and part.text:
                                        content = part.text

                                        # Track first token latency
                                        if first_token:
                                            first_token_time = time.time()
                                            first_token_latency_ms = int((first_token_time - start_time) * 1000)
                                            logger.info(
                                                "Gemini 3 Pro first token received",
                                                extra={
                                                    "provider": "gemini-3-pro-preview",
                                                    "latency_ms": first_token_latency_ms
                                                }
                                            )
                                            first_token = False

                                        token_count += 1
                                        accumulated_content.append(content)

                                        # Yield token in OpenAI-compatible SSE format
                                        yield {
                                            "type": "token",
                                            "content": content
                                        }

                            # Check for finish reason (completion or function call)
                            if candidate.finish_reason:
                                finish_reason_str = str(candidate.finish_reason)

                                # If STOP and no function call, we're done
                                if "STOP" in finish_reason_str and not function_call_detected:
                                    duration_ms = int((time.time() - start_time) * 1000)

                                    logger.info(
                                        "Gemini 3 Pro streaming completed",
                                        extra={
                                            "provider": "gemini-3-pro-preview",
                                            "duration_ms": duration_ms,
                                            "token_count": token_count,
                                            "finish_reason": finish_reason_str,
                                            "tool_iterations": tool_iteration
                                        }
                                    )

                                    # Get token counts
                                    prompt_tokens = 0
                                    completion_tokens = token_count

                                    try:
                                        prompt_tokens = self.model.count_tokens(gemini_messages).total_tokens
                                    except Exception as e:
                                        logger.warning(f"Failed to count prompt tokens: {str(e)}")

                                    # Track in Langfuse (fire-and-forget)
                                    if trace:
                                        try:
                                            cost_details = self.calculate_cost({
                                                "prompt_tokens": prompt_tokens,
                                                "completion_tokens": completion_tokens,
                                                "cached_tokens": 0
                                            })

                                            prompt_text = json.dumps([m for m in messages if m.get("role") != "tool"])
                                            truncated_prompt = self._truncate_text(prompt_text, 1000)
                                            full_completion = "".join(accumulated_content)
                                            truncated_completion = self._truncate_text(full_completion, 1000)

                                            trace.generation(
                                                name="llm_call_gemini-3-pro-preview_streaming",
                                                input=truncated_prompt,
                                                output=truncated_completion,
                                                model=self.model_name,
                                                metadata={
                                                    "provider": "gemini-3-pro-preview",
                                                    "duration_ms": duration_ms,
                                                    "streaming": True,
                                                    "safety_setting": str(self.safety_setting),
                                                    "tool_iterations": tool_iteration
                                                },
                                                usage={
                                                    "input": prompt_tokens,
                                                    "output": completion_tokens,
                                                    "total": prompt_tokens + completion_tokens,
                                                    "unit": "TOKENS"
                                                },
                                                usage_details=cost_details
                                            )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to track Gemini streaming in Langfuse: {str(e)}",
                                                extra={"provider": "gemini-3-pro-preview"}
                                            )

                                    # Yield completion event
                                    yield {
                                        "type": "done",
                                        "tokens_used": {
                                            "prompt": prompt_tokens,
                                            "completion": completion_tokens
                                        }
                                    }
                                    return  # Exit the multi-turn loop

                    # After chunk processing, check if we need to execute a tool
                    if function_call_detected and mcp_client:
                        # Execute tool via MCP client
                        tool_result = await self._execute_tool_call(
                            function_call_name,
                            function_call_args,
                            mcp_client
                        )

                        # Check if tool execution succeeded or failed
                        if "error" in tool_result:
                            # Emit tool_call_failed event
                            yield {
                                "type": "tool_call_failed",
                                "tool": function_call_name,
                                "error": tool_result.get("error", "Unknown error")
                            }
                        else:
                            # Emit tool_call_completed event
                            result_summary = str(tool_result)[:200] if tool_result else ""
                            yield {
                                "type": "tool_call_completed",
                                "tool": function_call_name,
                                "result_summary": result_summary
                            }

                        # With ChatSession, thought_signatures are preserved automatically
                        # We just need to format the tool response and continue the loop
                        # Reference: https://ai.google.dev/gemini-api/docs/thought-signatures

                        # Format function response for Gemini
                        formatted_result = self.tool_adapter.format_tool_result_for_gemini(
                            function_call_name,
                            tool_result
                        )

                        # ChatSession automatically includes the function call and preserves thought_signatures
                        # Send the function response as a Part with functionResponse
                        # The SDK expects a list of parts for multi-part messages
                        from google.ai import generativelanguage as glm

                        last_user_message = [
                            glm.Part(function_response=glm.FunctionResponse(
                                name=formatted_result["name"],
                                response=formatted_result["response"]
                            ))
                        ]

                        # Increment iteration and continue loop
                        tool_iteration += 1
                        logger.info(
                            "Tool execution completed, continuing multi-turn loop with ChatSession",
                            extra={
                                "provider": "gemini-3-pro-preview",
                                "tool": function_call_name,
                                "iteration": tool_iteration
                            }
                        )

                    elif function_call_detected and not mcp_client:
                        # No MCP client provided but function call detected
                        logger.error(
                            "Function call detected but no MCP client provided",
                            extra={"provider": "gemini-3-pro-preview", "tool": function_call_name}
                        )
                        yield {
                            "type": "tool_call_failed",
                            "tool": function_call_name,
                            "error": "MCP client not provided to execute tools"
                        }
                        return

                    elif not function_call_detected:
                        # No function call, but also no STOP - unexpected
                        logger.warning(
                            "Streaming ended without STOP or function call",
                            extra={"provider": "gemini-3-pro-preview"}
                        )
                        return

                except Exception as e:
                    # Check for quota/rate limit errors
                    error_str = str(e).lower()
                    if "quota" in error_str or "resource exhausted" in error_str or "429" in error_str:
                        logger.warning(
                            "Gemini quota/rate limit exceeded",
                            extra={
                                "provider": "gemini-3-pro-preview",
                                "error": str(e)
                            }
                        )
                        raise RateLimitError("gemini-3-pro-preview", retry_after=None)

                    # Re-raise as ProviderError
                    raise ProviderError("gemini-3-pro-preview", f"Streaming error: {str(e)}", e)

            # If we exit the loop due to max iterations, log warning
            if tool_iteration >= self.max_tool_iterations:
                logger.warning(
                    "Max tool iterations reached",
                    extra={
                        "provider": "gemini-3-pro-preview",
                        "max_iterations": self.max_tool_iterations
                    }
                )
                yield {
                    "type": "error",
                    "message": "Maximum tool calling iterations reached. Please simplify your request.",
                    "code": "MAX_ITERATIONS_EXCEEDED"
                }
                return

        except RateLimitError:
            # Re-raise rate limit errors as-is
            raise

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error(
                "Unexpected Gemini streaming error",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise ProviderError("gemini-3-pro-preview", f"Unexpected streaming error: {type(e).__name__}", e)

    async def _execute_tool_call(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        mcp_client
    ) -> Dict[str, Any]:
        """
        Execute MCP tool and handle errors gracefully.

        Args:
            tool_name: Name of the tool to execute
            tool_arguments: Tool arguments
            mcp_client: MCP client instance

        Returns:
            Tool execution result (or error response)
        """
        try:
            # Import MCPClient locally to avoid circular dependency
            from api.mcp_client import MCPClient, MCPNetworkError, MCPToolError

            logger.info(
                "Executing MCP tool for Gemini",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "tool_name": tool_name,
                    "arguments": tool_arguments
                }
            )

            # Execute tool via MCP client
            result = await mcp_client.call_tool(tool_name, tool_arguments)

            logger.info(
                "MCP tool execution completed successfully",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "tool_name": tool_name
                }
            )

            return result

        except MCPNetworkError as e:
            # MCP server unreachable - graceful error
            logger.warning(
                "MCP server unreachable during Gemini tool call",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "tool_name": tool_name,
                    "error": str(e)
                }
            )
            return {
                "error": "Tool unavailable, please continue without it",
                "status": "error",
                "tool": tool_name
            }

        except MCPToolError as e:
            # Tool execution failed - graceful error
            logger.warning(
                "MCP tool execution failed during Gemini call",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "tool_name": tool_name,
                    "error": str(e)
                }
            )
            return {
                "error": f"Tool execution failed: {e.message}",
                "status": "error",
                "tool": tool_name
            }

        except Exception as e:
            # Unexpected error
            logger.error(
                "Unexpected error during Gemini tool execution",
                extra={
                    "provider": "gemini-3-pro-preview",
                    "tool_name": tool_name,
                    "error": str(e)
                },
                exc_info=True
            )
            return {
                "error": f"Unexpected tool error: {str(e)}",
                "status": "error",
                "tool": tool_name
            }
