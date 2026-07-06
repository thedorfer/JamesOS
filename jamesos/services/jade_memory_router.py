from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from jamesos.services.jade_brain import PAVING_TICKETS, detect_query_entities
from jamesos.services.knowledge_graph_service import load_entity_page
from jamesos.services.unified_memory_search import memory_answer_context


KNOWLEDGE_GRAPH_AUTHORITY_RULE = (
    "Knowledge Graph is authoritative for local named people. "
    "Do not infer family relationships from last names."
)
LOCAL_PEOPLE_RULE = (
    "Do not use public or world knowledge for local named people unless the user explicitly asks."
)
MISSING_MEMORY_RULE = (
    "If local context is insufficient, say “I don’t have enough local memory” rather than guessing."
)


@dataclass
class RetrievalBundle:
    primary_context: list[dict[str, Any]] = field(default_factory=list)
    secondary_context: list[dict[str, Any]] = field(default_factory=list)
    blocked_context: list[dict[str, Any]] = field(default_factory=list)
    rules: list[str] = field(default_factory=list)
    entities: dict[str, list[str]] = field(
        default_factory=lambda: {"people": [], "projects": [], "tickets": []}
    )
    local_entity_query: bool = False
    explicit_world_knowledge: bool = False

    @property
    def has_local_context(self) -> bool:
        return bool(self.primary_context or self.secondary_context)

    @property
    def working_memory(self) -> list[str]:
        labels: list[str] = []
        for item in self.primary_context:
            title = str(item.get("title") or "").strip()
            if title and title not in labels:
                labels.append(title)
        if not labels:
            for item in self.secondary_context:
                title = str(item.get("title") or "").strip()
                if title and title not in labels:
                    labels.append(title)
        return labels

    def as_dict(self) -> dict[str, Any]:
        return {
            "primary_context": self.primary_context,
            "secondary_context": self.secondary_context,
            "blocked_context": self.blocked_context,
            "rules": self.rules,
            "entities": self.entities,
            "local_entity_query": self.local_entity_query,
            "explicit_world_knowledge": self.explicit_world_knowledge,
        }


def _explicit_world_request(question: str) -> bool:
    lower = question.casefold()
    return any(
        phrase in lower
        for phrase in (
            "public knowledge",
            "world knowledge",
            "general knowledge",
            "search the web",
            "search web",
            "look online",
            "public figure",
        )
    )


def _load_page(entity_type: str, name: str) -> dict[str, Any] | None:
    try:
        result = load_entity_page(entity_type, name)
    except Exception:
        return None
    if result.get("status") != "ok":
        return None
    return {
        "title": name,
        "entity_type": entity_type,
        "source_type": "knowledge_graph",
        "content": str(result.get("content") or ""),
        "path": str(result.get("path") or ""),
    }


def _contains_blocked_identity(item: dict[str, Any]) -> bool:
    text = "\n".join(
        str(item.get(key) or "")
        for key in ("title", "content", "snippet", "path")
    ).casefold()
    return "malcolm allendoerfer" in text


def _append_unique(items: list[dict[str, Any]], item: dict[str, Any] | None) -> None:
    if not item:
        return
    key = (item.get("source_type"), item.get("entity_type"), item.get("title"))
    if any(
        (current.get("source_type"), current.get("entity_type"), current.get("title")) == key
        for current in items
    ):
        return
    items.append(item)


def retrieve_for_question(question: str, intent: str, mode: str = "personal") -> RetrievalBundle:
    entities = detect_query_entities(question)
    lower = question.casefold()
    explicit_world = _explicit_world_request(question)
    local_query = bool(
        intent in {"person", "work"}
        or mode == "memory"
        or entities["people"]
        or entities["projects"]
        or entities["tickets"]
    ) and not explicit_world

    if "malcolm" in lower or "paving" in lower:
        entities["people"] = list(dict.fromkeys(["Malcolm Wrench", *entities["people"]]))
        entities["projects"] = list(dict.fromkeys(["Paving", *entities["projects"]]))
        entities["tickets"] = list(dict.fromkeys([*PAVING_TICKETS, *entities["tickets"]]))

    bundle = RetrievalBundle(
        entities=entities,
        local_entity_query=local_query,
        explicit_world_knowledge=explicit_world,
        rules=[
            KNOWLEDGE_GRAPH_AUTHORITY_RULE,
            LOCAL_PEOPLE_RULE,
            MISSING_MEMORY_RULE,
            "Use primary Knowledge Graph context before secondary Evidence.",
            "Blocked context must never be included in the answer.",
        ],
    )

    for person in entities["people"]:
        _append_unique(bundle.primary_context, _load_page("people", person))
    for project in entities["projects"]:
        _append_unique(bundle.primary_context, _load_page("projects", project))
    for ticket in entities["tickets"]:
        _append_unique(bundle.primary_context, _load_page("tickets", ticket))

    evidence_requested = any(
        term in lower for term in ("email", "memory", "history", "evidence", "source")
    )
    if local_query and (evidence_requested or not bundle.primary_context):
        try:
            result = memory_answer_context(question, limit=6)
        except Exception:
            result = {"sources": []}
        for source in result.get("sources", []):
            item = {
                "title": source.get("title") or "Local evidence",
                "source_type": source.get("source_type") or "evidence",
                "snippet": str(source.get("snippet") or ""),
                "path": str(source.get("path") or ""),
                "key_facts": source.get("key_facts") or [],
            }
            if _contains_blocked_identity(item):
                item["blocked_reason"] = "Stale or incorrect Malcolm identity."
                bundle.blocked_context.append(item)
            else:
                bundle.secondary_context.append(item)

    bundle.blocked_context.append(
        {
            "title": "Generic public identity inference",
            "blocked_reason": "Local named people must come from JamesOS Knowledge Graph.",
        }
    )
    return bundle
