from fastapi import APIRouter, Header

from jamesos.core.api import require_key
from jamesos.services.unified_memory_search import (
    history_context,
    search_unified,
    memory_health,
)
from jamesos.services.knowledge_graph_service import (
    build_knowledge_graph,
    health as knowledge_graph_health,
    load_entity_page,
)

router = APIRouter()


@router.get("/memory/explore")
def memory_explore(q: str, limit: int = 10, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return search_unified(q, limit=limit)


@router.get("/memory/context")
def memory_context(q: str, limit: int = 8, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "context": history_context(q, limit=limit)}


@router.get("/memory/health")
def memory_health_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return memory_health()


@router.get("/memory-v2/health")
def memory_v2_health_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return knowledge_graph_health()


@router.post("/memory-v2/build")
def memory_v2_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return build_knowledge_graph()


@router.get("/memory-v2/entity")
def memory_v2_entity(type: str, name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return load_entity_page(type, name)


@router.get("/knowledge-graph/health")
def knowledge_graph_health_report(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return knowledge_graph_health()


@router.post("/knowledge-graph/build")
def knowledge_graph_build(x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return build_knowledge_graph()


@router.get("/knowledge-graph/entity")
def knowledge_graph_entity(type: str, name: str, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return load_entity_page(type, name)
