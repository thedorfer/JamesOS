from __future__ import annotations

from hashlib import sha256
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from jamesos.core.errors import ValidationError
from jamesos.services import error_handler, product_orchestrator, sale_candidate_vector
from scripts import product_from_prompt


class ProductOrchestratorTests(unittest.TestCase):
    FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")

    def fixture(self, root: Path):
        source = root / "approved.png"; image = Image.new("RGBA", (4500, 5400), (0,0,0,0))
        ImageDraw.Draw(image).ellipse((1300,1200,3200,3600), fill=(235,50,120,255)); image.save(source); image.close()
        return {"candidate":source,"candidate_sha":sha256(source.read_bytes()).hexdigest(),"approval_sha":"approval",
                "production":{"canvas_dimensions":[4500,5400]}}

    @staticmethod
    def candidates(evidence, root: Path, _brief):
        root.mkdir(parents=True, exist_ok=True); result=[]
        for index, name in enumerate(("integrated_shadow_centered","integrated_shadow_curved_caption","integrated_shadow_compact")):
            path=root/f"{name}.png";path.write_bytes(evidence["candidate"].read_bytes())
            checks={"hard_phrase_correct":True,"hard_no_duplicate_or_missing_text":True,"hard_safe_bounds":True,
                    "hard_artwork_integrity":True,"hard_dimensions":True,"hard_valid_transparency":True,
                    "hard_no_unexpected_opaque_canvas":True,"hard_print_resolution":True,"soft_warning":"human review"}
            result.append({"candidate_id":name,"direction":name,"png_path":str(path),"png_sha256":sha256(path.read_bytes()).hexdigest(),
                "svg_path":str(path.with_suffix('.svg')),"svg_sha256":str(index)*64,"source_artwork_sha256":evidence["candidate_sha"],
                "font_sha256":"f"*64,"layout_id":name,"treatment_id":"integrated_shadow_v4","quality_checks":checks,
                "thumbnail_path":str(path),"thumbnail_readability_score":10+index,"garment_contrast_score":9,"balanced_bounds_score":8,
                "warnings":["Automated scoring does not prove artistic quality."]})
        return result

    def orchestrator(self, root: Path, evidence, client=None):
        adapters=product_orchestrator.Adapters(evidence=lambda _job:evidence,candidates=self.candidates,client_factory=lambda:client)
        return product_orchestrator.ProductOrchestrator(root/root.name,adapters)

    def test_prompt_normalization_and_listing_defaults(self):
        brief=product_orchestrator.normalize_prompt('Create a playful LOVE IS LOVE retro shirt on black and white. Price it at $24.99.')
        self.assertEqual(brief["exact_text"],"LOVE IS LOVE");self.assertEqual(brief["price_cents"],2499)
        self.assertEqual(brief["blank"],"Bella+Canvas 3001");self.assertIn("Black",brief["garment_colors"])

    def test_color_aliases_order_longest_match_duplicates_and_unresolved(self):
        for phrase in ("dark heather","dark gray heather","dark grey heather"):
            self.assertEqual(product_orchestrator.resolve_garment_colors(phrase)["canonical_colors"],["Dark Grey Heather"])
        ordered=product_orchestrator.resolve_garment_colors("black, dark grey heather, white, dark heather")
        self.assertEqual(ordered["canonical_colors"],["Black","Dark Grey Heather","White"])
        self.assertEqual(ordered["requested_color_phrases"][:3],["black","dark grey heather","white"])
        ambiguous=product_orchestrator.resolve_garment_colors("grey");self.assertEqual(ambiguous["canonical_colors"],[]);self.assertEqual(ambiguous["unresolved_colors"],["grey"])
        charcoal=product_orchestrator.resolve_garment_colors("charcoal heather",configured_aliases={"charcoal heather":"Dark Grey Heather"})
        self.assertEqual(charcoal["resolved_colors"][0]["resolution"],"configured_alias")

    def test_unresolved_color_blocks_before_client_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);client_factory=Mock(side_effect=AssertionError("no client"))
            adapters=product_orchestrator.Adapters(evidence=lambda _:evidence,candidates=self.candidates,client_factory=client_factory)
            orchestrator=product_orchestrator.ProductOrchestrator(root/"jobs",adapters)
            with patch.object(product_orchestrator,"handle_error",side_effect=lambda exc,**kw:error_handler.handle_error(exc,diagnostic_root=root/"diag",log=False,**kw)):
                state=orchestrator.create(prompt="LOVE IS LOVE on grey",source_job_id="source",shop_id=1,confirm_printify_draft=True,job_id="unresolved")
            self.assertEqual(state["stage"],"failed");self.assertEqual(state["last_error"]["code"],"VALIDATION_FAILED");client_factory.assert_not_called()

    def test_three_real_v4_refinements_and_correct_opaque_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);font_root=root/"fonts";font_root.mkdir()
            manifest={"fonts":[{"font_id":"lilita-one-regular","family":"Lilita One","style":"Regular","font_path":str(self.FONT),
                "font_sha256":sha256(self.FONT.read_bytes()).hexdigest(),"license_path":str(self.FONT),"license_sha256":"x"*64}]}
            (font_root/"acquired-fonts.json").write_text(json.dumps(manifest))
            candidates=sale_candidate_vector.generate_v4_refinements(evidence["candidate"],root/"v4",phrase="LOVE IS LOVE",font_root=font_root)
            self.assertEqual({x["candidate_id"] for x in candidates},{"integrated_shadow_centered","integrated_shadow_curved_caption","integrated_shadow_compact"})
            self.assertTrue(all(not x["quality_checks"]["unexpected_opaque_background"] for x in candidates))
            self.assertEqual(sha256(evidence["candidate"].read_bytes()).hexdigest(),evidence["candidate_sha"])
            self.assertTrue(all(set(x["previews"])=={"black","dark_heather","white"} for x in candidates))

    def test_local_stages_persist_then_confirmation_failure_is_resumable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);orchestrator=self.orchestrator(root,evidence)
            with patch.object(product_orchestrator,"handle_error",side_effect=lambda exc,**kw:error_handler.handle_error(exc,diagnostic_root=root/"diagnostics",log=False,**kw)):
                state=orchestrator.create(prompt="LOVE IS LOVE retro shirt",source_job_id="source",shop_id=9437076,job_id="job")
            self.assertEqual(state["stage"],"failed");self.assertIn("error_id",state["last_error"])
            self.assertIn("listing_ready",{x["stage"] for x in state["transitions"]});self.assertEqual(state["brief"],orchestrator.load("job")["brief"])
            approval=state["evidence"]["selection"]["approval"]
            self.assertEqual(approval["approved_by"],"JamesOS automated quality gate");self.assertFalse(approval["human_artistic_approval"])
            self.assertEqual(state["evidence"]["listing"]["selected_design_sha256"],state["evidence"]["selection"]["selected"]["png_sha256"])

    def test_hard_blocker_stops_before_printify_and_soft_warning_is_retained(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);client=Mock()
            def blocked(ev,path,brief):
                values=self.candidates(ev,path,brief)
                for value in values:value["quality_checks"]["hard_safe_bounds"]=False
                return values
            adapters=product_orchestrator.Adapters(evidence=lambda _:evidence,candidates=blocked,client_factory=lambda:client)
            orchestrator=product_orchestrator.ProductOrchestrator(root/"jobs",adapters)
            with patch.object(product_orchestrator,"handle_error",side_effect=lambda exc,**kw:error_handler.handle_error(exc,diagnostic_root=root/"diagnostics",log=False,**kw)):
                state=orchestrator.create(prompt="LOVE IS LOVE",source_job_id="source",shop_id=1,confirm_printify_draft=True,job_id="blocked")
            self.assertEqual(state["stage"],"failed");client.upload_image_contents.assert_not_called()
            self.assertEqual(state["evidence"]["candidates"][0]["quality_checks"]["soft_warning"],"human review")

    def test_confirmed_draft_resume_reuses_remote_ids_and_never_publishes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);client=Mock()
            client.upload_image_contents.return_value={"id":"upload-1"}
            client.get_variants.return_value={"variants":[{"id":101,"title":"Black / S","is_available":True}]}
            client.list_products.return_value={"data":[]}
            client.create_product.return_value={"id":"draft-1","images":[{"src":"https://mock/image.jpg","variant_ids":[101]}]}
            client.get_product.return_value={"id":"draft-1","images":[{"src":"https://mock/image.jpg","variant_ids":[101]}]}
            client.timeout=(1,1);client.session.get.return_value=Mock(content=b"mockup");client.session.get.return_value.raise_for_status.return_value=None
            orchestrator=self.orchestrator(root,evidence,client)
            state=orchestrator.create(prompt="LOVE IS LOVE black shirt size S",source_job_id="source",shop_id=9437076,
                garment_colors=["Black"],sizes=["S"],confirm_printify_draft=True,job_id="live-mocked")
            self.assertEqual(state["stage"],"awaiting_human_approval");self.assertEqual(state["publish_status"],"not_published");self.assertEqual(state["order_status"],"not_created")
            transitions=len(state["transitions"]);resumed=orchestrator.resume("live-mocked",confirm_printify_draft=True)
            self.assertEqual(len(resumed["transitions"]),transitions);self.assertEqual(client.upload_image_contents.call_count,1);self.assertEqual(client.create_product.call_count,1)
            self.assertNotEqual(resumed["evidence"]["draft"]["printify_product_id"],product_orchestrator.PROTECTED_PRODUCT_ID)
            report=orchestrator.report("live-mocked");text=report.read_text();self.assertIn("DRAFT · NOT PUBLISHED · NO ORDER CREATED",text);self.assertIn("LOVE IS LOVE",text)

    def test_realistic_variant_dictionary_selects_exact_eighteen(self):
        rows=[];variant_id=100
        for color in ("Black","Dark Grey Heather","White"):
            for size in ("S","M","L","XL","2XL","3XL"):
                rows.append({"id":variant_id,"title":f"{color} / {size}","is_available":True,"placeholders":[{"position":"front"}]});variant_id+=1
        rows.extend([{"id":999,"title":"Dark Grey / S","is_available":True},{"id":1000,"title":"Black / S","is_available":False}])
        evidence=product_orchestrator.select_printify_variants({"variants":rows,"other_key":"not a row"},colors=["black","DARK GREY HEATHER","white"],sizes=product_orchestrator.DEFAULT_SIZES)
        self.assertEqual(len(evidence["selected_variant_ids"]),18);self.assertNotIn(999,evidence["selected_variant_ids"]);self.assertNotIn(1000,evidence["selected_variant_ids"])
        selected={(x["color"],x["size"]) for x in evidence["selected_variants"]}
        self.assertIn(("Dark Grey Heather","3XL"),selected);self.assertIn(("White","XL"),selected)
        self.assertEqual(evidence["normalized_variants"][0]["placeholders"],[{"position":"front"}])
        with self.assertRaises(ValidationError):
            product_orchestrator.select_printify_variants({"variants":rows},colors=["Dark Grey"],sizes=["3XL"])

    def test_resume_after_variant_failure_reuses_upload_and_selects_eighteen(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);client=Mock();generation_calls=0
            def candidates(ev,path,brief):
                nonlocal generation_calls;generation_calls+=1;return self.candidates(ev,path,brief)
            adapters=product_orchestrator.Adapters(evidence=lambda _:evidence,candidates=candidates,client_factory=lambda:client)
            orchestrator=product_orchestrator.ProductOrchestrator(root/"jobs",adapters)
            client.upload_image_contents.return_value={"id":"existing-upload"};client.get_variants.return_value={"variants":[]}
            with patch.object(product_orchestrator,"handle_error",side_effect=lambda exc,**kw:error_handler.handle_error(exc,diagnostic_root=root/"diagnostics",log=False,**kw)):
                failed=orchestrator.create(prompt="LOVE IS LOVE",source_job_id="source",shop_id=9437076,confirm_printify_draft=True,job_id="resume-job")
            self.assertEqual(failed["stage"],"failed");self.assertEqual(failed["last_error"]["code"],"VALIDATION_FAILED")
            self.assertEqual(failed["evidence"]["upload"]["printify_image_id"],"existing-upload")
            rows=[{"id":index+1,"title":f"{color} / {size}","is_available":True} for index,(color,size) in enumerate(
                ([(color,size) for color in product_orchestrator.DEFAULT_COLORS for size in product_orchestrator.DEFAULT_SIZES]))]
            client.get_variants.return_value={"variants":rows};client.list_products.return_value={"data":[]}
            client.create_product.return_value={"id":"new-draft"};client.get_product.return_value={"id":"new-draft","images":[]}
            resumed=orchestrator.resume("resume-job",confirm_printify_draft=True)
            self.assertEqual(resumed["stage"],"awaiting_human_approval");self.assertEqual(generation_calls,1)
            self.assertIsNone(resumed["last_error"]);self.assertEqual(len(resumed["recovered_errors"]),1)
            self.assertEqual(resumed["recovered_errors"][0]["error_id"],failed["last_error"]["error_id"])
            self.assertEqual(resumed["recovered_errors"][0]["diagnostic_path"],failed["last_error"]["diagnostic_path"])
            client.get_upload.assert_called_once_with("existing-upload");self.assertEqual(client.upload_image_contents.call_count,1)
            payload=client.create_product.call_args.args[1];self.assertEqual(len(payload["variants"]),18)
            self.assertEqual({x["price"] for x in payload["variants"]},{2499});self.assertEqual(resumed["evidence"]["variant_selection"]["selected_variant_ids"],list(range(1,19)))

    def test_draft_marker_reconciles_interrupted_remote_creation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);client=Mock();orchestrator=self.orchestrator(root,evidence,client)
            client.upload_image_contents.return_value={"id":"upload-1"};client.get_variants.return_value={"variants":[]}
            with patch.object(product_orchestrator,"handle_error",side_effect=lambda exc,**kw:error_handler.handle_error(exc,diagnostic_root=root/"diagnostics",log=False,**kw)):
                orchestrator.create(prompt="LOVE IS LOVE black size S",source_job_id="source",shop_id=9437076,
                    garment_colors=["Black"],sizes=["S"],confirm_printify_draft=True,job_id="reconcile")
            client.get_variants.return_value={"variants":[{"id":101,"title":"Black / S","is_available":True}]}
            def products(_shop):
                marker=orchestrator.load("reconcile")["evidence"]["draft_marker"]
                return {"data":[{"id":"remote-draft","tags":[marker]}]}
            client.list_products.side_effect=products;client.get_product.return_value={"id":"remote-draft","images":[]}
            state=orchestrator.resume("reconcile",confirm_printify_draft=True)
            self.assertEqual(state["evidence"]["draft"]["printify_product_id"],"remote-draft")
            self.assertTrue(state["evidence"]["draft"]["reconciled_existing_remote_draft"]);client.create_product.assert_not_called()

    def test_final_resume_locally_normalizes_stale_error_without_client(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=self.fixture(root);client=Mock()
            client.upload_image_contents.return_value={"id":"upload-1"};client.get_variants.return_value={"variants":[{"id":101,"title":"Black / S","is_available":True}]}
            client.list_products.return_value={"data":[]};client.create_product.return_value={"id":"draft-1"};client.get_product.return_value={"id":"draft-1","images":[]}
            orchestrator=self.orchestrator(root,evidence,client)
            state=orchestrator.create(prompt="LOVE IS LOVE",source_job_id="source",shop_id=9437076,garment_colors=["Black"],sizes=["S"],confirm_printify_draft=True,job_id="stale")
            stale={"error_id":"err-old","code":"UNEXPECTED_INTERNAL_ERROR","user_message":"safe","retryable":False,
                "suggested_action":"inspect","diagnostic_path":"/protected/err-old.json"}
            failed_at="2026-07-15T17:32:48-05:00";state["last_error"]=stale;state.pop("recovered_errors",None)
            state["transitions"].insert(-1,{"timestamp":failed_at,"input_sha":"a","output_sha":"b","operation":"handle_failure",
                "stage":"failed","result":"failed","error_id":"err-old"})
            product_orchestrator._atomic_json(orchestrator._path("stale"),state); evidence_before=copy.deepcopy(state["evidence"]);transitions_before=len(state["transitions"])
            orchestrator.adapters.client_factory=Mock(side_effect=AssertionError("client must not be created"))
            normalized=orchestrator.resume("stale");self.assertIsNone(normalized["last_error"]);self.assertEqual(normalized["evidence"],evidence_before)
            self.assertEqual(len(normalized["transitions"]),transitions_before);self.assertEqual(normalized["recovered_errors"][0]["failed_at"],failed_at)
            self.assertEqual(normalized["recovered_errors"][0]["diagnostic_path"],"/protected/err-old.json")
            again=orchestrator.resume("stale");self.assertEqual(again,normalized);orchestrator.adapters.client_factory.assert_not_called()
            report=orchestrator.report("stale").read_text();self.assertIn("Recovered error history",report);self.assertIn("workflow is currently successful",report)

    def test_cli_success_omits_active_error_fields_and_failure_includes_them(self):
        orchestrator=Mock();orchestrator._path.return_value=Path("/tmp/job/orchestrator-state.json")
        success={"job_id":"job","stage":"awaiting_human_approval","publish_status":"not_published","order_status":"not_created",
            "last_error":None,"recovered_errors":[{"error_id":"err-old"}]}
        payload=product_from_prompt.response_summary(success,orchestrator)
        self.assertEqual(payload["recovered_from_error_ids"],["err-old"])
        for key in ("code","error_id","user_message","retryable","suggested_action","diagnostic_path","last_error"):self.assertNotIn(key,payload)
        active={"error_id":"err-current","code":"VALIDATION_FAILED","user_message":"failed","retryable":False,"suggested_action":"fix","diagnostic_path":"/diag"}
        failure={**success,"stage":"failed","last_error":active}
        failed=product_from_prompt.response_summary(failure,orchestrator);self.assertEqual(failed["error_id"],"err-current");self.assertEqual(failed["last_error"],active)

    def reconciliation_fixture(self, root: Path, *, product_id="draft-owned"):
        marker="jamesos-orchestrator-marker";image_id="upload-owned";design_sha="d"*64
        black=list(range(18100,18106));dark=list(range(18148,18154));white=list(range(18540,18546));sizes=product_orchestrator.DEFAULT_SIZES
        def rows(ids,color):return [{"id":item,"title":f"{color} / {size}","is_available":True,"is_enabled":True,"price":2499} for item,size in zip(ids,sizes)]
        current_rows=rows(black,"Black")+rows(white,"White");desired_rows=rows(black,"Black")+rows(dark,"Dark Grey Heather")+rows(white,"White")
        placement={"id":image_id,"x":.5,"y":.46,"scale":.85,"angle":0,"src":"https://example.invalid/image.png",
            "imageId":image_id,"layerType":"image","name":"response-only","type":"image","width":4500,"height":5400,"flipX":False,"flipY":False}
        current={"id":product_id,"shop_id":9437076,"title":"Love Is Love","description":"Description","tags":["love",marker],"blueprint_id":12,"print_provider_id":29,
            "visible":True,"is_locked":False,"variants":current_rows,"print_areas":[{"variant_ids":black+white,"placeholders":[{"position":"front","variant_ids":black+white,"images":[placement]}]}]}
        verified=copy.deepcopy(current);verified["variants"]=desired_rows;verified["print_areas"][0]["variant_ids"]=black+dark+white;verified["print_areas"][0]["placeholders"][0]["variant_ids"]=black+dark+white
        state={"job_id":"reconcile-job","stage":"awaiting_human_approval","shop_id":9437076,"original_prompt":"LOVE IS LOVE on black, dark heather, and white",
            "brief":{"sizes":sizes,"garment_colors":["Black","White"]},"publish_status":"not_published","order_status":"not_created","transitions":[],"stage_output":{},
            "evidence":{"draft":{"printify_product_id":product_id,"draft_marker":marker,"variant_ids":black+white,"publish_status":"not_published","order_status":"not_created"},"draft_marker":marker,
                "upload":{"printify_image_id":image_id,"selected_design_sha256":design_sha},"selection":{"selected":{"png_sha256":design_sha}},
                "listing":{"price_cents":2499},"variants":{"retained":True},"mockups":[{"local_path":"mock.jpg"}]}}
        orchestrator=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=lambda:None))
        product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        return orchestrator,state,current,verified,{"variants":desired_rows},dark

    def test_reconciliation_plan_and_single_confirmed_update(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root);client=Mock()
            orchestrator.adapters.client_factory=lambda:client;client.get_product.return_value=current;client.get_variants.return_value=catalog
            state_before=orchestrator._path("reconcile-job").read_bytes()
            plan=orchestrator.reconcile_draft("reconcile-job")
            self.assertFalse(plan["write_performed"]);client.update_product.assert_not_called();self.assertEqual(plan["plan"]["variant_ids_to_add"],dark)
            self.assertEqual(orchestrator._path("reconcile-job").read_bytes(),state_before)
            assessment=plan["plan"]["publication_assessment"];self.assertTrue(assessment["safe_to_reconcile"]);self.assertTrue(assessment["remote_visible"])
            self.assertIn("not sufficient publication evidence",assessment["remote_visible_interpretation"])
            self.assertEqual(plan["plan"]["current_variant_count"],12);self.assertEqual(plan["plan"]["resulting_variant_count"],18)
            self.assertEqual([x["scale"] for x in plan["plan"]["placement_adjustment_plan"]],[.85,.918,.952]);self.assertFalse(plan["plan"]["placement_change_included"])
            client.get_product.side_effect=[current,verified]
            result=orchestrator.reconcile_draft("reconcile-job",confirmed=True);client.update_product.assert_called_once()
            payload=client.update_product.call_args.args[2];self.assertEqual(len(payload["variants"]),18);self.assertEqual({x["price"] for x in payload["variants"]},{2499})
            placeholder=payload["print_areas"][0]["placeholders"][0];image=placeholder["images"][0]
            self.assertEqual(image,{"id":"upload-owned","x":.5,"y":.46,"scale":.85,"angle":0})
            self.assertNotIn("variant_ids",placeholder);self.assertEqual(payload["print_areas"][0]["variant_ids"],[item["id"] for item in payload["variants"]])
            self.assertEqual(result["reconciliation"]["added_variant_ids"],dark);self.assertTrue(result["reconciliation"]["no_new_upload"]);self.assertTrue(result["reconciliation"]["no_new_product"])
            client.upload_image_contents.assert_not_called();client.create_product.assert_not_called()
            saved=orchestrator.load("reconcile-job");self.assertEqual(saved["brief"]["garment_colors"],product_orchestrator.DEFAULT_COLORS)
            self.assertEqual(saved["evidence"]["listing"]["colors"],product_orchestrator.DEFAULT_COLORS)
            report=orchestrator.report("reconcile-job").read_text();self.assertIn("EXISTING DRAFT UPDATED",report);self.assertIn("Enabled variants: 18",report)

    def test_reconciliation_rejects_unsafe_ownership_publication_and_order(self):
        scenarios=(("wrong_id",lambda remote:remote.update(id="other")),("marker",lambda remote:remote.update(tags=[])),
            ("published",lambda remote:remote.update(is_published=True)),("published_alias",lambda remote:remote.update(published=True)),
            ("locked",lambda remote:remote.update(is_locked=True)),("shop",lambda remote:remote.update(shop_id=2)),
            ("order",lambda remote:remote.update(orders=[{"id":"order"}])) )
        for name,mutate in scenarios:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root);mutate(current);client=Mock()
                client.get_product.return_value=current;client.get_variants.return_value=catalog;orchestrator.adapters.client_factory=lambda:client
                with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.reconcile_draft("reconcile-job",confirmed=True)
                client.update_product.assert_not_called();client.upload_image_contents.assert_not_called();client.create_product.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,*_=self.reconciliation_fixture(root,product_id=product_orchestrator.PROTECTED_PRODUCT_ID)
            orchestrator.adapters.client_factory=Mock(side_effect=AssertionError("no client"))
            with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.reconcile_draft("reconcile-job",confirmed=True)
            orchestrator.adapters.client_factory.assert_not_called()

    def test_publication_assessment_exact_blockers_and_visible_information(self):
        state={"publish_status":"not_published","transitions":[],"evidence":{"draft":{"publish_status":"not_published"}}}
        safe=product_orchestrator.assess_draft_publication_state(state,{"visible":True,"is_locked":False})
        self.assertTrue(safe["safe_to_reconcile"]);self.assertEqual(safe["explicit_blockers"],[]);self.assertTrue(safe["informational_warnings"])
        cases=(("remote.is_published",{"is_published":True},state),("remote.published",{"published":True},state),
            ("remote.is_locked",{"is_locked":True},state),("state.publish_status",{}, {**state,"publish_status":"published"}),
            ("evidence.draft.publish_status",{}, {**state,"evidence":{"draft":{"publish_status":"published"}}}))
        for expected,remote,local in cases:
            with self.subTest(expected=expected):
                result=product_orchestrator.assess_draft_publication_state(local,{"visible":True,**remote})
                self.assertFalse(result["safe_to_reconcile"]);self.assertEqual(result["explicit_blockers"][0]["field"],expected)

    def test_reconciliation_publication_error_context_names_exact_field(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root);current["published"]=True;client=Mock()
            client.get_product.return_value=current;orchestrator.adapters.client_factory=lambda:client
            with self.assertRaises(product_orchestrator.StateConflictError) as raised:orchestrator.reconcile_draft("reconcile-job")
            blockers=raised.exception.context["blockers"];self.assertEqual(blockers[0]["field"],"remote.published");self.assertIs(blockers[0]["value"],True)
            client.update_product.assert_not_called()


if __name__ == "__main__":unittest.main()
