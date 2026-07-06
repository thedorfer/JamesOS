from jamesos.services import jade_reasoner
from jamesos.services.jade_brain import PAVING_TICKETS, detect_query_entities
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

    monkeypatch.setattr(
        jade_reasoner,
        "gather_context",
        lambda question, intent, sources: {
            "people": ["Malcolm Wrench"],
            "projects": ["Paving"],
            "tickets": list(PAVING_TICKETS),
            "results": {},
        },
    )

    def fake_load(entity_type: str, name: str):
        calls.append((entity_type, name))
        available = {
            ("people", "Malcolm"),
            ("people", "Wrench, Malcolm R"),
            ("projects", "Paving"),
            *(("tickets", ticket) for ticket in PAVING_TICKETS),
        }
        if (entity_type, name) in available:
            return {"status": "ok", "content": f"local {entity_type}: {name}"}
        return {"status": "missing"}

    monkeypatch.setattr(jade_reasoner, "load_entity_page", fake_load)

    plan = JadeReasoner().understand(
        "What do you know about Malcolm and paving from my email and memory?"
    )

    titles = [item["title"] for item in plan.evidence["results"]["memory_v2"]]
    assert "Malcolm" in titles
    assert "Malcolm Wrench" in titles
    assert "Paving" in titles
    assert set(PAVING_TICKETS) <= set(titles)
    assert ("people", "Wrench, Malcolm R") in calls


def test_memory_pages_are_inserted_into_prompt_and_tools_are_disabled(monkeypatch) -> None:
    captured = {}

    def fake_answer(question, use_ai=True, allow_tools=True, intent_override=None):
        captured.update(
            question=question,
            allow_tools=allow_tools,
            intent_override=intent_override,
        )
        return {"answer": "Local answer", "confidence": 90}

    monkeypatch.setattr(jade_reasoner, "answer_with_brain", fake_answer)
    plan = ReasoningPlan(
        question="What do you know about Malcolm and paving?",
        intent="person",
        entities={"people": ["Malcolm Wrench"], "projects": ["Paving"], "tickets": []},
        sources=["memory"],
        evidence={
            "local_memory_available": True,
            "results": {
                "memory_v2": [
                    {
                        "title": "Malcolm Wrench",
                        "content": "Malcolm helped test paving ticket 88858.",
                    }
                ]
            },
        },
    )

    JadeReasoner().answer(plan)

    assert "Malcolm helped test paving ticket 88858." in captured["question"]
    assert "Use JamesOS Knowledge Graph first." in captured["question"]
    assert "Use only JamesOS memory for named people" in captured["question"]
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
