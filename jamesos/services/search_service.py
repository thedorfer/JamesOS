import json
import re
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

INDEX_ROOT = VAULT / "JamesOS" / "Index"
SEARCH_FILE = INDEX_ROOT / "search.json"


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def build_search_index() -> str:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)

    entries = []

    for path in VAULT.rglob("*.md"):
        rel = path.relative_to(VAULT).as_posix()

        if rel.startswith(".obsidian/") or rel.startswith(".trash/"):
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        title = path.stem
        preview = _clean_text(text[:500])

        entries.append({
            "title": title,
            "file": rel,
            "folder": str(Path(rel).parent),
            "modified": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M"),
            "content": _clean_text(text.lower()),
            "preview": preview,
        })

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "entry_count": len(entries),
        "entries": entries,
    }

    SEARCH_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return f"Built search index with {len(entries)} entries"


def search_notes_index(query: str, limit: int = 10) -> str:
    if not SEARCH_FILE.exists():
        build_search_index()

    data = json.loads(SEARCH_FILE.read_text(encoding="utf-8"))
    q = query.strip().lower()

    results = []

    for entry in data.get("entries", []):
        score = 0

        if q in entry["title"].lower():
            score += 10

        if q in entry["file"].lower():
            score += 5

        if q in entry["content"]:
            score += entry["content"].count(q)

        if score > 0:
            results.append((score, entry))

    results.sort(key=lambda x: x[0], reverse=True)

    if not results:
        return f"No search results found for: {query}"

    lines = [f"# Search Results for {query}", ""]

    for score, entry in results[:limit]:
        link = Path(entry["file"]).with_suffix("").as_posix()
        lines.append(f"- [[{link}]] — score {score}")
        if entry.get("preview"):
            lines.append(f"  - {entry['preview'][:180]}")

    return "\n".join(lines)
