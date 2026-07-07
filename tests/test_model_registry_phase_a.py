from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import control_center, model_registry


class ModelRegistryPhaseATests(unittest.TestCase):
    def run_with_temp_registry(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registry_path = root / "JamesOSData" / "JamesOS" / "AI" / "model_registry.yaml"
            inventory_path = root / "JamesOSData" / "JamesOS" / "AI" / "model_inventory.json"
            report_path = root / "JamesOSData" / "JamesOS" / "Reports" / "Model Registry.md"
            patches = [
                patch.object(model_registry, "REGISTRY_PATH", registry_path),
                patch.object(model_registry, "INVENTORY_PATH", inventory_path),
                patch.object(model_registry, "REPORT_PATH", report_path),
                patch.object(control_center.model_registry, "REGISTRY_PATH", registry_path),
                patch.object(control_center.model_registry, "INVENTORY_PATH", inventory_path),
                patch.object(control_center.model_registry, "REPORT_PATH", report_path),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_scan_works_on_temp_model_folder(self) -> None:
        def scenario(root: Path) -> None:
            models = root / "AI" / "Models"
            (models / "checkpoints").mkdir(parents=True)
            (models / "checkpoints" / "sdxl_base.safetensors").write_bytes(b"abc")

            inventory = model_registry.build_model_inventory(model_roots=[models])

            self.assertEqual(inventory["summary"]["total"], 1)
            self.assertEqual(inventory["models"][0]["name"], "sdxl_base")
            self.assertEqual(inventory["models"][0]["category"], "checkpoints")
            self.assertFalse(inventory["models"][0]["enabled"])
            self.assertFalse(inventory["execution_enabled"])

        self.run_with_temp_registry(scenario)

    def test_classifier_recognizes_safetensors_checkpoint(self) -> None:
        path = Path("/tmp/AI/Models/checkpoints/my_sdxl_model.safetensors")
        self.assertEqual(model_registry.classify_model_file(path), "checkpoints")
        self.assertEqual(model_registry.infer_model_family(path), "sdxl")

    def test_classifier_recognizes_lora_by_path_name(self) -> None:
        path = Path("/tmp/AI/ComfyUI/models/loras/pride_typography_lora.safetensors")
        self.assertEqual(model_registry.classify_model_file(path), "loras")
        self.assertEqual(model_registry.infer_model_family(path), "lora")

    def test_classifier_recognizes_upscaler_by_path_name(self) -> None:
        path = Path("/tmp/AI/ComfyUI/models/upscale_models/4x_ultrasharp.pth")
        self.assertEqual(model_registry.classify_model_file(path), "upscalers")
        self.assertEqual(model_registry.infer_model_family(path), "upscaler")

    def test_inventory_report_writes(self) -> None:
        def scenario(root: Path) -> None:
            models = root / "AI" / "Models"
            (models / "upscalers").mkdir(parents=True)
            (models / "upscalers" / "4x_ultrasharp.pth").write_bytes(b"abc")
            inventory = model_registry.build_model_inventory(model_roots=[models])
            result = model_registry.write_model_inventory_report(inventory)

            report_path = Path(result["report_path"])
            self.assertTrue(report_path.exists())
            text = report_path.read_text(encoding="utf-8")
            self.assertIn("execution_enabled: false", text)
            self.assertIn("4x_ultrasharp", text)

        self.run_with_temp_registry(scenario)

    def test_service_output_keeps_enabled_false_and_execution_disabled(self) -> None:
        def scenario(root: Path) -> None:
            models = root / "AI" / "Models"
            (models / "loras").mkdir(parents=True)
            (models / "loras" / "style_lora.safetensors").write_bytes(b"abc")
            model_registry.build_model_inventory(model_roots=[models])

            result = model_registry.list_models()

            self.assertFalse(result["execution_enabled"])
            self.assertFalse(result["safety"]["execution_enabled"])
            self.assertEqual(len(result["discovered_models"]), 1)
            self.assertFalse(result["discovered_models"][0]["enabled"])

        self.run_with_temp_registry(scenario)

    def test_control_center_model_counts_are_present(self) -> None:
        def scenario(root: Path) -> None:
            models = root / "AI" / "Models"
            (models / "checkpoints").mkdir(parents=True)
            (models / "loras").mkdir(parents=True)
            (models / "upscalers").mkdir(parents=True)
            (models / "checkpoints" / "sd15.ckpt").write_bytes(b"abc")
            (models / "loras" / "clean_lora.safetensors").write_bytes(b"abc")
            (models / "upscalers" / "4x_ultrasharp.pth").write_bytes(b"abc")
            model_registry.build_model_inventory(model_roots=[models])

            result = control_center.gpu_comfyui_readiness()

            self.assertEqual(result["discovered_model_count"], 3)
            self.assertEqual(result["checkpoint_count"], 1)
            self.assertEqual(result["lora_count"], 1)
            self.assertEqual(result["upscaler_count"], 1)
            self.assertFalse(result["execution_enabled"])

        self.run_with_temp_registry(scenario)


if __name__ == "__main__":
    unittest.main()
