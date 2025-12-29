"""
Unit tests for prompts.py (Story 14.5).

Tests the memory management section, updated tool usage instructions,
and build_system_prompt() integration.

Coverage:
- MEMORY_MANAGEMENT_SECTION content verification
- TOOL_USAGE_INSTRUCTIONS content verification (with delete_memory)
- build_system_prompt() integration of memory management section
- User ID placeholder formatting
"""
import pytest


class TestMemoryManagementSection:
    """Test MEMORY_MANAGEMENT_SECTION constant content."""

    def test_memory_management_section_exists(self):
        """Test that MEMORY_MANAGEMENT_SECTION constant is defined."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        assert MEMORY_MANAGEMENT_SECTION is not None
        assert len(MEMORY_MANAGEMENT_SECTION) > 0

    def test_memory_management_section_contains_store_memory_guidance(self):
        """Test that section explains when to use store_memory."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        assert "store_memory" in MEMORY_MANAGEMENT_SECTION
        assert "CRITICAL" in MEMORY_MANAGEMENT_SECTION
        assert "explicit" in MEMORY_MANAGEMENT_SECTION.lower()

    def test_memory_management_section_contains_delete_memory_guidance(self):
        """Test that section explains when to use delete_memory."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        assert "delete_memory" in MEMORY_MANAGEMENT_SECTION
        assert "Deletion Workflow" in MEMORY_MANAGEMENT_SECTION
        assert "confirm" in MEMORY_MANAGEMENT_SECTION.lower()

    def test_memory_management_section_contains_retrieve_memories_guidance(self):
        """Test that section explains when to use retrieve_memories."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        assert "retrieve_memories" in MEMORY_MANAGEMENT_SECTION
        assert "LIBERALLY" in MEMORY_MANAGEMENT_SECTION

    def test_memory_management_section_contains_examples(self):
        """Test that section contains good and bad usage examples."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        assert "Good Examples" in MEMORY_MANAGEMENT_SECTION
        assert "Bad Examples" in MEMORY_MANAGEMENT_SECTION

    def test_memory_management_section_explains_background_extraction(self):
        """Test that section explains background extraction."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        assert "automatically" in MEMORY_MANAGEMENT_SECTION.lower()
        assert "background" in MEMORY_MANAGEMENT_SECTION.lower()


class TestToolUsageInstructions:
    """Test TOOL_USAGE_INSTRUCTIONS constant content."""

    def test_tool_usage_instructions_exists(self):
        """Test that TOOL_USAGE_INSTRUCTIONS constant is defined."""
        from api.prompts import TOOL_USAGE_INSTRUCTIONS

        assert TOOL_USAGE_INSTRUCTIONS is not None
        assert len(TOOL_USAGE_INSTRUCTIONS) > 0

    def test_tool_usage_instructions_includes_delete_memory(self):
        """Test that delete_memory is included in memory tools list."""
        from api.prompts import TOOL_USAGE_INSTRUCTIONS

        assert "delete_memory" in TOOL_USAGE_INSTRUCTIONS

    def test_tool_usage_instructions_includes_all_memory_tools(self):
        """Test that all memory tools are listed."""
        from api.prompts import TOOL_USAGE_INSTRUCTIONS

        assert "store_memory" in TOOL_USAGE_INSTRUCTIONS
        assert "retrieve_memories" in TOOL_USAGE_INSTRUCTIONS
        assert "delete_memory" in TOOL_USAGE_INSTRUCTIONS

    def test_tool_usage_instructions_has_user_id_placeholder(self):
        """Test that user_id placeholder exists for formatting."""
        from api.prompts import TOOL_USAGE_INSTRUCTIONS

        assert "{user_id}" in TOOL_USAGE_INSTRUCTIONS

    def test_tool_usage_instructions_explains_delete_workflow(self):
        """Test that delete workflow is explained."""
        from api.prompts import TOOL_USAGE_INSTRUCTIONS

        # Should mention the retrieve -> confirm -> delete workflow
        assert "retrieve" in TOOL_USAGE_INSTRUCTIONS.lower()
        assert "confirm" in TOOL_USAGE_INSTRUCTIONS.lower()

    def test_tool_usage_instructions_can_be_formatted(self):
        """Test that TOOL_USAGE_INSTRUCTIONS can be formatted with user_id."""
        from api.prompts import TOOL_USAGE_INSTRUCTIONS

        formatted = TOOL_USAGE_INSTRUCTIONS.format(user_id="test_user_123")
        assert "test_user_123" in formatted
        assert "{user_id}" not in formatted


class TestBuildSystemPromptMemorySection:
    """Test build_system_prompt() includes memory management section."""

    def test_build_system_prompt_includes_memory_section(self):
        """Test that build_system_prompt includes MEMORY_MANAGEMENT_SECTION."""
        from api.prompts import build_system_prompt, MEMORY_MANAGEMENT_SECTION

        prompt = build_system_prompt(user_id="test_user")

        # Check that memory management content is present
        assert "MEMORY MANAGEMENT" in prompt
        assert "store_memory" in prompt
        assert "delete_memory" in prompt
        assert "retrieve_memories" in prompt

    def test_memory_section_after_proactive_section(self):
        """Test that memory section appears after proactive capabilities."""
        from api.prompts import build_system_prompt

        prompt = build_system_prompt(user_id="test_user")

        # Find positions
        proactive_pos = prompt.find("PROACTIVE CAPABILITIES")
        memory_pos = prompt.find("MEMORY MANAGEMENT")

        assert proactive_pos > 0, "PROACTIVE CAPABILITIES not found in prompt"
        assert memory_pos > 0, "MEMORY MANAGEMENT not found in prompt"
        assert memory_pos > proactive_pos, "MEMORY MANAGEMENT should appear after PROACTIVE CAPABILITIES"

    def test_tool_usage_instructions_formatted_with_user_id(self):
        """Test that TOOL_USAGE_INSTRUCTIONS has user_id formatted."""
        from api.prompts import build_system_prompt

        user_id = "test_user_456"
        prompt = build_system_prompt(user_id=user_id)

        # Check that user_id is in the tool usage section
        assert f"Current user ID for all tool calls: {user_id}" in prompt

    def test_build_system_prompt_without_user_id(self):
        """Test that prompt still builds without user_id (no tool instructions)."""
        from api.prompts import build_system_prompt

        prompt = build_system_prompt()

        # Memory management section should still be present
        assert "MEMORY MANAGEMENT" in prompt

        # But tool usage instructions with user_id should not be present
        assert "Current user ID for all tool calls:" not in prompt

    def test_prompt_order_correctness(self):
        """Test the order of sections in the prompt."""
        from api.prompts import build_system_prompt

        prompt = build_system_prompt(
            user_id="test_user",
            platform="telegram"
        )

        # Find positions of key sections
        base_pos = prompt.find("Annie")
        proactive_pos = prompt.find("PROACTIVE CAPABILITIES")
        memory_mgmt_pos = prompt.find("MEMORY MANAGEMENT")
        user_id_pos = prompt.find("Current user ID: test_user")
        format_pos = prompt.find("Telegram MarkdownV2")
        tool_usage_pos = prompt.find("TOOL USAGE REQUIREMENTS")

        # Verify order
        assert base_pos >= 0
        assert proactive_pos > base_pos
        assert memory_mgmt_pos > proactive_pos
        assert user_id_pos > memory_mgmt_pos
        assert format_pos > user_id_pos
        assert tool_usage_pos > format_pos


class TestPromptTokenImpact:
    """Test that prompt changes don't drastically increase token count."""

    def test_memory_section_reasonable_length(self):
        """Test that MEMORY_MANAGEMENT_SECTION is reasonably sized (~300 tokens)."""
        from api.prompts import MEMORY_MANAGEMENT_SECTION

        # Rough estimate: ~4 chars per token
        estimated_tokens = len(MEMORY_MANAGEMENT_SECTION) / 4

        # Should be around 300 tokens as noted in story
        assert estimated_tokens < 500, "Memory management section is too long"
        assert estimated_tokens > 100, "Memory management section seems too short"
