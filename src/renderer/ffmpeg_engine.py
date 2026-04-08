"""
FFmpeg subprocess execution layer.

All FFmpeg invocations go through this module.
- Commands are always passed as list[str] (never shell=True)
- Errors include full stderr output
- FFmpeg binary is located once at startup via find_ffmpeg()
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Union


class FFmpegError(Exception):
    """Raised when FFmpeg exits with a non-zero return code."""

    def __init__(self, cmd: list[str], returncode: int, stderr: str):
        self.cmd = cmd
        self.returncode = returncode
        self.stderr = stderr
        cmd_str = " ".join(str(c) for c in cmd)
        super().__init__(
            f"\nFFmpeg failed (exit {returncode})\n"
            f"Command: {cmd_str}\n"
            f"Stderr:\n{stderr}"
        )


def find_ffmpeg() -> str:
    """
    Locate the ffmpeg binary.

    Search order:
      1. FFMPEG_BIN environment variable
      2. System PATH (via shutil.which)
      3. /opt/homebrew/bin/ffmpeg   (Apple Silicon Homebrew)
      4. /usr/local/bin/ffmpeg      (Intel Homebrew / Linux)
      5. /usr/bin/ffmpeg            (system package manager)

    Returns:
        Absolute path to ffmpeg binary

    Raises:
        EnvironmentError: With install instructions if not found
    """
    env_bin = os.environ.get("FFMPEG_BIN")
    if env_bin and os.path.isfile(env_bin):
        return env_bin

    which = shutil.which("ffmpeg")
    if which:
        return which

    candidates = [
        "/opt/homebrew/bin/ffmpeg",
        "/usr/local/bin/ffmpeg",
        "/usr/bin/ffmpeg",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path

    raise EnvironmentError(
        "\n\n[FFMPEG NOT FOUND]\n"
        "  FFmpeg is required but was not found on this system.\n\n"
        "  Install options:\n"
        "    Ubuntu/Debian: sudo apt install ffmpeg\n"
        "    macOS (Homebrew): brew install ffmpeg\n"
        "    Or set FFMPEG_BIN=/path/to/ffmpeg in your .env file\n"
    )


def get_ffmpeg_version(ffmpeg_bin: str) -> str:
    """Return FFmpeg version string (e.g. '6.1.1')."""
    try:
        result = subprocess.run(
            [ffmpeg_bin, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        first_line = result.stdout.splitlines()[0] if result.stdout else ""
        # "ffmpeg version 6.1.1 built with ..."
        parts = first_line.split()
        if len(parts) >= 3 and parts[0] == "ffmpeg":
            return parts[2]
        return first_line
    except Exception:
        return "unknown"


def run_ffmpeg(
    cmd: list[str],
    timeout_seconds: int = 300,
) -> subprocess.CompletedProcess:
    """
    Execute an FFmpeg command as a subprocess.

    Args:
        cmd: Full command as list[str] starting with the ffmpeg binary path
        timeout_seconds: Kill timeout; defaults to 5 minutes

    Returns:
        CompletedProcess with stdout/stderr captured

    Raises:
        FFmpegError: On non-zero exit code
        subprocess.TimeoutExpired: If FFmpeg exceeds timeout_seconds
    """
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    if result.returncode != 0:
        raise FFmpegError(cmd, result.returncode, result.stderr)
    return result


def build_image_command(
    ffmpeg_bin: str,
    inputs: List[Union[str, Path]],
    filter_complex: str,
    output_path: Union[str, Path],
    quality: int = 2,
    output_format: str = "jpeg",
) -> List[str]:
    """
    Build an FFmpeg command for image rendering.

    Args:
        ffmpeg_bin: Path to ffmpeg binary
        inputs: List of input file paths (source image, logo PNG, overlay PNG, ...)
        filter_complex: Complete -filter_complex string
        output_path: Destination file path
        quality: JPEG -q:v value (2 = ~95% quality; 1 = max)
        output_format: 'jpeg' or 'png'

    Returns:
        list[str] ready for subprocess.run()
    """
    cmd = [ffmpeg_bin, "-y", "-loglevel", "warning"]

    for inp in inputs:
        cmd += ["-i", str(inp)]

    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", "[final]"]
    cmd += ["-frames:v", "1"]

    if output_format == "jpeg":
        cmd += ["-q:v", str(quality)]
    elif output_format == "png":
        cmd += ["-compression_level", "0"]
    else:
        raise ValueError(f"Unsupported output_format: {output_format!r}")

    cmd.append(str(output_path))
    return cmd


def build_video_command(
    ffmpeg_bin: str,
    inputs: List[Union[str, Path]],
    filter_complex: str,
    output_path: Union[str, Path],
    crf: int = 18,
    fps: int = 30,
    preset: str = "slow",
    pix_fmt: str = "yuv420p",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
    has_audio: bool = True,
    duration_seconds: Optional[float] = None,
) -> List[str]:
    """
    Build an FFmpeg command for video rendering (MP4/H.264).

    Args:
        ffmpeg_bin: Path to ffmpeg binary
        inputs: Input file paths
        filter_complex: Complete -filter_complex string
        output_path: Destination .mp4 file path
        crf: libx264 CRF value (18 = visually lossless)
        fps: Output frame rate
        preset: x264 preset (slow/medium/fast)
        pix_fmt: Pixel format (yuv420p required for Instagram)
        audio_codec: Audio codec for output
        audio_bitrate: Audio bitrate string
        has_audio: If False, adds -an (no audio)
        duration_seconds: If set, adds -t duration limit

    Returns:
        list[str] ready for subprocess.run()
    """
    cmd = [ffmpeg_bin, "-y", "-loglevel", "warning"]

    if duration_seconds is not None:
        cmd += ["-t", str(duration_seconds)]

    for inp in inputs:
        cmd += ["-i", str(inp)]

    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", "[final]"]

    if has_audio:
        cmd += ["-map", "0:a?"]  # Map audio from first input if present

    cmd += [
        "-c:v", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-pix_fmt", pix_fmt,
        "-r", str(fps),
        "-movflags", "+faststart",
    ]

    if has_audio:
        cmd += ["-c:a", audio_codec, "-b:a", audio_bitrate]
    else:
        cmd += ["-an"]

    cmd.append(str(output_path))
    return cmd


def extract_cover_frame(
    ffmpeg_bin: str,
    video_path: Union[str, Path],
    output_path: Union[str, Path],
    timestamp_seconds: float = 0.5,
    quality: int = 2,
) -> List[str]:
    """
    Build command to extract a single frame from a video as JPEG.

    Args:
        ffmpeg_bin: Path to ffmpeg binary
        video_path: Source video file
        output_path: Destination JPEG path
        timestamp_seconds: Time offset in seconds to extract frame
        quality: JPEG quality (-q:v)

    Returns:
        list[str] for subprocess.run()
    """
    return [
        ffmpeg_bin, "-y", "-loglevel", "warning",
        "-ss", str(timestamp_seconds),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", str(quality),
        str(output_path),
    ]
