#!/usr/bin/env python3
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import random
import shutil
import sys
import tempfile
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from unittest.mock import patch

from PIL import Image, ImageDraw
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from jamesos.config import VAULT
from jamesos.services import image_worker, job_queue, production_artifact, upscale_model_registry
from jamesos.services.image_finisher import approve_concept_for_job, prepare_transparent_artifact_for_job
from jamesos.services.image_postprocessor import inspect_generated_image


PROTECTED_JOB_ID = "20260714-212815-f6c92984"
VALIDATION_JOB_ID = "e2e-artwork-20260715-105515-228d4132"
JOB_PREFIX = "e2e-artwork-"
DEFAULT_MODEL = "RealESRGAN_x2plus.pth"
REPORT_FILENAME = "artwork-pipeline-e2e-report.json"
LOGICAL_STAGE_SIZES = ((768, 768), (1536, 1536), (3072, 3072), (6144, 6144))
FORBIDDEN_READINESS_VALUES = {
    "publishable", "published", "uploaded", "provider-ready", "printify-ready", "order-ready", "commerce-ready"
}


class E2EHarnessError(RuntimeError):
    pass


class E2EHarnessFailure(E2EHarnessError):
    def __init__(self, report: dict[str, Any]):
        super().__init__(str(report.get("diagnostic") or "E2E pipeline failed"))
        self.report = report


def hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unique_test_job_id(now: datetime | None = None, suffix: str | None = None) -> str:
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    random_suffix = suffix or f"{random.SystemRandom().randrange(16**8):08x}"
    return f"{JOB_PREFIX}{timestamp}-{random_suffix}"


def validate_test_job_id(job_id: str) -> None:
    if job_id == PROTECTED_JOB_ID:
        raise E2EHarnessError("The approved heart job is permanently excluded from the E2E harness.")
    if not job_id.startswith(JOB_PREFIX):
        raise E2EHarnessError("The E2E harness accepts only e2e-artwork-* job IDs.")
    if any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in job_id):
        raise E2EHarnessError("The E2E job ID contains invalid characters.")


def create_concept_fixture(path: Path) -> str:
    """Create a deterministic, coherent rocket badge with a removable white exterior."""
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (768, 768), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    navy, teal, coral = (24, 48, 105), (22, 174, 166), (242, 91, 116)
    draw.ellipse((96, 80, 672, 656), fill=navy)
    rng = random.Random(20260715)
    for _ in range(70):
        x, y = rng.randint(145, 623), rng.randint(129, 607)
        if (x - 384) ** 2 + (y - 368) ** 2 < 248 ** 2:
            draw.ellipse((x - 1, y - 1, x + 1, y + 1), fill=(37, 67, 132))
    # Outer flame, inner flame, fins, and teal body are deliberately sampled by tests.
    draw.polygon(((330, 480), (384, 625), (438, 480)), fill=(247, 139, 42))
    draw.polygon(((355, 480), (384, 580), (413, 480)), fill=(255, 218, 65))
    draw.polygon(((310, 395), (245, 505), (335, 475)), fill=coral)
    draw.polygon(((458, 395), (523, 505), (433, 475)), fill=coral)
    draw.polygon(((384, 145), (300, 290), (315, 475), (453, 475), (468, 290)), fill=teal)
    draw.ellipse((348, 275, 420, 347), fill=(10, 63, 92))
    draw.ellipse((356, 283, 412, 339), fill=(255, 255, 255))
    # Colored isolated details include a near-edge dot to exercise alpha preservation.
    for x, y, radius, color in (
        (71, 365, 10, (255, 213, 62)), (693, 385, 8, coral),
        (145, 680, 7, teal), (625, 695, 6, (247, 139, 42)), (18, 150, 5, teal),
    ):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    draw.polygon(((696, 210), (701, 222), (714, 223), (704, 231), (708, 244),
                  (696, 237), (685, 244), (688, 231), (678, 223), (691, 222)), fill=(255, 213, 62))
    image.save(path, format="PNG", optimize=False)
    image.close()
    return hash_file(path)


def create_e2e_job(job_id: str, source_path: Path) -> dict[str, Any]:
    validate_test_job_id(job_id)
    if any((folder / f"{job_id}.json").exists() for folder in job_queue.status_dirs().values()):
        raise E2EHarnessError(f"Refusing to reuse existing E2E job ID: {job_id}")
    timestamp = job_queue.now_timestamp()
    job = job_queue.normalize_job({
        "id": job_id,
        "job_id": job_id,
        "type": "e2e_artwork_pipeline_test",
        "status": "pending",
        "created_at": timestamp,
        "updated_at": timestamp,
        "requires_approval": False,
        "approved": True,
        "payload": {
            "e2e_test_job": True,
            "output_image_path": str(source_path),
            "output_image_paths": [str(source_path)],
            "transparent_background_required": True,
            "provider_status": "not_ready",
            "printify_status": "not_ready",
            "final_print_ready": False,
        },
        "steps": [],
        "logs": [],
    })
    job_queue._write_job(job)
    return job


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise E2EHarnessError(message)


def _image_facts(path: Path) -> dict[str, Any]:
    with Image.open(path) as image:
        image.load()
        alpha_extrema = list(image.getchannel("A").getextrema()) if "A" in image.mode else None
        return {"path": str(path), "sha256": hash_file(path), "dimensions": list(image.size), "mode": image.mode, "alpha_extrema": alpha_extrema}


def _mock_stage_runner(workflows: list[dict[str, Any]], responses: list[dict[str, Any]]):
    def run_stage(
        *, job_id: str, stage_number: int, source_path: Path, output_path: Path, debug_folder: Path,
        selected_model: dict[str, Any], settings: dict[str, Any], expected_input: tuple[int, int], expected_output: tuple[int, int],
    ) -> dict[str, Any]:
        started = time.perf_counter()
        source_sha = hash_file(source_path)
        with Image.open(source_path) as source:
            source.load()
            _assert(source.size == expected_input, f"Mock stage {stage_number} received {source.size}, expected {expected_input}")
            _assert(source.mode == "RGBA", f"Mock stage {stage_number} input is not RGBA")
        input_name = f"{job_id}-mock-stage-{stage_number}-rgb.png"
        workflow = production_artifact.build_upscale_validation_workflow(input_name, selected_model["model_name"])
        workflows.append(workflow)
        debug_folder.mkdir(parents=True, exist_ok=True)
        workflow_path = debug_folder / f"stage-{stage_number}-submitted-workflow.json"
        workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        stage = Image.new("RGBA", expected_output, (0, 0, 0, 0))
        draw = ImageDraw.Draw(stage)
        inset = max(1, expected_output[0] // 8)
        draw.ellipse((inset, inset, expected_output[0] - inset, expected_output[1] - inset), fill=(30, 110, 210, 255))
        stage.save(output_path, format="PNG")
        stage.close()
        responses.append({
            "status": "completed", "prompt_id": f"mock-stage-{stage_number}",
            "output_path": str(output_path), "output_sha256": hash_file(output_path),
        })
        _assert(hash_file(source_path) == source_sha, f"Mock stage {stage_number} changed its source")
        facts = _image_facts(output_path)
        return {
            "stage": stage_number,
            "input_path": str(source_path), "output_path": str(output_path),
            "input_dimensions": list(expected_input), "output_dimensions": list(expected_output),
            "input_sha256": source_sha, "output_sha256": facts["sha256"],
            "model_name": selected_model["model_name"], "model_sha256": selected_model["sha256"],
            "settings": dict(settings), "alpha_extrema": facts["alpha_extrema"],
            "alpha_diagnostics": {"partially_transparent_pixel_count": 0},
            "execution_time_seconds": time.perf_counter() - started,
            "comfyui_prompt_id": f"mock-stage-{stage_number}", "workflow_path": str(workflow_path),
        }
    return run_stage


def _status_assertions(payload: dict[str, Any], *, approved: bool = True) -> dict[str, Any]:
    assertions = {
        "final_artifact_approved": payload.get("final_artifact_approved") is approved,
        "final_artifact_status": payload.get("final_artifact_status") == ("approved" if approved else "needs_final_review"),
        "approval_scope": ((payload.get("final_artifact_approval") or {}).get("approval_scope") == "jamesos_artwork_candidate_human_review_only") if approved else not payload.get("final_artifact_approval"),
        "provider_status": payload.get("provider_status") == "not_ready",
        "printify_status": payload.get("printify_status") == "not_ready",
        "final_print_ready": payload.get("final_print_ready") is False,
    }
    serialized = json.dumps(payload).lower()
    assertions["no_forbidden_readiness_state"] = not any(value in serialized for value in FORBIDDEN_READINESS_VALUES)
    _assert(all(assertions.values()), f"Truthful ending status assertion failed: {assertions}")
    return assertions


def _run_service_flow(job_id: str, source_path: Path, output_root: Path, mode: str, *, approve_final: bool = True,
                      production_strategy: str = "ai_upscale") -> dict[str, Any]:
    started = time.perf_counter()
    transitions: list[dict[str, Any]] = []
    source_before = hash_file(source_path)
    report: dict[str, Any] = {
        "test_job_id": job_id, "mode": mode, "transitions": transitions, "result": "running",
        "synthetic_fixture_style": "illustrative_rocket_badge", "ai_upscale_visual_review_required": True,
    }
    try:
        inspection = image_worker.analyze_output_image_for_job(job_id)
        readiness = inspection["print_readiness_analysis"]
        _assert(readiness["exists"], "Generated source inspection did not find the fixture")
        _assert(not inspection["final_print_ready"], "Concept inspection incorrectly reported final readiness")
        _assert(readiness["background_removal_required"], "Connected exterior background was not detected")
        transitions.append({"stage": "generated_concept_inspected", "source": _image_facts(source_path), "status": inspection})

        concept = approve_concept_for_job(job_id, approved_by="e2e-reviewer")
        _assert(concept["concept_approved"], "Concept approval was not recorded")
        _assert(hash_file(source_path) == source_before, "Concept approval changed source bytes")
        transitions.append({"stage": "concept_approved", "approved_at": concept["approved_at"], "source_sha256": source_before})

        transparent = prepare_transparent_artifact_for_job(job_id)
        derivative_path = Path(transparent["artifact_path"])
        derivative = _image_facts(derivative_path)
        _assert(derivative["mode"] == "RGBA" and derivative["alpha_extrema"] == [0, 255], "Transparent derivative alpha is not [0,255]")
        with Image.open(derivative_path) as image:
            _assert(image.getpixel((0, 0))[3] == 0, "Connected exterior white was not removed")
            enclosed = image.getpixel((384, 311))
            _assert(enclosed[:3] == (255, 255, 255) and enclosed[3] == 255, "Enclosed white artwork was not preserved")
            _assert(image.getpixel((71, 365))[3] == 255 and image.getpixel((18, 150))[3] == 255, "Small colored details were lost")
        _assert(hash_file(source_path) == source_before, "Transparent finishing changed source bytes")
        transitions.append({"stage": "transparent_artifact_prepared", "artifact": derivative, "source_unchanged": True})

        derivative_approval = production_artifact.approve_transparent_artifact_for_job(job_id, approved_by="e2e-reviewer")
        _assert(derivative_approval["approved_artifact_sha256"] == derivative["sha256"], "Derivative approval SHA mismatch")
        transitions.append({"stage": "transparent_artifact_approved", "approval": derivative_approval})

        model_evidence = None
        if production_strategy == "ai_upscale":
            selected = upscale_model_registry.select_upscale_model()
            _assert(selected["model_name"] == DEFAULT_MODEL, "Default model is not RealESRGAN_x2plus.pth")
            _assert(selected["validated"] and selected["production_approved"], "Default model is not effectively SHA-approved")
            _assert(selected["sha256"] == selected["validated_model_sha256"], "Installed model SHA differs from registry approval")
            model_evidence = {key: selected[key] for key in (
                "model_name", "sha256", "validated_model_sha256", "validated", "production_approved", "validation_reason")}
            transitions.append({"stage": "model_verified", "model": model_evidence})

        production = production_artifact.prepare_production_artifact_for_job(
            job_id, confirmed=True, production_strategy=production_strategy,
            artwork_category="flat_geometric" if production_strategy == "precision_resize" else "painterly",
            strategy_selected_by="test_harness",
        )
        stages = production["intermediate_stages"]
        if production_strategy == "ai_upscale":
            _assert([stage["input_dimensions"] for stage in stages] == [list(size) for size in LOGICAL_STAGE_SIZES[:-1]], "Stage input dimensions are wrong")
            _assert([stage["output_dimensions"] for stage in stages] == [list(size) for size in LOGICAL_STAGE_SIZES[1:]], "Stage output dimensions are wrong")
            _assert(stages[1]["input_sha256"] == stages[0]["output_sha256"] and stages[2]["input_sha256"] == stages[1]["output_sha256"], "Stage hashes are not chained")
        else:
            _assert(len(stages) == 1 and stages[0]["processing_method"] == "deterministic_precision_resize", "Precision evidence is not truthful")
            _assert(production["model_name"] is None and not production["ai_model_required"], "Precision path recorded AI evidence")
        for stage in stages:
            facts = _image_facts(Path(stage["output_path"]))
            _assert(facts["mode"] == "RGBA" and facts["alpha_extrema"][0] == 0, f"Stage {stage['stage']} lost transparency")
        transitions.append({"stage": "production_stages_complete", "stages": stages})

        candidate_path = Path(production["production_candidate_path"])
        metadata_path = candidate_path.parent / "production-artifact.json"
        candidate_before, metadata_before = hash_file(candidate_path), hash_file(metadata_path)
        candidate_facts = _image_facts(candidate_path)
        _assert(candidate_facts["dimensions"] == [4500, 5400] and candidate_facts["mode"] == "RGBA", "Candidate is not 4500x5400 RGBA")
        _assert(production["artwork_dimensions"] == [4050, 4050] and production["placement_coordinates"] == [225, 675], "Candidate placement is wrong")
        preview_facts = {name: _image_facts(Path(production[f"{name}_preview_path"])) for name in ("white", "dark", "checkerboard")}
        transitions.append({"stage": "production_candidate_prepared", "candidate": candidate_facts, "metadata_sha256": metadata_before, "previews": preview_facts})

        if not approve_final:
            raise E2EHarnessError("Internal candidate-only flow is not used by mocked service execution")
        try:
            production_artifact.approve_production_artifact_for_job(job_id, approved_by="e2e-reviewer", confirmed=False)
            raise E2EHarnessError("Final approval accepted confirmed=false")
        except job_queue.JobQueueError:
            pass
        approval = production_artifact.approve_production_artifact_for_job(job_id, approved_by="e2e-reviewer", confirmed=True)
        approval_path = candidate_path.parent / "final-artifact-approval.json"
        approval_sha = hash_file(approval_path)
        approved_at = approval["approval"]["approved_at"]
        repeat = production_artifact.approve_production_artifact_for_job(job_id, approved_by="e2e-reviewer", confirmed=True)
        _assert(repeat["idempotent"] and repeat["approval"]["approved_at"] == approved_at, "Final approval repeat was not idempotent")
        _assert(hash_file(approval_path) == approval_sha, "Idempotent approval rewrote its evidence")
        _assert(hash_file(candidate_path) == candidate_before and hash_file(metadata_path) == metadata_before, "Final approval changed immutable production files")
        transitions.append({"stage": "final_artifact_approved", "approval": approval["approval"], "approval_record_sha256": approval_sha, "idempotent_repeat": True})

        payload = job_queue.get_job(job_id)["payload"]
        status_assertions = _status_assertions(payload)
        report.update({
            "source": {"before_sha256": source_before, "after_sha256": hash_file(source_path), **_image_facts(source_path)},
            "derivative": derivative,
            "intermediates": [_image_facts(Path(stage["output_path"])) for stage in stages],
            "candidate": {
                **candidate_facts,
                "artwork_dimensions": production["artwork_dimensions"],
                "placement_coordinates": production["placement_coordinates"],
            },
            "production_metadata": {
                "path": str(metadata_path), "before_sha256": metadata_before,
                "after_sha256": hash_file(metadata_path), "content": production,
            },
            "model": model_evidence,
            "final_approval": {"path": str(approval_path), "sha256": approval_sha, **approval["approval"]},
            "status_assertions": status_assertions,
            "retained_artifact_directory": str(output_root),
            "total_runtime_seconds": time.perf_counter() - started,
            "result": "passed",
            "synthetic_fixture_style": "illustrative_rocket_badge",
            "ai_upscale_visual_review_required": True,
            "retention_status": "mocked_sandbox_cleaned",
        })
        return report
    except Exception as exc:
        report.update({
            "result": "failed",
            "diagnostic": {"type": type(exc).__name__, "message": str(exc), "failed_after_transition": transitions[-1]["stage"] if transitions else "job_created"},
            "retained_artifact_directory": str(output_root),
            "total_runtime_seconds": time.perf_counter() - started,
        })
        raise E2EHarnessFailure(report) from exc


def cleanup_e2e_job(job_id: str, artifact_directory: Path, *, confirmed: bool = False) -> dict[str, Any]:
    validate_test_job_id(job_id)
    if not confirmed:
        raise E2EHarnessError("E2E cleanup requires explicit confirmation.")
    if artifact_directory.is_symlink():
        raise E2EHarnessError("Cleanup refuses a symlinked E2E job directory.")
    resolved = artifact_directory.resolve(strict=True)
    generated_root = image_worker.GENERATED_ROOT.resolve()
    try:
        relative = resolved.relative_to(generated_root)
    except ValueError as exc:
        raise E2EHarnessError("Cleanup directory escapes the generated-artifact root.") from exc
    if resolved.name != job_id or len(relative.parts) != 2:
        raise E2EHarnessError("Cleanup directory is not confined to the requested E2E job.")
    removed = [str(path) for path in sorted(resolved.rglob("*"))]
    shutil.rmtree(resolved)
    queue_records = []
    for folder in job_queue.status_dirs().values():
        record = folder / f"{job_id}.json"
        if record.exists():
            queue_records.append(str(record))
            record.unlink()
    return {"job_id": job_id, "removed_artifact_directory": str(resolved), "removed_paths": removed, "removed_queue_records": queue_records}


def run_mocked(report_path: Path, *, model_hash_mismatch: bool = False,
               production_strategy: str = "ai_upscale") -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="jamesos-e2e-mocked-") as temporary:
        sandbox = Path(temporary)
        queue_root = sandbox / "Queue"
        generated_root = sandbox / "Generated"
        comfy_root = sandbox / "ComfyUI"
        model_root = comfy_root / "models" / "upscale_models"
        model_root.mkdir(parents=True)
        model_bytes = b"deterministic mocked RealESRGAN x2 model"
        model_path = model_root / DEFAULT_MODEL
        model_path.write_bytes(model_bytes)
        approved_model_sha = sha256(model_bytes).hexdigest()
        registry = sandbox / "upscale_models.yaml"
        registry.write_text(yaml.safe_dump({"models": {DEFAULT_MODEL: {
            "model_name": DEFAULT_MODEL, "scale_factor": 2, "model_family": "Real-ESRGAN",
            "intended_use": "mocked e2e artwork", "enabled": True, "validated": True, "default": True,
            "validated_model_sha256": approved_model_sha,
            "preferred_alpha_resize_method": "lanczos", "preferred_edge_bleed_iterations": 16,
            "preferred_edge_bleed_alpha_threshold": 128, "validation_output_filename": "e2e.png",
        }}}), encoding="utf-8")
        job_id = unique_test_job_id(suffix="mocked001")
        output_root = generated_root / datetime.now().date().isoformat() / job_id
        source_path = output_root / "generated-concept.png"
        create_concept_fixture(source_path)
        workflows: list[dict[str, Any]] = []
        responses: list[dict[str, Any]] = []
        patches = (
            patch.object(job_queue, "QUEUE_ROOT", queue_root), patch.object(job_queue, "PENDING", queue_root / "pending"),
            patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"), patch.object(job_queue, "PROCESSED", queue_root / "processed"),
            patch.object(job_queue, "FAILED", queue_root / "failed"), patch.object(job_queue, "REPORT_PATH", sandbox / "queue-report.md"),
            patch.object(image_worker, "GENERATED_ROOT", generated_root),
            patch.object(upscale_model_registry, "REGISTRY_PATH", registry), patch.object(upscale_model_registry, "COMFYUI_ROOT", comfy_root),
            patch.object(production_artifact, "COMFYUI_INPUT_ROOT", comfy_root / "input"),
            patch.object(production_artifact, "COMFYUI_OUTPUT_ROOT", comfy_root / "output"),
            patch.object(production_artifact, "_run_stage", side_effect=_mock_stage_runner(workflows, responses)),
        )
        report: dict[str, Any] = {"test_job_id": job_id, "mode": "mocked", "result": "failed"}
        with ExitStack() as stack:
            for item in patches:
                stack.enter_context(item)
            create_e2e_job(job_id, source_path)
            if model_hash_mismatch:
                model_path.write_bytes(b"mismatched model bytes")
            try:
                report = _run_service_flow(job_id, source_path, output_root, "mocked", production_strategy=production_strategy)
                report["mocked_workflows"] = workflows
                report["mocked_comfyui_responses"] = responses
            except E2EHarnessFailure as exc:
                report = exc.report
            except Exception as exc:
                report.setdefault("diagnostic", {"type": type(exc).__name__, "message": str(exc)})
            finally:
                report["retained_artifact_directory"] = ""
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        if report.get("result") != "passed":
            raise E2EHarnessError(str(report.get("diagnostic") or "Mocked E2E pipeline failed"))
        return report


def _api_post(base_url: str, api_key: str, route: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{route}", data=json.dumps(body or {}).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-JamesOS-Key": api_key}, method="POST",
    )
    try:
        with urlopen(request, timeout=3600) as response:
            result = json.loads(response.read().decode("utf-8") or "{}")
    except (HTTPError, URLError) as exc:
        raise E2EHarnessError(f"Local JamesOS API request failed: {exc}") from exc
    if result.get("status") == "error":
        raise E2EHarnessError(f"JamesOS API stage failed: {result}")
    return result


def run_live(
    report_path: Path, *, confirmed: bool, base_url: str = "http://127.0.0.1:8787",
) -> dict[str, Any]:
    if not confirmed:
        raise E2EHarnessError("Live mode requires --confirm-live.")
    job_id = unique_test_job_id()
    validate_test_job_id(job_id)
    output_root = image_worker.GENERATED_ROOT / datetime.now().date().isoformat() / job_id
    source_path = output_root / "generated-concept.png"
    create_concept_fixture(source_path)
    create_e2e_job(job_id, source_path)
    started = time.perf_counter()
    transitions: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "test_job_id": job_id, "mode": "live", "transitions": transitions, "result": "running",
        "synthetic_fixture_style": "illustrative_rocket_badge", "ai_upscale_visual_review_required": True,
    }
    try:
        api_key_path = VAULT / "JamesOS" / "Secrets" / "api_key.txt"
        if not api_key_path.is_file():
            raise E2EHarnessError("JamesOS API key is not configured.")
        api_key = api_key_path.read_text(encoding="utf-8").strip()
        transitions.append({"stage": "generated_concept_inspected", "response": _api_post(base_url, api_key, f"/image-worker/jobs/{job_id}/analyze-output")})
        transitions.append({"stage": "concept_approved", "response": _api_post(base_url, api_key, f"/image-worker/jobs/{job_id}/approve-concept", {"approved_by": "e2e-harness-automated-stage-gate"})})
        transitions.append({"stage": "transparent_artifact_prepared", "response": _api_post(base_url, api_key, f"/image-worker/jobs/{job_id}/prepare-transparent-artifact")})
        transitions.append({"stage": "transparent_artifact_approved", "response": _api_post(base_url, api_key, f"/image-worker/jobs/{job_id}/approve-transparent-artifact", {"approved_by": "e2e-harness-automated-stage-gate"})})
        inventory = upscale_model_registry.select_upscale_model()
        _assert(inventory["model_name"] == DEFAULT_MODEL and inventory["production_approved"], "Live default upscale model is not SHA-approved")
        transitions.append({"stage": "model_verified", "model_name": inventory["model_name"], "model_sha256": inventory["sha256"]})
        transitions.append({"stage": "production_candidate_prepared", "response": _api_post(base_url, api_key, f"/image-worker/jobs/{job_id}/prepare-production-artifact", {"confirmed": True, "upscale_model_name": DEFAULT_MODEL})})
        payload = job_queue.get_job(job_id)["payload"]
        production = payload["production_artifact"]
        candidate_path = Path(production["production_candidate_path"])
        metadata_path = candidate_path.parent / "production-artifact.json"
        approval_path = candidate_path.parent / "final-artifact-approval.json"
        _assert(not approval_path.exists(), "Live candidate creation unexpectedly created final approval evidence")
        previews = {name: _image_facts(Path(production[f"{name}_preview_path"])) for name in ("white", "dark", "checkerboard")}
        status_payload = dict(payload)
        status_payload.update({"final_artifact_approved": False, "final_artifact_status": "needs_final_review"})
        report.update({
            "result": "candidate_ready_for_visual_review", "status_assertions": _status_assertions(status_payload, approved=False),
            "final_artifact_approved": False, "final_artifact_status": "needs_final_review",
            "production_artifact_status": "needs_final_review", "approval_scope": "not_yet_approved",
            "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
            "source": _image_facts(source_path), "derivative": _image_facts(Path(payload["transparent_artifact_path"])),
            "intermediates": [_image_facts(Path(stage["output_path"])) for stage in production["intermediate_stages"]],
            "candidate": _image_facts(candidate_path),
            "production_metadata": {"path": str(metadata_path), "sha256": hash_file(metadata_path), "content": production},
            "previews": previews,
            "model": {"model_name": production["model_name"], "model_sha256": production["model_sha256"]},
            "retained_artifact_directory": str(output_root), "total_runtime_seconds": time.perf_counter() - started,
            "retention_status": "retained_until_explicit_cleanup",
        })
    except Exception as exc:
        report.update({"result": "failed", "diagnostic": {"type": type(exc).__name__, "message": str(exc)}, "retained_artifact_directory": str(output_root), "total_runtime_seconds": time.perf_counter() - started})
        raise
    finally:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
        retained_report = output_root / REPORT_FILENAME
        if output_root.exists() and retained_report.resolve() != report_path.resolve():
            retained_report.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def approve_live(report_path: Path, *, job_id: str, approved_by: str, confirmed: bool,
                 base_url: str = "http://127.0.0.1:8787") -> dict[str, Any]:
    started = time.perf_counter()
    validate_test_job_id(job_id)
    if not approved_by.strip():
        raise E2EHarnessError("approve-live requires a non-empty --approved-by human name.")
    if not confirmed:
        raise E2EHarnessError("approve-live requires --confirm-visual-review.")
    job = job_queue.get_job(job_id)
    payload = job.get("payload") or {}
    if not payload.get("e2e_test_job"):
        raise E2EHarnessError("Approval is restricted to isolated E2E artwork jobs.")
    payload = job.get("payload") or {}
    already_approved = bool(payload.get("final_artifact_approved") or payload.get("final_artifact_approval"))
    evidence = (validate_existing_approval_evidence(job_id, approved_by.strip(), job)
                if already_approved else validate_candidate_ready_evidence(job_id, job))
    production = evidence["production"]
    derivative, candidate, metadata = evidence["derivative_path"], evidence["candidate_path"], evidence["metadata_path"]
    candidate_before, metadata_before = evidence["candidate"]["sha256"], evidence["production_metadata"]["sha256"]
    model = evidence["model"]
    _preflight_live_report_path(report_path, candidate.parents[2])
    approval_path = candidate.parent / "final-artifact-approval.json"
    api_responses = []
    if already_approved:
        approval, approval_sha = evidence["final_approval"], evidence["final_approval_sha256"]
        approved_at = approval["approved_at"]
        refreshed = payload
    else:
        api_key = (VAULT / "JamesOS" / "Secrets" / "api_key.txt").read_text(encoding="utf-8").strip()
        route = f"/image-worker/jobs/{job_id}/approve-production-artifact"
        body = {"confirmed": True, "approved_by": approved_by.strip()}
        api_responses.append(_api_post(base_url, api_key, route, body))
        _assert(approval_path.is_file(), "Approval service did not create separate approval evidence")
        approval_sha, approval = hash_file(approval_path), json.loads(approval_path.read_text(encoding="utf-8"))
        approved_at = approval["approved_at"]
        _assert(hash_file(candidate) == candidate_before and hash_file(metadata) == metadata_before, "Approval changed immutable production files")
        refreshed = job_queue.get_job(job_id)["payload"]
    assertions = _status_assertions(refreshed)
    report = {
        "test_job_id": job_id, "mode": "approve-live", "result": "approved_after_human_visual_review",
        "final_artifact_approved": True, "final_artifact_status": "approved",
        "approval_scope": "jamesos_artwork_candidate_human_review_only",
        "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
        "candidate": {**_image_facts(candidate), "before_sha256": candidate_before, "after_sha256": hash_file(candidate)},
        "production_metadata": {"path": str(metadata), "before_sha256": metadata_before, "after_sha256": hash_file(metadata)},
        "derivative": _image_facts(derivative),
        "model": ({"model_name": model["model_name"], "sha256": model["sha256"]} if model else None),
        "final_approval": {"path": str(approval_path), "sha256": approval_sha, "approved_at": approved_at, "content": approval},
        "idempotent": already_approved, "status_assertions": assertions, "api_responses": api_responses,
        "retained_artifact_directory": str(candidate.parents[2]), "retention_status": "retained_until_explicit_cleanup",
        "total_runtime_seconds": time.perf_counter() - started,
    }
    try:
        report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    except OSError as exc:
        return {
            "test_job_id": job_id, "mode": "approve-live", "result": "approval_completed_report_write_failed",
            "approval_side_effect_completed": True, "report_write_failed": True,
            "approval_path": str(approval_path), "approval_sha256": approval_sha,
            "approved_at": approved_at, "idempotent": already_approved,
            "diagnostic": {"type": type(exc).__name__, "message": str(exc)},
        }
    return report


def _evidence_error(evidence_type: str, expected: Any, actual: Any, path: Path | str) -> None:
    raise E2EHarnessError(
        f"Authoritative evidence mismatch: evidence_type={evidence_type}; expected_sha={expected or '<missing>'}; "
        f"actual_sha={actual or '<missing>'}; authoritative_source_path={path}"
    )


def _validate_live_evidence(job_id: str, job: dict[str, Any] | None = None) -> dict[str, Any]:
    """Validate an existing candidate without trusting or modifying an E2E report."""
    validate_test_job_id(job_id)
    job = job or job_queue.get_job(job_id)
    payload = job.get("payload") or {}
    if not payload.get("e2e_test_job"):
        raise E2EHarnessError("Recovery is restricted to isolated E2E artwork jobs.")
    production = payload.get("production_artifact")
    if not isinstance(production, dict):
        raise E2EHarnessError("Authoritative production metadata is missing from job state.")
    _assert(payload.get("production_artifact_status") == "needs_final_review" and
            production.get("production_artifact_status") == "needs_final_review",
            "Production artifact must be needs_final_review")
    derivative, candidate, metadata, approval_path = production_artifact._critical_job_paths(job_id, payload)
    for evidence_type, path in (("transparent_derivative", derivative), ("production_candidate", candidate),
                                ("production_metadata", metadata)):
        if not path.is_file():
            _evidence_error(evidence_type, "file-present", "file-missing", path)
    try:
        file_metadata = json.loads(metadata.read_text(encoding="utf-8"))
    except Exception as exc:
        raise E2EHarnessError(f"Authoritative production metadata is unreadable: {exc}") from exc
    if file_metadata != production:
        raise E2EHarnessError(f"Authoritative evidence mismatch: evidence_type=production_metadata_content; "
                              f"expected_sha=job-state-content; actual_sha=file-content; authoritative_source_path={metadata}")
    candidate_sha = hash_file(candidate)
    if candidate_sha != production.get("production_candidate_sha256"):
        _evidence_error("production_candidate", production.get("production_candidate_sha256"), candidate_sha, candidate)
    derivative_sha = hash_file(derivative)
    derivative_approval = payload.get("transparent_derivative_approval")
    if not isinstance(derivative_approval, dict):
        _evidence_error("transparent_derivative_approval", "SHA-bound approval", "missing", derivative)
    approved_path = Path(str(derivative_approval.get("approved_artifact_path") or "")).expanduser().resolve()
    approved_sha = derivative_approval.get("approved_artifact_sha256")
    if approved_path != derivative:
        raise E2EHarnessError(f"Authoritative evidence mismatch: evidence_type=transparent_derivative_approval_path; "
                              f"expected_sha={derivative}; actual_sha={approved_path}; authoritative_source_path={derivative}")
    if derivative_sha != approved_sha:
        _evidence_error("transparent_derivative_approval", approved_sha, derivative_sha, derivative)
    if production.get("approved_source_sha256") != approved_sha:
        _evidence_error("production_approved_source", production.get("approved_source_sha256"), approved_sha, metadata)
    source = Path(str(payload.get("output_image_path") or "")).expanduser().resolve()
    if not source.is_file():
        _evidence_error("generated_source", "file-present", "file-missing", source)
    finishing = payload.get("finishing_metadata") or {}
    source_sha = hash_file(source)
    if source_sha != finishing.get("source_sha256_before") or source_sha != finishing.get("source_sha256_after"):
        _evidence_error("generated_source", finishing.get("source_sha256_before"), source_sha, source)
    stages = production.get("intermediate_stages")
    selected_strategy = production.get("selected_strategy") or "ai_upscale"
    expected_stage_count = 3 if selected_strategy == "ai_upscale" else 1
    if not isinstance(stages, list) or len(stages) != expected_stage_count:
        raise E2EHarnessError(f"Authoritative {selected_strategy} evidence must contain exactly {expected_stage_count} processing stage(s).")
    intermediates = []
    expected_input_sha = approved_sha
    for index, stage in enumerate(stages, 1):
        path = Path(str(stage.get("output_path") or "")).expanduser().resolve()
        actual = hash_file(path) if path.is_file() else "file-missing"
        if stage.get("stage") != index or stage.get("input_sha256") != expected_input_sha:
            _evidence_error(f"production_stage_{index}_input", expected_input_sha, stage.get("input_sha256"), metadata)
        if actual != stage.get("output_sha256"):
            _evidence_error(f"production_stage_{index}_output", stage.get("output_sha256"), actual, path)
        intermediates.append(_image_facts(path))
        expected_input_sha = actual
    previews = {}
    for name in ("white", "dark", "checkerboard"):
        path = Path(str(production.get(f"{name}_preview_path") or "")).expanduser().resolve()
        actual = hash_file(path) if path.is_file() else "file-missing"
        if actual != production.get(f"{name}_preview_sha256"):
            _evidence_error(f"{name}_preview", production.get(f"{name}_preview_sha256"), actual, path)
        previews[name] = _image_facts(path)
    model = None
    if selected_strategy == "ai_upscale":
        model = upscale_model_registry.select_upscale_model(production.get("model_name"))
        if not model.get("validated") or not model.get("production_approved") or model.get("sha256") != production.get("model_sha256"):
            _evidence_error("installed_validated_model", production.get("model_sha256"), model.get("sha256"), model.get("path", production.get("model_name")))
    elif production.get("model_name") or production.get("model_sha256") or production.get("ai_model_required") is not False:
        raise E2EHarnessError("Precision-resize evidence must not require or identify an AI model.")
    return {
        "payload": payload, "production": production, "source": _image_facts(source),
        "derivative": _image_facts(derivative), "derivative_approval": dict(derivative_approval),
        "intermediates": intermediates, "candidate": _image_facts(candidate), "previews": previews,
        "production_metadata": {"path": str(metadata), "sha256": hash_file(metadata), "content": production},
        "model": model, "derivative_path": derivative, "candidate_path": candidate, "metadata_path": metadata,
        "approval_path": approval_path,
    }


def validate_candidate_ready_evidence(job_id: str, job: dict[str, Any] | None = None) -> dict[str, Any]:
    evidence = _validate_live_evidence(job_id, job)
    payload, approval_path = evidence["payload"], evidence["approval_path"]
    if approval_path.exists() or payload.get("final_artifact_approved") or payload.get("final_artifact_approval"):
        raise E2EHarnessError("Existing final approval evidence is not candidate-ready recovery state.")
    return evidence


def validate_existing_approval_evidence(
    job_id: str, requested_reviewer: str, job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = _validate_live_evidence(job_id, job)
    payload, approval_path = evidence["payload"], evidence["approval_path"]
    recorded = payload.get("final_artifact_approval")
    if not payload.get("final_artifact_approved") or not isinstance(recorded, dict) or not approval_path.is_file():
        raise E2EHarnessError("Partial or contradictory final approval evidence is present.")
    try:
        file_approval = json.loads(approval_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise E2EHarnessError(f"Final approval evidence is unreadable: {exc}") from exc
    if file_approval != recorded:
        raise E2EHarnessError(f"Authoritative evidence mismatch: evidence_type=final_approval_content; "
                              f"expected_sha=job-state-content; actual_sha=file-content; authoritative_source_path={approval_path}")
    approval_sha = hash_file(approval_path)
    if approval_sha != payload.get("final_artifact_approval_record_sha256"):
        _evidence_error("final_approval_record", payload.get("final_artifact_approval_record_sha256"), approval_sha, approval_path)
    checks = {
        "approved_artifact_sha256": evidence["candidate"]["sha256"],
        "production_metadata_sha256": evidence["production_metadata"]["sha256"],
    }
    for key, actual in checks.items():
        if recorded.get(key) != actual:
            _evidence_error(f"final_approval_{key}", recorded.get(key), actual, approval_path)
    derivative_evidence = recorded.get("derivative_evidence") or {}
    if derivative_evidence.get("approved_artifact_sha256") != evidence["derivative"]["sha256"]:
        _evidence_error("final_approval_derivative", derivative_evidence.get("approved_artifact_sha256"),
                        evidence["derivative"]["sha256"], approval_path)
    model_evidence = recorded.get("model_evidence") or {}
    if evidence["model"] is not None and model_evidence.get("model_sha256") != evidence["model"].get("sha256"):
        _evidence_error("final_approval_model", model_evidence.get("model_sha256"), evidence["model"].get("sha256"), approval_path)
    existing_reviewer = str(recorded.get("approved_by") or "")
    if existing_reviewer != requested_reviewer:
        raise E2EHarnessError(f"Existing approval reviewer differs: existing_reviewer={existing_reviewer}; "
                              f"requested_reviewer={requested_reviewer}")
    evidence.update({"final_approval": file_approval, "final_approval_sha256": approval_sha})
    return evidence


def _preflight_live_report_path(report_path: Path, job_root: Path) -> None:
    if str(report_path) in ("", "."):
        raise E2EHarnessError("approve-live requires a non-empty report file path.")
    raw = report_path.expanduser()
    if raw.exists() and raw.is_dir():
        raise E2EHarnessError(f"approve-live report path is an existing directory: {raw}")
    parent = raw.parent.resolve()
    root = job_root.resolve()
    if not parent.is_relative_to(root):
        raise E2EHarnessError(f"approve-live report path must be confined to the E2E job directory: {root}")
    parent.mkdir(parents=True, exist_ok=True)
    if not parent.is_dir() or not os.access(parent, os.W_OK):
        raise E2EHarnessError(f"approve-live report parent is not writable: {parent}")
    if raw.exists() and (raw.is_symlink() or not raw.is_file() or not os.access(raw, os.W_OK)):
        raise E2EHarnessError(f"approve-live report destination is not a writable regular file: {raw}")


def resume_live(report_path: Path, *, job_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    evidence = validate_candidate_ready_evidence(job_id)
    payload, production = evidence["payload"], evidence["production"]
    status_payload = dict(payload)
    status_payload.update({"final_artifact_approved": False, "final_artifact_status": "needs_final_review"})
    report = {
        "test_job_id": job_id, "mode": "resume-live", "result": "candidate_ready_for_visual_review",
        "recovery_reason": "client_interrupted_after_server_processing",
        "transitions": [
            {"stage": "generated_concept_inspected", "artifact": evidence["source"]},
            {"stage": "concept_approved", "approved_by": payload.get("concept_approved_by"), "approved_at": payload.get("concept_approved_at")},
            {"stage": "transparent_artifact_prepared", "artifact": evidence["derivative"]},
            {"stage": "transparent_artifact_approved", "approval": evidence["derivative_approval"]},
            {"stage": "model_verified", "model_name": production["model_name"], "model_sha256": production["model_sha256"]},
            {"stage": "production_stages_complete", "stages": production["intermediate_stages"]},
            {"stage": "production_candidate_prepared", "candidate": evidence["candidate"], "previews": evidence["previews"]},
        ],
        "source": evidence["source"], "derivative": evidence["derivative"],
        "derivative_approval": evidence["derivative_approval"], "intermediates": evidence["intermediates"],
        "candidate": evidence["candidate"], "production_metadata": evidence["production_metadata"],
        "previews": evidence["previews"],
        "model": {"model_name": production["model_name"], "model_sha256": production["model_sha256"]},
        "final_artifact_approved": False, "final_artifact_status": "needs_final_review",
        "production_artifact_status": "needs_final_review", "approval_scope": "not_yet_approved",
        "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
        "status_assertions": _status_assertions(status_payload, approved=False),
        "retained_artifact_directory": str(evidence["candidate_path"].parents[2]),
        "retention_status": "retained_until_explicit_cleanup", "total_runtime_seconds": time.perf_counter() - started,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated JamesOS artwork pipeline E2E harness.")
    parser.add_argument("--mode", choices=("mocked", "live", "resume-live", "approve-live", "cleanup"), default="mocked")
    parser.add_argument("--report-path", type=Path, default=Path.cwd() / REPORT_FILENAME)
    parser.add_argument("--confirm-live", action="store_true")
    parser.add_argument("--job-id")
    parser.add_argument("--approved-by")
    parser.add_argument("--confirm-visual-review", action="store_true")
    parser.add_argument("--cleanup", action="store_true")
    parser.add_argument("--confirm-cleanup", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--production-strategy", choices=("ai_upscale", "precision_resize"), default="ai_upscale")
    args = parser.parse_args()
    try:
        if args.mode == "mocked":
            result = run_mocked(args.report_path, production_strategy=args.production_strategy)
        elif args.mode == "live":
            if args.cleanup or args.confirm_cleanup or args.confirm_visual_review or args.approved_by:
                raise E2EHarnessError("Live candidate creation cannot approve or clean up in the same command.")
            result = run_live(args.report_path, confirmed=args.confirm_live, base_url=args.base_url)
        elif args.mode == "resume-live":
            if args.confirm_live or args.cleanup or args.confirm_cleanup or args.confirm_visual_review or args.approved_by:
                raise E2EHarnessError("resume-live is inspection-only and accepts no processing, approval, or cleanup flags.")
            if not args.job_id:
                raise E2EHarnessError("resume-live requires --job-id.")
            result = resume_live(args.report_path, job_id=args.job_id)
        elif args.mode == "approve-live":
            if args.confirm_live or args.cleanup or args.confirm_cleanup:
                raise E2EHarnessError("approve-live is a separate approval-only command.")
            result = approve_live(args.report_path, job_id=args.job_id or "", approved_by=args.approved_by or "",
                                  confirmed=args.confirm_visual_review, base_url=args.base_url)
        else:
            if not args.cleanup or not args.confirm_cleanup or not args.job_id:
                raise E2EHarnessError("Cleanup requires --job-id, --cleanup, and --confirm-cleanup.")
            validate_test_job_id(args.job_id)
            payload = (job_queue.get_job(args.job_id).get("payload") or {})
            if not payload.get("e2e_test_job"):
                raise E2EHarnessError("Cleanup is restricted to isolated E2E artwork jobs.")
            source = Path(payload.get("output_image_path") or "")
            artifact_directory = source.parent
            cleanup_result = cleanup_e2e_job(args.job_id, artifact_directory, confirmed=True)
            result = {"test_job_id": args.job_id, "mode": "cleanup", "result": "cleaned", **cleanup_result}
            args.report_path.parent.mkdir(parents=True, exist_ok=True)
            args.report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"result": "failed", "error": str(exc), "report_path": str(args.report_path)}, indent=2))
        return 1
    summary = {"result": result["result"], "test_job_id": result["test_job_id"], "report_path": str(args.report_path)}
    if args.mode == "live":
        summary.update({
            "retained_artifact_directory": result["retained_artifact_directory"],
            "generated_source_path": result["source"]["path"], "transparent_derivative_path": result["derivative"]["path"],
            **{f"stage_{index}_path": item["path"] for index, item in enumerate(result["intermediates"], 1)},
            "production_candidate_path": result["candidate"]["path"],
            **{f"{name}_preview_path": value["path"] for name, value in result["previews"].items()},
            "production_metadata_path": result["production_metadata"]["path"],
            "human_approval_command": f"{sys.executable} {Path(__file__).resolve()} --mode approve-live --job-id {result['test_job_id']} --approved-by <human-name> --confirm-visual-review",
        })
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
