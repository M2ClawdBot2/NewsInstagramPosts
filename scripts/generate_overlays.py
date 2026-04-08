#!/usr/bin/env python3
"""
Generate gradient overlay PNG files used by the rendering pipeline.

These are pre-baked semi-transparent PNGs with a dark gradient that fades
from transparent at the top to opaque dark at the bottom. They are composited
over source images using FFmpeg's overlay filter for smooth, realistic gradients.

This script only needs to be run once (or after changing gradient settings).

Usage:
    python scripts/generate_overlays.py

Requirements:
    - ffmpeg must be installed (brew install ffmpeg / apt install ffmpeg)
    - Run from the project root directory (daily-beltway/)

Outputs:
    assets/overlays/gradient_bottom_1080x1080.png
    assets/overlays/gradient_bottom_1080x1920.png
    assets/backgrounds/solid_navy_1080x1080.png  (emergency fallback)
"""

import os
import subprocess
import sys


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_ffmpeg() -> str:
    import shutil
    env_bin = os.environ.get("FFMPEG_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin
    which = shutil.which("ffmpeg")
    if which:
        return which
    for p in ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"]:
        if os.path.isfile(p):
            return p
    print("ERROR: ffmpeg not found. Install it first:", file=sys.stderr)
    print("  macOS:  brew install ffmpeg", file=sys.stderr)
    print("  Ubuntu: sudo apt install ffmpeg", file=sys.stderr)
    sys.exit(1)


def run(cmd: list[str], desc: str) -> None:
    print(f"  Generating: {desc}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    print(f"  Done.")


def generate_gradient_overlay(ffmpeg: str, width: int, height: int, output_path: str) -> None:
    """
    Generate a gradient overlay PNG: transparent at top, dark navy at bottom.

    Technique: use geq filter to create per-pixel alpha channel that increases
    from 0 at the top to max_alpha at the bottom start point (55% from top).

    The gradient covers the bottom 55% of the frame, going from fully transparent
    at the 45% mark to fully opaque (navy at 82% opacity) at the bottom.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Brand colors
    navy_r, navy_g, navy_b = 27, 42, 74   # #1B2A4A
    max_alpha = int(0.82 * 255)             # 82% opacity at bottom

    # gradient starts at 45% from top = height * 0.45
    grad_start_y = int(height * 0.45)
    grad_height = height - grad_start_y

    # geq: above grad_start_y → alpha=0; below → alpha increases linearly
    alpha_expr = (
        f"if(lt(Y,{grad_start_y}),0,"
        f"({max_alpha}*(Y-{grad_start_y})/{grad_height}))"
    )

    filter_complex = (
        f"color=c=0x1B2A4A:s={width}x{height}:d=1[base];"
        f"[base]geq="
        f"r={navy_r}:g={navy_g}:b={navy_b}:"
        f"a='{alpha_expr}'[final]"
    )

    cmd = [
        ffmpeg, "-y", "-loglevel", "warning",
        "-f", "lavfi", "-i", f"color=c=black:s={width}x{height}:d=1",
        "-filter_complex", filter_complex,
        "-map", "[final]",
        "-frames:v", "1",
        "-compression_level", "0",
        output_path,
    ]
    run(cmd, os.path.basename(output_path))


def generate_solid_background(ffmpeg: str, width: int, height: int, output_path: str) -> None:
    """Generate a solid navy background PNG (used as fallback when no image_path is set)."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    cmd = [
        ffmpeg, "-y", "-loglevel", "warning",
        "-f", "lavfi",
        "-i", f"color=c=0x1B2A4A:s={width}x{height}:d=1",
        "-frames:v", "1",
        "-compression_level", "0",
        output_path,
    ]
    run(cmd, os.path.basename(output_path))


def main():
    ffmpeg = find_ffmpeg()
    print(f"Using FFmpeg: {ffmpeg}")
    print()

    overlays_dir = os.path.join(PROJECT_ROOT, "assets", "overlays")
    backgrounds_dir = os.path.join(PROJECT_ROOT, "assets", "backgrounds")

    print("Generating gradient overlays...")
    generate_gradient_overlay(ffmpeg, 1080, 1080,
        os.path.join(overlays_dir, "gradient_bottom_1080x1080.png"))
    generate_gradient_overlay(ffmpeg, 1080, 1920,
        os.path.join(overlays_dir, "gradient_bottom_1080x1920.png"))

    print()
    print("Generating solid backgrounds...")
    generate_solid_background(ffmpeg, 1080, 1080,
        os.path.join(backgrounds_dir, "solid_navy_1080x1080.png"))

    print()
    print("All assets generated successfully.")
    print()
    print("Next steps:")
    print("  1. Place assets/logos/daily_beltway_logo.png  (the actual logo)")
    print("  2. Place font TTF files in assets/fonts/")
    print("  3. Run: python -m daily_beltway validate-config")
    print("  4. Run: python -m daily_beltway generate --story stories/sample_story.json")


if __name__ == "__main__":
    main()
