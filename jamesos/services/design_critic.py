from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any

from jamesos.config import VAULT


CRITIQUE_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Critiques"
UNDERWEAR_TYPES = {"womens_underwear", "panties", "panty", "thong", "thongs"}
TEXT_HEAVY = {"large_readable_text", "typography_heavy", "headline_text", "readable_typography"}
NO_TEXT = {"no_text", "minimal_hidden_text"}
MOCKUP_LANGUAGE = {"mockup", "person", "model", "mannequin", "hands", "face", "body", "lifestyle", "photo", "wearing"}

SAFETY = {
    "calls_printify": False,
    "calls_inkedjoy": False,
    "calls_etsy": False,
    "uploads": False,
    "publishes": False,
    "orders": False,
    "sends": False,
    "provider_writes_enabled": False,
    "external_execution_enabled": False,
}


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _id(prefix: str = "critic") -> str:
    return f"{prefix}_{datetime.now().strftime('%Y%m%d-%H%M%S')}_{uuid.uuid4().hex[:8]}"


def _folder_for_id(critic_id: str, root: Path | None = None) -> Path:
    base = root or CRITIQUE_ROOT
    parts = critic_id.split("_")
    day = parts[1][:8] if len(parts) > 1 else ""
    folder_date = f"{day[:4]}-{day[4:6]}-{day[6:8]}" if len(day) == 8 and day.isdigit() else date.today().isoformat()
    return base / folder_date


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def _clamp(value: int) -> int:
    return max(0, min(100, int(value)))


def _product_key(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")


def _text_blob(*items: Any) -> str:
    chunks = []
    for item in items:
        if isinstance(item, dict):
            chunks.append(json.dumps(item, sort_keys=True))
        elif isinstance(item, list):
            chunks.append(" ".join(str(part) for part in item))
        else:
            chunks.append(str(item or ""))
    return " ".join(chunks).lower()


def recommend_mutations(critique: dict[str, Any]) -> list[dict[str, Any]]:
    mutations = []
    issues = " ".join(critique.get("blocking_issues", []) + critique.get("warnings", [])).lower()
    if "large typography" in issues or "slogan" in issues:
        mutations.append({"field": "typography_strategy", "action": "switch_to_no_text_or_minimal_hidden_text"})
    if "repeat" in issues or "pattern" in issues:
        mutations.append({"field": "pattern_strategy", "action": "increase_balanced_repeat_motif_spacing"})
    if "transparency" in issues:
        mutations.append({"field": "prompt_intent.transparent_background_requested", "action": "require_transparent_background_metadata"})
    if "mockup" in issues or "person" in issues or "photo" in issues:
        mutations.append({"field": "negative_rules", "action": "add_no_mockup_person_lifestyle_photo_language"})
    if not mutations:
        mutations.append({"field": "variation_axis", "action": "preserve_plan_and_generate_candidate"})
    return mutations


def _promotion(overall: int, blocking: list[str]) -> str:
    if blocking or overall < 70:
        return "reject"
    if overall >= 90:
        return "ready_for_printify_review"
    return "best_candidate_needs_review"


def critique_design_plan(plan: dict[str, Any], *, artifact: dict[str, Any] | None = None) -> dict[str, Any]:
    product_type = _product_key(str(plan.get("product_type") or ""))
    prompt_intent = plan.get("prompt_intent") or {}
    artifact = artifact or {}
    recipe = artifact.get("design_recipe") or {}
    prompt_package = artifact.get("prompt_package") or {}
    layer_manifest = artifact.get("layer_manifest") or {}
    plan_for_language = dict(plan)
    prompt_intent_for_language = dict(plan_for_language.get("prompt_intent") or {})
    prompt_intent_for_language.pop("negative_rules", None)
    prompt_intent_for_language.pop("avoid_mockup_person_photo", None)
    plan_for_language["prompt_intent"] = prompt_intent_for_language
    recipe_for_language = {key: value for key, value in recipe.items() if key != "negative_rules"}
    blob = _text_blob(plan_for_language, recipe_for_language, {"positive_prompt": prompt_package.get("positive_prompt", "")})

    blocking: list[str] = []
    warnings: list[str] = []
    strengths: list[str] = []
    recommendations: list[str] = []

    print_readiness_score = 86
    product_fit_score = 84
    commercial_consistency_score = 86
    recipe_adherence_score = 86
    composition_score = 84
    typography_score = 82
    transparency_score = 76
    layer_reuse_score = 65

    typography_strategy = str(plan.get("typography_strategy") or recipe.get("text_strategy") or "").lower()
    pattern_strategy = str(plan.get("pattern_strategy") or recipe.get("pattern_strategy") or "").lower()
    design_type = str(recipe.get("design_type") or "").lower()

    if product_type in UNDERWEAR_TYPES:
        if typography_strategy in NO_TEXT:
            typography_score = 95
            strengths.append("Underwear plan avoids large readable text.")
        elif typography_strategy in TEXT_HEAVY or "slogan" in blob:
            typography_score = 42
            product_fit_score = 55
            blocking.append("Large typography or slogan is a poor fit for underwear.")
        if "repeat" in pattern_strategy or "pattern" in pattern_strategy or "motif" in pattern_strategy or "pattern" in design_type:
            product_fit_score = max(product_fit_score, 94)
            composition_score = max(composition_score, 92)
            strengths.append("Underwear plan uses repeat-friendly motif/pattern structure.")
        else:
            product_fit_score = min(product_fit_score, 62)
            warnings.append("Underwear plan should use balanced motif or repeat pattern structure.")
    else:
        if typography_strategy in TEXT_HEAVY or "typography" in design_type:
            typography_score = 90
            strengths.append("Typography-capable product has a readable text strategy.")
        elif "text" in blob and "no_text" in typography_strategy:
            warnings.append("Product may support readable text, but plan is no-text.")

    if any(token in blob for token in MOCKUP_LANGUAGE):
        print_readiness_score -= 12
        commercial_consistency_score -= 10
        blocking.append("Mockup/person/lifestyle/photo language is not allowed for flat print artwork.")

    transparent_requested = bool(prompt_intent.get("transparent_background_requested") or artifact.get("transparent_background") or artifact.get("has_transparency"))
    if transparent_requested:
        transparency_score = 92
        strengths.append("Transparency metadata is present.")
    else:
        warnings.append("Transparency metadata is missing; high print-readiness requires it.")

    width = int(artifact.get("width") or artifact.get("image_width") or 1024)
    height = int(artifact.get("height") or artifact.get("image_height") or 1024)
    if width < 768 or height < 768:
        print_readiness_score -= 10
        warnings.append("Resolution metadata is below current print candidate baseline.")

    layers = layer_manifest.get("layers") if isinstance(layer_manifest, dict) else None
    if layers is None:
        layers = plan.get("layer_plan") or []
    if layers:
        layer_reuse_score = 90 if len(layers) >= 3 else 76
        strengths.append("Layer plan supports future reuse.")
    else:
        warnings.append("Layer reuse metadata is missing.")

    if plan.get("quality_target"):
        recipe_adherence_score = max(recipe_adherence_score, min(95, int(plan.get("quality_target") or 90)))

    if warnings:
        recommendations.extend(warnings)
    if not recommendations:
        recommendations.append("Preserve plan structure and generate after approval.")

    scores = {
        "print_readiness_score": _clamp(print_readiness_score),
        "product_fit_score": _clamp(product_fit_score),
        "commercial_consistency_score": _clamp(commercial_consistency_score),
        "recipe_adherence_score": _clamp(recipe_adherence_score),
        "composition_score": _clamp(composition_score),
        "typography_score": _clamp(typography_score),
        "transparency_score": _clamp(transparency_score),
        "layer_reuse_score": _clamp(layer_reuse_score),
    }
    overall = round(sum(scores.values()) / len(scores))
    critique = {
        "status": "ok",
        "critic_id": _id(),
        "created_at": _now(),
        "plan_id": plan.get("plan_id", ""),
        "overall_score": _clamp(overall),
        **scores,
        "blocking_issues": blocking,
        "warnings": warnings,
        "strengths": strengths,
        "recommendations": recommendations,
        "recommended_mutations": [],
        "promotion_recommendation": _promotion(overall, blocking),
        "safety": SAFETY,
        "external_execution_enabled": False,
    }
    critique["recommended_mutations"] = recommend_mutations(critique)
    return critique


def critique_generated_artifact(artifact: dict[str, Any]) -> dict[str, Any]:
    plan = artifact.get("design_plan") or {
        "plan_id": artifact.get("plan_id", ""),
        "product_type": artifact.get("product_type", ""),
        "niche": artifact.get("niche", ""),
        "typography_strategy": (artifact.get("design_recipe") or {}).get("text_strategy", ""),
        "pattern_strategy": (artifact.get("design_recipe") or {}).get("pattern_strategy", ""),
        "prompt_intent": {"transparent_background_requested": artifact.get("transparent_background", False)},
        "layer_plan": (artifact.get("design_recipe") or {}).get("layer_plan", []),
        "quality_target": 90,
    }
    return critique_design_plan(plan, artifact=artifact)


def save_critique(critique: dict[str, Any], *, root: Path | None = None, path: Path | None = None) -> dict[str, Any]:
    critic_id = str(critique.get("critic_id") or _id())
    critique["critic_id"] = critic_id
    out = path or (_folder_for_id(critic_id, root) / f"{critic_id}.json")
    _write_json(out, critique)
    return {"status": "ok", "critique": critique, "path": str(out), "external_execution_enabled": False}


def load_critique(critic_id_or_path: str, *, root: Path | None = None) -> dict[str, Any]:
    candidate = Path(critic_id_or_path).expanduser()
    if candidate.exists():
        return {"status": "ok", "critique": json.loads(candidate.read_text(encoding="utf-8")), "path": str(candidate), "external_execution_enabled": False}
    base = root or CRITIQUE_ROOT
    for path in sorted(base.glob(f"*/*{critic_id_or_path}*.json")):
        return {"status": "ok", "critique": json.loads(path.read_text(encoding="utf-8")), "path": str(path), "external_execution_enabled": False}
    raise KeyError(f"Unknown design critique: {critic_id_or_path}")


def design_critic_health() -> dict[str, Any]:
    CRITIQUE_ROOT.mkdir(parents=True, exist_ok=True)
    return {
        "status": "ok",
        "service": "design_critic",
        "storage_root": str(CRITIQUE_ROOT),
        "safety": SAFETY,
        "external_execution_enabled": False,
    }
