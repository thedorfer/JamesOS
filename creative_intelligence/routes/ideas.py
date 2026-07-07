from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from creative_intelligence.services.niche_service import suggest_niches
from creative_intelligence.services.scoring_service import rank_candidates

router = APIRouter(prefix="/ideas", tags=["creative-intelligence-ideas"])


class IdeaRequest(BaseModel):
    query: str = ""
    limit: int = 8


@router.post("/generate")
def generate_ideas(request: IdeaRequest) -> dict[str, object]:
    ideas = rank_candidates(suggest_niches(request.query, limit=request.limit))
    return {"ideas": ideas}

