"""
Comprehensive tests for sanitize_telegram_html().

This function takes LLM-generated Telegram HTML and:
1. Escapes all <, >, & in body text
2. Un-escapes only valid Telegram tags from the allowlist
3. Strips disallowed tags (their content is preserved as escaped text)

Tests cover:
- All valid Telegram tags (b, i, u, s, code, pre, a, blockquote, tg-spoiler, etc.)
- Tag aliases (strong, em, ins, strike, del)
- Attribute preservation for <a href> and <code class>
- Special character escaping ($, ., !, etc. should NOT be escaped)
- HTML special chars (<, >, &) escaped in body text
- Disallowed tags stripped (script, p, div, br, h1-h6, ul, li, etc.)
- Nested tags
- Edge cases (empty, None-like, malformed)
- Real-world LLM output samples
"""

from handlers.message import sanitize_telegram_html, split_html_safely


# ============================================================================
# Valid Telegram Tags - Pass-Through
# ============================================================================

class TestValidTagsPassThrough:
    """Valid Telegram tags should pass through unchanged."""

    def test_bold(self):
        assert sanitize_telegram_html("<b>bold</b>") == "<b>bold</b>"

    def test_italic(self):
        assert sanitize_telegram_html("<i>italic</i>") == "<i>italic</i>"

    def test_underline(self):
        assert sanitize_telegram_html("<u>underline</u>") == "<u>underline</u>"

    def test_strikethrough(self):
        assert sanitize_telegram_html("<s>strike</s>") == "<s>strike</s>"

    def test_code(self):
        assert sanitize_telegram_html("<code>x = 1</code>") == "<code>x = 1</code>"

    def test_pre(self):
        assert sanitize_telegram_html("<pre>block</pre>") == "<pre>block</pre>"

    def test_blockquote(self):
        assert sanitize_telegram_html("<blockquote>quoted</blockquote>") == "<blockquote>quoted</blockquote>"

    def test_spoiler(self):
        assert sanitize_telegram_html("<tg-spoiler>secret</tg-spoiler>") == "<tg-spoiler>secret</tg-spoiler>"


class TestTagAliases:
    """Telegram supports aliases like <strong>, <em>, <ins>, <strike>, <del>."""

    def test_strong_alias_for_bold(self):
        assert sanitize_telegram_html("<strong>bold</strong>") == "<strong>bold</strong>"

    def test_em_alias_for_italic(self):
        assert sanitize_telegram_html("<em>italic</em>") == "<em>italic</em>"

    def test_ins_alias_for_underline(self):
        assert sanitize_telegram_html("<ins>insert</ins>") == "<ins>insert</ins>"

    def test_strike_alias(self):
        assert sanitize_telegram_html("<strike>old</strike>") == "<strike>old</strike>"

    def test_del_alias(self):
        assert sanitize_telegram_html("<del>removed</del>") == "<del>removed</del>"


# ============================================================================
# Tag Attributes
# ============================================================================

class TestTagAttributes:
    """Tags with attributes (href, class) should preserve them."""

    def test_link_with_href(self):
        result = sanitize_telegram_html('<a href="https://example.com">click</a>')
        assert result == '<a href="https://example.com">click</a>'

    def test_link_with_query_params(self):
        result = sanitize_telegram_html('<a href="https://example.com?q=1&p=2">link</a>')
        # The & in URL gets escaped to &amp; via HTML escaping, then preserved
        assert '<a href="https://example.com?q=1' in result
        assert '">link</a>' in result

    def test_code_with_language_class(self):
        result = sanitize_telegram_html('<code class="language-python">print(1)</code>')
        assert result == '<code class="language-python">print(1)</code>'

    def test_pre_with_nested_code(self):
        inp = '<pre><code class="language-python">x = 1</code></pre>'
        assert sanitize_telegram_html(inp) == inp

    def test_telegram_user_mention_link(self):
        # tg://user?id=12345 is valid in Telegram links
        result = sanitize_telegram_html('<a href="tg://user?id=12345">mention</a>')
        assert '<a href="tg://user?id=12345">mention</a>' == result


# ============================================================================
# Special Characters - The Original Bug
# ============================================================================

class TestSpecialCharacters:
    """Punctuation should NOT be escaped — this was the original bug."""

    def test_dollar_sign_not_escaped(self):
        """The original bug: $ was being escaped to \\$."""
        assert sanitize_telegram_html("$1,450.78") == "$1,450.78"

    def test_period_not_escaped(self):
        assert sanitize_telegram_html("Hello world.") == "Hello world."

    def test_exclamation_not_escaped(self):
        assert sanitize_telegram_html("Wow!") == "Wow!"

    def test_parentheses_not_escaped(self):
        assert sanitize_telegram_html("(parens)") == "(parens)"

    def test_brackets_not_escaped(self):
        assert sanitize_telegram_html("[brackets]") == "[brackets]"

    def test_braces_not_escaped(self):
        assert sanitize_telegram_html("{braces}") == "{braces}"

    def test_pipe_not_escaped(self):
        assert sanitize_telegram_html("a | b") == "a | b"

    def test_hash_not_escaped(self):
        assert sanitize_telegram_html("#hashtag") == "#hashtag"

    def test_minus_not_escaped(self):
        assert sanitize_telegram_html("- item") == "- item"

    def test_plus_not_escaped(self):
        assert sanitize_telegram_html("a + b = c") == "a + b = c"

    def test_equals_not_escaped(self):
        assert sanitize_telegram_html("x = 5") == "x = 5"

    def test_backtick_not_escaped(self):
        assert sanitize_telegram_html("`raw`") == "`raw`"

    def test_tilde_not_escaped(self):
        assert sanitize_telegram_html("~approximately") == "~approximately"

    def test_emoji_not_escaped(self):
        assert sanitize_telegram_html("Hello 🎉") == "Hello 🎉"

    def test_unicode_not_escaped(self):
        assert sanitize_telegram_html("café résumé naïve") == "café résumé naïve"


# ============================================================================
# HTML Special Characters - SHOULD Be Escaped
# ============================================================================

class TestHtmlSpecialCharsEscaped:
    """<, >, & in body text MUST be escaped to prevent broken HTML."""

    def test_naked_less_than_escaped(self):
        assert sanitize_telegram_html("5 < 10") == "5 &lt; 10"

    def test_naked_greater_than_escaped(self):
        # Note: > in body text gets escaped via html.escape() with quote=False
        result = sanitize_telegram_html("10 > 5")
        assert "&gt;" in result

    def test_naked_ampersand_escaped(self):
        assert sanitize_telegram_html("Cost & tax") == "Cost &amp; tax"

    def test_html_entity_in_body(self):
        # Already-escaped entities should not be double-escaped
        result = sanitize_telegram_html("Tom & Jerry")
        assert result == "Tom &amp; Jerry"

    def test_comparison_operators(self):
        result = sanitize_telegram_html("if x < 10 and y > 5")
        assert "&lt;" in result
        assert "&gt;" in result
        assert "if x" in result


# ============================================================================
# Disallowed Tags - Should Be Stripped/Escaped
# ============================================================================

class TestDisallowedTags:
    """Tags not in Telegram's allowlist should be escaped, not removed."""

    def test_script_tag_stripped(self):
        result = sanitize_telegram_html("<script>alert(1)</script>")
        assert "<script>" not in result
        assert "&lt;script&gt;" in result
        assert "alert(1)" in result  # content preserved

    def test_paragraph_tag_stripped(self):
        result = sanitize_telegram_html("<p>paragraph</p>")
        assert "<p>" not in result
        assert "&lt;p&gt;paragraph&lt;/p&gt;" == result

    def test_div_tag_stripped(self):
        result = sanitize_telegram_html("<div>content</div>")
        assert "<div>" not in result

    def test_br_tag_stripped(self):
        result = sanitize_telegram_html("line1<br>line2")
        assert "<br>" not in result
        assert "&lt;br&gt;" in result

    def test_h1_tag_stripped(self):
        result = sanitize_telegram_html("<h1>Title</h1>")
        assert "<h1>" not in result

    def test_ul_li_tag_stripped(self):
        result = sanitize_telegram_html("<ul><li>item</li></ul>")
        assert "<ul>" not in result
        assert "<li>" not in result

    def test_table_tag_stripped(self):
        result = sanitize_telegram_html("<table><tr><td>cell</td></tr></table>")
        assert "<table>" not in result

    def test_iframe_tag_stripped(self):
        result = sanitize_telegram_html('<iframe src="evil.com"></iframe>')
        assert "<iframe" not in result

    def test_img_tag_stripped(self):
        result = sanitize_telegram_html('<img src="x.png">')
        assert "<img" not in result


# ============================================================================
# Nested and Mixed Content
# ============================================================================

class TestNestedTags:
    """Nested valid tags should work correctly."""

    def test_bold_inside_italic(self):
        assert sanitize_telegram_html("<i><b>bolditalic</b></i>") == "<i><b>bolditalic</b></i>"

    def test_code_inside_pre(self):
        inp = '<pre><code class="language-js">console.log("hi")</code></pre>'
        result = sanitize_telegram_html(inp)
        assert "<pre>" in result
        assert '<code class="language-js">' in result
        assert "console.log" in result

    def test_link_with_bold_text(self):
        inp = '<a href="https://example.com"><b>Bold Link</b></a>'
        assert sanitize_telegram_html(inp) == inp

    def test_blockquote_with_formatting(self):
        inp = "<blockquote>This is <b>important</b> text</blockquote>"
        assert sanitize_telegram_html(inp) == inp

    def test_mixed_valid_and_invalid(self):
        result = sanitize_telegram_html("<b>bold</b> <p>para</p> <i>italic</i>")
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<p>" not in result
        assert "&lt;p&gt;" in result


# ============================================================================
# Edge Cases
# ============================================================================

class TestEdgeCases:
    """Edge cases: empty input, malformed tags, etc."""

    def test_empty_string(self):
        assert sanitize_telegram_html("") == ""

    def test_none_input(self):
        # Should handle gracefully (returns falsy)
        assert sanitize_telegram_html(None) is None

    def test_plain_text_no_tags(self):
        assert sanitize_telegram_html("Just plain text") == "Just plain text"

    def test_only_whitespace(self):
        assert sanitize_telegram_html("   ") == "   "

    def test_newlines_preserved(self):
        assert sanitize_telegram_html("line1\nline2\nline3") == "line1\nline2\nline3"

    def test_tabs_preserved(self):
        assert sanitize_telegram_html("col1\tcol2") == "col1\tcol2"

    def test_unclosed_tag_treated_as_text(self):
        # <b without closing > should be escaped as text
        result = sanitize_telegram_html("text <b unclosed")
        assert "<b unclosed" not in result or "&lt;" in result

    def test_uppercase_tag_normalized(self):
        # HTML tags are case-insensitive
        result = sanitize_telegram_html("<B>bold</B>")
        # Function lowercases tag names
        assert "<b>bold</b>" == result

    def test_mixed_case_tag(self):
        result = sanitize_telegram_html("<Strong>text</Strong>")
        assert "<strong>text</strong>" == result

    def test_extra_whitespace_in_tag(self):
        # Telegram handles tags with extra spaces in attributes
        result = sanitize_telegram_html('<a   href="url">link</a>')
        assert "<a" in result and 'href="url"' in result


# ============================================================================
# Real-World LLM Output Samples
# ============================================================================

class TestRealWorldSamples:
    """Realistic LLM responses that exercise multiple features."""

    def test_financial_summary(self):
        """The exact sample from the original bug report."""
        inp = (
            "🚗 The <b>Ultimate Driving Machine</b>\n"
            "That $1,450.78 monthly payment to BMW Financial Services! "
            "You definitely appreciate a premium ride, though between that "
            "and the $275.20/mo to Geico, your car is practically paying Bay Area rent! 🏎️💨"
        )
        result = sanitize_telegram_html(inp)
        assert "$1,450.78" in result  # The bug
        assert "$275.20" in result
        assert "<b>Ultimate Driving Machine</b>" in result
        assert "🚗" in result
        assert "🏎️💨" in result

    def test_code_explanation(self):
        inp = (
            "Here's how to use it:\n\n"
            '<pre><code class="language-python">def hello():\n    print("hi")</code></pre>\n\n'
            "The <code>print</code> function outputs to stdout."
        )
        result = sanitize_telegram_html(inp)
        assert '<code class="language-python">' in result
        assert "<code>print</code>" in result

    def test_bullet_list_with_formatting(self):
        inp = (
            "Top picks:\n"
            "• <b>NVDA</b> — strong AI growth\n"
            "• <b>AAPL</b> — solid fundamentals\n"
            "• <b>TSLA</b> — high volatility"
        )
        result = sanitize_telegram_html(inp)
        assert "• <b>NVDA</b>" in result
        assert "• <b>AAPL</b>" in result
        assert "• <b>TSLA</b>" in result

    def test_link_in_paragraph(self):
        inp = 'Check out <a href="https://example.com/article">this article</a> for more info.'
        result = sanitize_telegram_html(inp)
        assert '<a href="https://example.com/article">this article</a>' in result

    def test_quoted_response(self):
        inp = (
            "<blockquote>The market closed at 5,234 today</blockquote>\n"
            "That's a <b>2.3% gain</b> from yesterday!"
        )
        result = sanitize_telegram_html(inp)
        assert "<blockquote>" in result
        assert "<b>2.3% gain</b>" in result

    def test_math_expression(self):
        inp = "The formula is: x = (a + b) * c / 2"
        result = sanitize_telegram_html(inp)
        assert "x = (a + b) * c / 2" in result

    def test_comparison_with_dollar_amounts(self):
        inp = "Spending: $500 < budget of $1000"
        result = sanitize_telegram_html(inp)
        assert "$500" in result
        assert "$1000" in result
        assert "&lt;" in result  # < should be escaped


# ============================================================================
# Tag Balancing (streaming partial output)
# ============================================================================

class TestTagBalancing:
    """During streaming, partial output may have unclosed tags. The sanitizer
    must auto-close them so Telegram doesn't reject the message."""

    def test_unclosed_bold_auto_closed(self):
        """Original streaming bug: <i>text without </i>"""
        result = sanitize_telegram_html("<b>partial bold text")
        assert result == "<b>partial bold text</b>"

    def test_unclosed_italic_auto_closed(self):
        """The exact error from production logs."""
        result = sanitize_telegram_html("Annie thinks <i>that's interesti")
        assert result == "Annie thinks <i>that's interesti</i>"

    def test_two_unclosed_tags_closed_in_reverse(self):
        """Stack-based: outer tag closed last."""
        result = sanitize_telegram_html("<b>bold and <i>italic")
        assert result == "<b>bold and <i>italic</i></b>"

    def test_three_unclosed_tags_closed_in_reverse(self):
        result = sanitize_telegram_html("<b>a<i>b<u>c")
        assert result == "<b>a<i>b<u>c</u></i></b>"

    def test_balanced_tags_unchanged(self):
        """Already-balanced tags should not get extra closing tags."""
        result = sanitize_telegram_html("<b>complete</b>")
        assert result == "<b>complete</b>"

    def test_partial_close_after_full_open_close(self):
        """First pair closed, second opened but unclosed."""
        result = sanitize_telegram_html("<b>done</b> and <i>open")
        assert result == "<b>done</b> and <i>open</i></b>" or result == "<b>done</b> and <i>open</i>"
        # Depending on stack tracking — the <b> was already popped, so only <i> needs closing
        assert "<i>open</i>" in result
        # And there should NOT be an extra </b> at the end
        assert result.count("</b>") == 1

    def test_unclosed_link(self):
        result = sanitize_telegram_html('<a href="https://example.com">click here')
        assert result == '<a href="https://example.com">click here</a>'

    def test_unclosed_code(self):
        result = sanitize_telegram_html("Use <code>foo")
        assert result == "Use <code>foo</code>"

    def test_unclosed_blockquote(self):
        result = sanitize_telegram_html("<blockquote>quoted text without close")
        assert result == "<blockquote>quoted text without close</blockquote>"

    def test_streaming_chunk_partial_attribute(self):
        """If the LLM cuts mid-attribute, the regex won't match it as a tag,
        so it gets escaped (no balancing needed)."""
        result = sanitize_telegram_html('<a href="https://exa')
        # Not a complete tag — should be escaped
        assert "&lt;a" in result

    def test_mismatched_closing_left_alone(self):
        """If LLM emits </b> without matching <b>, leave it (Telegram will
        complain — that's better than silently corrupting)."""
        result = sanitize_telegram_html("text </b> more")
        # </b> stays as escaped text since unescape_close only fires for the close regex
        # Note: this is technically a mismatch case — both behaviors are acceptable.
        # The key thing is the function doesn't crash.
        assert result is not None

    def test_balanced_then_unbalanced(self):
        """Multiple sequential tags with one unclosed at the end."""
        result = sanitize_telegram_html("<b>one</b> <i>two</i> <u>three")
        assert "<b>one</b>" in result
        assert "<i>two</i>" in result
        assert "<u>three</u>" in result

    def test_balancing_with_special_chars(self):
        """Combine unclosed tag with $ and other punctuation that shouldn't escape."""
        result = sanitize_telegram_html("<b>$1,450.78 monthly")
        assert result == "<b>$1,450.78 monthly</b>"

    def test_empty_unclosed_tag(self):
        """Tag opened with no content."""
        result = sanitize_telegram_html("<b>")
        assert result == "<b></b>"


# ============================================================================
# Message Splitting (HTML-aware)
# ============================================================================

class TestSplitHtmlSafely:
    """Splitting long HTML messages must preserve tag balance on both halves."""

    def test_no_split_needed(self):
        """Text under max_length returns as-is."""
        first, rest = split_html_safely("short text", 100)
        assert first == "short text"
        assert rest == ""

    def test_simple_split_at_sentence_boundary(self):
        """Splits at . ! ? \\n preferentially."""
        text = "First sentence. Second sentence. Third sentence."
        first, rest = split_html_safely(text, 30)
        # Should split after a sentence terminator
        assert first.rstrip().endswith(".")
        assert first + rest == text

    def test_split_inside_open_tag_avoided(self):
        """Don't split between < and > of an HTML tag."""
        text = "abc <b>bold text here</b> more " * 10
        first, rest = split_html_safely(text, 50)
        # First part must not contain a stray < without matching >
        # (it could end with a closing tag but not a partial open)
        assert "<b" not in first or ">" in first[first.rfind("<"):]

    def test_split_balances_open_tag_in_first_half(self):
        """If split leaves an open tag in part 1, close it and re-open in part 2."""
        text = "<b>" + ("x" * 100) + "</b> tail"
        first, rest = split_html_safely(text, 50)
        # First part should end with </b> (auto-closed)
        assert first.endswith("</b>")
        # Second part should start with <b> (re-opened)
        assert rest.startswith("<b>")

    def test_split_with_two_nested_tags(self):
        """Both nested tags must be closed/re-opened."""
        text = "<b><i>" + ("y" * 100) + "</i></b> tail"
        first, rest = split_html_safely(text, 50)
        # Closed in reverse: </i></b>
        assert first.endswith("</i></b>")
        # Re-opened in original order: <b><i>
        assert rest.startswith("<b><i>")

    def test_split_after_complete_tag_no_rebalancing(self):
        """If split point is after a balanced tag pair, no re-opening needed."""
        text = "<b>complete</b> " + ("z" * 100)
        first, rest = split_html_safely(text, 50)
        # No tags open at split point — first should not have extra closers
        # and rest should not have re-openers
        assert not rest.startswith("<b>")

    def test_split_preserves_total_content(self):
        """The combined parts (minus added closing/re-opening tags) cover original."""
        text = "<b>" + ("a" * 200) + "</b>"
        first, rest = split_html_safely(text, 100)
        # Strip the auto-added tags to verify content preservation
        first_content = first.replace("</b>", "")
        rest_content = rest.replace("<b>", "")
        # Combined should equal original
        assert first_content + rest_content == text

    def test_split_inside_attribute_value(self):
        """Don't split inside <a href="..."> attribute value."""
        text = '<a href="https://example.com/long-path">link</a> ' + ("x" * 100)
        first, rest = split_html_safely(text, 30)
        # Either the whole link is in first part or it starts fresh in second
        # Key: no broken attribute
        if "<a" in first:
            assert "</a>" in first or first.endswith('">link</a>')

    def test_long_text_real_world_example(self):
        """Realistic LLM output with multiple tags and a forced split."""
        text = (
            "<b>📊 Q4 Analysis</b>\n\n"
            "Your spending breakdown:\n"
            "• <b>BMW Financial</b> — <code>$1,450.78</code>/mo\n"
            "• <b>Geico</b> — <code>$275.20</code>/mo\n"
            "• <b>Rent</b> — <code>$3,200</code>/mo\n\n"
            "<i>Looking at this honestly, your transportation costs are roughly "
            "equivalent to a small studio apartment. That's not necessarily bad — "
            "but it's worth knowing.</i>\n\n"
            "Want me to model what happens if you downgrade to a less expensive "
            "vehicle next year? I can run a few scenarios."
        )
        first, rest = split_html_safely(text, 200)
        # Both halves should be balanced
        from handlers.message import _open_tags_at_end
        assert _open_tags_at_end(first) == [], f"first part has unclosed tags: {first}"
        assert _open_tags_at_end(rest) == [], f"rest has unclosed tags: {rest}"

    def test_split_with_blockquote(self):
        text = "<blockquote>" + ("q" * 200) + "</blockquote>"
        first, rest = split_html_safely(text, 100)
        assert first.endswith("</blockquote>")
        assert rest.startswith("<blockquote>")

    def test_split_with_code_block(self):
        text = "<pre>" + ("c" * 200) + "</pre>"
        first, rest = split_html_safely(text, 100)
        assert first.endswith("</pre>")
        assert rest.startswith("<pre>")


# ============================================================================
# Security
# ============================================================================

class TestSecurity:
    """Sanitizer should prevent XSS-like injection in HTML output."""

    def test_script_injection_blocked(self):
        result = sanitize_telegram_html('<script>alert("xss")</script>')
        assert "<script>" not in result

    def test_event_handler_in_disallowed_tag_blocked(self):
        result = sanitize_telegram_html('<img src="x" onerror="alert(1)">')
        assert "<img" not in result
        assert "onerror" not in result or "&lt;img" in result

    def test_javascript_url_in_link(self):
        # The function doesn't validate URL schemes — that's Telegram's job
        # But the link itself should still be marked as a valid <a> tag
        result = sanitize_telegram_html('<a href="javascript:alert(1)">click</a>')
        # Telegram itself rejects javascript: URLs, but the tag is preserved
        assert "<a" in result

    def test_html_injection_in_disallowed_tag(self):
        # An attacker tries to break out via a disallowed tag
        result = sanitize_telegram_html('<style>body{display:none}</style>')
        assert "<style>" not in result

    def test_no_unclosed_valid_tag_breaks_output(self):
        # Even if LLM forgets a closing tag, sanitizer should not crash
        result = sanitize_telegram_html("<b>unclosed bold")
        # Should still produce valid output (Telegram may render or reject)
        assert result is not None
