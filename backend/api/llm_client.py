"""
LLM Client Module (Factory Pattern)

Unified client for LLM providers with factory pattern for provider abstraction.
Maintains backward compatibility while enabling seamless provider switching.

This module now acts as a thin facade/factory, delegating all operations
to provider-specific implementations (GrokProvider, ChatGPTProvider, etc.).
"""

from typing import Any, AsyncGenerator, Dict, List, Optional
from api.config import get_config
from api.logging import get_logger
from api.providers import (
    BaseProvider,
    GrokProvider,
    ChatGPTProvider,
    GeminiProvider,  # Story 9.2
    ProviderError,
    RateLimitError
)

logger = get_logger(__name__)


# Re-export exception types for backward compatibility
class LLMClientError(Exception):
    """Base exception for LLM client errors."""
    pass


# Provider exceptions are already defined in providers package
# We re-export them here for backward compatibility
__all__ = [
    "LLMClient",
    "LLMClientError",
    "ProviderError",
    "RateLimitError"
]


class LLMClient:
    """
    Unified LLM client supporting multiple providers via factory pattern.

    Supports:
    - Grok-4 (XAI API) - via GrokProvider
    - ChatGPT-5 (OpenAI API) - via ChatGPTProvider
    - Gemini 3 Pro (Google AI API) - via GeminiProvider (Story 9.2)

    Features:
    - Automatic provider selection based on LLM_PROVIDER env var
    - Zero API changes - existing code continues to work
    - Provider-specific implementations isolated in provider classes
    - Automatic failover support (primary to fallback)
    - Structured error logging
    - Environment-based configuration

    Design Pattern: Factory + Facade
    - Factory: Creates appropriate provider instance based on configuration
    - Facade: Provides simple interface hiding provider complexity
    """

    def __init__(self):
        """
        Initialize LLM client with provider factory pattern.

        The provider is selected based on LLM_PROVIDER environment variable.
        Defaults to Grok-4 if provider is unknown or not configured.

        Raises:
            ValueError: If no providers are configured (missing API keys)
        """
        config = get_config()

        # Get provider selection from environment
        provider_name = config.get("LLM_PROVIDER", "grok-4")

        # Get API keys to determine which providers are available
        grok_api_key = config.get("GROK_API_KEY")
        chatgpt_api_key = config.get("CHATGPT_API_KEY")
        gemini_api_key = config.get("GEMINI_API_KEY")  # Story 9.2

        # Track which providers are available
        self.providers_available = {
            "grok-4": bool(grok_api_key and grok_api_key != "REPLACE_ME"),
            "chatgpt-5": bool(chatgpt_api_key and chatgpt_api_key != "REPLACE_ME"),
            "gemini-3-pro-preview": bool(gemini_api_key and gemini_api_key != "REPLACE_ME"),  # Story 9.2
            "gemini-3-flash-preview": bool(gemini_api_key and gemini_api_key != "REPLACE_ME"),  # Fallback for Gemini 3 Pro
            "gemini-2.5-pro": bool(gemini_api_key and gemini_api_key != "REPLACE_ME")  # Legacy fallback
        }

        # Instantiate provider based on configuration
        self.primary_provider_name = provider_name
        self.provider: Optional[BaseProvider] = None

        try:
            if provider_name == "grok-4" and self.providers_available["grok-4"]:
                self.provider = GrokProvider()
            elif provider_name == "chatgpt-5" and self.providers_available["chatgpt-5"]:
                self.provider = ChatGPTProvider()
            elif provider_name == "gemini-3-pro-preview" and self.providers_available["gemini-3-pro-preview"]:
                # Story 9.2: Gemini 3 Pro support
                self.provider = GeminiProvider()
            else:
                # Unknown provider or provider not configured, try fallback
                logger.warning(
                    f"Provider '{provider_name}' not available. Attempting fallback.",
                    extra={"requested_provider": provider_name, "providers_available": self.providers_available}
                )

                # Try Grok-4 as default fallback
                if self.providers_available["grok-4"]:
                    self.provider = GrokProvider()
                    self.primary_provider_name = "grok-4"
                    logger.info("Using Grok-4 as fallback provider")
                # Try ChatGPT-5 as secondary fallback
                elif self.providers_available["chatgpt-5"]:
                    self.provider = ChatGPTProvider()
                    self.primary_provider_name = "chatgpt-5"
                    logger.info("Using ChatGPT-5 as fallback provider")
                # Try Gemini as tertiary fallback (Story 9.2)
                elif self.providers_available["gemini-3-pro-preview"]:
                    self.provider = GeminiProvider()
                    self.primary_provider_name = "gemini-3-pro-preview"
                    logger.info("Using Gemini 3 Pro as fallback provider")
                else:
                    raise ValueError(
                        "No LLM providers configured. Please set GROK_API_KEY, CHATGPT_API_KEY, or GEMINI_API_KEY."
                    )

        except ValueError as e:
            # Provider initialization failed (missing API key)
            logger.error(
                "Failed to initialize provider",
                extra={"provider": provider_name, "error": str(e)}
            )
            raise

        logger.info(
            "LLM Client initialized with factory pattern",
            extra={
                "primary_provider": self.primary_provider_name,
                "provider_class": self.provider.__class__.__name__,
                "grok4_available": self.providers_available["grok-4"],
                "chatgpt5_available": self.providers_available["chatgpt-5"]
            }
        )

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - close provider HTTP client."""
        await self.close()

    async def close(self):
        """Close provider HTTP client connection."""
        if self.provider:
            await self.provider.close()

    def _get_fallback_provider(self, failed_provider: str) -> Optional[str]:
        """
        Get fallback provider for a failed provider.

        Fallback chains:
        - grok-4 → chatgpt-5
        - chatgpt-5 → grok-4
        - gemini-3-pro-preview → gemini-3-flash-preview → grok-4
        - gemini-3-flash-preview → grok-4
        - gemini-2.5-pro → grok-4

        Args:
            failed_provider: Provider that failed

        Returns:
            Fallback provider name, or None if no fallback available
        """
        if failed_provider == "grok-4" and self.providers_available["chatgpt-5"]:
            return "chatgpt-5"
        elif failed_provider == "chatgpt-5" and self.providers_available["grok-4"]:
            return "grok-4"
        elif failed_provider == "gemini-3-pro-preview":
            # Gemini 3 Pro → Gemini 3 Flash → Grok-4
            if self.providers_available["gemini-3-flash-preview"]:
                return "gemini-3-flash-preview"
            elif self.providers_available["grok-4"]:
                return "grok-4"
        elif failed_provider == "gemini-3-flash-preview" and self.providers_available["grok-4"]:
            return "grok-4"
        elif failed_provider == "gemini-2.5-pro" and self.providers_available["grok-4"]:
            return "grok-4"
        return None

    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        mcp_client=None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Send streaming chat completion request with automatic provider failover.

        This method delegates to the provider's stream_chat_completion implementation.
        If the primary provider fails, it automatically falls back to the alternative provider.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
                     Example: [{"role": "user", "content": "Hello"}]
            tools: Optional list of tools/functions in OpenAI format for function calling
            mcp_client: MCP client instance for tool execution (required if tools provided)

        Yields:
            Stream event dictionaries:
            - Token event: {"type": "token", "content": "text chunk"}
            - Tool call events: {"type": "tool_call_started|completed|failed", ...}
            - Completion event: {"type": "done", "tokens_used": {"prompt": N, "completion": M}}
            - Error event: {"type": "error", "message": "error message", "code": "ERROR_CODE"}

        Raises:
            LLMClientError: If all providers fail before streaming starts
        """
        provider_name = self.primary_provider_name
        fallback_name = self._get_fallback_provider(provider_name)

        logger.info(
            "Starting streaming chat completion",
            extra={
                "primary_provider": provider_name,
                "fallback_provider": fallback_name,
                "message_count": len(messages),
                "tools_provided": len(tools) if tools else 0,
                "mcp_client_provided": mcp_client is not None
            }
        )

        # Try primary provider
        try:
            async for event in self.provider.stream_chat_completion(messages, tools, mcp_client=mcp_client):
                yield event
            return  # Successfully completed streaming

        except RateLimitError as e:
            # Log rate limit and try fallback
            logger.warning(
                "Rate limit on primary provider during streaming, attempting fallback",
                extra={
                    "failed_provider": provider_name,
                    "fallback_provider": fallback_name,
                    "retry_after": e.retry_after
                }
            )

            # If no fallback, yield error event
            if not fallback_name:
                logger.error(
                    "No fallback provider available for streaming rate limit",
                    extra={"failed_provider": provider_name}
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
                    "failed_provider": provider_name,
                    "fallback_provider": fallback_name,
                    "error": e.message
                }
            )

            # If no fallback, yield error event
            if not fallback_name:
                logger.error(
                    "No fallback provider available for streaming",
                    extra={"failed_provider": provider_name}
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
                extra={"fallback_provider": fallback_name}
            )

            # Instantiate fallback provider
            if fallback_name == "grok-4":
                fallback_provider = GrokProvider()
            elif fallback_name == "chatgpt-5":
                fallback_provider = ChatGPTProvider()
            elif fallback_name == "gemini-3-flash-preview":
                fallback_provider = GeminiProvider(model_override="gemini-2.0-flash")
            elif fallback_name == "gemini-2.5-pro":
                fallback_provider = GeminiProvider(model_override="gemini-2.5-pro")
            elif fallback_name == "gemini-3-pro-preview":
                fallback_provider = GeminiProvider(model_override="gemini-3-pro-preview")
            else:
                raise ValueError(f"Unknown fallback provider: {fallback_name}")

            async with fallback_provider:
                async for event in fallback_provider.stream_chat_completion(messages, tools, mcp_client=mcp_client):
                    yield event

            logger.info(
                "Streaming fallback successful",
                extra={
                    "failed_provider": provider_name,
                    "successful_provider": fallback_name
                }
            )

        except (ProviderError, RateLimitError) as e:
            # Both providers failed
            logger.error(
                "All providers failed during streaming",
                extra={
                    "primary_provider": provider_name,
                    "fallback_provider": fallback_name,
                    "error": str(e)
                }
            )

            # Yield error event
            yield {
                "type": "error",
                "message": "I'm experiencing technical difficulties. Please try again in a moment.",
                "code": "ALL_PROVIDERS_FAILED"
            }

    async def chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        mcp_client=None
    ) -> Dict[str, Any]:
        """
        Send chat completion request with automatic provider failover.

        Note: This method is provided for backward compatibility but is not currently
        used by the application. The application uses stream_chat_completion exclusively.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
            tools: Optional list of tools/functions in OpenAI format
            mcp_client: MCP client instance for tool execution (required if tools provided)

        Returns:
            Response dictionary with 'choices', 'usage', etc.

        Raises:
            LLMClientError: If all providers fail
        """
        # Collect all tokens from streaming response
        tokens = []
        usage = {}

        async for event in self.stream_chat_completion(messages, tools, mcp_client):
            if event["type"] == "token":
                tokens.append(event["content"])
            elif event["type"] == "done":
                usage = event.get("tokens_used", {})
            elif event["type"] == "error":
                raise LLMClientError(event["message"])

        # Build response in OpenAI format
        return {
            "choices": [{
                "message": {
                    "role": "assistant",
                    "content": "".join(tokens)
                },
                "finish_reason": "stop"
            }],
            "usage": {
                "prompt_tokens": usage.get("prompt", 0),
                "completion_tokens": usage.get("completion", 0),
                "total_tokens": usage.get("prompt", 0) + usage.get("completion", 0)
            }
        }

    def health_check(self) -> str:
        """
        Check primary provider availability.

        Returns:
            "ok" if primary provider is available
            "degraded" if only fallback provider is available
            "unavailable" if no providers are available
        """
        primary_available = self.providers_available.get(self.primary_provider_name, False)
        fallback = self._get_fallback_provider(self.primary_provider_name)
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
                "primary_provider": self.primary_provider_name,
                "primary_available": primary_available,
                "fallback_available": fallback_available
            }
        )

        return status

    @staticmethod
    def convert_mcp_tools_to_functions(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert MCP tool schemas to OpenAI function calling format.

        This is a convenience method delegating to BaseProvider's static method.
        Provided for backward compatibility with existing code.

        Args:
            mcp_tools: List of MCP tool schemas with 'name', 'description', 'inputSchema'

        Returns:
            List of function definitions in OpenAI format
        """
        return BaseProvider.convert_mcp_tools_to_functions(mcp_tools)
