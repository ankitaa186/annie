"""
ChatGPT-5 Provider

Implementation of ChatGPT-5 (OpenAI API) provider with streaming support,
function calling, multimodal support, and Langfuse tracing integration.

Multimodal Support (Story 18.3):
- Images: Native support via image_url with base64 data URLs
- Documents (PDF, DOCX, XLSX): Text extraction fallback for non-Gemini providers
"""

import base64
import io
import json
import time
from typing import Any, AsyncGenerator, Dict, List, Optional
import httpx
from api.config import get_config
from api.logging import get_logger
from api.providers.base import BaseProvider, ContextLengthError
from api.observability.tracing import get_current_trace
from api.observability.cost import calculate_llm_cost
from api.utils import inject_user_id

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
        self.request_timeout = float(config.get("LLM_REQUEST_TIMEOUT", "300.0"))
        self.streaming_timeout = float(config.get("LLM_STREAMING_TIMEOUT", "300.0"))

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
        Stream chat completion from ChatGPT-5 with tool calling and multimodal support.

        Args:
            messages: List of message dictionaries
            tools: Optional list of tools in OpenAI format
            mcp_client: Optional MCP client for executing tool calls
            **kwargs: Additional parameters:
                - files: Optional list of FileAttachment objects for multimodal processing

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
        # Extract files from kwargs for multimodal support (Story 18.3)
        files = kwargs.get("files")
        # Extract user_id for tool argument injection (prevents LLM from using wrong IDs)
        user_id = kwargs.get("user_id")

        # Build multimodal messages if files provided
        if files:
            conversation_messages = self._build_multimodal_messages(list(messages), files)
        else:
            conversation_messages = list(messages)

        max_tool_iterations = 20
        iteration = 0

        while iteration < max_tool_iterations:
            iteration += 1

            async for event in self._stream_single_completion(
                conversation_messages, tools, mcp_client, user_id
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
        user_id: Optional[str] = None,
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

            # Detect if this is a multimodal request (messages have content arrays)
            has_multimodal = any(
                isinstance(msg.get("content"), list)
                for msg in messages
                if msg.get("role") == "user"
            )

            logger.info(
                "Starting ChatGPT-5 streaming request",
                extra={
                    "provider": "chatgpt-5",
                    "model": self.MODEL_NAME,
                    "message_count": len(messages),
                    "timeout_seconds": self.streaming_timeout,
                    "tool_count": len(tools) if tools else 0,
                    "has_multimodal": has_multimodal,
                    "event": "chatgpt_multimodal_stream" if has_multimodal else "chatgpt_text_stream"
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

                    # Detect context window overflow
                    error_lower = error_msg.lower()
                    if "context_length_exceeded" in error_lower or "maximum context length" in error_lower:
                        raise ContextLengthError("chatgpt-5", error_msg)

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
                                                    # Inject correct user_id to override LLM-inferred value
                                                    inject_user_id(
                                                        args, user_id, logger,
                                                        {"provider": "chatgpt-5", "tool_name": tool_name}
                                                    )
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

        except ContextLengthError:
            # Re-raise context length errors as-is
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

    def _build_multimodal_messages(
        self,
        messages: List[Dict[str, Any]],
        files: Optional[List] = None
    ) -> List[Dict[str, Any]]:
        """
        Build ChatGPT messages with multimodal content (images and document text).

        Story 18.3: ChatGPT fallback for multimodal support.
        - Images: Native support via image_url with base64 data URL
        - Documents (PDF, DOCX, TXT): Text extraction appended as text content
        - Spreadsheets (XLSX, CSV): Text extraction appended as text content

        Args:
            messages: List of OpenAI-format messages
            files: Optional list of FileAttachment objects

        Returns:
            List of messages with multimodal content structure
        """
        if not files:
            return messages

        # First pass: copy all messages unchanged
        result = list(messages)

        # Find the LAST user message and attach files to it
        for i in range(len(result) - 1, -1, -1):
            if result[i].get("role") == "user":
                content_parts = []

                # Add original text content
                text_content = result[i].get("content", "")
                if text_content:
                    content_parts.append({"type": "text", "text": text_content})

                # Process each file
                for file in files:
                    file_content = self._process_file_for_chatgpt(file)
                    if file_content:
                        content_parts.append(file_content)

                # Replace message with multimodal content array
                result[i] = {
                    "role": "user",
                    "content": content_parts
                }

                logger.info(
                    "Files attached to last user message for ChatGPT",
                    extra={
                        "file_count": len(files),
                        "mime_types": [f.mime_type for f in files],
                        "total_size_bytes": sum(f.size_bytes for f in files),
                        "message_index": i,
                        "event": "chatgpt_multimodal_request"
                    }
                )
                break  # Only attach to last user message

        return result

    def _process_file_for_chatgpt(self, file) -> Optional[Dict[str, Any]]:
        """
        Process a single file for ChatGPT content array.

        Args:
            file: FileAttachment object

        Returns:
            Content part dict for ChatGPT message content array, or None if unsupported
        """
        mime_type = file.mime_type

        # Images: Native support via image_url
        if mime_type.startswith("image/"):
            return {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{file.data_base64}"
                }
            }

        # Text files: Direct inclusion
        if mime_type == "text/plain":
            try:
                text = base64.b64decode(file.data_base64).decode("utf-8")
                return {
                    "type": "text",
                    "text": f"[Content from {file.filename}]:\n{text}"
                }
            except Exception as e:
                logger.warning(
                    "Failed to decode text file",
                    extra={"file_name": file.filename, "error": str(e)}
                )
                return None

        # CSV: Direct text inclusion
        if mime_type == "text/csv":
            try:
                text = base64.b64decode(file.data_base64).decode("utf-8")
                return {
                    "type": "text",
                    "text": f"[CSV data from {file.filename}]:\n{text}"
                }
            except Exception as e:
                logger.warning(
                    "Failed to decode CSV file",
                    extra={"file_name": file.filename, "error": str(e)}
                )
                return None

        # PDF: Text extraction
        if mime_type == "application/pdf":
            text = self._extract_pdf_text(file)
            if text:
                return {
                    "type": "text",
                    "text": f"[Content extracted from {file.filename}]:\n{text}"
                }
            return None

        # DOCX: Text extraction
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            text = self._extract_docx_text(file)
            if text:
                return {
                    "type": "text",
                    "text": f"[Content extracted from {file.filename}]:\n{text}"
                }
            return None

        # XLSX: Text extraction
        if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            text = self._extract_xlsx_text(file)
            if text:
                return {
                    "type": "text",
                    "text": f"[Spreadsheet data from {file.filename}]:\n{text}"
                }
            return None

        # Unsupported format
        logger.warning(
            "Unsupported file format for ChatGPT fallback",
            extra={
                "file_name": file.filename,
                "mime_type": mime_type,
                "event": "chatgpt_unsupported_format"
            }
        )
        return {
            "type": "text",
            "text": f"[Unable to process {file.filename} - format not supported for text extraction]"
        }

    def _extract_pdf_text(self, file) -> Optional[str]:
        """
        Extract text content from a PDF file.

        Args:
            file: FileAttachment with PDF data

        Returns:
            Extracted text or None if extraction fails
        """
        try:
            from pypdf import PdfReader

            # Decode base64 to bytes
            pdf_bytes = base64.b64decode(file.data_base64)
            pdf_buffer = io.BytesIO(pdf_bytes)

            # Extract text from all pages
            reader = PdfReader(pdf_buffer)
            text_parts = []

            for i, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"--- Page {i} ---\n{page_text}")

            if not text_parts:
                logger.warning(
                    "PDF appears to be image-based (no extractable text)",
                    extra={"file_name": file.filename, "page_count": len(reader.pages)}
                )
                return f"[This PDF ({file.filename}) contains {len(reader.pages)} pages but no extractable text. It may be scanned/image-based.]"

            full_text = "\n\n".join(text_parts)

            logger.info(
                "PDF text extraction successful",
                extra={
                    "file_name": file.filename,
                    "page_count": len(reader.pages),
                    "text_length": len(full_text),
                    "event": "pdf_text_extracted"
                }
            )

            return full_text

        except Exception as e:
            error_msg = str(e).lower()
            if "password" in error_msg or "encrypted" in error_msg:
                logger.warning(
                    "PDF is password-protected",
                    extra={"file_name": file.filename}
                )
                return f"[This PDF ({file.filename}) is password-protected and cannot be read. Please provide an unlocked version.]"

            logger.error(
                "PDF text extraction failed",
                extra={
                    "file_name": file.filename,
                    "error": str(e),
                    "event": "pdf_extraction_failed"
                }
            )
            return None

    def _extract_docx_text(self, file) -> Optional[str]:
        """
        Extract text content from a DOCX file.

        Args:
            file: FileAttachment with DOCX data

        Returns:
            Extracted text or None if extraction fails
        """
        try:
            from docx import Document

            # Decode base64 to bytes
            docx_bytes = base64.b64decode(file.data_base64)
            docx_buffer = io.BytesIO(docx_bytes)

            # Extract text from all paragraphs
            doc = Document(docx_buffer)
            text_parts = []

            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)

            # Also extract from tables
            for table in doc.tables:
                table_rows = []
                for row in table.rows:
                    row_cells = [cell.text.strip() for cell in row.cells]
                    table_rows.append(" | ".join(row_cells))
                if table_rows:
                    text_parts.append("\n".join(table_rows))

            full_text = "\n\n".join(text_parts)

            if not full_text.strip():
                logger.warning(
                    "DOCX appears empty",
                    extra={"file_name": file.filename}
                )
                return f"[This document ({file.filename}) appears to be empty or contains only images.]"

            logger.info(
                "DOCX text extraction successful",
                extra={
                    "file_name": file.filename,
                    "paragraph_count": len(doc.paragraphs),
                    "table_count": len(doc.tables),
                    "text_length": len(full_text),
                    "event": "docx_text_extracted"
                }
            )

            return full_text

        except Exception as e:
            logger.error(
                "DOCX text extraction failed",
                extra={
                    "file_name": file.filename,
                    "error": str(e),
                    "event": "docx_extraction_failed"
                }
            )
            return None

    def _extract_xlsx_text(self, file) -> Optional[str]:
        """
        Extract text content from an XLSX file as tabular text.

        Args:
            file: FileAttachment with XLSX data

        Returns:
            Extracted text or None if extraction fails
        """
        try:
            from openpyxl import load_workbook

            # Decode base64 to bytes
            xlsx_bytes = base64.b64decode(file.data_base64)
            xlsx_buffer = io.BytesIO(xlsx_bytes)

            # Load workbook
            wb = load_workbook(xlsx_buffer, read_only=True, data_only=True)
            text_parts = []

            for sheet_name in wb.sheetnames:
                sheet = wb[sheet_name]
                rows = []

                for row in sheet.iter_rows(values_only=True):
                    # Convert row values to strings, handling None
                    row_values = [str(cell) if cell is not None else "" for cell in row]
                    # Skip entirely empty rows
                    if any(v.strip() for v in row_values):
                        rows.append(" | ".join(row_values))

                if rows:
                    text_parts.append(f"=== Sheet: {sheet_name} ===\n" + "\n".join(rows))

            wb.close()

            full_text = "\n\n".join(text_parts)

            if not full_text.strip():
                logger.warning(
                    "XLSX appears empty",
                    extra={"file_name": file.filename}
                )
                return f"[This spreadsheet ({file.filename}) appears to be empty.]"

            logger.info(
                "XLSX text extraction successful",
                extra={
                    "file_name": file.filename,
                    "sheet_count": len(wb.sheetnames),
                    "text_length": len(full_text),
                    "event": "xlsx_text_extracted"
                }
            )

            return full_text

        except Exception as e:
            logger.error(
                "XLSX text extraction failed",
                extra={
                    "file_name": file.filename,
                    "error": str(e),
                    "event": "xlsx_extraction_failed"
                }
            )
            return None
