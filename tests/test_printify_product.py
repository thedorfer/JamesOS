from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image

from jamesos.integrations.printify_client import PrintifyAPIError, PrintifyClient, token_status
from jamesos.core.errors import ArtifactIntegrityError
from jamesos.services import job_queue, printify_product


class Response:
    def __init__(self, status=200, value=None, headers=None, content=b"mockup"):
        self.status_code, self.value, self.headers, self.content = status, value, headers or {}, content
    def json(self): return self.value
    def raise_for_status(self):
        if self.status_code >= 400: raise RuntimeError("http failure")


class PrintifyTests(unittest.TestCase):
    def client(self, root: Path, responses=None):
        token = root / "token"; token.write_text("super-secret-token", encoding="utf-8"); token.chmod(0o600)
        session = Mock(); session.request.side_effect = responses or [Response(value=[])]
        return PrintifyClient(token_path=token, session=session), session

    def fixture(self, root: Path):
        job_id = "e2e-artwork-printify-fixture"
        job_root = root / job_id; candidate_root = job_root / "production-artifacts" / "candidate"; candidate_root.mkdir(parents=True)
        derivative = job_root / "transparent_artifact.png"; candidate = candidate_root / "production-candidate.png"
        Image.new("RGBA", (8, 8), (1, 2, 3, 128)).save(derivative); Image.new("RGBA", (100, 120), (4, 5, 6, 128)).save(candidate)
        derivative_sha = sha256(derivative.read_bytes()).hexdigest(); candidate_sha = sha256(candidate.read_bytes()).hexdigest()
        production = {"job_id": job_id, "production_candidate_path": str(candidate), "production_candidate_sha256": candidate_sha,
                      "approved_source_sha256": derivative_sha, "canvas_dimensions": [100, 120], "selected_strategy": "precision_resize",
                      "production_artifact_status": "needs_final_review", "provider_status": "not_ready"}
        metadata = candidate_root / "production-artifact.json"; metadata.write_text(json.dumps(production, indent=2, sort_keys=True), encoding="utf-8")
        approval = {"job_id": job_id, "approved_artifact_path": str(candidate), "approved_artifact_sha256": candidate_sha,
                    "production_metadata_path": str(metadata), "production_metadata_sha256": sha256(metadata.read_bytes()).hexdigest(),
                    "approved_by": "James", "approved_at": "2026-07-15T12:00:00-05:00", "visual_review_result": "passed",
                    "derivative_evidence": {"approved_artifact_path": str(derivative), "approved_artifact_sha256": derivative_sha},
                    "strategy_evidence": {"selected_strategy": "precision_resize"}}
        approval_path = candidate_root / "final-artifact-approval.json"; approval_path.write_text(json.dumps(approval, indent=2, sort_keys=True), encoding="utf-8")
        payload = {"transparent_artifact_path": str(derivative), "production_artifact": production,
                   "final_artifact_approved": True, "final_artifact_status": "approved", "final_artifact_approval": approval,
                   "provider_status": "not_ready", "printify_status": "not_ready", "final_print_ready": False}
        return {"job_id": job_id, "payload": payload}, candidate

    def test_token_security_headers_and_safe_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); missing = root / "missing"
            self.assertEqual(token_status(missing)["status"], "not_configured")
            bad = root / "bad"; bad.write_text("secret", encoding="utf-8"); bad.chmod(0o644)
            self.assertEqual(token_status(bad)["status"], "invalid_permissions")
            client, session = self.client(root, [Response(value=[{"id": 1}])])
            self.assertEqual(client.list_shops(), [{"id": 1}])
            headers = session.request.call_args.kwargs["headers"]
            self.assertEqual(headers["Authorization"], "Bearer super-secret-token")
            self.assertIn("JamesOS", headers["User-Agent"])
            self.assertNotIn("super-secret-token", str(token_status(client.token_path)))
            session.request.side_effect = [Response(401, {"code": "unauthorized", "message": "bad credentials"})]
            with self.assertRaises(PrintifyAPIError) as raised: client.list_shops()
            self.assertNotIn("super-secret-token", str(raised.exception))

    def test_catalog_normalization_and_search(self):
        normalized = printify_product.normalize_catalog(
            {"id": 10, "title": "Unisex Tee", "brand": "Brand", "model": "Model"},
            {"id": 20, "title": "US Provider", "country": "US"},
            {"variants": [{"id": i, "title": f"Black / {size}", "cost": 1000, "is_available": True}
                          for i, size in enumerate(("S", "M", "L", "XL", "2XL"), 1)],
             "print_areas": [{"position": "front", "placeholders": [{"width": 4500, "height": 5400}], "decoration_methods": ["dtg"]}]})
        self.assertTrue(normalized["required_colors_covered"]); self.assertTrue(normalized["required_sizes_covered"])
        self.assertEqual(normalized["provider_location"], "US"); self.assertTrue(normalized["decoration_methods"])
        client = Mock(); client.list_blueprints.return_value = [{"id": 10, "title": "Adult Unisex T-Shirt"}, {"id": 11, "title": "Mug"}]
        self.assertEqual([x["blueprint_id"] for x in printify_product.search_shirt_blueprints(client)], [10])

    def test_upload_is_approval_bound_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); job, candidate = self.fixture(root); client = Mock()
            client.upload_image_contents.return_value = {"id": "image-1", "file_name": "remote.png", "width": 100, "height": 120,
                "size": 1000, "mime_type": "image/png", "preview_url": "https://example.test/image", "upload_time": "now"}
            client.get_upload.return_value = client.upload_image_contents.return_value
            with patch.object(job_queue, "get_job", return_value=job), patch.object(job_queue, "update_job_payload"):
                with self.assertRaises(job_queue.JobQueueError): printify_product.upload_approved_artwork(job["job_id"], confirmed=False, client=client)
                before = candidate.read_bytes(); first = printify_product.upload_approved_artwork(job["job_id"], confirmed=True, client=client)
                second = printify_product.upload_approved_artwork(job["job_id"], confirmed=True, client=client)
            self.assertEqual(candidate.read_bytes(), before); self.assertEqual(first["printify_image_id"], "image-1")
            self.assertTrue(second["idempotent"]); client.upload_image_contents.assert_called_once()
            payload = client.upload_image_contents.call_args.args; self.assertTrue(payload[0].startswith(f"jamesos-{job['job_id']}-"))
            self.assertTrue((candidate.parents[2] / "commerce" / "printify" / "upload.json").is_file())

    def test_unapproved_and_sha_changed_candidates_are_refused(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); job, candidate = self.fixture(root); client = Mock()
            job["payload"]["final_artifact_approved"] = False
            with patch.object(job_queue, "get_job", return_value=job):
                with self.assertRaises(job_queue.JobQueueError): printify_product.upload_approved_artwork(job["job_id"], confirmed=True, client=client)
            job["payload"]["final_artifact_approved"] = True; candidate.write_bytes(b"changed")
            with patch.object(job_queue, "get_job", return_value=job):
                with self.assertRaisesRegex(ArtifactIntegrityError, "candidate SHA"): printify_product.upload_approved_artwork(job["job_id"], confirmed=True, client=client)
            client.upload_image_contents.assert_not_called()

    def test_plan_product_and_mockups_are_idempotent_and_unpublished(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); job, candidate = self.fixture(root); client = Mock()
            upload = {"printify_image_id": "image-1"}
            with patch.object(job_queue, "get_job", return_value=job), patch.object(job_queue, "update_job_payload"):
                plan = printify_product.create_draft_plan(job["job_id"], upload=upload, shop_id=1, blueprint_id=2, provider_id=3,
                    enabled_variant_ids=[10, 11], prices={10: 2499, 11: 2599}, placeholder=(4500, 5400))
                client.create_product.return_value = {"id": "product-1", "shop_id": 1, "blueprint_id": 2, "print_provider_id": 3,
                    "is_locked": False, "variants": [{"id": 10, "is_enabled": True}, {"id": 11, "is_enabled": True}],
                    "print_areas": [{"placeholders": [{"images": [{"id": "image-1"}]}]}],
                    "images": [{"src": "https://example.test/mockup.jpg", "variant_ids": [10], "position": "front", "is_default": True}]}
                client.get_product.return_value = client.create_product.return_value
                first = printify_product.create_product_draft(job["job_id"], confirmed=True, client=client)
                second = printify_product.create_product_draft(job["job_id"], confirmed=True, client=client)
                client.session.get.return_value = Response(content=b"mockup-bytes")
                mockups = printify_product.download_mockups(job["job_id"], client=client)
            self.assertEqual(plan["publish_status"], "not_published"); self.assertEqual(first["publish_status"], "not_published")
            self.assertTrue(second["idempotent"]); client.create_product.assert_called_once()
            sent = client.create_product.call_args.args[1]
            self.assertEqual(sent["blueprint_id"], 2); self.assertEqual(sent["print_provider_id"], 3)
            self.assertEqual(sent["print_areas"][0]["placeholders"][0]["images"][0]["id"], "image-1")
            self.assertNotIn("visible", sent)
            self.assertEqual(len(mockups), 1); self.assertEqual(mockups[0]["sha256"], sha256(b"mockup-bytes").hexdigest())
            self.assertTrue(Path(mockups[0]["local_path"]).is_file())

    def test_no_forbidden_client_methods_or_routes(self):
        client_names = set(dir(PrintifyClient))
        for name in ("create_order", "send_to_production", "delete_product", "archive_upload"):
            self.assertNotIn(name, client_names)
        self.assertIn("publish_product",client_names)
        from jamesos.core.api import app
        paths = {route.path for route in app.routes}
        self.assertFalse(any("publish" in path or "order" in path for path in paths if path.startswith("/commerce/printify")))


if __name__ == "__main__": unittest.main()
