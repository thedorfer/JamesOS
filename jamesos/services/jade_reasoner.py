from dataclasses import dataclass, field
from typing import Any

from jamesos.services.jade_brain import (
    detect_intent,
    plan_sources,
    gather_context,
    answer_with_brain,
)
from jamesos.services.knowledge_graph import graph_lookup
from jamesos.services.identity_profile import identity_context
from jamesos.services.memory_service import remember
from jamesos.services.unified_memory_search import (
    history_context as unified_history_context,
    memory_answer_context,
)
from jamesos.services.memory_v2 import load_entity_page
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
    if results.get("chatgpt_history") or results.get("memory"):
        score += 25
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
        # Try loading Memory V2 pages for detected entities first
        results_block = []
        people = context.get("people", []) or []
        tickets = context.get("tickets", []) or []
        projects = context.get("projects", []) or []
        for p in people:
            try:
                r = load_entity_page("people", p)
                if r.get("status") == "ok":
                    results_block.append({"title": p, "content": r.get("content"), "source_type": "memory_v2"})
            except Exception:
                pass
        for t in tickets:
            try:
                r = load_entity_page("tickets", t)
                if r.get("status") == "ok":
                    results_block.append({"title": t, "content": r.get("content"), "source_type": "memory_v2"})
            except Exception:
                pass
        for pr in projects:
            try:
                r = load_entity_page("projects", pr)
                if r.get("status") == "ok":
                    results_block.append({"title": pr, "content": r.get("content"), "source_type": "memory_v2"})
            except Exception:
                pass

        # If we have memory v2 sources, attach as primary memory context; otherwise fall back to unified history
        if results_block:
            context.setdefault("results", {})["memory_v2"] = results_block
        else:
            history_ctx = unified_history_context(question, limit=6)
            if "No matching memory found." not in history_ctx:
                context.setdefault("results", {})["memory"] = history_ctx

        entities = {
            "people": context.get("people", []),
            "tickets": context.get("tickets", []),
        }

        return ReasoningPlan(
            question=question,
            intent=intent,
            entities=entities,
            sources=sources + ["memory"],
            mode=mode,
            confidence=_score_context(context, intent, mode),
            evidence=context,
        )

    def _is_chatgpt_history_request(self, question: str) -> bool:
        q = question.lower()
        return any(
            phrase in q
            for phrase in [
                "chatgpt history",
                "imported chatgpt history",
                "chatgpt-history",
                "chat gpt history",
            ]
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
        allow_tools = True
        history_context = plan.evidence.get("results", {}).get("memory", "")
        identity_block = identity_context()
        history_request = self._is_chatgpt_history_request(plan.question)

        if history_context or history_request or plan.mode == "memory":
            allow_tools = False

        memory_block = ""
        # prefer MemoryV2 structured pages if available
        mem_v2 = plan.evidence.get("results", {}).get("memory_v2")
        if mem_v2:
            parts: list[str] = ["# MemoryV2 Retrieved Pages"]
            for s in mem_v2:
                parts.append(f"## {s.get('title', '')} (memory_v2)")
                parts.append("")
                parts.append(str(s.get("content", ""))[:3000])
                parts.append("")
            memory_block = "\n".join(parts)
        elif history_context:
            # structured memory facts to include in prompt
            try:
                mem = memory_answer_context(plan.question, limit=6)
            except Exception:
                mem = None
            if mem and mem.get("status") == "ok":
                parts: list[str] = ["# Retrieved Memory Sources"]
                for s in mem.get("sources", []):
                    parts.append(f"## {s.get('title', '')} ({s.get('source_type', '')})")
                    parts.append(f"Path: {s.get('path', '')}")
                    parts.append("")
                    parts.append(str(s.get("snippet", ""))[:2000])
                    parts.append("")
                    kf = s.get("key_facts") or []
                    if kf:
                        parts.append("Key facts:")
                        for f in kf:
                            parts.append(f"- {f}")
                        parts.append("")
                memory_block = "\n".join(parts)

            question_for_brain = (
                f"{memory_block}\n\n"
                "# Response Task\n"
                "Summarize the facts found in the memory sources above as concise bullets. Do not invent facts. "
                "If the evidence is thin, list what was found and what is missing. Answer James directly and practically.\n"
                f"Question: {plan.question}"
            )

        if plan.mode != "personal":
            context_package = build_context_package(plan.question, plan.mode)
            question_for_brain = (
                f"{context_package}\n\n"
                f"{history_context}\n\n"
                "# Response Task\n"
                "Answer James's question directly. Do not describe the raw context package, JSON, nodes, edges, paths, or graph implementation.\n"
                f"Question: {plan.question}"
            )
            allow_tools = False

        result = answer_with_brain(question_for_brain, use_ai=use_ai, allow_tools=allow_tools)

        if use_ai and history_context:
            pass
        result["question"] = plan.question
        result["mode"] = plan.mode
        result["mode_label"] = mode_label(plan.mode)

        confidence = result.get("confidence", plan.confidence)
        result["confidence"] = confidence
        result["confidence_label"] = None if plan.mode == "chat" else confidence_label(confidence)
        result["reasoner"] = {
            "intent": plan.intent,
            "sources": plan.sources,
            "entities": plan.entities,
            "mode": plan.mode,
            "mode_label": mode_label(plan.mode),
            "confidence": confidence,
            "confidence_label": None if plan.mode == "chat" else confidence_label(confidence),
        }

        answer = result.get("answer", "")

        import re
        answer = re.sub(r"\n\n\*Confidence: .*?\(\d+%\)\*", "", answer)
        answer = _clean_jade_answer(answer, plan, result)
        if plan.mode != "chat":
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
