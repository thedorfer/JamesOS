from __future__ import annotations

from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services import asset_library, model_registry, prompt_library, style_registry, workflow_manager
from jamesos.services.brand_registry import get_brand, get_default_brand


COMFYUI_URL = "http://127.0.0.1:8188"
OUTPUT_FOLDER = VAULT / "JamesOS" / "AI" / "ComfyUI" / "Outputs"

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
        "one_image_job_at_a_time": True,
        "safety": SAFETY,
    }


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
