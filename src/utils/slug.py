"""
Deterministic slug generation for output folder names.

Output format: YYYY-MM-DD_{title-slug}
Example: 2026-04-08_trump-signs-executive-order-on-tariffs
"""

import datetime
import re
from typing import Optional


def _slugify(text: str, max_chars: int = 60) -> str:
    """
    Convert text to lowercase URL/filesystem-safe slug.
    - Lowercase
    - Spaces and underscores → hyphens
    - Non-alphanumeric (except hyphens) stripped
    - Multiple hyphens collapsed to one
    - Leading/trailing hyphens removed
    - Truncated to max_chars
    """
    text = text.lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"[^a-z0-9\-]", "", text)
    text = re.sub(r"-+", "-", text)
    text = text.strip("-")
    return text[:max_chars].rstrip("-")


def make_story_slug(title: str, date: Optional[datetime.date] = None) -> str:
    """
    Create a deterministic, filesystem-safe output folder name.

    Args:
        title: Story title (raw, unescaped)
        date: Date for the slug prefix; defaults to today (UTC)

    Returns:
        String like '2026-04-08_senate-passes-budget-resolution'
    """
    if date is None:
        date = datetime.date.today()
    date_str = date.strftime("%Y-%m-%d")
    slug = _slugify(title)
    if not slug:
        slug = "untitled-story"
    return f"{date_str}_{slug}"


def make_output_dir(base_output_path: str, slug: str) -> str:
    """
    Return the full output directory path for a story.
    Does NOT create the directory.

    Args:
        base_output_path: e.g. '/app/output'
        slug: from make_story_slug()

    Returns:
        '/app/output/READY_TO_REVIEW/2026-04-08_senate-passes-budget-resolution'
    """
    import os
    return os.path.join(base_output_path, "READY_TO_REVIEW", slug)
