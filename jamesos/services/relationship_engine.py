import json
from collections import defaultdict
from datetime import datetime
from itertools import combinations
from pathlib import Path

from jamesos.config import VAULT

INDEX_ROOT = VAULT / "JamesOS" / "Index"
ENTITIES_FILE = INDEX_ROOT / "entities.json"
RELATIONSHIPS_FILE = INDEX_ROOT / "relationships.json"


def _load_entities() -> dict:
    if not ENTITIES_FILE.exists():
        raise FileNotFoundError(f"Missing index file: {ENTITIES_FILE}")

    return json.loads(ENTITIES_FILE.read_text(encoding="utf-8"))


def _flatten_entities(entity_index: dict) -> dict[str, dict]:
    flat = {}

    for category, items in entity_index.get("entities", {}).items():
        for name, data in items.items():
            if data.get("mentions", 0) > 0:
                flat[name] = {
                    "name": name,
                    "type": category,
                    "files": set(data.get("files", [])),
                    "mentions": data.get("mentions", 0),
                }

    for ticket, data in entity_index.get("tickets", {}).items():
        flat[ticket] = {
            "name": ticket,
            "type": "Ticket",
            "files": set(data.get("files", [])),
            "mentions": data.get("mentions", 0),
        }

    return flat


def build_relationship_index() -> str:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)

    entity_index = _load_entities()
    flat = _flatten_entities(entity_index)

    relationships = defaultdict(lambda: {
        "source": "",
        "target": "",
        "source_type": "",
        "target_type": "",
        "shared_files": [],
        "weight": 0,
        "last_seen": None,
    })

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    names = sorted(flat.keys())

    for left, right in combinations(names, 2):
        left_files = flat[left]["files"]
        right_files = flat[right]["files"]
        shared = sorted(left_files & right_files)

        if not shared:
            continue

        key = f"{left} -> {right}"

        relationships[key] = {
            "source": left,
            "target": right,
            "source_type": flat[left]["type"],
            "target_type": flat[right]["type"],
            "shared_files": shared,
            "weight": len(shared),
            "last_seen": now,
        }

    output = {
        "generated_at": now,
        "vault": str(VAULT),
        "relationship_count": len(relationships),
        "relationships": dict(relationships),
    }

    RELATIONSHIPS_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")

    return f"Built relationship index: {RELATIONSHIPS_FILE.relative_to(VAULT)}"


def build_internal_db() -> str:
    from jamesos.services.indexer import build_entity_index

    entity_result = build_entity_index()
    relationship_result = build_relationship_index()

    return f"{entity_result}\n{relationship_result}"


def get_entity_relationships(name: str) -> str:
    if not RELATIONSHIPS_FILE.exists():
        build_internal_db()

    data = json.loads(RELATIONSHIPS_FILE.read_text(encoding="utf-8"))
    name_clean = name.strip().lower()

    matches = []

    for rel in data.get("relationships", {}).values():
        if rel["source"].lower() == name_clean or rel["target"].lower() == name_clean:
            other = rel["target"] if rel["source"].lower() == name_clean else rel["source"]
            other_type = rel["target_type"] if rel["source"].lower() == name_clean else rel["source_type"]
            files = ", ".join(rel.get("shared_files", []))
            matches.append(f"- {other} ({other_type}) via {files}")

    if not matches:
        return f"No relationships found for {name}"

    return f"# Relationships for {name}\n\n" + "\n".join(sorted(matches))
