from __future__ import annotations

import json
import re
from datetime import date, datetime
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
    create_job,
)


COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_FOLDER = VAULT / "JamesOS" / "AI" / "ComfyUI" / "Outputs"
GENERATED_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Generated"
LAST_IMAGE_PATH = VAULT / "JamesOS" / "CreativeStudio" / "Generated" / "last_image.txt"
LAST_ERROR_PATH = VAULT / "JamesOS" / "CreativeStudio" / "Generated" / "last_image_error.json"
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


class ImageWorkerError(JobQueueError):
    def __init__(self, error_code: str, message: str, next_step: str, job_id: str = "", workflow_path: str = ""):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.next_step = next_step
        self.job_id = job_id
        self.workflow_path = workflow_path


def structured_error(exc: Exception, job_id: str = "", workflow_path: str = "") -> dict[str, Any]:
    return {
        "status": "error",
        "error_code": getattr(exc, "error_code", "image_execution_failed"),
        "message": getattr(exc, "message", str(exc)),
        "job_id": getattr(exc, "job_id", "") or job_id,
        "workflow_path": getattr(exc, "workflow_path", "") or workflow_path,
        "next_step": getattr(exc, "next_step", "Review the failed image job log and fix the job payload before retrying."),
        "execution_enabled": False,
        "printify_execution_enabled": False,
        "etsy_execution_enabled": False,
        "upload_enabled": False,
        "publish_enabled": False,
        "order_enabled": False,
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
        "last_image_generation_error": last_image_generation_error(),
        "routes": [
            "GET /image-worker/health",
            "POST /image-worker/plan",
            "POST /image-worker/create-test-job",
            "POST /image-worker/jobs/{job_id}/execute-approved",
        ],
        "one_image_job_at_a_time": True,
        "safety": SAFETY,
    }


def running_image_job_count() -> int:
    return len([job for job in list_jobs("in_progress") if job.get("type") in EXECUTABLE_JOB_TYPES])


def last_generated_image_path() -> str:
    if LAST_IMAGE_PATH.exists():
        return LAST_IMAGE_PATH.read_text(encoding="utf-8").strip()
    return ""


def last_image_generation_error() -> dict[str, Any]:
    if not LAST_ERROR_PATH.exists():
        return {}
    try:
        return json.loads(LAST_ERROR_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"status": "error", "error_code": "last_error_file_unreadable", "message": "Last image error file could not be read."}


def create_image_generation_plan(package: dict[str, Any]) -> dict[str, Any]:
    creative_spec = package.get("creative_spec") if isinstance(package.get("creative_spec"), dict) else None
    brand_id = str(package.get("brand_id") or (creative_spec or {}).get("brand_id") or get_default_brand().get("brand_id", "unitystitches"))
    brand = get_brand(brand_id)
    selected_style = style_registry.select_style(package)
    selected_assets = asset_library.suggest_assets({**package, "brand_id": brand_id, "style": selected_style.get("name", "")})
    if creative_spec:
        creative_spec = dict(creative_spec)
        if selected_assets and not creative_spec.get("selected_assets"):
            creative_spec["selected_assets"] = selected_assets
        recipe = creative_spec.get("design_recipe")
        if isinstance(recipe, dict) and selected_assets and not recipe.get("assets"):
            creative_spec["design_recipe"] = {**recipe, "assets": [asset.get("name") for asset in selected_assets if asset.get("name")]}
    prompt_package = prompt_library.creative_spec_to_prompt_package(creative_spec) if creative_spec else {}
    if prompt_package:
        package = {
            **package,
            "creative_spec": creative_spec,
            "prompt": prompt_package["positive_prompt"],
            "negative_prompt": prompt_package["negative_prompt"],
            "width": prompt_package["width"],
            "height": prompt_package["height"],
            "workflow_type": prompt_package["recommended_workflow_type"],
        }
    workflow = workflow_manager.choose_workflow_for_package(package)
    model = model_registry.choose_model_for_workflow(workflow)
    selected_prompt_template = prompt_library.select_prompt_template({**package, "workflow_type": workflow.get("type", "")})
    output_folder = Path(str(package.get("output_folder") or OUTPUT_FOLDER)).expanduser()
    prompt = str(
        package.get("prompt")
        or package.get("design_prompt")
        or package.get("product_idea")
        or package.get("title")
        or ""
    )
    is_mockup_stage = "mockup" in " ".join(str(package.get(key, "")) for key in ["stage", "workflow_type", "product_type", "design_prompt"]).lower()
    if prompt and not creative_spec and not is_mockup_stage:
        prompt = (
            "Standalone flat vector-style print artwork, no person, no human, no model, "
            "no clothing being worn, no room, no lifestyle photo, no product mockup, "
            "white or transparent-background-friendly background, centered layout, large readable text. "
            f"{prompt}"
        )
    negative_prompt = str(
        package.get("negative_prompt")
        or (
            "No copyrighted characters, no hateful symbols, no explicit content, no upload, no publishing."
            if is_mockup_stage
            else "No copyrighted characters, no hateful symbols, no explicit content, no upload, no publishing, person, human, model, girl, woman, man, child, face, hands, body, wearing, shirt on body, product photo, lifestyle photo, room, couch, bed, shelf, mannequin, portrait, photorealistic person, mockup, blurry text, misspelled text, watermark."
        )
    )
    return {
        "status": "planned",
        "job_type": "image_generation",
        "execution_enabled": False,
        "requires_approval": True,
        "comfyui_url": COMFYUI_URL,
        "selected_workflow": workflow,
        "requested_workflow_type": workflow.get("requested_workflow_type") or package.get("workflow_type") or "",
        "selected_workflow_type": workflow.get("selected_workflow_type") or workflow.get("type") or "",
        "workflow_alias_used": bool(workflow.get("workflow_alias_used")),
        "selected_model": model,
        "selected_prompt_template": selected_prompt_template,
        "selected_style": selected_style,
        "creative_spec": creative_spec or package.get("creative_spec") or {},
        "prompt_package": prompt_package,
        "brand_id": brand["brand_id"],
        "brand_name": brand["display_name"],
        "brand_voice": brand.get("brand_voice", ""),
        "asset_suggestions": selected_assets,
        "selected_assets": selected_assets,
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "output_folder": str(output_folder),
        "safety": SAFETY,
        "message": "Safe image generation plan only. ComfyUI workflow execution is disabled.",
    }


def plan(package: dict[str, Any]) -> dict[str, Any]:
    return create_image_generation_plan(package)


def _first_discovered_checkpoint() -> dict[str, Any]:
    inventory = model_registry.load_model_inventory()
    for model in inventory.get("models", []):
        if model.get("category") == "checkpoints" and Path(str(model.get("path") or "")).exists():
            return model
    raise JobQueueError("No discovered checkpoint found. Run /models/scan first.")


def _product_art_basic_workflow() -> dict[str, Any]:
    try:
        return workflow_manager.get_executable_workflow_template("print_design_basic")
    except KeyError as exc:
        raise JobQueueError("print_design_basic API workflow template not found. Recreate JamesOS workflow templates and retry.") from exc


def _default_design_recipe(width: int, height: int, provider: str = "printify") -> dict[str, Any]:
    return {
        "product_type": "design_art",
        "niche": "LGBTQ+ pride",
        "design_goal": "Create a joyful pride design that reads clearly on POD products.",
        "artwork_type": "flat print design",
        "background": "white or transparent-background-friendly",
        "layout": "centered",
        "palette": ["rainbow", "white", "black accent"],
        "text": "Love Is Love",
        "typography": "bold readable rounded sans",
        "motifs": ["hearts", "sparkles", "pride rainbow"],
        "assets": [],
        "effects": "clean vector-like print art",
        "provider": provider,
        "print_notes": "high contrast, readable at thumbnail size, no person, no mockup",
        "width": width,
        "height": height,
    }


def create_test_image_job(
    *,
    positive_prompt: str = "UnityStitches inclusive pride standalone print design, standalone flat vector-style print artwork, no person, no human, no model, no clothing being worn, no room, no lifestyle photo, no product mockup, white or transparent-background-friendly background, centered layout, large readable text, clean bold typography, print-ready graphic",
    negative_prompt: str = "copyrighted logos, trademarked characters, hateful symbols, explicit content, person, human, model, girl, woman, man, child, face, hands, body, wearing, shirt on body, product photo, lifestyle photo, room, couch, bed, shelf, mannequin, portrait, photorealistic person, mockup, blurry text, misspelled text, watermark",
    seed: int = 1,
    width: int = 768,
    height: int = 768,
    brand_id: str = "unitystitches",
    draft_path: str = "",
) -> dict[str, Any]:
    checkpoint = _first_discovered_checkpoint()
    workflow = _product_art_basic_workflow()
    provider = "printify"
    design_recipe = _default_design_recipe(width, height, provider)
    selected_assets = asset_library.suggest_assets({
        "brand_id": brand_id,
        "niche": design_recipe["niche"],
        "style": "pride",
        "product_type": design_recipe["product_type"],
        "title": design_recipe["text"],
    })
    if selected_assets:
        design_recipe["assets"] = [asset.get("name") for asset in selected_assets if asset.get("name")]
    creative_spec = {
        "brand_id": brand_id,
        "brand_name": "UnityStitches",
        "stage": "design_art",
        "product_type": "design_art",
        "niche": "LGBTQ+ pride",
        "audience": "inclusive gift shoppers and pride supporters",
        "emotional_hook": "joyful, affirming, printable pride",
        "style": "bold pride typography",
        "colors": ["rainbow", "white", "black accent"],
        "text": "Love Is Love",
        "typography": "bold readable sans with friendly rounded edges",
        "assets": [],
        "layout": "flat centered print artwork",
        "print_requirements": "standalone print design, white or transparent-background-friendly background, POD-safe, high contrast, large readable text, no product photo",
        "safety_notes": "no copyrighted logos, no trademarked characters, no explicit content, no person, no model, no mockup",
        "design_recipe": design_recipe,
        "selected_assets": selected_assets,
        "pod_provider": provider,
        "width": width,
        "height": height,
    }
    prompt_package = prompt_library.creative_spec_to_prompt_package(creative_spec)
    positive_prompt = positive_prompt or prompt_package["positive_prompt"]
    negative_prompt = negative_prompt or prompt_package["negative_prompt"]
    payload = {
        "creative_spec": creative_spec,
        "prompt_package": prompt_package,
        "checkpoint_name": Path(str(checkpoint["path"])).name,
        "checkpoint_path": checkpoint["path"],
        "workflow_name": workflow["name"],
        "workflow_path": workflow.get("workflow_path") or workflow.get("path"),
        "requested_workflow_type": "print_design_basic",
        "positive_prompt": positive_prompt,
        "negative_prompt": negative_prompt,
        "seed": seed,
        "width": width,
        "height": height,
        "brand_id": brand_id,
        "pod_provider": provider,
        "draft_path": draft_path,
        "selected_assets": selected_assets,
        "image_plan": {
            "selected_workflow": {
                "name": workflow["name"],
                "workflow_path": workflow.get("workflow_path") or workflow.get("path"),
                "path": workflow.get("path") or workflow.get("workflow_path"),
                "type": workflow.get("type", "print_design_basic"),
                "requested_workflow_type": "print_design_basic",
                "selected_workflow_type": workflow.get("type", "print_design_basic"),
                "workflow_alias_used": workflow.get("name") == "product_art_basic" or workflow.get("type") != "print_design_basic",
                "workflow_format": workflow.get("workflow_format", "comfyui_api_prompt"),
            },
            "requested_workflow_type": "print_design_basic",
            "selected_workflow_type": workflow.get("type", "print_design_basic"),
            "workflow_alias_used": workflow.get("name") == "product_art_basic" or workflow.get("type") != "print_design_basic",
            "selected_model": {
                "name": checkpoint["name"],
                "path": checkpoint["path"],
                "category": checkpoint.get("category", "checkpoints"),
                "family": checkpoint.get("family", "unknown"),
            },
            "prompt": positive_prompt,
            "negative_prompt": negative_prompt,
            "creative_spec": creative_spec,
            "prompt_package": prompt_package,
            "design_recipe": design_recipe,
            "selected_assets": selected_assets,
            "seed": seed,
            "width": width,
            "height": height,
            "brand_id": brand_id,
            "pod_provider": provider,
        },
        "execution_enabled": False,
        "auto_execute": False,
        "printify_execution_enabled": False,
        "etsy_execution_enabled": False,
        "publish_enabled": False,
        "upload_enabled": False,
        "send_enabled": False,
    }
    job = create_job(
        "image_generation",
        payload,
        requires_approval=True,
        steps=["validation", "workflow prepared", "ComfyUI prompt queued", "image saved", "completed"],
    )
    return {
        "status": "ok",
        "job": job,
        "execution_enabled": False,
        "auto_execute": False,
        "requires_approval": True,
    }


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
        creative_spec = existing.get("creative_spec") if isinstance(existing.get("creative_spec"), dict) else payload.get("creative_spec")
        if isinstance(creative_spec, dict) and not existing.get("prompt"):
            prompt_package = prompt_library.creative_spec_to_prompt_package(creative_spec)
            existing = {
                **existing,
                "prompt": prompt_package["positive_prompt"],
                "negative_prompt": prompt_package["negative_prompt"],
                "width": prompt_package["width"],
                "height": prompt_package["height"],
                "workflow_type": prompt_package["recommended_workflow_type"],
                "prompt_package": prompt_package,
            }
        return existing
    return create_image_generation_plan(payload)


def _discovered_checkpoint(plan: dict[str, Any]) -> dict[str, Any]:
    selected = plan.get("selected_model") if isinstance(plan.get("selected_model"), dict) else {}
    if selected.get("path") or selected.get("local_path"):
        model_path = Path(str(selected.get("path") or selected.get("local_path"))).expanduser()
        if not model_path.exists():
            raise ImageWorkerError("workflow_model_checkpoint_missing", f"Checkpoint model does not exist: {model_path}", "Run /models/scan and recreate the image job with a discovered checkpoint.")
        return selected
    inventory = model_registry.load_model_inventory()
    for item in inventory.get("models", []):
        if item.get("category") == "checkpoints":
            model_path = Path(str(item.get("path") or item.get("local_path") or "")).expanduser()
            if not model_path.exists():
                continue
            return item
    raise ImageWorkerError("workflow_model_checkpoint_missing", "No discovered checkpoint is available in Model Registry inventory", "Put a checkpoint in the model roots, run /models/scan, then recreate the image job.")


def _requested_workflow_type(plan: dict[str, Any]) -> str:
    workflow = plan.get("selected_workflow") if isinstance(plan.get("selected_workflow"), dict) else {}
    requested = str(
        plan.get("requested_workflow_type")
        or plan.get("workflow_type")
        or workflow.get("requested_workflow_type")
        or workflow.get("type")
        or "print_design_basic"
    )
    if requested == "product_art":
        return "print_design_basic"
    return requested


def _validate_prepared_workflow(prepared: Any, text: str) -> None:
    if re.search(r"\{\{[A-Za-z0-9_]+\}\}", text):
        raise ImageWorkerError("workflow_placeholder_not_replaced", "Prepared workflow still contains unreplaced placeholders.", "Check the workflow template placeholders and the image job payload.")
    if not isinstance(prepared, dict):
        raise ImageWorkerError("workflow_file_not_json", "Prepared workflow must be a ComfyUI API prompt JSON object.", "Export or create a ComfyUI API workflow JSON object.")
    if "creative_spec" in prepared or "image_plan" in prepared or "positive_prompt" in prepared:
        raise ImageWorkerError("workflow_is_jamesos_spec_not_comfyui_api_prompt", "Workflow file appears to be a JamesOS spec, not a ComfyUI API prompt.", "Use a ComfyUI API workflow JSON with numbered node IDs and class_type fields.")
    if isinstance(prepared.get("nodes"), list) or "last_node_id" in prepared or "links" in prepared:
        raise ImageWorkerError("workflow_is_comfyui_ui_format_export_api_needed", "Workflow file appears to be a ComfyUI UI workflow export, not an API prompt.", "In ComfyUI, save/export the API prompt JSON format for JamesOS execution.")
    nodes = [node for node in prepared.values() if isinstance(node, dict)]
    if not nodes or not any(node.get("class_type") for node in nodes):
        raise ImageWorkerError("workflow_missing_required_nodes", "Workflow is missing ComfyUI API nodes with class_type.", "Use a valid ComfyUI API prompt workflow containing loader, prompt, sampler, and save-image nodes.")
    validation = workflow_manager.validate_comfyui_api_prompt(prepared)
    if not validation.get("valid"):
        raise ImageWorkerError(str(validation.get("error_code") or "workflow_missing_required_nodes"), "Workflow is missing required built-in ComfyUI API nodes.", "Use the managed print_design_basic.api.json template or export a complete API prompt.")


def _json_string_value(value: Any) -> str:
    encoded = json.dumps(str(value))
    return encoded[1:-1]


def _coerce_prepared_workflow_values(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _coerce_prepared_workflow_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_coerce_prepared_workflow_values(item) for item in value]
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value):
        return int(value)
    return value


def prepare_workflow_from_plan(plan: dict[str, Any]) -> dict[str, Any]:
    requested_workflow_type = _requested_workflow_type(plan)
    try:
        workflow = workflow_manager.get_executable_workflow_template(requested_workflow_type)
    except KeyError as exc:
        raise ImageWorkerError("no_executable_workflow_template", str(exc), "Create or restore a valid ComfyUI API prompt template for the requested workflow type.") from exc
    workflow_path = Path(str(workflow.get("workflow_path") or workflow.get("path"))).expanduser()
    workflow_format = workflow_manager.classify_workflow_format(workflow_path)
    if workflow_format == "comfyui_ui_workflow":
        raise ImageWorkerError("workflow_is_comfyui_ui_format_export_api_needed", "Selected workflow is a ComfyUI UI workflow export, not an API prompt.", "Export API prompt JSON and retry.", workflow_path=str(workflow_path))
    if workflow_format == "jamesos_spec":
        raise ImageWorkerError("workflow_is_jamesos_spec_not_comfyui_api_prompt", "Selected workflow is a JamesOS spec, not a ComfyUI API prompt.", "Use a ComfyUI API prompt template from disk.", workflow_path=str(workflow_path))
    if workflow_format != "comfyui_api_prompt":
        raise ImageWorkerError("no_executable_workflow_template", "Selected workflow is not an executable ComfyUI API prompt.", "Use the managed print_design_basic.api.json template.", workflow_path=str(workflow_path))
    checkpoint = _discovered_checkpoint(plan)
    checkpoint_name = Path(str(checkpoint.get("path") or checkpoint.get("local_path") or checkpoint.get("name"))).name
    replacements = {
        "{{positive_prompt}}": _json_string_value(plan.get("prompt") or ""),
        "{{negative_prompt}}": _json_string_value(plan.get("negative_prompt") or ""),
        "{{checkpoint_name}}": _json_string_value(checkpoint_name),
        "{{seed}}": str(plan.get("seed") or 1),
        "{{width}}": str(plan.get("width") or 1024),
        "{{height}}": str(plan.get("height") or 1024),
        "{{filename_prefix}}": _json_string_value(str(plan.get("filename_prefix") or "JamesOS")),
    }
    text = workflow_path.read_text(encoding="utf-8")
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    try:
        prepared = json.loads(text)
        prepared = _coerce_prepared_workflow_values(prepared)
        _validate_prepared_workflow(prepared, text)
        return {"workflow": prepared, "source_path": str(workflow_path), "template": workflow}
    except json.JSONDecodeError as exc:
        raise ImageWorkerError("workflow_file_not_json", f"Prepared workflow is not valid JSON: {exc}", "Fix the workflow template JSON and retry the approved job.", workflow_path=str(workflow_path)) from exc


def _job_output_folder(job_id: str) -> Path:
    return GENERATED_ROOT / date.today().isoformat() / job_id


def _save_prepared_workflow(job_id: str, workflow: dict[str, Any]) -> str:
    folder = _job_output_folder(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / "prepared_workflow.json"
    path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return str(path)


def _save_images(job_id: str, images: list[dict[str, Any]]) -> list[str]:
    if not images:
        raise ImageWorkerError("comfyui_output_missing", "ComfyUI completed without output images", "Check the workflow SaveImage node and ComfyUI history output, then retry.", job_id=job_id)
    folder = _job_output_folder(job_id)
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
    provider = str(data.get("pod_provider") or payload.get("pod_provider") or "printify").lower()
    update = {
        "design_image_path": image_path,
        "design_status": "image_generated",
        "pod_provider": provider,
        "provider_status": "manual_upload_ready",
        "status": "ready_for_pod_review",
    }
    if provider == "printify":
        update["printify_status"] = "ready_for_printify_review"
    else:
        update["printify_status"] = "not_applicable"
    data.update(update)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _creative_stage_updates(job_payload: dict[str, Any], image_path: str, image_paths: list[str]) -> dict[str, Any]:
    payload = dict(job_payload)
    payload["output_image_path"] = image_path
    payload["output_image_paths"] = image_paths
    payload["generated_assets"] = image_paths
    payload["generated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["image_status"] = "generated"
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
        raise ImageWorkerError("invalid_job_type", "Only image_generation or creative_image_generation jobs can execute", "Create an image_generation job before requesting image execution.")
    if job.get("status") == "processed":
        raise ImageWorkerError("job_already_processed", "Image job has already been processed", "Create a new approved image job for another generation.")
    if not job.get("approved"):
        raise ImageWorkerError("approval_required", "Image job must be explicitly approved before execution", "Approve the job first, then call execute-approved.")
    active = [item for item in list_jobs("in_progress") if item.get("type") in EXECUTABLE_JOB_TYPES and item.get("job_id") != job_id]
    if active:
        raise ImageWorkerError("image_job_in_progress", "Another image job is already in progress", "Wait for the active image job to finish before starting another.")
    payload = _payload_details(job)
    try:
        append_job_log(job_id, "validation passed")
        mark_step(job_id, "validation", "complete", "Approved image job validation passed.")
        update_job_status(job_id, "in_progress")
        plan = _plan_from_job(get_job(job_id))
        workflow_json = prepare_workflow_from_plan(plan)
        prepared_workflow_path = _save_prepared_workflow(job_id, workflow_json["workflow"])
        append_job_log(job_id, f"workflow prepared: {workflow_json['source_path']}")
        mark_step(job_id, "workflow prepared", "complete", prepared_workflow_path)
        if not comfyui_client.is_running(COMFYUI_URL, timeout=2.0):
            raise ImageWorkerError("comfyui_not_running", "ComfyUI is not running at http://127.0.0.1:8188", "Start local ComfyUI on 127.0.0.1:8188 and retry.", job_id=job_id, workflow_path=workflow_json["source_path"])
        try:
            queued = comfyui_client.queue_prompt(workflow_json["workflow"], api_url=COMFYUI_URL)
        except Exception as exc:
            raise ImageWorkerError("comfyui_rejected_prompt", f"ComfyUI rejected the prepared prompt: {exc}", "Open the prepared workflow in ComfyUI/API format and fix rejected node inputs.", job_id=job_id, workflow_path=workflow_json["source_path"]) from exc
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise ImageWorkerError("comfyui_rejected_prompt", "ComfyUI did not return a prompt_id", "Check ComfyUI API logs for rejected prompt details.", job_id=job_id, workflow_path=workflow_json["source_path"])
        append_job_log(job_id, "ComfyUI prompt queued")
        mark_step(job_id, "ComfyUI prompt queued", "complete", prompt_id)
        completed = comfyui_client.wait_for_completion(prompt_id, api_url=COMFYUI_URL)
        if completed.get("status") != "completed":
            code = "image_generation_timeout" if completed.get("status") == "timeout" else "comfyui_rejected_prompt"
            raise ImageWorkerError(code, f"ComfyUI prompt did not complete: {completed.get('status')}", "Review ComfyUI history and logs, then retry after fixing the workflow.", job_id=job_id, workflow_path=workflow_json["source_path"])
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
            "prepared_workflow_path": prepared_workflow_path,
            "workflow_path": workflow_json["source_path"],
            "job": processed,
            "execution_enabled": False,
            "printify_execution_enabled": False,
            "etsy_execution_enabled": False,
            "publish_enabled": False,
            "upload_enabled": False,
            "send_enabled": False,
        }
    except Exception as exc:
        error = structured_error(exc, job_id=job_id)
        LAST_ERROR_PATH.parent.mkdir(parents=True, exist_ok=True)
        LAST_ERROR_PATH.write_text(json.dumps(error, indent=2, sort_keys=True), encoding="utf-8")
        try:
            fail_job(job_id, str(exc))
        except Exception:
            pass
        if isinstance(exc, JobQueueError):
            raise
        raise JobQueueError(str(exc)) from exc
