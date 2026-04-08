"""Tests for FFmpeg drawtext escaping — the most failure-prone part of the system."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.utils.text_escaper import escape_drawtext, truncate_to_fit, wrap_text


class TestEscapeDrawtext:
    def test_plain_text_unchanged(self):
        assert escape_drawtext("Hello World") == "Hello World"

    def test_backslash_escaped_first(self):
        # "C:\\path" in Python is the string C:\path (C, colon, backslash, p, a, t, h)
        # The escaper must: 1) double the backslash, 2) escape the colon
        # Result: C\:\\path → repr "C\\:\\\\path"
        result = escape_drawtext("C:\\path")
        assert result == "C\\:\\\\path"

    def test_colon_escaped(self):
        result = escape_drawtext("key: value")
        assert result == "key\\: value"

    def test_apostrophe_escaped(self):
        result = escape_drawtext("it's fine")
        assert result == "it\\'s fine"

    def test_percent_escaped(self):
        result = escape_drawtext("100% done")
        assert result == "100%% done"

    def test_combined_special_chars(self):
        result = escape_drawtext("Mike's 50%: done\\now")
        # backslash first: "Mike's 50%: done\\now" → "Mike's 50%: done\\\\now"
        # then colon: → "Mike's 50%\\: done\\\\now"
        # then apostrophe: → "Mike\\'s 50%\\: done\\\\now"
        # then percent: → "Mike\\'s 50%%\\: done\\\\now"
        assert "\\\\\\\\now" not in result  # should not be over-escaped
        assert "50%%" in result
        assert "\\:" in result
        assert "Mike\\'" in result

    def test_null_byte_raises(self):
        with pytest.raises(ValueError, match="null bytes"):
            escape_drawtext("bad\x00char")

    def test_empty_string(self):
        assert escape_drawtext("") == ""

    def test_newline_preserved(self):
        # \n in input is a literal newline character — should not be escaped
        # (callers use \\n for FFmpeg line breaks, not actual newlines)
        result = escape_drawtext("line one\nline two")
        assert "line one" in result
        assert "line two" in result


class TestTruncateToFit:
    def test_short_text_unchanged(self):
        assert truncate_to_fit("Hello", 10) == "Hello"

    def test_exact_length_unchanged(self):
        assert truncate_to_fit("Hello!", 6) == "Hello!"

    def test_truncates_with_ellipsis(self):
        result = truncate_to_fit("Hello World", 8)
        assert result == "Hello..."
        assert len(result) == 8

    def test_custom_ellipsis(self):
        result = truncate_to_fit("Hello World", 7, ellipsis="…")
        assert result.endswith("…")

    def test_empty_string(self):
        assert truncate_to_fit("", 10) == ""


class TestWrapText:
    def test_short_text_single_line(self):
        result = wrap_text("Short headline", 30, 3)
        assert "\\n" not in result
        assert result == "Short headline"

    def test_wraps_at_word_boundary(self):
        result = wrap_text("SENATE PASSES BUDGET RESOLUTION", 20, 3)
        lines = result.split("\\n")
        assert len(lines) > 1
        for line in lines:
            assert len(line) <= 20

    def test_respects_max_lines(self):
        result = wrap_text("one two three four five six seven eight nine ten", 10, 2)
        lines = result.split("\\n")
        assert len(lines) <= 2

    def test_single_word_longer_than_limit(self):
        # Should not crash even if a single word exceeds max_chars_per_line
        result = wrap_text("SUPERLONGWORD", 5, 3)
        assert "SUPERLONGWORD" in result

    def test_empty_text(self):
        result = wrap_text("", 20, 3)
        assert result == ""
