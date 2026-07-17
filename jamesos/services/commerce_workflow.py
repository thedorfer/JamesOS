from __future__ import annotations

import base64
from datetime import datetime
from hashlib import sha256
import html
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any

from jamesos.core.commerce.proposal import compile_public_proposal
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
        warnings=["Final marketplace attributes require human review.","Publication may create temporary public exposure."]
        confirmations=["Artwork and mockups reviewed","Listing text and price reviewed","Marketplace destination and final state reviewed","No order will be created"]
        fields={"job_id":job_id,"profile_binding_reference":profile_reference,"artwork_sha256":artwork_sha,
            "artwork_phrase":str(brief.get("exact_text") or ""),"colors":list(brief.get("garment_colors") or listing.get("colors") or []),
            "sizes":list(brief.get("sizes") or listing.get("sizes") or []),"enabled_variant_count":len(variants),"enabled_variants":variants,
            "placement":placement,"title":metadata["title"],"description":metadata["description"],"tags":metadata["tags"],
            "price_cents":metadata["price_cents"],"currency":str(brief.get("currency") or listing.get("currency") or ""),
            "product_model":str(brief.get("blank") or listing.get("blank") or ""),"print_provider":str(brief.get("print_provider") or listing.get("print_provider") or ""),
            "expected_marketplace":str(marketplace),"expected_final_state":str(final_state),
            "mockups":[{"color":item.get("color"),"downloaded_sha256":item.get("downloaded_sha256"),"verified":item.get("verified_mockup_available") is True} for item in mockups],
            "warnings":warnings,"required_manual_confirmations":confirmations,"publication_status":state.get("publish_status"),
            "order_status":state.get("order_status"),"provider_draft_status":"unpublished_job_owned_draft"}
        proposal=compile_public_proposal(fields,generated_at=datetime.now().astimezone().isoformat())
        private={"schema_version":"1.0","proposal_sha256":proposal["proposal_sha256"],"job_id":job_id,"profile_binding":str(raw_profile),
            "provider_binding":{"shop_id":state.get("shop_id"),"product_id":draft.get("printify_product_id"),"upload_id":current_upload},"approval_eligible":True}
        self._reject_private_leaks(proposal,private)
        root=self.orchestrator._path(job_id).parent/"commerce-proposal";current=root/"current.json"
        if current.is_file():
            previous=json.loads(current.read_text(encoding="utf-8"));old_sha=previous.get("proposal_sha256")
            if old_sha==proposal["proposal_sha256"]:
                return self._result(job_id,root,proposal,False,state.get("stage"))
            archive=root/"archive"/str(old_sha);archive.mkdir(parents=True,exist_ok=True);os.chmod(archive,0o700)
            archived={**previous,"approval_eligible":False,"superseded":True,"superseded_by":proposal["proposal_sha256"]}
            _atomic_json(archive/"proposal.json",archived)
            for name in ("current-private.json","review.html","proposal-sha256.txt"):
                source=root/name
                if source.is_file():_atomic_bytes(archive/name,source.read_bytes())
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
        return {"result":"commerce_status","job_id":job_id,"stage":state.get("stage"),"proposal_exists":proposal is not None,
            "proposal_sha256":proposal.get("proposal_sha256") if proposal else None,"proposal_current":bool(proposal and proposal.get("approval_eligible") and not proposal.get("superseded")),
            "publication_status":state.get("publish_status"),"order_status":state.get("order_status"),
            "next_allowed_action":"review_proposal" if proposal else "prepare_proposal","write_performed":False}

    def review(self, job_id: str) -> dict[str, Any]:
        self._state(job_id);root=self.orchestrator._path(job_id).parent/"commerce-proposal";proposal_path=root/"current.json";review_path=root/"review.html"
        if not proposal_path.is_file() or not review_path.is_file():
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current commerce proposal review is unavailable.",operation="commerce_workflow.review",stage="proposal",retryable=False)
        proposal=json.loads(proposal_path.read_text(encoding="utf-8"))
        return {"result":"commerce_review_ready","job_id":job_id,"proposal_sha256":proposal["proposal_sha256"],"review_path":str(review_path),"write_performed":False}

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
        tags="".join(f"<li>{html.escape(tag)}</li>" for tag in proposal["tags"]);warnings="".join(f"<li>{html.escape(item)}</li>" for item in proposal["warnings"])
        confirms="".join(f"<li>{html.escape(item)}</li>" for item in proposal["required_manual_confirmations"])
        return "<!doctype html><meta charset='utf-8'><title>Commerce proposal review</title><style>body{font-family:sans-serif;max-width:1200px;margin:auto;padding:2rem}header{border:4px solid #b00;padding:1rem}main.images{display:grid;grid-template-columns:repeat(2,1fr);gap:1rem}img{max-width:100%;max-height:500px}</style>" \
            f"<header><strong>NOT PUBLISHED</strong><br><strong>NO ORDER CREATED</strong><br><strong>AWAITING FINAL APPROVAL</strong></header><h1>{html.escape(proposal['title'])}</h1>" \
            f"<main class='images'>{figures}</main><h2>Description</h2><p>{html.escape(proposal['description'])}</p><h2>Tags</h2><ul>{tags}</ul>" \
            f"<p>Price: {proposal['price_cents']} cents</p><p>Colors: {html.escape(', '.join(proposal['colors']))}</p><p>Sizes: {html.escape(', '.join(proposal['sizes']))}</p>" \
            f"<p>Variants: {proposal['enabled_variant_count']}</p><p>Placement: {html.escape(json.dumps(proposal['placement'],sort_keys=True))}</p>" \
            f"<p>Marketplace: {html.escape(proposal['expected_marketplace'])}; expected final state: {html.escape(proposal['expected_final_state'])}</p>" \
            f"<h2>Warnings</h2><ul>{warnings}</ul><h2>Required confirmations</h2><ul>{confirms}</ul><p>Proposal SHA-256: {proposal['proposal_sha256']}</p>"

    @staticmethod
    def _result(job_id: str, root: Path, proposal: dict[str, Any], wrote: bool, stage: str | None) -> dict[str, Any]:
        return {"result":"commerce_proposal_ready","job_id":job_id,"proposal_sha256":proposal["proposal_sha256"],"review_path":str(root/"review.html"),
            "proposal_path":str(root/"current.json"),"stage":stage,"write_performed":wrote,"external_write_performed":False,"printify_write_performed":False,
            "etsy_write_performed":False,"publish_performed":False,"order_created":False}
