from dataclasses import dataclass, field
from typing import Any

from jamesos.services.jade_brain import (
    detect_intent,
    plan_sources,
    answer_with_brain,
)
from jamesos.services.jade_memory_router import (
    KNOWLEDGE_GRAPH_AUTHORITY_RULE,
    LOCAL_PEOPLE_RULE,
    MISSING_MEMORY_RULE,
    RetrievalBundle,
    retrieve_for_question,
)
from jamesos.services.knowledge_graph import graph_lookup
from jamesos.services.memory_service import remember
from jamesos.services.jade_context_packages import (
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
    retrieval_bundle: RetrievalBundle | None = None


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


def _score_retrieval(bundle: RetrievalBundle, intent: str, mode: str) -> int:
    score = 25

    if bundle.primary_context:
        score += 45
    if bundle.secondary_context:
        score += 15
    if mode != "personal":
        score += 5
    if intent in {"sensitive_file", "weather"}:
        score = 95

    return min(score, 95)


class JadeReasoner:
    def _commerce_shop_command(self, question: str) -> dict | None:
        lower = question.strip().lower().replace("’", "'")
        generate_phrases = [
            "generate today's commerce_shop product drafts",
            "generate today’s commerce_shop product drafts",
            "generate today commerce_shop product drafts",
            "generate commerce_shop drafts",
        ]
        show_phrases = [
            "show commerce_shop drafts needing review",
            "show product drafts needing review",
            "show commerce_shop drafts",
        ]
        if any(phrase in lower for phrase in generate_phrases):
            from jamesos.services.commerce_product_pipeline import generate_daily_product_drafts

            result = generate_daily_product_drafts()
            drafts = result.get("drafts", [])
            lines = [
                f"Generated {len(drafts)} Commerce Shop draft packages for {result.get('date')}.",
                "",
            ]
            for draft in drafts:
                lines.append(
                    f"- {draft.get('product_type')}: {draft.get('title')} "
                    f"({draft.get('status')}, approval required)"
                )
            lines.extend([
                "",
                "No ComfyUI, Printify, Etsy, publishing, ordering, or sending was executed.",
            ])
            return {
                "question": question,
                "answer": "\n".join(lines),
                "action": "commerce_shop_generate_daily_drafts",
                "confidence": 95,
                "confidence_label": "🟢 High",
                "working_memory": ["Commerce Shop", "Creative Studio", "Job Queue"],
                "result": result,
            }
        if any(phrase in lower for phrase in show_phrases):
            from jamesos.services.commerce_product_pipeline import list_drafts

            result = list_drafts(status="needs_review")
            drafts = result.get("drafts", [])
            lines = [f"Commerce Shop drafts needing review: {len(drafts)}", ""]
            if not drafts:
                lines.append("- None")
            for draft in drafts[:20]:
                lines.append(
                    f"- {draft.get('date')} - {draft.get('product_type')}: {draft.get('title')}"
                )
            return {
                "question": question,
                "answer": "\n".join(lines),
                "action": "commerce_shop_show_drafts",
                "confidence": 95,
                "confidence_label": "🟢 High",
                "working_memory": ["Commerce Shop", "Creative Studio"],
                "result": result,
            }
        return None

    def understand(self, question: str, mode: str | None = None) -> ReasoningPlan:
        mode = normalize_mode(mode)
        intent = detect_intent(question)
        bundle = retrieve_for_question(question, intent=intent, mode=mode)
        source_names = ["knowledge_graph"] if bundle.primary_context else []
        source_names.extend(
            str(item.get("source_type") or "evidence")
            for item in bundle.secondary_context
        )
        sources = list(dict.fromkeys(source_names or plan_sources(intent)))
        context = {
            "results": {
                "knowledge_graph": bundle.primary_context,
                "memory_v2": bundle.primary_context,
                "memory": bundle.secondary_context,
            },
            "local_memory_available": bundle.has_local_context,
            "retrieval_bundle": bundle.as_dict(),
        }

        return ReasoningPlan(
            question=question,
            intent=intent,
            entities=bundle.entities,
            sources=sources,
            mode=mode,
            confidence=_score_retrieval(bundle, intent, mode),
            evidence=context,
            retrieval_bundle=bundle,
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

    def _explicit_world_knowledge_request(self, question: str) -> bool:
        q = question.lower()
        return any(
            phrase in q
            for phrase in [
                "public knowledge",
                "world knowledge",
                "general knowledge",
                "search the web",
                "search web",
                "look online",
                "public figure",
            ]
        )

    def collect_graph(self, plan: ReasoningPlan) -> None:
        if plan.retrieval_bundle and plan.retrieval_bundle.primary_context:
            return
        graph = {}
        for person in plan.entities.get("people", []):
            graph[person] = graph_lookup(person, limit=10)
        for ticket in plan.entities.get("tickets", []):
            graph[ticket] = graph_lookup(ticket, limit=10)

        if graph:
            plan.evidence.setdefault("results", {})["reasoner_graph"] = graph
            plan.confidence = min(plan.confidence + 10, 95)

    def answer(self, plan: ReasoningPlan, use_ai: bool = True) -> dict:
        bundle = plan.retrieval_bundle
        if bundle is None:
            results = plan.evidence.get("results", {})
            primary = results.get("knowledge_graph") or results.get("memory_v2") or []
            secondary = results.get("memory") or []
            if not isinstance(secondary, list):
                secondary = []
            local_query = (
                plan.intent in {"person", "work"} or plan.mode == "memory"
            ) and not self._explicit_world_knowledge_request(plan.question)
            bundle = RetrievalBundle(
                primary_context=list(primary),
                secondary_context=list(secondary),
                rules=[
                    KNOWLEDGE_GRAPH_AUTHORITY_RULE,
                    LOCAL_PEOPLE_RULE,
                    MISSING_MEMORY_RULE,
                ],
                entities=plan.entities,
                local_entity_query=local_query,
                explicit_world_knowledge=self._explicit_world_knowledge_request(plan.question),
            )

        history_request = self._is_chatgpt_history_request(plan.question)
        allow_tools = not (
            bundle.local_entity_query or history_request or plan.mode == "memory"
        )
        if bundle.explicit_world_knowledge:
            allow_tools = True

        if bundle.local_entity_query and not bundle.has_local_context:
            result = {
                "answer": "I don’t have enough local memory.",
                "action": "local_memory_missing",
                "intent": plan.intent,
                "planner": ["memory"],
                "confidence": 25,
            }
        else:
            result = answer_with_brain(
                plan.question,
                use_ai=use_ai,
                allow_tools=allow_tools,
                intent_override=plan.intent,
                retrieval_bundle=bundle,
                confidence_override=plan.confidence,
                mode=plan.mode,
            )

        result["question"] = plan.question
        result["mode"] = plan.mode
        result["mode_label"] = mode_label(plan.mode)
        result["working_memory"] = bundle.working_memory
        result["retrieval_bundle"] = bundle.as_dict()

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

        if mode == "private":
            return

        if intent in {"person", "work", "conversation_recall", "file"}:
            remember(
                f"Jade Reasoner interaction\nMode: {mode}\nQuestion: {q}\nIntent: {intent}\nConfidence: {label}",
                source="jade_reasoner",
                importance="normal",
            )

    def run(self, question: str, use_ai: bool = True, mode: str | None = None) -> dict:
        command_result = self._commerce_shop_command(question)
        if command_result is not None:
            return command_result
        plan = self.understand(question, mode=mode)
        self.collect_graph(plan)
        result = self.answer(plan, use_ai=use_ai)
        self.learn(result)
        return result


def answer_with_reasoner(question: str, use_ai: bool = True, mode: str | None = None) -> dict:
    return JadeReasoner().run(question, use_ai=use_ai, mode=mode)
