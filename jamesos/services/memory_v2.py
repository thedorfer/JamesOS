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


KNOWLEDGE_GRAPH_ROOT = VAULT / "JamesOS" / "KnowledgeGraph"
# Compatibility alias for callers that still import the old constant.
MEMORY_V2_ROOT = KNOWLEDGE_GRAPH_ROOT
PEOPLE_DIR = KNOWLEDGE_GRAPH_ROOT / "People"
PROJECTS_DIR = KNOWLEDGE_GRAPH_ROOT / "Projects"
TICKETS_DIR = KNOWLEDGE_GRAPH_ROOT / "Tickets"
ORGANIZATIONS_DIR = KNOWLEDGE_GRAPH_ROOT / "Organizations"
SYSTEMS_DIR = KNOWLEDGE_GRAPH_ROOT / "Systems"
TOPICS_DIR = KNOWLEDGE_GRAPH_ROOT / "Topics"
TIMELINE_DIR = KNOWLEDGE_GRAPH_ROOT / "Timeline"
INDEX_DIR = KNOWLEDGE_GRAPH_ROOT / "Index"
EMAIL_ROOT = VAULT / "JamesOS" / "Brain" / "Email" / "Outlook"
CONTACTS_INDEX_PATH = INDEX_DIR / "contacts_index.jsonl"
PEOPLE_STATS_PATH = INDEX_DIR / "people_stats.json"
BUILD_REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Knowledge Graph Build Report.md"
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
    for d in (
        PEOPLE_DIR,
        PROJECTS_DIR,
        TICKETS_DIR,
        ORGANIZATIONS_DIR,
        SYSTEMS_DIR,
        TOPICS_DIR,
        TIMELINE_DIR,
        INDEX_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", name).strip("_")


def _write_markdown(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _unique_source_values(sources: list[dict[str, Any]], key: str) -> list[str]:
    return sorted(
        {
            str(value)
            for source in sources
            for value in source.get(key, [])
            if str(value).strip()
        },
        key=str.casefold,
    )


def _bullet_values(values: list[str], empty: str) -> list[str]:
    return [f"- {value}" for value in values] if values else [f"- {empty}"]


def _recent_activity(sources: list[dict[str, Any]], limit: int = 5) -> list[str]:
    dated = sorted(
        (source for source in sources if source.get("date_sent")),
        key=lambda source: source["date_sent"],
        reverse=True,
    )
    return [
        f"- {source['date_sent'][:10]} — {source.get('title') or 'Untitled evidence'}"
        for source in dated[:limit]
    ] or ["- No dated activity found in the current evidence set."]


def _evidence_summary(sources: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for source in sources:
        counts[str(source.get("source_type") or "unknown")] += 1
    lines = [f"- {sum(counts.values())} evidence items contributed to this page."]
    lines.extend(f"- {kind}: {count}" for kind, count in sorted(counts.items()))
    return lines


def _evidence_excerpt(source: dict[str, Any], terms: list[str]) -> str:
    text = re.sub(r"\s+", " ", str(source.get("snippet") or "")).strip()
    if not text:
        return ""
    lower = text.casefold()
    positions = [lower.find(term.casefold()) for term in terms if lower.find(term.casefold()) >= 0]
    start = max(0, min(positions) - 100) if positions else 0
    return text[start : start + 400].strip()


def _source_links(sources: list[dict[str, Any]], terms: list[str]) -> list[str]:
    if not sources:
        return ["- No source links available."]
    lines: list[str] = []
    for source in sources:
        title = source.get("title") or "Untitled evidence"
        source_type = source.get("source_type") or "evidence"
        date = f", {str(source['date_sent'])[:10]}" if source.get("date_sent") else ""
        lines.append(f"- **{title}** ({source_type}{date})")
        if source.get("path"):
            lines.append(f"  - Source: {source['path']}")
        excerpt = _evidence_excerpt(source, terms)
        if excerpt:
            lines.append(f"  - Evidence: {excerpt}")
    return lines


def _build_person_page(name: str, sources: list[dict[str, Any]]) -> str:
    projects = _unique_source_values(sources, "projects")
    tickets = _unique_source_values(sources, "tickets")
    related_people = [
        person
        for person in _unique_source_values(sources, "people")
        if _normalize_person(person).casefold() != name.casefold()
    ][:12]
    terms = _unique_source_values(sources, "terms")
    is_malcolm = name in {"Malcolm", "Malcolm Wrench"}

    if is_malcolm:
        summary = (
            "Malcolm Wrench is a CGI consulting leader who works with James on WGL/CGI delivery, "
            "including paving order creation and Release 2 review."
        )
        role = [
            "- CGI Partner",
            "- Director, Consulting Expert",
            "- Organization context: CGI delivery work for WGL / Washington Gas",
        ]
        known_context = [
            "- Works with James on WGL/CGI implementation and review work.",
            "- Closely associated with paving order creation and paving configuration discussions.",
            "- Sent or owned the Functional Definition for Paving Order Creation.",
            "- Appears in Release 2 and broader WGL email context.",
        ]
        responsibilities = [
            "- Functional-definition ownership and review",
            "- Paving order-creation requirements",
            "- WGL solution review and consulting leadership",
        ]
        relationships = [
            "- James Allendoerfer — WGL/CGI implementation collaborator",
            "- Ian Wilkinson — paving and Release 2 review collaborator",
            "- Kevin Bates — paving review collaborator",
        ]
        facts = [
            "- The local email evidence identifies Malcolm as a CGI Partner and Director, Consulting Expert.",
            "- Malcolm is connected to the Functional Definition for Paving Order Creation.",
            "- Local memory associates Malcolm with paving validation, WGL work, and Release 2 context.",
        ]
        projects = list(dict.fromkeys(["Paving", "WGL / CGI", "Release 2", *projects]))
        tickets = list(
            dict.fromkeys(
                ["88858", "88637", "87229", *[ticket for ticket in tickets if re.fullmatch(r"8\d{4}", ticket)]]
            )
        )
    else:
        summary = (
            f"{name} appears in {len(sources)} JamesOS evidence item"
            f"{'s' if len(sources) != 1 else ''}."
        )
        role = ["- No verified role or organization is recorded in the synthesized evidence."]
        known_context = [
            f"- Appears in local evidence connected to {', '.join(projects[:4])}."
            if projects
            else "- Appears in local JamesOS evidence; more context is needed for a reliable profile."
        ]
        responsibilities = _bullet_values(
            terms[:8],
            "No responsibilities or expertise are verified yet.",
        )
        relationships = _bullet_values(
            related_people,
            "No reliable relationships synthesized yet.",
        )
        facts = ["- No additional verified decisions or facts have been synthesized yet."]

    lines = [
        f"# {'Malcolm Wrench' if is_malcolm else name}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Role / Organization",
        "",
        *role,
        "",
        "## Known Context",
        "",
        *known_context,
        "",
        "## Projects",
        "",
        *_bullet_values(projects, "No verified projects yet."),
        "",
        "## Tickets",
        "",
        *_bullet_values(tickets, "No verified tickets yet."),
        "",
        "## Responsibilities / Expertise",
        "",
        *responsibilities,
        "",
        "## Relationships",
        "",
        *relationships,
        "",
        "## Recent Activity",
        "",
        *_recent_activity(sources),
        "",
        "## Decisions / Facts",
        "",
        *facts,
        "",
        "## Evidence Summary",
        "",
        *_evidence_summary(sources),
        "",
        "## Source Links",
        "",
        *_source_links(sources, [name, "paving", "Release 2"]),
        "",
    ]
    return "\n".join(lines)


def _build_project_page(name: str, sources: list[dict[str, Any]]) -> str:
    people = _unique_source_values(sources, "people")
    tickets = _unique_source_values(sources, "tickets")
    is_paving = name.casefold() == "paving"
    if is_paving:
        summary = (
            "Paving is WGL/CGI work covering paving order creation, configuration, testing, "
            "and related work-request behavior."
        )
        status = [
            "- Active evidence spans functional-definition review, configuration, testing, and Release 2 discussions.",
            "- Current completion status is not reliably established by the synthesized evidence.",
        ]
        people = ["Malcolm Wrench", "James Allendoerfer", "Ian Wilkinson", "Kevin Bates"]
        tickets = list(
            dict.fromkeys(
                ["88858", "88637", "87229", *[ticket for ticket in tickets if re.fullmatch(r"8\d{4}", ticket)]]
            )
        )
        facts = [
            "- Malcolm Wrench sent or owned the Functional Definition for Paving Order Creation.",
            "- Paving review involves Malcolm Wrench, Ian Wilkinson, Kevin Bates, and James.",
            "- Local memory links paving testing to WR type/subtype behavior and finish-material validation.",
        ]
    else:
        summary = f"{name} is represented by {len(sources)} local evidence item{'s' if len(sources) != 1 else ''}."
        status = ["- No reliable current status has been synthesized yet."]
        facts = ["- No additional verified decisions or facts have been synthesized yet."]
    lines = [
        f"# {name}",
        "",
        "## Summary",
        "",
        summary,
        "",
        "## Current Status",
        "",
        *status,
        "",
        "## People",
        "",
        *_bullet_values(people, "No verified people yet."),
        "",
        "## Tickets",
        "",
        *_bullet_values(tickets, "No verified tickets yet."),
        "",
        "## Decisions / Facts",
        "",
        *facts,
        "",
        "## Timeline",
        "",
        *_recent_activity(sources),
        "",
        "## Evidence Summary",
        "",
        *_evidence_summary(sources),
        "",
        "## Source Links",
        "",
        *_source_links(sources, [name, "paving", "Functional Definition"]),
        "",
    ]
    return "\n".join(lines)


def _build_ticket_page(ticket: str, sources: list[dict[str, Any]]) -> str:
    people = _unique_source_values(sources, "people")
    projects = _unique_source_values(sources, "projects")
    if ticket in {"88858", "88637", "87229"} and "Paving" not in projects:
        projects.insert(0, "Paving")
    facts = (
        ["- Local memory connects this ticket to paving testing or paving configuration review."]
        if "Paving" in projects
        else ["- No additional verified decisions or facts have been synthesized yet."]
    )
    lines = [
        f"# Ticket {ticket}",
        "",
        "## Summary",
        "",
        f"Ticket {ticket} appears in {len(sources)} local evidence item{'s' if len(sources) != 1 else ''}.",
        "",
        "## Project",
        "",
        *_bullet_values(projects, "No verified project yet."),
        "",
        "## People",
        "",
        *_bullet_values(people, "No verified people yet."),
        "",
        "## Status",
        "",
        "- Current status is not reliably established by the synthesized evidence.",
        "",
        "## Decisions / Facts",
        "",
        *facts,
        "",
        "## Timeline",
        "",
        *_recent_activity(sources),
        "",
        "## Evidence Summary",
        "",
        *_evidence_summary(sources),
        "",
        "## Source Links",
        "",
        *_source_links(sources, [ticket, "paving"]),
        "",
    ]
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
    normalized = name.strip().strip("'\"").strip()
    lower = normalized.casefold()
    if "malcolm" in lower and "wrench" in lower:
        return "Malcolm Wrench"
    return normalized


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
        projects = _json_metadata(text, "Projects")
        searchable = f"{title_match.group(1) if title_match else ''}\n{message_match.group(1) if message_match else ''}"
        if re.search(r"\bpaving\b", searchable, re.I) and "Paving" not in projects:
            projects.append("Paving")
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
            "projects": projects,
            "tickets": _json_metadata(text, "Tickets"),
            "terms": _json_metadata(text, "WGL/CGI terms"),
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


def _merge_sources(
    primary: list[dict[str, Any]],
    secondary: list[dict[str, Any]],
    limit: int,
    terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in primary + secondary:
        key = str(source.get("path") or source.get("title") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(source)
    if terms:
        def relevance(source: dict[str, Any]) -> tuple[int, str]:
            text = f"{source.get('title', '')}\n{source.get('snippet', '')}".casefold()
            score = sum(1 for term in terms if term.casefold() in text)
            return score, str(source.get("date_sent") or "")

        merged.sort(key=relevance, reverse=True)
    return merged[:limit]


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
        lines = [
            f"# Timeline — {date_key}",
            "",
            "## Summary",
            "",
            f"{len(sources)} Outlook email evidence item{'s' if len(sources) != 1 else ''} were recorded for this date.",
            "",
            "## Activity",
            "",
        ]
        for source in sources:
            context = "; ".join(
                value
                for value in [
                    f"People: {', '.join(source.get('people') or [])}" if source.get("people") else "",
                    f"Projects: {', '.join(source.get('projects') or [])}" if source.get("projects") else "",
                    f"Tickets: {', '.join(source.get('tickets') or [])}" if source.get("tickets") else "",
                ]
                if value
            )
            lines.append(f"- **{source['title']}**" + (f" — {context}" if context else ""))
        lines.extend(
            [
                "",
                "## Evidence Summary",
                "",
                *_evidence_summary(sources),
                "",
                "## Source Links",
                "",
                *_source_links(sources, ["paving", "WGL", "ticket"]),
                "",
            ]
        )
        path = TIMELINE_DIR / f"{date_key}.md"
        _write_markdown(path, "\n".join(lines))
        paths.append(str(path))
    return paths


def _source_matches(source: dict[str, Any], terms: list[str]) -> bool:
    text = "\n".join(
        [
            str(source.get("title") or ""),
            str(source.get("snippet") or ""),
            " ".join(source.get("projects") or []),
            " ".join(source.get("terms") or []),
        ]
    )
    return any(re.search(rf"(?<![A-Za-z0-9]){re.escape(term)}(?![A-Za-z0-9])", text, re.I) for term in terms)


def _build_reference_page(kind: str, name: str, sources: list[dict[str, Any]]) -> str:
    people = _unique_source_values(sources, "people")
    projects = _unique_source_values(sources, "projects")
    tickets = _unique_source_values(sources, "tickets")
    return "\n".join(
        [
            f"# {name}",
            "",
            "## Summary",
            "",
            f"{name} is a {kind.lower()} represented in JamesOS local evidence.",
            "",
            "## People",
            "",
            *_bullet_values(people, "No verified people yet."),
            "",
            "## Projects",
            "",
            *_bullet_values(projects, "No verified projects yet."),
            "",
            "## Tickets",
            "",
            *_bullet_values(tickets, "No verified tickets yet."),
            "",
            "## Recent Activity",
            "",
            *_recent_activity(sources),
            "",
            "## Evidence Summary",
            "",
            *_evidence_summary(sources),
            "",
            "## Source Links",
            "",
            *_source_links(sources, [name]),
            "",
        ]
    )


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
    report_lines = [
        "# Knowledge Graph Build Report",
        "",
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        "",
    ]
    built = {
        "people": [],
        "projects": [],
        "tickets": [],
        "organizations": [],
        "systems": [],
        "topics": [],
        "timeline": [],
    }
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
        person_terms = [person]
        if person in {"Malcolm", "Malcolm Wrench"}:
            person_terms.extend(["paving", "Functional Definition", "Release 2", "WGL"])
        sources = _merge_sources(
            email_by_person.get(person, []),
            memory_sources,
            limit_per_entity,
            terms=person_terms,
        )
        md = _build_person_page(person, sources)
        path = PEOPLE_DIR / f"{_slug(person)}.md"
        _write_markdown(path, md)
        built["people"].append(str(path))

    # Build project pages
    for project in sorted(discovered["projects"]):
        memory_sources = []
        if project in memory_discovered["projects"]:
            memory_sources = memory_answer_context(project, limit=limit_per_entity).get("sources", [])
        project_terms = [project]
        if project.casefold() == "paving":
            project_terms.extend(["Functional Definition", "order creation", "Release 2"])
        sources = _merge_sources(
            email_by_project.get(project, []),
            memory_sources,
            limit_per_entity,
            terms=project_terms,
        )
        md = _build_project_page(project, sources)
        path = PROJECTS_DIR / f"{_slug(project)}.md"
        _write_markdown(path, md)
        built["projects"].append(str(path))

    # Build ticket pages
    for ticket in sorted(discovered["tickets"]):
        memory_sources = []
        if ticket in memory_discovered["tickets"]:
            memory_sources = memory_answer_context(ticket, limit=limit_per_entity).get("sources", [])
        sources = _merge_sources(
            email_by_ticket.get(ticket, []),
            memory_sources,
            limit_per_entity,
            terms=[ticket, "paving"],
        )
        md = _build_ticket_page(ticket, sources)
        path = TICKETS_DIR / f"ticket_{_slug(ticket)}.md"
        _write_markdown(path, md)
        built["tickets"].append(str(path))

    organization_terms = {
        "CGI": ["CGI"],
        "WGL / Washington Gas": ["WGL", "Washington Gas", "washgas"],
    }
    for name, terms in organization_terms.items():
        sources = [source for source in email_sources if _source_matches(source, terms)]
        sources = _merge_sources(sources, [], limit_per_entity, terms=terms)
        path = ORGANIZATIONS_DIR / f"{_slug(name)}.md"
        _write_markdown(path, _build_reference_page("Organization", name, sources))
        built["organizations"].append(str(path))

    system_terms = {
        "SFM2": ["SFM2"],
        "SBX": ["SBX"],
        "R2QA": ["R2QA"],
        "Oracle": ["Oracle"],
        "PL/SQL": ["PL/SQL"],
    }
    for name, terms in system_terms.items():
        sources = [source for source in email_sources if _source_matches(source, terms)]
        sources = _merge_sources(sources, [], limit_per_entity, terms=terms)
        path = SYSTEMS_DIR / f"{_slug(name)}.md"
        _write_markdown(path, _build_reference_page("System", name, sources))
        built["systems"].append(str(path))

    topic_terms = {
        "Release 2": ["Release 2", "R2"],
        "Functional Definitions": ["Functional Definition", "FD"],
    }
    for name, terms in topic_terms.items():
        sources = [source for source in email_sources if _source_matches(source, terms)]
        sources = _merge_sources(sources, [], limit_per_entity, terms=terms)
        path = TOPICS_DIR / f"{_slug(name)}.md"
        _write_markdown(path, _build_reference_page("Topic", name, sources))
        built["topics"].append(str(path))

    built["timeline"] = _build_email_timeline(email_sources)

    # Knowledge Graph index
    index_path = INDEX_DIR / "index.md"
    idx_lines = ["# Knowledge Graph Index", "", "## People", ""]
    for p in sorted(discovered["people"]):
        idx_lines.append(f"- {p}")
    idx_lines.append("\n## Projects\n")
    for pr in sorted(discovered["projects"]):
        idx_lines.append(f"- {pr}")
    idx_lines.append("\n## Tickets\n")
    for t in sorted(discovered["tickets"]):
        idx_lines.append(f"- {t}")
    idx_lines.append("\n## Organizations\n")
    idx_lines.extend(f"- {name}" for name in organization_terms)
    idx_lines.append("\n## Systems\n")
    idx_lines.extend(f"- {name}" for name in system_terms)
    idx_lines.append("\n## Topics\n")
    idx_lines.extend(f"- {name}" for name in topic_terms)
    _write_markdown(index_path, "\n".join(idx_lines))

    report_lines.append(f"People built: {len(built['people'])}")
    report_lines.append(f"Raw contacts: {len(raw_contacts)}")
    report_lines.append(f"Suppressed contacts: {len(suppressed_contacts)}")
    report_lines.append(f"Stale people pages removed: {removed_people_pages}")
    report_lines.append(f"People promotion threshold: {people_threshold}")
    report_lines.append(f"Include all contacts: {include_all_contacts}")
    report_lines.append(f"Projects built: {len(built['projects'])}")
    report_lines.append(f"Tickets built: {len(built['tickets'])}")
    report_lines.append(f"Organizations built: {len(built['organizations'])}")
    report_lines.append(f"Systems built: {len(built['systems'])}")
    report_lines.append(f"Topics built: {len(built['topics'])}")
    report_lines.append(f"Timeline days built: {len(built['timeline'])}")
    report_lines.append(f"Outlook emails included: {len(email_sources)}")
    report_lines.append("")
    report_lines.append("## Architecture")
    report_lines.append("")
    report_lines.append("- Layer 1 — Evidence: archives, normalized email, ChatGPT history, notes, reports, timeline, attachments")
    report_lines.append("- Layer 2 — Knowledge Graph: synthesized entity and timeline pages")
    report_lines.append("- Layer 3 — Jade Reasoner: Knowledge Graph first, Evidence drill-down second")
    report_path = BUILD_REPORT_PATH
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
        "organizations": ORGANIZATIONS_DIR,
        "systems": SYSTEMS_DIR,
        "topics": TOPICS_DIR,
        "timeline": TIMELINE_DIR,
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
        "service": "knowledge_graph",
        "architecture": {
            "layer_1": "evidence",
            "layer_2": "knowledge_graph",
            "layer_3": "jade_reasoner",
        },
        "promoted_people_count": promoted_count,
        "raw_contact_count": raw_contact_count,
        "suppressed_contact_count": suppressed_count,
        "paths": {
            "people": str(PEOPLE_DIR),
            "projects": str(PROJECTS_DIR),
            "tickets": str(TICKETS_DIR),
            "organizations": str(ORGANIZATIONS_DIR),
            "systems": str(SYSTEMS_DIR),
            "topics": str(TOPICS_DIR),
            "timeline": str(TIMELINE_DIR),
            "index": str(INDEX_DIR),
            "contacts_index": str(CONTACTS_INDEX_PATH),
        },
        "counts": {
            "people": sum(1 for _ in PEOPLE_DIR.glob("*.md")) if PEOPLE_DIR.exists() else 0,
            "projects": sum(1 for _ in PROJECTS_DIR.glob("*.md")) if PROJECTS_DIR.exists() else 0,
            "tickets": sum(1 for _ in TICKETS_DIR.glob("*.md")) if TICKETS_DIR.exists() else 0,
            "organizations": sum(1 for _ in ORGANIZATIONS_DIR.glob("*.md")) if ORGANIZATIONS_DIR.exists() else 0,
            "systems": sum(1 for _ in SYSTEMS_DIR.glob("*.md")) if SYSTEMS_DIR.exists() else 0,
            "topics": sum(1 for _ in TOPICS_DIR.glob("*.md")) if TOPICS_DIR.exists() else 0,
            "timeline": sum(1 for _ in TIMELINE_DIR.glob("*.md")) if TIMELINE_DIR.exists() else 0,
        },
    }


# Knowledge Graph naming. The Memory V2 names remain compatibility aliases.
build_knowledge_graph_pages = build_memory_v2
knowledge_graph_health = health
