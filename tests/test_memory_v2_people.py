import json

from jamesos.services import memory_v2
from jamesos.services.memory_v2 import (
    KNOWLEDGE_GRAPH_ROOT,
    _build_person_page,
    _build_project_page,
    _normalize_person,
    _promoted_people,
)


def test_promoted_people_respects_known_threshold_and_manual_context() -> None:
    counts = {
        "One Off": 1,
        "Frequent Contact": 5,
        "Manual Contact": 1,
    }

    promoted = _promoted_people(
        contact_counts=counts,
        memory_people=set(),
        threshold=5,
        include_all_contacts=False,
        promotion_context="manual contact is assigned to the paving project",
    )

    assert {"James", "Jidapa", "Malcolm", "Kevin", "Tom", "Ian", "Luke", "Heather"} <= promoted
    assert "Frequent Contact" in promoted
    assert "Manual Contact" in promoted
    assert "One Off" not in promoted


def test_include_all_contacts_is_explicit_opt_in() -> None:
    contacts = {"One Off": 1, "Another One Off": 1}

    default_promoted = _promoted_people(
        contact_counts=contacts,
        memory_people=set(),
        threshold=5,
        include_all_contacts=False,
        promotion_context="",
    )
    all_promoted = _promoted_people(
        contact_counts=contacts,
        memory_people=set(),
        threshold=5,
        include_all_contacts=True,
        promotion_context="",
    )

    assert not contacts.keys() <= default_promoted
    assert contacts.keys() <= all_promoted


def test_health_reports_people_promotion_counts(tmp_path, monkeypatch) -> None:
    people = tmp_path / "People"
    people.mkdir()
    stats_path = tmp_path / "people_stats.json"
    contacts_path = tmp_path / "contacts_index.jsonl"
    stats_path.write_text(
        json.dumps(
            {
                "promoted_people_count": 12,
                "raw_contact_count": 40,
                "suppressed_contact_count": 28,
            }
        ),
        encoding="utf-8",
    )
    contacts_path.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr(memory_v2, "PEOPLE_DIR", people)
    monkeypatch.setattr(memory_v2, "PEOPLE_STATS_PATH", stats_path)
    monkeypatch.setattr(memory_v2, "CONTACTS_INDEX_PATH", contacts_path)

    result = memory_v2.health()

    assert result["promoted_people_count"] == 12
    assert result["raw_contact_count"] == 40
    assert result["suppressed_contact_count"] == 28


def test_person_normalization_removes_wrapping_quotes() -> None:
    assert _normalize_person("'Volkoff, Eugene'") == "Volkoff, Eugene"


def test_knowledge_graph_uses_new_root() -> None:
    assert KNOWLEDGE_GRAPH_ROOT.name == "KnowledgeGraph"


def test_malcolm_and_paving_pages_are_synthesized_without_todos() -> None:
    sources = [
        {
            "title": "FD for the Paving Order Creation",
            "source_type": "outlook_email",
            "path": "/evidence/paving.md",
            "snippet": "Malcolm Wrench sent the Functional Definition for Paving Order Creation.",
            "date_sent": "2026-02-10T21:46:58+00:00",
            "people": ["Malcolm Wrench", "Ian Wilkinson", "Kevin Bates"],
            "projects": ["Paving"],
            "tickets": ["88858"],
            "terms": ["WGL", "CGI"],
        }
    ]

    person = _build_person_page("Malcolm Wrench", sources)
    project = _build_project_page("Paving", sources)

    assert "Director, Consulting Expert" in person
    assert "Functional Definition for Paving Order Creation" in person
    assert "Ian Wilkinson" in person
    assert "Kevin Bates" in person
    assert "## Evidence Summary" in person
    assert "## Source Links" in person
    assert "TODO" not in person
    assert "Malcolm Wrench" in project
    assert "88858" in project
    assert "TODO" not in project
