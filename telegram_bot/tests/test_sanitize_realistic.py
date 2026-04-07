"""
Realistic LLM-output tests for sanitize_telegram_html() and split_html_safely().

These tests exercise the sanitizer with the kind of multi-section, mixed-tag,
mixed-character output that Annie's TELEGRAM_FORMAT_INSTRUCTIONS prompt
encourages: financial summaries with $/% and tickers in <code>, code blocks,
bullet lists, blockquotes, spoilers, escaped HTML chars in body text, etc.

Goals:
- Verify realistic LLM payloads pass through unchanged where they should
- Verify split_html_safely() preserves tag balance across long messages
- Verify reassembly (minus auto-injected closer/opener) reproduces the original
- Verify no orphaned `<` or `>` symbols sneak through after a split
"""

from handlers.message import (
    _open_tags_at_end,
    sanitize_telegram_html,
    split_html_safely,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def assert_balanced(text: str) -> None:
    """A piece of HTML must have no still-open Telegram tags at the end."""
    assert _open_tags_at_end(text) == [], (
        f"Unbalanced HTML — open tags at end: {_open_tags_at_end(text)}\n"
        f"Text: {text!r}"
    )


def assert_no_orphan_brackets(text: str) -> None:
    """
    Each `<` should belong to a real tag (real-tag pattern matches it),
    and there should be no truncated tag like '<b' with no closing '>'.
    """
    # Walk: every '<' must be followed (eventually before any other '<')
    # by a matching '>'.
    i = 0
    while i < len(text):
        lt = text.find("<", i)
        if lt < 0:
            break
        gt = text.find(">", lt)
        next_lt = text.find("<", lt + 1)
        assert gt != -1, f"Orphan '<' with no closing '>' at pos {lt}: {text[lt:lt+30]!r}"
        if next_lt != -1:
            assert gt < next_lt, (
                f"Orphan '<' before next '<' (truncated tag) at pos {lt}: "
                f"{text[lt:next_lt]!r}"
            )
        i = gt + 1


# ---------------------------------------------------------------------------
# 1. Financial summaries
# ---------------------------------------------------------------------------

class TestFinancialSummaries:
    def test_portfolio_snapshot(self):
        text = (
            "<b>📊 Portfolio Snapshot</b>\n\n"
            "• <b>NVDA</b> — <code>$525.30</code> (+12.4%)\n"
            "• <b>AAPL</b> — <code>$237.50</code> (+0.8%)\n"
            "• <b>TSLA</b> — <code>$198.10</code> (-2.1%)\n\n"
            "<b>Total:</b> <code>$48,213.90</code> <i>(+3.2% today)</i>"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_multi_section_financials(self):
        text = (
            "<b>💰 This Month</b>\n"
            "Income: <code>$8,420</code>\n"
            "Spend:  <code>$5,118</code>\n"
            "Net:    <b><code>$3,302</code></b>\n\n"
            "<b>🎯 Goal Progress</b>\n"
            "Emergency fund — <i>62% of target</i>"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_percentages_and_dollar_signs_not_escaped(self):
        # The prompt says: do NOT escape $, ., !, etc.
        text = "<b>YTD return:</b> +18.7% on $124,000 invested."
        out = sanitize_telegram_html(text)
        assert "$" in out and "%" in out
        assert "&#36;" not in out and "&#37;" not in out
        assert out == text


# ---------------------------------------------------------------------------
# 2. Code explanations
# ---------------------------------------------------------------------------

class TestCodeExplanations:
    def test_python_pre_code_with_language_class(self):
        # NOTE: sanitize_telegram_html() expects RAW text, not pre-escaped.
        # We feed it a literal `<` and expect the sanitizer to escape it.
        # (If we passed `&lt;` we'd get `&amp;lt;` — see contract notes.)
        text = (
            "Here's a quick example:\n\n"
            '<pre><code class="language-python">def fib(n):\n'
            "    if n < 2:\n"
            "        return n\n"
            "    return fib(n - 1) + fib(n - 2)</code></pre>\n\n"
            "Note that <code>fib(10)</code> returns <b>55</b>."
        )
        out = sanitize_telegram_html(text)
        # The class attribute and the content inside should survive intact.
        assert 'class="language-python"' in out
        assert "def fib(n):" in out
        assert "&lt;" in out  # the literal `<` was escaped by the sanitizer
        # No raw `<` left in code body (only as part of real tags)
        assert "if n < 2" not in out
        assert_balanced(out)

    def test_inline_code_with_special_chars(self):
        text = "Run <code>git log --oneline | head -5</code> to see recent commits."
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_pre_block_no_class(self):
        text = "<pre>$ ls -la\ntotal 8\ndrwxr-xr-x  4 user  staff   128 Apr  5 09:00 .</pre>"
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 3. Bullet lists with mixed formatting
# ---------------------------------------------------------------------------

class TestBulletLists:
    def test_mixed_format_bullets(self):
        text = (
            "<b>Top movers today:</b>\n"
            "• <b>NVDA</b> — <code>$525</code> (+12.4%)\n"
            "• <b>META</b> — <code>$612</code> (+4.1%)\n"
            "• <b>GOOG</b> — <code>$172</code> (-0.6%)"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_nested_sub_bullets(self):
        text = (
            "<b>Plan:</b>\n"
            "• Save more\n"
            "  ◦ Automate <code>$500</code>/month transfer\n"
            "  ◦ Cut <i>discretionary</i> spend\n"
            "• Invest the rest"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 4. Numbered lists with sub-points
# ---------------------------------------------------------------------------

class TestNumberedLists:
    def test_outline_response(self):
        text = (
            "<b>How to think about this:</b>\n\n"
            "1. <b>Define the goal</b> — what does success look like?\n"
            "   ▸ Concrete, measurable, time-bound.\n"
            "2. <b>List constraints</b> — budget, time, risk tolerance.\n"
            "3. <b>Pick a path</b> — the one with best <i>risk-adjusted</i> return.\n\n"
            "Want me to walk through step 1 with you?"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 5. Blockquotes pulling out user words
# ---------------------------------------------------------------------------

class TestBlockquotes:
    def test_quoting_user(self):
        text = (
            "<blockquote>I want to retire by 50.</blockquote>\n"
            "Got it. Here's the math on what that takes…"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_blockquote_with_inline_formatting(self):
        text = (
            "You said:\n"
            "<blockquote>I'm losing sleep over the <b>NVDA</b> position.</blockquote>\n"
            "Let's unpack that."
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 6. Spoilers
# ---------------------------------------------------------------------------

class TestSpoilers:
    def test_spoiler_for_pnl(self):
        text = "Drumroll please… <tg-spoiler>You're up $4,200 this month 🎉</tg-spoiler>"
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_spoiler_inside_paragraph(self):
        text = (
            "Your guess was close. The actual answer: "
            "<tg-spoiler><b>42</b></tg-spoiler>."
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 7. Mixed HTML chars in text
# ---------------------------------------------------------------------------

class TestMixedHtmlChars:
    def test_comparison_operators_in_prose(self):
        # The sanitizer's contract: it escapes raw `<` itself. If the LLM
        # also pre-escapes, we'd get `&amp;lt;` (double-escape), which would
        # render as the literal string "&lt;" in Telegram instead of "<".
        # This test documents the expected behavior with raw input.
        text = "If 5 < 10 < 100, then the chain holds."
        out = sanitize_telegram_html(text)
        assert "5 &lt; 10 &lt; 100" in out
        assert "<" not in out.replace("&lt;", "")  # no real `<` left
        assert_balanced(out)

    def test_pre_escaped_input_normalized_correctly(self):
        # Regression: previously, pre-escaped input from LLMs caused double-
        # escaping (LLM emits &lt;, sanitizer produces &amp;lt;, Telegram
        # showed literal "<"). Fix: sanitize_telegram_html() now normalizes
        # input via html.unescape() first, so pre-escaped and raw forms
        # produce the same output.
        text = "If 5 &lt; 10, the chain holds."
        out = sanitize_telegram_html(text)
        # The 5 < 10 should be properly escaped to 5 &lt; 10 (single level)
        assert "5 &lt; 10" in out
        # Should NOT contain double-escaped form
        assert "&amp;lt;" not in out
        # Should NOT contain raw <
        assert out.count("<") == out.count("&lt;") - out.count("&lt;") + 0  # no real < tags

    def test_unescaped_lt_in_body_gets_escaped(self):
        # LLM forgot to escape — sanitizer should fix it
        text = "Condition: x < y < z"
        out = sanitize_telegram_html(text)
        assert "&lt;" in out
        assert "<" not in out.replace("&lt;", "")
        assert_balanced(out)

    def test_json_in_pre_block(self):
        text = (
            "Here's the response:\n"
            "<pre>{\n"
            '  "ticker": "AAPL",\n'
            '  "price": 237.50,\n'
            '  "change": "+0.8%"\n'
            "}</pre>"
        )
        out = sanitize_telegram_html(text)
        assert '"ticker"' in out
        assert "<pre>" in out and "</pre>" in out
        assert_balanced(out)

    def test_ampersand_in_prose(self):
        # Sanitizer takes raw `&` and escapes it.
        text = "Procter & Gamble (<code>PG</code>) is steady."
        out = sanitize_telegram_html(text)
        assert "Procter &amp; Gamble" in out
        assert "<code>PG</code>" in out
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 8. Multi-line section headers
# ---------------------------------------------------------------------------

class TestSectionHeaders:
    def test_analysis_response(self):
        text = (
            "<b>📊 Quick Read</b>\n"
            "Your portfolio is up 3.2% today, mostly from <b>NVDA</b>.\n\n"
            "━━━━━━━━━━━━\n\n"
            "<b>🤔 What I notice</b>\n"
            "You're heavy on AI names — about 62% of total exposure. That's "
            "fine if you're <i>convicted</i>; risky if you're <i>chasing</i>.\n\n"
            "<b>🎯 What I'd do</b>\n"
            "Trim 5% from <code>NVDA</code> on the next pop. Park it in "
            "<code>BIL</code> until you have a plan."
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)


# ---------------------------------------------------------------------------
# 9. Long response splitting
# ---------------------------------------------------------------------------

class TestLongResponseSplitting:
    def _build_long_response(self) -> str:
        # ~5000 chars of mixed formatting, balanced HTML throughout.
        sections = []
        for i in range(1, 21):
            sections.append(
                f"<b>Section {i}</b>\n"
                f"This is the body of section {i}. We talk about <code>TICK{i}</code> "
                f"trading at <code>${100 + i}.50</code> with <i>moderate</i> volume. "
                f"The change is <b>+{i}.2%</b> on the day. "
                f"Some additional prose to pad this section out so the total length "
                f"crosses the 4096 char Telegram limit comfortably and we have to "
                f"split. More words. Even more words. Almost there. Done.\n"
            )
        return "\n".join(sections)

    def test_long_response_is_long_enough(self):
        text = self._build_long_response()
        assert len(text) > 4096, f"need >4096 chars to test split, got {len(text)}"

    def test_split_produces_two_balanced_parts(self):
        text = self._build_long_response()
        first, second = split_html_safely(text, 4000)
        assert first and second
        assert len(first) <= 4000 + 50  # allow small slack for closing tags
        assert_balanced(first)
        assert_balanced(second)
        assert_no_orphan_brackets(first)
        assert_no_orphan_brackets(second)

    def test_split_recursive_until_done(self):
        text = self._build_long_response()
        parts = []
        remainder = text
        while remainder:
            first, remainder = split_html_safely(remainder, 4000)
            parts.append(first)
            if not remainder:
                break
        assert len(parts) >= 2
        for p in parts:
            assert_balanced(p)
            assert_no_orphan_brackets(p)
            assert len(p) <= 4096

    def test_split_inside_open_bold_re_opens(self):
        # Split point lands while <b> is open — verify close + reopen.
        text = "<b>" + ("word " * 1000) + "end</b>"
        first, second = split_html_safely(text, 1000)
        assert first.endswith("</b>")
        assert second.startswith("<b>")
        assert_balanced(first)
        assert_balanced(second)

    def test_split_avoids_cutting_inside_a_tag(self):
        # Construct text where the naive split point lands inside a tag
        prefix = "x" * 95
        text = prefix + '<a href="https://example.com/very-long-path">link text</a>' + ("y" * 200)
        first, second = split_html_safely(text, 100)
        assert_no_orphan_brackets(first)
        assert_no_orphan_brackets(second)
        assert_balanced(first)
        assert_balanced(second)

    def test_reassembly_recovers_original_modulo_injected_tags(self):
        text = "<i>" + ("word " * 800) + "tail</i>"
        first, second = split_html_safely(text, 1500)
        # First part has </i> injected at end; second part has <i> injected at start.
        assert first.endswith("</i>")
        assert second.startswith("<i>")
        recombined = first[: -len("</i>")] + second[len("<i>") :]
        assert recombined == text

    def test_short_text_returns_empty_remainder(self):
        text = "<b>short</b>"
        first, second = split_html_safely(text, 100)
        assert first == text
        assert second == ""

    def test_split_with_mixed_realistic_content(self):
        text = (
            "<b>Daily Recap</b>\n\n"
            + "\n".join(
                f"• <b>TICK{i}</b> — <code>${100+i}</code> (<i>+{i}.1%</i>) — "
                f"some commentary about why this moved today and what it means "
                f"for the broader portfolio strategy.\n"
                for i in range(60)
            )
            + "\n<b>Bottom line:</b> <code>$48,213</code> total, up <b>3.2%</b>."
        )
        assert len(text) > 4096
        first, second = split_html_safely(text, 4000)
        assert_balanced(first)
        assert_balanced(second)
        assert_no_orphan_brackets(first)
        assert_no_orphan_brackets(second)


# ---------------------------------------------------------------------------
# 10. Real conversation patterns
# ---------------------------------------------------------------------------

class TestConversationPatterns:
    def test_simple_greeting(self):
        text = "Hey! What's on your mind today?"
        out = sanitize_telegram_html(text)
        assert out == text

    def test_short_followup_no_formatting(self):
        text = "Got it. Want me to pull up your portfolio?"
        out = sanitize_telegram_html(text)
        assert out == text

    def test_decision_support_dialog(self):
        text = (
            "Two paths I can see:\n\n"
            "1. <b>Hold</b> — let it ride, accept the volatility.\n"
            "2. <b>Trim</b> — lock in gains on <code>NVDA</code>, redeploy later.\n\n"
            "<i>Which one feels more like you right now?</i>"
        )
        out = sanitize_telegram_html(text)
        assert out == text
        assert_balanced(out)

    def test_link_in_response(self):
        text = (
            'Found a good explainer: '
            '<a href="https://example.com/options-101">Options 101</a>. '
            "Want me to summarize?"
        )
        out = sanitize_telegram_html(text)
        assert '<a href="https://example.com/options-101">' in out
        assert "</a>" in out
        assert_balanced(out)

    def test_streaming_partial_open_tag_balanced(self):
        # Mid-stream: LLM has emitted <b>partial but not </b> yet
        partial = "<b>This is bold and not yet"
        out = sanitize_telegram_html(partial)
        assert out.endswith("</b>")
        assert_balanced(out)

    def test_streaming_partial_nested_balanced(self):
        partial = "<b>bold <i>and italic"
        out = sanitize_telegram_html(partial)
        assert out.endswith("</i></b>")
        assert_balanced(out)
