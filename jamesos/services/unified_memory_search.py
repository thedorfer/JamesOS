from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from .chatgpt_search_v2 import search_messages, DB_PATH, connect


# Memory source roots inside the JAMESOS_DATA vault
MEMORY_SOURCES = {
    "notes": VAULT / "JamesOS" / "Memory" / "Notes",
    "reports": VAULT / "JamesOS" / "Reports",
    "timeline": VAULT / "JamesOS" / "Timeline",
    "brain": VAULT / "JamesOS" / "Brain",
    "people": VAULT / "JamesOS" / "People",
}


def _tokenize(query: str) -> list[str]:
    return [t for t in re.findall(r"[A-Za-z0-9_#.-]{2,}", query)]


_EXPANSION_MAP = {
    "paving": ["WGL", "CGI", "WR Type", "Kevin", "SFM2", "SBX"],
}


def expand_terms(query: str) -> list[str]:
    tokens = _tokenize(query)
    expansions = []
    for t in tokens:
        low = t.lower()
        if low in _EXPANSION_MAP:
            expansions.extend(_EXPANSION_MAP[low])
    # include tokens, unique, preserve case for proper nouns
    return list(dict.fromkeys(tokens + expansions))


def _score_from_bm25(rank: Any) -> int:
    try:
        r = float(rank)
    except Exception:
        r = 1.0
    # lower bm25 is better — convert to 1-100 score
    score = max(1, min(100, int(100 - (r * 10))))
    return score


def _snippet_for_text(text: str, terms: list[str], context=120) -> str:
    low = text.lower()
    for term in terms:
        idx = low.find(term.lower())
        if idx >= 0:
            start = max(0, idx - context)
            end = min(len(text), idx + len(term) + context)
            return text[start:end].strip().replace("\n", " ")
    # fallback: start of text
    return text.strip().replace("\n", " ")[: context * 2]


def _search_files_for_terms(root: Path, terms: list[str], limit: int = 10) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if not root.exists():
        return results
    for path in sorted(root.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix.lower() not in {".md", ".txt", ".json", ".html"}:
            # still allow other text files, try reading but skip binaries
            pass
        try:
            txt = path.read_text(encoding="utf-8")
        except Exception:
            continue
        low = txt.lower()
        score = 0
        full_query = " ".join(terms)
        if full_query and full_query.lower() in low:
            score += 60
        # count matched unique terms
        matched = 0
        for t in terms:
            if t.lower() in low:
                matched += 1
                score += 10
        if matched == 0:
            continue
        snippet = _snippet_for_text(txt, terms)
        title = path.stem
        results.append({
            "source": "file",
            "source_type": root.name,
            "title": title,
            "path": str(path),
            "snippet": snippet,
            "score": score,
        })
        if len(results) >= limit:
            break
    return results


def search_unified(query: str, limit: int = 10) -> dict[str, Any]:
    """Search across ChatGPT index and vault memory sources.

    Returns: {status, query, results:list, count}
    Each result: {source, source_type, title, path, snippet, score}
    """
    terms = expand_terms(query)
    results: list[dict[str, Any]] = []

    # 1) ChatGPT index (if present)
    try:
        chat = search_messages(query, limit=limit)
        if chat.get("status") == "ok":
            for row in chat.get("results", [])[:limit]:
                score = _score_from_bm25(row.get("rank") if row.get("rank") is not None else 1)
                snippet = _snippet_for_text(str(row.get("text", "")), terms)
                results.append({
                    "source": "chatgpt",
                    "source_type": "chatgpt_index",
                    "title": row.get("title") or "ChatGPT",
                    "path": row.get("path") or "",
                    "snippet": snippet,
                    "score": score,
                })
    except Exception:
        # fail gracefully
        pass

    # 2) Files under configured memory sources
    for key, root in MEMORY_SOURCES.items():
        hits = _search_files_for_terms(root, terms, limit=limit)
        for h in hits:
            # demote file scores slightly relative to chatgpt
            h["score"] = min(100, h["score"] + 5)
            h["source"] = "file"
            h["source_type"] = key
            results.append(h)

    # Rank exact matches highest by boosting when full query appears
    full_q = query.strip().lower()
    for r in results:
        if full_q and full_q in (r.get("snippet", "").lower() or ""):
            r["score"] = min(100, r.get("score", 0) + 30)

    # sort by score descending
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return {"status": "ok", "query": query, "results": results[:limit], "count": len(results)}


def history_context(query: str, limit: int = 6) -> str:
    res = search_unified(query, limit=limit)
    rows = res.get("results") or []
    if not rows:
        return "No matching memory found."
    lines = ["# Unified Memory Matches", ""]
    for item in rows:
        lines.extend([
            f"## {item.get('title', '')} ({item.get('source')})",
            f"- Source: {item.get('source_type', '')}",
            f"- Path: {item.get('path', '')}",
            "",
            str(item.get('snippet', ''))[:1200],
            "",
        ])
    return "\n".join(lines)


def memory_health() -> dict[str, Any]:
    counts: dict[str, int] = {}
    # chatgpt count
    try:
        if DB_PATH.exists():
            with connect() as conn:
                row = conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()
                counts["chatgpt_messages"] = int(row["c"])
        else:
            counts["chatgpt_messages"] = 0
    except Exception:
        counts["chatgpt_messages"] = -1

    for key, root in MEMORY_SOURCES.items():
        try:
            if root.exists():
                counts[key] = sum(1 for _ in root.rglob("*"))
            else:
                counts[key] = 0
        except Exception:
            counts[key] = -1

    return {"status": "ok", "counts": counts}
