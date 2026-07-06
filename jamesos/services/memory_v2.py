from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import NOTES_VAULT, VAULT
from .unified_memory_search import search_unified, memory_answer_context


MEMORY_V2_ROOT = VAULT / "JamesOS" / "MemoryV2"
PEOPLE_DIR = MEMORY_V2_ROOT / "People"
PROJECTS_DIR = MEMORY_V2_ROOT / "Projects"
TICKETS_DIR = MEMORY_V2_ROOT / "Tickets"
TOPICS_DIR = MEMORY_V2_ROOT / "Topics"
INDEX_DIR = MEMORY_V2_ROOT / "Index"
TIMELINE_DIR = VAULT / "JamesOS" / "Timeline" / "Email" / "Outlook"
EMAIL_ROOT = VAULT / "JamesOS" / "Brain" / "Email" / "Outlook"
CONTACTS_INDEX_PATH = INDEX_DIR / "contacts_index.jsonl"
PEOPLE_STATS_PATH = INDEX_DIR / "people_stats.json"
DEFAULT_PEOPLE_THRESHOLD = 5


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
    for d in (PEOPLE_DIR, PROJECTS_DIR, TICKETS_DIR, TOPICS_DIR, INDEX_DIR, TIMELINE_DIR):
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


def _json_metadata(text: str, label: str) -> list[str]:
    match = re.search(rf"^{re.escape(label)}:\s*(\[.*\])\s*$", text, re.MULTILINE)
    if not match:
        return []
    try:
        values = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return [str(value) for value in values if str(value).strip()]


def _normalize_person(name: str) -> str:
    return name.strip().strip("'\"").strip()


def _email_catalog() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    if not EMAIL_ROOT.exists():
        return sources
    for path in sorted(EMAIL_ROOT.rglob("*.md")):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        title_match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        date_match = re.search(r"^Date Sent:\s*(.+)$", text, re.MULTILINE)
        from_match = re.search(r"^From:\s*(.*)$", text, re.MULTILINE)
        message_match = re.search(r"^## Message\s*$\n+(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
        source = {
            "title": title_match.group(1).strip() if title_match else path.stem,
            "source_type": "outlook_email",
            "path": str(path),
            "snippet": (message_match.group(1).strip() if message_match else text)[:2000],
            "score": 100,
            "key_facts": [],
            "date_sent": date_match.group(1).strip() if date_match else "",
            "from": from_match.group(1).strip() if from_match else "",
            "people": list(
                dict.fromkeys(
                    normalized
                    for value in _json_metadata(text, "People")
                    if (normalized := _normalize_person(value))
                )
            ),
            "email_addresses": _json_metadata(text, "Email addresses"),
            "projects": _json_metadata(text, "Projects"),
            "tickets": _json_metadata(text, "Tickets"),
        }
        sources.append(source)
    return sources


def _promotion_context_text() -> str:
    files = [VAULT / "JamesOS" / "Memory" / "Notes" / "work_contacts.md"]
    roots = [
        VAULT / "JamesOS" / "Reports" / "Context",
        VAULT / "JamesOS" / "Knowledge" / "Projects",
        NOTES_VAULT / "Work" / "Active Tickets",
        NOTES_VAULT / "Work" / "Completed",
        NOTES_VAULT / "Work" / "Ready for Testing",
        NOTES_VAULT / "Work" / "Waiting",
    ]
    for root in roots:
        if root.exists():
            files.extend(root.rglob("*.md"))

    text: list[str] = []
    seen: set[Path] = set()
    for path in files:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            text.append(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError):
            continue
    return "\n".join(text).casefold()


def _promoted_people(
    contact_counts: dict[str, int],
    memory_people: set[str],
    threshold: int,
    include_all_contacts: bool,
    promotion_context: str,
) -> set[str]:
    promoted = set(_KNOWN_PEOPLE) | set(memory_people)
    if include_all_contacts:
        promoted.update(contact_counts)
        return promoted
    for person, count in contact_counts.items():
        if count >= threshold or (len(person.strip()) >= 3 and person.casefold() in promotion_context):
            promoted.add(person)
    return promoted


def _write_contacts_index(
    suppressed: set[str],
    email_by_person: dict[str, list[dict[str, Any]]],
) -> None:
    CONTACTS_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = CONTACTS_INDEX_PATH.with_suffix(".jsonl.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        for person in sorted(suppressed, key=str.casefold):
            sources = email_by_person.get(person, [])
            dates = sorted(source.get("date_sent", "") for source in sources if source.get("date_sent"))
            row = {
                "name": person,
                "contact_count": len(sources),
                "first_seen": dates[0] if dates else "",
                "last_seen": dates[-1] if dates else "",
            }
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    temp_path.replace(CONTACTS_INDEX_PATH)


def _write_people_stats(stats: dict[str, Any]) -> None:
    PEOPLE_STATS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PEOPLE_STATS_PATH.write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _remove_suppressed_people_pages(promoted: set[str]) -> int:
    desired = {PEOPLE_DIR / f"{_slug(person)}.md" for person in promoted}
    removed = 0
    for path in PEOPLE_DIR.glob("*.md"):
        if path not in desired:
            path.unlink()
            removed += 1
    return removed


def _merge_sources(primary: list[dict[str, Any]], secondary: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in primary + secondary:
        key = str(source.get("path") or source.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(source)
        if len(merged) >= limit:
            break
    return merged


def _build_email_timeline(email_sources: list[dict[str, Any]]) -> list[str]:
    by_date: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in email_sources:
        try:
            date_key = datetime.fromisoformat(source["date_sent"]).date().isoformat()
        except (KeyError, TypeError, ValueError):
            continue
        by_date[date_key].append(source)

    paths: list[str] = []
    for date_key, sources in sorted(by_date.items()):
        lines = [f"# Email Timeline — {date_key}", ""]
        for source in sources:
            lines.extend(
                [
                    f"## {source['title']}",
                    "",
                    f"- From: {source.get('from', '')}",
                    f"- People: {', '.join(source.get('people') or []) or 'None'}",
                    f"- Projects: {', '.join(source.get('projects') or []) or 'None'}",
                    f"- Tickets: {', '.join(source.get('tickets') or []) or 'None'}",
                    f"- Source: {source['path']}",
                    "",
                    source.get("snippet", "")[:500],
                    "",
                ]
            )
        path = TIMELINE_DIR / f"{date_key}.md"
        _write_markdown(path, "\n".join(lines))
        paths.append(str(path))
    return paths


def build_memory_v2(
    limit_per_entity: int = 6,
    people_threshold: int | None = None,
    include_all_contacts: bool = False,
) -> dict[str, Any]:
    _ensure_dirs()
    if people_threshold is None:
        try:
            people_threshold = int(
                os.environ.get("MEMORY_V2_PEOPLE_THRESHOLD", DEFAULT_PEOPLE_THRESHOLD)
            )
        except ValueError:
            people_threshold = DEFAULT_PEOPLE_THRESHOLD
    people_threshold = max(1, people_threshold)
    report_lines = ["# Memory V2 Report", ""]
    built = {"people": [], "projects": [], "tickets": [], "timeline": []}
    email_sources = _email_catalog()
    email_by_person: dict[str, list[dict[str, Any]]] = defaultdict(list)
    email_by_project: dict[str, list[dict[str, Any]]] = defaultdict(list)
    email_by_ticket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in email_sources:
        for person in source["people"]:
            email_by_person[person].append(source)
        for project in source["projects"]:
            email_by_project[project].append(source)
        for ticket in source["tickets"]:
            email_by_ticket[ticket].append(source)

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
    memory_discovered = {key: set(values) for key, values in discovered.items()}
    contact_counts = {person: len(sources) for person, sources in email_by_person.items()}
    promoted_people = _promoted_people(
        contact_counts=contact_counts,
        memory_people=memory_discovered["people"],
        threshold=people_threshold,
        include_all_contacts=include_all_contacts,
        promotion_context=_promotion_context_text(),
    )
    raw_contacts = set(email_by_person)
    suppressed_contacts = raw_contacts - promoted_people
    discovered["people"] = promoted_people
    discovered["projects"].update(email_by_project)
    discovered["tickets"].update(email_by_ticket)
    _write_contacts_index(suppressed_contacts, email_by_person)
    removed_people_pages = _remove_suppressed_people_pages(promoted_people)

    # Build people pages
    for person in sorted(discovered["people"]):
        memory_sources = []
        if person in memory_discovered["people"]:
            memory_sources = memory_answer_context(person, limit=limit_per_entity).get("sources", [])
        sources = _merge_sources(email_by_person.get(person, []), memory_sources, limit_per_entity)
        md = _build_person_page(person, sources)
        path = PEOPLE_DIR / f"{_slug(person)}.md"
        _write_markdown(path, md)
        built["people"].append(str(path))

    # Build project pages
    for project in sorted(discovered["projects"]):
        memory_sources = []
        if project in memory_discovered["projects"]:
            memory_sources = memory_answer_context(project, limit=limit_per_entity).get("sources", [])
        sources = _merge_sources(email_by_project.get(project, []), memory_sources, limit_per_entity)
        md = _build_project_page(project, sources)
        path = PROJECTS_DIR / f"{_slug(project)}.md"
        _write_markdown(path, md)
        built["projects"].append(str(path))

    # Build ticket pages
    for ticket in sorted(discovered["tickets"]):
        memory_sources = []
        if ticket in memory_discovered["tickets"]:
            memory_sources = memory_answer_context(ticket, limit=limit_per_entity).get("sources", [])
        sources = _merge_sources(email_by_ticket.get(ticket, []), memory_sources, limit_per_entity)
        md = _build_ticket_page(ticket, sources)
        path = TICKETS_DIR / f"ticket_{_slug(ticket)}.md"
        _write_markdown(path, md)
        built["tickets"].append(str(path))

    built["timeline"] = _build_email_timeline(email_sources)

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
    report_lines.append(f"Raw contacts: {len(raw_contacts)}")
    report_lines.append(f"Suppressed contacts: {len(suppressed_contacts)}")
    report_lines.append(f"Stale people pages removed: {removed_people_pages}")
    report_lines.append(f"People promotion threshold: {people_threshold}")
    report_lines.append(f"Include all contacts: {include_all_contacts}")
    report_lines.append(f"Projects built: {len(built['projects'])}")
    report_lines.append(f"Tickets built: {len(built['tickets'])}")
    report_lines.append(f"Timeline days built: {len(built['timeline'])}")
    report_lines.append(f"Outlook emails included: {len(email_sources)}")
    report_path = VAULT / "JamesOS" / "Reports" / "Memory V2 Report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    people_stats = {
        "promoted_people_count": len(promoted_people),
        "raw_contact_count": len(raw_contacts),
        "suppressed_contact_count": len(suppressed_contacts),
        "people_threshold": people_threshold,
        "include_all_contacts": include_all_contacts,
        "removed_people_pages": removed_people_pages,
    }
    _write_people_stats(people_stats)
    return {
        "status": "ok",
        "built": built,
        "people": people_stats,
        "report": str(report_path),
    }


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
    stats: dict[str, Any] = {}
    if PEOPLE_STATS_PATH.exists():
        try:
            stats = json.loads(PEOPLE_STATS_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            stats = {}
    promoted_count = int(
        stats.get(
            "promoted_people_count",
            sum(1 for _ in PEOPLE_DIR.glob("*.md")) if PEOPLE_DIR.exists() else 0,
        )
    )
    contacts_index_count = 0
    if CONTACTS_INDEX_PATH.exists():
        try:
            with CONTACTS_INDEX_PATH.open(encoding="utf-8") as handle:
                contacts_index_count = sum(1 for _ in handle)
        except OSError:
            contacts_index_count = 0
    suppressed_count = int(
        stats.get(
            "suppressed_contact_count",
            contacts_index_count,
        )
    )
    raw_contact_count = int(
        stats.get("raw_contact_count", promoted_count + suppressed_count)
    )
    return {
        "status": "ok",
        "promoted_people_count": promoted_count,
        "raw_contact_count": raw_contact_count,
        "suppressed_contact_count": suppressed_count,
        "paths": {
            "people": str(PEOPLE_DIR),
            "projects": str(PROJECTS_DIR),
            "tickets": str(TICKETS_DIR),
            "timeline": str(TIMELINE_DIR),
            "index": str(INDEX_DIR),
            "contacts_index": str(CONTACTS_INDEX_PATH),
        },
        "counts": {
            "people": sum(1 for _ in PEOPLE_DIR.glob("*.md")) if PEOPLE_DIR.exists() else 0,
            "projects": sum(1 for _ in PROJECTS_DIR.glob("*.md")) if PROJECTS_DIR.exists() else 0,
            "tickets": sum(1 for _ in TICKETS_DIR.glob("*.md")) if TICKETS_DIR.exists() else 0,
            "timeline": sum(1 for _ in TIMELINE_DIR.glob("*.md")) if TIMELINE_DIR.exists() else 0,
        },
    }
