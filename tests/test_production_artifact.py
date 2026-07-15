from __future__ import annotations

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import yaml

from jamesos.services import job_queue, production_artifact, upscale_model_registry


def png_bytes(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class ProductionArtifactTests(unittest.TestCase):
    MODEL = "Approved_x2.pth"

    def sandbox(self, callback, *, validated: bool = True) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            queue_root = root / "Queue"
            generated = root / "Generated" / "2026-07-15" / "job"
            generated.mkdir(parents=True)
            original = generated / "original.png"
            Image.new("RGB", (2, 2), (20, 30, 40)).save(original)
            derivative = generated / "transparent_artifact.png"
            image = Image.new("RGBA", (2, 2), (200, 30, 50, 0))
            image.putpixel((0, 0), (30, 100, 180, 255))
            image.save(derivative)
            comfy = root / "ComfyUI"
            model_folder = comfy / "models" / "upscale_models"
            model_folder.mkdir(parents=True)
            model_content = b"approved model"
            (model_folder / self.MODEL).write_bytes(model_content)
            registry = root / "models.yaml"
            registry.write_text(yaml.safe_dump({"models": {self.MODEL: {
                "model_name": self.MODEL, "scale_factor": 2, "model_family": "test",
                "intended_use": "production test", "enabled": True, "validated": validated, "default": True,
                "validated_model_sha256": sha256(model_content).hexdigest() if validated else "",
                "preferred_alpha_resize_method": "lanczos", "preferred_edge_bleed_iterations": 2,
                "preferred_edge_bleed_alpha_threshold": 128, "validation_output_filename": "test.png",
            }}}), encoding="utf-8")
            target = root / "target.yaml"
            target.write_text(yaml.safe_dump({"production_target": {
                "canvas_width": 10, "canvas_height": 12, "safe_margin_percent": 10,
                "horizontal_alignment": "center", "vertical_alignment": "center", "output_mode": "RGBA",
                "transparent_background": True, "target_authority": "jamesos_default_not_provider_verified",
                "placement_resize_method": "lanczos",
            }}), encoding="utf-8")
            patches = [
                patch.object(job_queue, "QUEUE_ROOT", queue_root),
                patch.object(job_queue, "PENDING", queue_root / "pending"),
                patch.object(job_queue, "IN_PROGRESS", queue_root / "in_progress"),
                patch.object(job_queue, "PROCESSED", queue_root / "processed"),
                patch.object(job_queue, "FAILED", queue_root / "failed"),
                patch.object(job_queue, "REPORT_PATH", root / "report.md"),
                patch.object(upscale_model_registry, "REGISTRY_PATH", registry),
                patch.object(upscale_model_registry, "COMFYUI_ROOT", comfy),
                patch.object(production_artifact, "COMFYUI_INPUT_ROOT", comfy / "input"),
                patch.object(production_artifact, "COMFYUI_OUTPUT_ROOT", comfy / "output"),
                patch.object(production_artifact, "TARGET_CONFIG_PATH", target),
                patch.object(production_artifact, "STAGE_SIZES", ((2, 2), (4, 4), (8, 8), (16, 16))),
            ]
            for item in patches:
                item.start()
            try:
                job = job_queue.create_job(
                    "image_generation",
                    payload={"output_image_path": str(original), "transparent_artifact_path": str(derivative)},
                    requires_approval=False,
                )
                canonical_generated = generated.parent / job["job_id"]
                generated.rename(canonical_generated)
                original = canonical_generated / original.name
                derivative = canonical_generated / derivative.name
                job_queue.update_job_payload(job["job_id"], {
                    "output_image_path": str(original),
                    "transparent_artifact_path": str(derivative),
                })
                callback(root, job["job_id"], original, derivative)
            finally:
                for item in reversed(patches):
                    item.stop()

    def mocked_pipeline(self, job_id: str, *, fail_stage: int = 0):
        state = {"queue_count": 0, "outputs": [], "input_sizes": [], "workflows": []}

        def queue(workflow, **unused):
            state["queue_count"] += 1
            stage = state["queue_count"]
            state["workflows"].append(workflow)
            if fail_stage == stage:
                raise RuntimeError("synthetic stage failure")
            path = production_artifact.COMFYUI_INPUT_ROOT / workflow["1"]["inputs"]["image"]
            with Image.open(path) as image:
                image.load()
                self.assertEqual(image.mode, "RGB")
                state["input_sizes"].append(image.size)
                output = image.resize((image.width * 2, image.height * 2), Image.Resampling.NEAREST)
                state["outputs"].append(png_bytes(output))
            return {"prompt_id": f"stage-{stage}"}

        def output(*unused, **kwargs):
            filename = f"synthetic-stage-{state['queue_count']}.png"
            server_output = production_artifact.COMFYUI_OUTPUT_ROOT / filename
            server_output.parent.mkdir(parents=True, exist_ok=True)
            server_output.write_bytes(state["outputs"][state["queue_count"] - 1])
            return [{
                "filename": filename,
                "content": state["outputs"][state["queue_count"] - 1],
                "metadata": {"filename": filename, "subfolder": "", "type": "output"},
            }]

        return state, (
            patch.object(production_artifact.comfyui_client, "is_running", return_value=True),
            patch.object(production_artifact.comfyui_client, "queue_prompt", side_effect=queue),
            patch.object(production_artifact.comfyui_client, "wait_for_completion", return_value={"status": "completed"}),
            patch.object(production_artifact.comfyui_client, "get_output_images", side_effect=output),
        )

    def approve(self, job_id: str):
        return production_artifact.approve_transparent_artifact_for_job(job_id, approved_by="reviewer")

    def prepare_candidate(self, job_id: str):
        self.approve(job_id)
        state, patches = self.mocked_pipeline(job_id)
        with patches[0], patches[1], patches[2], patches[3]:
            result = production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
        return result

    def test_separate_sha_bound_derivative_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            approval = self.approve(job_id)
            stored = job_queue.get_job(job_id)["payload"]["transparent_derivative_approval"]
            self.assertEqual(stored["approved_artifact_path"], str(derivative.resolve()))
            self.assertEqual(stored["approved_artifact_sha256"], sha256(derivative.read_bytes()).hexdigest())
            self.assertEqual(stored["approved_by"], "reviewer")
            self.assertTrue(stored["approved_at"])
            self.assertEqual(approval["approved_artifact_sha256"], stored["approved_artifact_sha256"])
        self.sandbox(scenario)

    def test_processing_refuses_missing_approval_and_requires_confirmation(self) -> None:
        def scenario(root, job_id, original, derivative):
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
            self.approve(job_id)
            with patch.object(production_artifact.comfyui_client, "queue_prompt") as queue:
                with self.assertRaises(job_queue.JobQueueError):
                    production_artifact.prepare_production_artifact_for_job(job_id)
                queue.assert_not_called()
        self.sandbox(scenario)

    def test_changed_derivative_is_refused_and_sources_untouched(self) -> None:
        def scenario(root, job_id, original, derivative):
            original_before = original.read_bytes()
            self.approve(job_id)
            derivative.write_bytes(derivative.read_bytes() + b"changed")
            changed = derivative.read_bytes()
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
            self.assertEqual(original.read_bytes(), original_before)
            self.assertEqual(derivative.read_bytes(), changed)
        self.sandbox(scenario)

    def test_unvalidated_and_hash_mismatched_models_are_refused(self) -> None:
        def unvalidated(root, job_id, original, derivative):
            self.approve(job_id)
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
        self.sandbox(unvalidated, validated=False)

        def mismatch(root, job_id, original, derivative):
            self.approve(job_id)
            model = root / "ComfyUI" / "models" / "upscale_models" / self.MODEL
            model.write_bytes(b"changed model")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
        self.sandbox(mismatch)

    def test_three_scale_driven_stages_dimensions_alpha_metadata_and_previews(self) -> None:
        def scenario(root, job_id, original, derivative):
            original_before, derivative_before = original.read_bytes(), derivative.read_bytes()
            self.approve(job_id)
            state, patches = self.mocked_pipeline(job_id)
            with patches[0], patches[1], patches[2], patches[3]:
                result = production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
            self.assertEqual(state["queue_count"], 3)
            self.assertEqual(state["input_sizes"], [(2, 2), (4, 4), (8, 8)])
            for workflow in state["workflows"]:
                self.assertEqual(sum(node["class_type"] == "ImageUpscaleWithModel" for node in workflow.values()), 1)
                self.assertEqual(workflow["2"]["inputs"]["model_name"], self.MODEL)
            self.assertEqual([stage["output_dimensions"] for stage in result["intermediate_stages"]], [[4, 4], [8, 8], [16, 16]])
            self.assertEqual([stage["comfyui_prompt_id"] for stage in result["intermediate_stages"]], ["stage-1", "stage-2", "stage-3"])
            for stage in result["intermediate_stages"]:
                path = Path(stage["output_path"])
                self.assertTrue(path.exists())
                self.assertEqual(stage["output_sha256"], sha256(path.read_bytes()).hexdigest())
                with Image.open(path) as image:
                    self.assertEqual(image.mode, "RGBA")
                    self.assertLess(image.getchannel("A").getextrema()[0], 255)
            stages = result["intermediate_stages"]
            self.assertEqual(stages[1]["input_sha256"], stages[0]["output_sha256"])
            self.assertEqual(stages[2]["input_sha256"], stages[1]["output_sha256"])
            self.assertEqual(Path(stages[1]["input_path"]), Path(stages[0]["output_path"]))
            self.assertEqual(Path(stages[2]["input_path"]), Path(stages[1]["output_path"]))
            candidate = Path(result["production_candidate_path"])
            with Image.open(candidate) as image:
                self.assertEqual(image.size, (10, 12))
                self.assertEqual(image.mode, "RGBA")
                self.assertLess(image.getchannel("A").getextrema()[0], 255)
            self.assertEqual(result["canvas_dimensions"], [10, 12])
            self.assertEqual(result["artwork_dimensions"], [8, 8])
            self.assertEqual(result["placement_coordinates"], [1, 2])
            self.assertEqual(result["safe_margin_pixels"], {"left": 1, "right": 1, "top": 1, "bottom": 1})
            self.assertEqual(result["actual_upscale_settings"], {"alpha_resize_method": "lanczos", "edge_bleed_iterations": 2, "edge_bleed_alpha_threshold": 128})
            self.assertEqual(result["production_candidate_sha256"], sha256(candidate.read_bytes()).hexdigest())
            self.assertEqual(len(result["intermediate_sha256"]), 3)
            self.assertIn("alpha_diagnostics", result)
            for key in ("white_preview_path", "dark_preview_path", "checkerboard_preview_path"):
                self.assertTrue(Path(result[key]).exists())
                hash_key = key.replace("_path", "_sha256")
                self.assertEqual(result[hash_key], sha256(Path(result[key]).read_bytes()).hexdigest())
                with Image.open(result[key]) as preview:
                    self.assertEqual(preview.mode, "RGB")
            self.assertFalse(list(production_artifact.COMFYUI_OUTPUT_ROOT.glob("*")))
            self.assertEqual(result["production_artifact_status"], "needs_final_review")
            self.assertEqual(result["design_status"], "needs_final_review")
            self.assertEqual(result["provider_status"], "not_ready")
            self.assertEqual(result["printify_status"], "not_ready")
            self.assertFalse(result["final_print_ready"])
            self.assertEqual(original.read_bytes(), original_before)
            self.assertEqual(derivative.read_bytes(), derivative_before)
            persisted = job_queue.get_job(job_id)["payload"]["production_artifact"]
            self.assertEqual(persisted["production_candidate_sha256"], result["production_candidate_sha256"])
        self.sandbox(scenario)

    def test_aspect_ratio_safe_bounds_and_centered_placement(self) -> None:
        target = {
            "canvas_width": 100, "canvas_height": 80, "safe_margin_percent": 10,
            "horizontal_alignment": "center", "vertical_alignment": "center", "output_mode": "RGBA",
            "transparent_background": True, "placement_resize_method": "lanczos",
        }
        placement = production_artifact.calculate_placement((200, 100), target)
        self.assertEqual(placement["artwork_dimensions"], [80, 40])
        self.assertEqual(placement["placement_coordinates"], [10, 20])
        self.assertEqual(placement["safe_bounds"], [10, 8, 90, 72])
        self.assertEqual(placement["placement_scale"], 0.4)

    def test_default_target_builds_exact_4500x5400_transparent_rgba_canvas(self) -> None:
        target = production_artifact.load_production_target()
        self.assertEqual((target["canvas_width"], target["canvas_height"]), (4500, 5400))
        self.assertEqual(target["target_authority"], "jamesos_default_not_provider_verified")
        artwork = Image.new("RGBA", (2, 2), (255, 0, 0, 255))
        canvas, placement = production_artifact.place_artwork_on_canvas(artwork, target)
        self.assertEqual(canvas.size, (4500, 5400))
        self.assertEqual(canvas.mode, "RGBA")
        self.assertEqual(placement["placement_coordinates"], [2249, 2699])
        self.assertEqual(canvas.getpixel((0, 0))[3], 0)
        canvas.close()
        artwork.close()

    def test_existing_successful_candidate_is_preserved_by_later_refused_run(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.approve(job_id)
            state, patches = self.mocked_pipeline(job_id)
            with patches[0], patches[1], patches[2], patches[3]:
                first = production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
            candidate = Path(first["production_candidate_path"])
            before = candidate.read_bytes()
            with patch.object(production_artifact.comfyui_client, "queue_prompt") as queue:
                with self.assertRaises(job_queue.JobQueueError):
                    production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
                queue.assert_not_called()
            self.assertEqual(candidate.read_bytes(), before)
            self.assertEqual(job_queue.get_job(job_id)["payload"]["production_artifact"]["production_candidate_sha256"], sha256(before).hexdigest())
        self.sandbox(scenario)

    def test_failed_stage_stops_pipeline_cleans_candidate_and_preserves_debug_workflows(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.approve(job_id)
            before = derivative.read_bytes()
            state, patches = self.mocked_pipeline(job_id, fail_stage=2)
            with patches[0], patches[1], patches[2], patches[3]:
                with self.assertRaises(job_queue.JobQueueError):
                    production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
            production_root = derivative.parent / "production-artifacts"
            self.assertEqual(state["queue_count"], 2)
            self.assertFalse((production_root / "candidate").exists())
            self.assertFalse(list(production_root.glob(".production-run-*")))
            self.assertTrue((production_root / "debug" / "stage-1-submitted-workflow.json").exists())
            self.assertTrue((production_root / "debug" / "stage-2-submitted-workflow.json").exists())
            self.assertNotIn("production_artifact", job_queue.get_job(job_id)["payload"])
            self.assertEqual(derivative.read_bytes(), before)
        self.sandbox(scenario)

    def test_job_metadata_failure_rolls_back_newly_promoted_candidate(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.approve(job_id)
            state, patches = self.mocked_pipeline(job_id)
            with (
                patches[0], patches[1], patches[2], patches[3],
                patch.object(production_artifact, "update_job_payload", side_effect=RuntimeError("synthetic metadata failure")),
            ):
                with self.assertRaises(job_queue.JobQueueError):
                    production_artifact.prepare_production_artifact_for_job(job_id, confirmed=True)
            self.assertFalse((derivative.parent / "production-artifacts" / "candidate").exists())
            self.assertNotIn("production_artifact", job_queue.get_job(job_id)["payload"])
        self.sandbox(scenario)

    def test_authenticated_api_routes_forward_approval_and_confirmation(self) -> None:
        from jamesos.core import api
        approval = {"status": "ok"}
        prepared = {"status": "production_candidate_complete"}
        with (
            patch.object(api, "require_key", return_value=None) as authenticated,
            patch.object(api, "approve_transparent_artifact_for_job", return_value=approval) as approve,
            patch.object(api, "prepare_production_artifact_for_job", return_value=prepared) as prepare,
        ):
            self.assertEqual(api.image_worker_approve_transparent_artifact_route("job", api.TransparentArtifactApprovalRequest(approved_by="reviewer"), None), approval)
            self.assertEqual(api.image_worker_prepare_production_artifact_route("job", api.ProductionArtifactRequest(confirmed=True, upscale_model_name=self.MODEL), None), prepared)
        self.assertEqual(authenticated.call_count, 2)
        approve.assert_called_once_with("job", approved_by="reviewer")
        prepare.assert_called_once_with(
            "job", upscale_model_name=self.MODEL, confirmed=True, target_overrides=None,
            production_strategy="ai_upscale", artwork_category=None, strategy_selected_by="api_request",
        )

    def test_precision_resize_is_deterministic_non_ai_and_strategy_bound(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.approve(job_id)
            with patch.object(production_artifact.comfyui_client, "queue_prompt") as queue, \
                    patch.object(upscale_model_registry, "select_upscale_model", side_effect=AssertionError("model must not load")):
                result = production_artifact.prepare_production_artifact_for_job(
                    job_id, confirmed=True, production_strategy="precision_resize", artwork_category="logo",
                    strategy_selected_by="user",
                )
            queue.assert_not_called()
            self.assertEqual(result["selected_strategy"], "precision_resize")
            self.assertEqual(result["requested_strategy"], "precision_resize")
            self.assertEqual(result["strategy_selected_by"], "user")
            self.assertFalse(result["ai_model_required"])
            self.assertIsNone(result["model_name"]); self.assertIsNone(result["model_sha256"])
            self.assertEqual(len(result["intermediate_stages"]), 1)
            stage = result["intermediate_stages"][0]
            self.assertEqual(stage["processing_method"], "deterministic_precision_resize")
            self.assertNotIn("comfyui_prompt_id", stage); self.assertNotIn("model_name", stage)
            with Image.open(result["production_candidate_path"]) as candidate:
                self.assertEqual(candidate.size, (10, 12)); self.assertEqual(candidate.mode, "RGBA")
                self.assertLess(candidate.getchannel("A").getextrema()[0], 255)
            approved = production_artifact.approve_production_artifact_for_job(
                job_id, approved_by="final-reviewer", confirmed=True
            )["approval"]
            self.assertEqual(approved["strategy_evidence"]["selected_strategy"], "precision_resize")
            self.assertFalse(approved["strategy_evidence"]["ai_model_required"])
            self.assertIsNone(approved["model_evidence"])
        self.sandbox(scenario)

    def test_auto_is_conservative_and_explicit_override_is_recorded(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            uncertain = Path(temporary) / "uncertain.png"
            Image.new("RGBA", (16, 16), (120, 120, 120, 128)).save(uncertain)
            recommendation = production_artifact.recommend_production_strategy(uncertain)
            self.assertEqual(recommendation["status"], "needs_strategy_selection")
            self.assertEqual(production_artifact.recommend_production_strategy(uncertain, "flat_geometric")["selected_strategy"], "precision_resize")
            self.assertEqual(production_artifact.recommend_production_strategy(uncertain, "painterly")["selected_strategy"], "ai_upscale")

        def scenario(root, job_id, original, derivative):
            self.approve(job_id)
            state, patches = self.mocked_pipeline(job_id)
            with patches[0], patches[1], patches[2], patches[3]:
                result = production_artifact.prepare_production_artifact_for_job(
                    job_id, confirmed=True, production_strategy="ai_upscale", artwork_category="logo",
                    strategy_selected_by="user",
                )
            self.assertEqual(state["queue_count"], 3)
            self.assertTrue(result["strategy_override_used"])
            self.assertTrue(result["ai_model_required"])
            self.assertEqual(result["selected_strategy"], "ai_upscale")
        self.sandbox(scenario)

    def test_final_approval_requires_explicit_confirmation(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.prepare_candidate(job_id)
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="final-reviewer")
            self.assertNotIn("final_artifact_approval", job_queue.get_job(job_id)["payload"])
        self.sandbox(scenario)

    def test_successful_final_approval_is_bound_to_all_evidence_and_truthful_statuses(self) -> None:
        def scenario(root, job_id, original, derivative):
            candidate = self.prepare_candidate(job_id)
            candidate_before = Path(candidate["production_candidate_path"]).read_bytes()
            metadata_path = Path(candidate["production_candidate_path"]).parent / "production-artifact.json"
            metadata_before = metadata_path.read_bytes()
            result = production_artifact.approve_production_artifact_for_job(
                job_id, approved_by="final-reviewer", confirmed=True
            )
            payload = job_queue.get_job(job_id)["payload"]
            record = payload["final_artifact_approval"]
            self.assertTrue(payload["final_artifact_approved"])
            self.assertEqual(payload["final_artifact_status"], "approved")
            self.assertEqual(record["job_id"], job_id)
            self.assertEqual(record["approved_artifact_path"], candidate["production_candidate_path"])
            self.assertEqual(record["approved_artifact_sha256"], candidate["production_candidate_sha256"])
            self.assertEqual(record["production_metadata_sha256"], sha256(Path(record["production_metadata_path"]).read_bytes()).hexdigest())
            self.assertEqual(record["model_evidence"]["model_name"], self.MODEL)
            self.assertEqual(record["model_evidence"]["model_sha256"], candidate["model_sha256"])
            self.assertEqual(record["derivative_evidence"]["approved_artifact_sha256"], payload["transparent_derivative_approval"]["approved_artifact_sha256"])
            self.assertEqual(record["visual_review_result"], "passed")
            self.assertEqual(record["approval_scope"], "jamesos_artwork_candidate_human_review_only")
            approval_path = Path(payload["final_artifact_approval_record_path"])
            self.assertEqual(approval_path, Path(candidate["production_candidate_path"]).parent / "final-artifact-approval.json")
            self.assertTrue(approval_path.is_file())
            self.assertEqual(json.loads(approval_path.read_text(encoding="utf-8")), record)
            self.assertEqual(payload["final_artifact_approval_record_sha256"], sha256(approval_path.read_bytes()).hexdigest())
            self.assertEqual(Path(candidate["production_candidate_path"]).read_bytes(), candidate_before)
            self.assertEqual(metadata_path.read_bytes(), metadata_before)
            self.assertEqual(result["provider_status"], "not_ready")
            self.assertEqual(result["printify_status"], "not_ready")
            self.assertFalse(result["final_print_ready"])
            self.assertEqual(payload["provider_status"], "not_ready")
            self.assertEqual(payload["printify_status"], "not_ready")
            self.assertFalse(payload["final_print_ready"])
        self.sandbox(scenario)

    def test_candidate_hash_mismatch_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            Path(result["production_candidate_path"]).write_bytes(b"changed candidate")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_metadata_hash_or_content_mismatch_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            metadata = Path(result["production_candidate_path"]).parent / "production-artifact.json"
            changed = json.loads(metadata.read_text(encoding="utf-8"))
            changed["total_execution_time_seconds"] = 999
            metadata.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_changed_derivative_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.prepare_candidate(job_id)
            derivative.write_bytes(derivative.read_bytes() + b"changed")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_changed_model_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.prepare_candidate(job_id)
            (root / "ComfyUI" / "models" / "upscale_models" / self.MODEL).write_bytes(b"changed model")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_absent_candidate_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            Path(result["production_candidate_path"]).unlink()
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_absent_metadata_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            (Path(result["production_candidate_path"]).parent / "production-artifact.json").unlink()
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_incorrect_production_status_refuses_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.prepare_candidate(job_id)
            payload = job_queue.get_job(job_id)["payload"]
            payload["production_artifact_status"] = "draft"
            job_queue.update_job_payload(job_id, payload)
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(scenario)

    def test_valid_final_approval_repeat_is_idempotent(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.prepare_candidate(job_id)
            first = production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            approval_path = Path(first["approval"]["production_metadata_path"]).parent / "final-artifact-approval.json"
            file_sha_before = sha256(approval_path.read_bytes()).hexdigest()
            mtime_before = approval_path.stat().st_mtime_ns
            second = production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            self.assertFalse(first["idempotent"])
            self.assertTrue(second["idempotent"])
            self.assertEqual(first["approval"]["approved_at"], second["approval"]["approved_at"])
            self.assertEqual(sha256(approval_path.read_bytes()).hexdigest(), file_sha_before)
            self.assertEqual(approval_path.stat().st_mtime_ns, mtime_before)
        self.sandbox(scenario)

    def test_different_approver_cannot_replace_existing_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            self.prepare_candidate(job_id)
            first = production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            approval_path = Path(first["approval"]["production_metadata_path"]).parent / "final-artifact-approval.json"
            before = approval_path.read_bytes()
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="different-reviewer", confirmed=True)
            self.assertEqual(approval_path.read_bytes(), before)
            self.assertEqual(job_queue.get_job(job_id)["payload"]["approved_by"], "reviewer")
        self.sandbox(scenario)

    def test_immediate_post_approval_revalidates_every_hash_and_model(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            candidate = Path(result["production_candidate_path"])
            metadata = candidate.parent / "production-artifact.json"
            with (
                patch.object(production_artifact, "_hash_file", wraps=production_artifact._hash_file) as hashed,
                patch.object(upscale_model_registry, "select_upscale_model", wraps=upscale_model_registry.select_upscale_model) as selected,
            ):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            hashed_paths = [call.args[0] for call in hashed.call_args_list]
            self.assertGreaterEqual(hashed_paths.count(candidate), 2)
            self.assertGreaterEqual(hashed_paths.count(metadata), 2)
            self.assertGreaterEqual(hashed_paths.count(derivative.resolve()), 2)
            self.assertGreaterEqual(selected.call_count, 3)
        self.sandbox(scenario)

    def test_changed_evidence_invalidates_prior_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            candidate_parent = Path(result["production_candidate_path"]).parent
            approval_path = candidate_parent / "final-artifact-approval.json"
            preserved = {
                path: path.read_bytes()
                for path in (
                    candidate_parent / "production-artifact.json",
                    derivative,
                    Path(result["white_preview_path"]),
                    Path(result["dark_preview_path"]),
                    Path(result["checkerboard_preview_path"]),
                    Path(result["intermediate_stages"][0]["output_path"]),
                    derivative.parent / "production-artifacts" / "debug" / "stage-1-submitted-workflow.json",
                )
            }
            Path(result["production_candidate_path"]).write_bytes(b"changed after approval")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            payload = job_queue.get_job(job_id)["payload"]
            self.assertFalse(payload["final_artifact_approved"])
            self.assertEqual(payload["final_artifact_status"], "invalidated")
            self.assertNotIn("final_artifact_approval", payload)
            self.assertFalse(approval_path.exists())
            for path, content in preserved.items():
                self.assertEqual(path.read_bytes(), content)
            self.assertEqual(payload["provider_status"], "not_ready")
            self.assertEqual(payload["printify_status"], "not_ready")
            self.assertFalse(payload["final_print_ready"])
        self.sandbox(scenario)

    def test_failed_final_job_state_save_rolls_back_approval_record(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            candidate = Path(result["production_candidate_path"])
            metadata = candidate.parent / "production-artifact.json"
            candidate_before, metadata_before = candidate.read_bytes(), metadata.read_bytes()
            with patch.object(production_artifact, "update_job_payload", side_effect=RuntimeError("synthetic final-state failure")):
                with self.assertRaises(job_queue.JobQueueError):
                    production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            self.assertFalse((candidate.parent / "final-artifact-approval.json").exists())
            self.assertNotIn("final_artifact_approval", job_queue.get_job(job_id)["payload"])
            self.assertEqual(candidate.read_bytes(), candidate_before)
            self.assertEqual(metadata.read_bytes(), metadata_before)
        self.sandbox(scenario)

    def test_final_approval_refuses_traversal_and_symlink_escape(self) -> None:
        def traversal(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            payload = job_queue.get_job(job_id)["payload"]
            payload["production_artifact"]["production_candidate_path"] = str(
                Path(result["production_candidate_path"]).parent / ".." / "candidate" / "production-candidate.png"
            )
            job_queue.update_job_payload(job_id, payload)
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(traversal)

        def symlink(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            candidate = Path(result["production_candidate_path"])
            external = root / "external-candidate.png"
            candidate.replace(external)
            candidate.symlink_to(external)
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
        self.sandbox(symlink)

    def test_changed_metadata_invalidates_prior_final_approval(self) -> None:
        def scenario(root, job_id, original, derivative):
            result = self.prepare_candidate(job_id)
            production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            metadata_path = Path(result["production_candidate_path"]).parent / "production-artifact.json"
            metadata_path.write_bytes(metadata_path.read_bytes() + b"\n")
            with self.assertRaises(job_queue.JobQueueError):
                production_artifact.approve_production_artifact_for_job(job_id, approved_by="reviewer", confirmed=True)
            payload = job_queue.get_job(job_id)["payload"]
            self.assertFalse(payload["final_artifact_approved"])
            self.assertEqual(payload["final_artifact_status"], "invalidated")
            self.assertNotIn("final_artifact_approval", payload)
        self.sandbox(scenario)

    def test_final_approval_api_is_authenticated_and_forwards_required_fields(self) -> None:
        from jamesos.core import api
        expected = {"status": "ok", "final_artifact_approved": True}
        with (
            patch.object(api, "require_key", return_value=None) as authenticated,
            patch.object(api, "approve_production_artifact_for_job", return_value=expected) as approve,
        ):
            request = api.ProductionArtifactApprovalRequest(approved_by="reviewer", confirmed=True)
            self.assertEqual(api.image_worker_approve_production_artifact_route("job", request, None), expected)
        authenticated.assert_called_once_with(None)
        approve.assert_called_once_with("job", approved_by="reviewer", confirmed=True)

    def test_final_approval_api_rejects_missing_authentication_before_service(self) -> None:
        from jamesos.core import api
        request = api.ProductionArtifactApprovalRequest(approved_by="reviewer", confirmed=True)
        with (
            patch.object(api, "require_key", side_effect=PermissionError("authentication required")),
            patch.object(api, "approve_production_artifact_for_job") as approve,
        ):
            with self.assertRaises(PermissionError):
                api.image_worker_approve_production_artifact_route("job", request, None)
            approve.assert_not_called()


if __name__ == "__main__":
    unittest.main()
