from __future__ import annotations

from typing import Any

from creative_intelligence.config import DEFAULT_AUDIENCES
from creative_intelligence.services.compatibility_service import annotate_candidate
from creative_intelligence.services.keyword_service import extract_keywords
from creative_intelligence.services.trend_service import trend_keywords


def suggest_niches(query: str = "", *, limit: int = 8) -> list[dict[str, Any]]:
    terms = trend_keywords(query)[:limit]
    query_keywords = extract_keywords(query, limit=4)
    niches: list[dict[str, Any]] = []
    for idx, term in enumerate(terms):
        audience = DEFAULT_AUDIENCES[idx % len(DEFAULT_AUDIENCES)]
        niche = " ".join(dict.fromkeys([*query_keywords[:2], term])).strip()
        niches.append(
            {
                "name": niche or term,
                "audience": audience,
                "angle": f"{term.title()} products for {audience}",
                "keywords": list(dict.fromkeys([term, *query_keywords])),
            }
        )
    return niches


def suggest_compatible_niches(query: str = "", *, product_type: str = "", limit: int = 8) -> list[dict[str, Any]]:
    candidates = []
    for niche in suggest_niches(query, limit=limit):
        candidate = dict(niche)
        if product_type:
            candidate["product_type"] = product_type
        annotated = annotate_candidate(candidate)
        if annotated["compatible"]:
            candidates.append(annotated)
    return candidates
