"""
Story 23.1 — Provider token counting tests.

Verifies that:
- Gemini reads usage from `usage_metadata` on the final stream chunk (AC1).
- `count_tokens()` is no longer called in the streaming code path (AC2).
- Missing `usage_metadata` produces a Langfuse generation with NO `usage`
  kwarg, plus a single WARNING (`event="usage_metadata_missing"`) (AC3).
- ChatGPT-5 stream sets `stream_options.include_usage=true` (AC4) and
  applies the same null-and-warn fallback when the usage block is absent.
- Error paths still call `generation.end()` with `level="ERROR"` (AC5).
- The Apr-04-shaped placeholder traces (low-input/low-output) cannot recur
  via the "ended without STOP" path (AC6 regression).
- Log-spam regression: the WARNING fires <1% of generations on the
  happy path (AC10).

Story 24.1 (AC9) — patch sites re-targeted to provider-owned attributes.
The fakes simulate the new SDK's async chat API:
- `client.aio.chats.create(model=, history=, config=)` returns a fake chat.
- `chat.send_message_stream(message=)` is an async coroutine that returns
  an async iterator over `_Chunk` objects.
- `function_call.args` is a plain Python `dict` (no proto walker).
- Cached-token plumbing (AC15) verified via `cached_content_token_count`
  field on `_UsageMetadata`.
"""

import base64  # noqa: F401  (kept for parity with sibling test files)
import json
import logging
import re
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import httpx
import pytest

from api.providers.chatgpt_provider import ChatGPTProvider
from api.providers.gemini_provider import GeminiProvider
from api.providers.grok_provider import RateLimitError


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _UsageMetadata:
    """Mimics the SDK's usage_metadata object on a Gemini stream chunk.

    Story 24.1 (AC15): adds `cached_content_token_count` field. Defaults to
    None (no cache hit / pre-3.x model) but can be set to a non-None int
    to simulate an implicit-cache hit.
    """

    def __init__(
        self,
        prompt_token_count: Optional[int],
        candidates_token_count: Optional[int],
        cached_content_token_count: Optional[int] = None,
    ):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.cached_content_token_count = cached_content_token_count


class _Part:
    def __init__(self, text: Optional[str] = None, function_call: Any = None):
        self.text = text
        self.function_call = function_call


class _Content:
    def __init__(self, parts: List[_Part]):
        self.parts = parts


class _FinishReason:
    """Mimics Gemini's FinishReason enum (STOP value=1, name='STOP')."""

    def __init__(self, value: int, name: str):
        self._value = value
        self.name = name

    def __int__(self):
        return self._value

    def __bool__(self):
        return True

    def __str__(self):
        return self.name


class _Candidate:
    def __init__(
        self,
        text: Optional[str] = None,
        finish_value: Optional[int] = None,
        finish_name: Optional[str] = None,
        function_call: Any = None,
    ):
        self.content = _Content([_Part(text=text, function_call=function_call)])
        self.finish_reason = (
            _FinishReason(finish_value, finish_name)
            if finish_value is not None
            else None
        )
        self.safety_ratings: List[Any] = []


class _PromptFeedback:
    def __init__(self):
        self.block_reason = None


class _Chunk:
    def __init__(
        self,
        candidates: Optional[List[_Candidate]] = None,
        usage_metadata: Optional[_UsageMetadata] = None,
    ):
        self.candidates = candidates or []
        self.prompt_feedback = _PromptFeedback()
        if usage_metadata is not None:
            self.usage_metadata = usage_metadata


class _AsyncChunkIterator:
    """Async iterator over chunks. Story 24.1 (AC3): the new SDK's
    `send_message_stream(...)` returns an async iterator, not a sync iter.

    Optionally raises an exception after a given chunk index (used by the
    mid-stream-429 test to simulate the prompt-processed-then-429 path).
    """

    def __init__(
        self,
        chunks: List[_Chunk],
        raise_after: Optional[int] = None,
        raise_exc: Optional[Exception] = None,
    ):
        self._chunks = chunks
        self._idx = 0
        self._raise_after = raise_after
        self._raise_exc = raise_exc

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._raise_after is not None and self._idx >= self._raise_after:
            assert self._raise_exc is not None
            raise self._raise_exc
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk


class _FakeAsyncChat:
    """Pretends to be the object returned by `client.aio.chats.create(...)`.

    `send_message_stream` is an async coroutine that returns an async
    iterator. Story 24.1 (AC3): matches the new SDK's surface.
    """

    def __init__(
        self,
        chunks: List[_Chunk],
        raise_after: Optional[int] = None,
        raise_exc: Optional[Exception] = None,
        send_side_effect: Optional[Exception] = None,
    ):
        self._chunks = chunks
        self._raise_after = raise_after
        self._raise_exc = raise_exc
        self._send_side_effect = send_side_effect
        # Capture last call args for assertions.
        self.last_message: Any = None

    async def send_message_stream(self, message=None):
        self.last_message = message
        if self._send_side_effect is not None:
            raise self._send_side_effect
        return _AsyncChunkIterator(
            self._chunks,
            raise_after=self._raise_after,
            raise_exc=self._raise_exc,
        )


def _build_gemini_provider() -> GeminiProvider:
    """Construct a GeminiProvider with the SDK Client mocked away.

    Story 24.1 (AC9): patches `genai.Client` (the singleton constructor)
    rather than module-global `genai.configure` / `genai.GenerativeModel`.
    The full backend test suite must pass with `google-generativeai`
    uninstalled — silent-pass class is closed.
    """
    cfg = {
        "GOOGLE_API_KEY": "test-google-key",
        "GEMINI_MODEL": "gemini-3.1-pro-preview",
        "GEMINI_MAX_OUTPUT_TOKENS": "8192",
        "GEMINI_TEMPERATURE": "1.0",
        "GEMINI_SAFETY_SETTING": "BLOCK_NONE",
        "GEMINI_CONTEXT_CACHE_TTL": "300",
        "GEMINI_MAX_TOOL_ITERATIONS": "5",
    }
    with patch("api.providers.gemini_provider.get_config", return_value=cfg), \
         patch("api.providers.gemini_provider.genai.Client") as mock_client_cls:
        # The Client() instance has `.aio.chats.create(...)` — wire it up
        # so tests can override `provider.client.aio.chats.create` to
        # return their fake chat.
        fake_client = MagicMock()
        fake_client.aio.chats.create = MagicMock()
        mock_client_cls.return_value = fake_client
        provider = GeminiProvider()
    return provider


def _install_fake_chat(provider: GeminiProvider, fake_chat: _FakeAsyncChat) -> None:
    """Wire a fake chat into the provider's SDK client.

    Story 24.1 (AC3): the streaming path calls
    `self.client.aio.chats.create(...)` (synchronous return — async only
    on `send_message_stream`). Use a regular MagicMock with return_value.
    """
    provider.client.aio.chats.create = MagicMock(return_value=fake_chat)


class _FakeTrace:
    """Captures generation creation and end() calls for assertions."""

    def __init__(self):
        self.generations: List["_FakeGeneration"] = []

    def generation(self, **kwargs):
        gen = _FakeGeneration(kwargs)
        self.generations.append(gen)
        return gen


class _FakeGeneration:
    def __init__(self, init_kwargs: Dict[str, Any]):
        self.init_kwargs = init_kwargs
        self.end_kwargs: Optional[Dict[str, Any]] = None
        self.ended = False

    def end(self, **kwargs):
        self.end_kwargs = kwargs
        self.ended = True


# ---------------------------------------------------------------------------
# Gemini provider — AC1, AC2, AC3, AC5, AC6, AC10
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_provider_uses_usage_metadata():
    """AC1: tokens come from final-chunk usage_metadata, not chunk count."""
    provider = _build_gemini_provider()
    chunks = [
        _Chunk(candidates=[_Candidate(text="Hello ")]),
        _Chunk(candidates=[_Candidate(text="world!")]),
        _Chunk(
            candidates=[_Candidate(finish_value=1, finish_name="STOP")],
            usage_metadata=_UsageMetadata(
                prompt_token_count=1234,
                candidates_token_count=567,
            ),
        ),
    ]
    fake_chat = _FakeAsyncChat(chunks)
    _install_fake_chat(provider, fake_chat)
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
        events = []
        async for ev in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            events.append(ev)

    # The streaming path must produce a `done` event.
    assert any(ev.get("type") == "done" for ev in events)

    assert len(fake_trace.generations) == 1
    gen = fake_trace.generations[0]
    assert gen.ended, "generation.end() must fire on the success path"
    assert "usage" in gen.end_kwargs
    assert gen.end_kwargs["usage"]["input"] == 1234
    assert gen.end_kwargs["usage"]["output"] == 567
    # The chunk count was 2 content chunks — explicitly NOT used.
    assert gen.end_kwargs["usage"]["output"] != 2


@pytest.mark.asyncio
async def test_gemini_provider_omits_usage_when_metadata_absent(caplog):
    """AC3: missing usage_metadata → omit usage kwarg + single WARNING."""
    provider = _build_gemini_provider()
    chunks = [
        _Chunk(candidates=[_Candidate(text="Partial answer")]),
        _Chunk(candidates=[_Candidate(finish_value=1, finish_name="STOP")]),
        # NOTE: no usage_metadata on any chunk.
    ]
    _install_fake_chat(provider, _FakeAsyncChat(chunks))
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace), \
         caplog.at_level(logging.WARNING, logger="api.providers.gemini_provider"):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            pass

    assert len(fake_trace.generations) == 1
    gen = fake_trace.generations[0]
    assert gen.ended
    assert "usage" not in gen.end_kwargs, (
        "AC3: end_kwargs must omit `usage` entirely when usage_metadata absent"
    )
    warns = [
        r for r in caplog.records
        if getattr(r, "event", None) == "usage_metadata_missing"
    ]
    assert len(warns) == 1, f"expected exactly one usage_metadata_missing warning, got {len(warns)}"


@pytest.mark.asyncio
async def test_gemini_provider_no_count_tokens_call():
    """AC2: count_tokens() must not be invoked from the streaming path.

    Story 24.1: the new SDK exposes `client.models.count_tokens(...)` (not
    `model.count_tokens(...)`). We sentinel both to enforce.
    """
    provider = _build_gemini_provider()
    # Sentinel both possible call sites: the new SDK's `client.models.count_tokens`
    # AND the legacy `client.aio.models.count_tokens` (in case it exists).
    provider.client.models = MagicMock()
    provider.client.models.count_tokens = MagicMock(
        side_effect=AssertionError(
            "count_tokens() must not be called from the streaming path (Story 23.1 AC2)"
        )
    )
    chunks = [
        _Chunk(candidates=[_Candidate(text="ok")]),
        _Chunk(
            candidates=[_Candidate(finish_value=1, finish_name="STOP")],
            usage_metadata=_UsageMetadata(prompt_token_count=10, candidates_token_count=3),
        ),
    ]
    _install_fake_chat(provider, _FakeAsyncChat(chunks))

    with patch("api.providers.gemini_provider.get_current_trace", return_value=_FakeTrace()):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            pass

    # The mock's side_effect would have raised AssertionError if called.
    provider.client.models.count_tokens.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_error_path_traces_generation():
    """AC5: provider exception still emits a generation with level=ERROR."""
    provider = _build_gemini_provider()

    fake_chat = _FakeAsyncChat(
        chunks=[],
        send_side_effect=Exception("ResourceExhausted: 429 quota exceeded"),
    )
    _install_fake_chat(provider, fake_chat)
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
        with pytest.raises(RateLimitError):
            async for _ in provider.stream_chat_completion(
                messages=[{"role": "user", "content": "hi"}],
                tools=None,
                mcp_client=None,
            ):
                pass

    assert len(fake_trace.generations) >= 1, "AC5: error path must emit a generation"
    err_gens = [g for g in fake_trace.generations if g.end_kwargs and g.end_kwargs.get("level") == "ERROR"]
    assert err_gens, "AC5: at least one generation must end with level=ERROR"
    err = err_gens[0]
    assert "status_message" in err.end_kwargs
    # No usage data was delivered before the failure → must not fabricate.
    assert "usage" not in err.end_kwargs


@pytest.mark.asyncio
async def test_gemini_ended_without_stop_no_false_zero():
    """AC6 regression: 'ended without STOP' path no longer ships in=0/out=chunk_count."""
    provider = _build_gemini_provider()
    # Mimic the Apr-04 shape: the model emits a few content chunks then the
    # stream ends with a non-STOP finish reason.
    chunks = [
        _Chunk(candidates=[_Candidate(text="chunk1")]),
        _Chunk(candidates=[_Candidate(text="chunk2")]),
        # finish_reason MAX_TOKENS (value=2) — non-STOP. NO usage_metadata.
        _Chunk(candidates=[_Candidate(finish_value=2, finish_name="MAX_TOKENS")]),
    ]
    _install_fake_chat(provider, _FakeAsyncChat(chunks))
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            pass

    # The "ended without STOP" path tracks only when token_count > 0.
    # Generations may exist from this branch; check that NONE ship a false-zero
    # cost row (input=0 + output=small chunk count).
    for gen in fake_trace.generations:
        usage = (gen.end_kwargs or {}).get("usage")
        if usage is None:
            continue  # honest "we don't know" — fine
        assert not (usage.get("input") == 0 and 0 < usage.get("output", 0) < 50), (
            "AC6: must not emit false-zero placeholder rows like (in=0, out=<small>)"
        )


@pytest.mark.asyncio
async def test_gemini_mid_stream_429_records_real_prompt_tokens():
    """AC5 / Harpreet handoff #2: mid-stream 429 after prompt processing must
    surface a `level=ERROR` generation with NON-EMPTY usage reflecting the
    real billed prompt_token_count Gemini delivered before the failure.

    Story 24.1: simulates the prompt-processed-then-429 path on the new
    async iter — first chunk carries usage_metadata, then the iterator
    raises a 429-shaped exception.
    """
    provider = _build_gemini_provider()

    # First chunk carries real billed prompt tokens; second chunk raises 429.
    first_chunk = _Chunk(
        candidates=[_Candidate(text=None)],
        usage_metadata=_UsageMetadata(
            prompt_token_count=2500,
            candidates_token_count=0,
        ),
    )

    rate_limit_exc = Exception(
        "ResourceExhausted: 429 Your project has exceeded its monthly "
        "spending cap. Please go to AI Studio at https://ai.studio/spend"
    )
    fake_chat = _FakeAsyncChat(
        chunks=[first_chunk],
        raise_after=1,
        raise_exc=rate_limit_exc,
    )
    _install_fake_chat(provider, fake_chat)
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
        with pytest.raises(RateLimitError):
            async for _ in provider.stream_chat_completion(
                messages=[{"role": "user", "content": "expensive prompt"}],
                tools=None,
                mcp_client=None,
            ):
                pass

    # AC5: an ERROR-level generation must exist.
    err_gens = [
        g for g in fake_trace.generations
        if g.end_kwargs and g.end_kwargs.get("level") == "ERROR"
    ]
    assert err_gens, (
        "Mid-stream 429 must emit a level=ERROR generation. Without this, "
        "the prompt-processed-then-429 burst goes silent in Langfuse — exactly "
        "what triggered the original $88 cost-tracking gap."
    )

    err = err_gens[0]
    assert "usage" in err.end_kwargs, (
        "Mid-stream 429 with usage_metadata MUST record prompt tokens. "
        "Found error generation without `usage` key — real billed work is "
        "missing from Langfuse and reconciliation will under-report again."
    )
    usage = err.end_kwargs["usage"]
    assert usage["input"] == 2500, (
        f"Expected prompt_token_count=2500 (real billed input), got {usage.get('input')}"
    )
    assert usage["output"] == 0, (
        f"Expected candidates_token_count=0 (generation refused), got {usage.get('output')}"
    )
    # Cost must be computed for the input tokens (sanity check on calculate_cost
    # plumbing in _trace_error_generation).
    assert usage.get("input_cost", 0) > 0, (
        "input_cost must be non-zero for 2500 prompt tokens — otherwise the "
        "billing reconciliation script will under-report the 429-burst."
    )


@pytest.mark.asyncio
async def test_gemini_log_spam_regression(caplog):
    """AC10: on 100 happy-path generations the WARNING fires 0 times."""
    happy_count = 100
    fake_trace = _FakeTrace()

    with caplog.at_level(logging.WARNING, logger="api.providers.gemini_provider"):
        for _ in range(happy_count):
            provider = _build_gemini_provider()
            chunks = [
                _Chunk(candidates=[_Candidate(text="ok")]),
                _Chunk(
                    candidates=[_Candidate(finish_value=1, finish_name="STOP")],
                    usage_metadata=_UsageMetadata(prompt_token_count=12, candidates_token_count=3),
                ),
            ]
            _install_fake_chat(provider, _FakeAsyncChat(chunks))
            with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
                async for _ in provider.stream_chat_completion(
                    messages=[{"role": "user", "content": "hi"}],
                    tools=None,
                    mcp_client=None,
                ):
                    pass

    misses = [r for r in caplog.records if getattr(r, "event", None) == "usage_metadata_missing"]
    rate = len(misses) / happy_count
    assert rate < 0.01, f"AC10: usage_metadata_missing rate {rate:.2%} >= 1% on happy path"


# ---------------------------------------------------------------------------
# Story 24.1 — AC15 (cached_tokens plumbing)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_gemini_cached_tokens_plumbed_to_langfuse():
    """AC15: cached_content_token_count surfaces in Langfuse `usage` payload.

    Verifies the implicit-cache hit-rate is observable via traces. When a
    generation has cached tokens, the `usage.input_cached` field is the
    integer count (not None, not zero — the real value).
    """
    provider = _build_gemini_provider()
    chunks = [
        _Chunk(candidates=[_Candidate(text="ok")]),
        _Chunk(
            candidates=[_Candidate(finish_value=1, finish_name="STOP")],
            usage_metadata=_UsageMetadata(
                prompt_token_count=5000,
                candidates_token_count=200,
                cached_content_token_count=4000,  # 80% input cached
            ),
        ),
    ]
    _install_fake_chat(provider, _FakeAsyncChat(chunks))
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            pass

    assert len(fake_trace.generations) == 1
    gen = fake_trace.generations[0]
    assert "usage" in gen.end_kwargs
    usage = gen.end_kwargs["usage"]
    assert usage["input_cached"] == 4000, (
        "AC15: input_cached must reflect cached_content_token_count from usage_metadata"
    )
    # Bug 25.2 (AC1): emission `usage["input"]` is non-cached input
    # (prompt_tokens - cached_tokens), not raw prompt_tokens. Google's
    # prompt_token_count INCLUDES the cached subset, so emitting the full
    # prompt + cached_input separately to Langfuse double-counts the cached
    # portion. Invariant: input + input_cached == prompt_token_count.
    assert usage["input"] == 1000, (
        "Bug 25.2: emission must subtract cached_tokens from prompt_tokens. "
        "Pre-fix this asserted 5000 (raw prompt) which double-counted the "
        "cached subset at full input rate."
    )
    assert usage["input"] + usage["input_cached"] == 5000
    assert usage["output"] == 200
    # cached_cost should be present (the 90% discount lands here).
    assert "cached_cost" in usage


@pytest.mark.asyncio
async def test_gemini_cached_tokens_zero_when_field_none(caplog):
    """AC15: cached=None on chunk → input_cached=0 in trace, no log spam.

    Per Parminder steer: missing/None cached field is "we know it was zero",
    NOT "we don't know" — first-turn / non-3.x models legitimately have
    no cache hit.
    """
    provider = _build_gemini_provider()
    chunks = [
        _Chunk(candidates=[_Candidate(text="ok")]),
        _Chunk(
            candidates=[_Candidate(finish_value=1, finish_name="STOP")],
            usage_metadata=_UsageMetadata(
                prompt_token_count=1000,
                candidates_token_count=500,
                cached_content_token_count=None,  # first turn
            ),
        ),
    ]
    _install_fake_chat(provider, _FakeAsyncChat(chunks))
    fake_trace = _FakeTrace()

    with patch("api.providers.gemini_provider.get_current_trace", return_value=fake_trace):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            pass

    gen = fake_trace.generations[0]
    usage = gen.end_kwargs["usage"]
    assert usage["input_cached"] == 0
    # A `usage_metadata_missing` warning would mean we treated cache=None as
    # the whole-metadata-missing case — wrong. Verify NO such warning.
    misses = [r for r in caplog.records if getattr(r, "event", None) == "usage_metadata_missing"]
    assert len(misses) == 0


# ---------------------------------------------------------------------------
# ChatGPT provider — AC4, AC5
# ---------------------------------------------------------------------------


def _build_chatgpt_provider() -> ChatGPTProvider:
    cfg = {
        "OPENAI_API_KEY": "test-openai-key",
        "LLM_REQUEST_TIMEOUT": "30.0",
        "LLM_STREAMING_TIMEOUT": "30.0",
    }
    with patch("api.providers.chatgpt_provider.get_config", return_value=cfg):
        return ChatGPTProvider()


class _FakeStreamResponse:
    """Mimics the streaming response from `httpx.AsyncClient.stream(...)`."""

    def __init__(self, lines: List[str], status_code: int = 200, headers: Optional[Dict[str, str]] = None):
        self.status_code = status_code
        self.headers = headers or {}
        self._lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aread(self):
        return b""


def _ssE(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload)}"


class _CapturedRequest:
    """Captures the JSON payload sent on the stream call."""

    def __init__(self):
        self.payload: Optional[Dict[str, Any]] = None


def _make_fake_client(lines: List[str], captured: _CapturedRequest, status_code: int = 200):
    fake_client = MagicMock()

    def _stream(method, url, headers=None, json=None, timeout=None):
        captured.payload = json
        return _FakeStreamResponse(lines, status_code=status_code)

    fake_client.stream = _stream
    fake_client.aclose = MagicMock()
    return fake_client


@pytest.mark.asyncio
async def test_chatgpt_provider_uses_stream_options_usage():
    """AC4: the streaming request must set stream_options.include_usage=true."""
    provider = _build_chatgpt_provider()
    captured = _CapturedRequest()
    final_chunk = {
        "choices": [{"delta": {}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
    }
    lines = [
        _ssE({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}),
        _ssE(final_chunk),
        "data: [DONE]",
    ]
    provider.client = _make_fake_client(lines, captured)
    fake_trace = _FakeTrace()

    with patch("api.providers.chatgpt_provider.get_current_trace", return_value=fake_trace):
        async for _ in provider._stream_single_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
            user_id="u",
        ):
            pass

    assert captured.payload is not None
    assert captured.payload.get("stream_options", {}).get("include_usage") is True

    assert len(fake_trace.generations) == 1
    gen = fake_trace.generations[0]
    assert gen.end_kwargs["usage"]["input"] == 1000
    assert gen.end_kwargs["usage"]["output"] == 500


@pytest.mark.asyncio
async def test_chatgpt_provider_omits_usage_when_block_absent(caplog):
    """AC4 fallback: missing usage block → omit usage + single WARNING."""
    provider = _build_chatgpt_provider()
    captured = _CapturedRequest()
    # Final chunk has no `usage` field at all.
    final_chunk = {"choices": [{"delta": {}, "finish_reason": "stop"}]}
    lines = [
        _ssE({"choices": [{"delta": {"content": "hi"}, "finish_reason": None}]}),
        _ssE(final_chunk),
        "data: [DONE]",
    ]
    provider.client = _make_fake_client(lines, captured)
    fake_trace = _FakeTrace()

    with patch("api.providers.chatgpt_provider.get_current_trace", return_value=fake_trace), \
         caplog.at_level(logging.WARNING, logger="api.providers.chatgpt_provider"):
        async for _ in provider._stream_single_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
            user_id="u",
        ):
            pass

    assert len(fake_trace.generations) == 1
    gen = fake_trace.generations[0]
    assert "usage" not in gen.end_kwargs
    warns = [r for r in caplog.records if getattr(r, "event", None) == "usage_metadata_missing"]
    assert len(warns) == 1


@pytest.mark.asyncio
async def test_chatgpt_error_path_traces_generation():
    """AC5: ChatGPT timeout still emits a generation with level=ERROR."""
    provider = _build_chatgpt_provider()
    fake_client = MagicMock()

    def _stream(*args, **kwargs):
        raise httpx.TimeoutException("timeout")

    fake_client.stream = _stream
    fake_client.aclose = MagicMock()
    provider.client = fake_client
    fake_trace = _FakeTrace()

    with patch("api.providers.chatgpt_provider.get_current_trace", return_value=fake_trace):
        with pytest.raises(Exception):
            async for _ in provider._stream_single_completion(
                messages=[{"role": "user", "content": "hi"}],
                tools=None,
                mcp_client=None,
                user_id="u",
            ):
                pass

    err_gens = [g for g in fake_trace.generations if g.end_kwargs and g.end_kwargs.get("level") == "ERROR"]
    assert err_gens, "AC5: ChatGPT error path must emit a level=ERROR generation"


# ---------------------------------------------------------------------------
# Cost reconciliation script — smoke test for AC7
# ---------------------------------------------------------------------------


def test_cost_reconciliation_script(tmp_path, monkeypatch):
    """AC7 smoke: --dry-run produces a markdown report with the expected columns."""
    import importlib.util
    import os

    # Load the script as a module (it's outside the importable package tree).
    candidates = [
        "/app/scripts/cost_reconciliation.py",
        os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "cost_reconciliation.py")
        ),
    ]
    script_path = next((c for c in candidates if os.path.exists(c)), None)
    if script_path is None:
        pytest.skip(
            "scripts/cost_reconciliation.py not visible to the test environment "
            "(not mounted in backend container; run on host or mount scripts/)."
        )
    spec = importlib.util.spec_from_file_location("cost_reconciliation", script_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[union-attr]

    out_path = tmp_path / "report.md"
    monkeypatch.setattr(
        "sys.argv",
        ["cost_reconciliation.py", "--dry-run", "--output", str(out_path)],
    )
    rc = module.main()
    assert rc == 0
    content = out_path.read_text()
    # Header, table columns, totals, diagnostics
    assert "# Cost Reconciliation:" in content
    assert "| date | calls | input_tokens | output_tokens | recorded_cost | google_billed |" in content
    assert "**TOTAL**" in content
    assert "## Diagnostics" in content
    # The synthetic data includes one error generation; should be reflected.
    assert re.search(r"level=ERROR.*\*\*1\*\*", content) or "**1**" in content
