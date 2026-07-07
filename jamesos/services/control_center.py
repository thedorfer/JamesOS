from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services import creative_studio, job_queue, server_config
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
    configured_api_url = creative.get("comfyui_api_url", "http://localhost:8188")
    max_jobs = int(creative.get("max_concurrent_image_jobs", 1) or 1)
    return {
        "configured_api_url": configured_api_url,
        "max_concurrent_image_jobs": max_jobs,
        "one_image_job_at_a_time": max_jobs == 1,
        "execution_enabled": False,
        "status": "configured_not_running",
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
            "configured_api_url": comfyui["configured_api_url"],
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
