from __future__ import annotations

from typing import Any


def design_dna_from_recipe(
    recipe: dict[str, Any],
    *,
    brand_id: str,
    product_type: str,
    niche: str,
    quality: str = "premium",
) -> dict[str, Any]:
    return {
        "design_family": recipe.get("design_family", ""),
        "art_style": recipe.get("art_style", ""),
        "layout_system": recipe.get("layout", ""),
        "palette_system": recipe.get("palette", []),
        "typography_system": recipe.get("typography", ""),
        "motif_system": recipe.get("motifs", []),
        "pattern_system": recipe.get("pattern_strategy", ""),
        "brand_voice": "warm, inclusive, practical, giftable" if brand_id == "commerce_shop" else "brand-safe commercial",
        "commercial_goal": recipe.get("commercial_goal", ""),
        "target_products": recipe.get("product_fit", []),
        "blocked_products": recipe.get("avoid_product_types", []),
        "reuse_strategy": recipe.get("reuse_notes", ""),
        "variation_strategy": "vary palette emphasis, motif scale, layout rhythm, and accent density while preserving recipe DNA",
        "quality_target": quality,
        "print_constraints": {
            "transparent_background_requested": True,
            "safe_margins": True,
            "thumbnail_readable": True,
            "provider_writes_enabled": False,
        },
        "brand_id": brand_id,
        "product_type": product_type,
        "niche": niche,
    }
