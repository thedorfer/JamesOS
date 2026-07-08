from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jamesos.config import VAULT
from jamesos.services import model_registry


MANAGED_WORKFLOW_TEMPLATE_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "WorkflowTemplates"

WORKFLOW_ROOTS = [
    MANAGED_WORKFLOW_TEMPLATE_ROOT,
    Path.home() / "AI" / "Workflows",
    VAULT / "JamesOS" / "AI" / "Workflows",
]

WORKFLOW_INVENTORY_PATH = VAULT / "JamesOS" / "AI" / "workflow_inventory.json"
REPORT_PATH = VAULT / "JamesOS" / "Reports" / "Workflow Registry.md"

WORKFLOW_TYPES = {
    "print_design_basic",
    "transparent_print_design_basic",
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

RECOMMENDED_WORKFLOW_TYPES = ["print_design_basic", "transparent_print_design_basic", "transparent_png", "typography", "mockup", "upscale"]

REQUIRED_API_NODE_TYPES = {
    "CheckpointLoaderSimple",
    "CLIPTextEncode",
    "EmptyLatentImage",
    "KSampler",
    "VAEDecode",
    "SaveImage",
}


def _default_print_design_template() -> dict[str, Any]:
    return {
        "1": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "{{checkpoint_name}}"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": "{{positive_prompt}}"},
        },
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"clip": ["1", 1], "text": "{{negative_prompt}}"},
        },
        "4": {
            "class_type": "EmptyLatentImage",
            "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "model": ["1", 0],
                "positive": ["2", 0],
                "negative": ["3", 0],
                "latent_image": ["4", 0],
                "seed": "{{seed}}",
                "steps": 28,
                "cfg": 7.0,
                "sampler_name": "euler",
                "scheduler": "normal",
                "denoise": 1.0,
            },
        },
        "6": {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["5", 0], "vae": ["1", 2]},
        },
        "7": {
            "class_type": "SaveImage",
            "inputs": {"images": ["6", 0], "filename_prefix": "{{filename_prefix}}"},
        },
    }


def _default_transparent_print_design_template() -> dict[str, Any]:
    return _default_print_design_template()


def _write_template_if_missing_or_invalid(path: Path, template: dict[str, Any]) -> bool:
    should_write = not path.exists()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            should_write = not validate_comfyui_api_prompt_structure(data).get("valid")
        except Exception:
            should_write = True
    if should_write:
        path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    return should_write


def initialize_default_workflow_templates() -> dict[str, Any]:
    MANAGED_WORKFLOW_TEMPLATE_ROOT.mkdir(parents=True, exist_ok=True)
    path = MANAGED_WORKFLOW_TEMPLATE_ROOT / "print_design_basic.api.json"
    transparent_path = MANAGED_WORKFLOW_TEMPLATE_ROOT / "transparent_print_design_basic.api.json"
    created = _write_template_if_missing_or_invalid(path, _default_print_design_template())
    transparent_created = _write_template_if_missing_or_invalid(transparent_path, _default_transparent_print_design_template())
    return {
        "status": "ok",
        "template_root": str(MANAGED_WORKFLOW_TEMPLATE_ROOT),
        "default_print_design_workflow_path": str(path),
        "default_transparent_print_design_workflow_path": str(transparent_path),
        "transparent_background_requested": True,
        "transparency_method": "prompt_only",
        "background_removal_required": True,
        "created": created or transparent_created,
    }


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
    initialize_default_workflow_templates()
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
    elif "transparent_print_design" in text or ("transparent" in text and "print" in text and "design" in text):
        workflow_type = "transparent_print_design_basic"
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
    initialize_default_workflow_templates()
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
        ("transparent_print_design_basic", ["transparent_print_design_basic", "transparent_print_design", "transparent_print_art", "transparent_print"]),
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


def validate_comfyui_api_prompt(workflow_json: Any) -> dict[str, Any]:
    if not isinstance(workflow_json, dict):
        return {"valid": False, "error_code": "workflow_file_not_json", "missing_required_nodes": sorted(REQUIRED_API_NODE_TYPES)}
    if isinstance(workflow_json.get("nodes"), list) or "last_node_id" in workflow_json or "links" in workflow_json:
        return {"valid": False, "error_code": "workflow_is_comfyui_ui_format_export_api_needed", "missing_required_nodes": sorted(REQUIRED_API_NODE_TYPES)}
    if "creative_spec" in workflow_json or "image_plan" in workflow_json or "positive_prompt" in workflow_json:
        return {"valid": False, "error_code": "workflow_is_jamesos_spec_not_comfyui_api_prompt", "missing_required_nodes": sorted(REQUIRED_API_NODE_TYPES)}
    nodes = [node for node in workflow_json.values() if isinstance(node, dict)]
    class_types = {str(node.get("class_type") or "") for node in nodes}
    missing = sorted(REQUIRED_API_NODE_TYPES - class_types)
    if missing:
        return {"valid": False, "error_code": "workflow_missing_required_nodes", "missing_required_nodes": missing}
    return {"valid": True, "error_code": "", "missing_required_nodes": []}


def _is_node_reference(value: Any) -> bool:
    return (
        isinstance(value, list)
        and len(value) == 2
        and isinstance(value[0], (str, int))
        and isinstance(value[1], int)
    )


def normalize_comfyui_api_prompt_node_references(workflow_json: Any) -> Any:
    if not isinstance(workflow_json, dict):
        return workflow_json
    node_ids = {str(node_id) for node_id in workflow_json.keys()}

    def normalize(value: Any) -> Any:
        if _is_node_reference(value) and str(value[0]) in node_ids:
            return [str(value[0]), value[1]]
        if isinstance(value, list):
            return [normalize(item) for item in value]
        if isinstance(value, dict):
            return {key: normalize(item) for key, item in value.items()}
        return value

    return normalize(workflow_json)


def validate_comfyui_api_prompt_structure(workflow_json: Any) -> dict[str, Any]:
    base = validate_comfyui_api_prompt(workflow_json)
    issues: list[dict[str, Any]] = []
    if not isinstance(workflow_json, dict):
        return {
            "valid": False,
            "error_code": "workflow_file_not_json",
            "issues": [{"node_id": "", "field": "", "message": "Workflow must be a JSON object."}],
            "summary": "Workflow must be a JSON object.",
        }
    if not base.get("valid"):
        for missing in base.get("missing_required_nodes", []):
            issues.append({
                "node_id": "",
                "field": "class_type",
                "message": f"Required node class is missing: {missing}",
            })
    node_ids = {str(node_id) for node_id in workflow_json.keys()}
    for node_id, node in workflow_json.items():
        rendered_id = str(node_id)
        if not isinstance(node, dict):
            issues.append({
                "node_id": rendered_id,
                "field": "",
                "message": "Node must be an object with class_type and inputs.",
            })
            continue
        class_type = node.get("class_type")
        if not isinstance(class_type, str) or not class_type.strip():
            issues.append({
                "node_id": rendered_id,
                "field": "class_type",
                "message": "Node is missing non-empty class_type.",
            })
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            issues.append({
                "node_id": rendered_id,
                "field": "inputs",
                "message": "Node inputs must be an object.",
            })
            continue
        for field, value in inputs.items():
            if _is_node_reference(value):
                target_id = str(value[0])
                if isinstance(value[0], int):
                    issues.append({
                        "node_id": rendered_id,
                        "field": f"inputs.{field}",
                        "message": f"Node reference must use string node ID \"{target_id}\", not numeric {value[0]}.",
                        "reference": value,
                    })
                if target_id not in node_ids:
                    issues.append({
                        "node_id": rendered_id,
                        "field": f"inputs.{field}",
                        "message": f"Input references missing node {target_id}.",
                        "reference": value,
                    })
    return {
        "valid": not issues,
        "error_code": "" if not issues else (base.get("error_code") or "workflow_invalid_api_prompt_structure"),
        "issues": issues,
        "summary": "ok" if not issues else issues[0]["message"],
    }


def classify_workflow_format(path: Path) -> str:
    data = _load_workflow_json(path)
    if data is None:
        return "unknown"
    if isinstance(data, dict) and (isinstance(data.get("nodes"), list) or "last_node_id" in data or "links" in data):
        return "comfyui_ui_workflow"
    if isinstance(data, dict) and ("creative_spec" in data or "image_plan" in data or "positive_prompt" in data):
        return "jamesos_spec"
    validation = validate_comfyui_api_prompt(data)
    if validation["valid"]:
        return "comfyui_api_prompt"
    if isinstance(data, dict) and any(isinstance(node, dict) and node.get("class_type") for node in data.values()):
        return "comfyui_api_prompt"
    return "unknown"


def _compatible_models(workflow_type: str) -> list[str]:
    mapping = {
        "transparent_print_design_basic": ["transparent_png", "sdxl_base", "flux_schnell", "sd15"],
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
        "transparent_print_design_basic": ["manual-upload print-ready PNG candidates", "shirts", "hoodies", "mugs", "stickers", "totes"],
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
    workflow_format = classify_workflow_format(path)
    validation = validate_comfyui_api_prompt(data)
    name = path.stem[:-4] if path.stem.endswith(".api") else path.stem
    return {
        "name": name,
        "path": str(path),
        "workflow_path": str(path),
        "type": workflow_type,
        "workflow_format": workflow_format,
        "api_prompt_valid": bool(validation.get("valid")),
        "validation_error_code": validation.get("error_code", ""),
        "missing_required_nodes": validation.get("missing_required_nodes", []),
        "status": "discovered",
        "compatible_models": _compatible_models(workflow_type),
        "recommended_products": _recommended_products(workflow_type),
        "requires_transparency": workflow_type in {"transparent_print_design_basic", "transparent_png", "background_removal"},
        "transparent_background_requested": workflow_type in {"transparent_print_design_basic", "transparent_png", "background_removal"},
        "transparency_method": "prompt_only" if workflow_type == "transparent_print_design_basic" else "",
        "background_removal_required": workflow_type == "transparent_print_design_basic",
        "supports_mockups": workflow_type in {"mockup", "listing_image"},
        "enabled": False,
        "execution_enabled": False,
    }


def _summarize_inventory(workflows: list[dict[str, Any]]) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_format: dict[str, int] = {}
    for workflow in workflows:
        by_type[workflow["type"]] = by_type.get(workflow["type"], 0) + 1
        workflow_format = str(workflow.get("workflow_format") or "unknown")
        by_format[workflow_format] = by_format.get(workflow_format, 0) + 1
    missing = [item for item in RECOMMENDED_WORKFLOW_TYPES if item not in by_type]
    executable = [item for item in workflows if item.get("workflow_format") == "comfyui_api_prompt" and item.get("api_prompt_valid")]
    return {
        "total": len(workflows),
        "by_type": dict(sorted(by_type.items())),
        "by_format": dict(sorted(by_format.items())),
        "executable_workflow_template_count": len(executable),
        "missing_recommended_workflows": missing,
    }


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


def get_executable_workflow_template(workflow_type: str) -> dict[str, Any]:
    initialize_default_workflow_templates()
    requested = (workflow_type or "print_design_basic").strip() or "print_design_basic"
    inventory = build_workflow_inventory()
    workflows = inventory.get("workflows", [])
    candidates = [
        item for item in workflows
        if item.get("workflow_format") == "comfyui_api_prompt"
        and item.get("api_prompt_valid")
        and item.get("type") == requested
    ]
    if requested == "print_design_basic":
        for item in candidates:
            if Path(str(item.get("workflow_path") or "")).name == "print_design_basic.api.json":
                return {**item, "status": "ok", "comfyui_open_workflow_ignored": True}
    if requested == "transparent_print_design_basic":
        for item in candidates:
            if Path(str(item.get("workflow_path") or "")).name == "transparent_print_design_basic.api.json":
                return {
                    **item,
                    "status": "ok",
                    "comfyui_open_workflow_ignored": True,
                    "transparent_background_requested": True,
                    "transparency_method": "prompt_only",
                    "background_removal_required": True,
                }
    if candidates:
        return {**candidates[0], "status": "ok", "comfyui_open_workflow_ignored": True}
    if requested == "print_design_basic":
        fallback = [
            item for item in workflows
            if item.get("workflow_format") == "comfyui_api_prompt"
            and item.get("api_prompt_valid")
            and item.get("name") == "product_art_basic"
        ]
        if fallback:
            return {**fallback[0], "status": "ok", "workflow_alias_used": True, "comfyui_open_workflow_ignored": True}
    if requested == "transparent_print_design_basic":
        try:
            fallback = get_executable_workflow_template("print_design_basic")
            return {
                **fallback,
                "requested_workflow_type": requested,
                "workflow_alias_used": True,
                "transparent_background_requested": True,
                "transparency_method": "prompt_only",
                "background_removal_required": True,
            }
        except KeyError:
            pass
    raise KeyError(f"No executable ComfyUI API prompt template found for workflow type: {requested}")


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
