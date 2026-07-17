from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import hmac
import html
import json
import os
from pathlib import Path
import re
import shutil
import secrets
import tempfile
from typing import Any

from jamesos.core.commerce.proposal import canonical_proposal_sha256,compile_public_proposal
from jamesos.core.errors import StateConflictError, ValidationError
from jamesos.services import product_orchestrator
from jamesos.services.product_orchestrator import ProductOrchestrator


JOB_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _atomic_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True,exist_ok=True);os.chmod(path.parent,0o700)
    fd,name=tempfile.mkstemp(prefix=f".{path.name}.",dir=path.parent)
    try:
        with os.fdopen(fd,"wb") as handle:handle.write(content);handle.flush();os.fsync(handle.fileno())
        os.chmod(name,mode);os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)


def _atomic_json(path: Path, value: Any, mode: int = 0o600) -> None:
    _atomic_bytes(path,(json.dumps(value,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode("utf-8"),mode)


def _sha_file(path: Path) -> str:
    digest=sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):digest.update(chunk)
    return digest.hexdigest()


def _data_image(path: Path) -> str:
    if not path.is_file():return ""
    mime="image/png" if path.suffix.casefold()==".png" else "image/jpeg"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def format_currency(price_cents: int, currency: str) -> str:
    """Format integer minor units deterministically (commerce currently uses 2-digit cents)."""
    if type(price_cents) is not int or price_cents < 0:raise ValueError("price_cents must be a non-negative integer")
    amount=f"{price_cents // 100:,}.{price_cents % 100:02d}"
    symbols={"USD":"$","CAD":"CA$","AUD":"A$","EUR":"€","GBP":"£"}
    code=str(currency or "").upper()
    return f"{symbols.get(code,code + ' ')}{amount}"


class CommerceWorkflow:
    def __init__(self, orchestrator: ProductOrchestrator | None = None):
        self.orchestrator=orchestrator or ProductOrchestrator()

    def _state(self, job_id: str) -> dict[str, Any]:
        if not isinstance(job_id,str) or not JOB_ID.fullmatch(job_id) or Path(job_id).name!=job_id:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Commerce job ID is missing or malformed.",operation="commerce_workflow",stage="input",retryable=False)
        path=self.orchestrator._path(job_id)
        if not path.is_file():
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Commerce job was not found.",operation="commerce_workflow",stage="input",retryable=False)
        return self.orchestrator.load(job_id)

    @staticmethod
    def _evidence_digest(state: dict[str, Any]) -> str:
        evidence=state.get("evidence") or {}
        bound={"brief":state.get("brief"),"publish_status":state.get("publish_status"),"order_status":state.get("order_status"),
            "selection":evidence.get("selection"),"upload":evidence.get("upload"),"draft":evidence.get("draft"),
            "variant_selection":evidence.get("variant_selection"),"listing":evidence.get("listing"),"destination":evidence.get("destination")}
        return sha256(json.dumps(bound,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()).hexdigest()

    def prepare(self, job_id: str) -> dict[str, Any]:
        state=self._state(job_id)
        if state.get("stage")=="failed" and state.get("last_error"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Failed commerce job requires recovery before proposal preparation.",operation="commerce_workflow.prepare",stage="job_state",retryable=False)
        plan=self.orchestrator.prepare_listing(job_id,confirmed=False)
        if plan.get("safe_to_update") is not True:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Listing preparation did not produce a safe read-only plan.",operation="commerce_workflow.prepare",stage="proposal_validation",retryable=False)
        state=self._state(job_id);evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};upload=evidence.get("upload") or {}
        selected=(evidence.get("selection") or {}).get("selected") or {};brief=state.get("brief") or {};listing=evidence.get("listing") or {}
        metadata=product_orchestrator.validate_listing_metadata(state,"commerce_workflow.prepare")
        review_path=self.orchestrator._path(job_id).parent/"visual-review"/"visual-review.json"
        try:visual=json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Fresh visual review evidence is missing.",operation="commerce_workflow.prepare",stage="visual_review",retryable=False,context={"invalid_fields":["visual_review"]}) from exc
        checks=visual.get("checks") or {};mockups=checks.get("mockups") or [];current_upload=upload.get("printify_image_id")
        invalid=[]
        if visual.get("product_id")!=draft.get("printify_product_id"):invalid.append("visual_review.product")
        if checks.get("artwork_image_id")!=current_upload or checks.get("artwork_image_id_matches") is not True:invalid.append("visual_review.current_artwork")
        if len(mockups)!=3 or any(not item.get("downloaded_sha256") or item.get("verified_mockup_available") is not True for item in mockups):invalid.append("visual_review.mockups")
        artwork_sha=upload.get("selected_design_sha256") or selected.get("png_sha256")
        artwork_path=Path(str(selected.get("png_path") or ""))
        if not artwork_sha or not artwork_path.is_file() or _sha_file(artwork_path)!=artwork_sha:invalid.append("artwork_sha256")
        destination=evidence.get("destination") or {}
        marketplace=destination.get("marketplace") or product_orchestrator._COMMERCE.get("expected_marketplace")
        final_state=destination.get("expected_final_state") or product_orchestrator._COMMERCE.get("expected_final_state")
        if not marketplace:invalid.append("expected_marketplace")
        if not final_state:invalid.append("expected_final_state")
        if invalid:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Commerce proposal evidence is incomplete: {', '.join(invalid)}.",operation="commerce_workflow.prepare",stage="proposal_validation",retryable=False,
                context={"invalid_fields":invalid,"external_write_performed":False})
        raw_profile=state.get("profile_id") or state.get("selected_profile_id") or product_orchestrator._COMMERCE.get("profile_id") or "selected-commerce-profile"
        profile_reference=f"commerce-profile:{sha256(str(raw_profile).encode()).hexdigest()[:16]}"
        variants=sorted(draft.get("variant_ids") or (evidence.get("variant_selection") or {}).get("selected_variant_ids") or [])
        placement={key:checks.get("placement",{}).get(key) for key in ("x","y","scale","angle")}
        warnings=list(evidence.get("commerce_warnings") or [])
        diversity=evidence.get("candidate_diversity") or {};selected_novelty=(selected.get("novelty_evidence") or {}).get("status","not_assessed")
        design_summary={"candidates_generated":diversity.get("candidate_count",len(evidence.get("candidates") or [])),
            "candidates_rejected_for_prompt_mismatch":diversity.get("rejected_for_prompt_mismatch",0),
            "candidates_rejected_for_similarity":diversity.get("rejected_for_similarity",0),"selected_candidate_novelty_status":selected_novelty}
        fields={"job_id":job_id,"profile_binding_reference":profile_reference,"artwork_sha256":artwork_sha,
            "artwork_phrase":str(brief.get("exact_text") or ""),"colors":list(brief.get("garment_colors") or listing.get("colors") or []),
            "sizes":list(brief.get("sizes") or listing.get("sizes") or []),"enabled_variant_count":len(variants),"enabled_variants":variants,
            "placement":placement,"title":metadata["title"],"description":metadata["description"],"tags":metadata["tags"],
            "price_cents":metadata["price_cents"],"currency":str(brief.get("currency") or listing.get("currency") or ""),
            "product_model":str(brief.get("blank") or listing.get("blank") or ""),"print_provider":str(brief.get("print_provider") or listing.get("print_provider") or ""),
            "expected_marketplace":str(marketplace),"expected_final_state":str(final_state),
            "mockups":[{"color":item.get("color"),"downloaded_sha256":item.get("downloaded_sha256"),"verified":item.get("verified_mockup_available") is True} for item in mockups],"design_generation_summary":design_summary,
            "warnings":warnings,"required_manual_confirmations":[],"publication_status":state.get("publish_status"),
            "order_status":state.get("order_status"),"provider_draft_status":"unpublished_job_owned_draft"}
        proposal=compile_public_proposal(fields,generated_at=datetime.now().astimezone().isoformat())
        profile_execution=state.get("commerce_profile_binding") or {}
        private={"schema_version":"1.0","proposal_sha256":proposal["proposal_sha256"],"job_id":job_id,"profile_binding":str(raw_profile),
            "execution_profile_binding":profile_execution,
            "provider_binding":{"shop_id":state.get("shop_id"),"product_id":draft.get("printify_product_id"),"upload_id":current_upload},"approval_eligible":True,
            "job_evidence_sha256":self._evidence_digest(state),"csrf_token":secrets.token_urlsafe(32)}
        self._reject_private_leaks(proposal,private)
        root=self.orchestrator._path(job_id).parent/"commerce-proposal";current=root/"current.json"
        if current.is_file():
            previous=json.loads(current.read_text(encoding="utf-8"));old_sha=previous.get("proposal_sha256")
            if old_sha==proposal["proposal_sha256"]:
                return self._result(job_id,root,proposal,False,state.get("stage"))
            archive=root/"archive"/str(old_sha);archive.mkdir(parents=True,exist_ok=True);os.chmod(archive,0o700)
            archived={**previous,"approval_eligible":False,"superseded":True,"superseded_by":proposal["proposal_sha256"]}
            _atomic_json(archive/"proposal.json",archived)
            for name in ("current-private.json","review.html","proposal-sha256.txt","approval.json","revision-request.json"):
                source=root/name
                if source.is_file():
                    _atomic_bytes(archive/name,source.read_bytes());source.unlink()
        root.mkdir(parents=True,exist_ok=True);os.chmod(root,0o700)
        _atomic_json(current,proposal);_atomic_json(root/"current-private.json",private,0o600)
        _atomic_bytes(root/"proposal-sha256.txt",(proposal["proposal_sha256"]+"\n").encode())
        _atomic_bytes(root/"review.html",self._html(proposal,artwork_path,mockups,review_path.parent).encode("utf-8"))
        state["stage"]="awaiting_final_approval";state.setdefault("evidence",{})["commerce_proposal"]={"proposal_sha256":proposal["proposal_sha256"],"approval_eligible":True,"superseded":False}
        product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return self._result(job_id,root,proposal,True,"awaiting_final_approval")

    def status(self, job_id: str) -> dict[str, Any]:
        state=self._state(job_id);root=self.orchestrator._path(job_id).parent/"commerce-proposal";path=root/"current.json"
        proposal=json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None
        stage=state.get("stage")
        actions={"awaiting_final_approval":"review_or_approve","proposal_approved":"ready_to_publish","revision_requested":"revise_proposal",
            "publication_pending":"publishing","publication_started":"publishing","provider_update_uncertain":"reconcile_publication","provider_update_verified":"publishing",
            "marketplace_publish_submitted":"resolving_listing","marketplace_listing_pending":"reconcile_publication","marketplace_listing_resolved":"verifying_final_state",
            "final_state_verified":"completing","completed":"completed","publication_uncertain":"reconcile_publication","publication_failed":"inspect_failure"}
        return {"result":"commerce_status","job_id":job_id,"stage":state.get("stage"),"proposal_exists":proposal is not None,
            "proposal_sha256":proposal.get("proposal_sha256") if proposal else None,"proposal_current":bool(proposal and proposal.get("approval_eligible") and not proposal.get("superseded")),
            "publication_status":state.get("publish_status"),"order_status":state.get("order_status"),
            "next_allowed_action":actions.get(stage,"review_proposal" if proposal else "prepare_proposal"),"write_performed":False}

    def review(self, job_id: str, *, lifetime_seconds: int = 600) -> dict[str, Any]:
        state=self._state(job_id);root=self.orchestrator._path(job_id).parent/"commerce-proposal";proposal_path=root/"current.json";review_path=root/"review.html"
        if not proposal_path.is_file() or not review_path.is_file():
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current commerce proposal review is unavailable.",operation="commerce_workflow.review",stage="proposal",retryable=False)
        proposal=json.loads(proposal_path.read_text(encoding="utf-8"))
        invalid=[]
        if state.get("stage")!="awaiting_final_approval":invalid.append("stage.awaiting_final_approval")
        if proposal.get("approval_eligible") is not True or proposal.get("superseded") is True:invalid.append("proposal.approval_eligible")
        if state.get("publish_status")!="not_published":invalid.append("publication.not_published")
        if state.get("order_status")!="not_created":invalid.append("order.not_created")
        if invalid:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current proposal is not eligible for browser review.",operation="commerce_workflow.review",stage="review_eligibility",retryable=False,
                context={"failing_validation":invalid,"safe_state":{"stage":state.get("stage"),"proposal_current":proposal.get("approval_eligible") is True and not proposal.get("superseded"),
                    "publication_status":state.get("publish_status"),"order_status":state.get("order_status")}},suggested_action="Run commerce status and open only the current awaiting-final-approval proposal.")
        self._current(job_id,proposal["proposal_sha256"])
        if type(lifetime_seconds) is not int or not 1 <= lifetime_seconds <= 3600:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Review session lifetime is invalid.",operation="commerce_workflow.review",stage="input",retryable=False)
        token=secrets.token_urlsafe(32);issued=datetime.now(timezone.utc);expires=issued+timedelta(seconds=lifetime_seconds)
        session={"schema_version":"1.0","job_id":job_id,"proposal_sha256":proposal["proposal_sha256"],"token_sha256":sha256(token.encode()).hexdigest(),
            "cookie_sha256":None,"issued_at":issued.isoformat(),"expires_at":expires.isoformat(),"bootstrap_used":False,"active":True}
        _atomic_json(root/"review-session.json",session)
        return {"result":"commerce_review_ready","job_id":job_id,"proposal_sha256":proposal["proposal_sha256"],
            "review_url":f"http://127.0.0.1:8787/commerce/proposals/{job_id}/review?session={token}","review_path":str(review_path),
            "session_expires_at":expires.isoformat(),"write_performed":True,"external_write_performed":False}

    def browser_session(self, job_id: str) -> tuple[dict[str,Any],Path]:
        state=self._state(job_id);root=self.orchestrator._path(job_id).parent/"commerce-proposal"
        try:session=json.loads((root/"review-session.json").read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Browser review session is unavailable.",operation="commerce_workflow.review",stage="browser_session",retryable=False) from exc
        proposal_sha=str(session.get("proposal_sha256") or "");self._current(job_id,proposal_sha)
        try:expires=datetime.fromisoformat(str(session.get("expires_at")))
        except ValueError as exc:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Browser review session is invalid.",operation="commerce_workflow.review",stage="browser_session",retryable=False) from exc
        if session.get("job_id")!=job_id or session.get("active") is not True or expires<=datetime.now(timezone.utc):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Browser review session is expired or inactive.",operation="commerce_workflow.review",stage="browser_session",retryable=False)
        return session,root

    def establish_browser_session(self, job_id: str, token: str) -> tuple[str,int]:
        session,root=self.browser_session(job_id)
        digest=sha256(str(token).encode()).hexdigest()
        if session.get("bootstrap_used") is True or not hmac.compare_digest(digest,str(session.get("token_sha256") or "")):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Browser review token is invalid or already used.",operation="commerce_workflow.review",stage="browser_session",retryable=False)
        cookie=secrets.token_urlsafe(32);session["bootstrap_used"]=True;session["token_sha256"]=None;session["cookie_sha256"]=sha256(cookie.encode()).hexdigest()
        _atomic_json(root/"review-session.json",session)
        remaining=max(1,int((datetime.fromisoformat(session["expires_at"])-datetime.now(timezone.utc)).total_seconds()))
        return cookie,remaining

    def authenticate_browser_session(self, job_id: str, cookie: str) -> dict[str,Any]:
        session,_=self.browser_session(job_id)
        if not cookie or not session.get("cookie_sha256") or not hmac.compare_digest(sha256(cookie.encode()).hexdigest(),session["cookie_sha256"]):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Browser review cookie is invalid.",operation="commerce_workflow.review",stage="browser_session",retryable=False)
        return session

    def revoke_browser_session(self, job_id: str) -> None:
        self._state(job_id)
        root=self.orchestrator._path(job_id).parent/"commerce-proposal"
        try:session=json.loads((root/"review-session.json").read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Browser review session is unavailable.",operation="commerce_workflow.review",stage="browser_session",retryable=False) from exc
        session["active"]=False;session["cookie_sha256"]=None
        _atomic_json(root/"review-session.json",session)

    def _current(self, job_id: str, proposal_sha256: str) -> tuple[dict[str,Any],dict[str,Any],dict[str,Any],Path]:
        state=self._state(job_id);root=self.orchestrator._path(job_id).parent/"commerce-proposal"
        try:
            proposal=json.loads((root/"current.json").read_text());private=json.loads((root/"current-private.json").read_text())
        except (OSError,ValueError) as exc:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current commerce proposal is unavailable.",operation="commerce_workflow.mutate",stage="proposal",retryable=False) from exc
        current=proposal.get("proposal_sha256")
        if not isinstance(proposal_sha256,str) or proposal_sha256!=current or canonical_proposal_sha256(proposal)!=current:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Proposal SHA does not match the exact current proposal.",operation="commerce_workflow.mutate",stage="proposal",retryable=False,
                context={"failing_validation":"current_proposal_sha256","safe_state":{"submitted_matches_recorded":proposal_sha256==current,
                    "canonical_matches_recorded":canonical_proposal_sha256(proposal)==current,"proposal_schema_version":proposal.get("schema_version"),
                    "generation_summary":"recorded" if "design_generation_summary" in proposal else "not_recorded"}},suggested_action="Regenerate only if the current proposal content changed; optional legacy display evidence is not required.")
        if proposal.get("superseded") or private.get("superseded"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Proposal has been superseded.",operation="commerce_workflow.mutate",stage="proposal",retryable=False,
                context={"failing_validation":"proposal_not_superseded","safe_state":{"proposal_superseded":bool(proposal.get("superseded") or private.get("superseded"))}},suggested_action="Open the current proposal from commerce status.")
        if private.get("job_evidence_sha256")!=self._evidence_digest(state) or (state.get("evidence") or {}).get("commerce_proposal",{}).get("proposal_sha256")!=current:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current job evidence no longer matches this proposal.",operation="commerce_workflow.mutate",stage="evidence",retryable=False)
        return state,proposal,private,root

    def approve(self, job_id: str, proposal_sha256: str, *, confirmed: bool = False) -> dict[str,Any]:
        state,proposal,private,root=self._current(job_id,proposal_sha256)
        if proposal.get("approval_eligible") is not True or private.get("approval_eligible") is not True:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Proposal is not eligible for approval.",operation="commerce_workflow.approve",stage="proposal",retryable=False)
        result={"result":"commerce_approval_plan" if not confirmed else "commerce_proposal_approved","dry_run":not confirmed,"write_performed":confirmed,
            "proposal_sha256":proposal_sha256,"external_write_performed":False,"printify_write_performed":False,"etsy_write_performed":False,"publish_performed":False,"order_created":False}
        if not confirmed:return result
        _atomic_json(root/"approval.json",{"schema_version":"1.0","approved":True,"proposal_sha256":proposal_sha256,"approved_at":datetime.now().astimezone().isoformat()})
        state["stage"]="proposal_approved";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return result

    def request_changes(self, job_id: str, proposal_sha256: str, *, note: str = "", confirmed: bool = False) -> dict[str,Any]:
        if not isinstance(note,str):
            raise ValidationError("REVISION_NOTE_INVALID",diagnostic_message="Revision note must be text.",operation="commerce_workflow.request_changes",stage="input",retryable=False,
                context={"failing_validation":"revision_note_type","anything_changed":False},suggested_action="Enter a plain-text revision request and submit again.")
        note=note.replace("\r\n","\n").replace("\r","\n").strip()
        if not note or len(note)>1000 or any(ord(char)<32 and char not in "\n\t" for char in note):
            validation="revision_note_required" if not note else "revision_note_length" if len(note)>1000 else "revision_note_control_characters"
            raise ValidationError("REVISION_NOTE_INVALID",diagnostic_message="Revision note must be nonblank plain text of at most 1000 characters.",operation="commerce_workflow.request_changes",stage="input",retryable=False,
                context={"failing_validation":validation,"anything_changed":False,"safe_observed_length":len(note)},suggested_action="Enter a nonblank revision request of at most 1000 characters and submit again.")
        state,proposal,private,root=self._current(job_id,proposal_sha256)
        if state.get("stage")!="awaiting_final_approval":
            raise StateConflictError("REVISION_STAGE_INVALID",diagnostic_message="Request changes requires the current job to be awaiting final approval.",operation="commerce_workflow.request_changes",stage="state",retryable=False,
                context={"failing_validation":"awaiting_final_approval","safe_observed_stage":state.get("stage"),"anything_changed":False},suggested_action="Open the current review page and verify the job is awaiting final approval.")
        result={"result":"commerce_revision_request_plan" if not confirmed else "commerce_changes_requested","dry_run":not confirmed,"write_performed":confirmed,
            "proposal_sha256":proposal_sha256,"external_write_performed":False,"printify_write_performed":False,"etsy_write_performed":False,"order_created":False}
        if not confirmed:return result
        force_new=bool(re.search(r"\b(?:new design|new composition|different layout|fresh design)\b",note,re.I))
        _atomic_json(root/"revision-request.json",{"schema_version":"1.0","proposal_sha256":proposal_sha256,"requested_at":datetime.now().astimezone().isoformat(),"note":note,"force_new_composition":force_new})
        proposal["approval_eligible"]=False;private["approval_eligible"]=False
        _atomic_json(root/"current.json",proposal);_atomic_json(root/"current-private.json",private)
        archive=root/"archive"/proposal_sha256;archive.mkdir(parents=True,exist_ok=True);os.chmod(archive,0o700)
        _atomic_json(archive/"proposal.json",{**proposal,"superseded":True,"approval_eligible":False})
        approval=root/"approval.json"
        if approval.is_file():_atomic_bytes(archive/"approval.json",approval.read_bytes());approval.unlink()
        evidence=state.setdefault("evidence",{});evidence.setdefault("superseded_candidates",[]).extend({**item,"job_id":job_id} for item in evidence.get("candidates") or [])
        evidence["revision_constraints"]={"note":note,"force_new_composition":force_new};state["revision_number"]=int(state.get("revision_number") or 0)+1;state["stage"]="revision_requested";product_orchestrator._atomic_json(self.orchestrator._path(job_id),state)
        return result

    @staticmethod
    def _reject_private_leaks(public: dict[str, Any], private: dict[str, Any]) -> None:
        visible=json.dumps({key:public.get(key) for key in ("title","description","tags","warnings","required_manual_confirmations","artwork_phrase","product_model","print_provider")},ensure_ascii=False).casefold()
        identifiers=[private.get("profile_binding"),*(private.get("provider_binding") or {}).values()]
        leaked=[str(value) for value in identifiers if value not in (None,"") and str(value).casefold() in visible]
        if leaked or re.search(r"(?:secret:|/home/|file://|[a-z]:\\)",visible,re.I):
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Private identifiers appeared in public proposal fields.",operation="commerce_workflow.prepare",stage="proposal_privacy",retryable=False,
                context={"invalid_fields":["public_proposal.private_data"],"external_write_performed":False})

    @staticmethod
    def _html(proposal: dict[str, Any], artwork: Path, mockups: list[dict[str, Any]], review_root: Path) -> str:
        names={"Black":"black-front.png","Dark Grey Heather":"dark-grey-heather-front.png","White":"white-front.png"}
        images=[("Artwork",artwork),*((item.get("color") or "Mockup",review_root/names.get(item.get("color"),"missing")) for item in mockups)]
        figures="".join(f'<figure><img src="{_data_image(path)}" alt="{html.escape(str(label))}"><figcaption>{html.escape(str(label))}</figcaption></figure>' for label,path in images)
        tags="".join(f"<li>{html.escape(str(tag))}</li>" for tag in proposal["tags"])
        warnings="".join(f"<li>{html.escape(str(item))}</li>" for item in proposal.get("warnings") or [])
        warning_section=f"<section><h2>Warnings</h2><ul>{warnings}</ul></section>" if warnings else ""
        summary=proposal.get("design_generation_summary") or {}
        generation=f"<section><h2>Design generation</h2><p>Candidates generated: {int(summary.get('candidates_generated') or 0)}<br>Candidates rejected for prompt mismatch: {int(summary.get('candidates_rejected_for_prompt_mismatch') or 0)}<br>Candidates rejected for similarity: {int(summary.get('candidates_rejected_for_similarity') or 0)}<br>Selected candidate novelty: {html.escape(str(summary.get('selected_candidate_novelty_status') or 'not assessed'))}</p></section>"
        price=html.escape(format_currency(proposal["price_cents"],proposal["currency"]))
        return "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>Commerce proposal review</title><style>body{font:16px system-ui,sans-serif;max-width:1180px;margin:auto;padding:2rem;color:#18221c;background:#f7f8f6}header{background:#fff4d6;border-left:6px solid #d79b00;padding:1rem 1.4rem;border-radius:8px}.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:1rem}figure,section{background:white;padding:1rem;border-radius:10px;box-shadow:0 1px 5px #0002}img{width:100%;height:360px;object-fit:contain}p.description{max-width:72ch;white-space:pre-wrap}ul.tags{display:flex;flex-wrap:wrap;gap:.5rem;padding:0}ul.tags li{list-style:none;background:#e8eee9;padding:.3rem .65rem;border-radius:999px}.details{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.5rem 2rem}.actions{margin-top:2rem}.approve{background:#18743b;color:white;border:0;padding:.8rem 1.2rem;border-radius:6px;font-weight:700}button{cursor:pointer}textarea{display:block;width:min(100%,600px);min-height:90px;margin:.7rem 0}</style>" \
            f"<header><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong><br><strong>AWAITING FINAL APPROVAL</strong></header><h1>{html.escape(proposal['title'])}</h1>" \
            f"<main class='images'>{figures}</main><section><h2>Description</h2><p class='description'>{html.escape(proposal['description'])}</p><h2>Tags</h2><ul class='tags'>{tags}</ul></section>" \
            f"<section class='details'><p><strong>Price</strong><br>{price}</p><p><strong>Colors</strong><br>{html.escape(', '.join(proposal['colors']))}</p><p><strong>Sizes</strong><br>{html.escape(', '.join(proposal['sizes']))}</p>" \
            f"<p><strong>Variants</strong><br>{proposal['enabled_variant_count']}</p><p><strong>Placement</strong><br>{html.escape(json.dumps(proposal['placement'],sort_keys=True))}</p>" \
            f"<p><strong>Marketplace</strong><br>{html.escape(proposal['expected_marketplace'])}</p><p><strong>Expected final state</strong><br>{html.escape(proposal['expected_final_state'])}</p>" \
            f"<p><strong>Publication</strong><br>{html.escape(proposal['publication_status'])}</p><p><strong>Order</strong><br>{html.escape(proposal['order_status'])}</p></section>{generation}{warning_section}" \
            f"<p>Proposal SHA-256: <code>{html.escape(proposal['proposal_sha256'])}</code></p>" \
            "<section class='actions' id='browser-actions'><p>Open through the JamesOS localhost review URL to approve or request changes.</p></section>"

    @staticmethod
    def _result(job_id: str, root: Path, proposal: dict[str, Any], wrote: bool, stage: str | None) -> dict[str, Any]:
        return {"result":"commerce_proposal_ready","job_id":job_id,"proposal_sha256":proposal["proposal_sha256"],"review_path":str(root/"review.html"),
            "proposal_path":str(root/"current.json"),"stage":stage,"write_performed":wrote,"external_write_performed":False,"printify_write_performed":False,
            "etsy_write_performed":False,"publish_performed":False,"order_created":False}
