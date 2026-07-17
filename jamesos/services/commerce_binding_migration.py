from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import secrets
from typing import Any

from jamesos.core.commerce.proposal import canonical_proposal_sha256
from jamesos.core.errors import StateConflictError
from jamesos.core.profiles.selection import PROFILES_ROOT, selected_profile_id
from jamesos.services import product_orchestrator
from jamesos.services.commerce_workflow import CommerceWorkflow, _atomic_json


MIGRATION_VERSION = "1.0"


def _now() -> str: return datetime.now().astimezone().isoformat()
def _canonical_digest(value: Any) -> str: return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode()).hexdigest()
def _file_digest(path: Path) -> str: return sha256(path.read_bytes()).hexdigest()
def _redacted(value: Any) -> str | None:
    text = str(value or "")
    return f"profile:{sha256(text.encode()).hexdigest()[:12]}" if text else None


class LegacyCommerceBindingMigration:
    """Local-only compatibility migration; this service has no external adapters."""

    def __init__(self, workflow: CommerceWorkflow | None = None, *, profiles_root: Path = PROFILES_ROOT,
            selected_profile_resolver=selected_profile_id):
        self.workflow = workflow or CommerceWorkflow()
        self.profiles_root = Path(profiles_root)
        self.selected_profile_resolver = selected_profile_resolver

    def _error(self, code: str, message: str, stage: str) -> StateConflictError:
        return StateConflictError(code, diagnostic_message=message, operation="commerce_binding_migration", stage=stage, retryable=False)

    def _profile(self, profile_id: str) -> tuple[dict[str, Any], Path]:
        path = self.profiles_root / f"{profile_id}.json"
        try: profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc: raise self._error("MIGRATION_PROFILE_NOT_FOUND", "Requested private commerce profile is unavailable.", "profile") from exc
        if profile.get("profile_type") != "commerce_shop" or str(profile.get("profile_id") or "") != profile_id:
            raise self._error("MIGRATION_PROFILE_INVALID", "Requested profile is not the exact commerce_shop profile.", "profile")
        return profile, path

    def _read(self, job_id: str, target_profile_id: str | None) -> dict[str, Any]:
        state = self.workflow._state(job_id); root = self.workflow.orchestrator._path(job_id).parent / "commerce-proposal"
        try:
            proposal = json.loads((root / "current.json").read_text()); private = json.loads((root / "current-private.json").read_text())
            approval = json.loads((root / "approval.json").read_text())
        except (OSError, ValueError) as exc: raise self._error("MIGRATION_LEGACY_EVIDENCE_MISSING", "Required approved proposal evidence is unavailable.", "evidence") from exc
        proposal_sha = proposal.get("proposal_sha256")
        if not proposal_sha or canonical_proposal_sha256(proposal) != proposal_sha or private.get("proposal_sha256") != proposal_sha:
            raise self._error("MIGRATION_PROPOSAL_INVALID", "Current proposal evidence is inconsistent.", "proposal")
        if approval.get("approved") is not True or approval.get("proposal_sha256") != proposal_sha:
            raise self._error("MIGRATION_APPROVAL_INVALID", "Approval does not match the current proposal.", "approval")
        if state.get("stage") != "proposal_approved" or state.get("publish_status") != "not_published" or state.get("order_status") != "not_created":
            raise self._error("MIGRATION_STATE_CONFLICT", "Job is not an approved, unpublished, order-free legacy proposal.", "state")
        journal = root / "publication-execution.json"
        if journal.exists(): raise self._error("MIGRATION_PUBLICATION_EXISTS", "Publication execution evidence already exists.", "journal")
        binding = private.get("provider_binding") or {}; product_id = binding.get("product_id")
        if not product_id or str(product_id) == str(product_orchestrator.PROTECTED_PRODUCT_ID):
            raise self._error("MIGRATION_PROTECTED_PRODUCT", "Private product binding is missing or protected.", "ownership")
        legacy_ids = [str(x) for x in (private.get("profile_binding"), state.get("profile_id"), state.get("selected_profile_id")) if x]
        candidates = sorted(set(legacy_ids))
        if not candidates: raise self._error("MIGRATION_LEGACY_PROFILE_REQUIRED", "No exact legacy private profile identity exists.", "profile")
        if len(candidates) != 1: raise self._error("MIGRATION_LEGACY_PROFILE_AMBIGUOUS", "Legacy private profile identities conflict.", "profile")
        legacy_id = candidates[0]; selected_id = str(self.selected_profile_resolver() or "")
        explicit = target_profile_id is not None; target_id = str(target_profile_id or selected_id)
        if not target_id: raise self._error("MIGRATION_PROFILE_NOT_FOUND", "No target commerce profile was selected.", "profile")
        profile, profile_path = self._profile(target_id); config = profile.get("configuration") or {}
        provider = str(config.get("provider_type") or config.get("provider") or "printify").lower()
        marketplace = str(config.get("marketplace_type") or config.get("expected_marketplace") or config.get("sales_channel") or "").lower()
        destination = str(config.get("expected_marketplace") or config.get("sales_channel") or marketplace).lower()
        final_state = str(config.get("expected_final_state") or config.get("etsy_final_state") or "").lower()
        printify_shop = config.get("printify_shop_id"); etsy_shop = config.get("etsy_shop_id")
        if provider != "printify" or marketplace != "etsy" or destination != str(proposal.get("expected_marketplace") or "").lower() or final_state != str(proposal.get("expected_final_state") or "").lower():
            raise self._error("MIGRATION_PROFILE_CONFLICT", "Target profile provider, marketplace, destination, or final state conflicts with the proposal.", "profile")
        if str(printify_shop or "") != str(binding.get("shop_id") or ""):
            raise self._error("MIGRATION_PRINTIFY_SHOP_CONFLICT", "Target profile Printify shop differs from private job evidence.", "profile")
        return {"state": state, "root": root, "proposal": proposal, "private": private, "approval": approval,
            "legacy_id": legacy_id, "selected_id": selected_id, "target_id": target_id, "profile": profile, "profile_path": profile_path,
            "provider": provider, "marketplace": marketplace, "destination": destination, "final_state": final_state,
            "printify_shop": printify_shop, "etsy_shop": etsy_shop, "explicit": explicit}

    def _plan(self, data: dict[str, Any], *, repair_profile_binding: bool, set_selected_profile: bool) -> dict[str, Any]:
        reasons = ["BLOCKED_PROFILE_IDENTITY_MISMATCH"] if data["target_id"] != data["legacy_id"] and not data["explicit"] else []
        repair_source = None
        etsy_shop = data["etsy_shop"]
        if not etsy_shop:
            legacy_exact = (data["profile"].get("private_bindings") or {}).get("etsy_shop_id") or (data["profile"].get("configuration") or {}).get("legacy_etsy_shop_id")
            if repair_profile_binding and legacy_exact:
                etsy_shop = legacy_exact; repair_source = "target_profile_exact_legacy_binding"
            else: reasons.append("BLOCKED_ETSY_SHOP_BINDING_REQUIRED")
        files = ["commerce-proposal/current-private.json", "commerce-proposal/execution-binding-migration.json"]
        if repair_source: files.append("private commerce profile")
        if set_selected_profile and data["selected_id"] != data["target_id"]: files.append("selected commerce profile pointer")
        return {"result": "commerce_execution_binding_migration_plan", "dry_run": True, "job_id": data["state"]["job_id"],
            "proposal_sha256": data["proposal"]["proposal_sha256"], "approval_compatible": True,
            "legacy_profile": _redacted(data["legacy_id"]), "selected_profile": _redacted(data["selected_id"]), "target_profile": _redacted(data["target_id"]),
            "printify_shop_binding_match": True, "etsy_shop_binding_available": bool(etsy_shop),
            "expected_marketplace": data["proposal"]["expected_marketplace"], "expected_final_state": data["proposal"]["expected_final_state"],
            "files_would_change": files if not reasons else [], "public_proposal_sha_unchanged": True, "approval_remains_valid": True,
            "selected_profile_would_change": bool(set_selected_profile and data["selected_id"] != data["target_id"]),
            "blocking_reason": reasons[0] if reasons else None, "blocking_reasons": reasons, "migration_can_proceed": not reasons, "external_calls": False,
            "publication_performed": False, "order_created": False, "_etsy_shop": etsy_shop, "_repair_source": repair_source}

    def migrate(self, *, job_id: str, profile_id: str | None = None, confirmed: bool = False,
            set_selected_profile: bool = False, repair_profile_binding: bool = False) -> dict[str, Any]:
        if (set_selected_profile or repair_profile_binding) and not confirmed:
            raise self._error("MIGRATION_CONFIRMATION_REQUIRED", "Profile selection or repair flags require --confirm.", "confirmation")
        data = self._read(job_id, profile_id); plan = self._plan(data, repair_profile_binding=repair_profile_binding, set_selected_profile=set_selected_profile)
        public_plan = {k: v for k, v in plan.items() if not k.startswith("_")}
        existing = data["private"].get("execution_profile_binding")
        if existing:
            existing_digest = data["private"].get("execution_profile_binding_sha256")
            expected = {"schema_version": "1.0", "job_id": job_id, "proposal_sha256": data["proposal"]["proposal_sha256"],
                "profile_id": data["target_id"], "provider": data["provider"], "marketplace": data["marketplace"],
                "printify_shop_id": data["printify_shop"], "etsy_shop_id": plan["_etsy_shop"], "destination": data["destination"],
                "expected_final_state": data["final_state"], "migration_source": "legacy_approved_private_evidence", "migration_version": MIGRATION_VERSION}
            comparable = {key: existing.get(key) for key in expected}
            if comparable != expected or existing_digest != _canonical_digest(existing):
                raise self._error("MIGRATION_BINDING_CONFLICT", "A conflicting private execution binding already exists.", "binding")
            return {**public_plan, "dry_run": not confirmed, "already_migrated": True, "write_performed": False,
                "files_would_change": [], "blocking_reason": None, "blocking_reasons": [], "migration_can_proceed": True}
        if not confirmed: return public_plan
        if plan["blocking_reason"]: raise self._error(plan["blocking_reason"], "Migration cannot proceed without an exact private Etsy shop binding.", "profile")
        # Re-read immediately before writes and ensure the same validated target.
        fresh = self._read(job_id, profile_id)
        if _canonical_digest({k: fresh[k] for k in ("legacy_id", "selected_id", "target_id", "provider", "marketplace", "destination", "final_state", "printify_shop", "etsy_shop")}) != _canonical_digest({k: data[k] for k in ("legacy_id", "selected_id", "target_id", "provider", "marketplace", "destination", "final_state", "printify_shop", "etsy_shop")}):
            raise self._error("MIGRATION_STATE_CONFLICT", "Migration inputs changed during validation.", "concurrency")
        root = fresh["root"]; private_path = root / "current-private.json"; proposal_path = root / "current.json"; approval_path = root / "approval.json"
        etsy_shop = plan["_etsy_shop"]; binding = {"schema_version": "1.0", "job_id": job_id,
            "proposal_sha256": fresh["proposal"]["proposal_sha256"], "profile_id": fresh["target_id"], "provider": fresh["provider"],
            "marketplace": fresh["marketplace"], "printify_shop_id": fresh["printify_shop"], "etsy_shop_id": etsy_shop,
            "destination": fresh["destination"], "expected_final_state": fresh["final_state"], "created_at": _now(),
            "migration_source": "legacy_approved_private_evidence", "migration_version": MIGRATION_VERSION}
        digest = _canonical_digest(binding)
        migration_id = f"commerce-binding-{secrets.token_hex(8)}"; backup_root = root / "migration-backups" / f"{datetime.now().astimezone().strftime('%Y%m%dT%H%M%S%z')}-{migration_id[-8:]}"
        backup_root.mkdir(parents=True, exist_ok=False); os.chmod(backup_root, 0o700)
        prior_hashes = {"current-private.json": _file_digest(private_path), "current.json": _file_digest(proposal_path), "approval.json": _file_digest(approval_path)}
        (backup_root / "current-private.json").write_bytes(private_path.read_bytes()); os.chmod(backup_root / "current-private.json", 0o600)
        profile_changed = False
        if plan["_repair_source"]:
            profile_backup = backup_root / "profile.json"; profile_backup.write_bytes(fresh["profile_path"].read_bytes()); os.chmod(profile_backup, 0o600)
            profile = dict(fresh["profile"]); config = dict(profile.get("configuration") or {})
            if config.get("etsy_shop_id") not in (None, "", etsy_shop): raise self._error("MIGRATION_ETSY_SHOP_CONFLICT", "Existing Etsy shop binding conflicts with exact legacy evidence.", "profile")
            config["etsy_shop_id"] = etsy_shop; config["etsy_shop_binding_source"] = plan["_repair_source"]; profile["configuration"] = config
            _atomic_json(fresh["profile_path"], profile, 0o600); profile_changed = True
        pointer_changed = False
        if set_selected_profile and fresh["selected_id"] != fresh["target_id"]:
            pointer = self.profiles_root / "selected_commerce_profile"
            if pointer.exists():
                pointer_backup = backup_root / "selected_commerce_profile"; pointer_backup.write_bytes(pointer.read_bytes()); os.chmod(pointer_backup, 0o600)
            temp = pointer.with_name(f".{pointer.name}.{secrets.token_hex(6)}.tmp"); temp.write_text(fresh["target_id"] + "\n", encoding="utf-8"); os.chmod(temp, 0o600); os.replace(temp, pointer); pointer_changed = True
        updated = dict(fresh["private"]); updated["execution_profile_binding"] = binding; updated["execution_profile_binding_sha256"] = digest
        _atomic_json(private_path, updated, 0o600)
        receipt = {"schema_version": "1.0", "migration_id": migration_id, "created_at": _now(), "job_id": job_id,
            "proposal_sha256": fresh["proposal"]["proposal_sha256"], "files_changed": ["current-private.json"] + (["profile.json"] if profile_changed else []) + (["selected_commerce_profile"] if pointer_changed else []),
            "prior_hashes": prior_hashes, "new_hashes": {"current-private.json": _file_digest(private_path)}, "execution_profile_binding_sha256": digest,
            "proposal_sha_unchanged": _file_digest(proposal_path) == prior_hashes["current.json"], "approval_unchanged": _file_digest(approval_path) == prior_hashes["approval.json"],
            "external_calls": False, "publication_performed": False, "order_created": False}
        _atomic_json(root / "execution-binding-migration.json", receipt, 0o600)
        written = json.loads(private_path.read_text());
        if _canonical_digest(written["execution_profile_binding"]) != written["execution_profile_binding_sha256"]:
            raise self._error("MIGRATION_DIGEST_INVALID", "Written private binding digest did not verify.", "verification")
        final_state = self.workflow._state(job_id)
        if final_state.get("stage") != "proposal_approved" or (root / "publication-execution.json").exists():
            raise self._error("MIGRATION_STATE_CONFLICT", "Post-migration job state changed unexpectedly.", "verification")
        return {**public_plan, "dry_run": False, "already_migrated": False, "write_performed": True,
            "files_changed": ["private execution evidence"] + (["private profile"] if profile_changed else []) + (["selected profile pointer"] if pointer_changed else [])}
