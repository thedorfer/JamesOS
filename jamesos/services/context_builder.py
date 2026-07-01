import json
from pathlib import Path

from jamesos.config import VAULT

DATABASE_FILE = VAULT / "JamesOS" / "Database" / "jamesos_db.json"


def _load_db() -> dict:
    if not DATABASE_FILE.exists():
        from jamesos.services.database import build_database
        build_database()
    return json.loads(DATABASE_FILE.read_text(encoding="utf-8"))


def build_context(entity: str) -> str:
    db = _load_db()
    entity_clean = entity.strip()
    entity_lower = entity_clean.lower()

    relationships = db.get("relationships", {}).get("relationships", {})
    search_entries = db.get("search", {}).get("entries", [])

    related = []
    files = set()

    for rel in relationships.values():
        source = rel.get("source", "")
        target = rel.get("target", "")

        if source.lower() == entity_lower:
            related.append((target, rel.get("target_type", ""), rel.get("shared_files", [])))
            files.update(rel.get("shared_files", []))
        elif target.lower() == entity_lower:
            related.append((source, rel.get("source_type", ""), rel.get("shared_files", [])))
            files.update(rel.get("shared_files", []))

    for entry in search_entries:
        if entity_lower in entry.get("title", "").lower() or entity_lower in entry.get("content", ""):
            files.add(entry.get("file", ""))

    lines = [
        f"# Context: {entity_clean}",
        "",
        "## Related Entities",
    ]

    if related:
        for name, type_name, shared_files in sorted(related):
            lines.append(f"- {name} ({type_name})")
            for file in shared_files:
                lines.append(f"  - [[{Path(file).with_suffix('').as_posix()}]]")
    else:
        lines.append("- None found")

    lines.extend(["", "## Related Files"])

    clean_files = sorted(f for f in files if f)
    if clean_files:
        for file in clean_files:
            lines.append(f"- [[{Path(file).with_suffix('').as_posix()}]]")
    else:
        lines.append("- None found")

    lines.extend(["", "## Source Previews"])

    for file in clean_files[:10]:
        path = VAULT / file
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="ignore").strip()
            preview = text[:1200]
            lines.extend([
                f"### [[{Path(file).with_suffix('').as_posix()}]]",
                "",
                preview,
                "",
            ])

    return "\n".join(lines)


def write_context_report(entity: str) -> str:
    report = build_context(entity)
    reports_dir = VAULT / "JamesOS" / "Reports" / "Context"
    reports_dir.mkdir(parents=True, exist_ok=True)

    safe_name = entity.strip().replace("/", "-")
    path = reports_dir / f"{safe_name}.md"
    path.write_text(report + "\n", encoding="utf-8")

    return f"Wrote context report: {path.relative_to(VAULT)}"
