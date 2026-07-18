from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any,Callable
from uuid import uuid4

from jamesos.core.errors import StateConflictError,ValidationError
from jamesos.core.profiles.selection import load_commerce_profile_by_id
from jamesos.services import product_orchestrator
from jamesos.services.commerce_preparation import UnifiedCommercePreparation
from jamesos.services.commerce_workflow import CommerceWorkflow,_atomic_json


def _now()->str:return datetime.now().astimezone().isoformat()
def _clean(value:Any,limit:int,field:str,*,required:bool=False)->str:
    if value is None:value=""
    if not isinstance(value,str):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} must be text.",operation="commerce_creation",stage="input")
    value=value.replace("\r\n","\n").replace("\r","\n").strip()
    if required and not value:raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} is required.",operation="commerce_creation",stage="input")
    if len(value)>limit or any(ord(char)<32 and char not in "\n\t" for char in value):raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"{field} is invalid or too long.",operation="commerce_creation",stage="input")
    return value


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
            "creation_request_sha256":fingerprint,"created_at":now,"updated_at":now}
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
        state["stage"]="generating_artwork";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        local=self.orchestrator.resume(job_id,confirm_printify_draft=False);state=self.orchestrator.load(job_id)
        if not ((state.get("evidence") or {}).get("selection") or {}).get("selected"):
            state["stage"]="generation_failed";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state);raise StateConflictError("STATE_CONFLICT",diagnostic_message="Local artwork generation did not produce an eligible selection.",operation="commerce_creation",stage="generating_artwork")
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
            state=self.orchestrator.load(job_id);state["stage"]="generation_failed";safe_message=str(getattr(exc,"user_message","") or getattr(exc,"diagnostic_message","") or "Product generation did not complete.");state["generation_failure"]={"safe_message":safe_message,"external_result_uncertain":any(item.get("uncertain") for item in json.loads((self.orchestrator._path(job_id).parent/"unified-preparation.json").read_text()).get("provider_actions") or []) if (self.orchestrator._path(job_id).parent/"unified-preparation.json").is_file() else False};product_orchestrator._atomic_json(self.orchestrator._path(job_id),state);raise
        state=self.orchestrator.load(job_id);state["stage"]="awaiting_final_approval";state["provider_write_status"]="completed";state["revision_number"]=max(1,int(state.get("revision_number") or 0));product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return result

    def safe_status(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id);destination=state.get("destination") or {};stage=str(state.get("stage") or "")
        labels={"generation_queued":"Queued","generating_artwork":"Generating artwork…","preparing_listing":"Preparing listing…","uploading_artwork":"Uploading artwork…","creating_printify_draft":"Creating unpublished draft…","retrieving_mockups":"Retrieving mockups…","revision_requested":"Revision queued…","revision_generating_artwork":"Revising artwork…","revision_artwork_selected":"Preparing revised listing…","revision_provider_update_started":"Updating existing draft…","revision_provider_update_verified":"Retrieving revision mockups…","revision_mockups_ready":"Preparing revised proposal…","awaiting_final_approval":"Ready for review","generation_failed":"Generation failed","revision_failed":"Revision failed"}
        review_url=None
        if stage=="awaiting_final_approval":review_url=self.workflow.review(job_id)["review_url"]
        failure_message=(state.get("generation_failure") or {}).get("safe_message") or (state.get("last_error") or {}).get("user_message") or (state.get("stage_output") or {}).get("user_message")
        draft=(state.get("evidence") or {}).get("draft") or {};uncertain=bool((state.get("generation_failure") or {}).get("external_result_uncertain"))
        return {"job_id":job_id,"stage":stage,"progress_label":labels.get(stage,stage.replace("_"," ").title()),"revision_number":state.get("revision_number",0),
            "brand_display_name":state.get("brand_display_name"),"printify_shop_title":destination.get("printify_shop_title"),"printify_shop_id":destination.get("printify_shop_id"),"etsy_shop_slug":destination.get("etsy_shop_slug"),
            "ready_for_review":stage=="awaiting_final_approval","failed":stage.endswith("_failed"),"failure_message_safe":failure_message,"review_url":review_url,
            "printify_draft_exists":bool(draft.get("printify_product_id")),"retry_allowed":stage.endswith("_failed") and not uncertain,
            "publication_status":state.get("publish_status"),"order_status":state.get("order_status")}
