from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from jamesos.services import job_queue, sale_candidate, sale_candidate_vector
from jamesos.core.errors import FontAcquisitionError, ValidationError


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

    def test_curated_font_library_and_fallback_resolution(self):
        fonts = sale_candidate.load_curated_fonts()
        self.assertEqual({item["style_family"] for item in fonts}, {"retro_rounded", "groovy_retro", "hand_lettered_bold", "modern_rounded"})
        resolved = sale_candidate.list_curated_fonts()
        self.assertTrue(all(Path(item["resolved_font_path"]).is_absolute() for item in resolved))
        self.assertTrue(all(len(item["resolved_font_sha256"]) == 64 for item in resolved))
        fallback = sale_candidate.resolve_curated_font({**fonts[0], "font_path": "/definitely/missing/font.ttf",
            "fallback_font_path": str(self.FONT)})
        self.assertTrue(fallback["fallback_used"]); self.assertEqual(fallback["resolved_font_sha256"], sha256(self.FONT.read_bytes()).hexdigest())

    def test_multi_font_preview_selection_is_immutable_and_feeds_listing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); before = evidence["candidate"].read_bytes()
            profile_path = root / "profile.json"; profile_path.write_text(json.dumps({"profile_sha256": "profile-sha"}), encoding="utf-8")
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                previews = sale_candidate.generate_font_previews("job", "love-v2", phrase="LOVE IS LOVE", confirmed=True, preview_run_id="preview-001")
                composition_root = evidence["job_root"] / "commerce" / "product-compositions" / "love-v2"
                with self.assertRaisesRegex(job_queue.JobQueueError, "font/style selection"):
                    sale_candidate.generate_listing(composition_root, profile_path, confirmed=True)
                first = sale_candidate.approve_font_selection("job", "love-v2", preview_run_id="preview-001",
                    font_option_id="groovy-retro-01", approved_by="James", confirmed=True)
                approval_path = composition_root / "font-selection-approval.json"; approval_sha = sha256(approval_path.read_bytes()).hexdigest()
                repeat = sale_candidate.approve_font_selection("job", "love-v2", preview_run_id="preview-001",
                    font_option_id="groovy-retro-01", approved_by="James", confirmed=True)
                with self.assertRaisesRegex(job_queue.JobQueueError, "cannot be replaced"):
                    sale_candidate.approve_font_selection("job", "love-v2", preview_run_id="preview-001",
                        font_option_id="modern-rounded-01", approved_by="Other", confirmed=True)
                listing = sale_candidate.generate_listing(composition_root, profile_path, confirmed=True)
            self.assertEqual(len(previews["options"]), 4); self.assertEqual(evidence["candidate"].read_bytes(), before)
            self.assertTrue(Path(previews["comparison_sheet_path"]).is_file()); self.assertTrue(Path(previews["report_path"]).is_file())
            for option in previews["options"]:
                self.assertTrue(Path(option["composition_path"]).is_file()); self.assertTrue(Path(option["dark_preview_path"]).is_file())
                self.assertTrue(Path(option["light_preview_path"]).is_file()); self.assertEqual(len(option["font"]["resolved_font_sha256"]), 64)
            self.assertTrue(repeat["idempotent"]); self.assertEqual(repeat["approved_at"], first["approved_at"])
            self.assertEqual(sha256(approval_path.read_bytes()).hexdigest(), approval_sha)
            self.assertEqual(listing["selected_font_option_id"], "groovy-retro-01")
            self.assertEqual(listing["composition_sha256"], first["selected_composition_sha256"])
            self.assertEqual(listing["style_manifest_sha256"], first["manifest_sha256"])
            self.assertEqual(listing["publish_status"], "not_published"); self.assertEqual(listing["order_status"], "not_created")

    def test_font_acquisition_is_confirmed_restricted_and_records_license_sha(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValidationError) as denied:
                sale_candidate_vector.acquire_fonts(confirmed=False, font_root=root / "fonts")
            self.assertEqual(denied.exception.stage, "confirmation"); self.assertFalse(denied.exception.state["permanent_files_changed"])
            config = {"approved_source_hosts": ["raw.githubusercontent.com"], "fonts": [{"font_id": "test-font",
                "family": "Test Family", "style": "Regular", "license_type": "OFL-1.1", "license_display_name": "SIL Open Font License 1.1", "license_file_name": "OFL.txt",
                "display": "Test Family Regular", "filename": "font.ttf", "source_repository": "test/fonts",
                "approved_source_host": "raw.githubusercontent.com", "font_url": "http://unapproved.example/font.ttf",
                "license_url": "https://raw.githubusercontent.com/OFL.txt"}]}
            config_path = root / "fonts.json"; config_path.write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaises(FontAcquisitionError) as rejected:
                sale_candidate_vector.acquire_fonts(confirmed=True, font_root=root / "bad", config_path=config_path, downloader=lambda _url: b"unused")
            self.assertEqual(rejected.exception.stage, "preflight"); self.assertFalse((root / "bad").exists())
            good = {**config, "fonts": [{**config["fonts"][0], "font_url": "https://raw.githubusercontent.com/font.ttf"}]}
            config_path.write_text(json.dumps(good), encoding="utf-8")
            fake_scan = Mock(stdout="Test Family|Regular")
            def download(url): return b"SIL OPEN FONT LICENSE Version 1.1" if "OFL" in url else b"font-bytes"
            with patch.object(sale_candidate_vector.subprocess, "run", return_value=fake_scan):
                acquired = sale_candidate_vector.acquire_fonts(confirmed=True, font_root=root / "good", config_path=config_path, downloader=download)
            record = acquired["fonts"][0]
            self.assertEqual(record["font_sha256"], sha256(b"font-bytes").hexdigest())
            self.assertEqual(record["license_sha256"], sha256(b"SIL OPEN FONT LICENSE Version 1.1").hexdigest())
            self.assertTrue(Path(record["license_path"]).is_file())
            manifest_path = Path(acquired["manifest_path"]); manifest_before = manifest_path.read_bytes()
            unexpected = root / "good" / "operator-note.txt"; unexpected.write_text("retain", encoding="utf-8")
            with patch.object(sale_candidate_vector.subprocess, "run", return_value=fake_scan):
                repeated = sale_candidate_vector.acquire_fonts(confirmed=True, font_root=root / "good", config_path=config_path, downloader=download)
            self.assertEqual(repeated["result"], "already_acquired"); self.assertTrue(repeated["idempotent"])
            self.assertEqual(manifest_path.read_bytes(), manifest_before); self.assertEqual(unexpected.read_text(), "retain")
            self.assertTrue(any("operator-note.txt" in warning for warning in repeated["warnings"]))
            stale = json.loads(manifest_path.read_text(encoding="utf-8")); stale["fonts"][0]["font_sha256"] = "0" * 64
            manifest_path.write_text(json.dumps(stale), encoding="utf-8")
            with patch.object(sale_candidate_vector.subprocess, "run", return_value=fake_scan):
                repaired = sale_candidate_vector.acquire_fonts(confirmed=True, font_root=root / "good", config_path=config_path, downloader=download)
            self.assertEqual(repaired["result"], "acquired"); self.assertFalse(repaired["fonts"][0]["reused_existing_file"])
            Path(repaired["fonts"][0]["license_path"]).unlink()
            with patch.object(sale_candidate_vector.subprocess, "run", return_value=fake_scan):
                relicensed = sale_candidate_vector.acquire_fonts(confirmed=True, font_root=root / "good", config_path=config_path, downloader=download)
            self.assertEqual(relicensed["result"], "acquired"); self.assertFalse(relicensed["fonts"][0]["reused_existing_file"])

    def test_font_config_has_per_font_licenses_and_correct_chewy_sources(self):
        config = json.loads(sale_candidate_vector.FONT_CONFIG.read_text(encoding="utf-8"))
        self.assertTrue(sale_candidate_vector.preflight_font_config()["valid"])
        self.assertNotIn("license", config)
        chewy = next(x for x in config["fonts"] if x["font_id"] == "chewy-regular")
        self.assertEqual(chewy["license_type"], "Apache-2.0"); self.assertEqual(chewy["license_file_name"], "LICENSE.txt")
        self.assertIn("/apache/chewy/", chewy["font_url"]); self.assertTrue(chewy["license_url"].endswith("/LICENSE.txt"))
        self.assertEqual({x["license_type"] for x in config["fonts"] if x is not chewy}, {"OFL-1.1"})

    def test_font_acquisition_failure_is_transactional_and_cleans_staging(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); font_root = root / "fonts"; font_root.mkdir(); sentinel = font_root / "keep.txt"; sentinel.write_text("keep")
            calls = 0
            def failing(_url):
                nonlocal calls; calls += 1
                if calls == 7:
                    response = Mock(status_code=404); error = __import__("requests").HTTPError("404"); error.response = response; raise error
                return self.FONT.read_bytes() if calls % 2 else b"SIL OPEN FONT LICENSE Version 1.1"
            with patch.object(sale_candidate_vector.subprocess, "run", return_value=Mock(stdout="Coiny Fredoka Lilita One|Regular SemiBold")):
                with self.assertRaises(FontAcquisitionError) as raised:
                    sale_candidate_vector.acquire_fonts(confirmed=True, font_root=font_root, downloader=failing)
            result = raised.exception
            self.assertEqual(result.code, "FONT_RESOURCE_NOT_FOUND"); self.assertEqual(result.context["http_status"], 404)
            self.assertEqual(sentinel.read_text(), "keep"); self.assertFalse(list(font_root.glob(".font-acquisition-*")))
            self.assertFalse((font_root / "acquired-fonts.json").exists()); self.assertFalse(result.state["permanent_files_changed"])

    def test_v3_generates_six_structural_vector_concepts_and_design_approval(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); evidence = self.fixture(root); before = evidence["candidate"].read_bytes(); font_root = root / "fonts"; font_root.mkdir()
            font_config = json.loads(sale_candidate_vector.FONT_CONFIG.read_text(encoding="utf-8"))
            records = [{**{key: value for key, value in item.items() if key not in ("variation_axes", "axis_order")}, "font_path": str(self.FONT), "font_sha256": sha256(self.FONT.read_bytes()).hexdigest(),
                "license_path": str(root / "OFL.txt"), "license_sha256": "license", "verified_family": item["family"], "verified_style": item["style"]}
                for item in font_config["fonts"]]
            (font_root / "acquired-fonts.json").write_text(json.dumps({"fonts": records}), encoding="utf-8")
            profile_path = root / "profile.json"; profile_path.write_text(json.dumps({"profile_sha256": "profile"}), encoding="utf-8")
            with patch("jamesos.services.printify_product._approved_evidence", return_value=evidence):
                manifest = sale_candidate_vector.generate_design_concepts("job", "love-is-love-v3", phrase="LOVE IS LOVE",
                    confirmed=True, font_root=font_root, run_id="design-001")
                composition_root = evidence["job_root"] / "commerce" / "product-compositions" / "love-is-love-v3"
                with self.assertRaisesRegex(job_queue.JobQueueError, "design concept"):
                    sale_candidate.generate_listing(composition_root, profile_path, confirmed=True)
                first = sale_candidate_vector.approve_design_concept("job", "love-is-love-v3", design_run_id="design-001",
                    concept_id="top_bottom_badge", approved_by="James", confirmed=True)
                repeat = sale_candidate_vector.approve_design_concept("job", "love-is-love-v3", design_run_id="design-001",
                    concept_id="top_bottom_badge", approved_by="James", confirmed=True)
                with self.assertRaisesRegex(job_queue.JobQueueError, "cannot be silently replaced"):
                    sale_candidate_vector.approve_design_concept("job", "love-is-love-v3", design_run_id="design-001",
                        concept_id="minimal_editorial", approved_by="James", confirmed=True)
                listing = sale_candidate.generate_listing(composition_root, profile_path, confirmed=True)
            self.assertEqual(evidence["candidate"].read_bytes(), before); self.assertEqual(len(manifest["concepts"]), 6)
            self.assertEqual(len({item["layout_structure"] for item in manifest["concepts"]}), 6)
            self.assertTrue(Path(manifest["design_comparison_sheet"]["path"]).is_file()); self.assertTrue(Path(manifest["garment_comparison_sheet"]["path"]).is_file())
            for concept in manifest["concepts"]:
                self.assertTrue(Path(concept["svg_path"]).is_file()); self.assertEqual(len(concept["svg_sha256"]), 64)
                self.assertTrue(Path(concept["png_path"]).is_file()); self.assertEqual(len(concept["png_sha256"]), 64)
                self.assertEqual(concept["phrase"], "LOVE IS LOVE"); self.assertEqual(concept["status"], "needs_human_design_selection")
                self.assertTrue(Path(concept["thumbnail"]["path"]).is_file())
                with Image.open(concept["png_path"]) as image: self.assertEqual(image.size, (4500, 5400)); self.assertEqual(image.mode, "RGBA")
                self.assertEqual(set(concept["previews"]), {"black", "dark_heather", "white"})
            straight = next(x for x in manifest["concepts"] if x["concept_id"] == "stacked_groovy")
            curved = next(x for x in manifest["concepts"] if x["concept_id"] == "top_bottom_badge")
            self.assertTrue(straight["full_line_text_shaping"]); self.assertTrue(curved["glyph_bounds"])
            self.assertTrue(all("tangent_rotation_degrees" in glyph for glyph in curved["glyph_bounds"] if glyph.get("character") != " "))
            self.assertTrue(repeat["idempotent"]); self.assertEqual(repeat["approved_at"], first["approved_at"])
            self.assertEqual(listing["selected_design_concept_id"], "top_bottom_badge")
            self.assertEqual(listing["composition_sha256"], first["selected_png_sha256"])
            self.assertEqual(listing["publish_status"], "not_published")


if __name__ == "__main__": unittest.main()
