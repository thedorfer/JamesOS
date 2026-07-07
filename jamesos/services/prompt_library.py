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
        "template": "{brand_voice}. Flat printable design artwork for {product_type}: {prompt}. Standalone centered print graphic, no person, no model, no mockup, white or transparent-background-friendly background, marketplace-safe, review draft only.",
        "recommended_for": ["print_design_basic", "product_art", "listing_image"],
        "enabled": False,
    },
    "negative_marketplace_safe": {
        "name": "negative_marketplace_safe",
        "category": "negative",
        "template": "copyrighted logos, trademarked characters, hateful symbols, explicit content, watermark, blurry, misspelled text, upload, publishing, person, human, model, wearing, shirt on body, product photo, lifestyle photo, room, shelf, mannequin, face, hands, body, realistic person, portrait, mockup",
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
        "template": "flat print-on-demand design artwork, standalone centered graphic, white or transparent-background-friendly background, high contrast, large readable text, no person, no mockup, {prompt}",
        "recommended_for": ["apparel", "mugs", "stickers"],
        "enabled": False,
    },
    "print_design_basic": {
        "name": "print_design_basic",
        "category": "print_design",
        "template": "flat printable POD-safe artwork, centered composition, standalone graphic, white or transparent-background-friendly background, high contrast, large readable text, no person, no product photo, no lifestyle scene, {prompt}",
        "recommended_for": ["design_art", "apparel", "mugs", "stickers", "totes"],
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
    elif "print_design" in text or "design_art" in text or "product_art" in text:
        name = "print_design_basic"
    elif "transparent" in text or "png" in text:
        name = "transparent_png"
    elif "typography" in text or "shirt" in text or "sticker" in text:
        name = "typography_design"
    else:
        name = "product_art"
    return get_prompt_template(name, root)["template"]


def creative_spec_to_prompt_package(creative_spec: dict[str, Any]) -> dict[str, Any]:
    brand_voice = str(creative_spec.get("brand_voice") or "")
    product_type = str(creative_spec.get("product_type") or "product")
    niche = str(creative_spec.get("niche") or "")
    audience = str(creative_spec.get("audience") or "")
    emotional_hook = str(creative_spec.get("emotional_hook") or "")
    style = str(creative_spec.get("style") or "bold")
    colors = creative_spec.get("colors") or []
    text = str(creative_spec.get("text") or "")
    typography = str(creative_spec.get("typography") or "")
    assets = creative_spec.get("assets") or []
    stage = str(creative_spec.get("stage") or creative_spec.get("image_stage") or "design_art")
    layout = str(creative_spec.get("layout") or "flat centered print artwork")
    print_requirements = str(
        creative_spec.get("print_requirements")
        or "flat design only, print-ready graphic, POD-safe, high contrast, large readable text, white or transparent-background-friendly background"
    )
    safety_notes = str(creative_spec.get("safety_notes") or "marketplace-safe, no copyrighted logos")

    color_text = ", ".join(str(item) for item in colors) if isinstance(colors, list) else str(colors)
    asset_text = ", ".join(str(item) for item in assets) if isinstance(assets, list) else str(assets)
    is_mockup_stage = "mockup" in stage.lower()
    if is_mockup_stage:
        positive = (
            f"{brand_voice}. Local review mockup concept for {product_type} artwork for {niche}. "
            f"Audience: {audience}. Emotional hook: {emotional_hook}. Text: {text}. "
            f"Typography: {typography}. Colors: {color_text}. Assets/reference motifs: {asset_text}. "
            f"Layout: {layout}. {print_requirements}. Review-only mockup, no upload."
        ).strip()
    else:
        positive = (
            f"{brand_voice}. Standalone print design, flat centered print artwork for {product_type} and {niche}. "
            "Flat design only, no human model, no person wearing product, no room or lifestyle background, "
            "white or transparent-background-friendly background, print-ready graphic, POD-safe, high contrast, large readable text. "
            f"Audience: {audience}. Emotional hook: {emotional_hook}. "
            f"Text: {text}. Typography: {typography}. Colors: {color_text}. "
            f"Assets/reference motifs: {asset_text}. Layout: {layout}. {print_requirements}."
        ).strip()
    negative = (
        "copyrighted logos, trademarked characters, hateful symbols, explicit content, watermark, "
        "blurry, misspelled text, upload, publishing"
        + (
            ""
            if is_mockup_stage
            else ", person, human, model, wearing, shirt on body, product photo, lifestyle photo, room, shelf, mannequin, face, hands, body, realistic person, portrait, mockup"
        )
        + f". {safety_notes}"
    ).strip()

    lower = " ".join([stage, style, product_type, niche, layout, text]).lower()
    if "transparent" in lower or "sticker" in lower:
        workflow_type = "transparent_png"
    elif is_mockup_stage:
        workflow_type = "mockup"
    elif "design_art" in lower or "print_design" in lower or "product_art" in lower:
        workflow_type = "print_design_basic"
    elif "typography" in lower or text:
        workflow_type = "typography"
    else:
        workflow_type = "print_design_basic"

    if "flux" in lower:
        model_family = "flux"
    elif "sdxl" in lower:
        model_family = "sdxl"
    else:
        model_family = "sd15"

    return {
        "positive_prompt": positive,
        "negative_prompt": negative,
        "width": int(creative_spec.get("width") or 768),
        "height": int(creative_spec.get("height") or 768),
        "recommended_workflow_type": workflow_type,
        "recommended_model_family": model_family,
        "creative_spec": creative_spec,
        "execution_enabled": False,
    }
