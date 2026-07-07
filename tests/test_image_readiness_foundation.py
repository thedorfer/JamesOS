from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from jamesos.services import comfyui_client, control_center, image_worker, model_registry, workflow_manager


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class ImageReadinessFoundationTests(unittest.TestCase):
    def run_with_registry(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "JamesOSData" / "JamesOS" / "AI" / "model_registry.yaml"
            output_folder = root / "JamesOSData" / "JamesOS" / "AI" / "ComfyUI" / "Outputs"
            patches = [
                patch.object(model_registry, "REGISTRY_PATH", registry_path),
                patch.object(image_worker, "OUTPUT_FOLDER", output_folder),
                patch.object(control_center.model_registry, "REGISTRY_PATH", registry_path),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_model_registry_loads_defaults(self) -> None:
        def scenario(root: Path) -> None:
            result = model_registry.list_models()

            self.assertEqual(result["status"], "ok")
            self.assertIn("sdxl_base", result["models"])
            self.assertIn("flux_schnell", result["models"])
            self.assertFalse(result["models"]["sdxl_base"]["enabled"])
            self.assertFalse(result["execution_enabled"])

        self.run_with_registry(scenario)

    def test_workflows_list_safely(self) -> None:
        def scenario(root: Path) -> None:
            result = workflow_manager.list_workflows()

            self.assertEqual(result["status"], "ok")
            self.assertIn("product_art", result["workflows"])
            self.assertIn("typography_design", result["workflows"])
            self.assertFalse(result["execution_enabled"])
            self.assertFalse(result["workflows"]["product_art"]["execution_enabled"])

        self.run_with_registry(scenario)

    def test_image_worker_creates_plan_but_does_not_execute(self) -> None:
        def scenario(root: Path) -> None:
            with patch.object(comfyui_client, "urlopen") as urlopen:
                result = image_worker.plan(
                    {
                        "product_type": "shirt",
                        "niche": "Pride Month",
                        "design_prompt": "Clean Pride Month typography shirt design",
                        "negative_prompt": "blurry, watermark",
                    }
                )

            self.assertEqual(result["status"], "planned")
            self.assertFalse(result["execution_enabled"])
            self.assertTrue(result["requires_approval"])
            self.assertFalse(result["safety"]["comfyui_execution_enabled"])
            self.assertIn("typography_design", result["selected_workflow"]["name"])
            self.assertTrue(result["prompt"])
            urlopen.assert_not_called()

        self.run_with_registry(scenario)

    def test_comfyui_health_handles_not_running(self) -> None:
        with patch.object(comfyui_client, "urlopen", side_effect=OSError("offline")):
            result = comfyui_client.health(timeout=0.01)

        self.assertEqual(result["status"], "not_running")
        self.assertFalse(result["running"])
        self.assertFalse(result["execution_enabled"])
        self.assertFalse(result["prompt_queue_enabled"])

    def test_comfyui_health_handles_running(self) -> None:
        fake_stats = {"system": {"os": "linux"}, "devices": []}
        with patch.object(comfyui_client, "urlopen", return_value=_FakeResponse(fake_stats)):
            result = comfyui_client.health(timeout=0.01)

        self.assertEqual(result["status"], "running")
        self.assertTrue(result["running"])
        self.assertFalse(result["execution_enabled"])
        self.assertEqual(result["system_stats"], fake_stats)

    def test_execution_enabled_false_everywhere(self) -> None:
        def scenario(root: Path) -> None:
            self.assertFalse(model_registry.health()["execution_enabled"])
            self.assertFalse(workflow_manager.list_workflows()["execution_enabled"])
            self.assertFalse(image_worker.health()["execution_enabled"])

        self.run_with_registry(scenario)

    def test_control_center_includes_image_readiness(self) -> None:
        def scenario(root: Path) -> None:
            with patch.object(control_center.comfyui_client, "health", return_value={
                "status": "not_running",
                "running": False,
                "install_path": {"path": str(root / "AI" / "ComfyUI"), "exists": False, "kind": "preferred"},
                "execution_enabled": False,
            }):
                result = control_center.integrations()
                services = control_center.services()["services"]

            readiness = result["gpu_comfyui_readiness"]
            self.assertIn("model_registry_present", readiness)
            self.assertIn("workflow_registry_present", readiness)
            self.assertFalse(readiness["execution_enabled"])
            self.assertFalse(readiness["image_execution_enabled"])
            self.assertTrue(readiness["one_image_job_at_a_time"])
            self.assertIn("image_worker", services)
            self.assertIn("model_registry", services)
            self.assertIn("workflow_manager", services)
            self.assertIn("comfyui_client", services)

        self.run_with_registry(scenario)

    def test_no_external_image_generation_method_exists(self) -> None:
        self.assertFalse(hasattr(comfyui_client, "generate_image"))
        self.assertFalse(hasattr(comfyui_client.ComfyUIClient, "generate_image"))


if __name__ == "__main__":
    unittest.main()
