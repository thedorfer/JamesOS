from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from jamesos.services import control_center, creative_studio, job_queue, planner, server_config, worker_registry


class PlannerWorkersPipelineTests(unittest.TestCase):
    def run_with_foundation(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "JamesOSData"
            queue_root = vault / "JamesOS" / "Queue"
            config_root = vault / "JamesOS" / "Config"
            reports_root = vault / "JamesOS" / "Reports"

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

    def test_planner_health(self) -> None:
        result = planner.health()

        self.assertEqual(result["status"], "ok")
        self.assertFalse(result["executes_jobs"])
        self.assertIn("daily_product_generation", result["supported_intents"])

    def test_planner_creates_plan_but_does_not_execute(self) -> None:
        def scenario(vault: Path) -> None:
            result = planner.create_plan("daily_product_generation", "Generate Commerce Shop drafts")

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["intent"], "daily_product_generation")
            self.assertTrue(result["requires_approval"])
            self.assertFalse(result["executes_jobs"])
            self.assertEqual(len(job_queue.list_jobs()), 0)

        self.run_with_foundation(scenario)

    def test_worker_registry_lists_workers(self) -> None:
        result = worker_registry.list_workers()
        names = {worker["name"] for worker in result["workers"]}

        self.assertEqual(result["status"], "ok")
        self.assertIn("comfyui_worker", names)
        self.assertIn("printify_worker", names)
        self.assertIn("etsy_worker", names)

    def test_disabled_workers_cannot_execute(self) -> None:
        self.assertFalse(worker_registry.can_execute("comfyui_worker", "creative_image_generation"))
        self.assertFalse(worker_registry.can_execute("printify_worker", "printify_draft"))
        self.assertFalse(worker_registry.can_execute("etsy_worker", "etsy_review"))

    def test_creative_pipeline_stages_exist(self) -> None:
        def scenario(vault: Path) -> None:
            pipeline = creative_studio.create_pipeline({"title": "Pipeline shell test"})
            stage_names = [stage["name"] for stage in pipeline["payload"]["stages"]]

            self.assertEqual(stage_names, creative_studio.PIPELINE_STAGES)
            self.assertTrue(pipeline["requires_approval"])
            self.assertFalse(pipeline["approved"])
            self.assertFalse(pipeline["payload"]["comfyui_execution"])
            self.assertFalse(pipeline["payload"]["printify_execution"])
            self.assertFalse(pipeline["payload"]["etsy_execution"])
            for stage in pipeline["payload"]["stages"]:
                self.assertFalse(stage["execution_enabled"])

        self.run_with_foundation(scenario)

    def test_control_center_summary_is_human_readable(self) -> None:
        def scenario(vault: Path) -> None:
            result = control_center.human_summary()

            self.assertEqual(result["status"], "ok")
            self.assertIn("Overall status", result["sections"])
            self.assertIn("What is ready", result["sections"])
            self.assertIn("Pending approvals", result["sections"])
            self.assertNotIn("queue_counts", str(result["sections"]))
            self.assertFalse(result["safety"]["comfyui_execution_enabled"])
            self.assertFalse(result["safety"]["printify_execution_enabled"])
            self.assertFalse(result["safety"]["etsy_execution_enabled"])

        self.run_with_foundation(scenario)


if __name__ == "__main__":
    unittest.main()
