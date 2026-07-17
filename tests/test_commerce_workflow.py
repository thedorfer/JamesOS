from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from jamesos.services import product_orchestrator
from jamesos.services.commerce_workflow import CommerceWorkflow
from scripts import jamesos as jamesos_cli
from tests import test_product_orchestrator as product_tests


class CommerceWorkflowTests(unittest.TestCase):
    def fixture(self, root: Path):
        orchestrator,state,remote,replacement,client=product_tests.ProductOrchestratorTests().listing_fixture(root,product_id="private-product-fixture")
        artwork=root/"artwork.png";artwork.write_bytes(b"proposal-artwork")
        artwork_sha=product_orchestrator.sha256(artwork.read_bytes()).hexdigest()
        state["profile_id"]="private-profile-fixture";state["brief"].update(exact_text="PUBLIC PHRASE",garment_colors=product_orchestrator.DEFAULT_COLORS,
            sizes=product_orchestrator.DEFAULT_SIZES,currency="USD",blank="Public Model",print_provider="Public Provider")
        state["evidence"]["selection"]={"selected":{"png_path":str(artwork),"png_sha256":artwork_sha}}
        state["evidence"]["upload"]["selected_design_sha256"]=artwork_sha
        state["evidence"]["destination"]={"marketplace":"Etsy","expected_final_state":"inactive"}
        review_path=orchestrator._path("reconcile-job").parent/"visual-review"/"visual-review.json";review=json.loads(review_path.read_text())
        review["checks"].update(artwork_image_id=state["evidence"]["upload"]["printify_image_id"],artwork_image_id_matches=True,
            placement={"x":.5,"y":.46,"scale":.85,"angle":0})
        for item in review["checks"]["mockups"]:
            image=review_path.parent/{"Black":"black-front.png","Dark Grey Heather":"dark-grey-heather-front.png","White":"white-front.png"}[item["color"]]
            image.write_bytes(item["color"].encode())
        product_orchestrator._atomic_json(review_path,review);product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        return CommerceWorkflow(orchestrator),orchestrator,state,client

    def test_valid_job_creates_private_and_public_proposal_without_provider_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));result=workflow.prepare("reconcile-job")
            self.assertEqual(result["result"],"commerce_proposal_ready");self.assertEqual(result["stage"],"awaiting_final_approval")
            self.assertTrue(result["write_performed"]);self.assertFalse(result["external_write_performed"]);self.assertFalse(result["publish_performed"]);self.assertFalse(result["order_created"])
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";public=json.loads((root/"current.json").read_text());private=(root/"current-private.json")
            serialized=json.dumps(public).lower();self.assertNotIn("private-product-fixture",serialized);self.assertNotIn("upload-fixture",serialized);self.assertNotIn("1001",serialized)
            self.assertNotIn("secret:",serialized);self.assertNotIn("/home/",serialized);self.assertEqual(private.stat().st_mode&0o777,0o600)
            self.assertEqual(json.loads(private.read_text())["provider_binding"]["product_id"],"private-product-fixture")
            html=(root/"review.html").read_text();self.assertIn("NOT PUBLISHED",html);self.assertIn("NO ORDER CREATED",html);self.assertIn("AWAITING FINAL APPROVAL",html)
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called();client.create_product.assert_not_called()

    def test_prepare_is_deterministic_and_supersedes_differing_proposal(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary));first=workflow.prepare("reconcile-job");second=workflow.prepare("reconcile-job")
            self.assertEqual(first["proposal_sha256"],second["proposal_sha256"]);self.assertFalse(second["write_performed"])
            with patch.object(product_orchestrator,"ETSY_TITLE","Changed Public Title"):
                third=workflow.prepare("reconcile-job")
            self.assertNotEqual(first["proposal_sha256"],third["proposal_sha256"])
            root=orchestrator._path("reconcile-job").parent/"commerce-proposal";archived=json.loads((root/"archive"/first["proposal_sha256"]/"proposal.json").read_text())
            self.assertTrue(archived["superseded"]);self.assertFalse(archived["approval_eligible"]);self.assertEqual(archived["superseded_by"],third["proposal_sha256"])
            self.assertTrue(json.loads((root/"current.json").read_text())["approval_eligible"])

    def test_invalid_metadata_ownership_and_visual_review_create_no_artifacts(self):
        cases=("metadata","ownership","visual","mockup","published","ordered","protected","unexpected_area","variants")
        for case in cases:
            with self.subTest(case=case),tempfile.TemporaryDirectory() as temporary:
                workflow,orchestrator,state,client=self.fixture(Path(temporary));remote=client.get_product.return_value
                if case=="ownership":remote["id"]="other"
                elif case=="visual":json.loads((orchestrator._path("reconcile-job").parent/"visual-review"/"visual-review.json").read_text())
                elif case=="published":remote["is_published"]=True
                elif case=="ordered":remote["orders"]=[{"id":"order"}]
                elif case=="protected":
                    state["evidence"]["draft"]["printify_product_id"]=product_orchestrator.PROTECTED_PRODUCT_ID;product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
                elif case=="unexpected_area":remote["print_areas"][0]["placeholders"].append({"position":"sleeve","images":[{"id":"other"}]})
                elif case=="variants":next(item for item in remote["variants"] if item.get("is_enabled"))["is_enabled"]=False
                review_path=orchestrator._path("reconcile-job").parent/"visual-review"/"visual-review.json"
                if case in {"visual","mockup"}:
                    review=json.loads(review_path.read_text());review["checks"]["artwork_image_id_matches"]=False if case=="visual" else True
                    if case=="mockup":review["checks"]["mockups"][0]["downloaded_sha256"]=None
                    product_orchestrator._atomic_json(review_path,review)
                context=patch.object(product_orchestrator,"ETSY_TITLE","") if case=="metadata" else patch.object(product_orchestrator,"ETSY_TITLE",product_orchestrator.ETSY_TITLE)
                with context,self.assertRaises(Exception):workflow.prepare("reconcile-job")
                self.assertFalse((orchestrator._path("reconcile-job").parent/"commerce-proposal").exists())
                client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

    def test_status_review_and_cli_are_read_only_and_html_escapes(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary))
            with patch.object(product_orchestrator,"ETSY_TITLE","Public <Title>"):
                prepared=workflow.prepare("reconcile-job")
            before=orchestrator._path("reconcile-job").read_bytes();status=workflow.status("reconcile-job");review=workflow.review("reconcile-job")
            self.assertTrue(status["proposal_current"]);self.assertEqual(status["next_allowed_action"],"review_proposal");self.assertEqual(review["proposal_sha256"],prepared["proposal_sha256"])
            self.assertEqual(before,orchestrator._path("reconcile-job").read_bytes());self.assertIn("Public &lt;Title&gt;",Path(review["review_path"]).read_text())
            for command in ("prepare","status","review"):
                output=StringIO()
                with patch.object(sys,"argv",["jamesos.py","commerce",command,"--job-id","reconcile-job"]),redirect_stdout(output):
                    self.assertEqual(jamesos_cli._main(workflow),0)
                self.assertIn("reconcile-job",output.getvalue())
            client.update_product.assert_not_called();client.publish_product.assert_not_called();client.create_order.assert_not_called()

    def test_malformed_job_ids_fail_without_path_access(self):
        with tempfile.TemporaryDirectory() as temporary:
            workflow,orchestrator,state,client=self.fixture(Path(temporary))
            for job_id in ("", "../job", "/tmp/job", "a/b"):
                with self.subTest(job_id=job_id),self.assertRaises(Exception):workflow.status(job_id)


if __name__=="__main__":unittest.main()
