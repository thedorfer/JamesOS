from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from jamesos.services import creative_studio, job_queue


class CreativeStudioTests(unittest.TestCase):
    def run_with_studio(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = {
                **creative_studio.DEFAULT_CONFIG,
                "output_root": str(root / "CreativeStudio"),
                "generated_root": str(root / "CreativeStudio" / "Generated"),
                "assets_root": str(root / "CreativeStudio" / "Assets"),
                "jobs_root": str(root / "CreativeStudio" / "Jobs"),
                "templates_root": str(root / "CreativeStudio" / "Templates"),
            }
            config_path = root / "Config" / "creative_studio.yaml"
            config_path.parent.mkdir(parents=True)
            config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

            queue_root = root / "Queue"
            patches = [
                patch.object(creative_studio, "CONFIG_PATH", config_path),
                patch.object(creative_studio, "REPORT_PATH", root / "Reports" / "Creative Studio.md"),
                patch.object(job_queue, "QUEUE_ROOT", queue_root),
                patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"),
                patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"),
                patch.object(job_queue, "REPORT_PATH", root / "Reports" / "Job Queue.md"),
            ]
            for item in patches:
                item.start()
            try:
                callback(root)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_config_loads(self) -> None:
        def scenario(root: Path) -> None:
            config = creative_studio.load_config()

            self.assertTrue(config["enabled"])
            self.assertEqual(config["image_provider"], "comfyui")
            self.assertEqual(config["comfyui_api_url"], "http://localhost:8188")
            self.assertTrue(config["require_approval"])

        self.run_with_studio(scenario)

    def test_health_returns_safe_status(self) -> None:
        def scenario(root: Path) -> None:
            result = creative_studio.health()

            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["safe"])
            self.assertFalse(result["external_execution_enabled"])
            self.assertFalse(result["comfyui_execution_enabled"])
            self.assertFalse(result["printify_execution_enabled"])
            self.assertFalse(result["etsy_execution_enabled"])
            self.assertFalse(result["publishing_enabled"])
            self.assertFalse(result["ordering_enabled"])

        self.run_with_studio(scenario)

    def test_create_image_job_requires_review_and_approval(self) -> None:
        def scenario(root: Path) -> None:
            job = creative_studio.create_sample_image_job()

            self.assertEqual(job["type"], "creative_image_generation")
            self.assertEqual(job["status"], "pending")
            self.assertTrue(job["requires_approval"])
            self.assertFalse(job["approved"])
            self.assertEqual(job["payload"]["creative_status"], "needs_review")
            self.assertFalse(job["payload"]["comfyui_execution"])
            self.assertFalse(job["payload"]["printify_execution"])
            self.assertFalse(job["payload"]["etsy_execution"])

        self.run_with_studio(scenario)

    def test_create_product_draft_job(self) -> None:
        def scenario(root: Path) -> None:
            job = creative_studio.create_sample_product_job()

            self.assertEqual(job["type"], "creative_product_draft")
            self.assertTrue(job["payload"]["draft_only"])
            self.assertTrue(job["payload"]["approval_required"])
            self.assertFalse(job["payload"]["publish"])
            self.assertFalse(job["payload"]["order"])
            self.assertFalse(job["payload"]["send"])

        self.run_with_studio(scenario)

    def test_approval_changes_approval_state(self) -> None:
        def scenario(root: Path) -> None:
            job = creative_studio.create_sample_image_job()
            approved = creative_studio.approve_creative_job(job["job_id"])

            self.assertTrue(approved["approved"])
            approval_step = next(step for step in approved["steps"] if step["name"] == "approval")
            self.assertEqual(approval_step["status"], "approved")

        self.run_with_studio(scenario)

    def test_fail_creative_job(self) -> None:
        def scenario(root: Path) -> None:
            job = creative_studio.create_sample_product_job()
            failed = creative_studio.fail_creative_job(job["job_id"], "not ready")

            self.assertEqual(failed["status"], "failed")
            self.assertIn("not ready", str(failed["logs"]))

        self.run_with_studio(scenario)

    def test_no_external_execution_occurs(self) -> None:
        def scenario(root: Path) -> None:
            job = creative_studio.create_creative_job(
                "creative_mockup",
                {"title": "Mockup placeholder"},
            )

            payload = job["payload"]
            self.assertFalse(payload["external_execution"])
            self.assertFalse(payload["comfyui_execution"])
            self.assertFalse(payload["printify_execution"])
            self.assertFalse(payload["etsy_execution"])
            self.assertFalse(payload["publish"])
            self.assertFalse(payload["order"])
            self.assertFalse(payload["send"])

        self.run_with_studio(scenario)


if __name__ == "__main__":
    unittest.main()
