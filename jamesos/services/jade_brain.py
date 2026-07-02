import json
import re
from datetime import datetime, date, timedelta
from pathlib import Path

from jamesos.config import VAULT
from jamesos.services.memory_service import search_memory, remember
from jamesos.services.typed_index import search_typed_indexes
from jamesos.services.tool_router import detect_tool, route_tool
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.personality import jade_personality_prompt


BRAIN_ROOT = VAULT / "JamesOS" / "Brain"
CONVERSATIONS_FILE = BRAIN_ROOT / "conversation_summaries.json"
FILES_ROOT = VAULT / "JamesOS" / "Knowledge" / "Files"


def _load_conversations() -> dict:
    BRAIN_ROOT.mkdir(parents=True, exist_ok=True)
    if not CONVERSATIONS_FILE.exists():
        return {"conversations": []}
    return json.loads(CONVERSATIONS_FILE.read_text(encoding="utf-8"))


def _save_conversations(data: dict) -> None:
    BRAIN_ROOT.mkdir(parents=True, exist_ok=True)
    CONVERSATIONS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def detect_intent(question: str) -> str:
    q = question.lower()

    if q.startswith(("remember ", "remember that ")):
        return "remember"
    if q.startswith(("note ", "take a note ", "capture ")):
        return "note"
    if any(w in q for w in ["weather", "forecast", "rain", "snow", "temperature"]):
        return "weather"
    if any(w in q for w in ["look up", "search web", "latest", "news", "research online"]):
        return "web"
    if any(w in q for w in ["ssn", "social security", "tax", "ein", "passport", "license number"]):
        return "sensitive_file"
    if any(w in q for w in ["uploaded", "file", "pdf", "docx", "attachment", "document"]):
        return "file"
    if any(w in q for w in ["yesterday", "talk about", "talked about", "conversation", "remember we"]):
        return "conversation_recall"
    if any(w in q for w in ["kevin", "malcolm", "tom", "julia", "cj", "wife"]):
        return "person"
    if any(w in q for w in ["ticket", "bug", "paving", "wgl", "work", "sbx", "sfm2"]):
        return "work"

    return "general"


def plan_sources(intent: str) -> list[str]:
    plans = {
        "remember": ["memory"],
        "note": ["queue"],
        "weather": ["weather"],
        "web": ["web_search"],
        "sensitive_file": ["files"],
        "file": ["files", "memory"],
        "conversation_recall": ["conversation_summaries", "memory", "work", "gmail", "gcu", "chat"],
        "person": ["memory", "people", "work", "gmail", "calendar", "conversation_summaries"],
        "work": ["work", "memory", "gmail", "calendar", "conversation_summaries"],
        "general": ["memory", "knowledge", "reports"],
    }
    return plans.get(intent, ["memory", "knowledge"])


def _extract_people(text: str) -> list[str]:
    known = ["Kevin", "Malcolm", "Tom", "Julia", "CJ", "James", "Jade", "Ian", "Elias"]
    return [p for p in known if re.search(rf"\b{re.escape(p)}\b", text, re.I)]


def _extract_tickets(text: str) -> list[str]:
    return sorted(set(re.findall(r"\b\d{5}\b", text)))


def search_conversations(query: str, limit: int = 10) -> list[dict]:
    data = _load_conversations()
    q = query.lower()
    matches = []

    for item in data.get("conversations", []):
        blob = json.dumps(item).lower()
        score = blob.count(q) * 10

        for person in _extract_people(query):
            if person.lower() in blob:
                score += 20

        for ticket in _extract_tickets(query):
            if ticket in blob:
                score += 20

        if "yesterday" in q:
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            if item.get("date") == yesterday:
                score += 30

        if score:
            item = dict(item)
            item["score"] = score
            matches.append(item)

    matches.sort(key=lambda x: x["score"], reverse=True)
    return matches[:limit]


def summarize_chat_history() -> str:
    chat_file = VAULT / "JamesOS" / "Memory" / "chat_history.json"
    if not chat_file.exists():
        return "No chat history found."

    history = json.loads(chat_file.read_text(encoding="utf-8"))
    if not history:
        return "No chat history to summarize."

    recent = history[-50:]
    text = "\n\n".join(
        f"Q: {h.get('question','')}\nA: {h.get('answer','')}"
        for h in recent
    )

    if ollama_enabled():
        prompt = (
            jade_personality_prompt()
            + "\n\nCreate structured conversation memory from this chat history. "
            + "Extract topics, people, tickets, decisions, open items, and a concise summary. "
            + "Use only facts present in the chat. Do not invent details. "
            + "Return JSON only with keys: topic, summary, people, tickets, decisions, open_items, importance.\n\n"
            + text[:12000]
        )
        raw = ask_ollama(prompt)
    else:
        raw = "{}"

    try:
        parsed = json.loads(raw)
    except Exception:
        parsed = {
            "topic": "Recent Jade Conversation",
            "summary": raw[:2000],
            "people": _extract_people(text),
            "tickets": _extract_tickets(text),
            "decisions": [],
            "open_items": [],
            "importance": "normal",
        }

    data = _load_conversations()
    item = {
        "date": date.today().isoformat(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        **parsed,
    }
    data.setdefault("conversations", []).append(item)
    data["conversations"] = data["conversations"][-200:]
    _save_conversations(data)

    return f"Saved conversation summary: {item.get('topic', 'Recent Jade Conversation')}"


def gather_context(question: str, intent: str, sources: list[str]) -> dict:
    context = {
        "intent": intent,
        "sources": sources,
        "people": _extract_people(question),
        "tickets": _extract_tickets(question),
        "results": {},
    }

    if "memory" in sources:
        context["results"]["memory"] = search_memory(question, limit=8)

    if "conversation_summaries" in sources or "chat" in sources:
        context["results"]["conversation_summaries"] = search_conversations(question, limit=8)

    categories = []
    if "people" in sources:
        categories.append("people")
    if "work" in sources:
        categories.append("work")
    if "gmail" in sources:
        categories.append("gmail")
    if "gcu" in sources:
        categories.append("gcu")
    if "calendar" in sources:
        categories.append("calendar")
    if "files" in sources:
        categories.append("knowledge")
    if "knowledge" in sources:
        categories.append("knowledge")
    if "reports" in sources:
        categories.append("reports")

    if categories:
        context["results"]["indexes"] = search_typed_indexes(question, categories=categories, limit=8)

    return context


def _trust_score(source: str, category: str = "") -> int:
    if source == "indexes" and category in {"knowledge", "work", "gmail", "gcu", "calendar", "people"}:
        return {
            "knowledge": 95,
            "work": 90,
            "gmail": 85,
            "gcu": 85,
            "calendar": 85,
            "people": 75,
        }.get(category, 50)

    if source == "memory":
        return 55

    if source == "conversation_summaries":
        return 35

    return 50


def _rank_context(context: dict) -> list[str]:
    lines = [
        "# Source Trust Rules",
        "- Highest trust: extracted files, work notes, Gmail/GCU imports, calendar imports.",
        "- Medium trust: explicit memories created by James.",
        "- Low trust: prior Jade assistant answers and conversation summaries.",
        "- Do not treat prior Jade answers as verified facts unless confirmed by a source file, email, calendar item, or James's explicit memory.",
        "",
    ]

    for source, data in context.get("results", {}).items():
        if isinstance(data, list):
            trust = _trust_score(source)
            lines.append(f"# Source: {source} | Trust: {trust}/100")
            for item in data:
                lines.append(json.dumps(item, indent=2)[:2500])

        elif isinstance(data, dict):
            lines.append(f"# Source: {source}")
            for category, matches in data.items():
                trust = _trust_score(source, category)
                lines.append(f"## {category} | Trust: {trust}/100")
                for m in matches[:5]:
                    lines.append(
                        f"File: {m.get('file')}\n"
                        f"Title: {m.get('title')}\n"
                        f"Score: {m.get('score')}\n"
                        f"Trust: {trust}/100\n"
                        f"Preview:\n{m.get('preview','')[:2200]}"
                    )
        else:
            lines.append(f"# Source: {source} | Trust: {_trust_score(source)}/100")
            lines.append(str(data)[:2000])

        lines.append("")

    return lines


def _sensitive_file_lookup(question: str) -> dict | None:
    q = question.lower()

    if not any(w in q for w in ["ssn", "social security"]):
        return None

    name_terms = [
        w for w in re.findall(r"[a-zA-Z]+", q)
        if w not in {"what", "is", "the", "ssn", "social", "security", "number", "for", "of"}
    ]

    ssn_pattern = re.compile(r"\b\d{3}-\d{2}-\d{4}\b|\b\d{9}\b")

    if not FILES_ROOT.exists():
        return None

    matches = []

    for path in FILES_ROOT.rglob("*.md"):
        body = path.read_text(encoding="utf-8", errors="ignore")
        lower = body.lower()

        if name_terms and not any(term in lower for term in name_terms):
            continue

        for m in ssn_pattern.finditer(body):
            start = max(0, m.start() - 350)
            end = min(len(body), m.end() + 350)
            snippet = body[start:end]
            score = 10

            for term in name_terms:
                if term in snippet.lower():
                    score += 50

            matches.append((score, path, m.group(0), snippet))

    if not matches:
        return None

    matches.sort(key=lambda x: x[0], reverse=True)
    score, path, value, snippet = matches[0]
    rel = path.relative_to(VAULT).with_suffix("").as_posix()

    return {
        "answer": f"I found it.\n\n**SSN:** `{value}`\n\nSource: [[{rel}]]",
        "source": rel,
        "score": score,
        "snippet": snippet,
    }


def answer_with_brain(question: str, use_ai: bool = True) -> dict:
    intent = detect_intent(question)

    if intent in {"remember", "note"}:
        from jamesos.services.agent import handle_jade_message
        return handle_jade_message(question, use_ai=use_ai)

    if intent == "sensitive_file":
        direct = _sensitive_file_lookup(question)
        if direct:
            return {
                "question": question,
                "answer": direct["answer"],
                "action": "sensitive_file_lookup",
                "intent": intent,
                "planner": ["files"],
                "source": direct["source"],
            }

    tool = detect_tool(question)
    if tool != "local":
        routed = route_tool(question)
        answer = routed.get("result", "")

        if tool == "web_search" and use_ai and ollama_enabled():
            prompt = (
                jade_personality_prompt()
                + "\n\nSummarize these web results for James. "
                + "Use a clean executive-summary format. Include links only if useful.\n\n"
                + f"Question: {question}\n\nResults:\n{answer[:10000]}"
            )
            answer = ask_ollama(prompt)

        return {
            "question": question,
            "answer": answer,
            "action": "tool",
            "intent": intent,
            "planner": [tool],
            "tool_result": routed,
        }

    sources = plan_sources(intent)
    context = gather_context(question, intent, sources)
    ranked_context = "\n".join(_rank_context(context))

    if use_ai and ollama_enabled():
        prompt = (
            jade_personality_prompt()
            + "\n\nYou are answering as Jade. "
            + "Do not invent people, jobs, meetings, emails, dates, or details. "
            + "Use only facts present in high-trust source context. "
            + "Do not use prior Jade answers as facts unless a higher-trust source confirms them. "
            + "If the context is weak, unrelated, or low-trust, say that plainly. "
            + "Do not dump raw fields unless they matter. "
            + "Synthesize the answer like a sharp personal assistant. "
            + "Use short sections or bullets when helpful. "
            + "Do not moralize or lecture James about accessing his own local files. "
            + "For sensitive local documents, be discreet and factual. "
            + "Do not end with generic filler.\n\n"
            + f"Question: {question}\n"
            + f"Intent: {intent}\n"
            + f"Planned sources: {sources}\n\n"
            + f"Context:\n{ranked_context[:16000]}"
        )
        answer = ask_ollama(prompt)
    else:
        answer = ranked_context[:6000]

    # Store only as chat memory, not as verified fact. Source trust rules keep this low-trust.
    if any(w in question.lower() for w in ["kevin", "malcolm", "tom", "paving", "ticket", "important"]):
        remember(f"Low-trust Jade answer, not verified source fact.\nQ: {question}\nA: {answer[:2000]}", source="jade_brain_low_trust", importance="normal")

    return {
        "question": question,
        "answer": answer,
        "action": "brain",
        "intent": intent,
        "planner": sources,
        "context_summary": {
            "people": context.get("people", []),
            "tickets": context.get("tickets", []),
            "sources": sources,
        },
    }
