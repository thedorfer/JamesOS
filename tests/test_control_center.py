from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from jamesos.services import control_center, creative_studio, job_queue, server_config


class ControlCenterTests(unittest.TestCase):
    def run_with_control_center(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "JamesOSData"
            queue_root = vault / "JamesOS" / "Queue"
            config_root = vault / "JamesOS" / "Config"
            reports_root = vault / "JamesOS" / "Reports"
            graph_file = vault / "JamesOS" / "Brain" / "knowledge_graph.json"
            graph_report = reports_root / "Knowledge Graph.md"

            creative_config = {
                **creative_studio.DEFAULT_CONFIG,
                "output_root": str(vault / "JamesOS" / "CreativeStudio"),
                "generated_root": str(vault / "JamesOS" / "CreativeStudio" / "Generated"),
                "assets_root": str(vault / "JamesOS" / "CreativeStudio" / "Assets"),
                "jobs_root": str(vault / "JamesOS" / "CreativeStudio" / "Jobs"),
                "templates_root": str(vault / "JamesOS" / "CreativeStudio" / "Templates"),
            }
            config_root.mkdir(parents=True, exist_ok=True)
            (config_root / "creative_studio.yaml").write_text(
                yaml.safe_dump(creative_config, sort_keys=False),
                encoding="utf-8",
            )

            patches = [
                patch.object(control_center, "VAULT", vault),
                patch.object(control_center, "REPORT_PATH", reports_root / "Control Center.md"),
                patch.object(control_center, "GRAPH_FILE", graph_file),
                patch.object(control_center, "GRAPH_REPORT", graph_report),
                patch.object(job_queue, "QUEUE_ROOT", queue_root),
                patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"),
                patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"),
                patch.object(job_queue, "REPORT_PATH", reports_root / "Job Queue.md"),
                patch.object(creative_studio, "CONFIG_PATH", config_root / "creative_studio.yaml"),
                patch.object(creative_studio, "REPORT_PATH", reports_root / "Creative Studio.md"),
                patch.object(server_config, "VAULT", vault),
                patch.object(server_config, "CONFIG_ROOT", config_root),
                patch.object(server_config, "REPORT_PATH", reports_root / "Server Configuration.md"),
            ]
            for item in patches:
                item.start()
            try:
                callback(vault)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_health_returns_ok(self) -> None:
        def scenario(vault: Path) -> None:
            result = control_center.health()

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["safe"])

        self.run_with_control_center(scenario)

    def test_job_counts_are_present(self) -> None:
        def scenario(vault: Path) -> None:
            result = control_center.jobs()

            self.assertEqual(result["status"], "ok")
            self.assertEqual(
                sorted(result["queue_counts"].keys()),
                ["failed", "in_progress", "pending", "processed"],
            )

        self.run_with_control_center(scenario)

    def test_integrations_are_listed(self) -> None:
        def scenario(vault: Path) -> None:
            result = control_center.integrations()

            self.assertEqual(result["status"], "ok")
            for name in ["comfyui", "printify", "etsy", "tasker_phone_ingestion", "outlook_import"]:
                self.assertIn(name, result["integrations"])

        self.run_with_control_center(scenario)

    def test_comfyui_execution_remains_false(self) -> None:
        def scenario(vault: Path) -> None:
            result = control_center.integrations()

            self.assertFalse(result["gpu_comfyui_readiness"]["execution_enabled"])
            self.assertFalse(result["integrations"]["comfyui"]["execution_enabled"])
            self.assertTrue(result["gpu_comfyui_readiness"]["one_image_job_at_a_time"])

        self.run_with_control_center(scenario)

    def test_printify_and_etsy_execution_remain_false(self) -> None:
        def scenario(vault: Path) -> None:
            result = control_center.integrations()

            self.assertFalse(result["integrations"]["printify"]["execution_enabled"])
            self.assertFalse(result["integrations"]["printify"]["publish_enabled"])
            self.assertFalse(result["integrations"]["etsy"]["execution_enabled"])
            self.assertFalse(result["integrations"]["etsy"]["publish_enabled"])

        self.run_with_control_center(scenario)


if __name__ == "__main__":
    unittest.main()
