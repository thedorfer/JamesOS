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

    def test_safe_status_exposes_destination_not_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()));workflow=CommerceWorkflow(orch);p=profile("bagholder-supply",28275232,"BagholdersSupplyCo")
            service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p);queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="private brief",destination_confirmed=True)
            status=service.safe_status(queued["job_id"]);self.assertEqual(status["stage"],"generation_queued");self.assertEqual(status["etsy_shop_slug"],"BagholdersSupplyCo");self.assertNotIn("brief",json.dumps(status).casefold())


if __name__=="__main__":unittest.main()
