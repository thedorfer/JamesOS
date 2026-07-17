from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any

from jamesos.core.errors import ValidationError


SCHEMA_VERSION = "1.0"
PROPOSAL_TYPE = "commerce_final_review"
HASH_FIELDS = (
    "schema_version", "proposal_type", "job_id", "profile_binding_reference", "artwork_sha256", "artwork_phrase",
    "colors", "sizes", "enabled_variant_count", "enabled_variants", "placement", "title", "description", "tags",
    "price_cents", "currency", "product_model", "print_provider", "expected_marketplace", "expected_final_state",
    "mockups", "warnings", "required_manual_confirmations", "publication_status", "order_status", "provider_draft_status",
)


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        return [_stable(item) for item in value]
    if isinstance(value, float):
        return format(Decimal(str(value)).normalize(), "f")
    return value


def canonical_hash_payload(proposal: dict[str, Any]) -> dict[str, Any]:
    payload={key:deepcopy(proposal.get(key)) for key in HASH_FIELDS}
    payload["colors"]=sorted(payload.get("colors") or [],key=str.casefold)
    payload["sizes"]=sorted(payload.get("sizes") or [],key=str.casefold)
    payload["enabled_variants"]=sorted(payload.get("enabled_variants") or [])
    payload["tags"]=sorted(payload.get("tags") or [],key=str.casefold)
    payload["mockups"]=sorted(payload.get("mockups") or [],key=lambda item:str(item.get("color") or "").casefold())
    payload["warnings"]=sorted(payload.get("warnings") or [],key=str.casefold)
    payload["required_manual_confirmations"]=sorted(payload.get("required_manual_confirmations") or [],key=str.casefold)
    return _stable(payload)


def canonical_proposal_sha256(proposal: dict[str, Any]) -> str:
    encoded=json.dumps(canonical_hash_payload(proposal),sort_keys=True,separators=(",",":"),ensure_ascii=False).encode("utf-8")
    return sha256(encoded).hexdigest()


def compile_public_proposal(fields: dict[str, Any], *, generated_at: str) -> dict[str, Any]:
    proposal={"schema_version":SCHEMA_VERSION,"proposal_type":PROPOSAL_TYPE,**deepcopy(fields),"generated_at":generated_at,
        "approval_eligible":True,"superseded":False}
    invalid=[]
    required=("job_id","profile_binding_reference","artwork_sha256","artwork_phrase","title","description","currency",
        "product_model","print_provider","expected_marketplace","expected_final_state","publication_status","order_status","provider_draft_status")
    invalid.extend(key for key in required if not isinstance(proposal.get(key),str) or not proposal[key].strip())
    if type(proposal.get("price_cents")) is not int or proposal["price_cents"]<=0:invalid.append("price_cents")
    if proposal.get("enabled_variant_count")!=18 or len(proposal.get("enabled_variants") or [])!=18:invalid.append("enabled_variants")
    if len(proposal.get("tags") or [])!=13:invalid.append("tags")
    if len(proposal.get("mockups") or [])!=3 or any(not item.get("downloaded_sha256") or not item.get("verified") for item in proposal.get("mockups") or []):invalid.append("mockups")
    placement=proposal.get("placement") or {}
    if any(placement.get(key) is None for key in ("x","y","scale","angle")):invalid.append("placement")
    if invalid:
        raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Commerce proposal fields are incomplete: {', '.join(sorted(set(invalid)))}.",
            operation="commerce_workflow.prepare",stage="proposal_validation",retryable=False,
            context={"invalid_fields":sorted(set(invalid)),"external_write_performed":False})
    proposal["proposal_sha256"]=canonical_proposal_sha256(proposal)
    return proposal
