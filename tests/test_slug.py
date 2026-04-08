"""Tests for deterministic slug generation."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import datetime
import pytest
from src.utils.slug import make_story_slug, make_output_dir, _slugify


class TestSlugify:
    def test_lowercase(self):
        assert _slugify("HELLO WORLD") == "hello-world"

    def test_spaces_to_hyphens(self):
        assert _slugify("hello world") == "hello-world"

    def test_special_chars_stripped(self):
        assert _slugify("Trump's 'Big' Win!") == "trumps-big-win"

    def test_multiple_spaces_collapsed(self):
        assert _slugify("hello   world") == "hello-world"

    def test_leading_trailing_hyphens_removed(self):
        assert _slugify("---hello---") == "hello"

    def test_max_length_respected(self):
        long_text = "a " * 100
        result = _slugify(long_text, max_chars=20)
        assert len(result) <= 20

    def test_empty_string(self):
        assert _slugify("") == ""

    def test_numbers_preserved(self):
        assert _slugify("Top 10 Stories of 2026") == "top-10-stories-of-2026"


class TestMakeStorySlug:
    def test_format_with_date(self):
        date = datetime.date(2026, 4, 8)
        result = make_story_slug("Senate Passes Budget", date=date)
        assert result == "2026-04-08_senate-passes-budget"

    def test_date_prefix_always_present(self):
        result = make_story_slug("Test Story")
        assert result[:10].count("-") == 2  # YYYY-MM-DD

    def test_empty_title_uses_fallback(self):
        date = datetime.date(2026, 1, 1)
        result = make_story_slug("   ", date=date)
        assert "untitled-story" in result

    def test_long_title_truncated(self):
        long_title = "This is an extremely long story title that goes on and on forever " * 3
        result = make_story_slug(long_title, date=datetime.date(2026, 1, 1))
        slug_part = result[len("2026-01-01_"):]
        assert len(slug_part) <= 60


class TestMakeOutputDir:
    def test_path_structure(self):
        result = make_output_dir("/app/output", "2026-04-08_test-story")
        assert result == "/app/output/READY_TO_REVIEW/2026-04-08_test-story"

    def test_does_not_create_directory(self):
        # Should just return the path string without side effects
        path = make_output_dir("/nonexistent/path", "slug")
        assert not os.path.exists(path)
