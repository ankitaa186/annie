"""
Tests for context window overflow recovery.

Tests:
1. ContextLengthError is raised by each provider on context-length errors
2. LLMClient._compact_context reduces context correctly
3. LLMClient.stream_chat_completion recovers from ContextLengthError
"""

import sys
from pathlib import Path

# Ensure environment is set before imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

import pytest  # noqa: E402
from unittest.mock import AsyncMock, MagicMock, patch  # noqa: E402

from api.constants import MODEL_GROK_4, MODEL_GPT_5, MODEL_GEMINI_PRO  # noqa: E402
from api.providers.base import ContextLengthError  # noqa: E402
from api.providers.grok_provider import ProviderError, RateLimitError  # noqa: E402


# ---------------------------------------------------------------------------
# 1. ContextLengthError basics
# ---------------------------------------------------------------------------

class TestContextLengthError:
    """Test ContextLengthError exception class."""

    def test_inherits_from_exception(self):
        err = ContextLengthError("test-provider", "context too long")
        assert isinstance(err, Exception)

    def test_attributes(self):
        original = ValueError("original")
        err = ContextLengthError(MODEL_GROK_4, "max tokens exceeded", original)
        assert err.provider == MODEL_GROK_4
        assert err.message == "max tokens exceeded"
        assert err.original_error is original

    def test_str_representation(self):
        err = ContextLengthError(MODEL_GPT_5, "context_length_exceeded")
        assert MODEL_GPT_5 in str(err)
        assert "context_length_exceeded" in str(err)

    def test_not_subclass_of_provider_error(self):
        """ContextLengthError is separate from ProviderError so catch order matters."""
        err = ContextLengthError("test", "msg")
        assert not isinstance(err, ProviderError)


# ---------------------------------------------------------------------------
# 2. Provider detection of context-length errors
# ---------------------------------------------------------------------------

class TestGrokContextDetection:
    """Test that GrokProvider raises ContextLengthError for context errors."""

    @pytest.mark.asyncio
    async def test_context_length_exceeded_error(self):
        """Grok raises ContextLengthError when error contains 'context_length_exceeded'."""
        from api.providers.grok_provider import GrokProvider

        provider = GrokProvider()

        # Mock HTTP response with context length error
        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "This model\'s maximum context length is 131072 tokens. context_length_exceeded"}}')
        mock_response.aiter_lines = AsyncMock(return_value=iter([]))

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(provider.client, 'stream', return_value=mock_stream_ctx):
            with pytest.raises(ContextLengthError) as exc_info:
                async for _ in provider.stream_chat_completion(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass

            assert exc_info.value.provider == MODEL_GROK_4
            assert "context_length_exceeded" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_maximum_context_length_error(self):
        """Grok raises ContextLengthError when error contains 'maximum context length'."""
        from api.providers.grok_provider import GrokProvider

        provider = GrokProvider()

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "maximum context length exceeded"}}')

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(provider.client, 'stream', return_value=mock_stream_ctx):
            with pytest.raises(ContextLengthError):
                async for _ in provider.stream_chat_completion(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass

    @pytest.mark.asyncio
    async def test_regular_error_not_context_length(self):
        """Non-context errors still raise ProviderError, not ContextLengthError."""
        from api.providers.grok_provider import GrokProvider

        provider = GrokProvider()

        mock_response = AsyncMock()
        mock_response.status_code = 500
        mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "internal server error"}}')

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(provider.client, 'stream', return_value=mock_stream_ctx):
            with pytest.raises(ProviderError) as exc_info:
                async for _ in provider.stream_chat_completion(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass

            assert not isinstance(exc_info.value, ContextLengthError)


class TestChatGPTContextDetection:
    """Test that ChatGPTProvider raises ContextLengthError for context errors."""

    @pytest.mark.asyncio
    async def test_context_length_exceeded_error(self):
        """ChatGPT raises ContextLengthError for context_length_exceeded."""
        from api.providers.chatgpt_provider import ChatGPTProvider

        provider = ChatGPTProvider()

        mock_response = AsyncMock()
        mock_response.status_code = 400
        mock_response.aread = AsyncMock(return_value=b'{"error": {"message": "This model\'s maximum context length is 128000 tokens, however you requested 150000 tokens. context_length_exceeded"}}')

        mock_stream_ctx = AsyncMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        with patch.object(provider.client, 'stream', return_value=mock_stream_ctx):
            with pytest.raises(ContextLengthError) as exc_info:
                async for _ in provider._stream_single_completion(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass

            assert exc_info.value.provider == MODEL_GPT_5


class TestGeminiContextDetection:
    """Test that GeminiProvider raises ContextLengthError for context errors."""

    @pytest.mark.asyncio
    async def test_resource_exhausted_token_limit(self):
        """Gemini raises ContextLengthError for RESOURCE_EXHAUSTED + token + limit."""
        from api.providers.gemini_provider import GeminiProvider

        provider = GeminiProvider()

        # Simulate the Gemini SDK raising an error with token limit message
        error = Exception("400 RESOURCE_EXHAUSTED: Request payload exceeds the token limit of 1048576 tokens")

        with patch.object(provider.model, 'start_chat') as mock_chat:
            mock_session = MagicMock()
            mock_session.send_message.side_effect = error
            mock_chat.return_value = mock_session

            with pytest.raises(ContextLengthError) as exc_info:
                async for _ in provider.stream_chat_completion(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass

            assert "token" in str(exc_info.value).lower() or "limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_rate_limit_not_context_error(self):
        """Gemini quota/rate limit errors should NOT become ContextLengthError."""
        from api.providers.gemini_provider import GeminiProvider

        provider = GeminiProvider()

        # Simulate quota error without token/limit keywords
        error = Exception("429 RESOURCE EXHAUSTED: Quota exceeded for the day")

        with patch.object(provider.model, 'start_chat') as mock_chat:
            mock_session = MagicMock()
            mock_session.send_message.side_effect = error
            mock_chat.return_value = mock_session

            with pytest.raises(RateLimitError):
                async for _ in provider.stream_chat_completion(
                    [{"role": "user", "content": "hello"}]
                ):
                    pass


# ---------------------------------------------------------------------------
# 3. LLMClient._compact_context
# ---------------------------------------------------------------------------

class TestCompactContext:
    """Test the _compact_context helper on LLMClient."""

    def _make_client(self):
        """Create LLMClient with mocked provider."""
        with patch('api.llm_client.GrokProvider'):
            from api.llm_client import LLMClient
            return LLMClient()

    @pytest.mark.asyncio
    async def test_keeps_system_messages(self):
        """System messages are always preserved."""
        client = self._make_client()
        messages = [
            {"role": "system", "content": "You are Annie"},
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
            {"role": "user", "content": "msg2"},
            {"role": "assistant", "content": "reply2"},
            {"role": "user", "content": "msg3"},
            {"role": "assistant", "content": "reply3"},
            {"role": "user", "content": "msg4"},
        ]
        result = await client._compact_context(messages, None, None)

        # System message should be first
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are Annie"

    @pytest.mark.asyncio
    async def test_keeps_recent_messages(self):
        """Recent non-system messages are kept (up to 6)."""
        client = self._make_client()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "old_reply1"},
            {"role": "user", "content": "old2"},
            {"role": "assistant", "content": "old_reply2"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent_reply1"},
            {"role": "user", "content": "recent2"},
            {"role": "assistant", "content": "recent_reply2"},
            {"role": "user", "content": "recent3"},
            {"role": "assistant", "content": "recent_reply3"},
        ]
        result = await client._compact_context(messages, None, None)

        # 1 system + 6 recent (no summary since no state_manager)
        assert len(result) == 7
        assert result[-1]["content"] == "recent_reply3"
        assert result[-6]["content"] == "recent1"

    @pytest.mark.asyncio
    async def test_with_summary(self):
        """When state_manager provides a summary, it's injected as system message."""
        client = self._make_client()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "old_reply1"},
            {"role": "user", "content": "old2"},
            {"role": "assistant", "content": "old_reply2"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent_reply1"},
            {"role": "user", "content": "recent2"},
            {"role": "assistant", "content": "recent_reply2"},
            {"role": "user", "content": "recent3"},
            {"role": "assistant", "content": "recent_reply3"},
        ]

        mock_state = AsyncMock()
        mock_state.get_or_create_summary = AsyncMock(return_value="User discussed topics X and Y")

        result = await client._compact_context(messages, "conv_123", mock_state)

        # 1 original system + 1 summary system + 6 recent
        assert len(result) == 8
        assert result[0]["content"] == "sys"
        assert "[Earlier conversation summary]" in result[1]["content"]
        assert "User discussed topics X and Y" in result[1]["content"]
        assert result[1]["role"] == "system"

    @pytest.mark.asyncio
    async def test_summary_failure_falls_back(self):
        """When summary generation fails, falls back to brute-force truncation."""
        client = self._make_client()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old1"},
            {"role": "assistant", "content": "old_reply1"},
            {"role": "user", "content": "recent1"},
            {"role": "assistant", "content": "recent_reply1"},
            {"role": "user", "content": "recent2"},
            {"role": "assistant", "content": "recent_reply2"},
            {"role": "user", "content": "recent3"},
            {"role": "assistant", "content": "recent_reply3"},
        ]

        mock_state = AsyncMock()
        mock_state.get_or_create_summary = AsyncMock(side_effect=Exception("LLM unavailable"))

        result = await client._compact_context(messages, "conv_123", mock_state)

        # Should still produce valid result (brute-force: system + recent 6)
        assert result[0]["role"] == "system"
        assert len(result) <= 7  # system + at most 6

    @pytest.mark.asyncio
    async def test_few_messages_no_summary(self):
        """With few messages, keeps all and no summary attempt."""
        client = self._make_client()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
        ]

        result = await client._compact_context(messages, None, None)

        # 1 system + 2 non-system (all kept since <= 6)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_no_state_manager_no_summary(self):
        """Without state_manager, summary is skipped."""
        client = self._make_client()
        messages = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old_reply"},
            {"role": "user", "content": "r1"},
            {"role": "assistant", "content": "r1_reply"},
            {"role": "user", "content": "r2"},
            {"role": "assistant", "content": "r2_reply"},
            {"role": "user", "content": "r3"},
            {"role": "assistant", "content": "r3_reply"},
        ]

        result = await client._compact_context(messages, "conv_123", None)

        # No summary, just system + 6 recent
        assert len(result) == 7
        # No summary message
        assert not any("[Earlier conversation summary]" in m.get("content", "") for m in result)


# ---------------------------------------------------------------------------
# 4. LLMClient.stream_chat_completion overflow recovery integration
# ---------------------------------------------------------------------------

class TestOverflowRecoveryIntegration:
    """Test that stream_chat_completion handles ContextLengthError end-to-end."""

    @pytest.mark.asyncio
    async def test_recovers_with_compacted_context(self):
        """On ContextLengthError, compacts and retries successfully."""
        from api.llm_client import LLMClient

        with patch('api.llm_client.GrokProvider'):
            client = LLMClient()

            call_count = 0

            async def mock_stream(messages, tools=None, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ContextLengthError(MODEL_GROK_4, "context_length_exceeded")
                # Second call succeeds
                yield {"type": "token", "content": "recovered"}
                yield {"type": "done", "tokens_used": {"prompt": 10, "completion": 1}}

            client.provider.stream_chat_completion = mock_stream
            client.provider.close = AsyncMock()

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "msg"},
            ]

            events = []
            async for event in client.stream_chat_completion(messages):
                events.append(event)

            # Should have recovered
            assert any(e.get("content") == "recovered" for e in events)
            assert any(e.get("type") == "done" for e in events)
            assert call_count == 2

    @pytest.mark.asyncio
    async def test_falls_to_fallback_after_compacted_retry_fails(self):
        """If compacted retry also fails, falls through to fallback provider."""
        from api.llm_client import LLMClient

        with patch('api.llm_client.GrokProvider'), \
             patch('api.llm_client.ChatGPTProvider') as MockChatGPT:

            client = LLMClient()

            # Primary always raises ContextLengthError
            async def primary_stream(messages, tools=None, **kwargs):
                raise ContextLengthError(MODEL_GROK_4, "context_length_exceeded")
                yield  # make it a generator

            client.provider.stream_chat_completion = primary_stream
            client.provider.close = AsyncMock()

            # Fallback succeeds
            mock_fallback = AsyncMock()
            mock_fallback.__aenter__ = AsyncMock(return_value=mock_fallback)
            mock_fallback.__aexit__ = AsyncMock(return_value=False)

            async def fallback_stream(messages, tools=None, **kwargs):
                yield {"type": "token", "content": "fallback ok"}
                yield {"type": "done", "tokens_used": {"prompt": 5, "completion": 1}}

            mock_fallback.stream_chat_completion = fallback_stream
            MockChatGPT.return_value = mock_fallback

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "msg"},
            ]

            events = []
            async for event in client.stream_chat_completion(messages):
                events.append(event)

            assert any(e.get("content") == "fallback ok" for e in events)

    @pytest.mark.asyncio
    async def test_no_fallback_yields_error(self):
        """If compacted retry fails and no fallback, yields error event."""
        from api.llm_client import LLMClient

        with patch('api.llm_client.GrokProvider'):
            client = LLMClient()
            # Only grok available, no chatgpt
            client.providers_available[MODEL_GPT_5] = False
            client.providers_available[MODEL_GEMINI_PRO] = False

            async def always_overflow(messages, tools=None, **kwargs):
                raise ContextLengthError(MODEL_GROK_4, "context_length_exceeded")
                yield  # make it a generator

            client.provider.stream_chat_completion = always_overflow
            client.provider.close = AsyncMock()

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "msg"},
            ]

            events = []
            async for event in client.stream_chat_completion(messages):
                events.append(event)

            # Should yield error since no fallback
            assert any(e.get("type") == "error" for e in events)

    @pytest.mark.asyncio
    async def test_passes_conversation_id_and_state_manager(self):
        """Verify conversation_id and state_manager are used for summary."""
        from api.llm_client import LLMClient

        with patch('api.llm_client.GrokProvider'):
            client = LLMClient()

            call_count = 0

            async def mock_stream(messages, tools=None, **kwargs):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    raise ContextLengthError(MODEL_GROK_4, "too long")
                yield {"type": "token", "content": "ok"}
                yield {"type": "done", "tokens_used": {"prompt": 5, "completion": 1}}

            client.provider.stream_chat_completion = mock_stream
            client.provider.close = AsyncMock()

            mock_state = AsyncMock()
            mock_state.get_or_create_summary = AsyncMock(return_value="Summary of old msgs")

            messages = [
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "old1"},
                {"role": "assistant", "content": "old_reply"},
                {"role": "user", "content": "old2"},
                {"role": "assistant", "content": "old_reply2"},
                {"role": "user", "content": "old3"},
                {"role": "assistant", "content": "old_reply3"},
                {"role": "user", "content": "current"},
            ]

            events = []
            async for event in client.stream_chat_completion(
                messages,
                conversation_id="conv_test_123",
                state_manager=mock_state
            ):
                events.append(event)

            # Summary should have been generated
            mock_state.get_or_create_summary.assert_called_once()
            call_args = mock_state.get_or_create_summary.call_args
            assert call_args[0][0] == "conv_test_123"  # conversation_id

            # Should have recovered
            assert any(e.get("content") == "ok" for e in events)
