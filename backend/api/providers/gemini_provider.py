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
from api.providers.grok_provider import ProviderError, RateLimitError
from api.providers.gemini_tool_adapter import GeminiToolAdapter
from api.observability.tracing import get_current_trace
from api.observability.cost import calculate_llm_cost

logger = get_logger(__name__)


class GeminiProvider(BaseProvider):
    """
    Gemini (Google AI API) provider implementation.

    Features:
    - Streaming chat completion with function calling
    - Message format conversion (OpenAI → Gemini)
    - Safety filter handling (4 harm categories)
    - Quota and rate limit handling
    - Cost calculation with tiered pricing
    - Langfuse tracing integration (fire-and-forget)
    - Supports multiple Gemini models (gemini-3-pro-preview, gemini-2.5-pro, etc.)
    """

    # Default Gemini model
    DEFAULT_MODEL = "gemini-3-pro-preview"

    # Supported Gemini models
    SUPPORTED_MODELS = ["gemini-3-pro-preview", "gemini-3-flash-preview", "gemini-2.5-pro"]

    # Safety filter user-friendly messages
    SAFETY_MESSAGES = {
        HarmCategory.HARM_CATEGORY_HARASSMENT: "I cannot respond due to content policy. Please rephrase.",
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: "I cannot respond due to content policy. Please rephrase.",
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: "I cannot respond due to content policy. Please rephrase.",
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: "I cannot respond due to content policy. Please rephrase.",
    }

    def __init__(self, model_override: Optional[str] = None):
        """
        Initialize Gemini provider with configuration from environment.

        Args:
            model_override: Optional model name to use instead of env config.
                           Useful for fallback scenarios (e.g., gemini-2.5-pro fallback)

        Raises:
            ValueError: If GEMINI_API_KEY is not configured
        """
        config = get_config()

        # Get API key
        self.api_key = config.get("GEMINI_API_KEY")
        if not self.api_key or self.api_key == "REPLACE_ME":
            raise ValueError("GEMINI_API_KEY not configured")

        # Load configuration from environment, with optional override
        if model_override:
            self.model_name = model_override
        else:
            self.model_name = config.get("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.max_output_tokens = int(config.get("GEMINI_MAX_OUTPUT_TOKENS", "16384"))
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
        self.max_tool_iterations = int(config.get("GEMINI_MAX_TOOL_ITERATIONS", "20"))

        logger.info(
            "Gemini 3 Pro provider initialized",
            extra={
                "provider": self.model_name,
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

    def _normalize_model_name(self, model_name: str) -> str:
        """
        Normalize model name by removing 'models/' prefix if present.

        The Gemini SDK uses full paths like 'models/gemini-3-pro-preview',
        but the cost calculator expects just 'gemini-3-pro-preview'.
        """
        if model_name.startswith("models/"):
            return model_name[7:]  # Remove 'models/' prefix
        return model_name

    def get_provider_name(self) -> str:
        """Return provider name (model identifier without 'models/' prefix)."""
        return self._normalize_model_name(self.model_name)

    def calculate_cost(self, usage: Dict[str, int]) -> Dict[str, float]:
        """
        Calculate cost for Gemini usage.

        Args:
            usage: Token usage with keys:
                - prompt_tokens: Input tokens
                - completion_tokens: Output tokens
                - cached_tokens: Cached input tokens (optional)

        Returns:
            Cost details dictionary
        """
        return calculate_llm_cost(
            provider=self._normalize_model_name(self.model_name),
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            sources_used=0,  # Gemini doesn't have live search
            cached_tokens=usage.get("cached_tokens", 0)
        )

    def _convert_messages_to_gemini_format(
        self, messages: List[Dict[str, Any]], files: Optional[List] = None
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """
        Convert OpenAI-format messages to Gemini format with optional file attachments.

        OpenAI format: [{"role": "user", "content": "..."}]
        Gemini format: [{"role": "user", "parts": [{"text": "..."}, {"inline_data": {...}}]}]

        Role mapping:
        - user → user
        - assistant → model
        - system → prepended to first user message (Gemini has no native system role)

        Args:
            messages: List of OpenAI-format messages
            files: Optional list of FileAttachment objects for multimodal processing

        Returns:
            Tuple of (system_instruction, converted_messages)
        """
        system_instruction = None
        converted_messages = []

        # Convert all messages (files will be attached to last user message at the end)
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")

            if role == "system":
                # Gemini doesn't have native system role - extract for system_instruction
                system_instruction = content
            elif role == "user":
                # Build parts array with text only (files added to last user message below)
                parts = [{"text": content}]
                converted_messages.append({
                    "role": "user",
                    "parts": parts
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

        # Attach files to the LAST user message (current message, not history)
        if files and converted_messages:
            # Find the last user message and attach files to it
            for i in range(len(converted_messages) - 1, -1, -1):
                if converted_messages[i].get("role") == "user":
                    for file in files:
                        converted_messages[i]["parts"].append({
                            "inline_data": {
                                "mime_type": file.mime_type,
                                "data": file.data_base64
                            }
                        })
                    logger.info(
                        "Files attached to last user message for Gemini",
                        extra={
                            "file_count": len(files),
                            "mime_types": [f.mime_type for f in files],
                            "total_size_bytes": sum(f.size_bytes for f in files),
                            "message_index": i,
                            "event": "gemini_multimodal_request"
                        }
                    )
                    break

        return system_instruction, converted_messages

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from Gemini 3 Pro with tool calling and multimodal support.

        Implements multi-turn function calling with thought_signature preservation (Story 9.3).
        Supports multimodal inputs (images, documents, spreadsheets) via inline_data (Story 18.2).

        Args:
            messages: List of message dictionaries (OpenAI format)
            tools: Optional list of tools in OpenAI format for function calling
            **kwargs: Additional parameters:
                - mcp_client: MCP client for tool execution (required if tools provided)
                - files: Optional list of FileAttachment objects for multimodal processing

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
        files = kwargs.get("files")  # Extract files from kwargs
        user_id = kwargs.get("user_id")  # Extract user_id for tool argument injection

        try:
            # Convert messages to Gemini format with optional file attachments
            system_instruction, gemini_messages = self._convert_messages_to_gemini_format(messages, files)

            # Convert tools to Gemini format if provided (Story 9.3)
            gemini_tools = None
            mcp_client = kwargs.get("mcp_client")

            if tools:
                gemini_tools = self.tool_adapter.convert_openai_to_gemini_schema(tools)
                logger.info(
                    "Converted MCP tools to Gemini format",
                    extra={
                        "provider": self.model_name,
                        "tool_count": len(gemini_tools)
                    }
                )

            # Log request with last user message for debugging
            last_user_msg = None
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_msg = msg.get("content", "")[:200]
                    break

            logger.info(
                "Starting Gemini 3 Pro streaming request",
                extra={
                    "provider": self.model_name,
                    "model": self.model_name,
                    "message_count": len(messages),
                    "has_system_instruction": system_instruction is not None,
                    "tool_count": len(gemini_tools) if gemini_tools else 0,
                    "last_user_message": last_user_msg,
                    "has_files": files is not None,
                    "file_count": len(files) if files else 0,
                    "event": "gemini_multimodal_stream" if files else "gemini_text_stream"
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

            # Extract the last user message parts for send_message()
            # For multimodal requests, we need to send the full parts array (text + inline_data)
            # For text-only, we can send just the text string
            if gemini_messages:
                last_parts = gemini_messages[-1].get("parts", [])
                # Check if this is multimodal (has inline_data parts)
                has_files = any("inline_data" in part for part in last_parts)
                if has_files:
                    # Send full parts array for multimodal
                    last_user_message = last_parts
                else:
                    # Send just text for text-only (backward compatible)
                    last_user_message = last_parts[0]["text"] if last_parts else ""
            else:
                last_user_message = ""

            # CRITICAL: Prepend system_instruction to history if provided
            # Gemini doesn't have native system role, so we inject it into first user message
            if system_instruction and history:
                # Find first user message in history and prepend system instruction
                for msg in history:
                    if msg.get("role") == "user" and msg.get("parts"):
                        msg["parts"][0]["text"] = f"{system_instruction}\n\n{msg['parts'][0]['text']}"
                        logger.debug(
                            "Prepended system instruction to first user message in history",
                            extra={"provider": self.model_name}
                        )
                        break
            elif system_instruction and not history:
                # No history, prepend to last_user_message instead
                # Handle both string (text-only) and list (multimodal) formats
                if isinstance(last_user_message, list):
                    # Multimodal: prepend to text part
                    for part in last_user_message:
                        if "text" in part:
                            part["text"] = f"{system_instruction}\n\n{part['text']}"
                            break
                else:
                    # Text-only: prepend to string
                    last_user_message = f"{system_instruction}\n\n{last_user_message}"
                logger.debug(
                    "Prepended system instruction to first user message",
                    extra={"provider": self.model_name}
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
                    "provider": self.model_name,
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

                    # Track ALL function calls in this iteration (parallel tool calling support)
                    function_calls = []  # List of {name, args} dicts

                    # Debug: Track raw chunk data for MALFORMED_FUNCTION_CALL diagnosis
                    raw_chunk_data = []  # Accumulate for debugging if needed

                    # Process chunks
                    # Note: thought_signatures are handled automatically by ChatSession (Story 9.3)
                    for chunk in response:
                        # Debug: Capture raw chunk structure for diagnosing MALFORMED_FUNCTION_CALL
                        try:
                            chunk_info = {
                                "has_candidates": bool(chunk.candidates),
                                "candidate_count": len(chunk.candidates) if chunk.candidates else 0
                            }
                            if chunk.candidates and len(chunk.candidates) > 0:
                                cand = chunk.candidates[0]
                                chunk_info["finish_reason"] = str(cand.finish_reason) if cand.finish_reason else None
                                chunk_info["finish_reason_value"] = int(cand.finish_reason) if cand.finish_reason else None
                                chunk_info["has_content"] = bool(cand.content)
                                if cand.content:
                                    chunk_info["has_parts"] = bool(cand.content.parts)
                                    chunk_info["part_count"] = len(cand.content.parts) if cand.content.parts else 0
                                    # Capture part types and any function call info
                                    part_details = []
                                    if cand.content.parts:
                                        for part in cand.content.parts:
                                            part_info = {"has_text": hasattr(part, 'text') and bool(part.text)}
                                            if hasattr(part, 'function_call') and part.function_call:
                                                # Capture raw function call info before any conversion
                                                part_info["has_function_call"] = True
                                                part_info["function_name"] = getattr(part.function_call, 'name', 'UNKNOWN')
                                                # Try to get raw args as string to avoid conversion errors
                                                try:
                                                    part_info["function_args_raw"] = str(part.function_call.args)[:500]
                                                except Exception as args_err:
                                                    part_info["function_args_error"] = str(args_err)
                                            else:
                                                part_info["has_function_call"] = False
                                            part_details.append(part_info)
                                    chunk_info["parts"] = part_details
                            raw_chunk_data.append(chunk_info)
                        except Exception as debug_err:
                            raw_chunk_data.append({"debug_capture_error": str(debug_err)})

                        # Check for safety blocks
                        if hasattr(chunk, 'prompt_feedback') and chunk.prompt_feedback.block_reason:
                            # Safety filter blocked the prompt
                            block_reason = chunk.prompt_feedback.block_reason
                            logger.warning(
                                "Gemini safety filter blocked prompt",
                                extra={
                                    "provider": self.model_name,
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
                                        "provider": self.model_name,
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
                                    # Check for function call (Story 9.3) - supports parallel tool calls
                                    if hasattr(part, 'function_call') and part.function_call:
                                        func_name = part.function_call.name
                                        # Convert args to JSON-serializable format
                                        # Need to handle nested protobuf objects recursively

                                        def convert_proto_to_dict(obj):
                                            """Recursively convert protobuf objects to JSON-serializable dict."""
                                            # Import proto.marshal for type checking
                                            try:
                                                from proto.marshal.collections import RepeatedComposite, MapComposite
                                                from proto.marshal.collections.repeated import Repeated
                                                from proto.marshal.collections.maps import MapComposite as MapComp
                                            except ImportError:
                                                RepeatedComposite = type(None)
                                                MapComposite = type(None)
                                                Repeated = type(None)
                                                MapComp = type(None)

                                            # Handle proto.marshal wrapper types
                                            type_name = type(obj).__name__
                                            if 'Repeated' in type_name or 'MapComposite' in type_name:
                                                # Convert proto.marshal collections to list/dict
                                                if 'Repeated' in type_name:
                                                    # It's a list-like proto object
                                                    return [convert_proto_to_dict(item) for item in obj]
                                                elif 'MapComposite' in type_name:
                                                    # It's a dict-like proto object
                                                    return {k: convert_proto_to_dict(v) for k, v in obj.items()}

                                            # Handle normal Python types
                                            if isinstance(obj, dict):
                                                return {k: convert_proto_to_dict(v) for k, v in obj.items()}
                                            elif isinstance(obj, (list, tuple)):
                                                return [convert_proto_to_dict(item) for item in obj]
                                            elif isinstance(obj, (str, int, float, bool, type(None))):
                                                return obj
                                            elif hasattr(obj, '__dict__'):
                                                # This is likely a proto object, try to convert to dict
                                                try:
                                                    return convert_proto_to_dict(dict(obj))
                                                except (TypeError, ValueError):
                                                    # If that fails, use string representation
                                                    return str(obj)
                                            else:
                                                return obj

                                        # Convert the args dict recursively
                                        func_args = convert_proto_to_dict(dict(part.function_call.args))

                                        # Append to list (supports parallel tool calls)
                                        function_calls.append({
                                            "name": func_name,
                                            "args": func_args
                                        })

                                        # ChatSession handles thought_signatures automatically
                                        logger.info(
                                            f"Gemini requesting tool: {func_name}",
                                            extra={
                                                "provider": self.model_name,
                                                "tool_name": func_name,
                                                "iteration": tool_iteration
                                            }
                                        )

                                        # Emit tool_call_started event
                                        yield {
                                            "type": "tool_call_started",
                                            "tool": func_name,
                                            "arguments": func_args
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
                                                    "provider": self.model_name,
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
                                # finish_reason is an enum - check both value and name
                                # glm.Candidate.FinishReason.STOP has value 1
                                finish_reason_value = int(candidate.finish_reason) if candidate.finish_reason else 0
                                finish_reason_name = candidate.finish_reason.name if hasattr(candidate.finish_reason, 'name') else str(candidate.finish_reason)

                                logger.debug(
                                    "Gemini finish reason received",
                                    extra={
                                        "provider": self.model_name,
                                        "finish_reason": finish_reason_name,
                                        "finish_reason_value": finish_reason_value,
                                        "has_function_calls": bool(function_calls),
                                        "token_count": token_count
                                    }
                                )

                                # If STOP (value=1 or name="STOP") and no function calls, we're done
                                is_stop = finish_reason_value == 1 or finish_reason_name == "STOP"
                                if is_stop and not function_calls:
                                    duration_ms = int((time.time() - start_time) * 1000)

                                    logger.info(
                                        "Gemini 3 Pro streaming completed",
                                        extra={
                                            "provider": self.model_name,
                                            "duration_ms": duration_ms,
                                            "token_count": token_count,
                                            "finish_reason": finish_reason_name,
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
                                            cost_info = self.calculate_cost({
                                                "prompt_tokens": prompt_tokens,
                                                "completion_tokens": completion_tokens,
                                                "cached_tokens": 0
                                            })

                                            prompt_text = json.dumps([m for m in messages if m.get("role") != "tool"])
                                            truncated_prompt = self._truncate_text(prompt_text, 1000)
                                            full_completion = "".join(accumulated_content)
                                            truncated_completion = self._truncate_text(full_completion, 1000)

                                            # Create generation and finalize with end()
                                            # Langfuse v2 requires end() to be called for proper tracking
                                            generation = trace.generation(
                                                name=f"llm_call_{self.model_name}_streaming",
                                                input=truncated_prompt,
                                                model=self.model_name,
                                                model_parameters={
                                                    "temperature": self.temperature,
                                                    "max_output_tokens": self.max_output_tokens
                                                },
                                                metadata={
                                                    "provider": self.model_name,
                                                    "streaming": True,
                                                    "safety_setting": str(self.safety_setting),
                                                    "tool_iterations": tool_iteration
                                                }
                                            )

                                            # End the generation with output and usage (includes cost)
                                            # ModelUsage TypedDict: input, output, total, input_cost, output_cost, total_cost
                                            generation.end(
                                                output=truncated_completion,
                                                usage={
                                                    "input": prompt_tokens,
                                                    "output": completion_tokens,
                                                    "total": prompt_tokens + completion_tokens,
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
                                                    "provider": self.model_name,
                                                    "prompt_tokens": prompt_tokens,
                                                    "completion_tokens": completion_tokens,
                                                    "cost_usd": cost_info.get("total_cost", 0)
                                                }
                                            )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to track Gemini streaming in Langfuse: {str(e)}",
                                                extra={"provider": self.model_name, "error": str(e)}
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

                    # After chunk processing, check if we need to execute tools
                    # Supports parallel tool calls - execute ALL function calls
                    if function_calls and mcp_client:
                        tool_count = len(function_calls)
                        tool_names = [fc["name"] for fc in function_calls]

                        # Log parallel tool calls summary
                        if tool_count > 1:
                            logger.info(
                                f"Executing {tool_count} parallel tool calls",
                                extra={
                                    "provider": self.model_name,
                                    "tools": tool_names,
                                    "tool_count": tool_count,
                                    "iteration": tool_iteration
                                }
                            )

                        # Execute ALL tools via MCP client
                        tool_results = []

                        for idx, func_call in enumerate(function_calls, 1):
                            # Log tool execution with position indicator
                            logger.info(
                                f"Executing tool {idx}/{tool_count}: {func_call['name']}",
                                extra={
                                    "provider": self.model_name,
                                    "tool_name": func_call["name"],
                                    "tool_position": f"{idx}/{tool_count}",
                                    "iteration": tool_iteration
                                }
                            )

                            tool_result = await self._execute_tool_call(
                                func_call["name"],
                                func_call["args"],
                                mcp_client,
                                user_id=user_id
                            )

                            # Check if tool execution succeeded or failed
                            if "error" in tool_result:
                                # Emit tool_call_failed event
                                yield {
                                    "type": "tool_call_failed",
                                    "tool": func_call["name"],
                                    "error": tool_result.get("error", "Unknown error")
                                }
                            else:
                                # Emit tool_call_completed event
                                result_summary = str(tool_result)[:200] if tool_result else ""
                                yield {
                                    "type": "tool_call_completed",
                                    "tool": func_call["name"],
                                    "result_summary": result_summary
                                }

                            # Format function response for Gemini
                            formatted_result = self.tool_adapter.format_tool_result_for_gemini(
                                func_call["name"],
                                tool_result
                            )
                            tool_results.append(formatted_result)

                        # With ChatSession, thought_signatures are preserved automatically
                        # We just need to format the tool responses and continue the loop
                        # Reference: https://ai.google.dev/gemini-api/docs/thought-signatures

                        # ChatSession automatically includes the function calls and preserves thought_signatures
                        # Send ALL function responses as Parts with functionResponse
                        # The SDK expects a list of parts for multi-part messages (parallel tool calls)
                        from google.ai import generativelanguage as glm

                        last_user_message = [
                            glm.Part(function_response=glm.FunctionResponse(
                                name=result["name"],
                                response=result["response"]
                            ))
                            for result in tool_results
                        ]

                        # Increment iteration and continue loop
                        tool_iteration += 1
                        if tool_count > 1:
                            logger.info(
                                f"All {tool_count} parallel tools completed, continuing conversation",
                                extra={
                                    "provider": self.model_name,
                                    "tools_executed": tool_names,
                                    "tool_count": tool_count,
                                    "iteration": tool_iteration
                                }
                            )
                        else:
                            logger.info(
                                f"Tool '{tool_names[0]}' completed, continuing conversation",
                                extra={
                                    "provider": self.model_name,
                                    "tool_name": tool_names[0],
                                    "iteration": tool_iteration
                                }
                            )

                    elif function_calls and not mcp_client:
                        # No MCP client provided but function calls detected
                        tool_names = [fc["name"] for fc in function_calls]
                        logger.error(
                            "Function calls detected but no MCP client provided",
                            extra={"provider": self.model_name, "tools": tool_names}
                        )
                        for fc in function_calls:
                            yield {
                                "type": "tool_call_failed",
                                "tool": fc["name"],
                                "error": "MCP client not provided to execute tools"
                            }
                        return

                    elif not function_calls:
                        # No function calls, but also no STOP - unexpected but valid completion
                        # This can happen when Gemini finishes without explicit STOP signal
                        duration_ms = int((time.time() - start_time) * 1000)

                        # Get finish reason info for error message (may be set from chunk loop)
                        fr_name = finish_reason_name if 'finish_reason_name' in dir() else "UNKNOWN"
                        fr_value = finish_reason_value if 'finish_reason_value' in dir() else -1

                        logger.warning(
                            "Streaming ended without STOP or function call",
                            extra={
                                "provider": self.model_name,
                                "duration_ms": duration_ms,
                                "token_count": token_count,
                                "finish_reason": fr_name,
                                "finish_reason_value": fr_value,
                                "tool_iteration": tool_iteration
                            }
                        )

                        # CRITICAL: If no tokens were generated, send error to user
                        # This happens with finish_reason like THINKING_OVERFLOW (12),
                        # BLOCKLIST (7), PROHIBITED_CONTENT (8), MALFORMED_FUNCTION_CALL (10) etc.
                        if token_count == 0:
                            # Map common finish reasons to user-friendly messages
                            error_messages = {
                                7: "I couldn't complete my response due to content restrictions.",
                                8: "I couldn't complete my response due to content policy.",
                                9: "I couldn't complete my response due to sensitive information detection.",
                                10: "I had trouble processing that request. Let me try a different approach.",
                                12: "I ran into a processing limit while thinking. Please try rephrasing or simplifying your request.",
                            }

                            user_message = error_messages.get(
                                fr_value,
                                "I wasn't able to generate a response. Please try again or rephrase your request."
                            )

                            # For MALFORMED_FUNCTION_CALL, log detailed diagnostic info
                            if fr_value == 10:
                                # Extract tool names for debugging
                                tool_names = []
                                if gemini_tools:
                                    tool_names = [t.get("name", "UNKNOWN") for t in gemini_tools]

                                # Find chunks that had function call attempts (even partial/malformed)
                                func_call_chunks = [
                                    c for c in raw_chunk_data
                                    if c.get("parts") and any(
                                        p.get("has_function_call") or p.get("function_args_error")
                                        for p in c.get("parts", [])
                                    )
                                ]

                                # Get last chunk which should have the finish_reason
                                last_chunk = raw_chunk_data[-1] if raw_chunk_data else {}

                                logger.error(
                                    "MALFORMED_FUNCTION_CALL detected - Gemini failed to generate valid function call. "
                                    "RAW CHUNK DATA LOGGED FOR DIAGNOSIS.",
                                    extra={
                                        "provider": self.model_name,
                                        "tool_iteration": tool_iteration,
                                        "message_count": len(messages),
                                        "last_user_content": messages[-1].get("content", "")[:500] if messages else None,
                                        "tool_count": len(gemini_tools) if gemini_tools else 0,
                                        "tool_names": tool_names,
                                        "chunk_count": len(raw_chunk_data),
                                        "func_call_chunks": func_call_chunks,
                                        "last_chunk": last_chunk,
                                        "all_chunks_with_parts": [
                                            c for c in raw_chunk_data if c.get("parts")
                                        ]
                                    }
                                )

                            logger.error(
                                "Empty response from Gemini - sending error to user",
                                extra={
                                    "provider": self.model_name,
                                    "finish_reason": fr_name,
                                    "finish_reason_value": fr_value,
                                    "tool_iteration": tool_iteration,
                                    "error_message": user_message
                                }
                            )

                            # Yield error event so user sees feedback
                            yield {
                                "type": "error",
                                "message": user_message,
                                "code": f"EMPTY_RESPONSE_{fr_name}"
                            }

                        # Still track in Langfuse for this case
                        if trace and token_count > 0:
                            try:
                                prompt_tokens = 0
                                completion_tokens = token_count

                                try:
                                    prompt_tokens = self.model.count_tokens(gemini_messages).total_tokens
                                except Exception:
                                    pass

                                cost_info = self.calculate_cost({
                                    "prompt_tokens": prompt_tokens,
                                    "completion_tokens": completion_tokens,
                                    "cached_tokens": 0
                                })

                                prompt_text = json.dumps([m for m in messages if m.get("role") != "tool"])
                                truncated_prompt = self._truncate_text(prompt_text, 1000)
                                full_completion = "".join(accumulated_content)
                                truncated_completion = self._truncate_text(full_completion, 1000)

                                generation = trace.generation(
                                    name=f"llm_call_{self.model_name}_streaming",
                                    input=truncated_prompt,
                                    model=self.model_name,
                                    model_parameters={
                                        "temperature": self.temperature,
                                        "max_output_tokens": self.max_output_tokens
                                    },
                                    metadata={
                                        "provider": self.model_name,
                                        "streaming": True,
                                        "safety_setting": str(self.safety_setting),
                                        "tool_iterations": tool_iteration,
                                        "ended_without_stop": True
                                    }
                                )

                                # ModelUsage TypedDict: input, output, total, input_cost, output_cost, total_cost
                                generation.end(
                                    output=truncated_completion,
                                    usage={
                                        "input": prompt_tokens,
                                        "output": completion_tokens,
                                        "total": prompt_tokens + completion_tokens,
                                        "input_cost": cost_info.get("input_cost", 0),
                                        "output_cost": cost_info.get("output_cost", 0),
                                        "total_cost": cost_info.get("total_cost", 0)
                                    },
                                    metadata={
                                        "duration_ms": duration_ms
                                    }
                                )

                                logger.info(
                                    "Langfuse generation tracked (ended without STOP)",
                                    extra={
                                        "provider": self.model_name,
                                        "prompt_tokens": prompt_tokens,
                                        "completion_tokens": completion_tokens,
                                        "cost_usd": cost_info.get("total_cost", 0)
                                    }
                                )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to track Gemini streaming in Langfuse: {str(e)}",
                                    extra={"provider": self.model_name, "error": str(e)}
                                )

                        # Yield done event even without STOP
                        yield {
                            "type": "done",
                            "tokens_used": {
                                "prompt": 0,
                                "completion": token_count
                            }
                        }
                        return

                except Exception as e:
                    # Check for quota/rate limit errors
                    error_str = str(e).lower()
                    if "quota" in error_str or "resource exhausted" in error_str or "429" in error_str:
                        logger.warning(
                            "Gemini quota/rate limit exceeded",
                            extra={
                                "provider": self.model_name,
                                "error": str(e)
                            }
                        )
                        raise RateLimitError(self.model_name, retry_after=None)

                    # Re-raise as ProviderError
                    raise ProviderError(self.model_name, f"Streaming error: {str(e)}", e)

            # If we exit the loop due to max iterations, log warning
            if tool_iteration >= self.max_tool_iterations:
                logger.warning(
                    "Max tool iterations reached",
                    extra={
                        "provider": self.model_name,
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
                    "provider": self.model_name,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                    "error": str(e)
                }
            )
            raise ProviderError(self.model_name, f"Unexpected streaming error: {type(e).__name__}", e)

    async def _execute_tool_call(
        self,
        tool_name: str,
        tool_arguments: Dict[str, Any],
        mcp_client,
        user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute MCP tool and handle errors gracefully.

        Args:
            tool_name: Name of the tool to execute
            tool_arguments: Tool arguments
            mcp_client: MCP client instance
            user_id: User ID to inject into tool arguments (overrides LLM-provided value)

        Returns:
            Tool execution result (or error response)
        """
        try:
            # Import MCPClient locally to avoid circular dependency
            from api.mcp_client import MCPClient, MCPNetworkError, MCPToolError

            # Inject correct user_id to override any LLM-inferred value
            # This prevents the LLM from using wrong user_ids (e.g., inferring "ankit" from profile name)
            if user_id and "user_id" in tool_arguments:
                original_user_id = tool_arguments.get("user_id")
                if original_user_id != user_id:
                    logger.warning(
                        "Overriding LLM-provided user_id with correct value",
                        extra={
                            "provider": self.model_name,
                            "tool_name": tool_name,
                            "original_user_id": original_user_id,
                            "correct_user_id": user_id
                        }
                    )
                tool_arguments["user_id"] = user_id

            logger.info(
                "Executing MCP tool for Gemini",
                extra={
                    "provider": self.model_name,
                    "tool_name": tool_name,
                    "arguments": tool_arguments
                }
            )

            # Execute tool via MCP client
            result = await mcp_client.call_tool(tool_name, tool_arguments)

            logger.info(
                "MCP tool execution completed successfully",
                extra={
                    "provider": self.model_name,
                    "tool_name": tool_name
                }
            )

            return result

        except MCPNetworkError as e:
            # MCP server unreachable - graceful error
            logger.warning(
                "MCP server unreachable during Gemini tool call",
                extra={
                    "provider": self.model_name,
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
                    "provider": self.model_name,
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
                    "provider": self.model_name,
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
