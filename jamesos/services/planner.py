from __future__ import annotations

from typing import Any


SUPPORTED_INTENTS = {
    "daily_product_generation",
    "creative_image_generation",
    "knowledge_graph_rebuild",
    "briefing_generation",
    "phone_ingestion_review",
}


def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "planner",
        "supported_intents": sorted(SUPPORTED_INTENTS),
        "executes_jobs": False,
        "approval_first": True,
    }


def normalize_intent(intent: str = "", prompt: str = "") -> str:
    value = (intent or "").strip().lower().replace(" ", "_").replace("-", "_")
    text = f"{value} {prompt}".lower()
    if value in SUPPORTED_INTENTS:
        return value
    if "commerce_shop" in text or "product" in text:
        return "daily_product_generation"
    if "image" in text or "art" in text or "prompt" in text:
        return "creative_image_generation"
    if "knowledge graph" in text or "graph" in text:
        return "knowledge_graph_rebuild"
    if "brief" in text or "briefing" in text:
        return "briefing_generation"
    if "phone" in text or "tasker" in text:
        return "phone_ingestion_review"
    return "briefing_generation"


def _job_for_intent(intent: str, payload: dict[str, Any]) -> dict[str, Any]:
    jobs = {
        "daily_product_generation": {
            "type": "creative_pipeline",
            "title": "Prepare Commerce Shop daily product draft pipeline",
            "payload": {"pipeline": "commerce_shop_daily_products", **payload},
            "steps": ["idea", "prompt", "image", "mockup", "listing", "review"],
        },
        "creative_image_generation": {
            "type": "creative_image_generation",
            "title": "Prepare creative image generation draft",
            "payload": {"draft_only": True, **payload},
            "steps": ["idea", "prompt", "review"],
        },
        "knowledge_graph_rebuild": {
            "type": "knowledge_graph_rebuild",
            "title": "Rebuild Knowledge Graph from local evidence",
            "payload": {"local_only": True, **payload},
            "steps": ["scan_evidence", "build_graph", "write_report"],
        },
        "briefing_generation": {
            "type": "briefing_generation",
            "title": "Generate evidence-backed briefing",
            "payload": {"evidence_required": True, **payload},
            "steps": ["collect_evidence", "draft_briefing", "review_sources"],
        },
        "phone_ingestion_review": {
            "type": "phone_ingestion_review",
            "title": "Review phone ingestion evidence",
            "payload": {"local_only": True, **payload},
            "steps": ["read_ingested_events", "summarize", "review"],
        },
    }
    return jobs[intent]


def create_plan(intent: str = "", prompt: str = "", payload: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_intent(intent, prompt)
    details = dict(payload or {})
    if prompt:
        details["prompt"] = prompt
    recommended = _job_for_intent(normalized, details)
    return {
        "status": "ok",
        "intent": normalized,
        "summary": f"Planner prepared a draft-only plan for {normalized.replace('_', ' ')}.",
        "requires_approval": True,
        "executes_jobs": False,
        "recommended_jobs": [recommended],
        "next_actions": [
            "Review the proposed job.",
            "Create an approval-gated Job Queue item only if James explicitly asks.",
            "Keep external execution disabled until a future approved phase.",
        ],
        "safety": {
            "approval_first": True,
            "comfyui_execution_enabled": False,
            "printify_execution_enabled": False,
            "etsy_execution_enabled": False,
            "publish_enabled": False,
            "order_enabled": False,
            "send_enabled": False,
        },
    }
