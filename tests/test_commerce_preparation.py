from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

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
    return {"profile_id":"private-profile","profile_type":"commerce_shop","configuration":{"printify_shop_id":123}}


class UnifiedCommercePreparationTests(unittest.TestCase):
    def test_local_then_authorized_resume_is_bounded_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            orchestrator=FakeOrchestrator(Path(temporary));workflow=FakeWorkflow(orchestrator)
            service=UnifiedCommercePreparation(orchestrator,workflow=workflow,profile_loader=profile)
            local=service.create(prompt="Create YOU ARE SAFE WITH ME",authorize_draft_work=False)
            self.assertEqual(local["stage"],"draft_authorization_required");self.assertFalse(local["external_write_performed"])
            self.assertEqual(local["listing_summary"]["tag_count"],13);self.assertEqual(orchestrator.resume_calls,0)
            ready=service.create(prompt=None,resume_job_id=local["job_id"],authorize_draft_work=True)
            self.assertEqual(ready["result"],"commerce_review_ready");self.assertEqual(ready["stage"],"awaiting_final_approval")
            self.assertEqual(ready["publication_status"],"not_published");self.assertEqual(ready["order_status"],"not_created")
            self.assertEqual(orchestrator.resume_calls,1);self.assertNotIn("private-product",json.dumps(ready))
            repeated=service.create(prompt=None,resume_job_id=local["job_id"],authorize_draft_work=True)
            self.assertEqual(repeated["proposal_sha256"],ready["proposal_sha256"]);self.assertEqual(orchestrator.resume_calls,1)
            self.assertEqual(orchestrator.review_calls,1)

    def test_blank_prompt_fails_and_publication_executor_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            service=UnifiedCommercePreparation(FakeOrchestrator(Path(temporary)),workflow=FakeWorkflow(FakeOrchestrator(Path(temporary))),profile_loader=profile)
            with self.assertRaises(Exception):service.create(prompt="  ")
        with self.assertRaises(Exception) as raised:CommercePublicationExecutor().execute(job_id="job",proposal_sha256="a"*64,approval={"approved":True})
        self.assertEqual(raised.exception.code,"PUBLICATION_EXECUTOR_NOT_CONFIGURED")


if __name__=="__main__":unittest.main()
