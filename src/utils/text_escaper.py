"""
FFmpeg drawtext filter text escaping.

FFmpeg's drawtext has a two-layer escaping problem:
  Layer 1: The FFmpeg option parser (key=value:key=value)
  Layer 2: The drawtext filter's own text parser

Characters that require escaping inside drawtext text= values:
  \\  → must be doubled first (always escape backslash before anything else)
  :   → separates filter options; must be \\:
  '   → terminates single-quoted strings; must be \\'
  %   → printf-style format in drawtext; must be %%
  newline → use the literal \\n token in the text= string

Escaping order is critical: backslash MUST be processed first.
"""


def escape_drawtext(text: str) -> str:
    """
    Escape a string for safe use as a drawtext filter text= value.

    The result is safe to embed in a filter_complex string passed as
    a subprocess argument list (not shell string — no shell quoting needed).

    Args:
        text: Raw user-provided string (headline, label, etc.)

    Returns:
        Escaped string for drawtext text=

    Raises:
        ValueError: If text contains null bytes (not representable in drawtext)
    """
    if "\x00" in text:
        raise ValueError("drawtext text cannot contain null bytes")

    # Order matters — backslash first
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "%%")
    return text


def truncate_to_fit(text: str, max_chars: int, ellipsis: str = "...") -> str:
    """
    Hard-truncate text to max_chars, appending ellipsis if truncated.
    Used before inserting into fixed headline boxes.
    """
    if len(text) <= max_chars:
        return text
    return text[: max_chars - len(ellipsis)] + ellipsis


def wrap_text(text: str, max_chars_per_line: int, max_lines: int = 3) -> str:
    """
    Soft-wrap text into lines of at most max_chars_per_line characters,
    breaking on word boundaries. Returns lines joined by \\n for FFmpeg drawtext.

    Truncates to max_lines total lines (with ellipsis on last line if needed).
    """
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        if len(test) <= max_chars_per_line:
            current = test
        else:
            if current:
                lines.append(current)
            if len(lines) >= max_lines:
                break
            current = word

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and current != lines[-1]:
        lines[-1] = truncate_to_fit(lines[-1], max_chars_per_line)

    return "\\n".join(lines)
