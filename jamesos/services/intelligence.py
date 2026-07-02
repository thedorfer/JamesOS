import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.database import build_database

DB_FILE = VAULT / "JamesOS" / "Database" / "jamesos_db.json"
GRAPH_FILE = VAULT / "JamesOS" / "Database" / "knowledge_graph.json"
REPORTS = VAULT / "JamesOS" / "Reports"


def _load_db() -> dict:
    if not DB_FILE.exists():
        build_database()
    return json.loads(DB_FILE.read_text(encoding="utf-8"))


def build_knowledge_graph() -> str:
    db = _load_db()
    graph = defaultdict(lambda: {"type": "", "links": defaultdict(set), "files": set()})

    relationships = db.get("relationships", {}).get("relationships", {})
    for rel in relationships.values():
        src = rel.get("source", "")
        tgt = rel.get("target", "")
        if not src or not tgt:
            continue

        graph[src]["type"] = rel.get("source_type", "")
        graph[tgt]["type"] = rel.get("target_type", "")
        graph[src]["links"][rel.get("target_type", "related")].add(tgt)
        graph[tgt]["links"][rel.get("source_type", "related")].add(src)

        for file in rel.get("shared_files", []):
            graph[src]["files"].add(file)
            graph[tgt]["files"].add(file)

    output = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "nodes": {
            name: {
                "type": data["type"],
                "links": {k: sorted(v) for k, v in data["links"].items()},
                "files": sorted(data["files"]),
            }
            for name, data in graph.items()
        },
    }

    GRAPH_FILE.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_FILE.write_text(json.dumps(output, indent=2), encoding="utf-8")
    return f"Built knowledge graph with {len(output['nodes'])} nodes"


def smart_search(query: str, limit: int = 10) -> str:
    if not GRAPH_FILE.exists():
        build_knowledge_graph()

    graph = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    q = query.lower().strip()

    matches = []
    for name, data in graph.get("nodes", {}).items():
        score = 0
        if q in name.lower():
            score += 20
        for category, values in data.get("links", {}).items():
            for value in values:
                if q in value.lower():
                    score += 5
        for file in data.get("files", []):
            if q in file.lower():
                score += 3

        if score:
            matches.append((score, name, data))

    matches.sort(reverse=True, key=lambda x: x[0])

    lines = [f"# Smart Search: {query}", ""]
    if not matches:
        lines.append("No graph matches found.")
        return "\n".join(lines)

    for score, name, data in matches[:limit]:
        lines.append(f"## {name}")
        lines.append(f"- Type: {data.get('type', '')}")
        lines.append(f"- Score: {score}")

        for category, values in sorted(data.get("links", {}).items()):
            if values:
                lines.append(f"- {category}: {', '.join(values[:10])}")

        files = data.get("files", [])[:5]
        if files:
            lines.append("- Files:")
            for file in files:
                lines.append(f"  - [[{Path(file).with_suffix('').as_posix()}]]")

        lines.append("")

    return "\n".join(lines)


def generate_daily_intelligence() -> str:
    build_knowledge_graph()
    db = _load_db()

    search_entries = db.get("search", {}).get("entries", [])
    recent = sorted(search_entries, key=lambda e: e.get("modified", ""), reverse=True)[:20]

    lines = [
        "# Daily Intelligence",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## What Changed Recently",
    ]

    for entry in recent[:10]:
        lines.append(f"- [[{Path(entry.get('file', '')).with_suffix('').as_posix()}]]")

    lines.extend([
        "",
        "## Suggested Review",
        "- [[JamesOS/Reports/Recommendations]]",
        "- [[JamesOS/Reports/Work Intelligence]]",
        "- [[JamesOS/Reports/People]]",
        "- [[JamesOS/Reports/AI Inbox Cleanup]]",
        "",
        "## Useful Searches",
        "- `jamesos smart-search Kevin`",
        "- `jamesos smart-search travel`",
        "- `jamesos smart-search GCU`",
        "- `jamesos smart-search calendar`",
    ])

    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / "Daily Intelligence.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Wrote daily intelligence: {path.relative_to(VAULT)}"
