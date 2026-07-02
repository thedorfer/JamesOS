from __future__ import annotations

import re
from collections import Counter
from typing import Any

from jamesos.services.knowledge_db import (
    add_signal,
    export_obsidian_reports,
    init_db,
    knowledge_status,
    search_documents,
    top_rows,
    upsert_document,
    upsert_named,
    upsert_source,
)

PROJECT_PATTERNS = {
    "Paving": r"\bpaving\b|\bPWO\b|WR Type|finish material|cut type",
    "FERC": r"\bFERC\b|RU/UA|accounting|CU_ACCOUNTING",
    "UOM": r"\bUOM\b|unit of measure|SAP UOM",
    "CPMP": r"\bCPMP\b|corrosion|facility association",
    "Capital Work Order": r"Capital Work|PowerPlan|MSG_WR_UPDATE|MSG_WR_DETAILS",
    "JamesOS": r"JamesOS|Jade|Flutter|knowledge graph|reasoner",
    "GCU": r"\bGCU\b|Halo|grading|rubric|student|assignment|announcement|discussion",
}

TOPIC_PATTERNS = {
    "Deployment": r"deploy|deployment|SFM2|SBX|R2QA|restart|compile|package",
    "Oracle": r"Oracle|PL/SQL|procedure|table|schema|SQL|ORA-",
    "Testing": r"test|testing|tester|ready to test|validation",
    "GCU": r"GCU|student|grading|rubric|assignment|announcement",
    "Family": r"family|wife|daughter|kids|school|camp|birthday",
}

TICKET_RE = re.compile(r"\b\d{5}\b")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def _detect_projects(text: str) -> list[str]:
    return [name for name, pattern in PROJECT_PATTERNS.items() if re.search(pattern, text, re.I)]


def _detect_topics(text: str) -> list[str]:
    topics = [name for name, pattern in TOPIC_PATTERNS.items() if re.search(pattern, text, re.I)]
    for ticket in TICKET_RE.findall(text):
        topics.append(f"Ticket {ticket}")
    return sorted(set(topics))


def _importance(text: str) -> float:
    score = 1.0
    hot_words = ["urgent", "blocker", "blocked", "waiting", "deadline", "due", "today", "tomorrow", "deploy", "production", "failed", "error"]
    lowered = text.lower()
    score += sum(1.5 for word in hot_words if word in lowered)
    score += min(len(TICKET_RE.findall(text)) * 0.7, 4)
    return min(score, 10.0)


def seed_knowledge_foundation() -> dict[str, Any]:
    init_db()
    source_id = upsert_source("system", "jamesos_seed", "JamesOS Seed Knowledge")

    seed_docs = [
        {
            "external_id": "seed:jamesos2",
            "doc_type": "system_note",
            "title": "JamesOS 2.0 Knowledge Engine",
            "body": "JamesOS 2.0 uses SQLite as the structured Knowledge Engine while Obsidian remains the human notebook and report surface.",
            "snippet": "SQLite powers Jade's structured knowledge. Obsidian remains the notebook.",
        },
        {
            "external_id": "seed:trust_hierarchy",
            "doc_type": "system_note",
            "title": "Jade Trust Hierarchy",
            "body": "Trust order: World Model, Knowledge DB, generated reports, memory, graph, LLM reasoning. Verified facts override stale search results.",
            "snippet": "World Model and Knowledge DB override stale search.",
        },
    ]

    for doc in seed_docs:
        doc["source_id"] = source_id
        upsert_document(doc)

    for name in ["JamesOS", "Jade", "Knowledge Engine"]:
        upsert_named("projects", name, importance=8)
    for name in ["SQLite", "Obsidian", "Flutter", "Gmail", "CGI Email"]:
        upsert_named("topics", name, importance=6)
    for name in ["James Allendoerfer"]:
        upsert_named("people", name, importance=10, confidence="verified")

    add_signal(
        "milestone",
        "JamesOS 2.0 Knowledge Engine initialized",
        "SQLite knowledge.db is now the structured brain while Obsidian remains the human-readable notebook layer.",
        score=9.5,
        mode="jamesos",
        source={"source": "seed"},
    )

    export_obsidian_reports()
    return knowledge_status()


def ingest_text_document(
    *,
    source_type: str,
    source_key: str,
    external_id: str,
    title: str,
    body: str,
    doc_type: str = "document",
    author: str | None = None,
    author_email: str | None = None,
    created_at: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    init_db()
    source_id = upsert_source(source_type, source_key, source_key)
    text = f"{title}\n{body}"
    doc_id = upsert_document(
        {
            "source_id": source_id,
            "external_id": external_id,
            "doc_type": doc_type,
            "title": title,
            "body": body,
            "snippet": body[:300],
            "author": author,
            "author_email": author_email,
            "created_at": created_at,
            "metadata": metadata or {},
        }
    )

    detected_projects = _detect_projects(text)
    detected_topics = _detect_topics(text)
    importance = _importance(text)

    for project in detected_projects:
        upsert_named("projects", project, importance=importance, metadata={"source_document_id": doc_id})
    for topic in detected_topics:
        upsert_named("topics", topic, importance=importance, metadata={"source_document_id": doc_id})

    for email in EMAIL_RE.findall(text):
        name = email.split("@")[0].replace(".", " ").replace("_", " ").title()
        upsert_named("people", name, primary_email=email.lower(), domain=email.split("@")[-1].lower(), importance=importance)

    if importance >= 7:
        add_signal(
            "document_importance",
            title[:120],
            body[:500],
            score=importance,
            mode="personal",
            source={"document_id": doc_id, "doc_type": doc_type},
        )

    export_obsidian_reports()
    return {
        "document_id": doc_id,
        "projects": detected_projects,
        "topics": detected_topics,
        "importance": importance,
    }


def knowledge_dashboard(mode: str = "personal") -> dict[str, Any]:
    init_db()
    signals = [s for s in top_rows("signals", 20) if s.get("mode") in {mode, "personal", "jamesos"}]
    people = top_rows("people", 8)
    projects = top_rows("projects", 8)

    cards = []
    for signal in signals[:3]:
        cards.append({
            "title": signal["title"],
            "body": signal.get("body") or "",
            "kind": "signal",
            "prompt": f"Tell me more about this signal: {signal['title']}",
        })

    if projects:
        cards.append({
            "title": "Active knowledge projects",
            "body": ", ".join(row["name"] for row in projects[:5]),
            "kind": "knowledge",
            "prompt": "Summarize my active projects from the Knowledge Engine.",
        })

    if people:
        cards.append({
            "title": "Important people",
            "body": ", ".join(row["name"] for row in people[:5]),
            "kind": "knowledge",
            "prompt": "Summarize the important people in my Knowledge Engine.",
        })

    return {"status": "ok", "mode": mode, "cards": cards, "knowledge": knowledge_status()}


def knowledge_search(query: str, limit: int = 10) -> dict[str, Any]:
    return {"status": "ok", "query": query, "results": search_documents(query, limit=limit)}


def build_all_knowledge() -> dict[str, Any]:
    status = seed_knowledge_foundation()
    report = export_obsidian_reports()
    return {"status": status, "report": report}
