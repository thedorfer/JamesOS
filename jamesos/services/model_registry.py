from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


REGISTRY_PATH = VAULT / "JamesOS" / "AI" / "model_registry.yaml"

MODEL_NAMES = [
    "sdxl_base",
    "sdxl_typography",
    "flux_schnell",
    "flux_dev",
    "transparent_png",
    "mockup_model",
]

WORKFLOW_NAMES = [
    "product_art",
    "typography_design",
    "transparent_png",
    "mockup",
    "listing_image",
]

DEFAULT_CONFIG: dict[str, Any] = {
    "models": {
        "sdxl_base": {
            "name": "sdxl_base",
            "type": "checkpoint",
            "status": "missing",
            "local_path": "",
            "recommended_for": ["general product art", "stable diffusion xl"],
            "vram_notes": "Use modest sizes and lowvram settings on GTX 1080 Ti.",
            "enabled": False,
        },
        "sdxl_typography": {
            "name": "sdxl_typography",
            "type": "checkpoint_or_lora",
            "status": "missing",
            "local_path": "",
            "recommended_for": ["typography", "shirt designs", "stickers"],
            "vram_notes": "Prefer simple layouts; typography should be reviewed manually.",
            "enabled": False,
        },
        "flux_schnell": {
            "name": "flux_schnell",
            "type": "checkpoint",
            "status": "missing",
            "local_path": "",
            "recommended_for": ["fast concept drafts"],
            "vram_notes": "May be tight on Pascal; keep disabled until locally validated.",
            "enabled": False,
        },
        "flux_dev": {
            "name": "flux_dev",
            "type": "checkpoint",
            "status": "missing",
            "local_path": "",
            "recommended_for": ["high quality concept drafts"],
            "vram_notes": "Likely too heavy for GTX 1080 Ti without careful workflow choices.",
            "enabled": False,
        },
        "transparent_png": {
            "name": "transparent_png",
            "type": "workflow_support",
            "status": "missing",
            "local_path": "",
            "recommended_for": ["transparent background product artwork"],
            "vram_notes": "Use lightweight segmentation/background removal steps if available.",
            "enabled": False,
        },
        "mockup_model": {
            "name": "mockup_model",
            "type": "checkpoint_or_workflow_support",
            "status": "missing",
            "local_path": "",
            "recommended_for": ["product mockups", "listing previews"],
            "vram_notes": "Mockups should remain local review assets only.",
            "enabled": False,
        },
    },
    "workflows": {
        "product_art": {
            "name": "product_art",
            "status": "missing",
            "workflow_path": "",
            "compatible_models": ["sdxl_base", "flux_schnell"],
            "enabled": False,
        },
        "typography_design": {
            "name": "typography_design",
            "status": "missing",
            "workflow_path": "",
            "compatible_models": ["sdxl_typography", "sdxl_base"],
            "enabled": False,
        },
        "transparent_png": {
            "name": "transparent_png",
            "status": "missing",
            "workflow_path": "",
            "compatible_models": ["transparent_png", "sdxl_base"],
            "enabled": False,
        },
        "mockup": {
            "name": "mockup",
            "status": "missing",
            "workflow_path": "",
            "compatible_models": ["mockup_model"],
            "enabled": False,
        },
        "listing_image": {
            "name": "listing_image",
            "status": "missing",
            "workflow_path": "",
            "compatible_models": ["mockup_model", "sdxl_base"],
            "enabled": False,
        },
    },
    "output_paths": {
        "root": "~/JamesOSData/JamesOS/AI/ComfyUI/Outputs",
        "drafts": "~/JamesOSData/JamesOS/Products/UnityStitches/Assets",
    },
    "safety": {
        "execution_enabled": False,
        "requires_approval": True,
        "one_image_job_at_a_time": True,
        "call_printify": False,
        "call_etsy": False,
        "publish": False,
        "order": False,
        "upload": False,
        "send": False,
    },
}


def _registry_path(path: Path | None = None) -> Path:
    return path or REGISTRY_PATH


def initialize_registry(path: Path | None = None) -> dict[str, Any]:
    path = _registry_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    created = False
    if not path.exists():
        path.write_text(yaml.safe_dump(DEFAULT_CONFIG, sort_keys=False), encoding="utf-8")
        created = True
    return {"status": "ok", "created": created, "registry_path": str(path)}


def load_registry(path: Path | None = None) -> dict[str, Any]:
    path = _registry_path(path)
    initialize_registry(path)
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        loaded = {}
    return {
        "models": {**DEFAULT_CONFIG["models"], **(loaded.get("models") or {})},
        "workflows": {**DEFAULT_CONFIG["workflows"], **(loaded.get("workflows") or {})},
        "output_paths": {**DEFAULT_CONFIG["output_paths"], **(loaded.get("output_paths") or {})},
        "safety": {**DEFAULT_CONFIG["safety"], **(loaded.get("safety") or {})},
    }


def health(path: Path | None = None) -> dict[str, Any]:
    path = _registry_path(path)
    registry = load_registry(path)
    return {
        "status": "ok",
        "registry_path": str(path),
        "present": path.exists(),
        "model_count": len(registry.get("models", {})),
        "workflow_count": len(registry.get("workflows", {})),
        "execution_enabled": False,
        "safety": registry.get("safety", DEFAULT_CONFIG["safety"]),
    }


def list_models(path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    return {
        "status": "ok",
        "models": registry["models"],
        "execution_enabled": False,
        "safety": registry["safety"],
    }


def get_model(model_name: str, path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    model = registry["models"].get(model_name)
    if model is None:
        raise KeyError(f"Unknown model: {model_name}")
    return {"status": "ok", "model": model, "execution_enabled": False}


def choose_model_for_workflow(workflow: dict[str, Any], path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    for model_name in workflow.get("compatible_models", []):
        model = registry["models"].get(model_name)
        if model:
            return model
    return registry["models"]["sdxl_base"]
