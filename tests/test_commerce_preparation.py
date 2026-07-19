from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock,patch

from fastapi.testclient import TestClient
from PIL import Image

from jamesos.core import api
from jamesos.services.commerce_preparation import UnifiedCommercePreparation
from jamesos.services.commerce_publication import CommercePublicationExecutor


class FakeOrchestrator:
    def __init__(self,root:Path):self.root=root;self.resume_calls=0;self.review_calls=0
    def _path(self,job_id):return self.root/job_id/"orchestrator-state.json"
    def load(self,job_id):return json.loads(self._path(job_id).read_text())
    def _save(self,state):
        path=self._path(state["job_id"]);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(state))
    def create(self,**kwargs):
        job_id="unified-job";candidate=self.root/job_id/"candidate.png";candidate.parent.mkdir(parents=True);candidate.write_bytes(b"candidate")
        selected={"candidate_id":"best","png_sha256":"a"*64,"png_path":str(candidate)}
        state={"job_id":job_id,"original_prompt":kwargs["prompt"],"brief":{"exact_text":"YOU ARE SAFE WITH ME","visual_style":"warm rainbow",
            "price_cents":kwargs.get("price") or 2499,"currency":"USD","garment_colors":kwargs.get("garment_colors") or ["Black"],
            "sizes":kwargs.get("sizes") or ["S"],"blank":"Bella+Canvas 3001","print_provider":"Provider"},"stage":"failed","last_error":{},
            "publish_status":"not_published","order_status":"not_created","evidence":{"candidates":[selected,{**selected,"candidate_id":"other","png_sha256":"b"*64}],
            "selection":{"selected":selected,"alternatives_considered":[]},"listing":{}},"transitions":[]}
        self._save(state);return state
    def resume(self,job_id,**kwargs):
        self.resume_calls+=1;state=self.load(job_id);state["stage"]="awaiting_human_approval"
        state["evidence"].update(upload={"printify_image_id":"private-upload","selected_design_sha256":"a"*64},
            draft={"printify_product_id":"private-product","variant_ids":list(range(18)),"publish_status":"not_published","order_status":"not_created"})
        self._save(state);return state
    def review_draft(self,job_id):
        self.review_calls+=1;path=self.root/job_id/"visual-review"/"visual-review.json";path.parent.mkdir();path.write_text("{}")
        return {"result":"reviewed"}


class FakeWorkflow:
    def __init__(self,orchestrator):self.orchestrator=orchestrator
    def prepare(self,job_id):return {"proposal_sha256":"c"*64}
    def review(self,job_id):return {"review_url":f"http://127.0.0.1:8787/commerce/proposals/{job_id}/review?session=token","review_path":"review.html"}


def profile(required=True):
    return {"profile_id":"private-profile","profile_type":"commerce_shop","configuration":{"printify_shop_id":123,
        "listing_tags":["stock market shirt","bagholder shirt","trader humor tee","investor gift","finance joke shirt","market crash tee","wall street humor","stock trader gift","buy the dip shirt","bear market shirt","bull market tee","investment humor","finance nerd gift"]}}


class UnifiedCommercePreparationTests(unittest.TestCase):
    def test_chromium_loading_path_reaches_review_after_fake_provider_preparation(self):
        chrome=shutil.which("google-chrome") or shutil.which("chromium")
        if not chrome:self.skipTest("Chrome/Chromium is required")
        with tempfile.TemporaryDirectory() as temporary:
            orchestrator=FakeOrchestrator(Path(temporary));workflow=FakeWorkflow(orchestrator);service=UnifiedCommercePreparation(orchestrator,workflow=workflow,profile_loader=profile)
            local=service.create(prompt="Create YOU ARE SAFE WITH ME",authorize_draft_work=False);ready=service.create(prompt=None,resume_job_id=local["job_id"],authorize_draft_work=True)
            status={"brand_display_name":"Fixture","printify_shop_title":"Fixture","printify_shop_id":123,"etsy_shop_slug":"Fixture","progress_label":"Ready for review","open_product_review_allowed":True,"ready_for_review":True,"failed":False}
            mocked=Mock();mocked.safe_status.return_value=status;mocked.review_snapshot.return_value={"job_id":ready["job_id"],"ready_for_review":True,"selected_candidate_id":"best","generation_method":"deterministic_local_typography","dimensions":[4500,5400],"brand_display_name":"Fixture","printify_shop_title":"Fixture","printify_product_id":"private-product","listing_title":"Market review","description":"Review description","tags":[f"tag {index}" for index in range(13)],"artwork_palette":["red"],"garment_colors":["Black"],"provider_contacted":True,"workflow_timeline":["printify_draft_ready","ready_for_review"],"publication_status":"not_published","order_status":"not_created","artwork_url":f"/commerce/jobs/{ready['job_id']}/artwork-preview"}
            shell_profile={"profile_id":"private-profile","profile_type":"commerce_shop","enabled":True,"display_name":"Fixture","configuration":{"printify_shop_id":123,"printify_shop_title":"Fixture","etsy_shop_slug":"Fixture"}}
            with patch.object(api,"CommerceCreationService",return_value=mocked),patch.object(api,"list_commerce_profiles",return_value=[shell_profile]),patch.object(api,"selected_profile_id",return_value="private-profile"),patch.object(api,"_require_local"):
                loading=TestClient(api.app,base_url="http://127.0.0.1:8787").get(f"/commerce/jobs/{ready['job_id']}/loading").text
                review_response=TestClient(api.app,base_url="http://127.0.0.1:8787").get(f"/app?view=commerce.review&job_id={ready['job_id']}")
                review_csp=review_response.headers["content-security-policy"]
                review_document=review_response.text.replace("</body>","<p id='review-location'></p><p id='preview-result'>waiting</p><script>document.getElementById('review-location').textContent=location.pathname+location.search;const preview=document.getElementById('review-artwork-preview');preview.addEventListener('load',()=>document.getElementById('preview-result').textContent=preview.naturalWidth+'x'+preview.naturalHeight+' '+preview.src)</script></body>")
            preview_path=orchestrator.root/ready["job_id"]/"preview.png";Image.new("RGB",(7,5),(120,30,20)).save(preview_path);preview_bytes=preview_path.read_bytes()
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path.endswith("/status.json"):body=json.dumps(status).encode();content="application/json"
                    elif self.path.endswith("/artwork-preview"):body=preview_bytes;content="image/png"
                    elif self.path.startswith("/app?view=commerce.review"):body=review_document.encode();content="text/html"
                    else:body=loading.encode();content="text/html"
                    self.send_response(200);self.send_header("Content-Type",content)
                    if content=="text/html":self.send_header("Content-Security-Policy",review_csp)
                    self.end_headers();self.wfile.write(body)
                def do_POST(self):
                    self.send_response(303);self.send_header("Location",f"/app?view=commerce.review&job_id={ready['job_id']}");self.end_headers()
                def log_message(self,*args):pass
            server=ThreadingHTTPServer(("127.0.0.1",0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
            try:rendered=subprocess.run([chrome,"--headless=new","--no-sandbox","--disable-gpu","--virtual-time-budget=2500","--dump-dom",f"http://127.0.0.1:{server.server_port}/commerce/jobs/{ready['job_id']}/loading"],check=True,capture_output=True,text=True).stdout
            finally:server.shutdown();server.server_close()
            self.assertIn(f"view=commerce.review&amp;job_id={ready['job_id']}",rendered);self.assertIn("7x5 http://127.0.0.1:",rendered);self.assertIn(f"/{ready['job_id']}/artwork-preview",rendered);self.assertIn("private-product",rendered);self.assertIn("Etsy tags (13)",rendered);self.assertIn("Publication:</strong> no",rendered);self.assertIn("Order:</strong> no",rendered);self.assertEqual(orchestrator.resume_calls,1);self.assertEqual(orchestrator.review_calls,0)
    def test_generated_ten_tags_are_completed_from_bound_profile_before_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            orchestrator=FakeOrchestrator(Path(temporary));workflow=FakeWorkflow(orchestrator)
            generated=[f"generated tag {index}" for index in range(10)]
            def listing(brief,selected):return {"title":"Market Humor Tee","description":"Relevant market design","tags":generated,"price_cents":2499}
            result=UnifiedCommercePreparation(orchestrator,workflow=workflow,profile_loader=profile,listing_generator=listing).create(prompt="Market humor",authorize_draft_work=False)
            state=orchestrator.load(result["job_id"])
            self.assertEqual(len(state["final_listing_tags"]),13);self.assertEqual(state["profile_fallback_tags_used"],profile()["configuration"]["listing_tags"][:3])
            self.assertEqual(orchestrator.resume_calls,0)

    def test_tag_shortage_is_persisted_and_fails_before_provider(self):
        with tempfile.TemporaryDirectory() as temporary:
            orchestrator=FakeOrchestrator(Path(temporary));workflow=FakeWorkflow(orchestrator)
            bad_profile=lambda required=True:{"profile_id":"private-profile","profile_type":"commerce_shop","configuration":{"printify_shop_id":123,"listing_tags":["bad"]}}
            def listing(brief,selected):return {"title":"","description":"Relevant design","tags":["only valid"],"price_cents":2499}
            with self.assertRaises(Exception):UnifiedCommercePreparation(orchestrator,workflow=workflow,profile_loader=bad_profile,listing_generator=listing).create(prompt="Market humor",authorize_draft_work=True)
            state=orchestrator.load("unified-job");self.assertEqual(orchestrator.resume_calls,0)
            self.assertEqual(state["final_listing_tags"],["only valid"]);self.assertTrue(state["rejected_tags"])
    def test_local_then_authorized_resume_is_bounded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            orchestrator=FakeOrchestrator(Path(temporary));workflow=FakeWorkflow(orchestrator)
            service=UnifiedCommercePreparation(orchestrator,workflow=workflow,profile_loader=profile)
            local=service.create(prompt="Create YOU ARE SAFE WITH ME",authorize_draft_work=False)
            self.assertEqual(local["stage"],"draft_authorization_required");self.assertFalse(local["external_write_performed"])
            self.assertEqual(local["listing_summary"]["tag_count"],13);self.assertEqual(orchestrator.resume_calls,0)
            ready=service.create(prompt=None,resume_job_id=local["job_id"],authorize_draft_work=True)
            self.assertEqual(ready["result"],"commerce_review_ready");self.assertEqual(ready["stage"],"awaiting_human_approval")
            self.assertEqual(ready["publication_status"],"not_published");self.assertEqual(ready["order_status"],"not_created")
            self.assertEqual(orchestrator.resume_calls,1);self.assertNotIn("private-product",json.dumps(ready))
            repeated=service.create(prompt=None,resume_job_id=local["job_id"],authorize_draft_work=True)
            self.assertEqual(repeated["proposal_sha256"],ready["proposal_sha256"]);self.assertEqual(orchestrator.resume_calls,1)
            self.assertEqual(orchestrator.review_calls,0)

    def test_blank_prompt_fails_and_publication_executor_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            service=UnifiedCommercePreparation(FakeOrchestrator(Path(temporary)),workflow=FakeWorkflow(FakeOrchestrator(Path(temporary))),profile_loader=profile)
            with self.assertRaises(Exception):service.create(prompt="  ")
        with self.assertRaises(Exception) as raised:CommercePublicationExecutor().execute(job_id="job",proposal_sha256="a"*64,approval={"approved":True})
        self.assertEqual(raised.exception.code,"PUBLICATION_EXECUTOR_NOT_CONFIGURED")


if __name__=="__main__":unittest.main()
