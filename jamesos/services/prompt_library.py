from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


PROMPT_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "PromptLibrary"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Creative Foundations.md"

DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "positive_product_art": {
        "name": "positive_product_art",
        "category": "positive",
        "template": "{brand_voice}. Product artwork for {product_type}: {prompt}. Clean composition, marketplace-safe, review draft only.",
        "recommended_for": ["product_art", "listing_image"],
        "enabled": False,
    },
    "negative_marketplace_safe": {
        "name": "negative_marketplace_safe",
        "category": "negative",
        "template": "copyrighted logos, trademarked characters, hateful symbols, explicit content, watermark, blurry, misspelled text, upload, publishing",
        "recommended_for": ["all"],
        "enabled": False,
    },
    "typography_design": {
        "name": "typography_design",
        "category": "typography",
        "template": "bold readable typography, strong silhouette, centered layout, {brand_voice}, phrase: {prompt}",
        "recommended_for": ["shirts", "stickers", "posters"],
        "enabled": False,
    },
    "transparent_png": {
        "name": "transparent_png",
        "category": "transparent_png",
        "template": "transparent background PNG-style artwork, clean edges, no background scene, {prompt}",
        "recommended_for": ["stickers", "shirts", "totes"],
        "enabled": False,
    },
    "product_art": {
        "name": "product_art",
        "category": "product_art",
        "template": "print-on-demand product art, balanced composition, high readability, {prompt}",
        "recommended_for": ["apparel", "mugs", "stickers"],
        "enabled": False,
    },
    "mockup": {
        "name": "mockup",
        "category": "mockup",
        "template": "local review mockup concept for {product_type}, clean product-forward presentation, no upload, {prompt}",
        "recommended_for": ["mockups", "listing previews"],
        "enabled": False,
    },
}


def initialize_prompt_library(root: Path | None = None) -> dict[str, Any]:
    library_root = root or PROMPT_ROOT
    library_root.mkdir(parents=True, exist_ok=True)
    created = []
    for name, template in DEFAULT_TEMPLATES.items():
        path = library_root / f"{name}.yaml"
        if not path.exists():
            path.write_text(yaml.safe_dump(template, sort_keys=False), encoding="utf-8")
            created.append(name)
    return {"status": "ok", "root": str(library_root), "created": created}


def load_prompt_templates(root: Path | None = None) -> dict[str, Any]:
    library_root = root or PROMPT_ROOT
    initialize_prompt_library(library_root)
    templates: dict[str, dict[str, Any]] = {}
    for path in sorted(library_root.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        name = str(data.get("name") or path.stem)
        templates[name] = {**DEFAULT_TEMPLATES.get(name, {}), **data, "enabled": False}
    return {
        "status": "ok",
        "root": str(library_root),
        "templates": templates,
        "template_count": len(templates),
        "execution_enabled": False,
    }


def get_prompt_template(template_name: str, root: Path | None = None) -> dict[str, Any]:
    templates = load_prompt_templates(root)["templates"]
    template = templates.get(template_name)
    if template is None:
        raise KeyError(f"Unknown prompt template: {template_name}")
    return {"status": "ok", "template": template, "execution_enabled": False}


def select_prompt_template(package: dict[str, Any], root: Path | None = None) -> dict[str, Any]:
    text = " ".join(str(package.get(key, "")) for key in ["workflow_type", "product_type", "niche", "title", "design_prompt"]).lower()
    if "mockup" in text:
        name = "mockup"
    elif "transparent" in text or "png" in text:
        name = "transparent_png"
    elif "typography" in text or "shirt" in text or "sticker" in text:
        name = "typography_design"
    else:
        name = "product_art"
    return get_prompt_template(name, root)["template"]

