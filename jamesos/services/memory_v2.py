from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from .unified_memory_search import search_unified, memory_answer_context


MEMORY_V2_ROOT = VAULT / "JamesOS" / "MemoryV2"
PEOPLE_DIR = MEMORY_V2_ROOT / "People"
PROJECTS_DIR = MEMORY_V2_ROOT / "Projects"
TICKETS_DIR = MEMORY_V2_ROOT / "Tickets"
TOPICS_DIR = MEMORY_V2_ROOT / "Topics"
INDEX_DIR = MEMORY_V2_ROOT / "Index"


_KNOWN_PEOPLE = [
    "Malcolm",
    "Kevin",
    "Tom",
    "Ian",
    "Luke",
    "Heather",
    "James",
    "Jidapa",
]

_KNOWN_PROJECTS = ["Paving", "JamesOS", "GCU", "CGI", "WGL", "UnityStitches"]

_TICKET_RE = re.compile(r"\b(8\d{4})\b")


def _ensure_dirs() -> None:
    for d in (PEOPLE_DIR, PROJECTS_DIR, TICKETS_DIR, TOPICS_DIR, INDEX_DIR):
        d.mkdir(parents=True, exist_ok=True)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_")


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _build_person_page(name: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"# {name}", "", "## Summary", "", f"Summary: mentions of {name}.", "", "## Known Context", "", "", "## Projects", "", "- TODO"]
    lines.extend(["", "## Tickets", "", "- TODO", "", "## Timeline", "", "- TODO", "", "## Decisions / Facts", "", "- TODO", "", "## Related People", "", "- TODO", "", "## Source Mentions", ""])
    for s in sources:
        lines.append(f"### {s.get('title', '')} ({s.get('source_type', '')})")
        lines.append(f"Path: {s.get('path', '')}")
        lines.append("")
        lines.append(s.get('snippet', '')[:2000])
        kf = s.get('key_facts') or []
        if kf:
            lines.append("")
            lines.append("Key facts:")
            for f in kf:
                lines.append(f"- {f}")
        lines.append("")
    return "\n".join(lines)


def _build_project_page(name: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"# {name}", "", "## Summary", "", f"Summary: project {name}.", "", "## People", "", "- TODO", "", "## Tickets", "", "- TODO", "", "## Decisions / Facts", "", "- TODO", "", "## Timeline", "", "- TODO", "", "## Source Mentions", ""]
    for s in sources:
        lines.append(f"### {s.get('title', '')} ({s.get('source_type', '')})")
        lines.append(f"Path: {s.get('path', '')}")
        lines.append("")
        lines.append(s.get('snippet', '')[:2000])
        lines.append("")
    return "\n".join(lines)


def _build_ticket_page(ticket: str, sources: list[dict[str, Any]]) -> str:
    lines = [f"# Ticket {ticket}", "", "## Summary", "", f"Summary: ticket {ticket}.", "", "## People", "", "- TODO", "", "## Project", "", "- TODO", "", "## Status / Decisions", "", "- TODO", "", "## Source Mentions", ""]
    for s in sources:
        lines.append(f"### {s.get('title', '')} ({s.get('source_type', '')})")
        lines.append(f"Path: {s.get('path', '')}")
        lines.append("")
        lines.append(s.get('snippet', '')[:2000])
        lines.append("")
    return "\n".join(lines)


def extract_entities_from_text(text: str) -> dict[str, list[str]]:
    people = []
    projects = []
    tickets = []
    for p in _KNOWN_PEOPLE:
        if p.lower() in text.lower() and p not in people:
            people.append(p)
    for pr in _KNOWN_PROJECTS:
        if pr.lower() in text.lower() and pr not in projects:
            projects.append(pr)
    for m in _TICKET_RE.findall(text):
        if m not in tickets:
            tickets.append(m)
    return {"people": people, "projects": projects, "tickets": tickets}


def build_memory_v2(limit_per_entity: int = 6) -> dict[str, Any]:
    _ensure_dirs()
    report_lines = ["# Memory V2 Report", ""]
    built = {"people": [], "projects": [], "tickets": []}

    # Seed entity lists by scanning a few broad queries
    queries = ["", "paving", "Malcolm", "JamesOS", "88858", "SFM2"]
    discovered = {"people": set(), "projects": set(), "tickets": set()}
    for q in queries:
        ctx = memory_answer_context(q, limit=limit_per_entity)
        for s in ctx.get("sources", []):
            txt = s.get("snippet", "") + "\n" + "\n".join(s.get("key_facts") or [])
            ent = extract_entities_from_text(txt)
            for p in ent.get("people", []):
                discovered["people"].add(p)
            for pr in ent.get("projects", []):
                discovered["projects"].add(pr)
            for t in ent.get("tickets", []):
                discovered["tickets"].add(t)

    # ensure known people present
    for p in _KNOWN_PEOPLE:
        discovered["people"].add(p)

    # Build people pages
    for person in sorted(discovered["people"]):
        res = memory_answer_context(person, limit=limit_per_entity)
        sources = res.get("sources", [])
        md = _build_person_page(person, sources)
        path = PEOPLE_DIR / f"{_slug(person)}.md"
        _write_markdown(path, md)
        built["people"].append(str(path))

    # Build project pages
    for project in sorted(discovered["projects"]):
        res = memory_answer_context(project, limit=limit_per_entity)
        sources = res.get("sources", [])
        md = _build_project_page(project, sources)
        path = PROJECTS_DIR / f"{_slug(project)}.md"
        _write_markdown(path, md)
        built["projects"].append(str(path))

    # Build ticket pages
    for ticket in sorted(discovered["tickets"]):
        res = memory_answer_context(ticket, limit=limit_per_entity)
        sources = res.get("sources", [])
        md = _build_ticket_page(ticket, sources)
        path = TICKETS_DIR / f"ticket_{_slug(ticket)}.md"
        _write_markdown(path, md)
        built["tickets"].append(str(path))

    # Simple index file
    index_path = INDEX_DIR / "index.md"
    idx_lines = ["# Memory V2 Index", "", "## People", ""]
    for p in sorted(discovered["people"]):
        idx_lines.append(f"- {p}")
    idx_lines.append("\n## Projects\n")
    for pr in sorted(discovered["projects"]):
        idx_lines.append(f"- {pr}")
    idx_lines.append("\n## Tickets\n")
    for t in sorted(discovered["tickets"]):
        idx_lines.append(f"- {t}")
    _write_markdown(index_path, "\n".join(idx_lines))

    report_lines.append(f"People built: {len(built['people'])}")
    report_lines.append(f"Projects built: {len(built['projects'])}")
    report_lines.append(f"Tickets built: {len(built['tickets'])}")
    report_path = VAULT / "JamesOS" / "Reports" / "Memory V2 Report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {"status": "ok", "built": built, "report": str(report_path)}


def load_entity_page(entity_type: str, name: str) -> dict[str, Any]:
    dmap = {
        "people": PEOPLE_DIR,
        "projects": PROJECTS_DIR,
        "tickets": TICKETS_DIR,
        "topics": TOPICS_DIR,
    }
    root = dmap.get(entity_type)
    if not root:
        return {"status": "error", "message": "unknown entity type"}
    path = root / f"{_slug(name)}.md"
    # tickets have ticket_ prefix
    if entity_type == "tickets":
        path = root / f"ticket_{_slug(name)}.md"
    if not path.exists():
        return {"status": "missing", "path": str(path)}
    return {"status": "ok", "path": str(path), "content": path.read_text(encoding="utf-8")}


def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "paths": {
            "people": str(PEOPLE_DIR),
            "projects": str(PROJECTS_DIR),
            "tickets": str(TICKETS_DIR),
            "index": str(INDEX_DIR),
        },
        "counts": {
            "people": sum(1 for _ in PEOPLE_DIR.glob("*.md")) if PEOPLE_DIR.exists() else 0,
            "projects": sum(1 for _ in PROJECTS_DIR.glob("*.md")) if PROJECTS_DIR.exists() else 0,
            "tickets": sum(1 for _ in TICKETS_DIR.glob("*.md")) if TICKETS_DIR.exists() else 0,
        },
    }
