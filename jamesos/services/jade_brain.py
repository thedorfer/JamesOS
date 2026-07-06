from pathlib import Path
import json
import re
from datetime import datetime
from typing import Any

from jamesos.config import VAULT
from jamesos.services.tool_router import detect_tool, route_tool
from jamesos.services.ollama_service import ask_ollama, ollama_enabled
from jamesos.services.personality import jade_personality_prompt
from jamesos.services.identity_profile import identity_context


BRAIN_ROOT = VAULT / "JamesOS" / "Brain"
CONVERSATIONS_FILE = BRAIN_ROOT / "conversation_summaries.json"
FILES_ROOT = VAULT / "JamesOS" / "Knowledge" / "Files"
PAVING_TICKETS = ("88858", "88637", "87229")
LOCAL_PERSON_MEMORY_RULE = (
    "Use JamesOS Knowledge Graph first. Do not use public/world knowledge for "
    "named people unless explicitly asked. Use only JamesOS memory for named "
    "people unless the user explicitly asks for public/world knowledge."
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


def _append_confidence(answer: str, confidence: int) -> str:
    if confidence >= 90:
        label = "high"
    elif confidence >= 65:
        label = "medium"
    else:
        label = "low"

    return f"{answer}\n\n*Confidence: {label} ({confidence}%)*"


def _bundle_list(bundle: Any, name: str) -> list[dict]:
    if bundle is None:
        return []
    value = getattr(bundle, name, None)
    if value is None and isinstance(bundle, dict):
        value = bundle.get(name)
    return list(value) if isinstance(value, list) else []


def _bundle_rules(bundle: Any) -> list[str]:
    if bundle is None:
        return []
    value = getattr(bundle, "rules", None)
    if value is None and isinstance(bundle, dict):
        value = bundle.get("rules")
    return [str(rule) for rule in value] if isinstance(value, list) else []


def _render_retrieval_context(bundle: Any) -> str:
    lines: list[str] = ["# Retrieval Context"]
    primary = _bundle_list(bundle, "primary_context")
    secondary = _bundle_list(bundle, "secondary_context")

    lines.extend(["", "## Primary — JamesOS Knowledge Graph"])
    if primary:
        for item in primary:
            lines.extend(
                [
                    "",
                    f"### {item.get('title', 'Untitled')}",
                    str(item.get("content") or "")[:4500],
                ]
            )
    else:
        lines.extend(["", "No Knowledge Graph pages were retrieved."])

    lines.extend(["", "## Secondary — Evidence"])
    if secondary:
        for item in secondary:
            content = item.get("content") or item.get("snippet") or ""
            lines.extend(
                [
                    "",
                    f"### {item.get('title', 'Local evidence')} ({item.get('source_type', 'evidence')})",
                    str(content)[:1800],
                ]
            )
            facts = item.get("key_facts") or []
            if facts:
                lines.extend(f"- {fact}" for fact in facts[:5])
    else:
        lines.extend(["", "No secondary Evidence was retrieved."])
    return "\n".join(lines)


def build_jade_prompt(
    question: str,
    intent: str,
    retrieval_bundle: Any,
    mode: str = "personal",
) -> str:
    hard_rules = [
        "Knowledge Graph is authoritative for local named people. Do not infer family relationships from last names.",
        "Do not use public or world knowledge for named local people unless the user explicitly asks.",
        "Never include blocked context.",
        "Do not invent missing facts. If local context is insufficient, say “I don’t have enough local memory”.",
    ]
    rules = list(dict.fromkeys([*hard_rules, *_bundle_rules(retrieval_bundle)]))
    rules_text = "\n".join(f"- {rule}" for rule in rules)
    retrieval_text = _render_retrieval_context(retrieval_bundle)
    return (
        f"{jade_personality_prompt()}\n\n"
        f"{identity_context()}\n\n"
        "# Answering Rules\n"
        f"{rules_text}\n\n"
        f"{retrieval_text}\n\n"
        "# Response Task\n"
        "Answer James directly and concisely from the supplied Retrieval Context. "
        "Use Primary context first and Secondary Evidence only to clarify or support it. "
        "Do not describe retrieval internals, JSON, graph nodes, or file paths.\n"
        f"Mode: {mode}\n"
        f"Intent: {intent}\n"
        f"Question: {question}"
    )


def answer_with_brain(
    question: str,
    use_ai: bool = True,
    allow_tools: bool = True,
    intent_override: str | None = None,
    retrieval_bundle: Any = None,
    confidence_override: int | None = None,
    mode: str = "personal",
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

    primary_context = _bundle_list(retrieval_bundle, "primary_context")
    secondary_context = _bundle_list(retrieval_bundle, "secondary_context")
    confidence = confidence_override if confidence_override is not None else (
        85 if primary_context else 60 if secondary_context else 25
    )
    prompt = build_jade_prompt(
        question=question,
        intent=intent,
        retrieval_bundle=retrieval_bundle,
        mode=mode,
    )

    if use_ai and ollama_enabled():
        answer = ask_ollama(prompt)
    else:
        answer = _render_retrieval_context(retrieval_bundle)[:6000]

    return {
        "question": question,
        "answer": _append_confidence(answer, confidence),
        "action": "brain",
        "intent": intent,
        "planner": [
            *(["knowledge_graph"] if primary_context else []),
            *(["evidence"] if secondary_context else []),
        ],
        "context_summary": {
            "primary_count": len(primary_context),
            "secondary_count": len(secondary_context),
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
