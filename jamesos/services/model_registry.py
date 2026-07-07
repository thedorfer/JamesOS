from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT


REGISTRY_PATH = VAULT / "JamesOS" / "AI" / "model_registry.yaml"
INVENTORY_PATH = VAULT / "JamesOS" / "AI" / "model_inventory.json"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Model Registry.md"

MODEL_ROOTS = [
    Path.home() / "AI" / "Models",
    Path.home() / "AI" / "ComfyUI" / "models",
    VAULT / "JamesOS" / "AI" / "Models",
]

SUPPORTED_CATEGORIES = {
    "checkpoints",
    "loras",
    "vae",
    "embeddings",
    "controlnet",
    "upscalers",
    "clip",
    "unet",
    "diffusion_models",
    "text_encoders",
}

MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf"}

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


def _inventory_path(path: Path | None = None) -> Path:
    return path or INVENTORY_PATH


def _report_path(path: Path | None = None) -> Path:
    return path or REPORT_PATH


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
    inventory = load_model_inventory()
    summary = inventory.get("summary", {})
    return {
        "status": "ok",
        "registry_path": str(path),
        "present": path.exists(),
        "model_count": len(registry.get("models", {})),
        "workflow_count": len(registry.get("workflows", {})),
        "inventory_path": str(INVENTORY_PATH),
        "discovered_model_count": int(summary.get("total", 0) or 0),
        "checkpoint_count": int(summary.get("by_category", {}).get("checkpoints", 0) or 0),
        "lora_count": int(summary.get("by_category", {}).get("loras", 0) or 0),
        "upscaler_count": int(summary.get("by_category", {}).get("upscalers", 0) or 0),
        "missing_recommended_categories": missing_recommended_categories(inventory),
        "execution_enabled": False,
        "safety": registry.get("safety", DEFAULT_CONFIG["safety"]),
    }


def list_models(path: Path | None = None) -> dict[str, Any]:
    registry = load_registry(path)
    inventory = load_model_inventory()
    return {
        "status": "ok",
        "models": registry["models"],
        "configured_models": registry["models"],
        "discovered_inventory": inventory,
        "discovered_models": inventory.get("models", []),
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


def scan_model_files(model_roots: list[Path] | None = None) -> list[Path]:
    roots = model_roots or MODEL_ROOTS
    files: list[Path] = []
    for root in roots:
        expanded = Path(root).expanduser()
        if not expanded.exists():
            continue
        for path in expanded.rglob("*"):
            if path.is_file() and path.suffix.lower() in MODEL_EXTENSIONS:
                files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _path_parts_lower(path: Path) -> list[str]:
    return [part.lower() for part in path.parts]


def classify_model_file(path: Path) -> str:
    parts = _path_parts_lower(path)
    name = path.name.lower()
    joined = "/".join(parts)
    parent_parts = parts[:-1]
    if any(part in {"checkpoints", "checkpoint", "ckpt"} for part in parent_parts):
        return "checkpoints"
    category_aliases = [
        ("diffusion_models", ["diffusion_models", "diffusion models"]),
        ("text_encoders", ["text_encoders", "text encoders", "text_encoder", "text encoder"]),
        ("checkpoints", ["checkpoints", "checkpoint", "ckpt"]),
        ("loras", ["loras", "lora", "lycoris"]),
        ("vae", ["vae", "vaes"]),
        ("embeddings", ["embeddings", "embedding", "textual_inversion", "textual inversion"]),
        ("controlnet", ["controlnet", "control_net", "control net"]),
        ("upscalers", ["upscalers", "upscaler", "upscale_models", "upscale models", "esrgan", "realesrgan", "ultrasharp"]),
        ("clip", ["clip"]),
        ("unet", ["unet", "unets"]),
    ]
    for category, aliases in category_aliases:
        if category == "vae":
            if any(alias in parent_parts for alias in aliases) or name in {"vae.safetensors", "vae.ckpt", "vae.pt", "vae.pth", "vae.bin"} or name.endswith(".vae.safetensors"):
                return "vae"
            continue
        if any(alias in parts or alias in joined or alias in name for alias in aliases):
            return category
    if path.suffix.lower() == ".ckpt":
        return "checkpoints"
    return "checkpoints"


def infer_model_family(path_or_name: Path | str) -> str:
    path = Path(str(path_or_name))
    text = str(path_or_name).lower().replace("_", " ").replace("-", " ")
    parts = [part.lower() for part in path.parts]
    parent_parts = parts[:-1]
    if any(term in text for term in ["upscaler", "ultrasharp", "realesrgan", "esrgan", "4x"]):
        return "upscaler"
    if any(part in {"vae", "vaes"} for part in parent_parts) or path.name.lower() in {"vae.safetensors", "vae.ckpt", "vae.pt", "vae.pth", "vae.bin"} or path.name.lower().endswith(".vae.safetensors"):
        return "vae"
    if "lora" in text or "loras" in text or "lycoris" in text:
        return "lora"
    if "flux" in text:
        return "flux"
    if "pony" in text:
        return "pony"
    if any(term in text for term in ["sdxl", "xl base", "stable diffusion xl"]):
        return "sdxl"
    if any(term in text for term in ["sd15", "sd 1.5", "stable diffusion 1.5", "v1-5", "1.5", "realisticvision", "realistic vision"]):
        return "sd15"
    return "unknown"


def _recommended_for(category: str, family: str) -> list[str]:
    if category == "loras":
        return ["style adaptation", "product design variants"]
    if category == "upscalers" or family == "upscaler":
        return ["upscaling", "final image enhancement"]
    if category == "vae" or family == "vae":
        return ["image decoding", "color/contrast support"]
    if family == "flux":
        return ["concept drafts", "high quality prompts"]
    if family == "sdxl":
        return ["general product art", "typography drafts", "listing concepts"]
    if family == "sd15":
        return ["lightweight local drafts", "legacy workflows"]
    if family == "pony":
        return ["specialized style workflows only after review"]
    return ["manual review required"]


def _vram_notes(category: str, family: str) -> str:
    if family == "flux":
        return "Flux may be tight on GTX 1080 Ti; keep disabled until a lowvram workflow is validated."
    if family == "sdxl":
        return "SDXL can work with careful lowvram settings and modest sizes on GTX 1080 Ti."
    if family == "sd15":
        return "SD 1.5 is generally lighter and friendlier to GTX 1080 Ti."
    if category == "upscalers":
        return "Run upscalers one image at a time; memory use depends on image size."
    if category == "loras":
        return "LoRA VRAM impact depends on base model and workflow."
    return "Validate locally before enabling any future workflow."


def _inventory_record(path: Path) -> dict[str, Any]:
    category = classify_model_file(path)
    family = infer_model_family(path)
    try:
        file_size_mb = round(path.stat().st_size / (1024 * 1024), 2)
    except OSError:
        file_size_mb = 0.0
    return {
        "name": path.stem,
        "path": str(path),
        "category": category,
        "family": family,
        "file_size_mb": file_size_mb,
        "status": "discovered",
        "enabled": False,
        "recommended_for": _recommended_for(category, family),
        "vram_notes": _vram_notes(category, family),
    }


def _summarize_inventory(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_category: dict[str, int] = {}
    by_family: dict[str, int] = {}
    for record in records:
        by_category[record["category"]] = by_category.get(record["category"], 0) + 1
        by_family[record["family"]] = by_family.get(record["family"], 0) + 1
    return {
        "total": len(records),
        "by_category": dict(sorted(by_category.items())),
        "by_family": dict(sorted(by_family.items())),
    }


def missing_recommended_categories(inventory: dict[str, Any] | None = None) -> list[str]:
    data = inventory or load_model_inventory()
    by_category = data.get("summary", {}).get("by_category", {})
    recommended = ["checkpoints", "loras", "vae", "upscalers"]
    return [category for category in recommended if int(by_category.get(category, 0) or 0) == 0]


def build_model_inventory(
    model_roots: list[Path] | None = None,
    inventory_path: Path | None = None,
) -> dict[str, Any]:
    files = scan_model_files(model_roots)
    records = [_inventory_record(path) for path in files]
    inventory = {
        "status": "ok",
        "model_roots": [str(Path(root).expanduser()) for root in (model_roots or MODEL_ROOTS)],
        "models": records,
        "summary": _summarize_inventory(records),
        "execution_enabled": False,
        "safety": {
            "enabled": False,
            "execution_enabled": False,
            "requires_approval": True,
            "generates_images": False,
            "calls_comfyui": False,
            "calls_printify": False,
            "calls_etsy": False,
            "publishes": False,
            "uploads": False,
            "orders": False,
            "sends": False,
        },
    }
    path = _inventory_path(inventory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8")
    return inventory


def load_model_inventory(inventory_path: Path | None = None) -> dict[str, Any]:
    path = _inventory_path(inventory_path)
    if not path.exists():
        return {
            "status": "not_scanned",
            "model_roots": [str(root) for root in MODEL_ROOTS],
            "models": [],
            "summary": {"total": 0, "by_category": {}, "by_family": {}},
            "execution_enabled": False,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "models": [],
            "summary": {"total": 0, "by_category": {}, "by_family": {}},
            "execution_enabled": False,
        }


def write_model_inventory_report(
    inventory: dict[str, Any] | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    data = inventory or load_model_inventory()
    path = _report_path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = data.get("summary", {})
    lines = [
        "# Model Registry",
        "",
        "Phase A model inventory is read-only. No ComfyUI workflows are executed.",
        "",
        "## Safety",
        "",
        "- execution_enabled: false",
        "- model enabled flags remain false",
        "- no image generation",
        "- no Printify calls",
        "- no Etsy calls",
        "- no publishing, uploads, orders, or sending",
        "",
        "## Summary",
        "",
        f"- discovered models: {summary.get('total', 0)}",
        f"- checkpoints: {summary.get('by_category', {}).get('checkpoints', 0)}",
        f"- LoRAs: {summary.get('by_category', {}).get('loras', 0)}",
        f"- upscalers: {summary.get('by_category', {}).get('upscalers', 0)}",
        f"- missing recommended categories: {', '.join(missing_recommended_categories(data)) or 'none'}",
        "",
        "## Model Roots",
        "",
    ]
    for root in data.get("model_roots", []):
        lines.append(f"- {root}")
    lines.extend(["", "## Discovered Models", ""])
    if not data.get("models"):
        lines.append("- None discovered yet.")
    for model in data.get("models", [])[:200]:
        lines.append(
            f"- {model.get('name')} — {model.get('category')} / {model.get('family')} "
            f"({model.get('file_size_mb')} MB), enabled: false"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "report_path": str(path), "model_count": summary.get("total", 0)}


def scan_and_report(model_roots: list[Path] | None = None) -> dict[str, Any]:
    inventory = build_model_inventory(model_roots=model_roots)
    report = write_model_inventory_report(inventory)
    return {**inventory, "report": report}
