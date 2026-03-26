"""
Unit tests for update_user_profile MCP tool

Story 15.4: Update User Profile Tool
- Tests the update_user_profile_tool_handler function
- Tests all response code handling (200/201, 400, 404, 5xx, timeout)
- Tests category validation
- Tests all value types (string, number, boolean, array)
- Tests source="llm_explicit" in payload
- Tests retry logic with exponential backoff
- Tests tool schema definition
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from mcp_server.tools import (
    update_user_profile_tool_handler,
    update_user_profile_tool,
    ALLOWED_PROFILE_CATEGORIES,
    CANONICAL_FIELDS,
    FIELD_NAME_ALIASES
)


@pytest.fixture
def mock_profile_response():
    """Success response from agentic-memories profile API."""
    return {
        "user_id": "user123",
        "category": "preferences",
        "field_name": "communication_style",
        "value": "formal",
        "previous_value": "casual",
        "confidence": 100.0,
        "last_updated": "2025-12-30T12:00:00Z"
    }


@pytest.fixture
def mock_httpx_response():
    """Factory for creating mock httpx responses."""
    def _create(status_code: int, json_data: dict = None):
        mock_response = MagicMock()
        mock_response.status_code = status_code
        mock_response.json.return_value = json_data or {}
        mock_response.text = ""
        return mock_response
    return _create


class TestUpdateUserProfileToolHandler:
    """Test update_user_profile_tool_handler function."""

    @pytest.mark.asyncio
    async def test_success_path(self, mock_profile_response, mock_httpx_response):
        """AC #1: PUT to Profile API succeeds."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            assert result["status"] == "success"
            assert result["value"] == "formal"
            assert result["previous_value"] == "casual"
            assert result["confidence"] == 100.0
            assert result["category"] == "preferences"
            assert result["field_name"] == "communication_style"

    @pytest.mark.asyncio
    async def test_success_with_201_status(self, mock_profile_response, mock_httpx_response):
        """AC #1: PUT to Profile API succeeds with 201 status."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(201, mock_profile_response))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            assert result["status"] == "success"

    @pytest.mark.asyncio
    async def test_invalid_category_rejected(self):
        """AC #2: Category validation rejects invalid categories."""
        result = await update_user_profile_tool_handler(
            user_id="user123",
            category="invalid_category",
            field_name="test",
            value="test"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "Invalid category" in result["error_message"]
        assert "invalid_category" in result["error_message"]

    @pytest.mark.asyncio
    async def test_all_valid_categories(self, mock_profile_response, mock_httpx_response):
        """AC #2: All valid categories are accepted."""
        # Map each category to a valid canonical field name
        category_field_map = {
            "basics": "name",
            "preferences": "communication_style",
            "goals": "short_term",
            "interests": "hobbies",
            "background": "skills",
            "health": "allergies",
            "personality": "personality_type",
            "values": "life_values",
        }
        for category in ALLOWED_PROFILE_CATEGORIES:
            with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                response_data = {**mock_profile_response, "category": category}
                mock_client.put = AsyncMock(return_value=mock_httpx_response(200, response_data))
                mock_client_class.return_value = mock_client

                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category=category,
                    field_name=category_field_map[category],
                    value="test_value"
                )

                assert result["status"] == "success", f"Category {category} should be valid"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("value_type,test_value", [
        ("string", "test string"),
        ("number_int", 42),
        ("number_float", 3.14),
        ("boolean_true", True),
        ("boolean_false", False),
        ("array_strings", ["item1", "item2", "item3"]),
        ("array_mixed", ["item1", 42, True]),
    ])
    async def test_all_value_types(self, value_type, test_value, mock_httpx_response):
        """AC #3: All value types (string, number, boolean, array) supported."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, {
                "user_id": "user123",
                "value": test_value,
                "previous_value": None,
                "confidence": 100.0,
                "last_updated": "2025-12-30T12:00:00Z"
            }))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value=test_value
            )

            assert result["status"] == "success", f"Value type {value_type} should work"

    @pytest.mark.asyncio
    async def test_source_llm_explicit_in_request(self, mock_httpx_response):
        """AC #4: source='llm_explicit' is set in all requests."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, {
                "user_id": "user123",
                "value": "formal",
                "confidence": 100.0,
                "last_updated": "2025-12-30T12:00:00Z"
            }))
            mock_client_class.return_value = mock_client

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            # Verify PUT was called with source="llm_explicit"
            call_args = mock_client.put.call_args
            request_body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert request_body["source"] == "llm_explicit"

    @pytest.mark.asyncio
    async def test_404_not_found(self, mock_httpx_response):
        """AC #5: Handle 404 (Not Found) with clear error message."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(404, {}))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "NOT_FOUND"
            assert "not found" in result["error_message"].lower()
            assert "preferences/communication_style" in result["error_message"]

    @pytest.mark.asyncio
    async def test_400_validation_error(self, mock_httpx_response):
        """AC #6: Handle 400 (Invalid Request) with validation error."""
        mock_response = mock_httpx_response(400, {
            "message": "Value format is invalid"
        })

        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_response)
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="invalid_value_that_api_rejects"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "VALIDATION_ERROR"
            assert "invalid" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_retry_on_500(self, mock_profile_response, mock_httpx_response):
        """AC #7: Retry with exponential backoff on 5xx errors."""
        call_count = 0

        async def mock_put(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                return mock_httpx_response(503, {})
            return mock_httpx_response(200, mock_profile_response)

        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = mock_put
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):  # Skip actual sleep
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="communication_style",
                    value="formal"
                )

            assert result["status"] == "success"
            assert call_count == 3  # Two failures + one success

    @pytest.mark.asyncio
    async def test_retry_exhausted_returns_error(self, mock_httpx_response):
        """AC #7: After max retries, return error."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(503, {}))
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="communication_style",
                    value="formal"
                )

            assert result["status"] == "error"
            assert result["error_code"] == "SERVER_ERROR"
            assert "3 attempts" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_timeout_handling(self):
        """AC #7: Timeout errors trigger retry."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(side_effect=httpx.TimeoutException("Connection timed out"))
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="communication_style",
                    value="formal"
                )

            assert result["status"] == "error"
            assert result["error_code"] == "TIMEOUT_ERROR"
            assert "3 attempts" in result["error_message"].lower()

    @pytest.mark.asyncio
    async def test_timeout_retry_then_success(self, mock_profile_response, mock_httpx_response):
        """AC #7: Timeout then success after retry."""
        call_count = 0

        async def mock_put(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise httpx.TimeoutException("Connection timed out")
            return mock_httpx_response(200, mock_profile_response)

        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = mock_put
            mock_client_class.return_value = mock_client

            with patch('asyncio.sleep', new_callable=AsyncMock):
                result = await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="communication_style",
                    value="formal"
                )

            assert result["status"] == "success"
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_reason_included_in_payload(self, mock_profile_response, mock_httpx_response):
        """Optional reason parameter is included in request."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal",
                reason="User explicitly stated preference in conversation"
            )

            call_args = mock_client.put.call_args
            request_body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert request_body.get("reason") == "User explicitly stated preference in conversation"

    @pytest.mark.asyncio
    async def test_reason_not_included_when_not_provided(self, mock_profile_response, mock_httpx_response):
        """Reason parameter is not included when not provided."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
                # No reason provided
            )

            call_args = mock_client.put.call_args
            request_body = call_args.kwargs.get("json") or call_args[1].get("json")
            assert "reason" not in request_body

    @pytest.mark.asyncio
    async def test_correct_endpoint_url(self, mock_profile_response, mock_httpx_response):
        """Verify correct endpoint URL is called."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            call_args = mock_client.put.call_args
            url = call_args[0][0]
            assert "/v1/profile/preferences/communication_style" in url

    @pytest.mark.asyncio
    async def test_10s_timeout_configured(self, mock_profile_response, mock_httpx_response):
        """Verify 10 second timeout is configured."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            mock_client_class.assert_called_once_with(timeout=10.0)

    @pytest.mark.asyncio
    async def test_uses_config_url(self, mock_profile_response, mock_httpx_response):
        """Test that agentic-memories URL is read from config."""
        with patch('mcp_server.tools.profile.get_config') as mock_get_config:
            mock_get_config.return_value = {
                "AGENTIC_MEMORIES_URL": "http://custom-host:9999"
            }

            with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
                mock_client_class.return_value = mock_client

                await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="communication_style",
                    value="formal"
                )

                call_args = mock_client.put.call_args
                url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
                assert "http://custom-host:9999" in url

    @pytest.mark.asyncio
    async def test_config_failure_uses_default_url(self, mock_profile_response, mock_httpx_response):
        """Test that default URL is used when config fails."""
        with patch('mcp_server.tools.profile.get_config') as mock_get_config:
            mock_get_config.side_effect = Exception("Config error")

            with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
                mock_client = AsyncMock()
                mock_client.__aenter__.return_value = mock_client
                mock_client.__aexit__.return_value = None
                mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
                mock_client_class.return_value = mock_client

                await update_user_profile_tool_handler(
                    user_id="user123",
                    category="preferences",
                    field_name="communication_style",
                    value="formal"
                )

                call_args = mock_client.put.call_args
                url = call_args.args[0] if call_args.args else call_args.kwargs.get("url")
                assert "host.docker.internal:8080" in url

    @pytest.mark.asyncio
    async def test_unexpected_exception_handling(self):
        """Test handling of unexpected exceptions."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(side_effect=Exception("Network error"))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            assert result["status"] == "error"
            assert result["error_code"] == "INTERNAL_ERROR"
            assert "Network error" in result["error_message"]

    @pytest.mark.asyncio
    async def test_other_http_status_codes(self, mock_httpx_response):
        """Test handling of other HTTP status codes (e.g., 403)."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(403, {}))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category="preferences",
                field_name="communication_style",
                value="formal"
            )

            assert result["status"] == "error"
            assert result["error_code"] == 403
            assert "HTTP 403" in result["error_message"]


class TestUpdateUserProfileToolSchema:
    """Test update_user_profile_tool schema definition (AC #1, AC #10)."""

    def test_tool_has_required_fields(self):
        """Test that tool definition has all required fields."""
        assert "name" in update_user_profile_tool
        assert "description" in update_user_profile_tool
        assert "inputSchema" in update_user_profile_tool
        assert "handler" in update_user_profile_tool

    def test_tool_name(self):
        """Test tool name."""
        assert update_user_profile_tool["name"] == "update_user_profile"

    def test_tool_description_includes_guidance(self):
        """Test tool description includes usage guidance for LLM (AC #10)."""
        desc = update_user_profile_tool["description"]
        # Should mention when to use
        assert "explicitly" in desc.lower()
        # Should mention examples
        assert "moved to" in desc.lower() or "seattle" in desc.lower()
        # Should mention what NOT to use for
        assert "do not use" in desc.lower()
        # Should mention temporary states
        assert "temporary" in desc.lower()
        # Should mention categories
        assert "basics" in desc.lower()
        assert "preferences" in desc.lower()

    def test_tool_handler_is_callable(self):
        """Test tool handler is callable."""
        assert callable(update_user_profile_tool["handler"])
        assert update_user_profile_tool["handler"] == update_user_profile_tool_handler

    def test_input_schema_structure(self):
        """Test input schema structure (AC #1)."""
        schema = update_user_profile_tool["inputSchema"]
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema

    def test_input_schema_required_fields(self):
        """Test required fields."""
        schema = update_user_profile_tool["inputSchema"]
        required = schema["required"]
        assert "user_id" in required
        assert "category" in required
        assert "field_name" in required
        assert "value" in required
        # reason should NOT be required
        assert "reason" not in required

    def test_input_schema_user_id_property(self):
        """Test user_id property definition."""
        schema = update_user_profile_tool["inputSchema"]
        user_id_prop = schema["properties"]["user_id"]
        assert user_id_prop["type"] == "string"
        assert "description" in user_id_prop

    def test_input_schema_category_property(self):
        """Test category property definition with enum."""
        schema = update_user_profile_tool["inputSchema"]
        category_prop = schema["properties"]["category"]
        assert category_prop["type"] == "string"
        assert "enum" in category_prop
        assert set(category_prop["enum"]) == ALLOWED_PROFILE_CATEGORIES
        assert "description" in category_prop

    def test_input_schema_field_name_property(self):
        """Test field_name property definition."""
        schema = update_user_profile_tool["inputSchema"]
        field_prop = schema["properties"]["field_name"]
        assert field_prop["type"] == "string"
        assert "description" in field_prop

    def test_input_schema_value_property(self):
        """Test value property definition (string type for Gemini compatibility)."""
        schema = update_user_profile_tool["inputSchema"]
        value_prop = schema["properties"]["value"]
        # Should have description and type
        assert "description" in value_prop
        # Type is string for Gemini compatibility; handler parses JSON for arrays/objects
        assert value_prop["type"] == "string"
        # Description should explain JSON format for complex values
        assert "JSON" in value_prop["description"] or "json" in value_prop["description"].lower()

    def test_input_schema_reason_property(self):
        """Test reason property definition."""
        schema = update_user_profile_tool["inputSchema"]
        reason_prop = schema["properties"]["reason"]
        assert reason_prop["type"] == "string"
        assert "description" in reason_prop
        # Should mention audit
        assert "audit" in reason_prop["description"].lower()


class TestAllowedProfileCategories:
    """Test ALLOWED_PROFILE_CATEGORIES constant."""

    def test_has_expected_categories(self):
        """Test that all expected categories are present (8 total, matching agentic-memories)."""
        expected = {
            "basics", "preferences", "goals", "interests", "background",
            "health", "personality", "values"
        }
        assert ALLOWED_PROFILE_CATEGORIES == expected

    def test_is_set_type(self):
        """Test that it's a set for fast lookup."""
        assert isinstance(ALLOWED_PROFILE_CATEGORIES, set)


class TestCanonicalFieldsValidation:
    """Test CANONICAL_FIELDS validation and FIELD_NAME_ALIASES normalization."""

    def test_all_categories_have_canonical_fields(self):
        """Every allowed category has canonical field definitions."""
        for category in ALLOWED_PROFILE_CATEGORIES:
            assert category in CANONICAL_FIELDS
            assert len(CANONICAL_FIELDS[category]) > 0

    def test_canonical_fields_are_sets(self):
        """Canonical fields are sets for fast lookup."""
        for category, fields in CANONICAL_FIELDS.items():
            assert isinstance(fields, set)

    @pytest.mark.asyncio
    async def test_non_canonical_field_rejected(self):
        """Non-canonical field names are rejected with helpful error."""
        result = await update_user_profile_tool_handler(
            user_id="user123",
            category="basics",
            field_name="invalid_field_xyz",
            value="test"
        )

        assert result["status"] == "error"
        assert result["error_code"] == "VALIDATION_ERROR"
        assert "Invalid field" in result["error_message"]
        # Should list valid fields
        assert "name" in result["error_message"]

    @pytest.mark.asyncio
    async def test_alias_normalized_to_canonical(self, mock_profile_response, mock_httpx_response):
        """Field name aliases are normalized to canonical names."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            # Use 'birthdate' which should be normalized to 'birthday'
            await update_user_profile_tool_handler(
                user_id="user123",
                category="basics",
                field_name="birthdate",  # alias
                value="1990-01-15"
            )

            # Verify the canonical name was used in the URL
            call_args = mock_client.put.call_args
            url = call_args[0][0]
            assert "/birthday" in url  # normalized
            assert "/birthdate" not in url

    @pytest.mark.asyncio
    async def test_singular_to_plural_alias(self, mock_profile_response, mock_httpx_response):
        """Singular field names normalized to plural."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            await update_user_profile_tool_handler(
                user_id="user123",
                category="interests",
                field_name="hobby",  # singular alias
                value=["hiking", "reading"]
            )

            call_args = mock_client.put.call_args
            url = call_args[0][0]
            assert "/hobbies" in url  # normalized to plural

    def test_field_name_aliases_map_to_canonical_fields(self):
        """All aliases map to fields that exist in CANONICAL_FIELDS."""
        for alias, canonical in FIELD_NAME_ALIASES.items():
            # Find the category containing the canonical field
            found = False
            for category, fields in CANONICAL_FIELDS.items():
                if canonical in fields:
                    found = True
                    break
            assert found, f"Alias '{alias}' maps to '{canonical}' which is not in any category"

    @pytest.mark.asyncio
    @pytest.mark.parametrize("category,field_name", [
        ("basics", "name"),
        ("basics", "location"),
        ("basics", "occupation"),
        ("preferences", "communication_style"),
        ("preferences", "risk_tolerance"),
        ("goals", "short_term"),
        ("goals", "long_term"),
        ("interests", "hobbies"),
        ("background", "skills"),
        ("health", "allergies"),
        ("personality", "personality_type"),
        ("values", "life_values"),
    ])
    async def test_canonical_fields_accepted(self, category, field_name, mock_profile_response, mock_httpx_response):
        """Various canonical field names are accepted."""
        with patch('mcp_server.tools.profile.httpx.AsyncClient') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.__aenter__.return_value = mock_client
            mock_client.__aexit__.return_value = None
            mock_client.put = AsyncMock(return_value=mock_httpx_response(200, mock_profile_response))
            mock_client_class.return_value = mock_client

            result = await update_user_profile_tool_handler(
                user_id="user123",
                category=category,
                field_name=field_name,
                value="test_value"
            )

            assert result["status"] == "success", f"{category}/{field_name} should be valid"
