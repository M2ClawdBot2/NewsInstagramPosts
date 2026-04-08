"""
Dropbox exporter — writes finished story packages to Dropbox.

Two modes:
  1. API upload (production): uses Dropbox Python SDK with access token
  2. Local folder (dev/staging): writes to output/READY_TO_REVIEW/ locally

Environment variables (set in .env):
  DROPBOX_ACCESS_TOKEN  — Dropbox API OAuth2 long-lived token
  DROPBOX_DEST_PATH     — Dropbox folder path (default: /Daily Beltway/READY_TO_REVIEW)
  LOCAL_OUTPUT_PATH     — Local output dir (default: output/)
"""

import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List

from ..renderer.image_renderer import RenderResult


class ExportError(Exception):
    pass


class DropboxExporter:
    """
    Writes story output packages.

    If DROPBOX_ACCESS_TOKEN is set, uploads to Dropbox via API.
    Otherwise, writes to the local output directory.
    """

    def __init__(self, project_root: str):
        self.project_root = project_root
        self.local_base = os.environ.get(
            "LOCAL_OUTPUT_PATH",
            os.path.join(project_root, "output"),
        )
        self.dropbox_token = os.environ.get("DROPBOX_ACCESS_TOKEN", "")
        self.dropbox_dest = os.environ.get(
            "DROPBOX_DEST_PATH", "/Daily Beltway/READY_TO_REVIEW"
        )

    @property
    def use_dropbox_api(self) -> bool:
        return bool(self.dropbox_token)

    def export_package(
        self,
        slug: str,
        story: dict,
        render_result: RenderResult,
        ffmpeg_version: str = "unknown",
        additional_files: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Write or upload a complete story output package.

        Args:
            slug: Output folder name (e.g. '2026-04-08_senate-passes-budget')
            story: Validated story dict
            render_result: RenderResult from the renderer
            ffmpeg_version: FFmpeg version string for manifest
            additional_files: {filename: source_path} for extra files (e.g. reel_cover.jpg)

        Returns:
            Local directory path where files were written (even for Dropbox uploads)
        """
        local_dir = self._make_local_dir(slug)
        files_written = []

        # 1. Copy rendered media (post.jpg / reel.mp4)
        media_filename = self._media_filename(render_result)
        dest_media = os.path.join(local_dir, media_filename)
        shutil.copy2(render_result.output_path, dest_media)
        files_written.append(media_filename)

        # 2. Additional files (e.g. reel_cover.jpg)
        if additional_files:
            for filename, src_path in additional_files.items():
                if os.path.isfile(src_path):
                    dest = os.path.join(local_dir, filename)
                    shutil.copy2(src_path, dest)
                    files_written.append(filename)

        # 3. caption.txt
        caption_path = self._write_caption(local_dir, story)
        files_written.append("caption.txt")

        # 4. manifest.json
        manifest_path = self._write_manifest(
            local_dir, slug, story, render_result, ffmpeg_version, files_written
        )
        files_written.append("manifest.json")

        # 5. internal_notes.txt
        notes_path = self._write_internal_notes(local_dir, render_result, ffmpeg_version)
        files_written.append("internal_notes.txt")

        # 6. Upload to Dropbox if configured
        if self.use_dropbox_api:
            self._upload_to_dropbox(local_dir, slug, files_written)

        return local_dir

    def _make_local_dir(self, slug: str) -> str:
        """Create and return the local output directory for this story."""
        path = os.path.join(self.local_base, "READY_TO_REVIEW", slug)
        os.makedirs(path, exist_ok=True)
        return path

    def _media_filename(self, render_result: RenderResult) -> str:
        """Determine the canonical output filename based on template type."""
        if render_result.template_type == "video_reel":
            return "reel.mp4"
        return "post.jpg"

    def _write_caption(self, output_dir: str, story: dict) -> str:
        """Write caption.txt."""
        caption = story.get("caption") or story.get("title", "")
        source_url = story.get("source_url", "")
        lines = [caption]
        if source_url:
            lines += ["", f"Source: {source_url}"]
        path = os.path.join(output_dir, "caption.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def _write_manifest(
        self,
        output_dir: str,
        slug: str,
        story: dict,
        render_result: RenderResult,
        ffmpeg_version: str,
        output_files: list[str],
    ) -> str:
        """Write manifest.json with render metadata."""
        manifest = {
            "slug": slug,
            "rendered_at": datetime.now(tz=timezone.utc).isoformat(),
            "template_type": render_result.template_type,
            "story_title": story.get("title", ""),
            "story_category": story.get("category", ""),
            "source_url": story.get("source_url", ""),
            "output_files": output_files,
            "render_duration_ms": round(render_result.duration_ms, 1),
            "ffmpeg_version": ffmpeg_version,
            "system": {
                "dropbox_uploaded": self.use_dropbox_api,
                "dropbox_dest": self.dropbox_dest if self.use_dropbox_api else None,
            },
        }
        path = os.path.join(output_dir, "manifest.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        return path

    def _write_internal_notes(
        self,
        output_dir: str,
        render_result: RenderResult,
        ffmpeg_version: str,
    ) -> str:
        """Write internal_notes.txt with full FFmpeg command for debugging."""
        cmd_str = " ".join(str(c) for c in render_result.ffmpeg_command)
        lines = [
            "Daily Beltway — Render Notes",
            "=" * 60,
            f"Template:      {render_result.template_type}",
            f"Rendered at:   {datetime.now(tz=timezone.utc).isoformat()}",
            f"Duration:      {render_result.duration_ms:.0f}ms",
            f"FFmpeg:        {ffmpeg_version}",
            f"Output:        {render_result.output_path}",
            "",
            "FFmpeg command (copy-paste ready):",
            "-" * 60,
            cmd_str,
            "",
        ]
        path = os.path.join(output_dir, "internal_notes.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def _upload_to_dropbox(
        self,
        local_dir: str,
        slug: str,
        filenames: list[str],
    ) -> None:
        """
        Upload all package files to Dropbox via API.

        Requires: pip install dropbox
        Uses DROPBOX_ACCESS_TOKEN from environment.
        """
        try:
            import dropbox
            from dropbox.exceptions import ApiError, AuthError
            from dropbox.files import WriteMode
        except ImportError:
            raise ExportError(
                "Dropbox SDK not installed. Run: pip install dropbox\n"
                "Or set DROPBOX_ACCESS_TOKEN= (empty) to disable API upload."
            )

        try:
            dbx = dropbox.Dropbox(self.dropbox_token)
            # Verify token
            dbx.users_get_current_account()
        except Exception as e:
            raise ExportError(
                f"Dropbox authentication failed: {e}\n"
                f"Check DROPBOX_ACCESS_TOKEN in your .env file."
            ) from e

        dest_folder = f"{self.dropbox_dest.rstrip('/')}/{slug}"

        for filename in filenames:
            local_path = os.path.join(local_dir, filename)
            dropbox_path = f"{dest_folder}/{filename}"

            with open(local_path, "rb") as f:
                data = f.read()

            try:
                dbx.files_upload(
                    data,
                    dropbox_path,
                    mode=WriteMode("overwrite"),
                    mute=True,
                )
                print(f"  Uploaded → {dropbox_path}")
            except Exception as e:
                raise ExportError(
                    f"Failed to upload {filename} to Dropbox: {e}"
                ) from e
