from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any,Callable
from uuid import uuid4
from PIL import Image

from jamesos.core.errors import StateConflictError,ValidationError
from jamesos.core.profiles.selection import load_commerce_profile_by_id
from jamesos.services import product_orchestrator
from jamesos.services.commerce_preparation import UnifiedCommercePreparation
from jamesos.services.commerce_workflow import CommerceWorkflow,_atomic_json
from jamesos.services.error_handler import handle_error


def _now()->str:return datetime.now().astimezone().isoformat()
def _last_completed_stage(state:dict[str,Any])->str|None:
    completed=[str(item.get("stage")) for item in state.get("transitions") or [] if item.get("result")=="completed" and item.get("stage")]
    return completed[-1] if completed else None
def _clean(value:Any,limit:int,field:str,*,required:bool=False)->str:
    if value is None:value=""
    if not isinstance(value,str):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} must be text.",operation="commerce_creation",stage="input")
    value=value.replace("\r\n","\n").replace("\r","\n").strip()
    if required and not value:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} is required.",operation="commerce_creation",stage="input")
    if len(value)>limit or any(ord(char)<32 and char not in "\n\t" for char in value):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} is invalid or too long.",operation="commerce_creation",stage="input")
    return value


_ARTWORK_REJECTIONS={"hard_dimensions":("dimensions_too_small","Artwork dimensions do not meet the print requirement."),"hard_valid_transparency":("invalid_transparency","Artwork transparency is missing or invalid."),"hard_no_unexpected_opaque_canvas":("background_detected","An opaque background was detected where transparency is required."),"hard_artwork_integrity":("file_corruption","The artwork file could not be validated."),"hard_candidate_unique":("duplicate_candidate","The candidate duplicates another generated design."),"hard_phrase_correct":("typography_readability","The required phrase was not rendered exactly."),"hard_no_duplicate_or_missing_text":("typography_readability","Required typography was missing or duplicated."),"hard_safe_bounds":("incorrect_aspect_or_bounds","Artwork extends outside the safe print bounds."),"hard_print_resolution":("dimensions_too_small","Artwork resolution is below the print requirement."),"hard_novelty":("duplicate_candidate","The artwork is not materially distinct."),"hard_prompt_adherence":("candidate_quality_rejection","Artwork did not follow the approved brief."),"hard_negative_constraints":("candidate_quality_rejection","Artwork included prohibited visual content.")}


def _artwork_diagnostics(state:dict[str,Any])->dict[str,Any]:
    evidence=state.get("evidence") or {};candidates=evidence.get("candidates") if isinstance(evidence.get("candidates"),list) else [];diversity=evidence.get("candidate_diversity") if isinstance(evidence.get("candidate_diversity"),dict) else {};rows=[]
    diversity_rows={str(item.get("candidate_id") or ""):item for item in diversity.get("candidates") or [] if isinstance(item,dict)}
    for index,candidate in enumerate(candidates):
        checks=candidate.get("quality_checks") if isinstance(candidate.get("quality_checks"),dict) else {};rejections=[]
        for key,passed in checks.items():
            if key.startswith("hard_") and passed is not True:
                code,explanation=_ARTWORK_REJECTIONS.get(key,("candidate_quality_rejection","Artwork failed a required local eligibility check."));rejections.append({"code":code,"explanation":explanation})
        for reason in (diversity_rows.get(str(candidate.get("candidate_id") or ""),{}).get("rejection_reasons") or candidate.get("rejection_reasons") or []):
            category=str(reason.get("category") if isinstance(reason,dict) else reason);code="duplicate_candidate" if category=="novelty" else "typography_readability" if category=="prompt_adherence" else "candidate_quality_rejection";rejections.append({"code":code,"explanation":"Artwork was rejected by the local novelty check." if code=="duplicate_candidate" else "Artwork did not preserve the requested phrase and design direction."})
        detected_format=str(candidate.get("detected_format") or "PNG").upper();dimensions=candidate.get("dimensions") or candidate.get("canvas_dimensions");byte_size=candidate.get("byte_size");alpha="present" if candidate.get("visible_alpha_bounds") else "unknown"
        path=Path(str(candidate.get("png_path") or ""))
        try:
            if path.is_file():
                byte_size=path.stat().st_size
                with Image.open(path) as image:detected_format=str(image.format or detected_format);dimensions=list(image.size);alpha="present" if "A" in image.getbands() and image.getchannel("A").getextrema()[0]<255 else "opaque"
        except (OSError,ValueError):rejections.append({"code":"file_corruption","explanation":"The artwork file could not be inspected safely."})
        unique=[]
        for item in rejections:
            if item not in unique:unique.append(item)
        rows.append({"candidate_id":str(candidate.get("candidate_id") or f"candidate-{index+1}"),"detected_format":detected_format,"dimensions":dimensions,"byte_size":byte_size,"alpha_transparency":alpha,"eligible":not unique,"rejections":unique})
    selected=(((evidence.get("selection") or {}).get("selected") or {}).get("candidate_id"));accepted=sum(item["eligible"] for item in rows)
    if not rows and (state.get("stage")=="generation_failed" or (state.get("generation_failure") or {}).get("terminal_local_failure")):rows=[]
    return {"image_generation_readiness":"ready" if rows or selected else "unavailable_or_no_output" if state.get("stage")=="generation_failed" else "not_tested","request_started":state.get("stage") not in {"generation_queued","prompt_received"},"request_completed":bool(rows or state.get("stage")=="generation_failed"),"candidate_count":len(rows),"accepted_candidate_count":accepted,"rejected_candidate_count":len(rows)-accepted,"selected_candidate_id":selected,"candidates":rows,"zero_candidate_rejection":{"code":"no_candidates","explanation":"The local image-generation stage returned no candidates."} if not rows and state.get("stage")=="generation_failed" else None}


_PLACEHOLDER_PHRASES={"test","testing","asdf","qwerty","lorem ipsum","placeholder","sample text","foo","bar"}
_BRIEF_STOPWORDS={"a","an","and","as","at","be","by","for","from","in","is","it","of","on","or","that","the","this","to","with"}
_DESIGN_ATTRIBUTE_WORDS={
    "audience","community","fan","fans","gift","humor","market","pride","trader","traders","theme","teacher","teachers","investor","investors",
    "bold","clean","distressed","minimal","minimalist","modern","playful","retro","style","typographic","typography","vintage",
    "arched","badge","centered","composition","front","layout","stacked","symmetrical",
    "apparel","garment","hoodie","shirt","tee","tshirt","unisex","workwear",
    "art","artwork","color","colors","contrast","graphic","icon","illustration","linework","motif","palette",
}


def validate_product_input(exact_phrase:str,product_brief:str)->dict[str,Any]:
    """Bounded semantic preflight; it performs no model or provider work."""
    token_pattern=re.compile(r"[A-Za-z][A-Za-z'-]*")
    brief_tokens=[item.casefold() for item in token_pattern.findall(product_brief)]
    phrase_tokens=[item.casefold() for item in token_pattern.findall(exact_phrase)]
    meaningful=[item for item in brief_tokens if item not in _BRIEF_STOPWORDS]
    unique=len(set(meaningful));max_repeat=max((meaningful.count(item) for item in set(meaningful)),default=0)
    nonspace=sum(not char.isspace() for char in product_brief);alpha=sum(char.isalpha() for char in product_brief)
    alpha_ratio=alpha/max(1,nonspace);lexical_diversity=unique/max(1,len(meaningful));repeated_ratio=max_repeat/max(1,len(meaningful))
    normalized_brief=" ".join(brief_tokens);normalized_phrase=" ".join(phrase_tokens)
    placeholder=normalized_brief in _PLACEHOLDER_PHRASES or bool(brief_tokens) and all(item in _PLACEHOLDER_PHRASES for item in brief_tokens)
    repeats_phrase=bool(normalized_phrase) and normalized_brief==normalized_phrase
    attributes=sorted(set(brief_tokens)&_DESIGN_ATTRIBUTE_WORDS)
    reasons=[]
    if placeholder:reasons.append("placeholder_text")
    if len(meaningful)<3:reasons.append("too_few_meaningful_words")
    if len(meaningful)>=3 and lexical_diversity<.55:reasons.append("low_lexical_diversity")
    if len(meaningful)>=3 and repeated_ratio>=.67:reasons.append("repeated_tokens")
    if alpha_ratio<.60:reasons.append("insufficient_alphabetic_content")
    if repeats_phrase:reasons.append("brief_repeats_exact_phrase")
    if not attributes:reasons.append("missing_design_direction")
    phrase_normalized=" ".join(exact_phrase.split())
    if phrase_normalized:
        phrase_compact=" ".join(phrase_tokens)
        phrase_alpha=sum(char.isalpha() for char in phrase_normalized);phrase_visible=sum(not char.isspace() for char in phrase_normalized)
        short_random=(len("".join(phrase_tokens))<=3 and phrase_normalized!=phrase_normalized.upper() and not any(char in "aeiouyAEIOUY" for char in phrase_normalized))
        if not phrase_tokens or phrase_alpha/max(1,phrase_visible)<.50 or phrase_compact in _PLACEHOLDER_PHRASES or short_random:reasons.append("exact_phrase_not_intentional")
    diagnostic={"meaningful_word_count":len(meaningful),"unique_meaningful_word_count":unique,"lexical_diversity":round(lexical_diversity,3),
        "alphabetic_content_ratio":round(alpha_ratio,3),"repeated_token_ratio":round(repeated_ratio,3),"design_attributes":attributes,"reasons":list(dict.fromkeys(reasons))}
    if reasons:
        raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product input failed semantic preflight: "+", ".join(diagnostic["reasons"])+".",
            user_message="Add a clearer visual style, audience, or composition direction.",operation="commerce_creation",stage="product_brief_preflight",
            context={"product_input_preflight":diagnostic,"external_write_performed":False,"image_generation_calls":0,"provider_calls":0},
            state={"provider_write_status":"not_started","publish_status":"not_published","order_status":"not_created"})
    return diagnostic


class CommerceCreationService:
    def __init__(self,workflow:CommerceWorkflow|None=None,*,profile_loader:Callable[...,dict[str,Any]]=load_commerce_profile_by_id):
        self.workflow=workflow or CommerceWorkflow();self.orchestrator=self.workflow.orchestrator;self.profile_loader=profile_loader

    def _profile(self,profile_id:str)->dict[str,Any]:
        profile=self.profile_loader(profile_id,required=True);config=profile.get("configuration") or {}
        if profile.get("profile_type")!="commerce_shop" or profile.get("enabled") is not True:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Requested commerce profile is disabled or invalid.",operation="commerce_creation",stage="profile")
        if type(config.get("printify_shop_id")) is not int or not str(config.get("etsy_shop_slug") or "").strip():raise ValidationError("VALIDATION_FAILED",diagnostic_message="Commerce profile lacks an exact Printify and Etsy destination binding.",operation="commerce_creation",stage="profile")
        return profile

    def create_job(self,*,commerce_profile_id:str,product_brief:str,exact_phrase:str="",listing_title:str="",special_instructions:str="",
            destination_confirmed:bool=False,request_id:str|None=None)->dict[str,Any]:
        profile=self._profile(commerce_profile_id);config=profile["configuration"]
        brief=_clean(product_brief,5000,"product_brief",required=True);phrase=_clean(exact_phrase,500,"exact_phrase");title=_clean(listing_title,140,"listing_title");instructions=_clean(special_instructions,3000,"special_instructions")
        preflight=validate_product_input(phrase,brief)
        if destination_confirmed is not True:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Exact commerce destination confirmation is required.",operation="commerce_creation",stage="destination")
        request_id=_clean(request_id or uuid4().hex,128,"request_id",required=True);fingerprint=sha256(request_id.encode()).hexdigest()
        for path in self.orchestrator.root.glob("*/orchestrator-state.json") if self.orchestrator.root.is_dir() else []:
            try:existing=json.loads(path.read_text())
            except (OSError,ValueError):continue
            if existing.get("creation_request_sha256")==fingerprint:return {"result":"commerce_generation_queued","job_id":existing["job_id"],"already_exists":True,"stage":existing.get("stage")}
        job_id=f"product-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}";now=_now()
        destination={"printify_shop_id":config["printify_shop_id"],"printify_shop_title":str(config.get("printify_shop_title") or profile.get("display_name") or commerce_profile_id),
            "etsy_shop_slug":str(config["etsy_shop_slug"]),"etsy_shop_url":str(config.get("etsy_shop_url") or f"https://www.etsy.com/shop/{config['etsy_shop_slug']}"),
            "marketplace_write_route":str(config.get("marketplace_write_route") or "printify_connected_sales_channel")}
        prompt="\n\n".join(item for item in (f"Exact phrase:\n{phrase}" if phrase else "",brief,
            f"Brand concept: {config.get('concept_prompt')}" if config.get("concept_prompt") else "",f"Avoid: {config.get('negative_prompt')}" if config.get("negative_prompt") else "",instructions) if item)
        state={"job_id":job_id,"mode":product_orchestrator.MODE,"policy":product_orchestrator.POLICY,"shop_id":destination["printify_shop_id"],"source_job_id":None,
            "original_prompt":prompt,"brief":None,"stage":"generation_queued","stage_output":{},"transitions":[{"timestamp":now,"input_sha":product_orchestrator._json_sha({}),"output_sha":product_orchestrator._json_sha({"prompt_sha256":sha256(prompt.encode()).hexdigest()}),"operation":"queue_commerce_generation","stage":"prompt_received","result":"completed","error_id":None}],"evidence":{},
            "commerce_profile_id":commerce_profile_id,"profile_id":commerce_profile_id,"selected_profile_id":commerce_profile_id,"brand_display_name":str(profile.get("display_name") or config.get("brand_name") or commerce_profile_id),
            "destination":destination,"product_brief":{"exact_phrase":phrase,"brief":brief,"requested_listing_title":title,"special_instructions":instructions},"revision_number":0,
            "provider_write_status":"not_started","publish_status":"not_published","order_status":"not_created","destination_confirmed":True,"destination_confirmed_at":now,
            "creation_request_sha256":fingerprint,"product_input_preflight":preflight,"created_at":now,"updated_at":now}
        product_orchestrator._atomic_json(self.orchestrator._path(job_id),state);_atomic_json(self.orchestrator._path(job_id).parent/"creation-audit.json",{"event":"generation_queued","job_id":job_id,"profile_id":commerce_profile_id,"created_at":now})
        return {"result":"commerce_generation_queued","job_id":job_id,"stage":"generation_queued","brand_display_name":state["brand_display_name"],"destination":destination,"already_exists":False,
            "publication_status":"not_published","order_status":"not_created"}

    def run_generation(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id);profile_id=str(state.get("commerce_profile_id") or "");profile=self._profile(profile_id);config=profile["configuration"];destination=state.get("destination") or {}
        if destination.get("printify_shop_id")!=config.get("printify_shop_id") or destination.get("etsy_shop_slug")!=config.get("etsy_shop_slug") or state.get("destination_confirmed") is not True:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Immutable job destination no longer matches its bound profile.",operation="commerce_creation",stage="destination")
        if state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Generation requires an unpublished job with no order.",operation="commerce_creation",stage="state")
        if state.get("stage")=="awaiting_final_approval":return {"result":"commerce_review_ready","job_id":job_id,"already_completed":True}
        if state.get("stage")=="generation_failed" and (state.get("generation_failure") or {}).get("external_result_uncertain"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Generation provider result is uncertain; automatic retry is disabled.",operation="commerce_creation",stage="provider_recovery")
        if state.get("stage")=="manual_verification_required":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Manual verification is required; automatic generation retry is disabled.",operation="commerce_creation",stage="provider_recovery")
        state["stage"]="generating_artwork";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        try:local=self.orchestrator.resume(job_id,confirm_printify_draft=False)
        except Exception as exc:
            state=self.orchestrator.load(job_id);diversity=dict(getattr(exc,"context",{}).get("candidate_diversity") or {})
            if diversity:state.setdefault("evidence",{})["candidate_diversity"]=diversity
            last_completed=_last_completed_stage(state)
            safe_message=str(getattr(exc,"user_message","") or "Product generation did not complete.")
            state["stage"]="generation_failed";state["generation_failure"]={"safe_message":str(getattr(exc,"user_message","") or "Product generation did not complete."),
                "candidate_rejection_summary":safe_message if diversity else None,"manual_verification_required":False,"external_result_uncertain":False,"terminal_local_failure":True,"last_completed_stage":last_completed};product_orchestrator._atomic_json(self.orchestrator._path(job_id),state);raise
        state=self.orchestrator.load(job_id)
        if not ((state.get("evidence") or {}).get("selection") or {}).get("selected"):
            last_completed=_last_completed_stage(state);summary="Local artwork generation did not produce an eligible selection."
            state["stage"]="generation_failed";state["generation_failure"]={"safe_message":summary,"candidate_rejection_summary":summary,
                "last_completed_stage":last_completed,"terminal_local_failure":True,"manual_verification_required":False,"external_result_uncertain":False}
            product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
            return {"result":"generation_failed","job_id":job_id,"safe_message":summary,"last_completed_stage":last_completed,
                "provider_write_status":state.get("provider_write_status","not_started"),"publication_status":state.get("publish_status","not_published"),"order_status":state.get("order_status","not_created")}
        state["stage"]="preparing_listing";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        loader=lambda required=True:profile
        requested_title=str((state.get("product_brief") or {}).get("requested_listing_title") or "")
        def listing_generator(brief,selected):
            listing=product_orchestrator.generate_listing(brief,selected)
            if requested_title:listing["title"]=requested_title
            return listing
        preparation=UnifiedCommercePreparation(self.orchestrator,workflow=self.workflow,profile_loader=loader,listing_generator=listing_generator)
        try:result=preparation.create(prompt=None,resume_job_id=job_id,authorize_draft_work=True)
        except Exception as exc:
            state=self.orchestrator.load(job_id);draft=(state.get("evidence") or {}).get("draft") or {};manual=bool(getattr(exc,"context",{}).get("manual_verification_required") and draft.get("printify_product_id"));safe_message=("Manual verification is required before this Printify draft can continue." if manual else str(getattr(exc,"user_message","") or getattr(exc,"diagnostic_message","") or "Product generation did not complete."));state["stage"]="manual_verification_required" if manual else "generation_failed";state["generation_failure"]={"safe_message":safe_message,"manual_verification_required":manual,"external_result_uncertain":manual or (any(item.get("uncertain") for item in json.loads((self.orchestrator._path(job_id).parent/"unified-preparation.json").read_text()).get("provider_actions") or []) if (self.orchestrator._path(job_id).parent/"unified-preparation.json").is_file() else False)};state["manual_verification_required"]=manual;product_orchestrator._atomic_json(self.orchestrator._path(job_id),state);raise
        state=self.orchestrator.load(job_id);state["stage"]="awaiting_final_approval";state["provider_write_status"]="completed";state["revision_number"]=max(1,int(state.get("revision_number") or 0));product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return result

    def run_generation_safely(self,job_id:str)->None:
        try:self.run_generation(job_id)
        except Exception as exc:
            try:
                state=self.orchestrator.load(job_id);draft=(state.get("evidence") or {}).get("draft") or {}
                if state.get("stage") not in {"generation_failed","manual_verification_required"}:
                    last_completed=_last_completed_stage(state)
                    state["stage"]="manual_verification_required" if draft.get("printify_product_id") else "generation_failed"
                    state["generation_failure"]={"safe_message":"Manual verification is required before this Printify draft can continue." if draft.get("printify_product_id") else "Product generation did not complete.",
                        "manual_verification_required":bool(draft.get("printify_product_id")),"external_result_uncertain":bool(draft.get("printify_product_id")),"last_completed_stage":last_completed}
                    state["manual_verification_required"]=bool(draft.get("printify_product_id"));product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
                handle_error(exc,operation="commerce_creation.background",context={"job_id":job_id,"printify_product_id":draft.get("printify_product_id")})
            except Exception as persistence_exc:
                try:handle_error(persistence_exc,operation="commerce_creation.background_persistence",context={"job_id":job_id})
                except Exception:pass
            return None

    def retry_local_artwork(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id);draft=((state.get("evidence") or {}).get("draft") or {});selected=(((state.get("evidence") or {}).get("selection") or {}).get("selected"))
        if selected:return {"result":"artwork_already_eligible","job_id":job_id,"selected_candidate_id":selected.get("candidate_id"),"provider_write_status":state.get("provider_write_status","not_started")}
        if state.get("stage")!="generation_failed" or draft.get("printify_product_id") or state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Only a failed local artwork stage without a provider draft can be retried.",operation="commerce_creation.retry_local_artwork",stage="state")
        state["stage"]="generating_artwork";state["generation_failure"]=None;product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        self.orchestrator.resume(job_id,confirm_printify_draft=False);state=self.orchestrator.load(job_id);selected=(((state.get("evidence") or {}).get("selection") or {}).get("selected"))
        if not selected:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Local artwork retry produced no eligible candidate.",user_message="Local artwork retry produced no eligible candidate.",operation="commerce_creation.retry_local_artwork",stage="design_selected")
        state["stage"]="artwork_ready";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return {"result":"local_artwork_ready","job_id":job_id,"selected_candidate_id":selected.get("candidate_id"),"provider_write_status":"not_started","publication_status":"not_published","order_status":"not_created"}

    def run_generation_background(self,job_id:str)->None:
        """Compatibility alias for callers outside the ASGI route."""
        return self.run_generation_safely(job_id)

    def safe_status(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id);destination=state.get("destination") or {};stage=str(state.get("stage") or "")
        labels={"generation_queued":"Queued","generating_artwork":"Generating artwork…","preparing_listing":"Preparing listing…","uploading_artwork":"Uploading artwork…","creating_printify_draft":"Creating unpublished draft…","retrieving_mockups":"Retrieving mockups…","revision_requested":"Revision queued…","revision_generating_artwork":"Revising artwork…","revision_artwork_selected":"Preparing revised listing…","revision_provider_update_started":"Updating existing draft…","revision_provider_update_verified":"Retrieving revision mockups…","revision_mockups_ready":"Preparing revised proposal…","awaiting_final_approval":"Ready for review","generation_failed":"Generation failed","revision_failed":"Revision failed","manual_verification_required":"Manual verification required"}
        review_url=None
        failure_message=(state.get("generation_failure") or {}).get("safe_message") or (state.get("last_error") or {}).get("user_message") or (state.get("stage_output") or {}).get("user_message")
        rejection_summary=(state.get("generation_failure") or {}).get("candidate_rejection_summary") or (failure_message if (state.get("evidence") or {}).get("candidate_diversity") else None)
        draft=(state.get("evidence") or {}).get("draft") or {};uncertain=bool((state.get("generation_failure") or {}).get("external_result_uncertain"));manual_state=stage=="manual_verification_required" or bool(state.get("manual_verification_required"))
        journal_path=self.orchestrator._path(job_id).parent/"unified-preparation.json"
        if journal_path.is_file():
            try:uncertain=uncertain or any(item.get("uncertain") for item in json.loads(journal_path.read_text(encoding="utf-8")).get("provider_actions") or [])
            except (OSError,ValueError):uncertain=True
        completed=[item.get("stage") for item in state.get("transitions") or [] if item.get("result")=="completed"]
        last_completed=(state.get("generation_failure") or {}).get("last_completed_stage") or (completed[-1] if completed else None);review_alias=stage in {"awaiting_human_approval","awaiting_final_approval"} or last_completed in {"awaiting_human_approval","awaiting_final_approval"}
        review_ready=review_alias and bool(draft.get("printify_product_id")) and state.get("publish_status")=="not_published" and state.get("order_status")=="not_created" and not uncertain and not manual_state
        terminal_outcome="uncertain" if uncertain or manual_state else "review_ready" if review_ready else "recoverable" if stage.endswith("_failed") and draft.get("printify_product_id") else "failure"
        return {"job_id":job_id,"stage":stage,"progress_label":labels.get(stage,stage.replace("_"," ").title()),"revision_number":state.get("revision_number",0),
            "brand_display_name":state.get("brand_display_name"),"printify_shop_title":destination.get("printify_shop_title"),"printify_shop_id":destination.get("printify_shop_id"),"etsy_shop_slug":destination.get("etsy_shop_slug"),
            "ready_for_review":review_ready,"failed":stage.endswith("_failed") or manual_state,"failure_message_safe":failure_message,"review_url":review_url,
            "printify_draft_exists":bool(draft.get("printify_product_id")),"printify_product_id":draft.get("printify_product_id"),
            "last_completed_stage":last_completed,"provider_write_status":state.get("provider_write_status","not_started"),"candidate_rejection_summary":rejection_summary,"manual_verification_required":uncertain or manual_state,"terminal_outcome":terminal_outcome,
            "open_product_review_allowed":review_ready,"retry_allowed":stage=="generation_failed" and not uncertain and not draft.get("printify_product_id"),
            "resume_existing_draft_allowed":stage.endswith("_failed") and not uncertain and bool(draft.get("printify_product_id")) and not review_ready,
            "publication_status":state.get("publish_status"),"order_status":state.get("order_status"),"return_to_form_url":"/app?view=commerce.new","artwork_diagnostics":_artwork_diagnostics(state)}

    def open_product_review(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id)
        status=self.safe_status(job_id)
        if not status.get("open_product_review_allowed"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Job history is not eligible for review-ready restoration.",operation="commerce_creation.open_review",stage="classification")
        profile=self._profile(str(state.get("commerce_profile_id") or ""));config=profile["configuration"];destination=state.get("destination") or {};shop_id=destination.get("printify_shop_id")
        draft=(state.get("evidence") or {}).get("draft") or {};product_id=draft.get("printify_product_id")
        if shop_id!=state.get("shop_id") or shop_id!=config.get("printify_shop_id"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Job-bound Printify destination verification failed.",operation="commerce_creation.open_review",stage="destination")
        client=self.orchestrator.adapters.client_factory();remote=client.get_product(shop_id,product_id)
        marker=draft.get("draft_marker") or (state.get("evidence") or {}).get("draft_marker");marker_present=bool(marker and marker in " ".join([str(remote.get("title") or ""),*(str(x) for x in remote.get("tags") or [])]))
        canonical=(self.orchestrator.verify_draft_ownership(state,remote).get("verified") if (state.get("evidence") or {}).get("draft_ownership") else False)
        if remote.get("id")!=product_id or remote.get("shop_id") not in (None,shop_id) or not (canonical or marker_present or product_orchestrator.replacement_ownership_matches(state,remote,product_id)):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Confirmed Printify draft does not match the job binding.",operation="commerce_creation.open_review",stage="draft_verification")
        if state.get("publish_status")!="not_published" or state.get("order_status")!="not_created" or remote.get("order_status") not in (None,"not_created") or remote.get("orders"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Only an unpublished draft with no order can be opened for review.",operation="commerce_creation.open_review",stage="publication")
        root=self.orchestrator._path(job_id).parent;mockups=(state.get("evidence") or {}).get("mockups") or []
        visual_path=root/"visual-review"/"visual-review.json"
        try:visual=json.loads(visual_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):visual={}
        mockups_current=bool(mockups) and all(Path(str(item.get("local_path") or "")).is_file() for item in mockups) and visual.get("product_id")==product_id
        state.update(stage="awaiting_human_approval",generation_failure=None);product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        if not mockups_current:self.orchestrator.review_draft(job_id)
        current=root/"commerce-proposal"/"current.json"
        try:proposal=json.loads(current.read_text(encoding="utf-8"))
        except (OSError,ValueError):proposal={}
        if proposal.get("approval_eligible") is not True or proposal.get("superseded") is True:prepared=self.workflow.prepare(job_id)
        else:prepared={"proposal_sha256":proposal.get("proposal_sha256")}
        state=self.orchestrator.load(job_id);state.update(stage="awaiting_final_approval",generation_failure=None,provider_write_status="completed");product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        review=self.workflow.review(job_id)
        return {"result":"commerce_review_ready","job_id":job_id,"proposal_sha256":prepared["proposal_sha256"],"review_url":review["review_url"],"existing_product_reused":True,"printify_product_id":product_id,"publication_status":"not_published","order_status":"not_created"}

    def resume_existing_draft(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id);profile=self._profile(str(state.get("commerce_profile_id") or ""));config=profile["configuration"]
        destination=state.get("destination") or {};shop_id=destination.get("printify_shop_id");draft=(state.get("evidence") or {}).get("draft") or {};product_id=draft.get("printify_product_id")
        if shop_id!=state.get("shop_id") or shop_id!=config.get("printify_shop_id"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Job-bound Printify destination verification failed.",operation="commerce_creation.resume",stage="destination")
        journal_path=self.orchestrator._path(job_id).parent/"unified-preparation.json";journal=json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.is_file() else {"job_id":job_id,"profile_id":state.get("commerce_profile_id"),"provider_actions":[]}
        if journal.get("job_id")!=job_id or journal.get("profile_id") not in (None,state.get("commerce_profile_id")):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Provider-write journal does not belong to this job.",operation="commerce_creation.resume",stage="journal")
        if any(item.get("uncertain") for item in journal.get("provider_actions") or []):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Manual verification required before resuming an uncertain provider write.",operation="commerce_creation.resume",stage="provider_recovery")
        if not product_id:raise StateConflictError("STATE_CONFLICT",diagnostic_message="No confirmed Printify draft is recorded for this job.",operation="commerce_creation.resume",stage="draft")
        if state.get("stage")=="awaiting_final_approval":return {"result":"commerce_review_ready","job_id":job_id,"already_completed":True,"review_url":self.workflow.review(job_id)["review_url"]}
        client=self.orchestrator.adapters.client_factory();remote=client.get_product(shop_id,product_id);marker=draft.get("draft_marker") or (state.get("evidence") or {}).get("draft_marker")
        marker_present=bool(marker and marker in " ".join([str(remote.get("title") or ""),*(str(x) for x in remote.get("tags") or [])]))
        if remote.get("id")!=product_id or remote.get("shop_id") not in (None,shop_id) or not (marker_present or product_orchestrator.replacement_ownership_matches(state,remote,product_id)):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Confirmed Printify draft does not match the job binding.",operation="commerce_creation.resume",stage="draft_verification")
        state["generation_failure"]=None;state["stage"]="resuming_existing_draft";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        resumed=self.orchestrator.resume(job_id,confirm_printify_draft=True)
        if resumed.get("stage")=="failed":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Existing draft recovery did not complete safely.",operation="commerce_creation.resume",stage="orchestrator")
        self.orchestrator.review_draft(job_id);prepared=self.workflow.prepare(job_id);review=self.workflow.review(job_id);state=self.orchestrator.load(job_id)
        state.update(stage="awaiting_final_approval",provider_write_status="completed",revision_number=max(1,int(state.get("revision_number") or 0)));product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return {"result":"commerce_review_ready","job_id":job_id,"proposal_sha256":prepared["proposal_sha256"],"review_url":review["review_url"],"existing_product_reused":True,"printify_product_id":product_id,"publication_status":"not_published","order_status":"not_created"}


def run_commerce_generation_safely(job_id:str,service:CommerceCreationService|None=None)->None:
    """Final ASGI background boundary: expected workflow failures never escape."""
    worker=service or CommerceCreationService()
    try:worker.run_generation_safely(job_id)
    except Exception as exc:
        try:handle_error(exc,operation="commerce_creation.background_boundary",context={"job_id":job_id})
        except Exception:pass
    return None
