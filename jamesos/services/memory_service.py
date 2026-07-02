import json
import uuid
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT

MEMORY_ROOT = VAULT / "JamesOS" / "Memory"
MEMORY_FILE = MEMORY_ROOT / "conversation_memory.json"
MEMORY_NOTES = VAULT / "JamesOS" / "Memory" / "Notes"


def _load() -> dict:
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    MEMORY_NOTES.mkdir(parents=True, exist_ok=True)

    if not MEMORY_FILE.exists():
        return {"memories": []}

    return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))


def _save(data: dict) -> None:
    MEMORY_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def remember(text: str, source: str = "manual", importance: str = "normal") -> dict:
    data = _load()

    item = {
        "id": uuid.uuid4().hex[:12],
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "importance": importance,
        "text": text,
    }

    data["memories"].append(item)
    _save(data)

    note = MEMORY_NOTES / f"{item['created_at'][:10]} - {item['id']}.md"
    note.write_text(f"""# Memory {item['id']}

Created: {item['created_at']}
Source: {source}
Importance: {importance}

## Memory

{text}
""", encoding="utf-8")

    return item


def search_memory(query: str, limit: int = 10) -> list[dict]:
    data = _load()
    q = query.lower()

    matches = []
    for item in data.get("memories", []):
        if q in item.get("text", "").lower():
            matches.append(item)

    return list(reversed(matches))[:limit]
