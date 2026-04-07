"""
Adversarial fuzz tests for telegram_bot.handlers.message HTML helpers.

Targets:
- sanitize_telegram_html(text)
- _balance_telegram_tags(text)
- _open_tags_at_end(text)
- split_html_safely(text, max_length)

Goal: deliberately try to BREAK these functions with malformed HTML, weird
unicode, splitter edge cases, mismatched stacks, injection attempts, and
large inputs. Each test asserts only that:
  (a) The function does not crash, and
  (b) The output preserves invariants we care about (e.g. for splitter:
      first part is bounded; both parts concatenated yield balanced HTML).

Where the implementation is known to take a "best effort" path (e.g. leaving
mismatched closes alone), we assert the documented behavior rather than the
ideal behavior.
"""

import re

import pytest

from handlers.message import (
    _balance_telegram_tags,
    _open_tags_at_end,
    sanitize_telegram_html,
    split_html_safely,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_REAL_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>")
_ALLOWED = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "a", "blockquote", "tg-spoiler",
}


def is_balanced(text: str) -> bool:
    """Return True if all *allowed* opening tags have a matching close in LIFO order."""
    stack = []
    for m in _REAL_TAG.finditer(text):
        is_close = bool(m.group(1))
        tag = m.group(2).lower()
        if tag not in _ALLOWED:
            continue
        if is_close:
            if not stack or stack[-1] != tag:
                return False
            stack.pop()
        else:
            stack.append(tag)
    return not stack


# ---------------------------------------------------------------------------
# 1. Malformed HTML
# ---------------------------------------------------------------------------


class TestMalformedHTML:
    def test_unclosed_anchor_no_gt(self):
        """`<a href="...` with no closing `>` - should not crash, no real tag emitted."""
        out = sanitize_telegram_html('Click <a href="http://x.com')
        assert isinstance(out, str)
        assert "<a" not in out  # no real tag (since the original > was missing)
        assert is_balanced(out)

    def test_tag_with_inner_whitespace(self):
        """`< b >` is not a real tag — should be escaped."""
        out = sanitize_telegram_html("text < b > more")
        assert "<b>" not in out
        assert "&lt;" in out
        assert is_balanced(out)

    def test_tag_with_newline_inside(self):
        out = sanitize_telegram_html("a <b\n> c")
        assert isinstance(out, str)
        assert is_balanced(out)

    def test_tag_with_tab_inside(self):
        out = sanitize_telegram_html("a <b\t> c")
        assert isinstance(out, str)
        assert is_balanced(out)

    def test_self_closing_b(self):
        """`<b/>` — Telegram doesn't have self-closing. Sanitizer treats as open."""
        out = sanitize_telegram_html("hello <b/> world")
        # Either escaped as text, or parsed as <b> and then balanced
        assert isinstance(out, str)
        assert is_balanced(out)

    def test_self_closing_br_disallowed(self):
        out = sanitize_telegram_html("line1<br/>line2")
        assert "<br" not in out  # br not allowed
        assert is_balanced(out)

    def test_taglike_math_text(self):
        """Bare `5 < 10 > 3` must be escaped."""
        out = sanitize_telegram_html("if x < 10 and y > 0 then ok")
        # Numbers/letters after < should not get parsed as tags (10/y don't match
        # tag-name pattern only because regex requires letter start; "y > 0" might).
        # Either way, output must be balanced and contain &lt; / &gt;
        assert "&lt;" in out
        assert "&gt;" in out
        assert is_balanced(out)

    def test_nested_same_name_tag(self):
        out = sanitize_telegram_html("<b><b>nested</b></b>")
        # Should round-trip as real tags and stay balanced
        assert out.count("<b>") == 2
        assert out.count("</b>") == 2
        assert is_balanced(out)

    def test_empty_href(self):
        out = sanitize_telegram_html('<a href="">link</a>')
        assert "<a" in out
        assert "</a>" in out
        assert is_balanced(out)

    def test_bare_href_attribute(self):
        """`<a href>` (no value) — sanitizer should still survive."""
        out = sanitize_telegram_html("<a href>link</a>")
        assert isinstance(out, str)
        assert is_balanced(out)

    def test_single_quoted_href(self):
        out = sanitize_telegram_html("<a href='http://example.com'>link</a>")
        assert isinstance(out, str)
        assert is_balanced(out)

    def test_only_lt(self):
        out = sanitize_telegram_html("<")
        assert out == "&lt;"

    def test_only_gt(self):
        out = sanitize_telegram_html(">")
        assert out == "&gt;"

    def test_lots_of_lt_gt_no_tags(self):
        out = sanitize_telegram_html("<<<>>><<<")
        assert "<" not in out  # all escaped
        assert ">" not in out
        assert is_balanced(out)


# ---------------------------------------------------------------------------
# 2. Unicode edge cases
# ---------------------------------------------------------------------------


class TestUnicode:
    def test_rtl_hebrew(self):
        out = sanitize_telegram_html("<b>שלום</b>")
        assert "שלום" in out
        assert is_balanced(out)

    def test_combining_characters(self):
        # 'e' + combining acute
        out = sanitize_telegram_html("<i>cafe\u0301</i>")
        assert "cafe\u0301" in out
        assert is_balanced(out)

    def test_zero_width_space_inside_tag(self):
        out = sanitize_telegram_html("<b>te\u200bxt</b>")
        assert "\u200b" in out
        assert is_balanced(out)

    def test_emoji_with_zwj_sequence(self):
        # Family emoji using ZWJ
        out = sanitize_telegram_html("<b>family 👨\u200d👩\u200d👧</b>")
        assert "👨" in out
        assert is_balanced(out)

    def test_skin_tone_modifier(self):
        out = sanitize_telegram_html("<i>wave 👋🏽</i>")
        assert "👋" in out
        assert is_balanced(out)

    def test_emoji_racing_car(self):
        out = sanitize_telegram_html("🏎️💨 <b>fast</b>")
        assert "🏎" in out
        assert is_balanced(out)

    def test_lt_in_middle_of_unicode_run(self):
        out = sanitize_telegram_html("日本語 < 中文 > english")
        assert "&lt;" in out
        assert is_balanced(out)


# ---------------------------------------------------------------------------
# 3. split_html_safely edge cases
# ---------------------------------------------------------------------------


class TestSplitter:
    def test_text_exactly_max_length(self):
        text = "a" * 100
        first, rest = split_html_safely(text, 100)
        assert first == text
        assert rest == ""

    def test_text_one_over(self):
        text = "a" * 101
        first, rest = split_html_safely(text, 100)
        assert len(first) <= 100 or first.endswith(("</b>", "</i>"))  # may close tags
        assert first + rest != ""
        # Concatenation of stripped tags should equal original
        assert rest != ""

    def test_max_length_zero(self):
        """max_length=0 — degenerate. Should not crash."""
        try:
            first, rest = split_html_safely("hello world", 0)
            # split_point becomes 0, so first is empty, rest is full
            assert isinstance(first, str)
            assert isinstance(rest, str)
        except Exception as exc:
            pytest.fail(f"split_html_safely crashed with max_length=0: {exc}")

    def test_max_length_one(self):
        try:
            first, rest = split_html_safely("hello", 1)
            assert isinstance(first, str)
            assert isinstance(rest, str)
        except Exception as exc:
            pytest.fail(f"split_html_safely crashed with max_length=1: {exc}")

    def test_single_long_word_no_boundaries(self):
        """No sentence boundaries — splitter falls back to max_length."""
        text = "x" * 5000
        first, rest = split_html_safely(text, 4096)
        assert len(first) == 4096
        assert first + rest == text

    def test_multibyte_split_point(self):
        """Splitting at a mid-string Python string index — Python uses code points,
        so multi-byte UTF-8 cannot be cut mid-byte. Must not crash."""
        text = "日" * 5000  # each char is 3 bytes UTF-8 but 1 code point
        first, rest = split_html_safely(text, 4096)
        # Reconstruct must equal original
        assert first + rest == text

    def test_all_whitespace(self):
        first, rest = split_html_safely("   \n\t   ", 10)
        assert first == "   \n\t   "
        assert rest == ""

    def test_pure_html_no_text(self):
        text = "<b></b><i></i>"
        first, rest = split_html_safely(text, 100)
        assert first == text
        assert rest == ""

    def test_split_inside_tag_walks_back(self):
        """If split point lands inside `<b>`, splitter walks back."""
        # Construct text where the boundary lands inside a tag
        text = "a" * 95 + "<blockquote>more text here.</blockquote>"
        first, rest = split_html_safely(text, 100)
        # First part should not end mid-tag
        assert "<blockquote" not in first or first.endswith(">") or first.endswith("</blockquote>")
        # Both halves balanced
        assert is_balanced(first)
        assert is_balanced(rest)

    def test_split_reopens_tags(self):
        """Open tags at end of part1 must be re-opened in part2."""
        text = "<b>" + ("hello. " * 100) + "</b>"
        first, rest = split_html_safely(text, 200)
        if rest:
            assert is_balanced(first)
            assert is_balanced(rest)
            # rest must start with re-opened <b>
            assert rest.startswith("<b>")

    def test_split_nested_tags(self):
        text = "<b><i>" + ("word. " * 200) + "</i></b>"
        first, rest = split_html_safely(text, 300)
        assert is_balanced(first)
        assert is_balanced(rest)
        if rest:
            # Must re-open both
            assert "<b>" in rest[:20]
            assert "<i>" in rest[:20]

    def test_split_empty_string(self):
        first, rest = split_html_safely("", 100)
        assert first == ""
        assert rest == ""

    def test_split_negative_max_length(self):
        """Negative max — degenerate. Should not crash."""
        try:
            first, rest = split_html_safely("hello world", -5)
            assert isinstance(first, str)
            assert isinstance(rest, str)
        except Exception as exc:
            pytest.fail(f"split_html_safely crashed with negative max_length: {exc}")


# ---------------------------------------------------------------------------
# 4. Stack tracking edge cases
# ---------------------------------------------------------------------------


class TestStackEdgeCases:
    def test_orphan_close(self):
        """`</b>` with no `<b>` — should leave stack empty."""
        stack = _open_tags_at_end("</b>foo")
        assert stack == []

    def test_wrong_order_close(self):
        """`<b><i>x</b></i>` — interleaved. Per docstring, mismatches are left as-is."""
        # Real impl: stack pops only if top matches.
        # <b> -> stack=[b]; <i> -> stack=[b,i]; </b> top is i not b → no pop;
        # </i> top is i → pop; final stack=[b]
        stack = _open_tags_at_end("<b><i>x</b></i>")
        assert stack == ["b"]

    def test_balance_leaves_mismatch(self):
        """_balance_telegram_tags should append closes for whatever stack remains."""
        out = _balance_telegram_tags("<b><i>x</b></i>")
        # stack at end was [b], so a </b> appended
        assert out.endswith("</b>")

    def test_many_nested_b_tags(self):
        text = "<b>" * 100 + "core" + "</b>" * 100
        stack = _open_tags_at_end(text)
        assert stack == []  # all balanced

    def test_repeated_open_close(self):
        text = "<b>a</b><b>b</b><b>c</b>"
        stack = _open_tags_at_end(text)
        assert stack == []

    def test_disallowed_tag_ignored(self):
        """Real `<div>` (post-sanitization shouldn't exist, but check) — ignored."""
        stack = _open_tags_at_end("<div><b>x</b></div>")
        assert stack == []  # div ignored, b balanced

    def test_balance_empty_string(self):
        assert _balance_telegram_tags("") == ""

    def test_balance_none(self):
        # The function does `if not text: return text` — should handle None gracefully
        assert _balance_telegram_tags(None) is None

    def test_open_tags_empty(self):
        assert _open_tags_at_end("") == []


# ---------------------------------------------------------------------------
# 5. Injection / security
# ---------------------------------------------------------------------------


class TestInjection:
    def test_javascript_href(self):
        """Sanitizer's job is HTML safety, not URL safety. We just check no crash."""
        out = sanitize_telegram_html('<a href="javascript:alert(1)">x</a>')
        assert isinstance(out, str)
        # The 'a' tag is allowed, attribute passed through
        assert "javascript" in out
        assert is_balanced(out)

    def test_already_escaped_script(self):
        out = sanitize_telegram_html("<b>&lt;script&gt;evil()&lt;/script&gt;</b>")
        # &lt; in input is escaped to &amp;lt; by html.escape — no real tags
        assert "<script" not in out
        assert is_balanced(out)

    def test_double_escaped(self):
        out = sanitize_telegram_html("&amp;lt;b&amp;gt;text&amp;lt;/b&amp;gt;")
        assert isinstance(out, str)
        assert is_balanced(out)
        # No real <b> tag emerges
        assert "<b>" not in out

    def test_numeric_entities_decoded_to_real_tags(self):
        """`&#60;b&#62;` is decoded by html.unescape() in step 0, so the resulting
        <b> is recognized as a real tag. This is intentional — numeric entities
        for allowed tags become real tags. Disallowed tags (e.g. &#60;script&#62;)
        are decoded but then escaped back since they fail the allowlist."""
        out = sanitize_telegram_html("&#60;b&#62;text&#60;/b&#62;")
        assert "<b>text</b>" == out
        assert is_balanced(out)

    def test_numeric_entities_disallowed_tag_blocked(self):
        """Numeric entities for disallowed tags should NOT produce real tags."""
        out = sanitize_telegram_html("&#60;script&#62;alert(1)&#60;/script&#62;")
        assert "<script>" not in out
        assert is_balanced(out)
        # script should remain escaped
        assert "&lt;script&gt;" in out

    def test_script_tag_stripped(self):
        out = sanitize_telegram_html("<script>alert(1)</script>")
        assert "<script" not in out
        assert "alert(1)" in out
        assert is_balanced(out)

    def test_onclick_in_b(self):
        """Telegram <b> doesn't take attributes; sanitizer should pass them through
        but balance must hold."""
        out = sanitize_telegram_html('<b onclick="evil()">x</b>')
        assert "<b" in out
        assert "</b>" in out
        assert is_balanced(out)


# ---------------------------------------------------------------------------
# 6. Performance / DoS
# ---------------------------------------------------------------------------


class TestPerformance:
    def test_100k_b_tags(self):
        """100KB of <b> tags — must not blow up regex backtracking."""
        text = "<b>" * 16000 + "x" + "</b>" * 16000  # ~120KB
        import time
        start = time.time()
        out = sanitize_telegram_html(text)
        elapsed = time.time() - start
        assert elapsed < 5.0, f"sanitize took {elapsed:.2f}s on 100KB input"
        assert is_balanced(out)

    def test_10k_nested_tags(self):
        text = "<b>" * 10000 + "core" + "</b>" * 10000
        out = sanitize_telegram_html(text)
        assert is_balanced(out)

    def test_balance_100k_unclosed(self):
        text = "<b>" * 5000
        out = _balance_telegram_tags(text)
        assert out.endswith("</b>")
        assert out.count("</b>") == 5000

    def test_huge_text_no_tags(self):
        text = "abc " * 30000
        out = sanitize_telegram_html(text)
        assert len(out) >= len(text)

    def test_sanitize_with_lots_of_lt(self):
        text = "<" * 5000 + ">" * 5000
        out = sanitize_telegram_html(text)
        assert "<" not in out
        assert ">" not in out


# ---------------------------------------------------------------------------
# 7. Round-trip / streaming simulation
# ---------------------------------------------------------------------------


class TestStreamingSimulation:
    def test_streaming_partial_open_tag(self):
        """Mid-stream: `<b>partial<i>text` should be balanced to close both."""
        out = sanitize_telegram_html("<b>partial<i>text")
        assert out.endswith("</i></b>")
        assert is_balanced(out)

    def test_streaming_cut_mid_tag_name(self):
        """Cut at `<b` (no close `>`) — that '<' should be escaped."""
        out = sanitize_telegram_html("hello <b")
        assert "<b" not in out
        assert "&lt;b" in out
        assert is_balanced(out)

    def test_streaming_cut_mid_attribute(self):
        out = sanitize_telegram_html('<a href="http://exa')
        assert "<a" not in out
        assert is_balanced(out)
