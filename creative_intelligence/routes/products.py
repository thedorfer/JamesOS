from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from creative_intelligence.services.product_service import build_product_plans

router = APIRouter(prefix="/products", tags=["creative-intelligence-products"])


class ProductPlanRequest(BaseModel):
    query: str = ""
    limit: int = 6


@router.post("/plan")
def plan_products(request: ProductPlanRequest) -> dict[str, object]:
    return {"products": build_product_plans(request.query, limit=request.limit)}

