"""
Unit Tests for GeminiToolAdapter

Tests schema conversion between OpenAI and Gemini formats.
"""

import pytest
from api.providers.gemini_tool_adapter import GeminiToolAdapter


class TestGeminiToolAdapterSchemaConversion:
    """Test OpenAI → Gemini schema conversion."""

    def test_convert_simple_tool_schema(self):
        """Test conversion of simple tool with string parameter."""
        adapter = GeminiToolAdapter()

        openai_tools = [{
            "type": "function",
            "function": {
                "name": "internet_search",
                "description": "Search the internet for information",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        }]

        gemini_tools = adapter.convert_openai_to_gemini_schema(openai_tools)

        assert len(gemini_tools) == 1
        assert gemini_tools[0]["name"] == "internet_search"
        assert gemini_tools[0]["description"] == "Search the internet for information"
        assert gemini_tools[0]["parameters"]["type"] == "OBJECT"
        assert gemini_tools[0]["parameters"]["properties"]["query"]["type"] == "STRING"
        assert gemini_tools[0]["parameters"]["required"] == ["query"]

    def test_convert_multiple_parameter_types(self):
        """Test conversion handles all parameter types correctly."""
        adapter = GeminiToolAdapter()

        openai_tools = [{
            "type": "function",
            "function": {
                "name": "test_tool",
                "description": "Test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "text_param": {"type": "string"},
                        "num_param": {"type": "integer"},
                        "float_param": {"type": "number"},
                        "bool_param": {"type": "boolean"},
                        "array_param": {"type": "array", "items": {"type": "string"}},
                        "object_param": {"type": "object"}
                    }
                }
            }
        }]

        gemini_tools = adapter.convert_openai_to_gemini_schema(openai_tools)

        props = gemini_tools[0]["parameters"]["properties"]
        assert props["text_param"]["type"] == "STRING"
        assert props["num_param"]["type"] == "INTEGER"
        assert props["float_param"]["type"] == "NUMBER"
        assert props["bool_param"]["type"] == "BOOLEAN"
        assert props["array_param"]["type"] == "ARRAY"
        assert props["object_param"]["type"] == "OBJECT"

    def test_convert_nested_objects(self):
        """Test conversion handles nested object properties."""
        adapter = GeminiToolAdapter()

        openai_tools = [{
            "type": "function",
            "function": {
                "name": "complex_tool",
                "description": "Complex tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "nested": {
                            "type": "object",
                            "properties": {
                                "inner_field": {"type": "string"}
                            }
                        }
                    }
                }
            }
        }]

        gemini_tools = adapter.convert_openai_to_gemini_schema(openai_tools)

        nested_props = gemini_tools[0]["parameters"]["properties"]["nested"]
        assert nested_props["type"] == "OBJECT"
        assert nested_props["properties"]["inner_field"]["type"] == "STRING"

    def test_convert_array_with_items_schema(self):
        """Test conversion handles array items schema."""
        adapter = GeminiToolAdapter()

        openai_tools = [{
            "type": "function",
            "function": {
                "name": "array_tool",
                "description": "Array tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of tags"
                        }
                    }
                }
            }
        }]

        gemini_tools = adapter.convert_openai_to_gemini_schema(openai_tools)

        tags_param = gemini_tools[0]["parameters"]["properties"]["tags"]
        assert tags_param["type"] == "ARRAY"
        assert tags_param["items"]["type"] == "STRING"
        assert tags_param["description"] == "List of tags"

    def test_convert_enum_constraints(self):
        """Test conversion preserves enum constraints."""
        adapter = GeminiToolAdapter()

        openai_tools = [{
            "type": "function",
            "function": {
                "name": "enum_tool",
                "description": "Enum tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "mode": {
                            "type": "string",
                            "enum": ["auto", "on", "off"]
                        }
                    }
                }
            }
        }]

        gemini_tools = adapter.convert_openai_to_gemini_schema(openai_tools)

        mode_param = gemini_tools[0]["parameters"]["properties"]["mode"]
        assert mode_param["enum"] == ["auto", "on", "off"]

    def test_convert_empty_tool_list(self):
        """Test conversion handles empty tool list."""
        adapter = GeminiToolAdapter()

        gemini_tools = adapter.convert_openai_to_gemini_schema([])

        assert gemini_tools == []

    def test_convert_tool_without_type_wrapper(self):
        """Test conversion handles tools without 'type: function' wrapper."""
        adapter = GeminiToolAdapter()

        openai_tools = [{
            "name": "simple_tool",
            "description": "Simple tool",
            "parameters": {
                "type": "object",
                "properties": {
                    "arg": {"type": "string"}
                }
            }
        }]

        gemini_tools = adapter.convert_openai_to_gemini_schema(openai_tools)

        assert len(gemini_tools) == 1
        assert gemini_tools[0]["name"] == "simple_tool"


class TestGeminiToolAdapterCallConversion:
    """Test Gemini → OpenAI function call conversion."""

    def test_convert_simple_function_call(self):
        """Test conversion of simple Gemini function call to OpenAI format."""
        adapter = GeminiToolAdapter()

        gemini_call = {
            "name": "internet_search",
            "args": {"query": "latest AI news"}
        }

        openai_call = adapter.convert_gemini_to_openai_call(gemini_call)

        assert openai_call["type"] == "function"
        assert openai_call["function"]["name"] == "internet_search"
        assert '"query": "latest AI news"' in openai_call["function"]["arguments"]
        assert "id" in openai_call

    def test_convert_function_call_with_complex_args(self):
        """Test conversion handles complex arguments."""
        adapter = GeminiToolAdapter()

        gemini_call = {
            "name": "complex_tool",
            "args": {
                "text": "hello",
                "number": 42,
                "nested": {"key": "value"},
                "array": [1, 2, 3]
            }
        }

        openai_call = adapter.convert_gemini_to_openai_call(gemini_call)

        assert openai_call["function"]["name"] == "complex_tool"
        # Verify arguments are JSON serialized
        import json
        args = json.loads(openai_call["function"]["arguments"])
        assert args["text"] == "hello"
        assert args["number"] == 42
        assert args["nested"]["key"] == "value"
        assert args["array"] == [1, 2, 3]


class TestGeminiToolAdapterResultFormatting:
    """Test tool result formatting for Gemini."""

    def test_format_successful_tool_result(self):
        """Test formatting of successful tool result."""
        adapter = GeminiToolAdapter()

        tool_result = {
            "status": "success",
            "data": {"temperature": 72, "condition": "sunny"}
        }

        formatted = adapter.format_tool_result_for_gemini("get_weather", tool_result)

        assert formatted["name"] == "get_weather"
        assert formatted["response"] == tool_result

    def test_format_large_tool_result_truncation(self):
        """Test that large results are truncated."""
        adapter = GeminiToolAdapter()

        # Create result larger than 10KB (default max_size)
        large_data = "x" * 15000
        tool_result = {"data": large_data}

        formatted = adapter.format_tool_result_for_gemini(
            "large_tool",
            tool_result,
            max_size=10000
        )

        assert formatted["name"] == "large_tool"
        assert formatted["response"]["truncated"] is True
        assert formatted["response"]["original_size"] > 10000
        assert "warning" in formatted["response"]

    def test_format_tool_result_with_custom_max_size(self):
        """Test custom max_size parameter."""
        adapter = GeminiToolAdapter()

        tool_result = {"data": "x" * 500}

        formatted = adapter.format_tool_result_for_gemini(
            "test_tool",
            tool_result,
            max_size=300
        )

        # Should be truncated since result is ~500 chars
        assert formatted["response"]["truncated"] is True


class TestGeminiToolAdapterEdgeCases:
    """Test edge cases and error handling."""

    def test_extract_tool_arguments(self):
        """Test extracting arguments from Gemini function call."""
        adapter = GeminiToolAdapter()

        gemini_call = {
            "name": "test_tool",
            "args": {"param1": "value1", "param2": 42}
        }

        args = adapter.extract_tool_arguments(gemini_call)

        assert args == {"param1": "value1", "param2": 42}

    def test_extract_tool_arguments_empty(self):
        """Test extracting arguments when none provided."""
        adapter = GeminiToolAdapter()

        gemini_call = {"name": "test_tool"}

        args = adapter.extract_tool_arguments(gemini_call)

        assert args == {}
