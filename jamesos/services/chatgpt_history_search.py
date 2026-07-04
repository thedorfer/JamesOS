from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jamesos.config import VAULT

INDEX_PATH = VAULT / "JamesOS" / "Brain" / "ChatGPT" / "Index" / "conversations_index.jsonl"


def _terms(query: str) -> list[str]:
    return [t.lower() for t in re.findall(r"[A-Za-z0-9_#.-]{3,}", query)][:12]


def search_chatgpt_history(query: str, limit: int = 8) -> dict[str, Any]:
    if not INDEX_PATH.exists():
        return {"status": "missing", "query": query, "results": [], "message": "ChatGPT history index has not been imported yet."}

    terms = _terms(query)
    scored = []
    with INDEX_PATH.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            haystack = f"{item.get('title','')} {item.get('snippet','')} {' '.join(item.get('projects') or [])}".lower()
            score = sum(3 if term in str(item.get("title", "")).lower() else 1 for term in terms if term in haystack)
            if score:
                item["score"] = score
                scored.append(item)

    scored.sort(key=lambda x: (x.get("score", 0), x.get("created_at", "")), reverse=True)
    return {"status": "ok", "query": query, "results": scored[:limit], "count": len(scored)}


def chatgpt_history_context(query: str, limit: int = 6) -> str:
    result = search_chatgpt_history(query, limit=limit)
    rows = result.get("results") or []
    if not rows:
        return "No matching imported ChatGPT history found."

    lines = ["# Imported ChatGPT History Matches", ""]
    for item in rows:
        lines.extend([
            f"## {item.get('title', 'Untitled')}",
            f"- Date: {item.get('created_at', '')}",
            f"- Projects: {', '.join(item.get('projects') or ['Unclassified'])}",
            f"- Messages: {item.get('message_count', 0)}",
            f"- Path: {item.get('path', '')}",
            "",
            str(item.get("snippet", ""))[:1200],
            "",
        ])
    return "\n".join(lines)
