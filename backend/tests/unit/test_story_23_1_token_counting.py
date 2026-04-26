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
    """Mimics the SDK's usage_metadata object on a Gemini stream chunk."""

    def __init__(self, prompt_token_count: Optional[int], candidates_token_count: Optional[int]):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count


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


def _build_gemini_provider() -> GeminiProvider:
    """Construct a GeminiProvider with all SDK side effects mocked away."""
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
         patch("api.providers.gemini_provider.genai.configure"), \
         patch("api.providers.gemini_provider.genai.GenerativeModel"):
        provider = GeminiProvider()
    # Ensure a sentinel: count_tokens MUST NOT be called by the streaming path.
    provider.model.count_tokens = MagicMock(
        side_effect=AssertionError(
            "count_tokens() must not be called from the streaming path (Story 23.1 AC2)"
        )
    )
    return provider


class _FakeChat:
    """Pretends to be the object returned by `model.start_chat()`."""

    def __init__(self, chunks: List[_Chunk]):
        self._chunks = chunks

    def send_message(self, last_user_message, stream=True, tools=None):
        # Return a generator-like iterable. The provider iterates it directly.
        return iter(self._chunks)


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
            usage_metadata=_UsageMetadata(prompt_token_count=1234, candidates_token_count=567),
        ),
    ]
    fake_chat = _FakeChat(chunks)
    provider.model.start_chat = MagicMock(return_value=fake_chat)
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
    provider.model.start_chat = MagicMock(return_value=_FakeChat(chunks))
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
    """AC2: count_tokens() must not be invoked from the streaming path."""
    provider = _build_gemini_provider()
    chunks = [
        _Chunk(candidates=[_Candidate(text="ok")]),
        _Chunk(
            candidates=[_Candidate(finish_value=1, finish_name="STOP")],
            usage_metadata=_UsageMetadata(prompt_token_count=10, candidates_token_count=3),
        ),
    ]
    provider.model.start_chat = MagicMock(return_value=_FakeChat(chunks))

    with patch("api.providers.gemini_provider.get_current_trace", return_value=_FakeTrace()):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            mcp_client=None,
        ):
            pass

    # The mock's side_effect would have raised AssertionError if called.
    provider.model.count_tokens.assert_not_called()


@pytest.mark.asyncio
async def test_gemini_error_path_traces_generation():
    """AC5: provider exception still emits a generation with level=ERROR."""
    provider = _build_gemini_provider()

    def _explode(*args, **kwargs):
        raise Exception("ResourceExhausted: 429 quota exceeded")

    fake_chat = MagicMock()
    fake_chat.send_message = _explode
    provider.model.start_chat = MagicMock(return_value=fake_chat)
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
    # stream ends with a non-STOP finish reason. Pre-23.1 this path called
    # `count_tokens()`; if the call failed, it shipped (in=0, out=chunk_count).
    chunks = [
        _Chunk(candidates=[_Candidate(text="chunk1")]),
        _Chunk(candidates=[_Candidate(text="chunk2")]),
        # finish_reason MAX_TOKENS (value=2) — non-STOP. NO usage_metadata.
        _Chunk(candidates=[_Candidate(finish_value=2, finish_name="MAX_TOKENS")]),
    ]
    provider.model.start_chat = MagicMock(return_value=_FakeChat(chunks))
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
    # The mock's side_effect would have asserted if count_tokens were called.
    provider.model.count_tokens.assert_not_called()


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
            provider.model.start_chat = MagicMock(return_value=_FakeChat(chunks))
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
    # The backend test container mounts only `backend/` at /app, so the
    # script lives outside the container's filesystem when tests run there.
    # The fallback path is repo-relative and works in both environments
    # when scripts/ is mounted; otherwise we skip with a clear message.
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
