"""
Tests for Wake-Up Agent - LLM agent that executes proactive triggers.

Tests:
- Dynamic state gathering
- Agent prompt building
- Response parsing
- Agent execution
- Skip decision logic
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

from api.proactive.agent import (
    DynamicState,
    WakeUpResult,
    RESTRICTED_TOOLS,
    build_agent_prompt,
    parse_agent_response,
    execute_wake_up_agent,
)


# ============================================================================
# Data Model Tests
# ============================================================================

def test_dynamic_state_creation():
    """Test DynamicState dataclass creation."""
    state = DynamicState(
        current_datetime=datetime.now(timezone.utc),
        day_of_week="Monday",
        market_status="open",
        hours_since_last_message=2.5,
        recent_context="User asked about stocks",
        profile={"name": "Test User"},
        conversation_history=[{"role": "user", "content": "Hello"}]
    )

    assert state.day_of_week == "Monday"
    assert state.market_status == "open"
    assert state.conversation_history is not None
    assert state.hours_since_last_message == 2.5


def test_wake_up_result_creation():
    """Test WakeUpResult dataclass creation."""
    result = WakeUpResult(
        skip=False,
        skip_reason=None,
        message="Hello! Your stocks are up.",
        tools_called=["get_portfolio"],
        reasoning="User requested daily update"
    )

    assert result.skip is False
    assert result.message == "Hello! Your stocks are up."
    assert "get_portfolio" in result.tools_called


def test_wake_up_result_skip():
    """Test WakeUpResult for skip case."""
    result = WakeUpResult(
        skip=True,
        skip_reason="Market is closed",
        message=None,
        tools_called=[],
        reasoning="No point sending market update when market closed"
    )

    assert result.skip is True
    assert result.skip_reason == "Market is closed"
    assert result.message is None


def test_restricted_tools_list():
    """Test RESTRICTED_TOOLS contains expected tools."""
    assert "add_holding" in RESTRICTED_TOOLS
    assert "update_holding" in RESTRICTED_TOOLS
    assert "remove_holding" in RESTRICTED_TOOLS
    assert "create_trigger" in RESTRICTED_TOOLS
    assert "update_trigger" in RESTRICTED_TOOLS
    assert "delete_trigger" in RESTRICTED_TOOLS
    assert len(RESTRICTED_TOOLS) == 6


# ============================================================================
# Response Parsing Tests
# ============================================================================

def test_parse_agent_response_valid_json():
    """Test parsing valid JSON response."""
    response = '{"skip": false, "message": "Hello!", "reasoning": "User wanted update"}'
    result = parse_agent_response(response, ["get_portfolio"])

    assert result.skip is False
    assert result.message == "Hello!"
    assert "get_portfolio" in result.tools_called


def test_parse_agent_response_skip_true():
    """Test parsing skip response."""
    response = '{"skip": true, "skip_reason": "Market closed", "reasoning": "No update needed"}'
    result = parse_agent_response(response, [])

    assert result.skip is True
    assert result.skip_reason == "Market closed"
    assert result.message == ""  # Empty string when no message in JSON


def test_parse_agent_response_plain_text():
    """Test parsing plain text as message (fallback)."""
    response = "Hello! Your stocks are doing great today!"
    result = parse_agent_response(response, [])

    # Plain text should be treated as message
    assert result.skip is False
    assert result.message == response


def test_parse_agent_response_invalid_json():
    """Test parsing invalid JSON falls back to plain text."""
    response = "This is not valid JSON { broken"
    result = parse_agent_response(response, ["some_tool"])

    assert result.skip is False
    assert result.message == response


def test_parse_agent_response_with_preamble_text():
    """Test parsing JSON with preamble text before it."""
    response = '''Based on the trigger and your preferences, I've analyzed the data.

{
    "skip": false,
    "message": "📉 Market update: NVDA down 5%",
    "tools_called": ["get_portfolio", "get_stock_data"],
    "reasoning": "Found significant price movement"
}'''
    result = parse_agent_response(response, [])

    assert result.skip is False
    assert result.message == "📉 Market update: NVDA down 5%"
    assert "get_portfolio" in result.tools_called
    assert "get_stock_data" in result.tools_called
    assert result.reasoning == "Found significant price movement"


def test_parse_agent_response_research_protocol_format():
    """Research protocol: JSON metadata + ---REPORT--- + markdown body."""
    response = '''{
    "skip": false,
    "skip_reason": null,
    "tools_called": ["web_search", "web_crawl", "reddit_search"],
    "reasoning": "Ran 6 searches across vendor docs and Reddit"
}
---REPORT---
# Lightguns for OLED TVs

## Top picks
- Gun4IR
- Sinden
- Retro Shooter

## Caveats
None are truly "open box, done in 90 seconds".
'''
    result = parse_agent_response(response, [])

    assert result.skip is False
    assert result.message.startswith("# Lightguns for OLED TVs")
    # Body must contain REAL newlines, not literal backslash-n.
    assert "\n## Top picks\n" in result.message
    assert "\\n" not in result.message
    assert "web_search" in result.tools_called
    assert result.reasoning.startswith("Ran 6 searches")


def test_parse_agent_response_unescapes_double_escaped_newlines():
    """Legacy path: literal `\\n` sequences in the message are un-escaped."""
    # Simulates an LLM that double-escaped inside the JSON message field.
    response = (
        '{"skip": false, '
        '"message": "Intro paragraph\\\\n\\\\n## Header\\\\n- bullet", '
        '"reasoning": "test"}'
    )
    result = parse_agent_response(response, [])

    assert result.skip is False
    assert "\\n" not in result.message
    assert result.message == "Intro paragraph\n\n## Header\n- bullet"


def test_parse_agent_response_research_protocol_missing_json_header():
    """Body after ---REPORT--- still becomes message if JSON header is malformed."""
    response = "garbage header no braces\n---REPORT---\n# Report Title\n\nBody text."
    result = parse_agent_response(response, ["web_search"])

    assert result.skip is False
    assert result.message.startswith("# Report Title")
    # Falls back to the caller-supplied tools_called list.
    assert result.tools_called == ["web_search"]


def test_parse_agent_response_research_protocol_wrapped_in_code_fence():
    """Outer ```json fences should be stripped before looking for marker."""
    response = (
        "```json\n"
        '{"skip": false, "tools_called": ["web_search"], "reasoning": "ok"}\n'
        "---REPORT---\n"
        "# Title\n\nBody.\n"
        "```"
    )
    result = parse_agent_response(response, [])

    assert result.skip is False
    assert result.message.startswith("# Title")
    assert "web_search" in result.tools_called


# ============================================================================
# Prompt Building Tests
# ============================================================================

def test_build_agent_prompt_includes_trigger_info():
    """Test prompt includes trigger information."""
    trigger = {
        "id": "trigger_123",
        "intent_name": "Daily Briefing",
        "trigger_type": "cron",
        "fire_count": 5,
        "last_fired_at": "2025-12-24T08:00:00Z",
        "action_context": "Send a daily market briefing"
    }
    state = DynamicState(
        current_datetime=datetime.now(timezone.utc),
        day_of_week="Wednesday",
        market_status="open",
        hours_since_last_message=12.0,
        recent_context=None,
        profile=None,
        conversation_history=None
    )

    prompt = build_agent_prompt(trigger, state, [])

    assert "Daily Briefing" in prompt
    assert "cron" in prompt


def test_build_agent_prompt_includes_dynamic_state():
    """Test prompt includes dynamic state."""
    trigger = {
        "id": "t1",
        "intent_name": "Test",
        "trigger_type": "once",
        "action_context": "Check in with user"
    }
    state = DynamicState(
        current_datetime=datetime(2025, 12, 25, 10, 30, tzinfo=timezone.utc),
        day_of_week="Thursday",
        market_status="closed",
        hours_since_last_message=24.0,
        recent_context="User discussed portfolio yesterday",
        profile={"name": "Ankit"},
        conversation_history=[{"role": "user", "content": "Check my portfolio"}]
    )

    prompt = build_agent_prompt(trigger, state, [])

    assert "Thursday" in prompt
    assert "closed" in prompt or "market" in prompt.lower()


def test_build_agent_prompt_includes_tools():
    """Test prompt includes available tools."""
    trigger = {
        "id": "t1",
        "intent_name": "Test",
        "trigger_type": "once",
        "action_context": "Daily briefing"
    }
    state = DynamicState(
        current_datetime=datetime.now(timezone.utc),
        day_of_week="Monday",
        market_status="open",
        hours_since_last_message=2.0,
        recent_context=None,
        profile=None,
        conversation_history=None
    )
    tools = ["get_portfolio", "get_stock_price"]

    prompt = build_agent_prompt(trigger, state, tools)

    assert "get_portfolio" in prompt or "portfolio" in prompt.lower()


# ============================================================================
# Agent Execution Tests
# ============================================================================

@pytest.mark.asyncio
async def test_execute_wake_up_agent_returns_result():
    """Test execute_wake_up_agent returns WakeUpResult."""
    trigger = {
        "id": "trigger_123",
        "user_id": "user_456",
        "name": "Test Trigger",
        "trigger_type": "once",
        "action_context": "Say hello to the user"
    }
    user_id = "user_456"

    with patch('api.proactive.agent.gather_dynamic_state') as mock_gather:
        with patch('api.proactive.agent.LLMClient') as mock_llm:
            with patch('api.proactive.agent.MCPClient') as mock_mcp:
                # Setup mocks
                mock_gather.return_value = DynamicState(
                    current_datetime=datetime.now(timezone.utc),
                    day_of_week="Monday",
                    market_status="open",
                    hours_since_last_message=5.0,
                    recent_context=None,
                    profile=None,
                    conversation_history=None
                )

                # Mock MCP client
                mock_mcp_instance = AsyncMock()
                mock_mcp_instance.__aenter__ = AsyncMock(return_value=mock_mcp_instance)
                mock_mcp_instance.__aexit__ = AsyncMock(return_value=None)
                mock_mcp_instance.list_tools = AsyncMock(return_value=[])
                mock_mcp.return_value = mock_mcp_instance

                # Mock LLM client streaming response
                mock_llm_instance = AsyncMock()
                mock_llm_instance.stream_chat_with_tools = AsyncMock()

                async def mock_stream(*args, **kwargs):
                    yield {"type": "content", "content": '{"skip": false, "message": "Hello!", "reasoning": "Greeting"}'}

                mock_llm_instance.stream_chat_with_tools.return_value = mock_stream()
                mock_llm.return_value = mock_llm_instance

                result = await execute_wake_up_agent(trigger, user_id)

                assert isinstance(result, WakeUpResult)


@pytest.mark.asyncio
async def test_execute_wake_up_agent_error_returns_skip():
    """Test execute_wake_up_agent returns skip on error."""
    trigger = {
        "id": "trigger_123",
        "user_id": "user_456",
        "name": "Test Trigger",
        "trigger_type": "once",
        "action_context": "Do something"
    }
    user_id = "user_456"

    with patch('api.proactive.agent.gather_dynamic_state') as mock_gather:
        mock_gather.side_effect = Exception("Network error")

        result = await execute_wake_up_agent(trigger, user_id)

        assert isinstance(result, WakeUpResult)
        assert result.skip is True
        assert "error" in result.skip_reason.lower() or "error" in result.reasoning.lower()
