from __future__ import annotations

from pathlib import Path
from typing import Any

from jamesos.services import model_registry


def _workflow_with_validation(workflow: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(workflow)
    workflow_path = str(enriched.get("workflow_path") or "").strip()
    enriched["path_exists"] = bool(workflow_path and Path(workflow_path).expanduser().exists())
    enriched["execution_enabled"] = False
    if not enriched["path_exists"]:
        enriched["status"] = "missing"
    return enriched


def list_workflows() -> dict[str, Any]:
    registry = model_registry.load_registry()
    workflows = {
        name: _workflow_with_validation(workflow)
        for name, workflow in registry.get("workflows", {}).items()
    }
    return {
        "status": "ok",
        "workflows": workflows,
        "execution_enabled": False,
        "safety": registry.get("safety", {}),
    }


def get_workflow(workflow_name: str) -> dict[str, Any]:
    workflows = list_workflows()["workflows"]
    workflow = workflows.get(workflow_name)
    if workflow is None:
        raise KeyError(f"Unknown workflow: {workflow_name}")
    return {"status": "ok", "workflow": workflow, "execution_enabled": False}


def validate_workflow_path(workflow_name: str) -> dict[str, Any]:
    workflow = get_workflow(workflow_name)["workflow"]
    return {
        "status": "ok" if workflow["path_exists"] else "missing",
        "workflow": workflow,
        "path_exists": workflow["path_exists"],
        "execution_enabled": False,
    }


def choose_workflow_for_package(package: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(
        str(package.get(key, ""))
        for key in ["product_type", "niche", "title", "product_idea", "design_prompt"]
    ).lower()
    if "mockup" in text:
        name = "mockup"
    elif "transparent" in text or "png" in text:
        name = "transparent_png"
    elif "typography" in text or "shirt" in text or "sticker" in text:
        name = "typography_design"
    elif "listing" in text:
        name = "listing_image"
    else:
        name = "product_art"
    return get_workflow(name)["workflow"]
