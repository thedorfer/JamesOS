from pathlib import Path
import re

from jamesos.config import VAULT
from jamesos.services.agent import ask_agent, handle_jade_message
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.tool_router import detect_tool, route_tool
from jamesos.services.memory_service import search_memory


FILES_ROOT = VAULT / "JamesOS" / "Knowledge" / "Files"


STOPWORDS = {
    "what", "is", "in", "the", "a", "an", "i", "me", "my", "uploaded",
    "upload", "file", "pdf", "doc", "docx", "document", "about", "tell",
    "show", "summarize", "did", "we", "talk", "yesterday"
}


def _keywords(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z0-9_'-]+", text.lower())
    return [w for w in words if len(w) > 2 and w not in STOPWORDS]


def _search_file_knowledge(question: str, limit: int = 5) -> str:
    if not FILES_ROOT.exists():
        return ""

    terms = _keywords(question)
    matches = []

    for path in FILES_ROOT.rglob("*.md"):
        body = path.read_text(encoding="utf-8", errors="ignore")
        lower = body.lower()
        title = path.stem.lower()

        score = 0
        for term in terms:
            if term in title:
                score += 30
            score += lower.count(term) * 3

        if not terms and any(w in question.lower() for w in ["uploaded", "file", "pdf", "document"]):
            score += 1

        if score:
            matches.append((score, path.stat().st_mtime, path, body))

    matches.sort(key=lambda x: (x[0], x[1]), reverse=True)

    if not matches:
        recent = sorted(FILES_ROOT.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]
        matches = [(1, p.stat().st_mtime, p, p.read_text(encoding="utf-8", errors="ignore")) for p in recent]

    lines = ["# Uploaded File Context", ""]
    for score, _mtime, path, body in matches[:limit]:
        rel = path.relative_to(VAULT).with_suffix("").as_posix()
        lines.extend([
            f"## [[{rel}]]",
            f"Score: {score}",
            "",
            body[:8000],
            "",
            "---",
            "",
        ])

    return "\n".join(lines)


def _summarize(question: str, context: str) -> str:
    if ollama_enabled():
        prompt = (
            "You are Jade, James's private assistant. "
            "Answer using only the context below. Be concise, useful, and direct. "
            "If the answer is not in the context, say what is missing.\n\n"
            f"Question: {question}\n\n"
            f"Context:\n{context[:14000]}"
        )
        return ask_ollama(prompt)

    return context[:5000]


def answer_with_planner(question: str, use_ai: bool = True) -> dict:
    q = question.lower().strip()

    if q.startswith(("remember ", "remember that ", "take a note ", "note ", "capture ")):
        return handle_jade_message(question, use_ai=use_ai)

    if any(w in q for w in ["uploaded", "file", "pdf", "docx", "document", "attachment"]):
        context = _search_file_knowledge(question)
        answer = _summarize(question, context) if use_ai else context
        return {
            "question": question,
            "answer": answer,
            "action": "file_qa",
            "planner": ["file_knowledge"],
        }

    tool = detect_tool(question)
    if tool != "local":
        result = route_tool(question)
        raw = result.get("result", "")

        if tool == "web_search" and use_ai and ollama_enabled():
            answer = _summarize(question, raw)
        else:
            answer = raw

        return {
            "question": question,
            "answer": answer,
            "action": "tool",
            "tool": tool,
            "tool_result": result,
            "planner": [tool],
        }

    memories = search_memory(question, limit=5)
    memory_context = "\n\n".join(m["text"] for m in memories)

    result = ask_agent(question, use_ai=use_ai)

    if memory_context and use_ai and ollama_enabled():
        context = f"# Memory Context\n\n{memory_context}\n\n# Agent Answer\n\n{result.get('answer', '')}"
        result["answer"] = _summarize(question, context)
        result["planner"] = ["memory", "agent"]
    else:
        result["planner"] = ["agent"]

    result["action"] = "planned_agent"
    return result
