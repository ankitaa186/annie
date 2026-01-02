"""
Gemini Tool Adapter

Converts between OpenAI tool format (used by MCP tools) and Gemini's function_declarations format.
Enables seamless MCP tool integration with Gemini 3 Pro provider.
"""

import json
from typing import Any, Dict, List, Optional
from api.logging import get_logger

logger = get_logger(__name__)


class GeminiToolAdapter:
    """
    Adapter for converting tool schemas and calls between OpenAI and Gemini formats.

    Format Differences:
    - OpenAI: {"type": "function", "function": {"name": "...", "parameters": {...}}}
    - Gemini: {"name": "...", "description": "...", "parameters": {...}}

    Parameter Type Mapping:
    - OpenAI uses lowercase: string, integer, boolean, object, array
    - Gemini uses uppercase: STRING, INTEGER, BOOLEAN, OBJECT, ARRAY
    """

    # Type mapping from OpenAI to Gemini
    TYPE_MAPPING = {
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "object": "OBJECT",
        "array": "ARRAY"
    }

    # Reverse mapping for Gemini to OpenAI
    REVERSE_TYPE_MAPPING = {v: k for k, v in TYPE_MAPPING.items()}

    def __init__(self):
        """Initialize Gemini Tool Adapter."""
        logger.debug("Gemini Tool Adapter initialized")

    def convert_openai_to_gemini_schema(self, openai_tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Convert OpenAI tool schemas to Gemini function_declarations format.

        Args:
            openai_tools: List of tools in OpenAI format:
                [{
                    "type": "function",
                    "function": {
                        "name": "internet_search",
                        "description": "Search the internet",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "query": {"type": "string", "description": "Search query"}
                            },
                            "required": ["query"]
                        }
                    }
                }]

        Returns:
            List of tools in Gemini function_declarations format:
                [{
                    "name": "internet_search",
                    "description": "Search the internet",
                    "parameters": {
                        "type": "OBJECT",
                        "properties": {
                            "query": {"type": "STRING", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }]
        """
        if not openai_tools:
            return []

        gemini_tools = []
        for tool in openai_tools:
            try:
                # Extract function definition from OpenAI format
                if "function" in tool:
                    func = tool["function"]
                else:
                    # Already in simplified format
                    func = tool

                # Build Gemini function declaration
                gemini_func = {
                    "name": func["name"],
                    "description": func.get("description", "")
                }

                # Convert parameters if present
                if "parameters" in func:
                    gemini_func["parameters"] = self._convert_parameters_to_gemini(func["parameters"])

                gemini_tools.append(gemini_func)

                logger.debug(
                    "Converted tool schema to Gemini format",
                    extra={"tool_name": func["name"]}
                )

            except Exception as e:
                logger.error(
                    "Failed to convert tool schema to Gemini format",
                    extra={"tool": tool, "error": str(e)},
                    exc_info=True
                )
                # Skip this tool but continue with others
                continue

        logger.info(
            "Converted OpenAI tools to Gemini format",
            extra={"tool_count": len(gemini_tools)}
        )

        return gemini_tools

    def _convert_parameters_to_gemini(self, openai_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert OpenAI parameter schema to Gemini format (recursive).

        Args:
            openai_params: OpenAI parameter schema

        Returns:
            Gemini parameter schema with uppercase types
        """
        gemini_params = {}

        # Convert type
        if "type" in openai_params:
            param_type = openai_params["type"]
            gemini_params["type"] = self.TYPE_MAPPING.get(param_type, param_type.upper())

        # Copy description
        if "description" in openai_params:
            gemini_params["description"] = openai_params["description"]

        # Convert properties (for object types)
        if "properties" in openai_params:
            gemini_params["properties"] = {}
            for prop_name, prop_schema in openai_params["properties"].items():
                gemini_params["properties"][prop_name] = self._convert_parameters_to_gemini(prop_schema)

        # Convert items (for array types)
        if "items" in openai_params:
            gemini_params["items"] = self._convert_parameters_to_gemini(openai_params["items"])

        # Copy required fields
        if "required" in openai_params:
            gemini_params["required"] = openai_params["required"]

        # Copy enum constraints
        if "enum" in openai_params:
            gemini_params["enum"] = openai_params["enum"]

        return gemini_params

    def convert_gemini_to_openai_call(self, gemini_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Convert Gemini function call to OpenAI tool call format.

        This is used to execute the tool via MCP client, which expects OpenAI format.

        Args:
            gemini_call: Gemini function call from API response:
                {
                    "name": "internet_search",
                    "args": {"query": "latest AI news"}
                }

        Returns:
            OpenAI tool call format compatible with MCP client:
                {
                    "type": "function",
                    "id": "call_123",
                    "function": {
                        "name": "internet_search",
                        "arguments": "{\"query\": \"latest AI news\"}"
                    }
                }
        """
        try:
            # Extract function call details
            tool_name = gemini_call.get("name", "")
            tool_args = gemini_call.get("args", {})

            # Convert to OpenAI format
            openai_call = {
                "type": "function",
                "id": f"call_{tool_name}_{id(gemini_call)}",  # Generate unique ID
                "function": {
                    "name": tool_name,
                    "arguments": json.dumps(tool_args) if isinstance(tool_args, dict) else str(tool_args)
                }
            }

            logger.debug(
                "Converted Gemini function call to OpenAI format",
                extra={"tool_name": tool_name}
            )

            return openai_call

        except Exception as e:
            logger.error(
                "Failed to convert Gemini function call to OpenAI format",
                extra={"gemini_call": gemini_call, "error": str(e)},
                exc_info=True
            )
            raise

    def format_tool_result_for_gemini(
        self,
        tool_name: str,
        tool_result: Dict[str, Any],
        max_size: int = 30000
    ) -> Dict[str, Any]:
        """
        Format MCP tool result for Gemini function response.

        Handles large results by truncating with a warning.

        Args:
            tool_name: Name of the tool that was executed
            tool_result: Result from MCP tool execution
            max_size: Maximum result size in characters (default: 30KB)

        Returns:
            Gemini function response format:
                {
                    "name": "internet_search",
                    "response": {
                        "result": {...},
                        "status": "success"
                    }
                }
        """
        try:
            # Serialize result to check size
            result_str = json.dumps(tool_result)
            result_size = len(result_str)

            # Truncate if too large
            if result_size > max_size:
                logger.warning(
                    "Tool result too large, truncating",
                    extra={
                        "tool_name": tool_name,
                        "original_size": result_size,
                        "max_size": max_size
                    }
                )

                # Truncate and add warning
                truncated_result = {
                    "result": result_str[:max_size],
                    "truncated": True,
                    "original_size": result_size,
                    "warning": f"Result truncated due to size ({result_size} > {max_size} chars)"
                }

                gemini_response = {
                    "name": tool_name,
                    "response": truncated_result
                }
            else:
                # Return full result
                gemini_response = {
                    "name": tool_name,
                    "response": tool_result
                }

            logger.debug(
                "Formatted tool result for Gemini",
                extra={
                    "tool_name": tool_name,
                    "result_size": result_size,
                    "truncated": result_size > max_size
                }
            )

            return gemini_response

        except Exception as e:
            logger.error(
                "Failed to format tool result for Gemini",
                extra={
                    "tool_name": tool_name,
                    "tool_result": str(tool_result)[:200],  # Log first 200 chars
                    "error": str(e)
                },
                exc_info=True
            )

            # Return error response
            return {
                "name": tool_name,
                "response": {
                    "error": f"Failed to format tool result: {str(e)}",
                    "status": "error"
                }
            }

    def extract_tool_arguments(self, gemini_call: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract tool arguments from Gemini function call.

        Helper method for cleaner code when executing tools.

        Args:
            gemini_call: Gemini function call object

        Returns:
            Dictionary of tool arguments
        """
        return gemini_call.get("args", {})
