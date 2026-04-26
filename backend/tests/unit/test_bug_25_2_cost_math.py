"""
Bug 25.2 — Gemini cost-math fix: cached tokens are a SUBSET of prompt tokens.

Pre-fix: Annie emitted `usage["input"] = prompt_tokens` AND
`usage["cached_input"] = cached_tokens` to Langfuse, which then billed the
cached subset at the full input rate ($2/M) on top of the cached rate
($0.20/M) — a 5.5x cost overstatement on cache-hit traces.

Post-fix: Annie emits `usage["input"] = max(0, prompt_tokens - cached_tokens)`
and `usage["cached_input"] = cached_tokens`, satisfying the invariant
`input + cached_input == prompt_tokens` for every emission.

Concrete regression fixture (trace `1cd04de7`, recorded in the bug spec):
- prompt=22463, cached=20270, output=41
- Pre-fix Annie booked: $0.049472
- Post-fix Annie books: $0.008932 (matches Google's actual bill)
- Invariant: 2193 (non_cached) + 20270 (cached) == 22463 (prompt) ✓

These tests are mock-only — no live Gemini API calls. The fix is in
emission shape, not call behavior; existing Langfuse traces + this
invariant test suite fully cover the change.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.providers.gemini_provider import GeminiProvider


# ---------------------------------------------------------------------------
# Local test doubles (mirrors `test_story_24_1_genai_migration.py` style)
# ---------------------------------------------------------------------------


class _UsageMetadata:
    def __init__(
        self,
        prompt_token_count: Optional[int] = None,
        candidates_token_count: Optional[int] = None,
        cached_content_token_count: Optional[int] = None,
    ):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.cached_content_token_count = cached_content_token_count


class _FinishReason:
    def __init__(self, value: int, name: str):
        self._value = value
        self.name = name

    def __int__(self):
        return self._value

    def __bool__(self):
        return True

    def __str__(self):
        return self.name


class _Part:
    def __init__(
        self,
        text: Optional[str] = None,
        function_call: Any = None,
        thought_signature: Optional[bytes] = None,
    ):
        self.text = text
        self.function_call = function_call
        self.thought_signature = thought_signature


class _Content:
    def __init__(self, parts: List[_Part]):
        self.parts = parts


class _Candidate:
    def __init__(
        self,
        text: Optional[str] = None,
        finish_value: Optional[int] = None,
        finish_name: Optional[str] = None,
    ):
        self.content = _Content([_Part(text=text)])
        self.finish_reason = (
            _FinishReason(finish_value, finish_name)
            if finish_value is not None
            else None
        )
        self.safety_ratings: List[Any] = []


class _Chunk:
    def __init__(
        self,
        candidates: Optional[List[_Candidate]] = None,
        usage_metadata: Optional[_UsageMetadata] = None,
    ):
        self.candidates = candidates or []
        self.prompt_feedback = MagicMock()
        self.prompt_feedback.block_reason = None
        if usage_metadata is not None:
            self.usage_metadata = usage_metadata


class _AsyncChunkIter:
    def __init__(self, chunks: List[_Chunk]):
        self._chunks = chunks
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        c = self._chunks[self._idx]
        self._idx += 1
        return c


def _build_provider() -> GeminiProvider:
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
        fake_client = MagicMock()
        fake_client.aio.chats.create = MagicMock()
        mock_client_cls.return_value = fake_client
        return GeminiProvider()


def _build_trace_capturing_generation_end():
    """Build a fake Langfuse trace whose `generation()` returns a mock that
    captures the `end(**kwargs)` payload. Returns (trace, end_kwargs_holder).
    """
    end_kwargs_holder: Dict[str, Any] = {}
    fake_generation = MagicMock()

    def _capture_end(**kwargs):
        end_kwargs_holder.update(kwargs)
        return None

    fake_generation.end = MagicMock(side_effect=_capture_end)
    fake_trace = MagicMock()
    fake_trace.generation = MagicMock(return_value=fake_generation)
    return fake_trace, end_kwargs_holder


# ---------------------------------------------------------------------------
# AC3.a — helper-level invariant
# ---------------------------------------------------------------------------


class TestExtractUsageMetadataNonCachedInput:
    """Bug 25.2 (AC1, AC3): the helper computes non_cached_input_tokens.

    Concrete regression fixture: trace `1cd04de7`
    (prompt=22463, output=41, cached=20270 → non_cached=2193).
    """

    def test_extract_usage_metadata_subtracts_cached_from_input(self):
        """Helper returns non_cached = prompt - cached and the invariant holds."""
        chunk = _Chunk(
            usage_metadata=_UsageMetadata(
                prompt_token_count=22463,
                candidates_token_count=41,
                cached_content_token_count=20270,
            )
        )
        result = GeminiProvider._extract_usage_metadata(chunk)
        assert result is not None
        # The fix: non_cached_input_tokens carries the post-subtraction value.
        assert result["non_cached_input_tokens"] == 2193
        # The raw fields are preserved for cost-calc plumbing.
        assert result["prompt_tokens"] == 22463
        assert result["cached_tokens"] == 20270
        assert result["completion_tokens"] == 41
        # The load-bearing invariant: non_cached + cached == prompt.
        assert (
            result["non_cached_input_tokens"] + result["cached_tokens"]
            == result["prompt_tokens"]
        )

    def test_first_turn_no_cache_unchanged(self):
        """cached=0 → non_cached_input == prompt (no behavioral change)."""
        chunk = _Chunk(
            usage_metadata=_UsageMetadata(
                prompt_token_count=1000,
                candidates_token_count=200,
                cached_content_token_count=0,
            )
        )
        result = GeminiProvider._extract_usage_metadata(chunk)
        assert result is not None
        assert result["non_cached_input_tokens"] == 1000
        assert result["cached_tokens"] == 0
        # Invariant still holds trivially.
        assert (
            result["non_cached_input_tokens"] + result["cached_tokens"]
            == result["prompt_tokens"]
        )

    def test_cached_exceeds_prompt_clamped_with_warning(self, caplog):
        """AC8: defensive guard. If cached > prompt (Google contract violation
        / SDK math glitch), clamp non_cached to 0 and emit a structured
        WARNING with `event=cached_token_count_anomaly`.
        """
        chunk = _Chunk(
            usage_metadata=_UsageMetadata(
                prompt_token_count=10,
                candidates_token_count=5,
                cached_content_token_count=20,
            )
        )
        with caplog.at_level(logging.WARNING, logger="api.providers.gemini_provider"):
            result = GeminiProvider._extract_usage_metadata(chunk)

        assert result is not None
        # Clamp: never emit a negative input.
        assert result["non_cached_input_tokens"] == 0
        assert result["prompt_tokens"] == 10
        assert result["cached_tokens"] == 20

        # Verify a structured WARNING fired with the anomaly event tag.
        anomaly_records = [
            r for r in caplog.records
            if getattr(r, "event", None) == "cached_token_count_anomaly"
        ]
        assert len(anomaly_records) == 1, (
            f"Expected exactly one anomaly WARNING, got {len(anomaly_records)} "
            f"(records: {[r.message for r in caplog.records]})"
        )
        rec = anomaly_records[0]
        assert rec.levelno == logging.WARNING
        assert rec.prompt_tokens == 10
        assert rec.cached_tokens == 20

    def test_cached_field_missing_falls_back_to_prompt(self):
        """When cached_content_token_count is missing entirely, cached
        defaults to 0 and non_cached_input falls back to prompt (no-op).
        Locks the existing 24.1 default behavior.
        """
        # Use spec to ensure the field is genuinely absent (not Mock-fabricated).
        chunk = MagicMock(spec=["usage_metadata"])
        chunk.usage_metadata = MagicMock(
            spec=["prompt_token_count", "candidates_token_count"]
        )
        chunk.usage_metadata.prompt_token_count = 1000
        chunk.usage_metadata.candidates_token_count = 200
        result = GeminiProvider._extract_usage_metadata(chunk)
        assert result is not None
        assert result["cached_tokens"] == 0
        assert result["non_cached_input_tokens"] == 1000


# ---------------------------------------------------------------------------
# AC3.b — emission-site invariant via end-to-end streaming flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_emission_uses_non_cached_input_on_success_path():
    """Bug 25.2 (AC1, AC3): success-path emission (gemini_provider.py:~1044).

    Arms the streaming flow with the regression fixture (trace 1cd04de7
    shape: prompt=22463, cached=20270, output=41) and asserts the
    Langfuse `generation.end(usage=...)` payload satisfies:
    - usage["input"] == 2193  (NOT 22463 — the bug shape)
    - usage["cached_input"] == 20270
    - usage["output"] == 41
    - usage["input"] + usage["cached_input"] == 22463  (the load-bearing invariant)
    """
    provider = _build_provider()

    stop_chunk = _Chunk(
        candidates=[_Candidate(text="Done.", finish_value=1, finish_name="STOP")],
        usage_metadata=_UsageMetadata(
            prompt_token_count=22463,
            candidates_token_count=41,
            cached_content_token_count=20270,
        ),
    )

    fake_chat = MagicMock()
    fake_chat.send_message_stream = AsyncMock(return_value=_AsyncChunkIter([stop_chunk]))
    provider.client.aio.chats.create = MagicMock(return_value=fake_chat)

    fake_trace, end_kwargs = _build_trace_capturing_generation_end()

    with patch(
        "api.providers.gemini_provider.get_current_trace",
        return_value=fake_trace,
    ):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hello"}],
        ):
            pass

    # The Langfuse generation.end() must have been called with a usage block.
    assert "usage" in end_kwargs, (
        "generation.end() was called without a usage block — emission shape "
        "regression. Captured end_kwargs: " + repr(end_kwargs)
    )
    usage = end_kwargs["usage"]

    # Bug 25.2 invariant: input is non-cached input, cached_input is the cached
    # subset, and the two sum to the full prompt token count.
    assert usage["input"] == 2193, (
        f"Bug 25.2: emission still uses raw prompt_tokens. Expected "
        f"non_cached_input=2193, got {usage['input']}. Cached portion is "
        f"being double-billed at full input rate."
    )
    assert usage["input_cached"] == 20270
    assert usage["output"] == 41
    assert usage["input"] + usage["input_cached"] == 22463


@pytest.mark.asyncio
async def test_emission_first_turn_no_cache_unchanged():
    """AC6: no-cache regression guard. cached=0 turns must continue to emit
    `usage["input"] == prompt_tokens` (no behavioral change).
    """
    provider = _build_provider()

    stop_chunk = _Chunk(
        candidates=[_Candidate(text="Hi.", finish_value=1, finish_name="STOP")],
        usage_metadata=_UsageMetadata(
            prompt_token_count=1000,
            candidates_token_count=50,
            cached_content_token_count=0,
        ),
    )
    fake_chat = MagicMock()
    fake_chat.send_message_stream = AsyncMock(return_value=_AsyncChunkIter([stop_chunk]))
    provider.client.aio.chats.create = MagicMock(return_value=fake_chat)

    fake_trace, end_kwargs = _build_trace_capturing_generation_end()
    with patch(
        "api.providers.gemini_provider.get_current_trace",
        return_value=fake_trace,
    ):
        async for _ in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
        ):
            pass

    usage = end_kwargs.get("usage", {})
    assert usage.get("input") == 1000
    assert usage.get("input_cached") == 0
    # Invariant: no-cache turn satisfies sum trivially.
    assert usage.get("input", 0) + usage.get("input_cached", 0) == 1000


# ---------------------------------------------------------------------------
# AC3.c — error-path emission invariant (`_trace_error_generation`)
# ---------------------------------------------------------------------------


def test_error_path_emission_uses_non_cached_input():
    """Bug 25.2 (AC1, AC3): the `_trace_error_generation` helper
    (gemini_provider.py:~486) emits `usage["input"]` as non-cached input
    when `last_usage` carries cached tokens.

    Covers the prompt-processed-then-429 path where Gemini bills the
    cached portion before the rate-limit error fires.
    """
    provider = _build_provider()
    fake_trace, end_kwargs = _build_trace_capturing_generation_end()

    # Simulate: prompt processed (cached partial), then the SDK raised.
    last_usage = {
        "prompt_tokens": 22463,
        "completion_tokens": 41,
        "cached_tokens": 20270,
        "non_cached_input_tokens": 2193,
    }

    provider._trace_error_generation(
        trace=fake_trace,
        error=RuntimeError("simulated rate-limit"),
        duration_ms=123,
        last_usage=last_usage,
        tool_iteration=0,
    )

    assert "usage" in end_kwargs, (
        "_trace_error_generation did not emit a usage block. Captured: "
        + repr(end_kwargs)
    )
    usage = end_kwargs["usage"]
    assert usage["input"] == 2193
    assert usage["input_cached"] == 20270
    assert usage["output"] == 41
    assert usage["input"] + usage["input_cached"] == 22463


def test_error_path_falls_back_when_helper_key_missing():
    """Backwards-compat: if `last_usage` is built from an older shape that
    lacks `non_cached_input_tokens`, the error path computes the safe value
    locally rather than emitting raw prompt_tokens (the bug shape).
    """
    provider = _build_provider()
    fake_trace, end_kwargs = _build_trace_capturing_generation_end()

    # Older-shape last_usage missing the new key.
    last_usage = {
        "prompt_tokens": 1500,
        "completion_tokens": 30,
        "cached_tokens": 500,
        # no `non_cached_input_tokens`
    }

    provider._trace_error_generation(
        trace=fake_trace,
        error=RuntimeError("simulated"),
        duration_ms=100,
        last_usage=last_usage,
        tool_iteration=0,
    )

    usage = end_kwargs.get("usage", {})
    # 1500 - 500 = 1000 (computed locally)
    assert usage["input"] == 1000
    assert usage["input_cached"] == 500
    assert usage["input"] + usage["input_cached"] == 1500
