import json
from pathlib import Path

from jamesos.config import VAULT

INDEX_ROOT = VAULT / "JamesOS" / "Index"
RELATIONSHIPS_FILE = INDEX_ROOT / "relationships.json"
SEARCH_FILE = INDEX_ROOT / "search.json"


def build_context(entity: str) -> str:
    entity_clean = entity.strip()

    if not RELATIONSHIPS_FILE.exists():
        from jamesos.services.relationship_engine import build_internal_db
        build_internal_db()

    relationships = json.loads(RELATIONSHIPS_FILE.read_text(encoding="utf-8"))

    related = []
    files = set()

    for rel in relationships.get("relationships", {}).values():
        if rel["source"].lower() == entity_clean.lower():
            related.append((rel["target"], rel["target_type"], rel.get("shared_files", [])))
            files.update(rel.get("shared_files", []))
        elif rel["target"].lower() == entity_clean.lower():
            related.append((rel["source"], rel["source_type"], rel.get("shared_files", [])))
            files.update(rel.get("shared_files", []))

    lines = [
        f"# Context: {entity_clean}",
        "",
        "## Related Entities",
    ]

    if related:
        for name, type_, shared_files in sorted(related):
            lines.append(f"- {name} ({type_})")
            for file in shared_files:
                lines.append(f"  - [[{Path(file).with_suffix('').as_posix()}]]")
    else:
        lines.append("- None found")

    lines.extend([
        "",
        "## Related Files",
    ])

    if files:
        for file in sorted(files):
            lines.append(f"- [[{Path(file).with_suffix('').as_posix()}]]")
    else:
        lines.append("- None found")

    lines.extend([
        "",
        "## Source Notes",
    ])

    for file in sorted(files):
        path = VAULT / file
        if path.exists():
            lines.append(f"### [[{Path(file).with_suffix('').as_posix()}]]")
            text = path.read_text(encoding="utf-8", errors="ignore")
            preview = text[:1000].strip()
            lines.append("")
            lines.append(preview)
            lines.append("")

    return "\n".join(lines)


def write_context_report(entity: str) -> str:
    report = build_context(entity)

    reports_dir = VAULT / "JamesOS" / "Reports" / "Context"
    reports_dir.mkdir(parents=True, exist_ok=True)

    safe_name = entity.strip().replace("/", "-")
    path = reports_dir / f"{safe_name}.md"
    path.write_text(report + "\n", encoding="utf-8")

    return f"Wrote context report: {path.relative_to(VAULT)}"
