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
    "unitystitches_worker": {
        "name": "unitystitches_worker",
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
