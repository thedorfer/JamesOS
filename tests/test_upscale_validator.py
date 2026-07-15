from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import yaml

from jamesos.services import comfyui_client, image_worker, job_queue, upscale_model_registry, upscale_validator


def png_bytes(size: tuple[int, int], mode: str = "RGBA", transparent: bool = True) -> bytes:
    color = (30, 40, 50, 0 if transparent else 255) if mode == "RGBA" else (30, 40, 50)
    image = Image.new(mode, size, color)
    if mode == "RGBA":
        image.putpixel((size[0] // 2, size[1] // 2), (200, 30, 40, 255))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class UpscaleValidatorTests(unittest.TestCase):
    DEFAULT_MODEL = "RealESRGAN_x2plus.pth"
    ALTERNATE_MODEL = "AlternateArtwork_x2.pth"
    FOUR_X_MODEL = "FutureArtwork_x4.pth"

    def run_with_validation_paths(self, callback) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated_root = root / "Generated"
            comfy_root = root / "ComfyUI"
            model_root = comfy_root / "models" / "upscale_models"
            model_root.mkdir(parents=True)
            (model_root / self.DEFAULT_MODEL).write_bytes(b"default model")
            (model_root / self.ALTERNATE_MODEL).write_bytes(b"alternate model")
            (model_root / self.FOUR_X_MODEL).write_bytes(b"future 4x model")
            registry_path = root / "upscale_models.yaml"
            registry_path.write_text(yaml.safe_dump({"models": {
                self.DEFAULT_MODEL: {
                    "model_name": self.DEFAULT_MODEL,
                    "scale_factor": 2,
                    "model_family": "Real-ESRGAN",
                    "intended_use": "general artwork",
                    "enabled": True,
                    "validated": False,
                    "default": True,
                    "validation_output_filename": "realesrgan-x2-validation.png",
                },
                self.ALTERNATE_MODEL: {
                    "model_name": self.ALTERNATE_MODEL,
                    "scale_factor": 2,
                    "model_family": "test family",
                    "intended_use": "artwork testing",
                    "enabled": True,
                    "validated": True,
                    "default": False,
                    "validation_output_filename": "alternate-x2-validation.png",
                },
                self.FOUR_X_MODEL: {
                    "model_name": self.FOUR_X_MODEL,
                    "scale_factor": 4,
                    "model_family": "future test family",
                    "intended_use": "future 4x artwork testing",
                    "enabled": True,
                    "validated": False,
                    "default": False,
                    "validation_output_filename": "future-x4-validation.png",
                },
                "MissingArtwork_x4.pth": {
                    "model_name": "MissingArtwork_x4.pth",
                    "scale_factor": 4,
                    "model_family": "test family",
                    "intended_use": "artwork testing",
                    "enabled": True,
                    "validated": False,
                    "default": False,
                },
            }}), encoding="utf-8")
            patches = [
                patch.object(upscale_validator, "GENERATED_ROOT", generated_root),
                patch.object(upscale_validator, "COMFYUI_ROOT", comfy_root),
                patch.object(upscale_validator, "COMFYUI_INPUT_ROOT", comfy_root / "input"),
                patch.object(upscale_validator, "MANAGED_WORKFLOW_PATH", root / "WorkflowTemplates" / "upscale_model_validation.api.json"),
                patch.object(upscale_model_registry, "REGISTRY_PATH", registry_path),
                patch.object(upscale_model_registry, "COMFYUI_ROOT", comfy_root),
            ]
            for item in patches:
                item.start()
            try:
                callback(root, generated_root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def make_source(self, generated_root: Path, job_id: str = "validation-job") -> Path:
        source = generated_root / "2026-07-14" / job_id / "transparent_artifact.png"
        source.parent.mkdir(parents=True)
        source.write_bytes(png_bytes((768, 768)))
        return source

    def test_workflow_has_one_ai_pass_and_separate_alpha_path(self) -> None:
        workflow = upscale_validator.build_upscale_validation_workflow("input.png", self.DEFAULT_MODEL, (1536, 1536))
        class_types = [node["class_type"] for node in workflow.values()]

        self.assertEqual(class_types.count("ImageUpscaleWithModel"), 1)
        self.assertEqual(workflow["2"]["inputs"]["model_name"], self.DEFAULT_MODEL)
        self.assertEqual(workflow["3"]["inputs"]["image"], ["1", 0])
        self.assertEqual(workflow["4"]["inputs"]["input"], ["1", 1])
        self.assertEqual(workflow["4"]["inputs"]["resize_type.width"], 1536)
        self.assertEqual(workflow["4"]["inputs"]["resize_type.height"], 1536)
        self.assertEqual(workflow["4"]["inputs"]["resize_type.crop"], "disabled")
        self.assertFalse({"width", "height", "crop"} & set(workflow["4"]["inputs"]))
        self.assertEqual(workflow["4"]["inputs"]["resize_type"], "scale dimensions")
        self.assertEqual(workflow["4"]["inputs"]["scale_method"], "lanczos")
        self.assertEqual(workflow["5"]["inputs"]["image"], ["3", 0])
        self.assertEqual(workflow["5"]["inputs"]["alpha"], ["4", 0])
        self.assertEqual(workflow["6"]["class_type"], "SaveImage")

    def test_dynamic_combo_uses_exact_dotted_api_keys_and_rejects_other_shapes(self) -> None:
        workflow = upscale_validator.build_upscale_validation_workflow("input.png", self.DEFAULT_MODEL, (1536, 1536))
        inputs = workflow["4"]["inputs"]
        self.assertEqual(
            set(inputs),
            {
                "input",
                "resize_type",
                "resize_type.width",
                "resize_type.height",
                "resize_type.crop",
                "scale_method",
            },
        )

        flattened = deepcopy(workflow)
        flattened_inputs = flattened["4"]["inputs"]
        flattened_inputs["width"] = flattened_inputs.pop("resize_type.width")
        flattened_inputs["height"] = flattened_inputs.pop("resize_type.height")
        flattened_inputs["crop"] = flattened_inputs.pop("resize_type.crop")
        with self.assertRaises(job_queue.JobQueueError):
            upscale_validator._validate_rendered_workflow(flattened, (1536, 1536))

        nested = deepcopy(workflow)
        nested["4"]["inputs"] = {
            "input": ["1", 1],
            "resize_type": {"value": "scale dimensions", "width": 1536, "height": 1536, "crop": "disabled"},
            "scale_method": "lanczos",
        }
        with self.assertRaises(job_queue.JobQueueError):
            upscale_validator._validate_rendered_workflow(nested, (1536, 1536))

    def test_mocked_validation_saves_verified_rgba_output_and_metadata(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            source = self.make_source(generated_root)
            source_before = source.read_bytes()
            output_content = png_bytes((1536, 1536))
            captured_workflow: dict = {}

            def queue(workflow, **kwargs):
                captured_workflow.update(workflow)
                return {"status": "queued", "prompt_id": "prompt-123"}

            with (
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=queue),
                patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
                patch.object(upscale_validator.comfyui_client, "get_output_images", return_value=[{"filename": "out.png", "content": output_content}]),
            ):
                result = upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True)

            output_path = source.parent / "upscale-tests" / "realesrgan-x2-validation.png"
            metadata_path = output_path.with_suffix(".json")
            self.assertEqual(output_path.read_bytes(), output_content)
            self.assertTrue(metadata_path.exists())
            self.assertEqual(source.read_bytes(), source_before)
            self.assertEqual(result["input_dimensions"], [768, 768])
            self.assertEqual(result["output_dimensions"], [1536, 1536])
            self.assertEqual(result["input_mode"], "RGBA")
            self.assertEqual(result["output_mode"], "RGBA")
            self.assertTrue(result["output_meaningful_transparency"])
            self.assertTrue(result["input_unchanged"])
            self.assertEqual(result["model_name"], self.DEFAULT_MODEL)
            self.assertTrue(result["model_sha256"])
            self.assertEqual(result["scale_factor"], 2)
            self.assertEqual(result["comfyui_prompt_id"], "prompt-123")
            self.assertGreaterEqual(result["execution_time_seconds"], 0)
            self.assertEqual(result["provider_status"], "not_ready")
            self.assertEqual(result["printify_status"], "not_ready")
            self.assertFalse(result["final_print_ready"])
            self.assertEqual(captured_workflow["2"]["class_type"], "UpscaleModelLoader")
            self.assertEqual(captured_workflow["3"]["class_type"], "ImageUpscaleWithModel")
            self.assertFalse((upscale_validator.COMFYUI_INPUT_ROOT / "jamesos-validation-job-transparent-artifact.png").exists())
            self.assertEqual(json.loads(metadata_path.read_text(encoding="utf-8"))["output_sha256"], result["output_sha256"])

        self.run_with_validation_paths(scenario)

    def test_configured_4x_model_drives_workflow_dimensions_and_metadata(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            source = generated_root / "2026-07-14" / "validation-job" / "transparent_artifact.png"
            source.parent.mkdir(parents=True)
            source.write_bytes(png_bytes((8, 8)))
            captured_workflow: dict = {}

            def queue(workflow, **kwargs):
                captured_workflow.update(workflow)
                return {"prompt_id": "four-x-prompt"}

            with (
                patch.object(upscale_validator, "INPUT_SIZE", (8, 8)),
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=queue),
                patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
                patch.object(upscale_validator.comfyui_client, "get_output_images", return_value=[{"filename": "out.png", "content": png_bytes((32, 32))}]),
            ):
                result = upscale_validator.validate_upscale_model_for_job(
                    "validation-job", upscale_model_name=self.FOUR_X_MODEL, confirmed=True
                )

            self.assertEqual(captured_workflow["2"]["inputs"]["model_name"], self.FOUR_X_MODEL)
            self.assertEqual(captured_workflow["4"]["inputs"]["resize_type.width"], 32)
            self.assertEqual(captured_workflow["4"]["inputs"]["resize_type.height"], 32)
            self.assertEqual(captured_workflow["4"]["inputs"]["resize_type.crop"], "disabled")
            self.assertEqual(result["input_dimensions"], [8, 8])
            self.assertEqual(result["output_dimensions"], [32, 32])
            self.assertEqual(result["scale_factor"], 4)
            self.assertEqual(result["model_name"], self.FOUR_X_MODEL)

        self.run_with_validation_paths(scenario)

    def test_http_400_preserves_prompt_details_and_submitted_workflow_without_success_metadata(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            source = self.make_source(generated_root)
            source_sha_before = sha256(source.read_bytes()).hexdigest()
            response_json = {
                "error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
                "node_errors": {
                    "4": {
                        "errors": [
                            {"type": "required_input_missing", "message": "Required input is missing", "details": "width"}
                        ]
                    }
                },
            }
            http_error = comfyui_client.ComfyUIHTTPError(
                "ComfyUI prompt queue failed with HTTP 400",
                400,
                json.dumps(response_json),
                response_json,
            )
            with (
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=http_error),
            ):
                with self.assertRaises(upscale_validator.UpscalePromptValidationError) as raised:
                    upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True)

            error = raised.exception
            self.assertEqual(error.status_code, 400)
            self.assertEqual(error.response_body, json.dumps(response_json))
            self.assertEqual(error.response_json, response_json)
            self.assertEqual(error.prompt_validation_details, response_json["node_errors"])
            structured = image_worker.structured_error(error, job_id="validation-job")
            self.assertEqual(structured["response_body"], json.dumps(response_json))
            self.assertEqual(structured["prompt_validation_details"], response_json["node_errors"])

            validation_folder = source.parent / "upscale-tests"
            submitted = json.loads((validation_folder / "submitted-upscale-workflow.json").read_text(encoding="utf-8"))
            node_4 = submitted["4"]["inputs"]
            self.assertEqual(node_4["resize_type.width"], 1536)
            self.assertEqual(node_4["resize_type.height"], 1536)
            self.assertEqual(node_4["resize_type.crop"], "disabled")
            self.assertFalse((validation_folder / "realesrgan-x2-validation.png").exists())
            self.assertFalse((validation_folder / "realesrgan-x2-validation.json").exists())
            self.assertEqual(sha256(source.read_bytes()).hexdigest(), source_sha_before)

        self.run_with_validation_paths(scenario)

    def test_registry_selects_default_model_and_reports_discovery_metadata(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            selected = upscale_model_registry.select_upscale_model()
            inventory = upscale_model_registry.list_upscale_models()

            self.assertEqual(selected["model_name"], self.DEFAULT_MODEL)
            self.assertTrue(selected["exists"])
            self.assertGreater(selected["file_size_bytes"], 0)
            self.assertTrue(selected["sha256"])
            self.assertEqual(selected["scale_factor"], 2)
            self.assertEqual(inventory["default_model"], self.DEFAULT_MODEL)
            self.assertIn("validation_state", inventory)

        self.run_with_validation_paths(scenario)

    def test_registry_accepts_explicit_configured_installed_model(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            selected = upscale_model_registry.select_upscale_model(self.ALTERNATE_MODEL)
            self.assertEqual(selected["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(selected["model_family"], "test family")
            self.assertTrue(selected["validated"])

        self.run_with_validation_paths(scenario)

    def test_registry_rejects_unknown_arbitrary_path_and_missing_model(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            with self.assertRaises(job_queue.JobQueueError):
                upscale_model_registry.select_upscale_model("Unknown_x2.pth")
            with self.assertRaises(job_queue.JobQueueError):
                upscale_model_registry.select_upscale_model("/tmp/RealESRGAN_x2plus.pth")
            with self.assertRaises(job_queue.JobQueueError):
                upscale_model_registry.select_upscale_model("../RealESRGAN_x2plus.pth")
            with self.assertRaises(job_queue.JobQueueError):
                upscale_model_registry.select_upscale_model("MissingArtwork_x4.pth")

        self.run_with_validation_paths(scenario)

    def test_explicit_model_is_written_to_workflow_and_result_metadata(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            self.make_source(generated_root)
            captured_workflow: dict = {}

            def queue(workflow, **kwargs):
                captured_workflow.update(workflow)
                return {"prompt_id": "alternate-prompt"}

            with (
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=queue),
                patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
                patch.object(upscale_validator.comfyui_client, "get_output_images", return_value=[{"filename": "out.png", "content": png_bytes((1536, 1536))}]),
            ):
                result = upscale_validator.validate_upscale_model_for_job(
                    "validation-job", upscale_model_name=self.ALTERNATE_MODEL, confirmed=True
                )

            self.assertEqual(captured_workflow["2"]["inputs"]["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(result["model_name"], self.ALTERNATE_MODEL)
            self.assertTrue(result["model_sha256"])
            self.assertEqual(result["scale_factor"], 2)
            self.assertEqual(result["model_family"], "test family")
            persisted = json.loads(Path(result["output_path"]).with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(persisted["model_sha256"], result["model_sha256"])

        self.run_with_validation_paths(scenario)

    def test_confirmation_is_required_before_any_comfyui_call(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            self.make_source(generated_root)
            with patch.object(upscale_validator.comfyui_client, "queue_prompt") as queued:
                with self.assertRaises(job_queue.JobQueueError):
                    upscale_validator.validate_upscale_model_for_job("validation-job")
            queued.assert_not_called()

        self.run_with_validation_paths(scenario)

    def test_invalid_mocked_output_is_rejected_without_validation_artifact(self) -> None:
        def scenario(root: Path, generated_root: Path) -> None:
            source = self.make_source(generated_root)
            source_before = source.read_bytes()
            with (
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", return_value={"prompt_id": "prompt-bad"}),
                patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
                patch.object(upscale_validator.comfyui_client, "get_output_images", return_value=[{"filename": "bad.png", "content": png_bytes((1536, 1536), mode="RGB")}]),
            ):
                with self.assertRaises(job_queue.JobQueueError):
                    upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True)

            folder = source.parent / "upscale-tests"
            self.assertFalse((folder / "realesrgan-x2-validation.png").exists())
            self.assertFalse((folder / "realesrgan-x2-validation.json").exists())
            self.assertEqual(source.read_bytes(), source_before)

        self.run_with_validation_paths(scenario)

    def test_validation_source_contains_no_external_commerce_actions(self) -> None:
        source = Path(upscale_validator.__file__).read_text(encoding="utf-8").lower()
        for token in ("etsy", "printify.", "upload(", "publish(", "order("):
            self.assertNotIn(token, source)

    def test_api_passes_explicit_model_selection_to_validation(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise
        expected = {"status": "validation_complete", "model_name": self.ALTERNATE_MODEL}
        with (
            patch.object(api, "require_key", return_value=None),
            patch.object(api, "validate_upscale_model_for_job", return_value=expected) as validate,
        ):
            result = api.image_worker_validate_upscale_model_route(
                "validation-job",
                api.UpscaleValidationRequest(confirmed=True, upscale_model_name=self.ALTERNATE_MODEL),
                None,
            )
        self.assertEqual(result, expected)
        validate.assert_called_once_with(
            "validation-job", upscale_model_name=self.ALTERNATE_MODEL, confirmed=True
        )

    def test_upscale_models_api_is_read_only_inventory(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise
        expected = {"status": "ok", "installed_models": [], "default_model": self.DEFAULT_MODEL}
        with (
            patch.object(api, "require_key", return_value=None),
            patch.object(api, "list_upscale_models", return_value=expected) as listed,
        ):
            result = api.image_worker_upscale_models_route(None)
        self.assertEqual(result, expected)
        listed.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
