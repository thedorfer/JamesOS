"""Synthesized Knowledge Graph service.

The implementation remains in memory_v2 for compatibility with existing imports.
"""

from jamesos.services.memory_v2 import (
    build_knowledge_graph_pages,
    knowledge_graph_health,
    load_entity_page,
)


def build_knowledge_graph(
    limit_per_entity: int = 6,
    people_threshold: int | None = None,
    include_all_contacts: bool = False,
):
    return build_knowledge_graph_pages(
        limit_per_entity=limit_per_entity,
        people_threshold=people_threshold,
        include_all_contacts=include_all_contacts,
    )


def health():
    return knowledge_graph_health()
