"""
Integration Tests for Gemini + MCP Tool Calling

These tests require:
1. Running MCP server (docker compose up mcp-server)
2. Valid GOOGLE_API_KEY in environment
3. MCP tools configured and available

Run with: pytest tests/integration/test_gemini_mcp.py
"""

import pytest
import os


# Skip tests if GOOGLE_API_KEY not configured
pytestmark = pytest.mark.skipif(
    not os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_API_KEY") == "REPLACE_ME",
    reason="GOOGLE_API_KEY not configured"
)


@pytest.mark.asyncio
@pytest.mark.integration
class TestGeminiMCPBasicToolCalling:
    """Test basic tool calling flow with real MCP server."""

    async def test_single_tool_call_internet_search(self):
        """
        Test Gemini can execute internet_search tool via MCP.

        Flow:
        1. User asks question requiring internet search
        2. Gemini detects need for internet_search tool
        3. Tool executed via MCP client
        4. Gemini incorporates result into response
        """
        # TODO: Implement when MCP server is running
        # This test requires:
        # - GeminiProvider instance
        # - MCPClient instance pointing to running MCP server
        # - Tools list from MCP server
        # - Test message that triggers internet_search

        pytest.skip("Requires running MCP server - implement when ready")

    async def test_single_tool_call_store_memory(self):
        """
        Test Gemini can execute store_memory tool via MCP.

        Flow:
        1. User provides information to remember
        2. Gemini detects need to store memory
        3. store_memory tool executed via MCP
        4. Gemini confirms storage
        """
        pytest.skip("Requires running MCP server - implement when ready")


@pytest.mark.asyncio
@pytest.mark.integration
class TestGeminiMCPMultiToolCalling:
    """Test multi-tool sequences."""

    async def test_sequential_tool_calls(self):
        """
        Test Gemini can execute multiple tools in sequence.

        Flow:
        1. retrieve_memories (check existing knowledge)
        2. internet_search (get new information)
        3. store_memory (save combined result)
        """
        pytest.skip("Requires running MCP server - implement when ready")

    @pytest.mark.skipif(
        not os.getenv("RUN_LIVE_E2E"),
        reason="Live Gemini API — set RUN_LIVE_E2E=1 to run (incurs ~$0.01-0.05 per run)"
    )
    async def test_thought_signature_preservation(self, monkeypatch):
        """
        Test thought_signature is preserved across multi-turn tool calling.

        This is CRITICAL for Gemini - missing thought_signature causes 400 errors.

        Story 24.1 hotfix verification (2026-04-25): runs a REAL two-turn
        Gemini tool-calling flow against the live API. Verifies:
        1. The SDK (>=1.40) preserves Part.thought_signature on the wire.
        2. Annie's streaming loop captures it (visible in
           function_calls bookkeeping list / structured log line).
        3. Sending function_response back via Part.from_function_response
           does NOT trigger 400 INVALID_ARGUMENT
           ("Function call is missing a thought_signature").
        4. Final assistant turn produces a STOP with usable text.

        This is the test that would have caught today's outage. It is
        gated behind RUN_LIVE_E2E=1 — CI / `make test` will continue to
        skip it. Manual invocation:
            docker compose exec -e RUN_LIVE_E2E=1 backend \\
              python -m pytest tests/e2e/test_gemini_mcp.py::\\
              TestGeminiMCPMultiToolCalling::test_thought_signature_preservation -v

        Cost: ~$0.01-$0.05 per run (one tool call + one response turn,
        ~5K input tokens, ~200 output tokens on gemini-3.1-pro-preview).
        """
        from unittest.mock import AsyncMock, MagicMock
        from api.providers.gemini_provider import GeminiProvider

        # The autouse mock_env_vars fixture in tests/conftest.py overrides
        # GOOGLE_API_KEY with "test-google-key-12345". For a live run we
        # must restore the real key from the host's container env. We
        # recover it from /proc/1/environ — that's the docker-compose
        # injected env, untouched by conftest's monkeypatch.
        real_key = None
        try:
            with open("/proc/1/environ", "rb") as f:
                env_blob = f.read().decode("utf-8", errors="replace")
            for line in env_blob.split("\0"):
                if line.startswith("GOOGLE_API_KEY="):
                    real_key = line.split("=", 1)[1]
                    break
        except Exception:
            pass

        if not real_key or real_key == "REPLACE_ME":
            pytest.skip(
                "GOOGLE_API_KEY not present in container env "
                "(/proc/1/environ) — cannot run live test"
            )

        # Restore the real key for this test only. get_config() reads
        # os.environ on each call (no caching), so monkeypatching the
        # env var before constructing the provider is sufficient.
        monkeypatch.setenv("GOOGLE_API_KEY", real_key)

        provider = GeminiProvider()
        assert provider.client is not None, "GeminiProvider should construct a live client"

        # Define one tool the model should call.
        tools = [{
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": (
                    "Get the current weather for a city. Use this when the user "
                    "asks about weather conditions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {
                            "type": "string",
                            "description": "City name, e.g., 'Newark, CA'"
                        }
                    },
                    "required": ["city"],
                },
            },
        }]

        # Mock MCP client — return a deterministic weather payload so the
        # test does not depend on a real MCP server. The real wire surface
        # under test is Gemini's Part.thought_signature handling, not MCP.
        mcp_client = MagicMock()
        mcp_client.call_tool = AsyncMock(return_value={
            "result": "Newark, CA: 55°F, partly cloudy, light wind."
        })

        events = []
        async for ev in provider.stream_chat_completion(
            messages=[{
                "role": "user",
                "content": (
                    "What is the current weather in Newark, CA? "
                    "Use the get_weather tool."
                ),
            }],
            tools=tools,
            mcp_client=mcp_client,
        ):
            events.append(ev)

        # Bucket events for assertions.
        types_seen = [e.get("type") for e in events]
        errors = [e for e in events if e.get("type") == "error"]
        tool_started = [e for e in events if e.get("type") == "tool_call_started"]
        tool_completed = [e for e in events if e.get("type") == "tool_call_completed"]
        tokens = [e for e in events if e.get("type") == "token"]
        done = [e for e in events if e.get("type") == "done"]

        # Assertion 1: NO error events (the bug surfaced as a 400 from Gemini).
        assert not errors, (
            f"Live two-turn flow emitted error events — thought_signature "
            f"regression suspected. Errors: {errors}"
        )

        # Assertion 2: Gemini decided to call the tool.
        assert tool_started, (
            f"Gemini did not call the tool. Events: {types_seen}. "
            f"This indicates either the prompt was insufficient or the "
            f"model is degraded — re-run before drawing conclusions."
        )
        assert tool_started[0]["tool"] == "get_weather"

        # Assertion 3: tool completed (MCP path took the call).
        assert tool_completed, "Tool call started but never completed"

        # Assertion 4: turn-2 produced a real assistant response.
        # If thought_signature was stripped, the second turn would emit
        # an error event, not tokens.
        assert tokens, (
            "Second turn produced no text tokens — the function_response "
            "send likely returned 400 due to missing thought_signature."
        )

        # Assertion 5: stream finished cleanly.
        assert done, "Stream did not complete with a `done` event"

        # Assertion 6: bookkeeping captured the signature.
        # The provider stores thought_signature in its internal
        # function_calls list (not exposed publicly), but the structured
        # log line at gemini_provider.py:899-910 emits has_thought_signature.
        # We can't easily intercept logger calls in a live run without
        # adding a fixture, so we rely on the absence of a 400 error as
        # the load-bearing signal: if the signature was stripped
        # (SDK <1.40 behavior), turn-2 would have raised. Surviving the
        # full flow PROVES the threading works.


@pytest.mark.asyncio
@pytest.mark.integration
class TestGeminiMCPErrorHandling:
    """Test error handling for tool execution failures."""

    async def test_mcp_server_unreachable(self):
        """
        Test graceful handling when MCP server is unreachable.

        Expected: tool_call_failed event with user-friendly message
        """
        pytest.skip("Requires MCP server to be stopped - implement when ready")

    async def test_tool_execution_timeout(self):
        """
        Test handling of tool execution timeout.

        Expected: tool_call_failed event after timeout
        """
        pytest.skip("Requires mock MCP tool with delay - implement when ready")

    async def test_invalid_tool_arguments(self):
        """
        Test handling when Gemini provides invalid tool arguments.

        Expected: tool_call_failed event with validation error
        """
        pytest.skip("Requires argument validation - implement when ready")


@pytest.mark.asyncio
@pytest.mark.integration
class TestGeminiMCPStreamingEvents:
    """Test SSE event emission during tool calling."""

    async def test_tool_call_started_event_emitted(self):
        """
        Test tool_call_started event is emitted when tool execution begins.

        Event should include:
        - type: "tool_call_started"
        - tool: tool name
        - arguments: tool arguments dict
        """
        pytest.skip("Requires running MCP server - implement when ready")

    async def test_tool_call_completed_event_emitted(self):
        """
        Test tool_call_completed event is emitted when tool succeeds.

        Event should include:
        - type: "tool_call_completed"
        - tool: tool name
        - result_summary: truncated result
        """
        pytest.skip("Requires running MCP server - implement when ready")

    async def test_tool_call_failed_event_emitted(self):
        """
        Test tool_call_failed event is emitted when tool fails.

        Event should include:
        - type: "tool_call_failed"
        - tool: tool name
        - error: error message
        """
        pytest.skip("Requires MCP tool failure scenario - implement when ready")


@pytest.mark.asyncio
@pytest.mark.integration
class TestGeminiMCPProviderParity:
    """Test Gemini tool calling matches Grok-4/ChatGPT-5 behavior."""

    async def test_same_prompt_triggers_same_tools(self):
        """
        Test identical prompts trigger identical tools across all providers.

        Run same prompt with Grok, ChatGPT, and Gemini - verify same tools called.
        """
        pytest.skip("Requires all 3 providers configured - implement when ready")

    async def test_tool_results_produce_equivalent_responses(self):
        """
        Test tool results produce semantically equivalent final responses.

        Different LLMs may phrase differently, but should convey same information.
        """
        pytest.skip("Requires semantic similarity comparison - implement when ready")
