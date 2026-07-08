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

DESIGN_RECIPE_TEMPLATES: dict[str, dict[str, Any]] = {
    "typography": {
        "composition": "large centered typography with supporting motif",
        "effects": "clean vector edges, high contrast",
        "typography_style": "bold readable sans",
        "negative_emphasis": ["blurry text", "misspelled text", "thin unreadable lettering"],
        "print_recommendations": "thumbnail readable, safe margins, crisp lettering",
    },
    "sticker": {
        "composition": "single centered sticker-like focal point",
        "effects": "clean outline, flat color fills, crisp edges",
        "typography_style": "bold rounded sans when text is present",
        "negative_emphasis": ["background scene", "photo texture", "busy detail"],
        "print_recommendations": "isolated artwork, strong silhouette, transparent background requested",
    },
    "minimal": {
        "composition": "simple centered focal point with generous spacing",
        "effects": "minimal flat graphic, no unnecessary detail",
        "typography_style": "clean modern sans",
        "negative_emphasis": ["clutter", "busy background", "tiny details"],
        "print_recommendations": "clean silhouette, high contrast, safe margins",
    },
    "vintage": {
        "composition": "centered vintage badge layout",
        "effects": "subtle distressed print texture, retro ink feel",
        "typography_style": "vintage display lettering",
        "negative_emphasis": ["photograph", "realistic person", "muddy colors"],
        "print_recommendations": "limited palette, readable from thumbnail",
    },
    "retro": {
        "composition": "balanced retro poster-style focal point",
        "effects": "flat retro color blocks, clean edges",
        "typography_style": "bold retro display type",
        "negative_emphasis": ["lens flare", "photo realism", "background scene"],
        "print_recommendations": "strong contrast, clear shape language",
    },
    "badge": {
        "composition": "centered badge with border and single focal icon",
        "effects": "flat emblem style, crisp outline",
        "typography_style": "arched bold badge lettering",
        "negative_emphasis": ["tiny text", "crowded symbols", "mockup"],
        "print_recommendations": "safe margins, balanced spacing, print-ready silhouette",
    },
    "emblem": {
        "composition": "symmetrical emblem with one focal motif",
        "effects": "clean vector emblem, high contrast",
        "typography_style": "bold emblem lettering",
        "negative_emphasis": ["asymmetrical clutter", "photo texture", "background scene"],
        "print_recommendations": "centered, isolated, scalable artwork",
    },
    "line_art": {
        "composition": "centered line-art focal point",
        "effects": "clean consistent line weight",
        "typography_style": "minimal sans",
        "negative_emphasis": ["messy lines", "sketch noise", "low contrast"],
        "print_recommendations": "bold enough line weight for apparel printing",
    },
    "cartoon": {
        "composition": "single cartoon focal point with readable support text",
        "effects": "flat cartoon illustration, crisp outline",
        "typography_style": "friendly rounded bold type",
        "negative_emphasis": ["realistic person", "photograph", "busy scene"],
        "print_recommendations": "clean silhouette, bright but controlled palette",
    },
    "grunge": {
        "composition": "centered distressed typography and simple motif",
        "effects": "controlled grunge texture, screenprint feel",
        "typography_style": "bold distressed display type",
        "negative_emphasis": ["muddy detail", "unreadable text", "photo background"],
        "print_recommendations": "keep distress subtle enough for readable print",
    },
    "watercolor": {
        "composition": "centered soft motif with clean printable edges",
        "effects": "watercolor-inspired color wash, simplified for printing",
        "typography_style": "clean readable sans or script accent",
        "negative_emphasis": ["muddy wash", "blurred text", "background scene"],
        "print_recommendations": "preserve contrast and isolated shape",
    },
    "seasonal": {
        "composition": "centered seasonal motif and short readable phrase",
        "effects": "clean festive vector style",
        "typography_style": "bold seasonal display lettering",
        "negative_emphasis": ["busy holiday scene", "photo props", "tiny ornaments"],
        "print_recommendations": "clear seasonal signal, safe margins, high contrast",
    },
}

QUALITY_LEVELS: dict[str, list[str]] = {
    "draft": ["clear concept", "simple printable layout"],
    "production": ["clean vector-like artwork", "crisp typography", "balanced spacing", "high contrast", "thumbnail readable"],
    "premium": [
        "vector-like",
        "clean edges",
        "crisp typography",
        "balanced spacing",
        "isolated artwork",
        "transparent background",
        "high contrast",
        "thumbnail optimization",
    ],
}


NEGATIVE_PRINT_DESIGN_TERMS = [
    "person",
    "human",
    "model",
    "people",
    "woman",
    "man",
    "child",
    "wearing",
    "shirt",
    "pants",
    "underwear",
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
    "background scene",
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


def _asset_name(asset: Any) -> str:
    if isinstance(asset, dict):
        return _text(asset.get("name") or Path(str(asset.get("path") or "")).stem)
    return Path(str(asset)).stem


def describe_asset_for_prompt(asset: Any) -> str:
    if isinstance(asset, dict) and asset.get("prompt_description"):
        return _text(asset.get("prompt_description"))
    name = _asset_name(asset)
    normalized = name.lower().replace("-", "_").replace(" ", "_")
    if "gay_pride_flag" in normalized or ("pride" in normalized and "flag" in normalized and "trans" not in normalized and "intersex" not in normalized):
        return "six-stripe rainbow pride flag colors"
    if "transgender_pride" in normalized or "trans_pride" in normalized:
        return "pastel blue, pink, and white trans pride colors"
    if "intersex" in normalized:
        return "inclusive pride flag color palette"
    if "unitystitches" in normalized and "logo" in normalized:
        return "optional small brand mark space, do not recreate exact logo"
    if "rainbow" in normalized:
        return "rainbow pride color accents"
    if "logo" in normalized:
        return "optional small brand mark space"
    if "flag" in normalized:
        return "flag-inspired color palette"
    return normalized.replace("_", " ")


def asset_prompt_descriptions(assets: Any) -> list[str]:
    if not isinstance(assets, list):
        assets = [assets] if assets else []
    descriptions = [describe_asset_for_prompt(asset) for asset in assets if describe_asset_for_prompt(asset)]
    return list(dict.fromkeys(descriptions))


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
        terms.extend(part.strip() for part in extra.split(",") if part.strip())
    return _clean_prompt(", ".join(dict.fromkeys(term for term in terms if term)))


def recipe_template(template_name: str) -> dict[str, Any]:
    key = (template_name or "sticker").strip().lower().replace(" ", "_").replace("-", "_")
    return DESIGN_RECIPE_TEMPLATES.get(key, DESIGN_RECIPE_TEMPLATES["sticker"])


def list_design_recipe_templates() -> dict[str, Any]:
    return {
        "status": "ok",
        "templates": DESIGN_RECIPE_TEMPLATES,
        "template_count": len(DESIGN_RECIPE_TEMPLATES),
        "execution_enabled": False,
    }


def _quality_terms(level: str) -> list[str]:
    return QUALITY_LEVELS.get((level or "production").lower(), QUALITY_LEVELS["production"])


def _section(title: str, items: list[Any]) -> str:
    rendered = [_text(item) for item in items if _text(item)]
    if not rendered:
        return ""
    return f"{title}\n" + "\n".join(dict.fromkeys(rendered))


def _structured_prompt(sections: list[tuple[str, list[Any]]]) -> str:
    text = "\n\n".join(_section(title, items) for title, items in sections if _section(title, items))
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).lstrip(" .,:;-\n\t")


def _composition_metadata(template: dict[str, Any], recipe: dict[str, Any], quality_level: str) -> dict[str, Any]:
    return {
        "composition": _text(recipe.get("composition") or template.get("composition") or "centered single focal point"),
        "canvas_coverage": "approximately 75% of canvas",
        "centered": True,
        "safe_margins": True,
        "single_focal_point": True,
        "balanced_composition": True,
        "thumbnail_readable": True,
        "clean_silhouette": True,
        "high_contrast": True,
        "large_readable_typography": True,
        "minimal_unnecessary_detail": True,
        "quality_level": quality_level,
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


def _recipe_prompt_package(creative_spec: dict[str, Any], recipe: dict[str, Any]) -> dict[str, Any]:
    product_type = _text(recipe.get("product_type") or creative_spec.get("product_type") or "design_art")
    niche = _text(recipe.get("niche") or creative_spec.get("niche"))
    provider = _text(recipe.get("provider") or creative_spec.get("pod_provider") or creative_spec.get("provider") or "printify")
    is_mockup_stage = "mockup" in _text(creative_spec.get("stage") or recipe.get("stage")).lower()
    assets = recipe.get("assets") or creative_spec.get("selected_assets") or creative_spec.get("assets") or []
    asset_descriptions = asset_prompt_descriptions(assets)
    motifs = recipe.get("motifs") or creative_spec.get("motifs") or []
    template_name = _text(recipe.get("template") or recipe.get("style_template") or creative_spec.get("design_template") or "minimal")
    template = recipe_template(template_name)
    quality_level = _text(recipe.get("quality") or creative_spec.get("quality") or "production").lower() or "production"
    composition = _composition_metadata(template, recipe, quality_level)
    text = _text(recipe.get("text") or creative_spec.get("text"))
    typography = _text(recipe.get("typography") or template.get("typography_style") or creative_spec.get("typography"))
    lower = " ".join([_text(recipe.get("artwork_type")), product_type, niche, _text(recipe.get("layout")), _text(recipe.get("background")), template_name]).lower()
    if is_mockup_stage:
        positive = _structured_prompt([
            ("STYLE", ["local review mockup concept", recipe.get("artwork_type"), recipe.get("effects") or template.get("effects")]),
            ("SUBJECT", [recipe.get("design_goal"), product_type, niche, motifs, asset_descriptions]),
            ("TYPOGRAPHY", [text, typography]),
            ("LAYOUT", [recipe.get("layout") or template.get("composition"), "balanced spacing"]),
            ("PRINT", ["review-only mockup", "no upload", provider]),
        ])
    else:
        positive = _structured_prompt([
            ("STYLE", [
                recipe.get("artwork_type") or "clean vector illustration",
                "flat graphic",
                "sticker artwork",
                recipe.get("background") or "transparent background",
                "high contrast",
                recipe.get("effects") or template.get("effects"),
                _quality_terms(quality_level),
            ]),
            ("SUBJECT", [recipe.get("design_goal"), product_type, niche, motifs, asset_descriptions]),
            ("TYPOGRAPHY", [text, typography]),
            ("LAYOUT", [
                recipe.get("layout") or template.get("composition"),
                composition["canvas_coverage"],
                "centered",
                "safe margins",
                "single focal point",
                "balanced composition",
                "clean silhouette",
            ]),
            ("PRINT", [
                "isolated artwork",
                "white background or transparent",
                "POD ready",
                "thumbnail readable",
                "large readable typography",
                _sentence("Print notes", recipe.get("print_notes") or template.get("print_recommendations")),
                provider,
            ]),
        ])
    transparent_requested = (
        "transparent background" in lower
        or "transparent print" in lower
        or template_name.lower() == "sticker"
        or "sticker" in lower
    )
    if is_mockup_stage:
        workflow_type = "mockup"
    elif transparent_requested:
        workflow_type = "transparent_print_design_basic"
    else:
        workflow_type = "print_design_basic"
    negative_extra = ", ".join([
        _text(creative_spec.get("safety_notes")),
        _text(recipe.get("negative_emphasis")),
        _text(template.get("negative_emphasis")),
    ])
    negative = _negative_prompt(negative_extra, include_design_terms=not is_mockup_stage)
    return {
        "positive_prompt": positive,
        "negative_prompt": negative,
        "width": int(creative_spec.get("width") or recipe.get("width") or 768),
        "height": int(creative_spec.get("height") or recipe.get("height") or 768),
        "recommended_workflow_type": workflow_type,
        "recommended_model_family": "flux" if "flux" in lower else ("sdxl" if "sdxl" in lower else "sd15"),
        "creative_spec": creative_spec,
        "design_recipe": recipe,
        "asset_prompt_descriptions": asset_descriptions,
        "composition_metadata": composition,
        "design_quality_level": quality_level,
        "design_recipe_template": template_name,
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
    quality_level = _text(creative_spec.get("quality") or "production").lower() or "production"
    template_name = _text(creative_spec.get("design_template") or "sticker")
    template = recipe_template(template_name)
    composition = _composition_metadata(template, {"layout": layout}, quality_level)

    color_text = _text(colors)
    asset_descriptions = asset_prompt_descriptions(assets)
    asset_text = _text(asset_descriptions)
    is_mockup_stage = "mockup" in stage.lower()
    if is_mockup_stage:
        positive = _structured_prompt([
            ("STYLE", [brand_voice, "local review mockup concept", style]),
            ("SUBJECT", [product_type, niche, audience, emotional_hook, color_text, asset_text]),
            ("TYPOGRAPHY", [text, typography]),
            ("LAYOUT", [layout, "balanced spacing"]),
            ("PRINT", [print_requirements, "review-only mockup", "no upload"]),
        ])
    else:
        positive = _structured_prompt([
            ("STYLE", [
                brand_voice,
                "Standalone print design",
                "flat centered print artwork",
                "clean vector illustration",
                "flat graphic",
                "sticker artwork",
                "high contrast",
                style,
                _quality_terms(quality_level),
            ]),
            ("SUBJECT", [product_type, niche, audience, emotional_hook, color_text, asset_text]),
            ("TYPOGRAPHY", [text, typography]),
            ("LAYOUT", [
                layout,
                composition["canvas_coverage"],
                "centered",
                "safe margins",
                "single focal point",
                "balanced composition",
                "thumbnail readable",
                "clean silhouette",
            ]),
            ("PRINT", [
                print_requirements,
                "isolated artwork",
                "white background or transparent",
                "POD ready",
                "large readable typography",
                "No person",
                "No human model",
                "No product mockup",
                "No lifestyle background",
            ]),
        ])
    negative = _negative_prompt(safety_notes, include_design_terms=not is_mockup_stage)

    lower = " ".join([stage, style, product_type, niche, layout, text]).lower()
    if "transparent" in lower or "sticker" in lower:
        workflow_type = "transparent_print_design_basic"
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
        "asset_prompt_descriptions": asset_descriptions,
        "composition_metadata": composition,
        "design_quality_level": quality_level,
        "design_recipe_template": template_name,
        "execution_enabled": False,
    }
