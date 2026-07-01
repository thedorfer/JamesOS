import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.knowledge import DEFAULT_ENTITIES

INDEX_ROOT = VAULT / "JamesOS" / "Index"


def _read_md_files() -> list[Path]:
    ignore_parts = {".obsidian", ".trash", "JamesOS/Index"}
    files = []
    for path in VAULT.rglob("*.md"):
        rel = path.relative_to(VAULT).as_posix()
        if any(part in rel for part in ignore_parts):
            continue
        files.append(path)
    return files


def _known_entities() -> dict[str, list[str]]:
    return DEFAULT_ENTITIES


def build_entity_index() -> str:
    INDEX_ROOT.mkdir(parents=True, exist_ok=True)

    entities = {
        category: {
            name: {
                "type": category,
                "mentions": 0,
                "files": [],
                "last_seen": None,
            }
            for name in names
        }
        for category, names in _known_entities().items()
    }

    ticket_index = defaultdict(lambda: {
        "mentions": 0,
        "files": [],
        "last_seen": None,
    })

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for path in _read_md_files():
        rel = path.relative_to(VAULT).as_posix()

        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue

        for category, names in _known_entities().items():
            for name in names:
                pattern = r"\b" + re.escape(name) + r"\b"
                count = len(re.findall(pattern, text, flags=re.IGNORECASE))
                if count:
                    entities[category][name]["mentions"] += count
                    entities[category][name]["files"].append(rel)
                    entities[category][name]["last_seen"] = now

        for ticket in re.findall(r"\b\d{5}\b", text):
            ticket_index[ticket]["mentions"] += 1
            ticket_index[ticket]["files"].append(rel)
            ticket_index[ticket]["last_seen"] = now

    output = {
        "generated_at": now,
        "vault": str(VAULT),
        "entities": entities,
        "tickets": dict(ticket_index),
    }

    index_file = INDEX_ROOT / "entities.json"
    index_file.write_text(json.dumps(output, indent=2), encoding="utf-8")

    return f"Built entity index: {index_file.relative_to(VAULT)}"
