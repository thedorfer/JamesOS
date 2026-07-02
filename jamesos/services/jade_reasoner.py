from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from jamesos.services.jade_brain import (
    detect_intent,
    plan_sources,
    gather_context,
    answer_with_brain,
)
from jamesos.services.knowledge_graph import graph_lookup
from jamesos.services.memory_service import remember


@dataclass
class ReasoningPlan:
    question: str
    intent: str
    entities: dict[str, list[str]]
    sources: list[str]
    confidence: int = 25
    evidence: dict[str, Any] = field(default_factory=dict)


def confidence_label(score: int) -> str:
    if score >= 85:
        return "🟢 High"
    if score >= 60:
        return "🟡 Medium"
    return "🔴 Low"


def _score_context(context: dict, intent: str) -> int:
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
    if intent in {"sensitive_file", "weather"}:
        score = 95

    return min(score, 95)


class JadeReasoner:
    def understand(self, question: str) -> ReasoningPlan:
        intent = detect_intent(question)
        sources = plan_sources(intent)

        # Gather basic entity hints from the current brain context function.
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
            confidence=_score_context(context, intent),
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
        result = answer_with_brain(plan.question, use_ai=use_ai)

        confidence = result.get("confidence", plan.confidence)
        result["confidence"] = confidence
        result["confidence_label"] = confidence_label(confidence)
        result["reasoner"] = {
            "intent": plan.intent,
            "sources": plan.sources,
            "entities": plan.entities,
            "confidence": confidence,
            "confidence_label": confidence_label(confidence),
        }

        answer = result.get("answer", "")

        # Replace percentage confidence footer with simple Jade-style label.
        import re
        answer = re.sub(r"\n\n\*Confidence: .*?\(\d+%\)\*", "", answer)
        answer = answer.rstrip() + f"\n\n*{confidence_label(confidence)} confidence*"
        result["answer"] = answer

        return result

    def learn(self, result: dict) -> None:
        q = result.get("question", "")
        intent = result.get("intent") or result.get("reasoner", {}).get("intent", "")
        label = result.get("confidence_label", "")

        if intent in {"person", "work", "conversation_recall", "file"}:
            remember(
                f"Jade Reasoner interaction\nQuestion: {q}\nIntent: {intent}\nConfidence: {label}",
                source="jade_reasoner",
                importance="normal",
            )

    def run(self, question: str, use_ai: bool = True) -> dict:
        plan = self.understand(question)
        self.collect_graph(plan)
        result = self.answer(plan, use_ai=use_ai)
        self.learn(result)
        return result


def answer_with_reasoner(question: str, use_ai: bool = True) -> dict:
    return JadeReasoner().run(question, use_ai=use_ai)
