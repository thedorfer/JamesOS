import json
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

INDEX_ROOT = VAULT / "JamesOS" / "Database" / "indexes"

CATEGORIES = {
    "people": [VAULT / "JamesOS" / "People"],
    "work": [VAULT / "Work", VAULT / "JamesOS" / "Knowledge" / "Tickets"],
    "gmail": [VAULT / "Archive" / "Inbox" / "Gmail"],
    "gcu": [VAULT / "Archive" / "Inbox" / "GCU"],
    "calendar": [VAULT / "Archive" / "Inbox" / "Calendar"],
    "knowledge": [VAULT / "JamesOS" / "Knowledge"],
    "reports": [VAULT / "JamesOS" / "Reports"],
    "intake": [VAULT / "JamesOS" / "Intake"],
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def build_typed_indexes() -> str:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)
    total = 0

    for category, roots in CATEGORIES.items():
        entries = []

        for root in roots:
            if not root.exists():
                continue

            for path in root.rglob("*.md"):
                text = _read(path)
                rel = path.relative_to(VAULT).as_posix()

                entries.append({
                    "file": rel,
                    "title": path.stem,
                    "modified": path.stat().st_mtime,
                    "preview": text[:800],
                    "text": text[:5000],
                })

        entries.sort(key=lambda e: e["modified"], reverse=True)

        (INDEX_ROOT / f"{category}.json").write_text(json.dumps({
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "category": category,
            "count": len(entries),
            "entries": entries,
        }, indent=2), encoding="utf-8")

        total += len(entries)

    return f"Built typed indexes with {total} entries"


def search_typed_indexes(query: str, categories: list[str] | None = None, limit: int = 10) -> dict:
    q = query.lower().strip()
    results = {}

    if categories is None:
        categories = list(CATEGORIES.keys())

    for category in categories:
        path = INDEX_ROOT / f"{category}.json"
        if not path.exists():
            continue

        data = json.loads(path.read_text(encoding="utf-8"))
        matches = []

        for entry in data.get("entries", []):
            text = (entry.get("title", "") + "\n" + entry.get("text", "")).lower()
            score = 0

            if q in entry.get("title", "").lower():
                score += 30

            score += text.count(q) * 5

            if score:
                matches.append({
                    "score": score,
                    "file": entry["file"],
                    "title": entry["title"],
                    "preview": entry["preview"],
                })

        matches.sort(key=lambda e: e["score"], reverse=True)
        results[category] = matches[:limit]

    return results
