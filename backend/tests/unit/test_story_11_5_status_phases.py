"""
Unit tests for Story 11.5: Instrument Memory, Profile, and LLM Phases.

Tests status emissions for:
- AC #1: Memory retrieval operations
- AC #2: Profile loading operations
- AC #3: LLM composition phase
- AC #4: Grok Live Search (if applicable)
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch


class TestMemoryStatusEmissions:
    """Test AC #1: Memory operations status emissions."""

    @pytest.mark.asyncio
    async def test_memory_retrieval_status_in_stream(self):
        """Test that retrieve_memories tool emits start and completion status in stream context."""
        from api.routes.stream import stream_generator

        # Mock dependencies
        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        messages = [
            {"role": "user", "content": "What stocks did I invest in before?"}
        ]

        # Track status emissions
        status_messages = []
        def capture_status(msg):
            status_messages.append(msg)

        # Mock LLM client that calls retrieve_memories tool
        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            # Setup MCP client to return memory retrieval tool call
            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[
                {
                    "name": "retrieve_memories",
                    "description": "Retrieve memories",
                    "inputSchema": {"type": "object", "properties": {}}
                }
            ])

            # First call: LLM wants to call retrieve_memories
            mock_mcp.call_tool = AsyncMock(return_value={
                "memory_count": 3,
                "memories": [{"content": "mem1"}, {"content": "mem2"}, {"content": "mem3"}]
            })

            # Setup LLM client to trigger tool call, then stream response
            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[{"name": "retrieve_memories"}])

            # First non-streaming call: LLM wants to call tool
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "tool_calls": [{
                            "id": "call-123",
                            "function": {
                                "name": "retrieve_memories",
                                "arguments": '{"user_id": "user-1", "query": "stocks", "limit": 5}'
                            }
                        }]
                    }
                }]
            })

            # Second non-streaming call: No more tool calls, ready to stream
            async def chat_completion_side_effect(*args, **kwargs):
                # First call returns tool call, second call returns content
                if mock_llm.chat_completion.call_count == 1:
                    return {
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "tool_calls": [{
                                    "id": "call-123",
                                    "function": {
                                        "name": "retrieve_memories",
                                        "arguments": '{"user_id": "user-1", "query": "stocks", "limit": 5}'
                                    }
                                }]
                            }
                        }]
                    }
                else:
                    return {
                        "choices": [{
                            "message": {
                                "role": "assistant",
                                "content": "Based on your past investments..."
                            }
                        }]
                    }

            mock_llm.chat_completion.side_effect = chat_completion_side_effect

            # Stream final response
            async def mock_stream():
                yield {"type": "token", "content": "Based on "}
                yield {"type": "token", "content": "your past "}
                yield {"type": "token", "content": "investments..."}
                yield {"type": "done", "tokens_used": {"prompt": 100, "completion": 50}}

            mock_llm.stream_chat_completion = mock_stream

            # Collect events from generator
            events = []
            async for event in stream_generator("conv-123", messages, mock_request):
                events.append(event)
                # Check for status frames
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify status emissions for memory retrieval
            assert any("Retrieving your memories" in msg for msg in status_messages), \
                f"Expected memory retrieval start status, got: {status_messages}"
            assert any("Found 3 relevant memories" in msg for msg in status_messages), \
                f"Expected memory retrieval completion status, got: {status_messages}"

    @pytest.mark.asyncio
    async def test_memory_retrieval_no_memories_found(self):
        """Test status when no memories are found."""
        from api.routes.stream import stream_generator

        # Mock dependencies similar to above but with empty result
        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)

        messages = [{"role": "user", "content": "Test"}]
        status_messages = []

        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[{"name": "retrieve_memories"}])
            mock_mcp.call_tool = AsyncMock(return_value={
                "memory_count": 0,
                "memories": []
            })

            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[{"name": "retrieve_memories"}])
            mock_llm.chat_completion = AsyncMock(side_effect=[
                {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "call-1",
                                "function": {"name": "retrieve_memories", "arguments": "{}"}
                            }]
                        }
                    }]
                },
                {"choices": [{"message": {"content": "No memories found"}}]}
            ])

            async def mock_stream():
                yield {"type": "token", "content": "No memories"}
                yield {"type": "done", "tokens_used": {}}

            mock_llm.stream_chat_completion = mock_stream

            async for event in stream_generator("conv-123", messages, mock_request):
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify "No relevant memories found" status
            assert any("No relevant memories found" in msg for msg in status_messages), \
                f"Expected 'no memories' status, got: {status_messages}"


class TestProfileStatusEmissions:
    """Test AC #2: Profile operations status emissions."""

    @pytest.mark.asyncio
    async def test_profile_loading_status_in_stream(self):
        """Test that get_user_profile tool emits start and completion status."""
        from api.routes.stream import stream_generator

        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)
        messages = [{"role": "user", "content": "What are my investment preferences?"}]
        status_messages = []

        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[{"name": "get_user_profile"}])
            mock_mcp.call_tool = AsyncMock(return_value={
                "completeness": 67,
                "preferences": {"risk_tolerance": "moderate"}
            })

            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[{"name": "get_user_profile"}])
            mock_llm.chat_completion = AsyncMock(side_effect=[
                {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "id": "call-1",
                                "function": {"name": "get_user_profile", "arguments": '{"user_id": "u1"}'}
                            }]
                        }
                    }]
                },
                {"choices": [{"message": {"content": "Your preferences show..."}}]}
            ])

            async def mock_stream():
                yield {"type": "token", "content": "Your preferences"}
                yield {"type": "done", "tokens_used": {}}

            mock_llm.stream_chat_completion = mock_stream

            async for event in stream_generator("conv-123", messages, mock_request):
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify profile loading status with completeness
            assert any("Loading your profile" in msg for msg in status_messages)
            assert any("Profile loaded (67% complete)" in msg for msg in status_messages)


class TestLLMCompositionPhaseStatus:
    """Test AC #3: LLM composition phase status."""

    @pytest.mark.asyncio
    async def test_llm_composition_status_before_streaming(self):
        """Test that 'Composing response...' is emitted before LLM streaming starts."""
        from api.routes.stream import stream_generator

        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)
        messages = [{"role": "user", "content": "Hello"}]
        status_messages = []

        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[])

            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[])

            # No tool calls - go straight to streaming
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": "Hello!"}}]
            })

            async def mock_stream():
                yield {"type": "token", "content": "Hello!"}
                yield {"type": "done", "tokens_used": {"prompt": 10, "completion": 2}}

            mock_llm.stream_chat_completion = mock_stream

            events = []
            async for event in stream_generator("conv-123", messages, mock_request):
                events.append(event)
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify "Composing response..." status appears before first token
            assert any("Composing response" in msg for msg in status_messages), \
                f"Expected LLM composition status, got: {status_messages}"

            # Verify status appears before token in event stream
            status_idx = None
            token_idx = None
            for i, event in enumerate(events):
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status" and "Composing response" in data.get("message", ""):
                        status_idx = i
                    elif data.get("type") == "token" and status_idx is None:
                        token_idx = i

            assert status_idx is not None, "Composition status not found"
            if token_idx is not None:
                assert status_idx < token_idx, "Composition status should appear before first token"


class TestGrokLiveSearchStatus:
    """Test AC #4: Grok Live Search status emissions."""

    @pytest.mark.asyncio
    async def test_grok_live_search_status_when_used(self):
        """Test that Grok Live Search completion status is emitted when sources are used."""
        from api.routes.stream import stream_generator

        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)
        messages = [{"role": "user", "content": "What's the latest news?"}]
        status_messages = []

        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[])

            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[])
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": "Here's the news..."}}]
            })

            # Simulate Grok Live Search being used (sources_used in done event)
            async def mock_stream_with_live_search(*args, **kwargs):
                yield {"type": "token", "content": "Here's "}
                yield {"type": "token", "content": "the news..."}
                yield {
                    "type": "done",
                    "tokens_used": {"prompt": 50, "completion": 100},
                    "sources_used": 5  # Grok Live Search used 5 sources
                }

            mock_llm.stream_chat_completion = mock_stream_with_live_search

            async for event in stream_generator("conv-123", messages, mock_request):
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify Live Search completion status with source count
            assert any("Found 5 sources" in msg for msg in status_messages), \
                f"Expected Live Search sources status, got: {status_messages}"

    @pytest.mark.asyncio
    async def test_grok_live_search_no_status_when_not_used(self):
        """Test that no Live Search status is emitted when sources_used is 0."""
        from api.routes.stream import stream_generator

        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)
        messages = [{"role": "user", "content": "Simple question"}]
        status_messages = []

        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[])

            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[])
            mock_llm.chat_completion = AsyncMock(return_value={
                "choices": [{"message": {"content": "Simple answer"}}]
            })

            # No Live Search used
            async def mock_stream_no_live_search(*args, **kwargs):
                yield {"type": "token", "content": "Simple answer"}
                yield {
                    "type": "done",
                    "tokens_used": {"prompt": 10, "completion": 5},
                    "sources_used": 0  # No Live Search
                }

            mock_llm.stream_chat_completion = mock_stream_no_live_search

            async for event in stream_generator("conv-123", messages, mock_request):
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify NO Live Search status is emitted
            assert not any("sources" in msg.lower() for msg in status_messages), \
                f"Should not emit Live Search status when sources_used=0, got: {status_messages}"


class TestIntegrationScenarios:
    """Test complete scenarios with multiple status emissions."""

    @pytest.mark.asyncio
    async def test_full_workflow_with_all_statuses(self):
        """Test a complete workflow showing thinking -> memory -> profile -> composition -> live search."""
        from api.routes.stream import stream_generator

        mock_request = Mock()
        mock_request.is_disconnected = AsyncMock(return_value=False)
        messages = [{"role": "user", "content": "Should I invest in tech stocks based on my profile and past decisions?"}]
        status_messages = []

        with patch("api.routes.stream.LLMClient") as mock_llm_cls, \
             patch("api.routes.stream.MCPClient") as mock_mcp_cls, \
             patch("api.routes.stream.StateManager"):

            mock_mcp = mock_mcp_cls.return_value.__aenter__.return_value
            mock_mcp.list_tools = AsyncMock(return_value=[
                {"name": "retrieve_memories"},
                {"name": "get_user_profile"}
            ])

            # Mock tool calls for both memory and profile
            call_count = [0]
            async def mock_call_tool(tool_name, args):
                call_count[0] += 1
                if tool_name == "retrieve_memories":
                    return {"memory_count": 2, "memories": [{"content": "mem1"}, {"content": "mem2"}]}
                elif tool_name == "get_user_profile":
                    return {"completeness": 80, "preferences": {"risk_tolerance": "high"}}
                return {}

            mock_mcp.call_tool = mock_call_tool

            mock_llm = mock_llm_cls.return_value.__aenter__.return_value
            mock_llm.primary_provider_name = "grok-4"
            mock_llm.convert_mcp_tools_to_functions = Mock(return_value=[
                {"name": "retrieve_memories"},
                {"name": "get_user_profile"}
            ])

            # Simulate multi-step tool calling
            chat_calls = [0]
            async def mock_chat(*args, **kwargs):
                chat_calls[0] += 1
                if chat_calls[0] == 1:
                    # First call: retrieve memories
                    return {
                        "choices": [{
                            "message": {
                                "tool_calls": [{
                                    "id": "call-1",
                                    "function": {"name": "retrieve_memories", "arguments": "{}"}
                                }]
                            }
                        }]
                    }
                elif chat_calls[0] == 2:
                    # Second call: get profile
                    return {
                        "choices": [{
                            "message": {
                                "tool_calls": [{
                                    "id": "call-2",
                                    "function": {"name": "get_user_profile", "arguments": "{}"}
                                }]
                            }
                        }]
                    }
                else:
                    # Final call: no more tools, ready to respond
                    return {"choices": [{"message": {"content": "Based on your profile..."}}]}

            mock_llm.chat_completion = mock_chat

            # Final streaming with Live Search
            async def mock_stream(*args, **kwargs):
                yield {"type": "token", "content": "Based on "}
                yield {"type": "token", "content": "your profile..."}
                yield {
                    "type": "done",
                    "tokens_used": {"prompt": 200, "completion": 150},
                    "sources_used": 8  # Live Search used
                }

            mock_llm.stream_chat_completion = mock_stream

            async for event in stream_generator("conv-123", messages, mock_request):
                if event.get("event") == "message":
                    import json
                    data = json.loads(event["data"])
                    if data.get("type") == "status":
                        status_messages.append(data["message"])

            # Verify all expected statuses appear
            # NOTE: "thinking" status is emitted by telegram_bot before SSE connection,
            # not by stream_generator (to avoid duplicates). See stream.py lines 151-154.
            assert any("Retrieving your memories" in msg for msg in status_messages), "Should emit memory retrieval start"
            assert any("Found 2 relevant memories" in msg for msg in status_messages), "Should emit memory found"
            assert any("Loading your profile" in msg for msg in status_messages), "Should emit profile loading"
            assert any("Profile loaded (80% complete)" in msg for msg in status_messages), "Should emit profile loaded"
            assert any("Composing response" in msg for msg in status_messages), "Should emit composition phase"
            assert any("Found 8 sources" in msg for msg in status_messages), "Should emit Live Search sources"
