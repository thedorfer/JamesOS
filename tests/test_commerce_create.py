from __future__ import annotations

import json
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient
from PIL import Image,ImageDraw

from jamesos.core import api
from jamesos.core.errors import StateConflictError
from jamesos.core.profiles import selection
from jamesos.services.commerce_creation import CommerceCreationService,validate_product_input
from jamesos.services.commerce_workflow import CommerceWorkflow
from jamesos.services import product_orchestrator


def profile(profile_id,shop_id,slug,*,enabled=True,profile_type="commerce_shop"):
    return {"profile_id":profile_id,"profile_type":profile_type,"enabled":enabled,"display_name":profile_id.title(),"configuration":{"printify_shop_id":shop_id,"printify_shop_title":profile_id,"etsy_shop_slug":slug,"etsy_shop_url":f"https://www.etsy.com/shop/{slug}","marketplace_write_route":"printify_connected_sales_channel"}}


class CommerceCreateTests(unittest.TestCase):
    def test_product_studio_pauses_for_revision_checked_selection_then_uploads_only_approved_artwork(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);client=Mock();provider_calls=[]
            variants=[{"id":index+1,"title":f"{color} / {size}","is_available":True} for index,(color,size) in enumerate((color,size) for color in product_orchestrator.DEFAULT_COLORS for size in product_orchestrator.DEFAULT_SIZES)]
            client.get_variants.side_effect=lambda *args:(provider_calls.append("variants") or {"variants":variants});client.upload_image_contents.side_effect=lambda name,data:(provider_calls.append(("upload",name,data)) or {"id":"upload-selected"});client.list_products.side_effect=lambda *args:(provider_calls.append("list") or {"data":[]});client.create_product.side_effect=lambda *args:(provider_calls.append("create") or {"id":"draft-selected","images":[]});client.get_product.return_value={"id":"draft-selected","images":[]}
            orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=lambda:client));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");p["configuration"].update(artwork_palette=["warm cream","muted market red","muted market green"]);service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",exact_phrase="UNREALIZED LOSSES\nBUILD CHARACTER",product_brief="Bold centered typography artwork for market traders",listing_title="Unrealized Losses Shirt",special_instructions="Transparent source art; unpublished draft only",destination_confirmed=True)
            paused=service.run_generation(queued["job_id"]);self.assertEqual(paused["stage"],"artwork_review");snapshot=service.artwork_review_snapshot(queued["job_id"]);self.assertEqual((len(snapshot["candidates"]),len(snapshot["local_previews"])),(3,9));self.assertEqual(provider_calls,[]);self.assertFalse(snapshot["selected_candidate_id"])
            for candidate in snapshot["candidates"]:
                self.assertEqual(candidate["dimensions"],[4500,5400]);self.assertTrue(candidate["transparency"]);self.assertEqual(candidate["safe_margin_result"],"pass");self.assertEqual(candidate["thumbnail_readability_result"],"pass");self.assertGreaterEqual(candidate["occupied_width_ratio"],.55);self.assertLessEqual(candidate["occupied_width_ratio"],.88);self.assertGreaterEqual(candidate["occupied_height_ratio"],.22);self.assertLessEqual(candidate["occupied_height_ratio"],.78)
            self.assertEqual({item["candidate_name"] for item in snapshot["candidates"]},{"Clean centered stack","Loss emphasis","Character emphasis"});self.assertEqual({item["garment_color"] for item in snapshot["local_previews"]},{"black","navy","dark-heather"})
            selected=snapshot["candidates"][1];saved=service.select_artwork(queued["job_id"],selected["candidate_id"],selected["digest"],expected_revision=0);self.assertEqual(saved["selection_revision"],1);self.assertEqual(provider_calls,[])
            with self.assertRaises(StateConflictError):service.select_artwork(queued["job_id"],snapshot["candidates"][0]["candidate_id"],snapshot["candidates"][0]["digest"],expected_revision=0)
            result=service.continue_with_selected_artwork(queued["job_id"],expected_revision=1);self.assertEqual(result["result"],"commerce_review_ready");self.assertEqual([item if isinstance(item,str) else item[0] for item in provider_calls].count("upload"),1);self.assertEqual(provider_calls.count("create"),1)
            uploaded=next(item for item in provider_calls if isinstance(item,tuple));self.assertEqual(product_orchestrator._file_sha(Path(orch.load(queued["job_id"])["evidence"]["selection"]["selected"]["png_path"])),selected["digest"]);self.assertEqual(__import__("hashlib").sha256(base64.b64decode(uploaded[2])).hexdigest(),selected["digest"])
            with self.assertRaises(StateConflictError):service.continue_with_selected_artwork(queued["job_id"],expected_revision=1)
            self.assertEqual(orch.load(queued["job_id"])["publish_status"],"not_published");self.assertEqual(orch.load(queued["job_id"])["order_status"],"not_created");self.assertEqual(client.create_product.call_count,1)

    def test_artwork_regeneration_retains_sets_clears_selection_and_never_contacts_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider=Mock(side_effect=AssertionError("provider must not be constructed"));orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=provider));p=profile("bagholder-supply",1,"Shop");p["configuration"]["artwork_palette"]=["warm cream","muted market red","muted market green"];service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",exact_phrase="UNREALIZED LOSSES\nBUILD CHARACTER",product_brief="Bold centered typography artwork for market traders",special_instructions="No provider before selection",destination_confirmed=True);service.run_generation(queued["job_id"]);before=service.artwork_review_snapshot(queued["job_id"]);chosen=before["candidates"][0];service.select_artwork(queued["job_id"],chosen["candidate_id"],chosen["digest"],expected_revision=0)
            regenerated=service.regenerate_artwork_review(queued["job_id"]);after=service.artwork_review_snapshot(queued["job_id"]);self.assertEqual((regenerated["candidate_set_revision"],len(orch.load(queued["job_id"])["evidence"]["candidate_sets"])),(2,2));self.assertIsNone(after["selected_candidate_id"]);self.assertTrue(regenerated["selection_required"]);self.assertEqual(len(after["local_previews"]),9);provider.assert_not_called()
            replacement=after["candidates"][0];saved=service.select_artwork(queued["job_id"],replacement["candidate_id"],replacement["digest"],expected_revision=regenerated["selection_revision"]);selected_path=Path(orch.load(queued["job_id"])["evidence"]["selection"]["selected"]["png_path"]);selected_path.write_bytes(selected_path.read_bytes()+b"tampered")
            with self.assertRaises(StateConflictError):service.continue_with_selected_artwork(queued["job_id"],expected_revision=saved["selection_revision"])
            provider.assert_not_called()

    def test_artwork_review_api_requires_csrf_and_chromium_enables_continue(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required")
        with tempfile.TemporaryDirectory() as temporary:
            provider=Mock(side_effect=AssertionError("browser review must not contact provider"));orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=provider));p=profile("bagholder-supply",1,"Shop");p["configuration"]["artwork_palette"]=["warm cream","muted market red","muted market green"];service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",exact_phrase="UNREALIZED LOSSES\nBUILD CHARACTER",product_brief="Bold centered typography artwork for market traders",special_instructions="No provider before selection",destination_confirmed=True);service.run_generation(queued["job_id"]);snapshot=service.artwork_review_snapshot(queued["job_id"]);candidate=snapshot["candidates"][0]
            client=TestClient(api.app,base_url="http://127.0.0.1:8787");headers={"Origin":"http://127.0.0.1:8787"}
            with patch.object(api,"CommerceCreationService",return_value=service),patch.object(api,"list_commerce_profiles",return_value=[p]),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
                self.assertEqual(client.post(f"/commerce/jobs/{queued['job_id']}/select-artwork",json={"candidate_id":candidate["candidate_id"],"candidate_digest":candidate["digest"],"selection_revision":0},headers=headers).status_code,403)
                page=client.get(f"/app?view=commerce.artwork-review&job_id={queued['job_id']}").text
            script="""<script>window.fetch=async(url,options={})=>{const path=String(url);if(path.includes('/select-artwork'))return new Response(JSON.stringify({selection_revision:1}),{status:200,headers:{'Content-Type':'application/json'}});if(path.includes('/continue-selected-artwork')){localStorage.setItem('continued','yes');return new Response(JSON.stringify({review_url:'/final'}),{status:200,headers:{'Content-Type':'application/json'}})}return new Response('{}',{status:200,headers:{'Content-Type':'application/json'}})};document.addEventListener('DOMContentLoaded',()=>setTimeout(()=>{document.querySelector('[data-artwork-background=white]').click();localStorage.setItem('background',document.querySelector('.candidate-artwork').style.background?'yes':'no');document.querySelector('[data-select-artwork]').click();setTimeout(()=>{localStorage.setItem('selected',document.querySelector('[data-selected=true]')?'yes':'no');localStorage.setItem('enabled',document.querySelector('#continue-selected-artwork').disabled?'no':'yes');document.querySelector('#continue-selected-artwork').click()},100)},100))</script>"""
            document=page.replace("</body>",script+"</body>")
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path=="/final":body=b"<!doctype html><body><h1>Product package review</h1><p>Selected approved artwork</p><script>document.body.dataset.backgroundWorked=localStorage.getItem('background');document.body.dataset.selectionVisible=localStorage.getItem('selected');document.body.dataset.continueEnabled=localStorage.getItem('enabled');document.body.dataset.continued=localStorage.getItem('continued')</script></body>"
                    else:body=document.encode()
                    self.send_response(200);self.send_header("Content-Type","text/html");self.end_headers();self.wfile.write(body)
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
            try:rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=2500","--dump-dom",f"http://127.0.0.1:{server.server_port}/app"],capture_output=True,text=True,check=True,timeout=30).stdout
            finally:server.shutdown();server.server_close()
            self.assertIn('data-background-worked="yes"',rendered);self.assertIn('data-selection-visible="yes"',rendered);self.assertIn('data-continue-enabled="yes"',rendered);self.assertIn('data-continued="yes"',rendered);self.assertIn("Selected approved artwork",rendered);provider.assert_not_called()
    def test_artwork_preview_is_owned_read_only_png_with_safe_headers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/"jobs"/"preview-job";root.mkdir(parents=True);artwork=root/"selected.png"
            image=Image.new("RGBA",(3,2),(12,34,56,255));image.save(artwork);image.close();before=artwork.read_bytes()
            state={"evidence":{"selection":{"selected":{"candidate_id":"selected","png_path":str(artwork)}}}}
            orchestrator=Mock();orchestrator._path.side_effect=lambda job_id:Path(temporary)/"jobs"/job_id/"orchestrator-state.json";orchestrator.load.return_value=state
            service=Mock(orchestrator=orchestrator);service.review_snapshot.return_value={"selected_candidate_id":"selected"}
            client=TestClient(api.app,base_url="http://127.0.0.1:8787",client=("127.0.0.1",1234))
            with patch.object(api,"CommerceCreationService",return_value=service):
                responses=[client.get("/commerce/jobs/preview-job/artwork-preview"),client.get("/commerce/jobs/preview-job/artwork-preview",headers={"Referer":"http://127.0.0.1:8787/app?view=commerce.review"}),client.get("/commerce/jobs/preview-job/artwork-preview",headers={"Origin":"http://127.0.0.1:8787"})]
                self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview",headers={"Origin":"https://evil.example"}).status_code,403)
                self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview",headers={"Referer":"https://evil.example/review"}).status_code,403)
            for response in responses:
                self.assertEqual(response.status_code,200);self.assertEqual(response.content,before);self.assertEqual(response.headers["content-type"],"image/png");self.assertEqual(int(response.headers["content-length"]),len(before));self.assertEqual(response.headers["x-content-type-options"],"nosniff");self.assertEqual(response.headers["cache-control"],"private, no-store");self.assertNotIn(str(Path(temporary)),str(response.headers)+response.text)
            self.assertEqual(artwork.read_bytes(),before);self.assertEqual(service.review_snapshot.call_count,3)

    def test_artwork_preview_rejects_cross_job_escape_missing_and_invalid_png(self):
        with tempfile.TemporaryDirectory() as temporary:
            jobs=Path(temporary)/"jobs";foreign=jobs/"other-job"/"foreign.png";foreign.parent.mkdir(parents=True);Image.new("RGB",(1,1)).save(foreign)
            own=jobs/"preview-job";own.mkdir();state={"evidence":{"selection":{"selected":{"candidate_id":"selected","png_path":str(foreign)}}}}
            orchestrator=Mock();orchestrator._path.side_effect=lambda job_id:jobs/job_id/"orchestrator-state.json";orchestrator.load.return_value=state
            service=Mock(orchestrator=orchestrator);service.review_snapshot.return_value={"selected_candidate_id":"selected"};client=TestClient(api.app,base_url="http://127.0.0.1:8787")
            with patch.object(api,"CommerceCreationService",return_value=service):
                self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview").status_code,403)
                link=own/"escaped.png";link.symlink_to(foreign);state["evidence"]["selection"]["selected"]["png_path"]=str(link);self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview").status_code,403)
                state["evidence"]["selection"]["selected"]["png_path"]=str(own/"missing.png");self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview").status_code,404)
                invalid=own/"invalid.png";invalid.write_bytes(b"not executable and not a png");state["evidence"]["selection"]["selected"]["png_path"]=str(invalid);self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview").status_code,404)
                state["evidence"]["selection"]["selected"].pop("png_path");self.assertEqual(client.get("/commerce/jobs/preview-job/artwork-preview").status_code,404)
            service.review_snapshot.assert_called();self.assertEqual(foreign.exists(),True)

    def test_saved_mockup_route_is_job_owned_same_origin_and_read_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            jobs=Path(temporary)/"jobs";root=jobs/"preview-job";root.mkdir(parents=True);mockup=root/"front-black.jpg";Image.new("RGB",(8,6),(22,24,28)).save(mockup);before=mockup.read_bytes();digest=product_orchestrator._file_sha(mockup);asset_id=f"mockup-{digest[:20]}"
            state={"evidence":{"mockups":[{"asset_id":asset_id,"local_path":str(mockup),"sha256":digest}]}}
            orchestrator=Mock();orchestrator._path.side_effect=lambda job_id:jobs/job_id/"orchestrator-state.json";orchestrator.load.return_value=state
            service=Mock(orchestrator=orchestrator);service.review_snapshot.return_value={"mockups":[{"asset_id":asset_id}]};client=TestClient(api.app,base_url="http://127.0.0.1:8787")
            with patch.object(api,"CommerceCreationService",return_value=service):
                response=client.get(f"/commerce/jobs/preview-job/mockups/{asset_id}",headers={"Referer":"http://127.0.0.1:8787/app?view=commerce.review"})
                self.assertEqual(client.get(f"/commerce/jobs/preview-job/mockups/{asset_id}",headers={"Origin":"https://evil.example"}).status_code,403)
                service.review_snapshot.return_value={"mockups":[]};self.assertEqual(client.get(f"/commerce/jobs/other-job/mockups/{asset_id}").status_code,404)
            self.assertEqual(response.status_code,200);self.assertEqual(response.content,before);self.assertEqual(response.headers["content-type"],"image/jpeg");self.assertEqual(response.headers["cache-control"],"private, no-store");self.assertEqual(response.headers["x-content-type-options"],"nosniff");self.assertNotIn(str(Path(temporary)),str(response.headers));self.assertEqual(mockup.read_bytes(),before)

    def test_review_regeneration_versions_local_candidates_without_touching_draft(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider=Mock(side_effect=AssertionError("provider must not be constructed"));orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=provider));service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:profile(pid,1,"Shop"));job_id="review-regeneration";root=orch._path(job_id).parent;root.mkdir(parents=True);current=root/"current.png";Image.new("RGBA",(4500,5400),(0,0,0,0)).save(current);digest=product_orchestrator._file_sha(current)
            state={"job_id":job_id,"original_prompt":"Exact phrase:\nUNREALIZED LOSSES\nBUILD CHARACTER","brief":{"exact_text":"UNREALIZED LOSSES\nBUILD CHARACTER","requested_motifs":[],"negative_visual_constraints":[],"preferred_layout":"integrated_shadow","artwork_palette":"profile_guided","artwork_palette_names":["warm cream","muted market red","muted market green"],"artwork_palette_rgba":[[244,231,199,255],[174,75,72,255],[83,125,91,255]]},"stage":"awaiting_human_approval","publish_status":"not_published","order_status":"not_created","evidence":{"selection":{"selected":{"candidate_id":"current","png_path":str(current),"png_sha256":digest}},"draft":{"printify_product_id":"existing-draft","publish_status":"not_published","order_status":"not_created"}},"transitions":[]}
            product_orchestrator._atomic_json(orch._path(job_id),state);before=orch._path(job_id).read_bytes();current_before=current.read_bytes();result=service.regenerate_review_artwork(job_id);after=orch.load(job_id)
            self.assertEqual(result["candidate_count"],3);self.assertFalse(result["provider_contacted"]);self.assertEqual(after["evidence"]["draft"]["printify_product_id"],"existing-draft");self.assertEqual(after["evidence"]["selection"]["selected"]["png_sha256"],digest);self.assertEqual(current.read_bytes(),current_before);self.assertEqual(len(after["evidence"]["local_artwork_revisions"][0]["candidates"]),3);provider.assert_not_called();self.assertNotEqual(before,orch._path(job_id).read_bytes())

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
            self.assertEqual(state["product_brief"]["exact_phrase"],"UNREALIZED LOSSES\nREAL COMFORT");self.assertIn("Exact phrase:\nUNREALIZED LOSSES\nREAL COMFORT",state["original_prompt"])
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
        with patch.object(api,"list_commerce_profiles",return_value=rows) as listed,patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/commerce/new",follow_redirects=False)
        listed.assert_not_called();self.assertEqual(response.status_code,303);self.assertEqual(response.headers["location"],"/app?view=commerce.new");self.assertNotIn("Bagholder <Shop>",response.text)

    def test_new_page_does_not_change_selected_profile_pointer(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo"),profile("unitystitches",9437076,"UnityStitches")]
        with tempfile.TemporaryDirectory() as temporary:
            pointer=Path(temporary)/"selected_commerce_profile";pointer.write_text("unitystitches\n");before=pointer.read_bytes()
            with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",side_effect=lambda:pointer.read_text().strip()),patch.object(api,"_require_local"):
                response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/commerce/new",follow_redirects=False)
            self.assertEqual(response.status_code,303);self.assertEqual(response.headers["location"],"/app?view=commerce.new");self.assertEqual(pointer.read_bytes(),before)

    def test_safe_status_exposes_destination_not_prompt(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()));workflow=CommerceWorkflow(orch);p=profile("bagholder-supply",28275232,"BagholdersSupplyCo")
            service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p);queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography for market traders",destination_confirmed=True)
            status=service.safe_status(queued["job_id"]);self.assertEqual(status["stage"],"generation_queued");self.assertEqual(status["etsy_shop_slug"],"BagholdersSupplyCo");self.assertNotIn("brief",json.dumps(status).casefold())

    def test_safe_status_uses_failure_message_fallbacks(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo")
            service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p);queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography for market traders",destination_confirmed=True)
            state=orch.load(queued["job_id"]);state.update(stage="generation_failed",generation_failure={},last_error={"user_message":"Safe provider-free failure"},stage_output={"user_message":"lower priority"});product_orchestrator._atomic_json(orch._path(queued["job_id"]),state)
            status=service.safe_status(queued["job_id"]);self.assertEqual(status["failure_message_safe"],"Safe provider-free failure");self.assertTrue(status["retry_allowed"]);self.assertFalse(status["printify_draft_exists"])

    def test_both_approval_stages_are_review_ready(self):
        for stage in ("awaiting_human_approval","awaiting_final_approval"):
            with self.subTest(stage=stage),tempfile.TemporaryDirectory() as temporary:
                orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock()));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo")
                service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p);queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography for market traders",destination_confirmed=True)
                state=orch.load(queued["job_id"]);state.update(stage=stage);state["evidence"]["draft"]={"printify_product_id":"6a5ad44b1aa47d46900bf6db"};product_orchestrator._atomic_json(orch._path(queued["job_id"]),state)
                status=service.safe_status(queued["job_id"]);self.assertTrue(status["ready_for_review"]);self.assertTrue(status["open_product_review_allowed"]);self.assertFalse(status["resume_existing_draft_allowed"])

    def test_loading_page_automatically_posts_open_review(self):
        status={"brand_display_name":"Bagholder Supply Co","printify_shop_title":"BagholderSupplyCo","printify_shop_id":28275232,"etsy_shop_slug":"BagholdersSupplyCo","progress_label":"Ready for review"}
        service=Mock();service.safe_status.return_value=status
        with patch.object(api,"CommerceCreationService",return_value=service),patch.object(api,"_require_local"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/commerce/jobs/review-job/loading")
        self.assertEqual(response.status_code,200);self.assertIn("action='/commerce/jobs/review-job/open-review'",response.text);self.assertIn("requestSubmit()",response.text)
        self.assertNotIn(">Open product review<",response.text);self.assertIn("Continue to product review",response.text)

    def test_open_review_post_redirects_and_obsolete_resume_is_safe(self):
        service=Mock();service.open_product_review.return_value={"review_url":"/commerce/proposals/job/review?session=fresh"}
        service.safe_status.return_value={"open_product_review_allowed":True,"resume_existing_draft_allowed":False}
        client=TestClient(api.app,base_url="http://127.0.0.1:8787")
        headers={"Origin":"http://127.0.0.1:8787"}
        with patch.object(api,"CommerceCreationService",return_value=service),patch.object(api,"_require_local"):
            opened=client.post("/commerce/jobs/job/open-review",data={"csrf_token":api._COMMERCE_CREATE_CSRF},headers=headers,follow_redirects=False)
            obsolete=client.post("/commerce/jobs/job/resume-existing-draft",data={"csrf_token":api._COMMERCE_CREATE_CSRF},headers=headers,follow_redirects=False)
            get_resume=client.get("/commerce/jobs/job/resume-existing-draft",follow_redirects=False)
        self.assertEqual(opened.status_code,303);self.assertEqual(opened.headers["location"],"/commerce/proposals/job/review?session=fresh");service.open_product_review.assert_called_once_with("job")
        self.assertEqual(obsolete.status_code,303);self.assertEqual(obsolete.headers["location"],"/commerce/jobs/job/loading");service.resume_existing_draft.assert_not_called()
        self.assertEqual(get_resume.status_code,303);self.assertEqual(get_resume.headers["location"],"/commerce/jobs/job/loading");self.assertNotIn("application/json",get_resume.headers.get("content-type",""))

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
                "publish_status":"not_published","order_status":"not_created","evidence":{"upload":{"printify_image_id":"upload-1"},"draft":{"printify_product_id":"existing-product","draft_marker":"job-marker"},"mockups":[{"local_path":str(mockup)}]},
                "transitions":[{"stage":"printify_draft_created","result":"completed"},{"stage":"awaiting_human_approval","result":"completed"}]}
            product_orchestrator._atomic_json(orch._path(job_id),state);product_orchestrator._atomic_json(job_root/"unified-preparation.json",{"job_id":job_id,"profile_id":"bagholder-supply","provider_actions":[{"status":"completed","uncertain":False,"response_evidence":{"draft_recorded":True}}]})
            orch.review_draft=Mock()
            status=service.safe_status(job_id);self.assertEqual(status["terminal_outcome"],"review_ready");self.assertTrue(status["open_product_review_allowed"]);self.assertFalse(status["resume_existing_draft_allowed"])
            first=service.open_product_review(job_id);self.assertEqual(first["printify_product_id"],"existing-product");self.assertEqual(orch.load(job_id)["stage"],"awaiting_human_approval")
            second=service.open_product_review(job_id);self.assertEqual(second["printify_product_id"],"existing-product");self.assertEqual(workflow.review.call_count,0)
            orch.review_draft.assert_not_called();workflow.prepare.assert_not_called();client.create_product.assert_not_called();client.update_product.assert_not_called()

    def test_authoritative_review_reconciliation_is_local_and_product_id_alone_is_insufficient(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);provider=Mock(side_effect=AssertionError("review reconciliation must not contact provider"));orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=provider));workflow=Mock(orchestrator=orch);p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p)
            def state(job_id,authoritative):
                value={"job_id":job_id,"commerce_profile_id":"bagholder-supply","shop_id":28275232,"destination":{"printify_shop_id":28275232,"printify_shop_title":"Bagholders"},"stage":"generation_failed","provider_write_status":"not_started","generation_failure":{"safe_message":"presentation failed"},"publish_status":"not_published","order_status":"not_created","evidence":{"upload":{"printify_image_id":"upload-1"},"draft":{"printify_product_id":"draft-1"}},"transitions":[]}
                if authoritative:value["transitions"]=[{"stage":"printify_draft_created","result":"completed"},{"stage":"awaiting_human_approval","result":"completed"}]
                product_orchestrator._atomic_json(orch._path(job_id),value)
                if authoritative:product_orchestrator._atomic_json(orch._path(job_id).parent/"unified-preparation.json",{"job_id":job_id,"profile_id":"bagholder-supply","provider_actions":[{"status":"completed","uncertain":False,"response_evidence":{"draft_recorded":True}}]})
            state("product-authoritative",True);status=service.safe_status("product-authoritative");self.assertTrue(status["ready_for_review"]);self.assertFalse(status["failed"]);self.assertEqual(status["provider_write_status"],"completed");self.assertIn("job_id=product-authoritative",status["review_url"]);self.assertTrue((orch._path("product-authoritative").parent/"review-reconciliation.json").is_file())
            state("product-id-only",False);status=service.safe_status("product-id-only");self.assertTrue(status["failed"]);self.assertEqual(status["provider_write_status"],"not_started");provider.assert_not_called()

    def test_uncertain_journal_does_not_reconcile_review_ready_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=Mock(side_effect=AssertionError("no provider"))));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p);job_id="product-uncertain"
            state={"job_id":job_id,"commerce_profile_id":"bagholder-supply","stage":"generation_failed","provider_write_status":"not_started","publish_status":"not_published","order_status":"not_created","evidence":{"upload":{"printify_image_id":"upload"},"draft":{"printify_product_id":"draft"}},"transitions":[{"stage":"printify_draft_created","result":"completed"},{"stage":"awaiting_human_approval","result":"completed"}]};product_orchestrator._atomic_json(orch._path(job_id),state);product_orchestrator._atomic_json(orch._path(job_id).parent/"unified-preparation.json",{"job_id":job_id,"profile_id":"bagholder-supply","provider_actions":[{"status":"completed","uncertain":True,"response_evidence":{"draft_recorded":True}}]})
            status=service.safe_status(job_id);self.assertTrue(status["failed"]);self.assertFalse((orch._path(job_id).parent/"review-reconciliation.json").exists())

    def test_background_failure_is_persisted_and_never_reraised(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=Mock()));workflow=Mock(orchestrator=orch)
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(workflow,profile_loader=lambda pid,required=True:p);job_id="background-failure"
            state={"job_id":job_id,"commerce_profile_id":"bagholder-supply","shop_id":28275232,"destination":{"printify_shop_id":28275232},"stage":"preparing_listing","publish_status":"not_published","order_status":"not_created","evidence":{},"transitions":[]}
            product_orchestrator._atomic_json(orch._path(job_id),state);service.run_generation=Mock(side_effect=StateConflictError("STATE_CONFLICT",diagnostic_message="expected background failure",operation="test",stage="background"))
            with patch("jamesos.services.commerce_creation.handle_error",return_value={}):self.assertIsNone(service.run_generation_background(job_id))
            saved=orch.load(job_id);self.assertEqual(saved["stage"],"generation_failed");self.assertEqual(saved["generation_failure"]["safe_message"],"Product generation did not complete.")
            status=service.safe_status(job_id);self.assertTrue(status["failed"]);self.assertIsNotNone(status["failure_message_safe"])

    def test_product_input_preflight_rejects_placeholders_repetition_and_punctuation(self):
        for phrase,brief,reason in (("sdf","asdf","placeholder_text"),("","test test test test","repeated_tokens"),("","!!! ... ???","insufficient_alphabetic_content")):
            with self.subTest(brief=brief),self.assertRaises(Exception) as raised:validate_product_input(phrase,brief)
            self.assertIn(reason,raised.exception.context["product_input_preflight"]["reasons"])
            self.assertEqual(raised.exception.context["image_generation_calls"],0);self.assertEqual(raised.exception.context["provider_calls"],0)

    def test_product_input_preflight_accepts_intentional_slogan_or_no_phrase(self):
        first=validate_product_input("HODL", "Bold centered retro typography for long-term market investors")
        second=validate_product_input("", "Playful illustrated badge composition for gardening teachers on a dark tee")
        self.assertGreaterEqual(first["meaningful_word_count"],3);self.assertIn("typography",first["design_attributes"])
        self.assertIn("composition",second["design_attributes"])

    def test_invalid_form_preserves_values_and_queues_no_background_work(self):
        rows=[profile("bagholder-supply",28275232,"BagholdersSupplyCo")];background=Mock()
        client=TestClient(api.app,base_url="http://127.0.0.1:8787");headers={"Origin":"http://127.0.0.1:8787"}
        with patch.object(api,"list_commerce_profiles",return_value=rows),patch.object(api,"selected_profile_id",return_value="bagholder-supply"),patch.object(api,"_require_local"),patch.object(api,"handle_error",return_value={}) as persisted:
            response=client.post("/commerce/new",data={"csrf_token":api._COMMERCE_CREATE_CSRF,"commerce_profile_id":"bagholder-supply","exact_phrase":"sdf","product_brief":"asdf","listing_title":"Keep me","special_instructions":"asdf","destination_confirmed":"true"},headers=headers)
        self.assertEqual(response.status_code,422);self.assertIn("Add a clearer visual style",response.text);self.assertIn(">asdf</textarea>",response.text);self.assertIn("value='Keep me'",response.text)
        persisted.assert_called_once();background.assert_not_called()

    def test_candidate_rejections_persist_categories_and_safe_summary(self):
        candidates=[{"candidate_id":"one","composition_family":"stacked","prompt_validation":{"compliant":False,"reason":"phrase missing"},"png_path":"/missing","png_sha256":"x"}]
        prior=[{"candidate_id":"old","composition_family":"stacked","treatment_id":None,"png_path":"/also-missing","png_sha256":"x","job_id":"old-job"}]
        with self.assertRaises(Exception) as raised:product_orchestrator.validate_candidate_set(candidates,{},prior)
        report=raised.exception.context["candidate_diversity"];categories={item["category"] for item in report["candidates"][0]["rejection_reasons"]}
        self.assertEqual(categories,{"prompt_adherence","novelty"});self.assertIn("prompt adherence",raised.exception.user_message);self.assertIn("novelty",raised.exception.user_message)

    def test_candidate_failure_summary_is_exposed_by_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock(side_effect=AssertionError("no provider"))))
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography for market traders",destination_confirmed=True)
            error=StateConflictError("STATE_CONFLICT",user_message="Artwork candidates were rejected: 2 for prompt adherence and 1 for novelty.",operation="test",stage="design_candidates_ready",context={"candidate_diversity":{"candidates":[{"candidate_id":"one","rejection_reasons":[{"category":"prompt_adherence","reason":"phrase missing"}]}]}})
            orch.resume=Mock(side_effect=error)
            with self.assertRaises(StateConflictError):service.run_generation(queued["job_id"])
            saved=orch.load(queued["job_id"]);self.assertEqual(saved["evidence"]["candidate_diversity"]["candidates"][0]["candidate_id"],"one")
            self.assertIn("prompt adherence",service.safe_status(queued["job_id"])["failure_message_safe"])

    def test_browser_parsing_preserves_two_line_phrase_and_background_boundary_does_not_raise(self):
        service=Mock();service.create_job.return_value={"job_id":"multiline-job"};service.run_generation_safely.return_value=None
        client=TestClient(api.app,base_url="http://127.0.0.1:8787");headers={"Origin":"http://127.0.0.1:8787"}
        with patch.object(api,"CommerceCreationService",return_value=service),patch.object(api,"_require_local"),patch("jamesos.services.commerce_creation.handle_error",return_value={}):
            response=client.post("/commerce/new",data={"csrf_token":api._COMMERCE_CREATE_CSRF,"commerce_profile_id":"bagholder-supply","exact_phrase":"UNREALIZED LOSSES\r\nREAL COMFORT","product_brief":"Bold centered typography for market traders","destination_confirmed":"true"},headers=headers,follow_redirects=False)
        self.assertEqual(response.status_code,303);self.assertEqual(service.create_job.call_args.kwargs["exact_phrase"],"UNREALIZED LOSSES\r\nREAL COMFORT");service.run_generation_safely.assert_called_once_with("multiline-job");service.run_generation.assert_not_called()

    def test_terminal_local_status_has_completed_stage_and_safe_fields(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock(side_effect=AssertionError("no provider"))))
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography for market traders",destination_confirmed=True)
            state=orch.load(queued["job_id"]);state.update(stage="generation_failed",generation_failure={"safe_message":"All candidates omitted the required phrase ‘REAL COMFORT’.","last_completed_stage":"production_artifact_ready","terminal_local_failure":True});product_orchestrator._atomic_json(orch._path(queued["job_id"]),state)
            status=service.safe_status(queued["job_id"]);self.assertEqual(status["last_completed_stage"],"production_artifact_ready");self.assertEqual(status["provider_write_status"],"not_started");self.assertEqual(status["return_to_form_url"],"/app?view=commerce.new");self.assertTrue(status["retry_allowed"]);self.assertFalse(status["printify_draft_exists"]);self.assertEqual(status["publication_status"],"not_published");self.assertEqual(status["order_status"],"not_created")

    def test_failed_artwork_status_has_sanitized_candidate_diagnostics(self):
        with tempfile.TemporaryDirectory() as temporary:
            orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=Mock(side_effect=AssertionError("no provider"))));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography artwork palette for market traders",destination_confirmed=True);state=orch.load(queued["job_id"]);state.update(stage="generation_failed",generation_failure={"safe_message":"No eligible artwork.","last_completed_stage":"brief_ready","terminal_local_failure":True});product_orchestrator._atomic_json(orch._path(queued["job_id"]),state)
            diagnostic=service.safe_status(queued["job_id"])["artwork_diagnostics"];self.assertEqual((diagnostic["candidate_count"],diagnostic["accepted_candidate_count"],diagnostic["rejected_candidate_count"]),(0,0,0));self.assertEqual(diagnostic["zero_candidate_rejection"]["code"],"no_output");self.assertNotIn(str(Path(temporary)),json.dumps(diagnostic))

    def test_novelty_failure_reports_generated_candidates_and_real_failed_stage(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orch=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=Mock(side_effect=AssertionError("no provider"))));p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",exact_phrase="UNREALIZED LOSSES\nBUILD CHARACTER",product_brief="Bold centered typography artwork for market traders",destination_confirmed=True);state=orch.load(queued["job_id"]);candidate_root=root/"candidate";candidate_root.mkdir()
            candidates=[]
            for index,name in enumerate(("prompt_centered","prompt_balanced","prompt_compact")):
                path=candidate_root/f"{name}.png";image=Image.new("RGBA",(40,40),(0,0,0,0));ImageDraw.Draw(image).rectangle((5+index,5,30,35),fill="white");image.save(path);image.close()
                novelty={"comparison_scope":"authoritative_completed_products","authoritative_reference_count":1,"nearest_comparison_safe_id":"artwork:reference:approved","similarity_metric":"occupied_alpha_grayscale_similarity","similarity_score":1.0,"threshold":.9,"status":"duplicate_authoritative_artifact","rejection_code":"duplicate_authoritative_artifact","reuse_decision":"new_candidate"}
                candidates.append({"candidate_id":name,"job_id":queued["job_id"],"png_path":str(path),"png_sha256":product_orchestrator._file_sha(path),"quality_checks":{"hard_dimensions":True,"hard_novelty":False,"hard_prompt_adherence":True},"novelty_evidence":novelty})
            state["evidence"]={"candidates":candidates,"candidate_diversity":{"candidate_count":3,"rejected_for_prompt_mismatch":0,"rejected_for_similarity":3,"candidates":[{"candidate_id":item["candidate_id"],"eligible":False,"novelty_diagnostics":item["novelty_evidence"],"rejection_reasons":[{"category":"novelty","reason":"duplicate_authoritative_artifact"}]} for item in candidates]}}
            state.update(stage="generation_failed",generation_failure={"safe_message":"Artwork candidates were rejected: 0 for prompt adherence and 3 for novelty.","last_completed_stage":"production_artifact_ready","failed_stage":"design_candidates_ready","terminal_local_failure":True});product_orchestrator._atomic_json(orch._path(queued["job_id"]),state)
            status=service.safe_status(queued["job_id"]);diagnostic=status["artwork_diagnostics"]
            self.assertEqual(status["failed_stage"],"design_candidates_ready");self.assertEqual((diagnostic["generated_candidate_count"],diagnostic["technically_eligible_count"],diagnostic["prompt_adherence_rejected_count"],diagnostic["novelty_rejected_count"]),(3,3,0,3));self.assertIsNone(diagnostic["zero_candidate_rejection"]);self.assertEqual(diagnostic["image_generation_readiness"],"ready");self.assertNotIn(str(root),json.dumps(diagnostic))

    def test_no_eligible_selection_is_persisted_without_reraising(self):
        with tempfile.TemporaryDirectory() as temporary:
            provider=Mock(side_effect=AssertionError("no provider"));orch=product_orchestrator.ProductOrchestrator(Path(temporary)/"jobs",product_orchestrator.Adapters(client_factory=provider))
            p=profile("bagholder-supply",28275232,"BagholdersSupplyCo");service=CommerceCreationService(CommerceWorkflow(orch),profile_loader=lambda pid,required=True:p)
            queued=service.create_job(commerce_profile_id="bagholder-supply",product_brief="Bold centered typography for market traders",destination_confirmed=True);orch.resume=Mock(return_value={})
            result=service.run_generation(queued["job_id"]);self.assertEqual(result["result"],"generation_failed");self.assertEqual(result["provider_write_status"],"not_started")
            state=orch.load(queued["job_id"]);self.assertEqual(state["stage"],"generation_failed");self.assertTrue(state["generation_failure"]["terminal_local_failure"]);provider.assert_not_called()


if __name__=="__main__":unittest.main()
