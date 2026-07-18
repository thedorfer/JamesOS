from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.core.profiles import selection
from jamesos.services.commerce_creation import CommerceCreationService
from jamesos.services.commerce_workflow import CommerceWorkflow
from jamesos.services import product_orchestrator


def profile(profile_id,shop_id,slug,*,enabled=True,profile_type="commerce_shop"):
    return {"profile_id":profile_id,"profile_type":profile_type,"enabled":enabled,"display_name":profile_id.title(),"configuration":{"printify_shop_id":shop_id,"printify_shop_title":profile_id,"etsy_shop_slug":slug,"etsy_shop_url":f"https://www.etsy.com/shop/{slug}","marketplace_write_route":"printify_connected_sales_channel"}}


class CommerceCreateTests(unittest.TestCase):
    def test_profile_listing_and_safe_id_loading(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/"bagholder-supply.json").write_text(json.dumps(profile("bagholder-supply",28275232,"BagholdersSupplyCo")))
            (root/"unitystitches.json").write_text(json.dumps(profile("unitystitches",9437076,"UnityStitches")));(root/"disabled.json").write_text(json.dumps(profile("disabled",1,"Disabled",enabled=False)))
            (root/"notes.json").write_text(json.dumps(profile("notes",2,"Notes",profile_type="personal")))
            with patch.object(selection,"PROFILES_ROOT",root):
                self.assertEqual([x["profile_id"] for x in selection.list_commerce_profiles()],["bagholder-supply","unitystitches"])
                self.assertEqual(selection.load_commerce_profile_by_id("bagholder-supply",required=True)["configuration"]["printify_shop_id"],28275232)
                for unsafe in ("../secret","/tmp/x","a/b","..","%2e%2e"):
                    with self.subTest(unsafe=unsafe),self.assertRaises(Exception):selection.load_commerce_profile_by_id(unsafe,required=True)

    def test_create_job_binds_destination_without_provider_or_global_pointer(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);client=Mock(side_effect=AssertionError("provider must not be constructed"));orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=client));workflow=CommerceWorkflow(orch)
            profiles={"bagholder-supply":profile("bagholder-supply",28275232,"BagholdersSupplyCo"),"unitystitches":profile("unitystitches",9437076,"UnityStitches")}
            service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:profiles[pid]);before="unitystitches"
            queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Market terminal workwear",exact_phrase="UNREALIZED LOSSES\nREAL COMFORT",destination_confirmed=True,request_id="request-1")
            state=orch.load(queued["job_id"]);self.assertEqual(state["stage"],"generation_queued");self.assertEqual(state["shop_id"],28275232);self.assertEqual(state["destination"]["etsy_shop_slug"],"BagholdersSupplyCo");self.assertEqual(before,"unitystitches");client.assert_not_called()
            profiles["unitystitches"]["configuration"]["printify_shop_id"]=999
            self.assertEqual(orch.load(queued["job_id"])["destination"]["printify_shop_id"],28275232)
            repeated=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Market terminal workwear",destination_confirmed=True,request_id="request-1");self.assertTrue(repeated["already_exists"])

    def test_create_validation_rejects_disabled_missing_brief_and_traversal(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()))
            profiles={"disabled":profile("disabled",1,"Disabled",enabled=False)};service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:profiles[pid])
            with self.assertRaises(Exception):service.create_job(commerce_profile_id="disabled",product_brief="brief",destination_confirmed=True)
            service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:profile(pid,1,"Shop"))
            with self.assertRaises(Exception):service.create_job(commerce_profile_id="valid",product_brief="",destination_confirmed=True)
            with self.assertRaises(Exception):selection.load_commerce_profile_by_id("../bad",required=True)

    def test_new_page_lists_radio_cards_and_escapes_values(self):
        rows=[profile("unitystitches",9437076,"UnityStitches"),profile("bagholder-supply",28275232,"BagholdersSupplyCo")]
        rows[1]["display_name"]="Bagholder <Shop>"
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/commerce/new")
        self.assertEqual(response.status_code,200);self.assertEqual(response.text.count("type='radio'"),2);self.assertIn("28275232",response.text);self.assertIn("9437076",response.text);self.assertIn("Bagholder &lt;Shop&gt;",response.text);self.assertNotIn("Bagholder <Shop>",response.text)
        self.assertIn("JamesOS Product Studio",response.text);self.assertNotIn("Commerce Copilot",response.text);self.assertIn("Ask Product Studio",response.text)
        self.assertIn("Thinking…",response.text);self.assertIn("if(inFlight)return",response.text);self.assertNotIn("11434",response.text);self.assertIn("data-request-state='idle'",response.text)

    def test_safe_status_exposes_destination_not_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()));workflow=CommerceWorkflow(orch);p=profile("bagholder-supply",28275232,"BagholdersSupplyCo")
            service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p);queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="private brief",destination_confirmed=True)
            status=service.safe_status(queued["job_id"]);self.assertEqual(status["stage"],"generation_queued");self.assertEqual(status["etsy_shop_slug"],"BagholdersSupplyCo");self.assertNotIn("brief",json.dumps(status).casefold())

    def test_safe_status_uses_failure_message_fallbacks(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo")
            service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p);queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="private brief",destination_confirmed=True)
            state=orch.load(queued["job_id"]);state.update(stage="generation_failed",generation_failure={},last_error={"user_message":"Safe provider-free failure"},stage_output={"user_message":"lower priority"});product_orchestrator._atomic_json(orch._path(queued["job_id"]),state)
            status=service.safe_status(queued["job_id"]);self.assertEqual(status["failure_message_safe"],"Safe provider-free failure");self.assertTrue(status["retry_allowed"]);self.assertFalse(status["printify_draft_exists"])

    def test_existing_draft_resume_uses_bound_shop_and_never_creates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);client=Mock();client.get_product.return_value={"id":"existing-product","shop_id":28275232,"title":"Draft","tags":["job-marker"]}
            client.create_product.side_effect=AssertionError("must not create a second product")
            orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=lambda:client));workflow=Mock(orchestrator=orch)
            workflow.prepare.return_value={"proposal_sha256":"a"*64};workflow.review.return_value={"review_url":"/review/existing"}
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p)
            job_id="existing-draft";state={"job_id":job_id,"commerce_profile_id":"bagholder-supply","shop_id":28275232,"destination":{"printify_shop_id":28275232},
                "stage":"generation_failed","generation_failure":{"external_result_uncertain":False},"publish_status":"not_published","order_status":"not_created","revision_number":0,
                "evidence":{"draft":{"printify_product_id":"existing-product","draft_marker":"job-marker"}},"transitions":[]}
            product_orchestrator._atomic_json(orch._path(job_id),state);journal=orch._path(job_id).parent/"unified-preparation.json"
            product_orchestrator._atomic_json(journal,{"job_id":job_id,"profile_id":"bagholder-supply","provider_actions":[{"status":"completed","uncertain":False}]})
            resumed={**state,"stage":"awaiting_human_approval"};orch.resume=Mock(return_value=resumed);orch.review_draft=Mock(return_value={"result":"reviewed"})
            result=service.resume_existing_draft(job_id)
            self.assertTrue(result["existing_product_reused"]);client.get_product.assert_called_once_with(28275232,"existing-product");client.create_product.assert_not_called();orch.review_draft.assert_called_once_with(job_id)
            orch.resume.assert_called_once_with(job_id,confirm_printify_draft=True);workflow.prepare.assert_called_once_with(job_id)
            state["stage"]="awaiting_final_approval";product_orchestrator._atomic_json(orch._path(job_id),state)
            repeated=service.resume_existing_draft(job_id);self.assertTrue(repeated["already_completed"]);self.assertEqual(orch.resume.call_count,1)

    def test_uncertain_existing_draft_requires_manual_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);client=Mock(side_effect=AssertionError("uncertain recovery must not call provider"));orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=client));workflow=Mock(orchestrator=orch)
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p);job_id="uncertain-draft"
            state={"job_id":job_id,"commerce_profile_id":"bagholder-supply","shop_id":28275232,"destination":{"printify_shop_id":28275232},"stage":"generation_failed","publish_status":"not_published","order_status":"not_created","evidence":{"draft":{"printify_product_id":"existing-product"}},"transitions":[]}
            product_orchestrator._atomic_json(orch._path(job_id),state);product_orchestrator._atomic_json(orch._path(job_id).parent/"unified-preparation.json",{"job_id":job_id,"profile_id":"bagholder-supply","provider_actions":[{"status":"uncertain","uncertain":True}]})
            with self.assertRaises(Exception) as raised:service.resume_existing_draft(job_id)
            self.assertIn("Manual verification required",raised.exception.diagnostic_message);client.assert_not_called()
            status=service.safe_status(job_id);self.assertTrue(status["manual_verification_required"]);self.assertFalse(status["resume_existing_draft_allowed"])

    def test_review_ready_history_opens_same_product_without_provider_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);client=Mock();client.get_product.return_value={"id":"existing-product","shop_id":28275232,"title":"Draft job-marker","tags":[],"order_status":"not_created"}
            client.create_product.side_effect=AssertionError("review open must not create");client.update_product.side_effect=AssertionError("review open must not update")
            orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=lambda:client));workflow=Mock(orchestrator=orch)
            workflow.review.side_effect=lambda job_id:{"review_url":f"/review/{job_id}/{workflow.review.call_count}","proposal_sha256":"a"*64}
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p);job_id="review-ready"
            job_root=orch._path(job_id).parent;mockup=job_root/"mockup.jpg";mockup.parent.mkdir(parents=True);mockup.write_bytes(b"image")
            visual=job_root/"visual-review"/"visual-review.json";visual.parent.mkdir();visual.write_text(json.dumps({"product_id":"existing-product"}))
            proposal=job_root/"commerce-proposal"/"current.json";proposal.parent.mkdir();proposal.write_text(json.dumps({"proposal_sha256":"a"*64,"approval_eligible":True,"superseded":False}))
            state={"job_id":job_id,"commerce_profile_id":"bagholder-supply","shop_id":28275232,"destination":{"printify_shop_id":28275232},"stage":"generation_failed",
                "publish_status":"not_published","order_status":"not_created","evidence":{"draft":{"printify_product_id":"existing-product","draft_marker":"job-marker"},"mockups":[{"local_path":str(mockup)}]},
                "transitions":[{"stage":"awaiting_human_approval","result":"completed"}]}
            product_orchestrator._atomic_json(orch._path(job_id),state);product_orchestrator._atomic_json(job_root/"unified-preparation.json",{"job_id":job_id,"profile_id":"bagholder-supply","provider_actions":[{"status":"completed","uncertain":False}]})
            orch.review_draft=Mock()
            status=service.safe_status(job_id);self.assertEqual(status["terminal_outcome"],"review_ready");self.assertTrue(status["open_product_review_allowed"]);self.assertFalse(status["resume_existing_draft_allowed"])
            first=service.open_product_review(job_id);self.assertEqual(first["printify_product_id"],"existing-product");self.assertEqual(orch.load(job_id)["stage"],"awaiting_final_approval")
            second=service.open_product_review(job_id);self.assertTrue(second["already_completed"]);self.assertEqual(workflow.review.call_count,2)
            orch.review_draft.assert_not_called();workflow.prepare.assert_not_called();client.create_product.assert_not_called();client.update_product.assert_not_called()


if __name__=="__main__":unittest.main()
