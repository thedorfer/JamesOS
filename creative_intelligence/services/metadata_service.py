from __future__ import annotations

from creative_intelligence.services.keyword_service import extract_keywords


def product_metadata(title: str, description_seed: str = "") -> dict[str, object]:
    text = " ".join([title, description_seed]).strip()
    keywords = extract_keywords(text, limit=13)
    tags = keywords[:13]
    return {
        "title": title.strip().title(),
        "description": description_seed.strip()
        or f"A clean, giftable design inspired by {title.strip() or 'a focused niche'}.",
        "tags": tags,
        "keywords": keywords,
    }

