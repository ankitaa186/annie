"""
Property-based / invariant tests for sanitize_telegram_html and friends.

These tests verify that certain invariants hold for ANY input (not just
hand-picked examples). For each invariant we run 100+ random inputs through
a property check; if any input violates the invariant, that's a real bug.

We use Python's `random` module with a fixed seed for reproducibility — so
failing inputs are deterministic across runs and easy to debug.

Functions under test (in handlers/message.py):
  - sanitize_telegram_html
  - _balance_telegram_tags
  - _open_tags_at_end
  - split_html_safely

KNOWN REAL BUGS surfaced by these tests (as of writing):

  Bug 1 — sanitize_telegram_html is NOT idempotent.
    Example: sanitize("<")          == "&lt;"
             sanitize("&lt;")        == "&amp;lt;"   # double-escaped!
             sanitize(sanitize("<")) == "&amp;lt;"
    Impact: Re-sanitizing already-sanitized text mangles it. This will bite
    any code path that runs sanitize on text that may already have been
    sanitized (e.g. retry, append-then-resend during streaming, etc.).
    Root cause: html.escape() in step 1 escapes the `&` of existing
    `&lt;`/`&gt;`/`&amp;` entities, and step 2's regex only un-escapes
    valid Telegram tags — leaving `&amp;lt;` everywhere else.
    Fix: detect already-escaped entities and skip re-escaping their `&`,
    or operate only on a deescaped intermediate.

  Bug 2 — split_html_safely splits inside HTML entities.
    Example: text="...&gt;3]..." split_point lands inside `&gt;`,
             producing "...&gt" in part 1 and ";3]..." in part 2.
    The "don't split inside a tag" guard only avoids `<...>` boundaries;
    it doesn't avoid `&...;` entity boundaries.
    Fix: extend the boundary check to also walk back past any `&` whose
    matching `;` is past split_point.
"""

from __future__ import annotations

import html
import random
import re

import pytest

from handlers.message import (
    _TELEGRAM_ALLOWED_TAGS,
    _open_tags_at_end,
    sanitize_telegram_html,
    split_html_safely,
)


# ---------------------------------------------------------------------------
# Random input generators (seeded for reproducibility)
# ---------------------------------------------------------------------------

# Mix of valid Telegram tags and disallowed ones, to exercise both paths.
_TAG_POOL = [
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "a", "blockquote", "tg-spoiler",
    "p", "div", "script", "iframe", "style", "object", "h1", "h2",
    "br", "span", "img", "form", "input",
]

# Body characters that should NEVER be backslash-escaped by the sanitizer.
_BODY_CHARS = "abcdefghijklmnopqrstuvwxyz ABCDEF 0123456789 .!?$<>&-_()[]{}'\"\n"


def random_html_input(rng: random.Random, max_parts: int = 30) -> str:
    """Generate a random text with random HTML-ish tags interspersed."""
    parts: list[str] = []
    for _ in range(rng.randint(1, max_parts)):
        roll = rng.random()
        if roll < 0.25:
            tag = rng.choice(_TAG_POOL)
            # Sometimes add an attribute
            if tag == "a" and rng.random() < 0.6:
                parts.append(f'<a href="https://example.com/{rng.randint(1, 99)}">')
            elif rng.random() < 0.15:
                parts.append(f'<{tag} class="x">')
            else:
                parts.append(f"<{tag}>")
        elif roll < 0.40:
            tag = rng.choice(_TAG_POOL)
            parts.append(f"</{tag}>")
        elif roll < 0.50:
            # Drop a malformed tag fragment
            parts.append(rng.choice(["<", ">", "<<", ">>", "< b >", "<b", "b>"]))
        else:
            n = rng.randint(1, 25)
            parts.append("".join(rng.choices(_BODY_CHARS, k=n)))
    return "".join(parts)


# Body chars guaranteed not to need escaping by sanitize: no <, >, or &.
_SAFE_BODY_CHARS = "abcdefghijklmnopqrstuvwxyz ABCDEF 0123456789 .!?$-_()[]{}'\"\n"


def random_balanced_html(rng: random.Random) -> str:
    """Generate a deliberately balanced random HTML string of allowed tags.

    Body text uses only chars that don't require HTML escaping, so the result
    is already a valid (and idempotent) Telegram HTML string.
    """
    allowed = sorted(_TELEGRAM_ALLOWED_TAGS)
    out: list[str] = []
    stack: list[str] = []
    for _ in range(rng.randint(1, 20)):
        roll = rng.random()
        if roll < 0.3 and stack:
            tag = stack.pop()
            out.append(f"</{tag}>")
        elif roll < 0.6:
            tag = rng.choice(allowed)
            stack.append(tag)
            out.append(f"<{tag}>")
        else:
            n = rng.randint(1, 15)
            out.append("".join(rng.choices(_SAFE_BODY_CHARS, k=n)))
    while stack:
        out.append(f"</{stack.pop()}>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Strips real (unescaped) tags. Anything still escaped (&lt;p&gt;) is left alone.
_TAG_STRIP_RE = re.compile(r"<[^>]*>")

# Strips ONLY allowed Telegram tags (real, not escaped). Disallowed tags survive
# as literal text (matching sanitize_telegram_html's behaviour of escaping them).
_ALLOWED_TAG_NAMES_RE = "|".join(re.escape(t) for t in sorted(_TELEGRAM_ALLOWED_TAGS, key=len, reverse=True))
_ALLOWED_TAG_STRIP_RE = re.compile(
    # Attribute portion must not contain < or > (so we don't gobble across
    # adjacent malformed tags in the input).
    rf"</?(?:{_ALLOWED_TAG_NAMES_RE})(?:\s[^<>]*)?>",
    re.IGNORECASE,
)


def visible_text(s: str) -> str:
    """Return the visible text content of an HTML string (strips ALL tags)."""
    no_tags = _TAG_STRIP_RE.sub("", s)
    return html.unescape(no_tags)


def visible_text_allowed_only(s: str) -> str:
    """Return visible text after stripping ONLY allowed Telegram tags.

    This matches sanitize_telegram_html's contract: disallowed tags become
    escaped literal text and should be visible to the user.
    """
    no_allowed = _ALLOWED_TAG_STRIP_RE.sub("", s)
    return html.unescape(no_allowed)


def gen_inputs(seed: int, n: int = 120) -> list[str]:
    rng = random.Random(seed)
    inputs = ["", " ", "<", ">", "&", "<b>", "</b>", "<b>x"]
    for _ in range(n):
        inputs.append(random_html_input(rng))
    return inputs


def _summarize(failures: list, label: str, k: int = 3) -> str:
    """Format up to `k` example failures for an assertion message."""
    head = "\n".join(f"  [{i}] {f!r}" for i, f in enumerate(failures[:k]))
    return f"{label}: {len(failures)} failures. First {min(k, len(failures))}:\n{head}"


# ---------------------------------------------------------------------------
# Invariant 1: sanitize is idempotent
# ---------------------------------------------------------------------------

class TestIdempotence:
    """sanitize(sanitize(x)) == sanitize(x) for all x."""

    def test_idempotent(self):
        failures = []
        for inp in gen_inputs(seed=1):
            once = sanitize_telegram_html(inp)
            twice = sanitize_telegram_html(once)
            if once != twice:
                failures.append((inp, once, twice))
        assert not failures, _summarize(failures, "sanitize is not idempotent")


# ---------------------------------------------------------------------------
# Invariant 2: sanitize output has balanced tags
# ---------------------------------------------------------------------------

class TestBalancedAfterSanitize:
    """_open_tags_at_end(sanitize(x)) == [] for all x."""

    def test_balanced(self):
        failures = []
        for inp in gen_inputs(seed=2):
            out = sanitize_telegram_html(inp)
            still_open = _open_tags_at_end(out)
            if still_open:
                failures.append((inp, out, still_open))
        assert not failures, _summarize(failures, "sanitize left output unbalanced")


# ---------------------------------------------------------------------------
# Invariant 3: visible text content is preserved
# ---------------------------------------------------------------------------

class TestContentPreservation:
    """The visible (tag-stripped, entity-decoded) text is preserved by sanitize.

    Note: sanitize may *append* closing tags for unclosed open tags, but those
    closing tags are themselves tags (not visible text), so they vanish after
    stripping. So visible_text(input) should equal visible_text(output).
    """

    def test_preserves_visible_text(self):
        failures = []
        for inp in gen_inputs(seed=3):
            # Use the "allowed-only" stripper: disallowed tags survive as
            # visible text per the sanitizer's contract.
            before = visible_text_allowed_only(inp)
            after = visible_text_allowed_only(sanitize_telegram_html(inp))
            if before != after:
                failures.append((inp, before, after))
        assert not failures, _summarize(failures, "visible text changed by sanitize")


# ---------------------------------------------------------------------------
# Invariant 4: no literal backslash escapes
# ---------------------------------------------------------------------------

class TestNoBackslashEscapes:
    """sanitize must never introduce \\$, \\., \\!, \\-, \\(, \\) into the output.

    These are MarkdownV2 escape artifacts; in HTML mode they should be plain
    punctuation.
    """

    FORBIDDEN = [r"\$", r"\.", r"\!", r"\-", r"\(", r"\)"]

    def test_no_escapes_introduced(self):
        failures = []
        # Inputs that don't already contain backslash escapes
        for inp in gen_inputs(seed=4):
            if any(seq in inp for seq in self.FORBIDDEN):
                continue
            out = sanitize_telegram_html(inp)
            for seq in self.FORBIDDEN:
                if seq in out:
                    failures.append((inp, out, seq))
                    break
        assert not failures, _summarize(failures, "sanitize introduced backslash escapes")


# ---------------------------------------------------------------------------
# Invariant 5: only allowlisted tags survive as real tags
# ---------------------------------------------------------------------------

class TestAllowedTagsOnly:
    """Every real <tag> in sanitize output must be in the Telegram allowlist."""

    REAL_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>")

    def test_only_allowed(self):
        failures = []
        for inp in gen_inputs(seed=5):
            out = sanitize_telegram_html(inp)
            for m in self.REAL_TAG_RE.finditer(out):
                tag = m.group(2).lower()
                if tag not in _TELEGRAM_ALLOWED_TAGS:
                    failures.append((inp, out, tag))
                    break
        assert not failures, _summarize(failures, "disallowed real tags found in output")


# ---------------------------------------------------------------------------
# Invariant 6: split returns balanced parts and preserves visible content
# ---------------------------------------------------------------------------

class TestSplitBalanceAndContent:
    """split_html_safely should produce a balanced first part, balanced
    remainder (modulo additional splits), and preserve total visible text."""

    def test_split_balance_and_content(self):
        failures = []
        rng = random.Random(6)
        for _ in range(150):
            # Build a sanitized input (so it's well-formed HTML to start)
            raw = random_html_input(rng)
            text = sanitize_telegram_html(raw)
            if not text:
                continue
            # Pick a max_length somewhere in the middle
            if len(text) <= 4:
                continue
            max_length = rng.randint(2, max(2, len(text) - 1))

            first, rest = split_html_safely(text, max_length)

            # Both parts must be balanced.
            if _open_tags_at_end(first) != []:
                failures.append(("first_unbalanced", text, max_length, first, rest))
                continue
            if _open_tags_at_end(rest) != []:
                failures.append(("rest_unbalanced", text, max_length, first, rest))
                continue

            # Visible text must be preserved across the split.
            before = visible_text(text)
            after = visible_text(first) + visible_text(rest)
            if before != after:
                failures.append(("content_changed", text, max_length, before, after))
                continue

        assert not failures, _summarize(failures, "split_html_safely violated balance/content")


# ---------------------------------------------------------------------------
# Invariant 7: split is roughly length-bounded
# ---------------------------------------------------------------------------

class TestSplitLengthBound:
    """The first part of a split should not exceed max_length by more than
    the overhead of appended closing tags.

    Worst-case overhead: all allowed tags open at split point, each closed with
    "</tagname>" — pre is the longest at 6 chars name → "</pre>" (6) etc.
    Cap at 200 chars (very generous; real overhead is typically <30).
    """

    OVERHEAD_BUDGET = 200

    def test_length_bounded(self):
        failures = []
        rng = random.Random(7)
        for _ in range(150):
            text = sanitize_telegram_html(random_html_input(rng))
            if len(text) <= 4:
                continue
            max_length = rng.randint(2, max(2, len(text) - 1))
            first, _rest = split_html_safely(text, max_length)
            if len(first) > max_length + self.OVERHEAD_BUDGET:
                failures.append((text, max_length, len(first)))
        assert not failures, _summarize(failures, "split_html_safely first part exceeded length budget")


# ---------------------------------------------------------------------------
# Invariant 8: stack consistency in _open_tags_at_end
# ---------------------------------------------------------------------------

class TestStackConsistency:
    """Walking _open_tags_at_end should never produce a negative-depth state.

    This checks an internal invariant: every popped tag matched a previously
    pushed tag (i.e. the function never tries to pop from an empty stack).
    Mismatched closes are silently ignored, so the stack length is monotonic
    in the sense that it never goes below zero. We re-implement the walk and
    assert depth >= 0 at every step.
    """

    TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)((?:\s[^>]*)?)>")

    def test_stack_never_negative(self):
        failures = []
        for inp in gen_inputs(seed=8):
            text = sanitize_telegram_html(inp)
            depth = 0
            min_depth = 0
            stack: list[str] = []
            for m in self.TAG_RE.finditer(text):
                is_close = bool(m.group(1))
                tag = m.group(2).lower()
                if tag not in _TELEGRAM_ALLOWED_TAGS:
                    continue
                if is_close:
                    if stack and stack[-1] == tag:
                        stack.pop()
                        depth -= 1
                else:
                    stack.append(tag)
                    depth += 1
                if depth < min_depth:
                    min_depth = depth
            if min_depth < 0:
                failures.append((inp, text, min_depth))
            # Final invariant: balanced after sanitize → depth back to 0
            if depth != 0:
                failures.append((inp, text, depth))
        assert not failures, _summarize(failures, "stack walk produced inconsistent depth")


# ---------------------------------------------------------------------------
# Invariant 9: concatenation of two sanitized strings sanitizes to itself
# ---------------------------------------------------------------------------

class TestConcatenationSafety:
    """If A and B are fixed points of sanitize, then sanitize(A + B) == A + B.

    This catches bugs where the boundary between two valid HTML strings
    creates parser confusion (e.g. attribute regex eating across the join).
    """

    def test_concat_is_fixed_point(self):
        failures = []
        rng = random.Random(9)
        # Build a pool of guaranteed-fixed-point HTML strings (balanced
        # allowed-tag HTML with safe body text — no <, >, or & to escape).
        pool = [random_balanced_html(rng) for _ in range(40)]
        # Sanity-check the pool: each element must already be a fixed point.
        for s in pool:
            assert sanitize_telegram_html(s) == s, f"pool element not a fixed point: {s!r}"
        for _ in range(150):
            a = rng.choice(pool)
            b = rng.choice(pool)
            joined = a + b
            sanitized = sanitize_telegram_html(joined)
            if sanitized != joined:
                failures.append((a, b, joined, sanitized))
        assert not failures, _summarize(failures, "concatenation of fixed points is not a fixed point")


# ---------------------------------------------------------------------------
# Invariant 10: no injection — script/iframe/style never become real tags
# ---------------------------------------------------------------------------

class TestNoInjection:
    """Inputs containing dangerous tags must never produce them as real tags."""

    DANGEROUS = ["script", "iframe", "style", "object", "embed", "form", "img"]
    REAL_TAG_RE = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9-]*)(?:\s[^>]*)?>")

    def test_no_dangerous_tags(self):
        rng = random.Random(10)
        # Targeted payloads
        payloads = [
            "<script>alert(1)</script>",
            "<iframe src='evil'></iframe>",
            "<style>body{}</style>",
            "<object data='x'></object>",
            "<img src=x onerror=alert(1)>",
            "javascript:alert(1)",
            "<script><b>bold</b></script>",
            "<SCRIPT>x</SCRIPT>",
            "<b><script>x</script></b>",
            "hello <script>evil</script> world",
        ]
        # Plus random fuzz
        for _ in range(120):
            payloads.append(random_html_input(rng))

        failures = []
        for inp in payloads:
            out = sanitize_telegram_html(inp)
            for m in self.REAL_TAG_RE.finditer(out):
                tag = m.group(2).lower()
                if tag in self.DANGEROUS:
                    failures.append((inp, out, tag))
                    break
            # The literal substring "<script" (case-insensitive) shouldn't
            # appear as a real tag opener in the output.
            if re.search(r"<script\b", out, re.IGNORECASE):
                failures.append((inp, out, "literal <script"))
        assert not failures, _summarize(failures, "dangerous tag injection in output")


# ---------------------------------------------------------------------------
# Bonus: balanced random HTML round-trips through sanitize unchanged
# ---------------------------------------------------------------------------

class TestBalancedRoundTrip:
    """Inputs that are already valid Telegram HTML should pass through
    sanitize unchanged."""

    def test_balanced_round_trip(self):
        failures = []
        rng = random.Random(11)
        for _ in range(150):
            inp = random_balanced_html(rng)
            out = sanitize_telegram_html(inp)
            if out != inp:
                failures.append((inp, out))
        assert not failures, _summarize(failures, "balanced HTML changed by sanitize")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
