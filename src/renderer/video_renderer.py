"""
Video renderer — orchestrates rendering of video_reel template.

Handles:
- Blur-pad background from horizontal source video
- Lower-third branded strip
- Logo overlay
- Subtitle burn-in (second FFmpeg pass if SRT file provided)
- Cover image extraction
"""

import os
import time
from pathlib import Path
from typing import Optional

from .ffmpeg_engine import (
    build_video_command,
    extract_cover_frame,
    run_ffmpeg,
    FFmpegError,
)
from .filtergraph import build_video_filtergraph
from .image_renderer import RenderResult
from ..templates.loader import TemplateConfig


class VideoRenderer:
    """Renders video_reel template to 1080x1920 MP4."""

    def __init__(self, ffmpeg_bin: str):
        self.ffmpeg_bin = ffmpeg_bin

    def render(
        self,
        config: TemplateConfig,
        story: dict,
        output_path: str,
        subtitle_path: Optional[str] = None,
        dry_run: bool = False,
    ) -> RenderResult:
        """
        Render a video reel.

        Args:
            config: Merged TemplateConfig for video_reel
            story: Validated story dict (must have video_path)
            output_path: Destination .mp4 path
            subtitle_path: Optional path to .srt subtitle file
            dry_run: If True, return command without executing

        Returns:
            RenderResult
        """
        t0 = time.time()
        template_type = "video_reel"

        video_source = story.get("video_path")
        if not video_source or not os.path.isfile(video_source):
            raise FileNotFoundError(
                f"video_path not found: {video_source}\n"
                f"  Set 'video_path' in the story JSON to a valid video file."
            )

        logo = config.logo_abs_path

        # Build filtergraph (video has no gradient overlay PNG)
        inputs = [video_source, logo]
        fg = build_video_filtergraph(config, story)
        filter_complex = fg.build()

        # Export settings
        export = config.template.get("export", {})
        crf = export.get("crf", config.brand["export"]["video_crf"])
        preset = export.get("preset", config.brand["export"]["video_preset"])
        pix_fmt = export.get("pix_fmt", config.brand["export"]["video_pix_fmt"])
        fps = export.get("fps", config.brand["export"]["video_fps"])
        audio_codec = export.get("audio_codec", config.brand["export"]["audio_codec"])
        audio_bitrate = export.get("audio_bitrate", config.brand["export"]["audio_bitrate"])

        cmd = build_video_command(
            ffmpeg_bin=self.ffmpeg_bin,
            inputs=inputs,
            filter_complex=filter_complex,
            output_path=output_path,
            crf=crf,
            fps=fps,
            preset=preset,
            pix_fmt=pix_fmt,
            audio_codec=audio_codec,
            audio_bitrate=audio_bitrate,
            has_audio=True,
        )

        if dry_run:
            return RenderResult(
                output_path=output_path,
                ffmpeg_command=cmd,
                duration_ms=(time.time() - t0) * 1000,
                template_type=template_type,
            )

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        run_ffmpeg(cmd)

        # Optional subtitle burn-in (second pass)
        if subtitle_path and os.path.isfile(subtitle_path):
            output_path = self._burn_subtitles(
                config, output_path, subtitle_path, crf, preset, pix_fmt, fps
            )

        duration_ms = (time.time() - t0) * 1000
        return RenderResult(
            output_path=output_path,
            ffmpeg_command=cmd,
            duration_ms=duration_ms,
            template_type=template_type,
        )

    def render_cover_image(
        self,
        config: TemplateConfig,
        rendered_video_path: str,
        output_path: str,
    ) -> str:
        """
        Extract a cover image from the rendered video.

        Args:
            config: TemplateConfig (for cover_image.extract_second setting)
            rendered_video_path: Path to the rendered .mp4
            output_path: Destination .jpg path

        Returns:
            output_path
        """
        cover_cfg = config.template.get("cover_image", {})
        ts = cover_cfg.get("extract_second", 0.5)
        quality = config.brand["export"]["jpeg_quality"]

        cmd = extract_cover_frame(
            ffmpeg_bin=self.ffmpeg_bin,
            video_path=rendered_video_path,
            output_path=output_path,
            timestamp_seconds=ts,
            quality=quality,
        )
        run_ffmpeg(cmd)
        return output_path

    def _burn_subtitles(
        self,
        config: TemplateConfig,
        video_path: str,
        subtitle_path: str,
        crf: int,
        preset: str,
        pix_fmt: str,
        fps: int,
    ) -> str:
        """
        Burn SRT subtitles into the rendered video (second FFmpeg pass).
        Overwrites the input file in-place (via temp path).

        Returns:
            Path to the final video with subtitles burned in
        """
        sub_style = config.template.get("subtitles", {}).get(
            "force_style",
            "FontName=Arial,FontSize=38,PrimaryColour=&HFFFFFF,OutlineColour=&H000000,Outline=2,Alignment=2,MarginV=240",
        )
        # Clean up the style string (remove newlines from YAML folded scalar)
        sub_style = " ".join(sub_style.split())

        temp_path = video_path.replace(".mp4", "_subbed.mp4")

        # Escape subtitle path for FFmpeg subtitles filter (colons on Windows paths)
        safe_sub_path = subtitle_path.replace("\\", "/").replace(":", "\\:")

        filter_complex = f"[0:v]subtitles={safe_sub_path}:force_style='{sub_style}'[final]"

        cmd = [
            self.ffmpeg_bin, "-y", "-loglevel", "warning",
            "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[final]",
            "-map", "0:a?",
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", preset,
            "-pix_fmt", pix_fmt,
            "-r", str(fps),
            "-c:a", "copy",
            "-movflags", "+faststart",
            temp_path,
        ]
        run_ffmpeg(cmd)

        # Replace original with subtitle version
        os.replace(temp_path, video_path)
        return video_path
