from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services import asset_library, comfyui_client, model_registry, prompt_library, style_registry, workflow_manager
from jamesos.services.brand_registry import get_brand, get_default_brand
from jamesos.services.job_queue import (
    JobQueueError,
    append_job_log,
    fail_job,
    get_job,
    list_jobs,
    mark_step,
    update_job_payload,
    update_job_status,
)


COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_FOLDER = VAULT / "JamesOS" / "AI" / "ComfyUI" / "Outputs"
GENERATED_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Generated"
LAST_IMAGE_PATH = VAULT / "JamesOS" / "CreativeStudio" / "Generated" / "last_image.txt"
EXECUTABLE_JOB_TYPES = {"image_generation", "creative_image_generation"}

SAFETY = {
    "draft_only": True,
    "execution_enabled": False,
    "requires_approval": True,
    "approval_gated": True,
    "one_image_job_at_a_time": True,
    "comfyui_execution_enabled": False,
    "printify_execution_enabled": False,
    "etsy_execution_enabled": False,
    "publishing_enabled": False,
    "order_fulfillment_enabled": False,
    "upload_enabled": False,
    "send_enabled": False,
}


def health() -> dict[str, Any]:
    registry_health = model_registry.health()
    workflows = workflow_manager.list_workflows()
    prompts = prompt_library.load_prompt_templates()
    styles = style_registry.list_styles()
    assets = asset_library.scan_assets()
    return {
        "status": "ok",
        "worker": "image_worker",
        "execution_enabled": False,
        "requires_approval": True,
        "comfyui_url": COMFYUI_URL,
        "model_registry_present": bool(registry_health.get("present")),
        "workflow_registry_present": bool(workflows.get("workflows")),
        "prompt_library_status": prompts.get("status"),
        "style_registry_status": styles.get("status"),
        "asset_count": assets.get("asset_count", 0),
        "image_execution_available_only_when_approved": True,
        "running_image_job_count": running_image_job_count(),
        "last_generated_image_path": last_generated_image_path(),
        "one_image_job_at_a_time": True,
        "safety": SAFETY,
    }


def running_image_job_count() -> int:
    return len([job for job in list_jobs("in_progress") if job.get("type") in EXECUTABLE_JOB_TYPES])


def last_generated_image_path() -> str:
    if LAST_IMAGE_PATH.exists():
        return LAST_IMAGE_PATH.read_text(encoding="utf-8").strip()
    return ""


def create_image_generation_plan(package: dict[str, Any]) -> dict[str, Any]:
    workflow = workflow_manager.choose_workflow_for_package(package)
    model = model_registry.choose_model_for_workflow(workflow)
    brand_id = str(package.get("brand_id") or get_default_brand().get("brand_id", "unitystitches"))
    brand = get_brand(brand_id)
    selected_prompt_template = prompt_library.select_prompt_template({**package, "workflow_type": workflow.get("type", "")})
    selected_style = style_registry.select_style(package)
    asset_suggestions = asset_library.suggest_assets({**package, "brand_id": brand_id, "style": selected_style.get("name", "")})
    output_folder = Path(str(package.get("output_folder") or OUTPUT_FOLDER)).expanduser()
    prompt = str(
        package.get("prompt")
        or package.get("design_prompt")
        or package.get("product_idea")
        or package.get("title")
        or ""
    )
    negative_prompt = str(
        package.get("negative_prompt")
        or "No copyrighted characters, no hateful symbols, no explicit content, no upload, no publishing."
    )
    return {
        "status": "planned",
        "job_type": "image_generation",
        "execution_enabled": False,
        "requires_approval": True,
        "comfyui_url": COMFYUI_URL,
        "selected_workflow": workflow,
        "selected_model": model,
        "selected_prompt_template": selected_prompt_template,
        "selected_style": selected_style,
        "brand_id": brand["brand_id"],
        "brand_name": brand["display_name"],
        "brand_voice": brand.get("brand_voice", ""),
        "asset_suggestions": asset_suggestions,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "output_folder": str(output_folder),
        "safety": SAFETY,
        "message": "Safe image generation plan only. ComfyUI workflow execution is disabled.",
    }


def plan(package: dict[str, Any]) -> dict[str, Any]:
    return create_image_generation_plan(package)


def _payload_details(job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    details = payload.get("details")
    if isinstance(details, dict):
        merged = {**details, **payload}
        merged["details"] = details
        return merged
    return payload


def _plan_from_job(job: dict[str, Any]) -> dict[str, Any]:
    payload = _payload_details(job)
    existing = payload.get("image_plan") or payload.get("plan")
    if isinstance(existing, dict):
        return existing
    return create_image_generation_plan(payload)


def _discovered_checkpoint(plan: dict[str, Any]) -> dict[str, Any]:
    selected = plan.get("selected_model") if isinstance(plan.get("selected_model"), dict) else {}
    if selected.get("path") or selected.get("local_path"):
        model_path = Path(str(selected.get("path") or selected.get("local_path"))).expanduser()
        if not model_path.exists():
            raise JobQueueError(f"Checkpoint model does not exist: {model_path}")
        return selected
    inventory = model_registry.load_model_inventory()
    for item in inventory.get("models", []):
        if item.get("category") == "checkpoints":
            model_path = Path(str(item.get("path") or item.get("local_path") or "")).expanduser()
            if not model_path.exists():
                continue
            return item
    raise JobQueueError("No discovered checkpoint is available in Model Registry inventory")


def _workflow_path(plan: dict[str, Any]) -> Path:
    workflow = plan.get("selected_workflow") if isinstance(plan.get("selected_workflow"), dict) else {}
    value = workflow.get("workflow_path") or workflow.get("path")
    if not value:
        raise JobQueueError("Image plan does not include a workflow path")
    path = Path(str(value)).expanduser()
    if not path.exists():
        raise JobQueueError(f"Workflow JSON does not exist: {path}")
    return path


def prepare_workflow_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    workflow_path = _workflow_path(plan)
    checkpoint = _discovered_checkpoint(plan)
    checkpoint_name = Path(str(checkpoint.get("path") or checkpoint.get("local_path") or checkpoint.get("name"))).name
    replacements = {
        "{{positive_prompt}}": str(plan.get("prompt") or ""),
        "{{negative_prompt}}": str(plan.get("negative_prompt") or ""),
        "{{checkpoint_name}}": checkpoint_name,
        "{{seed}}": str(plan.get("seed") or 1),
        "{{width}}": str(plan.get("width") or 1024),
        "{{height}}": str(plan.get("height") or 1024),
    }
    text = workflow_path.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise JobQueueError(f"Prepared workflow is not valid JSON: {exc}") from exc


def _save_images(job_id: str, images: list[dict[str, Any]]) -> list[str]:
    if not images:
        raise JobQueueError("ComfyUI completed without output images")
    folder = GENERATED_ROOT / date.today().isoformat() / job_id
    folder.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    for index, image in enumerate(images, start=1):
        filename = str(image.get("filename") or f"image-{index}.png")
        suffix = Path(filename).suffix or ".png"
        path = folder / f"{index:02d}-{Path(filename).stem}{suffix}"
        path.write_bytes(image.get("content") or b"")
        saved.append(str(path))
    LAST_IMAGE_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_IMAGE_PATH.write_text(saved[0], encoding="utf-8")
    return saved


def _update_unitystitches_draft(payload: dict[str, Any], image_path: str) -> None:
    draft_path = payload.get("unitystitches_draft_path") or payload.get("draft_path")
    if not draft_path:
        return
    path = Path(str(draft_path)).expanduser()
    if not path.exists():
        return
    data = json.loads(path.read_text(encoding="utf-8"))
    data.update({
        "design_image_path": image_path,
        "design_status": "image_generated",
        "printify_status": "ready_for_printify_review",
        "status": "image_ready_needs_review",
    })
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _creative_stage_updates(job_payload: dict[str, Any], image_path: str, image_paths: list[str]) -> dict[str, Any]:
    payload = dict(job_payload)
    payload["output_image_path"] = image_path
    payload["generated_assets"] = image_paths
    payload["comfyui_execution"] = False
    payload["printify_execution"] = False
    payload["etsy_execution"] = False
    payload["publish"] = False
    payload["order"] = False
    payload["send"] = False
    stages = payload.get("stages")
    if isinstance(stages, list):
        for stage in stages:
            if stage.get("name") == "image":
                stage["status"] = "complete"
                stage["execution_enabled"] = False
            if stage.get("name") in {"mockup", "listing"}:
                stage["status"] = "needs_review"
                stage["execution_enabled"] = False
    details = payload.get("details")
    if isinstance(details, dict):
        details["output_image_path"] = image_path
        details["generated_assets"] = image_paths
    return payload


def execute_approved_image_job(job_id: str) -> dict[str, Any]:
    job = get_job(job_id)
    if job.get("type") not in EXECUTABLE_JOB_TYPES:
        raise JobQueueError("Only image_generation or creative_image_generation jobs can execute")
    if job.get("status") == "processed":
        raise JobQueueError("Image job has already been processed")
    if not job.get("approved"):
        raise JobQueueError("Image job must be explicitly approved before execution")
    active = [item for item in list_jobs("in_progress") if item.get("type") in EXECUTABLE_JOB_TYPES and item.get("job_id") != job_id]
    if active:
        raise JobQueueError("Another image job is already in progress")
    if not comfyui_client.is_running(COMFYUI_URL, timeout=2.0):
        raise JobQueueError("ComfyUI is not running at http://127.0.0.1:8188")

    payload = _payload_details(job)
    try:
        append_job_log(job_id, "validation passed")
        mark_step(job_id, "validation", "complete", "Approved image job validation passed.")
        update_job_status(job_id, "in_progress")
        plan = _plan_from_job(get_job(job_id))
        workflow_json = prepare_workflow_from_plan(plan)
        append_job_log(job_id, "workflow prepared")
        mark_step(job_id, "workflow prepared", "complete")
        queued = comfyui_client.queue_prompt(workflow_json, api_url=COMFYUI_URL)
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise JobQueueError("ComfyUI did not return a prompt_id")
        append_job_log(job_id, "ComfyUI prompt queued")
        mark_step(job_id, "ComfyUI prompt queued", "complete", prompt_id)
        completed = comfyui_client.wait_for_completion(prompt_id, api_url=COMFYUI_URL)
        if completed.get("status") != "completed":
            raise JobQueueError(f"ComfyUI prompt did not complete: {completed.get('status')}")
        images = comfyui_client.get_output_images(prompt_id, api_url=COMFYUI_URL)
        saved = _save_images(job_id, images)
        image_path = saved[0]
        append_job_log(job_id, "image saved")
        mark_step(job_id, "image saved", "complete", image_path)
        original_payload = get_job(job_id).get("payload", {})
        update_job_payload(job_id, _creative_stage_updates(original_payload, image_path, saved))
        _update_unitystitches_draft(payload, image_path)
        append_job_log(job_id, "completed")
        mark_step(job_id, "completed", "complete")
        processed = update_job_status(job_id, "processed")
        return {
            "status": "ok",
            "job_id": job_id,
            "image_path": image_path,
            "image_paths": saved,
            "prompt_id": prompt_id,
            "job": processed,
            "execution_enabled": False,
            "printify_execution_enabled": False,
            "etsy_execution_enabled": False,
            "publish_enabled": False,
            "upload_enabled": False,
            "send_enabled": False,
        }
    except Exception as exc:
        try:
            fail_job(job_id, str(exc))
        except Exception:
            pass
        if isinstance(exc, JobQueueError):
            raise
        raise JobQueueError(str(exc)) from exc
