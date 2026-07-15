from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from jamesos.services import job_queue, sale_candidate


class SaleCandidateTests(unittest.TestCase):
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

    def fixture(self, root: Path):
        job_root = root / "e2e-artwork-sale-fixture"; candidate = job_root / "production-artifacts" / "candidate" / "production-candidate.png"
        candidate.parent.mkdir(parents=True)
        image = Image.new("RGBA", (4500, 5400), (0, 0, 0, 0))
        ImageDraw.Draw(image).ellipse((750, 1100, 3750, 4300), fill=(235, 60, 100, 255))
        image.save(candidate); image.close()
        return {"candidate": candidate, "candidate_sha": sha256(candidate.read_bytes()).hexdigest(), "approval_sha": "approval-sha",
                "job_root": job_root, "production": {"canvas_dimensions": [4500, 5400]}}

    def test_composition_is_deterministic_sha_bound_and_previewed(self):
        self.assertTrue(self.FONT.is_file())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); before = evidence["candidate"].read_bytes()
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                first = sale_candidate.create_composition("job", "love-1", font_path=self.FONT, confirmed=True)
                second = sale_candidate.create_composition("job", "love-2", font_path=self.FONT, confirmed=True)
            self.assertEqual(first["exact_text"], "LOVE IS LOVE"); self.assertEqual(first["output_sha256"], second["output_sha256"])
            self.assertEqual(first["typography"]["resolved_font_sha256"], sha256(self.FONT.read_bytes()).hexdigest())
            self.assertEqual(evidence["candidate"].read_bytes(), before); self.assertAlmostEqual(first["heart_scale"], .87)
            with Image.open(first["output_path"]) as image:
                self.assertEqual(image.size, (4500, 5400)); self.assertEqual(image.mode, "RGBA")
            bbox = first["typography"]["text_bounding_box"]; self.assertGreaterEqual(bbox[0], 225); self.assertLessEqual(bbox[2], 4275)
            self.assertEqual(set(first["previews"]), {"dark", "white", "checkerboard"})
            self.assertTrue(all(Path(item["path"]).is_file() for item in first["previews"].values()))
            self.assertEqual(first["human_approval_status"], "not_approved")

    def test_missing_font_and_unapproved_upload_fail_safely(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); client = Mock()
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                with self.assertRaisesRegex(job_queue.JobQueueError, "font"):
                    sale_candidate.create_composition("job", "missing", font_path=root / "missing.ttf", confirmed=True)
                sale_candidate.create_composition("job", "love", font_path=self.FONT, confirmed=True)
                with self.assertRaisesRegex(job_queue.JobQueueError, "Human-approved"):
                    sale_candidate.upload_composition("job", "love", client=client, confirmed=True)
            client.upload_image_contents.assert_not_called()

    def test_profile_listing_and_approvals_are_bound_without_copying(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); client = Mock()
            existing = "Existing Listing Wording That Must Not Be Copied"
            client.list_products.return_value = {"data": [{"id": "p1", "title": "Rainbow Tee", "description": existing,
                "tags": ["rainbow"], "variants": [{"price": 1999}]}]}
            profile_path = root / "style.json"; profile = sale_candidate.profile_store(client, 9437076, profile_path)
            client.list_products.assert_called_once_with(9437076); self.assertEqual(profile["products_analyzed"], 1)
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                composition = sale_candidate.create_composition("job", "love", font_path=self.FONT, confirmed=True)
                sale_candidate.approve_composition("job", "love", approved_by="James", confirmed=True)
            composition_root = Path(composition["output_path"]).parent
            listing = sale_candidate.generate_listing(composition_root, profile_path, confirmed=True)
            self.assertNotEqual(listing["description"], existing)
            self.assertEqual(listing["style_profile_sha256"], profile["profile_sha256"])
            self.assertEqual(listing["composition_sha256"], composition["output_sha256"])
            self.assertEqual(listing["variants"]["preferred_primary_mockup_color"], "Black")
            approval = sale_candidate.approve_listing(composition_root / "listing", approved_by="James", confirmed=True)
            self.assertEqual(approval["review_result"], "passed")

    def test_replay_is_read_only_and_report_has_required_sections(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); client = Mock()
            client.get_product.return_value = {"id": "6a57eaa752f2c3e4700dbf23", "images": [{"src": "https://example.test/mockup.jpg"}]}
            report = root / "sale-candidate-report.html"
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                run = sale_candidate.replay_baseline("job", "6a57eaa752f2c3e4700dbf23", 9437076, client=client, report_path=report)
            client.get_product.assert_called_once(); client.upload_image_contents.assert_not_called(); client.create_product.assert_not_called()
            self.assertEqual(run["composition_id"], "baseline_without_text")
            document = report.read_text(encoding="utf-8")
            for required in ("Original approved artwork", "Product brief", "Typography and composition configuration",
                "Product-specific print file", "Dark preview", "White preview", "Checkerboard preview", "Store-style profile summary",
                "Generated title", "Generated description", "Generated tags", "Pricing and variants", "Printify upload evidence",
                "Product draft evidence", "Real Printify mockups", "Approval and readiness timeline", "Current next action",
                "DRAFT", "NOT PUBLISHED", "NO ORDER CREATED", "HUMAN REVIEW REQUIRED"):
                self.assertIn(required, document)
            self.assertNotIn("Authorization", document); self.assertNotIn("Bearer ", document)

    def test_composition_upload_and_new_draft_use_separate_records(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); client = Mock()
            client.upload_image_contents.return_value = {"id": "new-image", "mime_type": "image/png", "width": 4500, "height": 5400}
            client.create_product.return_value = {"id": "new-product", "images": [], "variants": [], "print_areas": []}
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                composition = sale_candidate.create_composition("job", "love", font_path=self.FONT, confirmed=True)
                sale_candidate.approve_composition("job", "love", approved_by="James", confirmed=True)
                upload = sale_candidate.upload_composition("job", "love", client=client, confirmed=True)
            composition_root = Path(composition["output_path"]).parent
            profile = {"profile_sha256": "profile"}; profile_path = root / "profile.json"; profile_path.write_text(json.dumps(profile), encoding="utf-8")
            listing = sale_candidate.generate_listing(composition_root, profile_path, confirmed=True)
            sale_candidate.approve_listing(composition_root / "listing", approved_by="James", confirmed=True)
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                draft = sale_candidate.create_composition_product_draft("job", "love", client=client, confirmed=True,
                    shop_id=9437076, blueprint_id=12, provider_id=29, variant_ids=[1, 2], price=2499, scale=.8)
            self.assertEqual(upload["printify_image_id"], "new-image"); self.assertEqual(draft["product_id"], "new-product")
            self.assertFalse(draft["baseline_product_id_reused"]); self.assertEqual(draft["publish_status"], "not_published")
            self.assertTrue((composition_root / "printify" / "upload.json").is_file())
            self.assertTrue((composition_root / "printify" / "product-draft.json").is_file())


if __name__ == "__main__": unittest.main()
