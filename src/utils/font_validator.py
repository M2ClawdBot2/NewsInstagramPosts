"""
Font file validation — called at CLI startup before any render.

The system HARD FAILS if any required font is missing.
There are no silent fallbacks. This is intentional: a missing font
means the output would use a random system font, breaking brand consistency.
"""

import os
import sys


class FontValidationError(Exception):
    """Raised when a required font file is missing or unreadable."""

    def __init__(self, font_key: str, expected_path: str):
        self.font_key = font_key
        self.expected_path = expected_path
        super().__init__(
            f"\n\n[FONT ERROR] Required font '{font_key}' not found.\n"
            f"  Expected path: {expected_path}\n\n"
            f"  To fix:\n"
            f"  1. Download Barlow font family from Google Fonts:\n"
            f"     https://fonts.google.com/specimen/Barlow+Condensed\n"
            f"     https://fonts.google.com/specimen/Barlow\n"
            f"  2. Place the required TTF files in assets/fonts/\n"
            f"  3. Run: python -m daily_beltway validate-config\n"
        )


def assert_font_readable(path: str, font_key: str) -> None:
    """
    Check that a font file exists and is readable.

    Args:
        path: Absolute or project-relative path to the font file
        font_key: Config key name (e.g. 'headline_font') for error messages

    Raises:
        FontValidationError: If file does not exist or cannot be read
    """
    if not os.path.isfile(path):
        raise FontValidationError(font_key, path)
    try:
        with open(path, "rb") as f:
            f.read(4)  # Just confirm it's readable
    except OSError as e:
        raise FontValidationError(font_key, path) from e


def validate_all_fonts(brand_config: dict, project_root: str) -> None:
    """
    Validate all font entries in brand_config['fonts'].

    Skips keys starting with 'system_' (system fallback paths used only
    by scripts/generate_overlays.py, not the main renderer).

    Args:
        brand_config: Loaded brand.yaml dict
        project_root: Absolute path to the project root directory

    Raises:
        FontValidationError: On first missing font (fails fast)
    """
    fonts = brand_config.get("fonts", {})
    if not fonts:
        print("[WARN] No fonts defined in brand config.", file=sys.stderr)
        return

    for key, rel_path in fonts.items():
        if key.startswith("system_"):
            continue  # System fallbacks are optional (overlays script only)
        abs_path = os.path.join(project_root, rel_path)
        assert_font_readable(abs_path, key)


def validate_logo(brand_config: dict, project_root: str) -> None:
    """
    Validate that the logo file exists and is readable.

    Raises:
        FileNotFoundError: With clear message if logo is missing
    """
    logo_path = brand_config.get("logo", {}).get("path", "")
    abs_path = os.path.join(project_root, logo_path)
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(
            f"\n\n[LOGO ERROR] Logo file not found: {abs_path}\n"
            f"  Place the Daily Beltway logo PNG at:\n"
            f"  {abs_path}\n"
        )
