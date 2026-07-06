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
    snippets: list[str] = []
    for term in terms:
        t = term.lower()
        start_idx = 0
        while True:
            idx = low.find(t, start_idx)
            if idx < 0:
                break
            start = max(0, idx - context)
            end = min(len(text), idx + len(term) + context)
            snippet = text[start:end].strip().replace("\n", " ")
            snippets.append(snippet)
            start_idx = idx + len(t)
    if snippets:
        # join multiple matched snippets with ellipses
        return " ... ".join(dict.fromkeys(snippets))
    # fallback: return the first 240 chars
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
        full_query = " ".join(terms).strip()

        # prefer certain vault areas
        preferred = {"Memory", "People", "Brain"}
        if any(p.lower() in str(path).lower() for p in preferred):
            score += 10

        # penalize generic report/status files by filename hints
        generic_hints = ["automatic context", "ai inbox cleanup", "import report", "status", "report"]
        if any(h in path.name.lower() for h in generic_hints):
            score -= 20

        # boost if title/path contains important terms
        boosts = [t.lower() for t in ["malcolm", "paving", "88858", "kevin", "sfm2", "sbx"]]
        if any(b in path.name.lower() or b in str(path).lower() for b in boosts):
            score += 30

        # full query exact match
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

        snippet = _snippet_for_text(txt, terms, context=240)
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


def _extract_key_facts_from_text(text: str, terms: list[str], max_facts: int = 5) -> list[str]:
    """Heuristic extraction of key facts: return up to `max_facts` lines containing terms or short sentences with entities."""
    facts: list[str] = []
    lines = [l.strip() for l in re.split(r"[\n\r]+", text) if l.strip()]
    for line in lines:
        low = line.lower()
        if any(t.lower() in low for t in terms):
            # truncate long lines
            s = line
            if len(s) > 240:
                s = s[:240].rstrip() + "..."
            facts.append(s)
        if len(facts) >= max_facts:
            break
    # fallback: take first sentences
    if not facts:
        sentences = re.split(r"(?<=[.!?])\s+", text)
        for s in sentences:
            if s.strip():
                facts.append(s.strip()[:240])
            if len(facts) >= max_facts:
                break
    return facts


def memory_answer_context(query: str, limit: int = 8) -> dict[str, Any]:
    """Return structured context useful for building prompts: top sources, snippets, and key facts."""
    res = search_unified(query, limit=limit)
    terms = expand_terms(query)
    out: list[dict[str, Any]] = []
    for item in res.get("results", [])[:limit]:
        entry = {
            "title": item.get("title"),
            "source_type": item.get("source_type"),
            "path": item.get("path"),
            "snippet": item.get("snippet"),
            "score": item.get("score"),
            "key_facts": [],
        }
        # attempt to read and extract richer facts when file exists
        p = item.get("path") or ""
        try:
            if p and Path(p).exists():
                txt = Path(p).read_text(encoding="utf-8")
                entry["snippet"] = _snippet_for_text(txt, terms, context=300)
                entry["key_facts"] = _extract_key_facts_from_text(txt, terms)
        except Exception:
            pass
        out.append(entry)
    return {"status": "ok", "query": query, "sources": out, "count": len(out)}


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
