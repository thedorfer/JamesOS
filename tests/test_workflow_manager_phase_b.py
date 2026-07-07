from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import control_center, image_worker, workflow_manager


class WorkflowManagerPhaseBTests(unittest.TestCase):
    def run_with_temp_workflows(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory_path = root / "JamesOSData" / "JamesOS" / "AI" / "workflow_inventory.json"
            report_path = root / "JamesOSData" / "JamesOS" / "Reports" / "Workflow Registry.md"
            patches = [
                patch.object(workflow_manager, "WORKFLOW_INVENTORY_PATH", inventory_path),
                patch.object(workflow_manager, "REPORT_PATH", report_path),
                patch.object(control_center.workflow_manager, "WORKFLOW_INVENTORY_PATH", inventory_path),
                patch.object(control_center.workflow_manager, "REPORT_PATH", report_path),
                patch.object(image_worker.workflow_manager, "WORKFLOW_INVENTORY_PATH", inventory_path),
                patch.object(image_worker.workflow_manager, "REPORT_PATH", report_path),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_workflow_discovery(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "product_art.json").write_text("{}", encoding="utf-8")

            inventory = workflow_manager.build_workflow_inventory(workflow_roots=[workflow_root])

            self.assertEqual(inventory["summary"]["total"], 1)
            self.assertEqual(inventory["workflows"][0]["name"], "product_art")
            self.assertFalse(inventory["workflows"][0]["enabled"])
            self.assertFalse(inventory["workflows"][0]["execution_enabled"])
            self.assertFalse(inventory["execution_enabled"])

        self.run_with_temp_workflows(scenario)

    def test_workflow_classification(self) -> None:
        self.assertEqual(
            workflow_manager.infer_workflow_type(Path("/tmp/transparent_png_workflow.json")),
            "transparent_png",
        )
        self.assertEqual(
            workflow_manager.infer_workflow_type(Path("/tmp/mockup_listing.json")),
            "mockup",
        )
        self.assertEqual(
            workflow_manager.infer_workflow_type(Path("/tmp/upscale_ultrasharp.json")),
            "upscale",
        )
        self.assertEqual(
            workflow_manager.infer_workflow_type(Path("/tmp/random_flow.json")),
            "generic",
        )

    def test_workflow_inventory_report_writes(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "background_removal.json").write_text("{}", encoding="utf-8")
            inventory = workflow_manager.build_workflow_inventory(workflow_roots=[workflow_root])
            result = workflow_manager.write_workflow_inventory_report(inventory)

            report_path = Path(result["report_path"])
            self.assertTrue(report_path.exists())
            text = report_path.read_text(encoding="utf-8")
            self.assertIn("execution_enabled: false", text)
            self.assertIn("background_removal", text)

        self.run_with_temp_workflows(scenario)

    def test_execution_disabled_in_service_output(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "shirt_typography.json").write_text("{}", encoding="utf-8")
            workflow_manager.build_workflow_inventory(workflow_roots=[workflow_root])

            result = workflow_manager.list_workflows()

            self.assertFalse(result["execution_enabled"])
            self.assertEqual(len(result["discovered_workflows"]), 1)
            discovered = result["discovered_workflows"][0]
            self.assertFalse(discovered["enabled"])
            self.assertFalse(discovered["execution_enabled"])

        self.run_with_temp_workflows(scenario)

    def test_image_worker_selects_discovered_workflow_but_does_not_execute(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "shirt_typography.json").write_text(
                json.dumps({"nodes": [{"class_type": "CLIPTextEncode"}]}),
                encoding="utf-8",
            )
            workflow_manager.build_workflow_inventory(workflow_roots=[workflow_root])

            plan = image_worker.plan({"product_type": "shirt", "design_prompt": "bold typography shirt"})

            self.assertEqual(plan["selected_workflow"]["name"], "shirt_typography")
            self.assertEqual(plan["selected_workflow"]["type"], "typography")
            self.assertFalse(plan["execution_enabled"])
            self.assertFalse(plan["selected_workflow"]["execution_enabled"])

        self.run_with_temp_workflows(scenario)

    def test_control_center_includes_workflow_readiness(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "transparent_png.json").write_text("{}", encoding="utf-8")
            workflow_manager.build_workflow_inventory(workflow_roots=[workflow_root])

            result = control_center.gpu_comfyui_readiness()

            self.assertEqual(result["workflow_count"], 1)
            self.assertEqual(result["workflow_types"]["transparent_png"], 1)
            self.assertIn("missing_recommended_workflows", result)
            self.assertFalse(result["execution_enabled"])

        self.run_with_temp_workflows(scenario)

    def test_api_scan_route_output_is_safe(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "mockup.json").write_text("{}", encoding="utf-8")

            try:
                from jamesos.core import api
            except ModuleNotFoundError as exc:
                if exc.name in {"fastapi", "pydantic"}:
                    self.skipTest("fastapi/pydantic are not installed in this Python environment")
                raise

            with (
                patch.object(api, "require_key", return_value=None),
                patch.object(api, "scan_workflows_and_report", lambda: workflow_manager.scan_and_report([workflow_root])),
            ):
                result = api.workflows_scan_route()

            self.assertEqual(result["status"], "ok")
            self.assertFalse(result["execution_enabled"])
            self.assertFalse(result["workflows"][0]["enabled"])
            self.assertFalse(result["workflows"][0]["execution_enabled"])

        self.run_with_temp_workflows(scenario)


if __name__ == "__main__":
    unittest.main()
