from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services.design_dna import design_dna_from_recipe
from jamesos.services.recipe_library import get_recipe


DESIGN_PLAN_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "DesignPlans"
UNDERWEAR_TYPES = {"womens_underwear", "panties", "panty", "thong", "thongs"}
TYPOGRAPHY_PRODUCTS = {"t_shirt", "shirt", "tee", "hoodie", "sweatshirt", "tote", "tote_bag", "mug", "sticker", "stickers"}

SAFETY = {
    "calls_printify": False,
    "calls_inkedjoy": False,
    "calls_etsy": False,
    "uploads": False,
    "publishes": False,
    "orders": False,
    "sends": False,
    "provider_writes_enabled": False,
    "external_execution_enabled": False,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _id(prefix: str = "plan") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _folder_for_id(plan_id: str, root: Path | None = None) -> Path:
    base = root or DESIGN_PLAN_ROOT
    parts = plan_id.split("_")
    day = parts[1][:8] if len(parts) > 1 else ""
    folder_date = f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 and day.isdigit() else date.today().isoformat()
    return base / folder_date


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _product_key(product_type: str) -> str:
    return product_type.lower().replace(" ", "_").replace("-", "_")


def _dominant_shape(recipe: dict[str, Any], niche: str, product_type: str) -> str:
    motifs = [str(item) for item in recipe.get("motifs", []) if str(item).strip()]
    if motifs:
        return motifs[0]
    if _product_key(product_type) in UNDERWEAR_TYPES:
        for token in ["heart", "bow", "star", "ribbon"]:
            if token in niche.lower():
                return f"{token}s"
        return "hearts"
    return "badge"


def design_plan_from_recipe(
    recipe: dict[str, Any],
    design_dna: dict[str, Any] | None = None,
    *,
    brand_id: str,
    product_type: str,
    niche: str,
    quality_target: int = 90,
) -> dict[str, Any]:
    product_key = _product_key(product_type)
    dna = design_dna or design_dna_from_recipe(recipe, brand_id=brand_id, product_type=product_type, niche=niche)
    text_strategy = str(recipe.get("text_strategy") or "").lower()
    recipe_supports_typography = text_strategy in {"large_readable_text", "typography_heavy", "headline_text"}

    if product_key in UNDERWEAR_TYPES:
        typography_strategy = "minimal_hidden_text" if text_strategy == "minimal_hidden_text" else "no_text"
        pattern_strategy = recipe.get("pattern_strategy") or "repeating motif / seamless-style repeat"
        coverage_percent = 55
        negative_space_percent = 35
        commercial_goal = recipe.get("commercial_goal") or "wearable pattern, not slogan"
        visual_weight = "medium-light repeat"
    else:
        typography_strategy = "readable_typography" if recipe_supports_typography or product_key in TYPOGRAPHY_PRODUCTS else "optional_short_text"
        pattern_strategy = recipe.get("pattern_strategy") or recipe.get("layout") or "centered print composition"
        coverage_percent = 72 if product_key in TYPOGRAPHY_PRODUCTS else 65
        negative_space_percent = 22
        commercial_goal = recipe.get("commercial_goal") or "clear giftable print design"
        visual_weight = "medium-bold focal"

    palette = list(recipe.get("palette") or dna.get("palette_system") or [])
    accent_shapes = [str(item) for item in recipe.get("motifs", [])[1:4]]
    if not accent_shapes and product_key in UNDERWEAR_TYPES:
        accent_shapes = ["bows", "stars", "ribbons"]

    plan = {
        "status": "ok",
        "plan_id": _id(),
        "created_at": _now(),
        "brand_id": brand_id,
        "product_type": product_type,
        "niche": niche,
        "recipe_id": recipe.get("recipe_id", ""),
        "design_family": recipe.get("design_family") or dna.get("design_family", ""),
        "target_buyer": recipe.get("target_buyer", ""),
        "occasion": recipe.get("occasion", ""),
        "mood": list(recipe.get("mood") or recipe.get("niche_fit") or []),
        "visual_weight": visual_weight,
        "coverage_percent": coverage_percent,
        "pattern_strategy": pattern_strategy,
        "typography_strategy": typography_strategy,
        "dominant_shape": _dominant_shape(recipe, niche, product_type),
        "accent_shapes": accent_shapes,
        "palette": palette,
        "contrast_goal": "high readable contrast" if "contrast" in " ".join(str(item).lower() for item in recipe.get("quality_rules", [])) else "clear commercial contrast",
        "complexity": recipe.get("difficulty", "medium"),
        "negative_space_percent": negative_space_percent,
        "safe_margin_percent": 8 if product_key in UNDERWEAR_TYPES else 10,
        "commercial_goal": commercial_goal,
        "layer_plan": list(recipe.get("layer_plan") or ["transparent_canvas", "motif", "final_composite"]),
        "composition_rules": list(recipe.get("composition_rules") or []),
        "prompt_intent": {
            "art_style": recipe.get("art_style") or dna.get("art_style", ""),
            "layout": recipe.get("layout") or dna.get("layout_system", ""),
            "motifs": list(recipe.get("motifs") or dna.get("motif_system") or []),
            "negative_rules": list(recipe.get("negative_rules") or []),
            "transparent_background_requested": True,
            "avoid_mockup_person_photo": True,
        },
        "reuse_strategy": recipe.get("reuse_strategy") or dna.get("reuse_strategy", ""),
        "quality_target": quality_target,
        "safety": SAFETY,
        "external_execution_enabled": False,
    }
    return plan


def create_design_plan(
    *,
    brand_id: str,
    product_type: str,
    niche: str,
    recipe_id: str,
    quality_target: int = 90,
    root: Path | None = None,
) -> dict[str, Any]:
    recipe = get_recipe(recipe_id)["recipe"]
    dna = design_dna_from_recipe(recipe, brand_id=brand_id, product_type=product_type, niche=niche, quality="premium")
    plan = design_plan_from_recipe(
        recipe,
        dna,
        brand_id=brand_id,
        product_type=product_type,
        niche=niche,
        quality_target=quality_target,
    )
    save_design_plan(plan, root=root)
    return plan


def save_design_plan(plan: dict[str, Any], *, root: Path | None = None, path: Path | None = None) -> dict[str, Any]:
    plan_id = str(plan.get("plan_id") or _id())
    plan["plan_id"] = plan_id
    out = path or (_folder_for_id(plan_id, root) / f"{plan_id}.json")
    _write_json(out, plan)
    return {"status": "ok", "plan": plan, "path": str(out), "external_execution_enabled": False}


def load_design_plan(plan_id_or_path: str, *, root: Path | None = None) -> dict[str, Any]:
    candidate = Path(plan_id_or_path).expanduser()
    if candidate.exists():
        return {"status": "ok", "plan": json.loads(candidate.read_text(encoding="utf-8")), "path": str(candidate), "external_execution_enabled": False}
    base = root or DESIGN_PLAN_ROOT
    for path in sorted(base.glob(f"*/*{plan_id_or_path}*.json")):
        return {"status": "ok", "plan": json.loads(path.read_text(encoding="utf-8")), "path": str(path), "external_execution_enabled": False}
    raise KeyError(f"Unknown design plan: {plan_id_or_path}")


def design_plan_health() -> dict[str, Any]:
    DESIGN_PLAN_ROOT.mkdir(parents=True, exist_ok=True)
    return {
        "status": "ok",
        "service": "design_planner",
        "storage_root": str(DESIGN_PLAN_ROOT),
        "safety": SAFETY,
        "external_execution_enabled": False,
    }
