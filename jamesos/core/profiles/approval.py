from __future__ import annotations
import hashlib,json
from typing import Any

PROPOSAL_FIELDS=("artwork","product_configuration","mockups","listing_metadata","destination","expected_final_state")

def complete_proposal_hash(proposal:dict[str,Any])->str:
    missing=[field for field in PROPOSAL_FIELDS if field not in proposal]
    if missing:raise ValueError(f"complete listing proposal missing: {', '.join(missing)}")
    document={field:proposal[field] for field in PROPOSAL_FIELDS}
    encoded=json.dumps(document,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()

def final_approval(proposal:dict[str,Any],*,approved:bool)->dict[str,Any]:
    return {"approved":bool(approved),"approval_mode":"single_final","proposal_sha256":complete_proposal_hash(proposal)}

def final_approval_matches(proposal:dict[str,Any],approval:dict[str,Any]|None)->bool:
    return bool(approval and approval.get("approved") is True and approval.get("approval_mode")=="single_final"
        and approval.get("proposal_sha256")==complete_proposal_hash(proposal))

def publication_workflow(configuration:dict[str,Any])->dict[str,str]:
    mode=configuration.get("approval_mode","staged");final_state=configuration.get("etsy_final_state","inactive")
    if mode not in {"single_final","staged"}:raise ValueError("unsupported approval mode")
    if final_state not in {"active","inactive"}:raise ValueError("unsupported Etsy final state")
    return {"approval_mode":mode,"etsy_final_state":final_state,
        "capability":"commerce.workflow.publish_active_after_approval" if final_state=="active" else "commerce.workflow.publish_to_inactive_review",
        "approval_scope":"final-proposal" if mode=="single_final" else "publish-and-deactivate"}
