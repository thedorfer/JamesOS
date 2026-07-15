from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any

from PIL import Image, ImageDraw
import yaml

from jamesos.services import comfyui_client, upscale_model_registry
from jamesos.services.job_queue import JobQueueError, append_job_log, get_job, mark_step, remove_job_payload_keys, update_job_payload
from jamesos.services.upscale_validator import (
    COMFYUI_INPUT_ROOT,
    COMFYUI_URL,
    build_upscale_validation_workflow,
    halo_diagnostics,
    prepare_halo_safe_rgb,
    resize_alpha,
)


TARGET_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "production_artifact.yaml"
COMFYUI_OUTPUT_ROOT = Path.home() / "AI" / "ComfyUI" / "output"
STAGE_SIZES = ((768, 768), (1536, 1536), (3072, 3072), (6144, 6144))
PREVIEW_BACKGROUNDS = {"white": (255, 255, 255, 255), "dark": (24, 24, 24, 255)}


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _remove_comfyui_outputs(outputs: list[dict[str, Any]]) -> None:
    """Remove only downloaded files explicitly reported from ComfyUI's output root."""
    root = COMFYUI_OUTPUT_ROOT.resolve()
    for output in outputs:
        metadata = output.get("metadata") if isinstance(output.get("metadata"), dict) else {}
        if str(metadata.get("type") or "output") != "output":
            continue
        filename = str(metadata.get("filename") or output.get("filename") or "")
        subfolder = str(metadata.get("subfolder") or "")
        if not filename or Path(filename).name != filename:
            continue
        candidate = (root / subfolder / filename).resolve()
        if candidate.is_relative_to(root):
            candidate.unlink(missing_ok=True)


def _payload(job: dict[str, Any]) -> dict[str, Any]:
    payload = job.get("payload") or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _artifact_path_for_job(job_id: str, payload: dict[str, Any]) -> Path:
    configured = str(payload.get("transparent_artifact_path") or "").strip()
    if not configured:
        artifact = payload.get("design_artifact") if isinstance(payload.get("design_artifact"), dict) else {}
        configured = str(artifact.get("transparent_artifact_path") or "").strip()
    if not configured:
        raise JobQueueError("Transparent derivative is not recorded for this job.")
    path = Path(configured).expanduser().resolve()
    if not path.is_file() or path.name != "transparent_artifact.png":
        raise JobQueueError("The recorded transparent derivative is missing or invalid.")
    return path


def load_production_target(path: Path | None = None) -> dict[str, Any]:
    try:
        loaded = yaml.safe_load((path or TARGET_CONFIG_PATH).read_text(encoding="utf-8")) or {}
        target = dict(loaded.get("production_target") or {})
    except Exception as exc:
        raise JobQueueError(f"Production target configuration could not be read: {exc}") from exc
    width, height = target.get("canvas_width"), target.get("canvas_height")
    margin = target.get("safe_margin_percent")
    if not all(isinstance(value, int) and not isinstance(value, bool) and value > 0 for value in (width, height)):
        raise JobQueueError("Production canvas dimensions must be positive integers.")
    if not isinstance(margin, (int, float)) or isinstance(margin, bool) or not 0 <= margin < 50:
        raise JobQueueError("Production safe margin percent must be from 0 up to (but not including) 50.")
    if target.get("horizontal_alignment") != "center" or target.get("vertical_alignment") != "center":
        raise JobQueueError("Only centered production placement is currently supported.")
    if target.get("output_mode") != "RGBA" or target.get("transparent_background") is not True:
        raise JobQueueError("Production output must be transparent RGBA.")
    if target.get("placement_resize_method") != "lanczos":
        raise JobQueueError("Production placement resize method must be lanczos.")
    return target


def approve_transparent_artifact_for_job(job_id: str, approved_by: str = "James") -> dict[str, Any]:
    job = get_job(job_id)
    payload = _payload(job)
    artifact_path = _artifact_path_for_job(job_id, payload)
    approved_by = str(approved_by or "James").strip() or "James"
    approval = {
        "approved_artifact_path": str(artifact_path),
        "approved_artifact_sha256": _hash_file(artifact_path),
        "approved_by": approved_by,
        "approved_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    payload["transparent_derivative_approval"] = approval
    update_job_payload(job_id, payload)
    append_job_log(job_id, f"Transparent derivative approved by {approved_by}")
    mark_step(job_id, "transparent derivative approved", "complete", "SHA-bound derivative approval recorded.")
    return {"status": "ok", "job_id": job_id, **approval}


def calculate_placement(artwork_size: tuple[int, int], target: dict[str, Any]) -> dict[str, Any]:
    canvas_width, canvas_height = target["canvas_width"], target["canvas_height"]
    margin_x = round(canvas_width * target["safe_margin_percent"] / 100)
    margin_y = round(canvas_height * target["safe_margin_percent"] / 100)
    bound_width, bound_height = canvas_width - 2 * margin_x, canvas_height - 2 * margin_y
    scale = min(bound_width / artwork_size[0], bound_height / artwork_size[1], 1.0)
    width = max(1, round(artwork_size[0] * scale))
    height = max(1, round(artwork_size[1] * scale))
    x, y = (canvas_width - width) // 2, (canvas_height - height) // 2
    return {
        "safe_margin_pixels": {"left": margin_x, "right": margin_x, "top": margin_y, "bottom": margin_y},
        "safe_bounds": [margin_x, margin_y, canvas_width - margin_x, canvas_height - margin_y],
        "artwork_dimensions": [width, height],
        "placement_coordinates": [x, y],
        "placement_scale": scale,
    }


def place_artwork_on_canvas(artwork: Image.Image, target: dict[str, Any]) -> tuple[Image.Image, dict[str, Any]]:
    placement = calculate_placement(artwork.size, target)
    target_size = tuple(placement["artwork_dimensions"])
    if target_size[0] > artwork.width or target_size[1] > artwork.height:
        raise JobQueueError("Production placement must not upscale artwork.")
    placed = artwork.convert("RGBA")
    if placed.size != target_size:
        resized = placed.resize(target_size, Image.Resampling.LANCZOS)
        placed.close()
        placed = resized
    try:
        canvas = Image.new("RGBA", (target["canvas_width"], target["canvas_height"]), (0, 0, 0, 0))
        canvas.alpha_composite(placed, tuple(placement["placement_coordinates"]))
    finally:
        placed.close()
    return canvas, placement


def _checkerboard(size: tuple[int, int], tile_size: int = 48) -> Image.Image:
    image = Image.new("RGBA", size, (224, 224, 224, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], tile_size):
        for x in range(0, size[0], tile_size):
            if (x // tile_size + y // tile_size) % 2:
                draw.rectangle((x, y, min(x + tile_size - 1, size[0] - 1), min(y + tile_size - 1, size[1] - 1)), fill=(176, 176, 176, 255))
    return image


def _verified_rgba(path: Path, expected_size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as image:
        image.load()
        if image.mode != "RGBA" or image.size != expected_size:
            raise JobQueueError(f"Stage artifact must be RGBA at {expected_size[0]}x{expected_size[1]}.")
        alpha_extrema = image.getchannel("A").getextrema()
        if alpha_extrema[0] >= 255:
            raise JobQueueError("Stage artifact lost meaningful transparency.")
        return image.copy()


def _run_stage(
    *, job_id: str, stage_number: int, source_path: Path, output_path: Path, debug_folder: Path,
    selected_model: dict[str, Any], settings: dict[str, Any], expected_input: tuple[int, int], expected_output: tuple[int, int],
) -> dict[str, Any]:
    source_hash_before = _hash_file(source_path)
    source = _verified_rgba(source_path, expected_input)
    stage_started = time.perf_counter()
    input_name = f"jamesos-{job_id}-production-stage-{stage_number}-rgb.png"
    comfy_input = COMFYUI_INPUT_ROOT / input_name
    workflow = build_upscale_validation_workflow(input_name, selected_model["model_name"])
    workflow_path = debug_folder / f"stage-{stage_number}-submitted-workflow.json"
    workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    prompt_id = ""
    prepared: Image.Image | None = None
    rgb: Image.Image | None = None
    alpha: Image.Image | None = None
    verified: Image.Image | None = None
    outputs: list[dict[str, Any]] = []
    try:
        prepared = prepare_halo_safe_rgb(
            source,
            bleed_iterations=settings["edge_bleed_iterations"],
            alpha_threshold=settings["edge_bleed_alpha_threshold"],
        )
        COMFYUI_INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        prepared.save(comfy_input, format="PNG")
        prepared.close()
        prepared = None
        if not comfyui_client.is_running(COMFYUI_URL, timeout=2.0):
            raise JobQueueError("ComfyUI is not running at http://127.0.0.1:8188.")
        try:
            queued = comfyui_client.queue_prompt(workflow, api_url=COMFYUI_URL)
        except comfyui_client.ComfyUIHTTPError as exc:
            error_path = debug_folder / f"stage-{stage_number}-comfy-error.json"
            error_path.write_text(json.dumps({"status_code": exc.status_code, "response_body": exc.response_body, "response_json": exc.response_json}, indent=2), encoding="utf-8")
            raise JobQueueError(f"ComfyUI rejected production stage {stage_number}: {exc.response_body or exc}") from exc
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise JobQueueError(f"ComfyUI did not return a prompt ID for production stage {stage_number}.")
        completed = comfyui_client.wait_for_completion(prompt_id, api_url=COMFYUI_URL)
        if completed.get("status") != "completed":
            raise JobQueueError(f"Production stage {stage_number} did not complete: {completed.get('status')}")
        outputs = comfyui_client.get_output_images(prompt_id, api_url=COMFYUI_URL)
        if len(outputs) != 1 or not outputs[0].get("content"):
            raise JobQueueError(f"Production stage {stage_number} must return exactly one RGB image.")
        with Image.open(BytesIO(bytes(outputs[0]["content"]))) as result:
            result.load()
            if result.size != expected_output:
                raise JobQueueError(f"Production stage {stage_number} output must be {expected_output[0]}x{expected_output[1]}.")
            rgb = result.convert("RGB")
        _remove_comfyui_outputs(outputs)
        outputs.clear()
        alpha = resize_alpha(source.getchannel("A"), expected_output, settings["alpha_resize_method"])
        rgb.putalpha(alpha)
        alpha.close()
        alpha = None
        output_path.parent.mkdir(parents=True, exist_ok=True)
        rgb.save(output_path, format="PNG")
        rgb.close()
        rgb = None
        verified = _verified_rgba(output_path, expected_output)
        if _hash_file(source_path) != source_hash_before:
            raise JobQueueError(f"Production stage {stage_number} source changed during processing.")
        record = {
            "stage": stage_number,
            "input_path": str(source_path), "output_path": str(output_path),
            "input_dimensions": list(expected_input), "output_dimensions": list(expected_output),
            "input_sha256": source_hash_before, "output_sha256": _hash_file(output_path),
            "model_name": selected_model["model_name"], "model_sha256": selected_model["sha256"],
            "settings": dict(settings), "alpha_extrema": list(verified.getchannel("A").getextrema()),
            "alpha_diagnostics": halo_diagnostics(verified),
            "execution_time_seconds": time.perf_counter() - stage_started, "comfyui_prompt_id": prompt_id,
            "workflow_path": str(workflow_path),
        }
        return record
    finally:
        _remove_comfyui_outputs(outputs)
        comfy_input.unlink(missing_ok=True)
        for image in (prepared, rgb, alpha, verified, source):
            if image is not None:
                image.close()


def prepare_production_artifact_for_job(
    job_id: str, *, upscale_model_name: str | None = None, confirmed: bool = False,
    target_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not confirmed:
        raise JobQueueError("Production-artifact processing requires explicit confirmation.")
    job = get_job(job_id)
    payload = _payload(job)
    approval = payload.get("transparent_derivative_approval")
    if not isinstance(approval, dict):
        raise JobQueueError("Separate transparent-derivative approval is required.")
    derivative = _artifact_path_for_job(job_id, payload)
    approved_path = Path(str(approval.get("approved_artifact_path") or "")).expanduser().resolve()
    if approved_path != derivative:
        raise JobQueueError("Approved transparent derivative path does not match the job artifact.")
    approved_sha = str(approval.get("approved_artifact_sha256") or "")
    if not approved_sha or _hash_file(derivative) != approved_sha:
        raise JobQueueError("Approved transparent derivative SHA has changed.")
    selected = upscale_model_registry.select_upscale_model(upscale_model_name)
    if not selected.get("validated") or not selected.get("production_approved"):
        raise JobQueueError(f"Upscale model is not SHA-validated: {selected.get('validation_reason')}")
    if selected.get("scale_factor") != 2:
        raise JobQueueError("Production artifact requires a configured 2x upscale model.")
    settings = {
        "alpha_resize_method": selected["preferred_alpha_resize_method"],
        "edge_bleed_iterations": selected["preferred_edge_bleed_iterations"],
        "edge_bleed_alpha_threshold": selected["preferred_edge_bleed_alpha_threshold"],
    }
    target = load_production_target()
    if target_overrides:
        target = {**target, **target_overrides}
        with tempfile.TemporaryDirectory() as temporary:
            config = Path(temporary) / "target.yaml"
            config.write_text(yaml.safe_dump({"production_target": target}), encoding="utf-8")
            target = load_production_target(config)

    root = derivative.parent / "production-artifacts"
    debug_folder = root / "debug"
    debug_folder.mkdir(parents=True, exist_ok=True)
    final_folder = root / "candidate"
    metadata_path = final_folder / "production-artifact.json"
    if final_folder.exists():
        raise JobQueueError("A production candidate already exists; preserve it and review before another run.")
    started = time.perf_counter()
    derivative_hash_before = _hash_file(derivative)
    staging_path: Path | None = None
    published_this_run = False
    try:
        staging_path = Path(tempfile.mkdtemp(prefix=".production-run-", dir=root))
        intermediates = staging_path / "intermediates"
        stage_records = []
        stage_source = derivative
        for stage_number, (expected_input, expected_output) in enumerate(zip(STAGE_SIZES, STAGE_SIZES[1:]), start=1):
            output = intermediates / f"stage-{stage_number}-{expected_output[0]}x{expected_output[1]}.png"
            record = _run_stage(
                job_id=job_id, stage_number=stage_number, source_path=stage_source, output_path=output,
                debug_folder=debug_folder, selected_model=selected, settings=settings,
                expected_input=expected_input, expected_output=expected_output,
            )
            stage_records.append(record)
            stage_source = output
        final_upscale = _verified_rgba(stage_source, STAGE_SIZES[-1])
        try:
            canvas, placement = place_artwork_on_canvas(final_upscale, target)
        finally:
            final_upscale.close()
        candidate_path = staging_path / "production-candidate.png"
        canvas.save(candidate_path, format="PNG")
        previews = {
            "white_preview_path": staging_path / "production-preview-white.png",
            "dark_preview_path": staging_path / "production-preview-dark.png",
            "checkerboard_preview_path": staging_path / "production-preview-checkerboard.png",
        }
        for name, background in PREVIEW_BACKGROUNDS.items():
            background_image = Image.new("RGBA", canvas.size, background)
            composited = Image.alpha_composite(background_image, canvas)
            preview = composited.convert("RGB")
            preview.save(previews[f"{name}_preview_path"], format="PNG")
            preview.close()
            composited.close()
            background_image.close()
        checker_background = _checkerboard(canvas.size)
        composited_checker = Image.alpha_composite(checker_background, canvas)
        checker = composited_checker.convert("RGB")
        checker.save(previews["checkerboard_preview_path"], format="PNG")
        checker.close()
        composited_checker.close()
        checker_background.close()
        if _hash_file(derivative) != derivative_hash_before or derivative_hash_before != approved_sha:
            raise JobQueueError("Approved derivative changed during production processing.")
        for record in stage_records:
            recorded_input = Path(record["input_path"])
            if recorded_input.is_relative_to(staging_path):
                record["input_path"] = str(final_folder / recorded_input.relative_to(staging_path))
            record["output_path"] = str(final_folder / "intermediates" / Path(record["output_path"]).name)
        metadata = {
            "status": "production_candidate_complete", "job_id": job_id,
            "approved_source_path": str(derivative), "approved_source_sha256": approved_sha,
            "approved_by": approval.get("approved_by"), "approved_at": approval.get("approved_at"),
            "intermediate_stages": stage_records,
            "intermediate_sha256": [stage["output_sha256"] for stage in stage_records],
            "production_candidate_path": str(final_folder / candidate_path.name),
            "production_candidate_sha256": _hash_file(candidate_path),
            "white_preview_path": str(final_folder / previews["white_preview_path"].name),
            "white_preview_sha256": _hash_file(previews["white_preview_path"]),
            "dark_preview_path": str(final_folder / previews["dark_preview_path"].name),
            "dark_preview_sha256": _hash_file(previews["dark_preview_path"]),
            "checkerboard_preview_path": str(final_folder / previews["checkerboard_preview_path"].name),
            "checkerboard_preview_sha256": _hash_file(previews["checkerboard_preview_path"]),
            "canvas_dimensions": [target["canvas_width"], target["canvas_height"]],
            **placement, "production_target": target,
            "model_name": selected["model_name"], "model_sha256": selected["sha256"],
            "actual_upscale_settings": settings, "alpha_extrema": list(canvas.getchannel("A").getextrema()),
            "alpha_diagnostics": halo_diagnostics(canvas), "placement_resize_method": "lanczos",
            "total_execution_time_seconds": time.perf_counter() - started,
            "production_artifact_status": "needs_final_review", "design_status": "needs_final_review",
            "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
        }
        canvas.close()
        metadata_path_staged = staging_path / metadata_path.name
        metadata_path_staged.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        staging_path.replace(final_folder)
        staging_path = None
        published_this_run = True
        payload.update({
            "production_artifact": metadata,
            "production_artifact_status": "needs_final_review", "design_status": "needs_final_review",
            "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
        })
        update_job_payload(job_id, payload)
        append_job_log(job_id, "Production artifact candidate prepared for final review")
        mark_step(job_id, "production artifact prepared", "complete", "Candidate requires final review; no provider action taken.")
        return metadata
    except JobQueueError as exc:
        if staging_path:
            shutil.rmtree(staging_path, ignore_errors=True)
        if published_this_run:
            shutil.rmtree(final_folder, ignore_errors=True)
            remove_job_payload_keys(job_id, ("production_artifact", "production_artifact_status"))
        error_path = debug_folder / "production-error.json"
        error_path.write_text(json.dumps({"error": str(exc), "type": type(exc).__name__, "job_id": job_id}, indent=2), encoding="utf-8")
        raise
    except Exception as exc:
        if staging_path:
            shutil.rmtree(staging_path, ignore_errors=True)
        if published_this_run:
            shutil.rmtree(final_folder, ignore_errors=True)
            try:
                remove_job_payload_keys(job_id, ("production_artifact", "production_artifact_status"))
            except Exception:
                pass
        error_path = debug_folder / "production-error.json"
        error_path.write_text(json.dumps({"error": str(exc), "type": type(exc).__name__}, indent=2), encoding="utf-8")
        raise JobQueueError(f"Production-artifact processing failed: {exc}") from exc
