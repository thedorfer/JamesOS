from __future__ import annotations

from typing import Any


def pipeline_status() -> dict[str, Any]:
    return {
        "name": "UnityStitches Product Pipeline",
        "status": "roadmap_only",
        "draft_only": True,
        "approval_required": True,
        "active_capabilities": [],
        "future_capabilities": [
            "daily product draft generation",
            "local ComfyUI artwork generation",
            "Printify draft creation",
            "Etsy draft listing preparation",
            "sales intelligence",
        ],
        "safety": [
            "No Printify API calls in Phase 1.",
            "No Etsy API calls in Phase 1.",
            "No image generation in Phase 1.",
            "No publishing, ordering, sending, or live listings without James approval.",
        ],
    }


def generate_daily_product_drafts(*args: Any, **kwargs: Any) -> dict[str, Any]:
    return {
        "status": "not_implemented",
        "message": "UnityStitches product generation is planned for a later phase. No drafts were created.",
    }
