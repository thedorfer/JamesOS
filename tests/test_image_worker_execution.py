from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from jamesos.services import comfyui_client, image_worker, job_queue, model_registry, pod_provider_registry, prompt_library, workflow_manager
from jamesos.services import image_finisher, image_postprocessor


class ImageWorkerExecutionTests(unittest.TestCase):
    def run_with_worker(self, callback):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            queue_root = root / "Queue"
            generated_root = root / "Generated"
            inventory_path = root / "model_inventory.json"
            checkpoint = root / "models" / "checkpoints" / "sdxl.safetensors"
            workflow = root / "workflow.json"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"checkpoint")
            workflow.write_text(
                json.dumps({
                    "1": {
                        "class_type": "CheckpointLoaderSimple",
                        "inputs": {"ckpt_name": "{{checkpoint_name}}"},
                    },
                    "2": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"text": "{{positive_prompt}}"},
                    },
                    "3": {
                        "class_type": "CLIPTextEncode",
                        "inputs": {"text": "{{negative_prompt}}"},
                    },
                    "4": {"inputs": {"seed": "{{seed}}", "width": "{{width}}", "height": "{{height}}"}},
                }),
                encoding="utf-8",
            )
            inventory_path.write_text(
                json.dumps({
                    "status": "ok",
                    "models": [
                        {
                            "name": "sdxl",
                            "path": str(checkpoint),
                            "category": "checkpoints",
                            "family": "sdxl",
                            "enabled": False,
                        }
                    ],
                    "summary": {"total": 1, "by_category": {"checkpoints": 1}},
                    "execution_enabled": False,
                }),
                encoding="utf-8",
            )
            patches = [
                patch.object(job_queue, "QUEUE_ROOT", queue_root),
                patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"),
                patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"),
                patch.object(job_queue, "REPORT_PATH", root / "Job Queue.md"),
                patch.object(image_worker, "GENERATED_ROOT", generated_root),
                patch.object(image_worker, "LAST_IMAGE_PATH", generated_root / "last_image.txt"),
                patch.object(model_registry, "INVENTORY_PATH", inventory_path),
                patch.object(image_worker.model_registry, "INVENTORY_PATH", inventory_path),
                patch.object(workflow_manager, "MANAGED_WORKFLOW_TEMPLATE_ROOT", root / "WorkflowTemplates"),
                patch.object(workflow_manager, "WORKFLOW_ROOTS", [root / "WorkflowTemplates", root / "AI" / "Workflows"]),
            ]
            for item in patches:
                item.start()
            try:
                callback(root, workflow, checkpoint)
            finally:
                for item in reversed(patches):
                    item.stop()

    def image_plan(self, workflow: Path, checkpoint: Path) -> dict:
        return {
            "selected_workflow": {"name": "test_workflow", "workflow_path": str(workflow), "type": "product_art"},
            "selected_model": {"name": "sdxl", "path": str(checkpoint), "category": "checkpoints"},
            "prompt": "positive prompt",
            "negative_prompt": "negative prompt",
            "seed": 7,
            "width": 512,
            "height": 512,
        }

    def test_inspect_generated_image_reports_rgb_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rgb.png"
            Image.new("RGB", (768, 768), color=(255, 255, 255)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path)
            self.assertTrue(analysis["exists"])
            self.assertEqual(analysis["width"], 768)
            self.assertEqual(analysis["height"], 768)
            self.assertEqual(analysis["mode"], "RGB")
            self.assertFalse(analysis["alpha_channel_present"])
            self.assertFalse(analysis["meaningful_transparency_present"])
            self.assertTrue(analysis["fully_opaque"])
            self.assertTrue(analysis["production_canvas_required"])
            self.assertFalse(analysis["background_removal_required"])
            self.assertTrue(analysis["visual_review_required"])
            self.assertFalse(analysis["final_print_ready"])
            self.assertEqual(analysis["provider_status"], "not_ready")
            self.assertEqual(analysis["printify_status"], "not_ready")
            self.assertIn("needs_production_canvas", analysis["readiness_statuses"])
            self.assertIn("needs_design_review", analysis["readiness_statuses"])

    def test_inspect_generated_image_reports_fully_opaque_rgba_png(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opaque_rgba.png"
            Image.new("RGBA", (1024, 1024), (255, 255, 255, 255)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path)
            self.assertTrue(analysis["alpha_channel_present"])
            self.assertFalse(analysis["meaningful_transparency_present"])
            self.assertTrue(analysis["fully_opaque"])
            self.assertFalse(analysis["background_removal_required"])

    def test_rgb_image_with_transparency_required_requires_background_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rgb_required.png"
            Image.new("RGB", (768, 768), color=(255, 255, 255)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=True)
            self.assertTrue(analysis["background_removal_required"])
            self.assertIn("needs_background_removal", analysis["readiness_statuses"])

    def test_fully_opaque_rgba_with_transparency_required_requires_background_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opaque_rgba_required.png"
            Image.new("RGBA", (1024, 1024), (255, 255, 255, 255)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=True)
            self.assertTrue(analysis["background_removal_required"])

    def test_genuinely_transparent_rgba_with_transparency_required_does_not(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transparent_rgba_required.png"
            image = Image.new("RGBA", (1024, 1024), (255, 255, 255, 0))
            image.putpixel((0, 0), (255, 255, 255, 128))
            image.save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=True)
            self.assertFalse(analysis["background_removal_required"])

    def test_opaque_image_with_transparency_required_false_does_not_require_removal(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "opaque_required_false.png"
            Image.new("RGBA", (1024, 1024), (255, 255, 255, 255)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=False)
            self.assertFalse(analysis["background_removal_required"])

    def test_inspect_generated_image_reports_real_transparency(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transparent_rgba.png"
            image = Image.new("RGBA", (1024, 1024), (255, 255, 255, 0))
            image.putpixel((0, 0), (255, 255, 255, 128))
            image.save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=True)
            self.assertTrue(analysis["alpha_channel_present"])
            self.assertTrue(analysis["meaningful_transparency_present"])
            self.assertFalse(analysis["fully_opaque"])
            self.assertFalse(analysis["background_removal_required"])

    def test_inspect_generated_image_reports_small_transparent_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "small_transparent.png"
            Image.new("RGBA", (300, 300), (255, 255, 255, 0)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=True)
            self.assertTrue(analysis["production_canvas_required"])
            self.assertFalse(analysis["background_removal_required"])

    def test_inspect_generated_image_reports_target_size_transparent_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "target_transparent.png"
            Image.new("RGBA", (4500, 5400), (255, 255, 255, 0)).save(path)
            analysis = image_postprocessor.inspect_generated_image(path, transparency_required=True)
            self.assertFalse(analysis["production_canvas_required"])
            self.assertFalse(analysis["background_removal_required"])
            self.assertFalse(analysis["final_print_ready"])

    def test_inspect_generated_image_reports_missing_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            analysis = image_postprocessor.inspect_generated_image(Path(tmp) / "missing.png")
            self.assertFalse(analysis["exists"])
            self.assertEqual(analysis["provider_status"], "not_ready")
            self.assertEqual(analysis["printify_status"], "not_ready")

    def test_analyze_output_image_for_job_handles_job_without_output_image(self) -> None:
        job = job_queue.create_job("image_generation", {"image_plan": {"prompt": "x"}})
        result = image_worker.analyze_output_image_for_job(job["job_id"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["provider_status"], "not_ready")
        self.assertFalse(result["final_print_ready"])

    def test_cannot_execute_unapproved_job(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            with self.assertRaises(job_queue.JobQueueError):
                image_worker.execute_approved_image_job(job["job_id"])

        self.run_with_worker(scenario)

    def test_cannot_execute_non_local_comfyui_url(self) -> None:
        with self.assertRaises(ValueError):
            comfyui_client.queue_prompt({}, api_url="https://example.com:8188")

    def test_cannot_execute_without_workflow_or_model(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job(
                "image_generation",
                {"image_plan": {"selected_workflow": {"workflow_path": str(root / "missing.json")}, "prompt": "x"}},
            )
            job_queue.approve_job(job["job_id"])
            with patch.object(image_worker.comfyui_client, "is_running", return_value=True):
                with self.assertRaises(job_queue.JobQueueError):
                    image_worker.execute_approved_image_job(job["job_id"])

        self.run_with_worker(scenario)

    def test_approved_job_creates_local_output_path_with_mocked_comfyui(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job(
                "image_generation",
                {"image_plan": self.image_plan(workflow, checkpoint)},
                steps=["validation", "workflow prepared", "ComfyUI prompt queued", "image saved", "completed"],
            )
            job_queue.approve_job(job["job_id"])
            with (
                patch.object(image_worker.comfyui_client, "is_running", return_value=True),
                patch.object(image_worker.comfyui_client, "queue_prompt", return_value={"status": "queued", "prompt_id": "abc"}),
                patch.object(image_worker.comfyui_client, "wait_for_completion", return_value={"status": "completed", "prompt_id": "abc"}),
                patch.object(image_worker.comfyui_client, "get_output_images", return_value=[{"filename": "out.png", "content": b"png"}]),
            ):
                result = image_worker.execute_approved_image_job(job["job_id"])

            self.assertEqual(result["status"], "ok")
            image_path = Path(result["image_path"])
            self.assertTrue(image_path.exists())
            self.assertEqual(image_path.read_bytes(), b"png")
            self.assertTrue((image_path.parent / "prepared_workflow.json").exists())
            processed = job_queue.get_job(job["job_id"])
            self.assertEqual(processed["status"], "processed")
            self.assertEqual(processed["payload"]["image_status"], "generated_concept")
            self.assertEqual(processed["payload"]["design_status"], "needs_design_review")
            self.assertEqual(processed["payload"]["provider_status"], "not_ready")
            self.assertEqual(processed["payload"]["printify_status"], "not_ready")
            self.assertIn("output_image_paths", processed["payload"])
            artifact = processed["payload"]["design_artifact"]
            self.assertEqual(artifact["source_image_path"], result["image_path"])
            self.assertEqual(artifact["quality_stage"], "production_candidate")
            self.assertFalse(artifact["manual_upload_ready"])
            self.assertTrue(processed["payload"]["generated_at"])
            self.assertFalse(result["printify_execution_enabled"])
            self.assertFalse(result["etsy_execution_enabled"])
            self.assertEqual(result["workflow_path"], str(root / "WorkflowTemplates" / "print_design_basic.api.json"))
            self.assertIn("print_readiness_analysis", processed["payload"])

    def test_prepare_transparent_artifact_creates_derivative_without_touching_source(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job(
                "image_generation",
                {"image_plan": self.image_plan(workflow, checkpoint), "design_artifact": {"transparent_background_required": True}},
            )
            source_path = root / "source.png"
            image = Image.new("RGBA", (256, 256), (255, 255, 255, 255))
            image.putpixel((0, 0), (255, 255, 255, 255))
            image.putpixel((120, 120), (10, 20, 30, 255))
            image.putpixel((20, 20), (255, 255, 255, 255))
            image.save(source_path)
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path), "output_image_paths": [str(source_path)]})

            source_bytes_before = source_path.read_bytes()

            with self.assertRaises(job_queue.JobQueueError):
                image_finisher.prepare_transparent_artifact_for_job(job["job_id"])
            self.assertEqual(job_queue.get_job(job["job_id"])["payload"].get("concept_approved"), None)

            image_finisher.approve_concept_for_job(job["job_id"], approved_by="tester")
            self.assertFalse(job_queue.get_job(job["job_id"])["approved"])
            result = image_finisher.prepare_transparent_artifact_for_job(job["job_id"])

            self.assertEqual(result["status"], "ok")
            artifact_path = Path(result["artifact_path"])
            self.assertTrue(artifact_path.exists())
            self.assertEqual(artifact_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")
            self.assertEqual(artifact_path.parent, image_worker._job_output_folder(job["job_id"]))
            self.assertEqual(source_path.read_bytes(), source_bytes_before)
            with Image.open(artifact_path) as artifact:
                self.assertEqual(artifact.size, image.size)
                self.assertEqual(artifact.getpixel((0, 0))[3], 0)
                self.assertEqual(artifact.getpixel((120, 120)), (10, 20, 30, 255))
            processed = job_queue.get_job(job["job_id"])
            payload = processed["payload"]
            self.assertTrue(payload["concept_approved"])
            self.assertEqual(payload["design_artifact"]["transparent_artifact_path"], str(artifact_path))
            self.assertEqual(payload["design_artifact"]["source_image_path"], str(source_path))
            self.assertEqual(payload["image_status"], "generated_concept")
            self.assertEqual(payload["transparent_artifact_status"], "transparent_derivative")
            self.assertEqual(payload["design_artifact"]["transparent_artifact_status"], "transparent_derivative")
            self.assertNotIn("final_image_path", payload["design_artifact"])
            self.assertEqual(payload["design_status"], "needs_design_review")
            self.assertFalse(payload["final_print_ready"])
            self.assertEqual(payload["provider_status"], "not_ready")
            self.assertEqual(payload["printify_status"], "not_ready")

        self.run_with_worker(scenario)

    def test_transparent_finishing_preserves_enclosed_white_detail(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            source_path = root / "enclosed-white.png"
            image = Image.new("RGBA", (9, 9), (255, 255, 255, 255))
            for y in range(2, 7):
                for x in range(2, 7):
                    image.putpixel((x, y), (20, 30, 40, 255))
            image.putpixel((4, 4), (255, 255, 255, 255))
            image.save(source_path)
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path)})
            image_finisher.approve_concept_for_job(job["job_id"])

            result = image_finisher.prepare_transparent_artifact_for_job(job["job_id"])

            with Image.open(result["artifact_path"]) as artifact:
                self.assertEqual(artifact.getpixel((0, 0))[3], 0)
                self.assertEqual(artifact.getpixel((4, 4)), (255, 255, 255, 255))

        self.run_with_worker(scenario)

    def test_transparent_finishing_refuses_opaque_result_without_persisting_success(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            source_path = root / "opaque.png"
            Image.new("RGB", (8, 8), (10, 20, 30)).save(source_path)
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path)})
            image_finisher.approve_concept_for_job(job["job_id"])
            artifact_path = image_worker._job_output_folder(job["job_id"]) / "transparent_artifact.png"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(b"stale derivative")
            image_worker.update_job_payload(job["job_id"], {
                "transparent_artifact_path": str(artifact_path),
                "transparent_artifact_status": "transparent_derivative",
                "finishing_metadata": {"status": "stale success"},
                "design_artifact": {
                    "transparent_artifact_status": "transparent_derivative",
                    "output_status": "transparent_derivative_ready",
                    "final_image_path": str(artifact_path),
                },
            })

            with self.assertRaises(job_queue.JobQueueError):
                image_finisher.prepare_transparent_artifact_for_job(job["job_id"])

            payload = job_queue.get_job(job["job_id"])["payload"]
            self.assertNotIn("transparent_artifact_path", payload)
            self.assertNotIn("transparent_artifact_status", payload)
            self.assertNotIn("finishing_metadata", payload)
            self.assertNotIn("transparent_artifact_status", payload["design_artifact"])
            self.assertNotIn("final_image_path", payload["design_artifact"])
            self.assertNotIn("output_status", payload["design_artifact"])
            self.assertFalse(artifact_path.exists())

        self.run_with_worker(scenario)

    def test_concept_approval_records_approver_and_timestamp(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})

            result = image_finisher.approve_concept_for_job(job["job_id"], approved_by="phase2-reviewer")

            payload = job_queue.get_job(job["job_id"])["payload"]
            self.assertTrue(payload["concept_approved"])
            self.assertEqual(payload["concept_approved_by"], "phase2-reviewer")
            self.assertTrue(payload["concept_approved_at"])
            self.assertEqual(result["approved_by"], "phase2-reviewer")
            self.assertEqual(result["approved_at"], payload["concept_approved_at"])

        self.run_with_worker(scenario)

    def test_transparent_finishing_preserves_colored_artwork_touching_edge(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            source_path = root / "edge-art.png"
            image = Image.new("RGB", (8, 8), (255, 255, 255))
            image.putpixel((0, 3), (220, 20, 30))
            image.putpixel((1, 3), (220, 20, 30))
            image.save(source_path)
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path)})
            image_finisher.approve_concept_for_job(job["job_id"])

            result = image_finisher.prepare_transparent_artifact_for_job(job["job_id"])

            with Image.open(result["artifact_path"]) as artifact:
                self.assertEqual(artifact.getpixel((0, 3)), (220, 20, 30, 255))
                self.assertEqual(artifact.getpixel((0, 0))[3], 0)

        self.run_with_worker(scenario)

    def test_already_transparent_interior_does_not_seed_unrelated_white_removal(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            source_path = root / "already-transparent.png"
            image = Image.new("RGBA", (7, 7), (20, 30, 40, 255))
            image.putpixel((3, 3), (20, 30, 40, 0))
            image.putpixel((3, 2), (255, 255, 255, 255))
            image.save(source_path)
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path)})
            image_finisher.approve_concept_for_job(job["job_id"])

            result = image_finisher.prepare_transparent_artifact_for_job(job["job_id"])

            with Image.open(result["artifact_path"]) as artifact:
                self.assertEqual(artifact.getpixel((3, 3))[3], 0)
                self.assertEqual(artifact.getpixel((3, 2)), (255, 255, 255, 255))
            self.assertEqual(result["finishing_metadata"]["removed_background_pixel_count"], 0)

        self.run_with_worker(scenario)

    def test_finishing_validates_threshold_and_neutral_tolerance(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            image_finisher.approve_concept_for_job(job["job_id"])
            with self.assertRaises(job_queue.JobQueueError):
                image_finisher.prepare_transparent_artifact_for_job(job["job_id"], white_threshold=256)
            with self.assertRaises(job_queue.JobQueueError):
                image_finisher.prepare_transparent_artifact_for_job(job["job_id"], neutral_tolerance=-1)

        self.run_with_worker(scenario)

    def test_configurable_white_threshold_changes_candidate_behavior(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            source_path = root / "threshold.png"
            Image.new("RGB", (8, 8), (230, 230, 230)).save(source_path)
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path)})
            image_finisher.approve_concept_for_job(job["job_id"])

            with self.assertRaises(job_queue.JobQueueError):
                image_finisher.prepare_transparent_artifact_for_job(job["job_id"], white_threshold=240)
            result = image_finisher.prepare_transparent_artifact_for_job(job["job_id"], white_threshold=220)

            self.assertEqual(result["finishing_metadata"]["white_threshold"], 220)
            self.assertEqual(result["finishing_metadata"]["removed_background_pixel_count"], 64)

        self.run_with_worker(scenario)

    def test_finishing_metadata_contains_hashes_pixel_counts_and_required_fields(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            source_path = root / "metadata.png"
            image = Image.new("RGB", (6, 5), (255, 255, 255))
            image.putpixel((3, 2), (10, 20, 30))
            image.save(source_path)
            source_bytes = source_path.read_bytes()
            image_worker.update_job_payload(job["job_id"], {"output_image_path": str(source_path)})
            image_finisher.approve_concept_for_job(job["job_id"])

            result = image_finisher.prepare_transparent_artifact_for_job(job["job_id"], neutral_tolerance=8)

            metadata = result["finishing_metadata"]
            required = {
                "source_image_path", "derived_image_path", "source_unchanged", "source_sha256_before",
                "source_sha256_after", "width", "height", "output_mode", "alpha_channel_present",
                "meaningful_transparency_present", "transparent_pixel_count", "opaque_pixel_count",
                "removed_background_pixel_count", "processing_method", "white_threshold",
                "neutral_tolerance", "visual_review_required", "final_print_ready",
            }
            self.assertTrue(required.issubset(metadata))
            self.assertEqual(metadata["source_sha256_before"], metadata["source_sha256_after"])
            self.assertEqual(metadata["transparent_pixel_count"] + metadata["opaque_pixel_count"], 30)
            self.assertTrue(metadata["source_unchanged"])
            self.assertEqual(source_path.read_bytes(), source_bytes)
            self.assertEqual(job_queue.get_job(job["job_id"])["payload"]["finishing_metadata"], metadata)

        self.run_with_worker(scenario)

    def test_unitystitches_draft_updated_to_ready_for_pod_review(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            draft_path = root / "draft.json"
            draft_path.write_text(json.dumps({"status": "needs_review", "pod_provider": "printify"}), encoding="utf-8")
            job = job_queue.create_job(
                "image_generation",
                {"image_plan": self.image_plan(workflow, checkpoint), "unitystitches_draft_path": str(draft_path)},
                steps=["validation", "workflow prepared", "ComfyUI prompt queued", "image saved", "completed"],
            )
            job_queue.approve_job(job["job_id"])
            with (
                patch.object(image_worker.comfyui_client, "is_running", return_value=True),
                patch.object(image_worker.comfyui_client, "queue_prompt", return_value={"status": "queued", "prompt_id": "abc"}),
                patch.object(image_worker.comfyui_client, "wait_for_completion", return_value={"status": "completed", "prompt_id": "abc"}),
                patch.object(image_worker.comfyui_client, "get_output_images", return_value=[{"filename": "out.png", "content": b"png"}]),
            ):
                image_worker.execute_approved_image_job(job["job_id"])

            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            self.assertEqual(draft["design_status"], "image_generated")
            self.assertEqual(draft["provider_status"], "manual_upload_ready")
            self.assertEqual(draft["printify_status"], "ready_for_printify_review")
            self.assertEqual(draft["status"], "ready_for_pod_review")
            self.assertTrue(draft["design_image_path"])

        self.run_with_worker(scenario)

    def test_non_printify_draft_does_not_claim_printify_review(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            draft_path = root / "draft.json"
            draft_path.write_text(json.dumps({"status": "needs_review", "pod_provider": "inkedjoy"}), encoding="utf-8")
            job = job_queue.create_job(
                "image_generation",
                {"image_plan": self.image_plan(workflow, checkpoint), "unitystitches_draft_path": str(draft_path)},
                steps=["validation", "workflow prepared", "ComfyUI prompt queued", "image saved", "completed"],
            )
            job_queue.approve_job(job["job_id"])
            with (
                patch.object(image_worker.comfyui_client, "is_running", return_value=True),
                patch.object(image_worker.comfyui_client, "queue_prompt", return_value={"status": "queued", "prompt_id": "abc"}),
                patch.object(image_worker.comfyui_client, "wait_for_completion", return_value={"status": "completed", "prompt_id": "abc"}),
                patch.object(image_worker.comfyui_client, "get_output_images", return_value=[{"filename": "out.png", "content": b"png"}]),
            ):
                image_worker.execute_approved_image_job(job["job_id"])

            draft = json.loads(draft_path.read_text(encoding="utf-8"))
            self.assertEqual(draft["provider_status"], "manual_upload_ready")
            self.assertEqual(draft["printify_status"], "not_applicable")
            self.assertEqual(draft["status"], "ready_for_pod_review")

        self.run_with_worker(scenario)

    def test_no_shop_or_upload_publish_send_behavior_exists(self) -> None:
        source = Path("jamesos/services/image_worker.py").read_text(encoding="utf-8")
        self.assertNotIn("printify.", source.lower())
        self.assertNotIn("etsy.", source.lower())
        self.assertNotIn("upload(", source.lower())
        self.assertNotIn("publish(", source.lower())
        self.assertNotIn("send(", source.lower())

    def test_create_test_image_job_requires_approval_and_does_not_execute(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            workflow_inventory = root / "workflow_inventory.json"
            workflow_inventory.write_text(
                json.dumps({
                    "status": "ok",
                    "workflows": [
                        {
                            "name": "product_art_basic",
                            "path": str(workflow),
                            "workflow_path": str(workflow),
                            "type": "product_art",
                            "compatible_models": ["sdxl_base"],
                            "enabled": False,
                            "execution_enabled": False,
                        }
                    ],
                    "summary": {"total": 1, "by_type": {"product_art": 1}},
                    "execution_enabled": False,
                }),
                encoding="utf-8",
            )
            with patch.object(image_worker.workflow_manager, "WORKFLOW_INVENTORY_PATH", workflow_inventory):
                result = image_worker.create_test_image_job()

            job = job_queue.get_job(result["job"]["job_id"])
            self.assertTrue(job["requires_approval"])
            self.assertFalse(job["approved"])
            self.assertEqual(job["status"], "pending")
            payload = job["payload"]
            self.assertIn("creative_spec", payload)
            self.assertIn("prompt_package", payload)
            self.assertIn("design_recipe", payload["creative_spec"])
            self.assertEqual(payload["pod_provider"], "printify")
            self.assertIn("selected_assets", payload)
            self.assertEqual(payload["brand_id"], "unitystitches")
            self.assertIn(payload["workflow_name"], {"product_art_basic", "print_design_basic", "transparent_print_design_basic"})
            self.assertEqual(payload["creative_spec"]["product_type"], "design_art")
            self.assertEqual(payload["creative_spec"]["layout"], "flat centered print artwork")
            self.assertIn("standalone print design", payload["positive_prompt"])
            self.assertIn("mockup", payload["negative_prompt"])
            self.assertIn("workflow_path", payload)
            self.assertIn("checkpoint_path", payload)
            self.assertIn("positive_prompt", payload)
            self.assertEqual(payload["requested_workflow_type"], "transparent_print_design_basic")
            self.assertIn("design_artifact", payload)
            artifact = payload["design_artifact"]
            self.assertEqual(artifact["artifact_type"], "print_ready_png")
            self.assertEqual(artifact["background"], "transparent")
            self.assertEqual(artifact["target_width"], 4500)
            self.assertEqual(artifact["target_height"], 5400)
            self.assertEqual(artifact["source_generation_width"], 1024)
            self.assertEqual(artifact["source_generation_height"], 1024)
            self.assertTrue(artifact["upscale_required"])
            self.assertTrue(artifact["transparent_background_required"])
            self.assertFalse(artifact["manual_upload_ready"])
            self.assertEqual(artifact["provider_target"], "printify")
            self.assertEqual(artifact["quality_stage"], "production_candidate")
            self.assertTrue(artifact["background_removal_required"])
            self.assertIn("asset_prompt_descriptions", payload["image_plan"])
            self.assertFalse(payload["execution_enabled"])
            self.assertFalse(payload["auto_execute"])

        self.run_with_worker(scenario)

    def test_workflow_validation_returns_structured_errors(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            bad_workflow = root / "ui_workflow.json"
            bad_workflow.write_text(json.dumps({"last_node_id": 1, "nodes": []}), encoding="utf-8")
            plan = self.image_plan(bad_workflow, checkpoint)

            with self.assertRaises(image_worker.ImageWorkerError) as raised:
                with patch.object(image_worker.workflow_manager, "get_executable_workflow_template", return_value={
                    "name": "ui_workflow",
                    "path": str(bad_workflow),
                    "workflow_path": str(bad_workflow),
                    "type": "print_design_basic",
                    "workflow_format": "comfyui_ui_workflow",
                    "api_prompt_valid": False,
                }):
                    image_worker.prepare_workflow_from_plan(plan)

            error = image_worker.structured_error(raised.exception)
            self.assertEqual(error["status"], "error")
            self.assertEqual(error["error_code"], "workflow_is_comfyui_ui_format_export_api_needed")
            self.assertIn("next_step", error)
            self.assertEqual(error["workflow_path"], str(bad_workflow))
            self.assertFalse(error["printify_execution_enabled"])

        self.run_with_worker(scenario)

    def test_image_worker_selects_managed_api_template_over_job_workflow_path(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            stale_ui = root / "old_open_ui_workflow.json"
            stale_ui.write_text(json.dumps({"last_node_id": 1, "nodes": []}), encoding="utf-8")
            plan = self.image_plan(stale_ui, checkpoint)

            prepared = image_worker.prepare_workflow_from_plan(plan)

            self.assertEqual(prepared["source_path"], str(root / "WorkflowTemplates" / "print_design_basic.api.json"))
            self.assertEqual(prepared["workflow"]["1"]["inputs"]["ckpt_name"], "sdxl.safetensors")

        self.run_with_worker(scenario)

    def test_unreplaced_placeholder_fails_before_queueing(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            template = root / "broken.api.json"
            template.write_text(
                json.dumps({
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{checkpoint_name}}"}},
                    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{unknown_placeholder}}"}},
                    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{negative_prompt}}"}},
                    "4": {"class_type": "EmptyLatentImage", "inputs": {"width": "{{width}}", "height": "{{height}}", "batch_size": 1}},
                    "5": {"class_type": "KSampler", "inputs": {"seed": "{{seed}}"}},
                    "6": {"class_type": "VAEDecode", "inputs": {}},
                    "7": {"class_type": "SaveImage", "inputs": {"filename_prefix": "{{filename_prefix}}"}},
                }),
                encoding="utf-8",
            )
            with patch.object(image_worker.workflow_manager, "get_executable_workflow_template", return_value={
                "name": "broken",
                "path": str(template),
                "workflow_path": str(template),
                "type": "print_design_basic",
                "workflow_format": "comfyui_api_prompt",
                "api_prompt_valid": True,
            }):
                with self.assertRaises(image_worker.ImageWorkerError) as raised:
                    image_worker.prepare_workflow_from_plan(self.image_plan(template, checkpoint))

            self.assertEqual(raised.exception.error_code, "workflow_placeholder_not_replaced")

        self.run_with_worker(scenario)

    def test_missing_required_node_fails_before_queueing(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            template = root / "missing_node.api.json"
            template.write_text(
                json.dumps({
                    "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "{{checkpoint_name}}"}},
                    "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "{{positive_prompt}}"}},
                }),
                encoding="utf-8",
            )
            with patch.object(image_worker.workflow_manager, "get_executable_workflow_template", return_value={
                "name": "missing_node",
                "path": str(template),
                "workflow_path": str(template),
                "type": "print_design_basic",
                "workflow_format": "comfyui_api_prompt",
                "api_prompt_valid": True,
            }):
                with self.assertRaises(image_worker.ImageWorkerError) as raised:
                    image_worker.prepare_workflow_from_plan(self.image_plan(template, checkpoint))

            self.assertEqual(raised.exception.error_code, "workflow_missing_required_nodes")

        self.run_with_worker(scenario)

    def test_invalid_node_reference_fails_before_queueing_with_node_field(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            template = root / "bad_reference.api.json"
            data = workflow_manager._default_print_design_template()
            data["2"]["inputs"]["clip"] = ["99", 0]
            template.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(image_worker.workflow_manager, "get_executable_workflow_template", return_value={
                "name": "bad_reference",
                "path": str(template),
                "workflow_path": str(template),
                "type": "print_design_basic",
                "workflow_format": "comfyui_api_prompt",
                "api_prompt_valid": True,
            }):
                with self.assertRaises(image_worker.ImageWorkerError) as raised:
                    image_worker.prepare_workflow_from_plan(self.image_plan(template, checkpoint))

            self.assertEqual(raised.exception.error_code, "workflow_invalid_api_prompt_structure")
            self.assertEqual(raised.exception.validation_issues[0]["node_id"], "2")
            self.assertEqual(raised.exception.validation_issues[0]["field"], "inputs.clip")

        self.run_with_worker(scenario)

    def test_numeric_node_reference_is_normalized_before_queueing(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            template = root / "numeric_reference.api.json"
            data = workflow_manager._default_print_design_template()
            data["7"]["inputs"]["images"] = [6, 0]
            template.write_text(json.dumps(data), encoding="utf-8")
            with patch.object(image_worker.workflow_manager, "get_executable_workflow_template", return_value={
                "name": "numeric_reference",
                "path": str(template),
                "workflow_path": str(template),
                "type": "print_design_basic",
                "workflow_format": "comfyui_api_prompt",
                "api_prompt_valid": True,
            }):
                prepared = image_worker.prepare_workflow_from_plan(self.image_plan(template, checkpoint))

            self.assertEqual(prepared["workflow"]["7"]["inputs"]["images"], ["6", 0])
            self.assertEqual(prepared["workflow"]["4"]["inputs"]["width"], 512)
            self.assertEqual(prepared["workflow"]["5"]["inputs"]["steps"], 28)
            self.assertEqual(prepared["workflow"]["5"]["inputs"]["cfg"], 7.0)
            self.assertTrue(workflow_manager.validate_comfyui_api_prompt_structure(prepared["workflow"])["valid"])

        self.run_with_worker(scenario)

    def test_comfyui_non_200_response_body_is_saved_and_structured(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job(
                "image_generation",
                {"image_plan": self.image_plan(workflow, checkpoint)},
                steps=["validation", "workflow prepared", "ComfyUI prompt queued", "image saved", "completed"],
            )
            job_queue.approve_job(job["job_id"])
            response_json = {
                "error": {"type": "invalid_prompt", "message": "Bad input"},
                "node_errors": {"5": {"inputs": {"sampler_name": "unknown sampler"}}},
            }
            exc = image_worker.comfyui_client.ComfyUIHTTPError(
                "ComfyUI prompt queue failed with HTTP 400",
                400,
                json.dumps(response_json),
                response_json,
            )
            with (
                patch.object(image_worker.comfyui_client, "is_running", return_value=True),
                patch.object(image_worker.comfyui_client, "queue_prompt", side_effect=exc),
            ):
                with self.assertRaises(image_worker.ImageWorkerError) as raised:
                    image_worker.execute_approved_image_job(job["job_id"])

            error = image_worker.structured_error(raised.exception, job_id=job["job_id"])
            self.assertIn("node 5", error["message"])
            self.assertIn("sampler_name", error["message"])
            self.assertIn("invalid_prompt", error["response_body"])
            saved = image_worker.comfy_response_for_job(job["job_id"])
            self.assertEqual(saved["comfy_response"]["status_code"], 400)
            self.assertEqual(saved["comfy_response"]["response_json"]["node_errors"]["5"]["inputs"]["sampler_name"], "unknown sampler")
            prepared = image_worker.prepared_workflow_for_job(job["job_id"])
            self.assertIn("prepared_workflow", prepared)

        self.run_with_worker(scenario)

    def test_provider_writes_remain_false_for_all_providers(self) -> None:
        providers = pod_provider_registry.list_providers()["providers"]
        self.assertTrue(providers)
        for provider in providers:
            self.assertFalse(provider["writes_enabled"])
            self.assertFalse(provider["draft_creation_enabled"])
            self.assertFalse(provider["order_enabled"])

    def test_asset_filenames_translate_to_prompt_descriptions(self) -> None:
        assets = [
            {"name": "Gay_Pride_Flag", "extension": ".svg"},
            {"name": "Transgender_Pride_flag", "extension": ".svg"},
            {"name": "Intersex-inclusive_pride_flag", "extension": ".svg"},
            {"name": "unitystitches_logo", "extension": ".png"},
        ]
        package = prompt_library.creative_spec_to_prompt_package({
            "stage": "design_art",
            "product_type": "design_art",
            "layout": "transparent centered print design",
            "selected_assets": assets,
            "design_recipe": {
                "product_type": "design_art",
                "niche": "LGBTQ+ pride",
                "artwork_type": "transparent print design",
                "assets": assets,
                "text": "Love Is Love",
            },
        })

        prompt = package["positive_prompt"]
        self.assertIn("six-stripe rainbow pride flag colors", prompt)
        self.assertIn("pastel blue, pink, and white trans pride colors", prompt)
        self.assertIn("inclusive pride flag color palette", prompt)
        self.assertNotIn("Gay_Pride_Flag", prompt)
        self.assertNotIn("Transgender_Pride_flag", prompt)
        self.assertNotIn("Intersex-inclusive_pride_flag", prompt)
        self.assertEqual(package["recommended_workflow_type"], "transparent_print_design_basic")

    def test_negative_prompt_strongly_rejects_people_products_and_mockups(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            result = image_worker.create_test_image_job()
            negative = job_queue.get_job(result["job"]["job_id"])["payload"]["negative_prompt"]

            for term in ["person", "people", "human", "model", "woman", "man", "child", "face", "hands", "body", "wearing", "shirt", "pants", "underwear", "product photo", "lifestyle photo", "room", "bed", "couch", "shelf", "mannequin", "mockup", "realistic person", "photorealistic person", "portrait", "background scene", "blurry text", "misspelled text", "watermark"]:
                self.assertIn(term, negative)

        self.run_with_worker(scenario)

    def test_execute_approved_route_exists(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise
        paths = {route.path for route in api.app.routes}
        self.assertIn("/image-worker/jobs/{job_id}/execute-approved", paths)
        self.assertIn("/image-worker/jobs/{job_id}/approve-concept", paths)
        self.assertIn("/image-worker/jobs/{job_id}/prepare-transparent-artifact", paths)
        self.assertIn("/image-worker/jobs/{job_id}/validate-upscale-model", paths)
        self.assertIn("/image-worker/upscale-models", paths)
        self.assertIn("/image-worker/jobs/{job_id}/prepared-workflow", paths)
        self.assertIn("/image-worker/jobs/{job_id}/comfy-response", paths)
        health = image_worker.health()
        self.assertIn("POST /image-worker/jobs/{job_id}/execute-approved", health["routes"])
        self.assertIn("POST /image-worker/jobs/{job_id}/approve-concept", health["routes"])
        self.assertIn("POST /image-worker/jobs/{job_id}/prepare-transparent-artifact", health["routes"])
        self.assertIn("POST /image-worker/jobs/{job_id}/validate-upscale-model", health["routes"])
        self.assertIn("GET /image-worker/upscale-models", health["routes"])
        self.assertIn("GET /image-worker/jobs/{job_id}/prepared-workflow", health["routes"])
        self.assertIn("GET /image-worker/jobs/{job_id}/comfy-response", health["routes"])

    def test_approve_concept_api_route_accepts_approver_and_defaults_safely(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise

        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            named_job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            default_job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            with patch.object(api, "require_key", return_value=None):
                named = api.image_worker_approve_concept_route(
                    named_job["job_id"], api.ConceptApprovalRequest(approved_by="api-reviewer"), None
                )
                defaulted = api.image_worker_approve_concept_route(default_job["job_id"], None, None)

            self.assertEqual(named["approved_by"], "api-reviewer")
            self.assertEqual(defaulted["approved_by"], "api_user")
            self.assertEqual(job_queue.get_job(default_job["job_id"])["payload"]["concept_approved_by"], "api_user")

        self.run_with_worker(scenario)

    def test_prepare_transparent_artifact_api_refuses_without_concept_approval(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise

        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            job = job_queue.create_job("image_generation", {"image_plan": self.image_plan(workflow, checkpoint)})
            with patch.object(api, "require_key", return_value=None):
                result = api.image_worker_prepare_transparent_artifact_route(job["job_id"], None)

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["job_id"], job["job_id"])
            self.assertFalse((image_worker._job_output_folder(job["job_id"]) / "transparent_artifact.png").exists())

        self.run_with_worker(scenario)

    def test_create_test_image_job_script_adds_project_root_to_syspath(self) -> None:
        source = Path("scripts/create_test_image_job.py").read_text(encoding="utf-8")
        self.assertIn("sys.path.insert", source)
        self.assertIn("next_commands", source)
        self.assertIn("selected_provider", source)
        self.assertIn("selected_assets", source)
        self.assertIn("open_output_folder", source)
        self.assertIn("ComfyUI open workflow is ignored.", source)
        self.assertIn("workflow_template_used", source)
        self.assertIn("--quality", source)
        self.assertIn("--transparent", source)
        self.assertIn("--provider", source)
        self.assertIn("production_candidate", source)
        self.assertIn("background_removal_required", source)

    def test_validate_workflow_script_exists(self) -> None:
        source = Path("scripts/validate_workflow.py").read_text(encoding="utf-8")
        self.assertIn("validate_comfyui_api_prompt_structure", source)
        self.assertIn("without contacting ComfyUI", source)


if __name__ == "__main__":
    unittest.main()
