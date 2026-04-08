"""
Story JSON loader and validator.

Stories are the input objects that drive all rendering. Every story
must have at minimum: title, short_headline, template_type.
All other fields have safe defaults.
"""

import json
import os
from pathlib import Path
from typing import Optional, Union

VALID_TEMPLATE_TYPES = {
    "breaking_news",
    "engagement_bait",
    "quote_card",
    "reel_cover",
    "carousel_slide",
    "video_reel",
}

VALID_CATEGORIES = {"breaking", "politics", "economy", "opinion", "world", "culture"}

REQUIRED_FIELDS = ["title", "short_headline", "template_type"]

DEFAULTS = {
    "subheadline": "",
    "caption": "",
    "source_url": "",
    "category": "politics",
    "image_path": None,
    "video_path": None,
    "quote_text": None,
    "attribution": None,
    "slide_number": None,
    "total_slides": None,
}


class StoryValidationError(Exception):
    """Raised when a story JSON fails schema validation."""

    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"Story validation error — field '{field}': {message}")


def load_story(json_path: Union[str, Path], project_root: Optional[str] = None) -> dict:
    """
    Load and validate a story JSON file.

    Args:
        json_path: Path to story .json file
        project_root: If provided, resolves relative image/video paths against it

    Returns:
        Validated story dict with defaults applied

    Raises:
        FileNotFoundError: If json_path does not exist
        StoryValidationError: On any schema violation
        json.JSONDecodeError: If file is not valid JSON
    """
    json_path = Path(json_path)
    if not json_path.is_file():
        raise FileNotFoundError(f"Story file not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        story = json.load(f)

    if not isinstance(story, dict):
        raise StoryValidationError("root", "Story must be a JSON object, not a list or scalar")

    # Check required fields
    for field in REQUIRED_FIELDS:
        if not story.get(field):
            raise StoryValidationError(field, f"Required field '{field}' is missing or empty")

    # Validate template_type
    if story["template_type"] not in VALID_TEMPLATE_TYPES:
        raise StoryValidationError(
            "template_type",
            f"'{story['template_type']}' is not a valid template type. "
            f"Choose from: {sorted(VALID_TEMPLATE_TYPES)}",
        )

    # Validate category if present
    if "category" in story and story["category"] not in VALID_CATEGORIES:
        raise StoryValidationError(
            "category",
            f"'{story['category']}' is not valid. Choose from: {sorted(VALID_CATEGORIES)}",
        )

    # Quote card requires quote_text
    if story["template_type"] == "quote_card" and not story.get("quote_text"):
        raise StoryValidationError(
            "quote_text",
            "quote_card template requires a 'quote_text' field",
        )

    # Video reel requires video_path
    if story["template_type"] == "video_reel" and not story.get("video_path"):
        raise StoryValidationError(
            "video_path",
            "video_reel template requires a 'video_path' field",
        )

    # Apply defaults
    story = apply_story_defaults(story)

    # Resolve paths
    if project_root:
        story = _resolve_paths(story, project_root)

    return story


def apply_story_defaults(story: dict) -> dict:
    """Apply default values for optional fields not present in the story."""
    result = dict(DEFAULTS)
    result.update(story)
    # If caption is empty, default to title
    if not result.get("caption"):
        result["caption"] = result["title"]
    return result


def _resolve_paths(story: dict, project_root: str) -> dict:
    """
    Resolve relative image_path and video_path to absolute paths.
    Leaves None values and already-absolute paths unchanged.
    Raises StoryValidationError if specified file does not exist.
    """
    for field in ("image_path", "video_path"):
        val = story.get(field)
        if val is None:
            continue
        p = Path(val)
        if not p.is_absolute():
            p = Path(project_root) / p
        if not p.is_file():
            raise StoryValidationError(
                field,
                f"File not found: {p}\n  Check that '{field}' points to an existing file.",
            )
        story[field] = str(p)
    return story
