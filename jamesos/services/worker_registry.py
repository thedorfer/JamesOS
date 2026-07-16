from __future__ import annotations

from typing import Any


WORKERS: dict[str, dict[str, Any]] = {
    "knowledge_graph_worker": {
        "name": "knowledge_graph_worker",
        "status": "planned",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["knowledge_graph_rebuild"],
        "safety_notes": "Can be wired to local graph rebuild jobs later; no worker execution is active.",
    },
    "creative_studio_worker": {
        "name": "creative_studio_worker",
        "status": "foundation",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": [
            "creative_pipeline",
            "creative_image_generation",
            "creative_product_draft",
            "creative_mockup",
            "creative_social_post",
        ],
        "safety_notes": "Creates and reviews local draft jobs only; no external execution is active.",
    },
    "comfyui_worker": {
        "name": "comfyui_worker",
        "status": "planned",
        "enabled": False,
        "execution_enabled": False,
        "supported_job_types": ["creative_image_generation"],
        "safety_notes": "Future local image worker. Must not call ComfyUI in this phase.",
    },
    "image_worker": {
        "name": "image_worker",
        "status": "foundation",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["image_generation", "creative_image_generation"],
        "safety_notes": "Plans local image generation jobs only. ComfyUI execution is disabled and approval-gated.",
    },
    "workflow_manager": {
        "name": "workflow_manager",
        "status": "foundation",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["workflow_selection", "workflow_validation"],
        "safety_notes": "Lists, validates, and selects workflows without executing them.",
    },
    "model_registry": {
        "name": "model_registry",
        "status": "foundation",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["model_lookup", "model_readiness"],
        "safety_notes": "Tracks local model placeholders and safety flags; models are disabled by default.",
    },
    "comfyui_client": {
        "name": "comfyui_client",
        "status": "health_only",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["comfyui_health_check"],
        "safety_notes": "Health and system_stats only. No prompt queue execution is implemented.",
    },
    "commerce_shop_worker": {
        "name": "commerce_shop_worker",
        "status": "planned",
        "enabled": False,
        "execution_enabled": False,
        "supported_job_types": ["creative_pipeline", "creative_product_draft"],
        "safety_notes": "Future draft package worker. Must remain draft-only and approval-gated.",
    },
    "printify_worker": {
        "name": "printify_worker",
        "status": "planned",
        "enabled": False,
        "execution_enabled": False,
        "supported_job_types": ["printify_draft"],
        "safety_notes": "Future draft target only. No Printify API calls, publishing, orders, or production sends.",
    },
    "etsy_worker": {
        "name": "etsy_worker",
        "status": "planned",
        "enabled": False,
        "execution_enabled": False,
        "supported_job_types": ["etsy_review"],
        "safety_notes": "Future Etsy review support only. No live listing creation or publishing.",
    },
    "phone_ingestion_worker": {
        "name": "phone_ingestion_worker",
        "status": "planned",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["phone_ingestion_review"],
        "safety_notes": "Reviews local phone evidence; no sending or external action.",
    },
    "briefing_worker": {
        "name": "briefing_worker",
        "status": "planned",
        "enabled": True,
        "execution_enabled": False,
        "supported_job_types": ["briefing_generation"],
        "safety_notes": "Future evidence-backed briefing worker. Must not invent facts.",
    },
}


def list_workers() -> dict[str, Any]:
    return {
        "status": "ok",
        "workers": [WORKERS[name] for name in sorted(WORKERS)],
        "external_execution_enabled": False,
    }


def get_worker(worker_name: str) -> dict[str, Any]:
    worker = WORKERS.get(worker_name)
    if worker is None:
        raise KeyError(f"Unknown worker: {worker_name}")
    return {"status": "ok", "worker": worker}


def can_execute(worker_name: str, job_type: str) -> bool:
    worker = WORKERS.get(worker_name)
    if not worker:
        return False
    return bool(
        worker.get("enabled")
        and worker.get("execution_enabled")
        and job_type in worker.get("supported_job_types", [])
    )
