from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from creative_intelligence.services.prompt_service import generate_prompt, generate_prompts

router = APIRouter(prefix="/prompts", tags=["creative-intelligence-prompts"])


class PromptRequest(BaseModel):
    idea: str
    style: str = "clean commercial illustration"
    product_type: str = "print-on-demand product"


class PromptBatchRequest(BaseModel):
    ideas: list[str]
    product_type: str = "print-on-demand product"


@router.post("/generate")
def generate_one_prompt(request: PromptRequest) -> dict[str, object]:
    return {"prompt": generate_prompt(request.idea, style=request.style, product_type=request.product_type)}


@router.post("/batch")
def generate_prompt_batch(request: PromptBatchRequest) -> dict[str, object]:
    return {"prompts": generate_prompts(request.ideas, product_type=request.product_type)}

