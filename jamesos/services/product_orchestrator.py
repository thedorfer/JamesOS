from __future__ import annotations

from dataclasses import dataclass
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


def normalize_prompt(prompt: str, *, price: int | None = None, garment_colors: list[str] | None = None,
                     sizes: list[str] | None = None) -> dict[str, Any]:
    cleaned = " ".join(prompt.split())
    if not cleaned: raise ValidationError("VALIDATION_FAILED", diagnostic_message="Product prompt is empty.", operation="product_orchestrator", stage="prompt_received")
    quoted = re.search(r"[\"“](.+?)[\"”]", cleaned)
    exact = quoted.group(1).upper().strip() if quoted else "LOVE IS LOVE" if "love is love" in cleaned.lower() else ""
    price_match = re.search(r"\$\s*(\d{1,4})(?:\.(\d{2}))?", cleaned)
    parsed_price = int(price_match.group(1)) * 100 + int(price_match.group(2) or 0) if price_match else 2499
    lower = cleaned.lower()
    colors = garment_colors or [color for color in DEFAULT_COLORS if color.lower().replace("grey", "gray") in lower.replace("grey", "gray")] or DEFAULT_COLORS
    return {"exact_text": exact, "product_type": "unisex_t_shirt", "visual_style": "playful bold retro" if "retro" in lower else "bold graphic",
        "garment_colors": colors, "sizes": sizes or DEFAULT_SIZES, "price_cents": price if price is not None else parsed_price,
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

    def _run(self, state: dict[str, Any], *, price: int | None = None, garment_colors: list[str] | None = None,
             sizes: list[str] | None = None, confirmed: bool = False) -> dict[str, Any]:
        completed = {item["stage"] for item in state["transitions"] if item["result"] == "completed"}
        if "awaiting_human_approval" in completed: return state
        try:
            if "brief_ready" not in completed:
                state["brief"] = normalize_prompt(state["original_prompt"], price=price, garment_colors=garment_colors, sizes=sizes)
                self._transition(state, "brief_ready", "normalize_prompt", state["brief"])
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
                variants = client.get_variants(12, 29); wanted = set(state["brief"]["sizes"]); colors = {x.lower() for x in state["brief"]["garment_colors"]}
                chosen = [x["id"] for x in variants if str(x.get("options", {}).get("size")) in wanted and str(x.get("options", {}).get("color", "")).lower() in colors]
                if not chosen: raise ValidationError("VALIDATION_FAILED", diagnostic_message="No valid Printify variants matched the brief.", operation="product_orchestrator", stage="printify_draft_created")
                listing = state["evidence"]["listing"]; image_id = state["evidence"]["upload"]["printify_image_id"]
                payload = {"title": listing["title"], "description": listing["description"], "tags": listing["tags"], "blueprint_id": 12, "print_provider_id": 29,
                    "variants": [{"id": x, "price": listing["price_cents"], "is_enabled": True} for x in chosen],
                    "print_areas": [{"variant_ids": chosen, "placeholders": [{"position": "front", "images": [{"id": image_id, "x": .5, "y": .46, "scale": .85, "angle": 0}]}]}]}
                product = client.create_product(state["shop_id"], payload)
                if product.get("id") == PROTECTED_PRODUCT_ID: raise StateConflictError("STATE_CONFLICT", diagnostic_message="Printify returned the protected baseline product ID.", operation="product_orchestrator", stage="printify_draft_created")
                draft = {"printify_product_id": product["id"], "variant_ids": chosen, "publish_status": "not_published", "order_status": "not_created"}
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
            self._transition(state, "awaiting_human_approval", "stop_before_publish", final); self.report(state["job_id"])
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
        document = f"<!doctype html><html><body><h1>DRAFT · NOT PUBLISHED · NO ORDER CREATED · AWAITING HUMAN APPROVAL</h1><h2>Original prompt</h2><p>{html.escape(state['original_prompt'])}</p><h2>Normalized brief</h2><pre>{html.escape(json.dumps(state.get('brief'), indent=2))}</pre><h2>V4 candidates</h2>{cards}<h2>Complete evidence and current state</h2><pre>{html.escape(json.dumps(state, indent=2, default=str))}</pre></body></html>"
        path.write_text(document, encoding="utf-8"); return path
