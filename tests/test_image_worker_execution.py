from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import comfyui_client, image_worker, job_queue, model_registry


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
            processed = job_queue.get_job(job["job_id"])
            self.assertEqual(processed["status"], "processed")
            self.assertFalse(result["printify_execution_enabled"])
            self.assertFalse(result["etsy_execution_enabled"])

        self.run_with_worker(scenario)

    def test_unitystitches_draft_updated_to_image_ready_needs_review(self) -> None:
        def scenario(root: Path, workflow: Path, checkpoint: Path) -> None:
            draft_path = root / "draft.json"
            draft_path.write_text(json.dumps({"status": "needs_review"}), encoding="utf-8")
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
            self.assertEqual(draft["printify_status"], "ready_for_printify_review")
            self.assertEqual(draft["status"], "image_ready_needs_review")
            self.assertTrue(draft["design_image_path"])

        self.run_with_worker(scenario)

    def test_no_shop_or_upload_publish_send_behavior_exists(self) -> None:
        source = Path("jamesos/services/image_worker.py").read_text(encoding="utf-8")
        self.assertNotIn("printify.", source.lower())
        self.assertNotIn("etsy.", source.lower())
        self.assertNotIn("upload(", source.lower())
        self.assertNotIn("publish(", source.lower())
        self.assertNotIn("send(", source.lower())


if __name__ == "__main__":
    unittest.main()
