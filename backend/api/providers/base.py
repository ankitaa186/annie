"""
Base Provider Interface

Abstract base class defining the interface contract for all LLM providers.
This enables seamless provider switching with zero changes to calling code.
"""

from abc import ABC, abstractmethod
from typing import Any, AsyncGenerator, Dict, List, Optional


class ContextLengthError(Exception):
    """Raised when request exceeds model's context window."""
    def __init__(self, provider: str, message: str, original_error: Exception = None):
        self.provider = provider
        self.message = message
        self.original_error = original_error
        super().__init__(f"{provider}: {message}")


class BaseProvider(ABC):
    """
    Abstract base class for LLM providers.

    All providers must implement this interface to ensure feature parity and
    maintain backward compatibility when adding new providers.

    Design Pattern: Strategy Pattern
    - Each provider encapsulates a specific algorithm (API communication)
    - Providers are interchangeable via common interface
    - Client code remains unchanged when switching providers
    """

    @abstractmethod
    async def stream_chat_completion(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream chat completion from provider.

        Args:
            messages: List of message dictionaries with 'role' and 'content'
                     Example: [{"role": "user", "content": "Hello"}]
                     Supports 'tool' role for tool results
            tools: Optional list of tools/functions in OpenAI format for function calling
            **kwargs: Provider-specific parameters

        Yields:
            Stream event dictionaries:
            - Token event: {"type": "token", "content": "text chunk"}
            - Completion event: {"type": "done", "tokens_used": {"prompt": N, "completion": M}}
            - Error event: {"type": "error", "message": "error message", "code": "ERROR_CODE"}

        Raises:
            ProviderError: If provider call fails
            RateLimitError: If rate limit is hit
        """
        pass

    @abstractmethod
    def calculate_cost(self, usage: Dict[str, int]) -> Dict[str, float]:
        """
        Calculate cost for token usage.

        Args:
            usage: Token usage dictionary with keys:
                - prompt_tokens: Number of input tokens
                - completion_tokens: Number of output tokens
                - sources_used: (Grok-4 only) Number of Live Search sources accessed

        Returns:
            Dictionary with cost details:
            {
                "input_cost_usd": float,
                "output_cost_usd": float,
                "search_cost_usd": float,  # Grok-4 only
                "total_cost_usd": float
            }
        """
        pass

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Return provider name (e.g., 'grok-4', 'chatgpt-5', 'gemini-3.1-pro-preview').

        Returns:
            Provider name string
        """
        pass

    # Shared utility methods (implemented in base class)

    @staticmethod
    def _truncate_text(text: str, max_length: int = 1000) -> str:
        """
        Truncate text to maximum length for Langfuse tracing.

        Args:
            text: Text to truncate
            max_length: Maximum length (default: 1000 as per Epic 8 requirement)

        Returns:
            Truncated text with suffix indicating original length
        """
        if len(text) <= max_length:
            return text
        return text[:max_length] + "..." + f" (truncated from {len(text)} chars)"

    @staticmethod
    def convert_mcp_tools_to_functions(mcp_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert MCP tool schemas to OpenAI function calling format.

        Args:
            mcp_tools: List of MCP tool schemas with 'name', 'description', 'inputSchema'

        Returns:
            List of function definitions in OpenAI format

        Note:
            OpenAI-compatible format is used by Grok-4, ChatGPT-5, and most providers.
            Gemini requires separate adapter (Story 9.3).
        """
        from api.logging import get_logger
        logger = get_logger(__name__)

        functions = []

        for tool in mcp_tools:
            function = {
                "type": "function",
                "function": {
                    "name": tool.get("name", ""),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {
                        "type": "object",
                        "properties": {},
                        "required": []
                    })
                }
            }
            functions.append(function)

        logger.debug(
            "Converted MCP tools to function calling format",
            extra={"tool_count": len(functions)}
        )

        return functions
