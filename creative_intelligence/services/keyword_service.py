from __future__ import annotations

import re
from collections import Counter


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def extract_keywords(text: str, *, limit: int = 12) -> list[str]:
    words = [
        word.lower()
        for word in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", text or "")
        if word.lower() not in STOPWORDS
    ]
    counts = Counter(words)
    return [word for word, _count in counts.most_common(limit)]


def keyword_variants(seed: str) -> list[str]:
    keywords = extract_keywords(seed, limit=8)
    if not keywords:
        return []
    phrases = list(dict.fromkeys(keywords + [seed.strip().lower()]))
    return [phrase for phrase in phrases if phrase]

