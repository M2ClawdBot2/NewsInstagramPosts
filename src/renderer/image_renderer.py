"""
Image renderer — orchestrates rendering of all image-based templates.

Dispatches to filtergraph builders based on template_type,
then calls ffmpeg_engine to execute the render.
"""

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List

from .ffmpeg_engine import build_image_command, run_ffmpeg
from .filtergraph import build_image_filtergraph
from ..templates.loader import TemplateConfig


@dataclass
class RenderResult:
    """Returned by every render call."""
    output_path: str
    ffmpeg_command: list[str]     # Full command list for internal_notes.txt
    duration_ms: float            # Wall-clock render time
    template_type: str
    success: bool = True
    error: Optional[str] = None


class ImageRenderer:
    """Renders all image-based templates (JPEG / PNG)."""

    def __init__(self, ffmpeg_bin: str):
        self.ffmpeg_bin = ffmpeg_bin

    def render(
        self,
        config: TemplateConfig,
        story: dict,
        output_path: str,
        dry_run: bool = False,
    ) -> RenderResult:
        """
        Main entry point. Selects source media, builds filtergraph,
        constructs command, and executes render.

        Args:
            config: Merged TemplateConfig
            story: Validated story dict
            output_path: Absolute path for output file
            dry_run: If True, returns command without executing FFmpeg

        Returns:
            RenderResult
        """
        t0 = time.time()
        template_type = config.template["template_type"]
        output_format = config.export_format  # 'jpeg' or 'png'

        # Gather inputs
        source = self._resolve_source(story, config)
        logo = config.logo_abs_path
        overlay = self._find_overlay(config)

        inputs = [source, logo]
        if overlay:
            inputs.append(overlay)

        # Build filtergraph
        fg = build_image_filtergraph(config, story, num_inputs=len(inputs))
        filter_complex = fg.build()

        # Build FFmpeg command
        quality = config.brand.get("export", {}).get("jpeg_quality", 2)
        cmd = build_image_command(
            ffmpeg_bin=self.ffmpeg_bin,
            inputs=inputs,
            filter_complex=filter_complex,
            output_path=output_path,
            quality=quality,
            output_format=output_format,
        )

        if dry_run:
            duration_ms = (time.time() - t0) * 1000
            return RenderResult(
                output_path=output_path,
                ffmpeg_command=cmd,
                duration_ms=duration_ms,
                template_type=template_type,
            )

        # Execute
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        run_ffmpeg(cmd)
        duration_ms = (time.time() - t0) * 1000

        return RenderResult(
            output_path=output_path,
            ffmpeg_command=cmd,
            duration_ms=duration_ms,
            template_type=template_type,
        )

    def _resolve_source(self, story: dict, config: TemplateConfig) -> str:
        """
        Return the source image path.
        Falls back to the solid navy background if no image_path provided.
        """
        image_path = story.get("image_path")
        if image_path and os.path.isfile(image_path):
            return image_path

        # Fallback: solid navy background
        fallback = os.path.join(
            config.project_root, "assets", "backgrounds", "solid_navy_1080x1080.png"
        )
        if os.path.isfile(fallback):
            return fallback

        raise FileNotFoundError(
            f"No image source found for story '{story.get('title', '?')}'\n"
            f"  Set 'image_path' in the story JSON, or generate the navy fallback:\n"
            f"    python scripts/generate_overlays.py"
        )

    def _find_overlay(self, config: TemplateConfig) -> Optional[str]:
        """
        Return path to gradient overlay PNG if it exists and is configured.
        Returns None if not available (filtergraph falls back to drawbox).
        """
        gradient_cfg = config.brand.get("gradient", {})
        if not gradient_cfg.get("use_overlay_png", True):
            return None

        overlay_dir = config.abs_path(gradient_cfg.get("overlay_dir", "assets/overlays"))
        W = config.canvas_width
        H = config.canvas_height
        filename = f"gradient_bottom_{W}x{H}.png"
        path = os.path.join(overlay_dir, filename)
        return path if os.path.isfile(path) else None
