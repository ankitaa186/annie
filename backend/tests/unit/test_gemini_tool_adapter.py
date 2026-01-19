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

    def test_default_max_size_is_100kb(self):
        """Test that default max_size is 100KB."""
        adapter = GeminiToolAdapter()

        # Create result just under 100KB - should pass through
        data = "x" * 99000
        tool_result = {"data": data}

        formatted = adapter.format_tool_result_for_gemini("test_tool", tool_result)

        # Should NOT be reduced
        assert formatted["response"] == tool_result

    def test_result_over_100kb_is_reduced(self):
        """Test that results over 100KB are reduced."""
        adapter = GeminiToolAdapter()

        # Create result over 100KB
        data = "x" * 110000
        tool_result = {"data": data}

        formatted = adapter.format_tool_result_for_gemini("test_tool", tool_result)

        # Should be reduced - string truncated with marker
        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 100000
        assert "TRUNCATED" in formatted["response"]["data"]

    def test_format_tool_result_with_custom_max_size(self):
        """Test custom max_size parameter."""
        adapter = GeminiToolAdapter()

        tool_result = {"data": "x" * 5000}

        formatted = adapter.format_tool_result_for_gemini(
            "test_tool",
            tool_result,
            max_size=1000
        )

        # Should be reduced
        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 1000


class TestSmartResultReduction:
    """Test smart result size reduction preserves valid JSON."""

    def test_reduce_large_list_keeps_valid_json(self):
        """Test reducing large list produces valid JSON with truncation notice."""
        adapter = GeminiToolAdapter()

        # Create list with 1000 items
        large_list = [{"id": i, "name": f"item_{i}", "data": "x" * 100} for i in range(1000)]
        tool_result = {"items": large_list}

        formatted = adapter.format_tool_result_for_gemini(
            "list_tool",
            tool_result,
            max_size=10000
        )

        # Verify result is valid JSON
        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 10000

        # Parse and verify structure
        parsed = json.loads(result_str)
        assert "items" in parsed

        # Should have truncation notice
        items_data = parsed["items"]
        if isinstance(items_data, dict):
            assert items_data.get("truncated") is True
            assert items_data.get("total") == 1000
            assert items_data.get("shown") < 1000

    def test_reduce_large_dict_keeps_valid_json(self):
        """Test reducing large dict produces valid JSON."""
        adapter = GeminiToolAdapter()

        # Create dict with many keys
        large_dict = {f"key_{i}": "x" * 500 for i in range(100)}

        formatted = adapter.format_tool_result_for_gemini(
            "dict_tool",
            large_dict,
            max_size=5000
        )

        # Verify result is valid JSON
        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 5000

        # Parse and verify it's valid
        parsed = json.loads(result_str)
        assert isinstance(parsed, dict)

    def test_reduce_large_string_adds_truncation_marker(self):
        """Test reducing large string adds clear truncation marker."""
        adapter = GeminiToolAdapter()

        large_string = "x" * 10000
        tool_result = {"content": large_string}

        formatted = adapter.format_tool_result_for_gemini(
            "string_tool",
            tool_result,
            max_size=1000
        )

        # Verify result is valid JSON
        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 1000

        # Verify truncation marker is present
        parsed = json.loads(result_str)
        assert "TRUNCATED" in parsed["content"]
        assert "10000 total chars" in parsed["content"]

    def test_reduce_nested_structure_preserves_validity(self):
        """Test deeply nested structures remain valid JSON after reduction."""
        adapter = GeminiToolAdapter()

        nested = {
            "level1": {
                "level2": {
                    "level3": {
                        "data": [{"item": "x" * 1000} for _ in range(50)]
                    }
                }
            }
        }

        formatted = adapter.format_tool_result_for_gemini(
            "nested_tool",
            nested,
            max_size=5000
        )

        # Verify result is valid JSON
        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 5000

        # Parse and verify structure is valid
        parsed = json.loads(result_str)
        assert isinstance(parsed, dict)

    def test_reduce_empty_list_unchanged(self):
        """Test empty list passes through unchanged."""
        adapter = GeminiToolAdapter()

        tool_result = {"items": []}

        formatted = adapter.format_tool_result_for_gemini(
            "empty_tool",
            tool_result,
            max_size=100
        )

        assert formatted["response"]["items"] == []

    def test_reduce_primitives_unchanged(self):
        """Test primitive values pass through unchanged."""
        adapter = GeminiToolAdapter()

        tool_result = {
            "count": 42,
            "ratio": 3.14,
            "enabled": True,
            "data": None
        }

        formatted = adapter.format_tool_result_for_gemini(
            "primitive_tool",
            tool_result,
            max_size=1000
        )

        assert formatted["response"]["count"] == 42
        assert formatted["response"]["ratio"] == 3.14
        assert formatted["response"]["enabled"] is True
        assert formatted["response"]["data"] is None

    def test_reduce_mixed_content_prioritizes_small_keys(self):
        """Test reduction keeps small values and reduces large ones."""
        adapter = GeminiToolAdapter()

        tool_result = {
            "small_key": "small",
            "medium_key": "x" * 500,
            "large_key": "x" * 5000
        }

        formatted = adapter.format_tool_result_for_gemini(
            "mixed_tool",
            tool_result,
            max_size=1000
        )

        import json
        result_str = json.dumps(formatted["response"])
        assert len(result_str) <= 1000

        parsed = json.loads(result_str)
        # Small key should be preserved
        assert parsed.get("small_key") == "small"

    def test_home_assistant_large_response_simulation(self):
        """Simulate Home Assistant query returning 400KB+ of entities."""
        adapter = GeminiToolAdapter()

        # Simulate HA entities response (like the 424KB we saw in logs)
        entities = []
        for i in range(500):
            entities.append({
                "entity_id": f"sensor.device_{i}",
                "state": "on" if i % 2 == 0 else "off",
                "attributes": {
                    "friendly_name": f"Device {i}",
                    "device_class": "switch",
                    "last_changed": "2026-01-19T12:00:00Z",
                    "extra_data": "x" * 500  # Simulate attribute bloat
                }
            })

        tool_result = {
            "status": "success",
            "entities": entities,
            "count": len(entities)
        }

        # Original would be ~400KB+
        import json
        original_size = len(json.dumps(tool_result))
        assert original_size > 300000  # Verify it's large

        # Reduce to 100KB (default)
        formatted = adapter.format_tool_result_for_gemini(
            "home_assistant_query",
            tool_result
        )

        result_str = json.dumps(formatted["response"])

        # Must be under 100KB
        assert len(result_str) <= 100000

        # Must be valid JSON
        parsed = json.loads(result_str)
        assert isinstance(parsed, dict)

        # Should have truncation indicators
        assert "status" in parsed or "entities" in parsed or "truncated" in str(parsed)

    def test_json_always_valid_after_reduction(self):
        """Stress test: random large structures always produce valid JSON."""
        import json
        import random

        adapter = GeminiToolAdapter()

        for _ in range(10):
            # Generate random structure
            depth = random.randint(1, 5)
            result = {}
            current = result

            for d in range(depth):
                key = f"level_{d}"
                if d == depth - 1:
                    # Leaf: large list or string
                    if random.choice([True, False]):
                        current[key] = ["item_" + "x" * random.randint(100, 1000) for _ in range(random.randint(10, 100))]
                    else:
                        current[key] = "x" * random.randint(1000, 10000)
                else:
                    current[key] = {}
                    current = current[key]

            formatted = adapter.format_tool_result_for_gemini(
                "stress_test",
                result,
                max_size=5000
            )

            # Must always be valid JSON
            result_str = json.dumps(formatted["response"])
            assert len(result_str) <= 5000

            # Must parse without error
            parsed = json.loads(result_str)
            assert parsed is not None


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
