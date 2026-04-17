"""
Unit tests for context compaction (pruning + summarization).

Tests:
- _create_tool_result_summary: deterministic, no mocks needed
- _prune_tool_results: deterministic, no mocks needed
- _format_messages_for_summary: deterministic
- get_or_create_summary: mocked LLMClient and Redis
- build_llm_context with summarization: mocked dependencies
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from api.state import StateManager


# =========================================================================
# _create_tool_result_summary tests (pure function, no mocks)
# =========================================================================

class TestCreateToolResultSummary:
    """Tests for deterministic tool result summarization."""

    def test_json_error_result(self):
        content = json.dumps({"status": "error", "error": "timeout after 10s"})
        result = StateManager._create_tool_result_summary(content, "web_search")
        assert "[Error:" in result
        assert "timeout" in result

    def test_json_failed_result(self):
        content = json.dumps({"status": "failed", "error": "connection refused"})
        result = StateManager._create_tool_result_summary(content, "web_crawl")
        assert "[Error:" in result

    def test_json_queued_result(self):
        content = json.dumps({"status": "queued", "message": "Memory storage initiated"})
        result = StateManager._create_tool_result_summary(content)
        assert result == "[Queued for background processing]"

    def test_json_results_array(self):
        content = json.dumps({
            "results": [
                {"title": "Result 1", "url": "http://example.com/1"},
                {"title": "Result 2", "url": "http://example.com/2"},
                {"title": "Result 3", "url": "http://example.com/3"}
            ]
        })
        result = StateManager._create_tool_result_summary(content, "web_search")
        assert result == "[Returned 3 results]"

    def test_json_memories_array(self):
        content = json.dumps({
            "memories": [{"id": "1", "text": "memory"}],
            "memory_count": 1
        })
        result = StateManager._create_tool_result_summary(content, "retrieve_memories")
        assert "[Retrieved 1 memories]" in result

    def test_json_memory_count(self):
        content = json.dumps({"memory_count": 5})
        result = StateManager._create_tool_result_summary(content)
        assert result == "[Retrieved 5 memories]"

    def test_json_profile(self):
        content = json.dumps({"completeness": 75, "basics": {"name": "Test"}})
        result = StateManager._create_tool_result_summary(content)
        assert "75%" in result

    def test_json_portfolio(self):
        content = json.dumps({
            "holdings": [
                {"ticker": "AAPL", "shares": 10},
                {"ticker": "NVDA", "shares": 5}
            ]
        })
        result = StateManager._create_tool_result_summary(content)
        assert result == "[Portfolio: 2 holdings]"

    def test_json_entities(self):
        content = json.dumps({
            "entities": [
                {"entity_id": "light.living_room", "state": "on"},
                {"entity_id": "sensor.temp", "state": "72"}
            ]
        })
        result = StateManager._create_tool_result_summary(content)
        assert result == "[2 entities returned]"

    def test_json_success_with_message(self):
        content = json.dumps({"status": "success", "message": "Profile updated"})
        result = StateManager._create_tool_result_summary(content)
        assert "Success" in result
        assert "Profile updated" in result

    def test_json_success_no_message(self):
        content = json.dumps({"status": "success"})
        result = StateManager._create_tool_result_summary(content)
        assert result == "[Success]"

    def test_json_generic_dict(self):
        content = json.dumps({"some_key": "some_value", "other": 123})
        result = StateManager._create_tool_result_summary(content, "custom_tool")
        assert "custom_tool result:" in result
        assert "chars" in result

    def test_non_json_content(self):
        content = "This is plain text, not JSON"
        result = StateManager._create_tool_result_summary(content)
        assert "[Tool result:" in result
        assert "chars" in result

    def test_empty_content(self):
        result = StateManager._create_tool_result_summary("", "test_tool")
        assert "[Tool result:" in result

    def test_none_content(self):
        result = StateManager._create_tool_result_summary(None, "test_tool")
        assert "[Tool result:" in result

    def test_long_error_truncated(self):
        long_error = "x" * 200
        content = json.dumps({"status": "error", "error": long_error})
        result = StateManager._create_tool_result_summary(content)
        # Error should be truncated to 80 chars
        assert len(result) < 200


# =========================================================================
# _prune_tool_results tests (pure function, no mocks)
# =========================================================================

class TestPruneToolResults:
    """Tests for tool result pruning."""

    def _make_messages(self, turns):
        """
        Helper to build a message list from turn descriptions.

        Each turn is a list of dicts: [{"role": "user", "content": "..."}, ...]
        """
        messages = []
        for turn in turns:
            messages.extend(turn)
        return messages

    def test_empty_messages(self):
        result = StateManager._prune_tool_results([])
        assert result == []

    def test_single_turn_no_pruning(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        result = StateManager._prune_tool_results(messages, keep_recent_turns=2)
        assert result == messages

    def test_two_turns_no_pruning(self):
        messages = [
            {"role": "user", "content": "Turn 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Response 2"}
        ]
        result = StateManager._prune_tool_results(messages, keep_recent_turns=2)
        assert result == messages

    def test_three_turns_prunes_oldest_tool_results(self):
        """With 3 turns and keep_recent=2, the first turn's tool results get pruned."""
        messages = [
            # Turn 1 (old — should be pruned)
            {"role": "user", "content": "Search for AAPL"},
            {
                "role": "assistant",
                "content": "",
                "is_tool_call": True,
                "tool_calls": [
                    {"id": "tc1", "type": "function", "function": {"name": "web_search", "arguments": '{"query": "AAPL stock"}'}}
                ]
            },
            {
                "role": "tool",
                "content": json.dumps({"results": [{"title": "Apple Inc"}] * 5}),
                "tool_call_id": "tc1",
                "tool_name": "web_search"
            },
            {"role": "assistant", "content": "Here's what I found about AAPL..."},
            # Turn 2 (recent — kept)
            {"role": "user", "content": "What about NVDA?"},
            {"role": "assistant", "content": "Let me check NVDA for you."},
            # Turn 3 (recent — kept)
            {"role": "user", "content": "Thanks!"},
            {"role": "assistant", "content": "You're welcome!"}
        ]

        result = StateManager._prune_tool_results(messages, keep_recent_turns=2)

        # Tool result in turn 1 should be pruned
        tool_result_msg = result[2]
        assert tool_result_msg["_pruned"] is True
        assert "[Returned 5 results]" in tool_result_msg["content"]

        # Tool call arguments in turn 1 should be stripped, type preserved
        tool_call_msg = result[1]
        assert tool_call_msg["_pruned"] is True
        assert tool_call_msg["tool_calls"][0]["function"]["arguments"] == "{}"
        assert tool_call_msg["tool_calls"][0]["type"] == "function"

        # Recent turns should be untouched
        assert result[4]["content"] == "What about NVDA?"
        assert result[6]["content"] == "Thanks!"

    def test_no_tool_messages_no_change(self):
        """Even with many turns, if no tool messages exist, nothing changes."""
        messages = [
            {"role": "user", "content": f"Turn {i}"}
            for i in range(5)
        ]
        result = StateManager._prune_tool_results(messages, keep_recent_turns=2)
        assert result == messages

    def test_recent_tool_results_preserved(self):
        """Tool results in recent turns should NOT be pruned."""
        messages = [
            # Old turn
            {"role": "user", "content": "Old question"},
            {"role": "assistant", "content": "Old answer"},
            # Recent turn with tool
            {"role": "user", "content": "Search for something"},
            {
                "role": "assistant",
                "content": "",
                "is_tool_call": True,
                "tool_calls": [
                    {"id": "tc1", "function": {"name": "web_search", "arguments": '{"query": "test"}'}}
                ]
            },
            {
                "role": "tool",
                "content": json.dumps({"results": [{"title": "Test"}]}),
                "tool_call_id": "tc1",
                "tool_name": "web_search"
            },
            {"role": "assistant", "content": "Here's what I found."},
            # Most recent turn
            {"role": "user", "content": "Got it, thanks!"},
            {"role": "assistant", "content": "Happy to help!"}
        ]

        result = StateManager._prune_tool_results(messages, keep_recent_turns=2)

        # Tool result in recent turn should be preserved (not pruned)
        tool_result = result[4]
        assert "_pruned" not in tool_result
        assert "results" in tool_result["content"]

    def test_keep_recent_turns_default(self):
        """Default keep_recent_turns=2 should preserve last 2 user turns."""
        messages = [
            {"role": "user", "content": "Turn 1"},
            {"role": "tool", "content": json.dumps({"results": [1, 2, 3]}), "tool_call_id": "tc1", "tool_name": "search"},
            {"role": "user", "content": "Turn 2"},
            {"role": "assistant", "content": "Answer 2"},
            {"role": "user", "content": "Turn 3"},
            {"role": "assistant", "content": "Answer 3"}
        ]

        result = StateManager._prune_tool_results(messages)  # default keep_recent_turns=2

        # Turn 1's tool result should be pruned
        assert result[1].get("_pruned") is True


# =========================================================================
# _format_messages_for_summary tests (pure function)
# =========================================================================

class TestFormatMessagesForSummary:
    """Tests for message formatting for the summarizer."""

    def test_basic_conversation(self):
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "User: Hello" in result
        assert "Assistant: Hi there!" in result

    def test_tool_messages_labeled(self):
        messages = [
            {"role": "tool", "content": "some result", "tool_name": "web_search"},
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "[Tool: web_search]" in result

    def test_tool_call_messages(self):
        messages = [
            {
                "role": "assistant",
                "content": "",
                "is_tool_call": True,
                "tool_calls": [
                    {"function": {"name": "web_search"}},
                    {"function": {"name": "retrieve_memories"}}
                ]
            }
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "web_search" in result
        assert "retrieve_memories" in result

    def test_system_messages_skipped(self):
        messages = [
            {"role": "system", "content": "You are Annie..."},
            {"role": "user", "content": "Hello"}
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "Annie" not in result
        assert "User: Hello" in result

    def test_long_user_content_not_truncated(self):
        long_content = "x" * 1000
        messages = [
            {"role": "user", "content": long_content}
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "[truncated]" not in result
        assert long_content in result

    def test_long_assistant_content_truncated_at_20k(self):
        long_content = "x" * 25000
        messages = [
            {"role": "assistant", "content": long_content}
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "[truncated]" in result
        assert len(result) < 20100  # 20000 chars + label + truncation marker

    def test_long_tool_content_truncated_at_10k(self):
        long_content = "x" * 15000
        messages = [
            {"role": "tool", "tool_name": "web_search", "content": long_content}
        ]
        result = StateManager._format_messages_for_summary(messages)
        assert "[truncated]" in result
        assert len(result) < 10100  # 10000 chars + label + truncation marker


# =========================================================================
# _extract_long_term_content tests (pure function)
# =========================================================================

class TestExtractLongTermContent:
    """Tests for extracting long-term content from structured summaries."""

    def test_extracts_both_sections(self):
        summary = """## What was on their mind
The user was stressed about their portfolio dropping and wanted reassurance about holding NVDA long-term.

## What we talked about
- Checked NVDA stock price using web_search
- Discussed long-term investment strategy
- Reviewed portfolio diversification

## What matters going forward
- User decided to hold NVDA despite the dip, citing long-term conviction
- User expressed preference for weekly portfolio updates rather than daily

## Metadata
```json
{"topics": ["investing", "nvda"], "mood": "stressed", "category": "advice", "people_mentioned": [], "has_unresolved": false}
```
"""
        result = StateManager._extract_long_term_content(summary)
        assert result is not None
        assert "stressed about their portfolio" in result
        assert "hold NVDA" in result
        assert "weekly portfolio updates" in result
        # Should not contain "What we talked about" content
        assert "web_search" not in result

    def test_extracts_forward_section_only(self):
        """If 'What was on their mind' is missing, still extract forward section."""
        summary = """## What we talked about
- Discussed weather

## What matters going forward
- User prefers morning notifications over evening
"""
        result = StateManager._extract_long_term_content(summary)
        assert result is not None
        assert "morning notifications" in result

    def test_extracts_mind_section_only(self):
        """If forward section is casual, still extract mind section if substantive."""
        summary = """## What was on their mind
The user was dealing with a tough day at work and needed someone to talk to about their frustrations with their manager.

## What we talked about
- Vented about work situation

## What matters going forward
Nothing specific — casual conversation.
"""
        result = StateManager._extract_long_term_content(summary)
        assert result is not None
        assert "tough day at work" in result
        # Forward section excluded because it's casual
        assert "Nothing specific" not in result

    def test_returns_none_for_casual_conversation(self):
        """Both sections are casual/empty — nothing to persist."""
        summary = """## What was on their mind
Nothing specific — casual conversation.

## What we talked about
- Chatted about the weather

## What matters going forward
Nothing specific — casual conversation.
"""
        result = StateManager._extract_long_term_content(summary)
        assert result is None

    def test_returns_none_for_empty(self):
        assert StateManager._extract_long_term_content("") is None
        assert StateManager._extract_long_term_content(None) is None

    def test_returns_none_when_no_structure(self):
        """No recognized section headers — nothing to extract."""
        summary = "User discussed stocks. Decided to hold NVDA."
        result = StateManager._extract_long_term_content(summary)
        assert result is None

    def test_handles_forward_at_end_of_text(self):
        summary = """## What was on their mind
User was curious about crypto trends.

## What we talked about
- Looked up Bitcoin price

## What matters going forward
- User is risk-averse with crypto investments
- Wants to revisit in a month"""
        result = StateManager._extract_long_term_content(summary)
        assert "risk-averse" in result
        assert "revisit in a month" in result
        assert "curious about crypto" in result

    def test_handles_metadata_after_forward_section(self):
        summary = """## What was on their mind
User wanted to plan a vacation.

## What we talked about
- Researched destinations

## What matters going forward
- Made a key decision about vacation to Japan in March

## Metadata
```json
{"topics": ["travel"], "mood": "excited", "category": "planning", "people_mentioned": [], "has_unresolved": false}
```"""
        result = StateManager._extract_long_term_content(summary)
        assert "vacation to Japan" in result
        # Should not include metadata section
        assert "```json" not in result


# =========================================================================
# _parse_summary_metadata tests (pure function)
# =========================================================================

class TestParseSummaryMetadata:
    """Tests for parsing LLM-generated metadata and merging with system fields."""

    def test_parses_valid_metadata(self):
        summary = """## What was on their mind
User wanted advice.

## Metadata
```json
{"topics": ["investing", "nvda"], "mood": "stressed", "category": "advice", "people_mentioned": ["Sarah"], "has_unresolved": true}
```
"""
        result = StateManager._parse_summary_metadata(
            summary, "conv_123", "user_456", "Ankit", 15
        )
        # System fields
        assert result["conversation_id"] == "conv_123"
        assert result["user_id"] == "user_456"
        assert result["user_name"] == "Ankit"
        assert result["source"] == "session_summary"
        assert result["message_count"] == 15
        assert "-08:00" in result["timestamp"] or "-07:00" in result["timestamp"]
        # LLM fields
        assert result["topics"] == ["investing", "nvda"]
        assert result["mood"] == "stressed"
        assert result["category"] == "advice"
        assert result["people_mentioned"] == ["Sarah"]
        assert result["has_unresolved"] is True

    def test_handles_missing_metadata_section(self):
        summary = """## What was on their mind
User just chatted.
"""
        result = StateManager._parse_summary_metadata(
            summary, "conv_1", "user_1", None, 5
        )
        # System fields present
        assert result["conversation_id"] == "conv_1"
        assert result["user_id"] == "user_1"
        assert result["message_count"] == 5
        # No LLM fields
        assert "topics" not in result
        assert "mood" not in result
        # No user_name if None
        assert "user_name" not in result

    def test_handles_malformed_json_gracefully(self):
        summary = """## Metadata
```json
{not valid json!!!}
```
"""
        result = StateManager._parse_summary_metadata(
            summary, "conv_2", "user_2", "Test", 3
        )
        # System fields still present
        assert result["conversation_id"] == "conv_2"
        assert result["user_id"] == "user_2"
        assert result["user_name"] == "Test"
        # No LLM fields (parsing failed gracefully)
        assert "topics" not in result

    def test_handles_partial_llm_metadata(self):
        """Only some LLM fields present."""
        summary = """## Metadata
```json
{"topics": ["stocks"], "mood": "neutral"}
```
"""
        result = StateManager._parse_summary_metadata(
            summary, "conv_3", "user_3", None, 10
        )
        assert result["topics"] == ["stocks"]
        assert result["mood"] == "neutral"
        assert "category" not in result
        assert "has_unresolved" not in result

    def test_user_name_omitted_when_none(self):
        result = StateManager._parse_summary_metadata(
            "no metadata", "conv_4", "user_4", None, 2
        )
        assert "user_name" not in result


# =========================================================================
# get_or_create_summary tests (mocked)
# =========================================================================

class TestGetOrCreateSummary:
    """Tests for summary caching and generation with mocked dependencies."""

    @pytest.mark.asyncio
    async def test_returns_cached_fresh_summary(self):
        """Should return cached summary if within staleness threshold."""
        cached_data = json.dumps({
            "text": "Previously summarized content",
            "message_count_at_generation": 18,
            "generated_at": "2025-01-01T00:00:00Z"
        })

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached_data)
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.get_or_create_summary(
            "conv_123",
            [{"role": "user", "content": "old msg"}],
            current_message_count=20  # 20 - 18 = 2, below threshold of 5
        )

        assert result == "Previously summarized content"

    @pytest.mark.asyncio
    async def test_regenerates_stale_summary(self):
        """Should regenerate summary if beyond staleness threshold."""
        cached_data = json.dumps({
            "text": "Old summary",
            "message_count_at_generation": 10,
            "generated_at": "2025-01-01T00:00:00Z"
        })

        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=cached_data)
        mock_redis.setex = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        # Mock the LLM call

        with patch("api.state.get_config", return_value={
            "REDIS_HOST": "localhost",
            "REDIS_PORT": "6379"
        }):
            with patch("api.state.StateManager._generate_summary", new_callable=AsyncMock) as mock_gen:
                mock_gen.return_value = "New summary of conversation"

                # Mock _echo_summary_to_memories to prevent background task
                with patch.object(state, "_echo_summary_to_memories", new_callable=AsyncMock):
                    result = await state.get_or_create_summary(
                        "conv_123",
                        [{"role": "user", "content": "old msg"}],
                        current_message_count=20  # 20 - 10 = 10, above threshold of 5
                    )

        assert result == "New summary of conversation"

    @pytest.mark.asyncio
    async def test_returns_none_on_generation_failure(self):
        """Should return None if summary generation fails."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch.object(state, "_generate_summary", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = None

            result = await state.get_or_create_summary(
                "conv_123",
                [{"role": "user", "content": "test"}],
                current_message_count=20
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_caches_new_summary(self):
        """Should cache newly generated summary in Redis."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch.object(state, "_generate_summary", new_callable=AsyncMock) as mock_gen:
            mock_gen.return_value = "Generated summary"

            with patch.object(state, "_echo_summary_to_memories", new_callable=AsyncMock):
                result = await state.get_or_create_summary(
                    "conv_123",
                    [{"role": "user", "content": "test"}],
                    current_message_count=20
                )

        assert result == "Generated summary"
        # Verify cache was written
        mock_redis.setex.assert_called_once()
        cache_key = mock_redis.setex.call_args[0][0]
        assert cache_key == "conversation:conv_123:summary"


# =========================================================================
# build_llm_context with summarization tests (mocked)
# =========================================================================

class TestBuildLLMContextSummarization:
    """Tests for build_llm_context with summarization path."""

    @pytest.mark.asyncio
    async def test_summarization_triggered_on_overflow(self):
        """When token limit exceeded, should attempt summarization."""
        # Create enough messages to exceed token limit
        # MAX_TOKENS = 20000, CHARS_PER_TOKEN = 4, so 80000 chars needed
        long_content = "x" * 10000  # 2500 tokens per message
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
        ] * 5  # 10 messages, 25000 tokens total

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch.object(state, "get_or_create_summary", new_callable=AsyncMock) as mock_summary:
            mock_summary.return_value = "Summary of earlier conversation"

            result = await state.build_llm_context("conv_123", "You are Annie")

        # Should have called summarization at least once. Note: with 10+ messages,
        # build_llm_context fires both the count-based refresh (Phase 2) and the
        # token-overflow path, so it can be called up to twice — that's expected.
        assert mock_summary.call_count >= 1

        # Should include the summary system message
        system_msgs = [m for m in result if m["role"] == "system"]
        assert any("[Earlier conversation summary]" in m["content"] for m in system_msgs)

    @pytest.mark.asyncio
    async def test_fallback_to_truncation_on_summary_failure(self):
        """If summarization fails, should fall back to plain truncation."""
        long_content = "x" * 10000
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
        ] * 5

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch.object(state, "get_or_create_summary", new_callable=AsyncMock) as mock_summary:
            mock_summary.return_value = None  # Failure

            result = await state.build_llm_context("conv_123", "You are Annie")

        # Should still return valid context (truncated)
        assert len(result) > 0
        # Should not contain summary
        assert not any(
            "[Earlier conversation summary]" in m.get("content", "")
            for m in result
        )

    @pytest.mark.asyncio
    async def test_no_summarization_when_under_limit(self):
        """Should not summarize when within token limits."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"}
        ]

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch.object(state, "get_or_create_summary", new_callable=AsyncMock) as mock_summary:
            await state.build_llm_context("conv_123", "You are Annie")

        # Should NOT call summarization
        mock_summary.assert_not_called()

    @pytest.mark.asyncio
    async def test_pruning_applied_before_token_check(self):
        """Pruning should happen before token calculation."""
        # Build messages with old tool results that should be pruned
        messages = [
            # Old turn with verbose tool result
            {"role": "user", "content": "Search for AAPL"},
            {
                "role": "assistant", "content": "",
                "is_tool_call": True,
                "tool_calls": [{"id": "tc1", "function": {"name": "web_search", "arguments": '{"q":"AAPL"}'}}]
            },
            {
                "role": "tool",
                "content": json.dumps({"results": [{"title": f"Result {i}"} for i in range(10)]}),
                "tool_call_id": "tc1",
                "tool_name": "web_search"
            },
            # Recent turns
            {"role": "user", "content": "What about NVDA?"},
            {"role": "assistant", "content": "Here's NVDA info..."},
            {"role": "user", "content": "Thanks"},
            {"role": "assistant", "content": "You're welcome!"}
        ]

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.build_llm_context("conv_123", "You are Annie")

        # Find the tool result message
        tool_msgs = [m for m in result if m.get("role") == "tool"]
        if tool_msgs:
            # The old tool result should have been pruned
            assert "_pruned" in tool_msgs[0] or "[Returned" in tool_msgs[0].get("content", "")


# =========================================================================
# _echo_summary_to_memories tests (verifies store_direct integration)
# =========================================================================

class TestEchoSummaryToMemories:
    """Tests for _echo_summary_to_memories using store_direct."""

    @pytest.mark.asyncio
    async def test_echo_calls_store_direct_with_long_term_content(self):
        """Should extract long-term content and call store_direct with correct params."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user_123")
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        summary = """## What was on their mind
The user was stressed about their portfolio and wanted reassurance about holding NVDA.

## What we talked about
- Checked NVDA stock price using web_search
- Discussed long-term investment strategy

## What matters going forward
- User decided to hold NVDA despite the dip, citing long-term conviction
- User prefers weekly portfolio updates rather than daily

## Metadata
```json
{"topics": ["investing", "nvda"], "mood": "stressed", "category": "advice", "people_mentioned": [], "has_unresolved": false}
```
"""
        mock_store_direct = AsyncMock(return_value={"id": "mem_1"})
        messages = [{"role": "user", "content": "msg"}] * 10

        with patch("api.memory_client.MemoryClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.store_direct = mock_store_direct
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with patch("api.profile.ProfileManager") as MockProfile:
                mock_profile_instance = AsyncMock()
                mock_profile_instance.load_profile_from_cache = AsyncMock(
                    return_value={"basics": {"name": "Ankit"}}
                )
                MockProfile.return_value = mock_profile_instance

                await state._echo_summary_to_memories("conv_abc", summary, messages)

            # Verify store_direct was called
            mock_store_direct.assert_called_once()
            call_kwargs = mock_store_direct.call_args[1]
            assert call_kwargs["user_id"] == "user_123"
            assert "hold NVDA" in call_kwargs["content"]
            assert "stressed about their portfolio" in call_kwargs["content"]
            assert call_kwargs["layer"] == "episodic"
            assert call_kwargs["memory_type"] == "explicit"
            # Tags
            assert "conversation_summary" in call_kwargs["persona_tags"]
            assert "advice" in call_kwargs["persona_tags"]
            assert "investing" in call_kwargs["persona_tags"]
            assert "nvda" in call_kwargs["persona_tags"]
            # Metadata
            assert call_kwargs["metadata"]["conversation_id"] == "conv_abc"
            assert call_kwargs["metadata"]["source"] == "session_summary"
            assert call_kwargs["metadata"]["user_id"] == "user_123"
            assert call_kwargs["metadata"]["user_name"] == "Ankit"
            assert call_kwargs["metadata"]["message_count"] == 10
            assert call_kwargs["metadata"]["mood"] == "stressed"
            assert call_kwargs["metadata"]["category"] == "advice"
            ts = call_kwargs["metadata"]["timestamp"]
            assert "-08:00" in ts or "-07:00" in ts

    @pytest.mark.asyncio
    async def test_echo_skips_when_no_user_id(self):
        """Should skip when no user_id mapping found."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch("api.memory_client.MemoryClient") as MockClient:
            await state._echo_summary_to_memories(
                "conv_no_user",
                "## What matters going forward\n- Some decision"
            )
            MockClient.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_skips_when_casual_conversation(self):
        """Should skip when summary has no significant content."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user_123")
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        summary = """## What was on their mind
Nothing specific — casual conversation.

## What we talked about
- Chatted about the weather

## What matters going forward
Nothing specific — casual conversation.
"""
        with patch("api.memory_client.MemoryClient") as MockClient:
            await state._echo_summary_to_memories("conv_trivial", summary)
            MockClient.assert_not_called()

    @pytest.mark.asyncio
    async def test_echo_handles_store_direct_failure_gracefully(self):
        """Should not raise on store_direct failure (fire-and-forget)."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user_123")
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        summary = """## What was on their mind
User wanted to switch investment strategy.

## What matters going forward
- User decided to switch to index funds
"""
        with patch("api.memory_client.MemoryClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.store_direct = AsyncMock(
                side_effect=Exception("Network failure")
            )
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with patch("api.profile.ProfileManager") as MockProfile:
                mock_profile_instance = AsyncMock()
                mock_profile_instance.load_profile_from_cache = AsyncMock(return_value=None)
                MockProfile.return_value = mock_profile_instance

                # Should not raise
                await state._echo_summary_to_memories("conv_fail", summary)

    @pytest.mark.asyncio
    async def test_echo_excludes_talked_about_section(self):
        """Should only store mind + forward sections, not 'What we talked about'."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user_123")
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        summary = """## What was on their mind
User was curious about vacation destinations.

## What we talked about
- User asked about the weather in NYC
- web_search tool returned forecast

## What matters going forward
- User expressed preference for sunny vacation destinations

## Metadata
```json
{"topics": ["travel"], "mood": "curious", "category": "planning", "people_mentioned": [], "has_unresolved": false}
```
"""
        mock_store_direct = AsyncMock(return_value={"id": "mem_2"})

        with patch("api.memory_client.MemoryClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.store_direct = mock_store_direct
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with patch("api.profile.ProfileManager") as MockProfile:
                mock_profile_instance = AsyncMock()
                mock_profile_instance.load_profile_from_cache = AsyncMock(return_value=None)
                MockProfile.return_value = mock_profile_instance

                await state._echo_summary_to_memories("conv_weather", summary)

            content = mock_store_direct.call_args[1]["content"]
            assert "sunny vacation" in content
            assert "curious about vacation" in content
            assert "weather in NYC" not in content
            assert "web_search" not in content

    @pytest.mark.asyncio
    async def test_echo_dynamic_tags_from_metadata(self):
        """Should generate dynamic tags from LLM metadata."""
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value="user_123")
        mock_redis.ping = AsyncMock(return_value=True)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        summary = """## What was on their mind
User needed help with a work problem that's been bugging them.

## What matters going forward
- Decided to talk to manager about workload
- Left unresolved: whether to ask for a raise

## Metadata
```json
{"topics": ["work", "career"], "mood": "frustrated", "category": "advice", "people_mentioned": ["manager"], "has_unresolved": true}
```
"""
        mock_store_direct = AsyncMock(return_value={"id": "mem_3"})

        with patch("api.memory_client.MemoryClient") as MockClient:
            mock_client_instance = AsyncMock()
            mock_client_instance.store_direct = mock_store_direct
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=False)
            MockClient.return_value = mock_client_instance

            with patch("api.profile.ProfileManager") as MockProfile:
                mock_profile_instance = AsyncMock()
                mock_profile_instance.load_profile_from_cache = AsyncMock(return_value=None)
                MockProfile.return_value = mock_profile_instance

                await state._echo_summary_to_memories("conv_work", summary)

            tags = mock_store_direct.call_args[1]["persona_tags"]
            assert "conversation_summary" in tags
            assert "has_unresolved" in tags
            assert "advice" in tags
            assert "work" in tags
            assert "career" in tags


# =========================================================================
# Story 22.1: Always-inject cached rolling summary
# =========================================================================

class TestAlwaysInjectSummary:
    """Story 22.1: the cached `conversation:{id}:summary` must be injected as
    a system message on normal turns, not only on 20k-token overflow."""

    @pytest.mark.asyncio
    async def test_summary_injected_when_cached_and_under_limit(self):
        """Cached summary + short context => summary appears as system msg once."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]

        cached_summary = json.dumps({
            "text": "Earlier: user asked about weekend plans.",
            "ts": 123,
            "message_count_at_generation": 2,
        })

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)

        async def fake_get(key):
            if key.endswith(":summary"):
                return cached_summary
            return None
        mock_redis.get = fake_get

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.build_llm_context("conv_abc", "You are Annie")

        system_msgs = [m for m in result if m["role"] == "system"]
        summary_msgs = [
            m for m in system_msgs
            if "[Earlier conversation summary]" in m.get("content", "")
        ]
        assert len(summary_msgs) == 1, "Expected exactly one summary block"
        assert "weekend plans" in summary_msgs[0]["content"]

    @pytest.mark.asyncio
    async def test_no_summary_injection_when_cache_empty(self):
        """No cached summary => no [Earlier conversation summary] block."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=None)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.build_llm_context("conv_abc", "You are Annie")

        assert not any(
            "[Earlier conversation summary]" in m.get("content", "")
            for m in result
        )

    @pytest.mark.asyncio
    async def test_no_double_injection_on_overflow(self):
        """When overflow branch fires with a cached summary present, the final
        context should contain exactly one [Earlier conversation summary]
        block — not two."""
        # Build messages large enough to trigger overflow.
        long_content = "x" * 10000  # 2500 tokens per msg
        messages = [
            {"role": "user", "content": long_content},
            {"role": "assistant", "content": long_content},
        ] * 5  # ~25k tokens

        cached_summary = json.dumps({
            "text": "Cached summary text.",
            "ts": 123,
            "message_count_at_generation": 10,
        })

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)

        async def fake_get(key):
            if key.endswith(":summary"):
                return cached_summary
            return None
        mock_redis.get = fake_get

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        with patch.object(state, "get_or_create_summary", new_callable=AsyncMock) as mock_summary:
            mock_summary.return_value = "Fresh summary from overflow branch."
            result = await state.build_llm_context("conv_abc", "You are Annie")

        summary_msgs = [
            m for m in result
            if m.get("role") == "system"
            and "[Earlier conversation summary]" in m.get("content", "")
        ]
        assert len(summary_msgs) == 1, (
            f"Expected exactly one summary block, got {len(summary_msgs)}: "
            f"{[m['content'][:80] for m in summary_msgs]}"
        )

    @pytest.mark.asyncio
    async def test_no_injection_when_summary_text_missing_in_payload(self):
        """Cached payload without a `text` key should be treated as absent."""
        messages = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
        ]

        cached_summary = json.dumps({"ts": 123})  # no "text"

        mock_redis = AsyncMock()
        mock_redis.lrange = AsyncMock(return_value=[json.dumps(m) for m in messages])
        mock_redis.ping = AsyncMock(return_value=True)
        mock_redis.get = AsyncMock(return_value=cached_summary)

        state = StateManager(redis_client=mock_redis)
        state._is_healthy = True

        result = await state.build_llm_context("conv_abc", "You are Annie")

        assert not any(
            "[Earlier conversation summary]" in m.get("content", "")
            for m in result
        )
