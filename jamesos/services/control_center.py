from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services import asset_library, brand_registry, comfyui_client, creative_studio, image_worker, job_queue, model_registry, prompt_library, server_config, style_registry, workflow_manager
from jamesos.services.knowledge_graph import GRAPH_FILE, GRAPH_REPORT


REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Control Center.md"


def now_timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _path_check(path: Path) -> dict[str, Any]:
    return {"path": str(path), "exists": path.exists()}


def _safe_call(default: dict[str, Any], callback) -> dict[str, Any]:
    try:
        return callback()
    except Exception as exc:
        result = dict(default)
        result["status"] = "degraded"
        result["error"] = str(exc)
        return result


def queue_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for status in ["pending", "in_progress", "processed", "failed"]:
        try:
            counts[status] = len(job_queue.list_jobs(status))
        except Exception:
            counts[status] = 0
    return counts


def approval_needed_jobs(limit: int = 10) -> list[dict[str, Any]]:
    try:
        all_jobs = job_queue.list_jobs()
    except Exception:
        return []
    approval_needed = [
        job for job in all_jobs
        if job.get("requires_approval") and not job.get("approved") and job.get("status") != "failed"
    ]
    return [
        {
            "job_id": job.get("job_id"),
            "type": job.get("type"),
            "status": job.get("status"),
            "priority": job.get("priority"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
        }
        for job in approval_needed[:limit]
    ]


def knowledge_graph_status() -> dict[str, Any]:
    node_count = 0
    edge_count = 0
    if GRAPH_FILE.exists():
        try:
            graph = json.loads(GRAPH_FILE.read_text(encoding="utf-8"))
            node_count = len(graph.get("nodes", []))
            edge_count = len(graph.get("edges", []))
        except Exception:
            pass
    return {
        "status": "ok" if GRAPH_FILE.exists() else "missing",
        "graph_file": _path_check(GRAPH_FILE),
        "report": _path_check(GRAPH_REPORT),
        "node_count": node_count,
        "edge_count": edge_count,
    }


def storage() -> dict[str, Any]:
    paths = {
        "JamesOSData": VAULT,
        "KnowledgeGraph": VAULT / "JamesOS" / "Brain",
        "CreativeStudio": VAULT / "JamesOS" / "CreativeStudio",
        "Queue": VAULT / "JamesOS" / "Queue",
        "Reports": VAULT / "JamesOS" / "Reports",
        "Phone": VAULT / "JamesOS" / "Phone",
        "Email": VAULT / "JamesOS" / "Brain" / "Email",
        "ChatGPT": VAULT / "JamesOS" / "Brain" / "ChatGPT",
    }
    return {"status": "ok", "paths": {name: _path_check(path) for name, path in paths.items()}}


def gpu_comfyui_readiness() -> dict[str, Any]:
    creative = _safe_call({"status": "degraded"}, creative_studio.health)
    configured_api_url = creative.get("comfyui_api_url", "http://127.0.0.1:8188")
    if configured_api_url == "http://localhost:8188":
        configured_api_url = "http://127.0.0.1:8188"
    max_jobs = int(creative.get("max_concurrent_image_jobs", 1) or 1)
    comfy = _safe_call({"status": "not_running", "running": False}, lambda: comfyui_client.health(configured_api_url, timeout=0.5))
    registry = _safe_call({"present": False}, model_registry.health)
    workflows = _safe_call({"workflows": {}}, workflow_manager.list_workflows)
    workflow_inventory = workflows.get("discovered_inventory", {})
    workflow_summary = workflow_inventory.get("summary", {})
    return {
        "configured_api_url": configured_api_url,
        "running": bool(comfy.get("running", False)),
        "comfyui_status": comfy.get("status", "not_running"),
        "selected_install_path": comfy.get("install_path", {}),
        "model_registry_present": bool(registry.get("present", False)),
        "workflow_registry_present": bool(workflows.get("workflows")),
        "workflow_count": int(workflow_summary.get("total", 0) or 0),
        "workflow_types": workflow_summary.get("by_type", {}),
        "missing_recommended_workflows": workflow_summary.get("missing_recommended_workflows", []),
        "discovered_model_count": int(registry.get("discovered_model_count", 0) or 0),
        "checkpoint_count": int(registry.get("checkpoint_count", 0) or 0),
        "lora_count": int(registry.get("lora_count", 0) or 0),
        "upscaler_count": int(registry.get("upscaler_count", 0) or 0),
        "missing_recommended_categories": registry.get("missing_recommended_categories", []),
        "max_concurrent_image_jobs": max_jobs,
        "one_image_job_at_a_time": max_jobs == 1,
        "execution_enabled": False,
        "image_execution_enabled": False,
        "image_execution_available_only_when_approved": True,
        "running_image_job_count": image_worker.running_image_job_count(),
        "last_generated_image_path": image_worker.last_generated_image_path(),
        "status": "running" if comfy.get("running") else "configured_not_running",
        "notes": "Control Center reports readiness only; JamesOS does not execute ComfyUI yet.",
    }


def integrations() -> dict[str, Any]:
    configured = _safe_call({"status": "degraded", "integrations": []}, server_config.integration_health)
    integration_rows = {
        item.get("name"): item for item in configured.get("integrations", [])
    }
    comfyui = gpu_comfyui_readiness()
    rows = {
        "comfyui": {
            "name": "comfyui",
            "status": "configured_not_running",
            "configured": True,
            "execution_enabled": False,
            "publish_enabled": False,
            "image_execution_enabled": False,
            "configured_api_url": comfyui["configured_api_url"],
            "running": comfyui["running"],
            "selected_install_path": comfyui["selected_install_path"],
            "model_registry_present": comfyui["model_registry_present"],
            "workflow_registry_present": comfyui["workflow_registry_present"],
            "workflow_count": comfyui["workflow_count"],
            "workflow_types": comfyui["workflow_types"],
            "missing_recommended_workflows": comfyui["missing_recommended_workflows"],
            "discovered_model_count": comfyui["discovered_model_count"],
            "checkpoint_count": comfyui["checkpoint_count"],
            "lora_count": comfyui["lora_count"],
            "upscaler_count": comfyui["upscaler_count"],
            "missing_recommended_categories": comfyui["missing_recommended_categories"],
            "one_image_job_at_a_time": comfyui["one_image_job_at_a_time"],
            "image_execution_available_only_when_approved": comfyui["image_execution_available_only_when_approved"],
            "running_image_job_count": comfyui["running_image_job_count"],
            "last_generated_image_path": comfyui["last_generated_image_path"],
            "gpu_target": integration_rows.get("comfyui", {}).get("gpu_target", "GTX 1080 Ti"),
            "notes": "Local image engine planned; execution remains disabled.",
        },
        "printify": {
            "name": "printify",
            "status": "not_configured",
            "configured": False,
            "execution_enabled": False,
            "publish_enabled": False,
            "notes": "Future draft-only target. No API calls are active.",
        },
        "etsy": {
            "name": "etsy",
            "status": "not_configured",
            "configured": False,
            "execution_enabled": False,
            "publish_enabled": False,
            "notes": "Future approval-gated sales platform. No live listings are active.",
        },
        "tasker_phone_ingestion": {
            "name": "tasker_phone_ingestion",
            "status": "planned",
            "configured": bool(integration_rows.get("tasker_phone_ingestion", {}).get("enabled", False)),
            "execution_enabled": False,
            "publish_enabled": False,
            "endpoint": "/phone-ingest",
            "notes": "Phone ingestion is planned/configurable through Tasker.",
        },
        "outlook_import": {
            "name": "outlook_import",
            "status": "available",
            "configured": True,
            "execution_enabled": False,
            "publish_enabled": False,
            "notes": "Email import/readiness is available as local evidence input.",
        },
    }
    return {
        "status": "ok",
        "integrations": rows,
        "gpu_comfyui_readiness": comfyui,
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


def jobs() -> dict[str, Any]:
    counts = queue_counts()
    approvals = approval_needed_jobs()
    return {
        "status": "ok",
        "queue_counts": counts,
        "approval_needed_count": len(approvals),
        "approval_needed_jobs": approvals,
    }


def services() -> dict[str, Any]:
    server = _safe_call({"status": "degraded"}, server_config.service_health)
    creative = _safe_call({"status": "degraded"}, creative_studio.health)
    brands = _safe_call({"status": "degraded", "brand_count": 0, "enabled_brand_count": 0}, brand_registry.brand_health)
    prompts = _safe_call({"status": "degraded", "template_count": 0}, prompt_library.load_prompt_templates)
    assets = _safe_call({"status": "degraded", "asset_count": 0}, asset_library.scan_assets)
    styles = _safe_call({"status": "degraded", "style_count": 0}, style_registry.list_styles)
    image = _safe_call({"status": "degraded", "execution_enabled": False}, image_worker.health)
    registry = _safe_call({"status": "degraded", "execution_enabled": False}, model_registry.health)
    workflows = _safe_call({"status": "degraded", "execution_enabled": False}, workflow_manager.list_workflows)
    comfy = _safe_call({"status": "not_running", "execution_enabled": False}, comfyui_client.health)
    kg = knowledge_graph_status()
    queue = jobs()
    return {
        "status": "ok",
        "services": {
            "api": {"status": "ok"},
            "job_queue": {
                "status": "ok",
                "queue_counts": queue["queue_counts"],
                "approval_needed_count": queue["approval_needed_count"],
            },
            "knowledge_graph": kg,
            "creative_studio": creative,
            "brand_registry": brands,
            "prompt_library": {
                "status": prompts.get("status", "ok"),
                "template_count": prompts.get("template_count", 0),
                "execution_enabled": False,
            },
            "asset_library": {
                "status": assets.get("status", "ok"),
                "asset_count": assets.get("asset_count", 0),
                "metadata_only": True,
                "execution_enabled": False,
            },
            "style_registry": {
                "status": styles.get("status", "ok"),
                "style_count": styles.get("style_count", 0),
                "execution_enabled": False,
            },
            "image_worker": image,
            "model_registry": registry,
            "workflow_manager": {
                "status": workflows.get("status", "ok"),
                "workflow_count": int(workflows.get("discovered_inventory", {}).get("summary", {}).get("total", 0) or 0),
                "workflow_types": workflows.get("discovered_inventory", {}).get("summary", {}).get("by_type", {}),
                "missing_recommended_workflows": workflows.get("discovered_inventory", {}).get("summary", {}).get("missing_recommended_workflows", []),
                "execution_enabled": False,
            },
            "comfyui_client": comfy,
            "server_config": server,
        },
    }


def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "safe": True,
        "api": {"status": "ok"},
        "jobs": jobs(),
        "integrations": {
            "comfyui_execution_enabled": False,
            "image_execution_enabled": False,
            "printify_execution_enabled": False,
            "etsy_execution_enabled": False,
            "publish_enabled": False,
        },
    }


def control_center() -> dict[str, Any]:
    summary = {
        "status": "ok",
        "updated_at": now_timestamp(),
        "health": health(),
        "services": services()["services"],
        "integrations": integrations(),
        "jobs": jobs(),
        "storage": storage(),
    }
    write_report(summary)
    summary["report"] = str(REPORT_PATH)
    return summary


def human_summary() -> dict[str, Any]:
    center = {
        "status": "ok",
        "updated_at": now_timestamp(),
        "services": services()["services"],
        "integrations": integrations(),
        "jobs": jobs(),
        "storage": storage(),
    }
    job_data = center["jobs"]
    counts = job_data.get("queue_counts", {})
    approval_jobs = job_data.get("approval_needed_jobs", [])
    service_data = center["services"]
    integration_data = center["integrations"].get("integrations", {})
    storage_data = center["storage"].get("paths", {})

    ready = [
        "JamesOS API is responding.",
        "Job Queue is available for approval-first automation.",
        "Creative Studio can create local draft jobs.",
        "Planner and worker foundations can describe work without executing it.",
    ]
    if service_data.get("knowledge_graph", {}).get("status") == "ok":
        ready.append("Knowledge Graph data is present.")

    needs_attention = []
    if service_data.get("knowledge_graph", {}).get("status") != "ok":
        needs_attention.append("Knowledge Graph data is missing or needs a rebuild.")
    if approval_jobs:
        needs_attention.append(f"{len(approval_jobs)} job(s) need James approval.")
    if not needs_attention:
        needs_attention.append("No immediate attention items found.")

    pending_approvals = [
        f"{job.get('type')} ({job.get('status')}) - {job.get('job_id')}"
        for job in approval_jobs
    ] or ["No jobs are waiting on approval."]

    active_count = counts.get("pending", 0) + counts.get("in_progress", 0)
    active_jobs = [
        f"{counts.get('pending', 0)} pending, {counts.get('in_progress', 0)} in progress, "
        f"{counts.get('processed', 0)} processed, {counts.get('failed', 0)} failed."
    ]

    integration_lines = []
    for name, item in integration_data.items():
        state = "ready for configuration" if item.get("configured") else "not configured"
        if item.get("execution_enabled"):
            state = "execution enabled"
        integration_lines.append(f"{name}: {item.get('status', state)}; external execution is disabled.")

    storage_lines = [
        f"{name}: {'present' if item.get('exists') else 'not found yet'}"
        for name, item in storage_data.items()
    ]

    next_actions = [
        "Review pending approvals before moving any job forward.",
        "Use Planner to turn requests into proposed jobs, then approve job creation explicitly.",
        "Rebuild the Knowledge Graph if local entity answers look stale.",
        "Keep ComfyUI, Printify, and Etsy execution disabled until their future phases are intentionally implemented.",
    ]
    if active_count == 0:
        next_actions.insert(0, "Create a draft-only Creative Studio pipeline when there is work to prepare.")

    return {
        "status": "ok",
        "sections": {
            "Overall status": "JamesOS is online and operating in approval-first mode.",
            "What is ready": ready,
            "What needs attention": needs_attention,
            "Pending approvals": pending_approvals,
            "Active jobs": active_jobs,
            "Integrations": integration_lines,
            "Storage": storage_lines,
            "Next suggested actions": next_actions,
        },
        "safety": {
            "comfyui_execution_enabled": False,
            "image_execution_enabled": False,
            "printify_execution_enabled": False,
            "etsy_execution_enabled": False,
            "publish_enabled": False,
            "order_enabled": False,
            "send_enabled": False,
        },
    }


def write_report(summary: dict[str, Any] | None = None) -> dict[str, Any]:
    data = summary or {
        "status": "ok",
        "updated_at": now_timestamp(),
        "services": services()["services"],
        "integrations": integrations(),
        "jobs": jobs(),
        "storage": storage(),
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    job_data = data.get("jobs", {})
    integration_data = data.get("integrations", {})
    lines = [
        "# Control Center",
        "",
        f"Updated: {data.get('updated_at', now_timestamp())}",
        f"Status: {data.get('status', 'ok')}",
        "",
        "## Services",
        "",
    ]
    for name, item in data.get("services", {}).items():
        lines.append(f"- {name}: {item.get('status', 'unknown')}")

    lines.extend(["", "## Job Queue", ""])
    for status, count in job_data.get("queue_counts", {}).items():
        lines.append(f"- {status}: {count}")
    lines.append(f"- approval needed: {job_data.get('approval_needed_count', 0)}")

    lines.extend(["", "## Integrations", ""])
    for name, item in integration_data.get("integrations", {}).items():
        lines.append(
            f"- {name}: {item.get('status', 'unknown')}, "
            f"execution_enabled={item.get('execution_enabled', False)}"
        )

    lines.extend([
        "",
        "## Safety",
        "",
        "- ComfyUI execution is disabled.",
        "- Printify execution is disabled.",
        "- Etsy execution is disabled.",
        "- Publishing, ordering, and sending are disabled.",
        "- Approval-first automation is required.",
        "",
    ])
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "report": str(REPORT_PATH)}
