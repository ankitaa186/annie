r"""
Unit tests for markdown_to_telegram_html() — MarkdownV2 backslash-escape stripping.

Covers the full set of 18 MarkdownV2 escape characters per Telegram's spec:
    _ * [ ] ( ) ~ ` > # + - = | { } . !

Background: LLMs (especially when prompted for "Telegram MarkdownV2") emit
backslash-prefixed forms (e.g., "\~75 cal \| 6g protein"). When we render via
HTML parse_mode, those literal backslashes leak through to the user's screen
unless we strip them. The strip block in `markdown_to_telegram_html()` was
originally missing 7 of 18 chars, producing visible \~, \|, \>, \+, \=, \{, \}
in user replies. This test pins the full set so future regressions surface
immediately.

Note on `<`, `>`, `&`: `html.escape()` runs FIRST inside the helper, so by the
time the strip block executes, the LLM's literal "\>" has become "\&gt;" in
the buffer. The strip targets that escaped form, and the assertion here checks
for the rendered "&gt;" output (which Telegram renders as ">").
"""

import pytest

# Import path matches existing tests in this directory.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from handlers.message import markdown_to_telegram_html


# (input, expected) pairs covering all 18 MarkdownV2 escape characters.
# `<`, `>`, `&` survive html.escape() in their entity form; the others
# round-trip to the bare character.
ESCAPE_CASES = [
    (r'\_', '_'),
    (r'\*', '*'),
    (r'\[', '['),
    (r'\]', ']'),
    (r'\(', '('),
    (r'\)', ')'),
    (r'\~', '~'),
    (r'\`', '`'),
    (r'\>', '&gt;'),   # html.escape turns ">" into "&gt;" before strip runs
    (r'\#', '#'),
    (r'\+', '+'),
    (r'\-', '-'),
    (r'\=', '='),
    (r'\|', '|'),
    (r'\{', '{'),
    (r'\}', '}'),
    (r'\.', '.'),
    (r'\!', '!'),
]


@pytest.mark.parametrize("escaped,expected", ESCAPE_CASES)
def test_markdownv2_escape_is_stripped(escaped, expected):
    """Each MarkdownV2 backslash-escape collapses to its bare (or html-entity) form."""
    assert markdown_to_telegram_html(escaped) == expected


def test_combined_realistic_llm_output():
    """
    Mimics a real LLM emission with several escapes interleaved in prose.
    This is the user-visible payload shape that motivated the hotfix.
    """
    raw = r'\~75 cal \| 6g protein \> goal \+ snack \= done'
    expected = '~75 cal | 6g protein &gt; goal + snack = done'
    assert markdown_to_telegram_html(raw) == expected


def test_full_escape_set_in_one_string():
    """All 18 escapes interleaved in a single input render correctly."""
    raw = r'\_\*\[\]\(\)\~\`\>\#\+\-\=\|\{\}\.\!'
    expected = '_*[]()~`&gt;#+-=|{}.!'
    assert markdown_to_telegram_html(raw) == expected


def test_unescaped_chars_unchanged():
    """Plain text containing the same chars (without backslashes) is untouched."""
    # No backslashes — html.escape only transforms <, >, &.
    raw = '~75 cal | 6g protein > goal + snack = done'
    expected = '~75 cal | 6g protein &gt; goal + snack = done'
    assert markdown_to_telegram_html(raw) == expected


def test_lone_backslash_preserved():
    """A backslash NOT followed by an escape char is left alone."""
    # `\n` is not in the MarkdownV2 escape set; the strip block must not touch it.
    raw = r'path\to\file'
    # html.escape doesn't touch backslashes, and no strip rule applies.
    assert markdown_to_telegram_html(raw) == r'path\to\file'
