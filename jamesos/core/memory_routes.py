from fastapi import APIRouter, Header

from jamesos.core.api import require_key
from jamesos.services.chatgpt_history_search import search_chatgpt_history, chatgpt_history_context

router = APIRouter()


@router.get("/memory/explore")
def memory_explore(q: str, limit: int = 10, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return search_chatgpt_history(q, limit=limit)


@router.get("/memory/context")
def memory_context(q: str, limit: int = 8, x_jamesos_key: str | None = Header(default=None)):
    require_key(x_jamesos_key)
    return {"status": "ok", "context": chatgpt_history_context(q, limit=limit)}
