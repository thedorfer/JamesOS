from __future__ import annotations

from dataclasses import dataclass
import copy
from datetime import datetime
from hashlib import sha256
import html
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable
from uuid import uuid4

from jamesos.config import VAULT
from jamesos.core.errors import ArtifactIntegrityError, StateConflictError, ValidationError
from jamesos.integrations.printify_client import PrintifyClient
from jamesos.services import printify_product, sale_candidate_vector
from jamesos.services.error_handler import handle_error


ROOT = VAULT / "JamesOS" / "Commerce" / "product-orchestrator"
MODE = "printify-draft"
POLICY = "draft_only_autopilot"
PROTECTED_PRODUCT_ID = "6a57eaa752f2c3e4700dbf23"
STAGES = ("prompt_received", "brief_ready", "artwork_ready", "production_artifact_ready", "design_candidates_ready",
          "design_selected", "listing_ready", "printify_image_uploaded", "printify_draft_created", "mockups_downloaded",
          "awaiting_human_approval", "failed")
DEFAULT_COLORS = ["Black", "Dark Grey Heather", "White"]
DEFAULT_SIZES = ["S", "M", "L", "XL", "2XL", "3XL"]
COLOR_EXACT = {"black":"Black", "dark grey heather":"Dark Grey Heather", "white":"White"}
COLOR_ALIASES = {"dark heather":"Dark Grey Heather", "dark gray heather":"Dark Grey Heather"}
COLOR_WORDS = re.compile(r"\b(?:black|white|grey|gray|heather|charcoal|navy|red|blue|green|yellow|purple|pink|orange)\b", re.I)


def _json_sha(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _file_sha(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True, default=str); handle.write("\n"); handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    temporary.replace(path)


def resolve_garment_colors(value: str | list[str], *, configured_aliases: dict[str, str] | None = None) -> dict[str, Any]:
    aliases = {**COLOR_ALIASES, **{key.casefold(): item for key, item in (configured_aliases or {}).items()}}
    phrases = {**COLOR_EXACT, **aliases}; requested = []; occupied: list[tuple[int,int]] = []
    inputs = [str(item).strip() for item in value] if isinstance(value, list) else None
    if inputs is None:
        text = value
        matches: list[tuple[int,str]] = []
        for phrase in sorted(phrases, key=len, reverse=True):
            for match in re.finditer(rf"(?<!\w){re.escape(phrase)}(?!\w)", text, re.I):
                if not any(match.start() < end and match.end() > start for start,end in occupied):
                    occupied.append((match.start(),match.end()));matches.append((match.start(),match.group(0).casefold()))
        matches.sort()
        for match in COLOR_WORDS.finditer(text):
            if not any(match.start() < end and match.end() > start for start,end in occupied): matches.append((match.start(),match.group(0).casefold()))
        requested = [phrase for _,phrase in sorted(matches)]
    else: requested = [item.casefold() for item in inputs if item]
    resolved=[];unresolved=[];seen=set()
    for phrase in requested:
        canonical=phrases.get(phrase)
        if canonical is None:
            if phrase not in unresolved: unresolved.append(phrase)
            continue
        if canonical in seen: continue
        seen.add(canonical);resolved.append({"requested":phrase,"canonical":canonical,
            "resolution":"exact" if phrase in COLOR_EXACT else "configured_alias"})
    return {"requested_color_phrases":requested,"resolved_colors":resolved,"unresolved_colors":unresolved,
            "canonical_colors":[item["canonical"] for item in resolved]}


def normalize_prompt(prompt: str, *, price: int | None = None, garment_colors: list[str] | None = None,
                     sizes: list[str] | None = None) -> dict[str, Any]:
    cleaned = " ".join(prompt.split())
    if not cleaned: raise ValidationError("VALIDATION_FAILED", diagnostic_message="Product prompt is empty.", operation="product_orchestrator", stage="prompt_received")
    quoted = re.search(r"[\"“](.+?)[\"”]", cleaned)
    exact = quoted.group(1).upper().strip() if quoted else "LOVE IS LOVE" if "love is love" in cleaned.lower() else ""
    price_match = re.search(r"\$\s*(\d{1,4})(?:\.(\d{2}))?", cleaned)
    parsed_price = int(price_match.group(1)) * 100 + int(price_match.group(2) or 0) if price_match else 2499
    lower = cleaned.lower(); color_resolution = resolve_garment_colors(garment_colors if garment_colors is not None else cleaned)
    colors = color_resolution["canonical_colors"] or (DEFAULT_COLORS if not color_resolution["requested_color_phrases"] else [])
    return {"exact_text": exact, "product_type": "unisex_t_shirt", "visual_style": "playful bold retro" if "retro" in lower else "bold graphic",
        "garment_colors": colors, "color_resolution": color_resolution, "sizes": sizes or DEFAULT_SIZES, "price_cents": price if price is not None else parsed_price,
        "currency": "USD", "preferred_layout": "integrated_shadow", "audience": "inclusive adults",
        "listing_tone": "playful positive", "blank": "Bella+Canvas 3001", "print_provider": "Monster Digital"}


def score_candidate(candidate: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    checks = candidate.get("quality_checks") or {}; blockers = [key for key, passed in checks.items() if key.startswith("hard_") and passed is not True]
    components = {"hard_quality": 35 if not blockers else 0, "phrase_correctness": 15 if checks.get("hard_phrase_correct") else 0,
        "safe_bounds": 10 if checks.get("hard_safe_bounds") else 0, "artwork_integrity": 15 if checks.get("hard_artwork_integrity") else 0,
        "thumbnail_readability": int(candidate.get("thumbnail_readability_score", 0)), "garment_contrast": int(candidate.get("garment_contrast_score", 0)),
        "balanced_bounds": int(candidate.get("balanced_bounds_score", 0)), "prompt_style_match": 5 if brief["preferred_layout"] in candidate.get("direction", "") else 3}
    return {"score": sum(components.values()), "components": components, "hard_blockers": blockers,
            "automated_score_scope": "deterministic technical ranking; not proof of artistic quality"}


def select_candidate(candidates: list[dict[str, Any]], brief: dict[str, Any]) -> dict[str, Any]:
    ranked = [{**candidate, "scoring": score_candidate(candidate, brief)} for candidate in candidates]
    eligible = [item for item in ranked if not item["scoring"]["hard_blockers"]]
    if not eligible: raise ValidationError("VALIDATION_FAILED", diagnostic_message="No design candidate passed every hard quality check.",
        operation="product_orchestrator", stage="design_selected", context={"candidate_scores": [x["scoring"] for x in ranked]})
    selected = max(eligible, key=lambda item: (item["scoring"]["score"], item["candidate_id"]))
    return {"selected": selected, "alternatives_considered": [{"candidate_id": x["candidate_id"], **x["scoring"]} for x in ranked],
        "approval": {"approved_by": "JamesOS automated quality gate", "approval_scope": "technical draft-readiness only",
                     "human_artistic_approval": False, "policy": POLICY, "approved_at": datetime.now().astimezone().isoformat()}}


def generate_listing(brief: dict[str, Any], selected: dict[str, Any]) -> dict[str, Any]:
    exact = brief["exact_text"].title()
    return {"title": f"{exact} Rainbow Heart Unisex Tee", "description": f"A {brief['visual_style']} {exact} design on a soft Bella+Canvas 3001 unisex tee.",
        "tags": [brief["exact_text"].lower(), "rainbow heart", "inclusive shirt", "retro tee", "unisex shirt"],
        "price_cents": brief["price_cents"], "currency": brief["currency"], "colors": brief["garment_colors"], "sizes": brief["sizes"],
        "blank": brief["blank"], "print_provider": brief["print_provider"], "selected_design_sha256": selected["png_sha256"],
        "draft_status": "not_published", "order_status": "not_created"}


def normalize_printify_variants(response: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise ValidationError("VALIDATION_FAILED", diagnostic_message="Printify variants response must be an object.",
            operation="product_orchestrator", stage="printify_variant_selection")
    normalized = []
    for row in response.get("variants") or []:
        if not isinstance(row, dict): continue
        title = str(row.get("title") or "").strip(); parts = [part.strip() for part in title.rsplit("/", 1)]
        color, size = (parts[0], parts[1].upper()) if len(parts) == 2 else ("", "")
        variant_id = row.get("id")
        if not isinstance(variant_id, int) or not color or size not in DEFAULT_SIZES: continue
        normalized.append({"variant_id": variant_id, "title": title, "color": color, "size": size,
            "is_available": bool(row.get("is_available", True)), "placeholders": row.get("placeholders") or []})
    return normalized


def select_printify_variants(response: dict[str, Any], *, colors: list[str], sizes: list[str]) -> dict[str, Any]:
    normalized = normalize_printify_variants(response); requested_colors = {value.strip().casefold() for value in colors}
    requested_sizes = {value.strip().upper() for value in sizes}
    selected = [row for row in normalized if row["is_available"] and row["color"].casefold() in requested_colors and row["size"] in requested_sizes]
    if not selected:
        raise ValidationError("VALIDATION_FAILED", diagnostic_message="No available Printify variants exactly matched the requested colors and sizes.",
            operation="product_orchestrator", stage="printify_variant_selection",
            context={"requested_colors": colors, "requested_sizes": sizes, "normalized_variant_count": len(normalized)})
    return {"normalized_variants": normalized, "selected_variants": selected,
            "selected_variant_ids": [row["variant_id"] for row in selected], "matching_policy": "exact case-insensitive color; exact normalized size"}


def _draft_marker(state: dict[str, Any]) -> str:
    stable = {"job_id": state["job_id"], "shop_id": state["shop_id"], "selected_design_sha256": state["evidence"]["selection"]["selected"]["png_sha256"]}
    return f"jamesos-orchestrator-{_json_sha(stable)[:20]}"


def _products(response: Any) -> list[dict[str, Any]]:
    if isinstance(response, list): return [row for row in response if isinstance(row, dict)]
    if isinstance(response, dict):
        rows = response.get("data") or response.get("products") or []
        return [row for row in rows if isinstance(row, dict)]
    return []


def _find_marked_draft(response: Any, marker: str) -> dict[str, Any] | None:
    for product in _products(response):
        tags = {str(tag) for tag in product.get("tags") or []}
        if marker in tags: return product
    return None


def assess_draft_publication_state(state: dict[str, Any], remote: dict[str, Any]) -> dict[str, Any]:
    draft = state.get("evidence", {}).get("draft") or {}; transitions = state.get("transitions") or []
    publish_operations = {"publish", "publish_product", "printify_publish", "publish_succeeded"}
    publish_stages = {"published", "printify_published", "publish_succeeded"}
    publish_transition = next((item for item in transitions if item.get("result") == "completed" and
        (item.get("operation") in publish_operations or item.get("stage") in publish_stages)), None)
    publish_evidence = state.get("evidence", {}).get("publish_success")
    publication_record = state.get("evidence", {}).get("publication")
    if not publish_evidence and (publication_record is True or isinstance(publication_record,dict) and publication_record.get("status") in ("published","success","completed")):
        publish_evidence = publication_record
    blockers = []
    def block(field: str, value: Any, reason: str) -> None: blockers.append({"field":field,"value":value,"reason":reason})
    if state.get("publish_status") != "not_published": block("state.publish_status",state.get("publish_status"),"local workflow is not marked unpublished")
    if draft.get("publish_status") != "not_published": block("evidence.draft.publish_status",draft.get("publish_status"),"local draft is not marked unpublished")
    if remote.get("is_locked") is True: block("remote.is_locked",True,"locked products cannot be safely reconciled")
    if "is_published" in remote and remote.get("is_published") is True: block("remote.is_published",True,"API explicitly reports publication")
    if "published" in remote and remote.get("published") is True: block("remote.published",True,"API explicitly reports publication")
    if publish_transition: block("state.transitions",publish_transition,"a successful local publish transition exists")
    if publish_evidence: block("state.evidence.publish_success",publish_evidence,"local publish-success evidence exists")
    visible = remote.get("visible")
    warnings = ([{"field":"remote.visible","value":visible,
        "message":"Printify defaults this field to true; it is not sufficient publication evidence."}] if visible is True else [])
    return {"safe_to_reconcile":not blockers,"local_publish_status":state.get("publish_status"),
        "local_draft_publish_status":draft.get("publish_status"),"remote_visible":visible,
        "remote_visible_interpretation":"Printify defaults this field to true; it is not sufficient publication evidence.",
        "remote_is_published":remote.get("is_published") if "is_published" in remote else None,
        "remote_published":remote.get("published") if "published" in remote else None,"remote_is_locked":remote.get("is_locked"),
        "publish_transition_found":bool(publish_transition),"explicit_blockers":blockers,"informational_warnings":warnings}


def _default_candidates(evidence: dict[str, Any], root: Path, brief: dict[str, Any]) -> list[dict[str, Any]]:
    return sale_candidate_vector.generate_v4_refinements(evidence["candidate"], root, phrase=brief["exact_text"])


@dataclass
class Adapters:
    evidence: Callable[[str], dict[str, Any]] = printify_product._approved_evidence
    candidates: Callable[[dict[str, Any], Path, dict[str, Any]], list[dict[str, Any]]] = _default_candidates
    client_factory: Callable[[], PrintifyClient] = PrintifyClient


class ProductOrchestrator:
    def __init__(self, root: Path = ROOT, adapters: Adapters | None = None) -> None:
        self.root, self.adapters = root, adapters or Adapters()

    def _path(self, job_id: str) -> Path: return self.root / job_id / "orchestrator-state.json"
    def load(self, job_id: str) -> dict[str, Any]: return json.loads(self._path(job_id).read_text(encoding="utf-8"))

    def _transition(self, state: dict[str, Any], stage: str, operation: str, output: Any, *, result: str = "completed", error_id: str | None = None) -> None:
        if stage not in STAGES: raise ValueError(stage)
        previous = state.get("stage_output") or {}
        state["stage"] = stage; state["stage_output"] = output
        state["transitions"].append({"timestamp": datetime.now().astimezone().isoformat(), "input_sha": _json_sha(previous),
            "output_sha": _json_sha(output), "operation": operation, "stage": stage, "result": result, "error_id": error_id})
        state["updated_at"] = state["transitions"][-1]["timestamp"]; _atomic_json(self._path(state["job_id"]), state)

    def create(self, *, prompt: str, shop_id: int, mode: str = MODE, source_job_id: str | None = None, price: int | None = None,
               garment_colors: list[str] | None = None, sizes: list[str] | None = None, confirm_printify_draft: bool = False,
               job_id: str | None = None) -> dict[str, Any]:
        if mode != MODE: raise ValidationError("VALIDATION_FAILED", diagnostic_message=f"Unsupported mode: {mode}", operation="product_orchestrator", stage="prompt_received")
        job_id = job_id or f"product-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        if self._path(job_id).exists(): raise StateConflictError("STATE_CONFLICT", diagnostic_message="Orchestrator job already exists.", operation="product_orchestrator", stage="prompt_received")
        state = {"job_id": job_id, "mode": mode, "policy": POLICY, "shop_id": shop_id, "source_job_id": source_job_id,
            "original_prompt": prompt, "brief": None, "stage": None, "stage_output": {}, "transitions": [], "evidence": {},
            "publish_status": "not_published", "order_status": "not_created", "protected_product_id": PROTECTED_PRODUCT_ID,
            "created_at": datetime.now().astimezone().isoformat()}
        self._transition(state, "prompt_received", "capture_prompt", {"prompt_sha256": sha256(prompt.encode()).hexdigest()})
        return self._run(state, price=price, garment_colors=garment_colors, sizes=sizes, confirmed=confirm_printify_draft)

    def resume(self, job_id: str, *, confirm_printify_draft: bool = False) -> dict[str, Any]:
        return self._run(self.load(job_id), confirmed=confirm_printify_draft)

    def reconcile_draft(self, job_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        state = self.load(job_id)
        if state.get("stage") != "awaiting_human_approval":
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Draft reconciliation requires awaiting_human_approval state.", operation="product_orchestrator.reconcile_draft", stage="preflight")
        draft = state.get("evidence", {}).get("draft") or {}; upload = state.get("evidence", {}).get("upload") or {}
        product_id = draft.get("printify_product_id")
        if not product_id or product_id == PROTECTED_PRODUCT_ID:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="The recorded draft is missing or protected.", operation="product_orchestrator.reconcile_draft", stage="ownership")
        client = self.adapters.client_factory(); remote = client.get_product(state["shop_id"], product_id)
        if remote.get("id") != product_id: raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote product ID does not match orchestrator ownership evidence.", operation="product_orchestrator.reconcile_draft", stage="ownership")
        if remote.get("shop_id") != state["shop_id"]:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote shop ID does not match the orchestrator job.", operation="product_orchestrator.reconcile_draft", stage="ownership",
                context={"blocker":{"field":"remote.shop_id","value":remote.get("shop_id"),"expected":state["shop_id"]}})
        marker = state.get("evidence", {}).get("draft_marker") or draft.get("draft_marker")
        if not marker or marker not in {str(tag) for tag in remote.get("tags") or []}:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote draft marker does not match orchestrator ownership evidence.", operation="product_orchestrator.reconcile_draft", stage="ownership")
        publication = assess_draft_publication_state(state, remote)
        if not publication["safe_to_reconcile"]:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Publication evidence blocks draft reconciliation.", operation="product_orchestrator.reconcile_draft", stage="publication",
                context={"publication_assessment":publication,"blockers":publication["explicit_blockers"]})
        if state.get("order_status") != "not_created" or remote.get("order_status") not in (None,"not_created") or remote.get("orders"):
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="A product with order evidence cannot be reconciled.", operation="product_orchestrator.reconcile_draft", stage="order")
        if remote.get("blueprint_id") != 12 or remote.get("print_provider_id") != 29:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote blueprint or provider differs from the orchestrator plan.", operation="product_orchestrator.reconcile_draft", stage="provider")
        image_id = upload.get("printify_image_id"); placements = [image for area in remote.get("print_areas") or []
            for placeholder in area.get("placeholders") or [] for image in placeholder.get("images") or [] if image.get("id") == image_id]
        if not image_id or not placements:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="The orchestrator image is not present in the remote draft.", operation="product_orchestrator.reconcile_draft", stage="artwork")
        selected_sha = state.get("evidence", {}).get("selection", {}).get("selected", {}).get("png_sha256")
        if upload.get("selected_design_sha256") != selected_sha:
            raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH", diagnostic_message="Uploaded image evidence no longer matches the selected design.", operation="product_orchestrator.reconcile_draft", stage="artwork")
        resolution = resolve_garment_colors(state["original_prompt"])
        if resolution["unresolved_colors"] or resolution["canonical_colors"] != DEFAULT_COLORS:
            raise ValidationError("VALIDATION_FAILED", diagnostic_message="The prompt did not resolve to the required three exact garment colors.", operation="product_orchestrator.reconcile_draft", stage="color_resolution", context=resolution)
        catalog = client.get_variants(12,29); desired = select_printify_variants(catalog,colors=resolution["canonical_colors"],sizes=state["brief"]["sizes"])
        desired_ids = desired["selected_variant_ids"]; current_rows = normalize_printify_variants({"variants":remote.get("variants") or []})
        current_ids = [row["variant_id"] for row in current_rows if row["is_available"] and next((item.get("is_enabled",True) for item in remote.get("variants") or [] if item.get("id")==row["variant_id"]),True)]
        retain = [item for item in desired_ids if item in current_ids]; add = [item for item in desired_ids if item not in current_ids]; remove = [item for item in current_ids if item not in desired_ids]
        current_scale = float(placements[0].get("scale") or 0); placement_plan = [{"label":"current","scale":current_scale,"inside_placeholder":0 < current_scale <= 1},
            {"label":"current_plus_8_percent","scale":round(current_scale*1.08,4),"inside_placeholder":0 < current_scale*1.08 <= 1},
            {"label":"current_plus_12_percent","scale":round(current_scale*1.12,4),"inside_placeholder":0 < current_scale*1.12 <= 1}]
        plan = {"product_id":product_id,"selected_image_id":image_id,"requested_colors":resolution["canonical_colors"],
            "color_resolution":resolution,"current_colors":list(dict.fromkeys(row["color"] for row in current_rows if row["variant_id"] in current_ids)),
            "current_sizes":list(dict.fromkeys(row["size"] for row in current_rows if row["variant_id"] in current_ids)),
            "desired_colors":resolution["canonical_colors"],"desired_sizes":state["brief"]["sizes"],"variant_ids_to_retain":retain,
            "variant_ids_to_add":add,"variant_ids_to_remove":remove,"current_variant_count":len(current_ids),"resulting_variant_count":len(desired_ids),
            "price_cents":state["evidence"]["listing"]["price_cents"],"placement":copy.deepcopy(placements[0]),"placement_adjustment_plan":placement_plan,
            "placement_change_included":False,"publish_status":"not_published","order_status":"not_created","draft_marker":marker,
            "publication_assessment":publication}
        if not confirmed: return {"result":"draft_reconciliation_plan","write_performed":False,"plan":plan}
        payload={"title":remote.get("title"),"description":remote.get("description"),"tags":remote.get("tags") or [],"blueprint_id":12,"print_provider_id":29,
            "variants":[{"id":item,"price":plan["price_cents"],"is_enabled":True} for item in desired_ids],"print_areas":copy.deepcopy(remote.get("print_areas") or [])}
        for area in payload["print_areas"]:
            area["variant_ids"]=desired_ids
            for placeholder in area.get("placeholders") or []: placeholder["variant_ids"]=desired_ids
        write_performed=bool(add or remove)
        if write_performed: client.update_product(state["shop_id"],product_id,payload)
        verified=client.get_product(state["shop_id"],product_id)
        verified_ids=sorted(item.get("id") for item in verified.get("variants") or [] if item.get("is_enabled"))
        verified_publication=assess_draft_publication_state(state,verified)
        if verified.get("id")!=product_id or verified.get("shop_id")!=state["shop_id"] or not verified_publication["safe_to_reconcile"] or verified_ids!=sorted(desired_ids):
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote draft verification did not match the reconciliation plan.", operation="product_orchestrator.reconcile_draft", stage="verification")
        verified_placements=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            for image in placeholder.get("images") or [] if image.get("id")==image_id]
        placement_keys=("x","y","scale","angle");placement_unchanged=bool(verified_placements and all(verified_placements[0].get(key)==placements[0].get(key) for key in placement_keys))
        evidence={"status":"existing_draft_updated" if write_performed else "already_reconciled","previous_variant_ids":current_ids,
            "resulting_variant_ids":desired_ids,"added_variant_ids":add,"removed_variant_ids":remove,"remote_product_verified":True,
            "updated_at":datetime.now().astimezone().isoformat(),"no_new_upload":True,"no_new_product":True,
            "publish_status":"not_published","order_status":"not_created","placement_unchanged":placement_unchanged,"plan":plan}
        state["brief"]["garment_colors"]=resolution["canonical_colors"];state["brief"]["color_resolution"]=resolution
        state["evidence"]["listing"]["colors"]=resolution["canonical_colors"]
        state["evidence"]["variant_selection"]=desired;state["evidence"]["draft_reconciliation"]=evidence;state["evidence"]["draft"]["variant_ids"]=desired_ids
        self._transition(state,"awaiting_human_approval","reconcile_existing_draft_variants",evidence);self.report(job_id)
        return {"result":evidence["status"],"write_performed":write_performed,"plan":plan,"reconciliation":evidence}

    def _normalize_recovered_error(self, state: dict[str, Any]) -> bool:
        current = state.get("last_error")
        if state.get("stage") != "awaiting_human_approval" or not current: return False
        error_id = current.get("error_id"); history = state.setdefault("recovered_errors", [])
        failed_transition = next((item for item in reversed(state.get("transitions", [])) if item.get("error_id") == error_id), {})
        if error_id and not any(item.get("error_id") == error_id for item in history):
            history.append({"error_id": error_id, "code": current.get("code"), "failed_at": failed_transition.get("timestamp"),
                "recovered_at": datetime.now().astimezone().isoformat(), "recovered_stage": "awaiting_human_approval",
                "diagnostic_path": current.get("diagnostic_path")})
        state["last_error"] = None; _atomic_json(self._path(state["job_id"]), state)
        return True

    def _run(self, state: dict[str, Any], *, price: int | None = None, garment_colors: list[str] | None = None,
             sizes: list[str] | None = None, confirmed: bool = False) -> dict[str, Any]:
        completed = {item["stage"] for item in state["transitions"] if item["result"] == "completed"}
        if "awaiting_human_approval" in completed:
            changed = self._normalize_recovered_error(state)
            if changed: self.report(state["job_id"])
            return state
        try:
            if "brief_ready" not in completed:
                state["brief"] = normalize_prompt(state["original_prompt"], price=price, garment_colors=garment_colors, sizes=sizes)
                self._transition(state, "brief_ready", "normalize_prompt", state["brief"])
            unresolved = (state["brief"].get("color_resolution") or {}).get("unresolved_colors") or []
            if unresolved:
                raise ValidationError("VALIDATION_FAILED", diagnostic_message="Requested garment colors could not be resolved to exact catalog colors.",
                    operation="product_orchestrator", stage="brief_ready", context={"unresolved_colors":unresolved})
            evidence = self.adapters.evidence(state["source_job_id"] or "")
            if "artwork_ready" not in completed:
                artwork = {"path": str(evidence["candidate"]), "sha256": evidence["candidate_sha"], "approval_sha256": evidence["approval_sha"]}
                state["evidence"]["artwork"] = artwork; self._transition(state, "artwork_ready", "verify_approved_artwork", artwork)
            if _file_sha(Path(evidence["candidate"])) != evidence["candidate_sha"]: raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH", operation="product_orchestrator", stage="artwork_ready")
            if "production_artifact_ready" not in completed:
                production = {"canvas_dimensions": evidence["production"].get("canvas_dimensions"), "sha256": evidence["candidate_sha"]}
                if production["canvas_dimensions"] != [4500, 5400]: raise ValidationError("VALIDATION_FAILED", diagnostic_message="Production artifact dimensions must be 4500x5400.", operation="product_orchestrator", stage="production_artifact_ready")
                state["evidence"]["production"] = production; self._transition(state, "production_artifact_ready", "verify_production_artifact", production)
            design_root = self._path(state["job_id"]).parent / "design-candidates"
            if "design_candidates_ready" not in completed:
                candidates = self.adapters.candidates(evidence, design_root, state["brief"]); state["evidence"]["candidates"] = candidates
                self._transition(state, "design_candidates_ready", "generate_v4_refinements", {"candidates": candidates})
            candidates = state["evidence"]["candidates"]
            if "design_selected" not in completed:
                selection = select_candidate(candidates, state["brief"]); state["evidence"]["selection"] = selection
                self._transition(state, "design_selected", "technical_candidate_selection", selection)
            selected = state["evidence"]["selection"]["selected"]
            if "listing_ready" not in completed:
                listing = generate_listing(state["brief"], selected); state["evidence"]["listing"] = listing
                self._transition(state, "listing_ready", "generate_listing", listing)
            if not confirmed:
                raise ValidationError("VALIDATION_FAILED", diagnostic_message="Printify draft creation requires --confirm-printify-draft.", operation="product_orchestrator", stage="printify_image_uploaded",
                    state={"external_write_attempted": False, "external_write_completed": False, "safe_to_retry": True}, suggested_action="Resume with --confirm-printify-draft after reviewing the local evidence.")
            client = self.adapters.client_factory()
            if "printify_image_uploaded" not in completed:
                remote = client.upload_image_contents(f"jamesos-{state['job_id']}-{selected['png_sha256'][:12]}.png", __import__("base64").b64encode(Path(selected["png_path"]).read_bytes()).decode())
                upload = {"printify_image_id": remote["id"], "selected_design_sha256": selected["png_sha256"]}; state["evidence"]["upload"] = upload
                self._transition(state, "printify_image_uploaded", "printify_upload", upload)
            else: client.get_upload(state["evidence"]["upload"]["printify_image_id"])
            if "printify_draft_created" not in completed:
                variant_evidence = select_printify_variants(client.get_variants(12, 29), colors=state["brief"]["garment_colors"], sizes=state["brief"]["sizes"])
                chosen = variant_evidence["selected_variant_ids"]; marker = state["evidence"].get("draft_marker") or _draft_marker(state)
                state["evidence"]["variant_selection"] = variant_evidence; state["evidence"]["draft_marker"] = marker
                _atomic_json(self._path(state["job_id"]), state)
                listing = state["evidence"]["listing"]; image_id = state["evidence"]["upload"]["printify_image_id"]
                payload = {"title": listing["title"], "description": listing["description"], "tags": listing["tags"], "blueprint_id": 12, "print_provider_id": 29,
                    "variants": [{"id": x, "price": listing["price_cents"], "is_enabled": True} for x in chosen],
                    "print_areas": [{"variant_ids": chosen, "placeholders": [{"position": "front", "images": [{"id": image_id, "x": .5, "y": .46, "scale": .85, "angle": 0}]}]}]}
                payload["tags"] = [*payload["tags"], marker]
                product = _find_marked_draft(client.list_products(state["shop_id"]), marker)
                reconciled = product is not None
                if product is None: product = client.create_product(state["shop_id"], payload)
                if product.get("id") == PROTECTED_PRODUCT_ID: raise StateConflictError("STATE_CONFLICT", diagnostic_message="Printify returned the protected baseline product ID.", operation="product_orchestrator", stage="printify_draft_created")
                draft = {"printify_product_id": product["id"], "variant_ids": chosen, "draft_marker": marker,
                    "reconciled_existing_remote_draft": reconciled, "publish_status": "not_published", "order_status": "not_created"}
                state["evidence"]["draft"] = draft; self._transition(state, "printify_draft_created", "printify_create_unpublished_draft", draft)
            else: client.get_product(state["shop_id"], state["evidence"]["draft"]["printify_product_id"])
            if "mockups_downloaded" not in completed:
                product = client.get_product(state["shop_id"], state["evidence"]["draft"]["printify_product_id"])
                mockups = []; mockup_root = self._path(state["job_id"]).parent / "mockups"; mockup_root.mkdir(exist_ok=True)
                for index, image in enumerate(product.get("images", [])[:6]):
                    url = str(image.get("src") or "")
                    if not url.startswith("https://"): continue
                    response = client.session.get(url, timeout=client.timeout); response.raise_for_status()
                    target = mockup_root / f"mockup-{index + 1}.jpg"; target.write_bytes(response.content)
                    mockups.append({"source_url":url,"local_path":str(target),"sha256":_file_sha(target),"variant_ids":image.get("variant_ids",[])})
                state["evidence"]["mockups"] = mockups; self._transition(state, "mockups_downloaded", "retrieve_mockup_metadata", {"mockups": mockups})
            final = {"status": "awaiting_human_approval", "banner": "DRAFT · NOT PUBLISHED · NO ORDER CREATED · AWAITING HUMAN APPROVAL"}
            self._transition(state, "awaiting_human_approval", "stop_before_publish", final)
            self._normalize_recovered_error(state); self.report(state["job_id"])
            return state
        except Exception as exc:
            envelope = handle_error(exc, operation="product_orchestrator", context={"job_id": state["job_id"], "source_job_id": state.get("source_job_id")},
                state=getattr(exc, "state", {}))
            state["last_error"] = {"error_id": envelope["error_id"], "code": envelope["code"], "user_message": envelope["user_message"],
                "retryable": envelope["retryable"], "suggested_action": envelope["suggested_action"], "diagnostic_path": envelope.get("diagnostic_artifact_path")}
            self._transition(state, "failed", "handle_failure", state["last_error"], result="failed", error_id=envelope["error_id"])
            return state

    def report(self, job_id: str) -> Path:
        state = self.load(job_id); path = self._path(job_id).with_name("product-orchestration-report.html")
        candidates = state.get("evidence", {}).get("candidates", [])
        scores = {x["candidate_id"]: x for x in state.get("evidence", {}).get("selection", {}).get("alternatives_considered", [])}
        cards = "".join(f"<section><h3>{html.escape(x['candidate_id'])}</h3><img src='{html.escape(x.get('thumbnail_path',''))}'><pre>{html.escape(json.dumps(scores.get(x['candidate_id']) or {}, indent=2))}</pre></section>" for x in candidates)
        recovered = state.get("recovered_errors") or []
        active = "None — the workflow is currently successful." if not state.get("last_error") else html.escape(json.dumps(state["last_error"], indent=2))
        reconciliation=state.get("evidence",{}).get("draft_reconciliation") or {}; colors=state.get("brief",{}).get("garment_colors") or []
        reconciliation_section=(f"<h2>EXISTING DRAFT UPDATED · NO NEW PRODUCT CREATED · NOT PUBLISHED · NO ORDER CREATED</h2><p>Requested colors:<br>{'<br>'.join(html.escape(x) for x in colors)}</p><p>Enabled variants: {len(reconciliation.get('resulting_variant_ids') or [])}</p><pre>{html.escape(json.dumps(reconciliation,indent=2))}</pre>" if reconciliation else "<h2>Draft reconciliation</h2><p>Not performed.</p>")
        document = f"<!doctype html><html><body><h1>DRAFT · NOT PUBLISHED · NO ORDER CREATED · AWAITING HUMAN APPROVAL</h1>{reconciliation_section}<h2>Current workflow state</h2><p>{html.escape(state['stage'])}</p><h2>Active failure</h2><pre>{active}</pre><h2>Recovered error history</h2><pre>{html.escape(json.dumps(recovered, indent=2))}</pre><h2>Original prompt</h2><p>{html.escape(state['original_prompt'])}</p><h2>Normalized brief</h2><pre>{html.escape(json.dumps(state.get('brief'), indent=2))}</pre><h2>V4 candidates</h2>{cards}<h2>Complete evidence and current state</h2><pre>{html.escape(json.dumps(state, indent=2, default=str))}</pre></body></html>"
        path.write_text(document, encoding="utf-8"); return path
