from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from creative_intelligence.services.trend_service import analyze_trends

router = APIRouter(prefix="/trends", tags=["creative-intelligence-trends"])


class TrendRequest(BaseModel):
    query: str = ""
    limit: int = 10


@router.get("")
def get_trends(query: str = "", limit: int = 10) -> dict[str, object]:
    return {"trends": analyze_trends(query, limit=limit)}


@router.post("/analyze")
def post_trends(request: TrendRequest) -> dict[str, object]:
    return {"trends": analyze_trends(request.query, limit=request.limit)}

