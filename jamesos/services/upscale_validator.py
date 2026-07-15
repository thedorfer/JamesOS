from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import time
from typing import Any

from PIL import Image, ImageChops, ImageFilter

from jamesos.config import VAULT
from jamesos.services import comfyui_client
from jamesos.services.job_queue import JobQueueError
from jamesos.services import upscale_model_registry


INPUT_SIZE = (768, 768)
COMFYUI_ROOT = Path.home() / "AI" / "ComfyUI"
COMFYUI_INPUT_ROOT = COMFYUI_ROOT / "input"
GENERATED_ROOT = VAULT / "JamesOS" / "CreativeStudio" / "Generated"
MANAGED_WORKFLOW_PATH = VAULT / "JamesOS" / "CreativeStudio" / "WorkflowTemplates" / "upscale_model_validation.api.json"
SOURCE_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / "workflow_templates" / "upscale_model_validation.api.json"
COMFYUI_URL = "http://127.0.0.1:8188"
DEFAULT_BLEED_ITERATIONS = 16
DEFAULT_ALPHA_THRESHOLD = 128
DEFAULT_ALPHA_RESIZE_METHOD = "lanczos"
ALPHA_RESIZE_METHODS = {"nearest-exact": Image.Resampling.NEAREST, "lanczos": Image.Resampling.LANCZOS}
PREVIEW_BACKGROUNDS = {"dark": (24, 24, 24, 255), "white": (255, 255, 255, 255)}


def _hash_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def _image_metadata(content: bytes) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            alpha_extrema = image.getchannel("A").getextrema() if "A" in image.mode else None
            return {
                "dimensions": [image.width, image.height],
                "mode": image.mode,
                "alpha_extrema": list(alpha_extrema) if alpha_extrema else None,
                "meaningful_transparency": bool(alpha_extrema and alpha_extrema[0] < 255),
            }
    except Exception as exc:
        raise JobQueueError(f"Upscale validation image is unreadable: {exc}") from exc


def _validate_halo_settings(bleed_iterations: int, alpha_threshold: int, alpha_resize_method: str) -> None:
    if isinstance(bleed_iterations, bool) or not isinstance(bleed_iterations, int) or not 1 <= bleed_iterations <= 256:
        raise JobQueueError("Edge-bleed iterations must be an integer from 1 through 256.")
    if isinstance(alpha_threshold, bool) or not isinstance(alpha_threshold, int) or not 1 <= alpha_threshold <= 255:
        raise JobQueueError("Edge-bleed alpha threshold must be an integer from 1 through 255.")
    if alpha_resize_method not in ALPHA_RESIZE_METHODS:
        raise JobQueueError("Alpha resize method must be nearest-exact or lanczos.")


def prepare_halo_safe_rgb(
    source: Image.Image, *, bleed_iterations: int = DEFAULT_BLEED_ITERATIONS, alpha_threshold: int = DEFAULT_ALPHA_THRESHOLD
) -> Image.Image:
    """Return RGB with bounded deterministic 8-neighbor color propagation under alpha.

    Pillow-native 3x3 dilation keeps memory bounded for production-size stages. Channel
    maxima are used only for newly reached hidden pixels; reliable artwork is untouched.
    """
    _validate_halo_settings(bleed_iterations, alpha_threshold, DEFAULT_ALPHA_RESIZE_METHOD)
    rgba = source.convert("RGBA")
    alpha = rgba.getchannel("A")
    reliable = alpha.point(lambda value: 255 if value >= alpha_threshold else 0, mode="L")
    source_rgb = rgba.convert("RGB")
    prepared = Image.new("RGB", rgba.size, (0, 0, 0))
    prepared.paste(source_rgb, mask=reliable)
    source_rgb.close()
    alpha.close()
    rgba.close()
    dilation = ImageFilter.MaxFilter(3)
    for _ in range(bleed_iterations):
        expanded = reliable.filter(dilation)
        frontier = ImageChops.subtract(expanded, reliable)
        if frontier.getbbox() is None:
            frontier.close()
            expanded.close()
            break
        propagated = prepared.filter(dilation)
        prepared.paste(propagated, mask=frontier)
        propagated.close()
        frontier.close()
        reliable.close()
        reliable = expanded
    reliable.close()
    return prepared


def resize_alpha(alpha: Image.Image, output_size: tuple[int, int], method: str) -> Image.Image:
    _validate_halo_settings(DEFAULT_BLEED_ITERATIONS, DEFAULT_ALPHA_THRESHOLD, method)
    return alpha.convert("L").resize(output_size, ALPHA_RESIZE_METHODS[method])


def halo_diagnostics(image: Image.Image) -> dict[str, Any]:
    rgba = image.convert("RGBA")
    partial = near_white = 0
    for red, green, blue, alpha in rgba.get_flattened_data():
        if 0 < alpha < 255:
            partial += 1
            if min(red, green, blue) >= 240:
                near_white += 1
    return {
        "partially_transparent_pixel_count": partial,
        "near_white_partially_transparent_pixel_count": near_white,
        "near_white_partially_transparent_percentage": round(near_white * 100 / partial, 6) if partial else 0.0,
    }


def _source_for_job(job_id: str) -> Path:
    if not job_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in job_id):
        raise JobQueueError("Invalid image job ID.")
    matches = sorted(GENERATED_ROOT.glob(f"*/{job_id}/transparent_artifact.png"), reverse=True)
    if not matches:
        raise JobQueueError(f"Transparent artifact not found for job: {job_id}")
    return matches[0]


def build_upscale_validation_workflow(input_filename: str, upscale_model_name: str) -> dict[str, Any]:
    workflow = json.loads(SOURCE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    workflow["1"]["inputs"]["image"] = input_filename
    workflow["2"]["inputs"]["model_name"] = upscale_model_name
    _validate_rendered_workflow(workflow)
    return workflow


def _validate_rendered_workflow(workflow: dict[str, Any]) -> None:
    expected = {"1": "LoadImage", "2": "UpscaleModelLoader", "3": "ImageUpscaleWithModel", "4": "SaveImage"}
    if set(workflow) != set(expected):
        raise JobQueueError("Upscale validation workflow must contain only the RGB upscale path.")
    for node_id, class_type in expected.items():
        if workflow.get(node_id, {}).get("class_type") != class_type:
            raise JobQueueError(f"Upscale validation workflow node {node_id} must be {class_type}.")
    if workflow["3"]["inputs"] != {"upscale_model": ["2", 0], "image": ["1", 0]}:
        raise JobQueueError("ImageUpscaleWithModel wiring is invalid.")
    if workflow["4"]["inputs"].get("images") != ["3", 0]:
        raise JobQueueError("SaveImage wiring is invalid.")


class UpscalePromptValidationError(JobQueueError):
    def __init__(self, exc: comfyui_client.ComfyUIHTTPError):
        super().__init__(f"ComfyUI rejected the upscale validation prompt: {exc.response_body or exc}")
        self.error_code = "comfyui_rejected_upscale_prompt"
        self.message = str(self)
        self.next_step = "Inspect the saved submitted workflow and ComfyUI prompt-validation details before retrying."
        self.status_code = exc.status_code
        self.response_body = exc.response_body
        self.response_json = exc.response_json
        self.prompt_validation_details = (
            exc.response_json.get("node_errors") or exc.response_json.get("error") or exc.response_json
            if isinstance(exc.response_json, dict) else exc.response_body
        )
        self.validation_issues = [self.prompt_validation_details]


def _write_managed_workflow(workflow: dict[str, Any]) -> Path:
    MANAGED_WORKFLOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANAGED_WORKFLOW_PATH.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return MANAGED_WORKFLOW_PATH


def validate_upscale_model_for_job(
    job_id: str, *, upscale_model_name: str | None = None, confirmed: bool = False,
    bleed_iterations: int | None = None, alpha_threshold: int | None = None,
    alpha_resize_method: str | None = None,
) -> dict[str, Any]:
    if not confirmed:
        raise JobQueueError("Upscale-model validation requires explicit confirmation.")
    source_path = _source_for_job(job_id)
    selected_model = upscale_model_registry.select_upscale_model(upscale_model_name)
    preferred_settings = {
        "alpha_resize_method": selected_model["preferred_alpha_resize_method"],
        "edge_bleed_iterations": selected_model["preferred_edge_bleed_iterations"],
        "edge_bleed_alpha_threshold": selected_model["preferred_edge_bleed_alpha_threshold"],
    }
    bleed_iterations = preferred_settings["edge_bleed_iterations"] if bleed_iterations is None else bleed_iterations
    alpha_threshold = preferred_settings["edge_bleed_alpha_threshold"] if alpha_threshold is None else alpha_threshold
    alpha_resize_method = preferred_settings["alpha_resize_method"] if alpha_resize_method is None else alpha_resize_method
    _validate_halo_settings(bleed_iterations, alpha_threshold, alpha_resize_method)
    scale_factor = selected_model["scale_factor"]
    input_content = source_path.read_bytes()
    input_sha256 = _hash_bytes(input_content)
    input_metadata = _image_metadata(input_content)
    if tuple(input_metadata["dimensions"]) != INPUT_SIZE:
        raise JobQueueError(f"Validation input must be exactly {INPUT_SIZE[0]}x{INPUT_SIZE[1]}.")
    if input_metadata["mode"] != "RGBA" or not input_metadata["meaningful_transparency"]:
        raise JobQueueError("Validation input must be an RGBA image with meaningful transparency.")
    output_size = tuple(value * scale_factor for value in INPUT_SIZE)

    settings_slug = f"halo-safe-{alpha_resize_method}-bleed-{bleed_iterations}-threshold-{alpha_threshold}"
    model_stem = Path(selected_model["validation_output_filename"]).stem
    validation_folder = source_path.parent / "upscale-tests"
    output_path = validation_folder / f"{model_stem}-{settings_slug}.png"
    metadata_path = output_path.with_suffix(".json")
    dark_preview_path = output_path.with_name(f"{output_path.stem}-preview-dark.png")
    white_preview_path = output_path.with_name(f"{output_path.stem}-preview-white.png")
    submitted_workflow_path = validation_folder / f"submitted-upscale-workflow-{settings_slug}.json"
    final_paths = [output_path, metadata_path, dark_preview_path, white_preview_path]
    if any(path.exists() for path in final_paths):
        raise JobQueueError("A validation output already exists for these halo-safe settings; choose different settings.")

    input_copy_name = f"jamesos-{job_id}-{settings_slug}-rgb.png"
    input_copy_path = COMFYUI_INPUT_ROOT / input_copy_name
    workflow = build_upscale_validation_workflow(input_copy_name, selected_model["model_name"])
    created_paths: list[Path] = []
    started = time.perf_counter()
    prompt_id = ""
    try:
        validation_folder.mkdir(parents=True, exist_ok=True)
        COMFYUI_INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        with Image.open(BytesIO(input_content)) as source_image:
            source_image.load()
            original_alpha = source_image.getchannel("A").copy()
            prepared_rgb = prepare_halo_safe_rgb(
                source_image, bleed_iterations=bleed_iterations, alpha_threshold=alpha_threshold
            )
        prepared_rgb.save(input_copy_path, format="PNG")
        with Image.open(input_copy_path) as prepared_check:
            if prepared_check.mode != "RGB":
                raise JobQueueError("Prepared ComfyUI input must be RGB.")
        _write_managed_workflow(workflow)
        submitted_workflow_path.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
        if not comfyui_client.is_running(COMFYUI_URL, timeout=2.0):
            raise JobQueueError("ComfyUI is not running at http://127.0.0.1:8188.")
        try:
            queued = comfyui_client.queue_prompt(workflow, api_url=COMFYUI_URL)
        except comfyui_client.ComfyUIHTTPError as exc:
            raise UpscalePromptValidationError(exc) from exc
        prompt_id = str(queued.get("prompt_id") or "")
        if not prompt_id:
            raise JobQueueError("ComfyUI did not return a prompt ID.")
        completed = comfyui_client.wait_for_completion(prompt_id, api_url=COMFYUI_URL)
        if completed.get("status") != "completed":
            raise JobQueueError(f"ComfyUI upscale validation did not complete: {completed.get('status')}")
        outputs = comfyui_client.get_output_images(prompt_id, api_url=COMFYUI_URL)
        if len(outputs) != 1 or not outputs[0].get("content"):
            raise JobQueueError("ComfyUI upscale validation must return exactly one image.")
        with Image.open(BytesIO(bytes(outputs[0]["content"]))) as ai_image:
            ai_image.load()
            if ai_image.size != output_size:
                raise JobQueueError(f"Upscale validation output must be exactly {output_size[0]}x{output_size[1]}.")
            upscaled_rgb = ai_image.convert("RGB")
        scaled_alpha = resize_alpha(original_alpha, output_size, alpha_resize_method)
        rgba_output = upscaled_rgb.copy()
        rgba_output.putalpha(scaled_alpha)
        output_content = _png_bytes(rgba_output)
        output_metadata = _image_metadata(output_content)
        if not output_metadata["meaningful_transparency"]:
            raise JobQueueError("Upscale validation output lost meaningful transparency.")
        if _hash_file(source_path) != input_sha256:
            raise JobQueueError("Source transparent artifact changed during validation.")

        previews = {
            dark_preview_path: _png_bytes(Image.alpha_composite(Image.new("RGBA", output_size, PREVIEW_BACKGROUNDS["dark"]), rgba_output).convert("RGB")),
            white_preview_path: _png_bytes(Image.alpha_composite(Image.new("RGBA", output_size, PREVIEW_BACKGROUNDS["white"]), rgba_output).convert("RGB")),
        }
        metadata = {
            "status": "validation_complete", "validation_only": True, "job_id": job_id,
            "source_path": str(source_path), "output_path": str(output_path),
            "dark_preview_path": str(dark_preview_path), "white_preview_path": str(white_preview_path),
            "input_sha256": input_sha256, "output_sha256": _hash_bytes(output_content),
            "input_dimensions": input_metadata["dimensions"], "output_dimensions": output_metadata["dimensions"],
            "input_mode": input_metadata["mode"], "output_mode": output_metadata["mode"],
            "input_alpha_extrema": input_metadata["alpha_extrema"], "output_alpha_extrema": output_metadata["alpha_extrema"],
            "input_meaningful_transparency": input_metadata["meaningful_transparency"],
            "output_meaningful_transparency": output_metadata["meaningful_transparency"], "input_unchanged": True,
            "model_name": selected_model["model_name"], "model_sha256": selected_model["sha256"],
            "scale_factor": scale_factor, "model_family": selected_model["model_family"],
            "model_intended_use": selected_model["intended_use"], "model_validated": False,
            "edge_bleed_iterations": bleed_iterations, "edge_bleed_alpha_threshold": alpha_threshold,
            "alpha_resize_method": alpha_resize_method, **halo_diagnostics(rgba_output),
            "configured_preferred_settings": preferred_settings,
            "actual_validation_settings": {
                "alpha_resize_method": alpha_resize_method,
                "edge_bleed_iterations": bleed_iterations,
                "edge_bleed_alpha_threshold": alpha_threshold,
            },
            "execution_time_seconds": time.perf_counter() - started, "comfyui_prompt_id": prompt_id,
            "workflow_path": str(MANAGED_WORKFLOW_PATH), "provider_status": "not_ready",
            "printify_status": "not_ready", "final_print_ready": False,
        }
        with tempfile.TemporaryDirectory(prefix=".halo-safe-", dir=validation_folder) as staging_name:
            staging = Path(staging_name)
            staged = {
                output_path: output_content, metadata_path: json.dumps(metadata, indent=2, sort_keys=True).encode(), **previews
            }
            for destination, content in staged.items():
                temporary = staging / destination.name
                temporary.write_bytes(content)
                temporary.replace(destination)
                created_paths.append(destination)
        return metadata
    except JobQueueError:
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        for path in created_paths:
            path.unlink(missing_ok=True)
        raise JobQueueError(f"Upscale-model validation failed: {exc}") from exc
    finally:
        input_copy_path.unlink(missing_ok=True)
