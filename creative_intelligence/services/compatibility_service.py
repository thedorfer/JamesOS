from __future__ import annotations

import re
from typing import Any


INTIMATE_PRODUCT_TERMS = {
    "womens_underwear",
    "women's underwear",
    "underwear",
    "panties",
    "panty",
    "thong",
    "thongs",
    "lingerie",
    "intimate apparel",
    "intimates",
}

SCHOOL_NICHE_TERMS = {
    "teacher",
    "school",
    "school staff",
    "classroom",
    "education",
    "educator",
    "gcu",
    "kids",
    "kid",
    "child",
    "children",
    "student",
    "students",
    "back-to-school",
    "back to school",
    "special education",
    "speech therapy",
    "occupational therapy",
}

UNDERWEAR_SAFE_NICHE_TERMS = {
    "lgbtq",
    "lgbtq+ pride",
    "pride",
    "trans pride",
    "trans",
    "nonbinary pride",
    "nonbinary",
    "ally",
    "supporter",
    "self-love",
    "self love",
    "confidence",
    "body positivity",
    "mental health positivity",
    "mental health",
    "be yourself",
    "affirmation",
    "mom pride",
    "family pride",
    "thai/english",
    "thai english",
    "thai",
    "custom pronoun",
    "pronoun",
    "custom name",
    "holiday pride",
    "seasonal inclusive",
    "valentines love-is-love",
    "valentine",
    "love-is-love",
    "love is love",
    "pride month",
    "spouse",
    "partner",
}

SCHOOL_SAFE_PRODUCT_TERMS = {
    "shirt",
    "t-shirt",
    "tee",
    "sweatshirt",
    "hoodie",
    "hoodies",
    "tote",
    "tote bag",
    "mug",
    "sticker",
    "stickers",
    "classroom accessory",
    "classroom accessories",
    "seasonal gift",
    "seasonal gifts",
    "seasonal_accessory",
}


def _normalize(value: str) -> str:
    text = value.replace("_", " ").lower()
    text = re.sub(r"[^a-z0-9+/' -]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _matched_terms(text: str, terms: set[str]) -> list[str]:
    normalized = _normalize(text)
    matches: list[str] = []
    for term in sorted(terms, key=len, reverse=True):
        normalized_term = _normalize(term)
        if not normalized_term:
            continue
        if " " in normalized_term or "-" in normalized_term or "/" in normalized_term or "+" in normalized_term:
            if normalized_term in normalized:
                matches.append(term)
        elif re.search(rf"\b{re.escape(normalized_term)}\b", normalized):
            matches.append(term)
    return matches


def is_intimate_product(product_type: str) -> bool:
    return bool(_matched_terms(product_type, INTIMATE_PRODUCT_TERMS))


def is_school_or_child_niche(niche: str) -> bool:
    return bool(_matched_terms(niche, SCHOOL_NICHE_TERMS))


def is_underwear_safe_niche(niche: str) -> bool:
    return bool(_matched_terms(niche, UNDERWEAR_SAFE_NICHE_TERMS)) and not is_school_or_child_niche(niche)


def is_school_safe_product(product_type: str) -> bool:
    return bool(_matched_terms(product_type, SCHOOL_SAFE_PRODUCT_TERMS)) and not is_intimate_product(product_type)


def assess_compatibility(product_type: str, niche: str) -> dict[str, Any]:
    product_matches = _matched_terms(product_type, INTIMATE_PRODUCT_TERMS)
    school_matches = _matched_terms(niche, SCHOOL_NICHE_TERMS)
    underwear_safe_matches = _matched_terms(niche, UNDERWEAR_SAFE_NICHE_TERMS)

    if product_matches and school_matches:
        return {
            "compatible": False,
            "compatibility_status": "blocked",
            "compatibility_reason": "School, teacher, education, child, therapy, or student niches must never be paired with underwear, lingerie, thongs, panties, or intimate apparel.",
            "blocked_terms": sorted(set(product_matches + school_matches)),
        }

    if product_matches and not underwear_safe_matches:
        return {
            "compatible": False,
            "compatibility_status": "blocked",
            "compatibility_reason": "Women's underwear requires an underwear-safe niche such as pride, self-love, body positivity, pronouns, Thai/English identity, or clean adult partner humor.",
            "blocked_terms": sorted(set(product_matches)),
        }

    if school_matches and not is_school_safe_product(product_type):
        return {
            "compatible": False,
            "compatibility_status": "blocked",
            "compatibility_reason": "Teacher, school, education, and child-related niches may only use non-intimate products such as shirts, hoodies, totes, mugs, stickers, classroom accessories, or seasonal gifts.",
            "blocked_terms": sorted(set(school_matches)),
        }

    return {
        "compatible": True,
        "compatibility_status": "allowed",
        "compatibility_reason": "Product type and niche are compatible under Creative Intelligence shop rules.",
        "blocked_terms": [],
    }


def annotate_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    product_type = str(candidate.get("product_type") or candidate.get("type") or "")
    niche = str(candidate.get("niche") or candidate.get("name") or candidate.get("title") or "")
    result = assess_compatibility(product_type, niche) if product_type and niche else {
        "compatible": True,
        "compatibility_status": "unknown",
        "compatibility_reason": "No complete product/niche pair was provided.",
        "blocked_terms": [],
    }
    return {**candidate, **result}


def filter_compatible(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [annotated for candidate in candidates if (annotated := annotate_candidate(candidate))["compatible"]]


def compatible_niches_for_product(product_type: str, niches: list[str]) -> list[str]:
    return [niche for niche in niches if assess_compatibility(product_type, niche)["compatible"]]


def compatible_products_for_niche(niche: str, product_types: list[str]) -> list[str]:
    return [product_type for product_type in product_types if assess_compatibility(product_type, niche)["compatible"]]


def select_compatible_package(
    product_type: str,
    niches: list[str],
    *,
    start_index: int = 0,
) -> dict[str, Any]:
    if not niches:
        raise ValueError("At least one niche is required")
    total = len(niches)
    for offset in range(total):
        niche = niches[(start_index + offset) % total]
        compatibility = assess_compatibility(product_type, niche)
        if compatibility["compatible"]:
            return {"product_type": product_type, "niche": niche, **compatibility}
    raise ValueError(f"No compatible niche found for product type: {product_type}")
