"""
Streaming behavior tests for sanitize_telegram_html().

The Telegram bot edits a message after each streamed LLM chunk. At any moment
the buffer may contain a partially-formed HTML structure (e.g. "<i>text" with
no closing tag yet, or even "<" / "<b" mid-tag). Each intermediate state must
sanitize to valid Telegram HTML or Telegram returns 400.

These tests simulate streaming by progressively building up text and asserting
each intermediate state is valid.
"""

from __future__ import annotations

import random
import re

import pytest

from handlers.message import (
    _open_tags_at_end,
    sanitize_telegram_html,
)


# ============================================================================
# Helpers
# ============================================================================

def stream_chunks(full_text: str, chunk_sizes: list[int] | None = None) -> list[str]:
    """Simulate streaming by yielding progressive prefixes of full_text.

    Each prefix is what the buffer would contain at a given point in time.

    Args:
        full_text: The complete final text the LLM will produce.
        chunk_sizes: Optional list of chunk sizes. If None, defaults to
            character-by-character (chunk_size=1). If the sizes don't sum to
            len(full_text), the last chunk just consumes whatever remains.

    Returns:
        A list of progressively longer prefixes ending with full_text itself.
    """
    if chunk_sizes is None:
        return [full_text[: i + 1] for i in range(len(full_text))]

    prefixes: list[str] = []
    pos = 0
    for size in chunk_sizes:
        if pos >= len(full_text):
            break
        pos = min(pos + size, len(full_text))
        prefixes.append(full_text[:pos])
    if not prefixes or prefixes[-1] != full_text:
        prefixes.append(full_text)
    return prefixes


# Match real (unescaped) tags inside sanitized output
_REAL_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>")


def _strip_real_tags(html_text: str) -> str:
    """Remove all real Telegram tags so we can inspect the body text."""
    return _REAL_TAG.sub("", html_text)


def assert_telegram_safe(html_text: str) -> None:
    """Assert that a sanitized string is safe to send to Telegram.

    Checks:
    - sanitize_telegram_html() returned a value (not None)
    - All open tags are balanced (stack is empty after walking)
    - No literal '\\$' (backslash-dollar) appears anywhere
    - No naked '<', '>', or unescaped '&' remains in the body text after
      stripping real tags. Body text must contain only escaped entities
      like &lt; &gt; &amp;.
    """
    assert html_text is not None, "sanitize_telegram_html returned None"

    # Tag balance: walking the result should leave the stack empty
    stack = _open_tags_at_end(html_text)
    assert stack == [], (
        f"Unbalanced tags after sanitize: stack={stack!r}, html={html_text!r}"
    )

    # No backslash-escaped dollar (Markdown habit must not leak in)
    assert "\\$" not in html_text, f"Found literal \\$ in output: {html_text!r}"

    # Strip all real tags, then check what's left for naked specials
    body = _strip_real_tags(html_text)

    assert "<" not in body, f"Naked '<' in body of {html_text!r} (body={body!r})"
    assert ">" not in body, f"Naked '>' in body of {html_text!r} (body={body!r})"

    # '&' is allowed only as part of an entity reference (&amp; &lt; &gt; &quot; &#x27; etc.)
    # Anything else is an unescaped ampersand.
    for m in re.finditer(r"&", body):
        rest = body[m.start() : m.start() + 8]
        if not re.match(r"&(?:amp|lt|gt|quot|apos|#x?[0-9a-fA-F]+);", rest):
            raise AssertionError(
                f"Unescaped '&' in body of {html_text!r} at {rest!r}"
            )


def assert_stream_safe(full_text: str, chunk_sizes: list[int] | None = None) -> None:
    """Run sanitize on every prefix of full_text and assert each is safe."""
    for prefix in stream_chunks(full_text, chunk_sizes):
        sanitized = sanitize_telegram_html(prefix)
        try:
            assert_telegram_safe(sanitized)
        except AssertionError as e:
            raise AssertionError(
                f"Streaming bug found.\n"
                f"  Input prefix: {prefix!r}\n"
                f"  Sanitized:    {sanitized!r}\n"
                f"  Reason:       {e}"
            ) from e


# ============================================================================
# 1. Token-by-token streaming
# ============================================================================

def test_token_by_token_simple_bold():
    assert_stream_safe("<b>hello world</b>")


def test_token_by_token_italic():
    assert_stream_safe("<i>some text</i>")


def test_token_by_token_plain_text():
    assert_stream_safe("Hello, world! How are you today?")


def test_token_by_token_with_dollar():
    assert_stream_safe("Your portfolio is worth $1,234.56 today.")


# ============================================================================
# 2. Word-by-word streaming
# ============================================================================

def _word_chunk_sizes(text: str) -> list[int]:
    """Build chunk sizes that produce word-by-word streaming."""
    sizes: list[int] = []
    for token in re.findall(r"\S+\s*", text):
        sizes.append(len(token))
    return sizes


def test_word_by_word_bold():
    text = "<b>This is a bold sentence with several words.</b>"
    assert_stream_safe(text, _word_chunk_sizes(text))


def test_word_by_word_mixed():
    text = "Here is some <b>bold</b> and some <i>italic</i> text."
    assert_stream_safe(text, _word_chunk_sizes(text))


def test_word_by_word_link():
    text = 'Check out <a href="https://example.com">this link</a> for details.'
    assert_stream_safe(text, _word_chunk_sizes(text))


# ============================================================================
# 3. Random chunk sizes (seeded)
# ============================================================================

def test_random_chunks_seeded():
    text = (
        "Hello! Here is a <b>bold word</b> and an <i>italic phrase</i>. "
        'Plus a <a href="https://example.com">link</a> and a $ price tag.'
    )
    rng = random.Random(42)
    sizes = [rng.choice([1, 3, 5, 7, 13, 27]) for _ in range(50)]
    assert_stream_safe(text, sizes)


def test_random_chunks_multiple_seeds():
    text = "<b>Outer <i>nested</i> bold</b> with extra <code>code()</code> bits."
    for seed in [1, 7, 13, 42, 99, 2026]:
        rng = random.Random(seed)
        sizes = [rng.choice([2, 4, 8, 16]) for _ in range(40)]
        assert_stream_safe(text, sizes)


# ============================================================================
# 4. The original bug case: <i>text without close yet
# ============================================================================

def test_original_bug_italic_unclosed_midstream():
    # The exact "open tag, no close yet" state must already balance.
    sanitized = sanitize_telegram_html("<i>text without close yet")
    assert_telegram_safe(sanitized)
    assert sanitized.endswith("</i>")


def test_original_bug_full_stream():
    assert_stream_safe("<i>text without close yet, but it ends eventually</i>")


# ============================================================================
# 5. Nested tags streaming
# ============================================================================

def test_nested_bold_italic_streaming():
    assert_stream_safe("<b><i>both opening then content</i></b>")


def test_nested_three_levels_streaming():
    assert_stream_safe("<b>outer <i>inner <u>deepest</u> back</i> out</b>")


def test_nested_word_chunks():
    text = "<b>Bold <i>and italic</i> together</b> done."
    assert_stream_safe(text, _word_chunk_sizes(text))


# ============================================================================
# 6. Tag opening boundary states
# ============================================================================

@pytest.mark.parametrize(
    "partial",
    [
        "<",
        "<b",
        "<b>",
        "<i",
        "<i>",
        "<co",
        "<code",
        "<code>",
        "<a",
        "<a ",
        '<a href',
        '<a href=',
        '<a href="',
        '<a href="https://example.com',
        '<a href="https://example.com"',
        '<a href="https://example.com">',
    ],
)
def test_tag_opening_boundary(partial):
    sanitized = sanitize_telegram_html(partial)
    assert_telegram_safe(sanitized)


# ============================================================================
# 7. Tag closing boundary states
# ============================================================================

@pytest.mark.parametrize(
    "partial",
    [
        "<b>x<",
        "<b>x</",
        "<b>x</b",
        "<b>x</b>",
        "<i>y<",
        "<i>y</",
        "<i>y</i",
        "<i>y</i>",
        "<code>z<",
        "<code>z</code",
        "<code>z</code>",
    ],
)
def test_tag_closing_boundary(partial):
    sanitized = sanitize_telegram_html(partial)
    assert_telegram_safe(sanitized)


# ============================================================================
# 8. Streaming with $ amounts — never escape to \$
# ============================================================================

def test_dollar_token_by_token():
    assert_stream_safe("Total: $1,234.56 (was $999.99 yesterday)")


def test_dollar_inside_bold_streaming():
    assert_stream_safe("<b>$500</b> profit and <i>$1.2k</i> loss.")


def test_multiple_dollars_word_by_word():
    text = "Prices: $10, $20, $30, $40, $50 — sum is $150 total."
    assert_stream_safe(text, _word_chunk_sizes(text))


# ============================================================================
# 9. Streaming with special chars (<, >, &) in body text
# ============================================================================

def test_less_than_inequality_char_by_char():
    # Naive sanitizer would leave a stray '<' for one tick at "5 <"
    assert_stream_safe("5 < 10 and 20 > 15")


def test_ampersand_streaming():
    assert_stream_safe("Tom & Jerry & friends")


def test_special_chars_inside_bold():
    assert_stream_safe("<b>if x < 5 && y > 2 then ok</b>")


def test_special_chars_word_by_word():
    text = "Compare: a < b, c > d, e & f together."
    assert_stream_safe(text, _word_chunk_sizes(text))


# ============================================================================
# 10. Long streaming response — 2000 chars in 50 chunks
# ============================================================================

def _build_long_response() -> str:
    parts = [
        "Here is a long response. ",
        "It has <b>bold sections</b> and <i>italic sections</i>. ",
        'It also has <a href="https://example.com">links</a> sometimes. ',
        "Plus dollar amounts like $1,234.56 and $99.00. ",
        "And inequalities like 5 < 10 and 20 > 15. ",
        "And ampersands like Tom & Jerry. ",
        "Some <code>inline code</code> too. ",
        "Nested <b>bold with <i>italic inside</i> is fine</b>. ",
    ]
    out = ""
    while len(out) < 2000:
        out += parts[len(out) % len(parts)]
    return out[:2000]


def test_long_streaming_50_chunks():
    text = _build_long_response()
    chunk_size = max(1, len(text) // 50)
    sizes = [chunk_size] * 50
    # Ensure final chunk reaches end
    sizes[-1] = len(text) - chunk_size * 49
    assert_stream_safe(text, sizes)


def test_long_streaming_random_chunks():
    text = _build_long_response()
    rng = random.Random(2026)
    sizes = [rng.randint(1, 80) for _ in range(200)]
    assert_stream_safe(text, sizes)


def test_long_streaming_char_by_char():
    # The harshest case: every single character boundary must be valid.
    text = _build_long_response()[:500]  # 500 prefixes is plenty
    assert_stream_safe(text)
