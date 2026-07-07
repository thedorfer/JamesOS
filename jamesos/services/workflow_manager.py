from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services import model_registry


WORKFLOW_ROOTS = [
    Path.home() / "AI" / "Workflows",
    Path.home() / "AI" / "ComfyUI" / "user" / "default" / "workflows",
    VAULT / "JamesOS" / "AI" / "Workflows",
]

WORKFLOW_INVENTORY_PATH = VAULT / "JamesOS" / "AI" / "workflow_inventory.json"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Workflow Registry.md"

WORKFLOW_TYPES = {
    "print_design_basic",
    "product_art",
    "transparent_png",
    "typography",
    "mockup",
    "listing_image",
    "social_post",
    "background_removal",
    "upscale",
    "img2img",
    "generic",
}

RECOMMENDED_WORKFLOW_TYPES = ["print_design_basic", "transparent_png", "typography", "mockup", "upscale"]


def _inventory_path(path: Path | None = None) -> Path:
    return path or WORKFLOW_INVENTORY_PATH


def _report_path(path: Path | None = None) -> Path:
    return path or REPORT_PATH


def _workflow_with_validation(workflow: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(workflow)
    workflow_path = str(enriched.get("workflow_path") or "").strip()
    if not workflow_path and enriched.get("path"):
        workflow_path = str(enriched.get("path"))
        enriched["workflow_path"] = workflow_path
    enriched["path_exists"] = bool(workflow_path and Path(workflow_path).expanduser().exists())
    enriched["execution_enabled"] = False
    enriched["enabled"] = False
    if not enriched["path_exists"]:
        enriched["status"] = "missing"
    return enriched


def list_workflows() -> dict[str, Any]:
    registry = model_registry.load_registry()
    configured_workflows = {
        name: _workflow_with_validation(workflow)
        for name, workflow in registry.get("workflows", {}).items()
    }
    inventory = load_workflow_inventory()
    discovered = {
        workflow["name"]: _workflow_with_validation(workflow)
        for workflow in inventory.get("workflows", [])
    }
    workflows = {**configured_workflows, **discovered}
    return {
        "status": "ok",
        "workflows": workflows,
        "configured_workflows": configured_workflows,
        "discovered_inventory": inventory,
        "discovered_workflows": inventory.get("workflows", []),
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
    requested = str(package.get("workflow_type") or package.get("recommended_workflow_type") or "").strip()
    text = " ".join(
        str(package.get(key, ""))
        for key in ["product_type", "niche", "title", "product_idea", "design_prompt"]
    ).lower()
    if requested:
        workflow_type = requested
    elif "mockup" in text:
        workflow_type = "mockup"
    elif "print_design" in text or "design_art" in text or "product_art" in text:
        workflow_type = "print_design_basic"
    elif "transparent" in text or "png" in text:
        workflow_type = "transparent_png"
    elif "typography" in text or "shirt" in text or "sticker" in text:
        workflow_type = "typography"
    elif "listing" in text:
        workflow_type = "listing_image"
    else:
        workflow_type = "product_art"
    workflows = list_workflows()["workflows"]
    def selected(workflow: dict[str, Any], alias_used: bool = False) -> dict[str, Any]:
        result = dict(workflow)
        result["requested_workflow_type"] = workflow_type
        result["selected_workflow_type"] = str(result.get("type") or result.get("name") or "")
        result["workflow_alias_used"] = alias_used
        return result

    for workflow in workflows.values():
        if workflow.get("type") == workflow_type:
            return selected(workflow)
    if workflow_type in workflows:
        return selected(workflows[workflow_type])
    aliases = {"typography": "typography_design", "print_design_basic": "product_art_basic", "product_art": "product_art_basic"}
    alias = aliases.get(workflow_type)
    if alias and alias in workflows:
        return selected(workflows[alias], alias_used=True)
    try:
        return selected(get_workflow(workflow_type)["workflow"])
    except KeyError:
        return selected(get_workflow("product_art")["workflow"], alias_used=workflow_type != "product_art")


def scan_workflows(workflow_roots: list[Path] | None = None) -> list[Path]:
    roots = workflow_roots or WORKFLOW_ROOTS
    files: list[Path] = []
    for root in roots:
        expanded = Path(root).expanduser()
        if not expanded.exists():
            continue
        for path in expanded.rglob("*.json"):
            if path.is_file():
                files.append(path)
    return sorted(files, key=lambda item: str(item).lower())


def _workflow_text(path: Path, data: Any | None = None) -> str:
    parts = [path.stem, " ".join(path.parts)]
    if isinstance(data, dict):
        parts.append(json.dumps(data, sort_keys=True)[:8000])
    return " ".join(parts).lower().replace("-", "_").replace(" ", "_")


def infer_workflow_type(path_or_name: Path | str, data: Any | None = None) -> str:
    text = _workflow_text(path_or_name if isinstance(path_or_name, Path) else Path(str(path_or_name)), data)
    checks = [
        ("print_design_basic", ["print_design_basic", "print_design", "design_art", "flat_print", "flat_design", "standalone_print"]),
        ("background_removal", ["background_removal", "remove_background", "rembg", "birefnet"]),
        ("transparent_png", ["transparent_png", "transparent", "alpha", "png"]),
        ("typography", ["typography", "text_design", "shirt", "sticker", "poster_text"]),
        ("mockup", ["mockup", "product_mockup"]),
        ("listing_image", ["listing_image", "listing", "etsy_listing"]),
        ("social_post", ["social_post", "instagram", "facebook", "pinterest", "social"]),
        ("upscale", ["upscale", "upscaler", "upscaling", "esrgan", "ultrasharp"]),
        ("img2img", ["img2img", "image_to_image", "loadimage", "denoise"]),
        ("product_art", ["product_art_basic", "product_art", "product", "print_on_demand", "pod"]),
    ]
    for workflow_type, markers in checks:
        if any(marker in text for marker in markers):
            return workflow_type
    return "generic"


def _load_workflow_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _compatible_models(workflow_type: str) -> list[str]:
    mapping = {
        "print_design_basic": ["sdxl_base", "flux_schnell", "sd15"],
        "product_art": ["sdxl_base", "flux_schnell"],
        "transparent_png": ["transparent_png", "sdxl_base"],
        "typography": ["sdxl_typography", "sdxl_base"],
        "mockup": ["mockup_model", "sdxl_base"],
        "listing_image": ["mockup_model", "sdxl_base"],
        "social_post": ["sdxl_base"],
        "background_removal": ["transparent_png"],
        "upscale": ["mockup_model"],
        "img2img": ["sdxl_base", "sdxl_typography"],
        "generic": ["sdxl_base"],
    }
    return mapping.get(workflow_type, ["sdxl_base"])


def _recommended_products(workflow_type: str) -> list[str]:
    mapping = {
        "print_design_basic": ["design_art", "shirts", "hoodies", "mugs", "stickers", "totes"],
        "product_art": ["shirts", "hoodies", "mugs", "stickers", "posters"],
        "transparent_png": ["stickers", "shirts", "transparent product art"],
        "typography": ["shirts", "hoodies", "stickers", "posters"],
        "mockup": ["listing previews", "product mockups"],
        "listing_image": ["Etsy listing images", "shop previews"],
        "social_post": ["Instagram posts", "Pinterest pins", "marketing drafts"],
        "background_removal": ["transparent assets", "mockup preparation"],
        "upscale": ["final local review assets", "larger previews"],
        "img2img": ["variation drafts", "reference-based concepts"],
        "generic": ["manual review required"],
    }
    return mapping.get(workflow_type, ["manual review required"])


def classify_workflow(path: Path) -> dict[str, Any]:
    data = _load_workflow_json(path)
    workflow_type = infer_workflow_type(path, data)
    return {
        "name": path.stem,
        "path": str(path),
        "workflow_path": str(path),
        "type": workflow_type,
        "status": "discovered",
        "compatible_models": _compatible_models(workflow_type),
        "recommended_products": _recommended_products(workflow_type),
        "requires_transparency": workflow_type in {"transparent_png", "background_removal"},
        "supports_mockups": workflow_type in {"mockup", "listing_image"},
        "enabled": False,
        "execution_enabled": False,
    }


def _summarize_inventory(workflows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    for workflow in workflows:
        by_type[workflow["type"]] = by_type.get(workflow["type"], 0) + 1
    missing = [item for item in RECOMMENDED_WORKFLOW_TYPES if item not in by_type]
    return {"total": len(workflows), "by_type": dict(sorted(by_type.items())), "missing_recommended_workflows": missing}


def build_workflow_inventory(
    workflow_roots: list[Path] | None = None,
    inventory_path: Path | None = None,
) -> dict[str, Any]:
    workflow_paths = scan_workflows(workflow_roots)
    workflows = [classify_workflow(path) for path in workflow_paths]
    inventory = {
        "status": "ok",
        "workflow_roots": [str(Path(root).expanduser()) for root in (workflow_roots or WORKFLOW_ROOTS)],
        "workflows": workflows,
        "summary": _summarize_inventory(workflows),
        "execution_enabled": False,
        "safety": {
            "enabled": False,
            "execution_enabled": False,
            "calls_comfyui_prompt_queue": False,
            "generates_images": False,
            "calls_printify": False,
            "calls_etsy": False,
            "uploads": False,
            "publishes": False,
        },
    }
    path = _inventory_path(inventory_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(inventory, indent=2, sort_keys=True), encoding="utf-8")
    return inventory


def load_workflow_inventory(inventory_path: Path | None = None) -> dict[str, Any]:
    path = _inventory_path(inventory_path)
    if not path.exists():
        return {
            "status": "not_scanned",
            "workflow_roots": [str(root) for root in WORKFLOW_ROOTS],
            "workflows": [],
            "summary": {"total": 0, "by_type": {}, "missing_recommended_workflows": RECOMMENDED_WORKFLOW_TYPES},
            "execution_enabled": False,
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "workflows": [],
            "summary": {"total": 0, "by_type": {}, "missing_recommended_workflows": RECOMMENDED_WORKFLOW_TYPES},
            "execution_enabled": False,
        }


def write_workflow_inventory_report(
    inventory: dict[str, Any] | None = None,
    report_path: Path | None = None,
) -> dict[str, Any]:
    data = inventory or load_workflow_inventory()
    path = _report_path(report_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = data.get("summary", {})
    lines = [
        "# Workflow Registry",
        "",
        "Phase B workflow inventory is read-only. No ComfyUI prompt queue calls are made.",
        "",
        "## Safety",
        "",
        "- execution_enabled: false",
        "- enabled: false for discovered workflows",
        "- no image generation",
        "- no Printify calls",
        "- no Etsy calls",
        "- no upload or publishing",
        "",
        "## Summary",
        "",
        f"- discovered workflows: {summary.get('total', 0)}",
        f"- missing recommended workflows: {', '.join(summary.get('missing_recommended_workflows', [])) or 'none'}",
        "",
        "## Types",
        "",
    ]
    for workflow_type, count in summary.get("by_type", {}).items():
        lines.append(f"- {workflow_type}: {count}")
    if not summary.get("by_type"):
        lines.append("- none")
    lines.extend(["", "## Workflow Roots", ""])
    for root in data.get("workflow_roots", []):
        lines.append(f"- {root}")
    lines.extend(["", "## Discovered Workflows", ""])
    if not data.get("workflows"):
        lines.append("- None discovered yet.")
    for workflow in data.get("workflows", [])[:200]:
        lines.append(
            f"- {workflow.get('name')} — {workflow.get('type')} "
            f"enabled: false, execution_enabled: false"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"status": "ok", "report_path": str(path), "workflow_count": summary.get("total", 0)}


def scan_and_report(workflow_roots: list[Path] | None = None) -> dict[str, Any]:
    inventory = build_workflow_inventory(workflow_roots=workflow_roots)
    report = write_workflow_inventory_report(inventory)
    return {**inventory, "report": report}
