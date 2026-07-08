from __future__ import annotations

from typing import Any


UNDERWEAR_TYPES = {"womens_underwear", "panties", "panty", "thong", "thongs"}
TEXT_HEAVY = {"large_readable_text", "typography_heavy", "headline_text"}
NO_TEXT = {"no_text", "minimal_hidden_text", "optional_short_text"}


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def score_variation(variation: dict[str, Any]) -> dict[str, Any]:
    recipe = variation.get("design_recipe") or {}
    product_type = str(variation.get("product_type") or "").lower()
    text_strategy = str(recipe.get("text_strategy") or "").lower()
    design_type = str(recipe.get("design_type") or "").lower()
    pattern_strategy = str(recipe.get("pattern_strategy") or "").lower()
    negative_rules = " ".join(str(item).lower() for item in recipe.get("negative_rules", []))
    quality_rules = " ".join(str(item).lower() for item in recipe.get("quality_rules", []))
    blocking: list[str] = []

    resolution_score = 85
    transparency_score = 90
    safe_margin_score = 90 if any("margin" in str(item).lower() for item in recipe.get("composition_rules", [])) else 78
    composition_score = 92 if any(token in pattern_strategy or token in design_type for token in ["pattern", "badge", "sticker", "motif"]) else 82
    contrast_score = 90 if "contrast" in quality_rules else 82
    recipe_adherence_score = 92
    trademark_safety_score = 92 if recipe.get("trademark_safety_notes") else 82
    commercial_style_score = 90 if recipe.get("commercial_goal") else 80

    if product_type in UNDERWEAR_TYPES:
        if text_strategy in NO_TEXT:
            typography_score = 92
        elif text_strategy in TEXT_HEAVY:
            typography_score = 45
            blocking.append("Large typography is a poor fit for underwear.")
        else:
            typography_score = 78
        if "pattern" in pattern_strategy or "motif" in design_type or "pattern" in design_type:
            product_fit_score = 94
        else:
            product_fit_score = 65
            blocking.append("Underwear needs pattern/motif/seamless-style design.")
        if text_strategy in TEXT_HEAVY:
            product_fit_score = min(product_fit_score, 58)
    else:
        if text_strategy in TEXT_HEAVY or "typography" in design_type:
            typography_score = 90
        elif text_strategy in NO_TEXT:
            typography_score = 78
        else:
            typography_score = 84
        product_fit_score = 90 if product_type in [str(item).lower() for item in recipe.get("product_fit", [])] else 72

    if product_type in [str(item).lower() for item in recipe.get("avoid_product_types", [])]:
        product_fit_score = min(product_fit_score, 35)
        blocking.append(f"Recipe avoids product type: {product_type}.")
    if "large text" in negative_rules and product_type in UNDERWEAR_TYPES:
        recipe_adherence_score += 3

    sales_signal = {}
    try:
        from creative_intelligence.services.etsy_sales_intelligence_service import sales_signal_for_candidate

        sales_signal = sales_signal_for_candidate(variation)
    except Exception:
        sales_signal = {"boost": 0.0, "matched_rows": 0, "matched_fields": []}

    sales_boost = int(round(float(sales_signal.get("boost") or 0.0) * 100))
    if sales_boost:
        commercial_style_score = _clamp(commercial_style_score + min(8, sales_boost))
        recipe_adherence_score = _clamp(recipe_adherence_score + min(5, sales_boost // 2))
        product_fit_score = _clamp(product_fit_score + min(4, sales_boost // 3))

    categories = {
        "resolution_score": resolution_score,
        "transparency_score": transparency_score,
        "safe_margin_score": safe_margin_score,
        "composition_score": composition_score,
        "contrast_score": contrast_score,
        "typography_score": typography_score,
        "product_fit_score": product_fit_score,
        "commercial_style_score": commercial_style_score,
        "recipe_adherence_score": _clamp(recipe_adherence_score),
        "trademark_safety_score": trademark_safety_score,
    }
    score = round(sum(categories.values()) / len(categories))
    notes = []
    if product_type in UNDERWEAR_TYPES:
        notes.append("Underwear scoring favors pattern, motif, color, and repeat-friendly artwork over typography.")
    if score < 90:
        notes.append("Needs manual review before Printify-ready status.")
    return {
        **categories,
        "print_readiness_score": score,
        "thumbnail_score": _clamp(round((composition_score + contrast_score + typography_score) / 3)),
        "manual_review_notes": notes,
        "blocking_issues": blocking,
        "recommended_next_steps": ["Generate local image after approval", "Review print scale and background"] if score >= 90 else ["Refine recipe/product fit", "Regenerate stronger variation"],
        "etsy_sales_signal": sales_signal,
        "execution_enabled": False,
    }


def score_variations(variations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{**variation, "score": score_variation(variation)} for variation in variations]
