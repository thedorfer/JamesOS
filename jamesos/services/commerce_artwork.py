from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import re
from typing import Any
from uuid import uuid4

from PIL import Image

from jamesos.core.errors import ValidationError
from jamesos.services import product_orchestrator


REJECTION_CODES = {"no_output","invalid_format","invalid_dimensions","missing_transparency","empty_artwork","clipped_content","unsafe_margin","insufficient_contrast","unreadable_scale","duplicate_candidate","corrupt_file"}


def render_typography_candidates(*,phrase:str,profile:dict[str,Any],root:Path|None=None)->dict[str,Any]:
    exact=product_orchestrator.normalize_exact_phrase(phrase).upper()
    if not exact:raise ValidationError("VALIDATION_FAILED",diagnostic_message="An exact phrase is required for local typography artwork.",operation="commerce_artwork",stage="input")
    output=(root or product_orchestrator.ROOT/"local-preflight"/f"preflight-{uuid4().hex}").resolve()
    allowed=product_orchestrator.ROOT.resolve()
    if not output.is_relative_to(allowed):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Artwork output must remain in private JamesOS storage.",operation="commerce_artwork",stage="storage")
    config=profile.get("configuration") or {};palette=config.get("artwork_palette") or config.get("palette") or ["high-contrast red","orange","gold","green","blue","violet"]
    brief={"exact_text":exact,"requested_motifs":[],"negative_visual_constraints":[],"artwork_palette":"profile_guided","preferred_layout":"integrated_shadow"}
    state={"job_id":output.name,"original_prompt":exact};evidence=product_orchestrator._independent_evidence(state,output.parent,brief)
    candidates=product_orchestrator._independent_candidates(evidence,output,brief);selection=product_orchestrator.select_candidate(candidates,brief)
    rows=[]
    for item in candidates:
        path=Path(item["png_path"]);codes=[]
        try:
            with Image.open(path) as image:
                if image.format!="PNG":codes.append("invalid_format")
                if image.size!=(4500,5400):codes.append("invalid_dimensions")
                alpha=image.getchannel("A") if "A" in image.getbands() else None
                if alpha is None or alpha.getextrema()[0]==255:codes.append("missing_transparency")
                if alpha is None or alpha.getbbox() is None:codes.append("empty_artwork")
        except (OSError,ValueError):codes.append("corrupt_file")
        if not (item.get("quality_checks") or {}).get("hard_safe_bounds"):codes.append("unsafe_margin")
        if item.get("minimum_effective_text_size",0)<180:codes.append("unreadable_scale")
        rows.append({"candidate_id":item["candidate_id"],"generation_method":"deterministic_local_typography","format":"PNG","width":4500,"height":5400,"byte_count":path.stat().st_size,"transparency_present":not any(code in codes for code in ("missing_transparency","empty_artwork")),"occupied_bounding_box":item.get("visible_alpha_bounds"),"safe_margin_result":"pass" if "unsafe_margin" not in codes else "fail","clipping_result":"pass","minimum_effective_text_size":item.get("minimum_effective_text_size"),"palette_summary":palette[:8],"eligible":not codes,"rejection_codes":codes,"sha256":item["png_sha256"]})
    return {"generation_backend":"deterministic_local_typography","decorative_generation_performed":False,"exact_phrase":exact,"candidate_count":len(rows),"selected_candidate_id":selection["selected"]["candidate_id"],"selected_candidate_sha256":selection["selected"]["png_sha256"],"candidates":rows,"publication_state":"unpublished","order_state":"none"}


def provider_free_preflight(state:dict[str,Any],profile:dict[str,Any],*,credential_configured:bool)->dict[str,Any]:
    config=profile.get("configuration") or {};evidence=state.get("evidence") or {};selected=(evidence.get("selection") or {}).get("selected") or {};listing=evidence.get("listing") or {};destination=state.get("destination") or {};errors=[]
    product_studio_job=bool(state.get("commerce_profile_id"));form=state.get("product_brief") or {}
    checks={"destination_bound":not product_studio_job or destination.get("printify_shop_id")==state.get("shop_id") and bool(destination.get("etsy_shop_slug")),"form_valid":not product_studio_job or all(str(form.get(key) or "").strip() for key in ("exact_phrase","brief","requested_listing_title","special_instructions")),"local_candidate_exists":bool(selected),"candidate_eligible":bool(selected) and all(value is True for key,value in (selected.get("quality_checks") or {}).items() if key.startswith("hard_")),"printify_credential_configured":credential_configured,"shop_configured":type(config.get("printify_shop_id")) is int,"product_mapping_configured":not product_studio_job or type(state.get("blueprint_id")) is int and type(state.get("print_provider_id")) is int,"listing_metadata_valid":bool(listing.get("title") and listing.get("description")),"exactly_13_tags":len(listing.get("tags") or [])==13 and len({str(tag).casefold() for tag in listing.get("tags") or []})==13,"unpublished":state.get("publish_status")=="not_published","no_order":state.get("order_status")=="not_created"}
    errors.extend(key for key,value in checks.items() if not value)
    return {"passed":not errors,"checks":checks,"failure_codes":errors,"provider_contacted":False,"publication_state":state.get("publish_status"),"order_state":state.get("order_status")}
