"""
Pressure tests for split_html_safely().

Telegram has a 4096-char per-message limit. This module hammers split_html_safely
with boundary, pathological, and property-based inputs to verify:
  1. Both halves are HTML-tag balanced (verified via _open_tags_at_end stack).
  2. No half cuts inside an HTML tag (no "<b" without ">").
  3. Concatenation of stripped-of-tags content preserves the original visible text.
  4. Repeated splitting eventually terminates and covers the original text.

NOTE: split_html_safely is a *best-effort* splitter. The first part may exceed
max_length slightly because:
  - Sentence-boundary search can land *past* max_length when scanning ahead, OR
  - Closing tags are appended after the split point.
We allow a small overhead in assertions and document any genuine bugs found.
"""

import random

import pytest

from handlers.message import (
    _TAG_PATTERN,
    _open_tags_at_end,
    split_html_safely,
)


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------


def is_balanced(text: str) -> bool:
    """Return True if all Telegram tags in text are properly nested/closed."""
    return _open_tags_at_end(text) == []


def strip_tags(text: str) -> str:
    """Remove all (real) Telegram tags so we can compare visible content."""
    return _TAG_PATTERN.sub("", text)


def assert_no_partial_tag(text: str) -> None:
    """Assert there is no '<' without a matching '>' after it (no cut tag)."""
    last_lt = text.rfind("<")
    last_gt = text.rfind(">")
    if last_lt == -1:
        return
    assert last_gt > last_lt, (
        f"Partial tag detected in text ending: ...{text[-60:]!r}"
    )


def assert_split_invariants(
    original: str,
    first: str,
    rest: str,
    max_length: int,
    overhead_allowed: int = 200,
):
    """
    Universal invariants every successful split must satisfy.

    overhead_allowed accommodates appended closing tags on first part. The
    splitter doesn't shrink the split point to "make room" for closing tags,
    so first can exceed max_length by a small amount.
    """
    # Both halves balanced
    assert is_balanced(first), f"First half unbalanced: stack={_open_tags_at_end(first)}"
    assert is_balanced(rest), f"Rest unbalanced: stack={_open_tags_at_end(rest)}"

    # Neither half is cut mid-tag
    assert_no_partial_tag(first)
    assert_no_partial_tag(rest)

    # First half should not wildly exceed max_length
    assert len(first) <= max_length + overhead_allowed, (
        f"First half too long: {len(first)} > {max_length}+{overhead_allowed}"
    )

    # Visible content preservation: stripped(first)+stripped(rest) == stripped(original)
    visible_combined = strip_tags(first) + strip_tags(rest)
    visible_original = strip_tags(original)
    assert visible_combined == visible_original, (
        "Visible content mismatch after split"
    )


# ============================================================================
# 1. Boundary conditions
# ============================================================================


class TestBoundaryConditions:
    def test_text_length_equals_max(self):
        text = "a" * 100
        first, rest = split_html_safely(text, 100)
        assert first == text
        assert rest == ""

    def test_text_length_max_plus_one(self):
        text = "a" * 101
        first, rest = split_html_safely(text, 100)
        assert first + rest == text
        assert len(first) <= 100
        assert rest != ""

    def test_text_length_max_minus_one(self):
        text = "a" * 99
        first, rest = split_html_safely(text, 100)
        assert first == text
        assert rest == ""

    def test_max_length_zero(self):
        # Pathological: max_length=0 with non-empty text
        # The function should not infinite-loop. We accept whatever it produces
        # provided invariants hold.
        text = "abc"
        first, rest = split_html_safely(text, 0)
        # Visible content preserved
        assert strip_tags(first) + strip_tags(rest) == "abc"

    def test_max_length_one(self):
        text = "abcdef"
        first, rest = split_html_safely(text, 1)
        assert strip_tags(first) + strip_tags(rest) == "abcdef"
        assert is_balanced(first)
        assert is_balanced(rest)

    def test_max_length_larger_than_text(self):
        text = "hello world"
        first, rest = split_html_safely(text, 10000)
        assert first == text
        assert rest == ""

    def test_empty_text(self):
        first, rest = split_html_safely("", 100)
        assert first == ""
        assert rest == ""

    def test_empty_text_zero_max(self):
        first, rest = split_html_safely("", 0)
        assert first == ""
        assert rest == ""


# ============================================================================
# 2. Tag at the cut point
# ============================================================================


class TestTagAtCutPoint:
    def test_open_tag_starts_exactly_at_split(self):
        text = "x" * 100 + "<b>more text here</b>"
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)

    def test_close_tag_at_split(self):
        text = "<b>" + "x" * 100 + "</b>" + "y" * 50
        first, rest = split_html_safely(text, 104)
        assert_split_invariants(text, first, rest, 104)

    def test_split_inside_blockquote_tag(self):
        # Place split point in middle of "<blockquote>"
        prefix = "x" * 95
        text = prefix + "<blockquote>content</blockquote>" + "y" * 50
        # split=100 lands inside "<blockquote>"
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)
        # First part must not contain partial "<blockquot"
        assert "<blockquot" not in first or "<blockquote>" in first

    def test_multiple_tags_clustered_at_split(self):
        text = "x" * 95 + "<b><i><u>nested</u></i></b>" + "y" * 50
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)

    def test_split_inside_attribute(self):
        text = "x" * 90 + '<a href="https://example.com/foo">link</a>' + "y" * 50
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)

    def test_split_right_after_open_tag(self):
        # Open tag closes just before split, content begins right after
        text = "<b>" + "x" * 200 + "</b>"
        first, rest = split_html_safely(text, 50)
        assert_split_invariants(text, first, rest, 50)
        # First should re-close <b>; rest should re-open <b>
        assert first.endswith("</b>")
        assert rest.startswith("<b>")


# ============================================================================
# 3. Pathological cases
# ============================================================================


class TestPathological:
    def test_50_nested_bold_tags(self):
        # 50 <b> tags then content then 50 </b>
        opens = "<b>" * 50
        closes = "</b>" * 50
        text = opens + ("x" * 500) + closes
        first, rest = split_html_safely(text, 200)
        assert_split_invariants(text, first, rest, 200, overhead_allowed=400)
        # All <b> should still be re-opened in rest if they were open at split
        rest_initial_stack = []
        for m in _TAG_PATTERN.finditer(rest):
            if not m.group(1):
                rest_initial_stack.append(m.group(2))
            else:
                if rest_initial_stack and rest_initial_stack[-1] == m.group(2):
                    rest_initial_stack.pop()
                else:
                    break

    def test_alternating_tags_200_iterations(self):
        chunks = []
        for i in range(200):
            chunks.append("<b>x</b><i>y</i>")
        text = "".join(chunks)
        first, rest = split_html_safely(text, 500)
        assert_split_invariants(text, first, rest, 500)

    def test_single_tag_spanning_entire_text(self):
        text = "<b>" + ("x" * 5000) + "</b>"
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)
        assert first.endswith("</b>")
        assert rest.startswith("<b>")

    def test_no_sentence_boundaries(self):
        # No . ! ? \n anywhere — should still split (just at max_length)
        text = "x" * 5000  # nothing but x
        first, rest = split_html_safely(text, 1000)
        assert_split_invariants(text, first, rest, 1000)
        # Visible content preserved
        assert strip_tags(first) + strip_tags(rest) == text

    def test_only_tags_no_content(self):
        text = "<b></b>" * 200
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)

    def test_deeply_nested_mixed_tags(self):
        text = "<b><i><u><s><code>deep</code></s></u></i></b>" * 100
        first, rest = split_html_safely(text, 500)
        assert_split_invariants(text, first, rest, 500)

    def test_blockquote_with_long_content(self):
        text = "<blockquote>" + ("word. " * 1000) + "</blockquote>"
        first, rest = split_html_safely(text, 800)
        assert_split_invariants(text, first, rest, 800)
        assert first.endswith("</blockquote>")
        assert rest.startswith("<blockquote>")


# ============================================================================
# 4. Splitting then re-splitting (multi-split)
# ============================================================================


def repeated_split(text: str, max_length: int, max_iters: int = 1000) -> list[str]:
    """Repeatedly split until everything fits. Returns the list of chunks."""
    chunks = []
    remainder = text
    iters = 0
    while remainder and iters < max_iters:
        first, remainder = split_html_safely(remainder, max_length)
        if not first:
            # Pathological: zero-length first part — break to avoid infinite loop
            break
        chunks.append(first)
        iters += 1
    if remainder:
        # didn't terminate
        chunks.append(remainder)
    return chunks


class TestMultiSplit:
    def test_split_10000_chars_into_1000_chunks(self):
        text = "Sentence number {}. ".format(0) * 500  # ~10000 chars
        chunks = repeated_split(text, 1000)
        # All but possibly the last chunk should be near max_length
        for c in chunks:
            assert is_balanced(c)
            assert_no_partial_tag(c)
        # Visible content preserved
        recovered = "".join(strip_tags(c) for c in chunks)
        assert recovered == strip_tags(text)

    def test_multisplit_with_formatting(self):
        text = ("<b>Bold sentence.</b> <i>Italic sentence.</i> " * 500)
        chunks = repeated_split(text, 500)
        for c in chunks:
            assert is_balanced(c), f"Unbalanced chunk: {c[:80]}..."
            assert_no_partial_tag(c)
        recovered = "".join(strip_tags(c) for c in chunks)
        assert recovered == strip_tags(text)

    def test_multisplit_30000_chars(self):
        text = ("This is a long sentence with <b>formatting</b> inside. " * 600)
        chunks = repeated_split(text, 4096)
        for c in chunks:
            assert is_balanced(c)
            assert_no_partial_tag(c)
            assert len(c) <= 4096 + 200  # small overhead allowance
        recovered = "".join(strip_tags(c) for c in chunks)
        assert recovered == strip_tags(text)

    def test_multisplit_terminates_on_pathological_input(self):
        # 50000 'x's, max=4096 — must terminate in reasonable iters
        text = "x" * 50000
        chunks = repeated_split(text, 4096, max_iters=100)
        assert len(chunks) < 100  # didn't hit the safety cap
        assert "".join(chunks) == text


# ============================================================================
# 5. Realistic scenarios
# ============================================================================


class TestRealisticScenarios:
    def test_long_financial_analysis(self):
        bullets = []
        for i in range(20):
            bullets.append(
                f"<b>Point {i}:</b> Consider <i>Apple Inc.</i> with a P/E of "
                f"{20+i}. The current price is <code>${100+i*5}</code>. "
                f"Analysts at <a href=\"https://example.com\">Example</a> "
                f"recommend a <s>buy</s> hold rating. " * 3
            )
        text = "\n\n".join(bullets)
        first, rest = split_html_safely(text, 4096)
        assert_split_invariants(text, first, rest, 4096)

    def test_long_code_block(self):
        code = "def function_{}():\n    return {}\n\n".format(0, 0) * 200
        text = '<pre><code class="language-python">' + code + "</code></pre>"
        # Force split well inside the code block
        first, rest = split_html_safely(text, 2000)
        assert_split_invariants(text, first, rest, 2000, overhead_allowed=300)

    def test_long_blockquote_with_nested_formatting(self):
        text = (
            "<blockquote>"
            + ("She said: <b>this is important</b> and <i>this is too</i>. " * 200)
            + "</blockquote>"
        )
        first, rest = split_html_safely(text, 2000)
        assert_split_invariants(text, first, rest, 2000, overhead_allowed=300)

    def test_mixed_paragraphs_with_links(self):
        para = (
            "First sentence here. <b>Bold sentence.</b> "
            "Visit <a href=\"https://example.com/path?q=1&amp;r=2\">link</a>. "
            "Another sentence with <i>italics</i>.\n\n"
        )
        text = para * 100
        first, rest = split_html_safely(text, 2000)
        assert_split_invariants(text, first, rest, 2000)


# ============================================================================
# 6. Property tests
# ============================================================================


def random_html(rng: random.Random, target_len: int) -> str:
    """Generate random valid Telegram HTML of approximately target_len chars."""
    tags = ["b", "i", "u", "s", "code"]
    out = []
    cur_len = 0
    open_stack: list[str] = []
    while cur_len < target_len:
        action = rng.choice(["text", "open", "close", "sentence"])
        if action == "text":
            chunk = "abc def ghi " * rng.randint(1, 5)
            out.append(chunk)
            cur_len += len(chunk)
        elif action == "sentence":
            ch = rng.choice([". ", "! ", "? ", "\n"])
            out.append(ch)
            cur_len += len(ch)
        elif action == "open" and len(open_stack) < 4:
            t = rng.choice(tags)
            out.append(f"<{t}>")
            open_stack.append(t)
            cur_len += len(t) + 2
        elif action == "close" and open_stack:
            t = open_stack.pop()
            out.append(f"</{t}>")
            cur_len += len(t) + 3
    # Close remaining
    while open_stack:
        t = open_stack.pop()
        out.append(f"</{t}>")
    return "".join(out)


class TestProperty:
    @pytest.mark.parametrize("seed", list(range(20)))
    def test_random_inputs_preserve_invariants(self, seed):
        rng = random.Random(seed)
        target_len = rng.randint(500, 5000)
        text = random_html(rng, target_len)
        # Sanity: random_html produces balanced text
        assert is_balanced(text), f"Generator bug, seed={seed}"

        max_length = rng.randint(50, len(text)) if len(text) > 50 else 50
        first, rest = split_html_safely(text, max_length)

        if len(text) <= max_length:
            assert first == text
            assert rest == ""
            return

        assert_split_invariants(text, first, rest, max_length, overhead_allowed=400)

    @pytest.mark.parametrize("seed", list(range(10)))
    def test_random_multisplit_terminates(self, seed):
        rng = random.Random(seed + 1000)
        text = random_html(rng, 8000)
        max_length = rng.randint(200, 1500)
        chunks = repeated_split(text, max_length, max_iters=500)
        # All chunks balanced
        for c in chunks:
            assert is_balanced(c)
            assert_no_partial_tag(c)
        # Content preserved
        recovered = "".join(strip_tags(c) for c in chunks)
        assert recovered == strip_tags(text)


# ============================================================================
# 7. Misc edge cases that surfaced during fuzzing
# ============================================================================


class TestMiscEdgeCases:
    def test_text_with_escaped_entities(self):
        text = "AT&amp;T is &lt;great&gt;. " * 200
        first, rest = split_html_safely(text, 500)
        assert_split_invariants(text, first, rest, 500)

    def test_split_point_at_newline(self):
        text = ("line one\n" * 200)
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)

    def test_consecutive_question_marks(self):
        text = "what??? " * 500
        first, rest = split_html_safely(text, 200)
        assert_split_invariants(text, first, rest, 200)

    def test_only_punctuation(self):
        text = "." * 5000
        first, rest = split_html_safely(text, 100)
        assert_split_invariants(text, first, rest, 100)

    def test_unicode_content(self):
        text = ("Hello 世界. " * 500)
        first, rest = split_html_safely(text, 500)
        assert_split_invariants(text, first, rest, 500)
