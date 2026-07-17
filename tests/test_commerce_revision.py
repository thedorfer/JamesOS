from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from PIL import Image,ImageDraw

from jamesos.services import product_orchestrator
from jamesos.services.commerce_revision import CommerceRevisionService


class FakeClient:
    def __init__(self,remote,*,fail_upload=False):self.remote=deepcopy(remote);self.upload_count=0;self.update_count=0;self.create_product=Mock(side_effect=AssertionError("must not create product"));self.fail_upload=fail_upload
    def get_product(self,shop_id,product_id):return deepcopy(self.remote)
    def upload_image_contents(self,name,contents):
        self.upload_count+=1
        if self.fail_upload:raise RuntimeError("ambiguous upload")
        return {"id":"revision-upload"}
    def update_product(self,shop_id,product_id,payload):
        self.update_count+=1;self.remote.update({key:deepcopy(value) for key,value in payload.items()});return {"id":product_id}


class FakeWorkflow:
    def __init__(self,orchestrator):self.orchestrator=orchestrator;self.prepares=0;self.reviews=0
    def prepare(self,job_id):self.prepares+=1;state=self.orchestrator.load(job_id);state["stage"]="awaiting_final_approval";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state);return {"proposal_sha256":"b"*64}
    def review(self,job_id):self.reviews+=1;return {"review_url":f"http://127.0.0.1:8787/commerce/proposals/{job_id}/review?session=fresh"}


class CommerceRevisionTests(unittest.TestCase):
    def fixture(self,root:Path,*,fail_upload=False):
        job="revision-job";job_root=root/job;old=job_root/"old.png";old.parent.mkdir(parents=True);Image.new("RGBA",(200,200),(20,20,20,255)).save(old)
        old_candidate={"candidate_id":"old","png_path":str(old),"png_sha256":product_orchestrator._file_sha(old),"composition_family":"badge","treatment_id":"badge-v1"}
        variants=[{"id":item,"price":2499,"is_enabled":item<18,"sku":f"sku-{item}"} for item in range(318)];desired=list(range(18))
        remote={"id":"existing-product","shop_id":123,"blueprint_id":12,"print_provider_id":29,"is_locked":False,"visible":True,"variants":variants,
            "print_areas":[{"variant_ids":list(range(318)),"placeholders":[{"position":"front","images":[{"id":"old-upload","x":.5,"y":.46,"scale":.85,"angle":0}]}]}],"orders":[],"order_status":"not_created","images":[]}
        client=FakeClient(remote,fail_upload=fail_upload)
        def evidence(state,path,brief):
            source=path/"revision-source.png";Image.new("RGBA",(4500,5400),(0,0,0,0)).save(source)
            return {"candidate":source,"candidate_sha":product_orchestrator._file_sha(source),"approval_sha":"a"*64,"origin":"independent_prompt","production":{"canvas_dimensions":[4500,5400]}}
        def candidates(generated,path,brief):
            path.mkdir(parents=True,exist_ok=True);rows=[]
            for index,family in enumerate(("stacked_left","diagonal_ribbon","split_columns")):
                target=path/f"candidate-{index}.png";image=Image.new("RGBA",(200,200),(0,0,0,0));draw=ImageDraw.Draw(image)
                if index==0:draw.rectangle((20,20,70,180),fill=(91,206,250,255));draw.rectangle((130,20,180,180),fill=(245,169,184,255))
                elif index==1:draw.polygon(((10,80),(190,20),(190,70),(10,130)),fill=(245,169,184,255))
                else:draw.rectangle((20,20,180,50),fill=(91,206,250,255));draw.rectangle((20,150,180,180),fill=(245,169,184,255))
                image.save(target);image.close();rows.append({"candidate_id":f"candidate-{index}","png_path":str(target),"png_sha256":product_orchestrator._file_sha(target),
                    "composition_family":family,"layout_id":family,"treatment_id":family,"quality_checks":{"hard_phrase_correct":True,"hard_safe_bounds":True,"hard_artwork_integrity":True},
                    "prompt_validation":{"compliant":True,"negative_constraint_violations":[]},"prompt_adherence_score":40,"thumbnail_readability_score":10,"garment_contrast_score":10,"balanced_bounds_score":10})
            return rows
        adapters=product_orchestrator.Adapters(independent_evidence=evidence,independent_candidates=candidates,client_factory=lambda:client)
        orchestrator=product_orchestrator.ProductOrchestrator(root,adapters)
        state={"job_id":job,"shop_id":123,"profile_id":"profile","selected_profile_id":"profile","stage":"revision_requested","original_prompt":"TRANS RIGHTS ARE HUMAN RIGHTS",
            "brief":{"exact_text":"TRANS RIGHTS ARE HUMAN RIGHTS","price_cents":2499,"garment_colors":product_orchestrator.DEFAULT_COLORS,"sizes":product_orchestrator.DEFAULT_SIZES},
            "publish_status":"not_published","order_status":"not_created","transitions":[],"evidence":{"candidates":[old_candidate],"selection":{"selected":old_candidate},
                "upload":{"printify_image_id":"old-upload","selected_design_sha256":old_candidate["png_sha256"]},"draft":{"printify_product_id":"existing-product","variant_ids":desired,"publish_status":"not_published","order_status":"not_created"},
                "variant_selection":{"selected_variant_ids":desired},"draft_marker":"marker","listing":{"title":"old"}}}
        product_orchestrator._atomic_json(orchestrator._path(job),state);proposal=job_root/"commerce-proposal";proposal.mkdir()
        note="Create a completely new composition. Exact phrase: TRANS RIGHTS ARE HUMAN RIGHTS. No heart, no rainbow heart, no badge, no rounded rectangle, no dark background panel, or reused layout. Use trans-pride light blue, pink, and white on a transparent background. Force a new composition."
        product_orchestrator._atomic_json(proposal/"revision-request.json",{"proposal_sha256":"a"*64,"note":note,"force_new_composition":True})
        product_orchestrator._atomic_json(job_root/"unified-preparation.json",{"provider_actions":[{"status":"completed","uncertain":False}]})
        orchestrator.review_draft=lambda job_id:{"result":"reviewed"}
        workflow=FakeWorkflow(orchestrator);profile=lambda required=True:{"profile_id":"profile","profile_type":"commerce_shop","configuration":{"printify_shop_id":123}}
        return CommerceRevisionService(workflow,profile_loader=profile),client,workflow

    def test_resume_reuses_existing_product_once_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temporary:
            service,client,workflow=self.fixture(Path(temporary));result=service.resume("revision-job")
            self.assertEqual(result["job_id"],"revision-job");self.assertTrue(result["existing_product_reused"]);self.assertFalse(result["new_product_created"])
            self.assertEqual(client.upload_count,1);self.assertEqual(client.update_count,1);client.create_product.assert_not_called();self.assertEqual(result["tag_count"],13)
            self.assertEqual(result["selected_novelty_status"],"materially_distinct");self.assertNotEqual(result["proposal_sha256"],result["old_proposal_sha256"])
            repeated=service.resume("revision-job");self.assertTrue(repeated["already_completed"]);self.assertEqual(client.upload_count,1);self.assertEqual(client.update_count,1)

    def test_uncertain_upload_is_never_retried(self):
        with tempfile.TemporaryDirectory() as temporary:
            service,client,workflow=self.fixture(Path(temporary),fail_upload=True)
            with self.assertRaises(RuntimeError):service.resume("revision-job")
            self.assertEqual(client.upload_count,1)
            with self.assertRaises(Exception):service.resume("revision-job")
            self.assertEqual(client.upload_count,1);self.assertEqual(client.update_count,0);client.create_product.assert_not_called()


if __name__=="__main__":unittest.main()
