from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from jamesos.core.errors import StateConflictError, ValidationError
from jamesos.core.profiles.selection import load_commerce_profile
from jamesos.services import product_orchestrator
from jamesos.services.commerce_workflow import CommerceWorkflow, _atomic_json
from jamesos.services.product_orchestrator import ProductOrchestrator, finalize_listing_tags, validate_listing_metadata
from jamesos.services.commerce_artwork import provider_free_preflight
from jamesos.services.shell_secrets import ShellSecretStore
from jamesos.integrations.printify_client import PrintifyClient,token_status
import os


def _now() -> str:return datetime.now().astimezone().isoformat()


def default_listing_generator(brief: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    return product_orchestrator.generate_listing(brief,selected)


class UnifiedCommercePreparation:
    def __init__(self, orchestrator: ProductOrchestrator | None=None, *, workflow: CommerceWorkflow | None=None,
            profile_loader: Callable[...,dict[str,Any]]=load_commerce_profile,
            listing_generator: Callable[[dict[str,Any],dict[str,Any]],dict[str,Any]]=default_listing_generator):
        self.orchestrator=orchestrator or ProductOrchestrator();self.workflow=workflow or CommerceWorkflow(self.orchestrator)
        self.profile_loader=profile_loader;self.listing_generator=listing_generator

    def create(self, *, prompt: str | None, price_cents: int | None=None, colors: list[str] | None=None,
            sizes: list[str] | None=None, profile_id: str | None=None, resume_job_id: str | None=None,
            authorize_draft_work: bool=False) -> dict[str,Any]:
        profile=self.profile_loader(required=True);selected_profile=str(profile.get("profile_id") or "")
        if profile.get("profile_type")!="commerce_shop" or profile_id and profile_id!=selected_profile:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="The requested commerce profile is not the selected commerce_shop profile.",operation="commerce_preparation",stage="profile")
        config=profile.get("configuration") or {};shop_id=config.get("printify_shop_id")
        if type(shop_id) is not int or shop_id<=0:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Selected commerce profile has no private provider shop binding.",operation="commerce_preparation",stage="profile")
        if resume_job_id:
            state=self.orchestrator.load(resume_job_id);job_id=resume_job_id
            if prompt and " ".join(prompt.split())!=" ".join(str(state.get("original_prompt") or "").split()):
                raise StateConflictError("STATE_CONFLICT",diagnostic_message="Resume prompt differs from the durable job input; create a new job for changed inputs.",operation="commerce_preparation",stage="resume")
        else:
            if not isinstance(prompt,str) or not prompt.strip():raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product prompt is empty.",operation="commerce_preparation",stage="prompt")
            state=self.orchestrator.create(prompt=prompt,shop_id=shop_id,price=price_cents,garment_colors=colors,sizes=sizes,confirm_printify_draft=False)
            job_id=state["job_id"]
        root=self.orchestrator._path(job_id).parent;journal_path=root/"unified-preparation.json"
        journal=json.loads(journal_path.read_text()) if journal_path.is_file() else {"job_id":job_id,"profile_id":selected_profile,"provider_actions":[]}
        if any(item.get("uncertain") for item in journal["provider_actions"]):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="A provider result is uncertain; explicit recovery is required and automatic retry is disabled.",operation="commerce_preparation",stage="provider_recovery")
        evidence=state.get("evidence") or {};selection=evidence.get("selection") or {};selected=selection.get("selected")
        if not selected:raise StateConflictError("STATE_CONFLICT",diagnostic_message="Local artwork preparation did not produce an eligible candidate.",operation="commerce_preparation",stage="artwork")
        diversity=evidence.get("candidate_diversity") or {}
        if diversity and not any(item.get("eligible") for item in diversity.get("candidates") or []):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="artwork_revision_required: no candidate passed prompt-adherence and novelty checks.",operation="commerce_preparation",stage="artwork")
        listing=self.listing_generator(state["brief"],selected)
        raw_tags=listing.get("raw_generated_tags",listing.get("tags") or [])
        try:tag_diagnostics=finalize_listing_tags(raw_tags,profile,str(listing.get("title") or ""))
        except ValidationError as exc:
            tag_diagnostics={key:exc.context.get(key,[]) for key in ("raw_generated_tags","normalized_generated_tags","rejected_tags","duplicate_tags","profile_fallback_tags_used","final_listing_tags")}
            state.update(tag_diagnostics);state["stage_output"]={**(state.get("stage_output") or {}),"user_message":exc.user_message,"listing_tag_diagnostics":tag_diagnostics}
            product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
            raise
        listing["tags"]=tag_diagnostics["final_listing_tags"]
        listing["tag_diagnostics"]=tag_diagnostics
        state.update({key:tag_diagnostics[key] for key in ("raw_generated_tags","normalized_generated_tags","rejected_tags","duplicate_tags","profile_fallback_tags_used","final_listing_tags")})
        validate_listing_metadata(state,"commerce_preparation",listing)
        evidence["listing"]=listing;state["profile_id"]=selected_profile;state["selected_profile_id"]=selected_profile
        state["commerce_profile_binding"]={"profile_id":selected_profile,"provider":config.get("provider_type","printify"),
            "marketplace":config.get("marketplace_type") or config.get("expected_marketplace"),"shop_id":shop_id,
            "etsy_shop_id":config.get("etsy_shop_id"),"destination":config.get("expected_marketplace"),"expected_final_state":config.get("expected_final_state")}
        evidence["destination"]={"marketplace":config.get("expected_marketplace"),"expected_final_state":config.get("expected_final_state")}
        adapters=getattr(self.orchestrator,"adapters",None);credential_configured=token_status()["status"]=="configured" or bool(os.environ.get("PRINTIFY_API_KEY")) or any(item["provider"]=="printify" and item["configured"] for item in ShellSecretStore().status()) or adapters is None or adapters.client_factory is not PrintifyClient
        preflight=provider_free_preflight(state,profile,credential_configured=credential_configured);state["evidence"]["provider_preflight"]=preflight;product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        if authorize_draft_work and not preflight["passed"]:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Provider-free preflight failed: "+", ".join(preflight["failure_codes"])+".",user_message="Product Studio preflight found configuration that must be corrected before provider contact.",operation="commerce_preparation",stage="provider_preflight",context={"failure_codes":preflight["failure_codes"],"provider_contacted":False})
        if not authorize_draft_work:
            state["stage"]="draft_authorization_required";state["last_error"]=None;product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
            _atomic_json(journal_path,journal)
            return self._authorization_result(state,journal)
        if not any(item.get("status")=="completed" for item in journal["provider_actions"]):
            approval={"approved":True,"human_artistic_approval":True,"candidate_id":selected["candidate_id"],"candidate_sha256":selected["png_sha256"],
                "approved_at":_now(),"approval_scope":"bounded non-public unified preparation"}
            evidence["human_design_approval"]=approval;selection.setdefault("approval",{}).update(approval);state["last_error"]=None
            action={"journal_id":f"create-{uuid4().hex}","intended_action":"upload artwork and create or reconcile one unpublished job-owned draft, then retrieve mockups",
                "idempotency_key":f"commerce-draft:{job_id}:{selected['png_sha256']}","started_at":_now(),"status":"started","uncertain":False}
            journal["provider_actions"].append(action);state["active_provider_create_journal_id"]=action["journal_id"];_atomic_json(journal_path,journal);product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
            state=self.orchestrator.resume(job_id,confirm_printify_draft=True)
            if state.get("stage")=="failed":
                action.update(status="uncertain",uncertain=True,completed_at=_now(),response_evidence=state.get("last_error"));_atomic_json(journal_path,journal)
                raise StateConflictError("STATE_CONFLICT",diagnostic_message="Provider draft result is uncertain; it will not be retried automatically.",operation="commerce_preparation",stage="provider_write")
            action.update(status="completed",completed_at=_now(),response_evidence={"upload_recorded":bool((state.get("evidence") or {}).get("upload")),"draft_recorded":bool((state.get("evidence") or {}).get("draft"))});_atomic_json(journal_path,journal)
        state=self.orchestrator.load(job_id);state.update(stage="awaiting_human_approval",provider_write_status="completed",generation_failure=None,manual_verification_required=False)
        product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return {"result":"commerce_review_ready","job_id":job_id,"stage":"awaiting_human_approval","proposal_sha256":None,
            "review_url":f"/app?view=commerce.review&job_id={job_id}","review_path":None,"publication_status":state.get("publish_status"),"order_status":state.get("order_status"),
            "external_write_summary":{"authorized_non_public_writes":["artwork_upload","unpublished_job_owned_draft","mockup_retrieval"],"publication_performed":False,"order_created":False}}

    def _authorization_result(self,state:dict[str,Any],journal:dict[str,Any])->dict[str,Any]:
        evidence=state.get("evidence") or {};selection=evidence.get("selection") or {};listing=evidence.get("listing") or {}
        return {"result":"commerce_draft_authorization_required","job_id":state["job_id"],"stage":"draft_authorization_required",
            "candidate_summary":{"count":len(evidence.get("candidates") or []),"selected_candidate_id":(selection.get("selected") or {}).get("candidate_id")},
            "design_generation_summary":{"candidates_generated":(evidence.get("candidate_diversity") or {}).get("candidate_count",len(evidence.get("candidates") or [])),
                "candidates_rejected_for_prompt_mismatch":(evidence.get("candidate_diversity") or {}).get("rejected_for_prompt_mismatch",0),
                "candidates_rejected_for_similarity":(evidence.get("candidate_diversity") or {}).get("rejected_for_similarity",0),
                "selected_candidate_novelty_status":((selection.get("selected") or {}).get("novelty_evidence") or {}).get("status","not_assessed")},
            "listing_summary":{"title":listing.get("title"),"tag_count":len(listing.get("tags") or []),"price_cents":listing.get("price_cents")},
            "planned_provider_operations":["upload selected artwork once","create or reconcile one unpublished job-owned draft","retrieve exact mockups"],
            "authorization_required_reason":"Bounded non-public provider writes require --authorize-draft-work.",
            "next_command":f"python scripts/jamesos.py commerce create --resume-job-id {state['job_id']} --authorize-draft-work",
            "write_performed":True,"external_write_performed":False,"publication_performed":False,"order_created":False}
