from __future__ import annotations

from typing import Any


def _etsy_adjustment(candidate: dict[str, Any]) -> float:
    try:
        from creative_intelligence.storage.sqlite import list_performance_history, performance_history_exists

        if not performance_history_exists():
            return 0.0

        name = str(candidate.get("name") or candidate.get("title") or "").lower()
        product_type = str(candidate.get("product_type") or "").lower()
        keywords = " ".join(str(item).lower() for item in candidate.get("keywords") or [])
        haystack = " ".join([name, product_type, keywords])
        rows = list_performance_history(limit=500)
    except Exception:
        return 0.0

    adjustment = 0.0
    low_conversion_matches = 0
    for row in rows:
        row_terms = " ".join(
            [
                str(row.get("title") or ""),
                str(row.get("product_type") or ""),
                str(row.get("niche") or ""),
            ]
        ).lower()
        if not any(term and term in haystack for term in row_terms.split()):
            continue

        orders = int(row.get("orders") or 0)
        conversion_rate = float(row.get("conversion_rate") or 0)
        views = int(row.get("views") or 0)
        if orders > 0:
            adjustment += min(0.20, orders * 0.02)
        if conversion_rate >= 0.02:
            adjustment += 0.08
        if views >= 100 and conversion_rate < 0.005:
            low_conversion_matches += 1

    if low_conversion_matches >= 3:
        adjustment -= 0.15
    elif low_conversion_matches:
        adjustment -= 0.05
    return adjustment


def score_candidate(candidate: dict[str, Any]) -> float:
    keywords = candidate.get("keywords") or []
    name = str(candidate.get("name") or candidate.get("title") or "")
    audience = str(candidate.get("audience") or "")
    score = 0.35
    score += min(len(keywords), 8) * 0.05
    score += 0.15 if len(name) >= 8 else 0.0
    score += 0.15 if audience else 0.0
    score += 0.10 if any(word in name.lower() for word in ["gift", "custom", "personal", "local"]) else 0.0
    score += _etsy_adjustment(candidate)
    return round(max(0.0, min(score, 1.0)), 2)


def rank_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = []
    for candidate in candidates:
        enriched = dict(candidate)
        enriched["score"] = score_candidate(enriched)
        ranked.append(enriched)
    return sorted(ranked, key=lambda item: item["score"], reverse=True)
