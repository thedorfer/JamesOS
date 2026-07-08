from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from jamesos.config import VAULT
from jamesos.services import prompt_library
from jamesos.services.design_dna import design_dna_from_recipe
from jamesos.services.job_queue import create_job
from jamesos.services.print_readiness_scorer import score_variation, score_variations
from jamesos.services.recipe_library import get_recipe


DESIGN_RUN_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "DesignRuns"

SAFETY = {
    "calls_printify": False,
    "calls_inkedjoy": False,
    "calls_etsy": False,
    "uploads": False,
    "publishes": False,
    "orders": False,
    "sends": False,
    "provider_writes_enabled": False,
    "auto_execute": False,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _run_id() -> str:
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def _run_folder(run_id: str, root: Path | None = None) -> Path:
    base = root or DESIGN_RUN_ROOT
    day = run_id[:8]
    formatted = f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 and day.isdigit() else date.today().isoformat()
    return base / formatted / run_id


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _variation_recipe(recipe: dict[str, Any], number: int, quality: str, product_type: str, niche: str) -> dict[str, Any]:
    variants = [
        {"variation_axis": "balanced motif repeat", "layout": recipe.get("layout"), "accent_density": "medium"},
        {"variation_axis": "larger focal motif", "layout": "larger centered motif with supporting repeat accents", "accent_density": "low"},
        {"variation_axis": "denser pattern rhythm", "layout": "small balanced repeat with tighter spacing", "accent_density": "high"},
        {"variation_axis": "soft commercial minimal", "layout": "minimal repeat with extra negative space", "accent_density": "low"},
    ]
    selected = variants[(number - 1) % len(variants)]
    return {
        **recipe,
        "quality": quality,
        "product_type": product_type,
        "niche": niche,
        "variation_number": number,
        "variation_axis": selected["variation_axis"],
        "layout": selected["layout"] or recipe.get("layout"),
        "accent_density": selected["accent_density"],
    }


def _layer_manifest(variation_id: str, recipe: dict[str, Any]) -> dict[str, Any]:
    planned = recipe.get("layer_plan") or ["transparent_canvas", "motif", "final_composite"]
    layers = []
    for index, layer_type in enumerate(planned, start=1):
        layers.append({
            "layer_id": f"{variation_id}-layer-{index:02d}",
            "layer_type": layer_type,
            "purpose": f"{layer_type.replace('_', ' ')} for reusable design construction",
            "source": "logical_recipe_layer",
            "prompt_fragment": ", ".join(str(item) for item in recipe.get("motifs", [])) if layer_type in {"pattern", "motif", "illustration", "accent"} else str(recipe.get("layout", "")),
            "output_path": "",
            "reusable": layer_type != "final_composite",
            "reuse_tags": [recipe.get("design_family", ""), layer_type, recipe.get("design_type", "")],
            "enabled": True,
            "notes": "Logical layer manifest only; current ComfyUI workflow may output one raster composite.",
        })
    return {"variation_id": variation_id, "layers": layers, "execution_enabled": False}


def _image_job_payload(run_id: str, variation: dict[str, Any], provider: str) -> dict[str, Any]:
    prompt_package = variation["prompt_package"]
    return {
        "design_run_id": run_id,
        "variation_id": variation["variation_id"],
        "creative_spec": {
            "brand_id": variation["brand_id"],
            "stage": "design_art",
            "product_type": variation["product_type"],
            "niche": variation["niche"],
            "design_recipe": variation["design_recipe"],
            "quality": variation["design_recipe"].get("quality", "premium"),
            "pod_provider": provider,
        },
        "image_plan": {
            "requested_workflow_type": prompt_package.get("recommended_workflow_type", "transparent_print_design_basic"),
            "prompt": prompt_package["positive_prompt"],
            "negative_prompt": prompt_package["negative_prompt"],
            "prompt_package": prompt_package,
            "design_recipe": variation["design_recipe"],
            "design_dna": variation["design_dna"],
            "seed": 1000 + int(variation["variation_number"]),
            "width": 1024,
            "height": 1024,
            "pod_provider": provider,
        },
        "execution_enabled": False,
        "auto_execute": False,
        "printify_execution_enabled": False,
        "inkedjoy_execution_enabled": False,
        "etsy_execution_enabled": False,
        "upload_enabled": False,
        "publish_enabled": False,
        "order_enabled": False,
        "send_enabled": False,
    }


def create_design_run(
    *,
    brand_id: str,
    product_type: str,
    niche: str,
    recipe_id: str,
    variations: int = 4,
    quality: str = "premium",
    provider: str = "printify",
    root: Path | None = None,
    create_image_jobs: bool = True,
) -> dict[str, Any]:
    recipe = get_recipe(recipe_id)["recipe"]
    count = max(1, min(int(variations or 4), 12))
    run_id = _run_id()
    folder = _run_folder(run_id, root)
    folder.mkdir(parents=True, exist_ok=True)
    dna = design_dna_from_recipe(recipe, brand_id=brand_id, product_type=product_type, niche=niche, quality=quality)
    yaml_path = folder / "recipe_snapshot.yaml"
    yaml_path.write_text(yaml.safe_dump(recipe, sort_keys=False), encoding="utf-8")
    _write_json(folder / "design_dna.json", dna)

    variation_records = []
    for number in range(1, count + 1):
        variation_id = f"variation_{number:02d}"
        variation_folder = folder / "variations" / variation_id
        design_recipe = _variation_recipe(recipe, number, quality, product_type, niche)
        creative_spec = {
            "brand_id": brand_id,
            "stage": "design_art",
            "product_type": product_type,
            "niche": niche,
            "quality": quality,
            "pod_provider": provider,
            "design_recipe": design_recipe,
        }
        prompt_package = prompt_library.creative_spec_to_prompt_package(creative_spec)
        layer_manifest = _layer_manifest(variation_id, design_recipe)
        _write_json(variation_folder / "layer_manifest.json", layer_manifest)
        _write_json(variation_folder / "prompt_package.json", prompt_package)
        variation = {
            "variation_id": variation_id,
            "variation_number": number,
            "recipe_id": recipe["recipe_id"],
            "recipe_version": recipe.get("version", "1.0"),
            "brand_id": brand_id,
            "product_type": product_type,
            "niche": niche,
            "design_recipe": design_recipe,
            "design_dna": dna,
            "layer_manifest_path": str(variation_folder / "layer_manifest.json"),
            "prompt_package": prompt_package,
            "score": {},
            "status": "planned",
            "image_job_id": "",
        }
        variation["score"] = score_variation(variation)
        if create_image_jobs:
            job = create_job(
                "image_generation",
                _image_job_payload(run_id, variation, provider),
                requires_approval=True,
                steps=["validation", "workflow prepared", "ComfyUI prompt queued", "image saved", "completed"],
            )
            variation["image_job_id"] = job["job_id"]
            variation["status"] = "image_job_created"
        _write_json(variation_folder / "variation.json", variation)
        variation_records.append(variation)

    scored = score_variations(variation_records)
    for variation in scored:
        path = folder / "variations" / variation["variation_id"] / "variation.json"
        _write_json(path, variation)
    summary = {
        "status": "created",
        "run_id": run_id,
        "run_folder": str(folder),
        "created_at": _now(),
        "brand_id": brand_id,
        "product_type": product_type,
        "niche": niche,
        "recipe_id": recipe["recipe_id"],
        "quality": quality,
        "provider": provider,
        "variation_count": len(scored),
        "variations": scored,
        "safety": SAFETY,
        "execution_enabled": False,
    }
    _write_json(folder / "run_summary.json", summary)
    _write_json(folder / "variation_summary.json", {"variations": scored})
    return summary


def _load_run_summary(run_id: str, root: Path | None = None) -> dict[str, Any]:
    folder = _run_folder(run_id, root)
    path = folder / "run_summary.json"
    if not path.exists():
        raise KeyError(f"Unknown design run: {run_id}")
    return json.loads(path.read_text(encoding="utf-8"))


def list_design_runs(root: Path | None = None) -> dict[str, Any]:
    base = root or DESIGN_RUN_ROOT
    runs = []
    if base.exists():
        for path in sorted(base.glob("*/*/run_summary.json"), reverse=True):
            try:
                runs.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
    return {"status": "ok", "runs": runs, "run_count": len(runs), "execution_enabled": False}


def get_design_run(run_id: str, root: Path | None = None) -> dict[str, Any]:
    return {"status": "ok", "run": _load_run_summary(run_id, root), "execution_enabled": False}


def score_design_run(run_id: str, root: Path | None = None) -> dict[str, Any]:
    summary = _load_run_summary(run_id, root)
    folder = Path(summary["run_folder"])
    variations = []
    for path in sorted((folder / "variations").glob("variation_*/variation.json")):
        variation = json.loads(path.read_text(encoding="utf-8"))
        variation["score"] = score_variation(variation)
        _write_json(path, variation)
        variations.append(variation)
    summary["variations"] = variations
    summary["status"] = "scored"
    _write_json(folder / "run_summary.json", summary)
    _write_json(folder / "variation_summary.json", {"variations": variations})
    return {"status": "ok", "run": summary, "execution_enabled": False}


def promote_best(run_id: str, root: Path | None = None) -> dict[str, Any]:
    scored = score_design_run(run_id, root)["run"]
    folder = Path(scored["run_folder"])
    variations = scored.get("variations", [])
    if not variations:
        raise ValueError("Design run has no variations")
    best = max(variations, key=lambda item: int((item.get("score") or {}).get("print_readiness_score", 0)))
    best_score = int((best.get("score") or {}).get("print_readiness_score", 0))
    provider = str(scored.get("provider") or "printify").lower()
    best_status = "ready_for_printify_review" if best_score >= 90 and provider == "printify" else "best_candidate_needs_review"
    for variation in variations:
        variation["status"] = best_status if variation["variation_id"] == best["variation_id"] else "rejected_or_lower_ranked"
        _write_json(folder / "variations" / variation["variation_id"] / "variation.json", variation)
    best = next(item for item in variations if item["variation_id"] == best["variation_id"])
    winner = {"status": best_status, "winning_variation": best, "score_threshold": 90, "provider": provider}
    _write_json(folder / "winner" / "winning_variation.json", winner)
    scored["status"] = "promoted" if best_status == "ready_for_printify_review" else "best_candidate_needs_review"
    scored["variations"] = variations
    scored["winning_variation_id"] = best["variation_id"]
    scored["winning_status"] = best_status
    _write_json(folder / "run_summary.json", scored)
    return {"status": "ok", "run": scored, "winner": winner, "execution_enabled": False}
