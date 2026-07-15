from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from scripts import test_artwork_pipeline_e2e as harness
from jamesos.services import job_queue


class ArtworkPipelineE2ETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory(prefix="e2e-harness-tests-")
        cls.root = Path(cls.temporary.name)
        cls.report_path = cls.root / harness.REPORT_FILENAME
        cls.report = harness.run_mocked(cls.report_path)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.temporary.cleanup()

    def transition(self, name: str) -> dict:
        return next(item for item in self.report["transitions"] if item["stage"] == name)

    def authoritative_live_fixture(self, root: Path, job_id: str = "e2e-artwork-fixture-00000001") -> tuple[dict, dict]:
        job_root = root / job_id
        candidate_root = job_root / "production-artifacts" / "candidate"
        intermediates_root = candidate_root / "intermediates"
        intermediates_root.mkdir(parents=True)
        source, derivative = job_root / "generated-concept.png", job_root / "transparent_artifact.png"
        Image.new("RGB", (8, 8), "white").save(source)
        Image.new("RGBA", (8, 8), (10, 20, 30, 128)).save(derivative)
        derivative_sha, source_sha = harness.hash_file(derivative), harness.hash_file(source)
        stages, prior_sha, prior_path = [], derivative_sha, derivative
        for number in range(1, 4):
            output = intermediates_root / f"stage-{number}.png"
            Image.new("RGBA", (8 * 2 ** number, 8 * 2 ** number), (number, 20, 30, 128)).save(output)
            output_sha = harness.hash_file(output)
            stages.append({"stage": number, "input_path": str(prior_path), "input_sha256": prior_sha,
                           "output_path": str(output), "output_sha256": output_sha})
            prior_sha, prior_path = output_sha, output
        candidate = candidate_root / "production-candidate.png"
        Image.new("RGBA", (32, 40), (1, 2, 3, 128)).save(candidate)
        production = {
            "job_id": job_id, "status": "production_candidate_complete", "production_artifact_status": "needs_final_review",
            "production_candidate_path": str(candidate), "production_candidate_sha256": harness.hash_file(candidate),
            "approved_source_path": str(derivative), "approved_source_sha256": derivative_sha,
            "model_name": harness.DEFAULT_MODEL, "model_sha256": "model-sha", "intermediate_stages": stages,
            "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
        }
        for name, color in (("white", "white"), ("dark", "black"), ("checkerboard", "gray")):
            preview = candidate_root / f"production-preview-{name}.png"
            Image.new("RGB", (32, 40), color).save(preview)
            production[f"{name}_preview_path"] = str(preview)
            production[f"{name}_preview_sha256"] = harness.hash_file(preview)
        metadata = candidate_root / "production-artifact.json"
        metadata.write_text(json.dumps(production, indent=2, sort_keys=True), encoding="utf-8")
        approval = {"approved_artifact_path": str(derivative), "approved_artifact_sha256": derivative_sha,
                    "approved_by": "fixture-reviewer", "approved_at": "2026-07-15T12:00:00-05:00"}
        payload = {
            "e2e_test_job": True, "output_image_path": str(source), "concept_approved": True,
            "concept_approved_by": "fixture-reviewer", "concept_approved_at": "2026-07-15T11:59:00-05:00",
            "finishing_metadata": {"source_sha256_before": source_sha, "source_sha256_after": source_sha},
            "transparent_artifact_path": str(derivative), "transparent_derivative_approval": approval,
            "production_artifact": production, "production_artifact_status": "needs_final_review",
            "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False,
        }
        model = {"model_name": harness.DEFAULT_MODEL, "sha256": "model-sha", "validated": True,
                 "production_approved": True, "path": str(root / "model.pth")}
        return {"job_id": job_id, "payload": payload}, model

    def test_complete_mocked_happy_path_and_machine_report(self) -> None:
        self.assertEqual(self.report["result"], "passed")
        self.assertEqual(self.report["mode"], "mocked")
        self.assertEqual(json.loads(self.report_path.read_text(encoding="utf-8"))["result"], "passed")
        self.assertEqual([item["stage"] for item in self.report["transitions"]], [
            "generated_concept_inspected", "concept_approved", "transparent_artifact_prepared",
            "transparent_artifact_approved", "model_verified", "production_stages_complete",
            "production_candidate_prepared", "final_artifact_approved",
        ])
        self.assertGreater(self.report["total_runtime_seconds"], 0)
        self.assertEqual([item["status"] for item in self.report["mocked_comfyui_responses"]], ["completed"] * 3)

    def test_unique_test_job_enforcement_and_protected_job_refusal(self) -> None:
        first = harness.unique_test_job_id(datetime(2026, 7, 15, 12, 0, 0), "00000001")
        second = harness.unique_test_job_id(datetime(2026, 7, 15, 12, 0, 0), "00000002")
        self.assertNotEqual(first, second)
        harness.validate_test_job_id(first)
        with self.assertRaises(harness.E2EHarnessError):
            harness.validate_test_job_id(harness.PROTECTED_JOB_ID)
        with self.assertRaises(harness.E2EHarnessError):
            harness.validate_test_job_id("ordinary-production-job")
        with self.assertRaises(harness.E2EHarnessError):
            harness.run_live(self.root / "guard.json", confirmed=False)

    def test_deterministic_concept_and_source_immutability(self) -> None:
        one, two = self.root / "fixture-one.png", self.root / "fixture-two.png"
        first_hash = harness.create_concept_fixture(one)
        second_hash = harness.create_concept_fixture(two)
        self.assertEqual(first_hash, second_hash)
        self.assertEqual(self.report["source"]["before_sha256"], self.report["source"]["after_sha256"])
        self.assertEqual(self.report["source"]["dimensions"], [768, 768])
        self.assertEqual(self.report["source"]["mode"], "RGB")
        self.assertEqual(self.report["synthetic_fixture_style"], "illustrative_rocket_badge")
        self.assertTrue(self.report["ai_upscale_visual_review_required"])
        with Image.open(one) as image:
            self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(image.getpixel((384, 100)), (24, 48, 105))
            self.assertEqual(image.getpixel((384, 400)), (22, 174, 166))
            self.assertEqual(image.getpixel((270, 475)), (242, 91, 116))
            self.assertEqual(image.getpixel((384, 550)), (255, 218, 65))
            self.assertEqual(image.getpixel((384, 311)), (255, 255, 255))
            self.assertEqual(image.getpixel((18, 150)), (22, 174, 166))

    def test_fixture_inspection_truthfully_requires_background_removal(self) -> None:
        inspection = self.transition("generated_concept_inspected")["status"]
        self.assertTrue(inspection["print_readiness_analysis"]["background_removal_required"])
        self.assertFalse(inspection["final_print_ready"])
        self.assertEqual(inspection["provider_status"], "not_ready")
        self.assertEqual(inspection["printify_status"], "not_ready")

    def test_transparent_derivative_and_sha_approval(self) -> None:
        derivative = self.report["derivative"]
        approval = self.transition("transparent_artifact_approved")["approval"]
        self.assertEqual(derivative["mode"], "RGBA")
        self.assertEqual(derivative["alpha_extrema"], [0, 255])
        self.assertEqual(approval["approved_artifact_sha256"], derivative["sha256"])

    def test_model_is_sha_approved_and_filename_alone_is_insufficient(self) -> None:
        model = self.report["model"]
        self.assertEqual(model["model_name"], harness.DEFAULT_MODEL)
        self.assertEqual(model["sha256"], model["validated_model_sha256"])
        self.assertTrue(model["validated"])
        self.assertTrue(model["production_approved"])
        failed_report = self.root / "mismatch-report.json"
        with self.assertRaises(harness.E2EHarnessError):
            harness.run_mocked(failed_report, model_hash_mismatch=True)
        failed = json.loads(failed_report.read_text(encoding="utf-8"))
        self.assertEqual(failed["result"], "failed")
        self.assertEqual(failed["diagnostic"]["failed_after_transition"], "transparent_artifact_approved")
        self.assertNotIn("production_stages_complete", [item["stage"] for item in failed["transitions"]])
        self.assertNotIn("final_artifact_approved", [item["stage"] for item in failed["transitions"]])

    def test_stage_hash_chaining_dimensions_and_one_model_pass(self) -> None:
        stages = self.transition("production_stages_complete")["stages"]
        self.assertEqual([stage["input_dimensions"] for stage in stages], [[768, 768], [1536, 1536], [3072, 3072]])
        self.assertEqual([stage["output_dimensions"] for stage in stages], [[1536, 1536], [3072, 3072], [6144, 6144]])
        self.assertEqual(stages[1]["input_sha256"], stages[0]["output_sha256"])
        self.assertEqual(stages[2]["input_sha256"], stages[1]["output_sha256"])
        for stage, workflow in zip(stages, self.report["mocked_workflows"]):
            self.assertEqual(sum(node["class_type"] == "ImageUpscaleWithModel" for node in workflow.values()), 1)
            self.assertEqual(workflow["2"]["inputs"]["model_name"], harness.DEFAULT_MODEL)
            for key in ("input_sha256", "output_sha256", "input_dimensions", "output_dimensions", "model_name", "model_sha256", "settings", "comfyui_prompt_id", "execution_time_seconds"):
                self.assertIn(key, stage)

    def test_final_candidate_dimensions_placement_and_preview_hashes(self) -> None:
        candidate = self.report["candidate"]
        transition = self.transition("production_candidate_prepared")
        self.assertEqual(candidate["dimensions"], [4500, 5400])
        self.assertEqual(candidate["mode"], "RGBA")
        self.assertEqual(candidate["artwork_dimensions"], [4050, 4050])
        self.assertEqual(candidate["placement_coordinates"], [225, 675])
        # The mocked sandbox is intentionally cleaned; retained report evidence remains authoritative.
        self.assertEqual(transition["candidate"]["dimensions"], [4500, 5400])
        stage_metadata = self.transition("production_stages_complete")
        self.assertEqual(len(stage_metadata["stages"]), 3)
        candidate_transition = self.transition("production_candidate_prepared")
        self.assertEqual(set(candidate_transition["previews"]), {"white", "dark", "checkerboard"})
        self.assertTrue(all(item["sha256"] for item in candidate_transition["previews"].values()))

    def test_final_approval_is_separate_immutable_and_idempotent(self) -> None:
        approval = self.transition("final_artifact_approved")
        self.assertTrue(approval["idempotent_repeat"])
        self.assertTrue(approval["approval"]["approved_at"])
        self.assertEqual(approval["approval"]["approval_scope"], "jamesos_artwork_candidate_human_review_only")
        self.assertTrue(approval["approval_record_sha256"])
        self.assertEqual(self.report["production_metadata"]["before_sha256"], self.report["production_metadata"]["after_sha256"])
        self.assertNotEqual(Path(self.report["production_metadata"]["path"]).name, Path(self.report["final_approval"]["path"]).name)

    def test_truthful_non_provider_ready_ending(self) -> None:
        assertions = self.report["status_assertions"]
        self.assertTrue(all(assertions.values()))

    def test_cleanup_is_confined_to_e2e_job(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue_root = root / "Queue"
            job_id = harness.unique_test_job_id(suffix="cleanup01")
            artifacts = root / "2026-07-15" / job_id
            artifacts.mkdir(parents=True)
            (artifacts / "owned.txt").write_text("owned", encoding="utf-8")
            unrelated = root / "unrelated"
            unrelated.mkdir()
            (unrelated / "keep.txt").write_text("keep", encoding="utf-8")
            patches = (
                patch.object(job_queue, "QUEUE_ROOT", queue_root), patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"), patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"), patch.object(job_queue, "REPORT_PATH", root / "report.md"),
                patch.object(harness.image_worker, "GENERATED_ROOT", root),
            )
            with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
                (queue_root / "pending").mkdir(parents=True)
                (queue_root / "pending" / f"{job_id}.json").write_text("{}", encoding="utf-8")
                with self.assertRaises(harness.E2EHarnessError):
                    harness.cleanup_e2e_job(job_id, unrelated, confirmed=True)
                with self.assertRaises(harness.E2EHarnessError):
                    harness.cleanup_e2e_job(job_id, artifacts, confirmed=False)
                harness.cleanup_e2e_job(job_id, artifacts, confirmed=True)
                self.assertFalse(artifacts.exists())
                self.assertFalse((queue_root / "pending" / f"{job_id}.json").exists())
            self.assertEqual((unrelated / "keep.txt").read_text(encoding="utf-8"), "keep")

    def test_cleanup_refuses_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            outside = root / "outside"
            outside.mkdir()
            job_id = harness.unique_test_job_id(suffix="symlink01")
            dated = root / "2026-07-15"
            dated.mkdir()
            link = dated / job_id
            link.symlink_to(outside, target_is_directory=True)
            with patch.object(harness.image_worker, "GENERATED_ROOT", root):
                with self.assertRaises(harness.E2EHarnessError):
                    harness.cleanup_e2e_job(job_id, link, confirmed=True)

    def test_live_creation_and_human_approval_are_separate_modes(self) -> None:
        source = Path(harness.__file__).read_text(encoding="utf-8")
        live_body = source.split("def run_live(", 1)[1].split("def approve_live(", 1)[0]
        self.assertNotIn("approve-production-artifact", live_body)
        approval_body = source.split("def approve_live(", 1)[1].split("def main(", 1)[0]
        self.assertIn("approve-production-artifact", approval_body)
        self.assertIn("final-artifact-approval.json", approval_body)
        with self.assertRaises(harness.E2EHarnessError):
            harness.approve_live(self.root / "no.json", job_id="ordinary-job", approved_by="Human", confirmed=True)
        with self.assertRaises(harness.E2EHarnessError):
            harness.approve_live(self.root / "no.json", job_id="e2e-artwork-missing", approved_by="", confirmed=True)
        with self.assertRaises(harness.E2EHarnessError):
            harness.approve_live(self.root / "no.json", job_id="e2e-artwork-missing", approved_by="Human", confirmed=False)

    def test_harness_contains_no_commerce_or_provider_action_calls(self) -> None:
        source = Path(harness.__file__).read_text(encoding="utf-8").lower()
        for forbidden in ("upload(", "publish(", "order(", "create_listing", "submit_order", "provider_client"):
            self.assertNotIn(forbidden, source)

    def test_resume_reconstructs_from_authoritative_state_without_processing_or_approval(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, model = self.authoritative_live_fixture(root)
            report_path = root / "resumed.json"
            artifact_hashes = {str(path): harness.hash_file(path) for path in root.rglob("*") if path.is_file()}
            with patch.object(job_queue, "get_job", return_value=job), \
                    patch.object(harness.upscale_model_registry, "select_upscale_model", return_value=model), \
                    patch.object(harness, "prepare_transparent_artifact_for_job") as processing, \
                    patch.object(harness.production_artifact, "approve_transparent_artifact_for_job") as derivative_approval, \
                    patch.object(harness.production_artifact, "approve_production_artifact_for_job") as final_approval:
                report = harness.resume_live(report_path, job_id=job["job_id"])
            processing.assert_not_called()
            derivative_approval.assert_not_called()
            final_approval.assert_not_called()
            self.assertEqual(report["result"], "candidate_ready_for_visual_review")
            self.assertEqual(report["recovery_reason"], "client_interrupted_after_server_processing")
            self.assertFalse(report["final_artifact_approved"])
            self.assertTrue(all(report["status_assertions"].values()))
            self.assertEqual(artifact_hashes, {path: harness.hash_file(Path(path)) for path in artifact_hashes})

    def test_incomplete_report_is_not_approval_authority_and_approve_succeeds_after_resume(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, model = self.authoritative_live_fixture(root)
            stale_report = root / "stale.json"
            stale_report.write_text(json.dumps({"result": "running", "derivative": {"sha256": "stale"}}), encoding="utf-8")
            resumed_report = root / "resumed.json"
            with patch.object(job_queue, "get_job", return_value=job), \
                    patch.object(harness.upscale_model_registry, "select_upscale_model", return_value=model):
                harness.resume_live(resumed_report, job_id=job["job_id"])
            approval_path = Path(job["payload"]["production_artifact"]["production_candidate_path"]).parent / "final-artifact-approval.json"
            response = {"status": "ok"}
            def api(*_args, **_kwargs):
                if not approval_path.exists():
                    approval = {"approved_at": "2026-07-15T12:30:00-05:00"}
                    approval_path.write_text(json.dumps(approval), encoding="utf-8")
                return response
            refreshed = dict(job["payload"])
            refreshed.update({"final_artifact_approved": True, "final_artifact_status": "approved",
                              "final_artifact_approval": {"approval_scope": "jamesos_artwork_candidate_human_review_only"}})
            with patch.object(job_queue, "get_job", side_effect=[job, {"payload": refreshed}]), \
                    patch.object(harness.upscale_model_registry, "select_upscale_model", return_value=model), \
                    patch.object(harness, "_api_post", side_effect=api):
                report = harness.approve_live(resumed_report, job_id=job["job_id"], approved_by="James", confirmed=True)
            self.assertEqual(report["result"], "approved_after_human_visual_review")
            self.assertEqual(json.loads(stale_report.read_text(encoding="utf-8"))["result"], "running")

    def test_changed_derivative_and_stale_mutable_approval_are_refused_without_repair(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            job, model = self.authoritative_live_fixture(root)
            derivative = Path(job["payload"]["transparent_artifact_path"])
            Image.new("RGBA", (8, 8), (99, 1, 2, 255)).save(derivative)
            before = dict(job["payload"]["transparent_derivative_approval"])
            with patch.object(job_queue, "get_job", return_value=job), \
                    patch.object(harness.upscale_model_registry, "select_upscale_model", return_value=model):
                with self.assertRaisesRegex(harness.E2EHarnessError, "evidence_type=transparent_derivative_approval"):
                    harness.resume_live(root / "no-report.json", job_id=job["job_id"])
            self.assertEqual(job["payload"]["transparent_derivative_approval"], before)
            self.assertFalse((root / "no-report.json").exists())


if __name__ == "__main__":
    unittest.main()
