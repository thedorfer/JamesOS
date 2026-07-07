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


NEGATIVE_PRINT_DESIGN_TERMS = [
    "person",
    "human",
    "model",
    "wearing",
    "shirt on body",
    "product photo",
    "lifestyle photo",
    "room",
    "shelf",
    "mannequin",
    "face",
    "hands",
    "body",
    "realistic person",
    "portrait",
    "mockup",
    "blurry text",
    "misspelled text",
    "watermark",
]


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item).strip() for item in value if str(item).strip())
    return str(value).strip()


def _clean_prompt(text: str) -> str:
    cleaned = " ".join(text.replace("..", ".").split())
    return cleaned.lstrip(" .,:;-\n\t")


def _sentence(label: str, value: Any) -> str:
    rendered = _text(value)
    return f"{label}: {rendered}." if rendered else ""


def _join_parts(parts: list[str]) -> str:
    return _clean_prompt(" ".join(part.strip() for part in parts if part and part.strip()))


def _negative_prompt(extra: str = "", include_design_terms: bool = True) -> str:
    terms = [
        "copyrighted logos",
        "trademarked characters",
        "hateful symbols",
        "explicit content",
        "upload",
        "publishing",
    ]
    if include_design_terms:
        terms.extend(NEGATIVE_PRINT_DESIGN_TERMS)
    if extra:
        terms.append(extra)
    return _clean_prompt(", ".join(dict.fromkeys(term for term in terms if term)))


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


def _recipe_prompt_package(creative_spec: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    product_type = _text(recipe.get("product_type") or creative_spec.get("product_type") or "design_art")
    niche = _text(recipe.get("niche") or creative_spec.get("niche"))
    provider = _text(recipe.get("provider") or creative_spec.get("pod_provider") or creative_spec.get("provider") or "printify")
    is_mockup_stage = "mockup" in _text(creative_spec.get("stage") or recipe.get("stage")).lower()
    assets = recipe.get("assets") or creative_spec.get("selected_assets") or creative_spec.get("assets") or []
    motifs = recipe.get("motifs") or creative_spec.get("motifs") or []
    positive_parts = [
        _sentence("Design goal", recipe.get("design_goal")),
        f"Standalone print design for {product_type}" + (f" and {niche}." if niche else "."),
        _sentence("Artwork type", recipe.get("artwork_type") or "flat print design"),
        _sentence("Background", recipe.get("background") or "white or transparent-background-friendly"),
        _sentence("Layout", recipe.get("layout") or "centered composition"),
        _sentence("Palette", recipe.get("palette")),
        _sentence("Text", recipe.get("text") or creative_spec.get("text")),
        _sentence("Typography", recipe.get("typography") or creative_spec.get("typography")),
        _sentence("Motifs", motifs),
        _sentence("Assets/reference motifs", assets),
        _sentence("Effects", recipe.get("effects") or "clean vector-style print art"),
        _sentence("Provider", provider),
        _sentence("Print notes", recipe.get("print_notes") or "high contrast, large readable typography, print-on-demand ready, no person, no mockup"),
    ]
    if not is_mockup_stage:
        positive_parts.extend([
            "Vector-style or clean graphic artwork.",
            "Centered composition.",
            "No person.",
            "No human model.",
            "No product mockup.",
            "No lifestyle background.",
            "High contrast.",
            "Large readable typography.",
            "Print-on-demand ready.",
        ])
    positive = _join_parts(positive_parts)
    lower = " ".join([_text(recipe.get("artwork_type")), product_type, niche, _text(recipe.get("layout"))]).lower()
    if is_mockup_stage:
        workflow_type = "mockup"
    elif "transparent" in lower or "sticker" in lower:
        workflow_type = "transparent_png"
    else:
        workflow_type = "print_design_basic"
    negative = _negative_prompt(_text(creative_spec.get("safety_notes")), include_design_terms=not is_mockup_stage)
    return {
        "positive_prompt": positive,
        "negative_prompt": negative,
        "width": int(creative_spec.get("width") or recipe.get("width") or 768),
        "height": int(creative_spec.get("height") or recipe.get("height") or 768),
        "recommended_workflow_type": workflow_type,
        "recommended_model_family": "flux" if "flux" in lower else ("sdxl" if "sdxl" in lower else "sd15"),
        "creative_spec": creative_spec,
        "design_recipe": recipe,
        "execution_enabled": False,
    }


def creative_spec_to_prompt_package(creative_spec: dict[str, Any]) -> dict[str, Any]:
    recipe = creative_spec.get("design_recipe")
    if isinstance(recipe, dict) and recipe:
        return _recipe_prompt_package(creative_spec, recipe)

    brand_voice = _text(creative_spec.get("brand_voice"))
    product_type = _text(creative_spec.get("product_type") or "product")
    niche = _text(creative_spec.get("niche"))
    audience = _text(creative_spec.get("audience"))
    emotional_hook = _text(creative_spec.get("emotional_hook"))
    style = _text(creative_spec.get("style") or "bold")
    colors = creative_spec.get("colors") or []
    text = _text(creative_spec.get("text"))
    typography = _text(creative_spec.get("typography"))
    assets = creative_spec.get("assets") or []
    stage = _text(creative_spec.get("stage") or creative_spec.get("image_stage") or "design_art")
    layout = _text(creative_spec.get("layout") or "flat centered print artwork")
    print_requirements = _text(
        creative_spec.get("print_requirements")
        or "flat design only, print-ready graphic, POD-safe, high contrast, large readable text, white or transparent-background-friendly background"
    )
    safety_notes = _text(creative_spec.get("safety_notes") or "marketplace-safe, no copyrighted logos")

    color_text = _text(colors)
    asset_text = _text(assets)
    is_mockup_stage = "mockup" in stage.lower()
    if is_mockup_stage:
        positive = _join_parts([
            brand_voice,
            f"Local review mockup concept for {product_type}" + (f" artwork for {niche}." if niche else "."),
            _sentence("Audience", audience),
            _sentence("Emotional hook", emotional_hook),
            _sentence("Text", text),
            _sentence("Typography", typography),
            _sentence("Colors", color_text),
            _sentence("Assets/reference motifs", asset_text),
            _sentence("Layout", layout),
            print_requirements,
            "Review-only mockup, no upload.",
        ])
    else:
        positive = _join_parts([
            brand_voice,
            f"Standalone print design, flat centered print artwork for {product_type}" + (f" and {niche}." if niche else "."),
            "Vector-style or clean graphic artwork.",
            "Centered composition.",
            "No person.",
            "No human model.",
            "No product mockup.",
            "No lifestyle background.",
            "High contrast.",
            "Large readable typography.",
            "Print-on-demand ready.",
            _sentence("Audience", audience),
            _sentence("Emotional hook", emotional_hook),
            _sentence("Text", text),
            _sentence("Typography", typography),
            _sentence("Colors", color_text),
            _sentence("Assets/reference motifs", asset_text),
            _sentence("Layout", layout),
            print_requirements,
        ])
    negative = _negative_prompt(safety_notes, include_design_terms=not is_mockup_stage)

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
