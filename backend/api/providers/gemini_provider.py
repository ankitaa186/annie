"""
Gemini 3 Pro Provider — google.genai SDK (Story 24.1)

Implementation of Gemini 3 Pro (Google AI API) provider with streaming support,
safety filter handling, function calling, and Langfuse tracing integration.

Story 24.1 migrated this file from the deprecated `google.generativeai` package
to `google.genai` (the new official SDK). Key shape changes:
- `genai.Client(api_key=...)` singleton (constructed once in __init__)
- Per-call `types.GenerateContentConfig(...)` for generation/safety/tools/AFC
- `client.aio.chats.create(...)` + `chat.send_message_stream(...)` async path
- `types.Part.from_function_response(...)` for tool responses
- `function_call.args` is a plain Python dict (no proto unwrapping)
- `automatic_function_calling=AutomaticFunctionCallingConfig(disable=True)`
  is set in a config builder, non-overridable from call sites — critical
  tripwire because the new SDK auto-executes Python callables by default.
"""

import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

from api.config import get_config
from api.logging import get_logger
from api.constants import MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH, MODEL_GEMINI_LEGACY
from api.providers.base import BaseProvider, ContextLengthError
from api.providers.grok_provider import ProviderError, RateLimitError
from api.providers.gemini_tool_adapter import GeminiToolAdapter
from api.observability.tracing import get_current_trace
from api.observability.cost import calculate_llm_cost
from api.utils import inject_user_id, strip_base64_from_tool_result

logger = get_logger(__name__)


# Story 24.1: legacy-compatible numeric values for FinishReason names.
# The legacy SDK's FinishReason was a proto IntEnum (STOP=1, MAX_TOKENS=2,
# MALFORMED_FUNCTION_CALL=10, etc.). The new SDK exposes FinishReason as a
# string enum (FinishReason.STOP, FinishReason.MAX_TOKENS, ...). The
# downstream finish-reason logic in this file is keyed off the legacy
# numeric values (especially fr_value == 10 for MALFORMED_FUNCTION_CALL
# retry triggering); rather than rewrite all those comparisons, we map
# the new enum's name back to the legacy numeric value.
_FINISH_REASON_NAME_TO_LEGACY_VALUE = {
    "FINISH_REASON_UNSPECIFIED": 0,
    "STOP": 1,
    "MAX_TOKENS": 2,
    "SAFETY": 3,
    "RECITATION": 4,
    "LANGUAGE": 6,
    "OTHER": 5,
    "BLOCKLIST": 7,
    "PROHIBITED_CONTENT": 8,
    "SPII": 9,
    "MALFORMED_FUNCTION_CALL": 10,
    "IMAGE_SAFETY": 11,
    "UNEXPECTED_TOOL_CALL": 13,
    # Story 9.x's THINKING_OVERFLOW (12) / others not in new SDK enum;
    # default to -1 / unknown handled by the .get() fallback.
}


def _finish_reason_to_legacy_int(fr: Any) -> int:
    """Translate a new-SDK FinishReason (str enum) to the legacy numeric value.

    Story 24.1: the streaming code path was written against the legacy
    proto IntEnum and uses fr_value comparisons (e.g., 10 ==
    MALFORMED_FUNCTION_CALL). Rather than rewrite every comparison, this
    helper preserves the old contract.
    """
    if fr is None:
        return 0
    name = getattr(fr, "name", None)
    if name is None:
        # Last resort: convert via str() and strip "FinishReason." prefix.
        name = str(fr).rsplit(".", 1)[-1]
    return _FINISH_REASON_NAME_TO_LEGACY_VALUE.get(name, -1)


class GeminiProvider(BaseProvider):
    """
    Gemini (Google AI API) provider implementation.

    Features:
    - Streaming chat completion with function calling
    - Message format conversion (OpenAI → Gemini)
    - Safety filter handling (4 harm categories)
    - Quota and rate limit handling
    - Cost calculation with tiered pricing + cached-token discount
    - Langfuse tracing integration (fire-and-forget)
    - Implicit prompt-cache instrumentation (Story 24.1 AC15)
    - Supports multiple Gemini models (gemini-3.1-pro-preview, gemini-2.5-pro, etc.)
    """

    # Default Gemini model
    DEFAULT_MODEL = MODEL_GEMINI_PRO

    # Supported Gemini models
    SUPPORTED_MODELS = [MODEL_GEMINI_PRO, MODEL_GEMINI_FLASH, MODEL_GEMINI_LEGACY]

    # Safety filter user-friendly messages, keyed by HarmCategory enum.
    SAFETY_MESSAGES = {
        genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT: "I cannot respond due to content policy. Please rephrase.",
        genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH: "I cannot respond due to content policy. Please rephrase.",
        genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: "I cannot respond due to content policy. Please rephrase.",
        genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: "I cannot respond due to content policy. Please rephrase.",
    }

    def __init__(self, model_override: Optional[str] = None):
        """
        Initialize Gemini provider with configuration from environment.

        Story 24.1 (AC2): client construction migrated to `genai.Client(api_key=...)`,
        constructed once and reused for the life of this provider instance
        (Parminder's singleton steer). Generation config + safety settings + tool
        configuration moved to per-call `types.GenerateContentConfig` (built by
        `_build_generate_content_config`).

        Args:
            model_override: Optional model name to use instead of env config.
                           Useful for fallback scenarios (e.g., gemini-2.5-pro fallback)

        Raises:
            ValueError: If GOOGLE_API_KEY is not configured
        """
        config = get_config()

        # Get API key
        self.api_key = config.get("GOOGLE_API_KEY")
        if not self.api_key or self.api_key == "REPLACE_ME":
            raise ValueError("GOOGLE_API_KEY not configured")

        # Load configuration from environment, with optional override
        # cost_model_id: the constant used for cost calculation and provider identity
        # model_name: what gets sent to the Gemini SDK (may differ, e.g. user sets GEMINI_MODEL)
        if model_override:
            self.cost_model_id = model_override
            self.model_name = model_override
        else:
            self.cost_model_id = self.DEFAULT_MODEL
            self.model_name = config.get("GEMINI_MODEL", self.DEFAULT_MODEL)
        self.max_output_tokens = int(config.get("GEMINI_MAX_OUTPUT_TOKENS", "16384"))
        self.temperature = float(config.get("GEMINI_TEMPERATURE", "1.0"))
        self.context_cache_ttl = int(config.get("GEMINI_CONTEXT_CACHE_TTL", "300"))

        # Load safety setting (default: BLOCK_NONE for minimal filtering)
        safety_setting_str = config.get("GEMINI_SAFETY_SETTING", "BLOCK_NONE")
        self.safety_setting = self._parse_safety_setting(safety_setting_str)
        self.safety_setting_str = safety_setting_str

        # Story 24.1 (AC2): construct the SDK client once. The new SDK no
        # longer has a module-global `genai.configure(...)` step; instead the
        # API key flows through the Client. Reused across every
        # stream_chat_completion call (Parminder's singleton steer — avoids
        # per-request httpx/auth setup churn and lets future SDK pooling
        # work).
        self.client = genai.Client(api_key=self.api_key)

        # Initialize tool adapter for function calling (Story 9.3)
        # Story 24.1 (AC14): kept on Parminder's strong steer — MCP boundary
        # delivers OpenAI-shaped tool dicts; `from_callable` requires Python
        # callables we don't have. The adapter is the right primitive.
        self.tool_adapter = GeminiToolAdapter()

        # Load max tool iterations from config (prevent infinite loops)
        self.max_tool_iterations = int(config.get("GEMINI_MAX_TOOL_ITERATIONS", "20"))

        logger.info(
            "Gemini 3 Pro provider initialized (google.genai SDK)",
            extra={
                "provider": self.model_name,
                "model": self.model_name,
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
                "safety_setting": safety_setting_str,
                "max_tool_iterations": self.max_tool_iterations,
                "sdk": "google.genai",
            }
        )

    def _parse_safety_setting(self, setting_str: str) -> "genai_types.HarmBlockThreshold":
        """
        Parse safety setting string to HarmBlockThreshold enum.

        Args:
            setting_str: Safety setting string

        Returns:
            HarmBlockThreshold enum value
        """
        setting_map = {
            "BLOCK_NONE": genai_types.HarmBlockThreshold.BLOCK_NONE,
            "BLOCK_ONLY_HIGH": genai_types.HarmBlockThreshold.BLOCK_ONLY_HIGH,
            "BLOCK_MEDIUM_AND_ABOVE": genai_types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            "BLOCK_LOW_AND_ABOVE": genai_types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        }
        return setting_map.get(setting_str, genai_types.HarmBlockThreshold.BLOCK_NONE)

    def _build_safety_settings(self) -> List[genai_types.SafetySetting]:
        """
        Build safety settings as a list[SafetySetting] for the new SDK.

        Story 24.1 (AC7): the new SDK takes safety settings as a list of
        `types.SafetySetting(category=, threshold=)`, not a dict keyed by
        HarmCategory. This builder produces that list for inclusion in
        `GenerateContentConfig.safety_settings`.
        """
        return [
            genai_types.SafetySetting(
                category=cat,
                threshold=self.safety_setting,
            )
            for cat in (
                genai_types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                genai_types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                genai_types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                genai_types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            )
        ]

    def _build_generate_content_config(
        self,
        tools_config: Optional[List[Dict[str, Any]]] = None,
        system_instruction: Optional[str] = None,
    ) -> genai_types.GenerateContentConfig:
        """
        Build a GenerateContentConfig for the streaming call.

        Story 24.1 (AC4 + Parminder steer): `automatic_function_calling.disable=True`
        is set ALWAYS by this builder, regardless of caller. The new SDK's default
        is to auto-execute Python callables passed via `tools=...`, bypassing
        Annie's MCP layer entirely. We don't pass Python callables, but the
        explicit disable is the correct tripwire and is non-overridable from
        call sites by design — `_build_generate_content_config` is the single
        place where AFC behavior is decided.

        Args:
            tools_config: Optional list of `{"function_declarations": [...]}`
                dicts (output of GeminiToolAdapter.convert_openai_to_gemini_schema
                wrapped per-call). The adapter delivers OpenAI-shaped function
                declarations the SDK accepts.
            system_instruction: Optional system instruction string. The new SDK
                accepts this as a top-level field on GenerateContentConfig
                (no more prepending to first user message).

        Returns:
            A GenerateContentConfig ready to pass into chats.create(config=...).
        """
        kwargs: Dict[str, Any] = {
            "temperature": self.temperature,
            "max_output_tokens": self.max_output_tokens,
            "safety_settings": self._build_safety_settings(),
            # Story 24.1 (AC4): non-negotiable. New SDK auto-executes Python
            # callables when `tools=[fn]` unless this disable flag is set.
            # Annie's tools are MCP-routed dicts (no Python callables) so
            # the disable is technically a no-op today, but it's the
            # tripwire that prevents a future regression where someone
            # adds a callable tool spec.
            "automatic_function_calling": genai_types.AutomaticFunctionCallingConfig(
                disable=True
            ),
        }

        if system_instruction:
            kwargs["system_instruction"] = system_instruction

        if tools_config:
            # tools_config is List[{"function_declarations": [...]}] — wrap each
            # in a Tool. The SDK accepts a list of Tool objects.
            tools_list: List[genai_types.Tool] = []
            for tc in tools_config:
                fds = tc.get("function_declarations", [])
                # Build FunctionDeclarations directly from the adapter's
                # OpenAI-shaped dicts — the SDK accepts dict-shaped fds via
                # the `tools=` arg, but going through the typed wrapper makes
                # the call site explicit and gives Pydantic validation.
                tools_list.append(genai_types.Tool(function_declarations=fds))
            kwargs["tools"] = tools_list

        return genai_types.GenerateContentConfig(**kwargs)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        # google.genai SDK doesn't require explicit cleanup
        pass

    async def close(self):
        """Close provider resources (no-op for Gemini)."""
        # google.genai SDK handles cleanup internally
        pass

    def _normalize_model_name(self, model_name: str) -> str:
        """
        Normalize model name by removing 'models/' prefix if present.

        The Gemini SDK uses full paths like 'models/gemini-3.1-pro-preview',
        but the cost calculator expects just 'gemini-3.1-pro-preview'.
        """
        if model_name.startswith("models/"):
            return model_name[7:]  # Remove 'models/' prefix
        return model_name

    def get_provider_name(self) -> str:
        """Return provider name (constant model identifier for cost/routing)."""
        return self.cost_model_id

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
            provider=self.cost_model_id,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            sources_used=0,  # Gemini doesn't have live search
            cached_tokens=usage.get("cached_tokens", 0)
        )

    @staticmethod
    def _extract_usage_metadata(chunk: Any) -> Optional[Dict[str, int]]:
        """
        Extract token usage from a Gemini stream chunk's `usage_metadata`.

        Story 23.1 (AC1): Tokens come from the SDK's `usage_metadata` on the
        final stream chunk, NOT from chunk-counting. Returns None ("we don't
        know") when either prompt/candidates field is missing — callers should
        omit the `usage` kwarg entirely from `generation.end()` rather than
        fabricate zeros (Parminder's note on AC3 — Langfuse coerces None→0
        and pollutes reconciliation).

        Story 24.1 (AC15 + Parminder steer): extends the helper with a third
        key `cached_tokens` (read from `cached_content_token_count`). Default
        is 0 (not None) when the field is missing — semantically "we know it
        was zero" on first turn / non-caching models, NOT "we don't know".
        Plumbed through `last_usage` into Langfuse `usage` payload so
        implicit-cache hit-rate is observable in traces.

        Bug 25.2 (AC1, AC8): adds `non_cached_input_tokens` =
        `max(0, prompt_tokens - cached_tokens)`. Google's
        `prompt_token_count` ALREADY INCLUDES `cached_content_token_count`
        as a subset, so emitting `usage["input"] = prompt_tokens` AND
        `usage["cached_input"] = cached_tokens` to Langfuse double-counts the
        cached portion (full rate + cached rate stacked = 5.5x overstatement
        on cache-hit traces). Callers MUST emit `non_cached_input_tokens` as
        Langfuse `usage["input"]`. The `max(0, ...)` guard handles the
        anomalous (and contract-violating) `cached > prompt` case; we log a
        WARNING here so the anomaly fires once per chunk rather than three
        times across emission sites.

        Args:
            chunk: A Gemini stream chunk that may have `.usage_metadata`.

        Returns:
            Dict with `prompt_tokens`, `completion_tokens`, `cached_tokens`,
            and `non_cached_input_tokens` if both required fields are present
            and non-None on the chunk. None otherwise.
        """
        usage_md = getattr(chunk, "usage_metadata", None)
        if usage_md is None:
            return None
        prompt = getattr(usage_md, "prompt_token_count", None)
        completion = getattr(usage_md, "candidates_token_count", None)
        if prompt is None or completion is None:
            return None
        # Story 24.1 (AC15): cached_content_token_count is None when no cache
        # hit / pre-3.x model / first turn. Default to 0 — we KNOW it was
        # zero in those cases, not "unknown".
        cached_raw = getattr(usage_md, "cached_content_token_count", None)
        cached = int(cached_raw) if cached_raw is not None else 0
        prompt_int = int(prompt)
        # Bug 25.2 (AC1, AC8): cached tokens are a SUBSET of prompt tokens per
        # Google's contract. Subtract for the Langfuse `input` emission shape;
        # clamp to 0 with a WARNING if the contract is violated.
        non_cached_input = prompt_int - cached
        if non_cached_input < 0:
            logger.warning(
                "cached_tokens exceeds prompt_tokens — clamping non_cached_input to 0",
                extra={
                    "event": "cached_token_count_anomaly",
                    "prompt_tokens": prompt_int,
                    "cached_tokens": cached,
                },
            )
            non_cached_input = 0
        return {
            "prompt_tokens": prompt_int,
            "completion_tokens": int(completion),
            "cached_tokens": cached,
            "non_cached_input_tokens": non_cached_input,
        }

    @staticmethod
    def _is_context_length_error(exc: Exception) -> bool:
        """
        Detect a context-window-overflow exception across the typed and
        substring paths.

        Story 24.1 (AC11.5): the new SDK raises typed errors
        (`google.genai.errors.ClientError` / `APIError`) carrying a `code`,
        a `status`, and a `message`. Our 1M-token edge-case test relies on
        catching this specifically as `ContextLengthError` (not as a generic
        ProviderError or RateLimitError), so the orchestrator's overflow
        recovery (Story 9.x) can fire compaction + retry. We must handle
        BOTH the typed exception (code/status checks) AND the substring path
        (legacy + safety net).

        Returns True when the exception looks like a token-limit overflow.
        """
        # 1. Typed-exception path: prefer structured fields.
        # ClientError carries `.code` (HTTP int), `.status` (str enum),
        # and `.message`. RESOURCE_EXHAUSTED + token + limit pattern.
        code = getattr(exc, "code", None)
        status = getattr(exc, "status", None) or ""
        message = getattr(exc, "message", None) or ""
        # Combine all available textual signal sources (lowercased).
        combined = f"{status} {message} {exc}".lower()

        has_resource_exhausted = (
            code == 429
            or "resource_exhausted" in combined
            or "resource exhausted" in combined
        )
        has_token_limit = "token" in combined and "limit" in combined
        return has_resource_exhausted and has_token_limit

    @staticmethod
    def _is_rate_limit_error(exc: Exception) -> bool:
        """
        Detect a rate-limit / quota exception (NOT context overflow).

        Story 24.1 (AC11.5): typed-exception migration. RESOURCE_EXHAUSTED
        without token+limit pattern == rate limit / monthly cap.
        """
        code = getattr(exc, "code", None)
        status = getattr(exc, "status", None) or ""
        message = getattr(exc, "message", None) or ""
        combined = f"{status} {message} {exc}".lower()
        return (
            code == 429
            or "quota" in combined
            or "resource_exhausted" in combined
            or "resource exhausted" in combined
            or " 429" in combined
            or "429 " in combined
        )

    def _trace_error_generation(
        self,
        trace: Any,
        error: Exception,
        duration_ms: int,
        last_usage: Optional[Dict[str, int]],
        tool_iteration: int,
    ) -> None:
        """
        Emit a Langfuse generation with `level="ERROR"` for a failed stream.

        Story 23.1 (AC5): when the provider raises (rate limit / quota /
        network / 5xx), Langfuse still receives a `generation.end()` so the
        cap-trip burst becomes observable in reconciliation. Fire-and-forget
        — never raises out of this helper. Caller must wrap the actual
        provider call in `try/finally` and pass the latest `last_usage`
        snapshot (which Gemini populates on the prompt-processed-then-429
        path, faithfully recording real billed prompt tokens).

        Story 24.1 (AC15): plumbs `cached_tokens` through too — error paths
        with prompt processed then 429 may have a non-zero cached count we
        want to record for cost attribution.
        """
        if not trace:
            return
        generation = None
        try:
            generation = trace.generation(
                name=f"llm_call_{self.model_name}_streaming",
                model=self.model_name,
                metadata={
                    "provider": self.model_name,
                    "streaming": True,
                    "tool_iterations": tool_iteration,
                    "error_path": True,
                },
            )
            end_kwargs: Dict[str, Any] = {
                "level": "ERROR",
                "status_message": f"{type(error).__name__}: {str(error)[:200]}",
                "metadata": {"duration_ms": duration_ms},
            }
            if last_usage is not None:
                cached_tokens = last_usage.get("cached_tokens", 0)
                # Bug 25.2 (AC1): use helper-computed non-cached input for
                # Langfuse emission; fall back to recomputation for safety
                # if an older usage shape lacks the key.
                non_cached_input_tokens = last_usage.get(
                    "non_cached_input_tokens",
                    max(0, last_usage["prompt_tokens"] - cached_tokens),
                )
                cost_info = self.calculate_cost({
                    "prompt_tokens": last_usage["prompt_tokens"],
                    "completion_tokens": last_usage["completion_tokens"],
                    "cached_tokens": cached_tokens,
                })
                # Bug 25.2 (AC1): emit non-cached input only — see
                # `_extract_usage_metadata` docstring for the math.
                end_kwargs["usage"] = {
                    "input": non_cached_input_tokens,
                    "output": last_usage["completion_tokens"],
                    "input_cached": cached_tokens,
                    "total": last_usage["prompt_tokens"] + last_usage["completion_tokens"],
                    "input_cost": cost_info.get("input_cost", 0),
                    "output_cost": cost_info.get("output_cost", 0),
                    "cached_cost": cost_info.get("cached_cost", 0),
                    "total_cost": cost_info.get("total_cost", 0),
                }
            generation.end(**end_kwargs)
        except Exception as trace_err:
            logger.warning(
                f"Failed to record error generation in Langfuse: {trace_err}",
                extra={"provider": self.model_name, "error": str(trace_err)},
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
        - system → returned as system_instruction (the new SDK supports this
          natively on GenerateContentConfig)

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

        Story 24.1 (AC3): migrated to `client.aio.chats.create(...)` +
        `chat.send_message_stream(...)` — full async, no sync-iter wrapping
        inside an async function.

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
            ContextLengthError: If the request exceeds the model's context window
        """
        start_time = time.time()
        files = kwargs.get("files")  # Extract files from kwargs
        user_id = kwargs.get("user_id")  # Extract user_id for tool argument injection
        last_usage: Optional[Dict[str, int]] = None
        tool_iteration = 0
        trace = None

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
            accumulated_content = []

            # Get current trace for Langfuse
            trace = get_current_trace()

            # Multi-turn tool calling loop (Story 9.3)
            # Use ChatSession API for automatic thought_signature handling

            # Initialize ChatSession with history (all messages except the last user message)
            # The last user message will be sent via send_message_stream()
            history = gemini_messages[:-1] if len(gemini_messages) > 1 else []

            # Extract the last user message parts for send_message_stream()
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

            # Story 24.1 (AC2): system_instruction is a top-level field on
            # GenerateContentConfig in the new SDK — no more prepending to
            # the first user message. The legacy prepend hack is GONE.

            # Build tool configuration (passed into _build_generate_content_config)
            tools_config = None
            if gemini_tools:
                tools_config = [{"function_declarations": gemini_tools}]

            # Build per-call generation config (AC4 + AC7 + Parminder steer:
            # AFC disable is set non-overridably here)
            gen_config = self._build_generate_content_config(
                tools_config=tools_config,
                system_instruction=system_instruction,
            )

            # Story 24.1 (AC3): async path. `client.aio.chats.create(...)`
            # returns an async chat session. Tools live in `config`, not on
            # send_message_stream. send_message_stream returns an async iterator.
            chat = self.client.aio.chats.create(
                model=self.model_name,
                history=history,
                config=gen_config,
            )

            logger.debug(
                "Initialized async ChatSession",
                extra={
                    "provider": self.model_name,
                    "history_length": len(history),
                    "has_tools": tools_config is not None
                }
            )

            malformed_retries = 0  # Track MALFORMED_FUNCTION_CALL retries (cap: 3)
            MAX_MALFORMED_RETRIES = 3

            while tool_iteration < self.max_tool_iterations:
                # Generate streaming response using ChatSession
                try:
                    # Send message with streaming
                    # On first iteration: send user message (string or list[Part]/list[dict])
                    # On subsequent iterations: send list of function-response Parts
                    response = await chat.send_message_stream(
                        message=last_user_message,
                    )

                    # Track ALL function calls in this iteration (parallel tool calling support)
                    function_calls = []  # List of {name, args} dicts
                    token_count = 0  # Reset per iteration for accurate retry detection
                    chunk_count = 0  # Story 23.1: telemetry only, NOT used for cost

                    # Story 23.1 (AC1): capture latest usage_metadata seen across chunks.
                    last_usage = None  # type: Optional[Dict[str, int]]

                    # Debug: Track raw chunk data for MALFORMED_FUNCTION_CALL diagnosis
                    raw_chunk_data = []  # Accumulate for debugging if needed

                    # Process chunks (async iter — Story 24.1 AC3)
                    async for chunk in response:
                        chunk_count += 1
                        # Story 23.1 (AC1) + 24.1 (AC15): pull usage_metadata as soon
                        # as it appears. Refresh on every chunk that carries one — the
                        # final chunk is canonical, but the SDK can attach earlier too.
                        usage_snapshot = self._extract_usage_metadata(chunk)
                        if usage_snapshot is not None:
                            last_usage = usage_snapshot

                        # Debug: Capture raw chunk structure for diagnosing MALFORMED_FUNCTION_CALL
                        # Story 24.1 (AC8): typed Pydantic field access — chunks have
                        # .candidates / .candidates[0].content.parts / .function_call /
                        # .function_call.name / .function_call.args (plain dict).
                        try:
                            candidates = chunk.candidates or []
                            chunk_info = {
                                "has_candidates": bool(candidates),
                                "candidate_count": len(candidates),
                            }
                            if candidates:
                                cand = candidates[0]
                                fr = cand.finish_reason
                                chunk_info["finish_reason"] = str(fr) if fr is not None else None
                                chunk_info["finish_reason_value"] = (
                                    _finish_reason_to_legacy_int(fr) if fr is not None else None
                                )
                                cand_content = cand.content
                                chunk_info["has_content"] = bool(cand_content)
                                if cand_content:
                                    cand_parts = cand_content.parts or []
                                    chunk_info["has_parts"] = bool(cand_parts)
                                    chunk_info["part_count"] = len(cand_parts)
                                    part_details = []
                                    for part in cand_parts:
                                        part_text = getattr(part, "text", None)
                                        part_info = {"has_text": bool(part_text)}
                                        fc = getattr(part, "function_call", None)
                                        if fc:
                                            part_info["has_function_call"] = True
                                            part_info["function_name"] = getattr(fc, "name", "UNKNOWN")
                                            try:
                                                part_info["function_args_raw"] = str(fc.args)[:500]
                                            except Exception as args_err:
                                                part_info["function_args_error"] = str(args_err)
                                        else:
                                            part_info["has_function_call"] = False
                                        part_details.append(part_info)
                                    chunk_info["parts"] = part_details
                            raw_chunk_data.append(chunk_info)
                        except Exception as debug_err:
                            raw_chunk_data.append({"debug_capture_error": str(debug_err)})

                        # Check for safety blocks at the prompt level
                        prompt_feedback = getattr(chunk, "prompt_feedback", None)
                        if prompt_feedback is not None:
                            block_reason = getattr(prompt_feedback, "block_reason", None)
                            if block_reason:
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
                        candidates = chunk.candidates or []
                        if candidates:
                            candidate = candidates[0]

                            # Check for safety block in candidate
                            finish_reason = candidate.finish_reason
                            if finish_reason is not None and "SAFETY" in str(finish_reason):
                                # Get harm category if available
                                harm_category = None
                                safety_ratings = getattr(candidate, "safety_ratings", None) or []
                                for rating in safety_ratings:
                                    if getattr(rating, "blocked", False):
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
                                        "finish_reason": str(finish_reason),
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
                            cand_content = candidate.content
                            cand_parts = cand_content.parts if cand_content else None
                            if cand_parts:
                                for part in cand_parts:
                                    # Check for function call (Story 9.3) - supports parallel tool calls
                                    # Story 24.1 (AC6): function_call.args is a plain dict
                                    # in the new SDK (Pydantic-backed). The proto-walker is GONE.
                                    fc = getattr(part, "function_call", None)
                                    if fc:
                                        func_name = fc.name
                                        # New SDK delivers args as a Python dict directly.
                                        # `dict(...)` is a defensive copy and tolerates None.
                                        func_args = dict(fc.args) if fc.args else {}

                                        # Hotfix 2026-04-25: capture thought_signature
                                        # alongside the function_call for observability.
                                        # The chat session writes the full Part (including
                                        # thought_signature) into _curated_history via
                                        # output_contents, so the next send_message_stream
                                        # automatically prepends the signed function_call
                                        # ahead of our function_response — but only if the
                                        # SDK is >=1.40 where thought_signature is a real
                                        # field on types.Part (not stripped by extra=forbid).
                                        # We capture the value here purely so logs prove
                                        # the wire delivered it; chat-session is what
                                        # threads it through.
                                        thought_sig = getattr(part, "thought_signature", None)

                                        # Append to list (supports parallel tool calls)
                                        function_calls.append({
                                            "name": func_name,
                                            "args": func_args,
                                            "thought_signature": thought_sig,
                                        })

                                        logger.info(
                                            f"Gemini requesting tool: {func_name}",
                                            extra={
                                                "provider": self.model_name,
                                                "tool_name": func_name,
                                                "iteration": tool_iteration,
                                                "has_thought_signature": thought_sig is not None,
                                                "thought_signature_bytes": (
                                                    len(thought_sig) if thought_sig else 0
                                                ),
                                            }
                                        )

                                        # Emit tool_call_started event
                                        yield {
                                            "type": "tool_call_started",
                                            "tool": func_name,
                                            "arguments": func_args
                                        }

                                    # Extract text content (can co-exist with function_call)
                                    part_text = getattr(part, "text", None)
                                    if part_text:
                                        content = part_text

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
                            if finish_reason is not None:
                                # Story 24.1: new SDK delivers FinishReason as a
                                # string enum. Translate to legacy numeric value
                                # so the downstream (==1 STOP, ==10 MALFORMED, etc.)
                                # comparisons keep working without rewriting.
                                finish_reason_value = _finish_reason_to_legacy_int(finish_reason)
                                finish_reason_name = (
                                    finish_reason.name if hasattr(finish_reason, "name")
                                    else str(finish_reason)
                                )

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

                                    # Story 23.1 (AC1, AC2) + 24.1 (AC15) + Bug 25.2 (AC1):
                                    # token counts come from the SDK's `usage_metadata`,
                                    # including `cached_tokens` for implicit-cache observability
                                    # and `non_cached_input_tokens` for the Langfuse emission
                                    # shape (avoids double-counting the cached subset).
                                    if last_usage is not None:
                                        prompt_tokens = last_usage["prompt_tokens"]
                                        completion_tokens = last_usage["completion_tokens"]
                                        cached_tokens = last_usage.get("cached_tokens", 0)
                                        non_cached_input_tokens = last_usage.get(
                                            "non_cached_input_tokens",
                                            max(0, prompt_tokens - cached_tokens),
                                        )
                                    else:
                                        # AC3: SDK didn't deliver usage_metadata.
                                        prompt_tokens = 0
                                        completion_tokens = 0
                                        cached_tokens = 0
                                        non_cached_input_tokens = 0
                                        logger.warning(
                                            "Gemini stream finished without usage_metadata",
                                            extra={
                                                "provider": self.model_name,
                                                "event": "usage_metadata_missing",
                                                "model": self.model_name,
                                                "chunk_count": chunk_count,
                                                "tool_iterations": tool_iteration,
                                                "finish_reason": finish_reason_name,
                                            }
                                        )

                                    # Track in Langfuse (fire-and-forget)
                                    if trace:
                                        generation = None
                                        try:
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
                                                    "tool_iterations": tool_iteration
                                                }
                                            )

                                            end_kwargs = {
                                                "output": truncated_completion,
                                                "metadata": {"duration_ms": duration_ms},
                                            }
                                            if last_usage is not None:
                                                cost_info = self.calculate_cost({
                                                    "prompt_tokens": prompt_tokens,
                                                    "completion_tokens": completion_tokens,
                                                    "cached_tokens": cached_tokens,
                                                })
                                                # Bug 25.2 (AC1): emit non-cached input only.
                                                # Google's prompt_token_count INCLUDES the cached
                                                # subset, so emitting the full prompt_tokens here
                                                # AND cached_tokens as cached_input would
                                                # double-count the cached portion in Langfuse.
                                                end_kwargs["usage"] = {
                                                    "input": non_cached_input_tokens,
                                                    "output": completion_tokens,
                                                    "input_cached": cached_tokens,
                                                    "total": prompt_tokens + completion_tokens,
                                                    "input_cost": cost_info.get("input_cost", 0),
                                                    "output_cost": cost_info.get("output_cost", 0),
                                                    "cached_cost": cost_info.get("cached_cost", 0),
                                                    "total_cost": cost_info.get("total_cost", 0)
                                                }
                                                logger.info(
                                                    "Langfuse generation tracked successfully",
                                                    extra={
                                                        "provider": self.model_name,
                                                        "prompt_tokens": prompt_tokens,
                                                        "completion_tokens": completion_tokens,
                                                        "cached_tokens": cached_tokens,
                                                        "non_cached_input_tokens": non_cached_input_tokens,
                                                        "cost_usd": cost_info.get("total_cost", 0),
                                                        "event": (
                                                            "implicit_cache_hit"
                                                            if cached_tokens > 0
                                                            else "implicit_cache_miss"
                                                        ),
                                                    }
                                                )
                                            else:
                                                logger.info(
                                                    "Langfuse generation tracked without usage",
                                                    extra={
                                                        "provider": self.model_name,
                                                        "event": "usage_metadata_missing",
                                                    }
                                                )
                                        except Exception as e:
                                            logger.warning(
                                                f"Failed to build Gemini Langfuse generation: {str(e)}",
                                                extra={"provider": self.model_name, "error": str(e)}
                                            )
                                        finally:
                                            if generation is not None:
                                                try:
                                                    generation.end(**end_kwargs)
                                                except Exception as end_err:
                                                    logger.warning(
                                                        f"Failed to end Gemini Langfuse generation: {str(end_err)}",
                                                        extra={"provider": self.model_name, "error": str(end_err)}
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

                        # Generate stable IDs for persistence tracking
                        tool_call_ids = [
                            f"gemini_{uuid.uuid4().hex[:8]}"
                            for _ in function_calls
                        ]

                        # Emit persistence event: batch of tool calls
                        yield {
                            "type": "tool_persist_calls",
                            "tool_calls": [
                                {
                                    "id": tool_call_ids[i],
                                    "name": fc["name"],
                                    "arguments": json.dumps(fc["args"])
                                }
                                for i, fc in enumerate(function_calls)
                            ]
                        }

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

                            # Emit persistence event: individual tool result
                            yield {
                                "type": "tool_persist_result",
                                "tool_name": func_call["name"],
                                "tool_call_id": tool_call_ids[idx - 1],
                                "result_content": json.dumps(tool_result)
                            }

                            # Strip large base64 blobs before sending back to Gemini
                            # (media is already extracted and sent via SSE media frames)
                            clean_result = strip_base64_from_tool_result(tool_result)

                            # Format function response for Gemini
                            formatted_result = self.tool_adapter.format_tool_result_for_gemini(
                                func_call["name"],
                                clean_result
                            )
                            tool_results.append(formatted_result)

                        # ChatSession preserves thought_signatures automatically when
                        # SDK is >=1.40 (Part.thought_signature is a real field there).
                        # The chat's _curated_history holds the prior assistant Content
                        # (with signed function_call Parts). We send only the new
                        # function_response Parts; the SDK prepends curated history,
                        # so each function_response is preceded by its signed
                        # function_call → API accepts the request.
                        # Story 24.1 (AC5): build function-response Parts via the new
                        # `types.Part.from_function_response` helper. The legacy
                        # `glm.Part(function_response=glm.FunctionResponse(...))` shape
                        # is GONE — `from google.ai import generativelanguage as glm`
                        # is no longer imported anywhere in this file.
                        last_user_message = [
                            genai_types.Part.from_function_response(
                                name=result["name"],
                                response=result["response"],
                            )
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

                            # For MALFORMED_FUNCTION_CALL, retry before giving up
                            if fr_value == 10:
                                malformed_retries += 1

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

                                if malformed_retries <= MAX_MALFORMED_RETRIES:
                                    logger.warning(
                                        f"MALFORMED_FUNCTION_CALL detected - retrying "
                                        f"({malformed_retries}/{MAX_MALFORMED_RETRIES})",
                                        extra={
                                            "provider": self.model_name,
                                            "tool_iteration": tool_iteration,
                                            "malformed_retry": malformed_retries,
                                            "max_malformed_retries": MAX_MALFORMED_RETRIES,
                                            "message_count": len(messages),
                                            "tool_count": len(gemini_tools) if gemini_tools else 0,
                                            "chunk_count": len(raw_chunk_data),
                                            "last_chunk": last_chunk,
                                        }
                                    )
                                    tool_iteration += 1
                                    continue  # Re-enter loop, re-send same message

                                # Exhausted retries — log full diagnostic and fall through to error
                                logger.error(
                                    "MALFORMED_FUNCTION_CALL detected - all retries exhausted. "
                                    "RAW CHUNK DATA LOGGED FOR DIAGNOSIS.",
                                    extra={
                                        "provider": self.model_name,
                                        "tool_iteration": tool_iteration,
                                        "malformed_retries_exhausted": malformed_retries,
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

                        # Story 23.1 (AC6): no more placeholder-row writes from
                        # this branch. Use last_usage if present, otherwise omit
                        # the usage kwarg.
                        if trace and token_count > 0:
                            generation = None
                            end_kwargs: Dict[str, Any] = {}
                            try:
                                if last_usage is not None:
                                    prompt_tokens = last_usage["prompt_tokens"]
                                    completion_tokens = last_usage["completion_tokens"]
                                    cached_tokens = last_usage.get("cached_tokens", 0)
                                    # Bug 25.2 (AC1): use helper-computed
                                    # non-cached input for Langfuse emission;
                                    # fall back to recomputation for safety if
                                    # an older usage shape lacks the key.
                                    non_cached_input_tokens = last_usage.get(
                                        "non_cached_input_tokens",
                                        max(0, prompt_tokens - cached_tokens),
                                    )
                                else:
                                    prompt_tokens = 0
                                    completion_tokens = 0
                                    cached_tokens = 0
                                    non_cached_input_tokens = 0
                                    logger.warning(
                                        "Gemini stream ended without STOP and without usage_metadata",
                                        extra={
                                            "provider": self.model_name,
                                            "event": "usage_metadata_missing",
                                            "model": self.model_name,
                                            "chunk_count": chunk_count,
                                            "tool_iterations": tool_iteration,
                                            "finish_reason": fr_name,
                                        }
                                    )

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

                                end_kwargs = {
                                    "output": truncated_completion,
                                    "metadata": {"duration_ms": duration_ms},
                                }
                                if last_usage is not None:
                                    cost_info = self.calculate_cost({
                                        "prompt_tokens": prompt_tokens,
                                        "completion_tokens": completion_tokens,
                                        "cached_tokens": cached_tokens,
                                    })
                                    # Bug 25.2 (AC1): emit non-cached input only
                                    # — see helper docstring for the math.
                                    end_kwargs["usage"] = {
                                        "input": non_cached_input_tokens,
                                        "output": completion_tokens,
                                        "input_cached": cached_tokens,
                                        "total": prompt_tokens + completion_tokens,
                                        "input_cost": cost_info.get("input_cost", 0),
                                        "output_cost": cost_info.get("output_cost", 0),
                                        "cached_cost": cost_info.get("cached_cost", 0),
                                        "total_cost": cost_info.get("total_cost", 0)
                                    }
                                    logger.info(
                                        "Langfuse generation tracked (ended without STOP)",
                                        extra={
                                            "provider": self.model_name,
                                            "prompt_tokens": prompt_tokens,
                                            "completion_tokens": completion_tokens,
                                            "cached_tokens": cached_tokens,
                                            "non_cached_input_tokens": non_cached_input_tokens,
                                            "cost_usd": cost_info.get("total_cost", 0)
                                        }
                                    )
                                else:
                                    logger.info(
                                        "Langfuse generation tracked without usage (ended without STOP)",
                                        extra={
                                            "provider": self.model_name,
                                            "event": "usage_metadata_missing",
                                        }
                                    )
                            except Exception as e:
                                logger.warning(
                                    f"Failed to build Gemini Langfuse generation (ended without STOP): {str(e)}",
                                    extra={"provider": self.model_name, "error": str(e)}
                                )
                            finally:
                                if generation is not None:
                                    try:
                                        generation.end(**end_kwargs)
                                    except Exception as end_err:
                                        logger.warning(
                                            f"Failed to end Gemini Langfuse generation: {str(end_err)}",
                                            extra={"provider": self.model_name, "error": str(end_err)}
                                        )

                        # Yield done event even without STOP. We pass token_count
                        # (chunk count) for behavioral compatibility with the
                        # downstream SSE consumer — this number is NOT used for
                        # cost; cost rides on Langfuse's usage_metadata path.
                        yield {
                            "type": "done",
                            "tokens_used": {
                                "prompt": 0,
                                "completion": token_count
                            }
                        }
                        return

                except (ContextLengthError, RateLimitError):
                    # Already-typed Annie exceptions: no need to re-classify.
                    raise
                except Exception as e:
                    err_duration_ms = int((time.time() - start_time) * 1000)

                    # Story 23.1 (AC5): emit a Langfuse generation with level=ERROR
                    # before propagating. last_usage is populated when Gemini's
                    # 429 comes back after prompt-processing.
                    self._trace_error_generation(
                        trace=trace,
                        error=e,
                        duration_ms=err_duration_ms,
                        last_usage=last_usage,
                        tool_iteration=tool_iteration,
                    )

                    # Story 24.1 (AC11.5): typed-exception-aware classification.
                    # Check context-overflow FIRST (more specific), then rate limit.
                    if self._is_context_length_error(e):
                        logger.warning(
                            "Gemini context length exceeded",
                            extra={
                                "provider": self.model_name,
                                "error_type": type(e).__name__,
                                "error": str(e)
                            }
                        )
                        raise ContextLengthError(self.model_name, str(e), e)

                    if self._is_rate_limit_error(e):
                        logger.warning(
                            "Gemini quota/rate limit exceeded",
                            extra={
                                "provider": self.model_name,
                                "error_type": type(e).__name__,
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

        except ContextLengthError:
            # Re-raise context length errors as-is
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
            self._trace_error_generation(
                trace=trace,
                error=e,
                duration_ms=duration_ms,
                last_usage=last_usage,
                tool_iteration=tool_iteration,
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
            from api.mcp_client import MCPNetworkError, MCPToolError

            # Inject correct user_id to override any LLM-inferred value
            inject_user_id(
                tool_arguments, user_id, logger,
                {"provider": self.model_name, "tool_name": tool_name}
            )

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
