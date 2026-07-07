from __future__ import annotations

from typing import Any

from creative_intelligence.config import DEFAULT_TREND_SEEDS
from creative_intelligence.services.keyword_service import extract_keywords


def analyze_trends(query: str = "", *, limit: int = 10) -> list[dict[str, Any]]:
    base_terms = extract_keywords(query, limit=6) if query else []
    seeds = base_terms or DEFAULT_TREND_SEEDS
    trends: list[dict[str, Any]] = []
    for index, seed in enumerate(seeds[:limit], start=1):
        score = round(max(0.25, 1.0 - ((index - 1) * 0.07)), 2)
        trends.append(
            {
                "term": seed,
                "score": score,
                "source": "local_seed" if not query else "query_analysis",
                "notes": "Local deterministic trend candidate; connect live feeds later if desired.",
            }
        )
    return trends


def trend_keywords(query: str = "") -> list[str]:
    return [trend["term"] for trend in analyze_trends(query)]

