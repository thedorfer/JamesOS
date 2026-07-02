import json
from pathlib import Path
from datetime import datetime

from jamesos.config import VAULT
from jamesos.services.extraction_engine import build_unified_graph
from jamesos.services.ollama_service import ask_ollama, ollama_enabled

GRAPH_FILE = VAULT / "JamesOS" / "Database" / "unified_graph.json"
REPORTS = VAULT / "JamesOS" / "Reports" / "Context"


def build_context_report(query: str, use_ai: bool = False) -> str:
    if not GRAPH_FILE.exists():
        build_unified_graph()

    data = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
    q = query.lower().strip()

    matches = []
    for name, node in data.get("nodes", {}).items():
        score = 0
        if q in name.lower():
            score += 20
        for file in node.get("files", []):
            if q in file.lower():
                score += 5
        for values in node.get("links", {}).values():
            for value in values:
                if q in value.lower():
                    score += 3
        if score:
            matches.append((score, name, node))

    matches.sort(reverse=True, key=lambda x: x[0])

    lines = [
        f"# Context Report: {query}",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Matches",
    ]

    source_text = []

    for score, name, node in matches[:15]:
        lines.append(f"## {name}")
        lines.append(f"- Type: {node.get('type', '')}")
        lines.append(f"- Score: {score}")

        files = node.get("files", [])[:10]
        if files:
            lines.append("- Files:")
            for file in files:
                lines.append(f"  - [[{Path(file).with_suffix('').as_posix()}]]")
                p = VAULT / file
                if p.exists() and len(source_text) < 8:
                    source_text.append(p.read_text(encoding="utf-8", errors="ignore")[:1200])

        lines.append("")

    if use_ai and ollama_enabled() and source_text:
        prompt = (
            "Summarize the following JamesOS context for the user. "
            "Focus on facts, relationships, and useful next actions.\n\n"
            + "\n\n---\n\n".join(source_text)
        )
        try:
            lines.extend(["", "## Ollama Summary", "", ask_ollama(prompt)])
        except Exception as exc:
            lines.extend(["", "## Ollama Summary", "", f"Ollama failed: {exc}"])

    REPORTS.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in " -_" else "-" for c in query)[:80]
    path = REPORTS / f"{safe}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return f"Wrote context report: {path.relative_to(VAULT)}"
