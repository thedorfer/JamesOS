import tempfile
import unittest
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

from PIL import Image,ImageDraw
from fastapi.testclient import TestClient

from jamesos.core import api
from jamesos.services.coloring_book_producer import ColoringBookProducer,SampleGenerationConflict,SampleGenerationFailure
from jamesos.services.local_creative_studio import LocalAssetResult
from tests.test_coloring_book_producer import FakeScout


class FakeCreative:
    provider_id="fake-local-creative";capabilities=frozenset({"coloring_page.line_art"})
    def __init__(self,configured=True,duplicate=False,mode="completed"):self.configured=configured;self.duplicate=duplicate;self.mode=mode;self.calls=[];self.persisted_before_execute=[]
    def readiness(self):return {"provider_id":self.provider_id,"provider_version":"test","profile_id":"fixture-profile","configured":self.configured,"reachable":self.configured,"status":"ready" if self.configured else "not_configured","message":"Local image provider is ready." if self.configured else "Local image provider is not configured","checkpoint":"fixture.ckpt" if self.configured else None,"workflow_reference":"fixture.api.json","workflow_hash":"a"*64}
    def execute(self,request):
        self.calls.append(request);manifest=Path(request.specification["owner_root"])/"samples/manifest.json";self.persisted_before_execute.append(__import__("json").loads(manifest.read_text()))
        if self.mode=="exception":raise RuntimeError("simulated provider exception")
        if self.mode=="empty":return LocalAssetResult(request.request_id,"completed",(),self.provider_id,0)
        if self.mode=="rejected":return LocalAssetResult(request.request_id,"rejected",(),self.provider_id,0,("simulated rejection",))
        artifacts=[];root=Path(request.specification["output_directory"]);root.mkdir(parents=True,exist_ok=True)
        for index,page in enumerate(request.specification["pages"]):
            sink=request.specification.get("operation_event_sink")
            if sink:sink({"comfyui_prompt_id":f"fake-prompt-{len(self.calls)}","seed":100+len(self.calls),"api_url":"http://127.0.0.1:8188","http_status":200,"submission_timestamp":"2026-07-23T15:05:48-05:00","instance_identity":{"instance_id":"instance-before","process_started_at":"Thu 2026-07-23 14:40:28 CDT"}})
            image=Image.new("L",(1024,1280),255);draw=ImageDraw.Draw(image);offset=index*15+len(self.calls);draw.rectangle((120+offset,150,900,1100),outline=0,width=12);draw.ellipse((300,300+offset,700,800),outline=0,width=10);content_path=root/f"fake-{len(self.calls)}-{index}.png";image.save(content_path);digest="f"*64 if self.duplicate else sha256(content_path.read_bytes()).hexdigest();artifacts.append({"asset_id":f"asset-{len(self.calls)}-{index}","page_id":page["page_id"],"prompt_id":page["prompt_id"],"provider_id":self.provider_id,"provider_version":"test","workflow_hash":"a"*64,"model_checkpoint":"fixture.ckpt","seed":index,"width":1024,"height":1280,"file_sha256":digest,"generated_at":"2026-07-20T00:00:00Z","provider_effects":{"local_gpu":False,"external_network":False,"marketplace_write":False},"review_state":"pending","local_path":str(content_path),"technical_validation":{"valid":True,"mostly_white_background":True,"not_blank":True,"safe_margins":True}})
        return LocalAssetResult(request.request_id,"completed",tuple(artifacts),self.provider_id,0)


class SamplePageGenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name);self.fake=FakeCreative();self.service=ColoringBookProducer(root/"projects",FakeScout(root/"runs"),creative=self.fake);self.pid=self.service.create("run-1","concept-011",confirmed=True)["project_id"]
    def tearDown(self):self.temp.cleanup()
    def approve_plan(self):self.service.approve_brief(self.pid,confirmed=True);self.service.generate_page_plan(self.pid,confirmed=True);self.service.approve_page_plan(self.pid,confirmed=True)
    def generate(self,service=None,pid=None):
        service=service or self.service;pid=pid or self.pid;preview=service.generate_samples(pid)
        identity={key:preview[key] for key in ("project_id","page_plan_revision","page_plan_hash","selected_page_ids","workflow_profile","workflow","workflow_hash","checkpoint","request_id","generation_identity")}
        return service.generate_samples(pid,confirmed=True,generation_identity=identity)

    def test_blocked_preview_nonwriting_and_unavailable(self):
        with self.assertRaisesRegex(ValueError,"approved current page plan"):self.service.generate_samples(self.pid)
        self.approve_plan();sample_root=self.service.root/self.pid/"samples";preview=self.service.generate_samples(self.pid)
        self.assertEqual(["page-001","page-005","page-015"],preview["selected_sample_page_ids"]);self.assertTrue((sample_root/"operations.json").is_file());self.assertEqual([],self.fake.calls)
        unavailable_service=ColoringBookProducer(self.service.root,self.service.scout,creative=FakeCreative(False))
        with self.assertRaisesRegex(SampleGenerationFailure,"not configured"):self.generate(unavailable_service)
        self.assertEqual("failed",unavailable_service.sample_status(self.pid)["status"])

    def test_generation_manifest_review_regenerate_and_style_approval(self):
        self.approve_plan();manifest=self.generate()
        self.assertEqual("review_ready",manifest["status"]);self.assertEqual(3,len(manifest["artifacts"]));self.assertEqual(3,len(self.fake.calls));self.assertEqual(["page-001","page-005","page-015"],[x.specification["pages"][0]["page_id"] for x in self.fake.calls]);self.assertEqual("coloring_page.line_art",self.fake.calls[0].capability)
        self.assertTrue(all(x["status"]=="running" and x["selected_page_ids"]==["page-001","page-005","page-015"] for x in self.fake.persisted_before_execute))
        self.assertTrue(all(Path(x["local_path"]).is_file() and x["technical_validation"]["valid"] for x in manifest["artifacts"]))
        for item in list(manifest["artifacts"]):manifest=self.service.review_sample(self.pid,item["asset_id"],"approve")
        preview=self.service.approve_sample_style(self.pid);self.assertEqual(3,len(preview["approved_page_ids"]));done=self.service.approve_sample_style(self.pid,confirmed=True)
        self.assertIn("Full-book generation has not started",done["message"]);status=self.service.sample_status(self.pid);self.assertEqual("sample_style_approved",status["status"]);self.assertFalse(status["full_book_generation_started"]);self.assertFalse(status["pdf_created"]);self.assertFalse(status["amazon_upload"]);self.assertFalse(status["marketplace_write"]);self.assertEqual("not_created",status["order_status"])

    def test_reject_and_regenerate_persist_and_duplicates_fail(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];self.service.review_sample(self.pid,asset["asset_id"],"reject");preview=self.service.regenerate_sample(self.pid,asset["asset_id"]);self.assertTrue(preview["confirmation_required"]);updated=self.service.regenerate_sample(self.pid,asset["asset_id"],confirmed=True);self.assertEqual("superseded",next(x for x in updated["artifacts"] if x["asset_id"]==asset["asset_id"])["review_state"])
        duplicate=FakeCreative(duplicate=True);other_root=Path(self.temp.name)/"other";other=ColoringBookProducer(other_root,self.service.scout,creative=duplicate);pid=other.create("run-1","concept-011",confirmed=True)["project_id"];other.approve_brief(pid,confirmed=True);other.generate_page_plan(pid,confirmed=True);other.approve_page_plan(pid,confirmed=True)
        with self.assertRaisesRegex(SampleGenerationFailure,"duplicate sample"):self.generate(other,pid)

    def test_prompt_override_persists_and_regenerates_only_edited_page(self):
        positive="""Simple black-and-white children’s coloring-book page for ages 4–8.
A friendly bear and rabbit unpack camping supplies beside one large tent.
Exactly two characters and one tent.
One clear foreground action, centered composition, bold thick black outlines,
large open coloring areas, minimal simple forest background, white page,
friendly expressions, no text, no shading."""
        negative="""multiple tents, crowd, many characters, tiny figures, distant subjects,
dense forest details, clutter, pencil sketch, faint gray lines, grayscale,
shading, crosshatching, fine texture, photorealism, color, text, watermark,
duplicate objects, malformed anatomy, extra limbs"""
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0]
        self.service.review_sample(self.pid,asset["asset_id"],"reject")
        source_path=self.service.root/self.pid/"page-prompts.json";source_before=source_path.read_bytes();calls_before=len(self.fake.calls)
        saved=self.service.edit_sample_prompt(self.pid,"page-001",positive,negative)
        self.assertEqual(1,saved["prompt_revision"]);self.assertNotEqual(saved["previous_prompt_hash"],saved["new_prompt_hash"]);self.assertEqual(source_before,source_path.read_bytes());self.assertEqual(calls_before,len(self.fake.calls));self.assertFalse(saved["image_generated"]);self.assertFalse(saved["page_plan_changed"])
        status=self.service.sample_status(self.pid);page_artifact=next(x for x in status["artifacts"] if x["asset_id"]==asset["asset_id"])
        self.assertEqual("rejected",page_artifact["review_state"]);self.assertTrue(page_artifact["prompt_stale"]);self.assertEqual(positive,page_artifact["prompt_details"]["positive_prompt"]);self.assertEqual(negative,page_artifact["prompt_details"]["negative_prompt"])
        refreshed=ColoringBookProducer(self.service.root,self.service.scout,creative=self.fake).sample_status(self.pid)
        self.assertEqual(positive,next(x for x in refreshed["artifacts"] if x["asset_id"]==asset["asset_id"])["prompt_details"]["positive_prompt"])
        preview=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"])
        self.assertEqual("page-001",preview["page_id"]);self.assertEqual(saved["previous_prompt_hash"],preview["old_prompt_hash"]);self.assertEqual(saved["new_prompt_hash"],preview["new_prompt_hash"]);self.assertEqual(0,preview["safety"]["marketplace_actions"])
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        updated=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys})
        self.assertEqual(calls_before+1,len(self.fake.calls));self.assertEqual(["page-001"],[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);self.assertEqual("kids-bold-line-art-v1",self.fake.calls[-1].specification["profile_id"]);self.assertEqual("kids-bold-line-art-v1",preview["new_profile"]);self.assertEqual(positive,self.fake.calls[-1].specification["pages"][0]["positive_prompt"]);self.assertNotIn("page-005",[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);self.assertNotIn("page-015",[x["page_id"] for x in self.fake.calls[-1].specification["pages"]])
        self.assertEqual("superseded",next(x for x in updated["artifacts"] if x["asset_id"]==asset["asset_id"])["review_state"]);self.assertEqual(4,len(updated["artifacts"]))
        journal=(self.service.root/self.pid/"samples/operations.json").read_text();self.assertIn('"operation": "sample_prompt_edited"',journal);self.assertIn('"marketplace_actions": 0',journal)

    def test_prompt_override_routes_and_ui_are_exposed(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0]
        body={"csrf_token":api._COMMERCE_CREATE_CSRF,"positive_prompt":"updated positive","negative_prompt":"updated negative"}
        with patch.object(api,"ColoringBookProducer",return_value=self.service),patch.object(api,"_require_local"),patch.object(api,"_require_coloring_book_producer"),patch.object(api,"_validate_commerce_origin"):
            client=TestClient(api.app,base_url="http://127.0.0.1:8787")
            saved=client.post(f"/app/agency/coloring-book-producer/projects/{self.pid}/samples/pages/page-001/prompt",json=body)
            preview=client.post(f"/app/agency/coloring-book-producer/projects/{self.pid}/samples/{asset['asset_id']}/regenerate-with-updated-prompt",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"confirmed":False})
            confirmed=client.post(f"/app/agency/coloring-book-producer/projects/{self.pid}/samples/{asset['asset_id']}/regenerate-with-updated-prompt",json={"csrf_token":api._COMMERCE_CREATE_CSRF,"confirmed":True,**preview.json()})
        self.assertEqual(200,saved.status_code);self.assertEqual(200,preview.status_code);self.assertEqual(200,confirmed.status_code);self.assertEqual(4,len(self.fake.calls));self.assertEqual(4,len(confirmed.json()["artifacts"]))
        shell=TestClient(api.app,base_url="http://127.0.0.1:8787").get("/app").text
        self.assertIn("Edit Prompt",shell);self.assertIn("Regenerate With Updated Prompt",shell);self.assertIn("No image was generated",shell)

    def test_invalid_artifact_cannot_be_approved_or_enable_style_approval(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];asset["technical_validation"]={"valid":False,"failed_reasons":["largest black component"]};self.service.artifacts.write(self.pid,"samples/manifest.json",manifest)
        with self.assertRaisesRegex(ValueError,"technically invalid"):self.service.review_sample(self.pid,asset["asset_id"],"approve")
        for item in manifest["artifacts"][1:]:self.service.review_sample(self.pid,item["asset_id"],"approve")
        with self.assertRaisesRegex(ValueError,"one approved image"):self.service.approve_sample_style(self.pid)

    def test_persistent_progress_summary_uses_provider_evidence(self):
        self.approve_plan();preview=self.service.generate_samples(self.pid);journal=self.service.root/self.pid/"samples/operations.json"
        status=self.service.sample_status(self.pid);progress=status["progress"]
        self.assertEqual("previewed",progress["operation_state"]);self.assertTrue(progress["active"]);self.assertEqual(["page-001","page-005","page-015"],progress["page_ids"]);self.assertEqual(3,progress["expected_artifact_count"])
        value=__import__("json").loads(journal.read_text());identity=preview["generation_identity"]
        value["operations"].extend([
            {"operation":"generate_samples","state":"submission_started","timestamp":"2026-07-23T16:00:00-05:00","generation_identity":identity,"page_ids":["page-001","page-005","page-015"]},
            {"operation":"generate_samples","state":"provider_submitted","timestamp":"2026-07-23T16:00:01-05:00","generation_identity":identity,"page_id":"page-001","comfyui_prompt_id":"accepted-prompt","instance_identity":{"instance_id":"fixture-instance","process_started_at":"fixture-start"}},
        ]);journal.write_text(__import__("json").dumps(value))
        self.fake.submission_evidence=lambda prompt_id,instance_id:{"queue_evidence":True,"history_evidence":False,"output_evidence":False}
        progress=self.service.sample_status(self.pid)["progress"]
        self.assertEqual("provider_submitted",progress["operation_state"]);self.assertEqual(["accepted-prompt"],progress["submitted_prompt_ids"]);self.assertEqual("queue_confirmed",progress["queue_confirmation_state"]);self.assertTrue(progress["provider_state_confirmed"]);self.assertEqual("fixture-instance",progress["comfyui_instance_identity"]["instance_id"]);self.assertIsNotNone(progress["started_at"]);self.assertIsNotNone(progress["last_status_update_at"])
        self.fake.submission_evidence=lambda prompt_id,instance_id:{"queue_evidence":False,"history_evidence":False,"output_evidence":False}
        progress=self.service.sample_status(self.pid)["progress"]
        self.assertEqual("submitted_unconfirmed",progress["queue_confirmation_state"]);self.assertFalse(progress["provider_state_confirmed"])
        value=__import__("json").loads(journal.read_text());value["operations"].append({"operation":"generate_samples","state":"failed","timestamp":"2026-07-23T16:00:02-05:00","generation_identity":identity,"safe_failure_message":"fixture failed safely"});journal.write_text(__import__("json").dumps(value))
        progress=self.service.sample_status(self.pid)["progress"];self.assertEqual("failed",progress["operation_state"]);self.assertFalse(progress["active"]);self.assertEqual("fixture failed safely",progress["safe_failure_message"])

    def test_candidate_history_and_reference_selection_are_preserved(self):
        self.approve_plan();manifest=self.generate();first=next(x for x in manifest["artifacts"] if x["page_id"]=="page-001");before=len(manifest["artifacts"]);record=self.service.mark_reference_candidate(self.pid,first["asset_id"])
        self.assertEqual(first["asset_id"],record["reference_asset_id"]);self.assertFalse(record["approval"]);self.assertEqual(0,record["external_actions"])
        refreshed=ColoringBookProducer(self.service.root,self.service.scout,creative=self.fake).sample_status(self.pid);self.assertEqual(before,len(refreshed["artifacts"]));self.assertTrue(next(x for x in refreshed["artifacts"] if x["asset_id"]==first["asset_id"])["reference_candidate"]);self.assertFalse(any(x["review_state"]=="approved" for x in refreshed["artifacts"]))

    def test_duplicate_page_regeneration_is_blocked_by_durable_progress(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];self.service.edit_sample_prompt(self.pid,"page-001","updated positive","updated negative");preview=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],profile_id="kids-bold-line-art-v6");journal=self.service.root/self.pid/"samples/operations.json";value=__import__("json").loads(journal.read_text());value["operations"].append({"operation":"regenerate_single_page","state":"submission_started","timestamp":"2026-07-23T16:00:00-05:00","page_id":"page-001","asset_id":asset["asset_id"],"regeneration_identity":"active-operation","generation_attempt_identity":preview["generation_attempt_identity"]});journal.write_text(__import__("json").dumps(value))
        with self.assertRaisesRegex(SampleGenerationConflict,"already active"):self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],profile_id="kids-bold-line-art-v6")
        progress=self.service.sample_status(self.pid)["progress"];self.assertEqual("regenerate_single_page",progress["operation_type"]);self.assertEqual(asset["asset_id"],progress["source_artifact_id"]);self.assertEqual(["page-001"],progress["page_ids"]);self.assertEqual("submission_started",progress["operation_state"]);self.assertEqual(3,len(self.fake.calls))

    def test_one_explicit_v3_regeneration_uses_only_page_001(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];self.service.edit_sample_prompt(self.pid,"page-001","one simple animal scene","human, clutter")
        preview=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],profile_id="kids-bold-line-art-v3");self.assertEqual("kids-bold-line-art-v3",preview["new_profile"]);self.assertEqual("page-001",preview["page_id"])
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        result=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys},profile_id="kids-bold-line-art-v3")
        self.assertEqual("kids-bold-line-art-v3",result["artifacts"][-1]["profile_id"]);self.assertEqual(["page-001"],[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);self.assertEqual("kids-bold-line-art-v3",self.fake.calls[-1].specification["profile_id"]);self.assertEqual(4,len(self.fake.calls))
        with self.assertRaisesRegex(SampleGenerationConflict,"already been used"):self.service.regenerate_with_updated_prompt(self.pid,result["artifacts"][-1]["asset_id"],profile_id="kids-bold-line-art-v3")

    def test_one_explicit_v4_regeneration_uses_fake_provider_for_page_001_only(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];self.service.edit_sample_prompt(self.pid,"page-001","one simple animal scene","human, clutter")
        preview=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],profile_id="kids-bold-line-art-v4");self.assertEqual("kids-bold-line-art-v4",preview["new_profile"]);self.assertEqual("page-001",preview["page_id"]);self.assertEqual(0,preview["safety"]["marketplace_actions"])
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        result=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys},profile_id="kids-bold-line-art-v4")
        self.assertEqual("kids-bold-line-art-v4",result["artifacts"][-1]["profile_id"]);self.assertEqual(["page-001"],[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);self.assertEqual("kids-bold-line-art-v4",self.fake.calls[-1].specification["profile_id"]);self.assertEqual(4,len(self.fake.calls));self.assertEqual(4,len(result["artifacts"]))
        with self.assertRaisesRegex(SampleGenerationConflict,"already been used"):self.service.regenerate_with_updated_prompt(self.pid,result["artifacts"][-1]["asset_id"],profile_id="kids-bold-line-art-v4")

    def test_one_explicit_v5_regeneration_preserves_override_and_requires_human_semantic_review(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];positive="one nonhuman bear cub and one nonhuman rabbit unpack a backpack, sleeping bag, and lantern beside one tent, sparse background, black outlines on white";negative="extra animals, missing rabbit, multiple tents, color, shading";saved=self.service.edit_sample_prompt(self.pid,"page-001",positive,negative)
        preview=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],profile_id="kids-bold-line-art-v5");self.assertEqual("kids-bold-line-art-v5",preview["new_profile"]);self.assertEqual("page-001",preview["page_id"]);self.assertEqual(saved["new_prompt_hash"],preview["new_prompt_hash"])
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        result=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys},profile_id="kids-bold-line-art-v5");candidate=result["artifacts"][-1]
        self.assertEqual("kids-bold-line-art-v5",candidate["profile_id"]);self.assertEqual(["page-001"],[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);self.assertEqual(4,len(result["artifacts"]));self.assertFalse(candidate["semantic_review"]["automated_certainty"]);self.assertIsNone(candidate["semantic_review"]["bear"]["detected"]);self.assertIsNone(candidate["semantic_review"]["rabbit"]["detected"]);self.assertIsNone(candidate["semantic_review"]["tent"]["detected"]);self.assertIsNone(candidate["semantic_review"]["unpacking_action"]["matched"])
        with self.assertRaisesRegex(SampleGenerationConflict,"already been used"):self.service.regenerate_with_updated_prompt(self.pid,candidate["asset_id"],profile_id="kids-bold-line-art-v5")

    def test_one_explicit_v6_regeneration_is_page001_only_and_human_reviewed(self):
        self.approve_plan();manifest=self.generate();asset=manifest["artifacts"][0];saved=self.service.edit_sample_prompt(self.pid,"page-001","exactly one nonhuman bear cub and one nonhuman rabbit unpack a backpack, sleeping bag, and lantern beside one tent, sparse campsite, black outlines on white","humans, costumes, text, shading, large black fills")
        preview=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],profile_id="kids-bold-line-art-v6");self.assertEqual("kids-bold-line-art-v6",preview["new_profile"]);self.assertEqual(saved["new_prompt_hash"],preview["new_prompt_hash"]);self.assertEqual("page-001",preview["page_id"])
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        result=self.service.regenerate_with_updated_prompt(self.pid,asset["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys},profile_id="kids-bold-line-art-v6");candidate=result["artifacts"][-1]
        self.assertEqual("kids-bold-line-art-v6",candidate["profile_id"]);self.assertEqual(["page-001"],[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);self.assertEqual(4,len(result["artifacts"]));self.assertFalse(candidate["semantic_review"]["automated_certainty"]);self.assertIsNone(candidate["semantic_review"]["bear"]["detected"]);self.assertIsNone(candidate["semantic_review"]["unpacking_action"]["matched"])
        with self.assertRaisesRegex(SampleGenerationConflict,"exact page"):self.service.regenerate_with_updated_prompt(self.pid,candidate["asset_id"],profile_id="kids-bold-line-art-v6")

    def test_v6_attempt_identity_allows_changed_prompts_and_stops_at_three(self):
        self.approve_plan();manifest=self.generate();source=manifest["artifacts"][0];original_ids=[x["asset_id"] for x in manifest["artifacts"]]
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        current=source
        for attempt in range(1,4):
            saved=self.service.edit_sample_prompt(self.pid,"page-001",f"changed positive revision {attempt}",f"changed negative revision {attempt}")
            preview=self.service.regenerate_with_updated_prompt(self.pid,current["asset_id"],profile_id="kids-bold-line-art-v6")
            self.assertEqual(attempt,preview["attempt_number"]);self.assertEqual(saved["prompt_revision"],preview["prompt_revision"]);self.assertEqual(64,len(preview["positive_prompt_hash"]));self.assertEqual(64,len(preview["negative_prompt_hash"]))
            before=len(self.fake.calls);result=self.service.regenerate_with_updated_prompt(self.pid,current["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys},profile_id="kids-bold-line-art-v6")
            self.assertEqual(before+1,len(self.fake.calls));self.assertEqual(["page-001"],[x["page_id"] for x in self.fake.calls[-1].specification["pages"]]);current=result["artifacts"][-1]
            with self.assertRaisesRegex(SampleGenerationConflict,"exact page"):self.service.regenerate_with_updated_prompt(self.pid,current["asset_id"],profile_id="kids-bold-line-art-v6")
        status=self.service.sample_status(self.pid);policy=status["page_generation_policy"]
        self.assertEqual(3,policy["attempts_used"]);self.assertEqual(0,policy["attempts_remaining"]);self.assertEqual("Maximum attempts reached. Human intervention required.",policy["blocked_reason"])
        self.assertTrue(all(asset_id in [x["asset_id"] for x in status["artifacts"]] for asset_id in original_ids))
        self.service.edit_sample_prompt(self.pid,"page-001","fourth positive","fourth negative")
        with self.assertRaisesRegex(SampleGenerationConflict,"Maximum attempts reached"):self.service.regenerate_with_updated_prompt(self.pid,current["asset_id"],profile_id="kids-bold-line-art-v6")
        self.assertFalse(status["marketplace_write"]);self.assertFalse(status["pdf_created"]);self.assertEqual("not_published",status["publication_status"]);self.assertEqual("not_created",status["purchase_status"]);self.assertEqual("not_created",status["order_status"])

    def test_changed_prompt_ignores_stale_terminal_attempt_and_creates_exact_new_candidate(self):
        self.approve_plan();manifest=self.generate();source=manifest["artifacts"][0]
        keys=("project_id","asset_id","page_id","old_prompt_revision","old_prompt_hash","new_prompt_hash","prompt_revision","positive_prompt_hash","negative_prompt_hash","old_profile","new_profile","profile_id","checkpoint","workflow_hash","postprocessing","validation_thresholds","reference_candidate_id","attempt_number","maximum_attempts_per_page","generation_attempt_identity","request_id","regeneration_identity")
        self.service.edit_sample_prompt(self.pid,"page-001","revision two positive","revision two negative")
        prior=self.service.regenerate_with_updated_prompt(self.pid,source["asset_id"],profile_id="kids-bold-line-art-v6")
        first=self.service.regenerate_with_updated_prompt(self.pid,source["asset_id"],confirmed=True,regeneration_identity={key:prior[key] for key in keys},profile_id="kids-bold-line-art-v6")
        old_candidate=first["artifacts"][-1];old_prompt_id=self.fake.calls[-1].request_id;before_ids=[x["asset_id"] for x in first["artifacts"]]
        self.service.edit_sample_prompt(self.pid,"page-001","revision three positive","revision three negative")
        available=self.service.sample_status(self.pid)
        self.assertEqual("not_started",available["progress"]["operation_state"]);self.assertNotIn(old_prompt_id,available["progress"]["submitted_prompt_ids"]);self.assertTrue(available["page_generation_policy"]["generation_available"])
        preview=self.service.regenerate_with_updated_prompt(self.pid,old_candidate["asset_id"],profile_id="kids-bold-line-art-v6")
        before_calls=len(self.fake.calls);second=self.service.regenerate_with_updated_prompt(self.pid,old_candidate["asset_id"],confirmed=True,regeneration_identity={key:preview[key] for key in keys},profile_id="kids-bold-line-art-v6")
        self.assertEqual(before_calls+1,len(self.fake.calls));self.assertEqual(len(first["artifacts"])+1,len(second["artifacts"]))
        newest=second["artifacts"][-1];self.assertEqual(preview["generation_attempt_identity"],newest["generation_attempt_identity"]);self.assertEqual(preview["prompt_revision"],newest["prompt_revision"]);self.assertEqual(preview["positive_prompt_hash"],newest["positive_prompt_hash"]);self.assertEqual(preview["negative_prompt_hash"],newest["negative_prompt_hash"])
        self.assertTrue(all(asset_id in [x["asset_id"] for x in second["artifacts"]] for asset_id in before_ids))
        refreshed=self.service.sample_status(self.pid);self.assertEqual(2,refreshed["page_generation_policy"]["attempts_used"]);self.assertEqual(preview["prompt_revision"],refreshed["page_generation_policy"]["latest_generated_revision"]);self.assertEqual(preview["generation_attempt_identity"],refreshed["progress"]["generation_attempt_identity"])

    def test_confirmed_identity_is_required_and_idempotent(self):
        self.approve_plan();preview=self.service.generate_samples(self.pid)
        with self.assertRaisesRegex(ValueError,"stale or incomplete"):
            self.service.generate_samples(self.pid,confirmed=True,generation_identity={"project_id":self.pid})
        manifest=self.generate();again=self.generate()
        self.assertTrue(again["idempotent"]);self.assertEqual(manifest["generation_identity"],again["generation_identity"]);self.assertEqual(3,len(self.fake.calls))
        journal=(self.service.root/self.pid/"samples/operations.json").read_text()
        for state in ("previewed","submission_started","provider_submitted","outputs_received","review_ready"):self.assertIn(f'"state": "{state}"',journal)

    def test_empty_result_and_provider_exception_persist_visible_failure(self):
        for mode,message in (("empty","0 artifacts"),("exception","simulated provider exception")):
            root=Path(self.temp.name)/mode;fake=FakeCreative(mode=mode);service=ColoringBookProducer(root,self.service.scout,creative=fake);pid=service.create("run-1","concept-011",confirmed=True)["project_id"];service.approve_brief(pid,confirmed=True);service.generate_page_plan(pid,confirmed=True);service.approve_page_plan(pid,confirmed=True)
            with self.assertRaisesRegex(SampleGenerationFailure,message):self.generate(service,pid)
            status=service.sample_status(pid);self.assertEqual("failed",status["status"]);self.assertIn(message,status["safe_failure_message"]);self.assertEqual(["page-001","page-005","page-015"],status["selected_page_ids"]);self.assertEqual(0,status["artifact_count"])

    def test_uncertain_submission_requires_explicit_one_time_reconciliation(self):
        self.approve_plan();preview=self.service.generate_samples(self.pid);identity={key:preview[key] for key in ("project_id","page_plan_revision","page_plan_hash","selected_page_ids","workflow_profile","workflow","workflow_hash","checkpoint","request_id","generation_identity")}
        journal=self.service.root/self.pid/"samples/operations.json";value=__import__("json").loads(journal.read_text());value["operations"].append({"operation":"generate_samples","state":"submission_started","request_id":preview["request_id"],"generation_identity":preview["generation_identity"],"page_ids":preview["selected_page_ids"]});journal.write_text(__import__("json").dumps(value))
        with self.assertRaisesRegex(SampleGenerationConflict,"explicit no-submission reconciliation"):self.service.generate_samples(self.pid,confirmed=True,generation_identity=identity)
        self.assertEqual(0,len(self.fake.calls));reconcile=self.service.reconcile_sample_generation(self.pid);self.assertTrue(reconcile["confirmation_required"]);self.service.reconcile_sample_generation(self.pid,confirmed=True);manifest=self.service.generate_samples(self.pid,confirmed=True,generation_identity=identity);self.assertEqual("review_ready",manifest["status"]);self.assertEqual(3,len(self.fake.calls))
        with self.assertRaisesRegex(SampleGenerationConflict,"already used"):self.service.reconcile_sample_generation(self.pid,confirmed=True)

    def test_http_never_returns_200_for_stale_silent_noop(self):
        self.approve_plan();preview=self.service.generate_samples(self.pid);identity={key:preview[key] for key in ("project_id","page_plan_revision","page_plan_hash","selected_page_ids","workflow_profile","workflow","workflow_hash","checkpoint","request_id","generation_identity")}
        journal=self.service.root/self.pid/"samples/operations.json";value=__import__("json").loads(journal.read_text());value["operations"].append({"operation":"generate_samples","state":"submission_started","request_id":preview["request_id"],"generation_identity":preview["generation_identity"],"page_ids":preview["selected_page_ids"]});journal.write_text(__import__("json").dumps(value))
        body={"csrf_token":api._COMMERCE_CREATE_CSRF,"confirmed":True,**identity}
        with patch.object(api,"ColoringBookProducer",return_value=self.service),patch.object(api,"_require_local"),patch.object(api,"_require_coloring_book_producer"),patch.object(api,"_validate_commerce_origin"):
            response=TestClient(api.app,base_url="http://127.0.0.1:8787").post(f"/app/agency/coloring-book-producer/projects/{self.pid}/samples/generate",json=body)
        self.assertEqual(409,response.status_code);self.assertIn("reconciliation",response.json()["detail"])

    def test_provider_restart_loses_prompt_and_requires_explicit_retry(self):
        class RestartCreative(FakeCreative):
            def submission_evidence(self,prompt_id,submitted_instance_id):
                return {"prompt_id":prompt_id,"submitted_instance_id":submitted_instance_id,"current_instance_identity":{"instance_id":"instance-after","process_started_at":"Thu 2026-07-23 15:06:28 CDT"},"instance_changed":True,"queue_evidence":False,"history_evidence":False,"output_evidence":False,"api_url":"http://127.0.0.1:8188"}
        root=Path(self.temp.name)/"restart";fake=RestartCreative();service=ColoringBookProducer(root,self.service.scout,creative=fake);pid=service.create("run-1","concept-011",confirmed=True)["project_id"];service.approve_brief(pid,confirmed=True);service.generate_page_plan(pid,confirmed=True);service.approve_page_plan(pid,confirmed=True);preview=service.generate_samples(pid)
        completed={"asset_id":"existing-page-005","page_id":"page-005","prompt_id":"prompt-005","provider_id":"fake-local-creative","file_sha256":"9"*64,"review_state":"pending"}
        manifest={"status":"running","operation_state":"provider_submitted","project_id":pid,"page_plan_revision":preview["page_plan_revision"],"page_plan_hash":preview["page_plan_hash"],"selected_page_ids":preview["selected_page_ids"],"generation_identity":preview["generation_identity"],"request_id":preview["request_id"],"workflow_profile":preview["workflow_profile"],"workflow_hash":preview["workflow_hash"],"checkpoint":preview["checkpoint"],"submitted_prompt_ids":["real-prompt"],"safe_failure_message":None,"artifacts":[completed],"artifact_count":1,"approval":None};service.artifacts.write(pid,"samples/manifest.json",manifest)
        journal=service.root/pid/"samples/operations.json";value=__import__("json").loads(journal.read_text());value["operations"].extend([{"operation":"generate_samples","state":"submission_started","request_id":preview["request_id"],"generation_identity":preview["generation_identity"],"page_ids":preview["selected_page_ids"]},{"operation":"generate_samples","state":"provider_submitted","timestamp":"2026-07-23T15:05:48-05:00","submission_timestamp":"2026-07-23T15:05:48-05:00","request_id":preview["request_id"],"generation_identity":preview["generation_identity"],"page_id":"page-001","prompt_id":"prompt-001","comfyui_prompt_id":"real-prompt","instance_identity":{"instance_id":"instance-before"}}]);journal.write_text(__import__("json").dumps(value))
        status=service.sample_status(pid);self.assertEqual("provider_submission_lost_after_restart",status["operation_state"]);self.assertIn("real ComfyUI prompt ID",status["safe_failure_message"]);self.assertEqual(0,len(fake.calls))
        identity={key:preview[key] for key in ("project_id","page_plan_revision","page_plan_hash","selected_page_ids","workflow_profile","workflow","workflow_hash","checkpoint","request_id","generation_identity")}
        with self.assertRaises(SampleGenerationConflict):service.generate_samples(pid,confirmed=True,generation_identity=identity)
        recon=service.reconcile_sample_generation(pid);self.assertEqual(["page-001"],recon["retry_page_ids"]);service.reconcile_sample_generation(pid,confirmed=True)
        retry=service.retry_unfinished_samples(pid);self.assertEqual(["page-001"],retry["retry_page_ids"]);self.assertEqual("real-prompt",retry["original_lost_prompt_id"]);retry_keys=("project_id","retry_page_ids","original_lost_prompt_id","page_plan_revision","page_plan_hash","workflow_profile","workflow_hash","checkpoint","request_id","generation_identity","comfyui_instance_identity","retry_attempt","retry_identity");first=service.retry_unfinished_samples(pid,confirmed=True,retry_identity={key:retry[key] for key in retry_keys});self.assertEqual("remaining_samples_authorized",first["operation_state"]);self.assertEqual(["page-001"],[x.specification["pages"][0]["page_id"] for x in fake.calls])
        remaining=service.retry_unfinished_samples(pid);self.assertEqual(["page-015"],remaining["retry_page_ids"]);done=service.retry_unfinished_samples(pid,confirmed=True,retry_identity={key:remaining[key] for key in retry_keys});self.assertEqual("review_ready",done["status"]);self.assertEqual(["page-001","page-015"],[x.specification["pages"][0]["page_id"] for x in fake.calls]);self.assertEqual(3,len(done["artifacts"]))
        states=[x["state"] for x in __import__("json").loads(journal.read_text())["operations"]];self.assertIn("provider_submission_lost_after_restart",states);self.assertIn("reconciled_lost_after_restart",states)


if __name__=="__main__":unittest.main()
