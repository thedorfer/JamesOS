import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.database import build_database

DATABASE_FILE = VAULT / "JamesOS" / "Database" / "jamesos_db.json"
MEMORY_ROOT = VAULT / "JamesOS" / "Database" / "memory"
REPORTS_ROOT = VAULT / "JamesOS" / "Reports" / "Memory"


def _load_db() -> dict:
    if not DATABASE_FILE.exists():
        build_database()
    return json.loads(DATABASE_FILE.read_text(encoding="utf-8"))


def build_memory() -> str:
    db = _load_db()
    MEMORY_ROOT.mkdir(parents=True, exist_ok=True)
    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)

    relationships = db.get("relationships", {}).get("relationships", {})
    memory = defaultdict(lambda: {
        "entity": "",
        "type": "",
        "related": defaultdict(list),
        "files": set(),
        "last_seen": None,
    })

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for rel in relationships.values():
        source = rel.get("source", "")
        target = rel.get("target", "")
        source_type = rel.get("source_type", "")
        target_type = rel.get("target_type", "")
        files = rel.get("shared_files", [])

        if not source or not target:
            continue

        memory[source]["entity"] = source
        memory[source]["type"] = source_type
        memory[source]["related"][target_type].append(target)
        memory[source]["files"].update(files)
        memory[source]["last_seen"] = now

        memory[target]["entity"] = target
        memory[target]["type"] = target_type
        memory[target]["related"][source_type].append(source)
        memory[target]["files"].update(files)
        memory[target]["last_seen"] = now

    output = {}

    for entity, data in memory.items():
        output[entity] = {
            "entity": data["entity"],
            "type": data["type"],
            "related": {
                key: sorted(set(values))
                for key, values in data["related"].items()
            },
            "files": sorted(data["files"]),
            "last_seen": data["last_seen"],
        }

    memory_file = MEMORY_ROOT / "entities_memory.json"
    memory_file.write_text(json.dumps(output, indent=2), encoding="utf-8")

    return f"Built memory for {len(output)} entities"


def write_memory_report(entity: str) -> str:
    memory_file = MEMORY_ROOT / "entities_memory.json"
    if not memory_file.exists():
        build_memory()

    data = json.loads(memory_file.read_text(encoding="utf-8"))
    entity_clean = entity.strip()

    if entity_clean not in data:
        return f"No memory found for {entity_clean}"

    item = data[entity_clean]

    lines = [
        f"# Memory: {entity_clean}",
        "",
        f"Type: {item.get('type', '')}",
        f"Last Seen: {item.get('last_seen', '')}",
        "",
        "## Related Entities",
    ]

    related = item.get("related", {})
    if related:
        for category, values in sorted(related.items()):
            lines.append(f"### {category}")
            for value in values:
                lines.append(f"- {value}")
            lines.append("")
    else:
        lines.append("- None")

    lines.append("## Related Files")
    files = item.get("files", [])
    if files:
        for file in files:
            lines.append(f"- [[{Path(file).with_suffix('').as_posix()}]]")
    else:
        lines.append("- None")

    REPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    safe_name = entity_clean.replace("/", "-")
    report = REPORTS_ROOT / f"{safe_name}.md"
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return f"Wrote memory report: {report.relative_to(VAULT)}"
