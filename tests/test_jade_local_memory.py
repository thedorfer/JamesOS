from jamesos.services import jade_memory_router, jade_reasoner
from jamesos.services.jade_brain import (
    PAVING_TICKETS,
    build_jade_prompt,
    detect_query_entities,
)
from jamesos.services.jade_reasoner import JadeReasoner, ReasoningPlan


def test_malcolm_and_paving_entity_detection_is_local_and_canonical() -> None:
    entities = detect_query_entities(
        "What do you know about Malcolm Wrench and paving from my email and memory?"
    )

    assert entities["people"] == ["Malcolm Wrench"]
    assert entities["projects"] == ["Paving"]
    assert set(PAVING_TICKETS) <= set(entities["tickets"])


def test_reasoner_loads_malcolm_alias_paving_and_ticket_pages(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_load(entity_type: str, name: str):
        calls.append((entity_type, name))
        available = {
            ("people", "Malcolm Wrench"),
            ("projects", "Paving"),
            *(("tickets", ticket) for ticket in PAVING_TICKETS),
        }
        if (entity_type, name) in available:
            content = (
                "# Malcolm Wrench\n## Role / Organization\nCGI Partner / Director, Consulting Expert"
                if name == "Malcolm Wrench"
                else f"# {name}\nLocal Knowledge Graph page"
            )
            return {"status": "ok", "content": content}
        return {"status": "missing"}

    monkeypatch.setattr(jade_memory_router, "load_entity_page", fake_load)
    monkeypatch.setattr(
        jade_memory_router,
        "memory_answer_context",
        lambda question, limit=6: {
            "sources": [
                {
                    "title": "Stale generic memory",
                    "source_type": "memory",
                    "snippet": "Malcolm Allendoerfer is probably related to James.",
                }
            ]
        },
    )

    plan = JadeReasoner().understand(
        "What do you know about Malcolm and paving from my email and memory?"
    )

    titles = [item["title"] for item in plan.retrieval_bundle.primary_context]
    assert "Malcolm Wrench" in titles
    assert "Paving" in titles
    assert set(PAVING_TICKETS) <= set(titles)
    assert ("people", "Malcolm Wrench") in calls
    assert plan.retrieval_bundle.blocked_context
    assert all(
        "Malcolm Allendoerfer" not in str(item)
        for item in plan.retrieval_bundle.secondary_context
    )


def test_memory_pages_are_inserted_into_prompt_and_tools_are_disabled(monkeypatch) -> None:
    captured = {}

    def fake_answer(
        question,
        use_ai=True,
        allow_tools=True,
        intent_override=None,
        retrieval_bundle=None,
        **kwargs,
    ):
        prompt = build_jade_prompt(
            question,
            intent_override,
            retrieval_bundle,
        )
        captured.update(
            prompt=prompt,
            allow_tools=allow_tools,
            intent_override=intent_override,
        )
        return {"answer": "Local answer", "confidence": 90}

    monkeypatch.setattr(jade_reasoner, "answer_with_brain", fake_answer)
    bundle = jade_memory_router.RetrievalBundle(
        primary_context=[
            {
                "title": "Malcolm Wrench",
                "content": "Malcolm Wrench is a CGI Partner / Director, Consulting Expert.",
            },
            {
                "title": "Paving",
                "content": "Paving is WGL/CGI work involving ticket 88858.",
            },
        ],
        blocked_context=[
            {"title": "Stale", "content": "Malcolm Allendoerfer is related to James."}
        ],
        rules=[jade_memory_router.KNOWLEDGE_GRAPH_AUTHORITY_RULE],
        entities={
            "people": ["Malcolm Wrench"],
            "projects": ["Paving"],
            "tickets": ["88858"],
        },
        local_entity_query=True,
    )
    plan = ReasoningPlan(
        question="What do you know about Malcolm and paving?",
        intent="person",
        entities=bundle.entities,
        sources=["knowledge_graph"],
        retrieval_bundle=bundle,
    )

    JadeReasoner().answer(plan)

    assert "CGI Partner / Director, Consulting Expert" in captured["prompt"]
    assert "Paving is WGL/CGI work" in captured["prompt"]
    assert "Malcolm Allendoerfer" not in captured["prompt"]
    assert "Knowledge Graph is authoritative for local named people." in captured["prompt"]
    assert "Do not infer family relationships from last names." in captured["prompt"]
    assert captured["allow_tools"] is False
    assert captured["intent_override"] == "person"


def test_missing_local_person_memory_never_calls_generic_answer(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs):
        raise AssertionError("generic answer path should not be called")

    monkeypatch.setattr(jade_reasoner, "answer_with_brain", fail_if_called)
    plan = ReasoningPlan(
        question="What do you know about Unknown Person?",
        intent="person",
        entities={"people": ["Unknown Person"], "projects": [], "tickets": []},
        sources=["memory"],
        evidence={"local_memory_available": False, "results": {}},
    )

    result = JadeReasoner().answer(plan)

    assert result["answer"].startswith("I don’t have enough local memory.")
