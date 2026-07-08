from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


RECIPE_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Recipes"


DEFAULT_RECIPES: dict[str, dict[str, Any]] = {
    "pride/typography_badge": {
        "name": "Pride Typography Badge",
        "design_family": "pride_typography",
        "shop_fit": ["unitystitches"],
        "product_fit": ["shirt", "hoodie", "mug", "tote", "sticker"],
        "avoid_product_types": ["womens_underwear", "panties", "thong"],
        "niche_fit": ["LGBTQ+ pride", "trans pride", "ally"],
        "design_type": "typography_badge",
        "art_style": "clean vector badge",
        "layout": "centered badge with bold headline text",
        "palette": ["rainbow", "white", "black accent"],
        "typography": "bold rounded sans",
        "text_strategy": "large_readable_text",
        "motifs": ["rainbow arc", "heart", "sparkles"],
        "pattern_strategy": "single badge, no repeat",
        "layer_plan": ["transparent_canvas", "base_shape", "motif", "typography", "accent", "final_composite"],
        "composition_rules": ["75% canvas coverage", "safe margins", "single focal point"],
        "quality_rules": ["high contrast", "thumbnail readable", "crisp typography"],
        "negative_rules": ["person", "mockup", "photograph", "blurry text", "misspelled text"],
        "commercial_goal": "bold pride statement gift design",
        "difficulty": "medium",
        "estimated_generation_cost": "low",
        "reuse_notes": "Reusable badge system for apparel and stickers.",
        "trademark_safety_notes": "Use generic pride phrases only.",
        "provider_notes": "Manual upload candidate only; no provider API calls.",
    },
    "pride/rainbow_heart_sticker": {
        "name": "Rainbow Heart Sticker",
        "design_family": "pride_sticker",
        "shop_fit": ["unitystitches"],
        "product_fit": ["shirt", "hoodie", "mug", "tote", "sticker"],
        "avoid_product_types": [],
        "niche_fit": ["LGBTQ+ pride", "ally"],
        "design_type": "sticker",
        "art_style": "cute clean vector sticker",
        "layout": "centered rainbow heart with sparkles",
        "palette": ["rainbow", "white", "black accent"],
        "typography": "optional small rounded sans",
        "text_strategy": "optional_short_text",
        "motifs": ["rainbow heart", "sparkles", "soft stars"],
        "pattern_strategy": "single sticker motif",
        "layer_plan": ["transparent_canvas", "base_shape", "motif", "accent", "final_composite"],
        "composition_rules": ["75% canvas coverage", "safe margins", "single focal point"],
        "quality_rules": ["clean silhouette", "high contrast", "crisp edges"],
        "negative_rules": ["person", "mockup", "photo", "background scene"],
        "commercial_goal": "giftable pride sticker-style artwork",
        "difficulty": "low",
        "estimated_generation_cost": "low",
        "reuse_notes": "Reusable pride motif for stickers, shirts, mugs, and totes.",
        "trademark_safety_notes": "Avoid copyrighted characters.",
        "provider_notes": "Manual upload candidate only; no provider API calls.",
    },
    "pride/trans_pastel_cute": {
        "name": "Trans Pastel Cute",
        "design_family": "trans_pride_cute",
        "shop_fit": ["unitystitches"],
        "product_fit": ["shirt", "hoodie", "mug", "tote", "sticker", "womens_underwear", "panties", "thong"],
        "avoid_product_types": [],
        "niche_fit": ["trans pride"],
        "design_type": "cute_motif",
        "art_style": "soft pastel vector",
        "layout": "centered pastel motif with tiny accents",
        "palette": ["pastel blue", "pink", "white"],
        "typography": "minimal rounded sans",
        "text_strategy": "minimal_hidden_text",
        "motifs": ["pastel hearts", "sparkles", "soft ribbon"],
        "pattern_strategy": "motif cluster or simple repeat",
        "layer_plan": ["transparent_canvas", "motif", "accent", "final_composite"],
        "composition_rules": ["safe margins", "soft balanced spacing"],
        "quality_rules": ["clean edges", "printable contrast"],
        "negative_rules": ["person", "mockup", "large text"],
        "commercial_goal": "soft affirming pride artwork",
        "difficulty": "low",
        "estimated_generation_cost": "low",
        "reuse_notes": "Works as motif or small repeating pattern.",
        "trademark_safety_notes": "Generic pride colors only.",
        "provider_notes": "Manual upload candidate only; no provider API calls.",
    },
    "underwear/pride_pattern": {
        "name": "Pride Pattern",
        "design_family": "underwear_pride_pattern",
        "shop_fit": ["unitystitches"],
        "product_fit": ["womens_underwear", "panties", "thong"],
        "avoid_product_types": [],
        "niche_fit": ["LGBTQ+ pride", "trans pride", "nonbinary pride"],
        "design_type": "repeat_pattern",
        "art_style": "clean vector pattern",
        "layout": "balanced seamless-style repeat motif",
        "palette": ["rainbow", "white", "soft neutrals"],
        "typography": "none",
        "text_strategy": "no_text",
        "motifs": ["tiny hearts", "rainbow ribbons", "sparkles"],
        "pattern_strategy": "seamless-style repeat, no large typography",
        "layer_plan": ["transparent_canvas", "pattern", "motif", "accent", "final_composite"],
        "composition_rules": ["balanced repeat", "safe scale", "no single large text block"],
        "quality_rules": ["clean repeat rhythm", "printable contrast", "not cluttered"],
        "negative_rules": ["large text", "slogan", "person", "mockup", "photo"],
        "commercial_goal": "wearable pride pattern for intimate apparel",
        "difficulty": "medium",
        "estimated_generation_cost": "low",
        "reuse_notes": "Reusable for underwear/panty/thong pattern systems.",
        "trademark_safety_notes": "No protected logos or characters.",
        "provider_notes": "Manual upload target: printify. No provider API calls.",
    },
    "underwear/coquette_hearts": {
        "name": "Coquette Hearts",
        "design_family": "underwear_coquette",
        "shop_fit": ["unitystitches"],
        "product_fit": ["womens_underwear", "panties", "thong"],
        "avoid_product_types": [],
        "niche_fit": ["self love", "pride", "seasonal"],
        "design_type": "repeat_pattern",
        "art_style": "cute coquette vector",
        "layout": "small bow and heart repeat",
        "palette": ["pink", "white", "soft red"],
        "typography": "none",
        "text_strategy": "no_text",
        "motifs": ["bows", "tiny hearts", "sparkles"],
        "pattern_strategy": "small balanced repeat",
        "layer_plan": ["transparent_canvas", "pattern", "motif", "accent", "final_composite"],
        "composition_rules": ["small scale", "balanced spacing"],
        "quality_rules": ["clean edges", "soft commercial palette"],
        "negative_rules": ["large text", "photo", "mockup"],
        "commercial_goal": "cute wearable pattern",
        "difficulty": "low",
        "estimated_generation_cost": "low",
        "reuse_notes": "Reusable for seasonal intimate apparel motifs.",
        "trademark_safety_notes": "Generic hearts and bows only.",
        "provider_notes": "Manual upload only.",
    },
    "underwear/subtle_pride_motif": {
        "name": "Subtle Pride Motif",
        "design_family": "underwear_subtle_pride",
        "shop_fit": ["unitystitches"],
        "product_fit": ["womens_underwear", "panties", "thong"],
        "avoid_product_types": [],
        "niche_fit": ["LGBTQ+ pride", "trans pride"],
        "design_type": "subtle_motif_pattern",
        "art_style": "minimal vector pattern",
        "layout": "small scattered pride symbols",
        "palette": ["muted rainbow", "white", "pastel accents"],
        "typography": "none",
        "text_strategy": "no_text",
        "motifs": ["tiny hearts", "mini rainbows", "dots"],
        "pattern_strategy": "subtle scattered repeat",
        "layer_plan": ["transparent_canvas", "pattern", "motif", "final_composite"],
        "composition_rules": ["small scale", "balanced repeat"],
        "quality_rules": ["wearable", "not loud", "clean print"],
        "negative_rules": ["large text", "slogan", "photo"],
        "commercial_goal": "subtle pride wearable pattern",
        "difficulty": "low",
        "estimated_generation_cost": "low",
        "reuse_notes": "Useful for intimate apparel and accent products.",
        "trademark_safety_notes": "Generic pride motifs only.",
        "provider_notes": "Manual upload only.",
    },
    "underwear/seasonal_repeat_pattern": {
        "name": "Seasonal Repeat Pattern",
        "design_family": "underwear_seasonal",
        "shop_fit": ["unitystitches"],
        "product_fit": ["womens_underwear", "panties", "thong"],
        "avoid_product_types": [],
        "niche_fit": ["seasonal", "holiday pride"],
        "design_type": "seasonal_repeat_pattern",
        "art_style": "clean seasonal vector",
        "layout": "small seasonal motif repeat",
        "palette": ["seasonal palette", "white"],
        "typography": "none",
        "text_strategy": "no_text",
        "motifs": ["seasonal icons", "hearts", "sparkles"],
        "pattern_strategy": "small seamless-style repeat",
        "layer_plan": ["transparent_canvas", "pattern", "motif", "accent", "final_composite"],
        "composition_rules": ["balanced repeat", "safe margins"],
        "quality_rules": ["clear seasonal signal", "wearable scale"],
        "negative_rules": ["large text", "busy scene", "photo"],
        "commercial_goal": "seasonal intimate apparel pattern",
        "difficulty": "medium",
        "estimated_generation_cost": "low",
        "reuse_notes": "Swap seasonal motifs while preserving layout.",
        "trademark_safety_notes": "Avoid protected holiday characters.",
        "provider_notes": "Manual upload only.",
    },
}

_EXTRA_RECIPES = {
    "market_chaos/degen_badge": ("Market Chaos Degen Badge", "typography_badge", ["shirt", "hoodie", "mug", "sticker"], ["womens_underwear", "panties", "thong"]),
    "market_chaos/candlestick_chaos": ("Candlestick Chaos", "badge", ["shirt", "hoodie", "mug"], ["womens_underwear", "panties", "thong"]),
    "programmer/funny_bug": ("Funny Bug", "typography_badge", ["shirt", "hoodie", "mug", "sticker"], ["womens_underwear", "panties", "thong"]),
    "programmer/terminal_joke": ("Terminal Joke", "typography_badge", ["shirt", "hoodie", "mug"], ["womens_underwear", "panties", "thong"]),
    "teacher/apple_badge": ("Apple Badge", "badge", ["shirt", "hoodie", "mug", "tote", "sticker"], ["womens_underwear", "panties", "thong"]),
    "teacher/pencil_stack": ("Pencil Stack", "sticker", ["shirt", "hoodie", "mug", "tote", "sticker"], ["womens_underwear", "panties", "thong"]),
}

for recipe_id, (name, design_type, product_fit, avoid) in _EXTRA_RECIPES.items():
    DEFAULT_RECIPES[recipe_id] = {
        "name": name,
        "design_family": recipe_id.split("/")[0],
        "shop_fit": ["general"],
        "product_fit": product_fit,
        "avoid_product_types": avoid,
        "niche_fit": [recipe_id.split("/")[0].replace("_", " ")],
        "design_type": design_type,
        "art_style": "clean commercial vector",
        "layout": "centered motif or badge",
        "palette": ["high contrast", "white", "accent color"],
        "typography": "bold readable sans",
        "text_strategy": "large_readable_text" if "badge" in design_type or "joke" in name.lower() else "optional_short_text",
        "motifs": ["simple icon", "spark accents"],
        "pattern_strategy": "single focal artwork",
        "layer_plan": ["transparent_canvas", "base_shape", "motif", "typography", "accent", "final_composite"],
        "composition_rules": ["75% canvas coverage", "safe margins", "thumbnail readable"],
        "quality_rules": ["high contrast", "clean edges", "commercial clarity"],
        "negative_rules": ["person", "mockup", "photo", "watermark", "blurry text"],
        "commercial_goal": "clear niche gift design",
        "difficulty": "medium",
        "estimated_generation_cost": "low",
        "reuse_notes": "Reusable niche layout foundation.",
        "trademark_safety_notes": "Avoid protected names, logos, and characters.",
        "provider_notes": "Manual upload only.",
    }

DEFAULT_FOLDERS = [
    "pride",
    "underwear",
    "halloween",
    "teacher",
    "programmer",
    "mom_family",
    "thai_english",
    "market_chaos",
    "massage_therapist",
]


def _recipe_path(recipe_id: str, root: Path | None = None) -> Path:
    base = root or RECIPE_ROOT
    return base / f"{recipe_id}.yaml"


def _with_identity(recipe_id: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipe_id": recipe_id,
        "version": str(data.get("version") or "1.0"),
        **data,
    }


def initialize_recipe_library(root: Path | None = None) -> dict[str, Any]:
    base = root or RECIPE_ROOT
    created: list[str] = []
    for folder in DEFAULT_FOLDERS:
        (base / folder).mkdir(parents=True, exist_ok=True)
    for recipe_id, data in DEFAULT_RECIPES.items():
        path = _recipe_path(recipe_id, base)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(yaml.safe_dump(_with_identity(recipe_id, data), sort_keys=False), encoding="utf-8")
            created.append(recipe_id)
    return {"status": "ok", "root": str(base), "created": created, "folder_count": len(DEFAULT_FOLDERS)}


def list_recipes(root: Path | None = None) -> dict[str, Any]:
    base = root or RECIPE_ROOT
    initialize_recipe_library(base)
    recipes = []
    for path in sorted(base.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            data = {}
        recipe_id = str(data.get("recipe_id") or path.relative_to(base).with_suffix(""))
        recipes.append(_with_identity(recipe_id, data))
    return {"status": "ok", "root": str(base), "recipes": recipes, "recipe_count": len(recipes), "execution_enabled": False}


def get_recipe(recipe_id: str, root: Path | None = None) -> dict[str, Any]:
    normalized = recipe_id.strip().removesuffix(".yaml")
    path = _recipe_path(normalized, root)
    if not path.exists():
        initialize_recipe_library(root)
    if not path.exists():
        raise KeyError(f"Unknown recipe: {recipe_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {"status": "ok", "recipe": _with_identity(normalized, data), "execution_enabled": False}


def recipes_by_product(product_type: str, root: Path | None = None) -> dict[str, Any]:
    product = product_type.strip().lower()
    recipes = [
        recipe for recipe in list_recipes(root)["recipes"]
        if product in [str(item).lower() for item in recipe.get("product_fit", [])]
        and product not in [str(item).lower() for item in recipe.get("avoid_product_types", [])]
    ]
    return {"status": "ok", "product_type": product_type, "recipes": recipes, "recipe_count": len(recipes), "execution_enabled": False}
