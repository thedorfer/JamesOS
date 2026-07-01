import json
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.memory_engine import build_memory
from jamesos.services.context_builder import build_context

MEMORY_FILE = VAULT / "JamesOS" / "Database" / "memory" / "entities_memory.json"
REPORTS = VAULT / "JamesOS" / "Reports"


def _load_memory() -> dict:
    if not MEMORY_FILE.exists():
        build_memory()
    return json.loads(MEMORY_FILE.read_text(encoding="utf-8"))


def _link(file: str) -> str:
    return f"[[{Path(file).with_suffix('').as_posix()}]]"


def generate_work_graph() -> str:
    memory = _load_memory()
    REPORTS.mkdir(parents=True, exist_ok=True)

    lines = [
        "# Work Graph",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    for entity, data in sorted(memory.items()):
        if data.get("type") not in ["Ticket", "People", "Projects", "Systems", "Customers", "Environments"]:
            continue

        lines.append(f"## {entity}")
        lines.append(f"Type: {data.get('type', '')}")
        lines.append("")

        for category, values in sorted(data.get("related", {}).items()):
            lines.append(f"### {category}")
            for value in values:
                lines.append(f"- {value}")
            lines.append("")

        files = data.get("files", [])
        if files:
            lines.append("### Files")
            for file in files:
                lines.append(f"- {_link(file)}")
            lines.append("")

    path = REPORTS / "Work Graph.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote work graph: {path.relative_to(VAULT)}"


def generate_recommendations() -> str:
    work = VAULT / "Work"
    REPORTS.mkdir(parents=True, exist_ok=True)

    ready = sorted((work / "Ready for Testing").glob("*.md")) if (work / "Ready for Testing").exists() else []
    waiting = sorted((work / "Waiting").glob("*.md")) if (work / "Waiting").exists() else []
    active = sorted((work / "Active Tickets").glob("*.md")) if (work / "Active Tickets").exists() else []
    inbox = sorted((VAULT / "00-Inbox").glob("*.md")) if (VAULT / "00-Inbox").exists() else []

    lines = [
        "# Recommendations",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Suggested Focus",
    ]

    if ready:
        lines.append("- Follow up on Ready for Testing tickets.")
    if waiting:
        lines.append("- Review Waiting items and decide whether to follow up.")
    if active:
        lines.append("- Update active ticket notes before end of day.")
    if inbox:
        lines.append("- Clear inbox captures.")
    if not any([ready, waiting, active, inbox]):
        lines.append("- No urgent JamesOS items found.")

    lines.extend(["", "## Specific Items"])

    for label, files in [
        ("Ready for Testing", ready),
        ("Waiting", waiting),
        ("Active", active),
        ("Inbox", inbox),
    ]:
        lines.append(f"### {label}")
        lines.extend([f"- [[{p.relative_to(VAULT).with_suffix('').as_posix()}]]" for p in files] or ["- None"])
        lines.append("")

    path = REPORTS / "Recommendations.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote recommendations: {path.relative_to(VAULT)}"


def generate_automatic_context() -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)

    work = VAULT / "Work"
    entities = []

    for folder in ["Ready for Testing", "Waiting", "Active Tickets"]:
        path = work / folder
        if path.exists():
            entities.extend(p.stem for p in path.glob("*.md"))

    lines = [
        "# Automatic Context",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
    ]

    if not entities:
        lines.append("No active work context found.")
    else:
        for entity in sorted(set(entities)):
            lines.append(f"## {entity}")
            lines.append("")
            lines.append(build_context(entity))
            lines.append("")

    path = REPORTS / "Automatic Context.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote automatic context: {path.relative_to(VAULT)}"


def generate_daily_conversation_memory() -> str:
    REPORTS.mkdir(parents=True, exist_ok=True)

    daily = VAULT / "Daily"
    meetings = VAULT / "Work" / "Meetings"

    recent_daily = sorted(daily.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5] if daily.exists() else []
    recent_meetings = sorted(meetings.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:5] if meetings.exists() else []

    lines = [
        "# Daily Conversation Memory",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "## Recent Daily Notes",
    ]

    lines.extend([f"- [[{p.relative_to(VAULT).with_suffix('').as_posix()}]]" for p in recent_daily] or ["- None"])

    lines.extend(["", "## Recent Meetings"])
    lines.extend([f"- [[{p.relative_to(VAULT).with_suffix('').as_posix()}]]" for p in recent_meetings] or ["- None"])

    lines.extend([
        "",
        "## Use This For",
        "- Continue where I left off yesterday",
        "- Summarize recent work context",
        "- Reconstruct recent conversations from notes",
        "",
    ])

    path = REPORTS / "Daily Conversation Memory.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return f"Wrote daily conversation memory: {path.relative_to(VAULT)}"


def generate_brain_reports() -> str:
    return "\n".join([
        build_memory(),
        generate_work_graph(),
        generate_recommendations(),
        generate_automatic_context(),
        generate_daily_conversation_memory(),
    ])
