from __future__ import annotations

import json
import re
from typing import Any

from jamesos.config import VAULT
from jamesos.services.chatgpt_message_index import search_messages, stats as message_index_stats

INDEX_PATH = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Index" / "conversations_index.jsonl"
CONVERSATIONS_ROOT = VAULT / "JamesOS" / "Brain" / "Conversations" / "ChatGPT"


def terms(query: str) -> list[str]:
    stop = {"what", "know", "about", "from", "your", "chatgpt", "history", "the", "and", "for", "with", "that", "this"}
    return [t.lower() for t in re.findall(r"[A-Za-z0-9_#.-]{2,}", query) if t.lower() not in stop][:12]


def around(text: str, words: list[str], size: int = 1000) -> str:
    low = text.lower()
    hits = [low.find(w) for w in words if low.find(w) >= 0]
    if not hits:
        return text[:size]
    start = max(min(hits) - 260, 0)
    end = min(start + size, len(text))
    return ("..." if start else "") + text[start:end].strip() + ("..." if end < len(text) else "")


def markdown_search(query: str, limit: int) -> list[dict[str, Any]]:
    if not CONVERSATIONS_ROOT.exists():
        return []
    words = terms(query)
    results = []
    for path in CONVERSATIONS_ROOT.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        low = text.lower()
        if not any(w in low for w in words):
            continue
        first = text.splitlines()[0] if text.splitlines() else path.stem
        title = first.lstrip("# ").strip() or path.stem
        title_low = title.lower()
        score = 0
        for w in words:
            if w in title_low:
                score += 8
            score += min(low.count(w), 12)
        results.append({
            "id": path.stem,
            "title": title,
            "created_at": "",
            "projects": [],
            "message_count": 0,
            "path": str(path),
            "score": score,
            "snippet": around(text, words),
            "source": "markdown_full_text",
        })
    results.sort(key=lambda x: x.get("score", 0), reverse=True)
    return results[:limit]


def summary_search(query: str, limit: int) -> list[dict[str, Any]]:
    if not INDEX_PATH.exists():
        return []
    words = terms(query)
    results = []
    with INDEX_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            title = str(item.get("title", ""))
            hay = f"{title} {item.get('snippet','')} {' '.join(item.get('projects') or [])}".lower()
            score = 0
            for w in words:
                if w in title.lower():
                    score += 4
                if w in hay:
                    score += 1
            if score:
                item["score"] = score
                item["source"] = "summary_index"
                results.append(item)
    results.sort(key=lambda x: (x.get("score", 0), x.get("created_at", "")), reverse=True)
    return results[:limit]


def search_history(query: str, limit: int = 8) -> dict[str, Any]:
    first = search_messages(query, limit=limit)
    if first.get("results"):
        return first
    second = markdown_search(query, limit)
    if second:
        return {"status": "ok", "query": query, "results": second, "count": len(second), "source": "markdown_full_text"}
    third = summary_search(query, limit)
    if third:
        return {"status": "ok", "query": query, "results": third, "count": len(third), "source": "summary_index"}
    return {"status": "ok", "query": query, "results": [], "count": 0, "source": message_index_stats().get("status", "none")}


def history_context(query: str, limit: int = 6) -> str:
    result = search_history(query, limit=limit)
    rows = result.get("results") or []
    if not rows:
        return "No imported history matched the question."
    lines = ["# Imported History Matches", "", "This is the user's own imported ChatGPT history. Use it as personal context.", ""]
    for item in rows:
        projects = item.get("projects") or ["Unclassified"]
        lines.extend([
            f"## {item.get('title', 'Untitled')}",
            f"- Date: {item.get('created_at', '')}",
            f"- Projects: {', '.join(projects)}",
            "",
            str(item.get("snippet", ""))[:1800],
            "",
        ])
    return "\n".join(lines)
