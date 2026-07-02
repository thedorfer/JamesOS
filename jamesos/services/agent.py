import json
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.rich_context import build_rich_context
from jamesos.services.context_engine import build_context_report
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.tool_router import detect_tool, route_tool
from jamesos.services.memory_service import remember
from jamesos.services.personality import jade_personality_prompt


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
    if any(w in q for w in ["file", "pdf", "docx", "document", "upload", "uploaded", "attachment"]):
        return "file"
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
        prompt = jade_personality_prompt() + f"""

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


def handle_jade_message(message: str, use_ai: bool = True) -> dict:
    text = message.strip()
    lower = text.lower()

    if lower.startswith(("remember ", "remember that ")):
        memory_text = text
        for prefix in ["remember that ", "remember "]:
            if lower.startswith(prefix):
                memory_text = text[len(prefix):].strip()
                break

        item = remember(memory_text, source="jade_chat", importance="normal")
        return {
            "question": message,
            "answer": f"Remembered: {memory_text}",
            "action": "memory",
            "memory": item,
        }

    if lower.startswith(("take a note ", "note ", "capture ")):
        from jamesos.core.queue import enqueue_job

        note_text = text
        for prefix in ["take a note ", "note ", "capture "]:
            if lower.startswith(prefix):
                note_text = text[len(prefix):].strip()
                break

        result = enqueue_job("intake", {
            "title": "Jade Note",
            "content": note_text,
            "source": "jade_chat",
            "source_detail": "single_box",
        })

        return {
            "question": message,
            "answer": f"Saved note: {note_text}",
            "action": "note",
            "result": result,
        }

    tool = detect_tool(text)
    if tool != "local":
        result = route_tool(text)
        answer = result.get("result", "")

        if result.get("tool") == "web_search" and use_ai and ollama_enabled():
            prompt = (
                "Summarize these web search results for James. "
                "Be concise, practical, and include useful links when present.\n\n"
                f"Question: {message}\n\n"
                f"Results:\n{answer[:8000]}"
            )
            answer = ask_ollama(prompt)

        _maybe_store_conversation_memory(message, answer, "tool")
        return {
            "question": message,
            "answer": answer,
            "action": "tool",
            "tool": result.get("tool"),
            "tool_result": result,
        }

    result = ask_agent(message, use_ai=use_ai)
    result["action"] = "agent"
    _maybe_store_conversation_memory(message, result.get("answer", ""), "agent")
    return result


def _maybe_store_conversation_memory(question: str, answer: str, action: str) -> None:
    lower = question.lower()

    important = (
        action in {"memory", "note"}
        or lower.startswith(("remember", "note", "take a note", "capture"))
        or any(word in lower for word in ["kevin", "malcolm", "tom", "gcu", "ticket", "paving", "important"])
    )

    if not important:
        return

    try:
        remember(
            f"Q: {question}\n\nA: {answer[:2000]}",
            source="jade_auto_memory",
            importance="normal",
        )
    except Exception:
        pass
