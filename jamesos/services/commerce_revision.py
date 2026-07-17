from __future__ import annotations

import base64
from datetime import datetime
import json
from pathlib import Path
from typing import Any,Callable

from jamesos.core.errors import StateConflictError,ValidationError
from jamesos.core.profiles.selection import load_commerce_profile,load_commerce_profile_by_id
from jamesos.services import product_orchestrator
from jamesos.services.commerce_workflow import CommerceWorkflow,_atomic_json


def _now()->str:return datetime.now().astimezone().isoformat()


class CommerceRevisionService:
    """Resume one durable, non-public revision without creating or publishing a product."""
    def __init__(self,workflow:CommerceWorkflow|None=None,*,profile_loader:Callable[...,dict[str,Any]]|None=None):
        self.workflow=workflow or CommerceWorkflow();self.orchestrator=self.workflow.orchestrator;self.profile_loader=profile_loader

    def resume(self,job_id:str)->dict[str,Any]:
        state=self.orchestrator.load(job_id);root=self.orchestrator._path(job_id).parent;proposal_root=root/"commerce-proposal"
        revision_path=proposal_root/"revision-request.json";journal_path=root/"revision-execution.json"
        if not revision_path.is_file():raise StateConflictError("STATE_CONFLICT",diagnostic_message="No durable revision request exists.",operation="commerce_revision",stage="revision_requested")
        revision=json.loads(revision_path.read_text(encoding="utf-8"));note=str(revision.get("note") or "")
        if not note.strip() or revision.get("force_new_composition") is not True:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Revision evidence must request a completely new composition.",operation="commerce_revision",stage="revision_requested")
        journal=json.loads(journal_path.read_text(encoding="utf-8")) if journal_path.is_file() else {"schema_version":"1.0","job_id":job_id,
            "revision_proposal_sha256":revision.get("proposal_sha256"),"status":"revision_requested","steps":{},"created_at":_now()}
        if journal.get("status")=="completed":
            review=self.workflow.review(job_id);return {**journal.get("result",{}),"already_completed":True,"review_url":review["review_url"]}
        if any(step.get("outcome")=="uncertain" for step in journal.get("steps",{}).values()):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="A revision provider result is uncertain; automatic retry is disabled.",operation="commerce_revision",stage="provider_reconciliation",
                context={"failing_validation":"uncertain_provider_result","safe_next_action":"run read-only revision reconciliation"})
        if state.get("stage") not in {"revision_requested","revision_generating_artwork","revision_artwork_selected","revision_provider_update_started","revision_provider_update_verified","revision_mockups_ready"}:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Job is not in a resumable revision stage.",operation="commerce_revision",stage="state")
        if state.get("publish_status")!="not_published" or state.get("order_status")!="not_created" or (proposal_root/"publication-execution.json").exists():
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Revision requires an unpublished job with no publication or order evidence.",operation="commerce_revision",stage="publication")
        profile=(self.profile_loader(required=True) if self.profile_loader else load_commerce_profile_by_id(str(state["commerce_profile_id"]),required=True) if state.get("commerce_profile_id") else load_commerce_profile(required=True));config=profile.get("configuration") or {}
        if profile.get("profile_id") not in {state.get("profile_id"),state.get("selected_profile_id")} or config.get("printify_shop_id")!=state.get("shop_id"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Selected commerce profile no longer matches the job shop binding.",operation="commerce_revision",stage="profile")
        authorization_path=root/"unified-preparation.json"
        authorization=json.loads(authorization_path.read_text()) if authorization_path.is_file() else {}
        if not any(item.get("status")=="completed" and not item.get("uncertain") for item in authorization.get("provider_actions") or []):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The prior bounded non-public draft authorization is absent or stale.",operation="commerce_revision",stage="authorization",
                suggested_action=f"Resume {job_id} only after renewing bounded non-public draft authorization.")
        evidence=state.setdefault("evidence",{});draft=evidence.get("draft") or {};product_id=draft.get("printify_product_id")
        if not product_id or product_id==product_orchestrator.PROTECTED_PRODUCT_ID:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Revision target is missing or protected.",operation="commerce_revision",stage="ownership")

        steps=journal.setdefault("steps",{})
        if steps.get("generate_artwork",{}).get("outcome")!="completed":
            state["stage"]="revision_generating_artwork";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
            old_brief=state.get("brief") or {};brief=product_orchestrator.normalize_prompt(note,price=old_brief.get("price_cents"),garment_colors=old_brief.get("garment_colors"),sizes=old_brief.get("sizes"))
            brief["force_new_composition"]=True
            generation=self.orchestrator.adapters.independent_evidence(state,root,brief)
            candidates=self.orchestrator.adapters.independent_candidates(generation,root/"revision-candidates",brief)
            prior=[{**item,"job_id":job_id} for item in evidence.get("superseded_candidates") or evidence.get("candidates") or []]
            diversity=product_orchestrator.validate_candidate_set(candidates,brief,prior);selection=product_orchestrator.select_candidate(candidates,brief);selected=selection["selected"]
            listing=product_orchestrator.generate_listing(brief,selected)
            forbidden=("rainbow heart","mental health","safe space","kindness message")
            public_text=json.dumps({"title":listing["title"],"description":listing["description"],"tags":listing["tags"]}).casefold()
            if len(listing["tags"])!=13 or any(term in public_text for term in forbidden):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Fresh revision listing contains inherited or incomplete metadata.",operation="commerce_revision",stage="listing")
            evidence.setdefault("superseded_candidates",[]).extend({**item,"job_id":job_id} for item in evidence.get("candidates") or [])
            evidence.update(candidates=candidates,selection=selection,candidate_diversity=diversity,listing=listing)
            state["brief"]=brief;state["revision_prompt"]=note;state["stage"]="revision_artwork_selected"
            steps["generate_artwork"]={"outcome":"completed","completed_at":_now(),"candidate_count":len(candidates),"selected_candidate_id":selected["candidate_id"],
                "selected_sha256":selected["png_sha256"],"novelty_status":selected["novelty_evidence"]["status"]}
            _atomic_json(journal_path,journal);product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        else:
            selected=(evidence.get("selection") or {}).get("selected") or {};listing=evidence.get("listing") or {}

        client=self.orchestrator.adapters.client_factory();shop_id=state["shop_id"]
        remote=client.get_product(shop_id,product_id);publication=product_orchestrator.assess_draft_publication_state(state,remote)
        if remote.get("id")!=product_id or remote.get("shop_id")!=shop_id or not publication["safe_to_reconcile"] or remote.get("orders") or remote.get("order_status") not in (None,"not_created"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Existing remote draft failed revision ownership or unpublished-state checks.",operation="commerce_revision",stage="provider_preflight")
        variants=remote.get("variants") or [];desired=set(draft.get("variant_ids") or (evidence.get("variant_selection") or {}).get("selected_variant_ids") or [])
        if len(variants)!=318 or len(desired)!=18 or any(type(item.get("id")) is not int or type(item.get("price")) is not int for item in variants):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Existing draft variants do not match the required 318-total/18-enabled shape.",operation="commerce_revision",stage="variants",
                context={"safe_variant_count":len(variants),"safe_enabled_target_count":len(desired)})

        if steps.get("upload",{}).get("outcome")!="completed":
            steps["upload"]={"outcome":"started","started_at":_now(),"selected_sha256":selected["png_sha256"]};journal["status"]="revision_provider_update_started";_atomic_json(journal_path,journal)
            try:uploaded=client.upload_image_contents(f"jamesos-{job_id}-revision-{selected['png_sha256'][:12]}.png",base64.b64encode(Path(selected["png_path"]).read_bytes()).decode())
            except Exception:
                steps["upload"].update(outcome="uncertain",finished_at=_now());journal["status"]="revision_uncertain";_atomic_json(journal_path,journal);raise
            upload_id=uploaded.get("id")
            if not upload_id:steps["upload"].update(outcome="uncertain",finished_at=_now());journal["status"]="revision_uncertain";_atomic_json(journal_path,journal);raise StateConflictError("STATE_CONFLICT",diagnostic_message="Revision upload returned no durable ID; do not retry automatically.",operation="commerce_revision",stage="upload")
            steps["upload"].update(outcome="completed",completed_at=_now(),upload_id=upload_id);_atomic_json(journal_path,journal)
        else:upload_id=steps["upload"]["upload_id"]

        if steps.get("update",{}).get("outcome")!="completed":
            marker=evidence.get("draft_marker") or draft.get("draft_marker");tags=[*listing["tags"],marker] if marker else listing["tags"]
            print_areas=[]
            for area in remote.get("print_areas") or []:
                placeholders=[]
                for placeholder in area.get("placeholders") or []:
                    if placeholder.get("position")=="front":images=[{"id":upload_id,"x":.5,"y":.46,"scale":.85,"angle":0}]
                    else:images=[{key:image[key] for key in ("id","x","y","scale","angle") if key in image} for image in placeholder.get("images") or []]
                    if images:placeholders.append({"position":placeholder.get("position"),"images":images})
                if placeholders:print_areas.append({"variant_ids":[item["id"] for item in variants],"placeholders":placeholders})
            payload={"title":listing["title"],"description":listing["description"],"tags":tags,
                "variants":[{"id":item["id"],"price":item["price"],"is_enabled":item["id"] in desired} for item in variants],"print_areas":print_areas}
            steps["update"]={"outcome":"started","started_at":_now(),"product_id":product_id,"variant_count":len(variants)};_atomic_json(journal_path,journal)
            try:client.update_product(shop_id,product_id,payload)
            except Exception:
                steps["update"].update(outcome="uncertain",finished_at=_now());journal["status"]="revision_uncertain";_atomic_json(journal_path,journal);raise
            steps["update"].update(outcome="completed",completed_at=_now());_atomic_json(journal_path,journal)

        verified=client.get_product(shop_id,product_id);enabled={item.get("id") for item in verified.get("variants") or [] if item.get("is_enabled") is True}
        front=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")=="front" for image in placeholder.get("images") or []]
        verified_publication=product_orchestrator.assess_draft_publication_state(state,verified)
        if verified.get("id")!=product_id or len(verified.get("variants") or [])!=318 or enabled!=desired or not any(item.get("id")==upload_id for item in front) or not verified_publication["safe_to_reconcile"]:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Existing draft failed post-revision verification; do not retry writes.",operation="commerce_revision",stage="provider_verification")
        evidence["upload"]={"printify_image_id":upload_id,"selected_design_sha256":selected["png_sha256"]};evidence["listing"]=listing
        evidence["draft"]["variant_ids"]=sorted(desired);state["stage"]="revision_provider_update_verified";steps["verification"]={"outcome":"completed","completed_at":_now(),"variant_count":318,"enabled_count":18}
        _atomic_json(journal_path,journal);product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)

        review=self.orchestrator.review_draft(job_id);state=self.orchestrator.load(job_id);state["stage"]="revision_mockups_ready"
        state.setdefault("evidence",{})["revision_completed"]={"old_proposal_sha256":revision.get("proposal_sha256"),"completed_at":_now()};product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        prepared=self.workflow.prepare(job_id);session=self.workflow.review(job_id)
        result={"result":"commerce_revision_completed","job_id":job_id,"old_proposal_sha256":revision.get("proposal_sha256"),"proposal_sha256":prepared["proposal_sha256"],
            "review_url":session["review_url"],"selected_candidate_id":selected["candidate_id"],"selected_novelty_status":selected["novelty_evidence"]["status"],
            "title":listing["title"],"tag_count":len(listing["tags"]),"existing_product_reused":True,"new_product_created":False,"upload_count":1,
            "update_count":1,"publication_performed":False,"etsy_contacted":False,"order_created":False}
        journal.update(status="completed",completed_at=_now(),result=result);steps["mockups"]={"outcome":"completed","completed_at":_now()};steps["proposal"]={"outcome":"completed","completed_at":_now(),"proposal_sha256":prepared["proposal_sha256"]};_atomic_json(journal_path,journal)
        return result
