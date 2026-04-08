"""Tests for config loader and validator."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from src.templates.validator import (
    validate_brand_config,
    validate_template_config,
    validate_all,
    _get_nested,
)


VALID_BRAND = {
    "brand_name": "Daily Beltway",
    "colors": {
        "primary_navy": "#1B2A4A",
        "accent_red": "#C8102E",
        "white": "#FFFFFF",
    },
    "fonts": {
        "headline_font": "assets/fonts/BarlowCondensed-ExtraBold.ttf",
        "body_font": "assets/fonts/Barlow-SemiBold.ttf",
        "label_font": "assets/fonts/Barlow-Bold.ttf",
    },
    "logo": {
        "path": "assets/logos/daily_beltway_logo.png",
        "default_width_pct": 0.15,
        "padding_px": 24,
        "position": "top-right",
    },
    "gradient": {
        "bottom_height_pct": 0.55,
        "opacity": 0.82,
    },
    "background_darkening": {
        "default_opacity": 0.45,
    },
    "export": {
        "jpeg_quality": 2,
        "png_compression": 0,
        "video_crf": 18,
        "video_codec": "libx264",
        "video_pix_fmt": "yuv420p",
    },
}

VALID_TEMPLATE_BREAKING = {
    "template_type": "breaking_news",
    "canvas_width": 1080,
    "canvas_height": 1080,
    "safe_margin_px": 40,
    "headline_box": {"x": 40, "y": 560, "font_size": 78},
    "label_region": {"enabled": True, "text": "BREAKING NEWS"},
    "export": {"format": "jpeg"},
}


class TestGetNested:
    def test_simple_key(self):
        assert _get_nested({"a": 1}, "a") == 1

    def test_nested_key(self):
        assert _get_nested({"a": {"b": {"c": 42}}}, "a.b.c") == 42

    def test_missing_key_returns_none(self):
        assert _get_nested({"a": 1}, "b") is None

    def test_missing_nested_key_returns_none(self):
        assert _get_nested({"a": {"b": 1}}, "a.c") is None

    def test_none_at_intermediate(self):
        assert _get_nested({"a": None}, "a.b") is None


class TestValidateBrandConfig:
    def test_valid_brand_returns_no_errors(self):
        errors = validate_brand_config(VALID_BRAND)
        assert errors == []

    def test_missing_color_field(self):
        brand = dict(VALID_BRAND)
        brand["colors"] = {"primary_navy": "#1B2A4A"}  # missing accent_red and white
        errors = validate_brand_config(brand)
        assert any("colors.accent_red" in e for e in errors)
        assert any("colors.white" in e for e in errors)

    def test_missing_font_field(self):
        import copy
        brand = copy.deepcopy(VALID_BRAND)
        del brand["fonts"]["headline_font"]
        errors = validate_brand_config(brand)
        assert any("headline_font" in e for e in errors)

    def test_completely_empty_config(self):
        errors = validate_brand_config({})
        assert len(errors) > 5  # Many fields missing


class TestValidateTemplateConfig:
    def test_valid_template_returns_no_errors(self):
        errors = validate_template_config(VALID_TEMPLATE_BREAKING)
        assert errors == []

    def test_missing_canvas_width(self):
        import copy
        t = copy.deepcopy(VALID_TEMPLATE_BREAKING)
        del t["canvas_width"]
        errors = validate_template_config(t)
        assert any("canvas_width" in e for e in errors)

    def test_missing_export_format(self):
        import copy
        t = copy.deepcopy(VALID_TEMPLATE_BREAKING)
        del t["export"]
        errors = validate_template_config(t)
        assert any("export.format" in e for e in errors)

    def test_breaking_news_requires_headline_box(self):
        import copy
        t = copy.deepcopy(VALID_TEMPLATE_BREAKING)
        del t["headline_box"]
        errors = validate_template_config(t)
        assert any("headline_box" in e for e in errors)


class TestValidateAll:
    def test_valid_configs_all_empty_errors(self):
        results = validate_all(VALID_BRAND, {"breaking_news": VALID_TEMPLATE_BREAKING})
        assert results["brand"] == []
        assert results["breaking_news"] == []

    def test_returns_all_config_names(self):
        results = validate_all(VALID_BRAND, {
            "breaking_news": VALID_TEMPLATE_BREAKING,
            "quote_card": {"template_type": "quote_card"},
        })
        assert "brand" in results
        assert "breaking_news" in results
        assert "quote_card" in results
