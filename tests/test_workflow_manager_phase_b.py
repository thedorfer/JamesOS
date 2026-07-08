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
                patch.object(workflow_manager, "MANAGED_WORKFLOW_TEMPLATE_ROOT", root / "JamesOSData" / "JamesOS" / "CreativeStudio" / "WorkflowTemplates"),
                patch.object(workflow_manager, "WORKFLOW_ROOTS", [
                    root / "JamesOSData" / "JamesOS" / "CreativeStudio" / "WorkflowTemplates",
                    root / "AI" / "Workflows",
                    root / "JamesOSData" / "JamesOS" / "AI" / "Workflows",
                ]),
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

    def test_default_print_design_api_template_is_created(self) -> None:
        def scenario(root: Path) -> None:
            result = workflow_manager.initialize_default_workflow_templates()
            path = Path(result["default_print_design_workflow_path"])
            transparent_path = Path(result["default_transparent_print_design_workflow_path"])

            self.assertTrue(path.exists())
            self.assertTrue(transparent_path.exists())
            self.assertEqual(path.name, "print_design_basic.api.json")
            self.assertEqual(transparent_path.name, "transparent_print_design_basic.api.json")
            data = json.loads(path.read_text(encoding="utf-8"))
            transparent_data = json.loads(transparent_path.read_text(encoding="utf-8"))
            self.assertTrue(workflow_manager.validate_comfyui_api_prompt(data)["valid"])
            self.assertTrue(workflow_manager.validate_comfyui_api_prompt(transparent_data)["valid"])
            self.assertTrue(result["background_removal_required"])

        self.run_with_temp_workflows(scenario)

    def test_workflow_format_classifier_detects_api_ui_and_jamesos_spec(self) -> None:
        def scenario(root: Path) -> None:
            api_path = Path(workflow_manager.initialize_default_workflow_templates()["default_print_design_workflow_path"])
            ui_path = root / "ui_workflow.json"
            spec_path = root / "jamesos_spec.json"
            ui_path.write_text(json.dumps({"last_node_id": 7, "nodes": [], "links": []}), encoding="utf-8")
            spec_path.write_text(json.dumps({"creative_spec": {}, "positive_prompt": "hello"}), encoding="utf-8")

            self.assertEqual(workflow_manager.classify_workflow_format(api_path), "comfyui_api_prompt")
            self.assertEqual(workflow_manager.classify_workflow_format(ui_path), "comfyui_ui_workflow")
            self.assertEqual(workflow_manager.classify_workflow_format(spec_path), "jamesos_spec")

        self.run_with_temp_workflows(scenario)

    def test_get_executable_prefers_managed_print_design_template(self) -> None:
        def scenario(root: Path) -> None:
            external = root / "AI" / "Workflows"
            external.mkdir(parents=True)
            (external / "print_design_basic_other.api.json").write_text(
                json.dumps(workflow_manager._default_print_design_template()),
                encoding="utf-8",
            )

            result = workflow_manager.get_executable_workflow_template("print_design_basic")

            self.assertEqual(Path(result["workflow_path"]).name, "print_design_basic.api.json")
            self.assertTrue(result["comfyui_open_workflow_ignored"])

        self.run_with_temp_workflows(scenario)

    def test_get_executable_prefers_managed_transparent_print_design_template(self) -> None:
        def scenario(root: Path) -> None:
            result = workflow_manager.get_executable_workflow_template("transparent_print_design_basic")

            self.assertEqual(Path(result["workflow_path"]).name, "transparent_print_design_basic.api.json")
            self.assertEqual(result["transparency_method"], "prompt_only")
            self.assertTrue(result["background_removal_required"])

        self.run_with_temp_workflows(scenario)

    def test_numeric_node_reference_is_detected_and_normalized(self) -> None:
        data = workflow_manager._default_print_design_template()
        data["7"]["inputs"]["images"] = [6, 0]

        invalid = workflow_manager.validate_comfyui_api_prompt_structure(data)
        self.assertFalse(invalid["valid"])
        self.assertEqual(invalid["issues"][0]["node_id"], "7")
        self.assertEqual(invalid["issues"][0]["field"], "inputs.images")
        self.assertIn("string node ID", invalid["issues"][0]["message"])

        normalized = workflow_manager.normalize_comfyui_api_prompt_node_references(data)
        self.assertEqual(normalized["7"]["inputs"]["images"], ["6", 0])
        valid = workflow_manager.validate_comfyui_api_prompt_structure(normalized)
        self.assertTrue(valid["valid"])

    def test_managed_template_saveimage_references_existing_string_node(self) -> None:
        def scenario(root: Path) -> None:
            result = workflow_manager.initialize_default_workflow_templates()
            path = Path(result["default_transparent_print_design_workflow_path"])
            data = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(data["7"]["inputs"]["images"], ["6", 0])
            self.assertIn("6", data)
            self.assertTrue(workflow_manager.validate_comfyui_api_prompt_structure(data)["valid"])

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

    def test_print_design_request_can_use_product_art_basic_alias(self) -> None:
        def scenario(root: Path) -> None:
            workflow_root = root / "AI" / "Workflows"
            workflow_root.mkdir(parents=True)
            (workflow_root / "product_art_basic.json").write_text("{}", encoding="utf-8")
            workflow_manager.build_workflow_inventory(workflow_roots=[workflow_root])

            plan = image_worker.plan({
                "brand_id": "unitystitches",
                "creative_spec": {
                    "stage": "design_art",
                    "product_type": "design_art",
                    "niche": "LGBTQ+ pride",
                    "design_recipe": {
                        "product_type": "design_art",
                        "niche": "LGBTQ+ pride",
                        "artwork_type": "flat print design",
                        "text": "Love Is Love",
                    },
                },
            })

            self.assertEqual(plan["requested_workflow_type"], "print_design_basic")
            self.assertEqual(plan["selected_workflow"]["name"], "product_art_basic")
            self.assertTrue(plan["workflow_alias_used"])
            self.assertFalse(plan["execution_enabled"])

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
