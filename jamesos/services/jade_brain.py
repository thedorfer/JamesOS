from pathlib import Path
import json
import re
from datetime import datetime, date, timedelta

from jamesos.config import VAULT
from jamesos.services.memory_service import search_memory, remember
from jamesos.services.typed_index import search_typed_indexes
from jamesos.services.tool_router import detect_tool, route_tool
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.personality import jade_personality_prompt
from jamesos.services.knowledge_graph import graph_lookup
from jamesos.services.identity_profile import identity_context


BRAIN_ROOT = VAULT / "JamesOS" / "Brain"
CONVERSATIONS_FILE = BRAIN_ROOT / "conversation_summaries.json"
FILES_ROOT = VAULT / "JamesOS" / "Knowledge" / "Files"
PAVING_TICKETS = ("88858", "88637", "87229")
LOCAL_PERSON_MEMORY_RULE = (
    "Use only JamesOS memory for named people unless the user explicitly asks "
    "for public/world knowledge."
)
_QUESTION_WORDS = {
    "What",
    "Who",
    "Where",
    "When",
    "Why",
    "How",
    "Do",
    "Does",
    "Did",
    "Tell",
    "Please",
    "My",
    "From",
}


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
    if any(w in q for w in ["ssn", "social security"]):
        return "sensitive_file"
    if any(w in q for w in ["weather", "forecast", "rain", "snow", "temperature"]):
        return "weather"
    if any(w in q for w in ["look up", "search web", "latest", "news", "research online"]):
        return "web"
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
        "file": ["files", "memory", "chat"],
        "conversation_recall": ["conversation_summaries", "memory", "work", "gmail", "gcu", "chat"],
        "person": ["memory", "people", "work", "gmail", "calendar", "conversation_summaries"],
        "work": ["work", "memory", "gmail", "calendar", "conversation_summaries"],
        "sensitive_file": ["files"],
        "general": ["memory", "knowledge", "reports"],
    }
    return plans.get(intent, plans["general"])


def detect_query_entities(question: str) -> dict[str, list[str]]:
    lower = question.lower()
    people = {
        name
        for name in re.findall(r"\b[A-Z][a-z]+\b", question)
        if name not in _QUESTION_WORDS
    }
    if re.search(r"\bmalcolm\b", lower):
        people.discard("Malcolm")
        if re.search(r"\bmalcolm\s+wrench\b", lower):
            people.discard("Wrench")
        people.add("Malcolm Wrench")

    projects: set[str] = set()
    if re.search(r"\bpaving\b", lower):
        projects.add("Paving")

    tickets = set(re.findall(r"\b\d{5}\b", question))
    if "Paving" in projects:
        tickets.update(PAVING_TICKETS)

    return {
        "people": sorted(people),
        "projects": sorted(projects),
        "tickets": sorted(tickets),
    }


def gather_context(question: str, intent: str, sources: list[str]) -> dict:
    entities = detect_query_entities(question)
    context = {
        "question": question,
        "intent": intent,
        "sources": sources,
        "people": entities["people"],
        "projects": entities["projects"],
        "tickets": entities["tickets"],
        "results": {},
    }

    if "memory" in sources:
        context["results"]["memory"] = search_memory(question, limit=8)

    if context.get("people") or context.get("tickets"):
        graph_terms = context.get("people") or context.get("tickets")
        context["results"]["knowledge_graph"] = {
            term: graph_lookup(term, limit=10)
            for term in graph_terms
        }

    if any(s in sources for s in ["work", "people", "gcu", "knowledge", "reports", "files"]):
        context["results"]["indexes"] = search_typed_indexes(question)

    if "conversation_summaries" in sources:
        context["results"]["conversation_summaries"] = _load_conversations().get("conversations", [])[-8:]

    return context


def _source_trust(source: str) -> int:
    trust = {
        "files": 95,
        "indexes": 85,
        "work": 85,
        "people": 80,
        "gmail": 80,
        "calendar": 80,
        "memory": 70,
        "conversation_summaries": 55,
        "knowledge_graph": 65,
        "reports": 65,
        "chat": 45,
    }
    return trust.get(source, 50)


def _rank_context(context: dict) -> list[str]:
    lines = []
    results = context.get("results", {})

    for source, matches in sorted(results.items(), key=lambda item: _source_trust(item[0]), reverse=True):
        trust = _source_trust(source)
        lines.append(f"\n## Source: {source} (trust {trust}/100)")

        if isinstance(matches, list):
            for m in matches[:5]:
                if isinstance(m, dict):
                    lines.append(json.dumps(m, indent=2)[:2500])
                else:
                    lines.append(str(m)[:2500])
        elif isinstance(matches, dict):
            lines.append(json.dumps(matches, indent=2)[:5000])
        else:
            lines.append(str(matches)[:2500])

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
    display_source = Path(rel).stem.replace("_", " ")

    return {
        "answer": f"Yep.\n\n**SSN**\n`{value}`\n\n*Found in {display_source}.*",
        "source": rel,
        "score": score,
        "snippet": snippet,
    }


def _confidence_from_context(context: dict, intent: str) -> int:
    results = context.get("results", {})
    score = 25

    if results.get("knowledge_graph"):
        score += 20
    if results.get("indexes"):
        score += 25
    if results.get("memory"):
        score += 10
    if results.get("conversation_summaries"):
        score += 5

    if intent in {"sensitive_file", "weather"}:
        score = 95

    return min(score, 95)


def _append_confidence(answer: str, confidence: int) -> str:
    if confidence >= 90:
        label = "high"
    elif confidence >= 65:
        label = "medium"
    else:
        label = "low"

    return f"{answer}\n\n*Confidence: {label} ({confidence}%)*"


def answer_with_brain(
    question: str,
    use_ai: bool = True,
    allow_tools: bool = True,
    intent_override: str | None = None,
) -> dict:
    intent = intent_override or detect_intent(question)

    if intent in {"remember", "note"}:
        from jamesos.services.agent import handle_jade_message
        return handle_jade_message(question, use_ai=use_ai)

    if intent == "sensitive_file":
        direct = _sensitive_file_lookup(question)
        if direct:
            return {
                "question": question,
                "answer": _append_confidence(direct["answer"], 95),
                "action": "sensitive_file_lookup",
                "intent": intent,
                "planner": ["files"],
                "source": direct["source"],
            }

    tool = detect_tool(question) if allow_tools else "local"
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

    confidence = _confidence_from_context(context, intent)

    if use_ai and ollama_enabled():
        prompt = (
            jade_personality_prompt()
            + "\n\n"
            + identity_context()
            + "\n\nYou are answering as Jade. "
            + "Do not invent people, jobs, meetings, emails, dates, or details. "
            + "Use only facts present in high-trust source context. "
            + LOCAL_PERSON_MEMORY_RULE
            + " If local memory is missing, say “I don’t have enough local memory” rather than guessing. "
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

    return {
        "question": question,
        "answer": _append_confidence(answer, confidence),
        "action": "brain",
        "intent": intent,
        "planner": sources,
        "context_summary": {
            "people": context.get("people", []),
            "tickets": context.get("tickets", []),
            "sources": sources,
        },
        "confidence": confidence,
    }


def summarize_chat_history() -> str:
    data = _load_conversations()
    today = datetime.now().strftime("%Y-%m-%d")
    summary = {
        "date": today,
        "topic": "Conversations with James's personal assistant Jade",
        "summary": "Recent Jade interactions summarized for future recall.",
        "people": [],
        "tickets": [],
        "decisions": [],
        "open_items": [],
        "importance": "normal",
    }
    data.setdefault("conversations", []).append(summary)
    _save_conversations(data)
    return "Saved conversation summary: Conversations with James's personal assistant Jade"
