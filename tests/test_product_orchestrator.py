from __future__ import annotations

from hashlib import sha256
import copy
from contextlib import redirect_stdout
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from jamesos.core.errors import ValidationError
from jamesos.integrations.printify_client import PrintifyAPIError
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
        desired_rows=rows(black,"Black")+rows(dark,"Dark Grey Heather")+rows(white,"White")
        remote_only=[18065,18097,18156,18161,18265,18417,18456,18457,18477,18478,18480,18481,18492,18529,38710,38722,38740,38743,38752,38755,38761,80476]
        common=[{"id":item,"title":"Navy / S","is_available":True,"is_enabled":False,"price":1900+(item%100)} for item in range(20000,20278)]
        drift=[{"id":item,"title":"Retired variant","is_available":False,"is_enabled":False,"price":2100+(index%100)} for index,item in enumerate(remote_only)]
        current_rows=copy.deepcopy(desired_rows)+common+drift
        for row in current_rows: row["is_enabled"]=row["id"] in black+white
        placement={"id":image_id,"x":.5,"y":.46,"scale":.85,"angle":0,"src":"https://example.invalid/image.png",
            "imageId":image_id,"layerType":"image","name":"response-only","type":"image","width":4500,"height":5400,"flipX":False,"flipY":False}
        current={"id":product_id,"shop_id":9437076,"title":"Love Is Love","description":"Description","tags":["love",marker],"blueprint_id":12,"print_provider_id":29,
            "visible":True,"is_locked":False,"variants":current_rows,"print_areas":[{"variant_ids":black+white,"placeholders":[
                {"position":"front","decoration_method":"dtg","variant_ids":black+white,"images":[placement]},
                {"position":"back","decoration_method":"dtg","variant_ids":black+white,"images":[]}]}]}
        verified=copy.deepcopy(current)
        for row in verified["variants"]: row["is_enabled"]=row["id"] in black+dark+white;row["price"]=2499 if row["is_enabled"] else row["price"]
        verified["print_areas"][0]["variant_ids"]=[row["id"] for row in verified["variants"]]
        state={"job_id":"reconcile-job","stage":"awaiting_human_approval","shop_id":9437076,"original_prompt":"LOVE IS LOVE on black, dark heather, and white",
            "brief":{"sizes":sizes,"garment_colors":["Black","White"]},"publish_status":"not_published","order_status":"not_created","transitions":[],"stage_output":{},
            "evidence":{"draft":{"printify_product_id":product_id,"draft_marker":marker,"variant_ids":black+white,"publish_status":"not_published","order_status":"not_created"},"draft_marker":marker,
                "upload":{"printify_image_id":image_id,"selected_design_sha256":design_sha},"selection":{"selected":{"png_sha256":design_sha}},
                "listing":{"price_cents":2499},"variants":{"retained":True},"mockups":[{"local_path":"mock.jpg"}]}}
        orchestrator=product_orchestrator.ProductOrchestrator(root/"jobs",product_orchestrator.Adapters(client_factory=lambda:None))
        product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        return orchestrator,state,current,verified,{"variants":copy.deepcopy(desired_rows)+copy.deepcopy(common)},dark

    def test_update_print_areas_exclude_empty_placeholders_and_areas(self):
        desired_ids=list(range(18));front={"id":"front-image","x":.5,"y":.46,"scale":.85,"angle":0,
            "src":"response-only","width":4500,"flipX":False}
        areas,excluded=product_orchestrator.sanitize_update_print_areas([
            {"placeholders":[{"position":"front","decoration_method":"dtg","variant_ids":[1],"images":[front]},
                {"position":"back","decoration_method":"dtg","variant_ids":[1],"images":[]}]},
            {"placeholders":[{"position":"sleeve","images":[]}]},
        ],desired_ids)
        self.assertEqual(len(areas),1);self.assertEqual(excluded,["back","sleeve"])
        self.assertEqual(areas[0]["variant_ids"],desired_ids);self.assertEqual(len(areas[0]["variant_ids"]),18)
        self.assertEqual([item["position"] for item in areas[0]["placeholders"]],["front"])
        placeholder=areas[0]["placeholders"][0];self.assertNotIn("variant_ids",placeholder)
        self.assertEqual(placeholder["decoration_method"],"dtg");self.assertEqual(set(placeholder["images"][0]),{"id","x","y","scale","angle"})
        self.assertEqual(placeholder["images"][0]["scale"],.85)

    def test_update_print_areas_preserve_front_and_back_when_both_used(self):
        desired_ids=list(range(18));placement=lambda image_id:{"id":image_id,"x":.5,"y":.46,"scale":.85,"angle":0}
        areas,excluded=product_orchestrator.sanitize_update_print_areas([{"placeholders":[
            {"position":"front","images":[placement("front-image")]},{"position":"back","images":[placement("back-image")]}
        ]}],desired_ids)
        self.assertEqual(excluded,[]);self.assertEqual(len(areas),1)
        self.assertEqual([item["position"] for item in areas[0]["placeholders"]],["front","back"])
        self.assertTrue(all(item["images"] for item in areas[0]["placeholders"]));self.assertEqual(areas[0]["variant_ids"],desired_ids)

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
            self.assertEqual(plan["plan"]["update_payload_summary"],{"payload_variant_count":318,"remote_variant_count":318,
                "current_catalog_variant_count":296,"remote_only_variant_count":22,
                "remote_only_variant_ids":[18065,18097,18156,18161,18265,18417,18456,18457,18477,18478,18480,18481,18492,18529,38710,38722,38740,38743,38752,38755,38761,80476],
                "catalog_ids_absent_from_remote_count":0,"desired_ids_present_in_remote":True,"desired_ids_present_in_catalog":True,
                "enabled_variant_count_before":12,"enabled_variant_count_after":18,"disabled_variant_count_after":300,
                "newly_enabled_variant_ids":dark,"newly_disabled_variant_ids":[],"remote_only_enabled_count_after":0,"print_area_variant_count":318,
                "variant_id_sets_match":True,"placeholder_positions":["front"],"empty_placeholders_excluded":["back"],
                "placement_scale":.85})
            client.get_product.side_effect=[current,verified]
            result=orchestrator.reconcile_draft("reconcile-job",confirmed=True);client.update_product.assert_called_once()
            payload=client.update_product.call_args.args[2];self.assertEqual(len(payload["variants"]),318)
            enabled=[item for item in payload["variants"] if item["is_enabled"]];disabled=[item for item in payload["variants"] if not item["is_enabled"]]
            self.assertEqual(len(enabled),18);self.assertEqual(len(disabled),300);self.assertEqual({item["id"] for item in enabled},{*range(18100,18106),*dark,*range(18540,18546)})
            self.assertEqual({item["price"] for item in enabled},{2499});remote_prices={item["id"]:item["price"] for item in current["variants"]}
            self.assertTrue(all(item["price"]==remote_prices[item["id"]] for item in disabled));self.assertTrue(all(set(item)=={"id","price","is_enabled"} for item in payload["variants"]))
            remote_only=set(plan["plan"]["update_payload_summary"]["remote_only_variant_ids"]);payload_by_id={item["id"]:item for item in payload["variants"]}
            self.assertTrue(remote_only<=set(payload_by_id));self.assertTrue(all(not payload_by_id[item]["is_enabled"] for item in remote_only))
            self.assertTrue(all(payload_by_id[item]["price"]==remote_prices[item] for item in remote_only))
            self.assertEqual(set(payload),{"title","description","tags","variants","print_areas"})
            self.assertNotIn("blueprint_id",payload);self.assertNotIn("print_provider_id",payload)
            placeholder=payload["print_areas"][0]["placeholders"][0];image=placeholder["images"][0]
            self.assertEqual(image,{"id":"upload-owned","x":.5,"y":.46,"scale":.85,"angle":0})
            self.assertEqual(set(image),{"id","x","y","scale","angle"});self.assertEqual(image["scale"],.85)
            self.assertNotIn("variant_ids",placeholder);self.assertEqual(len(payload["print_areas"][0]["variant_ids"]),318)
            self.assertEqual(payload["print_areas"][0]["variant_ids"],[item["id"] for item in payload["variants"]])
            self.assertTrue(remote_only<=set(payload["print_areas"][0]["variant_ids"]))
            self.assertEqual(result["reconciliation"]["added_variant_ids"],dark);self.assertTrue(result["reconciliation"]["no_new_upload"]);self.assertTrue(result["reconciliation"]["no_new_product"])
            client.upload_image_contents.assert_not_called();client.create_product.assert_not_called()
            saved=orchestrator.load("reconcile-job");self.assertEqual(saved["brief"]["garment_colors"],product_orchestrator.DEFAULT_COLORS)
            self.assertEqual(saved["evidence"]["listing"]["colors"],product_orchestrator.DEFAULT_COLORS)
            reconciliation=saved["evidence"]["draft_reconciliation"];self.assertEqual(len(reconciliation["full_remote_variant_ids"]),318)
            self.assertEqual(reconciliation["enabled_variant_ids"],[item["id"] for item in enabled])
            self.assertEqual(reconciliation["disabled_variant_count"],300);self.assertTrue(reconciliation["print_area_variant_ids_verified"])
            self.assertEqual(reconciliation["remote_only_variant_ids"],sorted(remote_only));self.assertEqual(reconciliation["remote_only_variant_count"],22)
            self.assertEqual(reconciliation["remote_only_enabled_count"],0);self.assertEqual(len(reconciliation["current_catalog_variant_ids"]),296)
            self.assertEqual(len(saved["evidence"]["draft"]["variant_ids"]),18)
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

    def test_reconciliation_variant_preflight_blocks_invalid_full_remote_set_without_mutation(self):
        def missing_price(remote,catalog,dark):remote["variants"][-1].pop("price")
        def duplicate_id(remote,catalog,dark):remote["variants"].append(copy.deepcopy(remote["variants"][-1]))
        def missing_desired(remote,catalog,dark):remote["variants"]=[item for item in remote["variants"] if item["id"]!=dark[0]]
        def desired_missing_catalog(remote,catalog,dark):catalog["variants"]=[item for item in catalog["variants"] if item["id"]!=dark[0]]
        for name,mutate in (("missing_price",missing_price),("duplicate_id",duplicate_id),("missing_desired",missing_desired),("desired_missing_catalog",desired_missing_catalog)):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root);mutate(current,catalog,dark)
                client=Mock();client.get_product.return_value=current;client.get_variants.return_value=catalog;orchestrator.adapters.client_factory=lambda:client
                state_before=orchestrator._path("reconcile-job").read_bytes()
                with self.assertRaises((ValidationError,product_orchestrator.StateConflictError)):
                    orchestrator.reconcile_draft("reconcile-job",confirmed=True)
                client.update_product.assert_not_called();self.assertEqual(orchestrator._path("reconcile-job").read_bytes(),state_before)

    def test_reconciliation_allows_remote_catalog_drift_and_unrelated_new_catalog_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root)
            catalog["variants"].append({"id":999999,"title":"New Catalog Color / S","is_available":True,"price":2499})
            client=Mock();client.get_product.return_value=current;client.get_variants.return_value=catalog;orchestrator.adapters.client_factory=lambda:client
            state_before=orchestrator._path("reconcile-job").read_bytes();plan=orchestrator.reconcile_draft("reconcile-job")
            self.assertEqual(plan["plan"]["update_payload_summary"]["remote_only_variant_count"],22)
            self.assertEqual(plan["plan"]["update_payload_summary"]["catalog_ids_absent_from_remote_count"],1)
            self.assertEqual(plan["plan"]["update_payload_summary"]["payload_variant_count"],318)
            client.update_product.assert_not_called();self.assertEqual(orchestrator._path("reconcile-job").read_bytes(),state_before)

    def review_fixture(self, root: Path, *, with_mockups: bool = True):
        orchestrator,state,remote,verified,catalog,dark=self.reconciliation_fixture(root);image_id="6a580a8e43d9a89162f792a7"
        desired={*range(18100,18106),*dark,*range(18540,18546)}
        for item in remote["variants"]:item["is_enabled"]=item["id"] in desired
        remote["print_areas"][0]["placeholders"][0]["images"][0]["id"]=image_id
        state["evidence"]["upload"]["printify_image_id"]=image_id;product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        if with_mockups:
            representatives=(18102,18150,18542);all_enabled=sorted(desired);remote["images"]=[{"src":f"https://mock.test/front/{variant_id}/preview.png?token=private",
                "mockup_id":f"front-{variant_id}-mockup","variant_ids":all_enabled,"position":"front","is_default":True} for variant_id in representatives]
        else:remote["images"]=[]
        client=Mock();client.get_product.return_value=remote;client.timeout=(1,1)
        def response(url,**_kwargs):
            variant_id=next(item for item in (18102,18150,18542) if str(item) in url);color={18102:(25,25,25),18150:(90,90,90),18542:(245,245,245)}[variant_id]
            image=Image.new("RGB",(320,480),color);content=BytesIO();image.save(content,"PNG");image.close()
            result=Mock(content=content.getvalue());result.raise_for_status.return_value=None;return result
        client.session.get.side_effect=response
        orchestrator.adapters.client_factory=lambda:client
        return orchestrator,state,remote,client

    def test_review_draft_creates_read_only_visual_package_and_safe_cli_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,client=self.review_fixture(root);state_before=orchestrator._path("reconcile-job").read_bytes()
            result=orchestrator.review_draft("reconcile-job");self.assertFalse(result["write_performed"]);self.assertFalse(result["printify_write_performed"])
            self.assertEqual(result["colors_reviewed"],product_orchestrator.DEFAULT_COLORS);self.assertEqual(result["placement"],{"x":.5,"y":.46,"scale":.85,"angle":0})
            review_root=orchestrator._path("reconcile-job").parent/"visual-review"
            expected={"black-front.png","dark-grey-heather-front.png","white-front.png","visual-review-sheet.png","visual-review.json","visual-review.html"}
            self.assertEqual({path.name for path in review_root.iterdir()},expected)
            self.assertTrue(all(path.resolve().is_relative_to(orchestrator._path("reconcile-job").parent.resolve()) for path in review_root.iterdir()))
            report=json.loads(Path(result["json_report_path"]).read_text());checks=report["checks"]
            self.assertTrue(all(item["mockup_available"] for item in checks["mockups"]));self.assertTrue(checks["artwork_image_id_matches"])
            self.assertEqual([item["selected_variant_id"] for item in checks["mockups"]],[18102,18150,18542])
            self.assertEqual([item["selected_mockup_id"] for item in checks["mockups"]],["front-18102-mockup","front-18150-mockup","front-18542-mockup"])
            self.assertTrue(all(item["selection_method"]=="exact_mockup_variant" and item["color_match_verified"] for item in checks["mockups"]))
            self.assertEqual(len({item["downloaded_sha256"] for item in checks["mockups"]}),3);self.assertEqual(result["recommended_scale_action"],"keep_0.85")
            self.assertTrue(checks["front_artwork_present"]);self.assertTrue(checks["back_artwork_absent"]);self.assertEqual(checks["placement"]["scale"],.85)
            html_report=Path(result["html_report_path"]).read_text();self.assertIn("Black - verified",html_report);self.assertNotIn("—",html_report)
            self.assertNotIn("mock.test",json.dumps(report));self.assertEqual(orchestrator._path("reconcile-job").read_bytes(),state_before)
            for method in (client.update_product,client.create_product,client.upload_image_contents,client.upload_image_url):method.assert_not_called()
            output=StringIO()
            with patch.object(product_from_prompt,"ProductOrchestrator",return_value=orchestrator),patch.object(product_from_prompt.sys,"argv",["product_from_prompt.py","review-draft","--job-id","reconcile-job"]),redirect_stdout(output):
                self.assertEqual(product_from_prompt._main(),0)
            cli=json.loads(output.getvalue());self.assertEqual(cli["result"],"draft_visual_review_created")
            self.assertNotIn("mock.test",output.getvalue());self.assertNotIn("private",output.getvalue())

    def test_review_draft_rejects_ownership_publication_and_lock_without_files_or_writes(self):
        scenarios=(("ownership",lambda remote:remote.update(id="other")),("published",lambda remote:remote.update(is_published=True)),
            ("locked",lambda remote:remote.update(is_locked=True)))
        for name,mutate in scenarios:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);orchestrator,state,remote,client=self.review_fixture(root);mutate(remote)
                with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.review_draft("reconcile-job")
                self.assertFalse((orchestrator._path("reconcile-job").parent/"visual-review").exists())
                client.session.get.assert_not_called();client.update_product.assert_not_called();client.create_product.assert_not_called()

    def test_review_draft_missing_mockups_requires_manual_review(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,client=self.review_fixture(root,with_mockups=False)
            result=orchestrator.review_draft("reconcile-job");self.assertEqual(result["recommended_scale_action"],"manual_review_required")
            report=json.loads(Path(result["json_report_path"]).read_text());self.assertTrue(all(not item["mockup_available"] for item in report["checks"]["mockups"]))
            client.session.get.assert_not_called();client.update_product.assert_not_called()

    def test_review_draft_ignores_variant_membership_without_exact_mockup_variant(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,client=self.review_fixture(root)
            for index,image in enumerate(remote["images"]):image.update(mockup_id=f"unrelated-{index}",src=f"https://mock.test/front/unrelated-{index}.png")
            result=orchestrator.review_draft("reconcile-job");report=json.loads(Path(result["json_report_path"]).read_text())
            self.assertEqual(result["recommended_scale_action"],"manual_review_required");client.session.get.assert_not_called()
            self.assertTrue(all(not item["mockup_available"] and not item["color_match_verified"] for item in report["checks"]["mockups"]))
            self.assertTrue(all("exact_mockup_variant_missing" in item["issues"] for item in report["checks"]["mockups"]))

    def test_review_draft_duplicate_hashes_flag_color_mismatch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,client=self.review_fixture(root)
            image=Image.new("RGB",(320,480),(100,100,100));content=BytesIO();image.save(content,"PNG");image.close()
            response=Mock(content=content.getvalue());response.raise_for_status.return_value=None;client.session.get.side_effect=None;client.session.get.return_value=response
            result=orchestrator.review_draft("reconcile-job");report=json.loads(Path(result["json_report_path"]).read_text());records=report["checks"]["mockups"]
            self.assertEqual(result["recommended_scale_action"],"manual_review_required");self.assertEqual(len({item["downloaded_sha256"] for item in records}),1)
            self.assertTrue(all(item["mockup_available"] and not item["color_match_verified"] for item in records))
            self.assertTrue(all("mockup_color_mismatch" in item["issues"] for item in records));self.assertIn("downloaded, not color-verified",Path(result["html_report_path"]).read_text())

    def listing_fixture(self, root: Path):
        orchestrator,state,remote,verified,catalog,dark=self.reconciliation_fixture(root,product_id=product_orchestrator.LISTING_PRODUCT_ID)
        desired=set(product_orchestrator.RECOVERY_VARIANT_IDS);marker=product_orchestrator.RECOVERY_TAGS[-1]
        for item in remote["variants"]:item["is_enabled"]=item["id"] in desired;item["price"]=2499 if item["is_enabled"] else item["price"]
        remote["tags"]=[*product_orchestrator.RECOVERY_TAGS];remote["title"]=product_orchestrator.RECOVERY_TITLE;remote["description"]=product_orchestrator.RECOVERY_DESCRIPTION
        remote["print_areas"][0]["placeholders"][0]["images"][0]["id"]=product_orchestrator.RECOVERY_UPLOAD_ID
        state["evidence"]["draft_marker"]=marker;state["evidence"]["draft"]["draft_marker"]=marker
        state["evidence"]["upload"]["printify_image_id"]=product_orchestrator.RECOVERY_UPLOAD_ID
        state["evidence"]["draft_recovery_history"]=[{"status":"verified","deleted_product_id":product_orchestrator.RECOVERY_DELETED_PRODUCT_ID,
            "replacement_product_id":product_orchestrator.LISTING_PRODUCT_ID,"historical":"preserved"}]
        state["recovered_errors"]=[{"error_id":"old-error"}];state["evidence"]["draft_reconciliation"]={"status":"preserved"}
        product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        review_root=orchestrator._path("reconcile-job").parent/"visual-review";review_root.mkdir()
        product_orchestrator._atomic_json(review_root/"visual-review.json",{"product_id":product_orchestrator.LISTING_PRODUCT_ID,
            "recommended_scale_action":"keep_0.85","checks":{"mockups":[{"color":color,"verified_mockup_available":True,
                "downloaded_sha256":str(index)*64} for index,color in enumerate(product_orchestrator.DEFAULT_COLORS,1)]}})
        client=Mock();client.get_product.return_value=remote;client.get_blueprint.return_value={"title":"Bella+Canvas 3001 unisex jersey crew tee",
            "claim_support":"direct-to-garment DTG machine wash cold tumble dry low hang dry do not bleach do not dry clean do not iron"}
        client.get_variants.return_value=catalog;orchestrator.adapters.client_factory=lambda:client
        replacement=copy.deepcopy(remote);replacement.update(title=product_orchestrator.ETSY_TITLE,description=product_orchestrator.ETSY_DESCRIPTION,tags=product_orchestrator.ETSY_TAGS)
        replacement["print_areas"]=product_orchestrator.sanitize_update_print_areas(remote["print_areas"],[item["id"] for item in remote["variants"]])[0]
        return orchestrator,state,remote,replacement,client

    def test_prepare_listing_dry_run_is_read_only_exact_and_marker_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,replacement,client=self.listing_fixture(root);remote["tags"]=["buyer tag"]
            before=orchestrator._path("reconcile-job").read_bytes();result=orchestrator.prepare_listing("reconcile-job")
            self.assertEqual(result,{"result":"listing_preparation_plan","write_performed":False,"printify_write_performed":False,
                "product_id":product_orchestrator.LISTING_PRODUCT_ID,"proposed_title":product_orchestrator.ETSY_TITLE,"seo_tag_count":13,
                "price_cents":2499,"enabled_variant_count":18,"placement_scale":.85,"primary_mockup_color":"Black",
                "primary_mockup_manual_action_required":True,"gpsr_manual_confirmation_required":True,"publish_status":"not_published",
                "order_status":"not_created","safe_to_update":True})
            self.assertEqual(orchestrator._path("reconcile-job").read_bytes(),before);client.update_product.assert_not_called()
            self.assertEqual(len(product_orchestrator.ETSY_TAGS),13);self.assertTrue(all(len(tag)<=20 and len(tag.split())>=2 for tag in product_orchestrator.ETSY_TAGS))
            self.assertNotIn("jamesos",json.dumps([product_orchestrator.ETSY_TITLE,product_orchestrator.ETSY_DESCRIPTION,product_orchestrator.ETSY_TAGS]).lower())

    def test_prepare_listing_confirmed_updates_once_and_preserves_product_document_and_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,replacement,client=self.listing_fixture(root);client.get_product.side_effect=[remote,replacement]
            result=orchestrator.prepare_listing("reconcile-job",confirmed=True);client.update_product.assert_called_once()
            payload=client.update_product.call_args.args[2];self.assertEqual(set(payload),{"title","description","tags","variants","print_areas"})
            self.assertEqual(payload["title"],product_orchestrator.ETSY_TITLE);self.assertEqual(payload["description"],product_orchestrator.ETSY_DESCRIPTION)
            self.assertEqual(payload["tags"],product_orchestrator.ETSY_TAGS);self.assertEqual(len(payload["variants"]),318)
            self.assertEqual({item["id"] for item in payload["variants"]},{item["id"] for item in remote["variants"]})
            self.assertEqual({item["id"] for item in payload["variants"] if item["is_enabled"]},set(product_orchestrator.RECOVERY_VARIANT_IDS))
            self.assertNotIn("images",payload);self.assertNotIn("mockups",payload);self.assertNotIn("default",payload)
            self.assertEqual(result["stage"],"awaiting_printify_human_review");saved=orchestrator.load("reconcile-job")
            self.assertEqual(saved["stage"],"awaiting_printify_human_review");prepared=saved["evidence"]["listing_preparation"]
            self.assertEqual(saved["active_product_id"],product_orchestrator.LISTING_PRODUCT_ID);self.assertTrue(saved["visual_review_completed"])
            self.assertEqual(saved["visual_review_recommendation"],"keep_0.85");self.assertFalse(saved["human_artistic_approval"])
            self.assertFalse(prepared["human_artistic_approval"]);self.assertTrue(prepared["primary_mockup_manual_action_required"])
            self.assertTrue(prepared["gpsr_manual_confirmation_required"]);self.assertTrue(prepared["shipping_profile_manual_confirmation_required"])
            self.assertEqual(prepared["local_draft_marker"],product_orchestrator.RECOVERY_TAGS[-1]);self.assertEqual(saved["recovered_errors"],[{"error_id":"old-error"}])
            self.assertEqual(saved["evidence"]["draft_reconciliation"],{"status":"preserved"});self.assertEqual(len(saved["evidence"]["draft_recovery_history"]),1)
            for method in (client.create_product,client.upload_image_contents,client.upload_image_url,client.publish_product,client.create_order,client.delete_product):method.assert_not_called()

    def test_prepare_listing_failed_update_not_retried_and_unsupported_claims_block(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,replacement,client=self.listing_fixture(root)
            client.update_product.side_effect=PrintifyAPIError("update_product",500,"failed","failed")
            with self.assertRaises(PrintifyAPIError):orchestrator.prepare_listing("reconcile-job",confirmed=True)
            client.update_product.assert_called_once();self.assertNotEqual(orchestrator.load("reconcile-job")["stage"],"awaiting_printify_human_review")
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,replacement,client=self.listing_fixture(root);client.get_blueprint.return_value={"title":"unknown shirt"}
            with self.assertRaises(ValidationError):orchestrator.prepare_listing("reconcile-job")
            client.update_product.assert_not_called()

    def test_prepare_listing_cli_uses_dedicated_confirmation_and_protected_product_never_writes(self):
        orchestrator=Mock();orchestrator.prepare_listing.return_value={"result":"listing_preparation_plan"}
        for argv,confirmed in ((["product_from_prompt.py","prepare-listing","--job-id","job"],False),
                               (["product_from_prompt.py","prepare-listing","--job-id","job","--confirm-printify-listing-update"],True)):
            with self.subTest(confirmed=confirmed):
                orchestrator.prepare_listing.reset_mock();output=StringIO()
                with patch.object(product_from_prompt,"ProductOrchestrator",return_value=orchestrator),patch.object(product_from_prompt.sys,"argv",argv),redirect_stdout(output):self.assertEqual(product_from_prompt._main(),0)
                orchestrator.prepare_listing.assert_called_once_with("job",confirmed=confirmed)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,remote,replacement,client=self.listing_fixture(root)
            state["evidence"]["draft"]["printify_product_id"]=product_orchestrator.PROTECTED_PRODUCT_ID;product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.prepare_listing("reconcile-job",confirmed=True)
            client.get_product.assert_not_called();client.update_product.assert_not_called()

    def recovery_fixture(self, root: Path):
        orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root,product_id=product_orchestrator.RECOVERY_DELETED_PRODUCT_ID)
        marker=product_orchestrator.RECOVERY_TAGS[-1];state["evidence"]["draft_marker"]=marker;state["evidence"]["draft"]["draft_marker"]=marker
        state["evidence"]["listing"].update({"title":product_orchestrator.RECOVERY_TITLE,"description":product_orchestrator.RECOVERY_DESCRIPTION,
            "tags":product_orchestrator.RECOVERY_TAGS[:-1],"price_cents":2499})
        state["evidence"]["upload"].update(printify_image_id=product_orchestrator.RECOVERY_UPLOAD_ID)
        state["recovered_errors"]=[{"error_id":"historical-error"}];state["evidence"]["draft_reconciliation"]={"status":"historical"}
        product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
        deleted=PrintifyAPIError("get_product",404,"not_found","Product not found")
        client=Mock();client.get_product.side_effect=[deleted];client.get_upload.return_value={"id":product_orchestrator.RECOVERY_UPLOAD_ID,
            "mime_type":"image/png","width":4500,"height":5400};client.list_products.return_value={"data":[]};client.get_variants.return_value=catalog
        orchestrator.adapters.client_factory=lambda:client
        replacement={"id":"replacement-draft","shop_id":9437076,"blueprint_id":12,"print_provider_id":29,
            "title":product_orchestrator.RECOVERY_TITLE,"tags":product_orchestrator.RECOVERY_TAGS,"visible":True,"is_locked":False,
            "variants":[{"id":item,"price":2499,"is_enabled":True} for item in product_orchestrator.RECOVERY_VARIANT_IDS],
            "print_areas":[{"variant_ids":product_orchestrator.RECOVERY_VARIANT_IDS,"placeholders":[{"position":"front","decoration_method":"dtg",
                "images":[{"id":product_orchestrator.RECOVERY_UPLOAD_ID,"x":.5,"y":.46,"scale":.85,"angle":0}]},{"position":"back","images":[]}]}],
            "order_status":"not_created","orders":[]}
        return orchestrator,state,client,replacement,deleted

    def test_recover_draft_default_is_read_only_plan_and_reuses_upload(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root);before=orchestrator._path("reconcile-job").read_bytes()
            result=orchestrator.recover_draft("reconcile-job")
            self.assertEqual(result,{"result":"draft_recovery_plan","write_performed":False,"printify_write_performed":False,"job_id":"reconcile-job",
                "deleted_product_id":product_orchestrator.RECOVERY_DELETED_PRODUCT_ID,"shop_id":9437076,"upload_id":product_orchestrator.RECOVERY_UPLOAD_ID,
                "reuse_existing_upload":True,"new_upload_required":False,"replacement_product_required":True,"enabled_variant_count":18,"price_cents":2499,
                "placement":{"x":.5,"y":.46,"scale":.85,"angle":0},"publish_status":"not_published","order_status":"not_created","safe_to_recover":True})
            self.assertEqual(orchestrator._path("reconcile-job").read_bytes(),before);client.create_product.assert_not_called();client.update_product.assert_not_called()
            client.upload_image_contents.assert_not_called();client.upload_image_url.assert_not_called()

    def test_recover_draft_cli_uses_dedicated_confirmation_flag(self):
        orchestrator=Mock();orchestrator.recover_draft.return_value={"result":"draft_recovery_plan"}
        for argv,confirmed in ((["product_from_prompt.py","recover-draft","--job-id","job"],False),
                               (["product_from_prompt.py","recover-draft","--job-id","job","--confirm-printify-draft-recovery"],True)):
            with self.subTest(confirmed=confirmed):
                orchestrator.recover_draft.reset_mock();output=StringIO()
                with patch.object(product_from_prompt,"ProductOrchestrator",return_value=orchestrator),patch.object(product_from_prompt.sys,"argv",argv),redirect_stdout(output):
                    self.assertEqual(product_from_prompt._main(),0)
                orchestrator.recover_draft.assert_called_once_with("job",confirmed=confirmed);self.assertEqual(json.loads(output.getvalue())["result"],"draft_recovery_plan")

    def test_recover_draft_refuses_existing_old_matching_replacement_and_protected_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root);client.get_product.side_effect=None
            client.get_product.return_value={"id":product_orchestrator.RECOVERY_DELETED_PRODUCT_ID}
            with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.recover_draft("reconcile-job")
            client.create_product.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root)
            client.list_products.return_value={"data":[{"id":"replacement","title":product_orchestrator.RECOVERY_TITLE,"tags":[]}]}
            with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.recover_draft("reconcile-job")
            client.create_product.assert_not_called()
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root)
            state["evidence"]["draft_recovery_history"]=[{"replacement_product_id":product_orchestrator.PROTECTED_PRODUCT_ID}]
            product_orchestrator._atomic_json(orchestrator._path("reconcile-job"),state)
            with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.recover_draft("reconcile-job")
            client.get_product.assert_not_called();client.create_product.assert_not_called()

    def test_recover_draft_confirmed_creates_once_verifies_and_preserves_history(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root)
            client.create_product.return_value={"id":"replacement-draft"};client.get_product.side_effect=[deleted,replacement]
            result=orchestrator.recover_draft("reconcile-job",confirmed=True);client.create_product.assert_called_once()
            payload=client.create_product.call_args.args[1];self.assertEqual(len(payload["variants"]),18);self.assertTrue(all(item["price"]==2499 for item in payload["variants"]))
            self.assertEqual(payload["print_areas"][0]["placeholders"][0]["images"][0],{"id":product_orchestrator.RECOVERY_UPLOAD_ID,"x":.5,"y":.46,"scale":.85,"angle":0})
            self.assertEqual(result["result"],"deleted_draft_recovered");self.assertEqual(result["replacement_product_id"],"replacement-draft")
            saved=orchestrator.load("reconcile-job");self.assertEqual(saved["evidence"]["draft"]["printify_product_id"],"replacement-draft")
            recovery=saved["evidence"]["draft_recovery_history"][-1];self.assertEqual(recovery["deleted_product_id"],product_orchestrator.RECOVERY_DELETED_PRODUCT_ID)
            self.assertEqual(recovery["replacement_product_id"],"replacement-draft");self.assertEqual(recovery["status"],"verified")
            self.assertEqual(saved["recovered_errors"],[{"error_id":"historical-error"}]);self.assertEqual(saved["evidence"]["draft_reconciliation"],{"status":"historical"})
            self.assertEqual(saved["evidence"]["visual_review_status"]["status"],"stale")
            for method in (client.update_product,client.upload_image_contents,client.upload_image_url,client.publish_product,client.create_order):method.assert_not_called()

    def test_recover_draft_creation_is_not_retried_and_failed_verification_retains_new_id(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root)
            client.create_product.side_effect=PrintifyAPIError("create_product",500,"failed","failed")
            with self.assertRaises(PrintifyAPIError):orchestrator.recover_draft("reconcile-job",confirmed=True)
            client.create_product.assert_called_once();self.assertNotIn("draft_recovery_history",orchestrator.load("reconcile-job")["evidence"])
        for field in ("is_published","is_locked"):
            with self.subTest(field=field),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);orchestrator,state,client,replacement,deleted=self.recovery_fixture(root);replacement[field]=True
                client.create_product.return_value={"id":"replacement-draft"};client.get_product.side_effect=[deleted,replacement]
                with self.assertRaises(product_orchestrator.StateConflictError) as raised:orchestrator.recover_draft("reconcile-job",confirmed=True)
                client.create_product.assert_called_once();saved=orchestrator.load("reconcile-job")
                recovery=saved["evidence"]["draft_recovery_history"][-1];self.assertEqual(recovery["replacement_product_id"],"replacement-draft")
                self.assertEqual(recovery["status"],"verification_failed");self.assertEqual(raised.exception.context["replacement_product_id"],"replacement-draft")

    def test_reconciliation_verification_rejects_total_or_enabled_variant_drift(self):
        for name,mutate in (("total",lambda verified:verified["variants"].pop()),
                            ("enabled",lambda verified:verified["variants"][-1].update(is_enabled=True)),
                            ("print_area",lambda verified:verified["print_areas"][0]["variant_ids"].pop())):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);orchestrator,state,current,verified,catalog,dark=self.reconciliation_fixture(root);mutate(verified);client=Mock()
                client.get_product.side_effect=[current,verified];client.get_variants.return_value=catalog;orchestrator.adapters.client_factory=lambda:client
                with self.assertRaises(product_orchestrator.StateConflictError):orchestrator.reconcile_draft("reconcile-job",confirmed=True)
                client.update_product.assert_called_once()

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
