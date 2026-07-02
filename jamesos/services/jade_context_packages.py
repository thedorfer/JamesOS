from __future__ import annotations

from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.memory_service import search_memory
from jamesos.services.knowledge_graph import graph_lookup


VALID_MODES = {"personal", "work", "gcu", "family", "jamesos"}


def normalize_mode(mode: str | None) -> str:
    value = (mode or "personal").strip().lower().replace(" ", "")
    if value in {"james_os", "james-os", "jamesos"}:
        return "jamesos"
    if value not in VALID_MODES:
        return "personal"
    return value


def mode_label(mode: str | None) -> str:
    mode = normalize_mode(mode)
    return {
        "personal": "Personal",
        "work": "Work",
        "gcu": "GCU",
        "family": "Family",
        "jamesos": "JamesOS",
    }[mode]


def mode_query(mode: str | None) -> str:
    mode = normalize_mode(mode)
    return {
        "personal": "James priorities today family work GCU JamesOS calendar reminders",
        "work": "WGL work tickets paving Kevin Malcolm Tom Ian deployment SFM2 SBX blockers",
        "gcu": "GCU teaching grading students announcements assignments due dates CST SYM DSC",
        "family": "family schedule school birthday kids wife personal reminders appointments",
        "jamesos": "JamesOS Flutter Jade backend git deploy knowledge graph memory reasoner API",
    }[mode]


def mode_directive(mode: str | None) -> str:
    mode = normalize_mode(mode)
    return {
        "personal": "Prioritize James's most useful personal-assistant context across work, GCU, family, JamesOS, calendar, and memory.",
        "work": "Prioritize WGL work, tickets, deployments, blockers, Oracle/PLSQL, SFM2/SBX/R2QA, and people such as Kevin, Malcolm, Tom, Ian, and Elias.",
        "gcu": "Prioritize teaching work, grading, announcements, students, courses, assignments, and instructor-ready wording.",
        "family": "Prioritize family logistics, school, birthdays, appointments, trips, home, reminders, and practical next steps.",
        "jamesos": "Prioritize JamesOS architecture, Flutter Jade app, backend API, git/deploy workflow, services, memory, knowledge graph, and next coding tasks.",
    }[mode]


def _read(path: Path, limit: int = 1800) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:limit]


def _report(name: str, limit: int = 1800) -> str:
    return _read(VAULT / "JamesOS" / "Reports" / f"{name}.md", limit=limit)


def build_context_package(question: str, mode: str | None = None) -> str:
    mode = normalize_mode(mode)
    query = mode_query(mode)

    reports = {
        "personal": ["Daily Briefing", "Proactive Assistant", "People"],
        "work": ["Work Intelligence", "Proactive Assistant", "People"],
        "gcu": ["Daily Briefing", "Proactive Assistant"],
        "family": ["Daily Briefing", "People", "Proactive Assistant"],
        "jamesos": ["Knowledge Graph", "Proactive Assistant", "Daily Briefing"],
    }[mode]

    sections: list[str] = [
        f"# Jade Context Package: {mode_label(mode)}",
        "",
        "Use this as background context only. Do not summarize the raw context, JSON, nodes, or graph structure unless James asks for that specifically.",
        "Answer James directly and bring the most useful facts or next actions up front.",
        "",
        f"Mode directive: {mode_directive(mode)}",
        "",
        f"James asked: {question}",
        "",
    ]

    memory = search_memory(query, limit=8)
    if memory:
        sections.extend(["## Relevant memory", str(memory)[:3000], ""])

    for report in reports:
        text = _report(report, limit=2200)
        if text:
            sections.extend([f"## {report}", text, ""])

    graph_terms = {
        "work": ["Kevin", "Malcolm", "Tom", "Paving", "88858"],
        "gcu": ["GCU", "CST", "SYM", "DSC"],
        "family": ["Jidapa", "Family", "School"],
        "jamesos": ["JamesOS", "Jade", "Flutter"],
        "personal": ["James", "Jade", "Work", "GCU", "Family"],
    }[mode]

    graph_lines = []
    for term in graph_terms:
        found = graph_lookup(term, limit=5)
        nodes = found.get("nodes", []) if isinstance(found, dict) else []
        if nodes:
            graph_lines.append(f"{term}: {len(nodes)} related items")

    if graph_lines:
        sections.extend(["## Knowledge graph summary", "\n".join(graph_lines), ""])

    return "\n".join(sections)[:12000]


def mode_brief_prompt(mode: str | None = None) -> str:
    return (
        f"Give James a concise {mode_label(mode)} mode briefing. "
        "Use the context package as background. Prioritize live/useful items and next actions. "
        "Do not mention raw JSON, graph nodes, or implementation details."
    )


def _card(title: str, body: str, kind: str = "info", prompt: str | None = None) -> dict:
    return {"title": title, "body": body, "kind": kind, "prompt": prompt or title}


def dashboard_cards(mode: str | None = None) -> dict:
    mode = normalize_mode(mode)
    label = mode_label(mode)
    query = mode_query(mode)

    cards: list[dict] = []
    cards.append(_card(
        f"{label} mode is active",
        mode_directive(mode),
        "mode",
        mode_brief_prompt(mode),
    ))

    # These are live-ish cards: generated from current reports/memory each time the app opens.
    memory = str(search_memory(query, limit=3) or "").strip()
    if memory:
        compact = " ".join(memory.split())[:180]
        cards.append(_card("Recent memory", compact, "memory", mode_brief_prompt(mode)))

    report_name = {
        "personal": "Daily Briefing",
        "work": "Work Intelligence",
        "gcu": "Daily Briefing",
        "family": "Daily Briefing",
        "jamesos": "Knowledge Graph",
    }[mode]
    report = _report(report_name, limit=500)
    if report:
        compact = " ".join(report.split())[:180]
        cards.append(_card(report_name, compact, "report", mode_brief_prompt(mode)))

    cards.append(_card(
        "Brief me",
        f"Ask Jade for the highest-value {label} priorities right now.",
        "action",
        mode_brief_prompt(mode),
    ))

    return {
        "status": "ok",
        "mode": mode,
        "mode_label": label,
        "cards": cards[:5],
    }
