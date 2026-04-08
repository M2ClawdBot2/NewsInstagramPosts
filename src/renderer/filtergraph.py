"""
FFmpeg filtergraph builder.

FilterNode and FilterGraph construct -filter_complex strings
programmatically. No raw string concatenation in the renderers.

All text values passed into drawtext nodes must already be escaped
via src.utils.text_escaper.escape_drawtext() before reaching this module.
"""

import os
from dataclasses import dataclass, field

from ..utils.color import (
    hex_to_ffmpeg_box,
    hex_to_ffmpeg_text,
    hex_to_drawtext_color_with_alpha,
)
from ..utils.text_escaper import escape_drawtext, wrap_text


class FilterGraphError(Exception):
    pass


@dataclass
class FilterNode:
    """One filter in a filtergraph chain."""
    name: str                          # FFmpeg filter name: scale, overlay, drawtext, etc.
    inputs: list[str]                  # Input pad labels: ["[0:v]", "[bg]"]
    outputs: list[str]                 # Output pad labels: ["[scaled]"]
    params: dict                       # Ordered params (use regular dict — Python 3.7+ preserves order)

    def to_str(self) -> str:
        """Render as: [0:v]scale=w=1080:h=1080[scaled]"""
        inp = "".join(self.inputs)
        out = "".join(self.outputs)
        if self.params:
            param_str = ":".join(
                f"{k}={v}" for k, v in self.params.items()
            )
            return f"{inp}{self.name}={param_str}{out}"
        return f"{inp}{self.name}{out}"


class FilterGraph:
    """
    Builds a complete FFmpeg -filter_complex string by composing FilterNodes.

    Usage:
        fg = FilterGraph()
        fg.add(FilterNode("scale", ["[0:v]"], ["[scaled]"], {"w": "1080", "h": "1080"}))
        fg.set_final_output("[scaled]")
        filter_complex_str = fg.build()
    """

    def __init__(self):
        self._nodes: list[FilterNode] = []
        self._final_output: str = ""

    def add(self, node: FilterNode) -> "FilterGraph":
        self._nodes.append(node)
        return self

    def set_final_output(self, label: str) -> "FilterGraph":
        self._final_output = label
        return self

    def build(self) -> str:
        if not self._final_output:
            raise FilterGraphError("final_output label not set — call set_final_output()")
        parts = [n.to_str() for n in self._nodes]
        # Replace the last output label with [final] so the engine can always use -map [final]
        graph = "; ".join(parts)
        graph = graph.replace(self._final_output, "[final]", 1)
        return graph


# ---------------------------------------------------------------------------
# High-level filtergraph factory functions
# ---------------------------------------------------------------------------

def _label(name: str) -> str:
    return f"[{name}]"


def build_image_filtergraph(
    config,           # TemplateConfig
    story: dict,
    num_inputs: int,  # How many -i inputs: 0=source, 1=logo, 2=overlay(optional)
) -> FilterGraph:
    """
    Build a complete filtergraph for any image-based template.

    Input index convention:
        [0:v] = source image (or solid background)
        [1:v] = logo PNG
        [2:v] = gradient overlay PNG (optional; only if num_inputs == 3)

    Returns a FilterGraph with final_output set.
    """
    fg = FilterGraph()
    template_type = config.template.get("template_type", "")
    W = config.canvas_width
    H = config.canvas_height

    # ---- Step 1: Normalize source to canvas size ----
    if template_type in ("reel_cover",) or H > W:
        # Vertical canvas: blur-pad background technique
        _add_blurpad_source(fg, config)
        prev = _label("composed")
    else:
        # Square canvas: scale-to-fill then center-crop
        fg.add(FilterNode(
            "scale", ["[0:v]"], ["[scaled]"],
            {"w": str(W), "h": str(H),
             "force_original_aspect_ratio": "increase",
             "flags": "lanczos"},
        ))
        fg.add(FilterNode(
            "crop", ["[scaled]"], ["[cropped]"],
            {"w": str(W), "h": str(H),
             "x": f"(iw-{W})/2", "y": f"(ih-{H})/2"},
        ))
        prev = _label("cropped")

    # ---- Step 2: Background darkening ----
    darkening = (
        config.template.get("background_darkening") or
        config.brand.get("background_darkening", {})
    )
    dark_opacity = darkening.get("opacity", 0.45)
    dark_color = config.brand["colors"]["overlay_dark"]
    fg.add(FilterNode(
        "drawbox", [prev], ["[darkened]"],
        {"x": "0", "y": "0", "w": str(W), "h": str(H),
         "color": hex_to_ffmpeg_box(dark_color, dark_opacity),
         "t": "fill"},
    ))
    prev = _label("darkened")

    # ---- Step 3: Gradient overlay (if overlay PNG available) ----
    if num_inputs >= 3:
        fg.add(FilterNode(
            "scale", ["[2:v]"], ["[overlay_scaled]"],
            {"w": str(W), "h": str(H)},
        ))
        fg.add(FilterNode(
            "overlay", [prev, "[overlay_scaled]"], ["[graded]"],
            {"x": "0", "y": "0", "format": "auto"},
        ))
        prev = _label("graded")

    # ---- Step 4: Logo overlay ----
    logo_w = config.logo_width_px
    pad = config.logo_padding
    position = config.logo_position

    logo_x, logo_y = _compute_logo_xy(position, W, H, logo_w, pad)

    fg.add(FilterNode(
        "scale", ["[1:v]"], ["[logo_scaled]"],
        {"w": str(logo_w), "h": "-1", "flags": "lanczos"},
    ))
    fg.add(FilterNode(
        "overlay", [prev, "[logo_scaled]"], ["[with_logo]"],
        {"x": str(logo_x), "y": str(logo_y)},
    ))
    prev = _label("with_logo")

    # ---- Step 5: Template-specific elements ----
    if template_type == "breaking_news":
        prev = _add_breaking_news_elements(fg, prev, config, story, W, H)
    elif template_type == "engagement_bait":
        prev = _add_engagement_bait_elements(fg, prev, config, story, W, H)
    elif template_type == "quote_card":
        prev = _add_quote_card_elements(fg, prev, config, story, W, H)
    elif template_type == "reel_cover":
        prev = _add_reel_cover_elements(fg, prev, config, story, W, H)
    elif template_type == "carousel_slide":
        prev = _add_carousel_slide_elements(fg, prev, config, story, W, H)

    fg.set_final_output(prev)
    return fg


def build_video_filtergraph(config, story: dict) -> FilterGraph:
    """
    Build filtergraph for video_reel template.
    Input convention: [0:v] = source video, [1:v] = logo PNG.
    No overlay PNG for video (gradient via drawbox).
    """
    fg = FilterGraph()
    W = config.canvas_width   # 1080
    H = config.canvas_height  # 1920

    # Blur-pad background from video source
    _add_blurpad_source(fg, config, is_video=True)
    prev = _label("composed")

    # Background darkening
    darkening = config.template.get("background_darkening", {})
    dark_opacity = darkening.get("opacity", 0.35)
    fg.add(FilterNode(
        "drawbox", [prev], ["[darkened]"],
        {"x": "0", "y": "0", "w": str(W), "h": str(H),
         "color": hex_to_ffmpeg_box("#000000", dark_opacity),
         "t": "fill"},
    ))
    prev = _label("darkened")

    # Logo
    logo_w = config.logo_width_px
    pad = config.logo_padding
    logo_x, logo_y = _compute_logo_xy(config.logo_position, W, H, logo_w, pad)
    fg.add(FilterNode(
        "scale", ["[1:v]"], ["[logo_scaled]"],
        {"w": str(logo_w), "h": "-1", "flags": "lanczos"},
    ))
    fg.add(FilterNode(
        "overlay", [prev, "[logo_scaled]"], ["[with_logo]"],
        {"x": str(logo_x), "y": str(logo_y), "shortest": "1"},
    ))
    prev = _label("with_logo")

    # Lower-third branding
    lt = config.template.get("lower_third", {})
    if lt.get("enabled"):
        prev = _add_lower_third(fg, prev, config, story, W, H, lt)

    fg.set_final_output(prev)
    return fg


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_blurpad_source(fg: FilterGraph, config, is_video: bool = False) -> None:
    """
    Blur-pad technique for filling a vertical canvas from a horizontal source.
    Creates [composed] output label.
    """
    W = config.canvas_width
    H = config.canvas_height
    blur_cfg = config.template.get("blur_pad", {})
    blur_r = blur_cfg.get("blur_radius", 22)
    blur_p = blur_cfg.get("blur_power", 4)
    src = "[0:v]"

    fg.add(FilterNode(
        "split", [src], ["[src_a]", "[src_b]"], {},
    ))
    # Background: scale-to-fill + crop + blur
    fg.add(FilterNode(
        "scale", ["[src_b]"], ["[bg_large]"],
        {"w": str(W), "h": str(H),
         "force_original_aspect_ratio": "increase", "flags": "lanczos"},
    ))
    fg.add(FilterNode(
        "crop", ["[bg_large]"], ["[bg_cropped]"],
        {"w": str(W), "h": str(H), "x": f"(iw-{W})/2", "y": f"(ih-{H})/2"},
    ))
    fg.add(FilterNode(
        "boxblur", ["[bg_cropped]"], ["[blurred_bg]"],
        {"luma_radius": str(blur_r), "luma_power": str(blur_p)},
    ))
    # Center: scale to fit width, preserve aspect
    fg.add(FilterNode(
        "scale", ["[src_a]"], ["[center]"],
        {"w": str(W), "h": "-1", "flags": "lanczos"},
    ))
    # Overlay center on blurred background
    fg.add(FilterNode(
        "overlay", ["[blurred_bg]", "[center]"], ["[composed]"],
        {"x": "0", "y": f"({H}-ih)/2"},
    ))


def _compute_logo_xy(
    position: str, canvas_w: int, canvas_h: int, logo_w: int, pad: int
) -> tuple[int, int]:
    """Compute pixel (x, y) for logo top-left corner from position string."""
    # Logo height is unknown at build time; use logo_w as conservative estimate
    # FFmpeg overlay uses top-left corner; logo_h computed dynamically via -1 scale
    logo_h_est = logo_w  # overestimate; actual logo is wider than tall

    positions = {
        "top-right":    (canvas_w - logo_w - pad, pad),
        "top-left":     (pad, pad),
        "bottom-right": (canvas_w - logo_w - pad, canvas_h - logo_h_est - pad),
        "bottom-left":  (pad, canvas_h - logo_h_est - pad),
    }
    if position not in positions:
        raise FilterGraphError(
            f"Unknown logo position: {position!r}. "
            f"Valid: {list(positions.keys())}"
        )
    return positions[position]


def _add_label_band(
    fg: FilterGraph, prev: str, config, W: int, H: int,
    label_cfg: dict, out_label: str,
) -> str:
    """Draw a colored horizontal band with text. Returns new prev label."""
    color = label_cfg.get("background_color", "#C8102E")
    text_color = label_cfg.get("text_color", "#FFFFFF")
    y = label_cfg["y"]
    band_h = label_cfg["height"]
    text = escape_drawtext(label_cfg.get("text", "BREAKING NEWS"))
    font_key = label_cfg.get("font", "label_font")
    font_path = config.font_path(font_key)
    font_size = label_cfg.get("font_size", 34)
    text_x = label_cfg.get("text_x_offset", 40)
    text_y = y + (band_h - font_size) // 2

    band_out = f"[{out_label}_band]"
    text_out = f"[{out_label}]"

    fg.add(FilterNode(
        "drawbox", [prev], [band_out],
        {"x": "0", "y": str(y), "w": str(W), "h": str(band_h),
         "color": hex_to_ffmpeg_box(color, 1.0), "t": "fill"},
    ))
    fg.add(FilterNode(
        "drawtext", [band_out], [text_out],
        {"fontfile": font_path,
         "text": text,
         "fontcolor": hex_to_ffmpeg_text(text_color),
         "fontsize": str(font_size),
         "x": str(text_x),
         "y": str(text_y)},
    ))
    return text_out


def _add_headline(
    fg: FilterGraph, prev: str, config, story: dict,
    box_cfg: dict, out_label: str,
) -> str:
    """Add drawtext for headline. Returns new label."""
    raw_text = story.get("short_headline", "")
    max_chars = box_cfg.get("max_chars_per_line", 22)
    max_lines = box_cfg.get("max_lines", 3)
    wrapped = wrap_text(raw_text, max_chars, max_lines)
    text = escape_drawtext(wrapped)

    font_path = config.font_path(box_cfg.get("font", "headline_font"))
    font_size = box_cfg.get("font_size", 78)
    color = box_cfg.get("color", "#FFFFFF")
    x = box_cfg.get("x", 40)
    y = box_cfg.get("y", 560)
    line_spacing = box_cfg.get("line_spacing", 6)
    out = f"[{out_label}]"

    fg.add(FilterNode(
        "drawtext", [prev], [out],
        {"fontfile": font_path,
         "text": text,
         "fontcolor": hex_to_ffmpeg_text(color),
         "fontsize": str(font_size),
         "x": str(x),
         "y": str(y),
         "line_spacing": str(line_spacing)},
    ))
    return out


def _add_subheadline(
    fg: FilterGraph, prev: str, config, story: dict,
    box_cfg: dict, out_label: str,
) -> str:
    """Add drawtext for subheadline. No-op (returns prev) if subheadline empty."""
    sub = story.get("subheadline", "").strip()
    if not sub or not box_cfg.get("enabled", True):
        return prev

    text = escape_drawtext(sub)
    font_path = config.font_path(box_cfg.get("font", "body_font"))
    font_size = box_cfg.get("font_size", 34)
    alpha = box_cfg.get("opacity", 1.0)
    color = hex_to_drawtext_color_with_alpha(box_cfg.get("color", "#FFFFFF"), alpha)
    x = box_cfg.get("x", 40)
    y = box_cfg.get("y", 768)
    out = f"[{out_label}]"

    fg.add(FilterNode(
        "drawtext", [prev], [out],
        {"fontfile": font_path,
         "text": text,
         "fontcolor": color,
         "fontsize": str(font_size),
         "x": str(x),
         "y": str(y)},
    ))
    return out


# ---------------------------------------------------------------------------
# Template-specific element builders
# ---------------------------------------------------------------------------

def _add_breaking_news_elements(
    fg: FilterGraph, prev: str, config, story: dict, W: int, H: int
) -> str:
    label_cfg = config.template.get("label_region", {})
    if label_cfg.get("enabled"):
        prev = _add_label_band(fg, prev, config, W, H, label_cfg, "labeled")

    hbox = config.template.get("headline_box", {})
    prev = _add_headline(fg, prev, config, story, hbox, "headlined")

    sbox = config.template.get("subheadline_box", {})
    prev = _add_subheadline(fg, prev, config, story, sbox, "subheadlined")
    return prev


def _add_engagement_bait_elements(
    fg: FilterGraph, prev: str, config, story: dict, W: int, H: int
) -> str:
    hbox = config.template.get("headline_box", {})
    prev = _add_headline(fg, prev, config, story, hbox, "headlined")

    poll = config.template.get("poll_boxes", {})
    if poll.get("enabled"):
        prev = _add_poll_boxes(fg, prev, config, W, H, poll)
    return prev


def _add_poll_boxes(
    fg: FilterGraph, prev: str, config, W: int, H: int, poll: dict
) -> str:
    for opt_key, out_suffix in (("option_a", "opt_a"), ("option_b", "opt_b")):
        opt = poll[opt_key]
        box_color = hex_to_ffmpeg_box(opt["background_color"], opt["background_opacity"])
        box_out = f"[poll_{out_suffix}_box]"
        text_out = f"[poll_{out_suffix}]"
        text = escape_drawtext(opt["text"])
        font_path = config.font_path(opt.get("font", "headline_font"))
        font_size = opt["font_size"]
        text_color = hex_to_ffmpeg_text(opt["text_color"])
        # Center text in box
        tx = opt["x"] + (opt["width"] - len(opt["text"]) * font_size // 2) // 2
        ty = opt["y"] + (opt["height"] - font_size) // 2

        fg.add(FilterNode(
            "drawbox", [prev], [box_out],
            {"x": str(opt["x"]), "y": str(opt["y"]),
             "w": str(opt["width"]), "h": str(opt["height"]),
             "color": box_color, "t": "fill"},
        ))
        fg.add(FilterNode(
            "drawtext", [box_out], [text_out],
            {"fontfile": font_path, "text": text,
             "fontcolor": text_color, "fontsize": str(font_size),
             "x": str(tx), "y": str(ty)},
        ))
        prev = text_out
    return prev


def _add_quote_card_elements(
    fg: FilterGraph, prev: str, config, story: dict, W: int, H: int
) -> str:
    # Red accent bar
    bar_cfg = config.template.get("accent_bar", {})
    if bar_cfg.get("enabled"):
        bar_out = "[accent_bar]"
        fg.add(FilterNode(
            "drawbox", [prev], [bar_out],
            {"x": str(bar_cfg["x"]), "y": str(bar_cfg["y"]),
             "w": str(bar_cfg["width"]), "h": str(bar_cfg["height"]),
             "color": hex_to_ffmpeg_box(bar_cfg["color"], 1.0),
             "t": "fill"},
        ))
        prev = bar_out

    # Quote text
    qbox = config.template.get("quote_box", {})
    quote_raw = story.get("quote_text") or story.get("short_headline", "")
    max_chars = qbox.get("max_chars_per_line", 28)
    wrapped = wrap_text(f'"{quote_raw}"', max_chars, qbox.get("max_lines", 6))
    text = escape_drawtext(wrapped)
    font_path = config.font_path(qbox.get("font", "headline_font"))
    q_out = "[quoted]"
    fg.add(FilterNode(
        "drawtext", [prev], [q_out],
        {"fontfile": font_path,
         "text": text,
         "fontcolor": hex_to_ffmpeg_text(qbox.get("color", "#FFFFFF")),
         "fontsize": str(qbox.get("font_size", 64)),
         "x": str(qbox.get("x", 72)),
         "y": str(qbox.get("y", 200)),
         "line_spacing": str(qbox.get("line_spacing", 10))},
    ))
    prev = q_out

    # Attribution
    abox = config.template.get("attribution_box", {})
    attr_raw = story.get("attribution") or story.get("subheadline", "")
    if attr_raw:
        attr_text = escape_drawtext(f"— {attr_raw}")
        font_path_a = config.font_path(abox.get("font", "body_font"))
        a_out = "[attributed]"
        fg.add(FilterNode(
            "drawtext", [prev], [a_out],
            {"fontfile": font_path_a,
             "text": attr_text,
             "fontcolor": hex_to_ffmpeg_text(abox.get("color", "#C8102E")),
             "fontsize": str(abox.get("font_size", 36)),
             "x": str(abox.get("x", 72)),
             "y": str(abox.get("y", 720))},
        ))
        prev = a_out

    return prev


def _add_reel_cover_elements(
    fg: FilterGraph, prev: str, config, story: dict, W: int, H: int
) -> str:
    label_cfg = config.template.get("label_region", {})
    if label_cfg.get("enabled"):
        prev = _add_label_band(fg, prev, config, W, H, label_cfg, "labeled")

    hbox = config.template.get("headline_box", {})
    prev = _add_headline(fg, prev, config, story, hbox, "headlined")
    return prev


def _add_carousel_slide_elements(
    fg: FilterGraph, prev: str, config, story: dict, W: int, H: int
) -> str:
    hbox = config.template.get("headline_box", {})
    prev = _add_headline(fg, prev, config, story, hbox, "headlined")

    sbox = config.template.get("subheadline_box", {})
    prev = _add_subheadline(fg, prev, config, story, sbox, "subheadlined")

    # Slide indicator e.g. "02 / 05"
    slide_cfg = config.template.get("slide_indicator", {})
    if slide_cfg.get("enabled") and story.get("slide_number"):
        num = story["slide_number"]
        total = story.get("total_slides", "?")
        indicator_text = escape_drawtext(f"{num:02d} / {total:02d}" if isinstance(total, int) else f"{num} / {total}")
        font_path = config.font_path(slide_cfg.get("font", "label_font"))
        font_size = slide_cfg.get("font_size", 26)
        alpha = slide_cfg.get("opacity", 0.60)
        color = hex_to_drawtext_color_with_alpha(slide_cfg.get("color", "#FFFFFF"), alpha)
        # Right-align: use x computed from canvas width
        x = W - 140  # approximate; right-align not natively supported in drawtext
        y = slide_cfg.get("y", H - 40)
        si_out = "[slide_indicator]"
        fg.add(FilterNode(
            "drawtext", [prev], [si_out],
            {"fontfile": font_path, "text": indicator_text,
             "fontcolor": color, "fontsize": str(font_size),
             "x": str(x), "y": str(y)},
        ))
        prev = si_out

    return prev


def _add_lower_third(
    fg: FilterGraph, prev: str, config, story: dict, W: int, H: int, lt: dict
) -> str:
    """Add lower-third branding strip for video reels."""
    # Accent line
    al = lt.get("accent_line", {})
    if al:
        al_out = "[accent_line]"
        fg.add(FilterNode(
            "drawbox", [prev], [al_out],
            {"x": str(al.get("x", 0)), "y": str(al.get("y", 1728)),
             "w": str(al.get("width", W)), "h": str(al.get("height", 6)),
             "color": hex_to_ffmpeg_box(al.get("color", "#C8102E"), 1.0),
             "t": "fill"},
        ))
        prev = al_out

    # Brand bug text (e.g. "DAILY BELTWAY")
    brand_text = escape_drawtext(lt.get("brand_bug_text", "DAILY BELTWAY"))
    font_path = config.font_path(lt.get("brand_bug_font", "label_font"))
    bb_out = "[brand_bug]"
    fg.add(FilterNode(
        "drawtext", [prev], [bb_out],
        {"fontfile": font_path,
         "text": brand_text,
         "fontcolor": hex_to_ffmpeg_text(lt.get("brand_bug_color", "#C8102E")),
         "fontsize": str(lt.get("brand_bug_size", 30)),
         "x": str(lt.get("brand_bug_x", 48)),
         "y": str(lt.get("brand_bug_y", 1744))},
    ))
    prev = bb_out

    # Headline text from story
    hl_raw = story.get("short_headline", "")
    max_chars = lt.get("headline_max_chars", 30)
    hl_text = escape_drawtext(wrap_text(hl_raw, max_chars, 1))
    hl_font = config.font_path(lt.get("headline_font", "headline_font"))
    hl_out = "[lt_headline]"
    fg.add(FilterNode(
        "drawtext", [prev], [hl_out],
        {"fontfile": hl_font,
         "text": hl_text,
         "fontcolor": hex_to_ffmpeg_text(lt.get("headline_color", "#FFFFFF")),
         "fontsize": str(lt.get("headline_size", 52)),
         "x": str(lt.get("headline_x", 48)),
         "y": str(lt.get("headline_y", 1786))},
    ))
    return hl_out
