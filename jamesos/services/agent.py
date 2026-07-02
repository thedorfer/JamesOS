import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.rich_context import build_rich_context
from jamesos.services.context_engine import build_context_report
from jamesos.services.ollama_service import ask_ollama, ollama_enabled


@dataclass
class JamesOSContext:
    query: str
    intent: str
    generated_at: str
    people: list[str]
    tickets: list[str]
    concepts: list[str]
    files: list[str]
    context_text: str


def detect_intent(question: str) -> str:
    q = question.lower()

    if any(w in q for w in ["today", "tomorrow", "calendar", "meeting", "schedule"]):
        return "calendar"
    if any(w in q for w in ["kevin", "malcolm", "tom", "julia", "person", "who is"]):
        return "person"
    if any(w in q for w in ["ticket", "bug", "88858", "work", "paving", "wgl"]):
        return "work"
    if any(w in q for w in ["email", "gmail", "gcu", "student", "grade"]):
        return "email"
    if any(w in q for w in ["trip", "flight", "hotel", "travel"]):
        return "travel"

    return "general"


def clean_query(question: str) -> str:
    q = question.strip()
    lower = q.lower()

    prefixes = [
        "what do you know about ",
        "tell me about ",
        "summarize ",
        "what is ",
        "who is ",
        "show me ",
        "find ",
    ]

    for prefix in prefixes:
        if lower.startswith(prefix):
            q = q[len(prefix):].strip()
            break

    return q.rstrip(" ?.") or question


def build_structured_context(question: str) -> JamesOSContext:
    query = clean_query(question)
    intent = detect_intent(question)

    build_context_report(query, use_ai=False)
    rich = build_rich_context(query, limit=15, chars_per_file=1600)

    people = []
    tickets = []
    concepts = []
    files = []

    for line in rich.splitlines():
        if line.startswith("## [["):
            files.append(line.replace("## [[", "").replace("]]", "").strip())
        if "Kevin" in line and "Kevin" not in people:
            people.append("Kevin")
        if "Malcolm" in line and "Malcolm" not in people:
            people.append("Malcolm")
        if "GCU" in line and "GCU" not in concepts:
            concepts.append("GCU")
        if "Travel" in line and "Travel" not in concepts:
            concepts.append("Travel")
        if "Paving" in line and "Paving" not in concepts:
            concepts.append("Paving")

    import re
    for ticket in sorted(set(re.findall(r"\b\d{5}\b", rich))):
        tickets.append(ticket)

    return JamesOSContext(
        query=query,
        intent=intent,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
        people=people,
        tickets=tickets[:20],
        concepts=concepts,
        files=files[:20],
        context_text=rich,
    )


def ask_agent(question: str, use_ai: bool = True) -> dict:
    ctx = build_structured_context(question)

    if use_ai and ollama_enabled():
        prompt = f"""You are JamesOS, James's private assistant.

Answer using only this structured context.
Be concise, practical, and action-oriented.
If something is missing, say what is missing.

Question:
{question}

Intent:
{ctx.intent}

People:
{ctx.people}

Tickets:
{ctx.tickets}

Concepts:
{ctx.concepts}

Files:
{ctx.files}

Context:
{ctx.context_text[:14000]}
"""
        answer = ask_ollama(prompt)
    else:
        answer = ctx.context_text[:5000]

    return {
        "question": question,
        "answer": answer,
        "context": asdict(ctx),
    }


def write_agent_report(question: str) -> str:
    result = ask_agent(question, use_ai=True)

    reports = VAULT / "JamesOS" / "Reports" / "Agent"
    reports.mkdir(parents=True, exist_ok=True)

    safe = "".join(c if c.isalnum() or c in " -_" else "-" for c in question)[:80]
    path = reports / f"{safe}.md"

    ctx = result["context"]

    lines = [
        f"# Agent Report: {question}",
        "",
        f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        f"Intent: {ctx['intent']}",
        f"Retrieval Query: {ctx['query']}",
        "",
        "## Answer",
        "",
        result["answer"],
        "",
        "## Structured Context",
        "",
        "### People",
    ]

    lines.extend([f"- {p}" for p in ctx["people"]] or ["- None"])
    lines.extend(["", "### Tickets"])
    lines.extend([f"- {t}" for t in ctx["tickets"]] or ["- None"])
    lines.extend(["", "### Concepts"])
    lines.extend([f"- {c}" for c in ctx["concepts"]] or ["- None"])
    lines.extend(["", "### Files"])
    lines.extend([f"- [[{f}]]" for f in ctx["files"]] or ["- None"])

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return f"Wrote agent report: {path.relative_to(VAULT)}"
