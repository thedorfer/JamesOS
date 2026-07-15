from __future__ import annotations

from collections import deque
from datetime import datetime
import hashlib
from pathlib import Path
from typing import Any

from PIL import Image

from jamesos.services.image_postprocessor import inspect_generated_image
from jamesos.services.job_queue import (
    JobQueueError,
    append_job_log,
    get_job,
    mark_step,
    remove_job_payload_keys,
    update_job_payload,
)


def _payload_details(job: dict[str, Any]) -> dict[str, Any]:
    payload = dict(job.get("payload") or {})
    if not isinstance(payload, dict):
        payload = {}
    return payload


def _job_output_folder(job_id: str) -> Path:
    from jamesos.services.image_worker import _job_output_folder as worker_output_folder

    return worker_output_folder(job_id)


def _resolve_source_image(payload: dict[str, Any]) -> str:
    candidates = []
    output_image_path = payload.get("output_image_path")
    if isinstance(output_image_path, str) and output_image_path:
        candidates.append(output_image_path)
    output_image_paths = payload.get("output_image_paths")
    if isinstance(output_image_paths, list):
        for item in output_image_paths:
            if isinstance(item, str) and item:
                candidates.append(item)
    artifact = payload.get("design_artifact") if isinstance(payload.get("design_artifact"), dict) else {}
    if isinstance(artifact, dict):
        source_image_path = artifact.get("source_image_path")
        if isinstance(source_image_path, str) and source_image_path:
            candidates.append(source_image_path)
        final_image_path = artifact.get("final_image_path")
        if isinstance(final_image_path, str) and final_image_path:
            candidates.append(final_image_path)
    for candidate in candidates:
        path = Path(candidate).expanduser()
        if path.exists() and path.is_file():
            return str(path)
    raise JobQueueError("source_image_missing", "No source image is available for finishing.", "Generate or save an output image before requesting transparent finishing.")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _clear_finishing_success(job_id: str, payload: dict[str, Any], artifact_path: Path, temporary_path: Path) -> None:
    artifact_path.unlink(missing_ok=True)
    temporary_path.unlink(missing_ok=True)
    for key in ("transparent_artifact_path", "transparent_artifact_analysis", "finishing_metadata"):
        payload.pop(key, None)
    artifact = payload.get("design_artifact")
    if isinstance(artifact, dict):
        artifact = dict(artifact)
        for key in ("transparent_artifact_path", "transparent_artifact_generated_at", "final_image_path", "finishing_metadata"):
            artifact.pop(key, None)
        payload["design_artifact"] = artifact
    update_job_payload(job_id, payload)
    remove_job_payload_keys(job_id, ("transparent_artifact_path", "transparent_artifact_analysis", "finishing_metadata"))


def approve_concept_for_job(job_id: str, approved_by: str = "James") -> dict[str, Any]:
    job = get_job(job_id)
    payload = _payload_details(job)
    approved_by = str(approved_by or "James").strip() or "James"
    approved_at = datetime.now().isoformat(timespec="seconds")
    payload["concept_approved"] = True
    payload["concept_approved_at"] = approved_at
    payload["concept_approved_by"] = approved_by
    update_job_payload(job_id, payload)
    append_job_log(job_id, f"Concept approved by {approved_by}")
    mark_step(job_id, "concept approved", "complete", "Concept approval recorded for transparent finishing.")
    return {"status": "ok", "job_id": job_id, "concept_approved": True, "approved_by": approved_by, "approved_at": approved_at}


def prepare_transparent_artifact_for_job(job_id: str, white_threshold: int = 240, neutral_tolerance: int = 15) -> dict[str, Any]:
    job = get_job(job_id)
    payload = _payload_details(job)
    if not payload.get("concept_approved"):
        raise JobQueueError("concept_approval_required", "Concept approval is required before transparent finishing can be prepared.", "Approve the concept for the job before preparing the transparent artifact.")

    folder = _job_output_folder(job_id)
    artifact_path = folder / "transparent_artifact.png"
    temporary_path = folder / ".transparent_artifact.tmp.png"
    if not isinstance(white_threshold, int) or isinstance(white_threshold, bool) or not 0 <= white_threshold <= 255:
        _clear_finishing_success(job_id, payload, artifact_path, temporary_path)
        raise JobQueueError("white_threshold must be an integer between 0 and 255.")
    if not isinstance(neutral_tolerance, int) or isinstance(neutral_tolerance, bool) or not 0 <= neutral_tolerance <= 255:
        _clear_finishing_success(job_id, payload, artifact_path, temporary_path)
        raise JobQueueError("neutral_tolerance must be an integer between 0 and 255.")

    try:
        folder.mkdir(parents=True, exist_ok=True)
        source_image_path = _resolve_source_image(payload)
        source_path = Path(source_image_path).expanduser()
        source_sha256_before = _sha256(source_path)
        removed_background_pixel_count = 0
        with Image.open(source_path) as source:
            source.load()
            image = source.convert("RGBA")
            width, height = image.size
            pixels = image.load()
            exterior = bytearray(width * height)
            queue: deque[tuple[int, int]] = deque()

            def is_background_candidate(x: int, y: int) -> bool:
                r, g, b, alpha = pixels[x, y]
                channels = (r, g, b)
                is_near_white_neutral = min(channels) >= white_threshold and max(channels) - min(channels) <= neutral_tolerance
                return alpha < 255 or is_near_white_neutral

            def seed(x: int, y: int) -> None:
                index = y * width + x
                if not exterior[index] and is_background_candidate(x, y):
                    exterior[index] = 1
                    queue.append((x, y))

            for x in range(width):
                seed(x, 0)
                if height > 1:
                    seed(x, height - 1)
            for y in range(1, height - 1):
                seed(0, y)
                if width > 1:
                    seed(width - 1, y)

            while queue:
                x, y = queue.popleft()
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < width and 0 <= ny < height:
                        index = ny * width + nx
                        if not exterior[index] and is_background_candidate(nx, ny):
                            exterior[index] = 1
                            queue.append((nx, ny))

            for y in range(height):
                row_offset = y * width
                for x in range(width):
                    if exterior[row_offset + x]:
                        r, g, b, alpha = pixels[x, y]
                        if alpha > 0:
                            removed_background_pixel_count += 1
                        pixels[x, y] = (r, g, b, 0)

            image.save(temporary_path, format="PNG")

        analysis = inspect_generated_image(temporary_path, transparency_required=True)
        if not analysis["meaningful_transparency_present"]:
            raise JobQueueError("Transparent finishing did not produce meaningful transparency.")
        with Image.open(temporary_path) as derived:
            derived.load()
            alpha_values = derived.getchannel("A").tobytes()
            transparent_pixel_count = sum(value < 255 for value in alpha_values)
            opaque_pixel_count = len(alpha_values) - transparent_pixel_count
            output_mode = derived.mode
            width, height = derived.size
        source_sha256_after = _sha256(source_path)
        source_unchanged = source_sha256_before == source_sha256_after
        if not source_unchanged:
            raise JobQueueError("Source image changed during transparent finishing.")
        temporary_path.replace(artifact_path)
        analysis = inspect_generated_image(artifact_path, transparency_required=True)
    except JobQueueError:
        _clear_finishing_success(job_id, payload, artifact_path, temporary_path)
        raise
    except Exception as exc:
        try:
            _clear_finishing_success(job_id, payload, artifact_path, temporary_path)
        except Exception:
            pass
        raise JobQueueError(f"Transparent finishing failed: {exc}") from exc
    finishing_metadata = {
        "source_image_path": str(source_path),
        "derived_image_path": str(artifact_path),
        "source_unchanged": source_unchanged,
        "source_sha256_before": source_sha256_before,
        "source_sha256_after": source_sha256_after,
        "width": width,
        "height": height,
        "output_mode": output_mode,
        "alpha_channel_present": analysis["alpha_channel_present"],
        "meaningful_transparency_present": analysis["meaningful_transparency_present"],
        "transparent_pixel_count": transparent_pixel_count,
        "opaque_pixel_count": opaque_pixel_count,
        "removed_background_pixel_count": removed_background_pixel_count,
        "processing_method": "edge_connected_near_white_flood_fill",
        "white_threshold": white_threshold,
        "neutral_tolerance": neutral_tolerance,
        "visual_review_required": True,
        "final_print_ready": False,
    }
    payload["transparent_artifact_path"] = str(artifact_path)
    payload["transparent_artifact_analysis"] = analysis
    payload["finishing_metadata"] = finishing_metadata
    payload["design_artifact"] = dict(payload.get("design_artifact") or {})
    payload["design_artifact"]["transparent_artifact_path"] = str(artifact_path)
    payload["design_artifact"]["transparent_artifact_generated_at"] = datetime.now().isoformat(timespec="seconds")
    payload["design_artifact"]["source_image_path"] = str(source_path)
    payload["design_artifact"]["final_image_path"] = str(artifact_path)
    payload["design_artifact"]["background_removal_required"] = False
    payload["design_artifact"]["transparent_background_required"] = True
    payload["design_artifact"]["output_status"] = "transparent_derivative_ready"
    payload["design_artifact"]["finishing_metadata"] = finishing_metadata
    payload["design_status"] = "needs_design_review"
    payload["image_status"] = "finished_concept"
    payload["provider_status"] = "not_ready"
    payload["printify_status"] = "not_ready"
    payload["final_print_ready"] = False
    payload["print_readiness_analysis"] = analysis
    update_job_payload(job_id, payload)
    append_job_log(job_id, f"Transparent artifact prepared: {artifact_path}")
    mark_step(job_id, "transparent artifact prepared", "complete", "Transparent derivative artifact created without modifying the original image.")
    return {
        "status": "ok",
        "job_id": job_id,
        "artifact_path": str(artifact_path),
        "source_image_path": str(source_path),
        "provider_status": "not_ready",
        "printify_status": "not_ready",
        "final_print_ready": False,
        "finishing_metadata": finishing_metadata,
        "analysis": analysis,
    }
