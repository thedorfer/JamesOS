from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import shutil
import time
from typing import Any

from PIL import Image

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
MASK_RESIZE_TYPE = "scale dimensions"
MASK_SCALE_METHOD = "lanczos"
MASK_CROP = "disabled"


def _hash_bytes(content: bytes) -> str:
    return sha256(content).hexdigest()


def _hash_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_metadata(content: bytes) -> dict[str, Any]:
    try:
        with Image.open(BytesIO(content)) as image:
            image.load()
            mode = image.mode
            size = image.size
            if "A" not in mode:
                alpha_extrema = None
                meaningful_transparency = False
            else:
                alpha_extrema = tuple(image.getchannel("A").getextrema())
                meaningful_transparency = alpha_extrema[0] < 255
            return {
                "dimensions": [size[0], size[1]],
                "mode": mode,
                "alpha_extrema": list(alpha_extrema) if alpha_extrema else None,
                "meaningful_transparency": meaningful_transparency,
            }
    except Exception as exc:
        raise JobQueueError(f"Upscale validation image is unreadable: {exc}") from exc


def _source_for_job(job_id: str) -> Path:
    if not job_id or any(character not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for character in job_id):
        raise JobQueueError("Invalid image job ID.")
    matches = sorted(GENERATED_ROOT.glob(f"*/{job_id}/transparent_artifact.png"), reverse=True)
    if not matches:
        raise JobQueueError(f"Transparent artifact not found for job: {job_id}")
    return matches[0]


def build_upscale_validation_workflow(
    input_filename: str,
    upscale_model_name: str,
    output_size: tuple[int, int],
) -> dict[str, Any]:
    workflow = json.loads(SOURCE_TEMPLATE_PATH.read_text(encoding="utf-8"))
    workflow["1"]["inputs"]["image"] = input_filename
    workflow["2"]["inputs"]["model_name"] = upscale_model_name
    workflow["4"]["inputs"]["resize_type.width"] = output_size[0]
    workflow["4"]["inputs"]["resize_type.height"] = output_size[1]
    _validate_rendered_workflow(workflow, output_size)
    return workflow


def _validate_rendered_workflow(workflow: dict[str, Any], output_size: tuple[int, int]) -> None:
    expected_nodes = {
        "1": "LoadImage",
        "2": "UpscaleModelLoader",
        "3": "ImageUpscaleWithModel",
        "4": "ResizeImageMaskNode",
        "5": "JoinImageWithAlpha",
        "6": "SaveImage",
    }
    for node_id, class_type in expected_nodes.items():
        if workflow.get(node_id, {}).get("class_type") != class_type:
            raise JobQueueError(f"Upscale validation workflow node {node_id} must be {class_type}.")
    mask_inputs = workflow["4"].get("inputs") or {}
    required = {
        "input",
        "resize_type",
        "scale_method",
        "resize_type.width",
        "resize_type.height",
        "resize_type.crop",
    }
    missing = sorted(required - set(mask_inputs))
    if missing:
        raise JobQueueError(f"ResizeImageMaskNode is missing required inputs: {', '.join(missing)}")
    if mask_inputs["input"] != ["1", 1]:
        raise JobQueueError("ResizeImageMaskNode must receive the LoadImage alpha mask output.")
    if mask_inputs["resize_type"] != MASK_RESIZE_TYPE or mask_inputs["scale_method"] != MASK_SCALE_METHOD:
        raise JobQueueError("ResizeImageMaskNode has invalid resize settings.")
    if any(key in mask_inputs for key in ("width", "height", "crop")) or isinstance(mask_inputs.get("resize_type"), dict):
        raise JobQueueError("ResizeImageMaskNode dynamic inputs must use exact dotted API keys.")
    if mask_inputs["resize_type.crop"] != MASK_CROP:
        raise JobQueueError("ResizeImageMaskNode crop must be disabled to preserve the complete alpha mask.")
    if (
        mask_inputs["resize_type.width"],
        mask_inputs["resize_type.height"],
    ) != output_size or not all(isinstance(value, int) for value in output_size):
        raise JobQueueError("ResizeImageMaskNode dimensions were not resolved to the expected numeric output size.")
    if workflow["3"]["inputs"] != {"upscale_model": ["2", 0], "image": ["1", 0]}:
        raise JobQueueError("ImageUpscaleWithModel wiring is invalid.")
    if workflow["5"]["inputs"] != {"image": ["3", 0], "alpha": ["4", 0]}:
        raise JobQueueError("JoinImageWithAlpha wiring is invalid.")
    if workflow["6"]["inputs"].get("images") != ["5", 0]:
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
        if isinstance(exc.response_json, dict):
            self.prompt_validation_details = exc.response_json.get("node_errors") or exc.response_json.get("error") or exc.response_json
        else:
            self.prompt_validation_details = exc.response_body
        self.validation_issues = [self.prompt_validation_details]


def _write_managed_workflow(workflow: dict[str, Any]) -> Path:
    MANAGED_WORKFLOW_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANAGED_WORKFLOW_PATH.write_text(json.dumps(workflow, indent=2), encoding="utf-8")
    return MANAGED_WORKFLOW_PATH


def validate_upscale_model_for_job(
    job_id: str,
    *,
    upscale_model_name: str | None = None,
    confirmed: bool = False,
) -> dict[str, Any]:
    if not confirmed:
        raise JobQueueError("Upscale-model validation requires explicit confirmation.")
    source_path = _source_for_job(job_id)
    selected_model = upscale_model_registry.select_upscale_model(upscale_model_name)
    selected_model_name = selected_model["model_name"]
    scale_factor = selected_model["scale_factor"]

    input_content = source_path.read_bytes()
    input_sha256 = _hash_bytes(input_content)
    input_metadata = _image_metadata(input_content)
    if tuple(input_metadata["dimensions"]) != INPUT_SIZE:
        raise JobQueueError(f"Validation input must be exactly {INPUT_SIZE[0]}x{INPUT_SIZE[1]}.")
    if input_metadata["mode"] != "RGBA" or not input_metadata["meaningful_transparency"]:
        raise JobQueueError("Validation input must be an RGBA image with meaningful transparency.")
    input_size = tuple(input_metadata["dimensions"])
    output_size = (input_size[0] * scale_factor, input_size[1] * scale_factor)

    validation_folder = source_path.parent / "upscale-tests"
    output_filename = Path(selected_model["validation_output_filename"]).name
    output_path = validation_folder / output_filename
    metadata_path = output_path.with_suffix(".json")
    submitted_workflow_path = validation_folder / "submitted-upscale-workflow.json"
    temporary_output_path = validation_folder / f".{output_filename}.tmp"
    input_copy_name = f"jamesos-{job_id}-transparent-artifact.png"
    input_copy_path = COMFYUI_INPUT_ROOT / input_copy_name
    workflow = build_upscale_validation_workflow(input_copy_name, selected_model_name, output_size)

    started = time.perf_counter()
    prompt_id = ""
    try:
        validation_folder.mkdir(parents=True, exist_ok=True)
        COMFYUI_INPUT_ROOT.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, input_copy_path)
        if _hash_file(input_copy_path) != input_sha256:
            raise JobQueueError("ComfyUI input copy failed source hash verification.")
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
        output_content = bytes(outputs[0]["content"])
        output_metadata = _image_metadata(output_content)
        if tuple(output_metadata["dimensions"]) != output_size:
            raise JobQueueError(f"Upscale validation output must be exactly {output_size[0]}x{output_size[1]}.")
        if output_metadata["mode"] != "RGBA":
            raise JobQueueError("Upscale validation output must be RGBA.")
        if not output_metadata["meaningful_transparency"]:
            raise JobQueueError("Upscale validation output lost meaningful transparency.")
        if _hash_file(source_path) != input_sha256:
            raise JobQueueError("Source transparent artifact changed during validation.")

        temporary_output_path.write_bytes(output_content)
        temporary_output_path.replace(output_path)
        execution_time_seconds = time.perf_counter() - started
        metadata = {
            "status": "validation_complete",
            "validation_only": True,
            "job_id": job_id,
            "source_path": str(source_path),
            "output_path": str(output_path),
            "input_sha256": input_sha256,
            "output_sha256": _hash_bytes(output_content),
            "input_dimensions": input_metadata["dimensions"],
            "output_dimensions": output_metadata["dimensions"],
            "input_mode": input_metadata["mode"],
            "output_mode": output_metadata["mode"],
            "input_alpha_extrema": input_metadata["alpha_extrema"],
            "output_alpha_extrema": output_metadata["alpha_extrema"],
            "input_meaningful_transparency": input_metadata["meaningful_transparency"],
            "output_meaningful_transparency": output_metadata["meaningful_transparency"],
            "input_unchanged": True,
            "model_name": selected_model_name,
            "model_sha256": selected_model["sha256"],
            "scale_factor": scale_factor,
            "model_family": selected_model["model_family"],
            "model_intended_use": selected_model["intended_use"],
            "model_validated": selected_model["validated"],
            "execution_time_seconds": execution_time_seconds,
            "comfyui_prompt_id": prompt_id,
            "workflow_path": str(MANAGED_WORKFLOW_PATH),
            "provider_status": "not_ready",
            "printify_status": "not_ready",
            "final_print_ready": False,
        }
        metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")
        return metadata
    except JobQueueError:
        temporary_output_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary_output_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
        metadata_path.unlink(missing_ok=True)
        raise JobQueueError(f"Upscale-model validation failed: {exc}") from exc
    finally:
        input_copy_path.unlink(missing_ok=True)
