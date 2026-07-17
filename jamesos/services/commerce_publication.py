from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from jamesos.core.commerce.proposal import canonical_proposal_sha256
from jamesos.core.errors import StateConflictError
from jamesos.services import product_orchestrator
from jamesos.services.commerce_workflow import CommerceWorkflow, _atomic_json, _sha_file
from jamesos.services.product_orchestrator import validate_listing_metadata


PUBLICATION_STAGES = (
    "proposal_approved", "publication_pending", "publication_started",
    "provider_update_uncertain", "provider_update_verified",
    "marketplace_publish_submitted", "marketplace_listing_pending",
    "marketplace_listing_resolved", "final_state_verified",
    "publication_uncertain", "publication_failed", "completed",
)


class ProviderDraftAdapter(Protocol):
    def get_product(self, shop_binding: Any, product_binding: Any) -> dict[str, Any]: ...
    def update_product(self, shop_binding: Any, product_binding: Any, payload: dict[str, Any]) -> dict[str, Any]: ...
    def publish_product(self, shop_binding: Any, product_binding: Any, payload: dict[str, Any]) -> dict[str, Any]: ...


class MarketplaceAdapter(Protocol):
    def resolve_listing(self, *, provider_product: dict[str, Any], publication_evidence: dict[str, Any]) -> dict[str, Any] | None: ...
    def get_listing_state(self, listing_binding: Any) -> dict[str, Any]: ...


class PrintifyProviderDraftAdapter:
    def __init__(self, client: Any): self.client = client
    def get_product(self, shop_binding: Any, product_binding: Any) -> dict[str, Any]: return self.client.get_product(shop_binding, product_binding)
    def update_product(self, shop_binding: Any, product_binding: Any, payload: dict[str, Any]) -> dict[str, Any]: return self.client.update_product(shop_binding, product_binding, payload)
    def publish_product(self, shop_binding: Any, product_binding: Any, payload: dict[str, Any]) -> dict[str, Any]: return self.client.publish_product(shop_binding, product_binding, payload)


def _external_listing_id(value: Any) -> Any:
    """Extract only an explicit durable external listing binding; never infer by title."""
    if not isinstance(value, dict): return None
    candidate = value.get("listing_id")
    if candidate not in (None, ""): return candidate
    for key in ("external", "listing", "result"):
        child = value.get(key)
        if isinstance(child, dict) and child.get("id") not in (None, ""): return child.get("id")
        candidate = _external_listing_id(child)
        if candidate not in (None, ""): return candidate
    return None


class EtsyMarketplaceAdapter:
    """Resolve the exact Printify-bound listing, then use Etsy as marketplace truth."""
    def __init__(self, etsy_client: Any, expected_shop_binding: Any):
        self.client = etsy_client
        self.expected_shop_binding = expected_shop_binding
        self._listings: dict[Any, dict[str, Any]] = {}

    def resolve_listing(self, *, provider_product: dict[str, Any], publication_evidence: dict[str, Any]) -> dict[str, Any] | None:
        external = provider_product.get("external") or {}
        listing_id = _external_listing_id(publication_evidence) or external.get("listing_id") or external.get("id")
        if listing_id in (None, ""): return None
        try: lookup_id = int(listing_id)
        except (TypeError, ValueError): lookup_id = listing_id
        listing = self.client.get_listing(lookup_id)
        owner = listing.get("shop_id") or (listing.get("shop") or {}).get("shop_id")
        if owner not in (None, "") and str(owner) != str(self.expected_shop_binding):
            raise StateConflictError("PUBLICATION_STATE_CONFLICT", diagnostic_message="Resolved marketplace listing belongs to another shop.", operation="commerce_publication", stage="marketplace_listing_resolution", retryable=False)
        self._listings[lookup_id] = listing
        return {"id": lookup_id}

    def get_listing_state(self, listing_binding: Any) -> dict[str, Any]:
        listing = self._listings.get(listing_binding) or self.client.get_listing(listing_binding)
        state = str(listing.get("state") or "").lower() or None
        url = self.get_safe_listing_url(listing)
        return {"state": state, "public_url": url}

    def get_safe_listing_url(self, listing_or_id: Any) -> str | None:
        listing = listing_or_id if isinstance(listing_or_id, dict) else self._listings.get(listing_or_id, {})
        candidate = str(listing.get("url") or listing.get("listing_url") or "")
        try:
            parsed = urlsplit(candidate)
            return candidate if parsed.scheme == "https" and parsed.hostname and (parsed.hostname == "etsy.com" or parsed.hostname.endswith(".etsy.com")) else None
        except ValueError:
            return None


# Backward-compatible import name; its behavior is now Etsy-authoritative.
PrintifyMarketplaceAdapter = EtsyMarketplaceAdapter


class ConnectedSalesChannelMarketplaceAdapter:
    """Interpret Printify's connected-channel binding without calling Etsy directly."""
    def __init__(self):self._records={}
    def resolve_listing(self,*,provider_product:dict[str,Any],publication_evidence:dict[str,Any])->dict[str,Any]|None:
        listing_id=_external_listing_id(publication_evidence) or _external_listing_id(provider_product.get("external") or {})
        if listing_id in (None,""):return None
        external=provider_product.get("external") or {};url=str(external.get("url") or external.get("listing_url") or "")
        self._records[listing_id]={"state":"active" if _published(provider_product) else "pending","public_url":url if url.startswith("https://www.etsy.com/") else None};return {"id":listing_id}
    def get_listing_state(self,listing_binding:Any)->dict[str,Any]:return self._records.get(listing_binding,{"state":"pending","public_url":None})


def _now() -> str: return datetime.now().astimezone().isoformat()
def _digest(value: Any) -> str: return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def _published(remote: dict[str, Any]) -> bool: return remote.get("is_published") is True or remote.get("published") is True
def _definite_rejection(exc: Exception) -> bool:
    status = getattr(exc, "status", None) or getattr(exc, "status_code", None)
    return type(status) is int and 400 <= status < 500


class CommercePublicationExecutor:
    def __init__(self, workflow: CommerceWorkflow | None = None, *, provider: ProviderDraftAdapter | None = None,
            marketplace: MarketplaceAdapter | None = None, profile_loader: Callable[..., dict[str, Any]] | None = None):
        self.workflow, self.provider, self.marketplace, self.profile_loader = workflow, provider, marketplace, profile_loader

    def _error(self, code: str, message: str, stage: str) -> StateConflictError:
        return StateConflictError(code, diagnostic_message=message, operation="commerce_publication", stage=stage, retryable=False)

    def _validated(self, job_id: str, proposal_sha256: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any], Path]:
        if not self.workflow: raise self._error("PUBLICATION_EXECUTOR_NOT_CONFIGURED", "Publication workflow is not configured.", "configuration")
        state = self.workflow._state(job_id); root = self.workflow.orchestrator._path(job_id).parent / "commerce-proposal"
        if state.get("stage") == "completed":
            try:
                proposal = json.loads((root / "current.json").read_text()); private = json.loads((root / "current-private.json").read_text())
                completed_journal = json.loads((root / "publication-execution.json").read_text())
            except (OSError, ValueError) as exc: raise self._error("PUBLICATION_STATE_CONFLICT", "Completed publication evidence is unavailable.", "completion") from exc
            if (proposal.get("proposal_sha256") != proposal_sha256 or canonical_proposal_sha256(proposal) != proposal_sha256
                    or completed_journal.get("status") != "completed" or completed_journal.get("proposal_sha256") != proposal_sha256):
                raise self._error("PUBLICATION_STATE_CONFLICT", "Completed publication evidence does not match the proposal.", "completion")
        else: state, proposal, private, root = self.workflow._current(job_id, proposal_sha256)
        if state.get("stage") not in PUBLICATION_STAGES or state.get("stage") == "revision_requested":
            raise self._error("PUBLICATION_APPROVAL_INVALID", "Job is not approved for publication.", "approval")
        try: approval = json.loads((root / "approval.json").read_text())
        except (OSError, ValueError) as exc: raise self._error("PUBLICATION_APPROVAL_INVALID", "Exact approval evidence is unavailable.", "approval") from exc
        if approval.get("approved") is not True or approval.get("proposal_sha256") != proposal_sha256:
            raise self._error("PUBLICATION_APPROVAL_INVALID", "Approval does not match the current proposal.", "approval")
        if state.get("order_status") != "not_created" or proposal.get("order_status") != "not_created":
            raise self._error("PUBLICATION_STATE_CONFLICT", "Order evidence prevents publication.", "order")
        selected = ((state.get("evidence") or {}).get("selection") or {}).get("selected") or {}; art = Path(str(selected.get("png_path") or ""))
        if not art.is_file() or _sha_file(art) != proposal.get("artwork_sha256"):
            raise self._error("PUBLICATION_STATE_CONFLICT", "Approved artwork no longer matches.", "artwork")
        evidence = state.get("evidence") or {}; upload = evidence.get("upload") or {}; draft = evidence.get("draft") or {}
        try: visual = json.loads((root.parent / "visual-review" / "visual-review.json").read_text())
        except (OSError, ValueError) as exc: raise self._error("PUBLICATION_STATE_CONFLICT", "Visual review evidence is unavailable.", "visual_review") from exc
        checks = visual.get("checks") or {}
        if checks.get("artwork_image_id") != upload.get("printify_image_id") or checks.get("artwork_image_id_matches") is not True:
            raise self._error("PUBLICATION_STATE_CONFLICT", "Visual review does not match current provider artwork.", "visual_review")
        observed = {x.get("color"): x.get("downloaded_sha256") for x in checks.get("mockups") or [] if x.get("verified_mockup_available") is True}
        approved = {x.get("color"): x.get("downloaded_sha256") for x in proposal.get("mockups") or []}
        if observed != approved: raise self._error("PUBLICATION_STATE_CONFLICT", "Approved mockup evidence changed.", "visual_review")
        validate_listing_metadata(state, "commerce_publication", {"title": proposal["title"], "description": proposal["description"], "tags": proposal["tags"], "price_cents": proposal["price_cents"]})
        binding = private.get("provider_binding") or {}
        if binding.get("shop_id") != state.get("shop_id") or binding.get("product_id") != draft.get("printify_product_id") or binding.get("upload_id") != upload.get("printify_image_id"):
            raise self._error("PUBLICATION_STATE_CONFLICT", "Private provider ownership binding changed.", "ownership")
        if not binding.get("product_id") or str(binding.get("product_id")) == str(product_orchestrator.PROTECTED_PRODUCT_ID):
            raise self._error("PUBLICATION_STATE_CONFLICT", "Protected or missing provider product cannot be published.", "ownership")
        return state, proposal, private, approval, root

    def _validate_profile(self, private: dict[str, Any], proposal: dict[str, Any]) -> None:
        if not self.profile_loader: return
        try: profile = self.profile_loader(required=True)
        except Exception as exc: raise self._error("PUBLICATION_PROFILE_CHANGED", "Selected commerce profile is unavailable.", "profile") from exc
        config = profile.get("configuration") or {}; expected = private.get("execution_profile_binding") or {}
        current = {"profile_id": profile.get("profile_id"), "provider": config.get("provider_type", "printify"),
            "marketplace": config.get("marketplace_type") or config.get("expected_marketplace"), "shop_id": config.get("printify_shop_id"),
            "etsy_shop_id": config.get("etsy_shop_id"), "destination": config.get("expected_marketplace"), "expected_final_state": config.get("expected_final_state")}
        if not expected:
            expected = {"profile_id": private.get("profile_binding"), "provider": "printify", "marketplace": proposal.get("expected_marketplace"),
                "shop_id": (private.get("provider_binding") or {}).get("shop_id"), "destination": proposal.get("expected_marketplace"),
                "expected_final_state": proposal.get("expected_final_state")}
        normalized_expected = {"profile_id": expected.get("profile_id"), "provider": expected.get("provider"), "marketplace": expected.get("marketplace"),
            "shop_id": expected.get("printify_shop_id", expected.get("shop_id")), "etsy_shop_id": expected.get("etsy_shop_id"),
            "destination": expected.get("destination"), "expected_final_state": expected.get("expected_final_state")}
        if any(str(current.get(k) or "").lower() != str(value or "").lower() for k,value in normalized_expected.items() if value is not None):
            raise self._error("PUBLICATION_PROFILE_CHANGED", "Selected commerce profile no longer matches the approved private execution binding.", "profile")

    def _new_journal(self, job_id: str, sha: str, private: dict[str, Any]) -> dict[str, Any]:
        now = _now(); steps = {name: {"step": name, "outcome": "not_started", "attempt_count": 0, "maximum_attempts": 1} for name in
            ("provider_metadata_update", "provider_update_verification", "marketplace_publish", "marketplace_listing_resolution", "final_state_verification")}
        return {"schema_version": "1.1", "job_id": job_id, "proposal_sha256": sha, "execution_id": uuid4().hex, "created_at": now,
            "updated_at": now, "status": "publication_pending", "steps": steps, "external_write_count": 0, "order_created": False,
            "private_execution_digest": _digest(private.get("execution_profile_binding") or private.get("profile_binding"))}

    def _save(self, path: Path, journal: dict[str, Any]) -> None: journal["updated_at"] = _now(); _atomic_json(path, journal)
    def _stage(self, state: dict[str, Any], stage: str) -> None: state["stage"] = stage; product_orchestrator._atomic_json(self.workflow.orchestrator._path(state["job_id"]), state)

    def _start(self, path: Path, journal: dict[str, Any], name: str, intent: str, target: dict[str, Any], request: dict[str, Any], intended_state: dict[str, Any] | None = None) -> dict[str, Any]:
        step = journal["steps"][name]
        if step["outcome"] in {"started", "uncertain"} or step["attempt_count"] >= 1:
            raise self._error("PUBLICATION_RESULT_UNCERTAIN", f"{name} cannot be retried automatically.", name)
        step.update(outcome="started", intended_action=intent, target_binding=target, idempotency_key=f"{journal['execution_id']}:{name}",
            request_digest=_digest(request), intended_state=intended_state, started_at=_now(), attempt_count=1)
        self._save(path, journal); return step

    def _verification(self, remote: dict[str, Any], proposal: dict[str, Any], private: dict[str, Any]) -> dict[str, str]:
        variants = remote.get("variants") or []; enabled = {x.get("id") for x in variants if x.get("is_enabled") is True}; expected_ids = set(proposal["enabled_variants"])
        enabled_prices = {x.get("price") for x in variants if x.get("is_enabled") is True}
        areas = remote.get("print_areas") or []; fronts = []; unexpected = []
        coverage = set()
        for area in areas:
            coverage.update(area.get("variant_ids") or [])
            for placeholder in area.get("placeholders") or []:
                images = placeholder.get("images") or []
                if placeholder.get("position") == "front": fronts.extend(images)
                elif images: unexpected.append(str(placeholder.get("position") or "unknown"))
        expected = proposal["placement"]; upload = (private.get("provider_binding") or {}).get("upload_id")
        result = {
            "title": "verified" if remote.get("title") == proposal["title"] else "mismatch",
            "description": "verified" if remote.get("description") == proposal["description"] else "mismatch",
            "tags": "not_returned" if "tags" not in remote else "verified" if remote.get("tags") == proposal["tags"] else "mismatch",
            "enabled_variant_ids": "verified" if enabled == expected_ids else "mismatch",
            "disabled_variants": "verified" if all((x.get("id") in expected_ids) == (x.get("is_enabled") is True) for x in variants) else "mismatch",
            "prices": "verified" if enabled_prices == {proposal["price_cents"]} else "mismatch",
            "artwork": "verified" if len(fronts) == 1 and fronts[0].get("id") == upload else "mismatch",
            "placement": "verified" if len(fronts) == 1 and all(fronts[0].get(k) == expected.get(k) for k in ("x", "y", "scale", "angle")) else "mismatch",
            "print_area_coverage": "not_returned" if not any("variant_ids" in area for area in areas) else "verified" if expected_ids <= coverage else "mismatch",
            "unexpected_artwork": "verified" if not unexpected else "mismatch",
            "color_size_mapping": "verified" if expected_ids <= {x.get("id") for x in variants} else "mismatch",
        }
        return result

    def _provider_matches(self, remote: dict[str, Any], proposal: dict[str, Any], private: dict[str, Any]) -> bool:
        verification = self._verification(remote, proposal, private)
        required = set(verification) - {"tags", "print_area_coverage"}
        return (all(verification[k] == "verified" for k in required)
            and verification["tags"] in {"verified", "not_returned"}
            and verification["print_area_coverage"] in {"verified", "not_returned"})

    def _payload(self, remote: dict[str, Any], proposal: dict[str, Any], private: dict[str, Any]) -> dict[str, Any]:
        enabled = set(proposal["enabled_variants"]); variants = []
        for row in remote.get("variants") or []:
            updated = dict(row); updated["is_enabled"] = row.get("id") in enabled
            if updated["is_enabled"]: updated["price"] = proposal["price_cents"]
            variants.append(updated)
        upload = (private.get("provider_binding") or {}).get("upload_id")
        print_areas = []
        for area in remote.get("print_areas") or [{"variant_ids": [x.get("id") for x in variants], "placeholders": []}]:
            updated_area = dict(area); updated_area["variant_ids"] = list(area.get("variant_ids") or [x.get("id") for x in variants])
            updated_area["placeholders"] = [{"position": "front", "images": [{"id": upload, **proposal["placement"]}]}]
            print_areas.append(updated_area)
        return {"title": proposal["title"], "description": proposal["description"], "tags": proposal["tags"], "variants": variants, "print_areas": print_areas}

    def _owned(self, remote: dict[str, Any], target: dict[str, Any]) -> bool:
        return (remote.get("id") == target["product"] and remote.get("shop_id") in (None, target["shop"])
            and not remote.get("orders") and remote.get("order_status") in (None, "not_created"))

    def _pending(self, path: Path, journal: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        step = journal["steps"]["marketplace_listing_resolution"]; step.update(outcome="pending", safe_next_action="reconcile_publication")
        journal["status"] = "marketplace_listing_pending"; self._save(path, journal); self._stage(state, "marketplace_listing_pending")
        return self._public(journal, {"proposal_sha256": journal["proposal_sha256"]})

    def _resolve_listing(self, remote: dict[str, Any], evidence: dict[str, Any], product_binding: Any) -> dict[str, Any] | None:
        try: return self.marketplace.resolve_listing(provider_product=remote, publication_evidence=evidence)
        except TypeError as exc:
            # Compatibility for injected pre-Phase-3 fakes only; production adapters use provider_product.
            if "provider_product" not in str(exc): raise
            return self.marketplace.resolve_listing(product_binding=product_binding, publication_evidence=evidence)

    def _complete_listing(self, path: Path, journal: dict[str, Any], state: dict[str, Any], proposal: dict[str, Any], approval: dict[str, Any], listing: dict[str, Any]) -> dict[str, Any]:
        step = journal["steps"]["marketplace_listing_resolution"]; step.update(outcome="completed", completed_at=_now(), response_evidence={"listing_binding_digest": _digest(listing["id"])})
        journal["status"] = "marketplace_listing_resolved"; self._save(path, journal); self._stage(state, "marketplace_listing_resolved")
        observed = self.marketplace.get_listing_state(listing["id"]); expected = proposal["expected_final_state"]
        if observed.get("state") != expected:
            journal["steps"]["final_state_verification"].update(outcome="failed", completed_at=_now(), verification_evidence={"expected": expected, "observed": observed.get("state")})
            journal["status"] = "publication_failed"; self._save(path, journal); self._stage(state, "publication_failed")
            raise self._error("MARKETPLACE_FINAL_STATE_MISMATCH", "Marketplace final state did not match approval.", "final_state_verification")
        public_url = str(observed.get("public_url") or ""); safe_url = None
        try:
            parsed = urlsplit(public_url)
            if parsed.scheme in {"http", "https"} and parsed.hostname: safe_url = public_url
        except ValueError: pass
        journal["steps"]["final_state_verification"].update(outcome="completed", completed_at=_now(), verification_evidence={"expected": expected, "observed": observed.get("state")})
        publish = journal["steps"]["marketplace_publish"]
        journal.update(status="completed", completed_at=_now(), approved_at=approval.get("approved_at"), publication_started_at=publish.get("started_at"),
            marketplace=proposal["expected_marketplace"], verified_final_state=expected, public_listing_url=safe_url, provider_update_verified=True, order_created=False)
        self._save(path, journal); self._stage(state, "final_state_verified")
        state = self.workflow.orchestrator.load(state["job_id"]); state.update(stage="completed", publish_status="published", order_status="not_created")
        product_orchestrator._atomic_json(self.workflow.orchestrator._path(state["job_id"]), state)
        return self._public(journal, proposal)

    def execute(self, *, job_id: str, proposal_sha256: str, approval: dict[str, Any] | None = None, confirmed: bool = False) -> dict[str, Any]:
        state, proposal, private, approval_record, root = self._validated(job_id, proposal_sha256)
        path = root / "publication-execution.json"; journal = json.loads(path.read_text()) if path.is_file() else None
        if journal and journal.get("proposal_sha256") != proposal_sha256: raise self._error("PUBLICATION_STATE_CONFLICT", "Publication journal is bound to another proposal.", "journal")
        if journal and journal.get("status") == "completed": return self._public(journal, proposal)
        if not confirmed: return {"result": "commerce_publication_plan", "dry_run": True, "write_performed": False, "proposal_sha256": proposal_sha256, "publication_performed": False, "order_created": False}
        if not self.provider or not self.marketplace: raise self._error("PUBLICATION_EXECUTOR_NOT_CONFIGURED", "Provider and marketplace adapters are required.", "configuration")
        self._validate_profile(private, proposal)
        if journal and journal.get("status") == "provider_update_uncertain":
            raise self._error("PROVIDER_UPDATE_RESULT_UNCERTAIN", "Provider update result is uncertain; run read-only reconciliation.", "provider_metadata_update")
        if journal and journal.get("status") == "publication_uncertain":
            raise self._error("PUBLICATION_RESULT_UNCERTAIN", "Publication result is uncertain; run read-only reconciliation.", "marketplace_publish")
        journal = journal or self._new_journal(job_id, proposal_sha256, private); self._save(path, journal)
        binding = private["provider_binding"]; target = {"shop": binding.get("shop_id"), "product": binding.get("product_id")}
        remote = self.provider.get_product(target["shop"], target["product"])
        if not self._owned(remote, target):
            journal["status"] = "publication_failed"; self._save(path, journal); self._stage(state, "publication_failed")
            raise self._error("PUBLICATION_STATE_CONFLICT", "Provider product is not the job-owned product.", "ownership")
        update = journal["steps"]["provider_metadata_update"]
        if update["outcome"] in {"started", "uncertain"}:
            if self._provider_matches(remote, proposal, private): update.update(outcome="completed", completed_at=_now(), reconciled=True); self._save(path, journal)
            else:
                update.update(outcome="uncertain", safe_next_action="reconcile_publication"); journal["status"] = "provider_update_uncertain"; self._save(path, journal); self._stage(state, "provider_update_uncertain")
                raise self._error("PROVIDER_UPDATE_RESULT_UNCERTAIN", "Provider update result is uncertain; run read-only reconciliation.", "provider_metadata_update")
        publish = journal["steps"]["marketplace_publish"]
        publication_attempted = publish["outcome"] in {"started", "uncertain", "completed"} or journal["status"] in {"marketplace_publish_submitted", "marketplace_listing_pending", "marketplace_listing_resolved", "final_state_verified"}
        if not publication_attempted and _published(remote):
            journal["status"] = "publication_failed"; self._save(path, journal); self._stage(state, "publication_failed")
            raise self._error("PUBLICATION_STATE_CONFLICT", "Provider product was already published before this execution.", "ownership")
        if not publication_attempted:
            if not self._provider_matches(remote, proposal, private):
                payload = self._payload(remote, proposal, private); step = self._start(path, journal, "provider_metadata_update", "reconcile approved proposal metadata", target, payload, payload)
                try: response = self.provider.update_product(target["shop"], target["product"], payload)
                except Exception as exc:
                    journal["external_write_count"] += 1
                    if _definite_rejection(exc):
                        step.update(outcome="failed", diagnostic={"type": type(exc).__name__, "definite_rejection": True}, safe_next_action="inspect_failure"); journal["status"] = "publication_failed"
                        self._save(path, journal); self._stage(state, "publication_failed")
                        raise self._error("PUBLICATION_PROVIDER_UPDATE_FAILED", "Provider rejected the metadata update before publication.", "provider_metadata_update") from exc
                    step.update(outcome="uncertain", diagnostic={"type": type(exc).__name__}, safe_next_action="reconcile_publication"); journal["status"] = "provider_update_uncertain"
                    self._save(path, journal); self._stage(state, "provider_update_uncertain")
                    raise self._error("PROVIDER_UPDATE_RESULT_UNCERTAIN", "Provider update may have been applied and will not be retried.", "provider_metadata_update") from exc
                step.update(outcome="completed", completed_at=_now(), response_evidence={"acknowledged": response is not None}); journal["external_write_count"] += 1; self._save(path, journal)
            elif update["outcome"] == "not_started": update.update(outcome="completed", completed_at=_now(), attempt_count=0, response_evidence={"no_op": True}); self._save(path, journal)
            verify = self.provider.get_product(target["shop"], target["product"]); verification = self._verification(verify, proposal, private)
            if not self._provider_matches(verify, proposal, private):
                journal["steps"]["provider_update_verification"].update(outcome="failed", completed_at=_now(), verification_evidence=verification); journal["status"] = "publication_failed"
                self._save(path, journal); self._stage(state, "publication_failed"); raise self._error("PUBLICATION_PROVIDER_VERIFICATION_FAILED", "Provider product does not match the approved proposal.", "provider_update_verification")
            journal["steps"]["provider_update_verification"].update(outcome="completed", completed_at=_now(), verification_evidence=verification); journal["status"] = "provider_update_verified"
            self._save(path, journal); self._stage(state, "provider_update_verified")
            request = {"title": True, "description": True, "images": True, "variants": True, "tags": True, "keyFeatures": True, "shipping_template": True}
            publish = self._start(path, journal, "marketplace_publish", "publish existing approved provider draft", target, request); self._stage(state, "publication_started")
            try: publication = self.provider.publish_product(target["shop"], target["product"], request)
            except Exception as exc:
                publish.update(outcome="uncertain", diagnostic={"type": type(exc).__name__}, safe_next_action="reconcile_publication"); journal["status"] = "publication_uncertain"; journal["external_write_count"] += 1
                self._save(path, journal); self._stage(state, "publication_uncertain"); raise self._error("PUBLICATION_RESULT_UNCERTAIN", "Publication call returned an ambiguous result and will not be retried.", "marketplace_publish") from exc
            publish.update(outcome="completed", completed_at=_now(), response_evidence=publication); journal["external_write_count"] += 1; journal["status"] = "marketplace_publish_submitted"
            self._save(path, journal); self._stage(state, "marketplace_publish_submitted"); remote = self.provider.get_product(target["shop"], target["product"])
        else:
            publication = publish.get("response_evidence") or {}
            if publish["outcome"] in {"started", "uncertain"}:
                if not _published(remote):
                    publish.update(outcome="uncertain", safe_next_action="reconcile_publication"); journal["status"] = "publication_uncertain"; self._save(path, journal); self._stage(state, "publication_uncertain")
                    raise self._error("PUBLICATION_RESULT_UNCERTAIN", "Publication result remains uncertain; it will not be retried.", "marketplace_publish")
                publish.update(outcome="completed", completed_at=_now(), reconciled=True); journal["status"] = "marketplace_publish_submitted"; self._save(path, journal); self._stage(state, "marketplace_publish_submitted")
        try: listing = self._resolve_listing(remote, publish.get("response_evidence") or {}, target["product"])
        except StateConflictError:
            journal["status"] = "publication_failed"; self._save(path, journal); self._stage(state, "publication_failed"); raise
        if not listing or listing.get("id") in (None, ""): return self._pending(path, journal, state)
        return self._complete_listing(path, journal, state, proposal, approval_record, listing)

    def reconcile(self, *, job_id: str, proposal_sha256: str) -> dict[str, Any]:
        state, proposal, private, approval, root = self._validated(job_id, proposal_sha256); path = root / "publication-execution.json"
        try: journal = json.loads(path.read_text())
        except (OSError, ValueError) as exc: raise self._error("PUBLICATION_STATE_CONFLICT", "Publication journal is unavailable.", "reconciliation") from exc
        if journal.get("status") == "completed": return self._public(journal, proposal)
        if not self.provider or not self.marketplace: raise self._error("PUBLICATION_EXECUTOR_NOT_CONFIGURED", "Read-only adapters are required.", "configuration")
        self._validate_profile(private, proposal)
        binding = private["provider_binding"]; remote = self.provider.get_product(binding["shop_id"], binding["product_id"])
        update = journal["steps"]["provider_metadata_update"]
        if journal.get("status") == "provider_update_uncertain" or update.get("outcome") in {"started", "uncertain"}:
            if not self._provider_matches(remote, proposal, private):
                return {"result": "provider_update_still_uncertain", "stage": "provider_update_uncertain", "external_write_performed": False, "publication_performed": False, "order_created": False}
            update.update(outcome="completed", completed_at=_now(), reconciled=True); journal["status"] = "provider_update_verified"; self._save(path, journal); self._stage(state, "provider_update_verified")
            return self._public(journal, proposal)
        publish = journal["steps"]["marketplace_publish"]
        if publish.get("outcome") in {"started", "uncertain"} and not _published(remote):
            if remote.get("is_published") is False and not remote.get("external"):
                publish.update(outcome="failed", completed_at=_now(), verification_evidence={"published": False}, safe_next_action="inspect_failure")
                journal["status"] = "publication_failed"; self._save(path, journal); self._stage(state, "publication_failed")
                return self._public(journal, proposal)
            return {"result": "publication_still_uncertain", "stage": "publication_uncertain", "external_write_performed": False, "publication_performed": False, "order_created": False}
        if publish.get("outcome") in {"started", "uncertain"}:
            publish.update(outcome="completed", completed_at=_now(), reconciled=True); journal["status"] = "marketplace_publish_submitted"; self._save(path, journal); self._stage(state, "marketplace_publish_submitted")
        try: listing = self._resolve_listing(remote, publish.get("response_evidence") or {}, binding["product_id"])
        except StateConflictError:
            journal["status"] = "publication_failed"; self._save(path, journal); self._stage(state, "publication_failed"); raise
        if not listing or listing.get("id") in (None, ""): return self._pending(path, journal, state)
        return self._complete_listing(path, journal, state, proposal, approval, listing)

    def _public(self, journal: dict[str, Any], proposal: dict[str, Any]) -> dict[str, Any]:
        return {"result": "commerce_publication_completed" if journal.get("status") == "completed" else "commerce_publication_status", "stage": journal.get("status"),
            "proposal_sha256": proposal["proposal_sha256"], "completed_at": journal.get("completed_at"), "marketplace": journal.get("marketplace"),
            "verified_final_state": journal.get("verified_final_state"), "public_listing_url": journal.get("public_listing_url"),
            "provider_update_verified": bool(journal.get("provider_update_verified")), "publication_performed": journal.get("status") == "completed", "order_created": False}
