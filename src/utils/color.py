"""
Hex color → FFmpeg color format conversions.

FFmpeg accepts colors differently per filter:
  drawtext fontcolor=  → 0xRRGGBB  (no alpha channel)
  drawbox color=       → 0xRRGGBBAA where AA = 0x00 (transparent) to 0xFF (opaque)
  overlay alpha=       → separate float 0.0–1.0
"""


def _parse_hex(hex_color: str) -> tuple[int, int, int]:
    """Parse #RRGGBB or RRGGBB → (r, g, b) ints."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex color: {hex_color!r} — expected #RRGGBB")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_to_ffmpeg_text(hex_color: str) -> str:
    """
    Convert hex color to FFmpeg drawtext fontcolor format.
    Returns '0xRRGGBB' (no alpha — drawtext does not support RGBA fontcolor).
    """
    r, g, b = _parse_hex(hex_color)
    return f"0x{r:02X}{g:02X}{b:02X}"


def hex_to_ffmpeg_box(hex_color: str, alpha: float = 1.0) -> str:
    """
    Convert hex color to FFmpeg drawbox color format.
    Returns '0xRRGGBBAA' where AA encodes opacity.

    Args:
        hex_color: '#RRGGBB' or 'RRGGBB'
        alpha: 0.0 (fully transparent) to 1.0 (fully opaque)

    Note: drawbox alpha is INVERTED in some FFmpeg builds — this function
    uses the standard 0xFF = opaque convention (verified with FFmpeg ≥ 4.4).
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be 0.0–1.0, got {alpha}")
    r, g, b = _parse_hex(hex_color)
    aa = int(alpha * 255)
    return f"0x{r:02X}{g:02X}{b:02X}{aa:02X}"


def hex_to_drawtext_color_with_alpha(hex_color: str, alpha: float = 1.0) -> str:
    """
    drawtext supports alpha via fontcolor as '0xRRGGBBAA@alpha' syntax.
    Returns the '@alpha' suffix form: '0xRRGGBB@0.88'
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError(f"alpha must be 0.0–1.0, got {alpha}")
    r, g, b = _parse_hex(hex_color)
    return f"0x{r:02X}{g:02X}{b:02X}@{alpha:.2f}"
