"""
Config validation — checks that all required fields are present in
brand.yaml and template YAMLs. Called by validate-config CLI command
and also at render time as a safety check.
"""

from .loader import ConfigError


# Dotted paths that MUST exist in a valid brand.yaml
REQUIRED_BRAND_FIELDS = [
    "colors.primary_navy",
    "colors.accent_red",
    "colors.white",
    "fonts.headline_font",
    "fonts.body_font",
    "fonts.label_font",
    "logo.path",
    "logo.default_width_pct",
    "logo.padding_px",
    "logo.position",
    "gradient.bottom_height_pct",
    "gradient.opacity",
    "background_darkening.default_opacity",
    "export.jpeg_quality",
    "export.png_compression",
    "export.video_crf",
    "export.video_codec",
    "export.video_pix_fmt",
]

# Dotted paths that MUST exist in every template YAML
REQUIRED_TEMPLATE_FIELDS = [
    "template_type",
    "canvas_width",
    "canvas_height",
    "safe_margin_px",
    "export.format",
]

# Fields required per template_type beyond the common set
TEMPLATE_TYPE_REQUIRED = {
    "breaking_news": ["headline_box", "label_region"],
    "engagement_bait": ["headline_box", "poll_boxes"],
    "quote_card": ["quote_box", "attribution_box"],
    "reel_cover": ["headline_box", "blur_pad"],
    "carousel_slide": ["headline_box", "slide_indicator"],
    "video_reel": ["lower_third", "blur_pad", "export.crf"],
}


def _get_nested(d: dict, dotted_key: str):
    """Traverse nested dict using 'a.b.c' notation. Returns None if any key missing."""
    parts = dotted_key.split(".")
    current = d
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def validate_brand_config(brand: dict) -> list[str]:
    """
    Validate brand config dict.

    Returns:
        List of error strings (empty = valid)
    """
    errors = []
    for field in REQUIRED_BRAND_FIELDS:
        if _get_nested(brand, field) is None:
            errors.append(f"brand.yaml missing required field: '{field}'")
    return errors


def validate_template_config(template: dict) -> list[str]:
    """
    Validate a template config dict.

    Returns:
        List of error strings (empty = valid)
    """
    errors = []
    for field in REQUIRED_TEMPLATE_FIELDS:
        if _get_nested(template, field) is None:
            errors.append(f"template missing required field: '{field}'")

    template_type = template.get("template_type")
    if template_type and template_type in TEMPLATE_TYPE_REQUIRED:
        for field in TEMPLATE_TYPE_REQUIRED[template_type]:
            if _get_nested(template, field) is None:
                errors.append(
                    f"template '{template_type}' missing required field: '{field}'"
                )
    return errors


def validate_all(brand: dict, templates: dict[str, dict]) -> dict[str, list[str]]:
    """
    Run validation across brand and all loaded template configs.

    Args:
        brand: Loaded brand.yaml dict
        templates: {template_name: template_dict} mapping

    Returns:
        Dict of {config_name: [error_strings]}. All values empty = fully valid.
    """
    results = {"brand": validate_brand_config(brand)}
    for name, tmpl in templates.items():
        results[name] = validate_template_config(tmpl)
    return results
