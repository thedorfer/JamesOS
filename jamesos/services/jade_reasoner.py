from dataclasses import dataclass, field
from typing import Any

from jamesos.services.jade_brain import (
    detect_intent,
    plan_sources,
    gather_context,
    answer_with_brain,
)
from jamesos.services.knowledge_graph import graph_lookup
from jamesos.services.memory_service import remember
from jamesos.services.jade_context_packages import (
    build_context_package,
    mode_label,
    normalize_mode,
)


@dataclass
class ReasoningPlan:
    question: str
    intent: str
    entities: dict[str, list[str]]
    sources: list[str]
    mode: str = "personal"
    confidence: int = 25
    evidence: dict[str, Any] = field(default_factory=dict)


def _clean_jade_answer(answer: str, plan: ReasoningPlan, result: dict) -> str:
    lower = answer.lower()

    bad_context_dump = any(
        phrase in lower
        for phrase in [
            "json data",
            "provided json",
            "three different entities",
            "nodes are files",
            "related nodes",
            "edges connecting",
            "graph structure",
        ]
    )

    if bad_context_dump:
        return (
            "I pulled context, but the answer came back too much like a data dump. "
            "The useful move is to ask for a focused briefing from the current mode, not summarize the graph itself."
        )

    banned_starts = [
        "based on the data provided",
        "based on the context",
        "in the provided data",
        "there are several nodes",
        "edges connecting",
        "to better understand",
        "it appears",
    ]

    if plan.intent == "person" and any(b in lower for b in banned_starts):
        people = plan.entities.get("people", [])
        person = people[0] if people else "that person"

        graph = plan.evidence.get("results", {}).get("knowledge_graph", {})
        graph_blob = str(graph)

        bullets = []

        if "Paving" in graph_blob:
            bullets.append("Connected to your Paving work")
        if "88858" in graph_blob:
            bullets.append("Related to ticket 88858")
        if "Malcolm" in graph_blob:
            bullets.append("Mentioned with Malcolm")
        if "SFM2" in graph_blob:
            bullets.append("Shows up around SFM2")
        if "SBX" in graph_blob:
            bullets.append("Shows up around SBX")
        if "GCU" in graph_blob:
            bullets.append("Shows up in some GCU-related memory too, but that looks lower-confidence")

        if not bullets:
            bullets.append("I found mentions, but not enough high-trust context to say much yet")

        return (
            f"{person} looks mostly tied to your recent work context.\n\n"
            "What I know:\n"
            + "\n".join(f"- {b}" for b in bullets)
        )

    answer = answer.replace("Based on the data provided, ", "")
    answer = answer.replace("Based on the context provided, ", "")
    answer = answer.replace("it appears that ", "")
    answer = answer.replace("It appears that ", "")
    answer = answer.replace("Let me know if you need more information.", "")
    answer = answer.replace("I hope this helps.", "")

    return answer.strip()


def confidence_label(score: int) -> str:
    if score >= 85:
        return "🟢 High"
    if score >= 60:
        return "🟡 Medium"
    return "🔴 Low"


def _score_context(context: dict, intent: str, mode: str) -> int:
    results = context.get("results", {})
    score = 25

    if results.get("knowledge_graph"):
        score += 25
    if results.get("indexes"):
        score += 25
    if results.get("memory"):
        score += 10
    if results.get("conversation_summaries"):
        score += 5
    if mode != "personal":
        score += 5
    if intent in {"sensitive_file", "weather"}:
        score = 95

    return min(score, 95)


class JadeReasoner:
    def understand(self, question: str, mode: str | None = None) -> ReasoningPlan:
        mode = normalize_mode(mode)
        intent = detect_intent(question)
        sources = plan_sources(intent)

        context = gather_context(question, intent, sources)
        entities = {
            "people": context.get("people", []),
            "tickets": context.get("tickets", []),
        }

        return ReasoningPlan(
            question=question,
            intent=intent,
            entities=entities,
            sources=sources,
            mode=mode,
            confidence=_score_context(context, intent, mode),
            evidence=context,
        )

    def collect_graph(self, plan: ReasoningPlan) -> None:
        graph = {}
        for person in plan.entities.get("people", []):
            graph[person] = graph_lookup(person, limit=10)
        for ticket in plan.entities.get("tickets", []):
            graph[ticket] = graph_lookup(ticket, limit=10)

        if graph:
            plan.evidence.setdefault("results", {})["reasoner_graph"] = graph
            plan.confidence = min(plan.confidence + 10, 95)

    def answer(self, plan: ReasoningPlan, use_ai: bool = True) -> dict:
        question_for_brain = plan.question
        if plan.mode != "personal":
            context_package = build_context_package(plan.question, plan.mode)
            question_for_brain = (
                f"{context_package}\n\n"
                "# Response Task\n"
                "Answer James's question directly. Do not describe the raw context package, JSON, nodes, edges, or graph implementation.\n"
                f"Question: {plan.question}"
            )

        result = answer_with_brain(question_for_brain, use_ai=use_ai)
        result["question"] = plan.question
        result["mode"] = plan.mode
        result["mode_label"] = mode_label(plan.mode)

        confidence = result.get("confidence", plan.confidence)
        result["confidence"] = confidence
        result["confidence_label"] = confidence_label(confidence)
        result["reasoner"] = {
            "intent": plan.intent,
            "sources": plan.sources,
            "entities": plan.entities,
            "mode": plan.mode,
            "mode_label": mode_label(plan.mode),
            "confidence": confidence,
            "confidence_label": confidence_label(confidence),
        }

        answer = result.get("answer", "")

        import re
        answer = re.sub(r"\n\n\*Confidence: .*?\(\d+%\)\*", "", answer)
        answer = _clean_jade_answer(answer, plan, result)
        answer = answer.rstrip() + f"\n\n*{confidence_label(confidence)} confidence*"
        result["answer"] = answer

        return result

    def learn(self, result: dict) -> None:
        q = result.get("question", "")
        intent = result.get("intent") or result.get("reasoner", {}).get("intent", "")
        label = result.get("confidence_label", "")
        mode = result.get("mode", "personal")

        if intent in {"person", "work", "conversation_recall", "file"}:
            remember(
                f"Jade Reasoner interaction\nMode: {mode}\nQuestion: {q}\nIntent: {intent}\nConfidence: {label}",
                source="jade_reasoner",
                importance="normal",
            )

    def run(self, question: str, use_ai: bool = True, mode: str | None = None) -> dict:
        plan = self.understand(question, mode=mode)
        self.collect_graph(plan)
        result = self.answer(plan, use_ai=use_ai)
        self.learn(result)
        return result


def answer_with_reasoner(question: str, use_ai: bool = True, mode: str | None = None) -> dict:
    return JadeReasoner().run(question, use_ai=use_ai, mode=mode)
