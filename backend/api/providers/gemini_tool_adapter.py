"""
Gemini Tool Adapter

Converts between OpenAI tool format (used by MCP tools) and Gemini's function_declarations format.
Enables seamless MCP tool integration with Gemini 3 Pro provider.
"""

import json
from typing import Any, Dict, List
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

    def _find_empty_objects(
        self,
        schema: Dict[str, Any],
        path: str = ""
    ) -> List[str]:
        """
        Recursively find OBJECT types without properties defined.

        These cause MALFORMED_FUNCTION_CALL errors because Gemini doesn't
        know what fields are valid for the object.

        Args:
            schema: The schema to check
            path: Current path for error reporting

        Returns:
            List of paths to empty object definitions
        """
        issues = []

        if isinstance(schema, dict):
            # Check if this is an object type with no properties
            if schema.get("type") in ("OBJECT", "object"):
                props = schema.get("properties", {})
                # Only flag nested objects, not top-level inputSchema
                if not props and path and "properties" in path:
                    issues.append(path)

            # Recurse into nested structures
            for key, value in schema.items():
                new_path = f"{path}.{key}" if path else key
                issues.extend(self._find_empty_objects(value, new_path))

        elif isinstance(schema, list):
            for i, item in enumerate(schema):
                issues.extend(self._find_empty_objects(item, f"{path}[{i}]"))

        return issues

    def _validate_tool_schema(self, tool_name: str, gemini_schema: Dict[str, Any]) -> None:
        """
        Validate a converted Gemini tool schema for common issues.

        Logs warnings for schemas that may cause MALFORMED_FUNCTION_CALL errors.

        Args:
            tool_name: Name of the tool for logging
            gemini_schema: The converted Gemini schema to validate
        """
        # Check for empty objects
        empty_objects = self._find_empty_objects(gemini_schema)

        if empty_objects:
            logger.warning(
                "Tool schema has OBJECT types without properties - may cause MALFORMED_FUNCTION_CALL",
                extra={
                    "tool_name": tool_name,
                    "empty_object_paths": empty_objects,
                    "issue": "EMPTY_OBJECT_SCHEMA",
                    "recommendation": "Add 'properties' to define valid fields for these objects"
                }
            )

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

                # Validate schema for potential issues
                self._validate_tool_schema(func["name"], gemini_func)

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
        max_size: int = 100000
    ) -> Dict[str, Any]:
        """
        Format MCP tool result for Gemini function response.

        Handles large results by intelligently reducing data while preserving valid JSON.

        Args:
            tool_name: Name of the tool that was executed
            tool_result: Result from MCP tool execution
            max_size: Maximum result size in characters (default: 100KB)

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

            # If under limit, return as-is
            if result_size <= max_size:
                logger.debug(
                    "Formatted tool result for Gemini",
                    extra={
                        "tool_name": tool_name,
                        "result_size": result_size,
                        "truncated": False
                    }
                )
                return {
                    "name": tool_name,
                    "response": tool_result
                }

            # Result too large - try to reduce intelligently
            logger.warning(
                "Tool result too large, applying smart reduction",
                extra={
                    "tool_name": tool_name,
                    "original_size": result_size,
                    "max_size": max_size
                }
            )

            reduced_result = self._reduce_result_size(tool_result, max_size)
            reduced_str = json.dumps(reduced_result)

            logger.info(
                "Tool result reduced successfully",
                extra={
                    "tool_name": tool_name,
                    "original_size": result_size,
                    "reduced_size": len(reduced_str),
                    "max_size": max_size
                }
            )

            return {
                "name": tool_name,
                "response": reduced_result
            }

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

    def _reduce_result_size(
        self,
        result: Any,
        max_size: int,
        depth: int = 0
    ) -> Any:
        """
        Recursively reduce result size while preserving valid JSON structure.

        Strategy:
        1. For lists: Keep first N items that fit within budget
        2. For dicts: Keep all keys but reduce nested values
        3. For strings: Truncate with ellipsis marker
        4. For primitives: Return as-is

        Args:
            result: The result to reduce
            max_size: Target maximum size in characters
            depth: Current recursion depth (for logging)

        Returns:
            Reduced result that serializes to valid JSON under max_size
        """
        # Check current size
        current_str = json.dumps(result)
        if len(current_str) <= max_size:
            return result

        # Handle different types
        if isinstance(result, list):
            # For lists, progressively reduce item count
            if len(result) == 0:
                return result

            # Binary search for optimal item count
            reduced_list = []
            overhead = 50  # Reserve space for metadata
            target_size = max_size - overhead

            for item in result:
                test_list = reduced_list + [item]
                test_str = json.dumps(test_list)
                if len(test_str) <= target_size:
                    reduced_list.append(item)
                else:
                    # Try reducing the item itself if it's large
                    reduced_item = self._reduce_result_size(item, target_size // 2, depth + 1)
                    test_list = reduced_list + [reduced_item]
                    test_str = json.dumps(test_list)
                    if len(test_str) <= target_size:
                        reduced_list.append(reduced_item)
                    else:
                        break

            # Add truncation notice
            if len(reduced_list) < len(result):
                return {
                    "items": reduced_list,
                    "truncated": True,
                    "shown": len(reduced_list),
                    "total": len(result),
                    "notice": f"Showing {len(reduced_list)} of {len(result)} items due to size limit"
                }
            return reduced_list

        elif isinstance(result, dict):
            # For dicts, try to reduce large nested values
            reduced_dict = {}
            # Reserve space for truncation metadata (count + notice, not full key list)
            overhead = 150
            target_size = max_size - overhead
            current_size = 2  # Start with {}

            # Sort keys by value size (smallest first) to maximize key retention
            sorted_keys = sorted(
                result.keys(),
                key=lambda k: len(json.dumps(result[k]))
            )

            truncated_count = 0
            for key in sorted_keys:
                value = result[key]
                value_str = json.dumps(value)
                value_size = len(value_str)

                # Calculate size with this key-value pair
                pair_size = len(json.dumps(key)) + value_size + 4  # key: value,

                if current_size + pair_size <= target_size:
                    reduced_dict[key] = value
                    current_size += pair_size
                else:
                    # Try to reduce the value
                    remaining = target_size - current_size - len(json.dumps(key)) - 4
                    if remaining > 100:  # Minimum useful size
                        reduced_value = self._reduce_result_size(value, remaining, depth + 1)
                        reduced_dict[key] = reduced_value
                        current_size += len(json.dumps(key)) + len(json.dumps(reduced_value)) + 4
                    else:
                        truncated_count += 1

            if truncated_count > 0:
                # Only store count, not full list of keys (to avoid bloating response)
                reduced_dict["_truncated"] = True
                reduced_dict["_keys_omitted"] = truncated_count
                reduced_dict["_notice"] = f"{truncated_count} keys omitted due to size limit"

            return reduced_dict

        elif isinstance(result, str):
            # For strings, truncate with clear marker
            if len(result) > max_size - 50:
                truncate_at = max_size - 80
                return result[:truncate_at] + f"... [TRUNCATED, {len(result)} total chars]"
            return result

        else:
            # Primitives (int, float, bool, None) - return as-is
            return result

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
