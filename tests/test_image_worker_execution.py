from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamesos.services import comfyui_client, image_worker, job_queue, model_registry, pod_provider_registry, workflow_manager


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
            self.assertEqual(processed["payload"]["image_status"], "generated")
            self.assertIn("output_image_paths", processed["payload"])
            self.assertTrue(processed["payload"]["generated_at"])
            self.assertFalse(result["printify_execution_enabled"])
            self.assertFalse(result["etsy_execution_enabled"])
            self.assertEqual(result["workflow_path"], str(root / "WorkflowTemplates" / "print_design_basic.api.json"))

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
            self.assertIn(payload["workflow_name"], {"product_art_basic", "print_design_basic"})
            self.assertEqual(payload["creative_spec"]["product_type"], "design_art")
            self.assertEqual(payload["creative_spec"]["layout"], "flat centered print artwork")
            self.assertIn("standalone print design", payload["positive_prompt"])
            self.assertIn("mockup", payload["negative_prompt"])
            self.assertIn("workflow_path", payload)
            self.assertIn("checkpoint_path", payload)
            self.assertIn("positive_prompt", payload)
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

    def test_provider_writes_remain_false_for_all_providers(self) -> None:
        providers = pod_provider_registry.list_providers()["providers"]
        self.assertTrue(providers)
        for provider in providers:
            self.assertFalse(provider["writes_enabled"])
            self.assertFalse(provider["draft_creation_enabled"])
            self.assertFalse(provider["order_enabled"])

    def test_execute_approved_route_exists(self) -> None:
        try:
            from jamesos.core import api
        except ModuleNotFoundError as exc:
            if exc.name in {"fastapi", "pydantic"}:
                self.skipTest("fastapi/pydantic are not installed in this Python environment")
            raise
        paths = {route.path for route in api.app.routes}
        self.assertIn("/image-worker/jobs/{job_id}/execute-approved", paths)
        health = image_worker.health()
        self.assertIn("POST /image-worker/jobs/{job_id}/execute-approved", health["routes"])

    def test_create_test_image_job_script_adds_project_root_to_syspath(self) -> None:
        source = Path("scripts/create_test_image_job.py").read_text(encoding="utf-8")
        self.assertIn("sys.path.insert", source)
        self.assertIn("next_commands", source)
        self.assertIn("selected_provider", source)
        self.assertIn("selected_assets", source)
        self.assertIn("open_output_folder", source)
        self.assertIn("ComfyUI open workflow is ignored.", source)
        self.assertIn("workflow_template_used", source)


if __name__ == "__main__":
    unittest.main()
