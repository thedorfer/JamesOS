from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import yaml

from jamesos.services import comfyui_client, image_worker, job_queue, upscale_model_registry, upscale_validator


def png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class UpscaleValidatorTests(unittest.TestCase):
    MODEL = "RealESRGAN_x2plus.pth"
    ALTERNATE_MODEL = "AlternateArtwork_x2.pth"
    FOUR_X_MODEL = "FutureArtwork_x4.pth"
    MISSING_MODEL = "MissingArtwork_x4.pth"
    DISABLED_MODEL = "DisabledArtwork_x2.pth"

    def run_in_sandbox(self, callback) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            generated = root / "Generated"
            comfy = root / "ComfyUI"
            models = comfy / "models" / "upscale_models"
            models.mkdir(parents=True)
            (models / self.MODEL).write_bytes(b"model")
            (models / self.ALTERNATE_MODEL).write_bytes(b"alternate model")
            (models / self.FOUR_X_MODEL).write_bytes(b"four-x model")
            (models / self.DISABLED_MODEL).write_bytes(b"disabled model")
            registry = root / "upscale_models.yaml"
            registry.write_text(yaml.safe_dump({"models": {
                self.MODEL: {
                    "model_name": self.MODEL, "scale_factor": 2, "model_family": "Real-ESRGAN",
                    "intended_use": "general artwork", "enabled": True, "validated": False, "default": True,
                    "validation_output_filename": "realesrgan-x2-validation.png",
                },
                self.ALTERNATE_MODEL: {
                    "model_name": self.ALTERNATE_MODEL, "scale_factor": 2, "model_family": "test family",
                    "intended_use": "artwork testing", "enabled": True, "validated": True, "default": False,
                    "validation_output_filename": "alternate-x2-validation.png",
                    "validated_model_sha256": sha256(b"alternate model").hexdigest(),
                    "validation_job_id": "approved-job",
                    "validation_output_sha256": "abc123",
                    "validated_at": "2026-07-15T09:46:10-05:00",
                    "preferred_alpha_resize_method": "nearest-exact",
                    "preferred_edge_bleed_iterations": 3,
                    "preferred_edge_bleed_alpha_threshold": 200,
                },
                self.FOUR_X_MODEL: {
                    "model_name": self.FOUR_X_MODEL, "scale_factor": 4, "model_family": "future family",
                    "intended_use": "4x testing", "enabled": True, "validated": False, "default": False,
                    "validation_output_filename": "future-x4-validation.png",
                },
                self.MISSING_MODEL: {
                    "model_name": self.MISSING_MODEL, "scale_factor": 4, "model_family": "missing family",
                    "intended_use": "missing testing", "enabled": True, "validated": False, "default": False,
                },
                self.DISABLED_MODEL: {
                    "model_name": self.DISABLED_MODEL, "scale_factor": 2, "model_family": "disabled family",
                    "intended_use": "disabled testing", "enabled": False, "validated": False, "default": False,
                },
            }}), encoding="utf-8")
            patches = [
                patch.object(upscale_validator, "GENERATED_ROOT", generated),
                patch.object(upscale_validator, "COMFYUI_ROOT", comfy),
                patch.object(upscale_validator, "COMFYUI_INPUT_ROOT", comfy / "input"),
                patch.object(upscale_validator, "MANAGED_WORKFLOW_PATH", root / "managed.json"),
                patch.object(upscale_model_registry, "REGISTRY_PATH", registry),
                patch.object(upscale_model_registry, "COMFYUI_ROOT", comfy),
            ]
            for item in patches:
                item.start()
            try:
                callback(root, generated)
            finally:
                for item in reversed(patches):
                    item.stop()

    def make_source(self, generated: Path, size=(8, 8)) -> Path:
        source = generated / "2026-07-14" / "validation-job" / "transparent_artifact.png"
        source.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGBA", size, (253, 253, 253, 0))
        for y in range(2, 6):
            for x in range(2, 6):
                image.putpixel((x, y), (30, 90, 180, 255))
        source.write_bytes(png_bytes(image))
        return source

    def run_validation(self, generated: Path, **kwargs):
        source = self.make_source(generated)
        captured = {}

        def queue(workflow, **unused):
            captured.update(workflow)
            input_name = workflow["1"]["inputs"]["image"]
            with Image.open(upscale_validator.COMFYUI_INPUT_ROOT / input_name) as prepared:
                self.assertEqual(prepared.mode, "RGB")
                upscaled = prepared.resize((16, 16), Image.Resampling.NEAREST)
            captured["output"] = png_bytes(upscaled)
            return {"prompt_id": "one-pass"}

        with (
            patch.object(upscale_validator, "INPUT_SIZE", (8, 8)),
            patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
            patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=queue),
            patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
            patch.object(upscale_validator.comfyui_client, "get_output_images", side_effect=lambda *a, **k: [{"content": captured["output"]}]),
        ):
            result = upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True, **kwargs)
        return source, result, captured

    def test_transparent_rgb_is_decontaminated_and_nearby_color_bleeds(self) -> None:
        image = Image.new("RGBA", (5, 5), (255, 255, 255, 0))
        image.putpixel((2, 2), (12, 80, 160, 255))
        result = upscale_validator.prepare_halo_safe_rgb(image, bleed_iterations=1, alpha_threshold=128)
        self.assertEqual(result.getpixel((2, 1)), (12, 80, 160))
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0))
        self.assertNotEqual(result.getpixel((2, 1)), (255, 255, 255))

    def test_enclosed_reliable_white_artwork_remains_white(self) -> None:
        image = Image.new("RGBA", (5, 5), (0, 0, 0, 0))
        image.putpixel((2, 2), (255, 255, 255, 255))
        result = upscale_validator.prepare_halo_safe_rgb(image, bleed_iterations=2, alpha_threshold=128)
        self.assertEqual(result.getpixel((2, 2)), (255, 255, 255))

    def test_settings_ranges_are_validated(self) -> None:
        image = Image.new("RGBA", (2, 2))
        for iterations, threshold, method in ((0, 128, "lanczos"), (1, 0, "lanczos"), (1, 128, "cubic")):
            with self.assertRaises(job_queue.JobQueueError):
                upscale_validator._validate_halo_settings(iterations, threshold, method)
        self.assertEqual(upscale_validator.resize_alpha(image.getchannel("A"), (4, 4), "nearest-exact").size, (4, 4))
        self.assertEqual(upscale_validator.resize_alpha(image.getchannel("A"), (4, 4), "lanczos").size, (4, 4))

    def test_alpha_methods_are_distinct_and_preserve_extrema(self) -> None:
        alpha = Image.new("L", (2, 1), 0)
        alpha.putpixel((1, 0), 255)
        nearest = upscale_validator.resize_alpha(alpha, (8, 1), "nearest-exact")
        lanczos = upscale_validator.resize_alpha(alpha, (8, 1), "lanczos")
        self.assertEqual(nearest.getextrema(), (0, 255))
        self.assertEqual(lanczos.getextrema(), (0, 255))
        self.assertNotEqual(list(nearest.get_flattened_data()), list(lanczos.get_flattened_data()))

    def test_halo_diagnostics_count_partial_near_white_pixels(self) -> None:
        image = Image.new("RGBA", (3, 1))
        image.putdata([(255, 255, 255, 128), (20, 30, 40, 64), (255, 255, 255, 255)])
        stats = upscale_validator.halo_diagnostics(image)
        self.assertEqual(stats["partially_transparent_pixel_count"], 2)
        self.assertEqual(stats["near_white_partially_transparent_pixel_count"], 1)
        self.assertEqual(stats["near_white_partially_transparent_percentage"], 50.0)

    def test_one_rgb_ai_pass_recombines_alpha_creates_previews_and_metadata(self) -> None:
        def scenario(root, generated):
            source, result, workflow = self.run_validation(generated, bleed_iterations=2, alpha_threshold=128)
            output = Path(result["output_path"])
            self.assertTrue(output.exists())
            with Image.open(output) as image:
                self.assertEqual(image.mode, "RGBA")
            with Image.open(result["dark_preview_path"]) as image:
                self.assertEqual(image.mode, "RGB")
            with Image.open(result["white_preview_path"]) as image:
                self.assertEqual(image.mode, "RGB")
            self.assertEqual(sum(node.get("class_type") == "ImageUpscaleWithModel" for node in workflow.values() if isinstance(node, dict)), 1)
            self.assertEqual(result["input_sha256"], sha256(source.read_bytes()).hexdigest())
            self.assertTrue(result["input_unchanged"])
            self.assertFalse(result["model_validated"])
            self.assertEqual(result["provider_status"], "not_ready")
            self.assertEqual(result["printify_status"], "not_ready")
            self.assertFalse(result["final_print_ready"])
            self.assertEqual(result["edge_bleed_iterations"], 2)
            self.assertEqual(result["alpha_resize_method"], "lanczos")
            self.assertIn("partially_transparent_pixel_count", result)
        self.run_in_sandbox(scenario)

    def test_each_alpha_method_gets_separate_output(self) -> None:
        def scenario(root, generated):
            _, nearest, _ = self.run_validation(generated, alpha_resize_method="nearest-exact")
            _, lanczos, _ = self.run_validation(generated, alpha_resize_method="lanczos")
            self.assertNotEqual(nearest["output_path"], lanczos["output_path"])
            self.assertTrue(Path(nearest["output_path"]).exists())
            self.assertTrue(Path(lanczos["output_path"]).exists())
        self.run_in_sandbox(scenario)

    def test_source_stays_byte_for_byte_unchanged(self) -> None:
        def scenario(root, generated):
            source = self.make_source(generated)
            before = source.read_bytes()
            self.run_validation(generated)
            self.assertEqual(source.read_bytes(), before)
        self.run_in_sandbox(scenario)

    def test_failure_cleans_temporary_input_and_records_no_success_metadata(self) -> None:
        def scenario(root, generated):
            source = self.make_source(generated)
            with (
                patch.object(upscale_validator, "INPUT_SIZE", (8, 8)),
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=RuntimeError("boom")),
            ):
                with self.assertRaises(job_queue.JobQueueError):
                    upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True)
            folder = source.parent / "upscale-tests"
            self.assertFalse(list(folder.glob("realesrgan-*.json")))
            self.assertFalse(list(folder.glob("*.png")))
            self.assertFalse(list((root / "ComfyUI" / "input").glob("*")))
        self.run_in_sandbox(scenario)

    def test_registry_default_selection_and_inventory_metadata(self) -> None:
        def scenario(root, generated):
            selected = upscale_model_registry.select_upscale_model()
            inventory = upscale_model_registry.list_upscale_models()
            self.assertEqual(selected["model_name"], self.MODEL)
            self.assertTrue(selected["exists"])
            self.assertTrue(selected["sha256"])
            self.assertEqual(selected["scale_factor"], 2)
            self.assertEqual(inventory["default_model"], self.MODEL)
            self.assertEqual(inventory["validation_state"]["configured_count"], 5)
            self.assertEqual(inventory["validation_state"]["installed_count"], 4)
            self.assertEqual(inventory["validation_state"]["validated_count"], 1)
        self.run_in_sandbox(scenario)

    def test_registry_selects_explicit_configured_installed_model(self) -> None:
        def scenario(root, generated):
            selected = upscale_model_registry.select_upscale_model(self.ALTERNATE_MODEL)
            self.assertEqual(selected["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(selected["model_family"], "test family")
            self.assertTrue(selected["exists"])
            self.assertTrue(selected["validated"])
        self.run_in_sandbox(scenario)

    def test_matching_validated_model_hash_reports_production_approved(self) -> None:
        def scenario(root, generated):
            selected = upscale_model_registry.select_upscale_model(self.ALTERNATE_MODEL)
            self.assertTrue(selected["validated"])
            self.assertTrue(selected["production_approved"])
            self.assertEqual(selected["validation_reason"], "model_hash_match")
            self.assertEqual(selected["validated_model_sha256"], selected["sha256"])
        self.run_in_sandbox(scenario)

    def test_changed_validated_model_hash_reports_mismatch_and_not_approved(self) -> None:
        def scenario(root, generated):
            model_path = root / "ComfyUI" / "models" / "upscale_models" / self.ALTERNATE_MODEL
            model_path.write_bytes(b"changed model")
            inventory = upscale_model_registry.list_upscale_models()
            selected = next(item for item in inventory["models"] if item["model_name"] == self.ALTERNATE_MODEL)
            self.assertFalse(selected["validated"])
            self.assertFalse(selected["production_approved"])
            self.assertEqual(selected["validation_reason"], "model_hash_mismatch")
            self.assertNotEqual(selected["sha256"], selected["validated_model_sha256"])
        self.run_in_sandbox(scenario)

    def test_preferred_model_settings_become_validator_defaults(self) -> None:
        def scenario(root, generated):
            _, result, _ = self.run_validation(generated, upscale_model_name=self.ALTERNATE_MODEL)
            expected = {
                "alpha_resize_method": "nearest-exact",
                "edge_bleed_iterations": 3,
                "edge_bleed_alpha_threshold": 200,
            }
            self.assertEqual(result["configured_preferred_settings"], expected)
            self.assertEqual(result["actual_validation_settings"], expected)
            self.assertEqual(result["alpha_resize_method"], "nearest-exact")
            self.assertEqual(result["edge_bleed_iterations"], 3)
            self.assertEqual(result["edge_bleed_alpha_threshold"], 200)
        self.run_in_sandbox(scenario)

    def test_explicit_validation_settings_override_model_preferences(self) -> None:
        def scenario(root, generated):
            _, result, _ = self.run_validation(
                generated,
                upscale_model_name=self.ALTERNATE_MODEL,
                alpha_resize_method="lanczos",
                bleed_iterations=7,
                alpha_threshold=111,
            )
            self.assertEqual(result["configured_preferred_settings"], {
                "alpha_resize_method": "nearest-exact",
                "edge_bleed_iterations": 3,
                "edge_bleed_alpha_threshold": 200,
            })
            self.assertEqual(result["actual_validation_settings"], {
                "alpha_resize_method": "lanczos",
                "edge_bleed_iterations": 7,
                "edge_bleed_alpha_threshold": 111,
            })
        self.run_in_sandbox(scenario)

    def test_inventory_exposes_validation_evidence_and_preferred_settings(self) -> None:
        def scenario(root, generated):
            inventory = upscale_model_registry.list_upscale_models()
            model = next(item for item in inventory["configured_models"] if item["model_name"] == self.ALTERNATE_MODEL)
            self.assertEqual(model["validation_job_id"], "approved-job")
            self.assertEqual(model["validation_output_sha256"], "abc123")
            self.assertEqual(model["validated_at"], "2026-07-15T09:46:10-05:00")
            self.assertEqual(model["preferred_alpha_resize_method"], "nearest-exact")
            self.assertEqual(model["preferred_edge_bleed_iterations"], 3)
            self.assertEqual(model["preferred_edge_bleed_alpha_threshold"], 200)
        self.run_in_sandbox(scenario)

    def test_unvalidated_and_unknown_models_are_not_production_approved(self) -> None:
        def scenario(root, generated):
            default = upscale_model_registry.select_upscale_model(self.MODEL)
            self.assertFalse(default["validated"])
            self.assertFalse(default["production_approved"])
            self.assertEqual(default["validation_reason"], "not_validated")
            with self.assertRaises(job_queue.JobQueueError):
                upscale_model_registry.select_upscale_model("UnknownProductionModel.pth")
        self.run_in_sandbox(scenario)

    def test_registry_rejects_unknown_paths_missing_and_disabled_models(self) -> None:
        def scenario(root, generated):
            rejected = (
                "Unknown_x2.pth",
                "/tmp/RealESRGAN_x2plus.pth",
                "../RealESRGAN_x2plus.pth",
                self.MISSING_MODEL,
                self.DISABLED_MODEL,
            )
            for model_name in rejected:
                with self.subTest(model_name=model_name):
                    with self.assertRaises(job_queue.JobQueueError):
                        upscale_model_registry.select_upscale_model(model_name)
        self.run_in_sandbox(scenario)

    def test_configured_4x_model_drives_rgb_alpha_and_persisted_scale_metadata(self) -> None:
        def scenario(root, generated):
            source = self.make_source(generated)
            captured = {}

            def queue(workflow, **unused):
                captured.update(workflow)
                input_path = upscale_validator.COMFYUI_INPUT_ROOT / workflow["1"]["inputs"]["image"]
                with Image.open(input_path) as prepared:
                    self.assertEqual(prepared.mode, "RGB")
                    captured["output"] = png_bytes(prepared.resize((32, 32), Image.Resampling.NEAREST))
                return {"prompt_id": "four-x"}

            original_resize_alpha = upscale_validator.resize_alpha
            alpha_calls = []

            def capture_alpha(alpha, output_size, method):
                alpha_calls.append((alpha.size, output_size, method))
                return original_resize_alpha(alpha, output_size, method)

            with (
                patch.object(upscale_validator, "INPUT_SIZE", (8, 8)),
                patch.object(upscale_validator, "resize_alpha", side_effect=capture_alpha),
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=queue),
                patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
                patch.object(upscale_validator.comfyui_client, "get_output_images", side_effect=lambda *a, **k: [{"content": captured["output"]}]),
            ):
                result = upscale_validator.validate_upscale_model_for_job(
                    "validation-job", upscale_model_name=self.FOUR_X_MODEL, confirmed=True
                )
            self.assertEqual(captured["2"]["inputs"]["model_name"], self.FOUR_X_MODEL)
            self.assertEqual(result["output_dimensions"], [32, 32])
            self.assertEqual(alpha_calls, [((8, 8), (32, 32), "lanczos")])
            self.assertEqual(result["scale_factor"], 4)
            persisted = json.loads(Path(result["output_path"]).with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["scale_factor"], 4)
            with Image.open(result["output_path"]) as output_image:
                self.assertEqual(output_image.getchannel("A").size, (32, 32))
            self.assertEqual(sha256(source.read_bytes()).hexdigest(), result["input_sha256"])
        self.run_in_sandbox(scenario)

    def test_http_400_preserves_response_and_submitted_workflow(self) -> None:
        def scenario(root, generated):
            source = self.make_source(generated)
            response_json = {
                "error": {"type": "prompt_outputs_failed_validation", "message": "Prompt outputs failed validation"},
                "node_errors": {"3": {"errors": [{"type": "invalid_input", "message": "Invalid model input"}]}},
            }
            response_body = json.dumps(response_json)
            http_error = comfyui_client.ComfyUIHTTPError("HTTP 400", 400, response_body, response_json)
            with (
                patch.object(upscale_validator, "INPUT_SIZE", (8, 8)),
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", side_effect=http_error),
            ):
                with self.assertRaises(upscale_validator.UpscalePromptValidationError) as raised:
                    upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True)
            error = raised.exception
            self.assertIsInstance(error, job_queue.JobQueueError)
            self.assertEqual(error.status_code, 400)
            self.assertEqual(error.response_body, response_body)
            self.assertEqual(error.response_json, response_json)
            self.assertEqual(error.prompt_validation_details, response_json["node_errors"])
            structured = image_worker.structured_error(error, job_id="validation-job")
            self.assertEqual(structured["response_body"], response_body)
            self.assertEqual(structured["response_json"], response_json)
            self.assertEqual(structured["prompt_validation_details"], response_json["node_errors"])
            submitted = source.parent / "upscale-tests" / "submitted-upscale-workflow-halo-safe-lanczos-bleed-16-threshold-128.json"
            self.assertTrue(submitted.exists())
            self.assertEqual(json.loads(submitted.read_text(encoding="utf-8"))["3"]["class_type"], "ImageUpscaleWithModel")
            self.assertFalse(list(source.parent.joinpath("upscale-tests").glob("realesrgan-*.json")))
        self.run_in_sandbox(scenario)

    def test_explicit_model_is_in_workflow_returned_and_persisted_metadata(self) -> None:
        def scenario(root, generated):
            source, result, workflow = self.run_validation(generated, upscale_model_name=self.ALTERNATE_MODEL)
            self.assertEqual(workflow["2"]["inputs"]["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(result["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(result["model_family"], "test family")
            persisted = json.loads(Path(result["output_path"]).with_suffix(".json").read_text(encoding="utf-8"))
            self.assertEqual(persisted["model_name"], self.ALTERNATE_MODEL)
            self.assertEqual(persisted["model_sha256"], result["model_sha256"])
            submitted = source.parent / "upscale-tests" / "submitted-upscale-workflow-halo-safe-nearest-exact-bleed-3-threshold-200.json"
            self.assertEqual(json.loads(submitted.read_text(encoding="utf-8"))["2"]["inputs"]["model_name"], self.ALTERNATE_MODEL)
        self.run_in_sandbox(scenario)

    def test_dimensionally_incorrect_ai_output_is_rejected_without_success_publication(self) -> None:
        def scenario(root, generated):
            source = self.make_source(generated)
            bad_output = png_bytes(Image.new("RGB", (15, 16)))
            with (
                patch.object(upscale_validator, "INPUT_SIZE", (8, 8)),
                patch.object(upscale_validator.comfyui_client, "is_running", return_value=True),
                patch.object(upscale_validator.comfyui_client, "queue_prompt", return_value={"prompt_id": "bad-size"}),
                patch.object(upscale_validator.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
                patch.object(upscale_validator.comfyui_client, "get_output_images", return_value=[{"content": bad_output}]),
            ):
                with self.assertRaises(job_queue.JobQueueError):
                    upscale_validator.validate_upscale_model_for_job("validation-job", confirmed=True)
            folder = source.parent / "upscale-tests"
            self.assertFalse(list(folder.glob("realesrgan-*.png")))
            self.assertFalse(list(folder.glob("realesrgan-*.json")))
        self.run_in_sandbox(scenario)

    def test_upscale_models_api_is_read_only_and_reports_full_inventory(self) -> None:
        def scenario(root, generated):
            from jamesos.core import api
            registry_before = upscale_model_registry.REGISTRY_PATH.read_bytes()
            model_hashes_before = {
                path.name: sha256(path.read_bytes()).hexdigest()
                for path in (root / "ComfyUI" / "models" / "upscale_models").iterdir()
            }
            with patch.object(api, "require_key", return_value=None):
                result = api.image_worker_upscale_models_route(None)
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["default_model"], self.MODEL)
            self.assertEqual(len(result["installed_models"]), 4)
            self.assertEqual(len(result["configured_models"]), 5)
            self.assertEqual(result["validation_state"]["validated_count"], 1)
            self.assertEqual(upscale_model_registry.REGISTRY_PATH.read_bytes(), registry_before)
            self.assertEqual({path.name: sha256(path.read_bytes()).hexdigest() for path in (root / "ComfyUI" / "models" / "upscale_models").iterdir()}, model_hashes_before)
        self.run_in_sandbox(scenario)

    def test_confirmation_required_before_queue(self) -> None:
        def scenario(root, generated):
            self.make_source(generated)
            with patch.object(upscale_validator.comfyui_client, "queue_prompt") as queue:
                with self.assertRaises(job_queue.JobQueueError):
                    upscale_validator.validate_upscale_model_for_job("validation-job")
                queue.assert_not_called()
            self.assertFalse((root / "ComfyUI" / "input").exists())
        self.run_in_sandbox(scenario)

    def test_api_passes_halo_settings(self) -> None:
        from jamesos.core import api
        expected = {"status": "validation_complete"}
        request = api.UpscaleValidationRequest(confirmed=True, upscale_model_name=self.MODEL, bleed_iterations=3, alpha_threshold=200, alpha_resize_method="nearest-exact")
        with patch.object(api, "require_key", return_value=None), patch.object(api, "validate_upscale_model_for_job", return_value=expected) as validate:
            self.assertEqual(api.image_worker_validate_upscale_model_route("job", request, None), expected)
        validate.assert_called_once_with("job", upscale_model_name=self.MODEL, confirmed=True, bleed_iterations=3, alpha_threshold=200, alpha_resize_method="nearest-exact")

    def test_validation_source_contains_no_external_commerce_actions(self) -> None:
        source = Path(upscale_validator.__file__).read_text(encoding="utf-8").lower()
        for token in ("etsy", "printify.", "upload(", "publish(", "order("):
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
