from __future__ import annotations

from fastapi import APIRouter

from creative_intelligence.services import etsy_readonly_service as etsy

router = APIRouter(prefix="/etsy", tags=["creative-intelligence-etsy-readonly"])


@router.get("/health")
def health() -> dict[str, object]:
    return etsy.health()


@router.get("/auth-status")
def auth_status() -> dict[str, object]:
    return etsy.auth_status()


@router.post("/sync-readonly")
def sync_readonly() -> dict[str, object]:
    return etsy.sync_readonly()


@router.get("/performance")
def performance() -> dict[str, object]:
    return etsy.get_performance_summary()


@router.get("/top-products")
def top_products(limit: int = 10) -> dict[str, object]:
    return etsy.get_top_products(limit=limit)


@router.get("/underperforming-products")
def underperforming_products(limit: int = 10) -> dict[str, object]:
    return etsy.get_underperforming_products(limit=limit)
