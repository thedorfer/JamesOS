from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT
from jamesos.services.job_queue import (
    JobQueueError,
    append_job_log,
    approve_job as approve_queue_job,
    create_job,
    fail_job as fail_queue_job,
    get_job,
    list_jobs,
    mark_step,
)


CONFIG_PATH = VAULT / "JamesOS" / "Config" / "creative_studio.yaml"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Creative Studio.md"

SAFE_JOB_TYPES = {
    "creative_pipeline",
    "creative_image_generation",
    "creative_product_draft",
    "creative_mockup",
    "creative_social_post",
}

PIPELINE_STAGES = [
    "idea",
    "prompt",
    "image",
    "mockup",
    "listing",
    "review",
    "printify_draft",
    "etsy_review",
    "complete",
]

DISABLED_EXTERNAL_STAGES = {"image", "mockup", "printify_draft", "etsy_review", "complete"}

DEFAULT_CONFIG = {
    "enabled": True,
    "image_provider": "comfyui",
    "comfyui_api_url": "http://localhost:8188",
    "require_approval": True,
    "max_concurrent_image_jobs": 1,
    "output_root": "~/JamesOSData/JamesOS/CreativeStudio",
    "generated_root": "~/JamesOSData/JamesOS/CreativeStudio/Generated",
    "assets_root": "~/JamesOSData/JamesOS/CreativeStudio/Assets",
    "jobs_root": "~/JamesOSData/JamesOS/CreativeStudio/Jobs",
    "templates_root": "~/JamesOSData/JamesOS/CreativeStudio/Templates",
}


def _expand_path(value: str) -> Path:
    return Path(value).expanduser()


def initialize_config() -> dict[str, Any]:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
        created = True
    cfg = load_config()
    ensure_directories(cfg)
    write_report()
    return {"status": "ok", "created": created, "config_path": str(CONFIG_PATH)}


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
    try:
        loaded = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    return {**DEFAULT_CONFIG, **loaded}


def ensure_directories(config: dict[str, Any] | None = None) -> None:
    cfg = config or load_config()
    for key in ["output_root", "generated_root", "assets_root", "jobs_root", "templates_root"]:
        _expand_path(str(cfg[key])).mkdir(parents=True, exist_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)


def health() -> dict[str, Any]:
    cfg = load_config()
    ensure_directories(cfg)
    creative_jobs = list_creative_jobs()
    checks = {
        key: {
            "path": str(_expand_path(str(cfg[key]))),
            "exists": _expand_path(str(cfg[key])).exists(),
        }
        for key in ["output_root", "generated_root", "assets_root", "jobs_root", "templates_root"]
    }
    if not REPORT_PATH.exists():
        write_report()
    return {
        "status": "ok",
        "enabled": bool(cfg.get("enabled", True)),
        "image_provider": cfg.get("image_provider", "comfyui"),
        "comfyui_api_url": cfg.get("comfyui_api_url", ""),
        "require_approval": bool(cfg.get("require_approval", True)),
        "max_concurrent_image_jobs": int(cfg.get("max_concurrent_image_jobs", 1)),
        "safe": True,
        "external_execution_enabled": False,
        "comfyui_execution_enabled": False,
        "printify_execution_enabled": False,
        "etsy_execution_enabled": False,
        "publishing_enabled": False,
        "ordering_enabled": False,
        "supported_job_types": sorted(SAFE_JOB_TYPES),
        "pipeline_stages": PIPELINE_STAGES,
        "job_count": len(creative_jobs),
        "checks": checks,
        "report": str(REPORT_PATH),
    }


def _creative_payload(job_type: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    if job_type not in SAFE_JOB_TYPES:
        raise JobQueueError(f"Unsupported Creative Studio job type: {job_type}")
    return {
        "creative_studio": True,
        "creative_status": "needs_review",
        "draft_only": True,
        "approval_required": True,
        "external_execution": False,
        "comfyui_execution": False,
        "printify_execution": False,
        "etsy_execution": False,
        "publish": False,
        "order": False,
        "send": False,
        "job_type": job_type,
        "details": payload or {},
    }


def _stage_notes(stage: str) -> str:
    notes = {
        "idea": "Capture the product or creative concept.",
        "prompt": "Prepare draft prompts without sending them to an image engine.",
        "image": "Future ComfyUI stage. Disabled in this phase.",
        "mockup": "Future mockup stage. Disabled in this phase.",
        "listing": "Prepare local listing copy only.",
        "review": "James reviews the local draft.",
        "printify_draft": "Future Printify draft stage. Disabled in this phase.",
        "etsy_review": "Future Etsy review stage. Disabled in this phase.",
        "complete": "Completion requires approved prior stages; no automation completes externally.",
    }
    return notes.get(stage, "Pipeline stage placeholder.")


def _pipeline_stage_records() -> list[dict[str, Any]]:
    return [
        {
            "name": stage,
            "status": "placeholder_disabled" if stage in DISABLED_EXTERNAL_STAGES else "pending",
            "requires_approval": stage in {"image", "mockup", "listing", "printify_draft", "etsy_review", "complete"},
            "execution_enabled": False,
            "notes": _stage_notes(stage),
        }
        for stage in PIPELINE_STAGES
    ]


def create_creative_job(
    job_type: str,
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 5,
) -> dict[str, Any]:
    cfg = load_config()
    ensure_directories(cfg)
    job = create_job(
        job_type,
        _creative_payload(job_type, payload),
        priority=priority,
        requires_approval=bool(cfg.get("require_approval", True)),
        steps=["draft", "review", "approval"],
    )
    mark_creative_job_needs_review(job["job_id"])
    write_report()
    return get_job(job["job_id"])


def create_pipeline(
    payload: dict[str, Any] | None = None,
    *,
    priority: int = 5,
) -> dict[str, Any]:
    cfg = load_config()
    ensure_directories(cfg)
    pipeline_payload = _creative_payload("creative_pipeline", payload)
    pipeline_payload.update({
        "pipeline": True,
        "pipeline_status": "needs_review",
        "stages": _pipeline_stage_records(),
        "disabled_external_stages": sorted(DISABLED_EXTERNAL_STAGES),
    })
    job = create_job(
        "creative_pipeline",
        pipeline_payload,
        priority=priority,
        requires_approval=bool(cfg.get("require_approval", True)),
        steps=[
            {
                "name": stage,
                "status": "blocked" if stage in DISABLED_EXTERNAL_STAGES else "pending",
            }
            for stage in PIPELINE_STAGES
        ],
    )
    mark_step(job["job_id"], "review", "needs_review", "Creative pipeline requires James review.")
    append_job_log(job["job_id"], "Creative pipeline shell created. External execution remains disabled.")
    write_report()
    return get_pipeline(job["job_id"])


def create_sample_image_job() -> dict[str, Any]:
    return create_creative_job(
        "creative_image_generation",
        {
            "title": "Sample image generation placeholder",
            "prompt": "Draft-only placeholder prompt. Do not execute ComfyUI yet.",
            "negative_prompt": "No external execution.",
        },
    )


def create_sample_product_job() -> dict[str, Any]:
    return create_creative_job(
        "creative_product_draft",
        {
            "title": "Sample product draft placeholder",
            "product_line": "Commerce Shop",
            "notes": "Draft-only product package placeholder. Do not call Printify or Etsy.",
        },
    )


def _is_creative_job(job: dict[str, Any]) -> bool:
    payload = job.get("payload", {})
    return bool(payload.get("creative_studio")) or job.get("type") in SAFE_JOB_TYPES


def _is_pipeline_job(job: dict[str, Any]) -> bool:
    payload = job.get("payload", {})
    return bool(payload.get("pipeline")) or job.get("type") == "creative_pipeline"


def list_creative_jobs(status: str | None = None) -> list[dict[str, Any]]:
    return [job for job in list_jobs(status) if _is_creative_job(job)]


def get_creative_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if not _is_creative_job(job):
        raise JobQueueError(f"Job is not a Creative Studio job: {job_id}")
    return job


def list_pipelines(status: str | None = None) -> list[dict[str, Any]]:
    return [job for job in list_creative_jobs(status) if _is_pipeline_job(job)]


def get_pipeline(job_id: str) -> dict[str, Any]:
    job = get_creative_job(job_id)
    if not _is_pipeline_job(job):
        raise JobQueueError(f"Job is not a Creative Studio pipeline: {job_id}")
    return job


def mark_creative_job_needs_review(job_id: str) -> dict[str, Any]:
    mark_step(job_id, "review", "needs_review", "Creative Studio draft requires James review.")
    append_job_log(job_id, "Creative job marked needs_review")
    job = get_creative_job(job_id)
    payload = job.setdefault("payload", {})
    payload["creative_status"] = "needs_review"
    # mark_step/append_job_log write the job; preserve review state through another log entry.
    append_job_log(job_id, "Creative status: needs_review")
    write_report()
    return get_creative_job(job_id)


def approve_creative_job(job_id: str) -> dict[str, Any]:
    job = get_creative_job(job_id)
    if not _is_creative_job(job):
        raise JobQueueError(f"Job is not a Creative Studio job: {job_id}")
    approve_queue_job(job_id)
    mark_step(job_id, "approval", "approved", "Approved for the next local draft step only.")
    append_job_log(job_id, "Creative job approved. External execution remains disabled.")
    write_report()
    return get_creative_job(job_id)


def fail_creative_job(job_id: str, reason: str = "") -> dict[str, Any]:
    job = get_creative_job(job_id)
    if not _is_creative_job(job):
        raise JobQueueError(f"Job is not a Creative Studio job: {job_id}")
    failed = fail_queue_job(job_id, reason)
    write_report()
    return failed


def write_report() -> dict[str, Any]:
    cfg = load_config()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    jobs = list_creative_jobs()
    lines = [
        "# Creative Studio",
        "",
        f"Enabled: {bool(cfg.get('enabled', True))}",
        f"Image provider: {cfg.get('image_provider', 'comfyui')}",
        f"Approval required: {bool(cfg.get('require_approval', True))}",
        "",
        "## Pipeline Shell",
        "",
        "Stages:",
        *[f"- {stage}" for stage in PIPELINE_STAGES],
        "",
        "Disabled placeholders:",
        "- ComfyUI image generation stage",
        "- Printify draft stage",
        "- Etsy review/listing stage",
        "",
        "## Safety",
        "",
        "- No ComfyUI execution is active.",
        "- No Printify calls are active.",
        "- No Etsy calls are active.",
        "- No publishing, ordering, or sending is active.",
        "- Creative jobs are draft-only and require James review.",
        "",
        "## Jobs",
        "",
    ]
    if not jobs:
        lines.append("- None")
    for job in jobs[:50]:
        payload = job.get("payload", {})
        pipeline = " pipeline=true" if payload.get("pipeline") else ""
        lines.append(
            f"- `{job.get('job_id')}` {job.get('type')} "
            f"status={job.get('status')} creative_status={payload.get('creative_status', 'unknown')} "
            f"approved={job.get('approved')}{pipeline}"
        )
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    return {"status": "ok", "report": str(REPORT_PATH), "job_count": len(jobs)}


def creative_studio_status() -> dict[str, Any]:
    return health()
