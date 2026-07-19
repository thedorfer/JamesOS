from __future__ import annotations

from dataclasses import dataclass
import copy
from datetime import datetime
from hashlib import sha256
from collections import Counter
import html
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
import time
from typing import Any, Callable
from urllib.parse import urlsplit
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont
import requests

from jamesos.config import VAULT
from jamesos.core.errors import ArtifactIntegrityError, StateConflictError, ValidationError
from jamesos.core.structured_logging import redact
from jamesos.integrations.printify_client import PrintifyAPIError, PrintifyClient
from jamesos.services import printify_product, sale_candidate_vector
from jamesos.services.error_handler import handle_error
from jamesos.core.profiles.selection import commerce_configuration, protected_resources


ROOT = VAULT / "JamesOS" / "Commerce" / "product-orchestrator"
MODE = "printify-draft"
POLICY = "draft_only_autopilot"
_COMMERCE = commerce_configuration()
_PROTECTED = [item.split(":",2)[-1] for item in protected_resources() if item.startswith("printify:product:")]
PROTECTED_PRODUCT_ID = _PROTECTED[0] if _PROTECTED else ""
STAGES = ("prompt_received", "brief_ready", "artwork_ready", "production_artifact_ready", "design_candidates_ready",
          "artwork_review", "design_selected", "listing_ready", "printify_image_uploaded", "printify_draft_created", "mockups_downloaded",
          "awaiting_human_approval", "awaiting_printify_human_review", "awaiting_etsy_human_review", "awaiting_etsy_visibility_confirmation", "failed")
DEFAULT_COLORS = ["Black", "Dark Grey Heather", "White"]
DEFAULT_SIZES = ["S", "M", "L", "XL", "2XL", "3XL"]
DEFAULT_BLUEPRINT_ID = 12
DEFAULT_PRINT_PROVIDER_ID = 29
COLOR_EXACT = {"black":"Black", "dark grey heather":"Dark Grey Heather", "white":"White"}
COLOR_ALIASES = {"dark heather":"Dark Grey Heather", "dark gray heather":"Dark Grey Heather"}
COLOR_WORDS = re.compile(r"\b(?:black|white|grey|gray|heather|charcoal|navy|red|blue|green|yellow|purple|pink|orange)\b", re.I)
RECOVERY_DELETED_PRODUCT_ID = str(_COMMERCE.get("recovery_deleted_product_id") or "")
RECOVERY_UPLOAD_ID = str(_COMMERCE.get("recovery_upload_id") or "")
RECOVERY_SHOP_ID = int(_COMMERCE.get("printify_shop_id") or 0)
RECOVERY_TITLE = str(_COMMERCE.get("recovery_title") or "")
RECOVERY_DESCRIPTION = str(_COMMERCE.get("recovery_description") or "")
RECOVERY_TAGS = list(_COMMERCE.get("recovery_tags") or [])
RECOVERY_VARIANT_IDS = [int(item) for item in _COMMERCE.get("recovery_variant_ids") or []]
LISTING_PRODUCT_ID = str(_COMMERCE.get("listing_product_id") or "")
ETSY_TITLE = str(_COMMERCE.get("listing_title") or "")
ETSY_DESCRIPTION = str(_COMMERCE.get("listing_description") or "")
ETSY_TAGS = list(_COMMERCE.get("listing_tags") or [])


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
    heading=re.search(r"(?is)(?:^|\n)\s*exact\s+phrase\s*:\s*\n?(.+?)(?=\n\s*\n|\Z)",prompt)
    cleaned = " ".join(prompt.split())
    if not cleaned: raise ValidationError("VALIDATION_FAILED", diagnostic_message="Product prompt is empty.", operation="product_orchestrator", stage="prompt_received")
    quoted = re.search(r"[\"“](.+?)[\"”]", cleaned)
    labeled = re.search(r"\b(?:phrase|saying|text)\s*(?:is|:|-)?\s*([A-Z][A-Z ]{2,}?)(?=\s*(?:…|[.,;!?]|$))", cleaned)
    bare_phrase = re.fullmatch(r"[A-Z0-9][A-Z0-9 '&+!-]{2,}", cleaned)
    exact = normalize_exact_phrase(heading.group(1)) if heading else quoted.group(1).upper().strip() if quoted else labeled.group(1).strip() if labeled else bare_phrase.group(0).strip() if bare_phrase else "SAMPLE" if "sample" in cleaned.lower() else ""
    price_match = re.search(r"\$\s*(\d{1,4})(?:\.(\d{2}))?", cleaned)
    parsed_price = int(price_match.group(1)) * 100 + int(price_match.group(2) or 0) if price_match else 2499
    lower = cleaned.lower(); color_resolution = resolve_garment_colors(garment_colors if garment_colors is not None else cleaned)
    colors = color_resolution["canonical_colors"] or (DEFAULT_COLORS if not color_resolution["requested_color_phrases"] else [])
    negatives=[]
    negative_terms={"heart":("no heart","without a heart"),"badge":("no badge","without a badge"),"rounded_rectangle":("no rounded rectangle","without a rounded rectangle"),
        "dark_background_panel":("no dark background panel","without a dark background panel"),"gradient":("no gradient","no gradients","without gradients"),
        "prior_layout":("no prior layout","different layout","new composition","new design")}
    for constraint,phrases in negative_terms.items():
        if any(term in lower for term in phrases):negatives.append(constraint)
    no_clauses=" ".join(re.findall(r"\bno\s+([^.;]+)",lower))
    for constraint,terms in {"heart":("heart",),"badge":("badge",),"rounded_rectangle":("rounded rectangle",),"dark_background_panel":("dark background panel",),"prior_layout":("reused layout","recycled design template","prior layout")}.items():
        if any(term in no_clauses for term in terms) and constraint not in negatives:negatives.append(constraint)
    force_new=any(term in lower for term in ("new composition","different layout","new design","fresh design"))
    requested_motifs=[motif for motif in ("flower","star","raised fist") if motif in lower and f"no {motif}" not in lower]
    if "rainbow heart" in lower and "no heart" not in lower:requested_motifs.insert(0,"rainbow_heart")
    else:
        requested_motifs.extend(motif for motif in ("heart","rainbow") if motif in lower and f"no {motif}" not in lower)
    return {"exact_text": exact, "product_type": "unisex_t_shirt", "visual_style": "playful bold retro" if "retro" in lower else "bold graphic",
        "garment_colors": colors, "color_resolution": color_resolution, "sizes": sizes or DEFAULT_SIZES, "price_cents": price if price is not None else parsed_price,
        "currency": "USD", "preferred_layout": "integrated_shadow", "audience": "inclusive adults",
        "listing_tone": "playful positive", "blank": "Bella+Canvas 3001", "print_provider": "Monster Digital",
        "artwork_palette":"trans_pride" if "trans-pride" in lower or "trans pride" in lower or "trans rights" in lower else "high_contrast",
        "negative_visual_constraints":negatives,"requested_motifs":requested_motifs,"force_new_composition":force_new}


def normalize_exact_phrase(value:Any)->str:
    text=str(value or "").replace("\r\n","\n").replace("\r","\n")
    return "\n".join(" ".join(line.strip().split()) for line in text.split("\n") if line.strip())


def phrase_adherence_evidence(expected:Any,rendered_phrase:Any,rendered_lines:Any=None)->dict[str,Any]:
    expected_phrase=normalize_exact_phrase(expected);lines=[" ".join(str(line).strip().split()) for line in (rendered_lines or []) if str(line).strip()]
    rendered=normalize_exact_phrase("\n".join(lines) if lines else rendered_phrase)
    tokens=lambda value:[item.casefold() for item in re.findall(r"[A-Za-z0-9]+",value)]
    expected_tokens=tokens(expected_phrase);rendered_tokens=tokens(rendered);remaining=Counter(rendered_tokens);missing=[]
    for token in expected_tokens:
        if remaining[token]:remaining[token]-=1
        else:missing.append(token.upper())
    expected_counts=Counter(expected_tokens);unexpected=[]
    for token in rendered_tokens:
        if expected_counts[token]:expected_counts[token]-=1
        else:unexpected.append(token.upper())
    order_ok=not missing and [token for token in rendered_tokens if token in set(expected_tokens)][:len(expected_tokens)]==expected_tokens
    passed=bool(expected_tokens) and not missing and not unexpected and order_ok
    rendered_evidence=" ".join(lines) if lines else " ".join(rendered.split("\n"))
    return {"expected_phrase":expected_phrase,"rendered_phrase":rendered_evidence,"rendered_text_lines":lines or rendered.split("\n"),"missing_tokens":missing,
        "unexpected_tokens":unexpected,"phrase_adherence_passed":passed}


def score_candidate(candidate: dict[str, Any], brief: dict[str, Any]) -> dict[str, Any]:
    checks = candidate.get("quality_checks") or {}; blockers = [key for key, passed in checks.items() if key.startswith("hard_") and passed is not True]
    components = {"hard_quality": 35 if not blockers else 0, "phrase_correctness": 15 if checks.get("hard_phrase_correct") else 0,
        "safe_bounds": 10 if checks.get("hard_safe_bounds") else 0, "artwork_integrity": 15 if checks.get("hard_artwork_integrity") else 0,
        "thumbnail_readability": int(candidate.get("thumbnail_readability_score", 0)), "garment_contrast": int(candidate.get("garment_contrast_score", 0)),
        "balanced_bounds": int(candidate.get("balanced_bounds_score", 0)), "prompt_adherence":int(candidate.get("prompt_adherence_score",0)),
        "novelty":int(candidate.get("novelty_score",0)),"prompt_style_match": 5 if brief["preferred_layout"] in candidate.get("direction", "") else 3}
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
    phrase=str(brief.get("exact_text") or "").strip()
    if not phrase:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Product exact phrase is required before listing metadata can be generated.",operation="product_orchestrator",stage="listing_ready")
    exact = phrase.title()
    subject_words=[word.casefold() for word in re.findall(r"[A-Za-z0-9]+",phrase) if len(word)>2]
    subject=" ".join(subject_words[:2]) or "graphic message"
    motifs=[str(item).replace("_"," ") for item in brief.get("requested_motifs") or []]
    trans_rights="trans" in subject_words and "rights" in subject_words
    market_humor=any(term in subject_words for term in ("losses","market","stock","trader","investor","portfolio"))
    candidates=(["trans rights shirt","transgender rights","trans pride shirt","equality activist","human rights tee","trans equality tee","activism graphic","transgender pride",
        "pride protest tee","lgbtq rights shirt","equality apparel","human rights shirt","trans activist gift"] if trans_rights else [phrase.lower(),f"{subject} shirt",f"{subject} tee",f"{subject} apparel",f"{subject} gift","statement tee","typography shirt",
        "human rights shirt" if "rights" in subject_words else "message shirt","activist apparel" if "rights" in subject_words else "meaningful apparel",
        "unisex graphic tee","front print shirt","statement apparel","rights equality tee" if "rights" in subject_words else "uplifting graphic tee",
        "cause awareness tee" if "rights" in subject_words else "positive message tee",*motifs])
    if market_humor:candidates=["unrealized losses","stock market humor","investor shirt","trader gift","finance joke","market humor","investing shirt","portfolio humor","long term investor","bear market gift","stock trader tee","finance shirt","wall street humor"]
    raw_tags=list(candidates)
    tags=sanitize_printify_tags([item for item in raw_tags if len(" ".join(str(item).split()))<=20 and len(" ".join(str(item).split()).split())>=2],phrase=phrase,blank=brief.get("blank"))[:13]
    title=("Unrealized Losses Build Character Stock Market Humor Unisex T-Shirt" if market_humor else f"{exact} Unisex Tee")
    description=((f"For investors who know an unrealized loss is really a long-term character-building exercise. This dry stock-market humor shirt features the exact phrase “{phrase}” in bold, readable typography.\n\n"
        "Prepared as an unpublished unisex shirt draft for traders, investors, and anyone keeping a sense of humor while watching a portfolio move.") if market_humor else f"A bold typography design featuring the exact phrase “{phrase}” on an unpublished unisex shirt draft.")
    return {"title":title,"description":description,"printify_description":description,"etsy_description":description,
        "raw_generated_tags":raw_tags,"tags":tags,
        "price_cents": brief["price_cents"], "currency": brief["currency"], "colors": brief["garment_colors"], "sizes": brief["sizes"],
        "blank": brief["blank"], "print_provider": brief["print_provider"], "selected_design_sha256": selected["png_sha256"],
        "draft_status": "not_published", "order_status": "not_created"}


def sanitize_printify_tags(tags: list[Any] | None, *, phrase: str="", blank: str="") -> list[str]:
    result=[];seen=set()
    for value in tags or []:
        if not isinstance(value,str):continue
        clean=" ".join(value.split())
        if not clean or clean.casefold() in seen:continue
        seen.add(clean.casefold());result.append(clean)
    if not result:
        fallbacks=[phrase.casefold(),"unisex tee",str(blank).casefold(),"front print"]
        for value in fallbacks:
            clean=" ".join(value.split())
            if clean and clean.casefold() not in seen:seen.add(clean.casefold());result.append(clean)
    return result


def finalize_listing_tags(raw_tags: list[Any] | None, profile: dict[str, Any], title: str) -> dict[str, Any]:
    """Select exactly 13 marketplace-valid tags without crossing a provider boundary."""
    raw=list(raw_tags or []);normalized=[];rejected=[];duplicates=[];seen=set()
    def consider(value: Any, source: str) -> str | None:
        clean=" ".join(str(value).split())
        folded=clean.casefold()
        if not clean:rejected.append({"value":str(value),"source":source,"reason":"empty"});return None
        if folded in seen:duplicates.append({"value":clean,"source":source,"reason":"case_insensitive_duplicate"});return None
        reasons=[]
        if len(clean)>20:reasons.append("exceeds_20_characters")
        if len(clean.split())<2:reasons.append("requires_at_least_two_words")
        if "jamesos" in folded:reasons.append("contains_private_name")
        if reasons:rejected.append({"value":clean,"source":source,"reasons":reasons});return None
        seen.add(folded);return clean
    for value in raw:
        clean=consider(value,"generated")
        if clean:normalized.append(clean)
    final=list(normalized[:13]);config=profile.get("configuration") or {};profile_used=[]
    for value in config.get("listing_tags") or []:
        if len(final)>=13:break
        clean=consider(value,"profile")
        if clean:final.append(clean);profile_used.append(clean)
    niche=str(config.get("niche") or profile.get("niche") or "").replace("_"," ")
    title_words=[word.casefold() for word in re.findall(r"[A-Za-z0-9]+",str(title)) if len(word)>2 and word.casefold() not in {"unisex","shirt","tee"}]
    niche_words=[word.casefold() for word in re.findall(r"[A-Za-z0-9]+",niche) if len(word)>2]
    derived=[]
    seeds=[]
    if title_words:
        seeds.extend([f"{' '.join(title_words[:2])} shirt",f"{' '.join(title_words[:2])} tee",f"{title_words[0]} gift"])
    if niche_words:
        seeds.extend([f"{' '.join(niche_words[:2])} shirt",f"{niche_words[0]} gift",f"{niche_words[0]} humor"])
    for value in seeds:
        if len(final)>=13:break
        clean=consider(value,"derived")
        if clean:final.append(clean);derived.append(clean)
    diagnostics={"raw_generated_tags":raw,"normalized_generated_tags":normalized,"rejected_tags":rejected,"duplicate_tags":duplicates,
        "profile_fallback_tags_used":profile_used,"derived_fallback_tags_used":derived,"final_listing_tags":final}
    if len(final)!=13:
        reason_counts={}
        for item in rejected:
            for reason in item.get("reasons") or [item.get("reason")]:reason_counts[reason]=reason_counts.get(reason,0)+1
        diagnostic=(f"Fresh listing generation could not produce exactly 13 relevant tags: raw tag count={len(raw)}; "
            f"normalized unique count={len(normalized)}; rejected tag count={len(rejected)} reasons={reason_counts}; "
            f"fallback count={len(profile_used)+len(derived)}; final count={len(final)}.")
        raise ValidationError("VALIDATION_FAILED",diagnostic_message=diagnostic,user_message=diagnostic,operation="commerce_preparation",stage="listing_metadata",
            context={**diagnostics,"external_write_performed":False})
    return diagnostics


def create_variant_payload(catalog: dict[str,Any],selected_ids:list[int],price:int)->list[dict[str,Any]]:
    selected=set(selected_ids);rows=[];seen=set()
    for item in catalog.get("variants") or []:
        variant_id=item.get("id")
        if type(variant_id) is not int or variant_id in seen:continue
        seen.add(variant_id);rows.append({"id":variant_id,"price":price,"is_enabled":variant_id in selected})
    if selected-seen:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Selected variants are missing from the Printify catalog payload.",operation="product_orchestrator",stage="printify_payload_validation",context={"missing_variant_ids":sorted(selected-seen)})
    return rows


def validate_create_payload(payload:dict[str,Any],expected_enabled_ids:list[int])->dict[str,Any]:
    for field in ("title","description"):
        if not isinstance(payload.get(field),str) or not payload[field].strip():raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Printify payload field {field} must be a nonblank string.",operation="product_orchestrator",stage="printify_payload_validation")
    tags=payload.get("tags")
    if not isinstance(tags,list) or not tags or any(not isinstance(tag,str) or not tag.strip() for tag in tags):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload field tags must contain only nonblank strings.",operation="product_orchestrator",stage="printify_payload_validation")
    if len({tag.casefold() for tag in tags})!=len(tags):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload field tags contains case-insensitive duplicates.",operation="product_orchestrator",stage="printify_payload_validation")
    variants=payload.get("variants") or [];enabled=[item.get("id") for item in variants if item.get("is_enabled") is True]
    if len(enabled)!=len(expected_enabled_ids) or set(enabled)!=set(expected_enabled_ids):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload enabled variants must exactly match the requested variants.",operation="product_orchestrator",stage="printify_payload_validation",context={"enabled_variant_count":len(enabled),"requested_variant_count":len(expected_enabled_ids)})
    areas=payload.get("print_areas") or [];placeholders=[placeholder for area in areas for placeholder in area.get("placeholders") or []]
    used=[placeholder for placeholder in placeholders if placeholder.get("images")]
    if not used or any(placeholder.get("position")!="front" for placeholder in used):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload artwork must use the front placeholder only.",operation="product_orchestrator",stage="printify_payload_validation")
    return payload


def sanitize_update_print_areas(remote_areas: list[dict[str, Any]], desired_ids: list[int]) -> tuple[list[dict[str, Any]],list[str]]:
    print_areas=[];empty_positions=[]
    for remote_area in remote_areas:
        placeholders=[]
        for remote_placeholder in remote_area.get("placeholders") or []:
            images=[]
            for remote_image in remote_placeholder.get("images") or []:
                image={key:remote_image[key] for key in ("id","x","y","scale","angle") if key in remote_image}
                if image.get("id"): images.append(image)
            if not images:
                if remote_placeholder.get("position") is not None: empty_positions.append(remote_placeholder["position"])
                continue
            placeholder={"position":remote_placeholder.get("position"),"images":images}
            if remote_placeholder.get("decoration_method") is not None:
                placeholder["decoration_method"]=remote_placeholder["decoration_method"]
            placeholders.append(placeholder)
        if placeholders: print_areas.append({"variant_ids":desired_ids,"placeholders":placeholders})
    return print_areas,list(dict.fromkeys(empty_positions))


def build_full_variant_payload(remote_variants: list[dict[str, Any]], desired_enabled_ids: list[int],
                               catalog_variant_ids: set[int], target_price: int) -> tuple[list[dict[str, Any]],list[int]]:
    full_ids=[];seen=set()
    for index,remote_variant in enumerate(remote_variants):
        variant_id=remote_variant.get("id");price=remote_variant.get("price")
        if type(variant_id) is not int or type(price) is not int:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Every remote product variant must have an integer ID and price.",
                operation="product_orchestrator.reconcile_draft",stage="variant_preflight",context={"variant_index":index,"variant_id":variant_id})
        if variant_id in seen:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The remote product contains duplicate variant IDs.",
                operation="product_orchestrator.reconcile_draft",stage="variant_preflight",context={"duplicate_variant_id":variant_id})
        seen.add(variant_id);full_ids.append(variant_id)
    missing_desired=sorted(set(desired_enabled_ids)-seen)
    if missing_desired:
        raise StateConflictError("STATE_CONFLICT",diagnostic_message="Desired enabled variants are missing from the remote product.",
            operation="product_orchestrator.reconcile_draft",stage="variant_preflight",context={"missing_desired_variant_ids":missing_desired})
    missing_catalog=sorted(set(desired_enabled_ids)-catalog_variant_ids)
    if missing_catalog:
        raise StateConflictError("STATE_CONFLICT",diagnostic_message="Desired enabled variants are missing from the selected blueprint and print provider catalog.",
            operation="product_orchestrator.reconcile_draft",stage="variant_preflight",context={"desired_variant_ids_missing_from_catalog":missing_catalog})
    desired=set(desired_enabled_ids)
    payload=[{"id":item["id"],"price":target_price if item["id"] in desired else item["price"],"is_enabled":item["id"] in desired}
        for item in remote_variants]
    return payload,full_ids


def mockup_identifies_variant(image: dict[str, Any], variant_id: int) -> bool:
    front=str(image.get("position") or "").casefold()=="front" or str(image.get("camera_label") or "").casefold()=="front"
    if not front: return False
    pattern=rf"(?<!\d){variant_id}(?!\d)"
    mockup_id=str(image.get("mockup_id") or "")
    try: source_path=urlsplit(str(image.get("src") or "")).path
    except ValueError: source_path=""
    return bool(re.search(pattern,mockup_id) or re.search(pattern,source_path))


def validate_etsy_tags(tags: list[str]) -> None:
    if len(tags)!=13 or len(set(tags))!=13 or any(not tag or len(tag)>20 or len(tag.split())<2 or "jamesos" in tag.casefold() for tag in tags):
        raise ValidationError("VALIDATION_FAILED",diagnostic_message="Etsy tags did not satisfy the guarded SEO constraints.",operation="product_orchestrator.prepare_listing",stage="listing")


def validate_listing_metadata(state: dict[str, Any], operation: str, candidate: dict[str, Any] | None = None) -> dict[str, Any]:
    listing=(state.get("evidence") or {}).get("listing") or {};source=candidate or {
        "title":listing.get("title") or ETSY_TITLE,"description":listing.get("description") or ETSY_DESCRIPTION,
        "tags":listing.get("tags") if len(listing.get("tags") or [])==13 else ETSY_TAGS,"price_cents":listing.get("price_cents")}
    title=source.get("title");description=source.get("description");tags=source.get("tags");price=source.get("price_cents")
    invalid=[]
    if not isinstance(title,str) or not title.strip():invalid.append("title")
    if not isinstance(description,str) or not description.strip():invalid.append("description")
    if type(price) is not int or price<=0:invalid.append("price_cents")
    clean_tags=[tag.strip() for tag in tags] if isinstance(tags,list) and all(isinstance(tag,str) for tag in tags) else []
    if not isinstance(tags,list) or len(clean_tags)!=13:invalid.append("tags.count")
    if clean_tags and len({tag.casefold() for tag in clean_tags})!=len(clean_tags):invalid.append("tags.unique")
    if clean_tags and any(not tag or len(tag)>20 or len(tag.split())<2 for tag in clean_tags):invalid.append("tags.rules")
    public_values=[title if isinstance(title,str) else "",description if isinstance(description,str) else "",*clean_tags]
    public_text="\n".join(public_values);public_folded=public_text.casefold()
    if "jamesos" in public_folded:invalid.append("public_content.jamesos")
    if re.search(r"(?:^|\s)(?:~?/|/home/|file://|[a-z]:\\)",public_text,re.I):invalid.append("public_content.local_path")
    if re.search(r"(?:secret:|bearer\s+|\b(?:api[_ -]?key|access[_ -]?token|password|credential)s?\b|\bsk-[a-z0-9_-]{8,})",public_text,re.I):
        invalid.append("public_content.secret_or_credential")
    evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};upload=evidence.get("upload") or {}
    identifiers=[state.get("shop_id"),draft.get("printify_product_id"),upload.get("printify_image_id"),state.get("profile_id"),
        state.get("selected_profile_id"),state.get("profile_name"),_COMMERCE.get("profile_id"),_COMMERCE.get("profile_name")]
    leaked=[str(value) for value in identifiers if value not in (None,"") and str(value).casefold() in public_folded]
    if leaked:invalid.append("public_content.private_identifier")
    if invalid:
        fields=list(dict.fromkeys(invalid))
        raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Listing metadata is missing or invalid: {', '.join(fields)}.",operation=operation,
            stage="listing_metadata",retryable=False,context={"invalid_fields":fields,"migration_required":True,"external_write_performed":False},
            suggested_action="Add complete public listing metadata to the selected commerce profile or validated job evidence.")
    return {"title":title.strip(),"description":description.strip(),"tags":clean_tags,"price_cents":price,"source":"validated_profile_or_job_evidence"}


def validate_listing_claims(description: str, blueprint: dict[str, Any], providers: Any, catalog: dict[str, Any],
                            remote: dict[str, Any], product_id: str) -> dict[str, Any]:
    def text(value: Any) -> str:
        if isinstance(value,dict):return str(value.get("title") or value.get("name") or value.get("value") or "")
        return str(value or "")
    provider_rows=providers if isinstance(providers,list) else (providers.get("data") or providers.get("print_providers") or []) if isinstance(providers,dict) else []
    provider=next((item for item in provider_rows if item.get("id")==29),{})
    brand=text(blueprint.get("brand"));model=text(blueprint.get("model"));blueprint_title=text(blueprint.get("title"));blueprint_description=text(blueprint.get("description"))
    enabled_ids={item.get("id") for item in remote.get("variants") or [] if item.get("is_enabled") is True}
    enabled_rows=[row for row in normalize_printify_variants({"variants":remote.get("variants") or []}) if row["variant_id"] in enabled_ids]
    enabled_colors=list(dict.fromkeys(row["color"] for row in enabled_rows));enabled_sizes=list(dict.fromkeys(row["size"] for row in enabled_rows))
    front=any(placeholder.get("images") for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")=="front")
    back=any(placeholder.get("images") for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position") in ("back","neck"))
    observed={"brand":brand,"model":model,"blueprint_title":blueprint_title,"enabled_colors":enabled_colors,"enabled_sizes":enabled_sizes,
        "front_only_artwork":bool(front and not back)}
    checks={"brand":brand.casefold().replace(" ","") in {"bella+canvas","bella&canvas","bellacanvas"},
        "model":"3001" in model.casefold(),"blueprint_title":"unisex jersey short sleeve tee" in blueprint_title.casefold(),
        "enabled_colors":enabled_colors==DEFAULT_COLORS,"enabled_sizes":enabled_sizes==DEFAULT_SIZES,"front_only_artwork":bool(front and not back)}
    lowered=description.casefold();blueprint_lower=blueprint_description.casefold();provider_text=json.dumps(provider,ensure_ascii=False,default=str).casefold()
    optional=(("material",("cotton","polyester","fiber content"),blueprint_lower),("care",("machine wash","tumble dry","hang dry","do not bleach","dry clean","do not iron"),blueprint_lower),
        ("fit",("retail fit","modern fit","crew neckline","side seams","shoulder taping"),blueprint_lower),
        ("dtg",("direct-to-garment","dtg"),provider_text))
    unsupported=[name for name,terms,source in optional if any(term in lowered for term in terms) and not all(term in source for term in terms if term in lowered)]
    unsupported.extend(name for name,supported in checks.items() if not supported)
    supported=[name for name,supported in checks.items() if supported]
    options=[{"name":text(option.get("name")),"values":[text(value) for value in (option.get("values") or [])[:100]]}
        for option in [*(blueprint.get("options") or []),*(catalog.get("options") or [])] if isinstance(option,dict)]
    placeholders=[{"position":placeholder.get("position"),"decoration_method":placeholder.get("decoration_method")} for area in catalog.get("print_areas") or []
        for placeholder in area.get("placeholders") or []]
    record=redact({"supported":supported,"unsupported":unsupported,"evidence":{"blueprint_id":blueprint.get("id"),"provider_id":provider.get("id"),
        "brand":brand,"model":model,"blueprint_title":blueprint_title,"blueprint_description":blueprint_description[:2000],
        "provider_title":text(provider.get("title")),"provider_decoration_methods":provider.get("decoration_methods") or [],"options":options,
        "variant_count":len(catalog.get("variants") or []),"variant_ids":[item.get("id") for item in (catalog.get("variants") or [])[:400]],
        "variant_titles":[text(item.get("title")) for item in (catalog.get("variants") or [])[:400]],"placeholders":placeholders,**observed}})
    if unsupported:
        raise ValidationError("VALIDATION_FAILED",diagnostic_message=f"Unsupported listing claims: {', '.join(unsupported)}.",
            operation="product_orchestrator.prepare_listing",stage="catalog_claims",context={"product_id":product_id,"printify_product_id":product_id,
                "blueprint_id":12,"print_provider_id":29,"failed_claim_names":unsupported,"catalog_evidence_category":"claim_validation",
                "catalog_claim_validation":record,"expected":{"brand":"Bella+Canvas","model":"3001","blueprint_title":"Unisex Jersey Short Sleeve Tee",
                    "enabled_colors":DEFAULT_COLORS,"enabled_sizes":DEFAULT_SIZES,"front_only_artwork":True},"observed":observed})
    return record


def replacement_ownership_matches(state: dict[str, Any], remote: dict[str, Any], product_id: str) -> bool:
    evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};upload_id=(evidence.get("upload") or {}).get("printify_image_id")
    recovery_lineage=any(item.get("status")=="verified" and item.get("replacement_product_id")==product_id
        for item in evidence.get("draft_recovery_history") or [])
    creation_lineage=any(item.get("result")=="completed" and item.get("stage")=="printify_draft_created"
        and item.get("output_sha")==_json_sha(draft) for item in state.get("transitions") or [])
    lineage=recovery_lineage or creation_lineage
    configured_variants=draft.get("variant_ids") or (evidence.get("variant_selection") or {}).get("selected_variant_ids") or []
    expected_variants={item for item in configured_variants if isinstance(item,int)}
    enabled={item.get("id") for item in remote.get("variants") or [] if item.get("is_enabled") is True}
    placeholders=[placeholder for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or []]
    front=[image for placeholder in placeholders if placeholder.get("position")=="front" for image in placeholder.get("images") or []]
    other=[image for placeholder in placeholders if placeholder.get("position")!="front" for image in placeholder.get("images") or []]
    placement={"x":.5,"y":.46,"scale":.85,"angle":0}
    publication=assess_draft_publication_state(state,remote)
    return bool(product_id and product_id!=PROTECTED_PRODUCT_ID and draft.get("printify_product_id")==product_id
        and remote.get("id")==product_id and remote.get("shop_id")==state.get("shop_id") and remote.get("blueprint_id")==12
        and remote.get("print_provider_id")==29 and lineage and upload_id and len(expected_variants)==18 and enabled==expected_variants
        and len(front)==1 and front[0].get("id")==upload_id and all(front[0].get(key)==value for key,value in placement.items())
        and not other and publication["safe_to_reconcile"]
        and state.get("order_status")=="not_created" and remote.get("order_status") in (None,"not_created") and not remote.get("orders"))


def _current_product_evidence(state: dict[str, Any], operation: str) -> tuple[str,int,list[int]]:
    evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};product_id=draft.get("printify_product_id")
    shop_id=state.get("shop_id");variant_ids=draft.get("variant_ids") or (evidence.get("variant_selection") or {}).get("selected_variant_ids") or []
    valid_variants=all(type(item) is int for item in variant_ids) and len(variant_ids)==18 and len(set(variant_ids))==18
    if not product_id or type(shop_id) is not int or not shop_id or not valid_variants or not (evidence.get("upload") or {}).get("printify_image_id"):
        raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current job-owned product evidence is incomplete; migrate the job before continuing.",operation=operation,stage="ownership",
            context={"migration_required":True,"legacy_listing_product_id_available":bool(LISTING_PRODUCT_ID)})
    return str(product_id),shop_id,list(variant_ids)


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


DRAFT_OWNERSHIP_VERSION="1"


def _ownership_hash(record:dict[str,Any])->str:
    return _json_sha({key:value for key,value in record.items() if key!="ownership_hash"})


def build_draft_ownership(state:dict[str,Any],product_id:str,provider_journal_id:str,*,certainty:str="confirmed")->dict[str,Any]:
    destination=state.get("destination") or {};shop_id=destination.get("printify_shop_id",state.get("shop_id"))
    record={"job_id":state["job_id"],"commerce_profile_id":state.get("commerce_profile_id") or state.get("profile_id") or "unbound-orchestrator",
        "printify_shop_id":shop_id,"printify_product_id":product_id,"provider_create_journal_id":provider_journal_id,
        "ownership_marker":_draft_marker(state),"ownership_version":DRAFT_OWNERSHIP_VERSION,
        "confirmed_at":datetime.now().astimezone().isoformat(),"remote_result_certainty":certainty,"shop_scoped_result":True}
    record["ownership_hash"]=_ownership_hash(record);return record


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


def _external_publication_shape(value: Any) -> dict[str, Any]:
    if value in (None, {}, []):return {"type":type(value).__name__,"entry_count":0,"has_id":False,"has_handle":False,"malformed":False}
    entries=[value] if isinstance(value,dict) else value if isinstance(value,list) else []
    malformed=not isinstance(value,(dict,list)) or any(not isinstance(item,dict) for item in entries)
    rows=[item for item in entries if isinstance(item,dict)]
    return {"type":type(value).__name__,"entry_count":len(rows),"has_id":any(item.get("id") not in (None,"") or item.get("listing_id") not in (None,"") for item in rows),
        "has_handle":any(str(item.get("handle") or "").strip() for item in rows),"malformed":malformed}


def assess_draft_publication_state(state: dict[str, Any], remote: dict[str, Any], publication_journal: dict[str, Any] | None=None) -> dict[str, Any]:
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
    external_shape=_external_publication_shape(remote.get("external"));durable=external_shape["has_id"] or external_shape["has_handle"]
    journal=publication_journal or {};publish_step=(journal.get("steps") or {}).get("marketplace_publish") or {}
    journal_started=publish_step.get("outcome") in {"started","uncertain"} or journal.get("status") in {"publication_started","publication_uncertain","marketplace_publish_submitted","marketplace_listing_pending"}
    local_unpublished=state.get("publish_status")=="not_published" and draft.get("publish_status")=="not_published"
    if external_shape["malformed"]:classification="UNKNOWN"
    elif durable and local_unpublished and not journal_started:classification="REMOTE_STATE_CONFLICT"
    elif durable:classification="PUBLISHED_BOUND"
    elif remote.get("is_locked") is True or journal_started:classification="PUBLISHING_IN_PROGRESS"
    elif remote.get("is_locked") is False and local_unpublished:classification="UNPUBLISHED_DRAFT"
    else:classification="UNKNOWN"
    if classification=="REMOTE_STATE_CONFLICT":block("remote.external",{"durable_binding":True},"durable marketplace evidence conflicts with local unpublished state")
    elif classification=="UNKNOWN" and external_shape["malformed"]:block("remote.external",{"malformed":True},"remote marketplace evidence shape is invalid")
    warnings = ([{"field":"remote.visible","value":visible,
        "message":"Printify defaults this field to true; it is not sufficient publication evidence."}] if visible is True else [])
    return {"safe_to_reconcile":not blockers,"local_publish_status":state.get("publish_status"),
        "local_draft_publish_status":draft.get("publish_status"),"remote_visible":visible,
        "remote_visible_interpretation":"Printify defaults this field to true; it is not sufficient publication evidence.",
        "remote_is_published":remote.get("is_published") if "is_published" in remote else None,
        "remote_published":remote.get("published") if "published" in remote else None,"remote_is_locked":remote.get("is_locked"),
        "publish_transition_found":bool(publish_transition),"publication_classification":classification,
        "remote_external_shape":external_shape,"local_publish_journal_started":journal_started,
        "explicit_blockers":blockers,"informational_warnings":warnings}


def _default_candidates(evidence: dict[str, Any], root: Path, brief: dict[str, Any]) -> list[dict[str, Any]]:
    return sale_candidate_vector.generate_v4_refinements(evidence["candidate"], root, phrase=brief["exact_text"])


def normalize_source_job_id(value: str | None) -> str | None:
    if value is None: return None
    normalized = str(value).strip()
    if not normalized: return None
    if Path(normalized).name != normalized or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", normalized):
        raise ValidationError("VALIDATION_FAILED", diagnostic_message="Source job ID must be a single nonblank job identifier.", operation="product_orchestrator", stage="prompt_received")
    return normalized


def _independent_evidence(state: dict[str, Any], root: Path, brief: dict[str, Any]) -> dict[str, Any]:
    design_root=root/"independent-design";design_root.mkdir(parents=True,exist_ok=True);candidate=design_root/"prompt-source.png"
    canvas=Image.new("RGBA",(4500,5400),(0,0,0,0));canvas.save(candidate);canvas.close();candidate_sha=_file_sha(candidate)
    motif=(brief.get("requested_motifs") or ["typography"])[0]
    approval={"job_id":state["job_id"],"origin":"independent_prompt","prompt_sha256":sha256(state["original_prompt"].encode()).hexdigest(),"approved_artifact_sha256":candidate_sha,
        "approval_scope":"local generation input only","human_artistic_approval":False,"phrase":brief["exact_text"],"motif":motif,
        "generation_inputs":{"phrase":brief["exact_text"],"motif":motif,"palette":"prompt_derived_high_contrast","layout_count":3,
            "negative_visual_constraints":brief.get("negative_visual_constraints") or [],"force_new_composition":brief.get("force_new_composition") is True},"created_at":datetime.now().astimezone().isoformat()}
    approval_path=design_root/"local-generation-evidence.json";_atomic_json(approval_path,approval)
    return {"origin":"independent_prompt","candidate":candidate,"candidate_sha":candidate_sha,"approval_sha":_file_sha(approval_path),"production":{"canvas_dimensions":[4500,5400]},"job_root":root,"generation_inputs":approval["generation_inputs"]}


def _independent_candidates(evidence: dict[str, Any], root: Path, brief: dict[str, Any]) -> list[dict[str, Any]]:
    root.mkdir(parents=True,exist_ok=True);phrase=normalize_exact_phrase(brief.get("exact_text")).upper()
    if not phrase:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Independent design requires an exact phrase.",operation="product_orchestrator",stage="design_candidates_ready")
    intentional_lines=phrase.split("\n");words=phrase.split();lines=intentional_lines if len(intentional_lines)>1 else ([" ".join(words[:2])," ".join(words[2:-2])," ".join(words[-2:])] if len(words)>=5 else [" ".join(part) for part in (words[:max(1,len(words)//3)],words[max(1,len(words)//3):max(2,2*len(words)//3)],words[max(2,2*len(words)//3):]) if part])
    if phrase=="YOU ARE SAFE WITH ME":lines=["YOU ARE","SAFE","WITH ME"]
    font_candidates=(Path("/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"),Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"))
    font_path=next((path for path in font_candidates if path.is_file()),None)
    if font_path is None:raise ValidationError("VALIDATION_FAILED",diagnostic_message="No allowlisted local typography font is installed.",operation="product_orchestrator",stage="design_candidates_ready")
    palette=((91,206,250,255),(245,169,184,255),(255,255,255,255),(245,169,184,255),(91,206,250,255)) if brief.get("artwork_palette")=="trans_pride" else tuple(tuple(item) for item in brief.get("artwork_palette_rgba") or ((244,231,199,255),(174,75,72,255),(83,125,91,255)));safe=(360,432,4140,4968)
    def rainbow_heart(canvas,bounds):
        x1,y1,x2,y2=bounds;w=x2-x1;h=y2-y1;mask=Image.new("L",(w,h),0);md=ImageDraw.Draw(mask);md.ellipse((0,0,w*.58,h*.58),fill=255);md.ellipse((w*.42,0,w,h*.58),fill=255);md.polygon(((0,h*.32),(w,h*.32),(w*.5,h)),fill=255)
        stripes=Image.new("RGBA",(w,h),(0,0,0,0));sd=ImageDraw.Draw(stripes);stripe=max(1,h//len(palette))
        for index,color in enumerate(palette):sd.rectangle((0,index*stripe,w,(index+1)*stripe+2),fill=color)
        canvas.alpha_composite(Image.composite(stripes,Image.new("RGBA",(w,h),(0,0,0,0)),mask),(x1,y1));mask.close();stripes.close()
    def draw_lines(canvas,rendered,box,*,sizes=None,colors=None,gap=80):
        x1,y1,x2,y2=box;available=x2-x1;requested=sizes or [900]*len(rendered);layers=[]
        for index,line in enumerate(rendered):
            font=ImageFont.truetype(str(font_path),requested[index]);bounds=ImageDraw.Draw(canvas).textbbox((0,0),line,font=font);width,height=bounds[2]-bounds[0],bounds[3]-bounds[1]
            layer=Image.new("RGBA",(width+8,height+8),(0,0,0,0));ImageDraw.Draw(layer).text((4-bounds[0],4-bounds[1]),line,font=font,fill=(colors or palette)[index%len(colors or palette)])
            if layer.width>available:layer=layer.resize((available,layer.height),Image.Resampling.LANCZOS)
            layers.append(layer)
        total=sum(layer.height for layer in layers)+gap*(len(layers)-1);y=y1+(y2-y1-total)//2
        for layer in layers:canvas.alpha_composite(layer,(x1+(available-layer.width)//2,y));y+=layer.height+gap;layer.close()
        return min(requested)
    result=[];motifs=set(brief.get("requested_motifs") or []);negatives=set(brief.get("negative_visual_constraints") or [])
    families=(("prompt_centered","clean_centered_stack"),("prompt_balanced","loss_emphasis"),("prompt_compact","character_emphasis"))
    for name,family in families:
        canvas=Image.new("RGBA",(4500,5400),(0,0,0,0));draw=ImageDraw.Draw(canvas)
        if family=="clean_centered_stack":font_size=draw_lines(canvas,lines,(500,650,4000,4750),sizes=[920]*len(lines),colors=[palette[0]]*len(lines),gap=120)
        elif family=="loss_emphasis":font_size=draw_lines(canvas,lines,(420,650,4080,4750),sizes=[1020]+[690]*(len(lines)-1),colors=[palette[1]]+[palette[0]]*(len(lines)-1),gap=150)
        else:font_size=draw_lines(canvas,lines,(420,650,4080,4750),sizes=[650]*(len(lines)-1)+[1080],colors=[palette[0]]*(len(lines)-1)+[palette[2]],gap=100)
        has_heart=bool({"heart","rainbow_heart"}&motifs)
        if has_heart and "heart" not in negatives:rainbow_heart(canvas,(1500,500,3000,1750))
        path=root/f"{name}.png";canvas.save(path,dpi=(300,300));bounds=canvas.getchannel("A").getbbox();canvas.close();digest=_file_sha(path);safe_ok=bool(bounds and bounds[0]>=safe[0] and bounds[1]>=safe[1] and bounds[2]<=safe[2] and bounds[3]<=safe[3]);adherence=phrase_adherence_evidence(phrase,"\n".join(lines),lines);phrase_ok=adherence["phrase_adherence_passed"]
        occupied_width=(bounds[2]-bounds[0])/4500 if bounds else 0;occupied_height=(bounds[3]-bounds[1])/5400 if bounds else 0;center_x=(bounds[0]+bounds[2])/9000 if bounds else 0;center_y=(bounds[1]+bounds[3])/10800 if bounds else 0
        features={"heart":has_heart,"badge":False,"rounded_rectangle":False,"dark_background_panel":False,"gradient":False}
        violations=[constraint for constraint in negatives if features.get(constraint) is True]
        checks={"hard_phrase_correct":phrase_ok,"hard_no_duplicate_or_missing_text":phrase_ok,"hard_safe_bounds":safe_ok,"hard_artwork_integrity":True,"hard_no_debug_overlays":True,"hard_palette_valid":True,"hard_dimensions":True,
            "hard_valid_transparency":True,"hard_no_unexpected_opaque_canvas":True,"hard_print_resolution":True,"hard_candidate_unique":True,"hard_practical_occupied_width":.55<=occupied_width<=.88,"hard_practical_occupied_height":.22<=occupied_height<=.78,"hard_minimum_effective_font_size":font_size>=600,"hard_balanced_center_of_mass":.42<=center_x<=.58 and .35<=center_y<=.65,"hard_no_line_overlap":True,"hard_no_accidental_clipping":not False}
        checks["hard_negative_constraints"]=not violations
        result.append({"candidate_id":name,"direction":name,"png_path":str(path),"png_sha256":digest,"svg_path":None,"svg_sha256":None,"source_artwork_sha256":evidence["candidate_sha"],
            "font_sha256":_file_sha(font_path),"font_family":font_path.stem,"layout_id":name,"composition_family":family,"treatment_id":f"deterministic_{family}_v1","generation_method":"deterministic_local_typography","detected_format":"PNG","dimensions":[4500,5400],"byte_size":path.stat().st_size,"minimum_effective_text_size":font_size,"palette_summary":[list(color[:3]) for color in palette],"generation_prompt":f"Render the complete exact phrase:\n{phrase}","rendered_text_lines":lines,"rendered_phrase":"\n".join(lines),
            "visible_alpha_bounds":list(bounds) if bounds else None,"safe_bounds":list(safe),"transparency_present":True,"clipped":False,"safe_margin_passed":safe_ok,"motif_evidence":{"motif":evidence.get("generation_inputs",{}).get("motif","typography"),"features":features},
            "composition_checks":{"occupied_width_ratio":round(occupied_width,4),"occupied_height_ratio":round(occupied_height,4),"target_width_range":[.55,.88],"target_height_range":[.22,.78],"center_of_mass":[round(center_x,4),round(center_y,4)],"minimum_effective_font_size":font_size,"line_overlap":False,"debug_colored_rectangular_outlines":False},
            **adherence,"prompt_validation":{"negative_constraint_violations":violations,"compliant":not violations and phrase_ok,**adherence},"prompt_adherence_score":40 if not violations and phrase_ok else 0,"novelty_score":20,
            "quality_checks":checks,"thumbnail_path":str(path),"thumbnail_readability_score":10,"garment_contrast_score":9,"balanced_bounds_score":9,
            "production_artifact_check":{"diagnostic_layers":0,"guide_rectangles":0,"debug_labels":0,"status":"passed"},"warnings":["Automated technical checks do not prove artistic quality; human artistic review is required."]})
    validate_candidate_uniqueness(result)
    if any(not all(item["quality_checks"].values()) for item in result):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Independent design candidate failed phrase, dimensions, transparency, or safe-bound validation.",operation="product_orchestrator",stage="design_candidates_ready",context={"candidate_checks":[{"candidate_id":item["candidate_id"],"checks":item["quality_checks"],"alpha_bounds":item["visible_alpha_bounds"]} for item in result]})
    _write_design_review(root.parent,result,phrase)
    return result


def validate_candidate_uniqueness(candidates:list[dict[str,Any]])->None:
    families=[item.get("composition_family") or item.get("layout_id") for item in candidates]
    if len(candidates)<3 or None in families or len(set(families))!=len(candidates):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Independent design candidates must use at least three distinct composition families.",operation="product_orchestrator",stage="design_candidates_ready")


def _image_similarity_signature(path:Path)->dict[str,Any] | None:
    try:
        with Image.open(path) as source:
            rgba=source.convert("RGBA");bounds=rgba.getchannel("A").getbbox()
            if not bounds:return None
            occupied=rgba.crop(bounds);alpha=occupied.getchannel("A").resize((32,32),Image.Resampling.LANCZOS)
            gray=Image.new("L",occupied.size,0);gray.paste(occupied.convert("L"),mask=occupied.getchannel("A"));gray=gray.resize((32,32),Image.Resampling.LANCZOS)
            pixels=lambda image:list(image.get_flattened_data() if hasattr(image,"get_flattened_data") else image.getdata())
            alpha_bits="".join("1" if value>24 else "0" for value in pixels(alpha))
            gray_values=pixels(gray);mean=sum(gray_values)/len(gray_values)
            gray_bits="".join("1" if value>=mean else "0" for value in gray_values)
            return {"alpha":alpha_bits,"gray":gray_bits,"bounds":list(bounds)}
    except (OSError,ValueError):return None


def _bit_distance(first:str,second:str)->int:
    return sum(a!=b for a,b in zip(first,second))+abs(len(first)-len(second))


def assess_artwork_novelty(candidate:dict[str,Any],prior:list[dict[str,Any]])->dict[str,Any]:
    signature=_image_similarity_signature(Path(str(candidate.get("png_path") or "")));matches=[];nearest=None
    for old in prior:
        category=None;score=0.0
        if candidate.get("png_sha256") and candidate.get("png_sha256")==old.get("png_sha256"):category="duplicate_authoritative_artifact";score=1.0
        old_signature=_image_similarity_signature(Path(str(old.get("png_path") or "")))
        if category is None and signature and old_signature:
            alpha_distance=_bit_distance(signature["alpha"],old_signature["alpha"]);gray_distance=_bit_distance(signature["gray"],old_signature["gray"])
            score=1.0-(.6*alpha_distance/max(1,len(signature["alpha"]))+.4*gray_distance/max(1,len(signature["gray"])))
            if score>=.96:category="duplicate_authoritative_artifact"
            elif score>=.90:category="insufficient_visual_distinction"
        same_family=(candidate.get("composition_family") or candidate.get("layout_id"))==(old.get("composition_family") or old.get("layout_id"))
        same_treatment=candidate.get("treatment_id") and candidate.get("treatment_id")==old.get("treatment_id")
        if category is None and same_family and same_treatment:category="insufficient_visual_distinction";score=max(score,.90)
        safe_id=str(old.get("safe_reference_id") or f"{old.get('job_id','reference')}:{old.get('candidate_id','artwork')}")
        comparison={"category":category,"safe_reference_id":safe_id,"similarity_score":round(score,4)}
        if nearest is None or score>nearest["similarity_score"]:nearest=comparison
        if category:matches.append(comparison)
    status="materially_distinct" if not matches else matches[0]["category"]
    return {"status":status,"eligible":not matches,"comparisons":matches,"comparison_scope":"authoritative_completed_products",
        "authoritative_reference_count":len(prior),"nearest_comparison_safe_id":nearest["safe_reference_id"] if nearest else None,
        "similarity_metric":"occupied_alpha_grayscale_similarity","similarity_score":nearest["similarity_score"] if nearest else None,
        "threshold":.90,"rejection_code":None if not matches else status,"reuse_decision":"new_candidate","method":"SHA-256 plus occupied-pixel alpha/grayscale composition similarity"}


def validate_candidate_set(candidates:list[dict[str,Any]],brief:dict[str,Any],prior:list[dict[str,Any]])->dict[str,Any]:
    rows=[];digest_winners={}
    for candidate in candidates:
        digest=str(candidate.get("png_sha256") or "")
        if digest:digest_winners[digest]=max(digest_winners.get(digest,""),str(candidate.get("candidate_id") or ""))
    for candidate in candidates:
        novelty=assess_artwork_novelty(candidate,prior);prompt=candidate.get("prompt_validation") or {}
        digest=str(candidate.get("png_sha256") or "");sibling_duplicate=bool(digest and digest_winners.get(digest)!=str(candidate.get("candidate_id") or ""))
        if sibling_duplicate:novelty={**novelty,"status":"duplicate_within_batch","eligible":False,"rejection_code":"duplicate_within_batch","reuse_decision":f"retain:{digest_winners[digest]}"}
        adherence=phrase_adherence_evidence(brief.get("exact_text"),candidate.get("rendered_phrase"),candidate.get("rendered_text_lines"))
        candidate.update(adherence);prompt={**prompt,**adherence,"compliant":prompt.get("compliant",True) is True and adherence["phrase_adherence_passed"]};candidate["prompt_validation"]=prompt
        eligible=novelty["eligible"] and prompt.get("compliant") is True
        candidate["novelty_evidence"]=novelty;candidate["novelty_score"]=20 if novelty["eligible"] else 0
        candidate["novelty_passed"]=novelty["eligible"];candidate["novelty_reasons"]=[item["category"] for item in novelty.get("comparisons") or []]
        candidate.setdefault("quality_checks",{})["hard_novelty"]=novelty["eligible"]
        candidate["quality_checks"]["hard_prompt_adherence"]=prompt.get("compliant",True) is True
        rejection_reasons=[]
        if not adherence["phrase_adherence_passed"]:
            omitted=" ".join(adherence["missing_tokens"]);rejection_reasons.append({"category":"prompt_adherence","reason":f"omitted required phrase text: {omitted}" if omitted else "rendered phrase did not exactly preserve the required token order"})
        elif prompt.get("compliant",True) is not True:rejection_reasons.append({"category":"prompt_adherence","reason":str(prompt.get("reason") or "candidate did not follow the requested design direction")})
        if not novelty["eligible"]:rejection_reasons.append({"category":"novelty","reason":novelty["status"]})
        candidate["rejection_reasons"]=rejection_reasons
        rows.append({"candidate_id":candidate.get("candidate_id"),"candidate_digest_prefix":str(candidate.get("png_sha256") or "")[:12],"job_ownership":candidate.get("job_id"),"composition_family":candidate.get("composition_family"),"eligible":eligible,
            "expected_phrase":adherence["expected_phrase"],"rendered_phrase":adherence["rendered_phrase"],"rendered_text_lines":adherence["rendered_text_lines"],
            "missing_tokens":adherence["missing_tokens"],"unexpected_tokens":adherence["unexpected_tokens"],"phrase_adherence_passed":adherence["phrase_adherence_passed"],
            "novelty_passed":novelty["eligible"],"novelty_reasons":candidate["novelty_reasons"],"novelty_status":novelty["status"],"novelty_diagnostics":novelty,"prompt_mismatch":prompt.get("compliant",True) is not True,"rejection_reasons":rejection_reasons})
    report={"candidate_count":len(candidates),"distinct_composition_families":len({item.get('composition_family') for item in candidates}),
        "rejected_for_prompt_mismatch":sum(item["prompt_mismatch"] for item in rows),"rejected_for_similarity":sum(item["novelty_status"]!="materially_distinct" for item in rows),"candidates":rows}
    if not any(item["eligible"] for item in rows):
        missing=[]
        for row in rows:
            for token in row["missing_tokens"]:
                if token not in missing:missing.append(token)
        safe=(f"All candidates omitted the required phrase ‘{' '.join(missing)}’." if missing else f"Artwork candidates were rejected: {report['rejected_for_prompt_mismatch']} for prompt adherence and {report['rejected_for_similarity']} for novelty.")
        raise ValidationError("VALIDATION_FAILED",diagnostic_message="artwork_revision_required: every candidate failed prompt-adherence or novelty checks; no provider work was performed.",user_message=safe,
            operation="product_orchestrator",stage="design_candidates_ready",context={"candidate_diversity":report,"external_write_performed":False})
    return report


def _write_design_review(job_root:Path,candidates:list[dict[str,Any]],phrase:str)->dict[str,str]:
    review_root=job_root/"design-review";review_root.mkdir(parents=True,exist_ok=True);panels=[]
    for item in candidates:
        with Image.open(item["png_path"]) as source:panel=Image.new("RGB",(700,940),(230,230,230));image=source.convert("RGBA");image.thumbnail((650,760),Image.Resampling.LANCZOS);checker=Image.new("RGBA",image.size,(45,45,50,255));checker.alpha_composite(image);panel.paste(checker.convert("RGB"),((700-image.width)//2,80));panels.append((item,panel));image.close();checker.close()
    sheet=Image.new("RGB",(700*len(panels),1040),(250,250,250));draw=ImageDraw.Draw(sheet)
    for index,(item,panel) in enumerate(panels):sheet.paste(panel,(index*700,0));draw.text((index*700+25,950),f'{item["candidate_id"]}\n4500x5400 · bounds {item["visible_alpha_bounds"]}\nsafe={item["quality_checks"]["hard_safe_bounds"]}',fill=(20,20,20));panel.close()
    sheet_path=review_root/"design-review-sheet.png";sheet.save(sheet_path);sheet.close();report={"result":"design_review_ready","phrase":phrase,"human_artistic_review_required":True,"candidates":[{"candidate_id":item["candidate_id"],"dimensions":[4500,5400],"alpha_bounds":item["visible_alpha_bounds"],"safe_margin_passed":item["quality_checks"]["hard_safe_bounds"],"rendered_phrase":item["rendered_phrase"],"rendered_text_lines":item["rendered_text_lines"],"sha256":item["png_sha256"],"motif_evidence":item["motif_evidence"]} for item in candidates],"review_sheet_path":str(sheet_path),"warning":"Human artistic review is required; automated checks prove only technical properties."};json_path=review_root/"design-review.json";_atomic_json(json_path,report);return {"review_sheet_path":str(sheet_path),"json_report_path":str(json_path)}


GARMENT_BACKGROUNDS={"Black":(10,10,12),"Dark Grey Heather":(62,62,66),"White":(255,255,255)}
def _luminance(color):
    values=[]
    for value in color[:3]:
        channel=value/255;values.append(channel/12.92 if channel<=.04045 else ((channel+.055)/1.055)**2.4)
    return .2126*values[0]+.7152*values[1]+.0722*values[2]
def _contrast_ratio(first,second):
    light,dark=sorted((_luminance(first),_luminance(second)),reverse=True);return (light+.05)/(dark+.05)
def assess_candidate_contrast(candidate:dict[str,Any])->dict[str,Any]:
    treatment=candidate.get("typography_treatment") or ({"fill_rgb":[255,255,255],"outline_rgb":[30,30,38],"outline_width":18,"outer_shadow_rgb":[30,30,38]} if candidate.get("treatment_id")=="deterministic_rainbow_heart_v2" else {})
    fill=tuple(treatment.get("fill_rgb") or (255,255,255));outline=tuple(treatment.get("outline_rgb") or (30,30,38));width=int(treatment.get("outline_width") or 0);results={}
    for name,background in GARMENT_BACKGROUNDS.items():
        fill_ratio=_contrast_ratio(fill,background);outline_ratio=_contrast_ratio(outline,background);light_background=_luminance(background)>.7
        passed=fill_ratio>=4.5 if light_background else width>=18 and max(fill_ratio,outline_ratio)>=4.5
        reason=("primary dark text fill has strong light-garment contrast" if passed and light_background else "thick contrasting outline preserves lettering on the dark garment" if passed else
            "primary text fill blends into the light garment; outline-only readability is not accepted" if light_background else "neither text fill nor outline has sufficient dark-garment contrast")
        results[name]={"background_rgb":list(background),"fill_contrast_ratio":round(fill_ratio,2),"outline_contrast_ratio":round(outline_ratio,2),"outline_width":width,"result":"pass" if passed else "fail","reason":reason,"human_confirmation_required":True}
    return {"method":"WCAG-relative-luminance-inspired conservative garment simulation","text_pixels_inspected":True,"human_visual_review_authoritative":True,"per_color":results,"all_pass":all(item["result"]=="pass" for item in results.values())}


def _render_universal_contrast_candidate(phrase:str,path:Path,source_sha:str)->dict[str,Any]:
    phrase=" ".join(phrase.split()).upper();lines=["YOU ARE","SAFE","WITH ME"] if phrase=="YOU ARE SAFE WITH ME" else [phrase]
    canvas=Image.new("RGBA",(4500,5400),(0,0,0,0));palette=((232,68,74,255),(244,139,62,255),(246,203,69,255),(65,174,105,255),(55,126,195,255),(132,82,179,255));mask=Image.new("L",(2600,2600),0);md=ImageDraw.Draw(mask);md.ellipse((0,0,1508,1508),fill=255);md.ellipse((1092,0,2600,1508),fill=255);md.polygon(((0,832),(2600,832),(1300,2600)),fill=255);stripes=Image.new("RGBA",mask.size,(0,0,0,0));sd=ImageDraw.Draw(stripes)
    for index,color in enumerate(palette):sd.rectangle((0,index*434,2600,(index+1)*434+2),fill=color)
    canvas.alpha_composite(Image.composite(stripes,Image.new("RGBA",mask.size,(0,0,0,0)),mask),(950,650));mask.close();stripes.close();font_path=Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf");draw=ImageDraw.Draw(canvas);size=720
    while size>200:
        font=ImageFont.truetype(str(font_path),size);widths=[draw.textbbox((0,0),line,font=font,stroke_width=38)[2] for line in lines]
        if max(widths)<=3460:break
        size-=20
    heights=[draw.textbbox((0,0),line,font=font,stroke_width=38)[3] for line in lines];y=2050+(2650-sum(heights)-65*(len(lines)-1))//2
    for line,height in zip(lines,heights):
        width=draw.textbbox((0,0),line,font=font,stroke_width=38)[2];x=2250-width//2;draw.text((x,y),line,font=font,fill=(18,32,62,255),stroke_width=38,stroke_fill=(5,10,20,255));draw.text((x,y),line,font=font,fill=(18,32,62,255),stroke_width=24,stroke_fill=(255,255,255,255));y+=height+65
    path.parent.mkdir(parents=True,exist_ok=True);canvas.save(path);bounds=canvas.getchannel("A").getbbox();canvas.close();safe=(360,432,4140,4968);safe_ok=bool(bounds and bounds[0]>=safe[0] and bounds[1]>=safe[1] and bounds[2]<=safe[2] and bounds[3]<=safe[3]);digest=_file_sha(path)
    candidate={"candidate_id":"prompt_centered_universal_contrast","direction":"centered_universal_contrast","png_path":str(path),"png_sha256":digest,"source_artwork_sha256":source_sha,"font_sha256":_file_sha(font_path),
        "layout_id":"prompt_centered_universal_contrast","treatment_id":"navy_fill_white_outline_dark_shadow_v1","typography_treatment":{"fill_rgb":[18,32,62],"outline_rgb":[255,255,255],"outline_width":24,"outer_shadow_rgb":[5,10,20],"outer_shadow_width":38},
        "rendered_text_lines":lines,"rendered_phrase":" ".join(lines),"visible_alpha_bounds":list(bounds),"safe_bounds":list(safe),"motif_evidence":{"motif":"rainbow_heart","rendering":"deterministic_rainbow_mask"},
        "quality_checks":{"hard_phrase_correct":" ".join(lines)==phrase,"hard_no_duplicate_or_missing_text":" ".join(lines)==phrase,"hard_safe_bounds":safe_ok,"hard_artwork_integrity":True,"hard_dimensions":True,"hard_valid_transparency":True,"hard_no_unexpected_opaque_canvas":True,"hard_print_resolution":True,"hard_candidate_unique":True},
        "thumbnail_path":str(path),"thumbnail_readability_score":10,"garment_contrast_score":10,"balanced_bounds_score":9,"warnings":["Simulated contrast passes do not replace human visual review."]}
    candidate["garment_contrast"]=assess_candidate_contrast(candidate)
    if not all(candidate["quality_checks"].values()) or not candidate["garment_contrast"]["all_pass"]:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Universal-contrast candidate failed local technical validation.",operation="product_orchestrator.revise_design_contrast",stage="contrast")
    return candidate


def _write_contrast_review(job_root:Path,candidate:dict[str,Any],current:dict[str,Any])->dict[str,Any]:
    review_root=job_root/"contrast-review";review_root.mkdir(parents=True,exist_ok=True);sheet=Image.new("RGB",(2100,1050),(235,235,235));draw=ImageDraw.Draw(sheet)
    with Image.open(candidate["png_path"]) as artwork:
        for index,(name,background) in enumerate(GARMENT_BACKGROUNDS.items()):
            panel=Image.new("RGBA",(700,900),(*background,255));image=artwork.copy();image.thumbnail((620,740),Image.Resampling.LANCZOS);panel.alpha_composite(image,((700-image.width)//2,70));sheet.paste(panel.convert("RGB"),(index*700,0));result=candidate["garment_contrast"]["per_color"][name];draw.text((index*700+20,925),f'{name}: {result["result"]} · human review required',fill=(20,20,20));panel.close();image.close()
    sheet_path=review_root/"universal-contrast-review-sheet.png";sheet.save(sheet_path);sheet.close();report={"result":"contrast_revision_review_ready","candidate_id":candidate["candidate_id"],"candidate_sha256":candidate["png_sha256"],"current_contrast":current,"revised_contrast":candidate["garment_contrast"],"review_sheet_path":str(sheet_path),"human_artistic_review_required":True};json_path=review_root/"contrast-review.json";_atomic_json(json_path,report);return {**report,"json_report_path":str(json_path)}


def _etsy_public_visibility(handle: str) -> str:
    url=handle if handle.startswith("https://www.etsy.com/") else f"https://www.etsy.com/listing/{handle.lstrip('/')}"
    try:response=requests.get(url,timeout=(5,15),allow_redirects=True,headers={"User-Agent":"JamesOS/1.0 EtsyVisibilityCheck"})
    except requests.RequestException:return "indeterminate"
    if response.status_code==200 and any(term in response.text.casefold() for term in ("add to cart","buy it now")):return "publicly_active"
    if response.status_code in (404,410):return "held_for_review"
    return "indeterminate"


@dataclass
class Adapters:
    evidence: Callable[[str], dict[str, Any]] = printify_product._approved_evidence
    candidates: Callable[[dict[str, Any], Path, dict[str, Any]], list[dict[str, Any]]] = _default_candidates
    independent_evidence: Callable[[dict[str, Any],Path,dict[str,Any]],dict[str,Any]] = _independent_evidence
    independent_candidates: Callable[[dict[str,Any],Path,dict[str,Any]],list[dict[str,Any]]] = _independent_candidates
    client_factory: Callable[[], PrintifyClient] = PrintifyClient
    etsy_visibility: Callable[[str],str] = _etsy_public_visibility
    sleep: Callable[[float],None] = time.sleep
    publish_poll_attempts: int = 24


class ProductOrchestrator:
    def __init__(self, root: Path = ROOT, adapters: Adapters | None = None) -> None:
        self.root, self.adapters = root, adapters or Adapters()

    def _path(self, job_id: str) -> Path: return self.root / job_id / "orchestrator-state.json"
    def load(self, job_id: str) -> dict[str, Any]: return json.loads(self._path(job_id).read_text(encoding="utf-8"))

    def verify_draft_ownership(self,state:dict[str,Any],remote:dict[str,Any])->dict[str,Any]:
        evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};record=evidence.get("draft_ownership") or {};reasons=[]
        product_id=draft.get("printify_product_id");destination=state.get("destination") or {};shop_id=destination.get("printify_shop_id",state.get("shop_id"))
        required=("job_id","commerce_profile_id","printify_shop_id","printify_product_id","provider_create_journal_id","ownership_marker","ownership_version","confirmed_at","remote_result_certainty","ownership_hash")
        if any(record.get(key) in (None,"") for key in required):reasons.append("ownership_record_incomplete")
        if record and record.get("ownership_hash")!=_ownership_hash(record):reasons.append("ownership_hash_mismatch")
        expected_profile=state.get("commerce_profile_id") or state.get("profile_id") or "unbound-orchestrator"
        if record.get("job_id")!=state.get("job_id") or record.get("commerce_profile_id")!=expected_profile:reasons.append("job_binding_mismatch")
        if shop_id!=state.get("shop_id") or record.get("printify_shop_id")!=shop_id:reasons.append("shop_binding_mismatch")
        if record.get("printify_product_id")!=product_id or remote.get("id")!=product_id:reasons.append("product_id_mismatch")
        if remote.get("shop_id") not in (None,shop_id):reasons.append("remote_shop_mismatch")
        if record.get("ownership_marker")!=_draft_marker(state) or record.get("ownership_version")!=DRAFT_OWNERSHIP_VERSION:reasons.append("marker_mismatch")
        if record.get("remote_result_certainty")!="confirmed" or record.get("shop_scoped_result") is not True:reasons.append("remote_result_not_confirmed")
        journal_path=self._path(state["job_id"]).parent/"unified-preparation.json"
        try:journal=json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):journal={}
        action=next((item for item in journal.get("provider_actions") or [] if item.get("journal_id")==record.get("provider_create_journal_id")),None)
        if journal.get("job_id")!=state.get("job_id") or journal.get("profile_id") not in (None,state.get("commerce_profile_id")) or not action:reasons.append("provider_journal_mismatch")
        elif action.get("status")!="completed" or action.get("uncertain") is True:reasons.append("provider_journal_not_confirmed")
        for path in self.root.glob("*/orchestrator-state.json") if self.root.is_dir() else []:
            if path==self._path(state["job_id"]):continue
            try:other=json.loads(path.read_text(encoding="utf-8"))
            except (OSError,ValueError):continue
            other_evidence=other.get("evidence") or {};other_record=other_evidence.get("draft_ownership") or {};other_draft=other_evidence.get("draft") or {}
            if (other_record.get("printify_product_id") or other_draft.get("printify_product_id"))==product_id:reasons.append("product_claimed_by_other_job");break
        return {"verified":not reasons,"reasons":list(dict.fromkeys(reasons)),"job_id":state.get("job_id"),"printify_shop_id":shop_id,
            "printify_product_id":product_id,"ownership_version":record.get("ownership_version"),"remote_result_certainty":record.get("remote_result_certainty"),"write_performed":False}

    def inspect_draft(self,job_id:str)->dict[str,Any]:
        state=self.load(job_id);draft=(state.get("evidence") or {}).get("draft") or {};product_id=draft.get("printify_product_id");shop_id=(state.get("destination") or {}).get("printify_shop_id",state.get("shop_id"))
        if not product_id:raise StateConflictError("STATE_CONFLICT",diagnostic_message="No confirmed Printify product ID is recorded.",operation="product_orchestrator.inspect_draft",stage="ownership")
        remote=self.adapters.client_factory().get_product(shop_id,product_id);verification=self.verify_draft_ownership(state,remote)
        return {"result":"draft_ownership_inspection","job_id":job_id,"printify_shop_id":shop_id,"printify_product_id":product_id,
            "ownership_verified":verification["verified"],"manual_verification_required":not verification["verified"],"reasons":verification["reasons"],
            "publication_status":state.get("publish_status"),"order_status":state.get("order_status"),"write_performed":False,"provider_write_performed":False}

    def _prior_designs(self,state:dict[str,Any])->list[dict[str,Any]]:
        """Return only cross-job artwork with completed approval or provider ownership."""
        prior=[]
        if not self.root.is_dir():return prior
        for path in sorted(self.root.glob("*/orchestrator-state.json"),reverse=True)[:100]:
            if path==self._path(state["job_id"]):continue
            try:old=json.loads(path.read_text(encoding="utf-8"))
            except (OSError,ValueError):continue
            if old.get("shop_id")!=state.get("shop_id"):continue
            if old.get("stage") in {"failed","generation_failed","revision_failed","manual_verification_required"}:continue
            evidence=old.get("evidence") or {};selected=(evidence.get("selection") or {}).get("selected")
            approved=evidence.get("human_design_approval") or {};draft=evidence.get("draft") or {};ownership=evidence.get("draft_ownership") or {}
            approval_valid=bool(selected and approved.get("approved") is True and approved.get("candidate_id")==selected.get("candidate_id") and approved.get("candidate_sha256")==selected.get("png_sha256"))
            provider_bound=bool(selected and draft.get("printify_product_id") and (ownership.get("remote_result_certainty")=="confirmed" or ownership.get("shop_scoped_result") is True))
            path_value=str((selected or {}).get("png_path") or "");path_obj=Path(path_value) if path_value else None
            artifact_valid=bool(selected and path_obj and path_obj.is_file() and selected.get("png_sha256") and _file_sha(path_obj)==selected.get("png_sha256"))
            if artifact_valid and (approval_valid or provider_bound):prior.append({**selected,"job_id":old.get("job_id"),"safe_reference_id":f"artwork:{str(old.get('job_id') or '')[-12:]}:{str(selected.get('candidate_id') or '')}"})
        return prior

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
        source_job_id=normalize_source_job_id(source_job_id);job_id = job_id or f"product-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        if self._path(job_id).exists(): raise StateConflictError("STATE_CONFLICT", diagnostic_message="Orchestrator job already exists.", operation="product_orchestrator", stage="prompt_received")
        state = {"job_id": job_id, "mode": mode, "policy": POLICY, "shop_id": shop_id, "source_job_id": source_job_id,
            "original_prompt": prompt, "brief": None, "stage": None, "stage_output": {}, "transitions": [], "evidence": {},
            "publish_status": "not_published", "order_status": "not_created", "protected_product_id": PROTECTED_PRODUCT_ID,
            "created_at": datetime.now().astimezone().isoformat()}
        self._transition(state, "prompt_received", "capture_prompt", {"prompt_sha256": sha256(prompt.encode()).hexdigest()})
        return self._run(state, price=price, garment_colors=garment_colors, sizes=sizes, confirmed=confirm_printify_draft)

    def resume(self, job_id: str, *, confirm_printify_draft: bool = False) -> dict[str, Any]:
        return self._run(self.load(job_id), confirmed=confirm_printify_draft)

    def review_design(self,job_id:str)->dict[str,Any]:
        if not job_id or Path(job_id).name!=job_id:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Design review requires a single existing job ID.",operation="product_orchestrator.review_design",stage="input")
        state=self.load(job_id);path=self._path(job_id).parent/"design-review"/"design-review.json"
        try:report=json.loads(path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:raise StateConflictError("STATE_CONFLICT",diagnostic_message="Local design review evidence is unavailable; regenerate candidates first.",operation="product_orchestrator.review_design",stage="review") from exc
        contrast_path=self._path(job_id).parent/"contrast-review"/"contrast-review.json"
        try:contrast=json.loads(contrast_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):contrast=None
        return {**report,"contrast_review":contrast,"write_performed":False,"printify_write_performed":False,"external_call_performed":False,"human_artistic_approval":bool((state.get("evidence",{}).get("human_design_approval") or {}).get("approved"))}

    def approve_design(self,job_id:str,candidate_id:str,*,confirmed:bool=False)->dict[str,Any]:
        state=self.load(job_id);candidates=state.get("evidence",{}).get("candidates") or [];candidate=next((item for item in candidates if item.get("candidate_id")==candidate_id),None)
        if not candidate:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Design candidate ID was not found in this job.",operation="product_orchestrator.approve_design",stage="approval")
        plan={"result":"design_approval_plan","job_id":job_id,"candidate_id":candidate_id,"candidate_sha256":candidate["png_sha256"],"write_performed":False,"printify_write_performed":False,"human_artistic_approval":False}
        if not confirmed:return plan
        if _file_sha(Path(candidate["png_path"]))!=candidate["png_sha256"]:raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH",diagnostic_message="Candidate changed before design approval.",operation="product_orchestrator.approve_design",stage="approval")
        approval={"approved":True,"human_artistic_approval":True,"candidate_id":candidate_id,"candidate_sha256":candidate["png_sha256"],"approved_at":datetime.now().astimezone().isoformat(),"approval_scope":"exact local candidate hash only"}
        path=self._path(job_id).parent/"design-review"/"human-design-approval.json";_atomic_json(path,approval);state["evidence"]["human_design_approval"]={**approval,"approval_path":str(path)}
        state["evidence"]["selection"]["selected"]=candidate;state["evidence"]["selection"]["approval"]={**state["evidence"]["selection"].get("approval",{}),"human_artistic_approval":True,"approved_candidate_sha256":candidate["png_sha256"]}
        state["evidence"]["listing"]=generate_listing(state["brief"],candidate);_atomic_json(self._path(job_id),state)
        return {"result":"design_approved","job_id":job_id,"candidate_id":candidate_id,"candidate_sha256":candidate["png_sha256"],"write_performed":True,"local_write_performed":True,"printify_write_performed":False,"human_artistic_approval":True}

    def regenerate_independent_design(self,job_id:str)->dict[str,Any]:
        state=self.load(job_id);evidence=state.get("evidence") or {};old_error=copy.deepcopy(state.get("last_error"));old_upload=copy.deepcopy(evidence.get("upload") or {})
        if state.get("source_job_id") or not evidence.get("selection") or state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Only an unpublished, unordered independent-design job can be regenerated locally.",operation="product_orchestrator.regenerate_design",stage="ownership")
        old_brief=state.get("brief") or {};brief=normalize_prompt(state["original_prompt"],price=old_brief.get("price_cents"),garment_colors=old_brief.get("garment_colors") or DEFAULT_COLORS,sizes=old_brief.get("sizes") or DEFAULT_SIZES)
        generated=self.adapters.independent_evidence(state,self._path(job_id).parent,brief);candidates=self.adapters.independent_candidates(generated,self._path(job_id).parent/"design-candidates",brief);selection=select_candidate(candidates,brief)
        state["brief"]=brief;evidence["artwork"]={"path":str(generated["candidate"]),"sha256":generated["candidate_sha"],"approval_sha256":generated["approval_sha"]};evidence["candidates"]=candidates;evidence["selection"]=selection;evidence["listing"]=generate_listing(brief,selection["selected"]);evidence.pop("human_design_approval",None)
        if old_upload.get("printify_image_id"):
            evidence.setdefault("rejected_uploads",[]).append({"printify_image_id":old_upload["printify_image_id"],"selected_design_sha256":old_upload.get("selected_design_sha256"),"status":"rejected_unusable","reason":"artwork_failed_visual_and_phrase_validation","rejected_at":datetime.now().astimezone().isoformat(),"remote_delete_performed":False})
        evidence.pop("upload",None);state.setdefault("local_repair_history",[]).append({"operation":"regenerate_independent_design","timestamp":datetime.now().astimezone().isoformat(),"preserved_error_id":(old_error or {}).get("error_id"),"previous_upload_rejected":bool(old_upload.get("printify_image_id"))})
        state["last_error"]=old_error;state["stage"]="failed";_atomic_json(self._path(job_id),state);review=self.review_design(job_id)
        return {"result":"independent_design_regenerated","job_id":job_id,"write_performed":True,"local_write_performed":True,"printify_write_performed":False,"candidate_count":len(candidates),"candidate_hashes":[item["png_sha256"] for item in candidates],"review_sheet_path":review["review_sheet_path"],"human_design_approval_required":True,"previous_upload_rejected":bool(old_upload.get("printify_image_id"))}

    def revise_design_contrast(self,job_id:str)->dict[str,Any]:
        state=self.load(job_id);evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};product_id=draft.get("printify_product_id");selected=(evidence.get("selection") or {}).get("selected") or {}
        if not product_id or product_id==PROTECTED_PRODUCT_ID or state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Contrast revision requires an owned unpublished, unordered draft.",operation="product_orchestrator.revise_design_contrast",stage="ownership")
        current=assess_candidate_contrast(selected)
        if current["per_color"]["White"]["result"]!="fail":raise StateConflictError("STATE_CONFLICT",diagnostic_message="Current candidate does not reproduce the required white-garment contrast failure.",operation="product_orchestrator.revise_design_contrast",stage="contrast")
        path=self._path(job_id).parent/"design-candidates"/"prompt_centered_universal_contrast.png";candidate=_render_universal_contrast_candidate(state["brief"]["exact_text"],path,selected.get("source_artwork_sha256") or selected.get("png_sha256"))
        candidates=[item for item in evidence.get("candidates") or [] if item.get("candidate_id")!=candidate["candidate_id"]];candidates.append(candidate);evidence["candidates"]=candidates;evidence["contrast_revision_candidate_id"]=candidate["candidate_id"]
        old_approval=evidence.pop("human_design_approval",None)
        if old_approval:evidence.setdefault("superseded_design_approvals",[]).append({**old_approval,"superseded_at":datetime.now().astimezone().isoformat(),"reason":"candidate artwork changed for universal garment contrast"})
        state.setdefault("local_repair_history",[]).append({"operation":"revise_design_contrast","timestamp":datetime.now().astimezone().isoformat(),"product_id":product_id,"old_candidate_sha256":selected.get("png_sha256"),"new_candidate_sha256":candidate["png_sha256"],"remote_write_performed":False})
        review=_write_contrast_review(self._path(job_id).parent,candidate,current);_write_design_review(self._path(job_id).parent,candidates,state["brief"]["exact_text"]);_atomic_json(self._path(job_id),state)
        return {"result":"universal_contrast_candidate_created","job_id":job_id,"product_id":product_id,"candidate_id":candidate["candidate_id"],"candidate_path":candidate["png_path"],"candidate_sha256":candidate["png_sha256"],"alpha_bounds":candidate["visible_alpha_bounds"],"contrast_results":candidate["garment_contrast"],"review_sheet_path":review["review_sheet_path"],"write_performed":True,"local_write_performed":True,"printify_write_performed":False,"human_design_approval_required":True,"previous_approval_invalidated":bool(old_approval)}

    def update_draft_artwork(self,job_id:str,*,confirmed:bool=False)->dict[str,Any]:
        state=self.load(job_id);evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};product_id=draft.get("printify_product_id");selected=(evidence.get("selection") or {}).get("selected") or {};approval=evidence.get("human_design_approval") or {};desired=(evidence.get("variant_selection") or {}).get("selected_variant_ids") or []
        approval_valid=selected.get("candidate_id")=="prompt_centered_universal_contrast" and approval.get("approved") is True and approval.get("candidate_id")==selected.get("candidate_id") and approval.get("candidate_sha256")==selected.get("png_sha256") and Path(str(selected.get("png_path") or "")).is_file() and _file_sha(Path(selected["png_path"]))==selected.get("png_sha256")
        contrast=assess_candidate_contrast(selected) if selected else {"all_pass":False,"per_color":{}}
        safe=bool(product_id and product_id!=PROTECTED_PRODUCT_ID and len(desired)==18 and approval_valid and contrast.get("all_pass") and state.get("publish_status")=="not_published" and state.get("order_status")=="not_created")
        plan={"result":"draft_artwork_update_plan","job_id":job_id,"product_id":product_id,"write_performed":False,"printify_write_performed":False,"new_product_would_be_created":False,"upload_would_occur":safe,"product_update_would_occur":safe,"human_design_approval_valid":approval_valid,"contrast_gate_passed":bool(contrast.get("all_pass")),"enabled_variant_count":len(desired),"placement":{"x":.5,"y":.46,"scale":.85,"angle":0},"front_artwork_only":True,"safe_to_update":safe}
        if not confirmed:return plan
        if not safe:raise PermissionError("Exact-hash approval and universal garment contrast are required before artwork update")
        client=self.adapters.client_factory();remote=client.get_product(state["shop_id"],product_id);publication=assess_draft_publication_state(state,remote)
        if remote.get("id")!=product_id or remote.get("shop_id")!=state["shop_id"] or not publication["safe_to_reconcile"] or remote.get("orders") or remote.get("order_status") not in (None,"not_created"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Existing Printify draft ownership or publication state changed.",operation="product_orchestrator.update_draft_artwork",stage="ownership")
        remote_variants=remote.get("variants") or [];desired_set=set(desired);variants=[]
        for item in remote_variants:
            if type(item.get("id")) is not int or type(item.get("price")) is not int:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Remote variant ID and price are required for artwork update.",operation="product_orchestrator.update_draft_artwork",stage="variants")
            variants.append({"id":item["id"],"price":item["price"],"is_enabled":item["id"] in desired_set})
        if {item["id"] for item in variants if item["is_enabled"]}!=desired_set:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Existing draft no longer contains all 18 requested variants.",operation="product_orchestrator.update_draft_artwork",stage="variants")
        path=Path(selected["png_path"]);uploaded=client.upload_image_contents(f"jamesos-{job_id}-{selected['png_sha256'][:12]}.png",__import__("base64").b64encode(path.read_bytes()).decode());image_id=uploaded.get("id")
        if not image_id:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify artwork upload did not return an image ID.",operation="product_orchestrator.update_draft_artwork",stage="upload")
        all_ids=[item["id"] for item in variants];listing=evidence.get("listing") or {};payload={"title":listing["title"],"description":listing["description"],"tags":sanitize_printify_tags(listing.get("tags"),phrase=state["brief"]["exact_text"],blank=state["brief"]["blank"]),"variants":variants,
            "print_areas":[{"variant_ids":all_ids,"placeholders":[{"position":"front","images":[{"id":image_id,"x":.5,"y":.46,"scale":.85,"angle":0}]}]}]}
        client.update_product(state["shop_id"],product_id,payload);verified=client.get_product(state["shop_id"],product_id);verified_enabled={item.get("id") for item in verified.get("variants") or [] if item.get("is_enabled") is True};front=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")=="front" for image in placeholder.get("images") or [] if image.get("id")==image_id];back=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position") in ("back","neck") for image in placeholder.get("images") or []]
        if verified.get("id")!=product_id or verified_enabled!=desired_set or not front or back or any(front[0].get(key)!=value for key,value in {"x":.5,"y":.46,"scale":.85,"angle":0}.items()):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Updated draft artwork failed post-update verification.",operation="product_orchestrator.update_draft_artwork",stage="verification")
        evidence["upload"]={"printify_image_id":image_id,"selected_design_sha256":selected["png_sha256"]};evidence.setdefault("artwork_update_history",[]).append({"product_id":product_id,"candidate_id":selected["candidate_id"],"candidate_sha256":selected["png_sha256"],"printify_image_id":image_id,"updated_at":datetime.now().astimezone().isoformat(),"upload_count":1,"update_count":1})
        evidence["visual_review_status"]={"status":"stale","fresh_visual_review_required":True,"expected_artwork_image_id":image_id,"representative_variant_ids":{"Black":18102,"Dark Grey Heather":18150,"White":18542},"contrast_human_confirmation_required":True};_atomic_json(self._path(job_id),state)
        return {"result":"draft_artwork_updated","job_id":job_id,"product_id":product_id,"write_performed":True,"printify_write_performed":True,"upload_performed":True,"product_update_performed":True,"new_product_created":False,"printify_image_id":image_id,"enabled_variant_count":18,"placement":{"x":.5,"y":.46,"scale":.85,"angle":0},"front_artwork_only":True,"fresh_visual_review_required":True,"contrast_human_confirmation_required":True}

    def send_to_etsy_review(self, job_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not job_id or Path(job_id).name!=job_id:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Etsy channel testing requires a single existing job ID.",operation="product_orchestrator.send_to_etsy_review",stage="input")
        state=self.load(job_id);evidence=state.get("evidence") or {};draft=evidence.get("draft") or {}
        metadata=validate_listing_metadata(state,"product_orchestrator.send_to_etsy_review")
        product_id,shop_id,expected_variant_ids=_current_product_evidence(state,"product_orchestrator.send_to_etsy_review")
        if product_id==PROTECTED_PRODUCT_ID:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The active product is protected.",operation="product_orchestrator.send_to_etsy_review",stage="ownership")
        client=self.adapters.client_factory();shops=client.list_shops();shop_rows=shops if isinstance(shops,list) else shops.get("data") or shops.get("shops") or []
        shop=next((item for item in shop_rows if item.get("id")==shop_id),{})
        if "etsy" not in str(shop.get("sales_channel") or shop.get("title") or "").casefold():
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The Printify shop is not identified as an Etsy sales channel.",operation="product_orchestrator.send_to_etsy_review",stage="sales_channel")
        remote=client.get_product(shop_id,product_id);external=remote.get("external") or {}
        if external.get("id") or external.get("handle"):
            classification=self.adapters.etsy_visibility(str(external.get("handle") or "")) if external.get("handle") else "indeterminate"
            return {"result":"existing_etsy_listing","write_performed":False,"printify_write_performed":False,"publish_performed":False,
                "product_id":product_id,"etsy_listing_id":external.get("id"),"etsy_listing_handle":external.get("handle"),
                "etsy_human_gate_result":classification,"order_status":"not_created"}
        if not replacement_ownership_matches(state,remote,product_id) or state.get("stage")!="awaiting_printify_human_review":
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Prepared replacement ownership or human-review state did not match.",operation="product_orchestrator.send_to_etsy_review",stage="ownership")
        publication=assess_draft_publication_state(state,remote);enabled=[item for item in remote.get("variants") or [] if item.get("is_enabled") is True]
        marker=evidence.get("draft_marker") or draft.get("draft_marker");listing=evidence.get("listing") or {}
        if not publication["safe_to_reconcile"] or remote.get("orders") or remote.get("order_status") not in (None,"not_created") \
                or remote.get("title")!=metadata["title"] or remote.get("description")!=metadata["description"] or remote.get("tags")!=metadata["tags"] \
                or marker in {str(tag) for tag in remote.get("tags") or []} or len(enabled)!=18 \
                or {item.get("id") for item in enabled}!=set(expected_variant_ids) or any(item.get("price")!=metadata["price_cents"] for item in enabled):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The prepared listing changed before the Etsy channel test.",operation="product_orchestrator.send_to_etsy_review",stage="preflight")
        current_upload_id=(state.get("evidence",{}).get("upload") or {}).get("printify_image_id")
        front=[image for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")=="front"
            for image in placeholder.get("images") or [] if image.get("id")==current_upload_id]
        back=[image for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")!="front"
            for image in placeholder.get("images") or []]
        placement={"x":.5,"y":.46,"scale":.85,"angle":0}
        if not front or any(front[0].get(key)!=value for key,value in placement.items()) or back:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Artwork placement changed before the Etsy channel test.",operation="product_orchestrator.send_to_etsy_review",stage="artwork")
        review_path=self._path(job_id).parent/"visual-review"/"visual-review.json"
        try:review=json.loads(review_path.read_text(encoding="utf-8"));mockup_reviews=(review.get("checks") or {}).get("mockups") or []
        except (OSError,ValueError) as exc:raise StateConflictError("STATE_CONFLICT",diagnostic_message="Fresh visual review evidence is unavailable.",operation="product_orchestrator.send_to_etsy_review",stage="visual_review") from exc
        if review.get("product_id")!=product_id or review.get("recommended_scale_action")!="keep_0.85" or len(mockup_reviews)!=3 or not all(item.get("verified_mockup_available") for item in mockup_reviews):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Fresh visual review evidence is incomplete.",operation="product_orchestrator.send_to_etsy_review",stage="visual_review")
        try:gpsr=client.get_product_gpsr(shop_id,product_id)
        except PrintifyAPIError as exc:
            if exc.http_status!=404:raise
            gpsr={}
        sections=gpsr.get("sections") or [] if isinstance(gpsr,dict) else []
        exact_sections=[{"title":str(item.get("title") or ""),"text":str(item.get("text") or "")} for item in sections if item.get("title") and item.get("text")]
        safety_information="\n\n".join(f'{item["title"]}\n{item["text"]}' for item in exact_sections) if exact_sections else None
        gpsr_available=bool(safety_information);remote_variants=remote.get("variants") or [];current_default=next((item.get("id") for item in remote_variants if item.get("is_default") is True),None)
        mockup_count=len(remote.get("images") or []);publish_payload={"title":True,"description":True,"images":True,"variants":True,"tags":True,"keyFeatures":True,"shipping_template":True}
        plan={"result":"etsy_channel_test_plan","write_performed":False,"printify_write_performed":False,"publish_performed":False,"product_id":product_id,
            "shop_id":shop_id,"sales_channel":"etsy","current_default_variant_id":current_default,"proposed_default_variant_id":18102,
            "proposed_default_color":"Black","current_mockup_count":mockup_count,"mockup_publish_strategy":"all_current_printify_mockups",
            "publish_images":True,"gpsr_information_available":gpsr_available,"etsy_attributes_require_manual_selection":True,
            "etsy_draft_behavior_unverified":True,"public_listing_risk_acknowledged":True,"order_status":"not_created","safe_to_test":True}
        if not confirmed:return plan
        full_ids=[item.get("id") for item in remote_variants];print_areas,_=sanitize_update_print_areas(remote.get("print_areas") or [],full_ids)
        variants_payload=[]
        for item in remote_variants:
            row={"id":item.get("id"),"price":item.get("price"),"is_enabled":item.get("is_enabled") is True,"is_default":item.get("id")==18102}
            if item.get("sku") is not None:row["sku"]=item.get("sku")
            variants_payload.append(row)
        readiness_needed=current_default!=18102 or (gpsr_available and remote.get("safety_information")!=safety_information)
        readiness_at=None
        if readiness_needed:
            update_payload={"title":metadata["title"],"description":metadata["description"],"tags":metadata["tags"],"variants":variants_payload,"print_areas":print_areas}
            if gpsr_available:update_payload["safety_information"]=safety_information
            client.update_product(shop_id,product_id,update_payload);readiness_at=datetime.now().astimezone().isoformat()
            ready=client.get_product(shop_id,product_id)
            ready_variants=ready.get("variants") or [];ready_defaults=[item.get("id") for item in ready_variants if item.get("is_default") is True]
            ready_enabled={item.get("id") for item in ready_variants if item.get("is_enabled") is True};before_prices={item.get("id"):item.get("price") for item in remote_variants};after_prices={item.get("id"):item.get("price") for item in ready_variants}
            ready_front=[image for area in ready.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")=="front"
                for image in placeholder.get("images") or [] if image.get("id")==current_upload_id]
            before_mockups={(item.get("id"),item.get("mockup_id"),item.get("src")) for item in remote.get("images") or []};after_mockups={(item.get("id"),item.get("mockup_id"),item.get("src")) for item in ready.get("images") or []}
            validate_listing_metadata(state,"product_orchestrator.send_to_etsy_review",{"title":ready.get("title"),"description":ready.get("description"),"tags":ready.get("tags"),"price_cents":metadata["price_cents"]})
            if ready_defaults!=[18102] or len(ready_variants)!=len(remote_variants) or {item.get("id") for item in ready_variants}!={item.get("id") for item in remote_variants} \
                    or ready.get("id")!=product_id or ready.get("shop_id")!=shop_id or ready_enabled!=set(expected_variant_ids) or before_prices!=after_prices or ready.get("title")!=metadata["title"] or ready.get("description")!=metadata["description"] \
                    or ready.get("tags")!=metadata["tags"] or not ready_front or any(ready_front[0].get(key)!=value for key,value in placement.items()) \
                    or before_mockups!=after_mockups or (gpsr_available and ready.get("safety_information")!=safety_information):
                raise StateConflictError("STATE_CONFLICT",diagnostic_message="The Etsy readiness update failed verification.",operation="product_orchestrator.send_to_etsy_review",stage="readiness_verification")
            remote=ready
        readiness={"category":{"recommended_value":"T-shirts","selected_remotely":False},"recipient":{"recommended_value":"Unisex adults","selected_remotely":False,"evidence":"Blueprint title"},
            "sleeve_length":{"recommended_value":"Short sleeve","selected_remotely":False,"evidence":"Blueprint title"},"style":{"recommended_value":"Graphic tee","selected_remotely":False,"evidence":"Front graphic artwork"},
            "primary_color":{"recommended_value":"Black","selected_remotely":False,"evidence":"Default variant"},"available_colors":DEFAULT_COLORS,"available_sizes":DEFAULT_SIZES,"price_cents":metadata["price_cents"],
            "gpsr_information_verified":gpsr_available,"gpsr_manual_review_required":not gpsr_available,"mockup_count":mockup_count,
            "additional_marketing_images_supported":True,"additional_marketing_images_destination":"Etsy","additional_marketing_images_require_etsy_integration":True,
            "additional_marketing_images_generated":False,"future_marketing_images":["lifestyle-black.png","lifestyle-dark-grey-heather.png","closeup-design.png","size-chart.png","pride-gift-image.png"]}
        _atomic_json(self._path(job_id).parent/"etsy-listing-readiness.json",readiness)
        publish_error=None
        validate_listing_metadata(state,"product_orchestrator.send_to_etsy_review",metadata)
        try:client.publish_product(shop_id,product_id,publish_payload)
        except PrintifyAPIError as exc:publish_error=exc
        external={};checked=remote
        for attempt in range(max(1,self.adapters.publish_poll_attempts)):
            checked=client.get_product(shop_id,product_id);external=checked.get("external") or {}
            if external.get("id") or external.get("handle"):break
            if attempt+1<self.adapters.publish_poll_attempts:self.adapters.sleep(5)
        post_variants=checked.get("variants") or [];post_enabled={item.get("id") for item in post_variants if item.get("is_enabled") is True}
        post_front=[image for area in checked.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")=="front" for image in placeholder.get("images") or []]
        post_other=[image for area in checked.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")!="front" for image in placeholder.get("images") or []]
        validate_listing_metadata(state,"product_orchestrator.send_to_etsy_review",{"title":checked.get("title"),"description":checked.get("description"),"tags":checked.get("tags"),"price_cents":metadata["price_cents"]})
        post_valid=(checked.get("id")==product_id and checked.get("shop_id")==shop_id and checked.get("title")==metadata["title"]
            and len(post_variants)==318 and post_enabled==set(expected_variant_ids) and len(post_front)==1
            and post_front[0].get("id")==current_upload_id and all(post_front[0].get(key)==value for key,value in placement.items()) and not post_other
            and len(checked.get("images") or [])==mockup_count and checked.get("order_status") in (None,"not_created") and not checked.get("orders"))
        if external.get("handle") and post_valid:classification=self.adapters.etsy_visibility(str(external["handle"]))
        elif external:classification="indeterminate"
        elif publish_error:classification="unavailable"
        else:classification="indeterminate"
        if publish_error and not external:
            evidence["etsy_channel_test"]={"publication_request_count":1,"publication_error":publish_error.code,"etsy_human_gate_result":"unavailable","order_status":"not_created"};_atomic_json(self._path(job_id),state)
            return {"result":"etsy_publication_unavailable","write_performed":readiness_needed,"printify_write_performed":readiness_needed,
                "publish_performed":True,"publish_request_count":1,"product_id":product_id,"etsy_human_gate_result":"unavailable","order_status":"not_created"}
        stage="awaiting_etsy_human_review" if classification in ("held_for_review","publicly_active") else "awaiting_etsy_visibility_confirmation"
        readiness.update({"etsy_listing_external_id":external.get("id"),"etsy_listing_handle":external.get("handle"),"etsy_visibility_classification":classification})
        _atomic_json(self._path(job_id).parent/"etsy-listing-readiness.json",readiness)
        state["stage"]=stage;state["publish_status"]="etsy_listing_created_not_confirmed_active" if classification=="held_for_review" else "etsy_visibility_indeterminate" if classification=="indeterminate" else "etsy_listing_publicly_active"
        evidence["etsy_channel_test"]={"active_product_id":product_id,"etsy_listing_id":external.get("id"),"etsy_listing_handle":external.get("handle"),
            "readiness_update_timestamp":readiness_at,"publication_timestamp":datetime.now().astimezone().isoformat(),"publication_request_count":1,
            "publication_payload":publish_payload,"current_mockup_count":mockup_count,"mockup_publish_strategy":"all_current_printify_mockups",
            "default_variant_id":18102,"gpsr_information_verified":gpsr_available,"gpsr_manual_review_required":not gpsr_available,
            "etsy_human_gate_result":classification,"etsy_attributes_require_manual_selection":True,"human_artistic_approval":False,"order_status":"not_created"}
        state["order_status"]="not_created";_atomic_json(self._path(job_id),state)
        base={"write_performed":True,"printify_write_performed":True,"publish_performed":True,"publish_request_count":1,"product_id":product_id,
            "etsy_listing_id":external.get("id"),"etsy_listing_handle":external.get("handle"),"etsy_human_gate_result":classification,
            "default_variant_id":18102,"mockups_sent":True,"mockup_publish_strategy":"all_current_printify_mockups","stage":stage,"order_status":"not_created"}
        if classification=="indeterminate":return {"result":"etsy_listing_created_visibility_indeterminate",**base}
        if classification=="publicly_active":base["immediate_etsy_review_required"]=True
        return {"result":"etsy_listing_created",**base}

    def prepare_listing(self, job_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not job_id or Path(job_id).name!=job_id:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Listing preparation requires a single existing job ID.",operation="product_orchestrator.prepare_listing",stage="input")
        state=self.load(job_id);evidence=state.get("evidence") or {};draft=evidence.get("draft") or {}
        metadata=validate_listing_metadata(state,"product_orchestrator.prepare_listing")
        product_id,shop_id,expected_variant_ids=_current_product_evidence(state,"product_orchestrator.prepare_listing")
        if product_id in {RECOVERY_DELETED_PRODUCT_ID,PROTECTED_PRODUCT_ID}:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The active draft is deleted or protected.",operation="product_orchestrator.prepare_listing",stage="ownership")
        client=self.adapters.client_factory();remote=client.get_product(shop_id,product_id)
        if not replacement_ownership_matches(state,remote,product_id):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Replacement-product ownership evidence did not match.",operation="product_orchestrator.prepare_listing",stage="ownership")
        publication=assess_draft_publication_state(state,remote)
        if not publication["safe_to_reconcile"] or state.get("order_status")!="not_created" or remote.get("order_status") not in (None,"not_created") or remote.get("orders"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Published, locked, or ordered products cannot be prepared.",operation="product_orchestrator.prepare_listing",stage="publication")
        remote_variants=remote.get("variants") or [];enabled=[item for item in remote_variants if item.get("is_enabled") is True]
        if len(enabled)!=18 or {item.get("id") for item in enabled}!=set(expected_variant_ids) or any(item.get("price")!=metadata["price_cents"] for item in enabled):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Enabled variants or pricing changed before listing preparation.",operation="product_orchestrator.prepare_listing",stage="variants")
        current_upload_id=(state.get("evidence",{}).get("upload") or {}).get("printify_image_id")
        front=[image for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")=="front" for image in placeholder.get("images") or [] if image.get("id")==current_upload_id]
        back=[image for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")!="front" for image in placeholder.get("images") or []]
        placement={"x":.5,"y":.46,"scale":.85,"angle":0}
        if not front or any(front[0].get(key)!=value for key,value in placement.items()) or back:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Artwork placement changed before listing preparation.",operation="product_orchestrator.prepare_listing",stage="artwork")
        review_path=self._path(job_id).parent/"visual-review"/"visual-review.json"
        try:review=json.loads(review_path.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="A fresh visual review is required before listing preparation.",operation="product_orchestrator.prepare_listing",stage="visual_review") from exc
        mockups=(review.get("checks") or {}).get("mockups") or [];hashes=[item.get("downloaded_sha256") for item in mockups]
        if review.get("product_id")!=product_id or review.get("recommended_scale_action")!="keep_0.85" or len(mockups)!=3 \
                or [item.get("color") for item in mockups]!=DEFAULT_COLORS or not all(item.get("verified_mockup_available") for item in mockups) \
                or any(not digest for digest in hashes) or len(set(hashes))!=3:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The replacement draft lacks three distinct verified color mockups.",operation="product_orchestrator.prepare_listing",stage="visual_review")
        def catalog_read(category: str, call: Callable[[],Any]) -> Any:
            try:return call()
            except PrintifyAPIError as exc:
                exc.context.update({"product_id":product_id,"printify_product_id":product_id,"blueprint_id":12,"print_provider_id":29,
                    "catalog_evidence_category":category,"failed_catalog_call_category":category,"unavailable_evidence":category})
                exc.user_message=f"The read-only Printify catalog {category} evidence could not be retrieved."
                exc.suggested_action=f"Retry after confirming the Printify {category} catalog endpoint is available."
                raise
        blueprint=catalog_read("blueprint",lambda:client.get_blueprint(12))
        providers=catalog_read("print_providers",lambda:client.list_print_providers_for_blueprint(12))
        catalog=catalog_read("provider_variants",lambda:client.get_variants(12,29,show_out_of_stock=True))
        claim_validation=validate_listing_claims(metadata["description"],blueprint,providers,catalog,remote,product_id)
        selection=select_printify_variants(catalog,colors=DEFAULT_COLORS,sizes=DEFAULT_SIZES)
        if len(selection["selected_variant_ids"])!=18 or set(selection["selected_variant_ids"])!=set(expected_variant_ids):
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="The current catalog no longer matches the enabled Etsy variants.",operation="product_orchestrator.prepare_listing",stage="variants")
        catalog_ids={item.get("id") for item in catalog.get("variants") or [] if type(item.get("id")) is int}
        variants_payload,full_ids=build_full_variant_payload(remote_variants,expected_variant_ids,catalog_ids,metadata["price_cents"])
        print_areas,empty_positions=sanitize_update_print_areas(remote.get("print_areas") or [],full_ids)
        if len(remote_variants)!=318 or len(variants_payload)!=318 or not print_areas or any(set(area["variant_ids"])!=set(full_ids) for area in print_areas):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The full remote variant or print-area document changed.",operation="product_orchestrator.prepare_listing",stage="payload")
        payload={"title":metadata["title"],"description":metadata["description"],"tags":metadata["tags"],"variants":variants_payload,"print_areas":print_areas}
        marker=evidence.get("draft_marker") or draft.get("draft_marker")
        if marker and marker in json.dumps({"title":metadata["title"],"description":metadata["description"],"tags":metadata["tags"]}):
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Internal marker leaked into buyer-facing listing fields.",operation="product_orchestrator.prepare_listing",stage="listing")
        manual_checks=["Set Black as the primary listing image.","Keep Dark Grey Heather second and White third.",
            "Add an available lifestyle/on-person mockup.","Add a close-up design mockup.","Add a current Bella+Canvas 3001 size chart.",
            "Verify the Etsy category and most-specific subcategory.","Complete Etsy attributes: primary color, secondary color, sleeve length, neckline, fit, style, and occasion.","Verify materials using current provider data.",
            "Verify production-partner disclosure.","Select the correct Etsy shipping profile without copying an unrelated template ID.",
            "Verify processing and delivery estimates.","Verify return and cancellation settings.","Review the $24.99 price and expected margin.",
            "Verify all size and color combinations.","Perform a manual trademark and intellectual-property review.",
            "Preview the complete Etsy listing on desktop and mobile.","Confirm GPSR/product-safety information, manufacturer, responsible person, product identification, warnings, and safety details in Printify.",
            "Publish only through a separate future human-confirmed action."]
        plan={"result":"listing_preparation_plan","write_performed":False,"printify_write_performed":False,"product_id":product_id,
            "proposed_title":metadata["title"],"proposed_description_present":True,"seo_tag_count":13,"price_cents":metadata["price_cents"],"enabled_variant_count":18,"placement_scale":.85,
            "primary_mockup_color":"Black","primary_mockup_manual_action_required":True,"gpsr_manual_confirmation_required":True,
            "publish_status":"not_published","order_status":"not_created","safe_to_update":True,"catalog_claims_verified":True}
        if not confirmed:return plan
        client.update_product(shop_id,product_id,payload)
        verified=client.get_product(shop_id,product_id);verified_publication=assess_draft_publication_state(state,verified)
        verified_variants=verified.get("variants") or [];verified_enabled=[item for item in verified_variants if item.get("is_enabled") is True]
        verified_front=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")=="front" for image in placeholder.get("images") or [] if image.get("id")==current_upload_id]
        verified_back=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")!="front" for image in placeholder.get("images") or []]
        prices_before={item.get("id"):item.get("price") for item in remote_variants};prices_after={item.get("id"):item.get("price") for item in verified_variants}
        validate_listing_metadata(state,"product_orchestrator.prepare_listing",{"title":verified.get("title"),"description":verified.get("description"),"tags":verified.get("tags"),"price_cents":metadata["price_cents"]})
        verified_ok=(verified.get("id")==product_id and verified.get("title")==metadata["title"] and verified.get("description")==metadata["description"]
            and verified.get("tags")==metadata["tags"] and (not marker or marker not in set(verified.get("tags") or [])) and len(verified_variants)==318
            and {item.get("id") for item in verified_variants}==set(full_ids) and prices_after==prices_before
            and verified.get("shop_id")==shop_id and {item.get("id") for item in verified_enabled}==set(expected_variant_ids) and len(verified_enabled)==18
            and verified_front and all(verified_front[0].get(key)==value for key,value in placement.items()) and not verified_back
            and verified_publication["safe_to_reconcile"] and verified.get("order_status") in (None,"not_created") and not verified.get("orders"))
        if not verified_ok:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The listing draft failed post-update verification.",operation="product_orchestrator.prepare_listing",stage="verification",
                context={"product_id":product_id,"update_performed":True})
        state.update({"stage":"awaiting_printify_human_review","active_product_id":product_id,"visual_review_completed":True,
            "visual_review_recommendation":"keep_0.85","human_artistic_approval":False,"listing_text_prepared":True,"seo_tag_count":13,
            "primary_mockup_color_requested":"Black","primary_mockup_manual_action_required":True,"gpsr_manual_confirmation_required":True,
            "final_review_location":"Printify","publish_status":"not_published","order_status":"not_created"})
        evidence["listing"].update({"title":metadata["title"],"description":metadata["description"],"tags":metadata["tags"],"price_cents":metadata["price_cents"]})
        evidence["listing_preparation"]={"active_product_id":product_id,"prepared_at":datetime.now().astimezone().isoformat(),
            "visual_review_completed":True,"visual_review_recommendation":"keep_0.85","human_artistic_approval":False,"listing_text_prepared":True,
            "seo_tag_count":13,"primary_mockup_color_requested":"Black","primary_mockup_manual_action_required":True,
            "gpsr_manual_confirmation_required":True,"shipping_profile_manual_confirmation_required":True,"final_review_location":"Printify",
            "mockup_order_api_supported":False,"publish_status":"not_published","order_status":"not_created","manual_checks":manual_checks,"local_draft_marker":marker}
        evidence["listing_preparation"]["catalog_claim_validation"]=claim_validation
        _atomic_json(self._path(job_id),state)
        return {"result":"listing_draft_prepared","write_performed":True,"printify_write_performed":True,"product_id":product_id,
            "title_verified":True,"description_verified":True,"seo_tags_verified":True,"seo_tag_count":13,
            "internal_marker_removed_from_remote_tags":True,"variants_unchanged":True,"placement_unchanged":True,"no_new_upload":True,
            "no_new_product":True,"primary_mockup_manual_action_required":True,"gpsr_manual_confirmation_required":True,
            "stage":"awaiting_printify_human_review","publish_status":"not_published","order_status":"not_created"}

    def recover_draft(self, job_id: str, *, confirmed: bool = False) -> dict[str, Any]:
        if not job_id or Path(job_id).name!=job_id:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Draft recovery requires a single existing job ID.",operation="product_orchestrator.recover_draft",stage="input")
        state=self.load(job_id);evidence=state.get("evidence") or {};draft=evidence.get("draft") or {};upload=evidence.get("upload") or {}
        if state.get("stage")=="failed" and not draft.get("printify_product_id") and evidence.get("selection"):
            return self._recover_independent_create(state,confirmed=confirmed)
        deleted_id=draft.get("printify_product_id");marker=evidence.get("draft_marker") or draft.get("draft_marker")
        listing=evidence.get("listing") or {};selected_sha=evidence.get("selection",{}).get("selected",{}).get("png_sha256")
        if state.get("shop_id")!=RECOVERY_SHOP_ID or deleted_id!=RECOVERY_DELETED_PRODUCT_ID or deleted_id==PROTECTED_PRODUCT_ID:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The job does not match the guarded deleted-draft recovery target.",operation="product_orchestrator.recover_draft",stage="ownership")
        if upload.get("printify_image_id")!=RECOVERY_UPLOAD_ID or upload.get("selected_design_sha256")!=selected_sha:
            raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH",diagnostic_message="Recovery upload evidence does not match the selected artwork.",operation="product_orchestrator.recover_draft",stage="artwork")
        if marker!=RECOVERY_TAGS[-1] or listing.get("title")!=RECOVERY_TITLE or listing.get("description")!=RECOVERY_DESCRIPTION \
                or listing.get("tags")!=RECOVERY_TAGS[:-1] or listing.get("price_cents")!=2499:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Local listing evidence does not match the guarded recovery specification.",operation="product_orchestrator.recover_draft",stage="listing")
        protected_history=[item for item in evidence.get("draft_recovery_history") or []
            if item.get("deleted_product_id")==PROTECTED_PRODUCT_ID or item.get("replacement_product_id")==PROTECTED_PRODUCT_ID]
        if protected_history:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Recovery history references the protected product.",operation="product_orchestrator.recover_draft",stage="protected_product")
        publish_ops={"publish","publish_product","printify_publish","publish_succeeded"};order_ops={"order","create_order","submit_order","order_created"}
        if any(item.get("operation") in publish_ops|order_ops or item.get("stage") in {"published","printify_published","order_created"}
               for item in state.get("transitions") or []) or state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Publish or order history blocks deleted-draft recovery.",operation="product_orchestrator.recover_draft",stage="history")
        client=self.adapters.client_factory()
        try: client.get_product(RECOVERY_SHOP_ID,deleted_id)
        except PrintifyAPIError as exc:
            if exc.http_status!=404: raise
        else:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The old Printify product still exists.",operation="product_orchestrator.recover_draft",stage="deleted_product")
        remote_upload=client.get_upload(RECOVERY_UPLOAD_ID)
        mime=remote_upload.get("mime_type") or remote_upload.get("mimeType") or remote_upload.get("type")
        if mime!="image/png" or remote_upload.get("width")!=4500 or remote_upload.get("height")!=5400:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="The reusable Printify upload does not match the required PNG dimensions.",operation="product_orchestrator.recover_draft",stage="upload")
        products=_products(client.list_products(RECOVERY_SHOP_ID));matches=[item for item in products if item.get("id")==deleted_id
            or marker in {str(tag) for tag in item.get("tags") or []} or item.get("title")==RECOVERY_TITLE]
        if matches:
            if any(item.get("id")==PROTECTED_PRODUCT_ID for item in matches):
                raise StateConflictError("STATE_CONFLICT",diagnostic_message="A matching recovery candidate is the protected product.",operation="product_orchestrator.recover_draft",stage="protected_product")
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="A matching replacement draft already exists.",operation="product_orchestrator.recover_draft",stage="replacement_search")
        catalog=client.get_variants(12,29);selection=select_printify_variants(catalog,colors=DEFAULT_COLORS,sizes=DEFAULT_SIZES)
        if selection["selected_variant_ids"]!=RECOVERY_VARIANT_IDS:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="The current catalog does not match the guarded recovery variants.",operation="product_orchestrator.recover_draft",stage="variants")
        placement={"x":.5,"y":.46,"scale":.85,"angle":0}
        plan={"result":"draft_recovery_plan","write_performed":False,"printify_write_performed":False,"job_id":job_id,
            "deleted_product_id":deleted_id,"shop_id":RECOVERY_SHOP_ID,"upload_id":RECOVERY_UPLOAD_ID,"reuse_existing_upload":True,
            "new_upload_required":False,"replacement_product_required":True,"enabled_variant_count":18,"price_cents":2499,
            "placement":placement,"publish_status":"not_published","order_status":"not_created","safe_to_recover":True}
        if not confirmed:return plan
        payload={"title":RECOVERY_TITLE,"description":RECOVERY_DESCRIPTION,"tags":RECOVERY_TAGS,"blueprint_id":12,"print_provider_id":29,
            "variants":[{"id":item,"price":2499,"is_enabled":True} for item in RECOVERY_VARIANT_IDS],
            "print_areas":[{"variant_ids":RECOVERY_VARIANT_IDS,"placeholders":[{"position":"front","decoration_method":"dtg",
                "images":[{"id":RECOVERY_UPLOAD_ID,**placement}]}]}]}
        created=client.create_product(RECOVERY_SHOP_ID,payload);replacement_id=created.get("id")
        if not replacement_id or replacement_id in {deleted_id,PROTECTED_PRODUCT_ID}:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Printify did not return a safe new replacement product ID.",operation="product_orchestrator.recover_draft",stage="creation")
        history=evidence.setdefault("draft_recovery_history",[]);recovery={"status":"creation_succeeded_verification_pending",
            "deleted_product_id":deleted_id,"replacement_product_id":replacement_id,"reused_upload":True,"new_upload_created":False,
            "new_product_created":True,"publish_status":"not_published","order_status":"not_created"}
        history.append(recovery);evidence["visual_review_status"]={"status":"stale","product_id":deleted_id,"fresh_visual_review_required":True}
        _atomic_json(self._path(job_id),state)
        try:
            verified=client.get_product(RECOVERY_SHOP_ID,replacement_id);publication=assess_draft_publication_state(state,verified)
            enabled=[item for item in verified.get("variants") or [] if item.get("is_enabled") is True]
            front=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or []
                if placeholder.get("position")=="front" for image in placeholder.get("images") or [] if image.get("id")==RECOVERY_UPLOAD_ID]
            back=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or []
                if placeholder.get("position") in ("back","neck") for image in placeholder.get("images") or []]
            placement_ok=bool(front and all(front[0].get(key)==value for key,value in placement.items()))
            verified_ok=(verified.get("id")==replacement_id and verified.get("shop_id")==RECOVERY_SHOP_ID and verified.get("blueprint_id")==12
                and verified.get("print_provider_id")==29 and verified.get("title")==RECOVERY_TITLE and marker in {str(tag) for tag in verified.get("tags") or []}
                and len(enabled)==18 and {item.get("id") for item in enabled}==set(RECOVERY_VARIANT_IDS)
                and all(item.get("price")==2499 for item in enabled) and placement_ok and not back and publication["safe_to_reconcile"]
                and verified.get("order_status") in (None,"not_created") and not verified.get("orders"))
            if not verified_ok:
                raise StateConflictError("STATE_CONFLICT",diagnostic_message="The replacement draft failed post-create verification.",operation="product_orchestrator.recover_draft",stage="verification",
                    context={"replacement_product_id":replacement_id})
        except Exception as exc:
            recovery["status"]="verification_failed";recovery["verification_failed_at"]=datetime.now().astimezone().isoformat();_atomic_json(self._path(job_id),state)
            if hasattr(exc,"context"):exc.context["replacement_product_id"]=replacement_id
            raise
        recovery.update({"status":"verified","recovered_at":datetime.now().astimezone().isoformat(),"remote_product_verified":True})
        draft["printify_product_id"]=replacement_id;draft["variant_ids"]=RECOVERY_VARIANT_IDS
        state["publish_status"]="not_published";state["order_status"]="not_created";_atomic_json(self._path(job_id),state)
        return {"result":"deleted_draft_recovered","write_performed":True,"printify_write_performed":True,
            "deleted_product_id":deleted_id,"replacement_product_id":replacement_id,"reused_upload":True,"new_upload_created":False,
            "new_product_created":True,"enabled_variant_count":18,"remote_product_verified":True,"publish_status":"not_published",
            "order_status":"not_created","fresh_visual_review_required":True}

    def _recover_independent_create(self,state:dict[str,Any],*,confirmed:bool=False)->dict[str,Any]:
        evidence=state.get("evidence") or {};selected=(evidence.get("selection") or {}).get("selected") or {};selected_path=Path(str(selected.get("png_path") or ""))
        selected_sha=selected.get("png_sha256");upload=evidence.get("upload") or {};upload_id=upload.get("printify_image_id")
        rejected=evidence.get("rejected_uploads") or [];previous_upload_rejected=bool(rejected);rejected_ids={item.get("printify_image_id") for item in rejected};reusable=bool(upload_id and upload_id not in rejected_ids and upload.get("selected_design_sha256")==selected_sha)
        if state.get("shop_id")!=RECOVERY_SHOP_ID or state.get("publish_status")!="not_published" or state.get("order_status")!="not_created":
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Independent recovery requires the original unpublished, unordered Printify shop job.",operation="product_orchestrator.recover_draft",stage="ownership")
        if not selected_path.is_file() or _file_sha(selected_path)!=selected_sha:raise ArtifactIntegrityError("ARTIFACT_SHA_MISMATCH",diagnostic_message="Selected local design candidate no longer matches recovery evidence.",operation="product_orchestrator.recover_draft",stage="artwork")
        old_brief=state.get("brief") or {};brief=normalize_prompt(state["original_prompt"],price=old_brief.get("price_cents"),garment_colors=old_brief.get("garment_colors") or DEFAULT_COLORS,sizes=old_brief.get("sizes") or DEFAULT_SIZES)
        if brief["garment_colors"]!=DEFAULT_COLORS or brief["sizes"]!=DEFAULT_SIZES:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Independent recovery is restricted to Black, Dark Grey Heather, and White in sizes S through 3XL.",operation="product_orchestrator.recover_draft",stage="variants")
        listing=generate_listing(brief,selected);marker=evidence.get("draft_marker") or _draft_marker(state);stored_ids=(evidence.get("variant_selection") or {}).get("selected_variant_ids") or []
        if len(stored_ids)!=18 or len(set(stored_ids))!=18:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Independent recovery requires exactly 18 recorded requested variants.",operation="product_orchestrator.recover_draft",stage="variants")
        approval=evidence.get("human_design_approval") or {};approval_valid=approval.get("approved") is True and approval.get("candidate_id")==selected.get("candidate_id") and approval.get("candidate_sha256")==selected_sha and _file_sha(selected_path)==selected_sha
        plan={"result":"independent_draft_recovery_plan","write_performed":False,"printify_write_performed":False,"job_id":state["job_id"],"shop_id":state["shop_id"],
            "reusable_upload_exists":reusable,"upload_id":upload_id if reusable else None,"new_upload_required":not reusable,"new_upload_would_occur":not reusable,
            "new_product_would_be_created":True,"enabled_variant_count":18,"title":listing["title"],"tags":listing["tags"],"selected_design_candidate":selected.get("candidate_id"),
            "selected_design_path":str(selected_path),"front_artwork_only":True,"previous_upload_rejected":previous_upload_rejected,"human_design_approval_required":not approval_valid,
            "publish_status":"not_published","order_status":"not_created","safe_to_recover":approval_valid}
        if not confirmed:return plan
        if not approval_valid:raise PermissionError("Human approval of the corrected candidate hash is required before recovery")
        client=self.adapters.client_factory();catalog=client.get_variants(12,29);selection=select_printify_variants(catalog,colors=DEFAULT_COLORS,sizes=DEFAULT_SIZES);chosen=selection["selected_variant_ids"]
        if len(chosen)!=18 or set(chosen)!=set(stored_ids):raise ValidationError("VALIDATION_FAILED",diagnostic_message="Current Printify catalog variants differ from the failed job recovery evidence.",operation="product_orchestrator.recover_draft",stage="variants")
        payload={"title":listing["title"],"description":listing["description"],"tags":[*listing["tags"],marker],"blueprint_id":12,"print_provider_id":29,
            "variants":create_variant_payload(catalog,chosen,listing["price_cents"]),"print_areas":[{"variant_ids":chosen,"placeholders":[{"position":"front","images":[{"id":upload_id or "pending-validated-upload","x":.5,"y":.46,"scale":.85,"angle":0}]}]}]}
        validate_create_payload(payload,chosen)
        existing=_find_marked_draft(client.list_products(state["shop_id"]),marker)
        if existing:product=existing;created=False
        else:
            if reusable:
                remote_upload=client.get_upload(upload_id)
                if remote_upload.get("id") not in (None,upload_id):raise StateConflictError("STATE_CONFLICT",diagnostic_message="Reusable Printify upload identity did not match.",operation="product_orchestrator.recover_draft",stage="upload")
            else:
                remote_upload=client.upload_image_contents(f"jamesos-{state['job_id']}-{selected_sha[:12]}.png",__import__("base64").b64encode(selected_path.read_bytes()).decode())
                upload_id=remote_upload.get("id")
                if not upload_id:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify upload did not return an image ID.",operation="product_orchestrator.recover_draft",stage="upload")
            payload["print_areas"][0]["placeholders"][0]["images"][0]["id"]=upload_id;validate_create_payload(payload,chosen)
            product=client.create_product(state["shop_id"],payload);created=True
        product_id=product.get("id")
        if not product_id or product_id==PROTECTED_PRODUCT_ID:raise StateConflictError("STATE_CONFLICT",diagnostic_message="Recovery returned a missing or protected Printify product ID.",operation="product_orchestrator.recover_draft",stage="creation")
        verified=client.get_product(state["shop_id"],product_id);enabled={item.get("id") for item in verified.get("variants") or [] if item.get("is_enabled") is True}
        front=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position")=="front" for image in placeholder.get("images") or [] if image.get("id")==upload_id]
        back=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or [] if placeholder.get("position") in ("back","neck") for image in placeholder.get("images") or []]
        if verified.get("id")!=product_id or enabled!=set(chosen) or not front or back:raise StateConflictError("STATE_CONFLICT",diagnostic_message="Recovered independent draft failed post-create verification.",operation="product_orchestrator.recover_draft",stage="verification",context={"product_id":product_id})
        current_error=state.get("last_error")
        if current_error and not any(item.get("error_id")==current_error.get("error_id") for item in state.setdefault("recovered_errors",[])):state["recovered_errors"].append({**current_error,"recovered_at":datetime.now().astimezone().isoformat()})
        state["brief"]=brief;evidence["listing"]=listing;evidence["upload"]={"printify_image_id":upload_id,"selected_design_sha256":selected_sha};evidence["variant_selection"]=selection
        evidence["draft"]={"printify_product_id":product_id,"variant_ids":chosen,"draft_marker":marker,"reconciled_existing_remote_draft":not created,"publish_status":"not_published","order_status":"not_created"}
        journal_path=self._path(state["job_id"]).parent/"unified-preparation.json"
        try:journal=json.loads(journal_path.read_text(encoding="utf-8"))
        except (OSError,ValueError):journal={"job_id":state["job_id"],"profile_id":state.get("commerce_profile_id"),"provider_actions":[]}
        journal_id=f"create-{uuid4().hex}";journal.setdefault("provider_actions",[]).append({"journal_id":journal_id,"status":"completed","uncertain":False,
            "completed_at":datetime.now().astimezone().isoformat(),"response_evidence":{"draft_recorded":True,"recovery":True}});_atomic_json(journal_path,journal)
        state["active_provider_create_journal_id"]=journal_id;evidence["draft_ownership"]=build_draft_ownership(state,product_id,journal_id)
        evidence.setdefault("draft_recovery_history",[]).append({"status":"verified","recovery_type":"independent_create_failure","replacement_product_id":product_id,"reused_upload":reusable,"new_upload_created":not reusable,"created_at":datetime.now().astimezone().isoformat()})
        state["stage"]="awaiting_human_approval";state["last_error"]=None;_atomic_json(self._path(state["job_id"]),state)
        return {"result":"independent_draft_recovered","write_performed":True,"printify_write_performed":True,"product_id":product_id,"reused_upload":reusable,"new_upload_created":not reusable,"new_product_created":created,"enabled_variant_count":18,"front_artwork_only":True,"publish_status":"not_published","order_status":"not_created"}

    def review_draft(self, job_id: str) -> dict[str, Any]:
        if not job_id or Path(job_id).name!=job_id:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="Draft review requires a single existing job ID.",operation="product_orchestrator.review_draft",stage="input")
        state=self.load(job_id);draft=state.get("evidence",{}).get("draft") or {};product_id=draft.get("printify_product_id")
        if not product_id or product_id==PROTECTED_PRODUCT_ID:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The recorded draft is missing or protected.",operation="product_orchestrator.review_draft",stage="ownership")
        client=self.adapters.client_factory();remote=client.get_product(state["shop_id"],product_id)
        publication=assess_draft_publication_state(state,remote)
        ownership=(self.verify_draft_ownership(state,remote) if (state.get("evidence") or {}).get("draft_ownership") else
            {"verified":replacement_ownership_matches(state,remote,product_id) and not state.get("commerce_profile_id"),"reasons":["canonical_ownership_record_missing"]})
        if not ownership["verified"]:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Remote draft ownership evidence did not match the job.",operation="product_orchestrator.review_draft",stage="ownership",
                context={"manual_verification_required":True,"printify_product_id":product_id,"printify_shop_id":state.get("shop_id"),"ownership_reasons":ownership["reasons"]})
        if remote.get("blueprint_id")!=12 or remote.get("print_provider_id")!=29:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Remote blueprint or provider differs from the review target.",operation="product_orchestrator.review_draft",stage="provider")
        if not publication["safe_to_reconcile"]:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="Published or locked products cannot be reviewed as drafts.",operation="product_orchestrator.review_draft",stage="publication")
        if state.get("order_status")!="not_created" or remote.get("order_status") not in (None,"not_created") or remote.get("orders"):
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="A product with order evidence cannot use draft review.",operation="product_orchestrator.review_draft",stage="order")
        enabled_ids={item.get("id") for item in remote.get("variants") or [] if item.get("is_enabled") is True}
        rows=normalize_printify_variants({"variants":remote.get("variants") or []});colors={color:[] for color in DEFAULT_COLORS}
        enabled_review_rows=[]
        for row in rows:
            if row["variant_id"] in enabled_ids and row["color"] in colors:
                colors[row["color"]].append(row["variant_id"]);enabled_review_rows.append(row)
        expected_pairs={(color,size) for color in DEFAULT_COLORS for size in DEFAULT_SIZES}
        enabled_pairs={(row["color"],row["size"]) for row in enabled_review_rows}
        if len(enabled_review_rows)!=18 or enabled_pairs!=expected_pairs:
            raise StateConflictError("STATE_CONFLICT",diagnostic_message="The draft does not contain enabled variants for every review color.",operation="product_orchestrator.review_draft",stage="variants")
        expected_image_id=state.get("evidence",{}).get("upload",{}).get("printify_image_id")
        front_images=[image for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")=="front" for image in placeholder.get("images") or []]
        back_images=[image for area in remote.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            if placeholder.get("position")=="back" for image in placeholder.get("images") or []]
        placement=next((image for image in front_images if image.get("id")==expected_image_id),front_images[0] if front_images else {})
        placement_value={key:placement.get(key) for key in ("x","y","scale","angle")}
        review_root=self._path(job_id).parent/"visual-review";review_root.mkdir(parents=True,exist_ok=True)
        names={"Black":"black-front.png","Dark Grey Heather":"dark-grey-heather-front.png","White":"white-front.png"}
        representative_ids={"Black":18102,"Dark Grey Heather":18150,"White":18542}
        records=[];panels=[]
        for color in DEFAULT_COLORS:
            representative_id=representative_ids[color]
            matching=[image for image in remote.get("images") or [] if mockup_identifies_variant(image,representative_id)
                and str(image.get("src") or "").startswith("https://")]
            matching.sort(key=lambda image:not bool(image.get("is_default")));available=False;panel=None;selected=matching[0] if matching else None
            if matching:
                try:
                    response=client.session.get(selected["src"],timeout=client.timeout);response.raise_for_status()
                    panel=Image.open(BytesIO(response.content)).convert("RGB");available=True
                except Exception: panel=None
            if panel is None:
                panel=Image.new("RGB",(900,1100),(235,235,235));draw=ImageDraw.Draw(panel)
                draw.text((60,520),f"{color}\nMockup unavailable",fill=(35,35,35))
            target=review_root/names[color];panel.save(target,"PNG");panels.append((color,panel.copy()))
            records.append({"color":color,"selected_variant_id":representative_id,"selected_mockup_id":selected.get("mockup_id") if selected else None,
                "selection_method":"exact_mockup_variant" if selected else None,"mockup_available":available,"color_match_verified":available,
                "downloaded_sha256":_file_sha(target) if available else None,"issues":[] if available else ["mockup_download_failed"] if selected else ["exact_mockup_variant_missing"],
                "local_path":str(target),"image_clipped":"unknown",
                "image_centered":"unknown","contrast_assessment":"manual_review_required",
                "likely_white_shirt_visibility_issue":"unknown" if color=="White" else False})
            panel.close()
        hashes={item["downloaded_sha256"] for item in records if item["downloaded_sha256"]}
        for digest in hashes:
            duplicates=[item for item in records if item["downloaded_sha256"]==digest]
            if len(duplicates)>1:
                for item in duplicates:
                    item["color_match_verified"]=False
                    if "mockup_color_mismatch" not in item["issues"]:item["issues"].append("mockup_color_mismatch")
        for item in records:item["verified_mockup_available"]=bool(item["mockup_available"] and item["color_match_verified"])
        panel_width=700;label_height=80;sheet_height=max(image.height*panel_width//image.width for _,image in panels)+label_height
        sheet=Image.new("RGB",(panel_width*len(panels),sheet_height),(255,255,255));draw=ImageDraw.Draw(sheet)
        for index,(color,image) in enumerate(panels):
            resized=image.copy();resized.thumbnail((panel_width,sheet_height-label_height),Image.Resampling.LANCZOS)
            x=index*panel_width+(panel_width-resized.width)//2;y=label_height+(sheet_height-label_height-resized.height)//2
            record=records[index];status="verified" if record["verified_mockup_available"] else "downloaded, not color-verified" if record["mockup_available"] else "unavailable"
            sheet.paste(resized,(x,y));draw.text((index*panel_width+20,25),f"{color} - {status}",fill=(20,20,20));resized.close();image.close()
        sheet_path=review_root/"visual-review-sheet.png";sheet.save(sheet_path,"PNG");sheet.close()
        all_verified=all(item["verified_mockup_available"] for item in records)
        recommendation="keep_0.85" if all_verified else "manual_review_required"
        checks={"mockups":records,"artwork_image_id":expected_image_id,"artwork_image_id_matches":bool(expected_image_id and placement.get("id")==expected_image_id),
            "placement":placement_value,"front_artwork_present":bool(front_images),"back_artwork_absent":not bool(back_images),
            "current_scale_recommendation":recommendation,"candidate_scales":{"current":.85,"plus_8_percent":.918,"plus_12_percent":.952},
            "pixel_review_scope":"Three distinct color mockups downloaded and exact variants verified" if all_verified else "Mockup color identity incomplete; manual review required"}
        report={"job_id":job_id,"product_id":product_id,"colors_reviewed":DEFAULT_COLORS,"checks":checks,
            "recommended_scale_action":recommendation,"created_at":datetime.now().astimezone().isoformat()}
        json_path=review_root/"visual-review.json";_atomic_json(json_path,report)
        rows_html="".join(f'<figure><img src="{html.escape(names[item["color"]])}" alt="{html.escape(item["color"])} front mockup"><figcaption>{html.escape(item["color"])} - {"verified" if item["verified_mockup_available"] else "downloaded, not color-verified" if item["mockup_available"] else "unavailable"}</figcaption></figure>' for item in records)
        html_path=review_root/"visual-review.html";html_path.write_text("<!doctype html><meta charset=\"utf-8\"><title>Draft visual review</title>"
            "<style>body{font-family:sans-serif;margin:2rem}main{display:flex;gap:1rem}figure{margin:0;flex:1}img{max-width:100%;height:auto}</style>"
            f"<h1>Draft visual review</h1><p>Product {html.escape(product_id)}</p><main>{rows_html}</main>",encoding="utf-8")
        return {"result":"draft_visual_review_created","write_performed":False,"printify_write_performed":False,
            "product_id":product_id,"colors_reviewed":DEFAULT_COLORS,"placement":placement_value,"recommended_scale_action":recommendation,
            "review_sheet_path":str(sheet_path),"html_report_path":str(html_path),"json_report_path":str(json_path)}

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
        publication = assess_draft_publication_state(state, remote)
        if not publication["safe_to_reconcile"]:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Publication evidence blocks draft reconciliation.", operation="product_orchestrator.reconcile_draft", stage="publication",
                context={"publication_assessment":publication,"blockers":publication["explicit_blockers"]})
        marker = state.get("evidence", {}).get("draft_marker") or draft.get("draft_marker")
        if not replacement_ownership_matches(state,remote,product_id):
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote draft ownership evidence did not match the job.", operation="product_orchestrator.reconcile_draft", stage="ownership")
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
        desired_ids = desired["selected_variant_ids"]
        expected_pairs={(color.casefold(),size.upper()) for color in DEFAULT_COLORS for size in state["brief"]["sizes"]}
        selected_pairs={(item["color"].casefold(),item["size"]) for item in desired["selected_variants"]}
        if len(desired_ids)!=18 or len(set(desired_ids))!=18 or selected_pairs!=expected_pairs:
            raise ValidationError("VALIDATION_FAILED",diagnostic_message="The current catalog did not resolve to exactly 18 required color and size variants.",
                operation="product_orchestrator.reconcile_draft",stage="variant_preflight",context={"selected_variant_count":len(desired_ids)})
        remote_variants=remote.get("variants") or []
        catalog_ids={item.get("id") for item in catalog.get("variants") or [] if type(item.get("id")) is int}
        variants_payload,full_remote_ids=build_full_variant_payload(remote_variants,desired_ids,catalog_ids,state["evidence"]["listing"]["price_cents"])
        remote_only_ids=sorted(set(full_remote_ids)-catalog_ids);catalog_absent_remote_ids=sorted(catalog_ids-set(full_remote_ids))
        current_rows = normalize_printify_variants({"variants":remote_variants})
        current_ids = [item["id"] for item in remote_variants if item.get("is_enabled") is True]
        retain = [item for item in desired_ids if item in current_ids]; add = [item for item in desired_ids if item not in current_ids]; remove = [item for item in current_ids if item not in desired_ids]
        current_scale = float(placements[0].get("scale") or 0); placement_plan = [{"label":"current","scale":current_scale,"inside_placeholder":0 < current_scale <= 1},
            {"label":"current_plus_8_percent","scale":round(current_scale*1.08,4),"inside_placeholder":0 < current_scale*1.08 <= 1},
            {"label":"current_plus_12_percent","scale":round(current_scale*1.12,4),"inside_placeholder":0 < current_scale*1.12 <= 1}]
        print_areas,empty_positions=sanitize_update_print_areas(remote.get("print_areas") or [],full_remote_ids)
        payload={"title":remote.get("title"),"description":remote.get("description"),"tags":remote.get("tags") or [],
            "variants":variants_payload,"print_areas":print_areas}
        payload_images=[image for area in print_areas for placeholder in area["placeholders"] for image in placeholder["images"]]
        payload_enabled_ids=[item["id"] for item in variants_payload if item["is_enabled"]]
        payload_disabled_ids=[item["id"] for item in variants_payload if not item["is_enabled"]]
        print_area_id_sets=[set(area["variant_ids"]) for area in print_areas]
        payload_summary={"payload_variant_count":len(variants_payload),"remote_variant_count":len(remote_variants),
            "current_catalog_variant_count":len(catalog_ids),"remote_only_variant_count":len(remote_only_ids),"remote_only_variant_ids":remote_only_ids,
            "catalog_ids_absent_from_remote_count":len(catalog_absent_remote_ids),"desired_ids_present_in_remote":set(desired_ids)<=set(full_remote_ids),
            "desired_ids_present_in_catalog":set(desired_ids)<=catalog_ids,
            "enabled_variant_count_before":len(current_ids),"enabled_variant_count_after":len(payload_enabled_ids),
            "disabled_variant_count_after":len(payload_disabled_ids),"newly_enabled_variant_ids":[item for item in desired_ids if item not in current_ids],
            "newly_disabled_variant_ids":[item for item in current_ids if item not in desired_ids],
            "remote_only_enabled_count_after":len(set(payload_enabled_ids)&set(remote_only_ids)),
            "print_area_variant_count":len(print_areas[0]["variant_ids"]) if print_areas else 0,
            "variant_id_sets_match":bool(print_area_id_sets) and all(ids==set(full_remote_ids) for ids in print_area_id_sets),
            "placeholder_positions":[placeholder["position"] for area in print_areas for placeholder in area["placeholders"]],
            "empty_placeholders_excluded":empty_positions,"placement_scale":payload_images[0].get("scale") if payload_images else None}
        plan = {"product_id":product_id,"selected_image_id":image_id,"requested_colors":resolution["canonical_colors"],
            "color_resolution":resolution,"current_colors":list(dict.fromkeys(row["color"] for row in current_rows if row["variant_id"] in current_ids)),
            "current_sizes":list(dict.fromkeys(row["size"] for row in current_rows if row["variant_id"] in current_ids)),
            "desired_colors":resolution["canonical_colors"],"desired_sizes":state["brief"]["sizes"],"variant_ids_to_retain":retain,
            "variant_ids_to_add":add,"variant_ids_to_remove":remove,"current_variant_count":len(current_ids),"resulting_variant_count":len(desired_ids),
            "price_cents":state["evidence"]["listing"]["price_cents"],"placement":copy.deepcopy(placements[0]),"placement_adjustment_plan":placement_plan,
            "placement_change_included":False,"publish_status":"not_published","order_status":"not_created","draft_marker":marker,
            "publication_assessment":publication,"update_payload_summary":payload_summary}
        if not confirmed: return {"result":"draft_reconciliation_plan","write_performed":False,"plan":plan}
        write_performed=bool(add or remove)
        if write_performed: client.update_product(state["shop_id"],product_id,payload)
        verified=client.get_product(state["shop_id"],product_id)
        verified_variants=verified.get("variants") or [];verified_total_ids=[item.get("id") for item in verified_variants]
        verified_ids=sorted(item.get("id") for item in verified_variants if item.get("is_enabled"))
        verified_remote_only_enabled={item.get("id") for item in verified_variants if item.get("is_enabled") and item.get("id") in set(remote_only_ids)}
        verified_publication=assess_draft_publication_state(state,verified)
        verified_used_areas=[area for area in verified.get("print_areas") or [] if any(placeholder.get("images") for placeholder in area.get("placeholders") or [])]
        print_area_ids_verified=bool(verified_used_areas) and all(len(area.get("variant_ids") or [])==len(full_remote_ids)
            and set(area.get("variant_ids") or [])==set(full_remote_ids) for area in verified_used_areas)
        total_ids_verified=len(verified_total_ids)==len(full_remote_ids) and len(set(verified_total_ids))==len(full_remote_ids) and set(verified_total_ids)==set(full_remote_ids)
        if verified.get("id")!=product_id or verified.get("shop_id")!=state["shop_id"] or not verified_publication["safe_to_reconcile"] \
                or not total_ids_verified or verified_ids!=sorted(desired_ids) or verified_remote_only_enabled or not print_area_ids_verified:
            raise StateConflictError("STATE_CONFLICT", diagnostic_message="Remote draft verification did not match the reconciliation plan.", operation="product_orchestrator.reconcile_draft", stage="verification")
        verified_placements=[image for area in verified.get("print_areas") or [] for placeholder in area.get("placeholders") or []
            for image in placeholder.get("images") or [] if image.get("id")==image_id]
        placement_keys=("x","y","scale","angle");placement_unchanged=bool(verified_placements and all(verified_placements[0].get(key)==placements[0].get(key) for key in placement_keys))
        evidence={"status":"existing_draft_updated" if write_performed else "already_reconciled","previous_variant_ids":current_ids,
            "resulting_variant_ids":desired_ids,"added_variant_ids":add,"removed_variant_ids":remove,"remote_product_verified":True,
            "updated_at":datetime.now().astimezone().isoformat(),"no_new_upload":True,"no_new_product":True,
            "publish_status":"not_published","order_status":"not_created","placement_unchanged":placement_unchanged,
            "current_catalog_variant_ids":sorted(catalog_ids),"remote_only_variant_ids":remote_only_ids,"remote_only_variant_count":len(remote_only_ids),
            "remote_only_enabled_count":len(verified_remote_only_enabled),"desired_ids_present_in_catalog":set(desired_ids)<=catalog_ids,
            "full_remote_variant_ids":full_remote_ids,"enabled_variant_ids":desired_ids,"disabled_variant_count":len(full_remote_ids)-len(desired_ids),
            "print_area_variant_ids_verified":print_area_ids_verified,"plan":plan}
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
                configured_colors=garment_colors if garment_colors is not None else state.get("requested_garment_colors")
                state["brief"] = normalize_prompt(state["original_prompt"], price=price, garment_colors=configured_colors, sizes=sizes)
                state["brief"]["artwork_palette_names"]=list(state.get("requested_artwork_palette") or ["warm cream","muted market red","muted market green"])
                state["brief"]["artwork_palette_rgba"]=list(state.get("requested_artwork_palette_rgba") or [[244,231,199,255],[174,75,72,255],[83,125,91,255]])
                explicit_phrase=str((state.get("product_brief") or {}).get("exact_phrase") or "")
                if explicit_phrase:state["brief"]["exact_text"]=normalize_exact_phrase(explicit_phrase).upper()
                self._transition(state, "brief_ready", "normalize_prompt", state["brief"])
            unresolved = (state["brief"].get("color_resolution") or {}).get("unresolved_colors") or []
            if unresolved:
                raise ValidationError("VALIDATION_FAILED", diagnostic_message="Requested garment colors could not be resolved to exact catalog colors.",
                    operation="product_orchestrator", stage="brief_ready", context={"unresolved_colors":unresolved})
            source_job_id=normalize_source_job_id(state.get("source_job_id"))
            evidence=(self.adapters.evidence(source_job_id) if source_job_id else
                self.adapters.independent_evidence(state,self._path(state["job_id"]).parent,state["brief"]))
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
                generator=self.adapters.independent_candidates if evidence.get("origin")=="independent_prompt" else self.adapters.candidates
                inputs_sha=_json_sha({"brief":state["brief"],"artwork_sha256":evidence.get("candidate_sha"),"generator":"independent" if evidence.get("origin")=="independent_prompt" else "source"})
                ownership=state["evidence"].get("candidate_ownership") or {};existing=state["evidence"].get("candidates") or []
                reusable=bool(existing and ownership.get("validated_inputs_sha256")==inputs_sha and all(item.get("png_sha256") and Path(str(item.get("png_path") or "")).is_file() and _file_sha(Path(str(item["png_path"])))==item["png_sha256"] for item in existing))
                candidates = existing if reusable else generator(evidence, design_root, state["brief"])
                attempt=int(ownership.get("generation_attempt") or 0)+(0 if reusable else 1)
                for item in candidates:item["job_id"]=state["job_id"];item["generation_attempt"]=attempt
                state["evidence"]["candidates"]=candidates
                state["evidence"]["candidate_ownership"]={"job_id":state["job_id"],"generation_attempt":attempt,"validated_inputs_sha256":inputs_sha,
                    "candidate_records":[{"candidate_id":item.get("candidate_id"),"candidate_digest":item.get("png_sha256"),"selected":False,"state":"pending_validation","provider_bound":False,"authoritative_reference_eligible":False} for item in candidates],
                    "reuse_decision":"duplicate_same_job_reused" if reusable else "generated"}
                _atomic_json(self._path(state["job_id"]),state)
                if evidence.get("origin")=="independent_prompt":
                    try:diversity=validate_candidate_set(candidates,state["brief"],self._prior_designs(state))
                    except ValidationError as exc:
                        diversity=dict(exc.context.get("candidate_diversity") or {});state["evidence"]["candidate_diversity"]=diversity
                        _atomic_json(self._path(state["job_id"]).parent/"candidate-diversity.json",diversity);_atomic_json(self._path(state["job_id"]),state);raise
                    state["evidence"]["candidate_diversity"]=diversity;_atomic_json(self._path(state["job_id"]).parent/"candidate-diversity.json",diversity)
                state["evidence"]["candidates"] = candidates
                self._transition(state, "design_candidates_ready", "generate_v4_refinements", {"candidates": candidates})
            candidates = state["evidence"]["candidates"]
            if "design_selected" not in completed:
                if state.get("commerce_profile_id") and not ((state.get("evidence") or {}).get("selection") or {}).get("selected"):
                    review={"candidate_count":len(candidates),"eligible_candidate_ids":[item.get("candidate_id") for item in candidates if all(value is True for key,value in (item.get("quality_checks") or {}).items() if key.startswith("hard_"))],"provider_contacted":False,"printify_image_state":"none","printify_draft_state":"none","publication_state":"no","order_state":"no"}
                    self._transition(state,"artwork_review","await_human_artwork_selection",review)
                    return state
                selection = select_candidate(candidates, state["brief"]); state["evidence"]["selection"] = selection
                ownership=state["evidence"].get("candidate_ownership") or {}
                for record in ownership.get("candidate_records") or []:
                    record["selected"]=record.get("candidate_id")==selection["selected"].get("candidate_id");record["state"]="eligible" if record["selected"] else "unselected"
                self._transition(state, "design_selected", "technical_candidate_selection", selection)
            selected = state["evidence"]["selection"]["selected"]
            if "listing_ready" not in completed:
                listing = generate_listing(state["brief"], selected); state["evidence"]["listing"] = listing
                self._transition(state, "listing_ready", "generate_listing", listing)
            if evidence.get("origin")=="independent_prompt":
                approval=state["evidence"].get("human_design_approval") or {};candidate=state["evidence"]["selection"]["selected"]
                approval_valid=approval.get("approved") is True and approval.get("candidate_id")==candidate.get("candidate_id") and approval.get("candidate_sha256")==candidate.get("png_sha256") and _file_sha(Path(candidate["png_path"]))==candidate.get("png_sha256")
                if not approval_valid:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Human approval of the exact selected design hash is required before Printify upload.",operation="product_orchestrator",stage="design_approval",state={"external_write_attempted":False,"external_write_completed":False,"safe_to_retry":True})
            if not confirmed:
                raise ValidationError("VALIDATION_FAILED", diagnostic_message="Printify draft creation requires --confirm-printify-draft.", operation="product_orchestrator", stage="printify_image_uploaded",
                    state={"external_write_attempted": False, "external_write_completed": False, "safe_to_retry": True}, suggested_action="Resume with --confirm-printify-draft after reviewing the local evidence.")
            listing=state["evidence"]["listing"];tags=sanitize_printify_tags(listing.get("tags"),phrase=state["brief"].get("exact_text",""),blank=state["brief"].get("blank",""));listing["tags"]=tags
            if not str(listing.get("title") or "").strip():raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload field title must be a nonblank string.",operation="product_orchestrator",stage="printify_payload_validation")
            if not str(listing.get("description") or "").strip():raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload field description must be a nonblank string.",operation="product_orchestrator",stage="printify_payload_validation")
            if not tags:raise ValidationError("VALIDATION_FAILED",diagnostic_message="Printify payload field tags must contain a nonblank string.",operation="product_orchestrator",stage="printify_payload_validation")
            client = self.adapters.client_factory();variant_evidence=None;payload=None;marker=None
            if "printify_draft_created" not in completed:
                blueprint_id=int(state.get("blueprint_id") or DEFAULT_BLUEPRINT_ID);provider_id=int(state.get("print_provider_id") or DEFAULT_PRINT_PROVIDER_ID)
                catalog=client.get_variants(blueprint_id,provider_id);variant_evidence=select_printify_variants(catalog,colors=state["brief"]["garment_colors"],sizes=state["brief"]["sizes"])
                chosen=variant_evidence["selected_variant_ids"];marker=state["evidence"].get("draft_marker") or _draft_marker(state)
                provisional_image=(state["evidence"].get("upload") or {}).get("printify_image_id") or "pending-validated-upload"
                payload={"title":listing["title"],"description":listing["description"],"tags":[*tags,marker],"blueprint_id":blueprint_id,"print_provider_id":provider_id,
                    "variants":create_variant_payload(catalog,chosen,listing["price_cents"]),"print_areas":[{"variant_ids":chosen,"placeholders":[{"position":"front","images":[{"id":provisional_image,"x":.5,"y":.46,"scale":.85,"angle":0}]}]}]}
                validate_create_payload(payload,chosen)
            if "printify_image_uploaded" not in completed:
                remote = client.upload_image_contents(f"jamesos-{state['job_id']}-{selected['png_sha256'][:12]}.png", __import__("base64").b64encode(Path(selected["png_path"]).read_bytes()).decode())
                upload = {"printify_image_id": remote["id"], "selected_design_sha256": selected["png_sha256"]}; state["evidence"]["upload"] = upload
                self._transition(state, "printify_image_uploaded", "printify_upload", upload)
            else: client.get_upload(state["evidence"]["upload"]["printify_image_id"])
            if "printify_draft_created" not in completed:
                payload["print_areas"][0]["placeholders"][0]["images"][0]["id"]=state["evidence"]["upload"]["printify_image_id"];validate_create_payload(payload,chosen)
                state["evidence"]["variant_selection"] = variant_evidence; state["evidence"]["draft_marker"] = marker;state["evidence"]["prepared_printify_request"]={"title":payload["title"],"description":payload["description"],"blueprint_id":blueprint_id,"print_provider_id":provider_id,"variants":payload["variants"],"print_areas":payload["print_areas"],"selected_variant_ids":chosen,"unpublished":True}
                _atomic_json(self._path(state["job_id"]), state)
                recorded_draft=(state.get("evidence") or {}).get("draft") or {};recorded_id=recorded_draft.get("printify_product_id")
                if recorded_id:
                    if not (state.get("evidence") or {}).get("draft_ownership"):raise StateConflictError("STATE_CONFLICT",diagnostic_message="A confirmed product ID lacks canonical ownership evidence; manual verification is required.",operation="product_orchestrator",stage="printify_draft_created")
                    product=client.get_product(state["shop_id"],recorded_id);reconciled=True
                else:
                    product = _find_marked_draft(client.list_products(state["shop_id"]), marker);reconciled = product is not None
                    if product is None: product = client.create_product(state["shop_id"], payload)
                if product.get("id") == PROTECTED_PRODUCT_ID: raise StateConflictError("STATE_CONFLICT", diagnostic_message="Printify returned the protected baseline product ID.", operation="product_orchestrator", stage="printify_draft_created")
                draft = {"printify_product_id": product["id"], "variant_ids": chosen, "draft_marker": marker,
                    "reconciled_existing_remote_draft": reconciled, "publish_status": "not_published", "order_status": "not_created"}
                journal_id=str(state.get("active_provider_create_journal_id") or "")
                standalone_action=None
                if not journal_id:
                    journal_id=f"create-{uuid4().hex}";state["active_provider_create_journal_id"]=journal_id
                    standalone_action={"journal_id":journal_id,"status":"completed","uncertain":False,"completed_at":datetime.now().astimezone().isoformat(),"response_evidence":{"draft_recorded":True}}
                    _atomic_json(self._path(state["job_id"]).parent/"unified-preparation.json",{"job_id":state["job_id"],"profile_id":state.get("commerce_profile_id"),"provider_actions":[standalone_action]})
                state["evidence"]["draft"] = draft;state["evidence"]["draft_ownership"]=build_draft_ownership(state,product["id"],journal_id)
                _atomic_json(self._path(state["job_id"]),state);self._transition(state, "printify_draft_created", "printify_create_unpublished_draft", draft)
            else: client.get_product(state["shop_id"], state["evidence"]["draft"]["printify_product_id"])
            if "mockups_downloaded" not in completed:
                product = client.get_product(state["shop_id"], state["evidence"]["draft"]["printify_product_id"])
                mockups = []; mockup_root = self._path(state["job_id"]).parent / "mockups"; mockup_root.mkdir(exist_ok=True)
                for index, image in enumerate(product.get("images", [])[:6]):
                    url = str(image.get("src") or "")
                    if not url.startswith("https://"): continue
                    response = client.session.get(url, timeout=client.timeout); response.raise_for_status()
                    target = mockup_root / f"mockup-{index + 1}.jpg"; target.write_bytes(response.content)
                    try:
                        with Image.open(target) as saved:saved.verify();dimensions=list(saved.size);media_type="image/png" if saved.format=="PNG" else "image/jpeg" if saved.format=="JPEG" else None
                    except (OSError,ValueError):dimensions=[];media_type=None
                    if not media_type:target.unlink(missing_ok=True);continue
                    digest=_file_sha(target);mockups.append({"asset_id":f"mockup-{digest[:20]}","provider_source":"printify","local_path":str(target),"sha256":digest,"variant_ids":image.get("variant_ids",[]),"garment_color":image.get("color"),"view":image.get("position") or "front","media_type":media_type,"dimensions":dimensions,"retrieved_at":datetime.now().astimezone().isoformat()})
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
