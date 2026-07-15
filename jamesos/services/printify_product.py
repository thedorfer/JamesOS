from __future__ import annotations

import base64
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from PIL import Image

from jamesos.integrations.printify_client import PrintifyClient, token_status
from jamesos.core.errors import ArtifactIntegrityError
from jamesos.services import job_queue, production_artifact


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def _json_hash(value: dict[str, Any]) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _write_immutable(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)


def status() -> dict[str, Any]:
    return {**token_status(), "required_scopes": ["shops.read", "catalog.read", "print_providers.read",
            "uploads.read", "uploads.write", "products.read", "products.write"],
            "publish_supported": False, "orders_supported": False}


def normalize_shops(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"shop_id": item.get("id"), "title": item.get("title"), "sales_channel": item.get("sales_channel")} for item in items]


def normalize_catalog(blueprint: dict[str, Any], provider: dict[str, Any], variants: dict[str, Any], shipping: dict[str, Any] | None = None) -> dict[str, Any]:
    options = variants.get("options") or {}
    normalized = []
    for item in variants.get("variants") or []:
        title = str(item.get("title") or "")
        parts = [part.strip() for part in title.split("/")]
        normalized.append({"variant_id": item.get("id"), "title": title,
                           "color": parts[0] if parts else None, "size": parts[-1] if len(parts) > 1 else None,
                           "cost": item.get("cost"), "available": item.get("is_available", True),
                           "placeholders": item.get("placeholders") or []})
    required_colors, required_sizes = {"black"}, {"s", "m", "l", "xl", "2xl"}
    colors = {str(v["color"] or "").lower() for v in normalized if v["available"]}
    sizes = {str(v["size"] or "").lower() for v in normalized if v["available"]}
    return {"blueprint_id": blueprint.get("id"), "blueprint_title": blueprint.get("title"),
            "brand": blueprint.get("brand"), "model": blueprint.get("model"),
            "print_provider_id": provider.get("id"), "provider_title": provider.get("title"),
            "provider_location": provider.get("location") or provider.get("country"),
            "decoration_methods": variants.get("print_areas") or options.get("print_areas") or [],
            "variants": normalized, "shipping": shipping or {},
            "required_colors_covered": required_colors <= colors, "required_sizes_covered": required_sizes <= sizes,
            "preferred_colors_covered": {"dark heather", "white"} & colors,
            "three_xl_available": "3xl" in sizes}


def search_shirt_blueprints(client: PrintifyClient) -> list[dict[str, Any]]:
    shirts = []
    for item in client.list_blueprints():
        text = f"{item.get('title','')} {item.get('brand','')} {item.get('model','')}".lower()
        if "shirt" in text or "tee" in text:
            shirts.append({"blueprint_id": item.get("id"), "title": item.get("title"),
                           "brand": item.get("brand"), "model": item.get("model"),
                           "ranking_reason": "Title/brand/model indicates an adult tee candidate; human selection required."})
    return shirts


def _approved_evidence(job_id: str) -> dict[str, Any]:
    job = job_queue.get_job(job_id); payload = job.get("payload") or {}
    if payload.get("final_artifact_approved") is not True or payload.get("final_artifact_status") != "approved":
        raise job_queue.JobQueueError("SHA-bound final artwork approval is required.")
    derivative, candidate, metadata, approval_path = production_artifact._critical_job_paths(job_id, payload)
    for path in (derivative, candidate, metadata, approval_path):
        if not path.is_file(): raise job_queue.JobQueueError(f"Required authoritative evidence is missing: {path.name}")
    production = payload.get("production_artifact") or {}
    approval = json.loads(approval_path.read_text(encoding="utf-8"))
    if approval != payload.get("final_artifact_approval") or approval.get("visual_review_result") != "passed":
        raise job_queue.JobQueueError("Final approval file and job state differ or visual review did not pass.")
    candidate_sha, metadata_sha, derivative_sha = _hash(candidate), _hash(metadata), _hash(derivative)
    if candidate_sha != approval.get("approved_artifact_sha256"): raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH", diagnostic_message="Approved candidate SHA mismatch.", operation="printify.evidence", stage="candidate_sha", context={"job_id": job_id})
    if metadata_sha != approval.get("production_metadata_sha256"): raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH", diagnostic_message="Approved production metadata SHA mismatch.", operation="printify.evidence", stage="metadata_sha", context={"job_id": job_id})
    derivative_evidence = approval.get("derivative_evidence") or {}
    if derivative_sha != derivative_evidence.get("approved_artifact_sha256"): raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH", diagnostic_message="Approved derivative SHA mismatch.", operation="printify.evidence", stage="derivative_sha", context={"job_id": job_id})
    selected_strategy = production.get("selected_strategy") or "ai_upscale"
    strategy_evidence = approval.get("strategy_evidence")
    if strategy_evidence and strategy_evidence.get("selected_strategy") != selected_strategy:
        raise job_queue.JobQueueError("Approved production strategy evidence mismatch.")
    if payload.get("provider_status") not in ("not_ready", "artwork_uploaded", "draft_created"):
        raise job_queue.JobQueueError("Provider state conflicts with Printify draft workflow.")
    return {"job": job, "payload": payload, "production": production, "approval": approval,
            "candidate": candidate, "candidate_sha": candidate_sha, "metadata_sha": metadata_sha,
            "approval_path": approval_path, "approval_sha": _hash(approval_path), "job_root": candidate.parents[2]}


def upload_approved_artwork(job_id: str, *, confirmed: bool, client: PrintifyClient, image_url: str | None = None) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Printify upload requires explicit confirmation.")
    evidence = _approved_evidence(job_id); commerce = evidence["job_root"] / "commerce" / "printify"
    commerce.mkdir(parents=True, exist_ok=True)
    if not commerce.is_dir() or not os.access(commerce, os.W_OK):
        raise job_queue.JobQueueError("Printify evidence directory is not writable; upload was not attempted.")
    record_path = commerce / "upload.json"
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("candidate_sha256") != evidence["candidate_sha"]: raise job_queue.JobQueueError("Existing upload is bound to a different candidate SHA.")
        remote = client.get_upload(record["printify_image_id"])
        return {**record, "remote": remote, "idempotent": True}
    candidate = evidence["candidate"]; before = _hash(candidate)
    filename = f"jamesos-{job_id}-{before[:12]}.png"
    if image_url:
        remote = client.upload_image_url(filename, image_url)
        method = "https_url"
    else:
        remote = client.upload_image_contents(filename, base64.b64encode(candidate.read_bytes()).decode("ascii")); method = "base64_contents"
    if _hash(candidate) != before: raise job_queue.JobQueueError("Approved candidate changed during upload.")
    if remote.get("mime_type") != "image/png" or int(remote.get("width") or 0) <= 0 or int(remote.get("height") or 0) <= 0:
        raise job_queue.JobQueueError("Printify upload response has invalid PNG metadata.")
    record = {"job_id": job_id, "candidate_path": str(candidate), "candidate_sha256": before,
              "final_approval_sha256": evidence["approval_sha"], "printify_image_id": remote.get("id"),
              "file_name": remote.get("file_name"), "width": remote.get("width"), "height": remote.get("height"),
              "size": remote.get("size"), "mime_type": remote.get("mime_type"), "preview_url": remote.get("preview_url"),
              "uploaded_at": remote.get("upload_time") or datetime.now().astimezone().isoformat(),
              "upload_method": method, "large_base64_warning": method == "base64_contents" and candidate.stat().st_size > 5 * 1024 * 1024,
              "api_operation_status": "completed", "idempotent": False}
    _write_immutable(record_path, record)
    job_queue.update_job_payload(job_id, {"printify_status": "artwork_uploaded", "provider_status": "artwork_uploaded",
                                         "final_print_ready": False, "product_status": "not_created", "publish_status": "not_published"})
    return record


def calculate_placement(artwork: tuple[int, int], placeholder: tuple[int, int], *, desired_width_fraction: float = .85,
                        requested_scale: float | None = None) -> dict[str, Any]:
    if min(*artwork, *placeholder) <= 0: raise ValueError("Artwork and placeholder dimensions must be positive.")
    calculated = min(desired_width_fraction, (placeholder[1] / placeholder[0]) / (artwork[1] / artwork[0]))
    scale = requested_scale if requested_scale is not None else calculated
    effective = (placeholder[0] * scale, placeholder[0] * scale * artwork[1] / artwork[0])
    dpi = artwork[0] / max(effective[0], 1) * 100
    return {"x": .5, "y": .5, "angle": 0, "requested_scale": requested_scale,
            "calculated_scale": calculated, "scale": scale, "placeholder_dimensions": list(placeholder),
            "artwork_dimensions": list(artwork), "expected_effective_print_dimensions": list(effective),
            "dpi_estimate": dpi, "dpi_warning": dpi < 150}


def create_draft_plan(job_id: str, *, upload: dict[str, Any], shop_id: int, blueprint_id: int, provider_id: int,
                      enabled_variant_ids: list[int], prices: dict[int, int], placeholder: tuple[int, int],
                      requested_scale: float | None = None, title: str = "Abstract Rainbow Heart Unisex Tee - Draft",
                      description: str = "Colorful abstract heart artwork on an adult unisex tee.") -> dict[str, Any]:
    evidence = _approved_evidence(job_id); plan_path = evidence["job_root"] / "commerce" / "printify" / "product-draft-plan.json"
    placement = calculate_placement(tuple(evidence["production"].get("canvas_dimensions") or (4500, 5400)), placeholder,
                                    requested_scale=requested_scale)
    plan = {"job_id": job_id, "approved_candidate_sha256": evidence["candidate_sha"],
            "final_approval_sha256": evidence["approval_sha"], "printify_image_id": upload["printify_image_id"],
            "shop_id": shop_id, "blueprint_id": blueprint_id, "print_provider_id": provider_id,
            "enabled_variant_ids": sorted(set(enabled_variant_ids)), "disabled_variant_ids": [],
            "title": title, "description": description, "tags": ["heart", "abstract", "unisex tee"],
            "retail_prices_cents": {str(k): v for k, v in prices.items()}, "print_placement": "front",
            "decoration_method": "dtg", **placement, "requested_colors": ["Black", "Dark Heather", "White"],
            "requested_sizes": ["S", "M", "L", "XL", "2XL", "3XL"], "creation_status": "planned",
            "publish_status": "not_published", "order_status": "not_created", "human_confirmation_status": "not_confirmed"}
    if plan_path.exists():
        existing = json.loads(plan_path.read_text(encoding="utf-8"))
        if existing != plan: raise job_queue.JobQueueError("An immutable Printify draft plan already exists and differs.")
        return {**existing, "plan_sha256": _hash(plan_path), "idempotent": True}
    _write_immutable(plan_path, plan)
    return {**plan, "plan_sha256": _hash(plan_path), "idempotent": False}


def create_product_draft(job_id: str, *, confirmed: bool, client: PrintifyClient) -> dict[str, Any]:
    if not confirmed: raise job_queue.JobQueueError("Printify product draft creation requires explicit confirmation.")
    evidence = _approved_evidence(job_id); root = evidence["job_root"] / "commerce" / "printify"
    plan_path, record_path = root / "product-draft-plan.json", root / "product-draft.json"
    if not plan_path.is_file(): raise job_queue.JobQueueError("Immutable Printify draft plan is missing.")
    plan = json.loads(plan_path.read_text(encoding="utf-8")); plan_sha = _hash(plan_path)
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("product_draft_plan_sha256") != plan_sha: raise job_queue.JobQueueError("Existing product draft is bound to a different plan.")
        return {**record, "product": client.get_product(plan["shop_id"], record["printify_product_id"]), "idempotent": True}
    variants = [{"id": item, "price": int(plan["retail_prices_cents"][str(item)]), "is_enabled": True} for item in plan["enabled_variant_ids"]]
    payload = {"title": plan["title"], "description": plan["description"], "tags": plan["tags"],
               "blueprint_id": plan["blueprint_id"], "print_provider_id": plan["print_provider_id"], "variants": variants,
               "print_areas": [{"variant_ids": plan["enabled_variant_ids"], "placeholders": [{"position": "front",
                   "decoration_method": plan["decoration_method"], "images": [{"id": plan["printify_image_id"],
                   "x": plan["x"], "y": plan["y"], "scale": plan["scale"], "angle": plan["angle"]}]}]}]}
    product = client.create_product(plan["shop_id"], payload)
    if not product.get("id") or product.get("blueprint_id") != plan["blueprint_id"] or product.get("print_provider_id") != plan["print_provider_id"]:
        raise job_queue.JobQueueError("Printify product response does not match the immutable plan.")
    if product.get("shop_id") not in (None, plan["shop_id"]) or product.get("is_locked") is True:
        raise job_queue.JobQueueError("Printify returned an unexpected shop or locked product.")
    returned_variants = {item.get("id") for item in product.get("variants") or [] if item.get("is_enabled")}
    if returned_variants != set(plan["enabled_variant_ids"]):
        raise job_queue.JobQueueError("Printify enabled variants do not match the immutable plan.")
    returned_images = [image for area in product.get("print_areas") or [] for placeholder in area.get("placeholders") or []
                       for image in placeholder.get("images") or []]
    if plan["printify_image_id"] not in {item.get("id") for item in returned_images}:
        raise job_queue.JobQueueError("Printify product does not contain the approved uploaded image.")
    record = {"job_id": job_id, "product_draft_plan_sha256": plan_sha, "candidate_sha256": evidence["candidate_sha"],
              "printify_image_id": plan["printify_image_id"], "shop_id": plan["shop_id"], "blueprint_id": plan["blueprint_id"],
              "print_provider_id": plan["print_provider_id"], "enabled_variant_ids": plan["enabled_variant_ids"],
              "placement": {key: plan[key] for key in ("x", "y", "scale", "angle")}, "printify_product_id": product["id"],
              "response_sha256": _json_hash(product), "created_at": product.get("created_at") or datetime.now().astimezone().isoformat(),
              "product_response": product, "publish_status": "not_published",
              "mockup_images": product.get("images") or [], "idempotent": False}
    _write_immutable(record_path, record)
    job_queue.update_job_payload(job_id, {"printify_status": "product_draft_created", "provider_status": "draft_created",
        "final_print_ready": False, "product_status": "draft", "publish_status": "not_published",
        "order_status": "not_created", "sample_status": "not_ordered"})
    return {**record, "product": product}


def download_mockups(job_id: str, *, client: PrintifyClient, limit: int = 4) -> list[dict[str, Any]]:
    evidence = _approved_evidence(job_id); root = evidence["job_root"] / "commerce" / "printify"
    record = json.loads((root / "product-draft.json").read_text(encoding="utf-8"))
    product = client.get_product(record["shop_id"], record["printify_product_id"])
    retained = []
    for index, item in enumerate((product.get("images") or [])[:limit]):
        url = str(item.get("src") or "")
        if not url.startswith("https://"): continue
        response = client.session.get(url, timeout=client.timeout); response.raise_for_status()
        path = root / "mockups" / f"mockup-{index + 1}.jpg"; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(response.content)
        retained.append({"source_url": url, "local_path": str(path), "sha256": _hash(path),
                         "variant_ids": item.get("variant_ids") or [], "position": item.get("position"),
                         "is_default": item.get("is_default", False)})
    manifest = root / "mockups.json"
    if not manifest.exists(): _write_immutable(manifest, {"mockups": retained})
    return retained
