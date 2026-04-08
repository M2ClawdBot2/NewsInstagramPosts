"""
Template config loader.

Loads brand.yaml and a per-template YAML, performs a deep merge
(template values override brand defaults where both exist), and
returns a TemplateConfig object used throughout the renderer.
"""

import copy
import os
from dataclasses import dataclass, field

import yaml


class ConfigError(Exception):
    """Raised for missing or malformed config files."""
    pass


@dataclass
class TemplateConfig:
    """Merged brand + template configuration."""
    brand: dict          # Full brand.yaml content
    template: dict       # Full template YAML content
    effective: dict      # Deep-merged: template overrides brand where conflicts exist
    project_root: str    # Absolute path to project root (for resolving asset paths)

    def get(self, *keys, default=None):
        """
        Traverse effective config with dotted keys or a sequence of keys.
        e.g. config.get('logo', 'padding_px') or config.get('export.jpeg_quality')
        """
        d = self.effective
        for k in keys:
            if isinstance(k, str) and "." in k:
                # Support 'a.b.c' notation in a single argument
                for part in k.split("."):
                    if not isinstance(d, dict):
                        return default
                    d = d.get(part, default)
                    if d is default:
                        return default
            else:
                if not isinstance(d, dict):
                    return default
                d = d.get(k, default)
                if d is None and default is not None:
                    return default
        return d

    def abs_path(self, rel_path: str) -> str:
        """Resolve a project-relative path to absolute."""
        if os.path.isabs(rel_path):
            return rel_path
        return os.path.join(self.project_root, rel_path)

    def font_path(self, font_key: str) -> str:
        """
        Resolve a font key (e.g. 'headline_font') to its absolute path.
        Raises ConfigError if font_key is not in brand.fonts.
        """
        fonts = self.brand.get("fonts", {})
        if font_key not in fonts:
            raise ConfigError(
                f"Font key '{font_key}' not found in brand config fonts section. "
                f"Available keys: {list(fonts.keys())}"
            )
        return self.abs_path(fonts[font_key])

    @property
    def canvas_width(self) -> int:
        return self.effective["canvas_width"]

    @property
    def canvas_height(self) -> int:
        return self.effective["canvas_height"]

    @property
    def logo_width_px(self) -> int:
        pct = self.effective.get("logo", {}).get(
            "default_width_pct", self.brand["logo"]["default_width_pct"]
        )
        return int(self.canvas_width * pct)

    @property
    def logo_padding(self) -> int:
        return self.effective.get("logo", {}).get(
            "padding_px", self.brand["logo"]["padding_px"]
        )

    @property
    def logo_position(self) -> str:
        # Template can override brand default
        return (
            self.effective.get("logo_position")
            or self.brand["logo"]["position"]
        )

    @property
    def logo_abs_path(self) -> str:
        return self.abs_path(self.brand["logo"]["path"])

    @property
    def export_format(self) -> str:
        return self.effective.get("export", {}).get("format", "jpeg")


def _deep_merge(base: dict, override: dict) -> dict:
    """
    Recursively merge override into base. Override values win.
    Returns a new dict (does not mutate inputs).
    """
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


def load_brand_config(brand_path: str) -> dict:
    """
    Load config/brand.yaml.

    Raises:
        ConfigError: If file is missing or contains invalid YAML
    """
    if not os.path.isfile(brand_path):
        raise ConfigError(
            f"Brand config not found: {brand_path}\n"
            f"  Expected at: config/brand.yaml relative to project root"
        )
    with open(brand_path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in brand config: {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"brand.yaml must be a YAML mapping, got {type(data).__name__}")
    return data


def load_template_config(template_name: str, templates_dir: str) -> dict:
    """
    Load config/templates/{template_name}.yaml.

    Args:
        template_name: e.g. 'breaking_news'
        templates_dir: Absolute path to config/templates/ directory

    Raises:
        ConfigError: If template file is missing or invalid YAML
    """
    path = os.path.join(templates_dir, f"{template_name}.yaml")
    if not os.path.isfile(path):
        raise ConfigError(
            f"Template config not found: {path}\n"
            f"  Available templates should be in: {templates_dir}"
        )
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in template config '{template_name}': {e}") from e
    if not isinstance(data, dict):
        raise ConfigError(f"Template '{template_name}' YAML must be a mapping")
    return data


def build_template_config(
    template_name: str,
    project_root: str,
) -> TemplateConfig:
    """
    Load, merge, and validate brand + template config.

    Args:
        template_name: e.g. 'breaking_news'
        project_root: Absolute path to the project root directory

    Returns:
        TemplateConfig ready for use by renderers
    """
    brand_path = os.path.join(project_root, "config", "brand.yaml")
    templates_dir = os.path.join(project_root, "config", "templates")

    brand = load_brand_config(brand_path)
    template = load_template_config(template_name, templates_dir)
    effective = _deep_merge(brand, template)

    return TemplateConfig(
        brand=brand,
        template=template,
        effective=effective,
        project_root=project_root,
    )
