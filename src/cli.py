"""
Daily Beltway — CLI entrypoint.

Commands:
  generate        Render all outputs for a story + export package
  preview         Render one template to /tmp for quick visual check
  validate-config Check all configs for missing required fields
  list-templates  Show available templates with canvas dimensions
"""

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

# Load .env from project root before anything else
_HERE = Path(__file__).resolve().parent.parent
load_dotenv(_HERE / ".env")

from .exporter.dropbox_exporter import DropboxExporter
from .renderer.ffmpeg_engine import find_ffmpeg, get_ffmpeg_version
from .renderer.image_renderer import ImageRenderer
from .renderer.video_renderer import VideoRenderer
from .templates.loader import build_template_config
from .templates.validator import validate_all
from .utils.font_validator import validate_all_fonts, validate_logo
from .utils.slug import make_story_slug, make_output_dir
from .utils.story_loader import load_story, VALID_TEMPLATE_TYPES
from .templates.loader import load_brand_config, load_template_config


PROJECT_ROOT = str(_HERE)


def _startup_checks(project_root: str) -> tuple[str, str]:
    """
    Run essential startup checks. Returns (ffmpeg_bin, ffmpeg_version).
    Exits with error message on any failure.
    """
    try:
        ffmpeg_bin = find_ffmpeg()
    except EnvironmentError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    brand_path = os.path.join(project_root, "config", "brand.yaml")
    try:
        brand = load_brand_config(brand_path)
        validate_all_fonts(brand, project_root)
        validate_logo(brand, project_root)
    except Exception as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    version = get_ffmpeg_version(ffmpeg_bin)
    return ffmpeg_bin, version


@click.group()
@click.version_option(package_name="daily-beltway", prog_name="daily_beltway")
def cli():
    """Daily Beltway Instagram graphics generator."""


@cli.command()
@click.option(
    "--story", required=True, type=click.Path(exists=True),
    help="Path to story JSON file"
)
@click.option(
    "--output-dir", default=None,
    help="Override output base directory (default: LOCAL_OUTPUT_PATH or output/)"
)
@click.option(
    "--dry-run", is_flag=True,
    help="Print FFmpeg command without executing"
)
def generate(story: str, output_dir: Optional[str], dry_run: bool):
    """Render all outputs for a story and export the package."""
    ffmpeg_bin, ffmpeg_version = _startup_checks(PROJECT_ROOT)

    # Load story
    try:
        story_data = load_story(story, project_root=PROJECT_ROOT)
    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)

    template_type = story_data["template_type"]
    slug = make_story_slug(story_data["title"])

    click.echo(f"Story:    {story_data['title']}")
    click.echo(f"Template: {template_type}")
    click.echo(f"Slug:     {slug}")
    click.echo("")

    # Load config
    try:
        config = build_template_config(template_type, PROJECT_ROOT)
    except Exception as e:
        click.echo(f"[CONFIG ERROR] {e}", err=True)
        sys.exit(1)

    # Determine output path
    base_out = output_dir or os.environ.get("LOCAL_OUTPUT_PATH", os.path.join(PROJECT_ROOT, "output"))
    out_dir = make_output_dir(base_out, slug)
    os.makedirs(out_dir, exist_ok=True)

    additional_files = {}

    if template_type == "video_reel":
        renderer = VideoRenderer(ffmpeg_bin)
        out_file = os.path.join(out_dir, "reel.mp4")
        subtitle_path = story_data.get("subtitle_path")
        try:
            result = renderer.render(config, story_data, out_file,
                                     subtitle_path=subtitle_path, dry_run=dry_run)
        except Exception as e:
            click.echo(f"[RENDER ERROR] {e}", err=True)
            sys.exit(1)

        # Extract cover image
        cover_path = os.path.join(out_dir, "reel_cover.jpg")
        if not dry_run and os.path.isfile(out_file):
            try:
                renderer.render_cover_image(config, out_file, cover_path)
                additional_files["reel_cover.jpg"] = cover_path
                click.echo(f"  Cover:  {cover_path}")
            except Exception as e:
                click.echo(f"  [WARN] Cover extraction failed: {e}", err=True)
    else:
        renderer = ImageRenderer(ffmpeg_bin)
        out_file = os.path.join(out_dir, "post.jpg")
        try:
            result = renderer.render(config, story_data, out_file, dry_run=dry_run)
        except Exception as e:
            click.echo(f"[RENDER ERROR] {e}", err=True)
            sys.exit(1)

    if dry_run:
        click.echo("DRY RUN — FFmpeg command:")
        click.echo(" ".join(str(c) for c in result.ffmpeg_command))
        return

    click.echo(f"  Output: {result.output_path}")
    click.echo(f"  Time:   {result.duration_ms:.0f}ms")

    # Export package
    exporter = DropboxExporter(PROJECT_ROOT)
    try:
        package_dir = exporter.export_package(
            slug=slug,
            story=story_data,
            render_result=result,
            ffmpeg_version=ffmpeg_version,
            additional_files=additional_files,
        )
    except Exception as e:
        click.echo(f"[EXPORT ERROR] {e}", err=True)
        sys.exit(1)

    click.echo("")
    click.echo(f"Package ready: {package_dir}")
    if exporter.use_dropbox_api:
        click.echo(f"Uploaded to Dropbox: {exporter.dropbox_dest}/{slug}")


@cli.command()
@click.option("--story", required=True, type=click.Path(exists=True))
@click.option(
    "--template", required=True,
    type=click.Choice(sorted(VALID_TEMPLATE_TYPES)),
    help="Template type to render"
)
@click.option("--open", "open_after", is_flag=True,
              help="Open rendered file after completion (macOS: uses 'open')")
def preview(story: str, template: str, open_after: bool):
    """Render a single template to /tmp/db_preview/ for quick visual review."""
    ffmpeg_bin, _ = _startup_checks(PROJECT_ROOT)

    try:
        story_data = load_story(story, project_root=PROJECT_ROOT)
    except Exception as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)

    # Override template type for preview
    story_data["template_type"] = template

    try:
        config = build_template_config(template, PROJECT_ROOT)
    except Exception as e:
        click.echo(f"[CONFIG ERROR] {e}", err=True)
        sys.exit(1)

    preview_dir = "/tmp/db_preview"
    os.makedirs(preview_dir, exist_ok=True)

    if template == "video_reel":
        out_file = os.path.join(preview_dir, f"preview_{template}.mp4")
        renderer = VideoRenderer(ffmpeg_bin)
        result = renderer.render(config, story_data, out_file)
    else:
        out_file = os.path.join(preview_dir, f"preview_{template}.jpg")
        renderer = ImageRenderer(ffmpeg_bin)
        result = renderer.render(config, story_data, out_file)

    click.echo(f"Preview: {result.output_path}  ({result.duration_ms:.0f}ms)")

    if open_after:
        subprocess.run(["open", result.output_path], check=False)


@cli.command(name="validate-config")
@click.option(
    "--brand-config",
    default=None,
    help="Path to brand.yaml (default: config/brand.yaml)"
)
def validate_config(brand_config: Optional[str]):
    """Validate brand.yaml and all template YAMLs."""
    brand_path = brand_config or os.path.join(PROJECT_ROOT, "config", "brand.yaml")
    templates_dir = os.path.join(PROJECT_ROOT, "config", "templates")

    try:
        brand = load_brand_config(brand_path)
    except Exception as e:
        click.echo(f"[FAIL] brand.yaml: {e}", err=True)
        sys.exit(1)

    templates = {}
    for yaml_file in sorted(Path(templates_dir).glob("*.yaml")):
        name = yaml_file.stem
        try:
            templates[name] = load_template_config(name, templates_dir)
        except Exception as e:
            click.echo(f"[FAIL] {name}.yaml: {e}", err=True)

    results = validate_all(brand, templates)
    any_error = False
    for config_name, errors in results.items():
        if errors:
            any_error = True
            for err in errors:
                click.echo(f"[FAIL] {config_name}: {err}")
        else:
            click.echo(f"[OK]   {config_name}")

    # Also validate font files and logo
    try:
        validate_all_fonts(brand, PROJECT_ROOT)
        click.echo("[OK]   fonts (all font files found on disk)")
    except Exception as e:
        click.echo(f"[FAIL] fonts: {e}")
        any_error = True

    try:
        validate_logo(brand, PROJECT_ROOT)
        click.echo("[OK]   logo file found on disk")
    except Exception as e:
        click.echo(f"[FAIL] logo: {e}")
        any_error = True

    if any_error:
        sys.exit(1)
    else:
        click.echo("\nAll configs valid.")


@cli.command(name="list-templates")
def list_templates():
    """List all available templates with canvas dimensions."""
    templates_dir = os.path.join(PROJECT_ROOT, "config", "templates")
    click.echo(f"{'Template':<20} {'Canvas':<14} {'Format':<8} Label")
    click.echo("-" * 70)
    for yaml_file in sorted(Path(templates_dir).glob("*.yaml")):
        name = yaml_file.stem
        try:
            t = load_template_config(name, templates_dir)
            w = t.get("canvas_width", "?")
            h = t.get("canvas_height", "?")
            fmt = t.get("export", {}).get("format", "?")
            label = t.get("label", "")
            click.echo(f"{name:<20} {w}x{h:<8} {fmt:<8} {label}")
        except Exception as e:
            click.echo(f"{name:<20} [ERROR] {e}")
