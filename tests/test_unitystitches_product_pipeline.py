from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from jamesos.services import creative_studio, job_queue, unitystitches_product_pipeline as unity


class UnityStitchesProductPipelineTests(unittest.TestCase):
    def run_with_pipeline(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vault = root / "JamesOSData"
            queue_root = vault / "JamesOS" / "Queue"
            config_root = vault / "JamesOS" / "Config"
            reports_root = vault / "JamesOS" / "Reports"
            drafts_root = vault / "JamesOS" / "Products" / "UnityStitches" / "Drafts"

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
                patch.object(unity, "CONFIG_PATH", config_root / "unitystitches_products.yaml"),
                patch.object(unity, "DRAFTS_ROOT", drafts_root),
                patch.object(unity, "REPORT_PATH", reports_root / "UnityStitches Product Drafts.md"),
                patch.object(job_queue, "QUEUE_ROOT", queue_root),
                patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"),
                patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"),
                patch.object(job_queue, "REPORT_PATH", reports_root / "Job Queue.md"),
                patch.object(creative_studio, "CONFIG_PATH", config_root / "creative_studio.yaml"),
                patch.object(creative_studio, "REPORT_PATH", reports_root / "Creative Studio.md"),
            ]
            for item in patches:
                item.start()
            try:
                callback(vault)
            finally:
                for item in reversed(patches):
                    item.stop()

    def test_generates_exactly_two_drafts(self) -> None:
        def scenario(vault: Path) -> None:
            result = unity.generate_daily_product_drafts("2026-07-07")

            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["draft_count"], 2)
            self.assertEqual(len(result["drafts"]), 2)

        self.run_with_pipeline(scenario)

    def test_always_includes_one_womens_underwear_product(self) -> None:
        def scenario(vault: Path) -> None:
            result = unity.generate_daily_product_drafts("2026-07-07")
            product_types = [draft["product_type"] for draft in result["drafts"]]

            self.assertEqual(product_types.count("womens_underwear"), 1)

        self.run_with_pipeline(scenario)

    def test_rotating_product_is_not_always_shirt(self) -> None:
        def scenario(vault: Path) -> None:
            rotating_types = set()
            for day in ["2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10"]:
                result = unity.generate_daily_product_drafts(day)
                rotating_types.add(result["drafts"][1]["product_type"])

            self.assertGreater(len(rotating_types), 1)
            self.assertTrue(any(product_type != "shirt" for product_type in rotating_types))

        self.run_with_pipeline(scenario)

    def test_all_drafts_are_needs_review_and_require_approval(self) -> None:
        def scenario(vault: Path) -> None:
            result = unity.generate_daily_product_drafts("2026-07-07")

            for draft in result["drafts"]:
                self.assertEqual(draft["status"], "needs_review")
                self.assertTrue(draft["approval_required"])

        self.run_with_pipeline(scenario)

    def test_external_execution_flags_remain_false(self) -> None:
        def scenario(vault: Path) -> None:
            result = unity.generate_daily_product_drafts("2026-07-07")

            self.assertFalse(result["safety"]["external_execution_enabled"])
            self.assertFalse(result["safety"]["comfyui_execution_enabled"])
            self.assertFalse(result["safety"]["create_printify_draft"])
            self.assertFalse(result["safety"]["publish_to_etsy"])
            self.assertFalse(result["safety"]["send_to_production"])
            for draft in result["drafts"]:
                self.assertFalse(draft["external_execution_enabled"])
                self.assertFalse(draft["comfyui_execution_enabled"])
                self.assertFalse(draft["printify_execution_enabled"])
                self.assertFalse(draft["etsy_execution_enabled"])
                self.assertFalse(draft["publish_enabled"])
                self.assertFalse(draft["order_enabled"])
                self.assertFalse(draft["send_enabled"])

        self.run_with_pipeline(scenario)

    def test_creates_creative_studio_pipeline_job(self) -> None:
        def scenario(vault: Path) -> None:
            result = unity.generate_daily_product_drafts("2026-07-07")
            job = result["creative_pipeline_job"]

            self.assertEqual(job["type"], "creative_pipeline")
            self.assertTrue(job["requires_approval"])
            self.assertFalse(job["approved"])
            self.assertEqual(len(creative_studio.list_pipelines()), 1)

        self.run_with_pipeline(scenario)

    def test_does_not_call_external_systems(self) -> None:
        def scenario(vault: Path) -> None:
            result = unity.generate_daily_product_drafts("2026-07-07")
            pipeline_payload = result["creative_pipeline_job"]["payload"]

            self.assertFalse(pipeline_payload["external_execution"])
            self.assertFalse(pipeline_payload["comfyui_execution"])
            self.assertFalse(pipeline_payload["printify_execution"])
            self.assertFalse(pipeline_payload["etsy_execution"])
            self.assertFalse(pipeline_payload["publish"])
            self.assertFalse(pipeline_payload["order"])
            self.assertFalse(pipeline_payload["send"])

        self.run_with_pipeline(scenario)


if __name__ == "__main__":
    unittest.main()
