"""
Regression tests for Bug — Gemini multimodal `send_message_stream` shape.

Production symptom (gemini-3.1-pro-preview):
    Streaming error: Message must be a valid part type ... got <class 'list'>

Root cause:
    `chat.send_message_stream(message=...)` in the google.genai SDK validates
    each list element against `Union[str, File, FileDict, Part, PartDict]`.
    The provider was passing list[dict] PartDicts (text + inline_data) — the
    SDK accepts PartDicts in some entrypoints but rejects them on this path
    in the multimodal branch, raising the "got <class 'list'>" error.

Fix:
    `_part_dict_to_part()` helper at module top of gemini_provider.py
    builds native types.Part objects:
      - text dict → Part(text=...)
      - inline_data dict → Part(inlineData=Blob(mimeType=..., data=<bytes>))
    `Blob.data` is bytes, so the base64 string is base64-decoded first.

These tests fail on the pre-fix code (raw list[dict] passed through) and
pass on the post-fix code (list[types.Part] passed through).
"""

import base64
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from google.genai import types as genai_types

from api.providers.gemini_provider import (
    GeminiProvider,
    _part_dict_to_part,
)


# ---------------------------------------------------------------------------
# Test doubles for the new SDK surface (mirrors test_story_24_1)
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
        function_call: Any = None,
        finish_value: Optional[int] = None,
        finish_name: Optional[str] = None,
    ):
        self.content = _Content([_Part(text=text, function_call=function_call)])
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


class _FakeAttachment:
    """Minimal stand-in for FileAttachment — only the fields the provider reads."""

    def __init__(self, mime_type: str, data_base64: str, size_bytes: int = 100):
        self.mime_type = mime_type
        self.data_base64 = data_base64
        self.size_bytes = size_bytes
        self.filename = "test.png"


# ---------------------------------------------------------------------------
# Unit tests — _part_dict_to_part
# ---------------------------------------------------------------------------


def test_part_dict_to_part_text():
    """Text PartDict → types.Part(text=...)."""
    part = _part_dict_to_part({"text": "hello world"})
    assert isinstance(part, genai_types.Part)
    assert part.text == "hello world"
    # No inline_data on a text part
    assert getattr(part, "inline_data", None) is None


def test_part_dict_to_part_inline_data_decodes_base64_to_bytes():
    """inline_data PartDict with base64 string → Part(inlineData=Blob) with raw bytes.

    This is the load-bearing assertion: Blob.data is `bytes` in the SDK,
    so the base64 string from FileAttachment.data_base64 MUST be decoded.
    Pre-fix path (passing the raw dict through) would have left data as a
    base64 string, which is exactly what the SDK rejected.
    """
    raw_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # 24 bytes of fake PNG
    b64 = base64.b64encode(raw_bytes).decode()

    part = _part_dict_to_part({
        "inline_data": {"mime_type": "image/png", "data": b64}
    })

    assert isinstance(part, genai_types.Part)
    # Pydantic model — the field is `inline_data` (snake-case alias).
    assert part.inline_data is not None
    assert part.inline_data.mime_type == "image/png"
    # CRITICAL: bytes, not the base64 string. Pre-fix code carried the
    # base64 string through; the SDK validator coerced/blew up on it.
    assert isinstance(part.inline_data.data, bytes)
    assert part.inline_data.data == raw_bytes
    # And specifically NOT the b64 string.
    assert part.inline_data.data != b64.encode()


def test_part_dict_to_part_inline_data_passthrough_when_already_bytes():
    """If `data` is already bytes, no decode (defensive — caller may pre-decode)."""
    raw = b"already-bytes"
    part = _part_dict_to_part({
        "inline_data": {"mime_type": "image/png", "data": raw}
    })
    assert part.inline_data.data == raw


def test_part_dict_to_part_unrecognized_shape_raises():
    """Unknown keys raise ValueError — better fail-fast than silent miscompile."""
    with pytest.raises(ValueError):
        _part_dict_to_part({"video_data": {"url": "..."}})


# ---------------------------------------------------------------------------
# Integration test — multimodal branch in stream_chat_completion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multimodal_branch_passes_list_of_part_objects_not_dicts():
    """The multimodal branch must call send_message_stream with list[types.Part],
    NOT list[dict]. Pre-fix code passed list[dict] and the SDK raised
    "Message must be a valid part type ... got <class 'list'>".

    Verified by:
      1. Mocking client.aio.chats.create → fake_chat
      2. Mocking fake_chat.send_message_stream as an AsyncMock
      3. Driving stream_chat_completion with one user message + one image file
      4. Inspecting the captured `message=` kwarg on send_message_stream
    """
    provider = _build_provider()

    # Prepare a STOP chunk so the loop completes after one iteration.
    stop_chunk = _Chunk(
        candidates=[_Candidate(
            text="ok",
            finish_value=1,
            finish_name="STOP",
        )],
        usage_metadata=_UsageMetadata(
            prompt_token_count=10,
            candidates_token_count=1,
            cached_content_token_count=0,
        ),
    )

    fake_chat = MagicMock()
    # AsyncMock returns the iter on each await — one call here.
    fake_chat.send_message_stream = AsyncMock(
        return_value=_AsyncChunkIter([stop_chunk])
    )
    provider.client.aio.chats.create = MagicMock(return_value=fake_chat)

    # Build a real FileAttachment-shaped object (mime + base64 string).
    raw_bytes = b"\x89PNG\r\n\x1a\n" + b"\x42" * 32
    b64 = base64.b64encode(raw_bytes).decode()
    file = _FakeAttachment(mime_type="image/png", data_base64=b64)

    # Drain the stream.
    events = []
    with patch("api.providers.gemini_provider.get_current_trace", return_value=None):
        async for ev in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "what's in this image?"}],
            tools=None,
            files=[file],
        ):
            events.append(ev)

    # The provider must have called send_message_stream exactly once.
    assert fake_chat.send_message_stream.await_count == 1
    call = fake_chat.send_message_stream.await_args
    msg_arg = call.kwargs.get("message")

    # Assertion 1: it's a list (multimodal branch).
    assert isinstance(msg_arg, list), (
        f"multimodal branch must pass list, got {type(msg_arg).__name__}"
    )
    # Assertion 2: every element is a real types.Part — NOT a dict.
    # Pre-fix code passed list[dict] which is exactly what the SDK rejected.
    assert all(isinstance(p, genai_types.Part) for p in msg_arg), (
        f"every element must be types.Part; got types: "
        f"{[type(p).__name__ for p in msg_arg]}"
    )
    # Assertion 3: the inline_data Part carries bytes (not the b64 string).
    image_parts = [p for p in msg_arg if p.inline_data is not None]
    assert len(image_parts) == 1
    assert isinstance(image_parts[0].inline_data.data, bytes)
    assert image_parts[0].inline_data.data == raw_bytes
    assert image_parts[0].inline_data.mime_type == "image/png"

    # Assertion 4: the text Part survived alongside the image.
    text_parts = [p for p in msg_arg if p.text is not None]
    assert len(text_parts) == 1
    assert text_parts[0].text == "what's in this image?"

    # And the stream completed cleanly (no error event emitted).
    error_events = [e for e in events if e.get("type") == "error"]
    assert not error_events, f"unexpected error events: {error_events}"
    done_events = [e for e in events if e.get("type") == "done"]
    assert len(done_events) == 1


@pytest.mark.asyncio
async def test_text_only_branch_unchanged_passes_string():
    """Sanity check: the text-only branch is NOT affected by the fix.
    It still passes a plain string to send_message_stream.
    """
    provider = _build_provider()

    stop_chunk = _Chunk(
        candidates=[_Candidate(
            text="ok",
            finish_value=1,
            finish_name="STOP",
        )],
        usage_metadata=_UsageMetadata(
            prompt_token_count=5,
            candidates_token_count=1,
            cached_content_token_count=0,
        ),
    )

    fake_chat = MagicMock()
    fake_chat.send_message_stream = AsyncMock(
        return_value=_AsyncChunkIter([stop_chunk])
    )
    provider.client.aio.chats.create = MagicMock(return_value=fake_chat)

    events = []
    with patch("api.providers.gemini_provider.get_current_trace", return_value=None):
        async for ev in provider.stream_chat_completion(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            # no files=
        ):
            events.append(ev)

    call = fake_chat.send_message_stream.await_args
    msg_arg = call.kwargs.get("message")
    assert isinstance(msg_arg, str)
    assert msg_arg == "hi"
