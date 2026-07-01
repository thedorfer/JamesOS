from datetime import datetime
from pathlib import Path
import json

from jamesos.config import VAULT

INDEX_ROOT = VAULT / "JamesOS" / "Index"
ENTITIES_FILE = INDEX_ROOT / "entities.json"
KNOWLEDGE_ROOT = VAULT / "JamesOS" / "Knowledge"


def update_knowledge_pages() -> str:
    if not ENTITIES_FILE.exists():
        from jamesos.services.relationship_engine import build_internal_db
        build_internal_db()

    data = json.loads(ENTITIES_FILE.read_text(encoding="utf-8"))
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    updated = 0

    for category, entities in data.get("entities", {}).items():
        folder = KNOWLEDGE_ROOT / category
        folder.mkdir(parents=True, exist_ok=True)

        for name, info in entities.items():
            if info.get("mentions", 0) <= 0:
                continue

            path = folder / f"{name}.md"
            files = info.get("files", [])

            content = f"""# {name}

Type: {category}
Last Indexed: {now}
Mentions: {info.get("mentions", 0)}
Status: active

## Summary

## Mentioned In

"""
            for file in files:
                content += f"- [[{Path(file).with_suffix('').as_posix()}]]\n"

            content += """

## Related Work

## Notes

"""

            path.write_text(content, encoding="utf-8")
            updated += 1

    return f"Updated {updated} knowledge pages"
